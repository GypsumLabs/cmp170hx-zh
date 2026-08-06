# PCIe 子系统

**本页内容：** CMP 170HX 的 PCIe 接口出厂时的物理和固件状态。卡离开工厂时带的两项限制、速度上限背后的熔丝和 DevInit 证据、位宽上限背后的缺件交流耦合电容、一张出厂卡精确的寄存器和 `lspci` 状态，以及会被误认为其中任一者的平台级干扰因素。速度上限的软件破解在[Gen2 解锁](../unlock/pcie-gen2.md)；破解位宽上限的焊接工作在[物理改装](../operations/physical-mods.md)。

## 头条：两个上限、两种机制、两种修复

一张出厂 CMP 170HX 以 **PCIe Gen1（2.5 GT/s）配 x4** 训练。那是两个完全独立的限制，恰好共存于同一块板上，破解其中任一对另一个毫无作用。

| | 速度上限 | 位宽上限 |
|---|---|---|
| 观察到的状态 | 2.5 GT/s（Gen1） | x4 训练，x16 宣告 |
| 机制 | OTP 熔丝加一个签名的 DevInit 表，固件强制 | 16 条通道中的 12 条出厂时交流耦合电容缺件 |
| 住在哪 | 硅片和 SPI 闪存 | PCB |
| 被破解 | 未发布分支上的驱动补丁（仅 Gen2） | 手工焊接 24 × 0402 电容 |
| 状态 | Gen2 于 2026-07-24 软件达到，**未发布**；Gen3 和 Gen4 未达到 | 自 2026 年 4 月起被多位独立改装者复现 |
| 会改变另一个吗？ | 不会。一张 Gen2 补丁的未改装卡是 Gen2 x4。 | 不会。一张完全改装的无补丁卡是 Gen1 x16。 |

证明两者独立的最清晰单条证据：一张出厂、从未焊接的 8 GB 卡运行 Gen2 代码时报告 `LnkCap: Port #0, Speed 5GT/s, Width x16`，而 `LnkSta` 读 `Speed 5GT/s, Width x4 (downgraded)`。能力寄存器说 x16；训练好的链路说 x4。软件中没有任何东西能弥合那个差距，因为 12 条通道上没有电气路径。

> [!WARNING]
> **实验性**
>
> 本页所有关于 Gen2 的内容描述的都是未发布分支代码。已发布的 `master` 不含任何 PCIe 补丁。参见[Gen2 解锁](../unlock/pcie-gen2.md)。

## 出厂链路状态

### `lspci` 打印什么

```console
$ sudo lspci -s 0a:00.0 -vvv | grep -E 'LnkCap|LnkSta|LnkCtl'
LnkCap: Port #0, Speed 2.5GT/s, Width x16, ASPM not supported
        ClockPM+ Surprise- LLActRep- BwNot- ASPMOptComp+
LnkCtl: ASPM Disabled; RCB 64 bytes, Disabled- CommClk+
LnkSta: Speed 2.5GT/s, Width x4 (downgraded)
LnkCap2: Supported Link Speeds: 2.5GT/s, Crosslink- Retimer- 2Retimers- DRS-
LnkCtl2: Target Link Speed: 2.5GT/s, EnterCompliance- SpeedDis-
LnkSta2: Current De-emphasis Level: -6dB, EqualizationComplete-, EqualizationPhase1-
```

两个细节值得内化。`LnkCap` 宣告 **Width x16**，所以卡知道自己有十六条通道；`LnkSta` 上的 `(downgraded)` 标记意味着链路*协商*降级，这正是接收端在通道 4 到 15 上看不到信号时发生的事。而 `LnkCap2` 只列出 2.5 GT/s 受支持，按 PCIe 规范这会钳制你写给 `LnkCtl2` 的任何目标链路速度：在出厂卡上写 `0x2` 读回来是 `0x1`。

内核每次启动都用它自己的话说明同一件事：

```text
pci 0000:0a:00.0: 8.000 Gb/s available PCIe bandwidth, limited by 2.5 GT/s PCIe x4 link at
  0000:09:01.0 (capable of 32.000 Gb/s with 2.5 GT/s PCIe x16 link)
```

注意内核在对比什么：2.5 GT/s x16 下的 32 Gb/s。它抱怨的是位宽，不是速度。

### 原始寄存器值

下面所有地址都是 XVE 配置空间的 BAR0 镜像。PCIe Express 能力位于配置偏移量 `0x78`（不是 `0x60`），XVE 影子基址是 `0x88000`，所以配置 `cap+0x0C` 映射到 BAR0 `0x00088084`，依此类推。

| 字段 | 配置偏移量 | BAR0 镜像 | 出厂，无解锁 | 带解锁器 |
|---|---|---|---|---|
| LnkCap | `CAP_EXP+0x0C` | `0x00088084` | `0x00456101` | `0x00456102` |
| LnkCtl / LnkSta | `CAP_EXP+0x10` | `0x00088088` | LnkCtl `0x0140`，LnkSta `0x1041` | LnkCtl `0x0140`，LnkSta `0x1042` |
| LnkCap2 | `CAP_EXP+0x2C` | `0x000880a4` | `0x00000002` | `0x00000006` |
| LnkCtl2 / LnkSta2 | `CAP_EXP+0x30` | `0x000880a8` | `0x0000` / `0x0000` | `0x0002` / `0x0001` 或 `0x0000` |
| DevCap2 | | | `0x00070803` | `0x00070813` |
| DevCtl2 | | | `0x1400` | `0x0400`（一台机器 `0x7410`） |

`nvidia-smi` 把 `pcie.link.gen.current, pcie.link.gen.max, pcie.link.width.current` 报告为：无解锁安装的卡上 **1, 1, 4**，带解锁器的卡上 **2, 2, 4**。两种情况下位宽都不动。

> [!NOTE]
> **不要复述一个已发布的地址**
>
> 一份广泛流传的实地手册把 LnkCap2 的 BAR0 镜像列为 `0x8808C`。这内部自相矛盾：XVE 镜像基于 `0x88000`，配置 `0xA4` 映射到 `0x880A4`，而 `0x8808C` 映射到配置 `0x8C`。分支补丁（`#define PCIE_GEN2_LINK_CAP2_ADDR 0x000880a4U`）和社区 `pcielink.sh` 诊断都用 `0x880A4`。用 `0x880A4`。

### 其它出厂配置空间事实

| 项 | 值 |
|---|---|
| 插槽功耗上限（DevCap） | 75 W |
| MaxPayload / MaxReadReq | 256 字节 / 512 字节 |
| ASPM | 不支持（在 LnkCap 中宣告） |
| FLReset | 支持 |
| BAR0 | 32 位不可预取区域里的 16 MB，孔径 `0x1000000` |
| BAR1 | 64 MB，64 位可预取 |
| BAR3 | 32 MB，64 位可预取 |
| Resizable BAR 能力 | 存在于 `[bb0 v1]`，但每个 BAR 恰好宣告一个受支持大小 |

无论卡报告多大的帧缓冲，BAR1 都停在 64 MiB，所以即使一张报告 81920 MiB 的卡上，全 VRAM 主机映射也不可用。因此 Resizable BAR 被宣告但功能上惰性。ReBAR "requires PCIe 3.0" 的旧异议是错的（ReBAR 是一个配置空间能力，自 2007 年就在规格里，与链路代数无关），但也没人在一张 Gen2 训练的 170HX 上演示过可工作的 ReBAR。

## 速度上限

### 熔丝证据

三个 OTP 熔丝影子形成这个锁的指纹。170HX 读 **1 / 1 / `0x16680000`**，而每一个对比的 Ampere 部件读 **0 / 0 / 无位 25 的东西**。

| 寄存器 | 地址 | 170HX（两个 SKU） | A100（全部三个 SKU）和 Drive A100 | 备注 |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | `0x0082057c` | `0x00000001` | `0x00000000` | 在 A10、A5000、A6000、RTX 3080 / 3080 Ti / 3090 / 3090 Ti 和一张 GA10x 对照卡上也是 0 |
| `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | `0x00820580` | `0x00000001` | `0x00000000` | 同一队列 |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000`（位 25 置位） | `0x00200000` | 位 25 被记录为 `GEN4_SPEED_DISABLED`，引用 NVIDIA bug 2220334。A10/A5000/A6000 读 `0x01a00000`；RTX 30 系读 `0x10a80000` |

两个 170HX 值都在两块物理单元上测得，每个部件读两次，跨一个 15 卡对比队列。`0x20c2` 读数来自一份驱动侧转储，打印 `OPT=00000001/00000001/16680000`；`0x2082` 读数来自一次独立探测的 `registers.json`。

两个相关熔丝关死显而易见的变通方案。`0x820040` 的 `FUSE_EN_SW_OVERRIDE` 读 0、`0x820084` 的 `FUSE_DIS_SW_OVR` 读 1，所以软件覆盖路径在硅片中被禁用。`0x820148` 是一个读 0、软件永远无法置位的 OTP 备用位；DevInit 只在 `0x820148 & 1` 时把 A100 值 `0x00200000` 写给 `MAGIC_D`，这恰好就是 DevInit 在 CMP 上从不写它的原因。

`0x0082057c` 的 `OPT_GEN23` 已从每一个可用的权限被攻击过：普通主机写、HS 特权驱动写、以及 SEC2 Booter 载荷。每次尝试都失败，回读仍是 `0x00000001`。它是一个没有写端口的纯熔丝感测反射。更多在[熔丝与 OTP](fuses-and-otp.md) 和[死路](../history/dead-ends.md)。

> [!NOTE]
> **熔丝不是杠杆**
>
> Gen2 解锁**在 `OPT_GEN23` 仍读 `0x00000001` 时**工作。已发布的分支补丁仍尝试写入、仍失败，Gen2 仍训练。可用的杠杆是 CYA_0、LINK_CONFIG_0、XP3G 和 PRIV_MISC_1 覆盖，不是熔丝影子。

### DevInit 层

熔丝只是三层之一。第二层是 SPI 闪存里**未加密** DevInit Falcon 映像内的一张 PCIe 配置表，它与传统的 x86 VBIOS 分开。

| 项 | CMP 170HX | A100 |
|---|---|---|
| PCIe 配置表，闪存偏移量 | `0x420ED`（镜像 `0xA20ED`） | `0x408A0`（镜像 `0xA08A0`） |
| 运行时 DMEM 基址 | `0xF1D` | `0xE50` |
| 那五个字节，表偏移量 `+0xC7` 到 `+0xCB` | `00 00 08 00 06` 在闪存 `0x421B4`-`0x421B8` | `00 00 14 00 06` 在闪存 `0x40967`-`0x4096B` |
| 表偏移量 `+0x0F` 的抑制标志 | `0x01` | `0x00` |
| DevInit 映像位置 | 闪存 `0xDE00`（反汇编基址 `0x8000`），在 bank 2 的 `+0x60000` 处复制 | |

抑制标志是决定性的：在 CMP 上，`ld b8 r9, D[tab+0x0F]; bra ne` 跳过整个 Gen4 编程块（反汇编 `0x31B3F`-`0x31B92`）。当那个块确实运行时，它计算 `0x88CE4 = (old & ((b1<<8)|b0)) | ((b3<<8)|b2)`，因为 `b0 = b1 = b3 = 0` 而归结为字节 `[+0xC9]`，以及 `0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)` 配 `b4 = 0x06`（两个部件都是）。一次更宽泛的符号分析发现总共有**十三个** DevInit 字节不同，其中十一个可归因于非 PCIe 的 SKU 功能（HBM、NVLink、ECC）；与 PCIe 相关的是 `[0xC9]`（喂 `0x88CE4`）、`[0x1C-0x1F]`（喂 `0x8C2C0`）和 `[0x3F]`（喂 `0x8C040`）。CMP 和 A100 的 BIT 表逐字节相同。

编辑那些字节是一条关闭的路径。五个字节全部 **100% 在** Davies-Meyer `csecret(2)` MAC 范围 `0x2200`-`0x43C00` 内，所以无钥伪造是一个 2^128 次第二原像，而重刷一个编辑过的映像会直接失败于 Ampere RSA 签名检查。参见[VBIOS](vbios.md)。

> [!CAUTION]
> **不要尝试修改过的重刷**
>
> 一个编辑过的 DevInit 或 VBIOS 映像被签名检查拒绝，卡不会启动。恢复需要一个外部编程器。碰闪存之前先读[恢复](../procedures/recovery.md)。

第三层是运行时：DevInit 本身从不读 `0x82057C` 或 `0x820580`。对 CMP DevInit 反汇编的一次穷举搜索只找到 `0x820C14`/`0x820D38`（FBIO/FBP 地板清扫）、`0x820684`（`FUSE_NVLINK_DIS`）、`0x82380C`/`0x823814`、`0x820520`、`0x820148`、`0x8243xx`、`0x8202xx`、`0x8201xx`、`0x82033C`/`0x82030C`。GSP-RM 是消费方：`470.42.01 gsp.bin` 里 `0x5D55834` 处的一张熔丝读跳转表用 `li a2, 0x580` 和 `li a2, 0x57c`，而 `580.105.08 gsp_tu10x.bin` 在 `0x4DD9B00` 用 `li a2, 0x57c` 做 `jalr fuse_read`。这就是为什么 Gen3 路径目前被描述为需要一个 GSP 补丁。

### 启动顺序

FWSEC-DevInit 在 SEC2 Booter 运行前编程并**锁存** `SUPPORTED_LINK_SPEED`，而 SEC2 Booter 正是解锁的时序洞 gadget 所在。因此锁存的能力在任何一个漏洞窗口打开前就已经固定。显存和算力解锁落地，是因为 `FEAT_OVR`（`0x82381C` / `0x823804`）和 FBPA（`0x9A0204`）是 16 MB BAR0 内的普通寄存器，一旦它们的 PLM 被打开就可写。一个锁存的 PHY 能力不是。Gen2 结果实际做的是让 PHY 反射再生成为 Gen2，然后在任何东西重新钳制它之前训练链路。

### 速度能力住在哪，逐寄存器

| 寄存器 | 地址 | 访问 | 备注 |
|---|---|---|---|
| 受支持速度源 | `0x00085080` | 只读，`[23:20]` | 从主机读 `0xBADF1100`（毒值）；在 4.1 M 行 RM 反汇编中零写入者 |
| 允许-Gen 掩码 | `0x00085084` | 每次重训练由 GSP-RM 重新推导 | 也读毒值 |
| `MAX_LINK_SPEED` | `0x00088084` `[3:0]` | PHY 反射，标 `R-XVF` | 无写端口 |
| `SUPPORTED_LINK_SPEED` | `0x0008808C` `[7:1]` | PHY 反射，标 `R-EVF` | 任何权限下都无写端口 |
| `TARGET_LINK_SPEED` | `0x000880A8` `[3:0]` | RW，但被 SUPPORTED 钳制 | |
| `LINK_CONTROL_STATUS` | `0x00088088` | `[19:16]` 处的活协商速度 | |
| `PRIV_MISC_1` | `0x0008841C` | PLM 下 RW | CYA Gen2/3 覆盖位 11-16、30、31 |
| `VSEC_HIERARCHY` | `0x00088610` | PLM 下 RW | 位 12 门控 PRIV_MISC_1 重新编程；活值 `0x00001001` |
| LTSSM 重训练触发 | `0x0008872C` | PLM 下 RW | 写 `6` |
| `PPCI_2.CONFIG_LINK`（`LINK_CONFIG_0`） | `0x0008C040` | PLM 下 RW | `[3:0]` LTSSM_DIRECTIVE，`[4]` LTSSM_STATUS，`[19:18]` SPEED（0 = 最大，2 = 5.0 GT/s，3 = 2.5 GT/s）。CMP 读 `0x800C4C00`（SPEED = 3）；A100 读 `0x80004C00`（SPEED = 0） |
| `CYA_0` | `0x0008C2C0` | PLM 下 RW | 位 2 是 `DIS_G2` chicken 位。CMP `0x068731B7` 对 A100 `0x060711B2` |
| `PL_LINK_RATE` | `0x0008C1C0` | | A100 读 `0x00040036` |
| `PPCI.UNK1C0` | `0x000881C0` | 主机读返回 `0xbadf5040` | rnndb：`[17:16]` LNK_CAP_SPEED，`[21:20]` SYSTEM_MAX_SPEED |

全篇使用的速度向量编码：Gen1 = `0x1`，Gen1_2 = `0x3`，Gen1_2_3 = `0x7`，Gen1_2_3_4 = `0xF`。

块布局遵循 envytools rnndb 对 GK104 及以后的命名：**PPCI** 在 `0x88000`（配置影子加特权）、**PPCI_HDA** 在 `0x8A000`、**PPCI_2** 在 `0x8C000`（LTSSM 和速度块，含 `0x8C040` 的 `CONFIG_LINK` 和 `0x8C080` 的 `WIDTH`，后者在 A100 上读 `0x00001010`）。完整清单在[寄存器索引](../appendix/register-index.md)。

## 位宽上限

### 是缺件，不是熔丝、不是固件

170HX 的十六条 PCIe 数据通道中有十二条出厂时交流耦合电容被物理省略出 PCB。每个差分对有 2 颗电容，所以十二条通道意味着 **24 颗缺失部件**。NVIDIA 只贴装了它打算让卡使用的四条通道。通道 0 到 3 贴装；通道 4 到 15 不贴。

三条独立证据线排除每一种软件解释：

1. **没有通道熔丝被置位。** `0x00820394` 的 `OPT_PCIE_LANE_DISABLE`、`0x0082082C` 的 `CTRL_OPT_PCIE_LANE` 和 `0x00820C2C` 的 `STATUS_OPT_PCIE_LANE` 在队列中的每一张卡（包括两块 170HX 单元）上都读 `0x00000000`。x16 电气宽度在硅片中是完好的。
2. **没有代码碰位宽。** 对 Gen2 代码里每一个与 PCIe 相关的写入的一次穷举审计，发现只写 `LINK_CTRL_2 [3:0]`、`LINK_CONFIG_0 [19:18]`、`CYA_0` 位 2、`PRIV_MISC_1` 位 11-14、`PL_LINK_RATE`、`OPT_GEN23`、XP3G 槽 0 和 3、VSEC 设备和层级位，以及配置空间的 `LNKCTL2` TLS。`LINK_CAP` 被读但只测试它的低速度半字节；`LINK_CAP[9:4]` 的 Max Link Width 字段从不被读也不被写，而 `LNKSTA` 被 `PCI_EXP_LNKSTA_CLS` 和 `PCI_EXP_LNKSTA_DLLLA` 掩码，但从不用 `PCI_EXP_LNKSTA_NLW`。对已发布的 master 和全部十二个未发布分支 grep "capacitor"、"AC coupling"、"solder" 或任何位宽寄存器一无所获。
3. **一个已知完好的 x16 主机端口仍以 x4 训练。** 2026-07-26 在一台主机里的两张卡上实测：sysfs 报告两块 GPU 都是位宽 `cur 4 / max 16`，而第二块 GPU 的上游端口本身是 x16 能力的（`cur 4 / max 16`），链路仍以 x4 训练。转接卡和插槽分歧假设由 PCB 分析回答，不由软件中任何东西回答。

### 部件

| 属性 | 规范值 |
|---|---|
| 数量 | 24（每差分对 2 颗 × 12 条缺件通道） |
| 封装 | 0402 |
| 电容 | 220 nF（0.22 µF） |
| 介质 | **X7R**（常被误写 "XR7"） |
| 额定电压 | 6.3 V 或更高。已知能工作的 x16 改装用了 6.3 V 部件；PCIe 把发射机 DC 共模限制到 3.6 V，所以 6.3 V 带充足余量 |
| 参考设计编号 | C1100 到 C1350 范围，例如每对 C1120 / C1125 / C1130 / C1135 |
| 已确认厂商料号 | Taiyo Yuden `MAASJ105SB7224KFCA01`（220 nF，6.3 V，X7R，0402）。Samsung `CL05B224KO5NNNC`（16 V）是一个报告可用的替代品 |
| 见过的分销商编号 | DigiKey `1276-1176-1-ND` 和 Digi-Key `3886834`。两者都貌似同一厂商料号的不同包装；把它们当作未验证的别名，按厂商料号购买 |

这个值不是猜测：它读自 NVIDIA A100 GA100-883 参考原理图 **P1001-B02 第 3 页、"IO: PCIe CONNECTOR"**，170HX 板密切跟随它。一位测试者报告 100 nF 替代品能用。

### 实测结果

```text
之前：  LnkSta: Speed 2.5GT/s, Width x4 (downgraded)
之后：  LnkSta: Speed 2.5GT/s, Width x16
```

用 `sudo lspci -s <bdf> -vvv | grep LnkSta` 验证。速度字段不动，那是预期结果。

部分工作会协商降级而非失败。PCIe 位宽协商经过合法位宽 16、8、4、1 回退，所以 24 颗电容中正确贴装 12 到 23 颗的卡以 **x8** 训练。一位改装者三张卡的进展是 x4、然后 x8、然后 x16，随技术提高；另一张卡 "after smaller readjustments"（经过小调整后）走 x4、x8、x16。改装后出现 x8 结果意味着焊接点不完整或桥接，而非一个不同的硬件限制。回流并检查全部 24 个焊点。

> [!CAUTION]
> **这是在一块你无法更换的卡上做细间距返工**
>
> 密集的高速差分区域里的 0402 部件。一个桥接对不仅无法加宽链路，还会破坏一条之前能工作的通道上的信令。含铅焊锡被报告让这活 "extremely easy"（极其容易）；用针头加风枪涂锡膏让部件自对准。完整流程和照片在[物理改装](../operations/physical-mods.md)。

## 各配置的带宽

| 配置 | 实测 | 方法和条件 | 置信度 |
|---|---|---|---|
| Gen1 x4 | 0.85 GB/s 写，0.84 GB/s 读 | clpeak `enqueueWriteBuffer` / `enqueueReadBuffer`，2023 发布表 | 高 |
| Gen1 x4 | 0.80 GB/s 发送，0.84 GB/s 接收，0.81 双向 | 从一个外部硬件组转发的 OpenCL-Benchmark 截图，10 GB 到 40 GB 卡；工具把链路标为 "Gen1 x16" | 中等 |
| Gen1 x16（电容改装，无 Gen2） | 2.88 GB/s 平坦，无错误 | 改装卡；标称约 4 GB/s，缺口归因于 PCIe 1.1 信令开销 | 中等 |
| Gen2 x4 | 1.68 GB/s 发送，1.71 GB/s 接收 | OpenCL-Benchmark，一张归档截图，未改装卡；设置脚本独立预测 "约 0.85 到约 1.7 GB/s，恰好 2x" | 中等 |
| Gen1 x8 → Gen2 x8（一张卡上 A/B） | 1.67 GB/s 到 3.24 GB/s | OpenCL，在一张协商 x8 的电容改装卡上。这既是**位宽**结果也是速度结果；不要把它引用为 Gen2 x4 数值 | 中等 |
| Gen2 x16 | 6.63 到 6.67 GB/s（`ocl_pcie_bw`）；同一次运行的 nvtop 截图显示 `PCIe GEN 2@16x`、TX 7.061 GiB/s。另一台机器报告四张卡各 5.97 GB/s | 带解锁器安装的电容改装卡 | 中等 |

> [!WARNING]
> **Gen2 x16 依赖单一观测**
>
> Gen2 x16 只被观察到**一次**，2026-07-26，在一台机器上、一张截图里、一张 24 电容改装完成的卡上。没有把它桥接到更早调查（其中每个 Gen2 结果都是 x4）的 `lspci` 捕获，没有老化测试，没有随时间的 AER 计数器，也没有第二台机器。把 6.63-6.67 GB/s 数值当作中等置信度，把 Gen2 x16 **稳定性**当作未确立。

一个被描述为 Gen1 x16 的卡的 `0.71 GB/s` 双向数值在流传。对那个配置它太低（标称约 4 GB/s），且该卡实际的通道状态从未确立。不要把它引用为 Gen1 x16 测量。

关于这些数字在实践中意味着什么，参见[性能](../operations/performance.md) 和[LLM 推理](../operations/llm-inference.md)。简版：在 Gen1 x4 下链路对图形是约束（Unigine Superposition 封顶 5 fps、1080p 游戏 15-20 fps、单个 1080p60 远程游戏流就饱和链路），而对流水线并行 LLM 解码链路几乎无关紧要（一个 5120 隐藏维模型每 token 每跳移动 10,240 字节，所以饱和单条 PCIe 1.0 通道需要约每秒 25,000 token）。张量和专家并行即使在 Gen2 x16 下也被判断为不可行。

## 看起来像原因却不是的东西

| 嫌疑 | 为什么它貌似合理 | 为什么它不是原因 |
|---|---|---|
| `NV_PTOP_FS4` `0x0002241c` | 记录的位名字面上是 `GEN2_PCIE`（位 0）和 `GEN2_PCIE_SPEED`（位 7） | 在 8 GB（`0x20c2`）卡上读 `0x00000000`、10 GB（`0x2082`）卡上读 `0x00000081`。一张训练 Gen4 的 GA10x 对照卡读同样的 `0x00000081`，而 10 GB 170HX 在仍被 Gen1 封顶时读 `0x00000081`。如果这些位门控速度，两个观察不可能都成立。`0x00022470` 的 `PTOP_FS_STATUS` 读 `0x0000003f` |
| 板卡跳线 | U808 附近有可见的跳线电阻焊盘；Strap4（R999/R1000）映射为 `PCIE_CFG` | 把 A100 跳线配置复制到 170HX 上导致**启动时卡不被检测到**。尝试者的裁决："the straps don't do anything"（跳线什么都不做）、"falcon is driving the rewrites"（falcon 在驱动重写） |
| 设备 ID 欺骗 | 把卡呈现为 A100 并继承其设置 | `0x00820584` 的 `FUSE_DEVID_SW_OVR_DIS` 在每块被探测的 Ampere 部件上都读 `0x00000001`；ID 来自只读熔丝 `0x008204D8` 和 `0x0082056C`。写 XVE 配置影子 dword0 只改变主机可见的 ID，每个锁都保持原位 |
| 刷入真 A100 80GB VBIOS | 逐字节相同的 BIT 表，近乎相同的 PCB | 测试并失败；至少 Gen4 位不迁移 |
| 一个 PCIe redriver | 便宜且可得 | redriver 只重新放大，所以端点仍自己产生其熔丝封顶的 TX 速率。只有**重定时器**（终止链路并能向两侧宣告不同速率）能伪造 TS1/TS2 Rate-ID。从未尝试 |
| ASPM | 许多平台把链路空降到 Gen1 | 测试时是真实的假阴性陷阱，所以要在负载下跑测试，但 170HX 在自己 `LnkCap` 里宣告 `ASPM not supported`，所以在它被提出的那个案例里它不是原因 |

一个值得记录的奇事：在**两块**物理 10 GB 卡上，`0x008204D8` 的 `FUSE_PCIE_DEVIDA` 读 `0x00002082`，而 `0x0082056C` 的 `FUSE_PCIE_DEVIDB` 读 `0x000020c2`。一块 10 GB 卡把 8 GB 变体的设备 ID 作为次级熔丝携带。跨 13 张对比卡，熔丝 B 等于熔丝 A 带位 6 置位（`+0x40`），例如 A100 PCIe 80G `0x20b5`/`0x20f5`。也测到：**这些 10 GB 单元上 `0x00821060` 的 `OPT_SKU_ID` = `0x00000068`**（`0x00000080` 是 8 GB / `0x20C2` 的值）、`0x008203f4` 的 `OPT_INTERNAL_SKU` = 0。

## 平台与互连

| 拓扑 | 裁决 |
|---|---|
| 裸金属 PCIe 插槽 | 支持，且是参考配置 |
| Oculink | 工作。本质上是一条直接 PCIe 转接卡，有时带一个用于时序的 redriver |
| Thunderbolt 3 eGPU 坞 | **彻底破坏解锁**，不只是 PCIe。`nvidia-smi` 返回 "No devices were found"，dmesg 显示完整的 GSP 启动失败链（`Booter failed with non-zero error code: 0x15`、`failed to execute Booter Load: 0xffff`、`Max GSP-RM boot attempts exceeded: 4/4`、`RmInitAdapter failed! (0x62:0xffff:2119)`） |
| GPU 直通进 VM | Gen2 能力被宣告但训练不发生。2026-07-24 被维护者承认，未修复 |
| 无源 SlimSAS / MCIO，70 cm | 在 Gen4 x8 下不可靠（许多错误），Gen3 x8 下稳定。线缆标记 `HNW-SS-8654-AA75`。大多数转接板带一个 `ICS 9ZXL1950DKIL`，那是一个**时钟缓冲器，不是 redriver**；`NFHK N-W54B-P` 变体被识别为带真 redriver |
| PCIe 交换机扇出（例如 PEX88096） | 交换机不创造带宽，而因为 170HX **没有 P2P**，一个交换机后面的卡无法绕过上行链路。在观察窗口内没人把 170HX 卡部署在一个交换机后面 |
| 集群里的 InfiniBand 或高速织网 | 在 Gen1 或 Gen2 下零收益。一位多节点操作者连 10 GbE 都饱和不了 |

这块卡上 P2P 缺失，任何分支都不含任何 P2P 使能。参见[P2P](../frontier/p2p.md)。

## 诊断规则

1. **读 `LnkSta`，绝不读 `LnkCap`。** `LnkCap` 是宣告的能力，在链路仍在以 Gen1 训练时可以读 Gen2。那个陷阱是大多数经不起推敲的 "it works"（能工作）声称的来源。
2. **不要信 sysfs 的 `max_link_speed`。** 两台机器上三张卡它报告 `cur 5.0 GT/s / max 2.5 GT/s`，一个低于当前速度的最大值，而配置空间 `LnkCap` 正确读 `0x00456102`。预期这种不匹配；它不是故障。
3. **不要把 `nvidia-smi` 的 `PCIe Generation Max` 当作任何东西的证据。** 一张出厂卡自 2023 年起就一直报告 `Max: 2` 配 `Device Current: 1` 和 `Device Max: 1`，而 `LnkCap2` 只列出 2.5 GT/s。它只作为指纹有用。
4. 三个诚实的字段是 `lspci -vvs <bdf> | grep LnkSta`、`/sys/bus/pci/devices/<bdf>/current_link_speed` 和 `nvidia-smi --query-gpu=pcie.link.gen.gpucurrent`。

社区的准链路报告是一个已发布的 `pcielink.sh` 诊断，它捕获内核、驱动、SEC2_DEBUG 行数、BDF、板卡和 GPU 料号、VBIOS、**GPU 和**主机桥两者的完整 LnkCap/LnkCap2/LnkCtl2/LnkSta/LnkSta2/DevCap2/DevCtl2/LnkCtl 集、sysfs 速度和位宽、`nvidia-smi` 数值和 AER 计数器。确认卡上观察到的身份：VBIOS `92.00.6D.00.0A` 和 `92.00.67.00.01`、BoardPN `900-11001-0108-000`、GPUPN `20C2-105-A1`、子系统 `0x158510DE`。

## 未解问题

> [!NOTE]
> **未解问题：Gen3 和 Gen4**
>
> `FUSE_PCIE_GEN23_DIS` 和 `FUSE_PCIE_GEN3_DIS` 都读 `0x00000001`，而且即使在 PHY 速率被强制到一个 Gen3 能力的 `0x00340036` 之后，受支持速度向量也裁剪在 `0x00000006`。"向量是连续的所以 Gen2/3/4 是一个问题" 这个论证是简单失败在这颗硅片上，还是 Gen3 熔丝在下游被独立强制，未解决。最便宜的未尝试实验：通过那个已经*尝试* `0x0082057c` 的同一个 `xp3g` 表写 `0x00820580 = 0`，注意那次写入失败，所以预期 `booter FAILED to set` 和 `rd=0x00000001`。然后请求 TLS = 3。便宜，但先验低。参见[Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)。

> [!NOTE]
> **未解问题：`FUSE_PCIE_MAGIC_D` 可写吗？**
>
> 一份分析把 `0x00820520` 标注为 "(writable)"；一条净室链把 `0x00200000` 写给它；实地手册把它列为只读；而分支补丁只读它。因为 Gen4 在没有 Gen4 主机时不可测试，这从未被操练过。读、写 `0x00200000`、回读，发布两个值。五分钟的活，没人做过。

> [!NOTE]
> **未解问题：x16 稳定吗？**
>
> 2026-07-26 的一次捕获是 Gen2 x16 的整个证据基础。没有老化测试、没有随时间的 AER 计数器、没有第二台机器。

> [!NOTE]
> **未解问题：Gen2 卡上的 Resizable BAR**
>
> 能力结构存在且已被捕获（`Capabilities: [bb0 v1] Physical Resizable BAR`，BAR0 16 MB、BAR1 64 MB、BAR3 32 MB，各一个受支持大小）。开放的是 ReBAR 能否被做成*可用*：即使卡报告 81920 MiB，BAR1 也钉在 64 MiB，而且没人在一张 Gen2 训练的卡上重测过它。

## 相关页面

- [Gen2 软件解锁](../unlock/pcie-gen2.md)，寄存器机制和分支代码
- [物理改装](../operations/physical-mods.md)，电容返工流程
- [熔丝与 OTP](fuses-and-otp.md)，完整熔丝图
- [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)，未解决的一半
- [寄存器索引](../appendix/register-index.md)
- [术语表](../start/glossary.md)
