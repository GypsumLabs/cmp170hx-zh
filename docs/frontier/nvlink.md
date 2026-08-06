# NVLink：熔断关闭、未找到杠杆

**本页覆盖内容。** CMP 170HX 上 NVLink 的完整状况：证明它是在一次性可编程硅片中禁用、而非在软件层禁用的熔丝读数；所有被探测过的内容；每一条被提出的覆盖路径及其关闭原因；物理连接器和桥接器的现状；以及真正能推进这个问题的简短实验清单。

**头条：CMP 170HX 上的 NVLink 不工作，对语料库中的任何人都从未工作过，也从未有过寄存器级的解锁尝试。** 它是被 OTP 熔丝禁用的，而不是被软件。cmpunlocker（出货 `master`，或 12 个未发布分支快照中的任意一个）里没有一行代码碰过 NVLink。NVLink 在整套分支中的全部存在，只是两个 README 特性表里的一个词——`Planned`。

> [!NOTE]
> **未解问题**
>
> 这是该领域价值最高的未知，桌上没有任何可操作的东西。两条覆盖路径都已关闭：`CTRL_OPT` 因 `FUSE_EN_SW_OVERRIDE` = `0x0` 而关闭，`FEAT_OVR` 路径则因该块中没有任何 NVLink 寄存器而关闭。正如 2026-07-20 的一份总结所说："Still unsolved rn, a bit harder as there's no fuse mask."（现在仍未解决，因为没有熔丝掩码而更难。）

**这个能力本该是什么。** NVLink 的行为类似 MMIO：链路远端的内存可被映射进本地 GPU 的地址空间，由 CUDA 内核或复制引擎驱动。此说来自利用的原始作者，置信度为中等。它从未在 170HX 上演示过，因为从来没有任何链路起来过。正是这种直接可寻址性，才让跨桥卡的内存池有了意义。

---

## 硅片说什么

三个读数定义了现状，它们跨两个 SKU 的至少五次独立回读、外加一个 15 卡 Ampere 参考群组，彼此一致。

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | `0x00820684` | `0x00000007` | `[2:0]` 禁用字段的三个位全部置位 |
| `STATUS_OPT_NVLINK`（只读镜像） | `0x00820DB8` | `0x00000007` | 芯片其余部分看到的有效状态 |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246C` | `0x0000000c` | 晶片缩放到 12 条链路、恰好像每颗 A100 |

接下来是三个表明硅片健康的读数：

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `FUSE_NVLINK_DEFECTIVE` | `0x0082068C` | `0x00000000` | 不是一次产量修复。一项调查报告它 15 卡群组里每张返回值的卡上都是 `0`；A16 列读 `BAR0` 占位符、ES 列空白 |
| `FUSE_NVLINK_DIS_CP`（禁用关键路径） | `0x00820688` | `0x00000000` | 没在关键路径级被禁用 |
| `FUSE_NVLIPT_RST_DIS` | `0x00821100` | `0x00000000` | NVLink IP 复位条件没被禁用 |

再下面四个涉及覆盖机制，其中最后两个表明它已关闭：

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `CTRL_OPT_NVLINK`（有效、每链路位 15:0） | `0x008209B8` | `0x00000000` | 没有 CTRL 覆盖被设置；禁用经 STATUS 路径到达 |
| `CTRL_OPT_PERLINK`（位 11:0） | `0x00820820` | `0x00000000` | 相同 |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | `0x00000000` | 整个 `CTRL_OPT` 覆盖机制被熔丝禁用 |
| `FUSE_DIS_SW_OVR` | `0x00820084` | `0x00000001` | 从另一个方向确认上面 |

语料库得出的结论是：**这是刻意的产品分区，而非报废分级。** 链路在物理上完整，晶片报告 12 条，没有一条被标记为有缺陷，禁用来自一颗熔丝。

### 它不是挖矿 SKU 专属限制

Drive A100 32 GB（PG199、`GA100-550F-A1`、`FUSE_PCIE_DEVIDA` = `0x000020bb`、`FUSE_PCIE_DEVIDB` = `0x000020fb`）在两张物理 PG199 板上测得完全相同的 `FUSE_NVLINK_DIS` = `0x00000007` 和 `STATUS_OPT_NVLINK` = `0x00000007`。三个常规 A100 SKU 全部读 `0x00000000`。任何把 NVLink 熔丝当成加密货币挖矿专属惩罚的理论，都必须解释得通 Drive 部件。

### 写安全按架构分裂、不按 SKU

`0x00820704` 处的 `OPT_SECURE_NVLINK_MASK_WR_SECURE` 在每个 GA100 部件上都读 `0x00000005`（两张 170HX 单元、全部三个 A100 SKU、Drive A100），在每个 GA10x 部件上读 `0x00000085`。170HX 相对普通 A100 并未被特别锁定。

---

## 代码说什么

在出货 `master` 树中，对 `nvlink` 及每个 NVLink 寄存器地址的 grep 均无结果。`common/constants.yaml`、`driver/build.sh`、`driver/VERSION`、`install.sh`、`remove.sh`、`README.md`，乃至六个补丁（`0001-sec2-postbl-plm-ss-cfg.patch` 到 `0006-persistent-sw-state.patch`）中都找不到。`constants.yaml` 只声明了两个驱动版本、设备 ID `20c2`/`2082`、算力值 `ss0: 0x88888888` / `ss1: 0x00000008`，以及两个显存档位。

未发布的分支同样如此。在全部十二个分支（`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`）中，NVLink 恰好出现一次，且只是表中的一个数据行：

```markdown
| PCIe Gen2 x4 | Platform-dependent (no separate Root-port patch) |
| ECC | Planned |
| NVLink | Planned |
```

这个行集只存在于 `housekeeping` 和 `memory` 分支的 README 里。任何地方都没有 NVLink 逻辑。

---

## 两个覆盖路径、以及为什么两者都关闭

### 路径 A：`CTRL_OPT_NVLINK`

这是整个语料库中被引用最多的 "next step"（下一步），**却从没人试过那次写**。它读 `0x00000000`，被文档化为*有效的*每链路使能/禁用字段，并被描述为可写。它看起来就像那个杠杆。

它被一个强先验关死，而不是被一次实际执行的实验：

- `FUSE_EN_SW_OVERRIDE` 位于 `0x00820040` = `0x00000000`，在 170HX 及所有数据中心 GA100 部件上如此，与之相对，所有消费级和工程样品部件上为 `0x00000001`。`CTRL_OPT` 覆盖机制本身在熔丝级被禁用。
- `FUSE_DIS_SW_OVR` 位于 `0x00820084` = `0x00000001`，在所有卡上如此。
- 在未签名 FwSec VBIOS 尾部（`0x43A00`-`0x47700`，即 MAC 验证范围外的 15,616 字节）偏移量 `0x47341` 处找到的 25 条目 `NV_FUSE_CTRL_OPT_*` 表，在 13 块被探测的 GA100 卡上读全零，在此处是惰性的。

任何经 `CTRL_OPT_NVLINK` 路由的方案，都必须先击破 `FUSE_EN_SW_OVERRIDE`，而这个机制并不存在。

### 路径 B：`FEAT_OVR` 式攻击

它有吸引力，因为出货的算力解锁恰好位于这个寄存器块，也因为在所有卡上，主覆盖灭杀 `FUSE_FEAT_OVR_DIS` 位于 `0x008203F0`，读 `0x00000000`（即**未**被烧断）。当时的推理是：如果算力节流能在这里被覆盖，也许 NVLink 也可以。

它被直接排除，因为块里没有 NVLink 寄存器。`0x00823800`-`0x0082382C` 的完整清单：

| 地址 | 名称 |
|---|---|
| `0x00823800` | `FEAT_OVR_ECC_PLM` |
| `0x00823804` | `FEAT_OVR_PLM` |
| `0x00823808` | `FEAT_OVR_QUADRO` |
| `0x0082380C` | `FEAT_OVR_ECC` |
| `0x00823810` | `FEAT_OVR_ECC_1` |
| `0x00823814` | `FEAT_READOUT_0` |
| `0x00823818` | `FEAT_READOUT_1` |
| `0x0082381C` | `FEAT_OVR_SM_SPD` |
| `0x00823820` | `FEAT_OVR_SM_SPD_1` |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` |
| `0x00823828` | `FEAT_READOUT_2` |
| `0x0082382C` | `FEAT_OVR_ECC_2` |

这十二个条目涵盖 ECC、Quadro 分类、SM 速度、行重映射和读出，没有可写的东西。对同一个块的 PCIe 尝试是一个有用的对照，它更像一个探测结果而非另一个寄存器：一次对 `0x00823800` 的高安全写回读 `0xfffffe8e`，说明写已生效，但 `OPT_GEN23`（`0x82057C`）仍停在 `0x1`，链路也停在 Gen1。那个结果当时被解读为"PCIe 覆盖使能被熔断成**关**"，尽管上面的清单里并没有 PCIe 条目。`0x0082381C` 处的 `SM_SPD` 是真实条目，且被熔断成**开**——这正是[算力解锁](../unlock/compute-throttle.md) 能走这条路、而[PCIe 速度解锁](pcie-gen3-gen4.md) 走不通的原因。

### DevInit 角度

DevInit 确实会读这颗熔丝。CMP DevInit 反汇编中 `0x1482xxxx`（MMIO `0x82xxxx`）访问的完整清单包含 `0x820684`，连同 `0x820C14`/`0x820D38`（FBIO/FBP 地板清扫）、`0x82380C`/`0x823814`、`0x820520`（`MAGIC_D`）和 `0x820148`。任何源码中都没有东西写它，没有命名任何有效覆盖，**也没人追踪过该值被读出后的去向**（置信度：中等；依据是访问清单，而非完整迹线）。

---

## 死路

这里的每一条，都是有人认真追过的真实、合理的想法。

| # | 想法 | 为什么它貌似合理 | 它怎么死的 |
|---|---|---|---|
| 1 | "NVLink 已经显示在引导日志里、所以我们只需要一块桥" | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` 确实每次引导出现 | 那行由 `nvidia-nvlink.ko` 软件核心库在 `nvlink_linux.c:344` 发出、宣布它加载了。记录在 `DBG_INFO`、基本任何 GPU 的每次驱动加载、在早期模块加载期间、GPU/GSP 拉起之前。`236` 是 `alloc_chrdev_region` 动态分配的字符设备主号、每次引导可能不同。一次记录的 `nvidia-smi nvlink` 运行返回 "Device does not have or support Nvlink." |
| 2 | "HULK" 加密阻塞器 | 它是唯一已发布的解释、在一个项目相邻 gitbook 上、带着权威口吻 | 网站维护者于 2026-07-20 撇清（"This hasn't been updated in some time, don't rely on that"）、页面自己的作者也叫它过时。任何熔丝读数、VBIOS 转储或 DevInit 反汇编里没有任何东西佐证一个门控 NVLink 的加密方案 |
| 3 | "`FUSE_NVLINK_PHYS_DMG = 0x1` 意味着链路被标记损坏" | 寄存器名是 `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE`；一个置位的损坏标志会是一扇单行道门 | 在全部十四张被探测的 Ampere 卡上读 `0x1`、包括健康 A100 |
| 4 | "NVLink 是软件锁的" | 170HX 的几个其它限制确实在固件侧 | 禁用从 OTP 熔丝 `0x00820684` 出来、镜像进一个只读状态寄存器。记录它、因为它在 2026-07-27、语料库最后一天仍流传 |
| 5 | Titan V 类比：NVLink 在那里被 VBIOS 禁用 | 一个真实的更早先例 | 在 170HX 上该值从一颗 OTP 熔丝出来、不是 VBIOS 设置。机制不迁移 |
| 6 | "有些晶片有工作的 VRAM 却失败的 NVLink 块、因此分级" | 正是报废分级通常的样子 | `FUSE_NVLINK_DEFECTIVE` = `0x00000000` 在每个被探测的 170HX 上。那颗熔丝恰恰是记录一条坏链路组的字段 |
| 7 | 按 A100 原理图焊上缺失的 NVLink 部件 | 板卡匹配、候选部件已被设计编号识别 | 依次被阻塞：净室政策（原理图被提供并被拒绝）；三颗无可见走线的 GPU 对地端接电阻、需要一个 boardview 或带专业红外返工的 GPU 移除；`R976` 落在带至少 82 行球的封装上**晶片下方**的球 `F51`；以及、决定性的、一次完美返工仍让 `FUSE_NVLINK_DIS` 停 `0x00000007` |
| 8 | 先表征 NVLink 信号完整性 | 对一个多几十 GHz 差分接口是正确的工程顺序 | 唯一可用的 60 GHz 示波器被判定不足；租足够设备被估计一个月几千美元。采纳的结论："Not like we need traceability on DIY nvlink boards. They either work or they don't."（DIY nvlink 板上又不需要可追踪性。它们要么工作、要么不。） |
| 9 | A100 桥上的 Microchip SM806022 时钟发生器 | 一颗真实、规格正确的部件（52.08333 MHz 晶振进、两个 156.25 MHz 差分 HCSL 出）真的在消费级 Ampere 桥上找到 | 对一块官方 A100 桥的直接检查：裸 PCB、无时钟发生器。命名它的拆解总结是从消费级桥材料机器生成的 |
| 10 | A100 桥含一个持有设备 ID 的 EEPROM | 消费级桥确实带一个 | "a100 nvlink has neither eeprom or sig gen"、来自直接检查。消费级 EEPROM 据信持有按板的线尾阻抗表征、不是 ID。对 SXM2 底板也确认："No, only traces" |
| 11 | 一块便宜的 4 卡主动 A100 NVLink 底板 | 被报告存在；会彻底解决拓扑问题 | NVIDIA 只文档化两两的三桥全部 Ampere 拓扑、NVSwitch 只存在于 SXM 平台内。识别出的唯一真实产品是一块中国 4x SXM V100 底板、无开关、一个带未知布线的不同代 |
| 12 | 一块单槽 8 路 NVLink 底板 | 真实 PCB CAD 工作存在：网格里重复的 `NVLink_MiniCoolEdge_124pin` 脚印带差分对布线、`SlimSAS_MCIO_8x` 连接器、铜浇注里 "A100" | 没制造板、没带起链路、没测带宽。8 路需要一个只存在于 SXM 的 NVSwitch。而且熔丝仍 `0x7`。唯一的信号完整性输入是一个机器写的 EM 模拟器、预测走线 "do a lot of antenna at 37ghz but the simulator says it will just barely work"（在 37ghz 做很多天线、但模拟器说它会勉强工作） |
| 13 | 买一块桥、逆向它、制造副本 | 桥被两位有数据中心硬件经验的人评估为完全无源、经济在约 200 欧元每颗时很残酷 | 没人买、没人造、语料库里从没有人手上有一块桥："I don't have a bridge to test"。而且熔丝立着时也没意义 |
| 14 | 从头制造一块 A100 interposer | "the a100 interposer is pretty simple, just needs the connector"、带一个具体信号完整性策略（Megtron 层压、非标准卡间朝向以缩短路径） | 连接器需要一个批量订购、带一个 90 度面板安装版本可能受出口限制的公开担忧（提出边安装作变通）。没订连接器、没制造板。而且 interposer 会插进死硅片 |
| 15 | 面对面装两块 PLX 底板让边缘连接器对齐 | 完全绕过插槽间距 | 纯猜测、从没画、从没估价、被同一颗熔丝阻塞 |
| 16 | 把 NVLink 当多卡带宽问题的修复 | 基线是约 1 GB/s 的 PCIe Gen1 x4、张量并行被反复叫 "a waste of time without nvlink" | 被一个 2x RTX 3090 带 NVLink 的一手测量缓和、它显示 vLLM 张量并行下一个 27B 模型只有约 10% 的吞吐提升。反方、相对 Gen1 x4 基线相对增益会大得多、只是推理、熔丝立着时不可测试 |
| 17 | "CMP PCB 完全没有 NVLink 连接器" | 有人真观察到一个带 NVLink 开口的导流罩盖着一块没有连接器的 PCB | 那个观察属于 CMP **90HX**、一块 GA102 RTX 3080 级板、它来自同一个无名制造商的兄弟 "RTX 3080 20GB" 确实用一块带 NVLink 连接器的 PCB。应用到 170HX 上它矛盾拆解证据（置信度：中等；这是一次内部调和、不是一个新鲜观察） |

---

## 物理情况

独立于熔丝之外，这里还有一个机械问题和一个人口/贴装问题。

- **金手指存在。** 170HX 复用了 A100 的板布局，NVLink 边缘金手指在物理上存在，也有三个桥连接器位置。这由 2023-10-25 的一次外部拆解确立，并得到卡主的认同。
- **导流罩挡住它们。** 在插上任何桥之前，必须对铝罩进行机加工或直接移除，这与 Tesla P100 的情况相同。NVIDIA 在 A100 上用橡胶盖住连接器，桥则卡扣在 A100 外壳上，因此给 170HX 装桥还需要采购带卡扣的 A100 外壳，或自制等效件。有一张 P100 用打磨机开出缺口后的照片，其电气结果未知。据报道，Bykski 的一款水冷头会让 NVLink 区域裸露在外。
- **桥是哑的。** 官方 A100 NVLink 桥是一块裸的无源 PCB：没有时钟发生器、EEPROM、重定时器，也没有包处理 ASIC。消费级 3090 SLI 桥*确实*带一个时钟发生器，据信是因为 NVIDIA 无法假定消费级主板会提供相同的 PCIe 参考时钟。从 Ampere 到 H200-NVL 的所有桥都被评估为 "dumb bridges"（哑桥）；开关只出现在更晚的世代。
- **你买不到第三方。** 唯一生产过的第三方 Ampere 桥，是已停产的 ElmorLabs NVB-3S——一个适用于 RTX 3090、RTX A5000 和 RTX A6000 的 3 槽部件，而非 A100 部件。对两个中文市场的一次调查只找到了价格统一的官方 2 槽和 3 槽桥，暗示交易量极低。

> [!NOTE]
> **未解问题：PCB 的 NVLink 区域贴装了吗？**
>
> 这是该领域影响最大的开放问题，因为它决定熔丝绕过是否还有意义。证据**倾向缺件**：语料库中唯一一次直接的 A100-对-CMP 板卡对比报告了部件缺失；而反方的说法是基于原理图的推断，并非观察。
>
> **缺件：** 2023 年的拆解陈述 "the gold fingers of the NV-Link interface exist, but the feature is unsupported with all components unpopulated on the PCB"（NV-Link 接口的金手指存在，但该功能不受支持，PCB 上的元件全部未贴装），并另称 "ICs related to the NV-Link interface are also missing"（与 NV-Link 接口相关的 IC 也已缺失）。一位依据 A100 原理图工作的研究者，识别出 GPU 上方五颗具体的缺件电阻（`R234` 000、`R237` NP、`R236` 1k、`R1024` 000、`R238` 000，全部在第 17 页），外加 `R976`、`R1029`、`R1030` 和三颗 GPU 对地端接电阻。另一位参与者回忆提到"给 NVLink 供电的部件缺失"。
>
> 这份电阻清单来自直接比较两块板："they are populated on a genuine A100, but missing on CMP"（它们在真 A100 上是贴装的，在 CMP 上缺失）。这是语料库中唯一一次这样的并排对比。
>
> **贴装：** 项目自己的 VBIOS 对比表陈述 "NVLink bridge, external bridge absent (PCB fully populated)"（NVLink 桥——外部桥缺失（PCB 完全贴装）），但那只是项目文档里的一行，并非实际检查。在电阻清单贴出**两小时前**，另一位研究者说 "I do not believe there are any missing NVlink components. According to the schematics, the GPU die is connected directly to the edge connectors"（我不认为有任何缺失的 NVlink 元件。根据原理图，GPU 晶片直接连接到边缘连接器），并把混淆归咎于桥含有主动元件，"including a ROM chip"（包括一颗 ROM 芯片）。最后那个前提本身也被反驳：下方死路 #10 记录的直接检查发现，A100 桥上并没有 EEPROM。
>
> **复杂化细节：** `R237` 在 A100 原理图**本身**里就被标为 **NP**（未贴装），所以五颗里至少一颗在真 A100 上也应是缺失的。这正说明用肉眼对比有多容易误导，也是结论只能停在"leans depopulated, one direct comparison, unrebutted"（倾向缺件、一次直接对比、未被反驳）而非定论的原因。没有人为了留档而在两块板上拍过这个区域。

---

## 拓扑和带宽、为了它要紧时

记录下来，免得有人重新推导，也因为几个流传甚广的数字是错的。

| 量 | 值 | 置信度 |
|---|---|---|
| A100 PCIe 受支持拓扑 | 2 个 GPU、全部三桥必需 | 高 |
| A100 每桥带宽 | 200 GB/s | 高 |
| A100 两两总计 | 600 GB/s | 高 |
| Ampere 端口结构 | 4 子端口 x 4 通道 @ 每通道 50 Gbps、陈述为每端口 200 Gbps；4 x 4 x 50 是 800 Gbps、所以分解和数字不可能都对 | 中等 |
| GA102（RTX 3090）第三代每链路 | 14.0625 GB/s 双向、四个 x4 链路 | 高 |
| GA102 总计 | 56.25 GB/s 双向、两 GPU 之间 112.5 GB/s 总聚合 | 高 |
| NVSwitch | 仅 SXM 平台（例如 DGX）；8 路 | 高 |

三个比值说法都在拉锯，没有一个能干净定论。频道把 A100 对 3090 定为 **3x**（600 对 200 GB/s），但 NVIDIA 文档化的 GA102 数字是 112.5 GB/s 总聚合，给出 **5.33x**。为 3090 引用的 200 GB/s 数字，在同一场讨论里被描述为 "200 GB/s-class bridges downclocked"（200 GB/s 级桥降频而来），这正说明 3x 的比较用了错误的约定。两种解读都同意：更早那句 "A100 has 6x the NVLink bandwidth of a 3090"（A100 的 NVLink 带宽是 3090 的 6 倍）是错的。能定论它的，是一个明确的陈述：A100 的 600 GB/s 究竟是单向求和，还是总聚合。

> [!NOTE]
> **未解问题：2 路还是 4 路无源？**
>
> 三个连接器恰好构成一个四节点全连接网格所需的节点度；每边 200 GB/s、跨 3 条边就是每卡 600 GB/s 的聚合，与两两数字在算术上相同。所以 4 路在几何上是自洽的。**尚未**确立的是：NVIDIA 的驱动或固件是否会在一块 PCIe GA100 上把链路训练到三个不同的对端。没有文档这么说，也没人演示过。两个说法讨论的是不同的事（几何结构对受支持配置），两者可能都成立。

> [!WARNING]
> **不要按 320 GB 数字定尺寸一个构建**
>
> 一场 4 卡 NVLink 讨论为四张 10 GB 卡引用了 320 GB 的内存池，那假设每卡 80 GB。出货解锁给 10 GB 卡 **40 GB**，所以四张合计 **160 GB**；四张解锁的 8 GB 卡合计 **256 GB**。80 GB 配置曾被尝试并发现不稳定：见[80 GB 尝试](80gb.md)。

---

## PCIe 点对点回退

由于 NVLink 不可达，PCIe P2P 成了今天唯一有机会工作的跨 GPU 加速路径。它不在 cmpunlocker 中：对 `master` 及每个分支搜索 `p2p` 和 `peer`，只命中 `build.sh` 安装列表里的出厂 `nvidia-peermem.ko`，以及 `0008` diff 中一行未修改的上下文（`nv_uvm_resume_P2P(pUuid)`）。任何分支都不含 P2P 使能。

候选是一个 `tinygrad/open-gpu-kernel-modules` 的社区 fork，默认分支 `610.43.03-p2p`，**版本与 cmpunlocker 瞄准的相同**。`HEAD~3` 是提交 `452cec62d827` "610.43.03"（2026-07-07），一次普通的 NVIDIA 发布导入。它之上压着三个提交：

| 提交 | 内容 | 大小 |
|---|---|---|
| `9fb650447c7b` | 组合 P2P mod | 8 个文件、+83/-28 |
| `52670f7fd6a7` | 实验性巨页 `cudaHostRegister` 加速 | 7 个文件、+383/-97 |
| `2849449f8cd6` | README | +245 |

P2P 提交改动 `install.sh`（+7）、`kernel-open/nvidia-uvm/uvm_gpu.h`（+7）、`kernel-open/nvidia/nv-reg.h`（+1/-1）、`src/nvidia/generated/g_kern_bus_nvoc.c`（+5/-5）、`src/nvidia/src/kernel/gpu/bif/kernel_bif.c`（+3/-3）、`src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c`（+10）、`src/nvidia/src/kernel/mem_mgr/io_vaspace.c`（+11/-10）和 `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c`（+39/-9）。它在 NVLink 缺失的 GPU 上启用 BAR1 P2P，存在 NVLink 时则回退到 NVLink；对 PCIe 对，传输会经 DMA 直接写入另一颗 GPU 的物理地址。

> [!WARNING]
> **实验性：GA100 不在受支持列表上**
>
> 分支列出 RTX 3090（有 NVLink 就两两、否则 PCIe BAR1）、RTX 4090 和 RTX 5090。**GA100 不在那个列表上、补丁从没在 170HX 上测试过。** P2P 路径碰 `kern_bus_gp100.c`、`io_vaspace.c` 和 `nv_gpu_ops.c`，所以一个 GA100 代码路径可能根本不存在。

> [!CAUTION]
> **只取 P2P 提交、不要取巨页提交**
>
> `52670f7fd6a7` 加速 `cudaHostRegister`、声称对 1G 巨页支持的缓冲约 5000x、并为这类映射缩小设备页表。它的作者陈述它被自动启用、且 "this path skips some of the per-4K-page bookkeeping the stock driver performs, so it may misbehave in edge cases the stock driver handles correctly"（这条路径跳过出厂商驱动执行的某些每-4K-页记账、所以它可能在出厂商驱动正确处理的边缘情况里出错）。把它当一个独立于解锁补丁的不稳定来源。

那个分支文档化的设置要求：`GRUB_CMDLINE_LINUX_DEFAULT` 里 `amd_iommu=on iommu=pt` 或 `intel_iommu=on iommu=pt`、`update-grub`、安装 610.43.03 驱动、跑 `./install.sh`、重启。IOMMU 必须处于 **passthrough** 模式且不翻译、否则 DMA 走 IOMMU 页表、传输失败。README 显式警告这 "very dangerous if you run untrusted software or devices"（如果你跑不受信任的软件或设备非常危险）。如果 P2P 慢、根端口上的 ACS 把一切 GPU 到 GPU 流量都经 CPU 根复合体强制；在 BIOS 里禁用它、用 `pcie_acs_override=downstream,multifunction`、或用 ACS 覆盖内核补丁。

完整处理见[P2P](p2p.md)。

---

## 什么会真正推进这个

按最易上手的排在前面。只有前两个是便宜的。

### 1. 做那个没人做过的写

在全部 31 个归档解锁器附件以及每个净室工件中，NVLink 只以熔丝读数形式出现。没有探测脚本，没有覆盖尝试，也没有任何记录的写入。在一张可牺牲卡上，对 `CTRL_OPT_NVLINK`（`0x008209B8`）和 `CTRL_OPT_PERLINK`（`0x00820820`）做一次读-写-读探测，随后重读 `STATUS_OPT_NVLINK`（`0x00820DB8`），只需一个会话。

> [!CAUTION]
> **只写到一张可牺牲卡**
>
> 这些是安全熔丝影子寄存器。关于写它们的普遍告诫，正是至今没人动过手的原因。预期结果是：写被丢弃，状态停在 `0x00000007`。这个负结果仍值得记录在案，因为目前语料库甚至连"它被试过"都说不出口。

### 2. 拍 NVLink 元件区的照片

为一张已去掉导流罩的 170HX 拍下 `R234`、`R236`、`R237`、`R238`、`R976`、`R1024`、`R1029`、`R1030` 等设计编号周围的高分辨率照片，与真 A100 并排，再做一次从 NVLink 边缘金手指到 BGA 球 `F1` 和 `G1` 的连通性检查（`R1029`/`R1030` 连到晶片边缘的球，可以用细线够到）。它便宜、决定性，只需一张卡和一次导流罩移除。维护者早在 2026-07-19 就把它列为实践第一步，却至今没人做过。

### 3. 追踪 DevInit 对 `0x820684` 的读

`0x820684` 在 DevInit 访问清单上。没人顺着反汇编追踪过这次读，看结果是否曾写入任何地方，还是仅仅被消费。如果在 OTP 和状态寄存器之间有一个可欺骗的消费方，它就在这里。这条路径只被工作量所阻，也撞上了曾挡住 PCIe 熔丝层的那堵墙。

### 4. 解码 3 位禁用字段对 12 条物理链路

`FUSE_NVLINK_DIS[2:0]` = `0x7`，对应 `PTOP_SCAL_NUM_NVLINK` = 12；而 `STATUS_OPT_NVLINK` 被标注为 16 位字段，却也读 `0x00000007`。**工作假设（未确认）：** 三条链路组，每组四条（12 = 3 x 4），这能解释反复出现的 "all groups"（所有组）措辞，以及 RTX 3080 相对其 `PTOP_SCAL_NUM_NVLINK` `0x4` 而读出的 `0x1`。语料库中没有任何东西能确认这一点。能定论它的办法：探测一颗带有已知部分 NVLink 地板清扫的 A100，或找到 NVIDIA 关于 GA100 上 `NV_FUSE_OPT_NVLINK_DISABLE` 字段宽度的文档。

### 5. 插一块桥、看看会发生什么

这是唯一一个从未有人跑过的经验测试。语料库中从未有人同时持有一张 170HX 和一块 A100 NVLink 桥。准备一块桥、做一次导流罩改装（或用一个让该区域裸露的水冷头），然后运行 `nvidia-smi nvlink` 并查看 dmesg。鉴于那颗熔丝，预期是负面的；但语料库如今甚至无法确认连接器是否正确对齐。

### 6. Interposer 制造

在项目 5 返回阳性之前毫无意义，降级处理。

### 7. 一次真正的熔丝绕过

桌上没有任何可操作的东西。进展还额外受阻于潜在贡献者手里没卡："I wanted to work on it but I cant get any cards. So you have to wait until someone else figures it out."（我想做，但弄不到任何卡。所以只能等别人把它搞明白。）

---

## 立场如何移动

| 时期 | 相信 | 被什么取代 |
|---|---|---|
| 2023-10-25 到 2026-05-07 | NVLink 不受支持因为硬件缺失（拆解：金手指存在、元件未贴装） | 一个测得的熔丝故事：晶片缩放到 12 条链路、没有标记有缺陷、禁用是一颗读 `0x7` 的 OTP 熔丝。直接 BAR0 回读对硅片相信什么胜过照片拆解。注意两者**不**互斥；贴装问题仍开放 |
| 2026-05-31 | 熔丝可能是值得那样攻击的挖矿 SKU 限制 | Drive A100 32 GB 读相同的 `0x7`/`0x7`。通用 GA100 分区 |
| 2026-05-31 起 | "NVLink killed, CTRL_OPT override path under investigation"（NVLink 被杀、CTRL_OPT 覆盖路径调查中）（仍在 VBIOS 对比表里打印） | 在同一文档内被 `FUSE_EN_SW_OVERRIDE` = `0x0` 取代："CTRL_OPT fuse override disabled, cannot be changed, inert on 170HX"。参考表内部不一致；熔丝测量赢 |
| 2026-07-07 到 2026-07-10 | A100 存在便宜的 4 卡主动 NVLink 底板 | 只有两两拓扑；NVSwitch 仅 SXM |
| 2026-07-18 到 2026-07-21 | A100 桥含主动电路（时钟发生器、EEPROM） | 直接检查：裸 PCB |
| 2026-07-19 | "it has triple (200GB/s?) NVLink, so PCIe is a non-issue" | 同一天被问 "doesn't work though, right?" 后自我撤回 |
| 2026-07-20 | 阻塞器是 "cracking some kind of security-by-design architecture using encryption named HULK" | 被网站维护者和页面自己的作者撇清。从没发布替代解释 |
| 2026-07-19 到 2026-07-27 | "worth trying, probably just a bridge"（值得一试、大概就是块桥） | "Might need to consider the state of NVLink, it's a lot harder than I thought to get working"（可能需要考虑 NVLink 的状态、它比我以为的难搞得多）。第一步被重新定义为为物理访问重新设计外壳、然后拍元件区照片。被问在一月和一年之间选时、答案是研究完成前无法说任何定论 |

---

## 实测值

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| `FUSE_NVLINK_DIS` `0x00820684` | `0x00000007` | 两张 170HX 单元；Drive A100 32GB（PG199） | 高 |
| 相同 | `0x00000000` | A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A5000、A6000、RTX 3090、RTX 3090 Ti | 高 |
| 相同 | `0x00000001` | RTX 3080、RTX 3080 Ti | 高 |
| `STATUS_OPT_NVLINK` `0x00820DB8`（RO） | `0x00000007` | 两张 170HX 单元；Drive A100 | 高 |
| `FUSE_NVLINK_DEFECTIVE` `0x0082068C` | `0x00000000` | 每张被探测的卡；15 卡调查里每张返回值的卡上 `0`、A16 和 ES 列除外 | 高 |
| `FUSE_NVLINK_DIS_CP` `0x00820688` | `0x00000000` | 每张被探测的卡 | 高 |
| `OPT_SECURE_NVLINK_MASK_WR_SECURE` `0x00820704` | GA100 `0x00000005` / GA10x `0x00000085` | 干净架构分裂 | 高 |
| `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE` `0x00820BD4` | `0x00000001` | 全部 14 张被探测的 Ampere 卡上统一 | 高 |
| `FUSE_NVLIPT_RST_DIS` `0x00821100` | `0x00000000` | 每张被探测的卡 | 高 |
| `CTRL_OPT_NVLINK` `0x008209B8` | `0x00000000` | 每张被探测的卡包括 170HX | 高 |
| `CTRL_OPT_PERLINK` `0x00820820` | `0x00000000` | 170HX | 高 |
| `PTOP_SCAL_NUM_NVLINK` `0x0002246C` | `0x0000000c`（12） | 两张 170HX、全部 A100 SKU、Drive A100 | 高 |
| 相同 | `0x00000004`（4） | A10、A5000、A6000、RTX 3080/3080 Ti/3090/3090 Ti | 高 |
| 相同 | `0x00000000` | 仅 A16 | 中等 |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000` 170HX 和数据中心 GA100 / `0x00000001` 消费级和 ES | 高 |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | 全部卡 | 高 |
| `FUSE_FEAT_OVR_DIS` `0x008203F0` | `0x00000000` | 全部卡；主覆盖灭杀**没**被烧断 | 高 |
| 未签名 FwSec VBIOS 尾 | `0x43A00`-`0x47700`、MAC 范围外 15,616 字节 | 在 `0x47341` 持有一个 25 条目 `NV_FUSE_CTRL_OPT_*` 表、13 块 GA100 卡上全零 | 高 |
| DevInit 对 NVLink 熔丝的读 | `0x820684` 存在于 `0x1482xxxx` 访问目录 | 只读、从不写 | 中等 |
| `nvidia-smi nvlink` 输出 | "Device does not have or support Nvlink." | 一个租用 8 卡 64 GiB 主机、2026-07-24、GPU 名掩码；语料库里唯一捕获 | 中等 |
| dmesg NVLink 行 | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` | 良性、软件核心加载 | 高 |
| 出货 `master` 里的 NVLink 引用 | 0 | 全树 grep | 高 |
| 全部 12 个分支里的 NVLink 引用 | 1 个词、`Planned`、两个 README 表 | 任何地方都无代码 | 高 |
| 4x 解锁 10 GB 卡池 | 160 GB（4 x 40960 MiB） | 出货 `constants.yaml` | 高 |
| 4x 解锁 8 GB 卡池 | 256 GB（4 x 65536 MiB） | 出货 `constants.yaml` | 高 |
| A100 桥市场价 | 约 200 欧元每颗、一个受支持的 A100 对需要全部三颗 | 2026-07-26 市场检查 | 中等 |
| 估计 NVLink 走线频率 | 37 GHz（机器写 EM 模拟器）对比约 60 GHz（二手） | 冲突；两者都非从 50 Gbps 通道速率推导 | 低 |
| 2x RTX 3090 vLLM TP、27B 模型 | 带 NVLink 约 10% 吞吐改善 | 一手、单一测试者 | 中等 |
| 2x RTX 3090 vLLM、已发布第三方 | 715 对比 483 t/s 输出；6,790 对比 4,583 t/s 吞吐 | 模型、量化和批设置未说明、所以与上面不可比 | 中等 |

> [!NOTE]
> **群组注意**
>
> 参考表中，A16 列对每个 NVLink 熔丝行都读占位符 `BAR0`。上文"on all cards"（全部卡上）形式的陈述，应理解为在熔丝行上排除 A16。A16 是唯一报告零 NVLink 缩放的 Ampere 部件，但它实际的禁用熔丝状态从未被捕获。

---

## 参见

- [NVLink 硬件](../hardware/nvlink-hardware.md) 看连接器和板卡细节
- [熔丝与 OTP](../hardware/fuses-and-otp.md) 看完整熔丝群组和方法论
- [算力节流](../unlock/compute-throttle.md) 看确实工作的 `FEAT_OVR` 路径
- [PCIe Gen3 和 Gen4](pcie-gen3-gen4.md) 看另一个熔丝门控前沿
- [P2P](p2p.md)、[状态板](status-board.md)、[未解问题](open-questions.md)
