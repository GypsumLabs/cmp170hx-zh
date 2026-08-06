# PCIe Gen3 和 Gen4：为什么它们仍被锁定

**本页覆盖内容。** 关于 CMP 170HX 上 5 GT/s 之上 PCIe 代墙的一切已知：两个独立锁层（一对 OTP 熔丝加已签名 DevInit 映像里一个五字节编辑）、为什么 2026-07-24 的 Gen2 突破没有把 Gen3 带上、那个工作的 Gen2 补丁读取却从不写入的精确寄存器、一份被反驳方法的完整目录、以及按成本排名的剩余路径。

**头条：从没有任何 Gen3 或 Gen4 链路在 CMP 170HX 上训练过。** 截至 2026-07-28 语料库里没有来源报告这张卡上 `LnkSta: Speed 8GT/s` 或 `16GT/s`。Gen3 *宣告* 在 2026-07-24 被做成工作（`LnkCap: Port #1, Speed 8GT/s, Width x4` 和 `LnkCtl2: Target Link Speed: 8GT/s`）而 `LnkSta` 仍钉在 `Speed 2.5GT/s, Width x4`。记录上的收官立场、由维护者于 2026-07-27 陈述，是 Gen3 需要一个 GSP-RM 固件补丁："Gen 3 doesn't work whatsoever, it's going to require a GSP patch"（Gen 3 完全不工作、它需要一个 GSP 补丁）、"I haven't seen anybody at all get a working GSP patch"（我从没见过任何人拿到一个工作的 GSP 补丁）。

> [!NOTE]
> **未解问题**
>
> 本页描述未解决的工作。这里没有任何东西出货。Gen2（5 GT/s）*是*在软件里解决并于 2026-07-29 在 `master` 出货：见[PCIe Gen2](../unlock/pcie-gen2.md)。

> [!WARNING]
> **速度不是位宽**
>
> PCIe 链路**速度**（Gen1 到 Gen2）和 PCIe 链路**位宽**（x4 到 x16）在这张卡上是两个完全独立的问题、带两个完全独立的修复。速度是固件和熔丝、本页的主题。位宽是一个只靠手工焊接 24 颗交流耦合电容修复的 PCB 缺件、在[物理改装](../operations/physical-mods.md) 覆盖。一个原生 x4 位宽下的 Gen3 软件解锁正是社区陈述的下一目标、因为它不需要焊接。

---

## 状态一览

| 代 | 速率 | 170HX 上的状态 | 机制 |
|---|---|---|---|
| Gen1 | 2.5 GT/s | 出厂、冷启动总训练 | 已签名 DevInit 编程 CMP PCIe 表 |
| Gen2 | 5.0 GT/s | **软件里解决**、自 2026-07-29 在 `master` 出货 | 经 SEC2 Booter 的组合寄存器序列加一次根端口重训练 |
| Gen3 | 8.0 GT/s | **未解决。** 能力可以被宣告；链路从不训练 | 2026-07-27 被维护者陈述需要 GSP-RM 补丁、且没有工作 GSP 补丁被生产出来 |
| Gen4 | 16.0 GT/s | **未解决且不可测试。** 没有贡献者有 Gen4 主机 | 熔丝位 25 `GEN4_SPEED_DISABLED` 加被抑制的 DevInit 块 |

供参考的链路状态指纹：

| 状态 | LnkCap | LnkCap2 | LnkCtl2 | LnkSta |
|---|---|---|---|---|
| 出厂（锁定） | `0x00456101` | `0x00000002` | `0x0000` | `0x1041` |
| 装了解锁器、已训练 | `0x00456102` | `0x00000006` | `0x0002` | `0x1042` |
| 第 3 轮向量欺骗 | 写了 `0x00457104`（x16 位宽） | 写了 `0x0180001E`；被裁剪回 `0x00456102` / `0x00000006` | 未记录 | 未记录 |
| Gen3 宣告、2026-07-24 | `Port #1, Speed 8GT/s, Width x4` | 未记录 | 目标 8GT/s 被接受 | 停 2.5GT/s x4 |

最后两行是**两个不同的实验**、从未一起观察、它们的 `LnkCap` 值编码不同的位宽（x16 对比 x4）。不要把它们读作一次运行。

---

## 为什么 Gen2 倒下而 Gen3 没有

2026-07-24 之前、盛行模型把受支持速度向量按规范当作连续的（Gen4 需要 Gen2 和 Gen3），所以 Gen2、Gen3 和 Gen4 被当作一个问题："either the vector opens or nothing does"（要么向量打开、要么什么都不打开）。向量随后打开了、而且只到 Gen2。

Gen2 结果通过经 SEC2 Booter 载荷写原语打开一组权限级别掩码、清除 `CYA_0` 里的 `DIS_G2` chicken 位、把 `LINK_CONFIG_0` MAX_RATE 强制到 2、驱动 XP3G 覆盖槽和 `PRIV_MISC_1`、然后让**上游根端口**重训练链路来工作。端点的 `LnkCap`/`LnkCap2` 是 PHY 反射：一旦 Gen2 门打开、它们再生到 `0x00456102` / `0x00000006`、无需任何东西直接写它们。它们再生到 Gen2 **且不再向前**、即使一个欺骗显式写 Gen1-4 值：

```text
第 3 轮欺骗：0x88084 <- 0x00457104   （A100 Max Link Speed = 4）
               0x880A4 <- 0x0180001E   （A100 受支持向量、Gen1-4）
观察后：CAP=0x00456102 CAP2=0x00000006
```

硬件把写裁剪到 Gen2。一位两天后证明出 Gen2 那一半的研究者把它总结为："Lnkctrl2 is capped at gen2 with a direct hardware mask (which is why gen 3/4 is such a pain). But you can achieve gen2 with the correct register writes."（Lnkctrl2 被一个直接硬件掩码封顶在 gen2（这就是为什么 gen 3/4 这么痛）。但你可以用正确的寄存器写达到 gen2。）

两个可能性仍活着、语料库里没有任何东西分开它们：

1. 连续性论证对这颗硅片就是错的，或
2. Gen3 熔丝被独立强制、在受支持速度向量下游。

最强的硅片上证据偏好 (2)。带 XP3G 权限级别掩码打开（`PLM[4] XP3G_PLM(0x8e1b0) reg=0xffffffff`）、PHY 速率寄存器被强制到一个 Gen3 能力的值并正确回读、链路仍以 Gen1 训练：

```text
XP3G rate=0x00340036 ovr0=0x4
lnksta=0x10410040 speed=1        # lspci: Speed 2.5GT/s
```

第二条、较弱的证据线：在 Gen2 训练过的卡上 `LnkSta2` 报告 `EqualizationComplete-` 和 `EqualizationPhase1-`、即 Gen3 强制的 PHY 均衡趟从未跑过。捕捉社区观点的那句措辞是 *"Gen2 is a software lockout, Gen3 is a hardware fuse"*（Gen2 是一个软件锁、Gen3 是一颗硬件熔丝）（置信度：中等；带实测 PHY 行为的 Gen3 强制尝试从未被报告过）。

---

## 锁层 1：OTP 熔丝

三个熔丝选项寄存器形成代锁的指纹。全部在两个物理 170HX SKU 上读取、并对照一个 15 卡 Ampere 群组。

| 寄存器 | 地址 | 170HX | 对比群组 | 备注 |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | `0x0082057c` | `0x00000001` | 全部三个 A100 SKU、A10、A5000、A6000、RTX 3080/3080 Ti/3090/3090 Ti、一个 ES 部件、一个 Drive A100 和一个 GA10x 对照上 `0x00000000` | 唯一 Gen2 补丁尝试写的那个 |
| `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | `0x00820580` | `0x00000001` | 别处全部 `0x00000000` | **从没被任何人写过** |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000`（位 25 置位） | A100 SXM4 40G / PCIe 40G / PCIe 80G / Drive A100 上 `0x00200000`；A10/A5000/A6000 上 `0x01a00000`；RTX 30 系列上 `0x10a80000` | 位 25 被文档化为 `GEN4_SPEED_DISABLED`、引用 NVIDIA bug 2220334 |

因此这个锁的三寄存器指纹是 **`1` / `1` / `0x16680000`**。

两个支持性熔丝事实对任何规划攻击的人要紧：

- **通道是干净的。** `OPT_PCIE_LANE_DISABLE` `0x00820394`、`CTRL_OPT_PCIE_LANE` `0x0082082C` 和 `STATUS_OPT_PCIE_LANE` `0x00820C2C` 都读 `0x00000000`。只有速度被熔断。这是 x4 位宽是一个板卡问题的独立确认。
- **软件覆盖路径被熔丝焊死。** `FUSE_EN_SW_OVERRIDE` `0x00820040` = `0`、`FUSE_DIS_SW_OVR` `0x00820084` = `1`。`0x00820148`、会让 DevInit 写 A100 `MAGIC_D` 值的那个 DevInit 门位、是一个读 `0` 且永不能被软件设置的 OTP 备用位。这正是为什么整个项目里最干净的 A/B（2026-07-22）看到 XVE 目标落地并持久、在同一引导里 `0x820520` 停 `0x16680000` 和 `0x820148` 停 `0`。

### `OPT_GEN3` 和 `OPT_MAGIC`：读取、记录、从不写入

这是本页最重要的代码级事实。工作的 Gen2 补丁 `0007-pcie-gen2.patch` `#define` 了全部三个熔丝选项寄存器并打印全部三个，但它的 23 条目 Booter 路由写表只含其中恰好一个：

```c
/* 来自 0007-pcie-gen2.patch */
#define PCIE_GEN2_OPT_GEN23_ADDR   0x0082057cU   /* 写被尝试 -> 在硅片上失败 */
#define PCIE_GEN2_OPT_GEN3_ADDR    0x00820580U   /* 只读 */
#define PCIE_GEN2_OPT_MAGIC_ADDR   0x00820520U   /* 只读 */
```

三个值一起出现在 `NV_PRINTF` 参数列表里、带格式 `OPT=%08x/%08x/%08x`（GEN23 / GEN3 / MAGIC）。在一个 Gen2 分支引导上那个打印读：

```text
OPT=00000001/00000001/16680000
```

那行本身就是一个有用的 dmesg 指纹：一个 Gen1 构建发 34 条 `SEC2_DEBUG` 行、一个 Gen2 构建发 80 条。

> [!NOTE]
> **行数不是一个可靠的跨构建指纹**
>
> 34（Gen1 构建）/ 80（Gen2 构建）被高置信度记录、而一个单独的 Gen2 分支 610.43.03 引导以中等置信度数到 152。不要把不匹配读成一次失败的安装。

任何分支里、以及独立净室工具集里、都没有代码路径请求高于 2 的目标链路速度：Gen2 代码里的 `constants.yaml` 钉 `target_gen: 2`、`TARGET_LINK_SPEED` 被写成 `2`、LTSSM 速度字段被设成 `2`、成功测试是 `LnkCap2 & 0x4`。

### `OPT_GEN23` 写失败、Gen2 反正工作

那一个*确实*被尝试的熔丝写不落地。逐字来自一个插桩构建、同一个引导的两张 GPU 上：

```text
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter OPT_GEN23(0x82057c)=0x00000000 \
  attempt=1 status=0xffff rd=0x00000001 OVR0=0x00000000 VAL0=0x00000000 \
  OVR3=0x00000000 VAL3=0x00000000
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter FAILED to set OPT_GEN23
```

一次直接高安全写记录 `PLM[4] OPT_GEN23(0x82057c) status=0xffff reg=0x1 (write FAILED)`。该寄存器是一个任何权限级别都无写端口的纯 OTP 熔丝感测反射。**Gen2 因此尽管 `OPT_GEN23` 从没被清除也工作。** 熔丝影子不是杠杆；`CYA_0`、`LINK_CONFIG_0`、XP3G 覆盖和 `PRIV_MISC_1` 才是。

这对规划要紧、因为对 Gen3 最常被引用的 "cheap next step"（便宜下一步）是经同一个 "already succeeds on `0x0082057c`"（在 `0x0082057c` 上已成功）的表写 `0x00820580 = 0`。那个前提是错的：表对 `0x0082057c` 的写在硅片上被观察到失败。实验仍值得跑（它花一次引导）但它的先验应该低。

---

## 锁层 2：DevInit 配置表

PCIe 速度限制也住在 SPI 闪存里**未加密** DevInit falcon 映像内的一张 PCIe 配置表、不在传统 x86 VBIOS 部分。

| 项 | CMP 170HX | A100 |
|---|---|---|
| 表位置、闪存 | `0x420ED`（镜像 `0xA20ED`） | `0x408A0`（镜像 `0xA08A0`） |
| 运行时 DMEM 基址 | `0xF1D` | `0xE50` |
| 表 `+0xC7..+0xCB` 处的五个字节 | `00 00 08 00 06` at flash `0x421B4-0x421B8` | `00 00 14 00 06` at flash `0x40967-0x4096B` |
| 表 `+0x0F` 处的抑制标志 | `0x01` | `0x00` |
| DevInit 映像 | flash `0xDE00`（反汇编基址 `0x8000`）、bank 2 里 `+0x60000` 处复制 | 相同布局 |
| BIT 表（I、i、C、D、x、p、u、B、M） | 与 A100 逐字节相同 | 与 CMP 逐字节相同 |

抑制标志是决定性的字节。在反汇编 `0x31B3F-0x31B92` 里代码读取它并分支远离整个 Gen4 编程块：

```text
ld b8 r9, D[tab+0x0F]
bra ne -> skip whole block
```

当块确实运行时它计算两个只写寄存器：

```text
0x88CE4 = (old & ((b1<<8) | b0)) | ((b3<<8) | b2)   ; 因为 b0=b1=b3=0 归结为字节 [+0xC9]
0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)               ; 两个部件上 b4 = 0x06
```

`0x88CE0` 和 `0x88CE4` 在整个 DevInit 反汇编里都是只写的（一次性 Gen4 init 配置）并坐在 Physical Layer 16.0 GT/s Extended Capability（PCIe 能力 ID `0x0026` 在 shadow `0x88C1C`）的 XVE 影子里。周围的 Gen4 序列也写 LTSSM 超时 `0x8D1A0 = 0x1B1F2327` 和 `0x8D1A4 = 0x0B0F1317`（与活 A100 值相同）和 `0x88610 = 0x1001`。

一个对 CMP DevInit 反汇编的符号 mini-解释器后来确立**总共**十三个 DevInit 字节不同、不是五个；其中十一个不同字节被归因到非 PCIe SKU 功能（HBM、NVLink、ECC）。与 PCIe 相关的消费者是 `[0xC9]` 到 `0x88CE4` 和 `0x132B70`、`[0x1C-0x1F]` 到 `0x8C2C0` 加 `0x918050`/`0x91C050`/`0x920050` 系列、和 `[0x3F]`（A100 上 `0x00`、CMP 上 `0x0C`）到 `0x8C040`。

> [!CAUTION]
> **重刷不是一条路径**
>
> 全部五个 PCIe 字节**100% 落在** Davies-Meyer `csecret(2)` MAC 范围 `0x2200-0x43C00` 内。一个无钥伪造是一个 2^128 次第二原像问题。Ampere RSA 签名检查拒绝一个编辑过的映像、卡不会引导。`0x40B4B`、`0x40F05-3D` 和 `0x40FC5-CB` 处的 Gen-cap 字节也在 MAC 内。不要尝试刷一个修改过的 DevInit：见[VBIOS](../hardware/vbios.md) 和[恢复](../procedures/recovery.md)。

### 被反驳的直觉：跳线字段是单调限制的

语料库里最有价值的更正之一。社区 `pcie_set_speed` 补丁的直觉方向恰好反了。已签名 FWSEC 里的 devinit 读-改-写是 `mov r9 0x14118f78; ld; and 0x3ff / or 0x400; st` 在 VBIOS 偏移量 `0xE88C`、每个 ROM 里 26 处引用；170HX-对比-A100 的增量是**被写的值**、不是代码。跳线字段是限制的：`0` = 所有代启用、`3` = 170HX 设置（清除 Gen2/3/4）、`0xF` = 越界 / 全部禁用。提高上限需要一个**更低**的跳线值、而且不存在写端口。

一个相关的地址空间声称于 2026-07-27 被撤回：FWSEC falcon 代码里每个 `0x14xx....` 常量是一个与孔径基址 `0x14000000` OR 的 BAR0 偏移量，所以 `0x14118F78` 是 BAR0 偏移量 `0x118F78`、在普通的 16 MB 窗口内、不在一条单独的 ">16 MB Falcon PRIV bus" 上。**带驱动加载**的主机读 `0x118F78` 返回 `0xbadf1100`、NVIDIA 的 priv 毒模式，所以 FWSEC 上下文之外的主机可达性仍未证明。

---

## 熔丝实际在哪被消费

DevInit 根本不读那两个 Gen 熔丝。CMP DevInit 反汇编里 `0x82xxxx` 访问的完整清单是 `0x820C14`/`0x820D38`（FBIO/FBP 地板清扫）、`0x820684`（`FUSE_NVLINK_DIS`）、`0x82380C`/`0x823814`、`0x820520`、`0x820148`、`0x8243xx`、`0x8202xx`、`0x8201xx`、`0x82033C`/`0x82030C`。`0x82057C` 和 `0x820580` 都不出现。

GSP-RM 确实读它们、那些读站点已定位：

| 固件 | 地址 | 指令证据 |
|---|---|---|
| `470.42.01 gsp.bin` | fuse-read 跳转表 at `0x5D55834` | `li a2, 0x580` 和 `li a2, 0x57c` |
| `580.105.08 gsp_tu10x.bin` | `0x4DD9B00`（`jalr fuse_read`） | `li a2, 0x57c` |

那个配对就是为什么当前的陈述是 "it needs a GSP patch"（它需要一个 GSP 补丁）。一次对 `gsp_tu10x.bin` 的完整反汇编扫描也确立 GSP **不**做什么：在任何地方都没找到对 `0x88CE4`、`0x88CE0`、`0x88084`、`0x880A4`、`0x880A8`、`0x820520` 或 `0x82057C` 的写。GSP 只为了链路管理碰 PCIe（`0x88088` 对位 0-1 的读-改-写、带 Gen1/2/3 分支的速度读、Gen4 落进默认路径、`0x8A088`、内部读 `0x88A48`/`0x88A4C`/`0x88A64`、和 `0x82000 | offset` 的动态熔丝块访问）。

> [!NOTE]
> **值得保留的方法注记**
>
> 一次早先天真的 4 字节常量搜索错误地报告 GSP 映像里 "no XVE references"（无 XVE 引用）、因为 RISC-V 经 `lui`/`addi` 动态构建这些地址。一次完整模式扫描是必需的。加密的 GSP 区域仍不可读、所以即使修正的扫描也不穷尽。

---

## 速度能力的寄存器级图

来自 RM 反汇编、带一个注意：工作的 Gen2 结果显示实际情况比这张图暗示的更宽容（置信度：中等）。

| 寄存器 | 角色 | 访问 | 170HX 上观察到 |
|---|---|---|---|
| `0x85080` | 受支持速度源 [23:20]、跳转表索引 | RO、4.1 M 行 RM 反汇编里零写入者 | 从注入点 `0xBADF1100`（毒） |
| `0x85084` | Allowed-Gen 掩码 [3:0]、每次重训练被 GSP-RM 重新派生 | 从可达上下文 RO | `0xBADF1100` |
| `0x88084` | `MAX_LINK_SPEED` [3:0] | PHY 反射、标 R-XVF | 出厂 `0x00456101` |
| `0x8808C` | `SUPPORTED_LINK_SPEED` [7:1] | PHY 反射、标 R-EVF（无写端口） | 被 PROT-wall 挡开主机 |
| `0x880A8` | `TARGET_LINK_SPEED` | RW 但被 SUPPORTED 封顶 | 出厂 `0x00000001` |
| `0x8841C` | `PRIV_MISC_1` CYA Gen2/3 覆盖位 11-16、30、31 | PLM 下 RW | `0x20340500` 到 `0x20342d00` |
| `0x88610` | `VSEC_HIERARCHY`、位 12 门控 PRIV_MISC_1 重新编程 | PLM 下 RW | 活 `0x00001001` |
| `0x8872C` | LTSSM 触发（写 `6`） | PLM 下 RW | 不是一个真实重训练 |
| `0x8C1C0` | `PL_LINK_RATE`、gen 字段 [19:16] | PLM 下 RW | 被 0007 写成 `0x00240036` |
| `0x881C0` | `PPCI.UNK1C0`、[17:16] `LNK_CAP_SPEED`、[21:20] `SYSTEM_MAX_SPEED` | 主机读被挡 | `0xbadf5040`；A100 孪生 `0x8C1C0` 读 `0x00040036` |

速度向量编码：Gen1 = `0x1`、Gen1_2 = `0x3`、Gen1_2_3 = `0x7`、Gen1_2_3_4 = `0xF`。

一个参考 A100 80GB 上的强制代扫描钉住了链路速率实际住在哪、是可用的最干净对照测量：

| 强制代 | `0x88088`（[19:16] 处速度） | `0x880a8`（[3:0] 处目标） | `0x88084` |
|---|---|---|---|
| Gen1 | `0x11010140` | `0x001e0001` | `0x00456104` 或 `0x00457104` |
| Gen2 | `0x11020140` | `0x001f0002` | 不变、半字节总 4 |
| Gen3 | `0x11030140` | `0x001f0003` | 不变 |
| Native | `0x11040140` | `0x001f0004` | 不变 |

---

## 试过并失败的东西

### 寄存器和配置空间攻击

| # | 方法 | 为什么它貌似合理 | 它怎么死的 | 日期 |
|---|---|---|---|---|
| 1 | 带所有速度设置的 `setpci` 写 LnkCap2（配置 `0x2C`） | 它字面上就是列出受支持速度的寄存器 | 被静默丢弃。硬件只读、在 NVIDIA 的 `dev_nv_xve3g_fn0` 头文件里标 `R-EVF`：任何权限级别都无写端口，所以打开一个 PLM 帮不了 | 2026-07-24 |
| 2 | 单独提高 `TARGET_LINK_SPEED`（`0x880A8`）并重训练 | TARGET 真可写 | 链路以 Gen1 重训练；端点在它的 TS1/TS2 ordered sets 里重新宣告 Gen1、被只读 SUPPORTED 字段限定 | 2026-07-24 |
| 3 | 对 `0x88070` / `0x8808C` / `0x88090` 的主机 BAR0 写 | 紧邻能力块 | 被 PROT-wall 挡开主机：读返回 0、写被忽略 | 2026-07-24 |
| 4 | 隔离的高安全 XP3G PHY 速率覆盖 | PLM 打开、覆盖寄存器可写、速率回读 Gen3 能力 `0x00340036` | 链路停在 Gen1。它确实证明一个阳性：`0x10B9` SEC2 CSB 邮箱 gadget 到达 XP3G/PCIe 特权块。后来成为工作的 Gen2 组合的一个*组件* | 2026-07-24 |
| 5 | 高安全 `FEAT_OVR` 写加重训练 | 算力解锁恰好经这条路线工作 | `0x823800` 回读 `0xfffffe8e`（写生效）、`OPT_GEN23` 停 `0x1`、链路停 Gen1、AER = 0。当时的结论：一个 PCIe 覆盖使能在 FEAT_OVR 里被熔断**关**、不像 `SM_SPD` 被熔断**开**。注意[FEAT_OVR 目录](nvlink.md#route-b-a-feat_ovr-style-attack) 在那个块里没列出 PCIe 寄存器，所以把它当探测结果、不是一个已定位寄存器 | 2026-07-24 |
| 6 | 直接写 `OPT_GEN23`（`0x82057C` <- 0） | 明显杠杆 | 从主机、从 HS-ROP、经 Booter 载荷都失败。仍被出货 Gen2 补丁尝试、仍失败、Gen2 反正工作 | 2026-07-23 |
| 7 | 经 Booter 设 `VSEC_DEVICE` 位 0 | 是已发布序列的一部分 | `pre=0x00000800 want=0x00000801`、失败两次带 `rd=0x00000800`。对 "transient window"（瞬态窗口）模型尴尬、它把窗口关闭归咎于 RM 清除一个补丁从未设置的位 | 2026-07-23 |
| 8 | 在 postbl 写派生的 allowed-Gen 掩码 `0x85084` | "GSP writes `0x85084`" 是真的 | `0x85080` 和 `0x85084` 从注入点读 `0xBADF1100`、写被丢弃。GSP 在一个注入点永远达不到的权限写它、而且反正每次重训练都重新派生它 | 2026-07-24 |
| 9 | VFIO/QEMU 下的 BAR0 `0x8872c` 值扫描 | LTSSM 相邻 | `0x6` 稳定、让 LTSSM 停在 Gen1 x4；`0x2` 和 `0xA` 暴露额外 Gen2 行为、但最终楔住 VFIO/QEMU 函数。出货 0007 恰好写 `0x6`、它自己的日志说 "skip mid-boot retrain" | 2026-07-12 |
| 10 | `0x88084` `MAX_LINK_SPEED` 作可写上限 | 一份分析得出结论没有主机可写后备寄存器 | 对一个 scratch 寄存器的一次 HS 写成功、而对整个 XP-PL `LINK_CONFIG` 簇（`0x8C044` / `0x8C048` / `0x8C04C`）的同一个写被拒绝。转发者标记那份分析可能错、但被检查的部分站得住：那个簇与工作补丁用的 `0x8C040`/`0x8C2C0`/`0x8C1C0` 真不同 | 2026-07-12 |
| 11 | `0x8c044`（XP_PL）作链路速率寄存器 | 具名候选 `0x8c044/0x2` | 读 `0xbadf5040`、priv 屏蔽哨兵；探测写测试跳过它。值得注意的是同一个三个寄存器在参考 A100 上*每一*代都读 `0xbadf5040` | 2026-07-20 |

### 固件和签名攻击

| # | 方法 | 它怎么死的 |
|---|---|---|
| 12 | 编辑 VBIOS devinit Gen-strap 字节 | 3 个 devinit 站点上的 5 个字节（通过搜索对 Falcon 寄存器 `0x14118F78`、字节模式 `78 8f 11 14` 的引用找到）。相对 A100 SXM4 的不同字节：命中 #8 `0xBB` 到 `0xE2`、命中 #10 `72 DE` 到 `52 DD`、命中 #11 `97/59` 到 `95/39`。全部五个都在 `csecret(2)` MAC 范围内。**CLOSED** |
| 13 | 重刷一个编辑过的 VBIOS（`nvflash` / CH341A） | Ampere RSA 签名检查拒绝它；卡不会引导 |
| 14 | RAM 打补丁 TOCTOU（在加载和验证之间补丁已签名固件） | 在 Ampere 上关闭：签名验证在 **DMA 进 IMEM 期间**发生，所以没有 load-versus-verify 窗口。泛化到对这个部件的任何固件级攻击 |
| 15 | `csigenc` ACL-`0x13` 溢出（把 HS 机密泄露过 1 位引导 oracle） | 离线死亡。`envydis` 显示 SEC2 booter 安全主体从 `0x101` 到 `0x86FB` 在 `csecret(6)` AES 下是密文、明文桩里零 SCP/crypto 操作码。无可钉 ROP 地址 |
| 16 | 主密钥签名绕过 / 任意 HS Falcon 代码 | 不存在缺陷。已知时序洞只产生**数据寄存器 poke**、不是任意 Falcon 代码、因为主体是 AES 加密且无法签名的。明文在 `0x101` 结束。不存在 HS 可达的 Ampere CVE |
| 17 | 泄露的生产 HULK 证书 | ROM 内 `0xFE504`、`csecret(40)`、`STRICT_ID_MATCH=NO`。被 `RmActivateHulk` fmodel 标志门控、生产硅片上 false；需要证书文件；卡上 FEAT_OVR 写反正不移动 `OPT_GEN23`（见 #5）。大体上无实际意义 |
| 18 | `csecret(6)`/`csecret(2)` 故障注入（EM 或电压毛刺） | 约 $400-2k 设备、数周工作、无保证、而且之后这个部件对 PCIe **仍**会是熔丝绑定的。工具离线验证过、设备从未获取。一个 ChipSHOUTER CW520 被提出、从未尝试 |

### 硬件和平台攻击

| # | 方法 | 它怎么死的 |
|---|---|---|
| 19 | 把 A100 的跳线配置复制到 170HX 上 | 被一个已有 Gen2 x16 工作的测试者试过：**引导时卡不被检测到**。后续回答直白："the straps don't do anything"（跳线什么都不做）、"falcon is driving the rewrites"（falcon 在驱动重写）、"there's no gen3 override register"（没有 gen3 覆盖寄存器）。Strap4（`R999`/`R1000`、靠近 `U808`）被映射为 `PCIE_CFG`。第二位研究者独立发现对照一个活 A100 转储比较跳线档位两天后是一条死路 |
| 20 | 一颗普通 PCIe redriver | redriver 只重新放大；端点仍产生它自己的熔丝封顶 TX 速率。只有**重定时器**、它终止链路并能对每一侧宣告不同速率、能伪造 TS1/TS2 Rate-ID。具名候选：Astera Aries、TI DS160PR810 类。从未尝试 |
| 21 | 驱动内完整移除重扫（"Option A"） | 三个注意：GSP 引导钩子在 `probe()` 内跑，所以那里的 `pci_stop_and_remove_bus_device()` 是它自己上下文的一次 use-after-free；重扫后驱动重新探测、GSP 引导、写跑、它又重扫（需要一个模块全局 once 标志）；活 CUDA 客户端被丢弃。Option B（上游桥重训练）反而出货了 |
| 22 | 设备 ID 欺骗呈现为 A100 | `FUSE_DEVID_SW_OVR_DIS` `0x00820584` = `0x00000001` 在每个被探测的 Ampere 部件上。写 XVE 配置影子 dword0 `0x88000 = 0x208210de` 只改变主机可见 ID、而 `MAGIC_D` 位 25、PPCI_2 SPEED 和被抑制的 `0x88CE4` 都保留 |
| 23 | 刷一个真 A100 80GB VBIOS 恢复 PCIe 4.0 | 测试并失败、2026-07-19 报告："Theyve tested that and it doesnt work. the pcie 4.0 bit at least."（他们测过、它不工作。至少 pcie 4.0 位是。） |
| 24 | VBIOS `CTRL_OPT` / HULK 选项区域作 PCIe 杠杆 | 结构上不可能："CTRL_OPT is remove only, not add"（CTRL_OPT 只移除、不添加） |

### 值得记录的假声称

- 一个宣称到达 **PCIe Gen 4** 的 fork 在 2026-07-19 一小时内被揭穿（"This is BS, didn't work for me at all"）。两位测试者的主机反正都被限制到 Gen3、所以一个 Gen4 结果本不可能被观察到。2026-07-21 撤回。
- **"PCIe Gen 3 is actually working" via AI-driven experimentation**（2026-07-24）。从没贴出测量、寄存器写或链路状态输出。该声称以开玩笑的口吻进来、立即被仍把 Gen3 和 Gen4 当作未解决的讨论跟随。
- 一个广告一张 170HX 在 "PCIe 3.0" 的公开租赁列表被判定为平台方错误报告；`OPT_GEN23` 写失败同日被记录。
- **"Gen 3.0 and 4.0 is a dead end due to fused blockers in the die"** 被频道内反驳："the fuses are signals used by the firmware to control function"（熔丝是固件用来控制功能的信号）、"they're not hard efuses that actually destroy functionality"（它们不是真正摧毁功能的硬 efuse）。反驳更好受支持、因为 Gen2 解锁证明至少一个熔断代限制是固件介导且可击败的。未定论、倾向反驳。

---

## Gen4 影子实验和它的引导循环

一个单独的净室补丁 `0007-pcie-gen4-shadow.patch`（不要和 cmpunlocker `0007-pcie-gen2.patch` 混淆、那是一颗带相同编号的不同补丁）被放弃到一个引导循环里、仍是最有趣的未完成 Gen4 工件。

> [!CAUTION]
> **这个实验会弄砖引导循环、直到模块被移除**
>
> 上游补丁 `0001`-`0006` 每次引导用 4 次 Booter 载荷运行、正常引导。Gen4 影子补丁把它提高到 7-11 次运行、包括熔丝和重训练尝试。**真正的** BooterLoad 随后以 `mailbox0 != 0`（状态 `0xffff`）失败、之后 RM 无限重试 `_kgspBootGspRm`、`wprStart` 每次重试沿帧缓冲下滑（按重试的 WPR 分配）并最终回绕。

一个原因被排除：带 `CMP_PCIE_RETRAIN=0` 循环仍持续、排除了驱动内重训练。两个假设存活、从未被裁决：

- **H-COUNT。** 紧接真实引导之前太多 Booter / priv-sequencer 执行耗尽 sequencer 状态。注意 `kgspExecuteBooterLoad_TU102` 在每次运行**之前**做 `kflcnReset(SEC2)`，所以 SEC2 不累积状态，但 priv sequencer 是没被复位的独立硬件、而 WPR2/PLM 寄存器和 XVE 写也存活。
- **H-WRITE。** 一个特定写在恰好 Booter 用来从 sysmem DMA 它签名的同一条链路上扰动 PCIe 块。头号嫌疑：`0x8C2C0`（LTSSM 配置）然后 `0x8C040`（SPEED）。

二分 harness 已经以编译时开关存在：`CMP_PCIE_ONCE=1`（每个模块生命周期应用一次、因为写持久、所以一个失败的首次循环后跟一个值已应用的干净二次循环）、`CMP_PCIE_ATTEMPTS=1`、和组 `CMP_PCIE_XVE_LTSSM_WRITES`、`CMP_PCIE_VECTOR_SPOOF`、`CMP_PCIE_UNK1C0_WRITE`、`CMP_PCIE_XVE_PHY_WRITES`。规定的二分顺序是先 LTSSM、然后 vector 欺骗、然后 UNK1C0、最后 PHY。结果从未被记录。

---

## 最有希望的剩余路径

按成本排名、最便宜在前。这些没有一个被做过。

### 1. 经 xp3g 表写 `0x00820580 = 0`、然后请求 TLS = 3

成本：一次引导。`FUSE_PCIE_GEN3_DIS` 从没被任何人写过。表机制已在 `0007-pcie-gen2.patch` 里存在；加一个条目并把 `target_gen` 提高是一个几行改动。预期结果、鉴于上面 #6、是一行 `booter FAILED to set` 和 `rd=0x00000001`，但那个负结果值得记录在案。决定性观察是 `LnkCap2` 是否曾到达 `0x0000000E`。

### 2. `FUSE_PCIE_MAGIC_D` 可写吗？读、写 `0x00200000`、回读

成本：五分钟、从未发布。证据真的矛盾。一份分析给位 25 加注 `GEN4_SPEED_DISABLED` 并显式标记寄存器 **"(writable)"**、对比 `GEN23_DIS` "needs no write"。一个独立净室链脚本记录把 `0x00820520 = 0x00200000`（A100 / Drive 参考值）作为一条*工作* Gen2 链的一部分写。但 PCIe 实地手册把 `0x820580` / `0x820520` 列为只读熔丝选项影子、而 `0007` 只读 `0x00820520`。因为 Gen4 不可测试、这从没被操练过。

### 3. 从 SEC2 高安全上下文内读 `0x85080` / `0x85084` / `0x881C0`

成本：一个插桩构建。三个从主机和注入点都读毒。`0x8e1b0` 和 `0x823800` 已被展示从 HS 可达、所以读可行。这是定位实际供给受支持速度向量的跳线层的唯一路径。

### 4. 测试 `0x823830`-`0x82383C` 的第二个特性覆盖组

成本：一次 HS 写-后-回读。从 PL0 读返回 `0xbadf5040`；HS 读返回真实值。没有手动 PLM 覆盖这个组、HS 写-后-回读从未被执行。被显式列在 "writability still unknown / worth testing"（可写性仍未知 / 值得测试）下。

### 5. 在一次强制 Gen3 尝试期间转储 `LnkSta2` 均衡字段

成本：一次带插桩的引导。反假设是 `GEN3_DIS` 可能在引导时被锁存进一个可重写的 PHY/strap 配置寄存器、而非被模拟 PHY 直接消费，那种情况下会存在一个引导后要覆盖的寄存器。提出者赌他们自己的想法输。能裁决它的测量是均衡 Phase 1 是否曾被进入。

### 6. GSP-RM 补丁

截至 2026-07-27 的陈述要求、和没人交付的原因："I haven't seen anybody at all get a working GSP patch."（我从没见过任何人拿到一个工作的 GSP 补丁。）具体起点是上面那两个熔丝读站点（`470.42.01 gsp.bin` 里 `0x5D55834`、`580.105.08 gsp_tu10x.bin` 里 `0x4DD9B00`）。问题是那个消费能否被像 Gen2 覆盖分流 Gen2 路径那样分流。加密 GSP 区域仍不可读、那是常驻障碍。

### 7. 一个带 `[+0x0F] = 0x00` 和 `[+0xC9] = 0x14` 的已签名或以其它方式被接受的闪存

这是唯一能确定 DevInit 五字节编辑**单独**是否会恢复 Gen4 的实验。熔丝参考 gist 断言 "PCIe double-locked: `FUSE_PCIE_GEN23_DIS` = `0x1` (fuse) + devinit (5 bytes). Firmware-only patch insufficient"（PCIe 双锁：熔丝 + devinit。仅固件补丁不足够），但那个结论是从熔丝值的推断、不是一次被尝试的固件补丁的结果。从没人刷过修改过的 DevInit 表、没有签名密钥也没人能。

### 8. 一个线缆级重定时器

被设备和板卡工作门控。某个有部件和板卡制造能力的人需要构建一个伪造 TS1/TS2 Rate-ID 的 interposer。具名候选：Astera Aries、TI DS160PR810 类。什么都没尝试。

### 9. 找一台 Gen4 主机

被硬件阻塞先于被技术阻塞。做 Gen4 的研究者直白陈述："I can't do PCIe Gen 4 because I don't have a computer that supports it"（我不能做 PCIe Gen 4、因为我没有支持它的电脑）、并分开说 "devinit routes are genuinely horrible to try to work on"（devinit 路径真的极其难弄）。

### 低优先级线索

一位研究者把 `Mellanox-ConnectX-5-PCIe-Gen-4-Enablement` 标记为一个类似的 "shipped-downgraded part"（出货降级部件）案例、显式 "not expecting much"（不期望太多）。什么都没尝试。

---

## 记录里的移动目标问题

Gen3 路径在大约 40 小时内四次改变方向、把任何单一引述读作项目立场之前值得知道：

| 时间戳 | 立场 |
|---|---|
| 2026-07-26 06:38 | "a devinit route might be the only way"（一条 devinit 路径可能是唯一方法） |
| 2026-07-26 14:25 | "My current fix doesn't use devinit, and it's a dead end"（我当前的修复不用 devinit、而且它是条死路） |
| 2026-07-26 14:42 | "We need to use devinit"（我们需要用 devinit） |
| 2026-07-27 22:57 | "Gen 3 doesn't work whatsoever, it's going to require a GSP patch" / "I haven't seen anybody at all get a working GSP patch" |

最后这个是截至 2026-07-28 的状态。

更早的 "four-layer wall"（四层墙）实地手册（日期 2026-07-24）得出结论全部四层（运行时寄存器写、寄存器语义、持久固件、硅片熔丝）都被经验关闭、在两个表面验证：一次 4032 运行离线固件 fuzz 扫描（从 66 个函数抽取的 126 个函数-寄存器对、每个扫过 32 个单一位值）和硅片上直接写探测。它自己的第 6 节含它为什么对 Gen2 错的原因：*"The full community Gen2 sequence ... as a single combined write was not run: every component is individually proven inert, so it is a low-odds combination."*（完整的社区 Gen2 序列……作为单次组合写没被跑过：每个组件被单独证明惰性、所以它是一个低概率组合。）那个低概率组合工作了。**那个结论的 Gen3 一半仍站得住。**

---

## 如果你在测试一个 Gen3 声称

> [!WARNING]
> **用 LnkSta 验证、绝不用 LnkCap**
>
> `LnkCap` 是宣告的能力、链路仍以 Gen1 训练时可以读一个更高代。那个陷阱是大多数站不住脚的 "it works"（能工作）声称的陈述来源。2026-07-24 的 Gen3 宣告结果恰好是这种情况。

```bash
# 三个诚实的字段
sudo lspci -vvs <bdf> | grep -E 'LnkCap:|LnkCap2:|LnkSta:'
cat /sys/bus/pci/devices/<bdf>/current_link_speed
nvidia-smi --query-gpu=pcie.link.gen.gpucurrent --format=csv
```

这张卡上两个已知假信号：

- 在 Gen2 训练过的 170HX 上、`/sys/.../max_link_speed` 仍读 `2.5 GT/s`、而 `current_link_speed` 读 `5.0 GT/s`。从配置空间诊断、不要从 sysfs 属性。
- `nvidia-smi` 自 2023 年起在一张出厂卡上报告 `PCIe Generation Max : 2`、而 `Device Current` 和 `Device Max` 都读 `1`、`LnkCap2` 只列 2.5 GT/s。只作指纹有用。

ASPM 在其它平台上是真实的假阴性陷阱（许多平台把链路空降到 Gen1），但 170HX 自己在它的 `LnkCap` 里宣告 `ASPM not supported`，所以它在这里是一个首选诊断、而非一个可能原因。

---

## 实测值

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS` `0x0082057c` | `0x00000001` | 两个 170HX SKU、两个物理单元、各读两次；13 个对比部件上 `0x00000000` | 高 |
| `FUSE_PCIE_GEN3_DIS` `0x00820580` | `0x00000001` | 相同 | 高 |
| `FUSE_PCIE_MAGIC_D` `0x00820520` | `0x16680000`（位 25 置位） | 170HX；A100 家族 `0x00200000` | 高 |
| `OPT_PCIE_LANE_DISABLE` `0x00820394` | `0x00000000` | 170HX | 高 |
| `CTRL_OPT_PCIE_LANE` `0x0082082c` | `0x00000000` | 170HX | 高 |
| `STATUS_OPT_PCIE_LANE` `0x00820c2c` | `0x00000000` | 170HX | 高 |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000` | 170HX 和全部数据中心 GA100；消费级部件上 `0x00000001` | 高 |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | 全部卡 | 高 |
| `0x00820148`（DevInit MAGIC_D 门） | `0x00000000` | OTP 备用位、永不能被软件设置 | 高 |
| Gen2 dmesg 里的 `OPT=` 三元组 | `00000001/00000001/16680000` | 一次完整 Gen2 运行后 GEN23 / GEN3 / MAGIC | 高 |
| PLM 打开后的 XP3G 速率 | `0x00340036`、`ovr0 = 0x4` | 写生效、链路停 Gen1（`lnksta=0x10410040`、速度 1） | 高 |
| `0x85080` / `0x85084` | `0xBADF1100`（毒） | 从注入点读 | 高 |
| `0x881C0` 主机读 | `0xbadf5040` | priv 屏蔽模式 | 高 |
| A100 上的 `0x8C1C0` | `0x00040036` | PPCI_2 UNK1C0 参考 | 高 |
| `A100 0x8C044` / `0x8C048` / `0x8C04C` | 每一代 `0xbadf5040` | 即使在参考卡上也屏蔽 | 高 |
| CMP `0x88CE4` | `0x0000003F` | 对比 A100 `0x00000014` | 高 |
| CMP `0x88CE0` 低 6 位 | `0x02` | 对比 A100 `0x06` | 高 |
| CMP `0x8C040` `PPCI_2.CONFIG_LINK` | `0x800C4C00`（SPEED = 3） | BAR0 mmap、无驱动；A100 `0x80004C00`（SPEED = 0） | 高 |
| CMP `0x8C2C0` | `0x068731B7` | 对比 A100 `0x060711B2` | 高 |
| CMP `0x880A8` | `0x00000001` | 对比 A100 `0x001F0004` | 高 |
| CMP `0x88084` / `0x880A4` | `0x00456101` / `0x00000002` | 对比 A100 `0x00457104` / `0x0180001E` | 高 |
| `0x118F78` / `0x132B70` | CMP 和 A100 上都是 `0` / `0` | **BAR0 mmap、无驱动加载**（同一个地址在驱动起来时主机读返回 `0xbadf1100`）；相同值不能编码一个 SKU 限制 | 高 |
| `0x132B30` / `0x132B6C` / `0x132B50` | 两者上 `0x00000400` / `0x08000020` / `0x03780000` | 空转、无驱动 | 高 |
| LTSSM 超时 `0x8D1A0` / `0x8D1A4` | `0x1B1F2327` / `0x0B0F1317` | CMP 和 A100 相同 | 高 |
| 每次引导的 Booter 载荷运行 | 4（补丁 0001-0006、正常引导）对比 7-11（Gen4 实验、引导循环） | GSP 引导 | 高 |
| Booter 载荷运行状态 | 每次运行 `0xffff`、即使写落地 | 寄存器回读是唯一有效判决 | 高 |
| SEC2_DEBUG dmesg 行数 | 29（归档单卡捕获）、34（Gen1 构建）、80（Gen2 构建）、134（归档双卡 Gen2 分支 610.43.03 日志）、152（两台双卡 Gen2 机架上的 `pcielink.sh`） | **不是一个可靠的跨构建指纹**；不要把不匹配读成一次失败的安装 | 高 |
| Gen3 宣告结果 | `LnkCap Speed 8GT/s`、`LnkCtl2 Target 8GT/s`、`LnkSta Speed 2.5GT/s` | 2026-07-24 | 高 |

---

## 参见

- [PCIe Gen2](../unlock/pcie-gen2.md) 看确实工作的机制
- [PCIe 子系统](../hardware/pcie-subsystem.md) 看寄存器块图
- [熔丝与 OTP](../hardware/fuses-and-otp.md) 看完整熔丝群组
- [VBIOS](../hardware/vbios.md) 看 DevInit 映像布局和签名
- [物理改装](../operations/physical-mods.md) 看只改位宽的电容改装
- [死路](../history/dead-ends.md) 和[未解问题](open-questions.md)
- [状态板](status-board.md)
