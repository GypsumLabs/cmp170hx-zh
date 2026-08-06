# 能力状态板

> [!WARNING]
> **截至语料库冻结、2026-07-28 的状态**
>
> 下文描述的是来源被捕获那一刻的状态：聊天档案止于 2026-07-28 00:01，仓库快照在 UTC 当日午夜后不久截取。**此后本页内容未再复核。** 漂移已现端倪：快照后一天内，远程 `ecc` 分支被强制更新，因此下文对它的描述是快照，而非实时。见[方法论](../appendix/methodology.md)。

**本页覆盖内容。** 用一张表汇总 NVIDIA CMP 170HX 上每一项目前人尝试解锁的能力，列明其当前状态、实现机制及详细出处。如果你只从本维基链出一页，就链这一页。

简言之：**算力与显存已解决并已发布。** 借助一份打过补丁的 NVIDIA 开源内核模块，8 GB 卡（`10de:20c2`）可变为 64 GB 卡，10 GB 卡（`10de:2082`）变为 40 GB 卡，SM 吞吐全面恢复。**PCIe 链路速度（Gen1 到 Gen2）已解决并已发布**，2026-07-29 合并进 `master`。**PCIe 链路位宽（x4 到 x16）已解决，但需焊接 24 颗电容**，与链路速度是完全独立的成果。**其余一切**（10 GB 卡上的 80 GB、Gen3、Gen4、NVLink、ECC、P2P）要么不稳定，要么被一颗无已知杠杆的熔丝所阻，要么未解决，要么未尝试。80 GB 是最微妙的：一套脚本驱动的连贯寄存器集确实能触及 40 GiB 之后的真实内存，但没有任何可安装的方案能做到，40 GB 仍是 10 GB 卡受支持的配置。

## 如何读状态列

| 标签 | 含义 |
|---|---|
| **Working (shipped)** | 在 cmpunlocker `master` 里，被许多独立测试者复现。 |
| **Working (hardware)** | 需要一次物理板卡改装，不含软件成分。 |
| **Working (shipped, partially)** | 在 `master` 里，但只交付能力的一部分。 |
| **Working (with caveats)** | 可用，但带一个需预先规划的文档化限制。 |
| **Working (hardware + shipped)** | 需要板卡改装加已发布的软件，两半皆已定论。 |
| **Experimental** | 被复现一两次。没有烧机、没有第二台机架，或报告存在已知缺陷。 |
| **Attempted and failed** | 存在一次严肃尝试；结果是负面、不稳定或不可用。 |
| **No known lever** | 阻塞机制已识别，但尚未有人找到绕过它的路径。 |
| **Not attempted** | 记录里没人试过。 |

## 状态板

| 能力 | 状态 | 如何达成 | 读更多 |
|---|---|---|---|
| 算力解锁（SM 节流） | **Working (shipped)** | 带一个超大签名缓冲区发射的 SEC2 Booter Load 打开 `FEAT_OVR_PLM 0x00823804`；驱动随后从主机写 `SS0 0x0082381c = 0x88888888` 和 `SS1 0x00823820 = 0x00000008` | [算力节流](../unlock/compute-throttle.md) |
| 显存：8 GB 卡到 **64 GB** | **Working (shipped)** | `CFG1 0x009a0204 = 0x02779000`、`LMR 0x00100ce0 = 0x0000020B`、`targetFbBytes = 0x0000001000000000` | [显存几何布局](../unlock/memory-geometry.md) |
| 显存：10 GB 卡到 **40 GB** | **Working (shipped)** | `CFG1 = 0x02669000`、`LMR = 0x0000028A`、`targetFbBytes = 0x0000000A00000000` | [显存几何布局](../unlock/memory-geometry.md) |
| 显存：10 GB 卡到 **80 GB** | **Experimental**（`80` 分支本身：attempted and failed） | `80` 分支报告 81920 MiB 然后约 40 GB 之上死掉。分开地、一个免驱动 refire 链发射连贯的 `CFG1 = 0x02779000` + `LMR = 0x0000028B`（解码 `0x10000300`）验证了**无折叠**到 77.5 GiB 的真实不同内存、出厂引导时序下 72 GiB。限制：每次发射在 Xid 154 前约一个 CUDA 上下文、边界之上约 79% 峰值带宽。未发布、不可安装 | [80 GB 问题](80gb.md) |
| PCIe **Gen2**（2.5 到 5 GT/s） | **Working (shipped)** | `0007-pcie-gen2.patch`（+ `0008` 重训练）：25 次 Booter 路由的寄存器写加对 XVE / XP3G 块的主机 BAR0 写。2026-07-29 在提交 `2e0a2c02` 合并进 `master`；master 的 README 现在带 `PCIe Gen 2 speeds | Working` 行 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| PCIe **x16 位宽** | **Working (hardware)** | 把 24 × 0402 220 nF X7R 交流耦合电容焊到通道 4-15（设计编号 C1100-C1350） | [物理改装](../operations/physical-mods.md) |
| PCIe **Gen2 与 x16 一起** | **Working (hardware + shipped)** | 一张卡上上面两者；无额外步骤。已发布捕获：一张卡 6.63-6.67 GB/s、四张各 5.97 GB/s 零 AER 错误 | [物理改装](../operations/physical-mods.md) |
| PCIe **Gen3 / Gen4** | **Attempted and failed** | 无机制。`FUSE_PCIE_GEN3_DIS 0x00820580 = 0x1`；受支持速度向量裁剪在 `0x00000006` | [Gen3 和 Gen4](pcie-gen3-gen4.md) |
| **NVLink** | **No known lever** | 熔丝禁用（`0x00820684 = 0x7`）。特性覆盖块里不存在它的条目、任何分支都没有代码、从未插过桥 | [NVLink](nvlink.md) |
| **ECC** | **No known lever** | 熔断关闭（`OPT_ECC_EN 0x00820228 = 0x00000000`）；`FBPA_ECC_CTRL` MASTER_EN 只读 | [ECC](ecc.md) |
| **P2P**（点对点 DMA） | **Attempted, unresolved** | 一个树外 P2P 补丁对着一个 cmpunlocker 树构建；它在纯-170HX 主机上是否做任何事有争议 | [P2P](p2p.md) |
| **多卡** | **Working (shipped, partially)** | 驱动内补丁按构造是每-GPU 的；多卡*安装器*仅分支 | [多卡](../procedures/multi-gpu.md) |
| **驱动回移植**（595 / 590 / 580） | **Experimental** | `clanker/driver-port` 分支、按主版本的补丁目录。源码验证、从未启动测试 | [驱动版本](../procedures/driver-versions.md) |

## 逐行细节

### 算力解锁

已发布，稳定，而且是整个解锁中唯一能挺过功能级复位（FLR）的部分。`FEAT_OVR_PLM 0x00823804` 位于常电功率岛上，一旦打开便保持开启；`SS0` 和 `SS1` 同样持久。正是这种不对称，让算力先于显存发布。

| 项 | 值 |
|---|---|
| SS0 `0x0082381c` | `0x88888888`（锁定卡读到按晶片而异的值，例如 `0x53540175`） |
| SS1 `0x00823820` | `0x00000008` |
| `FEAT_OVR_PLM 0x00823804` | 打开到 `0xffffffff`（出厂 `0xffffff8f`） |
| 主灭杀熔丝 `0x008203f0` | `0x00000000`，未烧断。正因如此这一切才可行 |
| 实用成功测试 | `FEATURE_READOUT_1 0x00823818 == 0x00000000` |
| 挺过 FLR | 是 |

> [!WARNING]
> **实验性**
>
> 通过设置 `0x820840` 的位 0，MIG 使能被演示，有三份相互佐证的 `nvidia-smi` 输出，并报告为持久生效；但它不在已发布的树里，且只存在 `1g.64gb` 档位。解锁后 INT8/IMMA 吞吐仍被门控，原因无人解释。

### 显存几何布局

几何布局**不**能挺过 FLR 或断电循环。打过补丁的驱动会在每次 GSP 引导时重新应用它，这正是采用驱动补丁而非一次性工具的原因。

| 量 | 8 GB 卡（`10de:20c2`） | 10 GB 卡（`10de:2082`） |
|---|---|---|
| 出厂容量 | 8192 MiB | 10240 MiB |
| 出厂 `CFG1 0x009a0204` | `0x02449000` | `0x02449000` |
| 出厂 `LMR 0x00100ce0` | `0x00000208` | `0x00000288` |
| 解锁容量 | **65536 MiB** | **40960 MiB** |
| 解锁 CFG1 | `0x02779000` | `0x02669000` |
| 解锁 LMR | `0x0000020B` | `0x0000028A` |
| `targetFbBytes` | `0x0000001000000000` | `0x0000000A00000000` |
| 活动 FBPA / 总线宽度 | 16 个 FBPA（8 个 FBP）、4096-bit | 20 个 FBPA（10 个 FBP）、5120-bit |

第三个设备 ID `10de:20b0` 会被 `install.sh` 检测到，但**不**被解锁：驱动内门 `_kgspSec2PostblTimingEnabled()` 只接受 `0x20C2` 和 `0x2082`。

> [!CAUTION]
> **10 GB 卡上的 80 GB 不是一个可用配置**
>
> `80` 分支报告 81920 MiB（85,545,582,592 字节），77 GiB 的 `cudaMalloc` 成功。但在 80 GB 下，触碰超过约 40 GB 的内核会造成致命 GPU 丢失，与功耗上限无关。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 显存测试后的 Xid 154；主导报告症状是挂起。Xid 31 单独出现是旁观者提出的，并未被持故障卡的操作者佐证为*那个*特征。按实际构建，分支编程的是 CFG1 `0x02779000`、LMR `0x0000028A` 和 `fb_length 0x0000001400000000`，这三处彼此矛盾，本身就是一个候选原因。分支 `constants.yaml` 里的 `0x0000028B` 是惰性元数据：`build.sh` 从不读取该文件。见[80 GB 问题](80gb.md)。

> [!WARNING]
> **实验性：连贯的 80 GB 集存在、但不是一个安装路径**
>
> 与分支不同，一个净室 refire 脚本在 2026-07-23 至 2026-07-27 之间，于 10 GB 卡上发射了*连贯*寄存器集（CFG1 `0x02779000` + LMR `0x0000028B`、L2 解码 `0x10000300`），其中至少含一张未改装卡。稠密带标签写/回读在 77.5 GiB 处**无折叠**，出厂引导时序下 72 GiB 通过。限制是实打实的：每次发射在 Xid 154 前约一个 CUDA 上下文，边界之上约 79% 峰值带宽。两位操作者，无烧机。已发布的 master 给 10 GB 卡 **40 GB**，那仍是受支持的配置。

### PCIe：速度和位宽是两个不同的问题

> [!NOTE]
> **不要混为一谈**
>
> Gen1 到 Gen2 是对链路**速度**的**软件**改动。x4 到 x16 是对链路**位宽**的**硬件**改动，源于 NVIDIA 在 16 条通道中的 12 条上缺件了交流耦合电容。两者互不影响：仅做电容改装得到 Gen1 x16；仅用 Gen2 补丁得到 Gen2 x4。

| 方面 | 出厂、无解锁 | 带解锁器 | 电容改装后 |
|---|---|---|---|
| `LnkCap` | `0x00456101` | `0x00456102` | 不变 |
| `LnkCap2` | `0x00000002` | `0x00000006` | 不变 |
| `LnkSta` | `0x1041`（2.5 GT/s、x4） | `0x1042`（5 GT/s、x4） | 2.5 GT/s、**x16** |
| `nvidia-smi` cur/max/width | 1, 1, 4 | 2, 2, 4 | 1, 1, 16 |
| 实测带宽 | 约 0.85 GB/s（Gen1 x4） | 约 1.71 GB/s（Gen2 x4） | 2.88 GB/s（Gen1 x16） |

电容改装规格：**24 颗**（每差分对 2 颗 × 12 条缺件通道），**0402、220 nF（0.22 µF）、X7R、≥6.3 V**，设计编号在 **C1100-C1350** 范围。确认部件为 Taiyo Yuden `MAASJ105SB7224KFCA01`。该取值来自 NVIDIA A100 GA100-883 参考原理图 P1001-B02 第 3 页（"IO: PCIe CONNECTOR"）。24 颗中只装 12 颗会得到 x8，因为 PCIe 位宽协商会回退到下一个合法位宽（16 到 8 到 4 到 1）。改装后得出 x8，说明焊接不完整或桥接，而非存在一个独立的硬件限制。

Gen2 **不在已发布的 master 里**：master 只带补丁 `0001` 到 `0006`，`constants.yaml` 里没有 `pcie:` 块。`0007-pcie-gen2.patch` 存在于分支 `debug-gen2`、`Gen2`、`far` 和 `deced` 上；`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2`、`far` 和 `deced` 上。

> [!WARNING]
> **实验性**
>
> Gen2 并非在每个主机上都训练成功。一个 Intel 平台（ASUS W890 SAGE、Ubuntu 24.04）跨越两个分支、一个外部 fork、两个插槽，以及改装和未改装的卡，都从未达到 Gen2；而一个 AMD HiveOS 主机在完全不做内核命令行改动的情况下就达到了。Gen2 也不会在 VFIO 直通下的虚拟机内训练，Thunderbolt 3 坞则连*解锁本身*都彻底失败，而不仅仅是链路（`Booter Load 0x15 / 0xffff`、`RmInitAdapter failed! (0x62:0xffff:2119)`）。Oculink 可用，因为它本质上就是一块转接卡。
>
> **这可能已被修复。** 2026-07-27 是记录中最后一次 Gen2 状态变化，当天维护者发布了 `deced` 分支，并称硬编码的 `0a:00.0` PCI 地址是 "the big bug that I think was causing all the issues"（我认为它是造成所有问题的那个大 bug），VM 直通被列作唯一已知的剩余情况。语料库冻结前没有测试者报告回来；维基自身的分析认为 `deced` 修改的那个文件（`tools/retrain.sh`）在该谱系上是死代码，这构成一个未解决的冲突。见[死路](../history/dead-ends.md)。

> [!NOTE]
> **Gen2 在 x16 无需额外步骤**
>
> 它就是电容改装加已发布的 Gen2 代码，无需任何额外步骤。首次捕获于 2026-07-26：`PCIe GEN 2@16x`、`ocl_pcie_bw` 6.63-6.67 GB/s、nvtop TX 7.061 GiB/s。第二位构建者贴出了跨两个板修订的四张卡，附 `lspci` 捕获，90 分钟持续负载下零 AER 可纠正或致命错误。迄今无人发布过长时间烧机数据。

### Gen3 和 Gen4

反复尝试皆失败。两个熔丝在两个 170HX SKU 上都读 `0x00000001`：`FUSE_PCIE_GEN23_DIS 0x0082057c` 和 `FUSE_PCIE_GEN3_DIS 0x00820580`。Gen2 补丁尝试经 Booter 将 `0x0082057c` 写零，但**写失败**（`status=0xffff rd=0x00000001`，随后 `SEC2_DEBUG: PCIe xp3g booter FAILED to set OPT_GEN23`）。Gen2 实为经 `CYA_0` / `LINK_CONFIG_0` / XP3G / `PRIV_MISC_1` 覆盖加一次根端口重训练达成。`0x00820580` 从未被任何人写过，也没有任何代码路径请求过高于 2 的目标链路速度。把 PHY 速率强制到 Gen3 能力的 `0x00340036`，链路仍停在 Gen1。Gen4 另被设备所限：追查它的研究者没有 Gen4 能力的主机。

### NVLink

| 寄存器 | 170HX 上的值 | 含义 |
|---|---|---|
| `FUSE_NVLINK_DIS 0x00820684` | `0x00000007` | `[2:0]` 禁用字段的三个位全部置位 |
| `STATUS_OPT_NVLINK 0x00820DB8` | `0x00000007` | 只读镜像一致 |
| `FUSE_NVLINK_DEFECTIVE 0x0082068C` | `0x00000000` | 硅片完好；这是分区、不是产量修复 |
| `PTOP_SCAL_NUM_NVLINK 0x0002246C` | `0x0000000c` | 晶片携带完整 12 链路 GA100 配置 |
| `CTRL_OPT_NVLINK 0x008209B8` | `0x00000000` | 而 `FUSE_EN_SW_OVERRIDE = 0x0`、所以这条路径惰性 |

`0x00823800`-`0x0082382C` 特性覆盖块中任何地方都没有 NVLink 寄存器，因此解锁算力所用的机制在此不适用。任何分支都不含 NVLink 代码。记录中从未有人同时持有一张 170HX 和一块 A100 NVLink 桥，所以连连接器是否对齐都尚未确立。

### ECC

熔断关闭，且无遥测。`OPT_ECC_EN 0x00820228` 在两张 170HX 单元上读 `0x00000000`，在 A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A5000、A6000 和 Drive A100 上读 `0x00000001`。`FBPA_ECC_CTRL 0x009a0470` 读 `0x00000000`，`MASTER_EN`（位 0）只读，对比 A100 上的 `0x00000041`。特性覆盖影子存在且被填充（`FEAT_OVR_ECC 0x0082380c = 0x00888888`、`_1 0x00823810 = 0x002aaaaa`、`_2 0x0082382c = 0x0000000a`），但从未被写过。`nvidia-smi -q` 将每个 ECC 字段报告为 `N/A`。

字面上名为 `ecc` 的分支**不含 ECC 代码**：仅一个提交、"Fixed dual geometry support"，外加一个标准的 64/40 GB `constants.yaml`。

**实际后果：** 解锁的 170HX 没有 ECC 计数器，因此真实容量上限之上的静默损坏，永远不会以错误统计的形式浮出水面。

### P2P

`torch.cuda.can_device_access_peer` 对一个 8 卡主机的全部 56 个对返回 `False`，ggml 日志显示零 P2P 活动，`MIG 1g.64gb` 实例报告 `P2P: No`。一个树外 P2P 补丁成功构建进 cmpunlocker 树，之后一位测试者报告它 "doesn't seem to take effect on the 170HX"（在 170HX 上似乎没生效），只在机器上还有其它型号 GPU 时才有用。同一天另一份 "p2p + cmpunlock working"（p2p + cmpunlock 工作）的报告来自一台也含两张 RTX 3090 的机架，那恰是混合型号的情况，因此两份报告可能并不冲突。纯-170HX 主机上不存在 `p2pBandwidthLatencyTest` 矩阵。

### 多卡

驱动内补丁会在每次 GSP 引导时读取 `pGpu->idInfo.PCIDeviceID`，因此**多卡主机即使使用已发布的 master 也能被正确解锁**，包括混合 8 GB / 10 GB 的主机。master 所缺的是安装器支持：其 `install.sh` 只检查第一张匹配的 GPU（`lspci ... | head -1`），并以单一档位构建。

`multiple-cards` 分支（tip `b1cb6d8`，提交于 2026-07-19T05:41Z，在作者的 `-07:00` 时区为 2026-07-18 当地时间）枚举每个 `10de:20b0|10de:20c2|10de:2082` 设备，构建按-BDF 的档位数组，加入一个设 `SKIP_GEOMETRY_REWRITE=1` 的第三个 `mixed` 档位，将清单持久化到 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`，并新增一个按 PCI 总线 ID 检查每张卡的 `verify.sh`。同一个安装器被并入 `Gen2` 分支，两者均未合并。

### 驱动回移植

| 树 | 版本 | 启动测试过 |
|---|---|---|
| 已发布的 `master` | `610.43.03`（默认）、`610.43.02` | 是、两者 |
| `clanker/driver-port` | `driver/VERSION` 里 12 个、`constants.yaml` 里 5 个（`610.43.03`、`610.43.02`、`595.71.05`、`590.48.01`、`580.105.08`） | **否** |

Master 会对白名单两个条目之外的任何版本硬性失败构建。移植分支加入按主版本划分的补丁目录：`580`（37,034 B）、`590`（37,118 B）、`595`（36,993 B）和 `610`（37,415 B，**与 master 逐字节相同**）。分支自身的 `VERSION` 与 `constants.yaml` 在究竟声称哪些版本上也互不一致，这是一处已被承认的内部不一致。

> [!WARNING]
> **实验性**
>
> 任何 595、590 或 580 构建上都没有启动报告。补丁能干净应用、大小看似合理，这就是全部依据。每分支一个测试者报告 `dmesg | grep SEC2_DEBUG` 和 `POST-BooterLoad verify` 行即可定论。

## 次要能力

| 能力 | 状态 | 备注 |
|---|---|---|
| MIG | **Experimental** | 通过设置 `0x820840` 的位 0，使能被演示并报告为持久；只存在 `1g.64gb` 档位，`-cgi 9,3g.20gb -C` 返回 `Invalid Argument`。未上游化。 |
| Resizable BAR | **Not attempted** | 卡宣告一个 Physical Resizable BAR 能力，据报告被限制在 64 MiB。Master 刻意把两个设备 ID 的 BAR0/PRAMIN 窗口钳制到 8 GiB 出厂偏移量。 |
| SR-IOV | **Not attempted** | 归档的 `lspci -vvv` 捕获中没有出现 SR-IOV 扩展能力，这有提示性，但该捕获是为其它目的做的。 |
| NVENC | **No known lever** | 很可能是硅片缺失：GA100 普遍缺 NVENC 硬件。NVDEC 存在。 |
| Windows | **Not attempted** | 解锁是对 Linux 开源内核模块的补丁，没有 Windows 对应物。免驱动的纯 Python 算力尝试，是唯一可信的便宜实验。 |
| VM 直通 | **Working (with caveats)** | 算力和显存解锁在 Proxmox 下工作，但客户机必须用 **SeaBIOS，而非 UEFI/OVMF**；UEFI 会产生看起来像利用根本没生效的 `RmInitAdapter` 失败。Gen2 不在客户机中训练。 |
| Thunderbolt 3 eGPU | **Attempted and failed** | Booter Load 彻底失败。用裸金属或 Oculink。 |

## 前沿实际在哪

按各项离解决的距离排序，当前难题依次是：**Gen2 合并进 master**（卡在清理上，而非知识上）、**由驱动构建而非发射脚本携带的连贯 80 GB 集**，以及随其而来的 Xid 154 每次发射一个上下文的限制——它如今才是真正的 80 GB 阻塞者，而非折叠；**经 `0x00820580 = 0` 的 Gen3**（从未尝试，但先验很低：经同一 `xp3g` 表对相邻 `0x0082057c` 的写，已在硅片上观察到失败）；**在纯-170HX 对上实测的 P2P**；以及 **ECC**（阻塞机制已识别，但未找到杠杆）。NVLink 是价值最高、却无任何可操作路径的未知。

其中每一项——试过什么、什么证据能定论它——都在[未解问题登记](open-questions.md) 里。
