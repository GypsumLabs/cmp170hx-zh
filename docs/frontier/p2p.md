# 点对点与多 GPU

## 本页覆盖内容

两张 CMP 170HX 卡能否直接互相通信？第三方 `aikitoria/open-gpu-kernel-modules` P2P 补丁做了什么？它如何以一个文档化的三提交 diff 叠加在[cmpunlocker](../unlock/driver-patches.md) 之上？IOMMU 和 BAR 尺寸与它有什么关系？还有哪些仍是未知？

**短答案：这张卡默认没有点对点。** 没有任何已发布的代码启用它，语料库中的每一项测量都报告它不可用。唯一可能改变这一点的第三方补丁，确实能在解锁之上构建并加载——这本身就是一个有用的结果，因为它证明了 cmpunlocker 的构建系统能与其他无关的驱动 diff 组合。一位构建者此后报告，该补丁在 GA100 上"半工作"：对等*数据移动*以 6.25 GB/s 运行，但对等*同步*完全失效，这会让 NCCL 及所有其它集合库挂起。那份报告**未经验证**，出自一台机架，且无独立复现。见[未验证报告](#未验证报告对等-dma-工作对等同步不)。

**第二个短答案：即便 P2P 工作，链路仍会是瓶颈。** 在 PCIe Gen1 x4（约 1.0 GB/s）下，项目广泛认同的立场是：P2P 受带宽束缚，在 Gen3 之前几乎换不来什么收益。项目在软件上达到的最远是 Gen2 x4，已于 2026-07-29 随 `master` 发布；Gen2 x16 则在两架机上复现过，且只在做了 24 电容焊接改装的卡上。见[PCIe Gen2](../unlock/pcie-gen2.md) 和[Gen3/Gen4](pcie-gen3-gen4.md)。

---

## 测得的基线：没有 P2P 时是什么样

| 观察 | 结果 | 条件 |
|---|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | **全部 56** 对上 `False`（P2P 能力对：56 中 0） | 8 张解锁卡、全部对、包括一个 `PIX` 组内 |
| ggml `-lv 5` 日志 | 零个 `peer` / `p2p` / `rpc` 出现 | 同一机架 |
| `nvidia-smi nvlink` | `Device does not have or support Nvlink.` | 同一机架、8 张解锁 64 GiB 卡、2026-07-24；语料库里唯一捕获 |
| MIG 档位列表 | `1g.64gb`、ID 0、63.00 GiB、70 SMs、5 CEs、**P2P No** | 解锁卡上 `nvidia-smi mig -lgip` 提供的唯一档位 |
| 扫描期间的活链路 | Gen1 x4、约 1.0 GB/s、推理负载下不爬升 | 设备最大报告为 Gen2 x16 |

缺失同样体现在源码树里，而不只在遥测中。对已发布的 `master` 和全部十二个未发布分支搜索 `p2p` 与 `peer`，恰好命中两类：`build.sh` 模块安装列表中的出厂 `nvidia-peermem.ko` 文件名，以及 Gen2 分支 `0008-pcie-gen2-probe-retrain.patch` 中一行未修改的上下文（`nv_uvm_resume_P2P(pUuid)`）。**任何分支都不含 P2P 使能。**

> [!NOTE]
> **`nvidia-peermem` 不是一回事**
>
> `build.sh` 收集并安装五个模块：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko` 和 `nvidia-peermem.ko`。`nvidia-peermem` 是让第三方 RDMA 硬件访问 GPU 内存的出厂对等显存客户端。看到它被构建并加载（包括那行无害的 `Skipping BTF generation for ... nvidia-peermem.ko`）**并非** GPU 到 GPU 对等访问可用的证据。

### 为什么它要紧：测得的代价

在 8 卡、80 层模型（每 GPU 10 层）上采用 `-sm layer` 拆分时，每个生成的 token 要做 **7 次 GPU 到 CPU RAM 再到 GPU 的跳跃**，其中一次在层 49 到 50 的过渡处跨过 NUMA/socket 边界。后果表现为一个并发上限：

| 并发用户 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| 聚合 tok/s | 17.3 | 21.6 | 25.7 | 28.1 | 38.9 |
| 每用户 tok/s | 17.3 | 10.8 | 6.4 | 3.5 | 2.4 |
| 批墙钟时间 (s) | n/a | 11.9 | 20.0 | 36.5 | 52.6 |
| 相对 1 用户的扩展 | 1.00x | 1.25x | 1.49x | 1.62x | 2.25x |

这就是从 1 到 16 用户的 **2.25x 聚合扩展**；源报告把三者合起来当作原因：P2P/NVLink 缺失、一次跨-NUMA 流水线跳跃，以及链路本身。它是一次在单台虚拟化主机上的扫描，链路读作活跃 Gen1 x4，设备上限为 Gen2 x16。张量并行——那个本应从对等访问中受益最多的策略——在这些链路上是一个被实测证明的死路：

| 配置 | Prefill 1k / 4k / 16k (t/s) | Decode (t/s) |
|---|---|---|
| 1 卡 | 839 / 1,092 / 960 | 27.3 |
| PP2（流水线） | 829 / 1,084 / 1,167 | 29.1 |
| TP2（张量） | 316 / 420 / 416 | 33.7 |

Qwen2.5-72B dense AWQ，vLLM，Gen1 x4。TP 在 prefill 阶段差 2.3-2.8x，换来 decode +23%。更多见[LLM 推理](../operations/llm-inference.md)。

---

## aikitoria fork

`github.com/aikitoria/open-gpu-kernel-modules` 是 `tinygrad/open-gpu-kernel-modules` 的一个 fork，创建于 2024-10-14。它的默认分支是 **`610.43.03-p2p`**，与 cmpunlocker 瞄准的驱动版本相同；fork 里的分支名从 515 一直延伸到 610.43.03。正是这个版本对齐，才让叠加变得可行：master 的 `build.sh` 会对任何不在 `driver/VERSION`（`610.43.03`、`610.43.02`）中的驱动版本硬性失败。

分支是在一次普通 NVIDIA 发布导入之上的三个提交：

| 提交 | 主题 | 范围 |
|---|---|---|
| `452cec62d827` | `610.43.03`（基础导入、2026-07-07） | `README.md`、`kernel-open/Kbuild`、`dp_connectorimpl.cpp`、`nvBldVer.h`、`nvUnixVersion.h`、`version.mk` |
| `9fb650447c7b` | 组合 P2P mod | 8 个文件、**+83 / -28** |
| `52670f7fd6a7` | 实验性巨页 `cudaHostRegister` | 7 个文件、**+383 / -97** |
| `2849449f8cd6` | README 更新 | **+245** |

P2P 提交本身碰：

| 文件 | 差 |
|---|---|
| `install.sh` | +7 |
| `kernel-open/nvidia-uvm/uvm_gpu.h` | +7 |
| `kernel-open/nvidia/nv-reg.h` | +1 / -1 |
| `src/nvidia/generated/g_kern_bus_nvoc.c` | +5 / -5 |
| `src/nvidia/src/kernel/gpu/bif/kernel_bif.c` | +3 / -3 |
| `src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c` | +10 |
| `src/nvidia/src/kernel/mem_mgr/io_vaspace.c` | +11 / -10 |
| `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c` | +39 / -9 |

**机制：** 它在 NVLink 缺失的 GPU 上启用 **BAR1 点对点**、存在时回退到 NVLink。对 PCIe 对、传输经 DMA 直接写进另一颗 GPU 的物理地址、而非经主机 RAM 弹跳。

> [!WARNING]
> **实验性：GA100 不是一个受支持配置**
>
> 分支 README 列出 RTX 3090（有 NVLink 就两两、否则 PCIe BAR1）、RTX 4090（PCIe BAR1）和 RTX 5090（PCIe BAR1）、并陈述 P2P 也在同代的不同设备之间工作。**GA100 不在那个列表上、补丁从没在 170HX 上验证过。** 它修改的代码路径是 `kern_bus_gp100.c`（Pascal 及以后的 bus 代码）、`io_vaspace.c` 和 `nv_gpu_ops.c`、所以里面一个工作的 GA100 分支可能根本不存在。

---

## 三提交 diff 工作流

这是 2026-07-23 随一张成功构建的截图贴出的精确配方：

```bash
git clone https://github.com/aikitoria/open-gpu-kernel-modules open-gpu-kernel-modules-p2p
git -C open-gpu-kernel-modules-p2p diff --src-prefix=a/ HEAD~3 > ./cmpunlocker/driver/patches/0007-unlock-p2p.patch
cd ./cmpunlocker && sudo install.sh
```

### 为什么它组合

`driver/build.sh` 删除并重新解压一棵干净的出厂树，然后按 glob（字典序）顺序，用 `patch -p1` 应用**每一个**匹配 `driver/patches/*.patch` 的文件：

```bash
rm -rf "${SRC_DIR}"
# ... 重新解压 open-gpu-kernel-modules-${VERSION}.tar.gz ...
for p in "${patches[@]}"; do
    patch -p1 < "${p}"
done
```

脚本在 `set -euo pipefail` 下运行，因此一个失败的 hunk 会中止构建，而不是产出一个半打补丁的模块。把第三方 diff 命名为 `0007-unlock-p2p.patch`，它会排在已发布的系列 `0001`-`0006` 之后，于是解锁先落地，P2P 改动再叠加其上。`--src-prefix=a/` 保证了 `patch -p1` 所预期的 `a/` 和 `b/` 路径前缀。`HEAD~3` 不带第二个修订，会对着三个提交之前的工作树做 diff，产出一个包含全部三个提交的压扁补丁，而非三个独立的补丁。

机制由代码确认。特定 diff 与 610.43.0x 的兼容性仅由一位测试者报告，未被独立复现，所以请把这份配方视为中等置信度。

> [!CAUTION]
> **你也在安装实验性巨页提交**
>
> `HEAD~3..HEAD` 包含 `52670f7fd6a7`，它为 1G 巨页支持的缓冲加速 `cudaHostRegister`，并缩小这类映射的设备页表。它自己的作者记录道：它会被自动启用，且 "this path skips some of the per-4K-page bookkeeping the stock driver performs, so it may misbehave in edge cases the stock driver handles correctly"（这条路径跳过了出厂驱动所做的一部分每-4K-页记账，因此在出厂驱动能正确处理的一些边缘情况下，它可能会出错）。它没有任何 GA100 验证。若只想取 P2P 改动，请单独 cherry-pick 或 format-patch **`9fb650447c7b`**，而不要取整个范围。

### 配方的实际注意

- 按原文转写，最后一行是 `sudo install.sh`。master 的安装器是以 `sudo ./install.sh` 调用的；不带路径的 `install.sh` 只在 `.` 位于 `PATH` 中时才有效。
- fork 自己对 `install.sh` 的改动（+7 行）会被一并扫进 diff，却毫无作用：它要补丁的文件，是一个 cmpunlocker 的 `build.sh` 从不运行的出厂 NVIDIA 安装器脚本。
- **文件名碰撞危险。** Gen2 现已进入 `master`，已占用 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`，因此 P2P diff 必须对任何当前检出编号为 `0009` 或更晚。在 2026-07-29 之前，这是个分支合并风险；如今它只是每个分层补丁都必须遵守的编号规则。
- `build.sh` 用 `curl -L --fail` 抓取上游 tarball，且**不做任何校验和或签名验证**。在其上再叠加第二个未经验证的 diff，只会放大这一点。
- 安装后，`build.sh` 会比较 `/sys/module/nvidia/srcversion` 与打过补丁 `nvidia.ko` 上的 `modinfo -F srcversion`。不一致意味着出厂模块赢得了加载竞争，解锁和 P2P 补丁都未生效。见[验证](../procedures/verify.md)。

---

## 实测结果

几乎一个都没有——而这个空白正是本页最重要的事。

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| 任何 170HX 上的 `p2pBandwidthLatencyTest` | **没跑** | 没人贴过矩阵、无论带不带补丁 | n/a |
| 报告有能力的 P2P 对、未打补丁 | 56 中 0 | 8 张解锁卡、PyTorch | 高 |
| P2P 补丁在 cmpunlocker 上构建并加载 | 是 | 一位测试者、2026-07-23、截图；机架也含 2x RTX 3090 | 中等 |
| 对纯-170HX 对的效果 | 报告**无** | 一位测试者、没贴测试输出 | 低 |
| 参考 P2P 禁用带宽 | 42.69-43.91 GB/s | 9-GPU Blackwell 系统、Gen5 x16、**不是 170HX** | 高（对该系统） |
| 参考 P2P 启用带宽 | 55.59-56.58 GB/s | 相同系统 | 高（对该系统） |
| 参考设备-到-自身 | 1611.24-1665.83 GB/s | 相同系统 | 高（对该系统） |

Blackwell 的参考数字**不能**套用过来。一张 Gen1 x4、甚至 Gen2 x4 的 170HX，只搬得动那些数字的三十分之一到六十分之一；而且那个系统的驱动分支只把 3090/4090/5090 列为受支持。

> [!NOTE]
> **未解问题：补丁在纯-170HX 主机上做任何事吗？**
>
> 同一天存在两份报告。一份记录在带截图的情况下拿到了 "p2p + cmpunlock working"，机架上还有两张 RTX 3090。另一份记录，在成功构建之后 "it doesn't seem to take effect on the 170HX ... it only has an effect on them if there are other models of GPUs on the same machine"（它在 170HX 上似乎没有生效……只有机器上还有其它型号 GPU 时才对它们起作用）。这两份也许并不冲突：那个成功的机架，恰恰就是负面报告所说的"唯一能工作的混合型号"情形。两边都没人贴出过 `simpleP2P` 或 `p2pBandwidthLatencyTest` 的输出。**能定论它的办法：** 一台纯-170HX 双卡主机的连通性矩阵，分别带与不带分层补丁。这个测试很便宜，结果也不含糊。

---

## 未验证报告：对等 DMA 工作、对等同步不

> [!CAUTION]
> **未验证社区声称**
>
> 本节的一切都出自一台四卡机架上的单一构建者，日志随附贴出，但从未被独立复现。它与上面"effect unproven"（效果未经证实）的立场相矛盾。请把它当作一条值得核查的线索，而非一个结果。

这份声称是：叠加的 `aikitoria` P2P 补丁确实在 GA100 上生效，但只生效一半——对等*数据移动*可用，对等*同步*不行。

| 测试 | 报告结果 |
|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | 4 卡主机上全部 12 个有序对 `True` |
| 跨卡的 `cudaMemcpyPeer` | **6.25 GB/s**、对经主机内存分阶段的同一拷贝 5.70 GB/s |
| 跨进程 CUDA IPC 句柄共享 | 工作 |
| 任何 NCCL 集合 | **在传输连接处挂起**：无错误、无超时、两颗 GPU 都钉在 100 % |
| vLLM 自定义 all-reduce | 同样方式**挂起** |

给出的解释是，这两半的要求不同。一次对等拷贝，是一个 DMA 引擎沿着某个映射搬数据；而一次集合操作，还额外需要一颗 GPU 把一个标志写入另一颗 GPU 的内存，并让第二颗 GPU 上的内核自旋，直到观察到那次写入。被报告失效的，正是第二种模式——这能解释为何一次原始拷贝成功、而所有集合库都挂起而非报错。

为它提供的机制，也未验证：

- `kbusIsPcieBar1P2PMappingSupported_GH100` 要求两颗 GPU 上都有**静态 BAR1**，而静态 BAR1 又要求 BAR1 在一个 512 MB 对齐的偏移量上横跨整个帧缓冲。在 170HX 上，BAR1 是 **64 MB**，所以这项检查无法通过。见[BAR 尺寸](#bar-尺寸与-resizable-bar-限制)，这正是阻塞本页其它内容的同一个 64 MB 约束。
- 邮箱回退随后失败它自己的对齐断言、`kern_bus.c` 里 `(base & RM_PAGE_MASK) == 0`、随后 `kern_bus_gm200.c` 里 `remoteWMBoxLocalAddr != ~0ULL`。
- 另外，报告者声称 cmpunlocker 自己的 `P2P` 分支在 `_kbifInitRegistryOverrides` 里，把 `p2pOverride` 和 `pcieP2PType` 门控在从 `pGpu->idInfo.PCIDeviceID` 读出的 `devId == 0x20C2` 之后；但那个字段直到 `gpu.c` 中更晚的位置才被填充，所以这道门永远不会打开。上游 `aikitoria` 提交 `9fb650447c7b` 则是无条件设置这两者。

如果这个说法成立，实际后果虽窄却真实：手写的多 GPU 代码——在卡之间搬移缓冲、并把协调交给**主机**——能用上对等 DMA；而所有集合库、进而主流推理服务器里的张量并行，都用不上。报告者在多卡 vLLM 上的可用配置是 `NCCL_P2P_DISABLE=1` 加 `--disable-custom-all-reduce`，这恰恰是完全没有 P2P 补丁也能工作的配置。在那架机上，补丁对推理而言等于什么也没买到。

**能定论它的办法。** 用第二架机跑三个测试：`can_device_access_peer`、一次计时的 `cudaMemcpyPeer`，以及任意一个 NCCL 集合。第三个是决定性的，而且对任何手里已有两张卡、并构建好补丁的人来说，只是个两分钟的测试。

---

## IOMMU 交互

BAR1 对等 DMA 会在另一台设备处写入一个原始物理地址，这只有在 IOMMU 不翻译那些地址时才成立。

P2P 分支的文档化设置是：

```bash
# /etc/default/grub, GRUB_CMDLINE_LINUX_DEFAULT
amd_iommu=on iommu=pt        # AMD
intel_iommu=on iommu=pt      # Intel
sudo update-grub
# 安装 610.43.03 驱动、跑 ./install.sh、重启
```

README 直截了当地陈述了要求：IOMMU 必须处于 **passthrough** 模式，即不翻译地址，否则 DMA 会走 IOMMU 页表，传输失败。

> [!CAUTION]
> **Passthrough 模式削弱 DMA 隔离**
>
> 同一个 README 警告，这个配置 "is very dangerous if you run untrusted software or devices"（如果你运行不受信任的软件或设备，会非常危险）。`iommu=pt` 意味着设备以主机物理地址做 DMA，而 IOMMU 不再监管它们。不要把它用在一台多租户主机上。

**ACS 是问题的另一半。** 如果 P2P 被启用却很慢，根端口上的 Access Control Services 会把所有 GPU 到 GPU 的流量都往上推向 CPU 根复合体，从而毁掉这个补丁存在的目的——带宽。给出的补救措施按偏好顺序为：在 BIOS 里禁用 ACS；用 `pcie_acs_override=downstream,multifunction` 引导；或应用一个 ACS 覆盖内核补丁。注意 ACS override 也正是打破 IOMMU 组隔离的东西，所以它会与上面的警告相互叠加。

对 A/B 测试、3090 对可以被强制到 PCIe BAR1 路径而非 NVLink、用：

```conf
# /etc/modprobe.d/nvidia.conf
options nvidia NVreg_RegistryDwords="RMForceP2PType=1"
```

### cmpunlocker 自己对 IOMMU 做什么

| 树 | IOMMU 处理 |
|---|---|
| `master`（已发布的） | **无。** `install.sh` 和 `remove.sh` 完全不含 `iommu` 或内核命令行处理 |
| Gen2 代码（现在在 `master` 里） | 把 `intel_iommu=on iommu=pt`（GenuineIntel）或 `amd_iommu=on iommu=pt`（AuthenticAMD）追加到 `/etc/default/grub` 或 `/etc/kernel/cmdline`、带一个 `--no-iommu` 退出 |

Gen2 安装器还在运行时用 `grep -qw iommu=pt /proc/cmdline && [[ -d /sys/class/iommu ]] && [[ -n "$(ls -A /sys/class/iommu)" ]]` 验证，打印 `IOMMU is already active in passthrough mode on the running kernel`（IOMMU 已在运行中的内核上处于 passthrough 模式）或 `IOMMU passthrough takes effect after the next reboot`（IOMMU passthrough 将在下次重启后生效），并提醒 VT-d / AMD-Vi / SVM 也必须在 BIOS 中开启。那个分支上的 `remove.sh` 从 `*.cmpunlocker.bak` 恢复，并打印 `Reverted IOMMU kernel parameters (effective after reboot)`（已还原 IOMMU 内核参数（重启后生效））；或报告没有找到 IOMMU 配置备份，内核命令行保持原样。那来自提交 `6a85e6c` "IOMMU enablement as part of install script"，是分支代码，未发布。

实际后果：**Gen2 代码已经配置好了 P2P 补丁所需的全部东西**，这让"Gen2 加 P2P"成为任何人今天能拼出的最接近预配置的栈。却没人拼过它。

一个测试机架的一次已验证 passthrough 引导、供对比：

```text
Linux 7.1.3-arch2-2, cmdline: intel_iommu=on iommu=pt nowatchdog nvme_load=YES
DMAR: IOMMU enabled
(four DRHD units)
iommu: Default domain type: Passthrough (set via kernel command line)
GPU at 0000:65:00.0, alone in IOMMU group 3
```

一次分开的 `lspci -vvv` 捕获显示，一张 `0000:81:00.0` 的卡位于 IOMMU 组 31。一张独自待在自己组里的卡，正是 passthrough 设置想要的；但它对根端口之间的 ACS 行为什么也说明不了——而管束 P2P 吞吐的，恰恰是后者。

免驱动 [refire 链](../history/tool-lineage.md) 出于不同原因也有同类要求：它需要 `intel_iommu=off` **或** `iommu=pt`，这样当它把巨页地址交给 Booter 时，DMA 物理地址才能等于主机物理地址。

---

## BAR 尺寸与 Resizable BAR 限制

170HX 暴露三个 BAR，外加一个实际上无法调整任何东西的 Resizable BAR 能力。

| BAR | 大小 | 类型 | 观察到的区域基址 | ReBAR 受支持大小 |
|---|---|---|---|---|
| BAR0 | 16 MB（`0x1000000`） | 32 位、不可预取 | `f0000000`（另一台主机 `0xfa000000`） | 仅 16MB |
| BAR1 | **64 MB** | 64 位、可预取 | `20048000000` | 仅 64MB |
| BAR3 | 32 MB | 64 位、可预取 | `2004c000000` | 仅 32MB |

`lspci -vvv` 报告 `Capabilities: [bb0 v1] Physical Resizable BAR` 带每个 BAR 恰好一个受支持大小、`nvidia-smi` 同意：`BAR1 Memory Usage Total: 64 MiB`。在一张解锁卡上创建的一个 MIG 实例报告 `0MiB / 64MiB` 共享 BAR1 连同 `1MiB / 65053MiB` 显存。

**即便卡宣告 81920 MiB 的帧缓冲，BAR1 也停在 64 MiB。** 因此大-BAR 或全-VRAM 主机映射在这张卡上不可用，这也正是[PRAMIN 窗口](../unlock/memory-geometry.md) 对显存解锁尤为要紧的确切原因。

由于 aikitoria 补丁通过 **BAR1** 映射对等显存，这个 64 MiB、不可调整大小的孔径，就成了悬在 GA100 整个方案之上的结构性问题。语料库中没有任何来源能确认，驱动 BAR1 P2P 路径能否在 64 MiB 窗口内工作，或它是否像消费级 4090/5090 设置那样假设一个大 BAR。没人测过它。

### 已发布的 BAR0/PRAMIN 钳制

`0004-bar0-pramin-clamp.patch` 有 20 行，应用到**两个**设备 ID。当 `devId == 0x20C2 || devId == 0x2082` 且 `Ram.fbAddrSpaceSizeMb > 0x2000`（8192 MB）时：

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

一张 10240 MB 的 10 GB 卡已经超过 `0x2000`，所以钳制同样在那里接合：一张解锁到 40 GB 的 10 GB 卡，会得到一个基于 8192 MiB 而非 10240 MiB 的 PRAMIN 窗口。这是一个刻意的两行级常量，任何想实验 BAR 行为的人都可以改掉它并重新构建。

### Resizable BAR：什么已定论、什么没有

> [!NOTE]
> **未解问题：Large BAR / ReBAR / Above 4G Decoding**
>
> 问题于 2026-07-22 14:11 被贴出，从未得到回答。它很要紧，因为已发布的解锁刻意钳制 BAR0/PRAMIN 窗口，而卡宣告的 ReBAR 能力又似乎不提供任何替代大小。**下一步：** 开启 Above 4G Decoding 引导，在一张 Gen2 训练过的卡上回读 ReBAR 能力的大小。如果能力结构确实为每个 BAR 只列出单个受支持大小，那么任何主机侧变通方案都无济于事——包括面向 UEFI 缺 ReBAR 支持主机的 `github.com/xCuri0/ReBarUEFI`。

### 多卡时的 BAR 压力

一份二手报告描述了单台服务器中，八颗以上高-VRAM GPU 之上的 BAR 地址空间问题，没有捕获错误字符串或平台。一个重要的限定：解锁**不会**增长任何 BAR，所以 BAR 压力来自每设备的可调整大小-BAR 孔径，而非 64 GB 的帧缓冲。对 128 通道的单 socket 平台，通道算术在同样的聚合带宽下，给出约七张 x16 卡（去掉 NVMe 则有八张），或数量多得多的 x4 卡。目前有操作者正以 8 卡和 10 卡服务器在生产运行。

---

## 多 GPU 安装状态

P2P 天生是一个多卡主题，而 cmpunlocker 的多卡支持只在分支里。

| 能力 | `master` | `multiple-cards` / `Gen2` |
|---|---|---|
| 卡枚举 | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082' \| head -1`（仅第一匹配） | `mapfile -t PCI_LINES`、每个匹配、五个平行数组（BDF、devid、档位、expected_mib、current_mib） |
| 档位 | 从 `nvidia-smi memory.total` 阈值 `8gb` / `10gb` | `profile_from_devid()`：`20c2 → 8gb`、`2082 → 10gb`、加一个第三个 `mixed` 档位 |
| 清单文件 | 无 | `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`、每 GPU 一行、例如 `0000:0b:00.0 20c2 8gb 65536` |
| `verify.sh` | 不存在 | 每 GPU `OK` / `STOCK` / `MISSING` / `UNEXPECTED`、阈值 `>= 60000 MiB`（8gb）和 `35000-59999 MiB`（10gb） |

安装器的限制对解锁本身而言只是表面问题：补丁 `0001` 在**每次** GSP 引导时读取 `pGpu->idInfo.PCIDeviceID`，并按设备选择几何布局，所以即使 master 的安装器只检查一张卡，多卡主机也会被完整解锁。一个构建就能服务一台同时含 8 GB 和 10 GB 卡的主机。

> [!CAUTION]
> **混合-GPU 主机误检测档位**
>
> `detect_card_profile()` 读取 `nvidia-smi --query-gpu=memory.total ... | head -1`，那是 **nvidia-smi 顺序中的第一张 GPU**，而非 `lspci` 找到的 CMP。一台同时带有 RTX 3080 10 GB 和 8 GB 170HX 的主机，会从 3080 检测出 "10GB"，从而选错档位。这一点已被至少两位测试者复现；其它 CMP SKU 也曾被误判成 10 GB 170HX 卡。**在混合主机上，务必显式传入 `--profile=8gb` 或 `--profile=10gb`。** 这对 P2P 工作伤害尤甚，因为混合型号主机正是 P2P 补丁据报唯一有效果的配置。

两个更多值得带在这的多 GPU 约束：

- **Proxmox 直通需要 SeaBIOS，而非 UEFI/OVMF。** UEFI 会产生看起来像是利用根本没生效的 RM init / 适配器失败。两人曾独立把"无法复现"归因于此。
- **`verify.sh` 从不检查 PCIe 代数**，即便在 Gen2 分支谱系上也一样。在 `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 中搜索 "pcie"，返回零命中。链路状态必须用 `nvidia-smi` 或 `pcielink.sh` 手工核对。

完整安装路径见[多 GPU 流程](../procedures/multi-gpu.md)。

---

## P2P 相对替代方案的位置

| 路径 | 状态 | 阻塞者 |
|---|---|---|
| NVLink | 熔丝禁用（`FUSE_NVLINK_DIS` `0x00820684` = `0x00000007`）、从未带起 | OTP 熔丝加缺件板卡元件；见[NVLink](nvlink.md) |
| PCIe P2P、已发布的解锁 | 缺失 | 树里任何地方都没有代码 |
| PCIe P2P、分层补丁 | 构建并加载。一个**未验证**报告对等 DMA 在 6.25 GB/s、对等同步仍坏 | 受支持配置未确定；集合被报告挂起 |
| 更快链路（Gen2 x4） | 自 2026-07-29 随 `master` 发布 | 在陈述的张量并行阈值之下 |
| 更快链路（Gen2 x16） | 在两架机上复现、5.97 到 6.67 GB/s | 需要 24 电容焊接改装；90 分钟以上烧机未测 |
| Gen3 / Gen4 | 未达成 | 被评估为需要一个没人生产出来的 GSP 补丁 |

让张量并行值得一试的门槛，据陈述是 **PCIe Gen2 x16 或 Gen3 x4**。解锁器交付的是 Gen2 **x4**，低于这个门槛。恢复 x16 是一处[物理改装](../operations/physical-mods.md)（24 颗 0402 220 nF X7R 电容），不是软件改动；它只改通道数，从不改链路代数。两个机制相互独立，绝不可混为一谈。

在那之前，工作指引不变：用流水线并行，而非张量并行；用 MoE 模型来减少每个 token 的跨设备激活流量。

---

## 未解问题

> [!NOTE]
> **未解问题：P2P 问题集**
>
> 1. **分层补丁在两颗 170HX 卡之间启用 P2P 吗？** 在一个纯-170HX 对上跑 `simpleP2P` 和 `p2pBandwidthLatencyTest`、带和不带补丁、并贴矩阵。这个领域里没有别的东西这么便宜或这么决定性。
> 2. **补丁里到底存在 GA100 代码路径吗？** 修改的文件是 Pascal 时代 bus 代码加 VA 空间和 RM API 层。对 GA100 HAL 读 `kern_bus_gp100.c` 会在无需硬件的情况下回答这个。
> 3. **BAR1 P2P 能在一个 64 MiB 不可调整大小孔径里工作吗？** 未确立。这可能是负面报告存在的原因。
> 4. **P2P 在 Gen1 x4 或 Gen2 x4 下值得吗？** 记录在案的头号立场是 "I would only implement P2P when we get at least PCIe Gen 3, otherwise it seems kind of a waste on these cards"（我只会等到至少拿到 PCIe Gen 3 才实现 P2P，否则在这些卡上似乎有点浪费）。这个前提目前并未满足，而且没有任何证据说明它是否可达。
> 5. **硅片里存在 P2P 能力位吗？** 记录在案的一个建议是检查 `0x00823804` 处 FEAT PLM 管辖的寄存器空间是否携带一个 P2P 能力位、因为解锁已经到达那个块。没人看过。
> 6. **tinygrad 谱系的设备表，究竟能不能匹配一张 170HX？** 上游 P2P 驱动枚举了 A100 和 CMP 40HX 到 CMP 90HX，却略过了 170HX；一个为 610.x 更新的 fork 也仍然略过它。未知一张解锁卡会被接受，还是 `Graphics Device` 识别字符串会打破设备匹配。往表里加两个设备 ID 并测试，只是个微不足道的改动。
> 7. **多卡、IOMMU 和 Gen2 应该合并进 master 吗、以什么顺序？** `multiple-cards` 安装器改动（`b1cb6d8`）自包含、能单独落地；Gen2 分支把未验证 PCIe 寄存器写与它们捆绑。

---

## 相关页面

- [PCIe 子系统](../hardware/pcie-subsystem.md) 看链路、BAR 和配置空间细节
- [PCIe Gen2 解锁](../unlock/pcie-gen2.md) 和 [Gen3/Gen4](pcie-gen3-gen4.md)
- [NVLink](nvlink.md) 和 [NVLink 硬件](../hardware/nvlink-hardware.md)
- [驱动补丁](../unlock/driver-patches.md) 看 `0001`-`0006` 系列和构建系统
- [多 GPU 安装](../procedures/multi-gpu.md) 和[验证](../procedures/verify.md)
- [物理改装](../operations/physical-mods.md) 看 x16 电容改装
- [LLM 推理](../operations/llm-inference.md) 看并行测量
- [状态板](status-board.md) 和[未解问题](open-questions.md)
- [术语表](../start/glossary.md)
