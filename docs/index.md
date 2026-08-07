# CMP 170HX Wiki

**本页介绍什么：** NVIDIA CMP 170HX 是什么，社区从这张卡上恢复了哪些能力，如今哪些功能确实可用，以及根据你的目的接下来应该阅读什么。

CMP 170HX 是一款基于 **GA100** 的加密货币挖矿加速器，使用的就是 NVIDIA A100 同款的 826 mm²、7 nm 晶片。它以两个 SKU 发布：PCI ID `10de:20c2` 的卡报告 8192 MiB，`10de:2082` 的卡报告 10240 MiB；两者在计算能力 8.0 下都提供 70 个流多处理器、4480 个 CUDA 核心和 280 个第三代张量核心。NVIDIA 有意从四个方面对它进行了限制：FP32 FMA 以及每条张量核心路径的 SM 发射速率都通过熔丝降到约 1/32；HBM 容量通过跳线限制为堆叠物理容量的一小部分；PCIe 链路速度被限制为 Gen1，并且在布线的 16 条通道中只能协商为 x4；NVLink 和 ECC 则通过熔丝关闭。一份严谨的 2023 年拆解报告认为，这种组合“guaranteed the uselessness of the GPU”（注定让这颗 GPU 毫无用处），并判断由于固件签名的存在，这些限制无法突破。

在 2023 年到 2026 年 7 月期间，一个分布式社区通过纯软件方式恢复了其中大部分能力，既不刷写 VBIOS，也不伪造签名。当前发布版解锁器是针对 NVIDIA 开源内核模块的一组六个补丁。它使用精心构造的签名载荷重新触发 SEC2 Booter Load，从而打开四个权限级别掩码；随后在 GSP 引导窗口内执行四次寄存器写入：向 `0x0082381c` 写入 `0x88888888`，向 `0x00823820` 写入 `0x00000008`，恢复完整的 SM 发射速率；向 FBPA CFG1 `0x009a0204` 和 MMU LMR `0x00100ce0` 写入相应值，恢复真正的 A100 显存几何布局。实测结果包括：FP32 非张量性能从约 0.39 提升到约 12.6 TFLOPS（增益约为 26x 至 32x），BF16 张量性能从 6.4 提升到 171-193 TFLOPS，FP64 在 torch GEMM 上达到 11.6 TFLOPS（张量路径方面，同一次 clpeak 转储中，标量结果为 6.31 TFLOPS，而 `wmma_fp64` 为 11.96），并且一张 8 GB 卡能够报告并使用 **65536 MiB**。整个过程只增加约一秒的驱动加载时间，会在每次模块加载时重新执行，而且不会向闪存写入任何内容。同一会话中完成基准测试的八张租用卡，测试结果的离散度低于 2.5%，并且 8/8 都通过了完整 VRAM 的逐字节对比完整性测试。

> [!WARNING]
> **在阅读其他任何内容之前，先弄清两件事**
>
> **容量取决于 SKU，不能互换。** 8 GB 卡可以解锁到 **64 GB**。
> 10 GB 卡可以解锁到 **40 GB**，而 40 GB 才是受支持的配置。面向 10 GB 卡的 80 GB
> 驱动分支曾经构建和测试过，但后来被放弃：它会报告 81920 MiB，却在实际使用量
> 超过约 40 GB 后失败。另有一组由脚本驱动的相干寄存器设置，确实能够访问
> 40 GiB 以上的真实显存，但它尚未发布，仍属实验性方案，而且每次触发大约
> 只会产生一个 CUDA 上下文。
>
> **PCIe 速度和 PCIe 位宽是两个不同的问题，也需要两种不同的修复方式。**
> Gen1 到 Gen2 属于*软件*解锁，目前只存在于未发布分支。要突破 x4 *位宽*，
> 则需要在电路板上手工焊接 24 颗交流耦合电容。两者互不影响，任何一个修复
> 都不能替代另一个。

## 今日状态

| 能力 | 状态 | 详情 |
|---|---|---|
| SM 节流移除（算力） | **已发布、稳定** | 两次寄存器写入；可挺过 FLR。[原理](unlock/compute-throttle.md) |
| 8 GB 卡到 64 GB | **已发布、稳定、生产中** | CFG1 `0x02779000`、LMR `0x0000020B`。[显存几何布局](unlock/memory-geometry.md) |
| 10 GB 卡到 40 GB | **已发布、稳定** | CFG1 `0x02669000`、LMR `0x0000028A` |
| 跨重启持久化 | **自动** | 每次 GSP 引导时重新应用；不会刷写任何内容。[安装](procedures/install.md) |
| 多卡机架 | **可工作** | 已测量 8 卡机架；见[多卡](procedures/multi-gpu.md) |
| GPC 时钟偏移 / 欠压 | **经 NVML 可工作** | 8 GB SKU 上为 `[-1000..+1000]` MHz。[调优](operations/tuning.md) |
| 功耗限制（`nvidia-smi -pl`） | **可工作** | 出厂状态为 100-250 W，OC VBIOS 上为 300 W。[供电](operations/power-and-psu.md) |
| PCIe Gen2（链路**速度**） | **可工作，仅限未发布分支** | 不在当前发布版 `master` 中；实地表现具有不确定性。[Gen2](unlock/pcie-gen2.md) |
| PCIe x16（链路**位宽**） | **仅可通过硬件改装** | 24 × 0402 220 nF X7R 电容。[物理改装](operations/physical-mods.md) |
| Gen2 与 x16 同时实现 | **观测过一次** | 6.63-6.67 GB/s，单台机架，2026-07-26，中等置信度 |
| 10 GB 卡到 80 GB | **分支被拒；相干设置仍属实验性** | `80` 分支报告 81920 MiB，但实际使用量超过约 40 GB 就会失败。一次无驱动的相干触发通过了 77.5 GiB 无折叠测试，但每次触发只产生一个 CUDA 上下文。[80 GB](frontier/80gb.md) |
| PCIe Gen3 / Gen4 | **未解决** | 两个代际熔丝都读为 `0x00000001`。[Gen3/Gen4](frontier/pcie-gen3-gen4.md) |
| 超过 70 个 SM | **未解决** | 针对 GPC 禁用熔丝的每条写入路径都已锁存 |
| ECC | **未找到可用手段** | 已通过熔丝关闭，没有遥测，`MASTER_EN` 只读。[ECC](frontier/ecc.md) |
| NVLink | **这块板上不可能实现** | 已通过熔丝关闭。板侧接口 IC 是否安装仍未确定，目前倾向于未安装。[NVLink](frontier/nvlink.md) |
| 点对点（P2P） | **不存在** | [P2P](frontier/p2p.md) |
| MIG | **仅有一份报告，尚未发布** | `0x820840` 的第 0 位；还需要第二张卡和一次拉取请求 |
| 空闲功耗降低 | **没有可用手段** | 只有性能状态 P0；`nvidia-pstated` 返回 `NVAPI_ERROR` |
| 显存时钟控制 | **通过 NVML 被拒**，但打过补丁的模块可以实现 | NVML MEM VF 偏移范围是 `[0..0]`，且不支持 `-lmc`；不过，实际测试中，打过补丁的模块配合一次重启确实降低了 HBM 频率：1728 MHz → 212.2 TF / 181.2 W；1620 MHz（NDIV 60）→ 211.6 TF / 172.9 W；1404 MHz（NDIV 52）→ 210.5 TF / 169.3 W |
| VBIOS 修改 | **解锁手段已被排除** | 容量跳线和 PCIe 代际跳线位于 Davies-Meyer MAC 范围内。未签名的 FwSec 尾部位于该范围之外，确实包含可编辑字段，包括 `0x45E45` 处的板卡功耗上限和 `freqDelta`；但写入这些字段需要 CH341A 夹。[VBIOS](hardware/vbios.md) |

当前发布版 `master` 支持的驱动恰好只有 **`610.43.03`**（默认）和 **`610.43.02`**；使用其他任何版本都会导致构建直接失败。面向 595 / 590 / 580 的移植存在于一个分支中，已经通过源码验证，但从未有人报告成功引导。

## 从这里开始

**“我刚买了一张卡，想让它正常工作。”**
先阅读[这张卡是什么](start/what-is-this-card.md)了解背景，再通过[识别你的卡](start/identify-your-card.md)确认你手中的 SKU（后续所有步骤都取决于此），然后依次阅读[风险](start/risks.md)、[快速上手](start/quick-start.md)和[安装](procedures/install.md)。在给显卡通电之前，务必阅读[散热](operations/cooling.md)和[供电与 PSU](operations/power-and-psu.md)：这张卡采用被动散热，没有风扇；它唯一的 8-pin 插座是 **EPS** 插座，不是 PCIe 插座。把 PCIe 线缆硬插进去会损坏显卡。安装完成后，请通过[验证](procedures/verify.md)确认结果，不要只靠查看 dmesg。

**“我想解锁它，也想知道自己输入的命令究竟做了什么。”**
先阅读[解锁概览](unlock/overview.md)，再阅读[原理](unlock/how-it-works.md)。整个机制可以分为[Falcon 与 Booter](unlock/falcon-and-booter.md)、[权限级别掩码](unlock/privilege-level-masks.md)、[算力节流](unlock/compute-throttle.md)和[显存几何布局](unlock/memory-geometry.md)。如果出现问题，[排障](procedures/troubleshooting.md)会按照你实际看到的完整报错字符串分类。[驱动版本](procedures/driver-versions.md)则解释了为什么驱动版本无法协商、必须固定。

**“我想从寄存器层面理解它的工作方式。”**
先阅读[硬件概览](hardware/overview.md)查看完整规格，再阅读[GA100 晶片](hardware/ga100-silicon.md)、[熔丝与 OTP](hardware/fuses-and-otp.md)、[显存子系统](hardware/memory-subsystem.md)和[PCIe 子系统](hardware/pcie-subsystem.md)。项目中出现的每个地址、数值和回读结果，都收录在[寄存器参考](unlock/register-reference.md)中，并由[寄存器索引](appendix/register-index.md)建立索引。[VBIOS 页面](hardware/vbios.md)则解释了为什么固件攻击路线已经行不通。

**“我想帮助解决剩下的问题。”**
从[状态板](frontier/status-board.md)和[未解问题](frontier/open-questions.md)开始。这两页会按问题的可解决性排序，并为每个问题列出一个具体的下一步实验。其中有几项成本很低：一次三方引导对比就能解决 `RMPcieLinkSpeed` `0x1` 与 `0x2` 的争议；查阅一次头文件就能确定 LMR 量级字段的宽度；修改一个常量并重启一次，就能测试*相干的* 80 GB 三元组是否与 `80` 分支实际发布的非相干三元组表现不同。请先阅读[失败路线](history/dead-ends.md)：大量工作已经投入到如今被关闭的路径上，该页面准确记录了每条路径为何被关闭。

## 本维基如何标记置信

读者必须能一眼分辨既定事实与活跃推测。

- **普通正文表示已确认的事实。** 这类内容不带标记，因为没有必要。某个数字若由代码推导而来，正文会给出源文件；若来自测量，则会说明测量条件。
- `> [!WARNING]` **Experimental** 提示框用于标记未发布分支中的内容，以及任何仅依据单一报告得出的结论。PCIe Gen2 的全部内容都属于这一类别，因为 Gen2 补丁从未合并到 `master`。
- `> [!CAUTION]` 提示框用于标记可能摧毁硬件或静默损坏数据的内容。本维基中最重要的例子并不明显：在 1400 MHz 上限下，+325 MHz 的时钟偏移**会在不引发崩溃的情况下损坏显存**，因此一次运行成功并不能证明该设置是安全的。
- `> [!NOTE]` **Open problem** 提示框用于标记尚未有人解决的问题，并且总会说明已经尝试过什么、下一步应该做什么。

只基于一次观察的结论，会在句子中明确说明，例如“one tester reported”（一位测试者报告）或“a single rig on one day”（一天中的一台机架）。在多个位置出现的数字，已经与唯一的规范值进行过核对；如果两个来源确实存在分歧，且没有证据能够裁定哪一个正确，本维基会明确写出该值未知，而不会悄悄选择一个。完整约定见[如何阅读本维基](start/how-to-read-this-wiki.md)；底层主张的裁决方式见[方法论](appendix/methodology.md)。
