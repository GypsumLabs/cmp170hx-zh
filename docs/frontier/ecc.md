# ECC：熔断关闭、且 `ecc` 分支是空的

**本页覆盖内容。** CMP 170HX 上纠错内存的状态：实际已知什么（很少、而且几乎全部是负面）、被尝试过的那一次寄存器级攻击以及它为什么在两个独立层上失败、为什么名叫 `ecc` 的分支根本不含 ECC 代码、什么从没被测量过、以及要让这个问题变得可回答必须发生什么。

**头条：ECC 关着、没有已知杠杆、也没有遥测。** 卡报告无 ECC 状态、无可纠正错误计数器、也无易失/聚合 ECC 页。关于这块硬件的每个容量和稳定性声称、包括[64 GB 和 40 GB 解锁](../unlock/memory-geometry.md)、都是在非 ECC 内存上做出的。

> [!NOTE]
> **未解问题**
>
> ECC 在 PCIe Gen 2 之后立即被命名为候选目标、然后什么都没发生。除了在对比群组里读 `OPT_ECC_EN` 和转储四个 `FEATURE_OVERRIDE` ECC 字、**什么都没被尝试过。** 那个先导问题、HBM 堆叠是否携带 ECC 配置、有一个部分答案而非没有：下面的 A100 容量差读作 ECC 是同一批堆叠的一块切片、不是独立存储。那是在频道内陈述的、从没对照数据手册核查。

---

## 状态一览

| 声称 | 状态 | 依据 |
|---|---|---|
| ECC 在 CMP 170HX 上被禁用 | 已确认 | 每个已发布规格表和每个卡报告 |
| 禁用是熔丝/POR 锁存、不是运行时设置 | 已确认 | `0x00823814` 读出是 POR/熔丝锁存；运行时覆盖不移动它 |
| 一个 `FEAT_OVR` 式 ECC 解锁工作 | **被反驳** | 两个专用尝试脚本、两个独立失败层 |
| `ecc` 分支实现 ECC | **假的** | 单一提交、"Fixed dual geometry support"、无 ECC 代码 |
| ECC 在 HBM 堆叠里实现 | **部分回答** | 对熔丝表的一次一手读数：A100 上每堆叠的每-FBPA `CSTATUS_RAMAMOUNT` 读 `0x7ff` / `0xfff` 对消费级的 `0x800` / `0x1000`、即 ECC 是同一批 HBM2 堆叠内的带内容量预留。从没对照数据手册确认 |
| `OPT_ECC_EN`（`0x00820228`）在 170HX 上读 `0x00000000` | 已确认 | 两张物理 170HX 单元；每个 A100 级对比部件上 `0x00000001` |

---

## 寄存器块

GA100 上的 ECC 由特性覆盖块里 `0x00823800`-`0x0082382C` 的五个寄存器描述、同一个携带工作[算力解锁](../unlock/compute-throttle.md) 的块。那种相邻性正是 ECC 解锁看起来可达的原因。

| 寄存器 | 地址 | 170HX | A100 80 GB | 备注 |
|---|---|---|---|---|
| `FEAT_OVR_ECC_PLM` | `0x00823800` | `0xffffff8f` 冷 | 未捕获 | 门控三个覆盖字的权限级别掩码。可被 HS-ROP 打开、打开后惰性 |
| `FEAT_OVR_ECC` | `0x0082380C` | `0x00888888` | `0x00000101` | 每单元 ECC：SM_LRF / L1 / LTC / DRAM / CBU |
| `FEAT_OVR_ECC_1` | `0x00823810` | `0x002AAAAA` | `0x00100105` | icache / FECS / GPCCS / PMU / HUBMMU |
| `FEAT_OVR_ECC_2` | `0x0082382C` | `0x0000000A` | 未捕获 | 出厂和解锁读相同 |
| `FEAT_READOUT_0` | `0x00823814` | `0x00000233` | `0xef8ff100` | **ECC 使能读出。POR/熔丝锁存。** 出厂和解锁读相同 |

对这些值的置信度：中等。它们来自 PLM 范围扫描和解锁后探测、而非一次重复的多卡扫描、A100 对比列是一张单卡。

> [!WARNING]
> **不要把 `0x00823800` 与 `0x00823804` 混淆**
>
> `FEAT_OVR_ECC_PLM` at `0x00823800` 和 `FEAT_OVR_PLM` at `0x00823804` 是不同的寄存器。出货解锁打开 `0x00823804`（出厂 `0xffffff8f`、打开到 `0xffffffff`）以到达 SS0 和 SS1。`0x00823800` 出厂也读 `0xffffff8f`、这让两者在转储里容易搞混。Gen2 家族分支也打开 `0x00823800`、但只作为 PCIe 序列里十八个 PLM 打开之一、不为任何 ECC 目的。

---

## 那一次尝试、和它的两个失败层

**假设。** 打开 `FEAT_OVR_ECC_PLM`（`0x823800`）、它门控 `FEAT_OVR_ECC`（`0x82380C`）、`FEAT_OVR_ECC_1`（`0x823810`）和 `FEAT_OVR_ECC_2`（`0x82382C`）、会允许 ECC 在运行时被启用、恰如 `FEAT_OVR_PLM` 加 SS0/SS1 击败算力节流。

**为什么它貌似合理。** PLM 在 170HX 上冷读 `0xffffff8f`、意思是它是一个正常的 L3 门控掩码而非什么奇异的东西；HS-ROP 真的能打开它；而主覆盖灭杀熔丝 `FUSE_FEAT_OVR_DIS` at `0x008203F0` 在每张被探测的卡上读 `0x00000000`、所以覆盖作为一个类没有被永久锁定。那个最后事实正是整个算力和显存解锁之所以能行的原因。

**发生了什么。** 多个专用尝试、`fire_ecc_driverless_test.sh` 和 `fire_ecc_unlock.sh`、全部失败。两个独立层在 `ecc-unlock-dead.md` 里于 2026-07-16 被识别并写清：

1. **覆盖不是常开的。** `FEAT_OVR_ECC` 不在常开（AON）岛里，所以任何写给它覆盖在功能级复位时回退。这是让显存几何布局不持久的同一个不对称：SS0、SS1 和 `0x00823804` 挺过 FLR、而几何和 ECC 路径里其它一切不。见[权限级别掩码](../unlock/privilege-level-masks.md)。
2. **读出是 POR 锁存的、那是致命的。** `0x00823814` 在上电时从熔丝锁存，所以**没有运行时覆盖会改变有效 ECC 状态**。即使一个持久覆盖也是在写给芯片其余部分已经停止咨询的东西。

层 2 是关闭路径的那个。它不是 "we could not make the write stick"（我们不能让写粘住）失败；它是 "the write is not the thing that decides"（写不是做决定的东西）失败。

---

## `ecc` 分支不含 ECC 代码

分支名叫 `ecc`。它有单一提交、`bb4d669 Fixed dual geometry support`。它对 `master` 的完整 diff：

- 被删除的拉取请求模板，
- `build.sh`、`install.sh` 和 `remove.sh` 里的注释块，
- `constants.yaml` 里的 `# 64 GiB` 和 `# 40 GiB` 标注，
- 一行 README 依赖行，
- 一个新 `requirements.txt` 含 `pyyaml>=5.1` 和 `pytest>=7.0`。

**树里不存在 ECC 寄存器、ECC 使能路径、也没有 ECC 测试。** 名字记录的是一个意图、不是工作。

两条相关更正：

为完整：`PG199` 分支快照与 `ecc` 快照逐字节相同、除了 `_COMMITS.txt`（`ecc` 列 `bb4d669`；`PG199` 的是零字节）。它们的 `_DIFF_vs_master.patch` 文件逐字节相同。两者都是占位符。分支目录见[驱动补丁](../unlock/driver-patches.md)。

---

## 什么从没被测量过

这是本页诚实的部分、它比有结果的部分长。

- **对 A100 差的一次解码。** 上面表背后的单卡 A100 转储覆盖五个 ECC 相关字中的三个（`0x0082380C`、`0x00823810` 和 `0x00823814`）、不携带 `0x00823800` 或 `0x0082382C`。一个更宽的并排确实存在：15 卡熔丝参考表给两张 170HX 单元对 A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G 和 Drive A100 的整个 `0x00823800`-`0x0082382C` 块、全部读 `FUSE_ECC_EN` = `1`。从没被生产的是那个差的一次字段级解码、而两份独立的 A100 80 GB 转储彼此不一致（`0x0082380C` `0x00000101` 对比 `0x00110111`；`0x00823810` `0x00100105` 对比 `0x00104104`），所以 A100 侧也没定论。
- **ECC 是否在 HBM 堆叠自己里面实现。** 如果它是一个显存厂商 QA 和分级属性、而非一个固件开关、就没什么可解锁。语料库没定论这个、但确实含一个实质读数："On GA100 cards, ECC is a feature of the HBM2 stack. On the 170HX, ECC is fused off can likely not be enabled"（GA100 卡上、ECC 是 HBM2 堆叠的一个特性。170HX 上、ECC 熔断关闭很可能无法被启用）、被 15 卡熔丝表里的每-FBPA `CSTATUS_RAMAMOUNT` 差支持、那里 A100 部件为 8 GB 和 16 GB 堆叠读 `0x07ff` 和 `0x0fff` 对消费级卡上的 `0x0800` 和 `0x1000`。那个模式读作 ECC 预留同一批堆叠可寻址范围的一部分、而非活在额外专用存储里、这也是杀掉 "a whole stack is reserved for ECC"（整堆被 ECC 预留）理论的东西。它是一个参与者对寄存器值的推断、背后没有数据手册、预留的精确比例从没被同意。注意 HBM 密度模式寄存器 `FBPA_MRS_8`（`0x009A0320`）在全部 15 张卡上读相同的 `0x00200000`、包括一张 10 GB CMP、一张 40 GB A100 和一张 80 GB A100、所以堆叠没被告知它们比实际小、但那对 ECC 配置什么都不说。
- **ECC 在解锁几何布局下是否甚至可取。** 解锁卡上不存在错误率的前后数据。

---

## 不是证据的起源故事

熔丝证据在缺陷读数上倾斜、至少显存侧是：在一块 10 GB 卡上、`FBP_DEFECTIVE`（`0x8205CC`）和 `FBP_DISABLE`（`0x820364`）都读 `0x840`、即禁用-但-非-有缺陷集为空、卡在那几个分区上真死了。一份社区转储显示一个非空差（`FBP_DISABLE` = `0x852` 对 `FBP_DEFECTIVE` = `0x840`）、所以按卡变化是真实的。

---

## 无 ECC 运行的实际后果

无 ECC 意味着无可纠正错误计数器、无不可纠正错误报告、无行重映射遥测、也无 `nvidia-smi` ECC 页可在工作负载出错时咨询。语料库记录的实际效果：

- **诊断更难。** 没有 ECC 计数器、确立一个显存配置健全的唯一方式是一次写/回读别名（"fold"）测试、而非报告的大小。这条规则在一次报告 79.4 GiB 在 40 GiB 之上折叠、和一次报告 4 GiB 被证明是一个工具 bug 后被采纳。它直接适用于[80 GB 尝试](80gb.md)。
- **行重映射。** `FEAT_OVR_ROW_REMAP` at `0x00823824` 在两张 170HX 单元上读 `0x00000000`（置信度：高；在 A100 SXM4 40G、A100 PCIe 80G、A10 和 Drive A100 上也 `0`、对比 A100 PCIe 40G、A5000、A6000 和 RTX 30 上 `0x00000001`）。行重映射器是惰性的。一个中等置信度来源报告出厂 `0x00000001`；它被压倒。它的候选 PLM `0x00823b00` 被写测试并记录 FLR 后 `PLM=0xffffffff(AON=YES)`、把它放进 `0x823804` 和 `0x823800` 旁的持久类。没人追过行重映射器在一张无 ECC 卡上做什么。
- **市场挂牌。** 无 ECC 是否阻塞租赁市场挂牌未解决。给卡不可挂牌的理由包括无 ECC、错 PCI ID 和差带宽。反方是 2080 Ti 22 GB mods 和消费级 30/40/50 系列卡无 ECC 且已挂牌。从技术优点、提供的立场是 "neural nets are largely very robust against bit flips and it's still going to be a rare occurrence"（神经网络大体上对位翻转非常稳健、它仍会是一个罕见事件）；一位拥有者报告一颗带整行坏内存的 A100 处理 LLM 推理正常、在图形里却严重故障。一个市场说它没有为启用 CMP 卡设时间线；其它平台确实挂牌了。什么能定论它：一个市场陈述它实际的阻塞标准。

---

## 什么会推进这个

按最可处理的排前。全部未开始。

1. **解码已存在的 `0x00823800`-`0x0082382C` 差。** 15 卡熔丝参考表已持有两张 170HX 单元和 A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G 和 Drive A100 的整个块；缺的是把那些 dword 映射到字段。做那个也会关系到为什么 `FEATURE_OVERRIDE_QUADRO`（`0x00823808`）跨全部三个已知转储不同（出厂 170HX `0x00100183`、解锁 170HX `0x00000081`、A100 80 GB `0x01000282`）的开放问题。
2. **确立 HBM 堆叠是否携带 ECC 配置。** IEEE 1500 HBM 调试桥在这张卡上是活的（`I1500_INSTR` `0x009a3cb4`、`MODE` `0x009a3cb8`、`DATA` `0x009a3cbc`、`SHADOW_WIR` `0x009a3cc0`、`SHADOW_WDR` `0x009a3cc4`、`STATUS` `0x009a3cc8`）而且是到达 HBM 堆叠身份的唯一工作路径、因为 `FBPA_VEND_ID_C0`/`C1`（`0x009A0838`/`0x009A083C`）在全部 15 张卡上读 `0x00000000`。没人把 `SHADOW_WDR` 内容解码成厂商和密度、更别说一个 ECC 能力。建议的下一步是移入标准 IEEE 1500 `DEVICE_ID` WIR 操作码、而非读取留下锁存的任何指令。
3. **找一个不是 POR 锁存的 `0x00823814` 消费者。** 这是唯一能复活寄存器攻击的路径、而且没有候选被命名。

> [!CAUTION]
> **不要把一张解锁卡当 ECC 保护的**
>
> 本页没有任何东西描述一条工作的 ECC 路径。一张解锁的 170HX 跑 40 GB 或 64 GB 是跑在工厂从没验证过的几何布局上的无保护 HBM。对静默位翻转不可接受的工作负载、这不是正确的硬件。

---

## 实测值

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| `FEAT_OVR_ECC_PLM` `0x00823800` | 冷 `0xffffff8f` | 170HX；可被 HS-ROP 打开但惰性 | 高 |
| `FEATURE_OVERRIDE_ECC` `0x0082380C` | `0x00888888`（170HX）/ `0x00000101`（A100 80 GB） | 每单元 ECC：SM_LRF、L1、LTC、DRAM、CBU | 中等 |
| `FEATURE_OVERRIDE_ECC_1` `0x00823810` | `0x002AAAAA`（170HX）/ `0x00100105`（A100 80 GB） | icache、FECS、GPCCS、PMU、HUBMMU | 中等 |
| `FEATURE_OVERRIDE_ECC_2` `0x0082382C` | `0x0000000A` | 170HX、出厂和解锁 | 中等 |
| `FEAT_READOUT_0` `0x00823814` | `0x00000233`（170HX）/ `0xef8ff100`（A100 80 GB） | 出厂和解锁相同；POR/熔丝锁存 | 中等 |
| `FUSE_FEAT_OVR_DIS` `0x008203F0` | `0x00000000` | 全部卡；主覆盖灭杀**没**被烧断 | 高 |
| `OPT_ECC_EN` `0x00820228` | 两张 170HX 单元上 `0x00000000`；A100 SXM4 40G、A100 PCIe 40G/80G、A10、A5000、A6000 和 Drive A100 上 `0x00000001` | 两张物理 170HX 单元、六份独立探测报告 | 高 |
| `FEAT_OVR_ROW_REMAP` `0x00823824` | 两张 170HX 单元上 `0x00000000` | 在 A100 SXM4 40G、A100 PCIe 80G、A10 和 Drive A100 上也 `0`；A100 PCIe 40G、A5000、A6000 和 RTX 30 上 `0x00000001` | 高 |
| FLR 后 `0x00823b00`（行重映射器 PLM 候选） | `0xffffffff`、AON = YES | in-HS 几何布局扫描；没让几何布局持久 | 高 |
| `FBPA_MRS_8` `0x009A0320`（MR8 密度） | `0x00200000` | 全部 15 张卡包括 10 GB CMP、A100 40 GB、A100 80 GB | 高 |
| `FBPA_VEND_ID_C0` / `C1` `0x009A0838` / `0x083C` | `0x00000000` | 全部 15 张卡；身份必须改从 IEEE 1500 来 | 高 |
| 出货 `master` 里的 ECC 代码 | 无 | 全树读 | 高 |
| `ecc` 分支里的 ECC 代码 | 无 | 单一提交、"Fixed dual geometry support" | 高 |

---

## 参见

- [显存子系统](../hardware/memory-subsystem.md) 看 HBM 组织和地板清扫
- [显存几何布局解锁](../unlock/memory-geometry.md) 看确实工作的
- [算力节流](../unlock/compute-throttle.md) 看成功的 `FEAT_OVR` 路径
- [权限级别掩码](../unlock/privilege-level-masks.md) 看 AON 对非-AON 分裂
- [80 GB 尝试](80gb.md) 看最接近 ECC 问题的显存压力数据
- [熔丝与 OTP](../hardware/fuses-and-otp.md)、[状态板](status-board.md)、[未解问题](open-questions.md)
