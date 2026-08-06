# CMP 170HX 维基

**本页涵盖什么：** NVIDIA CMP 170HX 是什么，社区从它身上夺回了什么，如今哪些功能确切可用，以及根据你的来意，下一步该去哪里。

CMP 170HX 是一颗基于 **GA100** 的加密货币挖矿加速器，用的正是 NVIDIA A100 那颗 826 mm² 7 nm 晶片。它分两个 SKU 已发布：PCI ID `10de:20c2` 的卡报告 8192 MiB，`10de:2082` 的卡报告 10240 MiB，两者在计算能力 8.0 下都提供 70 个流式多处理器、4480 个 CUDA 核和 280 个第三代张量核。NVIDIA 以四种刻意阉割的方式销售它：针对 FP32 FMA 和每一条张量核路径，SM 发射速率都被熔断至约 1/32；HBM 容量被跳线限制到堆叠物理承载量的一小部分；PCIe 链路被限制在 Gen1 速度，且只能协商出 16 条连线中的 x4；NVLink 和 ECC 被熔断关闭。2023 年一份细致的拆解认定，这个组合"guaranteed the uselessness of the GPU"（注定了 GPU 的一无是处），并因固件签名而判定这些上限无法打破。

在 2023 到 2026 年 7 月之间，一个分布式社区用纯软件、在不刷写 VBIOS、不伪造签名的情况下夺回了其中大部分。已发布解锁器是对 NVIDIA 开源内核模块的六补丁集。它用一个精心构造的签名载荷重新触发 SEC2 Booter Load，以打开四个权限级别掩码，然后在 GSP 引导窗口内做四次寄存器写：`0x0082381c` = `0x88888888` 和 `0x00823820` = `0x00000008` 恢复完整的 SM 发射速率，FBPA CFG1 `0x009a0204` 加 MMU LMR `0x00100ce0` 则恢复真正的 A100 显存几何布局。实测结果：FP32 非张量从约 0.39 到约 12.6 TFLOPS（26x 到 32x 增益），BF16 张量从 6.4 到 171-193 TFLOPS，FP64 在一个 torch GEMM 上到 11.6 TFLOPS（张量路径：同一次 clpeak 转储中，标量测得 6.31 TFLOPS，而 `wmma_fp64` 测得 11.96），而一张 8 GB 卡报告并使用 **65536 MiB**。整个序列大约耗时一秒的驱动加载，在每次模块加载时重跑，且不向闪存写任何东西。同一会话中做过基准测试的八张租用卡，彼此离散度不到 2.5%，并且 8/8 通过了全 VRAM 逐字节对比的完整性测试。

> [!WARNING]
> **在阅读其他任何内容之前，先弄清两件事**
>
> **容量由 SKU 决定且不可互换。** 8 GB 卡解锁到 **64 GB**。
> 10 GB 卡解锁到 **40 GB**，40 GB 才是受支持的配置。10 GB 卡的 80 GB
> 驱动分支曾被构建、测试，随后被放弃：它报告 81920 MiB，但实际使用
> 超过约 40 GB 就会失败。另有一套脚本驱动的相干寄存器组确实能触达
> 40 GiB 之后的真实显存，但它尚未发布、属于实验性质，而且每次触发
> 大约只会产生一个 CUDA 上下文。
>
> **PCIe 速度和 PCIe 位宽是两个不同的问题，需要两种不同的修复。**
> Gen1 到 Gen2 是一个*软件*解锁，只存在于未发布的分支上。要超越
> x4 *位宽*，需要在板上手工焊接 24 颗交流耦合电容。两者互不相干，
> 谁也替代不了谁。

## 今日状态

| 能力 | 状态 | 详情 |
|---|---|---|
| SM 节流移除（算力） | **已发布、稳定** | 两次寄存器写；挺过 FLR。[原理](unlock/compute-throttle.md) |
| 8 GB 卡到 64 GB | **已发布、稳定、生产中** | CFG1 `0x02779000`、LMR `0x0000020B`。[显存几何布局](unlock/memory-geometry.md) |
| 10 GB 卡到 40 GB | **已发布、稳定** | CFG1 `0x02669000`、LMR `0x0000028A` |
| 跨重启持久化 | **自动** | 每次 GSP 引导时重新应用；不向闪存写任何内容。[安装](procedures/install.md) |
| 多卡机架 | **可工作** | 已实测 8 卡机架；见[多卡](procedures/multi-gpu.md) |
| GPC 时钟偏移 / 欠压 | **经 NVML 可工作** | 8 GB SKU 上 `[-1000..+1000]` MHz。[调优](operations/tuning.md) |
| 功耗限制（`nvidia-smi -pl`） | **可工作** | 出厂 100-250 W、OC VBIOS 上 300 W。[供电](operations/power-and-psu.md) |
| PCIe Gen2（链路**速度**） | **可工作、仅未发布分支** | 不在已发布 `master` 里；实地表现不确定。[Gen2](unlock/pcie-gen2.md) |
| PCIe x16（链路**位宽**） | **仅硬件改装** | 24 × 0402 220 nF X7R 电容。[物理改装](operations/physical-mods.md) |
| Gen2 与 x16 一起 | **观测过一次** | 6.63-6.67 GB/s，单台机架，2026-07-26，中等置信 |
| 10 GB 卡到 80 GB | **分支被拒；相干寄存器组仍属实验** | `80` 分支报告 81920 MiB，但实际使用超过约 40 GB 就失败。一次无驱动的相干触发通过了 77.5 GiB 无折叠测试，但每次触发只产生一个 CUDA 上下文。[80 GB](frontier/80gb.md) |
| PCIe Gen3 / Gen4 | **未解决** | 两个代熔丝都读 `0x00000001`。[Gen3/Gen4](frontier/pcie-gen3-gen4.md) |
| 超过 70 个 SM | **未解决** | 到 GPC-禁用熔丝的每条写路径都被锁存 |
| ECC | **未找到杠杆** | 熔断关闭，无遥测，`MASTER_EN` 只读。[ECC](frontier/ecc.md) |
| NVLink | **这块板上不可能** | 熔断关闭。板侧接口 IC 是否焊有元件尚无定论，倾向于没有。[NVLink](frontier/nvlink.md) |
| 点对点（P2P） | **缺失** | [P2P](frontier/p2p.md) |
| MIG | **仅一份报告，未发布** | `0x820840` 的位 0；等待第二张卡和一次拉取请求 |
| 空转功耗降低 | **无杠杆** | 只存在性能状态 P0；`nvidia-pstated` 返回 `NVAPI_ERROR` |
| 显存时钟控制 | **经 NVML 被拒**，但用打过补丁的模块可以做到 | NVML MEM VF 偏移范围是 `[0..0]` 且 `-lmc` 不受支持，然而，一个打过补丁的模块加一次重启确实在实践中降低了 HBM 频率：1728 MHz → 212.2 TF / 181.2 W；1620 MHz（NDIV 60）→ 211.6 TF / 172.9 W；1404 MHz（NDIV 52）→ 210.5 TF / 169.3 W |
| VBIOS 修改 | **对解锁杠杆关闭** | 容量跳线和 PCIe 代跳线都落在 Davies-Meyer MAC 范围内。未签名的 FwSec 尾在它外面，确实持有可编辑字段，包括 `0x45E45` 处的板功耗上限和 `freqDelta`，但写入它们需要一个 CH341A 夹。[VBIOS](hardware/vbios.md) |

已发布的 `master` 上受支持的驱动恰好是 **`610.43.03`**（默认）和 **`610.43.02`**；其它任何版本都会导致构建直接失败。到 595 / 590 / 580 的移植存在于一个分支上，经源码验证，但从未被报告引导成功过。

## 从这里开始

**"我刚买了一张卡，想让它正常工作。"**
先读[这张卡是什么](start/what-is-this-card.md)了解背景，再用[识别你的卡](start/identify-your-card.md)确定你持有哪个 SKU（这决定下游的一切），然后依次看[风险](start/risks.md)、[快速上手](start/quick-start.md)和[安装](procedures/install.md)。在给任何东西上电之前，务必读[散热](operations/cooling.md)和[供电与 PSU](operations/power-and-psu.md)：卡是被动散热、没有风扇，它唯一的 8-pin 插座是一个 **EPS** 插座，不是 PCIe 的。把一根 PCIe 线缆硬塞进去会损坏卡。安装完成时，用[验证](procedures/verify.md)来确认，而不是靠读 dmesg。

**"我想解锁它，而且想知道自己输入的命令是什么。"**
先看[解锁、概览](unlock/overview.md)，再看[原理](unlock/how-it-works.md)。这套机制分为[Falcon 与 Booter](unlock/falcon-and-booter.md)、[权限级别掩码](unlock/privilege-level-masks.md)、[算力节流](unlock/compute-throttle.md)和[显存几何布局](unlock/memory-geometry.md)。如果出问题，[排障](procedures/troubleshooting.md)会按你实际看到的报错字符串来分类。[驱动版本](procedures/driver-versions.md)解释了为什么版本钉死不可协商。

**"我想在寄存器层面理解它如何工作。"**
先看[硬件概览](hardware/overview.md)了解完整规格，再看[GA100 硅片](hardware/ga100-silicon.md)、[熔丝与 OTP](hardware/fuses-and-otp.md)、[显存子系统](hardware/memory-subsystem.md)和[PCIe 子系统](hardware/pcie-subsystem.md)。项目里出现的每个地址、数值和回读都收录在[寄存器参考](unlock/register-reference.md)中，并由[寄存器索引](appendix/register-index.md)建立索引。[VBIOS 页](hardware/vbios.md)则解释了为什么固件攻击这条路行不通。

**"我想帮忙解决剩下的。"**
从[状态板](frontier/status-board.md)和[未解问题](frontier/open-questions.md)开始，它们按可解性排序，每一条都附有具体的下一步实验。其中几项成本极低：一次三方引导对比，就能定夺 `RMPcieLinkSpeed` `0x1` 对 `0x2` 之争；查一次头文件，就能确定 LMR 量级字段的宽度；改动一个常量再重启一次，就能验证*相干的* 80 GB 三元组，是否与 `80` 分支实际已发布的那个非相干三元组表现不同。先读[死路](history/dead-ends.md)：大量精力已经投入在如今已关闭的路径上，该页精确记录了每条路径为何被关闭。

## 本维基如何标记置信

读者必须能一眼分辨既定事实与活跃推测。

- **普通正文即已确认的事实。** 这类文字无需携带标记。文中的数字若由代码推出，会点明其来源文件；若为实测所得，会交代测量条件。
- 一个 `> [!WARNING]` **Experimental** alert 标记未发布分支材料，以及任何只靠单一报告的东西。关于 PCIe Gen2 的一切都在这个类别里，因为 Gen2 补丁从未被合并到 `master`。
- 一个 `> [!CAUTION]` alert 标记任何能摧毁硬件或静默损坏数据的东西。本维基中最重要的一个实例并不显眼：在 1400 MHz 上限处，一个 +325 MHz 时钟偏移**会在不崩溃的情况下损坏显存**，所以一次跑完并不等于设置安全。
- 一个 `> [!NOTE]` **Open problem** alert 标记没人解决过的东西，并总是说明尝试过什么、下一步会是什么。

仅凭单一观察得出的结论，会在句子中自行说明："one tester reported"（一位测试者报告）、"a single rig on one day"（一天一台机架）。在多处出现的数字，已经与唯一的规范值核对一致；当两个来源确实分歧、又没有证据能裁断时，本维基会写明该值未知，而不是悄悄选一个。完整的约定见[如何读本维基](start/how-to-read-this-wiki.md)，底层声称如何被裁决见[方法论](appendix/methodology.md)。
