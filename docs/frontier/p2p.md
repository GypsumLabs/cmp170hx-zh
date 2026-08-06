# 点对点与多 GPU

## 本页覆盖内容

两张 CMP 170HX 卡能否直接互相通信、第三方 `aikitoria/open-gpu-kernel-modules` P2P 补丁做什么、它如何以一个文档化的三提交 diff 分层在[cmpunlocker](../unlock/driver-patches.md) 之上、IOMMU 和 BAR 尺寸与它有什么关系、以及什么仍未知。

**短答案：这张卡默认没有点对点。** 没有出货代码启用它、语料库里每个测量都报告它不可用。那个本可能合理改变它的第三方补丁确实构建并加载在解锁之上、那本身是一个有用结果、因为它证明 cmpunlocker 构建系统与无关驱动 diff 组合。一位构建者此后报告补丁在 GA100 上半个工作：对等*数据移动*以 6.25 GB/s 运行、而对等*同步*完全不管用、那会让 NCCL 和每个其它集合库挂起。那份报告**未验证**、来自一台机架、无独立复现。见[未验证报告](#未验证报告对等-dma-工作对等同步不)。

**第二个短答案：即使 P2P 工作、链路仍会是瓶颈。** 在 PCIe Gen1 x4（约 1.0 GB/s）项目广泛同意的立场是 P2P 是带宽绑定、在 Gen3 前买不到什么。项目在软件里达到的最远是 Gen2 x4、它于 2026-07-29 在 `master` 出货；Gen2 x16 已在两架机上复现、而且只在携带 24 电容焊接改装的卡上。见[PCIe Gen2](../unlock/pcie-gen2.md) 和[Gen3/Gen4](pcie-gen3-gen4.md)。

---

## 测得的基线："no P2P"（无 P2P）看起来什么样

| 观察 | 结果 | 条件 |
|---|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | **全部 56** 对上 `False`（P2P 能力对：56 中 0） | 8 张解锁卡、全部对、包括一个 `PIX` 组内 |
| ggml `-lv 5` 日志 | 零个 `peer` / `p2p` / `rpc` 出现 | 同一机架 |
| `nvidia-smi nvlink` | `Device does not have or support Nvlink.` | 同一机架、8 张解锁 64 GiB 卡、2026-07-24；语料库里唯一捕获 |
| MIG 档位列表 | `1g.64gb`、ID 0、63.00 GiB、70 SMs、5 CEs、**P2P No** | 解锁卡上 `nvidia-smi mig -lgip` 提供的唯一档位 |
| 扫描期间的活链路 | Gen1 x4、约 1.0 GB/s、推理负载下不爬升 | 设备最大报告为 Gen2 x16 |

缺失在源码树里也可见、不只在遥测里。对出货 `master` 和全部十二个未发布分支做 `p2p` 和 `peer` 的 grep 恰好返回两种命中：`build.sh` 模块安装列表里的出厂 `nvidia-peermem.ko` 文件名、和 Gen2 分支 `0008-pcie-gen2-probe-retrain.patch` 里一行未修改上下文（`nv_uvm_resume_P2P(pUuid)`）。**任何分支都不含 P2P 使能。**

> [!NOTE]
> **`nvidia-peermem` 不是一回事**
>
> `build.sh` 收集并安装五个模块：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko` 和 `nvidia-peermem.ko`。`nvidia-peermem` 是让第三方 RDMA 硬件到达 GPU 内存的出厂对等显存客户端。看到它被构建和加载（包括那个无害的 `Skipping BTF generation for ... nvidia-peermem.ko` 行）**不是** GPU 到 GPU 对等访问可用的证据。

### 为什么它要紧：测得的代价

带 `-sm layer` 拆分在一个 8 卡、80 层模型（每 GPU 10 层）上、每个生成的 token 做 **7 次 GPU 到 CPU RAM 到 GPU 跳**、其中一次在层 49 到 50 过渡处跨一个 NUMA/socket 边界。后果以一个并发上限出现：

| 并发用户 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| 聚合 tok/s | 17.3 | 21.6 | 25.7 | 28.1 | 38.9 |
| 每用户 tok/s | 17.3 | 10.8 | 6.4 | 3.5 | 2.4 |
| 批墙钟时间 (s) | n/a | 11.9 | 20.0 | 36.5 | 52.6 |
| 相对 1 用户的扩展 | 1.00x | 1.25x | 1.49x | 1.62x | 2.25x |

那是 **1 到 16 用户 **2.25x** 聚合扩展**、源报告把它归因到三个原因一起：P2P/NVLink 缺失、一次跨-NUMA 流水线跳、和链路。它是一次在单个虚拟化主机上的扫描、其链路读作活 Gen1 x4、设备最大 Gen2 x16。张量并行、那个会从对等访问受益最多的策略、在这些链路上是一个测得的死路：

| 配置 | Prefill 1k / 4k / 16k (t/s) | Decode (t/s) |
|---|---|---|
| 1 卡 | 839 / 1,092 / 960 | 27.3 |
| PP2（流水线） | 829 / 1,084 / 1,167 | 29.1 |
| TP2（张量） | 316 / 420 / 416 | 33.7 |

Qwen2.5-72B dense AWQ 在 vLLM、Gen1 x4。TP 在 prefill 时差 2.3-2.8x、换 +23% decode。更多在[LLM 推理](../operations/llm-inference.md)。

---

## aikitoria fork

`github.com/aikitoria/open-gpu-kernel-modules` 是 `tinygrad/open-gpu-kernel-modules` 的一个 fork、创建于 2024-10-14。它的默认分支是 **`610.43.03-p2p`**、与 cmpunlocker 瞄准的同一个驱动版本、fork 里的分支名从 515 跑到 610.43.03。那个版本对齐正是让分层可行的东西：master 的 `build.sh` 对任何不在 `driver/VERSION`（`610.43.03`、`610.43.02`）里的驱动版本硬失败。

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

这是 2026-07-23 带一个工作构建截图贴出的精确配方：

```bash
git clone https://github.com/aikitoria/open-gpu-kernel-modules open-gpu-kernel-modules-p2p
git -C open-gpu-kernel-modules-p2p diff --src-prefix=a/ HEAD~3 > ./cmpunlocker/driver/patches/0007-unlock-p2p.patch
cd ./cmpunlocker && sudo install.sh
```

### 为什么它组合

`driver/build.sh` 删除并重新解压一棵干净出厂树、然后按 glob（字典序）顺序用 `patch -p1` 应用**每个**匹配 `driver/patches/*.patch` 的文件：

```bash
rm -rf "${SRC_DIR}"
# ... 重新解压 open-gpu-kernel-modules-${VERSION}.tar.gz ...
for p in "${patches[@]}"; do
    patch -p1 < "${p}"
done
```

脚本在 `set -euo pipefail` 下运行、所以一个失败的 hunk 中止构建而非产生一个半打补丁的模块。把第三方 diff 命名成 `0007-unlock-p2p.patch` 把它排在出货系列 `0001`-`0006` 之后、所以解锁先落地、P2P 改动应用在其上。`--src-prefix=a/` 保证 `patch -p1` 预期的 `a/` 和 `b/` 路径前缀。`HEAD~3` 不带第二个修订对三个提交之前的工作树做 diff、产生一个含全部三个提交的压扁补丁、而非三个分开的。

机制被代码确认。特定 diff 与 610.43.0x 的兼容性由一位测试者报告、未被独立复现，所以把配方当中等置信度。

> [!CAUTION]
> **你也在安装实验性巨页提交**
>
> `HEAD~3..HEAD` 含 `52670f7fd6a7`、它为 1G 巨页支持的缓冲加速 `cudaHostRegister` 并为这类映射缩小设备页表。它自己的作者记录它被自动启用、且 "this path skips some of the per-4K-page bookkeeping the stock driver performs, so it may misbehave in edge cases the stock driver handles correctly"（这条路径跳过出厂商驱动执行的某些每-4K-页记账、所以它可能在出厂商驱动正确处理的边缘情况里出错）。它没有任何 GA100 验证。只取 P2P 改动、cherry-pick 或 format-patch **`9fb650447c7b` 单独**、不要整个范围。

### 配方的实际注意

- 按转写、最后一行读 `sudo install.sh`。Master 的安装器被调成 `sudo ./install.sh`；不带路径的 `install.sh` 只在 `.` 在 `PATH` 上时工作。
- fork 自己的 `install.sh` 改动（+7 行）被扫进 diff 却无效果：它补丁的文件是一个 cmpunlocker 的 `build.sh` 从不运行的出厂商 NVIDIA 安装器脚本。
- **文件名碰撞危险。** Gen2 现在在 `master` 里、已经用 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`、所以 P2P diff 必须对任何当前检出编号成 `0009` 或更晚。这在 2026-07-29 前是一个分支合并危险；现在它只是每个分层补丁必须遵守的编号。
- `build.sh` 用 `curl -L --fail` 抓上游 tarball 且**不做任何校验和或签名验证**。在其上分层第二个未验证 diff 放大了那个。
- 安装后、`build.sh` 对比 `/sys/module/nvidia/srcversion` 与打过补丁 `nvidia.ko` 上的 `modinfo -F srcversion`。不匹配意味着出厂模块赢得了加载竞争、解锁和 P2P 补丁都不活跃。见[验证](../procedures/verify.md)。

---

## 实测结果

几乎一个都没有、而那个差距是本页最重要的事。

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| 任何 170HX 上的 `p2pBandwidthLatencyTest` | **没跑** | 没人贴过矩阵、无论带不带补丁 | n/a |
| 报告有能力的 P2P 对、未打补丁 | 56 中 0 | 8 张解锁卡、PyTorch | 高 |
| P2P 补丁在 cmpunlocker 上构建并加载 | 是 | 一位测试者、2026-07-23、截图；机架也含 2x RTX 3090 | 中等 |
| 对纯-170HX 对的效果 | 报告**无** | 一位测试者、没贴测试输出 | 低 |
| 参考 P2P 禁用带宽 | 42.69-43.91 GB/s | 9-GPU Blackwell 系统、Gen5 x16、**不是 170HX** | 高（对该系统） |
| 参考 P2P 启用带宽 | 55.59-56.58 GB/s | 相同系统 | 高（对该系统） |
| 参考设备-到-自身 | 1611.24-1665.83 GB/s | 相同系统 | 高（对该系统） |

Blackwell 参考数字**不**迁移。一张 Gen1 x4、甚至 Gen2 x4 的 170HX 移动那些数字的大约三十分之一到六十分之一、而那个系统的驱动分支只把 3090/4090/5090 列为受支持。

> [!NOTE]
> **未解问题：补丁在纯-170HX 主机上做任何事吗？**
>
> 同日存在两份报告。一份记录带截图拿到 "p2p + cmpunlock working"、在一个也含两张 RTX 3090 的机架上。另一份记录成功构建后 "it doesn't seem to take effect on the 170HX ... it only has an effect on them if there are other models of GPUs on the same machine"（它在 170HX 上似乎没生效……只有当机器上有其它型号 GPU 时才对它们有效）。那两份可能实际不冲突：成功的机架恰恰是负面报告说唯一工作的混合型号情况。两边都没人贴过 `simpleP2P` 或 `p2pBandwidthLatencyTest` 输出。**什么能定论它：** 一个纯-170HX 双卡主机的连通性矩阵、带和不带分层补丁。测试便宜、结果不含糊。

---

## 未验证报告：对等 DMA 工作、对等同步不

> [!CAUTION]
> **未验证社区声称**
>
> 本节一切来自一个单台四卡机架上的单一构建者、带日志贴出、从没被独立复现。它矛盾上面的 "effect unproven"（效果未证明）立场。把它当一个值得检查的线索、不是一个结果。

声称是分层的 `aikitoria` P2P 补丁确实在 GA100 上生效、但只一半：对等*数据移动*工作、对等*同步*不。

| 测试 | 报告结果 |
|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | 4 卡主机上全部 12 个有序对 `True` |
| 跨卡的 `cudaMemcpyPeer` | **6.25 GB/s**、对经主机内存分阶段的同一拷贝 5.70 GB/s |
| 跨进程 CUDA IPC 句柄共享 | 工作 |
| 任何 NCCL 集合 | **在传输连接处挂起**：无错误、无超时、两颗 GPU 都钉在 100 % |
| vLLM 自定义 all-reduce | 同样方式**挂起** |

提供的解释是两半有不同的要求。一次对等拷贝是一个 DMA 引擎走一个映射。一个集合额外地需要一颗 GPU 把标志写进另一颗 GPU 的内存、并让第二颗 GPU 上的一个内核旋转直到它观察到那次写。正是第二个模式被报告不工作、那会解释为什么一次原始拷贝成功、而每个集合库都挂起而非失败。

为它提供的机制、也未验证：

- `kbusIsPcieBar1P2PMappingSupported_GH100` 要求两颗 GPU 上**静态 BAR1**、而静态 BAR1 要求 BAR1 在一个 512 MB 对齐偏移量上横跨整个帧缓冲。在 170HX 上 BAR1 是 **64 MB**、所以检查无法通过。见[BAR 尺寸](#bar-尺寸与-resizable-bar-限制)、它是阻塞本页其它东西的同一个 64 MB 约束。
- 邮箱回退随后失败它自己的对齐断言、`kern_bus.c` 里 `(base & RM_PAGE_MASK) == 0`、随后 `kern_bus_gm200.c` 里 `remoteWMBoxLocalAddr != ~0ULL`。
- 分开地、报告者声称 cmpunlocker 自己的 `P2P` 分支把 `p2pOverride` 和 `pcieP2PType` 门控在 `_kbifInitRegistryOverrides` 里从 `pGpu->idInfo.PCIDeviceID` 读的 `devId == 0x20C2` 之后、但那个字段直到 `gpu.c` 里更晚才被填充、所以门从不打开。上游 `aikitoria` 提交 `9fb650447c7b` 无条件设置两者。

如果这站住、实际后果窄而真实：手写多 GPU 代码在卡之间移动缓冲并把协调留给**主机**、能用对等 DMA、而每个集合库、因此主流推理服务器里的张量并行、都不能。报告者多卡 vLLM 的工作配置是 `NCCL_P2P_DISABLE=1` 加 `--disable-custom-all-reduce`、那恰恰是根本没有 P2P 补丁也工作的配置。在那架机上补丁因此为推理没买到任何东西。

**什么能定论它。** 第二架机跑三个测试：`can_device_access_peer`、一次定时的 `cudaMemcpyPeer`、和任何 NCCL 集合。第三个是决定性的、而且对任何已经有两张卡和补丁构建的人来说是一个两分钟测试。

---

## IOMMU 交互

BAR1 对等 DMA 在另一颗设备处写一个原始物理地址。那只在 IOMMU 不翻译那些地址时工作。

P2P 分支的文档化设置是：

```bash
# /etc/default/grub, GRUB_CMDLINE_LINUX_DEFAULT
amd_iommu=on iommu=pt        # AMD
intel_iommu=on iommu=pt      # Intel
sudo update-grub
# 安装 610.43.03 驱动、跑 ./install.sh、重启
```

README 直接陈述要求：IOMMU 必须处于 **passthrough** 模式、不翻译、否则 DMA 走 IOMMU 页表、传输失败。

> [!CAUTION]
> **Passthrough 模式削弱 DMA 隔离**
>
> 同一个 README 警告这个配置 "is very dangerous if you run untrusted software or devices"（如果你跑不受信任的软件或设备非常危险）。`iommu=pt` 意味着设备用主机物理地址 DMA、IOMMU 不在管束它们。不要把它应用到一个多租户主机。

**ACS 是问题的另一半。** 如果 P2P 被启用却慢、根端口上的 Access Control Services 把所有 GPU 到 GPU 流量都往 CPU 根复合体推、那摧毁补丁存在来提供的带宽。给出的补救、按偏好顺序：在 BIOS 里禁用 ACS；用 `pcie_acs_override=downstream,multifunction` 引导；或应用一个 ACS 覆盖内核补丁。注意 ACS override 也正是打破 IOMMU 组隔离的东西、所以这与上面的警告复合。

对 A/B 测试、3090 对可以被强制到 PCIe BAR1 路径而非 NVLink、用：

```conf
# /etc/modprobe.d/nvidia.conf
options nvidia NVreg_RegistryDwords="RMForceP2PType=1"
```

### cmpunlocker 自己对 IOMMU 做什么

| 树 | IOMMU 处理 |
|---|---|
| `master`（出货） | **无。** `install.sh` 和 `remove.sh` 完全不含 `iommu` 或内核命令行处理 |
| Gen2 代码（现在在 `master` 里） | 把 `intel_iommu=on iommu=pt`（GenuineIntel）或 `amd_iommu=on iommu=pt`（AuthenticAMD）追加到 `/etc/default/grub` 或 `/etc/kernel/cmdline`、带一个 `--no-iommu` 退出 |

Gen2 安装器还在运行时用 `grep -qw iommu=pt /proc/cmdline && [[ -d /sys/class/iommu ]] && [[ -n "$(ls -A /sys/class/iommu)" ]]` 验证、打印 `IOMMU is already active in passthrough mode on the running kernel`（IOMMU 已在运行中的内核上处于 passthrough 模式）或 `IOMMU passthrough takes effect after the next reboot`（IOMMU passthrough 在下一次重启后生效）加一个 VT-d / AMD-Vi / SVM 也必须 BIOS 里开的提醒。那个分支上的 `remove.sh` 从 `*.cmpunlocker.bak` 恢复并打印 `Reverted IOMMU kernel parameters (effective after reboot)`（已还原 IOMMU 内核参数（重启后生效））、或报告没有找到 IOMMU 配置备份、内核命令行保持原样。那是提交 `6a85e6c` "IOMMU enablement as part of install script"、分支代码、不出货。

实际后果：**Gen2 代码已经配置恰好 P2P 补丁要求的东西**、这让 Gen2 加 P2P 成为任何人今天能组装的最接近预配置栈的东西。没人组装过它。

一个测试机架的一次已验证 passthrough 引导、供对比：

```text
Linux 7.1.3-arch2-2, cmdline: intel_iommu=on iommu=pt nowatchdog nvme_load=YES
DMAR: IOMMU enabled
(four DRHD units)
iommu: Default domain type: Passthrough (set via kernel command line)
GPU at 0000:65:00.0, alone in IOMMU group 3
```

一次分开的 `lspci -vvv` 捕获显示一张 `0000:81:00.0` 的卡在 IOMMU 组 31。一张独自在自己组里的卡是 passthrough 设置想要的、但它对根端口之间的 ACS 行为什么都不说、而那正是管束 P2P 吞吐的部分。

免驱动 [refire 链](../history/tool-lineage.md) 出于不同原因有同类要求：它需要 `intel_iommu=off` **或** `iommu=pt`、这样它把巨页地址交给 Booter 时 DMA 物理地址等于主机物理地址。

---

## BAR 尺寸与 Resizable BAR 限制

170HX 暴露三个 BAR 和一个实际上不能调整任何东西的 Resizable BAR 能力。

| BAR | 大小 | 类型 | 观察到的区域基址 | ReBAR 受支持大小 |
|---|---|---|---|---|
| BAR0 | 16 MB（`0x1000000`） | 32 位、不可预取 | `f0000000`（另一台主机 `0xfa000000`） | 仅 16MB |
| BAR1 | **64 MB** | 64 位、可预取 | `20048000000` | 仅 64MB |
| BAR3 | 32 MB | 64 位、可预取 | `2004c000000` | 仅 32MB |

`lspci -vvv` 报告 `Capabilities: [bb0 v1] Physical Resizable BAR` 带每个 BAR 恰好一个受支持大小、`nvidia-smi` 同意：`BAR1 Memory Usage Total: 64 MiB`。在一张解锁卡上创建的一个 MIG 实例报告 `0MiB / 64MiB` 共享 BAR1 连同 `1MiB / 65053MiB` 显存。

**即使卡宣告 81920 MiB 帧缓冲 BAR1 也停在 64 MiB。** 大-BAR 或全-VRAM 主机映射因此在这张卡上不可用、那正是[PRAMIN 窗口](../unlock/memory-geometry.md) 对显存解锁要紧的确切原因。

因为 aikitoria 补丁通过 **BAR1** 映射对等显存工作、这个 64 MiB 不可调整大小的孔径是悬在 GA100 整个方法上的结构问题。语料库里没有来源确立驱动 BAR1 P2P 路径能否在一个 64 MiB 窗口内工作、或它是否假设消费级 4090/5090 设置那样的一个大 BAR。没人测过它。

### 出货 BAR0/PRAMIN 钳制

`0004-bar0-pramin-clamp.patch` 是 20 行、应用到**两个**设备 ID。当 `devId == 0x20C2 || devId == 0x2082` 且 `Ram.fbAddrSpaceSizeMb > 0x2000`（8192 MB）时：

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

一张 10240 MB 的 10 GB 卡已经超过 `0x2000`、所以钳制也在那里接合、一张解锁到 40 GB 的 10 GB 卡得到一个基于 8192 MiB 的 PRAMIN 窗口、而非基于 10240 MiB 的。这是一个刻意的两行级常量、任何实验 BAR 行为的人可以改动并重新构建。

### Resizable BAR：什么已定论、什么没有

> [!NOTE]
> **未解问题：Large BAR / ReBAR / Above 4G Decoding**
>
> 问题在 2026-07-22 14:11 被贴出、从没被回答。它要紧、因为出货解锁刻意钳制 BAR0/PRAMIN 窗口、卡宣告一个看似不提供替代大小的 ReBAR 能力。**下一步：** 带 Above 4G Decoding 启用引导、在一张 Gen2 训练过的卡上回读 ReBAR 能力大小。如果能力结构真列出每个 BAR 单个受支持大小、没有主机侧变通方案帮忙、包括对 UEFI 缺 ReBAR 支持的主机的 `github.com/xCuri0/ReBarUEFI`。

### 多卡时的 BAR 压力

一份二手报告描述单台服务器里八颗以上高-VRAM GPU 之上的 BAR 地址空间问题、没捕获错误字符串或平台。重要的限定：解锁**不**增长任何 BAR、所以 BAR 压力来自每设备可调整大小-BAR 孔径、而非 64 GB 帧缓冲。128 通道单 socket 平台的通道算术对同一聚合带宽给出约七张 x16 卡（八张无 NVMe）或远多 x4 卡。操作者正在生产运行 8 卡和 10 卡服务器。

---

## 多 GPU 安装状态

P2P 天生是一个多卡主题、cmpunlocker 的多卡支持仅分支。

| 能力 | `master` | `multiple-cards` / `Gen2` |
|---|---|---|
| 卡枚举 | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082' \| head -1`（仅第一匹配） | `mapfile -t PCI_LINES`、每个匹配、五个平行数组（BDF、devid、档位、expected_mib、current_mib） |
| 档位 | 从 `nvidia-smi memory.total` 阈值 `8gb` / `10gb` | `profile_from_devid()`：`20c2 → 8gb`、`2082 → 10gb`、加一个第三个 `mixed` 档位 |
| 清单文件 | 无 | `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`、每 GPU 一行、例如 `0000:0b:00.0 20c2 8gb 65536` |
| `verify.sh` | 不存在 | 每 GPU `OK` / `STOCK` / `MISSING` / `UNEXPECTED`、阈值 `>= 60000 MiB`（8gb）和 `35000-59999 MiB`（10gb） |

安装器限制对解锁本身是表面的：补丁 `0001` 在**每次** GSP 引导读 `pGpu->idInfo.PCIDeviceID` 并按设备选几何布局、所以一个多卡主机被完全解锁、即使 master 的安装器只检查一张卡。一个构建服务一个含 8 GB 和 10 GB 卡两者的主机。

> [!CAUTION]
> **混合-GPU 主机误检测档位**
>
> `detect_card_profile()` 读 `nvidia-smi --query-gpu=memory.total ... | head -1`、那是 **nvidia-smi 顺序里的第一张 GPU**、不是 `lspci` 找到的 CMP。一张带 RTX 3080 10 GB 配 8 GB 170HX 的主机从 3080 检测出 "10GB" 并选错档位。被至少两位测试者复现；其它 CMP SKU 也被误检测为 10 GB 170HX 卡。**在混合主机上始终显式传 `--profile=8gb` 或 `--profile=10gb`。** 这特别咬 P2P 工作、因为混合型号主机是 P2P 补丁被报告有任何效果的那一个配置。

两个更多值得带在这的多 GPU 约束：

- **Proxmox 直通需要 SeaBIOS、不要 UEFI/OVMF。** UEFI 产生看起来恰好像利用根本不工作的 RM init / 适配器失败。两人独立把无法复现追到这个。
- **`verify.sh` 从不检查 PCIe 代数**、即使在 Gen2 分支谱系上也如此。grep `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 找 "pcie" 返回零命中。链路状态必须用 `nvidia-smi` 或 `pcielink.sh` 手工检查。

完整安装路径见[多 GPU 流程](../procedures/multi-gpu.md)。

---

## P2P 相对替代方案的位置

| 路径 | 状态 | 阻塞者 |
|---|---|---|
| NVLink | 熔丝禁用（`FUSE_NVLINK_DIS` `0x00820684` = `0x00000007`）、从未带起 | OTP 熔丝加缺件板卡元件；见[NVLink](nvlink.md) |
| PCIe P2P、出货解锁 | 缺失 | 树里任何地方都没有代码 |
| PCIe P2P、分层补丁 | 构建并加载。一个**未验证**报告对等 DMA 在 6.25 GB/s、对等同步仍坏 | 受支持配置未确定；集合被报告挂起 |
| 更快链路（Gen2 x4） | 自 2026-07-29 在 `master` 出货 | 在陈述的张量并行阈值之下 |
| 更快链路（Gen2 x16） | 在两架机上复现、5.97 到 6.67 GB/s | 需要 24 电容焊接改装；90 分钟以上烧机未测 |
| Gen3 / Gen4 | 未达成 | 被评估为需要一个没人生产出来的 GSP 补丁 |

张量并行变得值得尝试的陈述阈值是 **PCIe Gen2 x16 或 Gen3 x4**。解锁器交付 Gen2 **x4**、那在它之下。恢复 x16 是一个[物理改装](../operations/physical-mods.md)（24 x 0402 220 nF X7R 电容）、不是一个软件改动、它只改通道数、从不改链路代数。两个机制独立、绝不可混为一谈。

在那之前、工作指导不变：流水线并行、不要张量并行、用 MoE 模型减少每 token 的跨设备激活流量。

---

## 未解问题

> [!NOTE]
> **未解问题：P2P 问题集**
>
> 1. **分层补丁在两颗 170HX 卡之间启用 P2P 吗？** 在一个纯-170HX 对上跑 `simpleP2P` 和 `p2pBandwidthLatencyTest`、带和不带补丁、并贴矩阵。这个领域里没有别的东西这么便宜或这么决定性。
> 2. **补丁里到底存在 GA100 代码路径吗？** 修改的文件是 Pascal 时代 bus 代码加 VA 空间和 RM API 层。对 GA100 HAL 读 `kern_bus_gp100.c` 会在无需硬件的情况下回答这个。
> 3. **BAR1 P2P 能在一个 64 MiB 不可调整大小孔径里工作吗？** 未确立。这可能是负面报告存在的原因。
> 4. **P2P 在 Gen1 x4 或 Gen2 x4 值得任何东西吗？** 记录在案的头号立场是 "I would only implement P2P when we get at least PCIe Gen 3, otherwise it seems kind of a waste on these cards"（我只会在我们至少得到 PCIe Gen 3 时实现 P2P、否则在这些卡上似乎有点浪费）。那个前提目前未满足、而且没有证据说明它是否可达。
> 5. **硅片里存在 P2P 能力位吗？** 记录在案的一个建议是检查 `0x00823804` 处 FEAT PLM 管辖的寄存器空间是否携带一个 P2P 能力位、因为解锁已经到达那个块。没人看过。
> 6. **tinygrad 谱系设备表甚至匹配一张 170HX 吗？** 上游 P2P 驱动枚举 A100 和 CMP 40HX 到 CMP 90HX 却省略 170HX、一个为 610.x 更新的 fork 也仍省略它。未知一张解锁卡会被接受、还是 `Graphics Device` 识别字符串打破设备匹配。往表加两个设备 ID 并测试是一个琐碎改动。
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
