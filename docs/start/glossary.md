# 术语表

**这一页讲什么。** 这里收录本维基中出现的缩写、寄存器别名、工具名称和专业术语，并给出准确的英文展开和简明解释。项目自己的文档分支曾经编造过一些缩写展开，这些错误说法至今还在第三方指南中流传，本文也会特别标出。

本页遵循两条规则：NVIDIA 没有公开正式展开的内部模块名，就明确写成“尚未确定”，不自行猜测；同一个寄存器如果有两个名称，就放在同一条目下说明，不重复拆列。

---

## 已更正的展开：不要再使用

`cmpunlocker` 的 `docs` 分支（`docs/docs/ARCHITECTURE.md`）写了五个缩写展开。但这些展开既不见于发布版源码，也不见于任何分支快照或 NVIDIA 发布的头文件，属于凭空编造的说法，却已经传播到下游指南中。

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
> 这个文件还带来了两个相关的事实错误：它声称 SS0 和 SS1 都写入 `0xffffffff`，但发布版补丁实际写入的是 `0x88888888` 和 `0x00000008`；它还声称解锁依靠“注入自定义 PLM 序列”，而实际机制是反复运行带有超大签名缓冲区的 Booter Load，从而打开四个指定的权限级别掩码寄存器。参见[算力节流](../unlock/compute-throttle.md)和[权限级别掩码](../unlock/privilege-level-masks.md)。

还有两个与该分支无关、但也容易混淆的术语：

- **ROP。** 在普通 GPU 语境中，ROP 通常指 *Raster Operations Pipeline*（光栅操作流水线）。但在本维基中，它始终指 **Return-Oriented Programming（面向返回编程）**，也就是驱动 SEC2 Booter 所使用的利用技术。参见[ROP 链](../unlock/rop-chain.md)。
- **XR7。** 几篇改装文章以及本项目早期简报，都把 PCIe 耦合电容的介质代码写成“XR7”。正确写法是 **X7R**。参见[物理改装](../operations/physical-mods.md)。

---

## A

**A100D**
::   NVIDIA DRIVE A100（`10DE:20BB`，板卡代码 PG199）的非正式名称。这是一款 32 GB 的 GA100 部件，在本资料库中只作为对照设备出现。该部件曾被观察到 Booter 状态 `0x54`，但这个状态至今没有解码。名为 `PG199` 的 `cmpunlocker` 分支不包含任何 A100D 支持。

**ACR**
::   Access Control Region，即访问控制区域。NVIDIA 为 GPU 微控制器设计的签名安全启动框架，负责在帧缓冲中划出写保护区域，并通过互斥锁串行化安全引擎的访问。SEC2 邮箱卡死时，经常有人将原因归结为 ACR 互斥锁仍被占用。

**AER**
::   Advanced Error Reporting，即高级错误报告，是 PCIe 标准提供的错误记录能力。在状态正常的 170HX 上，`lspci -vvv` 会在能力偏移量 `[420]` 处显示 AER，且所有 UESta/CESta 位都为 0。要判断 Gen2 链路或电容改装后的链路是否真正稳定，应查看 AER 计数器。

**AON island**（也作 **always-on island**、**GC6 island**、**PGC6**）
::   GPU 中始终保持供电的区域，即常电域。引擎复位后，该区域内的寄存器仍然保留，区域外的寄存器则不会。这种差异是整个解锁机制最重要的结构性事实：`FEAT_OVR_PLM`（`0x00823804`）、SS0 和 SS1 属于 AON，可以挺过 [FLR](#f)；CFG1、每个 FBPA 的 CFG1、CSTATUS、LMR、显存几何 PLM 和 AON LMR 影子 `0x001180f0` 则不能。因此，算力解锁比显存解锁更早发布。至于 `SECURE_SCRATCH_14` 位于标记为 RW-4R 的 PGC6 区域这一具体机制，目前置信度为中等。

---

## B

**BAR0**
::   Base Address Register 0，即基址寄存器 0。它提供一个 16 MB 的内存映射寄存器空间，本维基中几乎所有寄存器都通过它读写。工具通过 mmap `/sys/bus/pci/devices/<BDF>/resource0` 访问 BAR0。如果 BAR0 全部读为 `0xffffffff`，通常说明显卡已经脱离 PCIe 总线。

**BAR1 / Resizable BAR**
::   BAR1 是暴露给主机的帧缓冲地址窗口。170HX 在 `[bb0]` 声明支持 Physical Resizable BAR，但窗口被限制为 64 MiB，因此无法利用大 BAR 技巧。

**BAR2**
::   BAR2 是驱动 `kbusVerifyBar2` 自检使用的 MMU 转换地址窗口。如果该测试访问到了 Booter 划出的 WPR2 区域，而不是损坏的显存，就会解码失败，返回 `NV_ERR_MEMORY_ERROR`（`0x72`），并记录 `"BAR 0/BAR 2 failed."`。

**BDF**
::   Bus:Device.Function，即总线:设备.功能，用来表示显卡的 PCI 地址，例如 `0000:0a:00.0`。用户态辅助工具 `tools/retrain.sh` 把 BDF `0a:00.0` 写死，这正是 PCIe Gen2 在不同机器上表现不一致的根本原因。

**Booter / Booter Load**
::   NVIDIA 签名的 ACR 引导加载器 ucode。驱动会在 [SEC2](#s) Falcon 上运行它，以完成认证并启动 [GSP-RM](#g)。解锁器向 Booter Load 传入一个刻意放大的签名缓冲区，使受控溢出能够在 Booter 自己的权限上下文中执行 [ROP 链](../unlock/rop-chain.md)。在发布版流程中，Booter 每次运行都会报告 `0xffff`，无论实际成功还是失败，因此只能通过寄存器回读判断结果。

**BSI scratch**
::   位于 `0x001180xx` 的安全暂存寄存器块，例如 `0x001180f8` 的 `SECURE_SCRATCH_14` 和 `0x001180f0` 的 AON LMR 影子。从 PL0 读取它们会返回 `0xbadf5108`。“BSI”的正式展开在本资料库中尚未确定。

---

## C

**Canary**
::   栈金丝雀。它是每次启动时随机生成的值，Booter 将其放在保存的返回地址下方，并在返回前重新检查，以检测简单的缓冲区溢出。170HX 的 Booter 从 DMEM `0x6340` 读取金丝雀；如果校验失败，就通过 SEC2 邮箱 `0x47` 触发 panic。发布版载荷会在构造的签名缓冲区的多个偏移处写入 `0xc0deca7e`，作为**伪造的金丝雀**。

**CE**
::   Copy Engine，即复制引擎，是 GPU 的 DMA 引擎。这里有两个相关点：发布版补丁 0005 在这类显卡上禁用了基于 VAS 的 CE 清理路径；另一份 Xid 31 捕获则显示，64 GB 窗口顶端的故障客户端是 `ENGINE CE2 HUBCLIENT_HSCE2`。

**CFG0 / CFG1**
::   `NV_PFB_FBPA_CFG0` 和 `NV_PFB_FBPA_CFG1`，即内存控制器配置寄存器。CFG1 定义每个分区的寻址深度，也是显存解锁的主要目标。广播 CFG1 位于 `0x009a0204`；每个 FBPA 的单播副本位于 `0x00900204 + n*0x4000`，其中 n = 0..23。两种 SKU 的出厂 CFG1 都是 `0x02449000`；解锁后，8 GB 卡为 `0x02779000`，10 GB 卡为 `0x02669000`。字节 [23:16] 表示层级：出厂值为 `0x44`，`0x66` 表示每个 FBPA 2048 MiB，`0x77` 表示每个 FBPA 4096 MiB。两种卡的每个活动分区中，未被禁用的每-FBPA CFG0 都读为 `0x07981800`。

**CMP**
::   Cryptocurrency Mining Processor，即加密货币挖矿处理器。NVIDIA 为计算能力受限的挖矿部件推出的产品线，CMP 170HX 是其中基于 GA100 的型号，于 2021 年 9 月 1 日发布。

**CSTATUS_RAMAMOUNT**
::   每个分区的容量回读寄存器，位于 `0x0090020C + n*0x4000`。出厂时，两种 SKU 都读为 `0x200`，即每个 FBPA 512 MiB。如果这里读到 `0xbadf20NN`，说明该分区已被地板清扫，末尾字节编码了实例编号。

**CPU-RM**
::   一种整体式驱动模式：资源管理器运行在主机 CPU 上，而不是 GSP 上。通过 `NVreg_EnableGpuFirmware=0` 选择该模式。它会将 SM 时钟锁定在 1140 MHz 基频，而 GSP-RM 模式会锁定在 1410 MHz。

**CYA_0**
::   BAR0 `0x0008c2c0`。位 2 是 `DIS_G2`，即 Gen2 禁用。Gen2 分支会清除它。

---

## D

**DEVINIT**
::   嵌入 VBIOS 的设备初始化脚本，在其他固件开始运行前执行。ECC、NVLink 以及可能的 PCIe Gen3 等若干未解决限制，被认为在 DEVINIT 阶段就已经确定；这也是启动后进行寄存器覆盖无法解除它们的原因。

**DKMS / srcversion**
::   DKMS 会针对每个内核重新构建树外内核模块。`srcversion` 是模块的源码哈希。将 `/sys/module/nvidia/srcversion` 与 `/lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko` 中的 srcversion 对比，可以确定当前实际运行的是补丁模块还是出厂模块。

**DIO**
::   Falcon 的次级数据 I/O 带外接口，Booter 通过它访问常电域中的暂存寄存器。NVIDIA 的公开文档没有解释这几个字母的含义。一次针对 `0x1180f8` 的受污染 DIO 读取会返回 `0xdead5ec1`。

**DLLLA**
::   Data Link Layer Link Active，即数据链路层链路激活状态，对应 PCIe Link Status 寄存器的第 13 位（`0x2000`）。即使 Gen2 x4 链路已经训练成功，GPU 仍总是报告 LnkSta `0x1042`，并且 DLLLA 为 0。因此补丁 `0008` 的成功判断条件永远不会触发，“retrain completed without Gen2 link”这行在**每台主机上都是假阴性**。同一份捕获中的 `0x7042` 是*上游根端口*的 LnkSta，不是另一类主机的数值；补丁 `0008` 读取的是 GPU 端的状态。

**DMEM / IMEM**
::   Falcon 的数据内存和指令内存。独立工具会在 DMEM `0x0900` 加载 63,232 字节，在 IMEM `0x0000` 加载 45,824 字节；IMEM 按 256 字节块对齐。Falcon 进入 [HS 模式](#h)后，主机既不能读取也不能写入 DMEM：写入会被静默丢弃，`DMEM_PRIV_LEVEL_MASK`（`0x00840284`）会显示 `wr_prot == 0`。

**`dmem.bin`**
::   位于 `/lib/firmware/nvidia/ga100/gsp/dmem.bin` 的可选外部载荷覆盖文件。这是一个开发调试接口。文件不存在时报告状态 `0x59`，属于正常且健康的路径。

---

## E

**ECC**
::   Error-Correcting Code，即纠错码内存。170HX 已通过熔丝关闭 ECC（`FUSE_ECC_EN = 0x0`），没有已知开关，也没有遥测；`nvidia-smi -q` 会将所有 ECC 字段报告为 `N/A`。名为 `ecc` 的分支实际上没有任何 ECC 代码。参见[ECC](../frontier/ecc.md)。

**EPS 8-pin**
::   显卡实际使用的 CPU 式 8-pin 电源接口，额定功率为 300 W，内部带有两条独立的 12 V 供电轨。它**不是** PCIe 8-pin 接口，后者额定 150 W，且两种接口的 12 V 与地线引脚定义不同。参见[风险](risks.md)。

---

## F

**Falcon**
::   NVIDIA 的一系列小型嵌入式微控制器，通常展开为 *FAst Logic CONtroller*。SEC2、GSP 的启动核心和 FECS 都属于 Falcon。Falcon 拥有独立的 IMEM/DMEM、加密协处理器，以及由硬件强制执行的安全模式。

**FBHUB**
::   帧缓冲枢纽，负责连接引擎客户端和帧缓冲分区。`FBHUB_NUM_ACTIVE_LTCS` 位于 `0x00100800`，8 GB 卡读为 `0x10`（16），10 GB 卡读为 `0x14`（20）。

**FBP / FBPA**
::   FBP 是帧缓冲分区，也就是包含 L2 缓存切片和两个 FBPA 的显存子系统分区。FBPA 通常展开为 *frame buffer partition adapter*，即帧缓冲分区适配器，本质上就是 DRAM 控制器。8 GB 卡在 8 个 FBP 上启用了 16 个 FBPA，总线宽度为 4096 bit；10 GB 卡在 10 个 FBP 上启用了 20 个 FBPA，总线宽度为 5120 bit。完整 GA100 有 24 个 FBPA，因此探测工具会遍历 24 个槽位。

**FECS**
::   图形流水线中的前端上下文切换微控制器。`FECS_FEAT_OVERRIDE`（`0x00409664`）和 `FECS_FEAT_READOUT_1`（`0x00409668`）会镜像 PRI 功能覆盖状态；从无特权上下文读取时，返回值为 `0xbadf5040`。

**Floorsweeping**
::   在制造过程中通过熔丝永久关闭有缺陷或多余的单元，例如 GPC、TPC、FBPA 和 NVLink，以便保留部分可用的晶片。地板清扫掩码**按晶片变化**，而不是按 SKU 变化：四张 170HX 读到的 `OPT_GPC_DISABLE` 分别为 `0x85`、`0x45`、`0x13` 和 `0xa8`，但四张卡仍都枚举出 70 个 SM。不要硬编码某个地板清扫值。

**FLR**
::   Function Level Reset，即功能级复位。它是通过 `echo 1 > /sys/bus/pci/devices/<BDF>/reset` 触发的 PCIe 单功能复位。170HX 在 DevCap 中声明支持 `FLReset+`，这正是解锁工具能够工作的原因。一次成功的 FLR **确实**会清除 WPR2，也会清除 SEC2 的复位 PLM 污染，使其从 `0x8f` 回到 `0xff`；但它不会复位 [AON island](#a)。

**FRTS**
::   FWSEC 命令，用于在 GSP 启动前于帧缓冲中建立固件驻留区域，由 `kgspPrepareForBootstrap` 调用。该缩写的正式展开在本资料库中尚未确定。

**FWSEC / FWSECLIC**
::   驻留在 VBIOS 中的固件安全 ucode，会在启动早期运行于某个 Falcon，并负责执行 FRTS 分区等工作。发布版补丁 0002 的主要目的之一，就是让 FWSEC 失败变得可诊断：它把致命断言转换成 `SEC2_DEBUG: FWSEC status=0x%x` 形式的日志。FWSECLIC 是与之配套的许可证检查程序。

---

## G

**GA100**
::   A100 和 CMP 170HX 共用的 Ampere 数据中心晶片，采用 TSMC 7 nm N7 工艺，拥有 542 亿个晶体管，面积为 826 mm²，使用 BGA-2743 封装，CUDA 计算能力为 8.0。每个被探测到的 GA100，其 `PMC_BOOT_0` 都读为 `0x170000a1`。

**GPC / TPC / SM**
::   分别指 Graphics Processing Cluster（图形处理集群）、Texture Processing Cluster（纹理处理集群）和 Streaming Multiprocessor（流多处理器）。两个 SKU 的 170HX 都枚举出 5 个活动 GPC、35 个活动 TPC 和 **70 个 SM**，共 4480 个 CUDA 核心，已经达到熔丝设定的下限。完整 GA100 则有 8 个 GPC 和 64 个 TPC。

**GSP**
::   GPU System Processor，即 GPU 系统处理器。它是 Ampere 及后续架构中的 RISC-V 微控制器，负责在 GPU 晶片上运行大部分资源管理器。

**GSP-RM**
::   运行在 GSP 上的资源管理器固件映像。它在主机侧的对应实现是 Kernel-RM / CPU-RM。本维基记录的启动失败，几乎都是 GSP-RM 引导失败。

---

## H

**HBM2 / HBM2e**
::   High Bandwidth Memory，即高带宽内存，是 GA100 使用的堆叠式 DRAM。170HX 的理论峰值为 1555.2 GB/s，即 5120 bit 总线、1215 MHz DDR。实际测量值会因工具和访问模式而不同，范围约为 1305.86 至 1600 GB/s，没有唯一的标准数值。

**HS mode**（Heavy Secure）
::   Falcon 的最高权限模式。只有通过签名验证后，代码才能进入 HS。进入 HS 后，IMEM `0x00` 处的低安全引导程序会被擦除，主机无法再访问 DMEM，Falcon 则可以写入原本被 PL0 阻挡的寄存器。显存解锁之所以可行，正是因为那组关键寄存器写入只能从 HS 模式执行。

**HULK**
::   NVIDIA 用于启用调试和厂商功能的内部许可证/证书机制。170HX 在许可证区域 `0xFE000`-`0xFEFFF` 中带有一个已经建立但内容为空的 HULK 目录表。该路线已经调查过，并被排除。

---

## I

**InfoROM**
::   VBIOS 映像中按板卡持久保存序列号和校准数据的区域。在 DRIVE A100 上，两颗物理上不同但使用相同固件的 GPU，其字节差异有 99.5% 来自这个区域。

**IOMMU**
::   主机输入/输出内存管理单元。安装解锁器后，如果 PCIe 仍停留在 Gen1，首先应检查直通模式（`iommu=pt`）。安装器会自动设置 `intel_iommu=on iommu=pt`，或设置 AMD 平台上的等效参数。

---

## L

**LMR**
::   `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`，位于 `0x00100ce0`，表示 MMU 认定的本地显存容量。编码方式为 `size_MiB = MAG[9:4] << SCALE[3:0]`。出厂值为 `0x00000208`（8 GB 卡）和 `0x00000288`（10 GB 卡）；解锁值为 `0x0000020B`（64 GB）和 `0x0000028A`（40 GB）。它对应的 PLM 位于 `0x001fa7c4`（`..._LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`），AON 域中另有一个影子寄存器，地址为 `0x001180f0`。**不要**把 LMR 展开成“LM Request”。

**LnkCap / LnkCap2 / LnkCtl2 / LnkSta**
::   PCIe Express Capability 中的一组寄存器，分别表示链路能力、支持的速度、目标速度和已经训练出的状态。出厂 170HX 的值为 `LnkCap 0x00456101`、`LnkCap2 0x00000002`、`LnkSta 0x1041`；使用解锁器后为 `LnkCap 0x00456102`、`LnkCap2 0x00000006`、`LnkCtl2 0x0002`、`LnkSta 0x1042`。设备声明支持的能力，不等于实际训练成功的链路状态。

**LTC**
::   Level-two cache slice，即二级缓存切片。170HX 的 L2 缓存为 32 MB，A100 为 40 MB。

**LTSSM**
::   Link Training and Status State Machine，即链路训练与状态机，负责在 PCIe 中协商链路速度和位宽。在这张卡上，Gen2 补丁中称为 LTSSM 的寄存器位于 BAR0 `0x0008872c`，写入值为 `0x00000006`。该寄存器块中的其他相关字段包括 LTSSM_DIRECTIVE（0 = NORMAL，1 = CHANGE_SPEED）以及位于 [19:18] 的 SPEED 字段。

---

## M

**MIG**
::   Multi-Instance GPU，即多实例 GPU，是 Ampere 提供的硬件分区功能。在解锁后的 170HX 上，设置 `0x820840` 的第 0 位即可启用；之后 `nvidia-smi` 会报告 `MIG M. Enabled`，并显示 65536 MiB 显存。

> [!WARNING]
> **实验性**
>
> 启用 MIG 属于社区提供的额外写入，**不包含在**发布版解锁器中。

**MOK / Secure Boot**
::   Machine Owner Key，即机器所有者密钥。通过登记 MOK，可以让签名的树外内核模块在 UEFI 安全启动开启时加载。当前补丁模块没有签名，因此如果 `mokutil --sb-state` 报告 `SecureBoot enabled`，`install.sh` 会直接失败。

---

## N

**NVGI / PciAt / FwSec body**
::   GA100 VBIOS 映像中的三个主要区域。NVGI 最先执行，由 PBUS/XVE 的 ROM 初始化序列器在任何固件运行前处理；PciAt 保存 PCI 可见的设备身份；FwSec body 保存签名固件。8 GB 和 10 GB VBIOS 映像之间的全部功能差异，最终都归结为 NVGI 引导程序中的 2 个字节。

**NVLink**
::   170HX 已通过熔丝关闭 NVLink（`FUSE_NVLINK_DIS`），任何固件或驱动改动都无法恢复。板侧是否安装了 NVLink 接口 IC，目前仍未确定。参见[NVLink](../frontier/nvlink.md)。

**nvidia-open**
::   NVIDIA 的开源 GPU 内核模块。`cmpunlocker` 修改的是这套模块，而不是专有驱动模块；目前只接受 `610.43.03`（默认版本）和 `610.43.02`。

---

## O

**OTP**
::   One-Time Programmable，即一次性可编程。相关熔丝保存了算力节流信息（`OPT_SM_SPEED_SELECT`，共 9 个独立熔丝）、设备 ID、PCIe 代数禁用状态和地板清扫掩码。用于暴露这些信息的寄存器只是只读的熔丝影子。位于 `0x008203f0` 的主清除熔丝读为 `0x00000000`，表示尚未烧断；这正是各种功能覆盖仍然可能实现的原因。

---

## P

**P2P**
::   Peer-to-peer，即 GPU 之间的点对点传输。这张卡不支持该功能。

**PLM**（权限级别掩码）
::   按寄存器设置的访问控制掩码，用来决定哪些权限级别可以读写它保护的寄存器。权限级别从 PL0（主机）到 PL3（重度安全）。打开 PLM 是整个解锁过程的关键：发布版驱动的内部路径会按顺序打开以下四个掩码，每个最多尝试两次：

    | 索引 | 名称 | 地址 | 目标值 |
    |---|---|---|---|
    | 0 | `WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` |
    | 1 | `FBPA` | `0x009a0148` | `0xffffffff` |
    | 2 | `WPR` | `0x001fa7c4` | `0xffffffff` |
    | 3 | `FEAT` | `0x00823804` | `0xffffffff` |

    `WPR_CFG` 回读为 `0xfffff0ff` 是**正确的**，不表示失败。声称“所有 PLM 都必须读为 `0xffffffff`”的指南要求过严。

**PMA**
::   Physical Memory Allocator，即物理内存分配器。它是负责管理帧缓冲页的 RM 对象（`pmaRegisterRegion`、`pmaGetFreeMemory`、`PMA_REGION_DESCRIPTOR`）。发布版补丁 0003 会执行一次“延迟 PMA 扩展”，扩大高地址 PMA 区域，以覆盖新暴露的帧缓冲，并记录 `SEC2_DEBUG: late PMA extension status=0x%x`。它与电源管理没有关系。

**PMC_BOOT_0**
::   位于 BAR0 `0x00000000` 的芯片身份寄存器。每个 GA100 都读为 `0x170000a1`；一个 GA10x 对照部件读为 `0xb74000a1`。

**PRAMIN**
::   特权 BAR0 窗口，使 CPU 可以直接访问显存中的一段可移动区域。当 `fbAddrSpaceSizeMb > 0x2000` 时，发布版补丁 0004 会把 PRAMIN 基址限制回基于出厂 8 GB 容量计算的偏移量（`(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`）。否则窗口会按 65536 MB 计算，落到 BAR0 可访问范围之外。PRAMIN 也曾被用来证明 10 GB 卡上存在 80 GiB 的物理 DRAM。

**PRI**
::   GPU 内部的特权寄存器总线。读取被权限阻挡或不存在的目标时，不会返回数据，而会返回 `0xbadfXXXX` 形式的毒值：`0xbadf5040` 表示被权限级别掩码阻挡，`0xbadf1100` 表示目标不存在，`0xbadf20NN` 表示目标存在但对应 FBPA 已被地板清扫，`0xbadf5108` 表示从 PL0 读取 AON 安全暂存区。

**`probe.sh`**
::   只读表征工具（`tools/mmio-probe`）。它以只读方式 mmap `resource0`，转储约 120 至 130 个具名寄存器，并读取 24 个 FBPA 的对应寄存器；它**从不向 BAR0 写入**。相关常量为 `FBPA_BASE = 0x900000`、`FBPA_STRIDE = 0x4000`、`CSTATUS_RAM = 0x20C`。工具会输出 `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv` 和 `probe.log`。它是标准验证工具：完成任何写入后，都应使用 `probe.sh` 回读寄存器，不要只相信工具报告“成功”。

**PTE kind**
::   GPU 页表条目中的 `kind` 字段，用来描述压缩和分块格式。对于这些设备 ID，发布版补丁 0005 强制设置 `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY`，取代原来的 `..._COMPRESSIBLE_DISABLE_PLC`。

---

## R

**RFRD**
::   VBIOS SPI ROM 中记录映像布局的描述符，位于绝对地址 `0x2000`。某个社区解析器曾将它误标为“power table”，但它并不是电源表。

**ROP chain**
::   Return-Oriented Programming chain，即面向返回编程链。它完全由已签名代码中现成的短指令序列（“gadgets”，即小工具）组成，通过覆盖返回地址将这些序列串联起来，因此不需要为新代码签名。在这张卡上，ROP 链放在超大的 GSP 签名缓冲区中，由 SEC2 Booter 执行。Booter 从 DMEM `0xFF5C` 读取被劫持的返回地址；`0xFF48` 是 `0x4d4` pop 块中保存 r3 的槽位，也是 `0x18` 字节帧网格的起点。因此，在已经被替代的独立链中，包含 N 次写入的尾部从 `0xFF48 + N*0x18` 开始。参见[ROP 链](../unlock/rop-chain.md)。

---

## S

**SBR**
::   Secondary Bus Reset，即次级总线复位。它由上游桥发出，比 FLR 更强。SBR 会关闭并重新初始化常电域，因此能够清除那些根植于 AON 暂存区、可以挺过 FLR 的卡死状态。

**SCP**
::   Falcon 的 Secure Co-Processor，即安全协处理器，是用于签名验证和密钥处理的加密模块。Falcon 引擎复位恢复期间，会轮询 `SCP_CTL_P2PRX` 的第 3 位（SFK_LOADED）。

**SEC2**
::   GPU 的安全引擎 Falcon，BAR0 基址为 `0x00840000`（邮箱 0 位于 `0x00840040`）。它负责运行 Booter ucode，也是解锁机制利用的引擎。它的复位 PLM 观测值地址据报告为 `0x008403C4`，但具体身份仍有争议。干净状态下读为 `0xff`；运行 `secure_teardown` 后读为 `0x8f`；驱动仍加载、处于部分触发状态时读为 `0x00cf`。

**Signature buffer**
::   保存 GSP 固件签名的内存描述符。出厂大小为 4096 字节；发布版补丁将其扩大到 `0x0000f800`（63,488 字节），并填入载荷和 dword `0x000004a7`。更早的方案曾尝试直接修改磁盘上的 `gsp_tu10x.bin`，但 `fwsignature_ga100` 节只有 `0x1000` 字节，因此无法继续。

**SS0 / SS1**
::   分别指 `FEATURE_OVERRIDE_SM_SPEED_SELECT`（`0x0082381c`）和 `..._SM_SPEED_SELECT_1`（`0x00823820`）。它们控制每个指令单元的**发射速率**，不决定哪些 SM 处于活动状态。解锁时写入的值分别是 `0x88888888` 和 `0x00000008`。锁定卡的 SS0 可能读为 `0x53540175`。这两个寄存器属于 AON，可以挺过 FLR；它们不是“Suspension State”寄存器。

**Strap / strap resistor**
::   一个 0402 电阻和旁边的空焊盘。把元件移到两个位置中的另一个位置，就会改变硬件采样到的配置位。170HX 上有 5 对跨接位（共 10 个焊盘，位号为 R986 至 R1005），另有一对位于其他位置的 DEVID_SEL。主 PCIe 设备 ID 已熔入晶片，**不能**通过跨接设置；`FUSE_DEVID_SW_OVR_DIS 0x00820584` 在每张被探测的卡上都读为 1。

---

## V

**VBIOS**
::   显卡的固件 ROM。目前公开存在 4 款 170HX 映像，其中两款在 TechPowerUp 上被标成“16 GB”和“0 GB”，这些容量标签是错误的，而且两者都不能解锁显存。VBIOS 版本不会影响解锁是否生效。参见[VBIOS](../hardware/vbios.md)。

**VSEC**
::   Vendor-Specific Extended Capability，即厂商特定扩展能力，是 PCIe 配置空间中的扩展能力块。对 Gen2 来说，有两个寄存器很重要：`VSEC_DEVICE` 位于 `0x0008860c`，由 Booter 载荷将位 0 置为 1；`VSEC_HIERARCHY` 位于 `0x00088610`，在 Booter 阶段结束后由主机通过普通 BAR0 写入。

---

## W

**WPR / WPR1 / WPR2**
::   Write Protected Region，即写保护区域。它是 MMU 不允许无特权代理写入的帧缓冲范围，用来保存 ACR 和 GSP 固件状态。WPR2 的 lo/hi 值位于 `0x001fa824` 和 `0x001fa828`。禁用时读数为 `0x1FFFFE00 / 0x00000000`；运行一次 Booter 后读数为 `0x01F77000 / 0x01FFEE00`。发布版补丁会各保存一次这两个值，并在**每一次** Booter Load 尝试前重新写入，而不是清除它们。“WPR2 already up”曾是早期最常见的失败原因，现在已经降级为一条允许流程继续的警告。

**WprMeta**
::   描述 WPR 布局的元数据结构，包括 `fbSize` 和 `sizeOfSignature`。该结构由驱动填充，再由 Booter 验证。

---

## X

**Xid**
::   NVIDIA 驱动发出的错误编号。本资料库中比较重要的有：

    | Xid | 在本语料库中的含义 |
    |---|---|
     | 31 | MMU 故障，`FAULT_INFO_TYPE_REGION_VIOLATION`。表示分配越过了解锁窗口的可用上限，显卡在重启前无法继续用于 CUDA。在 80 GB 配置下，访问超过约 40 GB 的内核会在与功耗上限无关的情况下造成致命 GPU 丢失；报告的错误码包括 Xid 31（有人称其为无害）以及 CUDA 内存测试后的 Xid 154，最常见的症状是卡死。单独将 Xid 31 视为该故障的特征，是旁观者提出的说法，故障卡的操作者并未证实这一点。 |
     | 45 | 对正在运行的 CUDA 验证内核执行 SIGKILL 后触发，并要求进行一次复位循环。 |
     | 119 | GSP RPC 超时。有两种不同情况：等待函数 4097 `GSP_INIT_DONE` 超过 60 秒，表示启动从未完成；等待函数 103 `GSP_RM_ALLOC` 超过 6 秒，表示启动后卡死，之后每次执行 `nvidia-smi` 都会重复。 |
     | 154 | 过度配置的 80 GB 模式在 CUDA 内存测试后的主要故障；每次触发后，显卡只能保留一个 CUDA 上下文。 |

**XP3G**
::   位于 `0x0008e1xx` 的 PCIe 链路层覆盖模块，包括 `XP3G_OVR0`（`0x0008e110`）、`XP3G_VAL0`（`0x0008e120`）、`XP3G_OVR3`（`0x0008e11c`）、`XP3G_VAL3`（`0x0008e12c`），以及 4 个 PLM：`0x0008e1b0`、`0x0008e1b4`、`0x0008e1b8`、`0x0008e1bc`。Gen2 补丁通过 Booter 载荷原语写入 23 项的 `xp3gTable`，包括 18 次打开 PLM 和 5 次写入数值。NVIDIA 没有公开这个名称的正式展开。

**XVE**
::   NVIDIA 对 PCI Express 端点和配置空间模块的内部名称，基址为 `0x00088xxx`。Gen2 系列分支在表中加入了 3 个 XVE 能力 PLM：`0x00088ff4`（XVE）、`0x00088ab4`（XVE_B）和 `0x00088ff8`（XVE_C）。NVIDIA 的公开文档没有解释这些字母的含义。

---

## 数字、代码和文件路径

**`0x008200FC`**
::   同一个寄存器有两个名称。分支源码中写的是 `{0x008200fcU, 0xffffffffU, "OPT_PLM"}`，因此 `OPT_PLM` 是代码中的名称；净室工具则称其为 `FUSE_SS_PLM`。发布版 `master` **不会**写入这个寄存器。它是否可写，以及冷卡上的读数是多少，目前仍没有定论。

**`0xbadfXXXX`**
::   参见[PRI](#p)。这些值不是实际存储的数据，而是寄存器访问失败时返回的标记值。

**`0xc0deca7e`**
::   写入构造签名缓冲区的伪金丝雀标记值。

**分支名称**
::   共有 **12** 个未发布分支快照（`80`、`Gen2`、`PG199`、`clanker_driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`），加上当前发布的 `master`，一共 13 棵代码树。把它们称为“13 个未发布分支”的文档多算了一个。

**`/lib/modules/$(uname -r)/updates/cmpunlocker/`**
::   安装程序写入补丁模块和 3 个标记文件的目录：`driver_version`、`card_profile`（`8gb` 或 `10gb`）以及 `unlock_geometry`。多卡分支还会增加 `gpu_inventory`。

**`SEC2_DEBUG`**
::   解锁路径使用的日志标签。`sudo dmesg | grep SEC2_DEBUG` 是首要、也是唯一的核心诊断手段。另外还有两个同类标签：`SEC2_DEBUG_HEAP` 和 `SEC2_DEBUG_LATE_PMA`。它们都以 `LEVEL_ERROR` 级别输出，不需要额外开启调试标志。如果完全没有 SEC2_DEBUG 日志，说明补丁模块从未运行。

---

## 本维基提到的工具

| 工具 | 在这里的用途 |
|---|---|
| `clpeak` | OpenCL 带宽和算力微基准工具；Gen1 x4 约 0.85 GB/s 的数值来源 |
| `cuda_memtest` | GPU 显存验证工具；80 GB 档位在重启后可以通过一次，随后失败 |
| `gpu-burn` | 带错误计数器的持续算力压力测试工具；稳定的 40 GB 卡可以无错误运行 5 分钟 |
| `mixbench` | 混合精度吞吐测试工具；其中 `1769.47 GB/sec` 是理论值，不是实测值 |
| `nvtop` | 实时显示每张 GPU 的遥测信息，包括 PCIe 代数和链路位宽 |
| `ocl_pcie_bw` | OpenCL 主机到设备带宽测试工具；Gen2 x16 的 6.63 至 6.67 GB/s 数值来源 |
| `pcielink.sh` | 社区提供的链路训练信息采集脚本；会打印 GPU 和桥的身份，以及完整的 LnkCap/LnkSta/AER 信息 |
| `probe.sh` | 只读寄存器调查工具，见上文的 [PRI](#p) |
| `verify.sh` | 多卡分支中按 BDF 验证解锁状态的工具 |
| `CH341A` | SPI 闪存编程器。GPU EEPROM 使用 1.8 V，因此需要 1.8 V 转接器 |

---

## 参见

- [如何阅读本维基](how-to-read-this-wiki.md)：了解置信度和证据等级。
- [寄存器参考](../unlock/register-reference.md)：在一张表中查看所有地址。
- [识别你的卡](identify-your-card.md)：确认你手中的 SKU。
