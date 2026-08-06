# 术语表

**本页覆盖内容。** 本维基出现的每个缩写、寄存器昵称、工具名和行话术语，都会给出准确的展开与简短解释。它还标出项目自己的文档分支杜撰的缩写展开——这些展开是错误的，却仍被复制进第三方指南。

全篇遵循两条约定：对于 NVIDIA 从未公布过展开的内部块名，本页如实说明，不妄加猜测；对于同一寄存器存在的两个名字，则并列在同一条目中，而不是拆成两条。

---

## 已更正的展开：不要复述这些

`cmpunlocker` 的 `docs` 分支（`docs/docs/ARCHITECTURE.md`）包含五个缩写展开，这些展开既不出现在已发布的源码中，也不出现在任何分支快照或 NVIDIA 发布的头文件里，纯属杜撰，却已传播进下游指南。

> [!WARNING]
> **流传的错误展开**
>
>
> | 术语 | 错误展开（以及出处） | 正确 |
> |---|---|---|
> | PLM | "Program Logic Modules"（`ARCHITECTURE.md` 第 38 行） | **权限级别掩码**，一个按寄存器控制的访问控制掩码 |
> | PMA | "Power Management Array"（第 30 行） | **物理内存分配器**，一个 RM 内存管理对象 |
> | SS0 / SS1 | "Suspension State" 寄存器（第 29 行） | `FEATURE_OVERRIDE_SM_SPEED_SELECT`（`0x0082381c`）和 `..._SM_SPEED_SELECT_1`（`0x00823820`） |
> | LMR | "LM Request" / "LM (Local Memory) Request register"（第 28 行） | `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`，本地显存**范围** |
> | PMM | "the PMM (Permute Mask Model)"（第 41 行） | 代码中不存在这样的块。该术语是捏造的。 |
>
> 两个相关的事实错误随之而来：同一文件声称 SS0 和 SS1 都写入 `0xffffffff`（发布的补丁写入的是 `0x88888888` 和 `0x00000008`），并声称解锁靠"注入自定义 PLM 序列"工作（实际是通过重跑带超大签名缓冲区的 Booter Load，打开四个具名的权限级别掩码寄存器）。参见[算力节流](../unlock/compute-throttle.md) 和[权限级别掩码](../unlock/privilege-level-masks.md)。

还有两个与那个分支无关的术语陷阱：

- **ROP。** 在普通 GPU 词汇里 ROP 指 *Raster Operations Pipeline*（光栅操作流水线）。在本维基的任何地方它都指 **Return-Oriented Programming（面向返回编程）**，即用来驱动 SEC2 Booter 的利用技术。参见[ROP 链](../unlock/rop-chain.md)。
- **XR7。** 几篇改装文章（以及本项目自己简报的早期草稿）说 PCIe 耦合电容是 "XR7"。介质代码是 **X7R**。参见[物理改装](../operations/physical-mods.md)。

---

## A

**A100D**
::   NVIDIA DRIVE A100（`10DE:20BB`，板卡代码 PG199）的非正式名称，一个 32 GB 的 GA100 部件，在本语料库中只作为对比设备出现。Booter 状态 `0x54` 曾在该部件上被观察到，至今未解码。名为 `PG199` 的 `cmpunlocker` 分支不含任何 A100D 支持。

**ACR**
::   访问控制区域。NVIDIA 面向 GPU 微控制器的签名安全启动框架，负责在帧缓冲中划出写保护区域，并管理串行化安全引擎访问的互斥锁。ACR 互斥锁被持有时，是解释 SEC2 邮箱卡死时反复出现的说法之一。

**AER**
::   Advanced Error Reporting（高级错误报告），标准的 PCIe 错误记录能力。在健康的 170HX 上，`lspci -vvv` 在能力偏移量 `[420]` 处显示 AER，所有 UESta/CESta 位清零。AER 计数器是判断一条 Gen2 或改装过电容的链路是否真正干净的正确工具。

**AON island**（也作 **always-on island**、**GC6 island**、**PGC6**）
::   GPU 的常电域，在引擎复位后依然保持供电。它内部的寄存器能挺过 [FLR](#f)；它外部的则不能。这种不对称是整个解锁最重要的结构事实：`FEAT_OVR_PLM`（`0x00823804`）、SS0 和 SS1 属于 AON、能挺过 FLR，而 CFG1、每-FBPA CFG1、CSTATUS、LMR、FB 几何 PLM 和 AON LMR 影子 `0x001180f0` 则不行。这就是算力解锁先于显存解锁发布的原因。机制描述本身（即 `SECURE_SCRATCH_14` 位于标为 RW-4R 的 PGC6 域中）属于中等置信度。

---

## B

**BAR0**
::   Base Address Register 0（基址寄存器 0）。16 MB 的内存映射寄存器孔径，本维基里几乎所有寄存器都通过它读写。工具通过 mmap `/sys/bus/pci/devices/<BDF>/resource0` 到达它。若 BAR0 读出来全是 `0xffffffff`，说明卡已脱离总线。

**BAR1 / Resizable BAR**
::   BAR1 是暴露给主机的帧缓冲孔径。170HX 在 `[bb0]` 声明一个 Physical Resizable BAR 能力，但窗口被限制为 64 MiB，所以无法使用大 BAR 的技巧。

**BAR2**
::   BAR2 是驱动自己的 `kbusVerifyBar2` 自检所用的 MMU 翻译孔径。当该测试命中 booter 划出的 WPR2 区域（而非损坏的显存）时，会解码失败，返回 `NV_ERR_MEMORY_ERROR`（`0x72`）并带日志字符串 `"BAR 0/BAR 2 failed."`。

**BDF**
::   Bus:Device.Function（总线:设备.功能），卡的 PCI 地址，例如 `0000:0a:00.0`。用户态辅助工具 `tools/retrain.sh` 中硬编码的 BDF `0a:00.0`，正是那些因机器而异的 PCIe Gen2 失败的根因。

**Booter / Booter Load**
::   NVIDIA 签名的 ACR 引导加载器 ucode，驱动把它运行在 [SEC2](#s) Falcon 上以认证并启动 [GSP-RM](#g)。解锁的做法是向 Booter Load 传递一个刻意超大的签名缓冲区，令一次受控溢出在 Booter 自身的权限上下文内执行一个 [ROP 链](../unlock/rop-chain.md)。无论成败，Booter 在发布流程的每次运行中都报告 `0xffff`，因此寄存器回读才是唯一可靠的结论。

**BSI scratch**
::   `0x001180xx` 安全暂存块（例如 `SECURE_SCRATCH_14` 在 `0x001180f8`，以及 AON LMR 影子在 `0x001180f0`）。从 PL0 读它们返回 `0xbadf5108`。"BSI" 的展开在本语料库中未确定。

---

## C

**Canary**
::   一个栈金丝雀：一个每次启动都随机的值，Booter 将它存放在所保存的返回地址下方，并在返回前重新核对，从而检测出简单的缓冲区溢出。170HX Booter 从 DMEM `0x6340` 加载它的金丝雀。若不一致，则以 SEC2 邮箱 `0x47` 触发 panic。发布的载荷会在构造的签名缓冲区中多个偏移量处写入值 `0xc0deca7e` 的**假金丝雀**。

**CE**
::   Copy Engine（复制引擎）。GPU 的 DMA 引擎。有两处相关：发布补丁 0005 在这些卡上禁用了基于 VAS 的 CE 清理路径；另一份 Xid 31 捕获则把 `ENGINE CE2 HUBCLIENT_HSCE2` 列为 64 GB 窗口顶端的故障客户端。

**CFG0 / CFG1**
::   `NV_PFB_FBPA_CFG0` 和 `NV_PFB_FBPA_CFG1`，内存控制器配置寄存器。CFG1 是定义每个分区寻址深度的寄存器，也是显存解锁的主要目标。广播 CFG1 是 `0x009a0204`；每-FBPA 的单播副本是 `0x00900204 + n*0x4000`，n = 0..23。出厂 CFG1 在两个 SKU 上都是 `0x02449000`；解锁后是 `0x02779000`（8 GB 卡）或 `0x02669000`（10 GB 卡）。字节 [23:16] 是层：出厂 `0x44`，`0x66` = 每 FBPA 2048 MiB，`0x77` = 每 FBPA 4096 MiB。两张卡每个活动分区上活着的每-FBPA CFG0 读 `0x07981800`。

**CMP**
::   Cryptocurrency Mining Processor（加密货币挖矿处理器），NVIDIA 面向计算受限挖矿部件的产品线。CMP 170HX 是这条产品线中基于 GA100 的成员，2021 年 9 月 1 日发布。

**CSTATUS_RAMAMOUNT**
::   每分区容量回读寄存器，位于 `0x0090020C + n*0x4000`。出厂时在两个 SKU 上都读 `0x200`（每 FBPA 512 MiB）。此处出现 `0xbadf20NN` 说明该分区已被地板清扫，低字节编码了实例号。

**CPU-RM**
::   资源管理器运行在主机 CPU 上而非 GSP 上的整体式驱动模式，用 `NVreg_EnableGpuFirmware=0` 选择。它把 SM 时钟锁定在 1140 MHz 基频，而非 GSP-RM 锁定的 1410 MHz。

**CYA_0**
::   BAR0 `0x0008c2c0`。位 2 是 `DIS_G2`，即 Gen2 禁用。Gen2 分支会清除它。

---

## D

**DEVINIT**
::   嵌入 VBIOS、在任何固件运行前执行的设备初始化脚本。若干未解决的限制（ECC、NVLink、可能还有 PCIe Gen3）被认为在 DEVINIT 阶段就已确定，这正是启动后的寄存器级覆盖无法触及它们的原因。

**DKMS / srcversion**
::   DKMS 为每个内核重建树外内核模块。`srcversion` 是模块的源码哈希；比较 `/sys/module/nvidia/srcversion` 与 `/lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko` 的 srcversion，是判断实际运行的是补丁模块还是出厂模块的确定性测试。

**DIO**
::   Falcon 的次级数据 I/O 带外接口，Booter 用它到达常电暂存寄存器。这些字母在任何公开 NVIDIA 文档中都没展开。对 `0x1180f8` 的一次被下毒的 DIO 读会返回 `0xdead5ec1`。

**DLLLA**
::   Data Link Layer Link Active（数据链路层链路活跃），PCIe Link Status 寄存器的位 13（`0x2000`）。即便在已训练好的 Gen2 x4 链路上，GPU 也总是报告 LnkSta `0x1042` 且 DLLLA 清零，所以补丁 `0008` 的成功谓词从不触发，而 "retrain completed without Gen2 link" 那行在**每台主机上都是假阴性**。`0x7042` 是同一份捕获中*上游根端口*的 LnkSta，不是不同类别的主机；`0008` 读的是 GPU 的。

**DMEM / IMEM**
::   Falcon 数据内存和指令内存。独立工具在 DMEM `0x0900` 加载 63,232 字节、在 IMEM `0x0000` 加载 45,824 字节。IMEM 按 256 字节块对齐。一旦 Falcon 进入 [HS 模式](#h)，DMEM 既不能读也不能写：写入被静默丢弃，`DMEM_PRIV_LEVEL_MASK`（`0x00840284`）显示 `wr_prot == 0`。

**`dmem.bin`**
::   位于 `/lib/firmware/nvidia/ga100/gsp/dmem.bin` 的可选外部载荷覆盖。它是一个开发钩子。它缺失时报告为状态 `0x59`，属正常、健康的路径。

---

## E

**ECC**
::   Error-Correcting Code（纠错码）内存。在 170HX 上熔断关闭（`FUSE_ECC_EN = 0x0`），既没有已知开关也没有遥测：`nvidia-smi -q` 把每个 ECC 字段报告为 `N/A`。名为 `ecc` 的分支里面根本没有 ECC 代码。参见[ECC](../frontier/ecc.md)。

**EPS 8-pin**
::   卡实际使用的 CPU 式 8-pin 电源接口，额定 300 W，内部携带两条独立的 12 V 轨。它**不是** PCIe 8-pin（额定 150 W），两者的 12 V 与地线引脚排布也各不相同。参见[Risks](risks.md)。

---

## F

**Falcon**
::   NVIDIA 的一族小型嵌入式微控制器，常展开为 *FAst Logic CONtroller*，以 SEC2、GSP 的启动核、FECS 等形态出现。Falcon 有自己的 IMEM/DMEM、一个加密协处理器，以及硬件强制的安全模式。

**FBHUB**
::   帧缓冲枢纽，引擎客户端与帧缓冲分区之间的交叉开关。`FBHUB_NUM_ACTIVE_LTCS` 位于 `0x00100800`，8 GB 卡读得 `0x10`（16），10 GB 卡读得 `0x14`（20）。

**FBP / FBPA**
::   FBP 是一个帧缓冲分区，即包含 L2 切片和两个 FBPA 的显存子系统切片。FBPA（常展开为 *frame buffer partition adapter*，帧缓冲分区适配器）就是 DRAM 控制器本身。8 GB 卡在 8 个 FBP 上有 16 个活动 FBPA，4096-bit 总线；10 GB 卡在 10 个 FBP 上有 20 个 FBPA，5120-bit 总线。探测工具走 24 个 FBPA 槽位，因为完整 GA100 有 24 个。

**FECS**
::   图形流水线中的前端上下文切换微控制器。`FECS_FEAT_OVERRIDE`（`0x00409664`）和 `FECS_FEAT_READOUT_1`（`0x00409668`）镜像 PRI 功能覆盖状态，从未特权上下文读返回 `0xbadf5040`。

**Floorsweeping**
::   制造时通过熔丝永久禁用有缺陷或多余的单元（GPC、TPC、FBPA、NVLink），以挽救部分有缺陷的晶片。地板清扫掩码**按晶片**而非按 SKU：四张 170HX 卡读出的 `OPT_GPC_DISABLE` 值分别是 `0x85`、`0x45`、`0x13` 和 `0xa8`，而四张仍全部枚举 70 个 SM。绝不硬编码一个地板清扫值。

**FLR**
::   Function Level Reset（功能级复位），由 `echo 1 > /sys/bus/pci/devices/<BDF>/reset` 触发的 PCIe 每功能复位。170HX 在 DevCap 里声明 `FLReset+`，这正是解锁装置可行的原因。一次成功的 FLR **确实**会清除 WPR2，也确实会清除 SEC2 复位-PLM 污染（`0x8f` 回到 `0xff`），但它不会复位 [AON island](#a)。

**FRTS**
::   在 GSP 启动前于帧缓冲中建立固件驻留区域的 FWSEC 命令，由 `kgspPrepareForBootstrap` 调用。该缩写的展开在本语料库的任何地方都未确定。

**FWSEC / FWSECLIC**
::   驻留 VBIOS 的固件安全 ucode，在引导早期运行于某个 Falcon 上，其中一项工作就是执行 FRTS 划区。发布补丁 0002 很大程度上是为了让 FWSEC 失败可诊断，把致命断言转换成 `SEC2_DEBUG: FWSEC status=0x%x` 样式的日志行。FWSECLIC 是配套的许可证检查程序。

---

## G

**GA100**
::   A100 和 CMP 170HX 共同使用的 Ampere 数据中心晶片：TSMC 7 nm N7、542 亿晶体管、826 mm²、BGA-2743 封装、CUDA 计算能力 8.0。每个被探测的 GA100 上 `PMC_BOOT_0` 都读得 `0x170000a1`。

**GPC / TPC / SM**
::   Graphics Processing Cluster（图形处理集群）、Texture Processing Cluster（纹理处理集群）、Streaming Multiprocessor（流多处理器）。170HX 在两个 SKU 上都枚举 5 个活动 GPC、35 个活动 TPC 和 **70 个 SM**（4480 个 CUDA 核心），已经处在它的熔丝下限。完整 GA100 会是 8 个 GPC 和 64 个 TPC。

**GSP**
::   GPU System Processor（GPU 系统处理器），Ampere 及以后的 RISC-V 微控制器，在晶片上运行大部分资源管理器。

**GSP-RM**
::   运行在 GSP 上的资源管理器固件映像。它在主机上的对应物是 Kernel-RM / CPU-RM。本维基里的启动失败几乎总是 GSP-RM 引导失败。

---

## H

**HBM2 / HBM2e**
::   High Bandwidth Memory（高带宽内存），GA100 使用的堆叠 DRAM。170HX 上的理论峰值是 1555.2 GB/s（5120-bit 上的 1215 MHz DDR）。实测值随工具与访问模式不同，在 1305.86 到 1600 GB/s 之间浮动，不存在唯一的标准数字。

**HS mode**（Heavy Secure）
::   Falcon 的最高权限模式。代码只有在签名验证后才会进入 HS；一旦进入 HS，IMEM `0x00` 处的低安全引导程序被擦除，DMEM 对主机不可访问，Falcon 就能写其它被 PL0 阻挡的寄存器。整个显存解锁之所以存在，是因为只有从 HS 才能执行一组特定的寄存器写入。

**HULK**
::   NVIDIA 用于启用调试和厂商功能的内部许可证/证书机制。170HX 在它的许可证区域 `0xFE000`-`0xFEFFF` 携带一个预建但为空的 HULK 目录表。已调查，并作为一条路径被排除。

---

## I

**InfoROM**
::   VBIOS 映像中按板卡持久保存序列号与校准数据的数据区域。在 DRIVE A100 上，它占了两颗物理不同、却承载相同固件的 GPU 之间字节差异的 99.5%。

**IOMMU**
::   主机输入输出内存管理单元。直通模式（`iommu=pt`）是安装解锁器后 PCIe 仍停留在 Gen1 时首先要检查的；安装器会自动设置 `intel_iommu=on iommu=pt` 或 AMD 的等效项。

---

## L

**LMR**
::   `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE` 位于 `0x00100ce0`：即 MMU 所认为的本地显存容量。编码为 `size_MiB = MAG[9:4] << SCALE[3:0]`。出厂值是 `0x00000208`（8 GB 卡）和 `0x00000288`（10 GB 卡）；解锁值是 `0x0000020B`（64 GB）和 `0x0000028A`（40 GB）。它的 PLM 是 `0x001fa7c4`（`..._LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`），还有一个 AON 影子在 `0x001180f0`。**不要**把 LMR 展开成 "LM Request"。

**LnkCap / LnkCap2 / LnkCtl2 / LnkSta**
::   用于链路能力、受支持速度、目标速度和已训练状态的 PCIe Express Capability 寄存器。出厂 170HX：`LnkCap 0x00456101`、`LnkCap2 0x00000002`、`LnkSta 0x1041`。带解锁器：`LnkCap 0x00456102`、`LnkCap2 0x00000006`、`LnkCtl2 0x0002`、`LnkSta 0x1042`。声明的能力不是已训练的链路。

**LTC**
::   Level-two cache slice（二级缓存切片）。170HX 有 32 MB 的 L2，而 A100 是 40 MB。

**LTSSM**
::   Link Training and Status State Machine（链路训练与状态状态机），负责协商速度和位宽的 PCIe 状态机。这块卡上，Gen2 补丁中昵称为 LTSSM 的寄存器是 BAR0 `0x0008872c`，写入 `0x00000006`。该块其它位置涉及的字段包括 LTSSM_DIRECTIVE（0 = NORMAL，1 = CHANGE_SPEED）和 [19:18] 处的 SPEED 字段。

---

## M

**MIG**
::   Multi-Instance GPU（多实例 GPU），Ampere 的硬件分区功能。在解锁的 170HX 上，设置 `0x820840` 的位 0 即可启用，之后 `nvidia-smi` 报告 `MIG M. Enabled`，可见 65536 MiB。

    > [!WARNING]
    > **实验性**
        MIG 启用是一个社区写入，**不在**发布的解锁器中。

**MOK / Secure Boot**
::   Machine Owner Key（机器所有者密钥）登记，让签名的树外模块能在 UEFI 安全启动下加载的机制。补丁模块未签名，所以如果 `mokutil --sb-state` 报告 `SecureBoot enabled`，`install.sh` 会硬性失败。

---

## N

**NVGI / PciAt / FwSec body**
::   GA100 VBIOS 映像的三个主要区域。NVGI 是最早的，在任何固件运行前由 PBUS/XVE 的从 ROM 初始化序列器执行；PciAt 持有 PCI 可见的身份；FwSec body 持有签名的固件。8 GB 和 10 GB VBIOS 映像之间全部的功能差异归结为 NVGI 引导程序里的 2 个字节。

**NVLink**
::   在 170HX 上熔断关闭（`FUSE_NVLINK_DIS`）。任何固件或驱动改动都无法恢复它。板侧 NVLink 接口 IC 是否被贴装仍未解决。参见[NVLink](../frontier/nvlink.md)。

**nvidia-open**
::   NVIDIA 的开源 GPU 内核模块。`cmpunlocker` 补丁的是这棵树而非专有那棵，且仅接受版本 `610.43.03`（默认）和 `610.43.02`。

---

## O

**OTP**
::   One-Time Programmable（一次性可编程）。熔丝承载算力节流（`OPT_SM_SPEED_SELECT`，九个独立熔丝）、设备 ID、PCIe 代数禁用及地板清扫掩码。暴露它们的寄存器是只读的熔丝影子。位于 `0x008203f0` 的主清除熔丝读 `0x00000000`（未烧断），这就是这一切之所以可行的原因。

---

## P

**P2P**
::   Peer-to-peer（点对点）GPU 间传输。这块卡上并不具备。

**PLM**（权限级别掩码）
::   一个按寄存器控制的访问控制掩码，决定哪些权限级别（PL0 主机，直到 PL3 重度安全）可以读和写它所守护的寄存器。打开 PLM 是整个关键：发布版驱动的内部路径按顺序恰好打开四个，每个最多尝试两次：

    | 索引 | 名称 | 地址 | 目标值 |
    |---|---|---|---|
    | 0 | `WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` |
    | 1 | `FBPA` | `0x009a0148` | `0xffffffff` |
    | 2 | `WPR` | `0x001fa7c4` | `0xffffffff` |
    | 3 | `FEAT` | `0x00823804` | `0xffffffff` |

    `WPR_CFG` 回读为 `0xfffff0ff` 是**正确的**，不是失败。说 "all PLMs must show `0xffffffff`" 的指南过于严格。

**PMA**
::   Physical Memory Allocator（物理内存分配器），拥有帧缓冲页的 RM 对象（`pmaRegisterRegion`、`pmaGetFreeMemory`、`PMA_REGION_DESCRIPTOR`）。发布补丁 0003 执行一次"晚期 PMA 扩展"，把高地址的 PMA 区域扩大，以覆盖新暴露的帧缓冲，记录 `SEC2_DEBUG: late PMA extension status=0x%x`。它与电源管理毫无关系。

**PMC_BOOT_0**
::   BAR0 `0x00000000`，芯片身份寄存器。在每个 GA100 上都读 `0x170000a1`。一个 GA10x 对照部件读 `0xb74000a1`。

**PRAMIN**
::   特权 BAR0 窗口，让 CPU 直接访问视频内存的一块可移动区域。发布补丁 0004 在 `fbAddrSpaceSizeMb > 0x2000` 时把 PRAMIN 基址钳回出厂 8 GB 派生的偏移量（`(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`），否则窗口会基于 65536 MB 计算，落至可达的 BAR0 空间之外。PRAMIN 也正是用来证明 10 GB 卡上存在 80 GiB 物理 DRAM 的手段。

**PRI**
::   GPU 的内部特权寄存器总线。被阻挡或目标不存在的读返回 `0xbadfXXXX` 毒值而非数据：`0xbadf5040` = 被权限级别掩码阻挡，`0xbadf1100` = 目标不存在，`0xbadf20NN` = 目标存在但该 FBPA 已被地板清扫，`0xbadf5108` = 从 PL0 读 AON 安全暂存。

**`probe.sh`**
::   只读表征工具（`tools/mmio-probe`）。它以只读方式 mmap `resource0`，转储大约 120 到 130 个具名寄存器外加 24 次每-FBPA 读，并且**从不对 BAR0 写入**。常量：`FBPA_BASE = 0x900000`、`FBPA_STRIDE = 0x4000`、`CSTATUS_RAM = 0x20C`。它输出 `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv` 和 `probe.log`。它是标准的验证工具：任何写入之后，都用 `probe.sh` 回读寄存器，而不是轻信工具声称的成功。

**PTE kind**
::   GPU 页表条目的 "kind"（种类）字段，描述压缩和分块格式。发布补丁 0005 为这些设备 ID 强制 `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY`，取代 `..._COMPRESSIBLE_DISABLE_PLC`。

---

## R

**RFRD**
::   VBIOS SPI ROM 中的一个映像布局描述符记录，位于绝对地址 `0x2000`。有社区解析器把它误标为 "power table"，其实并非如此。

**ROP chain**
::   Return-Oriented Programming chain（面向返回编程链）。一个完全由已签名代码中现成的短指令序列（"gadgets"，小工具）构建的载荷，通过覆写返回地址把它们串起来，这样就不需要为任何新代码签名。在这块卡上，链被放在超大的 GSP 签名缓冲区里，由 SEC2 Booter 执行。Booter 从 DMEM `0xFF5C` 取它被劫持的返回地址；`0xFF48` 是 `0x4d4` pop 块里的保存-r3 槽位，也是 `0x18` 字节帧网格的基址，所以在被取代的独立链中，一个 N 写尾部从 `0xFF48 + N*0x18` 开始。参见[ROP 链](../unlock/rop-chain.md)。

---

## S

**SBR**
::   Secondary Bus Reset（次级总线复位），由上游桥发出的一种比 FLR 更强的复位。SBR 会下电并重新初始化常电域，因此能清除那些根植于 AON 暂存、且能挺过 FLR 的卡死状态。

**SCP**
::   Falcon 的 Secure Co-Processor（安全协处理器），用于签名验证和密钥处理的加密块。Falcon 引擎复位恢复期间会轮询 `SCP_CTL_P2PRX` 的位 3（SFK_LOADED）。

**SEC2**
::   GPU 的安全引擎 Falcon，位于 BAR0 基址 `0x00840000`（邮箱 0 在 `0x00840040`）。它运行 Booter ucode，也是解锁所利用的引擎。它的复位-PLM 可观察量（地址报告为 `0x008403C4`，身份有争议）干净时读 `0xff`，`secure_teardown` 运行后读 `0x8f`，驱动仍加载的部分触发状态下读 `0x00cf`。

**Signature buffer**
::   持有 GSP 固件签名的内存描述符。出厂大小为 4096 字节；发布补丁把它放大到 `0x0000f800`（63,488 字节）并填充载荷，dword `0x000004a7`。更早、已放弃的做法是在磁盘上补丁 `gsp_tu10x.bin`，但因 `fwsignature_ga100` 节只有 `0x1000` 字节而受阻。

**SS0 / SS1**
::   `FEATURE_OVERRIDE_SM_SPEED_SELECT`（`0x0082381c`）和 `..._SM_SPEED_SELECT_1`（`0x00823820`）。它们控制每个指令单元的**发射速率**，而不是哪些 SM 活跃。解锁写入 `0x88888888` 和 `0x00000008`。锁定卡在 SS0 处读到的值，例如为 `0x53540175`。它们属于 AON、能挺过 FLR。它们不是 "Suspension State" 寄存器。

**Strap / strap resistor**
::   一个 0402 电阻加一个空的相邻焊盘，在两个位置之间移动元件就会翻转一个由硬件采样的配置位。170HX 携带五对跨接（十个焊盘，位号 R986 到 R1005），外加位于别处的一对 DEVID_SEL。主 PCIe 设备 ID 熔进晶片，**不能**靠跨接设置（`FUSE_DEVID_SW_OVR_DIS 0x00820584` = 在每张被探测的卡上都是 1）。

---

## V

**VBIOS**
::   卡的固件 ROM。公开存在四款 170HX 映像；其中两款上 TechPowerUp 的 "16 GB" 和 "0 GB" 大小标签是错的，且两者都不解锁显存。VBIOS 版本对解锁能否生效没有区别。参见[VBIOS](../hardware/vbios.md)。

**VSEC**
::   Vendor-Specific Extended Capability（厂商特定扩展能力），PCIe 配置空间的扩展能力块。对 Gen2 而言有两个寄存器要紧：`VSEC_DEVICE` 在 `0x0008860c`（通过 Booter 载荷置位 0）和 `VSEC_HIERARCHY` 在 `0x00088610`（Booter 阶段之后的一次普通主机 BAR0 写入）。

---

## W

**WPR / WPR1 / WPR2**
::   Write Protected Region（写保护区域）。MMU 拒绝让非特权代理写入的帧缓冲范围，用于持有 ACR 和 GSP 固件状态。WPR2 的 lo/hi 值位于 `0x001fa824` 和 `0x001fa828`。禁用时它们读 `0x1FFFFE00 / 0x00000000`；一次 Booter 运行后读 `0x01F77000 / 0x01FFEE00`。发布补丁把两者各保存一次，并在**每一次** Booter Load 尝试前重写它们，而不是清除它们。"WPR2 already up" 是早期的主导失败，现在降级为一条继续执行的警告。

**WprMeta**
::   描述 WPR 布局的元数据结构，包括 `fbSize` 和 `sizeOfSignature`，由驱动填充、由 Booter 验证。

---

## X

**Xid**
::   NVIDIA 驱动发出的错误标识。这里要紧的有：

    | Xid | 在本语料库中的含义 |
    |---|---|
    | 31 | MMU 故障，`FAULT_INFO_TYPE_REGION_VIOLATION`。分配越过解锁窗口的可用顶端。卡在重启前无法在 CUDA 中使用。在 80 GB 下，触碰超过约 40 GB 的内核会独立于功耗上限造成致命 GPU 丢失；报告的错误码包括 Xid 31（被描述为无害）和 CUDA 内存测试后的 Xid 154，主导报告症状是挂起。Xid 31 单独出现是由旁观者提出的，并未被持故障卡的操作者证实为*那个*标志。 |
    | 45 | 由 SIGKILL 一个活跃的 CUDA 验证内核诱发；强制一次复位循环。 |
    | 119 | GSP RPC 超时。两种不同变体：等函数 4097 `GSP_INIT_DONE` 60 秒（启动从未完成）和函数 103 `GSP_RM_ALLOC` 6 秒（启动后挂起，每次 `nvidia-smi` 重复）。 |
    | 154 | 过度配置的 80 GB 配置在 CUDA 内存测试后的主导失败；把卡限制为每次触发一个 CUDA 上下文。 |

**XP3G**
::   `0x0008e1xx` 处的 PCIe 链路层覆盖块，包括 `XP3G_OVR0` `0x0008e110`、`XP3G_VAL0` `0x0008e120`、`XP3G_OVR3` `0x0008e11c`、`XP3G_VAL3` `0x0008e12c` 和 PLM 四元组 `0x0008e1b0` / `0x0008e1b4` / `0x0008e1b8` / `0x0008e1bc`。Gen2 补丁通过 Booter 载荷原语推入一张 23 条目 `xp3gTable`（18 次 PLM 打开加 5 次值写入）。NVIDIA 未发布该名字的展开。

**XVE**
::   NVIDIA 对 PCI Express 端点和配置空间块的内部名称，基址 `0x00088xxx`。Gen2 系分支在表里加三个 XVE 能力 PLM：`0x00088ff4`（XVE）、`0x00088ab4`（XVE_B）、`0x00088ff8`（XVE_C）。这些字母在任何公开 NVIDIA 文档中都没展开。

---

## 数字、代码和文件路径

**`0x008200FC`**
::   一个寄存器，两个名字。分支源码写 `{0x008200fcU, 0xffffffffU, "OPT_PLM"}`，所以 `OPT_PLM` 是代码名；`FUSE_SS_PLM` 是净室工具对同一寄存器的名字。它**不**被发布的 master 写入。它是否可写、冷卡上读出的值为何，目前仍无定论。

**`0xbadfXXXX`**
::   参见[PRI](#p)。它们绝不是存储的数据。

**`0xc0deca7e`**
::   放在构造的签名缓冲区里的假金丝雀哨兵。

**Branch names**
::   有 **12** 个未发布的分支快照（`80`、`Gen2`、`PG199`、`clanker_driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`），加上当前发布的 `master` 共 13 棵树。称 "thirteen unreleased branches" 的文档漏了一个。

**`/lib/modules/$(uname -r)/updates/cmpunlocker/`**
::   安装写入补丁模块外加三个标记文件的地方：`driver_version`、`card_profile`（`8gb` 或 `10gb`）和 `unlock_geometry`。多卡分支增加 `gpu_inventory`。

**`SEC2_DEBUG`**
::   解锁路径的日志标签。`sudo dmesg | grep SEC2_DEBUG` 是首要且唯一的诊断手段。存在两个兄弟标签：`SEC2_DEBUG_HEAP` 和 `SEC2_DEBUG_LATE_PMA`。全部在 `LEVEL_ERROR` 级别发出，所以无需额外调试标志。完全没有 SEC2_DEBUG 行意味着补丁模块从未运行。

---

## 本维基引用的工具

| 工具 | 在这里的用途 |
|---|---|
| `clpeak` | OpenCL 带宽和算力微基准；Gen1 x4 约 0.85 GB/s 数值的来源 |
| `cuda_memtest` | GPU 显存验证；80 GB 档位在重启后通过一次然后失败 |
| `gpu-burn` | 带错误计数器的持续算力压力；稳定的 40 GB 卡干净通过 5 分钟 |
| `mixbench` | 混合精度吞吐；它的 `1769.47 GB/sec` 数值是理论的，不是实测 |
| `nvtop` | 包括 PCIe 代数和位宽在内的实时每 GPU 遥测 |
| `ocl_pcie_bw` | OpenCL 主机到设备带宽；Gen2 x16 的 6.63 到 6.67 GB/s 数值的来源 |
| `pcielink.sh` | 收集链路训练报告的社区数据采集脚本；打印 GPU 和桥的身份加全套 LnkCap/LnkSta/AER |
| `probe.sh` | 只读寄存器调查；见上方[PRI](#p) |
| `verify.sh` | 多卡分支上的按-BDF 解锁验证 |
| `CH341A` | SPI flash 编程器。GPU EEPROM 是 1.8 V，所以需要一个 1.8 V 转接器 |

---

## 参见

- [如何阅读本维基](how-to-read-this-wiki.md)，了解置信度约定。
- [寄存器参考](../unlock/register-reference.md)，一张表里收全所有地址。
- [识别你的卡](identify-your-card.md)，弄清你持有哪个 SKU。
