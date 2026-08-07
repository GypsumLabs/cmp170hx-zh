# NVLink：熔丝禁用，未找到可用杠杆

**本页涵盖内容。** 本页梳理 CMP 170HX 上 NVLink 的完整现状：证明它是在一次性可编程硅片中被禁用、而不是由软件禁用的熔丝读数；已经进行过的全部探测；提出过的每条覆盖路径及其失效原因；物理连接器和桥接器的情况；以及真正能够推动问题进展的简短实验清单。

**核心结论：CMP 170HX 上的 NVLink 不工作，语料库中没有任何人曾让它工作过，也没有人尝试过寄存器级解锁。** 它是被 OTP 熔丝禁用的，不是被软件禁用的。cmpunlocker 的代码中，无论是发布版 `master`，还是 12 个未发布分支快照中的任何一个，都没有一行涉及 NVLink。NVLink 在全部分支中只出现过一次：两个 README 特性表中的一个词 `Planned`。

> [!NOTE]
> **未解问题**
>
> 这是该领域价值最高的未知项，但目前没有任何可直接推进的方案。两条覆盖路径都已经关闭：`CTRL_OPT` 路径被 `FUSE_EN_SW_OVERRIDE` = `0x0` 关闭，`FEAT_OVR` 路径则因为对应寄存器块中根本没有 NVLink 寄存器而被排除。正如 2026-07-20 的一份总结所说：“Still unsolved rn, a bit harder as there's no fuse mask.”（现在仍未解决，因为没有熔丝掩码，问题更难。）

**这种能力理论上应当是什么样。** NVLink 的行为类似 MMIO：链路远端的内存可以映射到本地 GPU 的地址空间，再由 CUDA 内核或复制引擎驱动。这个说法来自最初提出该利用方案的作者，置信度为中等。它从未在 170HX 上演示过，因为从来没有任何链路成功建立。正是这种直接寻址能力，使桥接显卡之间的共享显存池具有实际意义。

---

## 硅片给出的信息

下面三项读数定义了当前状况。它们在两个 SKU 上至少五次独立回读中保持一致，也与 15 张 Ampere 参考卡组成的对照组一致。

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | `0x00820684` | `0x00000007` | `[2:0]` 禁用字段的三个 bit 全部置位 |
| `STATUS_OPT_NVLINK`（只读镜像） | `0x00820DB8` | `0x00000007` | 芯片其余部分实际看到的状态 |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246C` | `0x0000000c` | 晶片按 12 条链路进行缩放，与每个 A100 完全相同 |

下面三项则说明硅片本身是健康的：

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `FUSE_NVLINK_DEFECTIVE` | `0x0082068C` | `0x00000000` | 不是为了修复良率而禁用。一次调查中，15 张对照卡里所有成功返回数值的卡都读为 `0`；A16 列读到的是 `BAR0` 占位符，ES 列为空 |
| `FUSE_NVLINK_DIS_CP`（禁用关键路径） | `0x00820688` | `0x00000000` | 没有在关键路径级别被禁用 |
| `FUSE_NVLIPT_RST_DIS` | `0x00821100` | `0x00000000` | NVLink IP 的复位条件没有被禁用 |

再看覆盖机制相关的四项，后两项表明覆盖机制已经关闭：

| 寄存器 | 地址 | 170HX 值 | 含义 |
|---|---|---|---|
| `CTRL_OPT_NVLINK`（有效值，每条链路占 bit 15:0） | `0x008209B8` | `0x00000000` | 没有设置 CTRL 覆盖；禁用状态通过 STATUS 路径传入 |
| `CTRL_OPT_PERLINK`（bit 11:0） | `0x00820820` | `0x00000000` | 同上 |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | `0x00000000` | 整个 `CTRL_OPT` 覆盖机制已在熔丝级别禁用 |
| `FUSE_DIS_SW_OVR` | `0x00820084` | `0x00000001` | 从另一个方向确认了上面的结论 |

语料库给出的结论是：**这是刻意的产品分区，而不是通过熔丝裁剪进行的报废分级。** 链路在晶片上物理存在，晶片报告有 12 条链路，没有一条被标记为有缺陷，而禁用状态来自一颗熔丝。

### 这不是挖矿 SKU 专属限制

Drive A100 32 GB（PG199、`GA100-550F-A1`、`FUSE_PCIE_DEVIDA` = `0x000020bb`、`FUSE_PCIE_DEVIDB` = `0x000020fb`）在两块实体 PG199 板卡上测得完全相同的 `FUSE_NVLINK_DIS` = `0x00000007` 和 `STATUS_OPT_NVLINK` = `0x00000007`。三个普通 A100 SKU 全都读为 `0x00000000`。任何把 NVLink 熔丝解释为加密货币挖矿专属惩罚的理论，都必须解释 Drive 部件为何也有同样的状态。

### 写安全性按架构划分，而不是按 SKU 划分

`0x00820704` 处的 `OPT_SECURE_NVLINK_MASK_WR_SECURE`，在每一个 GA100 部件上都读为 `0x00000005`（两张 170HX、三个 A100 SKU 以及 Drive A100），在每一个 GA10x 部件上都读为 `0x00000085`。与普通 A100 相比，170HX 并没有被额外锁定。

---

## 代码给出的信息

在发布版 `master` 整棵代码树中，搜索 `nvlink` 以及每个 NVLink 寄存器地址，都没有命中。`common/constants.yaml`、`driver/build.sh`、`driver/VERSION`、`install.sh`、`remove.sh`、`README.md`，以及六个补丁（从 `0001-sec2-postbl-plm-ss-cfg.patch` 到 `0006-persistent-sw-state.patch`）中都没有相关内容。`constants.yaml` 只声明了两个驱动版本、设备 ID `20c2`/`2082`、算力值 `ss0: 0x88888888` / `ss1: 0x00000008`，以及两个显存配置。

未发布分支的情况也一样。在全部 12 个分支（`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`）中，NVLink 恰好只出现一次，而且只是表格中的一行：

```markdown
| PCIe Gen2 x4 | Platform-dependent (no separate Root-port patch) |
| ECC | Planned |
| NVLink | Planned |
```

这组表格行只存在于 `housekeeping` 和 `memory` 分支的 README 中。任何地方都没有 NVLink 逻辑。

---

## 两条覆盖路径，以及它们为何都已关闭

### 路径 A：`CTRL_OPT_NVLINK`

这是整个语料库中被提及最多的“下一步”，但**从来没有人真正执行过这次写入**。它读为 `0x00000000`，文档将其定义为*有效的*逐链路启用/禁用字段，并称其可写。它看起来像是那个可用的杠杆。

但它是被强有力的先验证据关闭的，而不是被一次实际实验关闭的：

- 170HX 和所有数据中心 GA100 部件的 `FUSE_EN_SW_OVERRIDE`（地址 `0x00820040`）均为 `0x00000000`；相比之下，所有消费级部件和工程样品部件均为 `0x00000001`。`CTRL_OPT` 覆盖机制本身已经在熔丝级别被禁用。
- 所有卡的 `FUSE_DIS_SW_OVR`（地址 `0x00820084`）均为 `0x00000001`。
- 未签名 FwSec VBIOS 尾部（`0x43A00`-`0x47700`，即 MAC 验证范围之外的 15,616 字节）中偏移 `0x47341` 处的 25 项 `NV_FUSE_CTRL_OPT_*` 表，在探测过的 13 张 GA100 卡上全部读为零；在这里它不起作用。

任何经由 `CTRL_OPT_NVLINK` 的方案，都必须先突破 `FUSE_EN_SW_OVERRIDE`，而目前不存在能做到这一点的机制。

### 路径 B：`FEAT_OVR` 式攻击

这条思路之所以有吸引力，是因为发布版算力解锁恰好位于同一个寄存器块，而且所有卡上的主覆盖禁用熔丝 `FUSE_FEAT_OVR_DIS`（地址 `0x008203F0`）都读为 `0x00000000`，也就是说它**没有被烧断**。当时的推理是：如果算力节流可以在这里覆盖，也许 NVLink 也可以。

但这条路被直接排除，因为该寄存器块中没有 NVLink 寄存器。`0x00823800`-`0x0082382C` 的完整清单如下：

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

这 12 项覆盖 ECC、Quadro 分类、SM 速度、行重映射和读出，没有任何 NVLink 项，也没有可供写入的 NVLink 目标。对同一寄存器块进行的 PCIe 尝试可以作为有用的对照，但它是一次探测结果，而不是第二个寄存器：对 `0x00823800` 进行高安全级别写入后回读为 `0xfffffe8e`，说明写入确实生效；然而 `OPT_GEN23`（`0x82057C`）仍为 `0x1`，链路也仍停在 Gen1。当时对这一结果的解释是：PCIe 覆盖使能已被熔丝置为**关闭**，尽管上面的清单中没有 PCIe 项。`0x0082381C` 的 `SM_SPD` 是真实存在的项，并且熔丝状态为**开启**，所以[算力解锁](../unlock/compute-throttle.md)可以走这条路径，而[PCIe 速度解锁](pcie-gen3-gen4.md)不行。

### DevInit 角度

DevInit 确实会读取这颗熔丝。CMP DevInit 反汇编中所有 `0x1482xxxx`（MMIO `0x82xxxx`）访问的完整清单包含 `0x820684`，还包括 `0x820C14`/`0x820D38`（FBIO/FBP 熔丝裁剪）、`0x82380C`/`0x823814`、`0x820520`（`MAGIC_D`）和 `0x820148`。任何源码都没有写入它，也没有指出任何有效覆盖机制，**更没有人追踪过读取该值之后发生了什么**（置信度：中等；依据是访问清单，而不是完整执行轨迹）。

---

## 失败路线

下面每一项都是真实有人认真追查过的合理想法。

| # | 想法 | 为什么看似合理 | 如何失败 |
|---|---|---|---|
| 1 | “NVLink 已经出现在引导日志里，所以只差一块桥” | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` 确实会在每次引导时出现 | 这行由 `nvidia-nvlink.ko` 软件核心库在 `nvlink_linux.c:344` 发出，只是在宣布模块已加载。它以 `DBG_INFO` 级别记录，几乎所有 GPU 的每次驱动加载都会出现，发生在早期模块加载期间、GPU/GSP 启动之前。`236` 是由 `alloc_chrdev_region` 动态分配的字符设备主设备号，每次引导可能不同。一次被记录的 `nvidia-smi nvlink` 运行返回了 “Device does not have or support Nvlink.” |
| 2 | “HULK” 加密阻塞器 | 这是唯一发布过的解释，出现在一个项目相关的 gitbook 上，而且语气很权威 | 网站维护者于 2026-07-20 公开否定了它（“This hasn't been updated in some time, don't rely on that”），页面作者本人也称其已经过时。任何熔丝读数、VBIOS 转储或 DevInit 反汇编都没有证据支持存在一个用加密机制门控 NVLink 的方案 |
| 3 | “`FUSE_NVLINK_PHYS_DMG = 0x1` 意味着链路被标记为损坏” | 寄存器名是 `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE`；置位的损坏标志看起来像一道单向闸门 | 在探测过的全部 14 张 Ampere 卡上都读为 `0x1`，其中包括健康的 A100 |
| 4 | “NVLink 是软件锁定的” | 170HX 的其他几项限制确实位于固件侧 | 禁用状态来自 OTP 熔丝 `0x00820684`，并被镜像到只读状态寄存器中。之所以仍要记录这条说法，是因为直到语料库的最后一天 2026-07-27，它还在流传 |
| 5 | Titan V 类比：NVLink 在那里由 VBIOS 禁用 | 这是一个真实存在的早期先例 | 170HX 的值来自 OTP 熔丝，而不是 VBIOS 设置；两者的机制不能类推 |
| 6 | “有些晶片的显存正常，但 NVLink 块损坏，所以这是分级结果” | 这正是通常的报废分级方式 | 每一张被探测的 170HX 的 `FUSE_NVLINK_DEFECTIVE` 都是 `0x00000000`。这颗熔丝恰好就是用来记录坏链路组的字段 |
| 7 | 按 A100 原理图给缺失的 NVLink 器件补焊 | 板卡布局匹配，而且已经通过设计编号识别出候选器件 | 依次受阻于：净室规则（原理图曾被提供，但被拒绝使用）；三颗没有可见走线的 GPU 对地端接电阻，需要 boardview 或专业红外返工拆下 GPU；`R976` 落在一个至少有 82 行球的封装中、晶片下方的球 `F51` 上；最关键的是，即使返工完美，`FUSE_NVLINK_DIS` 仍然是 `0x00000007` |
| 8 | 先做 NVLink 信号完整性表征 | 对多几十 GHz 的差分接口来说，这是正确的工程顺序 | 唯一可用的 60 GHz 示波器被认为仍不够用；租用足够的设备预计一个月要几千美元。最终采用的结论是：“Not like we need traceability on DIY nvlink boards. They either work or they don't.”（DIY NVLink 板不需要做可追溯性，它们要么工作，要么不工作。） |
| 9 | A100 桥上的 Microchip SM806022 时钟发生器 | 这是一颗真实且规格匹配的器件（输入 52.08333 MHz 晶振，输出两路 156.25 MHz 差分 HCSL），确实在消费级 Ampere 桥上被发现过 | 直接检查一块官方 A100 桥后发现它只是裸 PCB，没有时钟发生器。最初指出该器件的拆解总结，是根据消费级桥材料机器生成的 |
| 10 | A100 桥包含一个保存设备 ID 的 EEPROM | 消费级桥确实带有一个 EEPROM | 直接检查给出的结论是 “a100 nvlink has neither eeprom or sig gen”。据推测，消费级 EEPROM 保存的是每块板的生产末端阻抗表征，而不是设备 ID。对 SXM2 底板也得到确认：“No, only traces” |
| 11 | 一块廉价的 4 卡主动式 A100 NVLink 底板 | 有人报告说它存在，而且它可以彻底解决拓扑问题 | NVIDIA 只记录了 Ampere 两两连接、需要全部三块桥的拓扑；NVSwitch 只存在于 SXM 平台内部。最终识别出的唯一真实产品是一块中国制造的 4x SXM V100 底板，没有交换芯片，属于不同代际，具体走线未知 |
| 12 | 一块单槽 8 路 NVLink 底板 | 确实存在过真实的 PCB CAD 设计：网格中重复放置 `NVLink_MiniCoolEdge_124pin` 封装并布置差分对，配有 `SlimSAS_MCIO_8x` 连接器，铜皮中还写有 “A100” | 没有制造出板卡，没有建立链路，也没有测量带宽。8 路连接需要只存在于 SXM 平台的 NVSwitch，而且熔丝仍然是 `0x7`。唯一的信号完整性依据是一份机器生成的 EM 模拟结果，它预测走线“do a lot of antenna at 37ghz but the simulator says it will just barely work”（在 37ghz 会产生大量天线效应，但模拟器说它勉强能工作） |
| 13 | 买一块桥、逆向它，再制造复制品 | 两位有数据中心硬件经验的人都判断桥是完全无源的，而每块约 200 欧元的成本非常不划算 | 没有人买桥，也没有人制造复制品；语料库中从来没有人手上真正有一块桥：“I don't have a bridge to test”。而且在熔丝仍然存在的情况下，这件事也没有意义 |
| 14 | 从头制造一块 A100 interposer | “the a100 interposer is pretty simple, just needs the connector”，并且提出了具体的信号完整性方案（Megtron 层压板，以及通过非标准的卡间朝向缩短走线） | 连接器需要批量订购，另有一种公开担忧认为 90 度面板安装版本可能受到出口限制，因此有人提出使用边缘安装版本规避。没有订购连接器，也没有制造板卡。而且 interposer 最终仍会插到已被熔丝禁用的晶片上 |
| 15 | 将两块 PLX 底板面对面安装，让边缘连接器彼此对齐 | 完全绕过插槽间距问题 | 纯属推测，从未画图、估价，也同样被那颗熔丝阻塞 |
| 16 | 把 NVLink 当作多卡带宽问题的解决方案 | 基线是约 1 GB/s 的 PCIe Gen1 x4，而且人们反复说没有 NVLink 时张量并行“a waste of time without nvlink” | 一次对带 NVLink 的 2x RTX 3090 进行的一手测量削弱了这个判断：在 vLLM 张量并行下运行 27B 模型，吞吐量只提升约 10%。反方认为，相对于 Gen1 x4 基线，增益会大得多；但这只是推理，在熔丝仍然存在时无法验证 |
| 17 | “CMP PCB 完全没有 NVLink 连接器” | 确实有人观察到，一块没有连接器的 PCB 上方盖着带 NVLink 开口的导流罩 | 这个观察属于 CMP **90HX**，也就是 GA102 RTX 3080 级别的板卡；同一无名制造商生产的兄弟型号 “RTX 3080 20GB” 确实使用了带 NVLink 连接器的 PCB。把这一观察套用到 170HX 会与拆解证据矛盾（置信度：中等；这是对内部证据的调和，不是新的观察） |

---

## 物理情况

除了熔丝状态之外，这里还有一个机械问题和一个板上器件贴装问题。

- **金手指确实存在。** 170HX 复用了 A100 的板卡布局；NVLink 边缘金手指在物理上存在，板上也有三个桥接器连接器位置。这一点由 2023-10-25 的一次外部拆解确立，也得到持卡者认可。
- **导流罩挡住了连接器。** 在插入任何桥之前，必须对铝制导流罩进行机加工或拆除，情况与 Tesla P100 相同。NVIDIA 在 A100 上用橡胶盖住连接器，桥则通过卡扣固定在 A100 外壳上。因此，要在 170HX 上安装桥，还需要找到带卡扣的 A100 外壳，或自制等效结构。有一张照片显示 P100 已用电磨机开出缺口，但其电气结果未知。据报道，Bykski 的一款水冷头会让 NVLink 区域露出。
- **桥是无源的。** 官方 A100 NVLink 桥是一块裸的无源 PCB：没有时钟发生器、EEPROM、重定时器或数据包处理 ASIC。消费级 3090 SLI 桥**确实**带有时钟发生器，据推测是因为 NVIDIA 无法假定消费级主板会提供相同的 PCIe 参考时钟。从 Ampere 到 H200-NVL 的所有桥都被判断为“dumb bridges”（哑桥）；交换芯片只在更晚的代际中出现。
- **买不到第三方桥。** 唯一生产过的第三方 Ampere 桥是已经停产的 ElmorLabs NVB-3S。这是一款适用于 RTX 3090、RTX A5000 和 RTX A6000 的 3 槽部件，不是 A100 部件。对两个中文市场的调查只找到了价格统一的官方 2 槽和 3 槽桥，说明市场交易量极低。

> [!NOTE]
> **未解问题：PCB 的 NVLink 区域是否贴装了器件？**
>
> 这是该领域影响最大的未解问题，因为它决定即使绕过熔丝，是否仍然有实际意义。现有证据倾向于**未贴装**：语料库中唯一一次 A100 与 CMP 的直接板卡对比报告了器件缺失，而相反的说法来自原理图推断，并非直接观察。
>
> **未贴装：** 2023 年的拆解称：“the gold fingers of the NV-Link interface exist, but the feature is unsupported with all components unpopulated on the PCB”（NV-Link 接口的金手指存在，但该功能不受支持，PCB 上所有器件都未贴装）；拆解还单独称“ICs related to the NV-Link interface are also missing”（与 NV-Link 接口相关的 IC 也缺失）。一位根据 A100 原理图开展工作的研究者识别出 GPU 上方五颗具体的未贴装电阻（`R234` 000、`R237` NP、`R236` 1k、`R1024` 000、`R238` 000，全部位于第 17 页），以及 `R976`、`R1029`、`R1030` 和三颗 GPU 对地端接电阻。另一位参与者回忆说，“给 NVLink 供电的部分器件缺失”。
>
> 这份电阻清单来自对两块板卡的直接对比：“they are populated on a genuine A100, but missing on CMP”（这些器件在真正的 A100 上已贴装，但在 CMP 上缺失）。这是语料库中唯一一次这样的并排对比。
>
> **已贴装：** 项目自己的 VBIOS 对比表写着“NVLink bridge, external bridge absent (PCB fully populated)”（NVLink 桥：外部桥缺失（PCB 已完整贴装）），但这只是项目文档中的一行，并非实际检查结果。在电阻清单发布**前两小时**，另一位研究者说：“I do not believe there are any missing NVlink components. According to the schematics, the GPU die is connected directly to the edge connectors”（我不认为有任何 NVLink 器件缺失。根据原理图，GPU 晶片直接连接到边缘连接器），并把混淆归因于桥中含有主动元件，“including a ROM chip”（包括一颗 ROM 芯片）。后一项前提本身也已被推翻：下面失败路线 #10 记录的直接检查发现，A100 桥上没有 EEPROM。
>
> **复杂之处：** A100 原理图本身就把 `R237` 标为 **NP**（未贴装），因此五颗电阻中至少有一颗在真正的 A100 上也应当缺失。这说明仅凭肉眼对比很容易误判，也正是结论只能停留在“leans depopulated, one direct comparison, unrebutted”（倾向于未贴装、有一次直接对比、尚未被反驳），而不能算作定论的原因。没有人为了留下可复核记录而拍摄过两块板卡的这一整片区域。

---

## 拓扑和带宽：等它真正有用时再看

记录这些信息，是为了避免后来者重复推导，也因为流传中的几个数字并不正确。

| 量 | 值 | 置信度 |
|---|---|---|
| A100 PCIe 支持的拓扑 | 2 个 GPU，三块桥全部必需 | 高 |
| A100 每块桥的带宽 | 200 GB/s | 高 |
| A100 两两连接总带宽 | 600 GB/s | 高 |
| Ampere 端口结构 | 4 个子端口 x 每个 4 条通道、每通道 50 Gbps，资料称每个端口 200 Gbps；但 4 x 4 x 50 等于 800 Gbps，因此端口拆分方式和该数字不可能同时正确 | 中等 |
| GA102（RTX 3090）第三代每条链路 | 双向 14.0625 GB/s，四条 x4 链路 | 高 |
| GA102 总带宽 | 双向 56.25 GB/s，两个 GPU 之间总聚合带宽 112.5 GB/s | 高 |
| NVSwitch | 仅用于 SXM 平台（例如 DGX）；8 路 | 高 |

目前有三种比值说法在流传，但没有一种能被干净地定论。频道将 A100 与 3090 的比值定为 **3x**（600 对 200 GB/s），但 NVIDIA 文档给出的 GA102 数字是总聚合 112.5 GB/s，因此比值应为 **5.33x**。同一场讨论中，对 3090 引用的 200 GB/s 被描述为“200 GB/s-class bridges downclocked”（200 GB/s 级别的桥降频后的数值），这说明 3x 比较采用了错误的统计口径。两种解读都同意，早先“A100 的 NVLink 带宽是 3090 的 6 倍”这一说法是错误的。要解决争议，需要明确说明 A100 的 600 GB/s 究竟是单向带宽求和，还是总聚合带宽。

> [!NOTE]
> **未解问题：2 路还是 4 路无源连接？**
>
> 三个连接器恰好是四节点全连接网格所需的节点度；每条边 200 GB/s，跨三条边就是每卡 600 GB/s 的聚合带宽，在算术上与两两连接的数字一致。因此，4 路在几何结构上是自洽的。**尚未确立**的是：NVIDIA 的驱动或固件是否会在 PCIe GA100 上让链路与三个不同的对端完成训练。没有文档这样描述，也没有人演示过。两种说法讨论的是不同问题（几何结构与受支持配置），所以两者可能同时成立。

> [!WARNING]
> **不要按 320 GB 这个数字为构建方案规划容量**
>
> 一场 4 卡 NVLink 讨论曾为四张 10 GB 卡引用 320 GB 的共享显存池，这相当于假设每卡有 80 GB。发布版解锁器给 10 GB 卡提供的是**40 GB**，因此四张卡合计为**160 GB**；四张解锁后的 8 GB 卡合计为**256 GB**。80 GB 配置曾经被尝试过，但结果不稳定：参见[80 GB 尝试](80gb.md)。

---

## PCIe 点对点回退路径

由于 NVLink 无法使用，PCIe P2P 是目前唯一有可能工作的跨 GPU 加速路径。它不在 cmpunlocker 中：在 `master` 和所有分支中搜索 `p2p` 与 `peer`，只命中 `build.sh` 安装列表里的出厂 `nvidia-peermem.ko`，以及 `0008` diff 中一行未修改的上下文（`nv_uvm_resume_P2P(pUuid)`）。没有任何分支包含 P2P 启用逻辑。

候选方案是 `tinygrad/open-gpu-kernel-modules` 的一个社区 fork，其默认分支为 `610.43.03-p2p`，**使用的驱动版本与 cmpunlocker 目标版本相同**。`HEAD~3` 是提交 `452cec62d827` “610.43.03”（2026-07-07），只是一次普通的 NVIDIA 发布版导入。其上方还有三个提交：

| 提交 | 内容 | 大小 |
|---|---|---|
| `9fb650447c7b` | 组合 P2P 修改 | 8 个文件，+83/-28 |
| `52670f7fd6a7` | 实验性巨页 `cudaHostRegister` 加速 | 7 个文件，+383/-97 |
| `2849449f8cd6` | README | +245 |

P2P 提交修改了 `install.sh`（+7）、`kernel-open/nvidia-uvm/uvm_gpu.h`（+7）、`kernel-open/nvidia/nv-reg.h`（+1/-1）、`src/nvidia/generated/g_kern_bus_nvoc.c`（+5/-5）、`src/nvidia/src/kernel/gpu/bif/kernel_bif.c`（+3/-3）、`src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c`（+10）、`src/nvidia/src/kernel/mem_mgr/io_vaspace.c`（+11/-10）以及 `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c`（+39/-9）。它会在没有 NVLink 的 GPU 上启用 BAR1 P2P；如果存在 NVLink，则回退到 NVLink。对于 PCIe 连接的 GPU 对，传输会通过 DMA 直接写入另一颗 GPU 的物理地址。

> [!WARNING]
> **实验性：GA100 不在支持列表中**
>
> 该分支列出了 RTX 3090（有 NVLink 时使用两两 NVLink，否则使用 PCIe BAR1）、RTX 4090 和 RTX 5090。**GA100 不在列表中，而且该补丁从未在 170HX 上测试过。** P2P 路径涉及 `kern_bus_gp100.c`、`io_vaspace.c` 和 `nv_gpu_ops.c`，因此 GA100 对应的代码路径可能根本不存在。

> [!CAUTION]
> **只取 P2P 提交，不要取巨页提交**
>
> `52670f7fd6a7` 为 `cudaHostRegister` 加速；对于由 1G 巨页支持的缓冲区，它声称可以提升约 5000 倍，并会缩小这类映射的设备页表。作者说明该功能会自动启用，而且“this path skips some of the per-4K-page bookkeeping the stock driver performs, so it may misbehave in edge cases the stock driver handles correctly”（这条路径跳过了出厂驱动执行的部分逐 4K 页记账，因此在出厂驱动能正确处理的边缘情况下，它可能出现异常）。应将它视为独立于解锁补丁之外的额外不稳定来源。

该分支文档要求的配置步骤是：在 `GRUB_CMDLINE_LINUX_DEFAULT` 中加入 `amd_iommu=on iommu=pt` 或 `intel_iommu=on iommu=pt`，执行 `update-grub`，安装 610.43.03 驱动，运行 `./install.sh`，然后重启。IOMMU 必须处于**直通**模式而不进行地址转换，否则 DMA 会经过 IOMMU 页表，传输就会失败。README 明确警告，这种配置“very dangerous if you run untrusted software or devices”（如果运行不受信任的软件或使用不受信任的设备，会非常危险）。如果 P2P 速度很慢，可能是根端口上的 ACS 强制所有 GPU 到 GPU 的流量经过 CPU 根复合体；可以在 BIOS 中禁用 ACS，使用 `pcie_acs_override=downstream,multifunction`，或者应用 ACS 覆盖内核补丁。

完整说明见[P2P](p2p.md)。

---

## 真正能推动问题进展的事项

按可操作性从高到低排列。只有前两项成本较低。

### 1. 执行那次从未有人执行过的写入

在全部 31 个归档解锁器附件和每一份净室工作产物中，NVLink 只以熔丝读数的形式出现。没有探测脚本，没有覆盖尝试，也没有任何已记录的写入。只需在一张可牺牲的卡上，对 `CTRL_OPT_NVLINK`（`0x008209B8`）和 `CTRL_OPT_PERLINK`（`0x00820820`）进行一次读-写-读探测，然后重新读取 `STATUS_OPT_NVLINK`（`0x00820DB8`）。

> [!CAUTION]
> **只能写入可牺牲的卡**
>
> 这些是安全熔丝影子寄存器。关于写入它们的普遍警告，正是迄今无人尝试的明确原因。预期结果是写入被丢弃，状态保持为 `0x00000007`。即便得到的是否定结果，也值得记录，因为当前语料库甚至无法说这件事曾经被尝试过。

### 2. 拍摄 NVLink 器件区域

为一张拆除导流罩的 170HX 拍摄高分辨率照片，覆盖设计编号 `R234`、`R236`、`R237`、`R238`、`R976`、`R1024`、`R1029`、`R1030` 周围的区域，并与真正的 A100 并排对照；随后检查 NVLink 边缘金手指到 BGA 球 `F1` 和 `G1` 的连通性（`R1029`/`R1030` 在晶片边缘连接到这些球，可以用细线接触）。这项工作成本低、结论性强，只需要一张卡和一次导流罩拆除。维护者早在 2026-07-19 就将其列为实际上的第一步，但至今仍没人完成。

### 3. 追踪 DevInit 对 `0x820684` 的读取

`0x820684` 位于 DevInit 访问清单中。没有人沿着反汇编追踪这次读取，确认其结果之后是否被写入某处，还是仅被消费。如果 OTP 熔丝与状态寄存器之间存在一个可以欺骗的消费方，线索就在这里。这条路线只受工作量限制，同时也会撞上曾经阻挡 PCIe 熔丝层分析的那堵墙。

### 4. 将 3 bit 禁用字段与 12 条物理链路对应起来

`FUSE_NVLINK_DIS[2:0]` = `0x7`，而 `PTOP_SCAL_NUM_NVLINK` = 12；与此同时，虽然 `STATUS_OPT_NVLINK` 被标注为 16 bit 字段，它也读为 `0x00000007`。**工作假设（尚未确认）：** 12 条链路由三个链路组组成，每组四条（12 = 3 x 4）。这可以解释反复出现的 “all groups”（所有组）措辞，也可以解释 RTX 3080 的 `PTOP_SCAL_NUM_NVLINK` 为 `0x4`、而禁用值为 `0x1`。语料库中没有任何证据确认这一点。要解决它，可以探测一张已知只裁剪了部分 NVLink 的 A100，或者找到 NVIDIA 关于 GA100 上 `NV_FUSE_OPT_NVLINK_DISABLE` 字段宽度的文档。

### 5. 插上一块桥，看看会发生什么

这是唯一一项从未有人进行过的经验测试。语料库中从来没有人同时拥有一张 170HX 和一块 A100 NVLink 桥。准备一块桥，进行一次导流罩改装（或者使用能露出该区域的水冷头），然后运行 `nvidia-smi nvlink` 并检查 dmesg。考虑到熔丝状态，预期结果是否定的；但目前的语料库甚至无法确认连接器是否能够正确对齐。

### 6. 制造 interposer

在第 5 项得到阳性结果之前没有意义，应降低优先级。

### 7. 真正绕过熔丝

目前没有任何可直接实施的方案。进展还受到潜在贡献者手里没有卡的限制：“I wanted to work on it but I cant get any cards. So you have to wait until someone else figures it out.”（我想研究它，但弄不到任何卡。所以只能等别人把它搞清楚。）

---

## 立场如何变化

| 时期 | 当时的判断 | 后来被什么取代 |
|---|---|---|
| 2023-10-25 到 2026-05-07 | NVLink 不受支持，因为硬件缺失（拆解：金手指存在、器件未贴装） | 实测熔丝结论：晶片按 12 条链路缩放，没有链路被标记为有缺陷，禁用状态来自读为 `0x7` 的 OTP 熔丝。对于硅片实际认为的状态，直接 BAR0 回读比照片拆解更有说服力。注意，这两种说法**并不互斥**；器件是否贴装仍是未解问题 |
| 2026-05-31 | 这颗熔丝可能是值得攻击的挖矿 SKU 限制 | Drive A100 32 GB 读出完全相同的 `0x7`/`0x7`，说明这是通用的 GA100 产品分区 |
| 2026-05-31 起 | “NVLink killed, CTRL_OPT override path under investigation”（NVLink 已被禁用，正在调查 CTRL_OPT 覆盖路径；这句话仍印在 VBIOS 对比表中） | 同一份文档后来又以 `FUSE_EN_SW_OVERRIDE` = `0x0` 推翻了它：“CTRL_OPT fuse override disabled, cannot be changed, inert on 170HX”。参考表内部自相矛盾，但熔丝测量结果更可信 |
| 2026-07-07 到 2026-07-10 | A100 有一种廉价的 4 卡主动式 NVLink 底板 | 实际只有两两连接拓扑；NVSwitch 仅存在于 SXM 平台 |
| 2026-07-18 到 2026-07-21 | A100 桥包含主动电路（时钟发生器、EEPROM） | 直接检查结果：只是裸 PCB |
| 2026-07-19 | “it has triple (200GB/s?) NVLink, so PCIe is a non-issue” | 被追问“doesn't work though, right?”后在当天自行撤回 |
| 2026-07-20 | 阻塞因素是“cracking some kind of security-by-design architecture using encryption named HULK” | 被网站维护者和页面作者本人否定。从未发布过替代解释 |
| 2026-07-19 到 2026-07-27 | “worth trying, probably just a bridge”（值得尝试，大概只需要一块桥） | “Might need to consider the state of NVLink, it's a lot harder than I thought to get working”（可能得认真考虑 NVLink 的现状，它比我想象中难得多）。第一步被重新定义为先改造外壳以获得物理访问，再拍摄器件区域。有人要求在一个月和一年之间做选择时，得到的回答是：研究完成前无法给出任何定论 |

---

## 实测值

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| `FUSE_NVLINK_DIS` `0x00820684` | `0x00000007` | 两张 170HX；Drive A100 32GB（PG199） | 高 |
| 同上 | `0x00000000` | A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A5000、A6000、RTX 3090、RTX 3090 Ti | 高 |
| 同上 | `0x00000001` | RTX 3080、RTX 3080 Ti | 高 |
| `STATUS_OPT_NVLINK` `0x00820DB8`（RO） | `0x00000007` | 两张 170HX；Drive A100 | 高 |
| `FUSE_NVLINK_DEFECTIVE` `0x0082068C` | `0x00000000` | 每张被探测的卡；在 15 卡调查中，所有成功返回数值的卡均为 `0`，A16 和 ES 列除外 | 高 |
| `FUSE_NVLINK_DIS_CP` `0x00820688` | `0x00000000` | 每张被探测的卡 | 高 |
| `OPT_SECURE_NVLINK_MASK_WR_SECURE` `0x00820704` | GA100 `0x00000005` / GA10x `0x00000085` | 清晰的架构分界 | 高 |
| `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE` `0x00820BD4` | `0x00000001` | 探测过的全部 14 张 Ampere 卡都相同 | 高 |
| `FUSE_NVLIPT_RST_DIS` `0x00821100` | `0x00000000` | 每张被探测的卡 | 高 |
| `CTRL_OPT_NVLINK` `0x008209B8` | `0x00000000` | 每张被探测的卡，包括 170HX | 高 |
| `CTRL_OPT_PERLINK` `0x00820820` | `0x00000000` | 170HX | 高 |
| `PTOP_SCAL_NUM_NVLINK` `0x0002246C` | `0x0000000c`（12） | 两张 170HX、全部 A100 SKU、Drive A100 | 高 |
| 同上 | `0x00000004`（4） | A10、A5000、A6000、RTX 3080/3080 Ti/3090/3090 Ti | 高 |
| 同上 | `0x00000000` | 仅 A16 | 中等 |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000`（170HX 和数据中心 GA100）/ `0x00000001`（消费级部件和 ES） | 高 |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | 所有卡 | 高 |
| `FUSE_FEAT_OVR_DIS` `0x008203F0` | `0x00000000` | 所有卡；主覆盖禁用熔丝**没有**被烧断 | 高 |
| 未签名 FwSec VBIOS 尾部 | `0x43A00`-`0x47700`，MAC 范围之外的 15,616 字节 | `0x47341` 处有一个 25 项 `NV_FUSE_CTRL_OPT_*` 表，在 13 张 GA100 卡上全部为零 | 高 |
| DevInit 对 NVLink 熔丝的读取 | `0x820684` 出现在 `0x1482xxxx` 访问清单中 | 只读，从未写入 | 中等 |
| `nvidia-smi nvlink` 输出 | “Device does not have or support Nvlink.” | 一台租用的 8 卡 64 GiB 主机，2026-07-24，GPU 名称已打码；语料库中唯一一次捕获 | 中等 |
| dmesg 中的 NVLink 行 | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` | 无害，只表示软件核心加载 | 高 |
| 发布版 `master` 中的 NVLink 引用 | 0 | 全树搜索 | 高 |
| 全部 12 个分支中的 NVLink 引用 | 两个 README 表中出现 1 个词 `Planned` | 任何地方都没有代码 | 高 |
| 4 张解锁后的 10 GB 卡共享显存池 | 160 GB（4 x 40960 MiB） | 发布版 `constants.yaml` | 高 |
| 4 张解锁后的 8 GB 卡共享显存池 | 256 GB（4 x 65536 MiB） | 发布版 `constants.yaml` | 高 |
| A100 桥的市场价格 | 每块约 200 EUR；一个受支持的 A100 两卡组合需要三块桥 | 2026-07-26 市场调查 | 中等 |
| 估计的 NVLink 走线频率 | 37 GHz（机器生成的 EM 模拟器）对比约 60 GHz（二手信息） | 两者冲突，且都不是从 50 Gbps 通道速率推导出来的 | 低 |
| 2x RTX 3090 vLLM TP、27B 模型 | 使用 NVLink 时吞吐量提升约 10% | 一手数据，单个测试者 | 中等 |
| 2x RTX 3090 vLLM、已发布的第三方数据 | 输出 715 对 483 t/s；吞吐量 6,790 对 4,583 t/s | 未说明模型、量化方式和批处理设置，因此不能与上一项直接比较 | 中等 |

> [!NOTE]
> **对照组注意事项**
>
> 在参考表中，A16 列的每一行 NVLink 熔丝都读到占位符 `BAR0`。因此，上文“所有卡上”的说法，在涉及熔丝的行中都应理解为排除 A16。A16 是唯一一个报告 NVLink 缩放数量为零的 Ampere 部件，但它实际的禁用熔丝状态从未被捕获。

---

## 参见

- [NVLink 硬件](../hardware/nvlink-hardware.md)：查看连接器和板卡细节
- [熔丝与 OTP](../hardware/fuses-and-otp.md)：查看完整的熔丝对照组和方法论
- [算力节流](../unlock/compute-throttle.md)：查看确实可工作的 `FEAT_OVR` 路径
- [PCIe Gen3 和 Gen4](pcie-gen3-gen4.md)：查看另一个由熔丝门控的前沿问题
- [P2P](p2p.md)、[状态板](status-board.md)、[未解问题](open-questions.md)
