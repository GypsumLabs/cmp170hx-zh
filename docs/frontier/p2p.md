# P2P 与多 GPU

## 本页覆盖内容

两张 CMP 170HX 卡能否直接通信？第三方 `aikitoria/open-gpu-kernel-modules` 的 P2P 补丁做了什么？它如何通过一份有文档记录的三提交 diff 叠加到 [cmpunlocker](../unlock/driver-patches.md) 之上？IOMMU 和 BAR 大小与它有什么关系？目前还有哪些问题没有答案？

**简短结论：这张卡默认没有 P2P。** 没有任何发布版代码启用该功能，资料库中的每一次测量也都报告它不可用。唯一一个有可能改变这一点的第三方补丁，确实能够在解锁器之上构建并加载。这本身就是一个有价值的结果，因为它证明了 cmpunlocker 的构建系统可以与无关的其他驱动 diff 组合使用。此后，一位构建者报告说，该补丁在 GA100 上只能做到一半：对等*数据移动*可以达到 6.25 GB/s，但对等*同步*完全不能工作，这会导致 NCCL 和其他所有集合通信库挂起。这份报告**未经验证**，来自一台主机，且没有独立复现。见[未经验证的报告](#未经验证的报告对等-dma-可用对等同步不可用)。

**第二个简短结论：即使 P2P 能工作，链路仍然会是瓶颈。** 在 PCIe Gen1 x4（约 1.0 GB/s）下，项目中普遍认可的判断是：P2P 受带宽限制，在 Gen3 之前几乎没有多少收益。项目通过软件达到的最高水平是 Gen2 x4，该支持已随 `master` 于 2026-07-29 发布；Gen2 x16 已在两台主机上复现，但仅限于做过 24 颗电容焊接改装的卡。见 [PCIe Gen2](../unlock/pcie-gen2.md) 和 [Gen3/Gen4](pcie-gen3-gen4.md)。

---

## 实测基线：没有 P2P 时的表现

| 观察项 | 结果 | 条件 |
|---|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | **全部 56 对**均为 `False`（具备 P2P 能力的组合：56 对中 0 对） | 8 张解锁卡、所有卡对，包括同一 `PIX` 组内的组合 |
| ggml `-lv 5` 日志 | `peer` / `p2p` / `rpc` 均出现 0 次 | 同一台主机 |
| `nvidia-smi nvlink` | `Device does not have or support Nvlink.` | 同一台主机、8 张解锁的 64 GiB 卡、2026-07-24；资料库中唯一的一次捕获 |
| MIG 档案列表 | `1g.64gb`、ID 0、63.00 GiB、70 SM、5 CE、**P2P No** | 解锁卡上 `nvidia-smi mig -lgip` 唯一提供的档案 |
| 扫描期间的活跃链路 | Gen1 x4、约 1.0 GB/s，在推理负载下没有升速 | 设备报告的最大能力为 Gen2 x16 |

这种缺失不仅体现在遥测数据中，也能在源码树里看到。对发布版 `master` 和全部 12 个未发布分支搜索 `p2p` 与 `peer`，得到的命中恰好只有两类：`build.sh` 模块安装列表中的出厂 `nvidia-peermem.ko` 文件名，以及 Gen2 分支 `0008-pcie-gen2-probe-retrain.patch` 中一行未修改的上下文（`nv_uvm_resume_P2P(pUuid)`）。**没有任何分支包含 P2P 启用代码。**

> [!NOTE]
> **`nvidia-peermem` 不是同一回事**
>
> `build.sh` 会收集并安装 5 个模块：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko` 和 `nvidia-peermem.ko`。`nvidia-peermem` 是出厂的对等显存客户端，用于让第三方 RDMA 硬件访问 GPU 显存。看到它被构建并加载（包括无害的 `Skipping BTF generation for ... nvidia-peermem.ko` 日志）**不能**证明 GPU 到 GPU 的对等访问可用。

### 为什么这很重要：实测代价

在一台 8 卡主机上运行 80 层模型、每张 GPU 分配 10 层，并使用 `-sm layer` 进行拆分时，每生成一个 token 都要经历 **7 次 GPU 到 CPU RAM 再到 GPU 的跳转**，其中一次还会在第 49 层到第 50 层的切换处跨越 NUMA/socket 边界。结果表现为并发能力上限：

| 并发用户数 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| 聚合 tok/s | 17.3 | 21.6 | 25.7 | 28.1 | 38.9 |
| 每用户 tok/s | 17.3 | 10.8 | 6.4 | 3.5 | 2.4 |
| 批处理墙钟时间 (s) | n/a | 11.9 | 20.0 | 36.5 | 52.6 |
| 相对于 1 个用户的扩展 | 1.00x | 1.25x | 1.49x | 1.62x | 2.25x |

这意味着从 1 个用户增加到 16 个用户时，聚合吞吐量只扩展到 **2.25 倍**。源报告将其归因于三个因素共同作用：缺少 P2P/NVLink、流水线中有一次跨 NUMA 跳转，以及链路本身的限制。这是一次在一台虚拟化主机上进行的扫描，链路读数为活跃 Gen1 x4，设备最大能力为 Gen2 x16。张量并行本应最能从对等访问中受益，但在这些链路上，它已经被实测证明是一条失败路线：

| 配置 | Prefill 1k / 4k / 16k (t/s) | Decode (t/s) |
|---|---|---|
| 1 卡 | 839 / 1,092 / 960 | 27.3 |
| PP2（流水线并行） | 829 / 1,084 / 1,167 | 29.1 |
| TP2（张量并行） | 316 / 420 / 416 | 33.7 |

测试对象是 Gen1 x4 下由 vLLM 运行的 Qwen2.5-72B dense AWQ。TP 在 prefill 阶段慢了 2.3 至 2.8 倍，只换来 decode 阶段 23% 的提升。更多信息见 [LLM 推理](../operations/llm-inference.md)。

---

## aikitoria fork

`github.com/aikitoria/open-gpu-kernel-modules` 是 `tinygrad/open-gpu-kernel-modules` 的 fork，创建于 2024-10-14。它的默认分支是 **`610.43.03-p2p`**，与 cmpunlocker 目标版本相同；这个 fork 的分支名从 515 一直延伸到 610.43.03。正是因为版本对齐，分层应用才成为可能：master 的 `build.sh` 遇到 `driver/VERSION` 中未列出的驱动版本（`610.43.03`、`610.43.02`）就会直接失败。

该分支是在一次普通 NVIDIA 发布版导入之上增加的 3 个提交：

| 提交 | 主题 | 范围 |
|---|---|---|
| `452cec62d827` | `610.43.03`（基础导入，2026-07-07） | `README.md`、`kernel-open/Kbuild`、`dp_connectorimpl.cpp`、`nvBldVer.h`、`nvUnixVersion.h`、`version.mk` |
| `9fb650447c7b` | 组合 P2P 改动 | 8 个文件、**+83 / -28** |
| `52670f7fd6a7` | 实验性巨页 `cudaHostRegister` | 7 个文件、**+383 / -97** |
| `2849449f8cd6` | README 更新 | **+245** |

P2P 提交本身修改了以下文件：

| 文件 | 变更 |
|---|---|
| `install.sh` | +7 |
| `kernel-open/nvidia-uvm/uvm_gpu.h` | +7 |
| `kernel-open/nvidia/nv-reg.h` | +1 / -1 |
| `src/nvidia/generated/g_kern_bus_nvoc.c` | +5 / -5 |
| `src/nvidia/src/kernel/gpu/bif/kernel_bif.c` | +3 / -3 |
| `src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c` | +10 |
| `src/nvidia/src/kernel/mem_mgr/io_vaspace.c` | +11 / -10 |
| `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c` | +39 / -9 |

**工作机制：** 在缺少 NVLink 的 GPU 上启用 **BAR1 P2P**，存在 NVLink 时则回退到 NVLink。对于 PCIe 卡对，传输会通过 DMA 直接写入另一张 GPU 的物理地址，而不是绕道主机 RAM。

> [!WARNING]
> **实验性配置：GA100 不在支持范围内**
>
> 该分支的 README 列出 RTX 3090（有 NVLink 时两两使用 NVLink，否则使用 PCIe BAR1）、RTX 4090（PCIe BAR1）和 RTX 5090（PCIe BAR1），并声称同代不同设备之间也支持 P2P。**GA100 不在列表中，而且该补丁从未在 170HX 上验证过。** 它修改的代码路径包括 `kern_bus_gp100.c`（Pascal 及以后架构的 bus 代码）、`io_vaspace.c` 和 `nv_gpu_ops.c`，因此其中可能根本不存在可用的 GA100 分支。

---

## 三提交 diff 工作流

以下是 2026-07-23 随一张成功构建截图发布的准确配方：

```bash
git clone https://github.com/aikitoria/open-gpu-kernel-modules open-gpu-kernel-modules-p2p
git -C open-gpu-kernel-modules-p2p diff --src-prefix=a/ HEAD~3 > ./cmpunlocker/driver/patches/0007-unlock-p2p.patch
cd ./cmpunlocker && sudo install.sh
```

### 为什么能够组合

`driver/build.sh` 会删除并重新解压一棵干净的出厂源码树，然后按照 glob 的字典序，用 `patch -p1` 应用所有匹配 `driver/patches/*.patch` 的文件：

```bash
rm -rf "${SRC_DIR}"
# ... re-extract open-gpu-kernel-modules-${VERSION}.tar.gz ...
for p in "${patches[@]}"; do
    patch -p1 < "${p}"
done
```

脚本在 `set -euo pipefail` 下运行，因此某个 hunk 应用失败时会中止构建，而不是生成一个只打了一部分补丁的模块。将第三方 diff 命名为 `0007-unlock-p2p.patch` 后，它会排在发布版的 `0001`-`0006` 系列之后，于是解锁补丁先应用，P2P 改动再叠加到其上。`--src-prefix=a/` 确保生成 `patch -p1` 所需的 `a/` 和 `b/` 路径前缀。`HEAD~3` 不带第二个修订号，表示将当前工作树与 3 个提交之前的版本做 diff，生成一个包含全部 3 个提交的压平补丁，而不是 3 个独立补丁。

其工作机制已经由代码确认。至于这份特定 diff 是否兼容 610.43.0x，则只有一位测试者报告过，尚未独立复现，因此这份配方的置信度为中等。

> [!CAUTION]
> **你还会同时安装实验性巨页提交**
>
> `HEAD~3..HEAD` 包含 `52670f7fd6a7`。该提交会加速 1G 巨页支持的缓冲区上的 `cudaHostRegister`，并缩小这类映射使用的设备页表。它的作者明确记录过：该功能会自动启用，而且“这条路径跳过了出厂驱动执行的一部分逐 4K 页记账，因此在出厂驱动能够正确处理的某些边缘情况下可能出现异常”。它完全没有经过 GA100 验证。若只想采用 P2P 改动，应单独 cherry-pick 或 format-patch **`9fb650447c7b`**，而不要应用整个范围。

### 配方的实际注意事项

- 按原文抄录，最后一行是 `sudo install.sh`。master 的安装器实际通过 `sudo ./install.sh` 调用；不带路径的 `install.sh` 只有在 `.` 位于 `PATH` 中时才有效。
- fork 自己对 `install.sh` 的改动（+7 行）也会被包含进 diff，但不会产生作用：它修改的是出厂 NVIDIA 安装器脚本，而 cmpunlocker 的 `build.sh` 根本不会运行该脚本。
- **存在文件名冲突风险。** Gen2 现在已经进入 `master`，并占用了 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`，因此在任何当前检出版本中，P2P diff 都必须编号为 `0009` 或更晚。2026-07-29 之前这属于分支合并风险；现在则只是每个分层补丁都必须遵守的编号规则。
- `build.sh` 使用 `curl -L --fail` 获取上游 tarball，且**不会进行校验和或签名验证**。在其上再叠加一份未经验证的 diff，只会进一步放大这一风险。
- 安装之后，`build.sh` 会将 `/sys/module/nvidia/srcversion` 与打过补丁的 `nvidia.ko` 上由 `modinfo -F srcversion` 返回的值进行比较。如果不一致，说明出厂模块在加载竞争中获胜，解锁补丁和 P2P 补丁都没有生效。见[验证](../procedures/verify.md)。

---

## 实测结果

实测结果几乎没有，而这个空白正是本页最重要的信息。

| 项目 | 值 | 条件 | 置信度 |
|---|---|---|---|
| 任意 170HX 上的 `p2pBandwidthLatencyTest` | **未运行** | 没有人发布过带补丁和不带补丁的矩阵 | n/a |
| 未打补丁时报告具备 P2P 能力的卡对 | 56 对中 0 对 | 8 张解锁卡、PyTorch | 高 |
| P2P 补丁能否在 cmpunlocker 上构建并加载 | 可以 | 一位测试者，2026-07-23，截图；该主机还装有 2 张 RTX 3090 | 中 |
| 对纯 170HX 卡对的效果 | 报告为**没有效果** | 一位测试者，没有发布测试输出 | 低 |
| P2P 禁用时的参考带宽 | 42.69-43.91 GB/s | 9-GPU Blackwell 系统、Gen5 x16、**不是 170HX** | 对该系统而言高 |
| P2P 启用时的参考带宽 | 55.59-56.58 GB/s | 同一系统 | 对该系统而言高 |
| 设备到自身的参考带宽 | 1611.24-1665.83 GB/s | 同一系统 | 对该系统而言高 |

Blackwell 的参考数字**不能直接套用**。Gen1 x4、甚至 Gen2 x4 下的 170HX，大约只能达到这些数字的三十分之一到六十分之一；而且该系统的驱动分支只将 3090/4090/5090 列为支持对象。

> [!NOTE]
> **未解问题：该补丁在纯 170HX 主机上是否真的有作用？**
>
> 同一天出现了两份报告。一份带截图记录了“p2p + cmpunlock working”，但测试主机中还装有两张 RTX 3090。另一份则记录说，成功构建之后，“它在 170HX 上似乎没有生效……只有在同一台机器上还有其他型号的 GPU 时才会对它们生效”。这两份报告可能并不矛盾：那台成功的主机恰好就是负面报告所说的唯一能工作的混合型号配置。无论哪一方，都没有发布 `simpleP2P` 或 `p2pBandwidthLatencyTest` 的输出。**要解决这个问题：** 在一台只有 170HX 的双卡主机上，分别使用和不使用分层补丁，发布连通性矩阵。这个测试成本低，结果也明确。

---

## 未经验证的报告：对等 DMA 可用，对等同步不可用

> [!CAUTION]
> **未经验证的社区说法**
>
> 本节的所有内容都来自一位构建者在一台四卡主机上的测试，虽然随附发布了日志，但从未被独立复现。它与上文“效果尚未证实”的判断相矛盾。请把它视为值得核查的线索，而不是已确认的结果。

这份说法是：叠加的 `aikitoria` P2P 补丁确实在 GA100 上生效，但只生效了一半：对等*数据移动*可以工作，而对等*同步*不能工作。

| 测试 | 报告结果 |
|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | 4 卡主机上的全部 12 个有序卡对均为 `True` |
| 卡间 `cudaMemcpyPeer` | **6.25 GB/s**；同一拷贝通过主机内存中转时为 5.70 GB/s |
| 跨进程共享 CUDA IPC 句柄 | 可用 |
| 任意 NCCL 集合通信 | 在传输连接阶段**挂起**：没有错误、没有超时，两张 GPU 都固定在 100% |
| vLLM 自定义 all-reduce | 以同样方式**挂起** |

报告给出的解释是，这两种能力需要满足不同条件。对等拷贝只是让一个 DMA 引擎沿着某个映射搬运数据；而集合通信还需要一张 GPU 向另一张 GPU 的显存写入标志，并让第二张 GPU 上的内核不断自旋，直到观察到这次写入。据报告，不能工作的是后一种模式。这就解释了为什么原始拷贝可以成功，而所有集合通信库不是报错，而是直接挂起。

报告还给出了以下机制解释，但同样没有验证：

- `kbusIsPcieBar1P2PMappingSupported_GH100` 要求两张 GPU 都具备**静态 BAR1**；而静态 BAR1 又要求 BAR1 在一个 512 MB 对齐的偏移处覆盖整个帧缓冲。170HX 的 BAR1 只有 **64 MB**，因此这项检查无法通过。见[BAR 大小](#bar-大小与-resizable-bar-限制)，这也是本页其他问题受到阻碍的同一个 64 MB 限制。
- 随后的邮箱回退会先失败于自身的对齐断言，即 `kern_bus.c` 中的 `(base & RM_PAGE_MASK) == 0`，然后又失败于 `kern_bus_gm200.c` 中的 `remoteWMBoxLocalAddr != ~0ULL`。
- 另外，报告者声称 cmpunlocker 自己的 `P2P` 分支会在 `_kbifInitRegistryOverrides` 中，将 `p2pOverride` 和 `pcieP2PType` 置于一个门控条件之后：从 `pGpu->idInfo.PCIDeviceID` 读取的 `devId == 0x20C2`。但该字段直到 `gpu.c` 的更后面才会填充，因此这道门永远不会打开。上游 aikitoria 提交 `9fb650447c7b` 则会无条件设置这两个值。

如果这一说法最终得到确认，实际影响虽然有限，却确实存在：手写的多 GPU 代码可以在卡之间搬运缓冲区，并把协调工作交给**主机**，因此可能使用对等 DMA；但所有集合通信库都不能使用它，主流推理服务器中的张量并行也就无法使用。报告者在多卡 vLLM 上采用的可用配置是 `NCCL_P2P_DISABLE=1` 加 `--disable-custom-all-reduce`，这恰好就是完全不安装 P2P 补丁时也能工作的配置。对那台主机的推理任务来说，这个补丁实际上没有带来任何收益。

**要解决这个问题：** 在第二台主机上运行 3 个测试：`can_device_access_peer`、计时的 `cudaMemcpyPeer`，以及任意一个 NCCL 集合通信。第三个测试最具决定性；对于已经拥有两张卡并完成补丁构建的人来说，它只需要两分钟。

---

## IOMMU 交互

BAR1 P2P DMA 会将原始物理地址写入另一台设备。只有在 IOMMU 不转换这些地址时，这种方式才能工作。

P2P 分支记录的配置方式是：

```bash
# /etc/default/grub, GRUB_CMDLINE_LINUX_DEFAULT
amd_iommu=on iommu=pt        # AMD
intel_iommu=on iommu=pt      # Intel
sudo update-grub
# install the 610.43.03 driver, run ./install.sh, reboot
```

README 直接说明了要求：IOMMU 必须处于 **passthrough** 模式，而不是转换地址；否则 DMA 会经过 IOMMU 页表，传输就会失败。

> [!CAUTION]
> **Passthrough 模式会削弱 DMA 隔离**
>
> 同一份 README 还警告说，如果运行不受信任的软件或设备，这种配置“非常危险”。`iommu=pt` 意味着设备使用主机物理地址执行 DMA，而 IOMMU 不会对这些访问进行监管。不要在多租户主机上使用该配置。

**ACS 是问题的另一半。** 如果 P2P 已启用但速度很慢，根端口上的 Access Control Services 会迫使所有 GPU 到 GPU 的流量向上经过 CPU 根复合体，从而破坏这个补丁本来要提供的带宽。给出的补救措施按优先顺序为：在 BIOS 中禁用 ACS；使用 `pcie_acs_override=downstream,multifunction` 引导；或者应用 ACS override 内核补丁。需要注意的是，ACS override 同样会破坏 IOMMU 组隔离，因此会进一步叠加上面的安全风险。

为了进行 A/B 测试，可以使用以下配置让 3090 卡对强制走 PCIe BAR1 路径，而不是 NVLink：

```conf
# /etc/modprobe.d/nvidia.conf
options nvidia NVreg_RegistryDwords="RMForceP2PType=1"
```

### cmpunlocker 自身如何处理 IOMMU

| 代码树 | IOMMU 处理方式 |
|---|---|
| `master`（发布版） | **没有处理。** `install.sh` 和 `remove.sh` 完全不包含 `iommu` 或内核命令行相关逻辑 |
| Gen2 代码（现在已进入 `master`） | 将 `intel_iommu=on iommu=pt`（GenuineIntel）或 `amd_iommu=on iommu=pt`（AuthenticAMD）追加到 `/etc/default/grub` 或 `/etc/kernel/cmdline`，并提供 `--no-iommu` 退出选项 |

Gen2 安装器还会在运行时执行以下检查：`grep -qw iommu=pt /proc/cmdline && [[ -d /sys/class/iommu ]] && [[ -n "$(ls -A /sys/class/iommu)" ]]`。它会打印 `IOMMU is already active in passthrough mode on the running kernel`，或者打印 `IOMMU passthrough takes effect after the next reboot`，同时提醒必须在 BIOS 中启用 VT-d / AMD-Vi / SVM。该分支的 `remove.sh` 会从 `*.cmpunlocker.bak` 恢复配置，并打印 `Reverted IOMMU kernel parameters (effective after reboot)`；如果找不到 IOMMU 配置备份，则会报告没有找到备份，并保持内核命令行不变。这来自提交 `6a85e6c`“IOMMU enablement as part of install script”，属于分支代码，并未进入发布版。

实际后果是：**Gen2 代码已经配置了 P2P 补丁所需的全部内容**，因此“Gen2 加 P2P”是今天任何人能够拼出的最接近预配置栈的方案。但还没有人真正把它们组合起来。

以下是一台测试主机上已经验证过的 passthrough 引导结果，可作对照：

```text
Linux 7.1.3-arch2-2, cmdline: intel_iommu=on iommu=pt nowatchdog nvme_load=YES
DMAR: IOMMU enabled
(four DRHD units)
iommu: Default domain type: Passthrough (set via kernel command line)
GPU at 0000:65:00.0, alone in IOMMU group 3
```

另一次 `lspci -vvv` 捕获显示，一张位于 `0000:81:00.0` 的卡处于 IOMMU 组 31。卡独自处于一个 IOMMU 组中，正是 passthrough 配置所希望的状态；但这无法说明根端口之间的 ACS 行为，而后者才是决定 P2P 吞吐量的部分。

免驱动的 [refire 链](../history/tool-lineage.md) 出于不同原因也有类似要求：它需要 `intel_iommu=off` **或** `iommu=pt`，这样当它把巨页地址交给 Booter 时，DMA 物理地址才能等于主机物理地址。

---

## BAR 大小与 Resizable BAR 限制

170HX 暴露出 3 个 BAR，并声明支持 Resizable BAR，但实际上无法调整任何大小。

| BAR | 大小 | 类型 | 观察到的区域基址 | ReBAR 支持的大小 |
|---|---|---|---|---|
| BAR0 | 16 MB（`0x1000000`） | 32 位、不可预取 | `f0000000`（另一台主机为 `0xfa000000`） | 仅 16MB |
| BAR1 | **64 MB** | 64 位、可预取 | `20048000000` | 仅 64MB |
| BAR3 | 32 MB | 64 位、可预取 | `2004c000000` | 仅 32MB |

`lspci -vvv` 报告 `Capabilities: [bb0 v1] Physical Resizable BAR`，而且每个 BAR 恰好只有一个支持的大小；`nvidia-smi` 也给出了相同结论：`BAR1 Memory Usage Total: 64 MiB`。在一张解锁卡上创建的 MIG 实例报告共享 BAR1 为 `0MiB / 64MiB`，同时显存为 `1MiB / 65053MiB`。

**即使显卡宣称拥有 81920 MiB 帧缓冲，BAR1 仍然只有 64 MiB。** 因此，这张卡无法使用大 BAR 或完整显存的主机映射；这也正是 [PRAMIN 窗口](../unlock/memory-geometry.md) 对显存解锁至关重要的原因。

由于 aikitoria 补丁通过 **BAR1** 映射对等显存，这个 64 MiB 且不可调整大小的孔径，就成了整个 GA100 方案的结构性疑问。资料库中没有任何来源能够确定：驱动的 BAR1 P2P 路径能否在 64 MiB 窗口内工作，或者它是否像消费级 4090/5090 配置那样假设存在大 BAR。没有人测试过这一点。

### 发布版 BAR0/PRAMIN 钳制

`0004-bar0-pramin-clamp.patch` 共 20 行，对**两个**设备 ID 都生效。当 `devId == 0x20C2 || devId == 0x2082` 且 `Ram.fbAddrSpaceSizeMb > 0x2000`（8192 MB）时：

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

一张容量为 10240 MB 的 10 GB 卡已经超过 `0x2000`，因此同样会触发这个钳制；一张从 10 GB 解锁到 40 GB 的卡，得到的是基于 8192 MiB 而不是 10240 MiB 计算的 PRAMIN 窗口。这是一个有意保留、只有两行代码规模的常量，任何研究 BAR 行为的人都可以修改它并重新构建。

### Resizable BAR：已经确定的内容与尚未确定的内容

> [!NOTE]
> **未解问题：Large BAR / ReBAR / Above 4G Decoding**
>
> 这个问题于 2026-07-22 14:11 发布，此后一直没有答案。它很重要，因为发布版解锁器会有意钳制 BAR0/PRAMIN 窗口，而显卡声明支持的 ReBAR 似乎又没有提供任何替代大小。**下一步：** 在一张已经训练为 Gen2 的卡上启用 Above 4G Decoding 引导，并回读 ReBAR 能力结构中的大小。如果该能力结构确实只为每个 BAR 列出一个支持大小，那么任何主机侧变通方案都无法解决问题，包括为 UEFI 缺少 ReBAR 支持的主机准备的 `github.com/xCuri0/ReBarUEFI`。

### 多卡时的 BAR 压力

一份二手报告描述了单台服务器中超过 8 张高显存 GPU 时出现 BAR 地址空间问题，但没有记录错误字符串或平台信息。需要强调的是：解锁**不会扩大**任何 BAR，因此 BAR 压力来自每个设备的可调整大小 BAR 孔径，而不是 64 GB 帧缓冲。对于一个拥有 128 条通道的单 socket 平台，在相同聚合带宽下，通道数计算大约支持 7 张 x16 卡（不安装 NVMe 时为 8 张），或者数量多得多的 x4 卡。已有操作者在生产环境中运行 8 卡和 10 卡服务器。

---

## 多 GPU 安装状态

P2P 天生就是多卡主题，而 cmpunlocker 的多卡支持目前只存在于分支中。

| 能力 | `master` | `multiple-cards` / `Gen2` |
|---|---|---|
| 卡枚举 | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082' \| head -1`（仅取第一条匹配） | `mapfile -t PCI_LINES`，取全部匹配，使用 5 个并行数组（BDF、devid、profile、expected_mib、current_mib） |
| 档案 | 根据 `nvidia-smi memory.total` 的阈值判断 `8gb` / `10gb` | `profile_from_devid()`：`20c2 → 8gb`、`2082 → 10gb`，另有第三个 `mixed` 档案 |
| 清单文件 | 无 | `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`，每张 GPU 一行，例如 `0000:0b:00.0 20c2 8gb 65536` |
| `verify.sh` | 不存在 | 对每张 GPU 报告 `OK` / `STOCK` / `MISSING` / `UNEXPECTED`，阈值为 `>= 60000 MiB`（8gb）和 `35000-59999 MiB`（10gb） |

对于解锁本身来说，安装器的这一限制只是表面问题：补丁 `0001` 会在**每次** GSP 启动时读取 `pGpu->idInfo.PCIDeviceID`，并按设备选择显存几何布局。因此，即使 master 的安装器只检查一张卡，多卡主机仍会被完整解锁。一次构建就可以服务一台同时包含 8 GB 和 10 GB 卡的主机。

> [!CAUTION]
> **混合 GPU 主机会误判档案**
>
> `detect_card_profile()` 读取 `nvidia-smi --query-gpu=memory.total ... | head -1`，也就是 **nvidia-smi 顺序中的第一张 GPU**，而不是 `lspci` 找到的 CMP。一台同时安装 RTX 3080 10 GB 和 8 GB 170HX 的主机会从 3080 读出“10GB”，从而选择错误的档案。至少已有两位测试者复现了这一问题；其他 CMP SKU 也曾被误判为 10 GB 170HX 卡。**在混合主机上务必显式传入 `--profile=8gb` 或 `--profile=10gb`。** 这对 P2P 尤其重要，因为据报告，混合型号主机是 P2P 补丁唯一可能有效的配置。

还有两个值得在此说明的多 GPU 限制：

- **Proxmox 直通需要 SeaBIOS，而不是 UEFI/OVMF。** UEFI 会产生看起来与解锁器完全无关的 RM init / adapter 失败。两人曾独立确认，无法复现的问题都源于这一点。
- **`verify.sh` 从不检查 PCIe 代数**，即使是 Gen2 分支谱系也如此。在 `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 中搜索“pcie”都没有命中。必须手动使用 `nvidia-smi` 或 `pcielink.sh` 检查链路状态。

完整安装流程见[多 GPU 操作流程](../procedures/multi-gpu.md)。

---

## P2P 与替代方案的相对位置

| 路径 | 状态 | 阻塞因素 |
|---|---|---|
| NVLink | 已被熔丝禁用（`FUSE_NVLINK_DIS` `0x00820684` = `0x00000007`），从未成功启用 | OTP 熔丝以及被省略的板卡元件；见 [NVLink](nvlink.md) |
| PCIe P2P，发布版解锁器 | 缺失 | 源码树中任何位置都没有相关代码 |
| PCIe P2P，分层补丁 | 能构建并加载。有一份**未经验证**的报告称对等 DMA 达到 6.25 GB/s，但对等同步仍然损坏 | 支持范围尚未确定；据报告集合通信会挂起 |
| 更快链路（Gen2 x4） | 自 2026-07-29 起随 `master` 发布 | 低于已提出的张量并行门槛 |
| 更快链路（Gen2 x16） | 已在两台主机上复现，5.97 至 6.67 GB/s | 需要 24 颗电容焊接改装；超过 90 分钟的烧机稳定性尚未测量 |
| Gen3 / Gen4 | 尚未实现 | 经评估需要一份尚未有人生成的 GSP 补丁 |

已有说法认为，PCIe Gen2 x16 或 Gen3 x4 是张量并行至少值得尝试的门槛。解锁器提供的是 Gen2 **x4**，低于这个门槛。恢复到 x16 需要进行[物理改装](../operations/physical-mods.md)（24 颗 0402 220 nF X7R 电容），而不是软件改动；它只改变通道数，不会改变链路代数。这两个机制彼此独立，不能混为一谈。

在达到该条件之前，实际使用建议不变：采用流水线并行，而不是张量并行；使用 MoE 模型来减少每个 token 的跨设备激活流量。

---

## 未解问题

> [!NOTE]
> **未解问题：P2P 问题集**
>
> 1. **分层补丁能否在两张 170HX 卡之间启用 P2P？** 在一对只有 170HX 的卡上，分别使用和不使用该补丁运行 `simpleP2P` 与 `p2pBandwidthLatencyTest`，并发布矩阵。在这个领域，没有其他测试比它成本更低、结论更明确。
> 2. **补丁中是否真的存在 GA100 代码路径？** 被修改的文件是 Pascal 时代的 bus 代码，加上 VA 空间和 RM API 层。将 `kern_bus_gp100.c` 与 GA100 HAL 对照阅读，无需硬件就能回答这个问题。
> 3. **BAR1 P2P 能否通过 64 MiB 的不可调整大小孔径工作？** 尚未确定。这可能正是负面报告出现的原因。
> 4. **在 Gen1 x4 或 Gen2 x4 下，P2P 是否有价值？** 目前记录在案的主要观点是：“我只会在至少拿到 PCIe Gen 3 后才实现 P2P，否则在这些卡上似乎有点浪费。”这一前提目前尚未满足，也没有证据表明它是否能够实现。
> 5. **硅片中是否存在 P2P 能力位？** 已有一个建议：检查受 FEAT PLM 管辖的 `0x00823804` 寄存器空间是否包含 P2P 能力位，因为解锁器已经能够访问这个区域。还没有人检查过。
> 6. **tinygrad 谱系的设备表是否真的能匹配 170HX？** 上游 P2P 驱动会枚举 A100 以及 CMP 40HX 到 CMP 90HX，但遗漏了 170HX；一个针对 610.x 更新过的 fork 仍然遗漏它。尚不清楚解锁卡会被接受，还是 `Graphics Device` 识别字符串会导致设备匹配失败。向表中加入两个设备 ID 并进行测试，是一项很小的改动。
> 7. **多卡、IOMMU 和 Gen2 是否应该合并进 master，顺序又应如何？** `multiple-cards` 安装器的改动（`b1cb6d8`）自包含，可以单独合并；Gen2 分支则将它们与未经验证的 PCIe 寄存器写入捆绑在一起。

---

## 相关页面

- [PCIe 子系统](../hardware/pcie-subsystem.md)：链路、BAR 和配置空间细节
- [PCIe Gen2 解锁](../unlock/pcie-gen2.md) 和 [Gen3/Gen4](pcie-gen3-gen4.md)
- [NVLink](nvlink.md) 和 [NVLink 硬件](../hardware/nvlink-hardware.md)
- [驱动补丁](../unlock/driver-patches.md)：`0001`-`0006` 系列和构建系统
- [多 GPU 安装](../procedures/multi-gpu.md) 和[验证](../procedures/verify.md)
- [物理改装](../operations/physical-mods.md)：x16 电容改装
- [LLM 推理](../operations/llm-inference.md)：并行测量
- [状态板](status-board.md) 和[未解问题](open-questions.md)
- [术语表](../start/glossary.md)
