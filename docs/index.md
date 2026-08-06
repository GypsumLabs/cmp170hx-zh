# CMP 170HX 维基

**本页涵盖什么：** NVIDIA CMP 170HX 是什么、社区从它手里夺回了什么、今天确切能工作什么、以及根据你为何而来下一步该去哪里。

CMP 170HX 是一颗基于 **GA100** 的加密货币挖矿加速器、与 NVIDIA A100 相同的那颗 826 mm² 7 nm 晶片。它以两个 SKU 出货、PCI ID `10de:20c2` 报告 8192 MiB、`10de:2082` 报告 10240 MiB、两者在计算能力 8.0 下都暴露 70 个流式多处理器、4480 个 CUDA 核和 280 个第三代张量核。NVIDIA 以四种刻意残废的方式卖它：SM 发射速率对 FP32 FMA 和每条张量核路径被熔断降到约 1/32、HBM 容量被跳线限制到堆叠物理承载量的一小部分、PCIe 链路被封顶在 Gen1 速度且只协商它 16 条线里 x4、NVLink 和 ECC 被熔断关闭。一份仔细的 2023 拆解得出结论该组合"guaranteed the uselessness of the GPU"（保证了 GPU 的无用）、并因固件签名判定这些上限不可破。

在 2023 到 2026 年 7 月之间、一个分布式社区用软件、无 VBIOS 刷写、无签名伪造地夺回了其中大部分。出货解锁器是一组对 NVIDIA 开源内核模块的六补丁集。它用一个做手脚的签名载荷重新 fire SEC2 Booter Load 以打开四个权限级别掩码、然后在 GSP 引导窗口内做四次寄存器写：`0x0082381c` = `0x88888888` 和 `0x00823820` = `0x00000008` 恢复完整 SM 发射速率、FBPA CFG1 `0x009a0204` 加 MMU LMR `0x00100ce0` 恢复真正的 A100 显存几何布局。测得结果：FP32 非张量从约 0.39 到约 12.6 TFLOPS（一个 26x 到 32x 增益）、BF16 张量从 6.4 到 171-193 TFLOPS、FP64 在一个 torch GEMM 上到 11.6 TFLOPS（张量路径：一次 clpeak 转储在同一个运行里打印 6.31 TFLOPS 标量对 `wmma_fp64` 的 11.96）、而一张 8 GB 卡报告并使用 **65536 MiB**。整个序列花约一秒钟驱动加载、在每次模块加载时重跑、且不写任何东西到闪存。一次会话里基准过的八张租用卡测得不到 2.5% 离散、并 8/8 通过全-VRAM 逐字节对比完整性测试。

> [!WARNING]
> **读任何别的东西前要搞对两件事**
>
> **容量按 SKU 固定、且不可互换。** 8 GB 卡解锁到 **64 GB**。
> 10 GB 卡解锁到 **40 GB**、而 40 GB 是受支持的配置。10 GB 卡的 80 GB
> 驱动分支被构建、测试并被放弃：它报告 81920 MiB 但在约 40 GB 实际使用
> 之上失败。一个单独的脚本驱动的相干寄存器集确实能到
> 40 GiB 之后的真实显存、但它是未出货、实验性的、而且每次 fire
> 大约给一个 CUDA 上下文。
>
> **PCIe 速度和 PCIe 位宽是两个不同问题、两个不同修复。**
> Gen1 到 Gen2 是一个*软件*解锁、只存在于未发布分支上。超越
> x4 *位宽*需要在板上手工焊接 24 颗交流耦合电容。两者都不对
> 另一个起任何作用。

## 今日状态

| 能力 | 状态 | 详情 |
|---|---|---|
| SM 节流移除（算力） | **已出货、稳定** | 两次寄存器写；挺过 FLR。[原理](unlock/compute-throttle.md) |
| 8 GB 卡到 64 GB | **已出货、稳定、生产中** | CFG1 `0x02779000`、LMR `0x0000020B`。[显存几何布局](unlock/memory-geometry.md) |
| 10 GB 卡到 40 GB | **已出货、稳定** | CFG1 `0x02669000`、LMR `0x0000028A` |
| 跨重启持久化 | **自动** | 每次 GSP 引导重新应用；没有任何东西被刷写。[安装](procedures/install.md) |
| 多卡机架 | **可工作** | 8 卡机架被测量；见[多卡](procedures/multi-gpu.md) |
| GPC 时钟偏移 / 欠压 | **经 NVML 可工作** | 8 GB SKU 上 `[-1000..+1000]` MHz。[调优](operations/tuning.md) |
| 功耗限制（`nvidia-smi -pl`） | **可工作** | 出厂 100-250 W、OC VBIOS 上 300 W。[供电](operations/power-and-psu.md) |
| PCIe Gen2（链路**速度**） | **可工作、仅未发布分支** | 不在出货 `master` 里；野外非确定性。[Gen2](unlock/pcie-gen2.md) |
| PCIe x16（链路**位宽**） | **仅硬件改装** | 24 × 0402 220 nF X7R 电容。[物理改装](operations/physical-mods.md) |
| Gen2 与 x16 一起 | **观测过一次** | 6.63-6.67 GB/s、一台机架、2026-07-26、中等置信 |
| 10 GB 卡到 80 GB | **分支被拒；相干寄存器集实验性** | `80` 分支报告 81920 MiB 且在约 40 GB 之上失败。一次免驱动相干 fire 通过一次 77.5 GiB 无折叠测试、但每次 fire 给一个 CUDA 上下文。[80 GB](frontier/80gb.md) |
| PCIe Gen3 / Gen4 | **未解决** | 两个代熔丝都读 `0x00000001`。[Gen3/Gen4](frontier/pcie-gen3-gen4.md) |
| 超过 70 个 SM | **未解决** | 到 GPC-禁用熔丝的每条写路径都被锁存 |
| ECC | **未找到杠杆** | 熔断关闭、无遥测、`MASTER_EN` 只读。[ECC](frontier/ecc.md) |
| NVLink | **这块板上不可能** | 熔断关闭。板上侧接口 IC 是否被装未定、且倾向未装。[NVLink](frontier/nvlink.md) |
| 点对点（P2P） | **缺失** | [P2P](frontier/p2p.md) |
| MIG | **单一报告、未出货** | `0x820840` 的位 0；等待第二张卡和一次拉取请求 |
| 空转功耗降低 | **无杠杆** | 只存在性能状态 P0；`nvidia-pstated` 返回 `NVAPI_ERROR` |
| 显存时钟控制 | **经 NVML 被拒**、但用一个打过补丁的模块可达 | NVML MEM VF 偏移范围是 `[0..0]` 且 `-lmc` 不受支持、然而一个打过补丁的模块加一次重启在实践中降频了 HBM：1728 MHz → 212.2 TF / 181.2 W；1620 MHz（NDIV 60）→ 211.6 TF / 172.9 W；1404 MHz（NDIV 52）→ 210.5 TF / 169.3 W |
| VBIOS 修改 | **对解锁杠杆关闭** | 容量跳线和 PCIe 代跳线坐在 Davies-Meyer MAC 范围内。未签名的 FwSec 尾在它外面、且确实持有可编辑字段、包括 `0x45E45` 处的板功耗上限和 `freqDelta`、但写它们需要一个 CH341A 夹。[VBIOS](hardware/vbios.md) |

出货 `master` 上受支持的驱动恰好是 **`610.43.03`**（默认）和 **`610.43.02`**；其它任何东西构建都会硬失败。到 595 / 590 / 580 的移植存在于一个分支上、被源码验证、且从未被报告引导过。

## 从这里开始

**"我刚买了一张、我想要它工作。"**
读[这张卡是什么](start/what-is-this-card.md)了解背景、然后[识别你的卡](start/identify-your-card.md)以确定你持有哪个 SKU（这决定下游一切）、然后[风险](start/risks.md)、然后[快速上手](start/quick-start.md)和[安装](procedures/install.md)。在给任何东西上电前、读[散热](operations/cooling.md)和[供电与 PSU](operations/power-and-psu.md)：卡是被动散热、没有风扇、它唯一的 8-pin 插座是一个 **EPS** 插座、不是 PCIe 的。把一根 PCIe 线缆硬塞进去会损坏卡。当安装完成时、用[验证](procedures/verify.md)确认它、而不是读 dmesg。

**"我想解锁它、而且我想知道我在敲什么。"**
[解锁、概览](unlock/overview.md)然后[原理](unlock/how-it-works.md)。机制分成[Falcon 与 Booter](unlock/falcon-and-booter.md)、[权限级别掩码](unlock/privilege-level-masks.md)、[算力节流](unlock/compute-throttle.md)和[显存几何布局](unlock/memory-geometry.md)。如果出问题、[排障](procedures/troubleshooting.md)按你看到的精确字符串组织。[驱动版本](procedures/driver-versions.md)解释为什么版本钉死不可协商。

**"我想在寄存器层面理解它如何工作。"**
[硬件概览](hardware/overview.md)看完整规格、然后[GA100 硅片](hardware/ga100-silicon.md)、[熔丝与 OTP](hardware/fuses-and-otp.md)、[显存子系统](hardware/memory-subsystem.md)和[PCIe 子系统](hardware/pcie-subsystem.md)。项目里每个地址、值和回读都收集在[寄存器参考](unlock/register-reference.md)里、并在[寄存器索引](appendix/register-index.md)里被索引。[VBIOS 页](hardware/vbios.md)解释为什么固件攻击是关闭的。

**"我想帮忙解决剩下的。"**
从[状态板](frontier/status-board.md)和[未解问题](frontier/open-questions.md)开始、它们按可解性排名、每个都带一个具体下一个实验。几个是便宜的：一次三方引导对比定案 `RMPcieLinkSpeed` `0x1`-对-`0x2` 之争、一次头部查找定案 LMR 量级字段宽度、一次常量改动加一次重启会测试一个*相干的* 80 GB 三元组是否与 `80` 分支实际出货的非相干那个表现不同。先读[死路](history/dead-ends.md)：大量努力已经花在现在已关闭的路径上、该页精确记录每条为何关闭。

## 本维基如何标记置信

读者必须能一眼分辨既定事实与活跃推测。

- **普通正文是已确认的。** 它不带标记、因为不需要。当一个数字是代码派生的、来源文件被点名；当它是测得的、条件被给出。
- 一个 `> [!WARNING]` **Experimental** alert 标记未发布分支材料、以及任何立足单一报告的东西。关于 PCIe Gen2 的一切都在这个类别、因为 Gen2 补丁从未被合并到 `master`。
- 一个 `> [!CAUTION]` alert 标记任何能摧毁硬件或静默损坏数据的东西。本维基里最重要的实例不是一个明显的：在 1400 MHz 上限处、一个 +325 MHz 时钟偏移**损坏显存而不崩溃**、所以一次完成的运行不是设置安全的证据。
- 一个 `> [!NOTE]` **Open problem** alert 标记没人解决过的东西、并总是说明尝试过什么、下一步会是什么。

立足单一观察的声称在句子本身里说明："one tester reported"（一位测试者报告）、"a single rig on one day"（一天一台机架）。出现在不止一处的数字已对照单一规范值调和、而两个来源真正分歧且无证据定案时、本维基说该值未知、而非悄悄选一个。见[如何读本维基](start/how-to-read-this-wiki.md)看完整约定、[方法论](appendix/methodology.md)看底层声称如何被裁决。
