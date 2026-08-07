# PCIe 子系统

**本页内容：** CMP 170HX 出厂时 PCIe 接口的硬件与固件状态；显卡出厂时自带的两项限制；速度上限背后的熔丝和 DevInit 证据；位宽上限背后的缺失交流耦合电容；出厂卡准确的寄存器与 `lspci` 状态；以及那些容易被误认为是上述任一限制原因的平台级干扰因素。速度上限的软件破解方案见[Gen2 解锁](../unlock/pcie-gen2.md)；破解位宽上限所需的焊接工作见[物理改装](../operations/physical-mods.md)。

## 核心结论：两个上限、两种机制、两种修复方式

一张出厂状态的 CMP 170HX 会以 **PCIe Gen1（2.5 GT/s）x4** 完成链路训练。这是两个完全独立的限制，只是恰好同时存在于同一块板卡上；破解其中一个，对另一个完全没有作用。

| | 速度上限 | 位宽上限 |
|---|---|---|
| 观察到的状态 | 2.5 GT/s（Gen1） | 训练为 x4，但宣告为 x16 |
| 机制 | OTP 熔丝加签名 DevInit 表，由固件强制执行 | 16 条通道中有 12 条出厂时缺少交流耦合电容 |
| 所在位置 | 晶片和 SPI 闪存 | PCB |
| 破解方式 | 未发布分支中的驱动补丁（仅支持 Gen2） | 手工焊接 24 颗 0402 电容 |
| 状态 | 2026-07-24 已通过软件达到 Gen2，**尚未发布**；尚未达到 Gen3 和 Gen4 | 自 2026 年 4 月起已由多名独立改装者复现 |
| 会改变另一个限制吗？ | 不会。安装 Gen2 补丁但未改装电容的卡仍是 Gen2 x4 | 不会。完成电容改装但未安装补丁的卡仍是 Gen1 x16 |

证明这两个限制彼此独立的最清晰单条证据是：一张出厂且从未焊接过的 8 GB 卡运行 Gen2 代码时，报告 `LnkCap: Port #0, Speed 5GT/s, Width x16`，而 `LnkSta` 读取为 `Speed 5GT/s, Width x4 (downgraded)`。能力寄存器宣告 x16，实际训练出的链路却是 x4。12 条通道没有电气路径，因此软件无法弥合这段差距。

> [!WARNING]
> **实验性**
>
> 本页涉及 Gen2 的全部内容都针对尚未发布的分支代码。当前发布版 `master` 不包含任何 PCIe 补丁。参见[Gen2 解锁](../unlock/pcie-gen2.md)。

## 出厂链路状态

### `lspci` 的输出

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

这里有两个细节值得记住。`LnkCap` 宣告 **Width x16**，说明显卡知道自己有 16 条通道；`LnkSta` 中的 `(downgraded)` 标记表示链路在协商时降级，这正是接收端在通道 4 到 15 上收不到信号时会出现的结果。此外，`LnkCap2` 只列出 2.5 GT/s 为受支持速度。按照 PCIe 规范，这会钳制写入 `LnkCtl2` 的目标链路速度：在出厂卡上向其中写入 `0x2`，读回仍是 `0x1`。

内核每次启动时也会用自己的方式说明同一件事：

```text
pci 0000:0a:00.0: 8.000 Gb/s available PCIe bandwidth, limited by 2.5 GT/s PCIe x4 link at
  0000:09:01.0 (capable of 32.000 Gb/s with 2.5 GT/s PCIe x16 link)
```

注意内核比较的是 **2.5 GT/s x16** 下的 32 Gb/s。它抱怨的是位宽，而不是速度。

### 原始寄存器值

下面所有地址都是 XVE 配置空间的 BAR0 镜像。PCIe Express 能力位于配置空间偏移量 `0x78`（不是 `0x60`），XVE 影子基址为 `0x88000`，因此配置空间的 `cap+0x0C` 会映射到 BAR0 `0x00088084`，其他字段以此类推。

| 字段 | 配置空间偏移量 | BAR0 镜像 | 出厂状态，无解锁 | 安装解锁器后 |
|---|---|---|---|---|
| LnkCap | `CAP_EXP+0x0C` | `0x00088084` | `0x00456101` | `0x00456102` |
| LnkCtl / LnkSta | `CAP_EXP+0x10` | `0x00088088` | LnkCtl `0x0140`，LnkSta `0x1041` | LnkCtl `0x0140`，LnkSta `0x1042` |
| LnkCap2 | `CAP_EXP+0x2C` | `0x000880a4` | `0x00000002` | `0x00000006` |
| LnkCtl2 / LnkSta2 | `CAP_EXP+0x30` | `0x000880a8` | `0x0000` / `0x0000` | `0x0002` / `0x0001` 或 `0x0000` |
| DevCap2 | | | `0x00070803` | `0x00070813` |
| DevCtl2 | | | `0x1400` | `0x0400`（一台测试机为 `0x7410`） |

在未安装解锁器的卡上，`nvidia-smi` 报告的 `pcie.link.gen.current, pcie.link.gen.max, pcie.link.width.current` 为 **1, 1, 4**；安装解锁器后为 **2, 2, 4**。两种情况下位宽都不会变化。

> [!NOTE]
> **不要重复某个已发布资料中的错误地址**
>
> 一份广泛流传的实地手册把 LnkCap2 的 BAR0 镜像列为 `0x8808C`。这个地址在逻辑上自相矛盾：XVE 镜像基址是 `0x88000` 时，配置空间 `0xA4` 应映射到 `0x880A4`，而 `0x8808C` 实际映射的是配置空间 `0x8C`。分支补丁（`#define PCIE_GEN2_LINK_CAP2_ADDR 0x000880a4U`）和社区的 `pcielink.sh` 诊断工具都使用 `0x880A4`。请使用 `0x880A4`。

### 其他出厂配置空间事实

| 项目 | 值 |
|---|---|
| 插槽功耗上限（DevCap） | 75 W |
| MaxPayload / MaxReadReq | 256 字节 / 512 字节 |
| ASPM | 不支持（在 LnkCap 中宣告） |
| FLReset | 支持 |
| BAR0 | 32 位不可预取区域中的 16 MB，孔径为 `0x1000000` |
| BAR1 | 64 MB，64 位可预取 |
| BAR3 | 32 MB，64 位可预取 |
| Resizable BAR 能力 | 存在于 `[bb0 v1]`，但每个 BAR 恰好只宣告一个受支持大小 |

无论显卡报告的帧缓冲容量是多少，BAR1 都固定为 64 MiB。因此，即使显卡报告有 81920 MiB，也无法将完整显存映射到主机。Resizable BAR 虽然被宣告支持，但实际上不起作用。过去有人认为 ReBAR“需要 PCIe 3.0”，这个说法是错误的：ReBAR 是一种配置空间能力，自 2007 年起就已存在于规范中，并且与链路代数无关。不过，也没有人在一张以 Gen2 训练的 170HX 上演示过可用的 ReBAR。

## 速度上限

### 熔丝证据

三个 OTP 熔丝影子共同构成了这个锁的指纹。170HX 读取为 **1 / 1 / `0x16680000`**，而所有用于对比的 Ampere 部件读取的前两项都是 0，第三项也都没有置位 bit 25。

| 寄存器 | 地址 | 170HX（两个 SKU） | A100（全部三个 SKU）和 Drive A100 | 备注 |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | `0x0082057c` | `0x00000001` | `0x00000000` | A10、A5000、A6000、RTX 3080 / 3080 Ti / 3090 / 3090 Ti 以及一张 GA10x 对照卡上也都是 0 |
| `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | `0x00820580` | `0x00000001` | `0x00000000` | 同一批对照部件 |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000`（bit 25 置位） | `0x00200000` | bit 25 被记录为 `GEN4_SPEED_DISABLED`，引用 NVIDIA bug 2220334。A10/A5000/A6000 读取 `0x01a00000`；RTX 30 系列读取 `0x10a80000` |

两个 170HX 的数值都在两块实物上测得，每块卡读取两次，并横跨 15 张卡的对比样本。`0x20c2` 的读数来自驱动侧转储，其中打印了 `OPT=00000001/00000001/16680000`；`0x2082` 的读数来自独立探测工具生成的 `registers.json`。

另外两个相关熔丝堵死了显而易见的变通路线。`0x820040` 的 `FUSE_EN_SW_OVERRIDE` 读取为 0，`0x820084` 的 `FUSE_DIS_SW_OVR` 读取为 1，因此芯片内部禁用了软件覆盖路径。`0x820148` 是一个读取为 0、且软件永远无法置位的 OTP 备用位；只有在 `0x820148 & 1` 时，DevInit 才会把 A100 的值 `0x00200000` 写入 `MAGIC_D`，这正是 DevInit 从不在 CMP 上写入它的原因。

`0x0082057c` 的 `OPT_GEN23` 已经从所有可用权限级别尝试写入：普通主机写入、HS 权限驱动写入，以及 SEC2 Booter 载荷写入。每次尝试都失败，回读结果仍为 `0x00000001`。它只是熔丝感测值的只读映射，没有写入端口。详见[熔丝与 OTP](fuses-and-otp.md)和[失败路线](../history/dead-ends.md)。

> [!NOTE]
> **熔丝不是突破口**
>
> Gen2 解锁在 `OPT_GEN23` 仍然读取为 `0x00000001` 时就能工作。已发布的分支补丁仍会尝试写入它，写入仍然失败，但 Gen2 仍然能够训练成功。真正有效的突破口是 CYA_0、LINK_CONFIG_0、XP3G 和 PRIV_MISC_1 覆盖，而不是熔丝影子。

### DevInit 层

熔丝只是三层限制中的一层。第二层是 SPI 闪存中**未加密**的 DevInit Falcon 映像内的一张 PCIe 配置表；它与传统的 x86 VBIOS 分开存在。

| 项目 | CMP 170HX | A100 |
|---|---|---|
| PCIe 配置表，闪存偏移量 | `0x420ED`（镜像 `0xA20ED`） | `0x408A0`（镜像 `0xA08A0`） |
| 运行时 DMEM 基址 | `0xF1D` | `0xE50` |
| 表偏移量 `+0xC7` 到 `+0xCB` 的五个字节 | 闪存 `0x421B4`-`0x421B8` 处为 `00 00 08 00 06` | 闪存 `0x40967`-`0x4096B` 处为 `00 00 14 00 06` |
| 表偏移量 `+0x0F` 的抑制标志 | `0x01` | `0x00` |
| DevInit 映像位置 | 闪存 `0xDE00`（反汇编基址 `0x8000`），并在 bank 2 的 `+0x60000` 处复制 | |

抑制标志是决定性的：在 CMP 上，`ld b8 r9, D[tab+0x0F]; bra ne` 会跳过整个 Gen4 编程代码块（反汇编位置 `0x31B3F`-`0x31B92`）。当该代码块运行时，它会计算 `0x88CE4 = (old & ((b1<<8)|b0)) | ((b3<<8)|b2)`。由于 `b0 = b1 = b3 = 0`，结果归结为字节 `[+0xC9]`；同时，它会计算 `0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)`，两块部件的 `b4` 都是 `0x06`。更广泛的符号分析发现，DevInit 总共有 **13 个**字节不同，其中 11 个可以归因于非 PCIe 的 SKU 功能（HBM、NVLink、ECC）；与 PCIe 相关的是 `[0xC9]`（输入 `0x88CE4`）、`[0x1C-0x1F]`（输入 `0x8C2C0`）和 `[0x3F]`（输入 `0x8C040`）。CMP 和 A100 的 BIT 表逐字节相同。

修改这些字节是一条走不通的路线。这 5 个字节 **100% 位于** Davies-Meyer `csecret(2)` MAC 范围 `0x2200`-`0x43C00` 内，因此无密钥伪造需要进行一次复杂度为 2^128 的第二原像攻击；而重刷修改后的映像会直接被 Ampere RSA 签名检查拒绝。参见[VBIOS](vbios.md)。

> [!CAUTION]
> **不要尝试刷写修改后的映像**
>
> 修改过的 DevInit 或 VBIOS 映像会被签名检查拒绝，显卡也将无法启动。恢复需要外部编程器。接触闪存之前，请先阅读[恢复](../procedures/recovery.md)。

第三层是运行时限制：DevInit 本身从不读取 `0x82057C` 或 `0x820580`。对 CMP DevInit 反汇编进行穷举搜索，只找到 `0x820C14`/`0x820D38`（FBIO/FBP 熔丝裁剪）、`0x820684`（`FUSE_NVLINK_DIS`）、`0x82380C`/`0x823814`、`0x820520`、`0x820148`、`0x8243xx`、`0x8202xx`、`0x8201xx`、`0x82033C`/`0x82030C`。真正使用这些信息的是 GSP-RM：`470.42.01 gsp.bin` 中 `0x5D55834` 处的熔丝读取跳转表使用 `li a2, 0x580` 和 `li a2, 0x57c`；`580.105.08 gsp_tu10x.bin` 则在 `0x4DD9B00` 处使用 `li a2, 0x57c` 调用 `jalr fuse_read`。这就是为什么当前认为 Gen3 路线需要 GSP 补丁。

### 启动顺序

FWSEC-DevInit 会在 SEC2 Booter 运行前编程并**锁存** `SUPPORTED_LINK_SPEED`，而解锁所需的时序漏洞 gadget 正位于 SEC2 Booter 中。因此，在任何漏洞窗口打开之前，锁存的能力就已经确定。显存和算力解锁之所以能够实现，是因为 `FEAT_OVR`（`0x82381C` / `0x823804`）和 FBPA（`0x9A0204`）都是位于 16 MB BAR0 内的普通寄存器；打开相应的 PLM 后就可以写入。已经锁存的 PHY 能力则不同。Gen2 解锁实际做的是让 PHY 反射值重新生成 Gen2 能力，然后在其他逻辑再次钳制它之前训练链路。

### 速度能力所在位置：逐寄存器说明

| 寄存器 | 地址 | 访问方式 | 备注 |
|---|---|---|---|
| 受支持速度源 | `0x00085080` | 只读，字段 `[23:20]` | 从主机读取 `0xBADF1100`（毒值）；在 410 万行 RM 反汇编中没有找到写入者 |
| 允许的代际掩码 | `0x00085084` | 每次重新训练时由 GSP-RM 重新推导 | 同样读取为毒值 |
| `MAX_LINK_SPEED` | `0x00088084` `[3:0]` | PHY 反射，标记为 `R-XVF` | 没有写入端口 |
| `SUPPORTED_LINK_SPEED` | `0x0008808C` `[7:1]` | PHY 反射，标记为 `R-EVF` | 任何权限级别下都没有写入端口 |
| `TARGET_LINK_SPEED` | `0x000880A8` `[3:0]` | 可读写，但受 SUPPORTED 钳制 | |
| `LINK_CONTROL_STATUS` | `0x00088088` | `[19:16]` 为当前协商出的速度 | |
| `PRIV_MISC_1` | `0x0008841C` | PLM 下可读写 | CYA Gen2/3 覆盖位为 11-16、30、31 |
| `VSEC_HIERARCHY` | `0x00088610` | PLM 下可读写 | bit 12 控制 PRIV_MISC_1 的重新编程；当前值为 `0x00001001` |
| LTSSM 重新训练触发器 | `0x0008872C` | PLM 下可读写 | 写入 `6` |
| `PPCI_2.CONFIG_LINK`（`LINK_CONFIG_0`） | `0x0008C040` | PLM 下可读写 | `[3:0]` 为 LTSSM_DIRECTIVE，`[4]` 为 LTSSM_STATUS，`[19:18]` 为 SPEED（0 = 最大速度，2 = 5.0 GT/s，3 = 2.5 GT/s）。CMP 读取 `0x800C4C00`（SPEED = 3）；A100 读取 `0x80004C00`（SPEED = 0） |
| `CYA_0` | `0x0008C2C0` | PLM 下可读写 | bit 2 是 `DIS_G2` chicken 位。CMP 为 `0x068731B7`，A100 为 `0x060711B2` |
| `PL_LINK_RATE` | `0x0008C1C0` | | A100 读取 `0x00040036` |
| `PPCI.UNK1C0` | `0x000881C0` | 主机读取返回 `0xbadf5040` | rnndb：`[17:16]` 为 LNK_CAP_SPEED，`[21:20]` 为 SYSTEM_MAX_SPEED |

全文使用的速度向量编码如下：Gen1 = `0x1`，Gen1_2 = `0x3`，Gen1_2_3 = `0x7`，Gen1_2_3_4 = `0xF`。

寄存器块布局遵循 envytools rnndb 对 GK104 及后续架构的命名：**PPCI** 位于 `0x88000`（配置空间影子加特权寄存器），**PPCI_HDA** 位于 `0x8A000`，**PPCI_2** 位于 `0x8C000`（LTSSM 与速度寄存器块，其中 `CONFIG_LINK` 位于 `0x8C040`，`WIDTH` 位于 `0x8C080`；后者在 A100 上读取为 `0x00001010`）。完整列表见[寄存器索引](../appendix/register-index.md)。

## 位宽上限

### 是缺少硬件，而不是熔丝或固件

170HX 的 16 条 PCIe 数据通道中，有 12 条出厂时就从 PCB 上物理省略了交流耦合电容。每个差分对需要 2 颗电容，因此 12 条通道意味着 **24 颗缺失部件**。NVIDIA 只贴装了它打算让这张卡使用的 4 条通道。通道 0 到 3 已贴装，通道 4 到 15 没有贴装。

以下三条相互独立的证据排除了所有软件层面的解释：

1. **没有通道熔丝被置位。** 队列中每张卡（包括两块 170HX）上的 `0x00820394` `OPT_PCIE_LANE_DISABLE`、`0x0082082C` `CTRL_OPT_PCIE_LANE` 和 `0x00820C2C` `STATUS_OPT_PCIE_LANE` 都读取为 `0x00000000`。这说明晶片内部的 x16 电气宽度是完整的。
2. **没有代码会修改位宽。** 对 Gen2 代码中每一处与 PCIe 相关的写入进行穷举审计后发现，代码只写入 `LINK_CTRL_2 [3:0]`、`LINK_CONFIG_0 [19:18]`、`CYA_0` bit 2、`PRIV_MISC_1` bits 11-14、`PL_LINK_RATE`、`OPT_GEN23`、XP3G 槽位 0 和 3、VSEC 设备与层级位，以及配置空间中的 `LNKCTL2` TLS。代码会读取 `LINK_CAP`，但只测试其中的低速率半字节；从不读取或写入 `LINK_CAP[9:4]` 的 Max Link Width 字段；`LNKSTA` 会与 `PCI_EXP_LNKSTA_CLS` 和 `PCI_EXP_LNKSTA_DLLLA` 做掩码，但从不使用 `PCI_EXP_LNKSTA_NLW`。对发布版 `master` 以及全部 12 个未发布分支搜索“capacitor”“AC coupling”“solder”或任何通道位宽寄存器，都没有找到结果。
3. **一个已知完好的 x16 主机端口仍然会训练为 x4。** 2026-07-26 在同一台主机中的两张卡上进行测量：sysfs 报告两块 GPU 的位宽都是 `cur 4 / max 16`；第二块 GPU 的上游端口本身也支持 x16（`cur 4 / max 16`），但链路仍然训练为 x4。转接卡和插槽分拆假设，应由 PCB 分析来回答，而不是由软件中的任何现象来解释。

### 电容部件

| 属性 | 标准值 |
|---|---|
| 数量 | 24（每个差分对 2 颗 × 12 条缺件通道） |
| 封装 | 0402 |
| 电容值 | 220 nF（0.22 µF） |
| 介质 | **X7R**（经常被误写成“XR7”） |
| 额定电压 | 6.3 V 或更高。已知成功的 x16 改装使用了 6.3 V 部件；PCIe 将发射器直流共模电压限制在 3.6 V，因此 6.3 V 具有充足余量 |
| 参考设计编号 | C1100 至 C1350 范围，例如每个差分对使用 C1120 / C1125 / C1130 / C1135 |
| 已确认的厂商料号 | Taiyo Yuden `MAASJ105SB7224KFCA01`（220 nF，6.3 V，X7R，0402）。据报告可用的替代品是 Samsung `CL05B224KO5NNNC`（16 V） |
| 见过的分销商编号 | DigiKey `1276-1176-1-ND` 和 Digi-Key `3886834`。两者很可能是同一厂商料号的不同包装；应将它们视为未经验证的别名，按厂商料号购买 |

这个电容值并非猜测，而是从 NVIDIA A100 GA100-883 参考原理图 **P1001-B02 第 3 页“IO: PCIe CONNECTOR”**中读出的；170HX 的 PCB 与该设计高度相似。有测试者报告称，使用 100 nF 替代品也能正常工作。

### 实测结果

```text
之前：  LnkSta: Speed 2.5GT/s, Width x4 (downgraded)
之后：  LnkSta: Speed 2.5GT/s, Width x16
```

使用 `sudo lspci -s <bdf> -vvv | grep LnkSta` 验证。速度字段不会变化，这是预期结果。

部分改装不会导致链路训练失败，而是会协商为较低位宽。PCIe 位宽协商会依次回退到合法的 16、8、4、1，因此 24 颗电容中正确贴装 12 至 23 颗的卡会以 **x8** 训练。一名改装者在三张卡上的进展是 x4、然后 x8、最后 x16，随着焊接技术提高而改善；另一张卡在“after smaller readjustments”（经过一些小调整后）也经历了 x4、x8、x16。改装后得到 x8，说明焊点不完整或发生桥接，而不是存在另一种硬件限制。请重新回流焊接，并检查全部 24 个焊点。

> [!CAUTION]
> **这是在一块无法替换的显卡上进行细间距返工**
>
> 这些 0402 部件位于密集的高速差分区域。桥接一对焊点不仅无法拓宽链路，还可能破坏原本正常工作的通道上的信号。有人报告称，含铅焊锡让这项工作“extremely easy”（极其容易）；用针头涂抹焊膏，再配合热风枪，可以让部件自动对齐。完整流程和照片见[物理改装](../operations/physical-mods.md)。

## 各配置下的带宽

| 配置 | 实测值 | 方法和条件 | 置信度 |
|---|---|---|---|
| Gen1 x4 | 写入 0.85 GB/s，读取 0.84 GB/s | `clpeak` 的 `enqueueWriteBuffer` / `enqueueReadBuffer`，2023 年发布的表格 | 高 |
| Gen1 x4 | 发送 0.80 GB/s，接收 0.84 GB/s，双向 0.81 GB/s | 外部硬件群组转发的一张 OpenCL-Benchmark 截图，10 GB 至 40 GB 卡；工具把链路标记为“Gen1 x16” | 中 |
| Gen1 x16（电容改装，无 Gen2） | 2.88 GB/s，结果平稳且无错误 | 改装卡；理论值约 4 GB/s，差距归因于 PCIe 1.1 信令开销 | 中 |
| Gen2 x4 | 发送 1.68 GB/s，接收 1.71 GB/s | OpenCL-Benchmark 的一张归档截图，未改装卡；设置脚本独立预测“约 0.85 到约 1.7 GB/s，恰好是 2 倍” | 中 |
| Gen1 x8 → Gen2 x8（同一张卡上的 A/B 测试） | 1.67 GB/s 至 3.24 GB/s | 在一张协商为 x8 的电容改装卡上运行 OpenCL。这既是**位宽**结果，也是速度结果；不要把它作为 Gen2 x4 数值引用 | 中 |
| Gen2 x16 | 6.63 至 6.67 GB/s（`ocl_pcie_bw`）；同一次运行的 nvtop 截图显示 `PCIe GEN 2@16x`，TX 为 7.061 GiB/s。另一台测试机报告 4 张卡各为 5.97 GB/s | 安装解锁器的电容改装卡 | 中 |

> [!WARNING]
> **Gen2 x16 只有一次观测结果**
>
> Gen2 x16 只在 **2026-07-26** 被观察到过一次：一台测试机、一张截图、一张完成 24 颗电容改装的卡。没有 `lspci` 捕获可以将它与更早的调查结果连接起来；在更早的调查中，所有 Gen2 结果都是 x4。也没有老化测试、随时间记录的 AER 计数器，或第二台测试机。请将 6.63-6.67 GB/s 视为中等置信度，并将 Gen2 x16 的**稳定性**视为尚未确立。

有一张被描述为 Gen1 x16 的卡流传出 `0.71 GB/s` 双向带宽。这个数值对于该配置来说过低（理论值约 4 GB/s），而且从未确认该卡的实际通道状态。不要把它作为 Gen1 x16 的测量结果引用。

要了解这些数字在实际使用中的含义，请参见[性能](../operations/performance.md)和[LLM 推理](../operations/llm-inference.md)。简而言之：在 Gen1 x4 下，链路是图形工作负载的瓶颈（Unigine Superposition 被限制在 5 fps，1080p 游戏为 15-20 fps，单路 1080p60 远程游戏串流就能占满链路）；但对于流水线并行的 LLM 解码，链路几乎无关紧要（一个隐藏维度为 5120 的模型每个 token 每跳传输 10,240 字节，因此要占满一条 PCIe 1.0 通道，需要每秒约 25,000 个 token）。即使在 Gen2 x16 下，张量并行和专家并行仍被认为无法实际运行。

## 看似原因、实际并非原因的因素

| 疑点 | 为什么看起来合理 | 为什么不是原因 |
|---|---|---|
| `NV_PTOP_FS4` `0x0002241c` | 文档中的位名称确实是 `GEN2_PCIE`（bit 0）和 `GEN2_PCIE_SPEED`（bit 7） | 8 GB（`0x20c2`）卡读取 `0x00000000`，10 GB（`0x2082`）卡读取 `0x00000081`。一张能够训练 Gen4 的 GA10x 对照卡也读取同样的 `0x00000081`；而 10 GB 170HX 仍然被限制在 Gen1 时也读取 `0x00000081`。如果这些位控制速度，这两种观察结果不可能同时成立。`0x00022470` 的 `PTOP_FS_STATUS` 读取为 `0x0000003f` |
| 板卡跳线 | U808 附近有可见的跳线电阻焊盘；Strap4（R999/R1000）映射为 `PCIE_CFG` | 将 A100 的跳线配置复制到 170HX 后，结果是**显卡在启动时无法被检测到**。尝试者的结论是：“the straps don't do anything”（跳线不起作用）和“falcon is driving the rewrites”（falcon 在驱动重写） |
| 设备 ID 欺骗 | 让显卡呈现为 A100，并继承 A100 的设置 | 每块被探测的 Ampere 部件上，`0x00820584` 的 `FUSE_DEVID_SW_OVR_DIS` 都读取为 `0x00000001`；设备 ID 来自只读熔丝 `0x008204D8` 和 `0x0082056C`。写入 XVE 配置空间影子的 dword0 只会改变主机可见的 ID，所有限制仍然存在 |
| 刷入真正的 A100 80GB VBIOS | BIT 表逐字节相同，PCB 也非常相似 | 已经测试过但失败了；至少 Gen4 位不会随之迁移 |
| 使用 PCIe redriver | 价格低且容易获得 | redriver 只能重新放大信号，因此端点仍会以自身被熔丝限制的 TX 速率发送。只有**重定时器**能够终止链路并向两侧宣告不同速率，因而可能伪造 TS1/TS2 Rate-ID。尚未进行尝试 |
| ASPM | 许多平台会将空闲链路降到 Gen1 | 这确实是测试时容易造成假阴性的因素，因此应在负载下进行测试；但 170HX 自己的 `LnkCap` 已宣告 `ASPM not supported`，所以在提出该假设的案例中，它不是原因 |

还有一个值得记录的奇怪现象：在**两块**实物 10 GB 卡上，`0x008204D8` 的 `FUSE_PCIE_DEVIDA` 都读取为 `0x00002082`，而 `0x0082056C` 的 `FUSE_PCIE_DEVIDB` 都读取为 `0x000020c2`。也就是说，一块 10 GB 卡会在第二个熔丝中携带 8 GB 变体的设备 ID。在 13 张对比卡上，熔丝 B 都等于熔丝 A 置位 bit 6 后的值（`+0x40`），例如 A100 PCIe 80G 的 `0x20b5`/`0x20f5`。此外还测得：这些 10 GB 部件的 **`OPT_SKU_ID`（`0x00821060`）= `0x00000068`**（8 GB / `0x20C2` 的值是 `0x00000080`），而 `0x008203f4` 的 `OPT_INTERNAL_SKU` = 0。

## 平台与互连

| 拓扑 | 结论 |
|---|---|
| 裸机 PCIe 插槽 | 支持，也是参考配置 |
| Oculink | 可以工作。本质上是直接 PCIe 转接卡，有时会带一个用于时序的 redriver |
| Thunderbolt 3 eGPU 外置盒 | **会彻底破坏解锁**，不只是破坏 PCIe。`nvidia-smi` 返回“No devices were found”，dmesg 显示完整的 GSP 启动失败链（`Booter failed with non-zero error code: 0x15`、`failed to execute Booter Load: 0xffff`、`Max GSP-RM boot attempts exceeded: 4/4`、`RmInitAdapter failed! (0x62:0xffff:2119)`） |
| 将 GPU 直通到虚拟机 | 会宣告 Gen2 能力，但不会进行 Gen2 训练。维护者已于 2026-07-24 承认这一问题，尚未修复 |
| 无源 SlimSAS / MCIO，70 cm | Gen4 x8 下不可靠（错误很多），Gen3 x8 下稳定。线缆标记为 `HNW-SS-8654-AA75`。大多数转接板带有 `ICS 9ZXL1950DKIL`，它是**时钟缓冲器而不是 redriver**；已确认 `NFHK N-W54B-P` 变体带有真正的 redriver |
| PCIe 交换机扇出（例如 PEX88096） | 交换机不会创造额外带宽，而且由于 170HX **不支持 P2P**，交换机后面的卡无法绕过上行链路。在观察期间，没有人将 170HX 卡部署在交换机后面 |
| 集群中的 InfiniBand 或高速互连网络 | 在 Gen1 或 Gen2 下都没有收益。一名多节点操作者甚至无法占满 10 GbE |

这张卡不支持 P2P，任何分支都没有包含 P2P 使能代码。参见[P2P](../frontier/p2p.md)。

## 诊断规则

1. **读取 `LnkSta`，不要读取 `LnkCap`。** `LnkCap` 是宣告的能力，即使链路仍然以 Gen1 训练，它也可能读取为 Gen2。这个陷阱正是大多数经不起复核的“it works”（能工作）说法的来源。
2. **不要相信 sysfs 的 `max_link_speed`。** 在两台测试机上的 3 张卡中，它报告过 `cur 5.0 GT/s / max 2.5 GT/s`，即最大速度低于当前速度；与此同时，配置空间的 `LnkCap` 正确读取为 `0x00456102`。应预期这种不匹配，它不是故障。
3. **不要把 `nvidia-smi` 的 `PCIe Generation Max` 当作任何结论的证据。** 一张出厂卡从 2023 年起就一直报告 `Max: 2`，同时 `Device Current: 1`、`Device Max: 1`，而 `LnkCap2` 只列出 2.5 GT/s。它只能作为指纹使用。
4. 三个可信字段是 `lspci -vvs <bdf> | grep LnkSta`、`/sys/bus/pci/devices/<bdf>/current_link_speed` 和 `nvidia-smi --query-gpu=pcie.link.gen.gpucurrent`。

社区标准的链路报告工具是已发布的 `pcielink.sh` 诊断脚本。它会采集内核、驱动、SEC2_DEBUG 行数、BDF、板卡和 GPU 料号、VBIOS，以及 **GPU 和主机桥**双方完整的 LnkCap/LnkCap2/LnkCtl2/LnkSta/LnkSta2/DevCap2/DevCtl2/LnkCtl 集合；还会采集 sysfs 速度和位宽、`nvidia-smi` 数值以及 AER 计数器。已确认卡上观察到的身份包括：VBIOS `92.00.6D.00.0A` 和 `92.00.67.00.01`、BoardPN `900-11001-0108-000`、GPUPN `20C2-105-A1`、子系统 `0x158510DE`。

## 未解问题

> [!NOTE]
> **未解问题：Gen3 和 Gen4**
>
> `FUSE_PCIE_GEN23_DIS` 和 `FUSE_PCIE_GEN3_DIS` 都读取为 `0x00000001`；即使将 PHY 速率强制到具备 Gen3 能力的 `0x00340036`，受支持速度向量仍然会被裁剪为 `0x00000006`。目前尚未确定“速度向量是连续的，因此 Gen2/3/4 属于同一个问题”这一论证究竟是在这颗晶片上失效了，还是 Gen3 熔丝在下游被独立强制执行。
> 最便宜的未尝试实验，是通过同一个已经*尝试*写入 `0x0082057c` 的 `xp3g` 表，写入 `0x00820580 = 0`。需要注意的是，这次写入会失败，因此预期会出现 `booter FAILED to set` 和 `rd=0x00000001`。然后请求 TLS = 3。成本低，但先验成功概率也低。参见[Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)。

> [!NOTE]
> **未解问题：`FUSE_PCIE_MAGIC_D` 是否可写？**
>
> 一份分析将 `0x00820520` 标注为“(writable)”；一条净室逆向链曾向其中写入 `0x00200000`；实地手册则将其列为只读；分支补丁也只读取它。由于没有 Gen4 主机就无法测试 Gen4，这个操作从未真正执行过。读取它、写入 `0x00200000`、再读回并公布两个数值——这是五分钟就能完成的工作，但至今没人做过。

> [!NOTE]
> **未解问题：x16 是否稳定？**
>
> 2026-07-26 的一次捕获是 Gen2 x16 全部证据的基础。没有老化测试、没有随时间记录的 AER 计数器，也没有第二台测试机。

> [!NOTE]
> **未解问题：Gen2 卡上的 Resizable BAR**
>
> 该能力结构确实存在，并且已经被捕获（`Capabilities: [bb0 v1] Physical Resizable BAR`；BAR0 为 16 MB、BAR1 为 64 MB、BAR3 为 32 MB，每个 BAR 都只有一个受支持大小）。尚未解决的问题是能否让 ReBAR **真正可用**：即使显卡报告 81920 MiB，BAR1 仍固定为 64 MiB，而且还没有人在以 Gen2 训练的卡上重新测试过它。

## 另请参阅

- [Gen2 软件解锁](../unlock/pcie-gen2.md)，了解寄存器机制和分支代码
- [物理改装](../operations/physical-mods.md)，了解电容返工流程
- [熔丝与 OTP](fuses-and-otp.md)，查看完整熔丝图
- [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)，了解尚未解决的另一半问题
- [寄存器索引](../appendix/register-index.md)
- [术语表](../start/glossary.md)
