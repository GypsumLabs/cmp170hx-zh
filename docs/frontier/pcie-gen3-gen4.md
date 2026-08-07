# PCIe Gen3 和 Gen4：为什么仍然处于锁定状态

**本页内容。** 本页汇总 CMP 170HX 上高于 5 GT/s 的 PCIe 代际限制目前已知的一切：两层彼此独立的锁（一对 OTP 熔丝，以及已签名 DevInit 映像中的五字节修改）；为什么 2026-07-24 的 Gen2 突破没有连带解锁 Gen3；可用的 Gen2 补丁读取但从不写入的确切寄存器；所有已被反驳方案的完整目录；以及按成本排序的剩余路线。

**核心结论：CMP 170HX 上从未有 Gen3 或 Gen4 链路完成训练。** 截至 2026-07-28，语料库中没有任何来源报告这张卡出现 `LnkSta: Speed 8GT/s` 或 `16GT/s`。2026-07-24 的实验确实让 Gen3 *能力宣告*生效（`LnkCap: Port #1, Speed 8GT/s, Width x4` 和 `LnkCtl2: Target Link Speed: 8GT/s`），但 `LnkSta` 仍然固定为 `Speed 2.5GT/s, Width x4`。维护者于 2026-07-27 给出的记录收束结论是：Gen3 需要 GSP-RM 固件补丁："Gen 3 doesn't work whatsoever, it's going to require a GSP patch"（Gen 3 完全无法工作，需要 GSP 补丁），"I haven't seen anybody at all get a working GSP patch"（我从没见过任何人拿出一个可用的 GSP 补丁）。

> [!NOTE]
> **未解问题**
>
> 本页描述的是尚未解决的工作，本文没有任何内容已经随发布版提供。Gen2（5 GT/s）*确实*已经通过软件解决，并于 2026-07-29 随 `master` 发布：见[PCIe Gen2](../unlock/pcie-gen2.md)。

> [!WARNING]
> **速率不是位宽**
>
> 在这张卡上，PCIe 链路**速率**（Gen1 到 Gen2）与 PCIe 链路**位宽**（x4 到 x16）是两个完全独立的问题，也需要两种完全不同的修复方案。速率由固件和熔丝决定，是本页的主题；位宽则是 PCB 缺件造成的，只能通过手工焊接 24 颗交流耦合电容修复，见[物理改装](../operations/physical-mods.md)。社区明确的下一个目标，是在原生 x4 位宽下通过软件解锁 Gen3，原因正是这条路线不需要焊接。

---

## 状态一览

| 代 | 速率 | 170HX 上的状态 | 机制 |
|---|---|---|---|
| Gen1 | 2.5 GT/s | 出厂状态，冷启动时总能完成训练 | 已签名 DevInit 对 CMP PCIe 表进行编程 |
| Gen2 | 5.0 GT/s | **已通过软件解决**，自 2026-07-29 随 `master` 发布 | 经 SEC2 Booter 执行组合寄存器序列，再由根端口重训练链路 |
| Gen3 | 8.0 GT/s | **未解决。** 可以宣告能力，但链路从未完成训练 | 维护者于 2026-07-27 表示需要 GSP-RM 补丁，且至今没有可用的 GSP 补丁 |
| Gen4 | 16.0 GT/s | **未解决且无法测试。** 没有贡献者拥有 Gen4 主机 | 熔丝位 25 `GEN4_SPEED_DISABLED`，以及被抑制的 DevInit 代码块 |

供参考的链路状态指纹：

| 状态 | LnkCap | LnkCap2 | LnkCtl2 | LnkSta |
|---|---|---|---|---|
| 出厂（锁定） | `0x00456101` | `0x00000002` | `0x0000` | `0x1041` |
| 安装解锁器并完成训练 | `0x00456102` | `0x00000006` | `0x0002` | `0x1042` |
| 第 3 轮向量伪造 | 写入 `0x00457104`（x16 位宽） | 写入 `0x0180001E`；被裁剪回 `0x00456102` / `0x00000006` | 未记录 | 未记录 |
| Gen3 能力宣告，2026-07-24 | `Port #1, Speed 8GT/s, Width x4` | 未记录 | 接受目标 8GT/s | 仍为 2.5GT/s x4 |

最后两行对应**两个不同的实验**，从未在同一次运行中同时观察到；它们的 `LnkCap` 值编码的位宽也不同（x16 对 x4）。不要把它们理解成同一次运行的结果。

---

## 为什么 Gen2 解锁了，而 Gen3 没有

在 2026-07-24 之前，主流模型根据规范把受支持速率向量视为连续的（Gen4 需要 Gen2 和 Gen3），因此 Gen2、Gen3 和 Gen4 被视为同一个问题：“要么向量被打开，要么什么都打不开”。后来向量确实被打开了，但只开放到了 Gen2。

Gen2 之所以可行，是因为 SEC2 Booter 载荷的写入原语打开了一组权限级别掩码，清除了 `CYA_0` 中的 `DIS_G2` chicken 位，将 `LINK_CONFIG_0` 的 MAX_RATE 强制设为 2，驱动 XP3G 覆盖槽和 `PRIV_MISC_1`，最后由**上游根端口**重新训练链路。端点的 `LnkCap`/`LnkCap2` 是 PHY 的反射值：Gen2 门控打开后，它们会自动重新生成 `0x00456102` / `0x00000006`，不需要任何代码直接写入。它们只会重新生成到 Gen2，**不会继续提升到更高代际**，即使显式写入 Gen1-4 的值也一样：

```text
round-3 spoof: 0x88084 <- 0x00457104   (A100 Max Link Speed = 4)
               0x880A4 <- 0x0180001E   (A100 supported vector, Gen1-4)
observed post: CAP=0x00456102 CAP2=0x00000006
```

硬件把这次写入裁剪到了 Gen2。两天后证明 Gen2 部分可行的一位研究者总结道："Lnkctrl2 is capped at gen2 with a direct hardware mask (which is why gen 3/4 is such a pain). But you can achieve gen2 with the correct register writes."（Lnkctrl2 被直接硬件掩码限制在 Gen2，这就是 Gen3/4 如此棘手的原因；但只要寄存器写入正确，就能实现 Gen2。）

目前两种可能性都不能排除，语料库中没有任何证据能区分它们：

1. 连续性论证对这颗晶片并不成立；或者
2. Gen3 熔丝在受支持速率向量之后的路径中被独立强制执行。

晶片上的最强证据倾向于 (2)。打开 XP3G 权限级别掩码后（`PLM[4] XP3G_PLM(0x8e1b0) reg=0xffffffff`），PHY 速率寄存器被强制写入一个具备 Gen3 能力的值，并且回读正确，但链路仍然以 Gen1 完成训练：

```text
XP3G rate=0x00340036 ovr0=0x4
lnksta=0x10410040 speed=1        # lspci: Speed 2.5GT/s
```

第二条较弱的证据是：在已训练到 Gen2 的卡上，`LnkSta2` 报告 `EqualizationComplete-` 和 `EqualizationPhase1-`，也就是说 Gen3 所要求的 PHY 均衡过程从未运行。最能概括社区观点的说法是 *"Gen2 is a software lockout, Gen3 is a hardware fuse"*（Gen2 是软件锁，Gen3 是硬件熔丝）（置信度：中等；从未有人报告过带有实测 PHY 行为的 Gen3 强制尝试）。

---

## 锁层 1：OTP 熔丝

三个熔丝选项寄存器共同构成这道代际锁的指纹。研究者在两张实体 170HX SKU 上都读取了它们，并与 15 张 Ampere 对照卡进行了比较。

| 寄存器 | 地址 | 170HX | 对比群组 | 备注 |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | `0x0082057c` | `0x00000001` | 三个 A100 SKU、A10、A5000、A6000、RTX 3080/3080 Ti/3090/3090 Ti、一个 ES 部件、一个 Drive A100 和一个 GA10x 对照部件上均为 `0x00000000` | Gen2 补丁唯一尝试写入的寄存器 |
| `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | `0x00820580` | `0x00000001` | 别处全部 `0x00000000` | **从没被任何人写过** |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000`（位 25 置位） | A100 SXM4 40G / PCIe 40G / PCIe 80G / Drive A100 上为 `0x00200000`；A10/A5000/A6000 上为 `0x01a00000`；RTX 30 系列上为 `0x10a80000` | 位 25 的文档名称为 `GEN4_SPEED_DISABLED`，引用 NVIDIA bug 2220334 |

因此，这道锁的三寄存器指纹是 **`1` / `1` / `0x16680000`**。

下面两个与熔丝有关的事实，对于任何计划进行尝试的人都很重要：

- **通道没有被裁剪。** `OPT_PCIE_LANE_DISABLE` `0x00820394`、`CTRL_OPT_PCIE_LANE` `0x0082082C` 和 `STATUS_OPT_PCIE_LANE` `0x00820C2C` 都读为 `0x00000000`，只有速率被熔丝限制。这独立证实了 x4 位宽是板卡问题。
- **软件覆盖路径已被熔丝关闭。** `FUSE_EN_SW_OVERRIDE` `0x00820040` = `0`，`FUSE_DIS_SW_OVR` `0x00820084` = `1`。`0x00820148` 是 DevInit 用来决定是否写入 A100 `MAGIC_D` 值的 OTP 备用位；它读为 `0`，并且永远不能由软件置位。这解释了整个项目中最干净的一次 A/B 实验（2026-07-22）：在同一次引导中，XVE 目标成功写入并保持生效，而 `0x820520` 仍为 `0x16680000`、`0x820148` 仍为 `0`。

### `OPT_GEN3` 和 `OPT_MAGIC`：只读取和记录，从不写入

这是本页最重要的代码级事实。可用的 Gen2 补丁 `0007-pcie-gen2.patch` 用 `#define` 定义了全部三个熔丝选项寄存器，也会逐个打印它们；但在包含 23 个条目的 Booter 路由写表中，恰好只有其中一个寄存器出现：

```c
/* from 0007-pcie-gen2.patch */
#define PCIE_GEN2_OPT_GEN23_ADDR   0x0082057cU   /* write attempted -> fails on silicon */
#define PCIE_GEN2_OPT_GEN3_ADDR    0x00820580U   /* read only */
#define PCIE_GEN2_OPT_MAGIC_ADDR   0x00820520U   /* read only */
```

三个值一起出现在 `NV_PRINTF` 参数列表里、带格式 `OPT=%08x/%08x/%08x`（GEN23 / GEN3 / MAGIC）。在一个 Gen2 分支引导上那个打印读：

```text
OPT=00000001/00000001/16680000
```

单凭这一行就能作为有用的 dmesg 指纹：Gen1 构建会输出 34 条 `SEC2_DEBUG` 日志，Gen2 构建会输出 80 条。

> [!NOTE]
> **行数不是一个可靠的跨构建指纹**
>
> 34（Gen1 构建）/ 80（Gen2 构建）这一结果的置信度较高；另一次 Gen2 分支 610.43.03 引导则以中等置信度统计到 152 条。不要因为数量不一致，就判断安装失败。

任何分支（包括独立的净室逆向工具集）都没有代码路径请求高于 2 的目标链路速率：Gen2 代码在 `constants.yaml` 中将 `target_gen: 2` 固定为 2，写入的 `TARGET_LINK_SPEED` 是 `2`，LTSSM 速率字段也设为 `2`，成功条件则是 `LnkCap2 & 0x4`。

### `OPT_GEN23` 写入失败，但 Gen2 仍然可用

唯一一次*确实*尝试过的熔丝写入并未生效。下面的日志逐字摘自一次插桩构建，记录的是同一轮引导中的两张 GPU：

```text
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter OPT_GEN23(0x82057c)=0x00000000 \
  attempt=1 status=0xffff rd=0x00000001 OVR0=0x00000000 VAL0=0x00000000 \
  OVR3=0x00000000 VAL3=0x00000000
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter FAILED to set OPT_GEN23
```

一次直接的高安全写入记录了 `PLM[4] OPT_GEN23(0x82057c) status=0xffff reg=0x1 (write FAILED)`。该寄存器只是 OTP 熔丝感测值的反射，没有任何权限级别的写入端口。**因此，即使 `OPT_GEN23` 从未被清除，Gen2 仍然可以工作。** 真正的突破点不是熔丝影子，而是 `CYA_0`、`LINK_CONFIG_0`、XP3G 覆盖和 `PRIV_MISC_1`。

这对后续规划很重要，因为 Gen3 最常被提到的“便宜的下一步”是：通过那张据称“已经成功写入 `0x0082057c`”的表，将 `0x00820580 = 0`。但这个前提是错误的：在晶片上已经观察到该表对 `0x0082057c` 的写入失败。这个实验仍值得做（只需一次引导），但成功的先验概率应当很低。

---

## 锁层 2：DevInit 配置表

PCIe 速率限制还存在于 SPI 闪存中**未加密**的 DevInit Falcon 映像内的一张 PCIe 配置表中，而不是传统 x86 VBIOS 部分。

| 项 | CMP 170HX | A100 |
|---|---|---|
| 表位置、闪存地址 | `0x420ED`（镜像 `0xA20ED`） | `0x408A0`（镜像 `0xA08A0`） |
| 运行时 DMEM 基址 | `0xF1D` | `0xE50` |
| 表 `+0xC7..+0xCB` 处的五个字节 | `00 00 08 00 06`，位于闪存 `0x421B4-0x421B8` | `00 00 14 00 06`，位于闪存 `0x40967-0x4096B` |
| 表 `+0x0F` 处的抑制标志 | `0x01` | `0x00` |
| DevInit 映像 | 闪存 `0xDE00`（反汇编基址 `0x8000`），并复制到 bank 2 的 `+0x60000` 处 | 布局相同 |
| BIT 表（I、i、C、D、x、p、u、B、M） | 与 A100 逐字节相同 | 与 CMP 逐字节相同 |

抑制标志是决定性字节。在 `0x31B3F-0x31B92` 的反汇编中，代码读取该标志，然后跳过整个 Gen4 编程块：

```text
ld b8 r9, D[tab+0x0F]
bra ne -> skip whole block
```

当这段代码块确实运行时，它会计算两个只写寄存器的值：

```text
0x88CE4 = (old & ((b1<<8) | b0)) | ((b3<<8) | b2)   ; reduces to byte [+0xC9] since b0=b1=b3=0
0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)               ; b4 = 0x06 on both parts
```

`0x88CE0` 和 `0x88CE4` 在整个 DevInit 反汇编中都只被写入（属于一次性的 Gen4 初始化配置），位于 Physical Layer 16.0 GT/s Extended Capability 的 XVE 影子中（PCIe 能力 ID 为 `0x0026`，影子地址为 `0x88C1C`）。周围的 Gen4 序列还会写入 LTSSM 超时值 `0x8D1A0 = 0x1B1F2327` 和 `0x8D1A4 = 0x0B0F1317`（与正在工作的 A100 值相同），以及 `0x88610 = 0x1001`。

后来，针对 CMP DevInit 反汇编运行的符号化 mini-解释器确认，DevInit 中总共有**十三个**字节不同，而不是五个；其中十一处差异被归因于非 PCIe 的 SKU 功能（HBM、NVLink、ECC）。与 PCIe 相关的使用方包括：`[0xC9]` 被用于 `0x88CE4` 和 `0x132B70`；`[0x1C-0x1F]` 被用于 `0x8C2C0` 以及 `0x918050`/`0x91C050`/`0x920050` 系列；`[0x3F]`（A100 上为 `0x00`，CMP 上为 `0x0C`）被用于 `0x8C040`。

> [!CAUTION]
> **重新刷写不是可行路线**
>
> 全部五个 PCIe 字节都**100% 位于** Davies-Meyer `csecret(2)` MAC 范围 `0x2200-0x43C00` 内。没有密钥的伪造属于 2^128 次第二原像问题。Ampere RSA 签名检查会拒绝被编辑过的映像，显卡将无法引导。`0x40B4B`、`0x40F05-3D` 和 `0x40FC5-CB` 处的 Gen 能力字节也位于 MAC 范围内。不要尝试刷写修改过的 DevInit：见[VBIOS](../hardware/vbios.md)和[恢复](../procedures/recovery.md)。

### 被反驳的直觉：跳线字段会单调限制能力

这是语料库中最有价值的更正之一。社区 `pcie_set_speed` 补丁所采用的直觉方向恰好相反。已签名 FWSEC 中的 DevInit 读-改-写代码是 `mov r9 0x14118f78; ld; and 0x3ff / or 0x400; st`，位于 VBIOS 偏移 `0xE88C`，每个 ROM 中都有 26 处引用；170HX 与 A100 的差异在于**写入的值**，而不在代码本身。该跳线字段具有限制作用：`0` = 启用所有代际，`3` = 170HX 的设置（清除 Gen2/3/4），`0xF` = 越界 / 全部禁用。要提高上限，必须使用**更低**的跳线值，但不存在写入端口。

一个相关的地址空间说法于 2026-07-27 被撤回：FWSEC Falcon 代码中的每个 `0x14xx....` 常量，都是与孔径基址 `0x14000000` 进行 OR 运算后得到的 BAR0 偏移量，因此 `0x14118F78` 实际对应 BAR0 偏移 `0x118F78`，位于普通 16 MB 窗口内，而不是位于独立的 ">16 MB Falcon PRIV bus" 上。**加载驱动时**，主机读取 `0x118F78` 返回 `0xbadf1100`（NVIDIA 的 priv 毒值模式），所以在 FWSEC 上下文之外，主机是否能够访问该地址仍未得到证明。

---

## 熔丝实际上在哪里被使用

DevInit 完全不会读取那两颗 Gen 熔丝。CMP DevInit 反汇编中所有 `0x82xxxx` 访问如下：`0x820C14`/`0x820D38`（FBIO/FBP 熔丝裁剪）、`0x820684`（`FUSE_NVLINK_DIS`）、`0x82380C`/`0x823814`、`0x820520`、`0x820148`、`0x8243xx`、`0x8202xx`、`0x8201xx`、`0x82033C`/`0x82030C`。其中没有 `0x82057C` 或 `0x820580`。

GSP-RM 确实会读它们，这些读取点已定位：

| 固件 | 地址 | 指令证据 |
|---|---|---|
| `470.42.01 gsp.bin` | 熔丝读取跳转表，位于 `0x5D55834` | `li a2, 0x580` 和 `li a2, 0x57c` |
| `580.105.08 gsp_tu10x.bin` | `0x4DD9B00`（`jalr fuse_read`） | `li a2, 0x57c` |

正是这组读取点，构成了当前“需要 GSP 补丁”这一结论的依据。对 `gsp_tu10x.bin` 的完整反汇编扫描还确认了 GSP **不会**做什么：在任何位置都没有找到对 `0x88CE4`、`0x88CE0`、`0x88084`、`0x880A4`、`0x880A8`、`0x820520` 或 `0x82057C` 的写入。GSP 只在链路管理过程中访问 PCIe（对 `0x88088` 的位 0-1 执行读-改-写；读取速率时有 Gen1/2/3 分支，而 Gen4 会落入默认路径；还会访问 `0x8A088`、内部寄存器 `0x88A48`/`0x88A4C`/`0x88A64`，以及通过 `0x82000 | offset` 动态访问熔丝块）。

> [!NOTE]
> **值得保留的方法说明**
>
> 早期一次简单的 4 字节常量搜索错误地报告 GSP 映像中 “no XVE references”（没有 XVE 引用），原因是 RISC-V 会通过 `lui`/`addi` 动态构造这些地址，因此必须进行完整的模式扫描。加密的 GSP 区域仍然无法读取，所以即便修正后的扫描也不是穷尽式的。

---

## 速率能力的寄存器级图

以下内容来自 RM 反汇编，但需要注意：可用的 Gen2 结果表明，实际情况比这张图所暗示的更加宽松（置信度：中等）。

| 寄存器 | 角色 | 访问 | 170HX 上观察到 |
|---|---|---|---|
| `0x85080` | 受支持速率来源 [23:20]、跳转表索引 | RO，在 4.1 M 行 RM 反汇编中没有写入者 | 从注入点读取为 `0xBADF1100`（毒值） |
| `0x85084` | Allowed-Gen 掩码 [3:0]，每次重训练时由 GSP-RM 重新派生 | 从可达上下文看为 RO | `0xBADF1100` |
| `0x88084` | `MAX_LINK_SPEED` [3:0] | PHY 反射值，标记为 R-XVF | 出厂为 `0x00456101` |
| `0x8808C` | `SUPPORTED_LINK_SPEED` [7:1] | PHY 反射值，标记为 R-EVF（无写入端口） | 主机访问被 PROT-wall 拦截 |
| `0x880A8` | `TARGET_LINK_SPEED` | RW，但受 SUPPORTED 限制 | 出厂为 `0x00000001` |
| `0x8841C` | `PRIV_MISC_1` CYA Gen2/3 覆盖位 11-16、30、31 | PLM 下 RW | `0x20340500` 到 `0x20342d00` |
| `0x88610` | `VSEC_HIERARCHY`、位 12 门控 PRIV_MISC_1 重新编程 | PLM 下 RW | 活 `0x00001001` |
| `0x8872C` | LTSSM 触发器（写入 `6`） | PLM 下 RW | 不是真正的重训练 |
| `0x8C1C0` | `PL_LINK_RATE`、gen 字段 [19:16] | PLM 下 RW | 被 0007 写成 `0x00240036` |
| `0x881C0` | `PPCI.UNK1C0`、[17:16] `LNK_CAP_SPEED`、[21:20] `SYSTEM_MAX_SPEED` | 主机读被挡 | `0xbadf5040`；A100 孪生 `0x8C1C0` 读 `0x00040036` |

速率向量编码：Gen1 = `0x1`，Gen1_2 = `0x3`，Gen1_2_3 = `0x7`，Gen1_2_3_4 = `0xF`。

对参考 A100 80GB 进行的一次强制代际扫描，确定了链路速率实际由哪里决定，也是目前最干净的对照测量：

| 强制代 | `0x88088`（[19:16] 处速度） | `0x880a8`（[3:0] 处目标） | `0x88084` |
|---|---|---|---|
| Gen1 | `0x11010140` | `0x001e0001` | `0x00456104` 或 `0x00457104` |
| Gen2 | `0x11020140` | `0x001f0002` | 不变、半字节总 4 |
| Gen3 | `0x11030140` | `0x001f0003` | 不变 |
| 原生 | `0x11040140` | `0x001f0004` | 不变 |

---

## 已尝试但失败的方案

### 寄存器和配置空间尝试

| # | 方法 | 看起来合理的原因 | 失败原因 | 日期 |
|---|---|---|---|---|
| 1 | 使用所有速率设置，通过 `setpci` 写入 LnkCap2（配置空间 `0x2C`） | 它确实就是列出受支持速率的寄存器 | 写入被静默丢弃。硬件将其设为只读，NVIDIA 的 `dev_nv_xve3g_fn0` 头文件将其标为 `R-EVF`：任何权限级别都没有写入端口，因此打开 PLM 也无济于事 | 2026-07-24 |
| 2 | 单独提高 `TARGET_LINK_SPEED`（`0x880A8`）并重训练 | TARGET 确实可写 | 链路仍以 Gen1 重新训练；端点在自己的 TS1/TS2 ordered sets 中重新宣告 Gen1，并受只读 SUPPORTED 字段限制 | 2026-07-24 |
| 3 | 从主机向 `0x88070` / `0x8808C` / `0x88090` 执行 BAR0 写入 | 它们紧邻能力块 | 主机访问被 PROT-wall 拦截：读取返回 0，写入被忽略 | 2026-07-24 |
| 4 | 单独执行高安全 XP3G PHY 速率覆盖 | PLM 已打开，覆盖寄存器可写，回读速率为 Gen3 能力值 `0x00340036` | 链路仍停留在 Gen1。这至少证明了一个正面结果：`0x10B9` SEC2 CSB 邮箱 gadget 能够到达 XP3G/PCIe 特权块。后来它成为可用 Gen2 组合中的一个*组件* | 2026-07-24 |
| 5 | 写入高安全 `FEAT_OVR` 后重新训练 | 算力解锁恰好就是通过这条路线实现的 | `0x823800` 回读为 `0xfffffe8e`（写入生效），`OPT_GEN23` 仍为 `0x1`，链路仍停在 Gen1，AER = 0。当时的结论是：FEAT_OVR 中某个 PCIe 覆盖使能被熔丝设为**关闭**，不像 `SM_SPD` 那样被熔丝设为**开启**。注意，[FEAT_OVR 目录](nvlink.md#route-b-a-feat_ovr-style-attack)没有在该块中列出 PCIe 寄存器，因此应将其视为探测结果，而不是已经定位到的寄存器 | 2026-07-24 |
| 6 | 直接写入 `OPT_GEN23`（`0x82057C` <- 0） | 看起来是明显的突破点 | 从主机、HS-ROP 以及 Booter 载荷写入都失败。已发布的 Gen2 补丁仍会尝试写入它，但仍然失败，而 Gen2 依旧可用 | 2026-07-23 |
| 7 | 经 Booter 设 `VSEC_DEVICE` 位 0 | 是已发布序列的一部分 | `pre=0x00000800 want=0x00000801`、失败两次带 `rd=0x00000800`。对 "transient window"（瞬态窗口）模型尴尬、它把窗口关闭归咎于 RM 清除一个补丁从未设置的位 | 2026-07-23 |
| 8 | 在 postbl 阶段写入派生出的 allowed-Gen 掩码 `0x85084` | “GSP writes `0x85084`”确实属实 | 从注入点读取 `0x85080` 和 `0x85084` 都得到 `0xBADF1100`，写入也会被丢弃。GSP 是在注入点无法达到的权限级别下写入该寄存器，而且每次重训练时都会重新派生它 | 2026-07-24 |
| 9 | 在 VFIO/QEMU 下扫描 BAR0 `0x8872c` 的取值 | 它靠近 LTSSM | `0x6` 很稳定，但会让 LTSSM 停在 Gen1 x4；`0x2` 和 `0xA` 会暴露额外的 Gen2 行为，最终却使 VFIO/QEMU 函数卡死。已发布的 0007 恰好写入 `0x6`，其日志也写着 "skip mid-boot retrain" | 2026-07-12 |
| 10 | 将 `0x88084` `MAX_LINK_SPEED` 作为可写上限 | 一份分析认为不存在主机可写的后备寄存器 | 对某个 scratch 寄存器执行的一次 HS 写入成功，但对整个 XP-PL `LINK_CONFIG` 簇（`0x8C044` / `0x8C048` / `0x8C04C`）执行相同写入却被拒绝。转发者认为那份分析可能有误，但已检查的部分仍成立：该寄存器簇确实不同于工作补丁使用的 `0x8C040`/`0x8C2C0`/`0x8C1C0` | 2026-07-12 |
| 11 | 将 `0x8c044`（XP_PL）作为链路速率寄存器 | 已提出的候选 `0x8c044/0x2` | 读取为 `0xbadf5040`，即 priv 屏蔽哨兵值；探测写入测试跳过了它。值得注意的是，在参考 A100 上，同一组三个寄存器在*每一*代际都读为 `0xbadf5040` | 2026-07-20 |

### 固件和签名相关尝试

| # | 方法 | 失败原因 |
|---|---|---|
| 12 | 编辑 VBIOS devinit 的 Gen-strap 字节 | 通过搜索 Falcon 寄存器 `0x14118F78` 的引用和字节模式 `78 8f 11 14`，在 3 个 devinit 位置找到 5 个字节。相对于 A100 SXM4 的差异是：命中 #8 从 `0xBB` 变为 `0xE2`，命中 #10 从 `72 DE` 变为 `52 DD`，命中 #11 从 `97/59` 变为 `95/39`。5 个字节全部位于 `csecret(2)` MAC 范围内。**已关闭** |
| 13 | 重新刷写编辑过的 VBIOS（`nvflash` / CH341A） | Ampere RSA 签名检查会拒绝它，显卡无法引导 |
| 14 | RAM 打补丁 TOCTOU（在加载和验证之间修改已签名固件） | Ampere 上这条路已关闭：签名验证发生在 **DMA 传入 IMEM 的过程中**，不存在加载与验证之间的窗口。该结论适用于针对这一部件的任何固件级攻击 |
| 15 | `csigenc` ACL-`0x13` 溢出（让 HS 机密越过 1 bit 的引导 oracle 泄露） | 离线分析已经排除。`envydis` 显示 SEC2 booter 的安全主体从 `0x101` 到 `0x86FB` 都是在 `csecret(6)` AES 下的密文，明文桩中没有 SCP/crypto 操作码，因此没有可固定的 ROP 地址 |
| 16 | 绕过主密钥签名 / 执行任意 HS Falcon 代码 | 不存在可利用的缺陷。已知的时序漏洞只能产生**数据寄存器 poke**，不能执行任意 Falcon 代码，因为主体经过 AES 加密且无法伪造签名。明文在 `0x101` 处结束，也不存在 HS 可达的 Ampere CVE |
| 17 | 泄露的生产 HULK 证书 | 相关内容位于 ROM `0xFE504`、`csecret(40)`，且 `STRICT_ID_MATCH=NO`。它受 `RmActivateHulk` fmodel 标志控制，在生产晶片上为 false；还需要证书文件。并且卡上的 FEAT_OVR 写入无论如何都不会改变 `OPT_GEN23`（见 #5），所以这条路线基本没有实际意义 |
| 18 | `csecret(6)`/`csecret(2)` 故障注入（EM 或电压毛刺） | 需要约 $400-2k 的设备、数周工作且没有成功保证；即使成功，这个部件在 PCIe 上**仍然**会受熔丝限制。工具链已在线下验证，但设备从未购置。有人提出 ChipSHOUTER CW520，但从未尝试 |

### 硬件和平台相关尝试

| # | 方法 | 失败原因 |
|---|---|---|
| 19 | 将 A100 的跳线配置复制到 170HX | 一名已经实现 Gen2 x16 的测试者尝试后，结果是：**显卡在引导时无法被检测到**。后续回答很直接：“the straps don't do anything”（跳线不起作用）、“falcon is driving the rewrites”（Falcon 在驱动重写）、“there's no gen3 override register”（没有 Gen3 覆盖寄存器）。Strap4（`R999`/`R1000`，靠近 `U808`）被映射为 `PCIE_CFG`。另一名研究者独立花了两天，将跳线配置与正常工作的 A100 转储进行比较，最后也认定这是失败路线 |
| 20 | 使用普通 PCIe redriver | redriver 只能重新放大信号，端点仍会以自身熔丝限制的 TX 速率发送。只有**重定时器**能够终止链路、向两侧宣告不同速率，并伪造 TS1/TS2 Rate-ID。候选器件包括 Astera Aries、TI DS160PR810 类，尚未尝试 |
| 21 | 在驱动内部完整移除设备并重扫（“Option A”） | 有三个问题：GSP 引导钩子运行在 `probe()` 内部，因此在那里调用 `pci_stop_and_remove_bus_device()` 会让自身上下文发生 use-after-free；重扫后驱动会再次探测、引导 GSP、执行写入，然后再次重扫（需要模块全局 once 标志）；正在使用的 CUDA 客户端也会被丢弃。最终发布的是 Option B（重新训练上游桥） |
| 22 | 伪造设备 ID，使其显示为 A100 | 所有被探测的 Ampere 部件上，`FUSE_DEVID_SW_OVR_DIS` `0x00820584` 都是 `0x00000001`。写入 XVE 配置影子 dword0 `0x88000 = 0x208210de` 只能改变主机可见的 ID，而 `MAGIC_D` 位 25、PPCI_2 SPEED 和被抑制的 `0x88CE4` 都会保留 |
| 23 | 刷写真正的 A100 80GB VBIOS，以恢复 PCIe 4.0 | 已测试且失败。2026-07-19 的报告是：“Theyve tested that and it doesnt work. the pcie 4.0 bit at least.”（他们已经测试过了，但不起作用，至少 PCIe 4.0 位不行。） |
| 24 | 将 VBIOS `CTRL_OPT` / HULK 选项区域作为 PCIe 突破点 | 从结构上不可能：“CTRL_OPT is remove only, not add”（CTRL_OPT 只能移除，不能添加） |

### 值得记录的错误声称

- 一个声称可以达到 **PCIe Gen 4** 的 fork 于 2026-07-19 在一小时内被揭穿（"This is BS, didn't work for me at all"）。两名测试者的主机本来就被限制在 Gen3，因此根本不可能观察到 Gen4 结果。该声称于 2026-07-21 撤回。
- **“PCIe Gen 3 is actually working” via AI-driven experimentation**（2026-07-24）。从未公布测量结果、寄存器写入或链路状态输出。该声称以玩笑口吻出现，随后立即有人继续讨论仍未解决的 Gen3 和 Gen4。
- 某个公开租赁列表宣称一张 170HX 支持“PCIe 3.0”，后来被认定为平台方的错误报告；同一天还记录了 `OPT_GEN23` 写入失败。
- 频道内反驳了 **“Gen 3.0 and 4.0 is a dead end due to fused blockers in the die”**：“the fuses are signals used by the firmware to control function”（熔丝是固件用来控制功能的信号），“they're not hard efuses that actually destroy functionality”（它们不是会真正摧毁功能的硬 efuse）。反驳观点的证据更充分，因为 Gen2 解锁证明至少有一个熔断的代际限制由固件介导，并且可以被击败。结论仍未定，但目前倾向于反驳观点。

---

## Gen4 影子实验及其引导循环

一个独立的净室逆向补丁 `0007-pcie-gen4-shadow.patch`（不要与 cmpunlocker 的 `0007-pcie-gen2.patch` 混淆，后者是编号相同但不同的补丁）最终陷入引导循环并被放弃，仍然是最有趣的未完成 Gen4 工件。

> [!CAUTION]
> **移除模块之前，这个实验会让引导循环卡死**
>
> 上游补丁 `0001`-`0006` 每次引导运行 4 次 Booter 载荷，可以正常启动。Gen4 影子补丁将其增加到 7-11 次，包括熔丝和重训练尝试。随后，**真正的** BooterLoad 以 `mailbox0 != 0`（状态 `0xffff`）失败；之后 RM 无限重试 `_kgspBootGspRm`，`wprStart` 每次重试都会沿帧缓冲向下移动（每次重试都会重新分配 WPR），最终发生回绕。

其中一个原因已经排除：设置 `CMP_PCIE_RETRAIN=0` 后循环仍然持续，因此可以排除驱动内重训练。剩下两个假设，至今没有得到裁决：

- **H-COUNT。** 在真正引导前执行了过多 Booter / priv-sequencer 操作，耗尽了 sequencer 状态。注意 `kgspExecuteBooterLoad_TU102` 会在每次运行**之前**执行 `kflcnReset(SEC2)`，因此 SEC2 不会累积状态；但 priv sequencer 是另一套不会复位的独立硬件，WPR2/PLM 寄存器和 XVE 写入也会保留。
- **H-WRITE。** 某一次特定写入扰动了 PCIe 块，而 Booter 正好会通过同一条链路从 sysmem DMA 传入签名。首要嫌疑是先写 `0x8C2C0`（LTSSM 配置），再写 `0x8C040`（SPEED）。

二分测试 harness 已经通过编译时开关提供：`CMP_PCIE_ONCE=1`（每个模块生命周期只应用一次；由于写入会保留，第一次循环失败后，第二次循环会在值已应用的干净状态下运行）、`CMP_PCIE_ATTEMPTS=1`，以及分组开关 `CMP_PCIE_XVE_LTSSM_WRITES`、`CMP_PCIE_VECTOR_SPOOF`、`CMP_PCIE_UNK1C0_WRITE`、`CMP_PCIE_XVE_PHY_WRITES`。规定的二分顺序是先测试 LTSSM，再测试 vector 伪造，然后是 UNK1C0，最后才是 PHY。结果从未记录。

---

## 最有希望的剩余路线

按成本从低到高排列，最便宜的路线在前。这些路线都还没有人完成。

### 1. 通过 xp3g 表写入 `0x00820580 = 0`，然后请求 TLS = 3

成本：一次引导。`FUSE_PCIE_GEN3_DIS` 从未被任何人写入。表机制已经存在于 `0007-pcie-gen2.patch` 中；新增一个条目并提高 `target_gen` 只需修改几行。根据上面的 #6，预期结果是出现一行 `booter FAILED to set` 和 `rd=0x00000001`，但把这个否定结果记录下来仍然有价值。关键观察点是 `LnkCap2` 是否会达到 `0x0000000E`。

### 2. `FUSE_PCIE_MAGIC_D` 是否可写？读取、写入 `0x00200000`，再回读

成本：五分钟，从未公开。证据确实相互矛盾。一份分析在位 25 旁标注了 `GEN4_SPEED_DISABLED`，并明确把该寄存器标为 **"(writable)"**，与 `GEN23_DIS` 的 "needs no write" 相对照。一个独立的净室逆向链脚本记录了将 `0x00820520 = 0x00200000`（A100 / Drive 对照值）作为*可用* Gen2 链的一部分写入。但 PCIe 实地手册将 `0x820580` / `0x820520` 列为只读熔丝选项影子，而 `0007` 也只读取 `0x00820520`。由于 Gen4 无法测试，这一点从未实际验证。

### 3. 在 SEC2 高安全上下文中读取 `0x85080` / `0x85084` / `0x881C0`

成本：一次插桩构建。从主机和注入点读取这三个寄存器都会得到毒值。`0x8e1b0` 和 `0x823800` 已经证明可以从 HS 到达，因此读取是可行的。这是定位真正提供受支持速率向量的跳线层的唯一途径。

### 4. 测试 `0x823830`-`0x82383C` 的第二组特性覆盖寄存器

成本：一次 HS 写入并回读。从 PL0 读取返回 `0xbadf5040`，而 HS 读取会返回真实值。该组没有手动 PLM 覆盖，也从未执行过 HS 写入后回读。它被明确列在“writability still unknown / worth testing”（可写性仍未知 / 值得测试）项目下。

### 5. 在一次强制 Gen3 尝试中转储 `LnkSta2` 均衡字段

成本：一次带插桩的引导。反向假设是：`GEN3_DIS` 可能在引导时被锁存到一个可重写的 PHY/strap 配置寄存器中，而不是由模拟 PHY 直接使用；如果确实如此，就会存在一个可以在引导后覆盖的寄存器。提出者本人也认为这个假设更可能失败。能够裁决这一点的测量是：是否曾进入均衡 Phase 1。

### 6. GSP-RM 补丁

这是截至 2026-07-27 被明确提出的要求，也是至今无人交付补丁的原因："I haven't seen anybody at all get a working GSP patch."（我从没见过任何人拿出一个可用的 GSP 补丁。）具体起点是上面提到的两个熔丝读取点（`470.42.01 gsp.bin` 中的 `0x5D55834`，以及 `580.105.08 gsp_tu10x.bin` 中的 `0x4DD9B00`）。问题在于，这种熔丝使用路径能否像 Gen2 覆盖那样被改道，从而绕过 Gen2 路径。加密的 GSP 区域仍然无法读取，这是持续存在的障碍。

### 7. 一个带 `[+0x0F] = 0x00` 和 `[+0xC9] = 0x14` 的已签名或以其它方式被接受的闪存

这是唯一能够确定 DevInit 五字节修改**单独**是否可以恢复 Gen4 的实验。熔丝参考 gist 断言 "PCIe double-locked: `FUSE_PCIE_GEN23_DIS` = `0x1` (fuse) + devinit (5 bytes). Firmware-only patch insufficient"（PCIe 双重锁定：`FUSE_PCIE_GEN23_DIS` = `0x1`（熔丝）+ devinit（5 个字节），仅固件补丁不足），但这个结论只是根据熔丝值推断出来的，并不是实际尝试固件补丁后的结果。从未有人刷写过修改后的 DevInit 表，而没有签名密钥也不可能做到。

### 8. 一个链路级重定时器

受设备和板卡加工条件限制。需要有人利用现成器件和板卡制造能力，制作一个能够伪造 TS1/TS2 Rate-ID 的 interposer。候选器件包括 Astera Aries、TI DS160PR810 类，尚未进行任何尝试。

### 9. 找一台 Gen4 主机

首先受硬件条件阻塞，而不是技术条件阻塞。研究 Gen4 的人直白地说："I can't do PCIe Gen 4 because I don't have a computer that supports it"（我无法做 PCIe Gen4，因为没有支持它的电脑），并另称 "devinit routes are genuinely horrible to try to work on"（devinit 路线确实非常难处理）。

### 低优先级线索

一位研究者将 `Mellanox-ConnectX-5-PCIe-Gen-4-Enablement` 标记为一个类似的 "shipped-downgraded part"（发布时被降级的部件）案例，并明确表示 "not expecting much"（不抱太大期待）。尚未进行任何尝试。

---

## 记录中的方向反复问题

Gen3 路线在大约 40 小时内改变了四次方向。在把任何一句引述视为项目立场之前，应该先了解这一点：

| 时间戳 | 立场 |
|---|---|
| 2026-07-26 06:38 | "a devinit route might be the only way"（一条 devinit 路径可能是唯一方法） |
| 2026-07-26 14:25 | "My current fix doesn't use devinit, and it's a dead end"（我当前的修复不用 devinit、而且它是条死路） |
| 2026-07-26 14:42 | "We need to use devinit"（我们需要用 devinit） |
| 2026-07-27 22:57 | "Gen 3 doesn't work whatsoever, it's going to require a GSP patch" / "I haven't seen anybody at all get a working GSP patch" |

最后一条就是截至 2026-07-28 的状态。

更早的 "four-layer wall"（四层墙）实地手册（日期为 2026-07-24）得出结论：四层限制（运行时寄存器写入、寄存器语义、持久固件、晶片熔丝）在实证上都已关闭，并通过两种方式验证：一次进行了 4032 次运行的离线固件 fuzz 扫描（从 66 个函数中提取 126 个函数-寄存器对，每对扫描 32 个单独的位值），以及晶片上的直接写入探测。该手册第 6 节也说明了它为何在 Gen2 上判断错误：*"The full community Gen2 sequence ... as a single combined write was not run: every component is individually proven inert, so it is a low-odds combination."*（完整的社区 Gen2 序列……没有作为一次组合写入执行；每个组件单独看来都不起作用，因此这是一个成功概率很低的组合。）结果这个低概率组合成功了。**但该结论关于 Gen3 的部分仍然成立。**

---

## 如果你要验证一个 Gen3 声称

> [!WARNING]
> **使用 LnkSta 验证，绝不要使用 LnkCap**
>
> `LnkCap` 表示宣告的能力，即使链路仍以 Gen1 训练，它也可能报告更高的代际。这个陷阱正是大多数经不起验证的 "it works"（能工作）声称的来源。2026-07-24 的 Gen3 能力宣告结果恰好就是这种情况。

```bash
# the three honest fields
sudo lspci -vvs <bdf> | grep -E 'LnkCap:|LnkCap2:|LnkSta:'
cat /sys/bus/pci/devices/<bdf>/current_link_speed
nvidia-smi --query-gpu=pcie.link.gen.gpucurrent --format=csv
```

这张卡上有两个已知的假信号：

- 在完成 Gen2 训练的 170HX 上，`/sys/.../max_link_speed` 仍然读为 `2.5 GT/s`，而 `current_link_speed` 读为 `5.0 GT/s`。应从配置空间进行诊断，不要依赖 sysfs 属性。
- 自 2023 年起，`nvidia-smi` 在一张出厂卡上报告 `PCIe Generation Max : 2`，但 `Device Current` 和 `Device Max` 都读为 `1`，`LnkCap2` 也只列出 2.5 GT/s。它只能用作指纹。

ASPM 在其他平台上确实可能造成假阴性（许多平台在空闲时会把链路降到 Gen1），但 170HX 自身在 `LnkCap` 中宣告 `ASPM not supported`，所以在这张卡上它更适合作为首要诊断信息，而不是可能的原因。

---

## 实测值

| 测量项 | 值 | 条件 | 置信度 |
|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS` `0x0082057c` | `0x00000001` | 两个 170HX SKU、两个物理单元、各读两次；13 个对比部件上 `0x00000000` | 高 |
| `FUSE_PCIE_GEN3_DIS` `0x00820580` | `0x00000001` | 相同 | 高 |
| `FUSE_PCIE_MAGIC_D` `0x00820520` | `0x16680000`（位 25 置位） | 170HX；A100 家族 `0x00200000` | 高 |
| `OPT_PCIE_LANE_DISABLE` `0x00820394` | `0x00000000` | 170HX | 高 |
| `CTRL_OPT_PCIE_LANE` `0x0082082c` | `0x00000000` | 170HX | 高 |
| `STATUS_OPT_PCIE_LANE` `0x00820c2c` | `0x00000000` | 170HX | 高 |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000` | 170HX 和全部数据中心 GA100；消费级部件上 `0x00000001` | 高 |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | 全部卡 | 高 |
| `0x00820148`（DevInit MAGIC_D 门控位） | `0x00000000` | OTP 备用位，软件永远无法设置 | 高 |
| Gen2 dmesg 中的 `OPT=` 三元组 | `00000001/00000001/16680000` | 完整 Gen2 运行后的 GEN23 / GEN3 / MAGIC | 高 |
| PLM 打开后的 XP3G 速率 | `0x00340036`、`ovr0 = 0x4` | 写生效、链路停 Gen1（`lnksta=0x10410040`、速度 1） | 高 |
| `0x85080` / `0x85084` | `0xBADF1100`（毒值） | 从注入点读取 | 高 |
| `0x881C0` 主机读 | `0xbadf5040` | priv 屏蔽模式 | 高 |
| A100 上的 `0x8C1C0` | `0x00040036` | PPCI_2 UNK1C0 参考 | 高 |
| `A100 0x8C044` / `0x8C048` / `0x8C04C` | 每一代 `0xbadf5040` | 即使在参考卡上也屏蔽 | 高 |
| CMP `0x88CE4` | `0x0000003F` | 对比 A100 `0x00000014` | 高 |
| CMP `0x88CE0` 低 6 位 | `0x02` | 对比 A100 `0x06` | 高 |
| CMP `0x8C040` `PPCI_2.CONFIG_LINK` | `0x800C4C00`（SPEED = 3） | BAR0 mmap、无驱动；A100 `0x80004C00`（SPEED = 0） | 高 |
| CMP `0x8C2C0` | `0x068731B7` | 对比 A100 `0x060711B2` | 高 |
| CMP `0x880A8` | `0x00000001` | 对比 A100 `0x001F0004` | 高 |
| CMP `0x88084` / `0x880A4` | `0x00456101` / `0x00000002` | 对比 A100 `0x00457104` / `0x0180001E` | 高 |
| `0x118F78` / `0x132B70` | CMP 和 A100 上都是 `0` / `0` | **BAR0 mmap，未加载驱动**（同一地址在驱动运行时由主机读取会返回 `0xbadf1100`）；相同的值不能编码 SKU 限制 | 高 |
| `0x132B30` / `0x132B6C` / `0x132B50` | 两者上 `0x00000400` / `0x08000020` / `0x03780000` | 空转、无驱动 | 高 |
| LTSSM 超时 `0x8D1A0` / `0x8D1A4` | `0x1B1F2327` / `0x0B0F1317` | CMP 和 A100 相同 | 高 |
| 每次引导的 Booter 载荷运行 | 4（补丁 0001-0006、正常引导）对比 7-11（Gen4 实验、引导循环） | GSP 引导 | 高 |
| Booter 载荷运行状态 | 每次运行都是 `0xffff`，即使写入已经生效 | 只有寄存器回读能够作为有效判据 | 高 |
| SEC2_DEBUG dmesg 行数 | 29（归档单卡捕获）、34（Gen1 构建）、80（Gen2 构建）、134（归档双卡 Gen2 分支 610.43.03 日志）、152（两台双卡 Gen2 机架上的 `pcielink.sh`） | **不是一个可靠的跨构建指纹**；不要把不匹配读成一次失败的安装 | 高 |
| Gen3 宣告结果 | `LnkCap Speed 8GT/s`、`LnkCtl2 Target 8GT/s`、`LnkSta Speed 2.5GT/s` | 2026-07-24 | 高 |

---

## 参见

- [PCIe Gen2](../unlock/pcie-gen2.md)：查看确实可用的机制
- [PCIe 子系统](../hardware/pcie-subsystem.md)：查看寄存器块图
- [熔丝与 OTP](../hardware/fuses-and-otp.md)：查看完整熔丝群组
- [VBIOS](../hardware/vbios.md)：查看 DevInit 映像布局和签名
- [物理改装](../operations/physical-mods.md)：查看只改变位宽的电容改装
- [失败路线](../history/dead-ends.md)和[未解问题](open-questions.md)
- [状态板](status-board.md)
