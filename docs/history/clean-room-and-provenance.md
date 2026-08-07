# 净室逆向工程与来源溯源问题

## 本页覆盖内容

CMP 170HX 解锁是在一套明确的净室逆向工程规则下开发的。这套规则要回答的核心问题只有一个：在不接触 2022 年 2 月 LAPSUS$ 泄露的 NVIDIA 材料的前提下，能否独立产出最终代码。本页记录净室工作的组织方式、适用规则、允许使用的输入、当时的来源溯源评估及其推理依据、后来的字节级比较结果，以及一份泄露的私有概念验证如何在 2026-07-18 进入整个事件。

下面的一切都由两个结果主导。

1. **发布版 ROP 载荷中的每个常量，除一个之外，都已经追溯到早于发布版补丁的、带日期的公开工件或净室派生工件。** Gadget 地址来自 2026-07-01 发布的解密调试版 Booter 反汇编，gadget 语义来自 2026-07-10 发布的自动生成图谱，DMEM 栈帧网格来自 2026-07-15T04:47Z 的公开 git 提交，缓冲区、守卫、填充值和大小常量来自 2026 年 6 月的学术预印本。唯一例外是载荷偏移量 `0x1100`（`D[0x1900]`）处写入的 `0x00000007`，没有任何早于该补丁的带日期工件能够解释它。载荷中的其他内容都不需要依赖泄露材料来推导。
2. **发布版 `cmpunlocker` 驱动补丁集逐行对应泄露的 `patch.diff`，**只是增加了 10 GB 双几何布局支持并移除了一处有害改动，而且是在 `patch.diff` 发布 70 分钟后才被采用。原则上可以推导出来，和实际上就是通过推导得出，并不是一回事；现有材料无法确定究竟发生了哪一种情况。

本页同时报告这两方面，完整陈述双方提出的论据，到此为止。它不提供法律结论，也不在任何地方点名个人。代码本身见[六个驱动补丁](../unlock/driver-patches.md)和[ROP 链](../unlock/rop-chain.md)；日期见[项目时间线](timeline.md)。

---

## 为什么一开始需要净室工作

解锁工作并不是从净室逆向工程开始的。它于 2026 年 3 月起步于一个公开的 GitHub issue 跟踪器，2026 年 4 月转移到 Discord 服务器，到 2026 年 5 月已经得到决定性的密码学结果，使 AES 加密、RSA 签名的 `booter_load` 代码变得可读。2026 年 6 月，团队演示并公开宣布了一条能够跳转到该代码内部任意地址的 ROP 链。随后，开发转移到一个由**七人**组成的私人群组，产出了概念验证、日期为 2026 年 6 月的学术预印本，以及两份内部**驱动修改指南**（一份针对算力，一份针对显存）。

这个私人群组做出了两个影响此后所有工作的决定：

- **发表论文、暂不公开利用代码**，等待独立复现。
- **删除原始 Discord 服务器**，理由是其中可能包含从 NVIDIA 泄露的材料。

净室工作由此建立，目的是只使用能够证明来源的输入，从头复现被暂不公开的结果。它要管理的风险就是 LAPSUS$ 泄露：按照后来来源溯源评估的描述，这起发生于 2022 年 2 月至 3 月的事件泄露了约 **1 TB** 的 NVIDIA 数据，其中包括 GPU 驱动源码、内部硬件文档和固件签名密钥。泄露缓存至今仍能在公开网络上定位（频道内曾点名 Internet Archive），所以这里需要一条明确规则，而不能只靠假设资料没有被看过。

---

## 规则集

治理标准自 2026-06-27 起作为频道政策发布，并在整个期间通过删除内容和威胁封禁来执行：

1. **不得讨论任何 NVIDIA 秘密信息。**
2. **只有在能够证明同一信息可以从公开来源推导出来时，相关秘密知识才可采信。**
3. **发布泄露或非法材料将被封禁。** 这明确包括泄露源码、泄露原理图，以及从已删除的早期 Discord 带过来的任何文件。

2026 年 6 月的预印本被指定为**唯一的净室输入文档**，理由有两个：它发布在科学出版物网站上，并且已经发送给 NVIDIA。

第 2 条是整套规则真正的支柱，也是 2026-07-18 事件给压力最大的那一条。见下文[两种读法，尚无定论](#two-readings-unresolved)。

---

## 净室与非净室：设想与实际

第一天就有人提出双团队分工。设想中的组织原则很常规：由一个**非净室（dirty-room）团队**执行逆向工程，只产出不含非法内容的文档；另一个没有接触过其他材料的**净室团队**，只依据这些文档重新实现结果。

这个分工后来基本被放弃。实际形成的是**频道隔离，而不是团队隔离**：

| 设想 | 实际发生的情况 |
|---|---|
| 隔离的非净室团队执行 RE 并编写规格说明 | 源集中的文档没有任何一份把“dirty room”作为实际运作的团队 |
| 未接触受限材料的净室团队只依据规格实现 | 同一批人跨频道工作 |
| 通过团队成员资格强制隔离 | 通过频道主题和采信规则强制隔离 |

实际存在的频道包括只传递工作数值的 `#general-how-to-cleanroom` 指南频道，以及更深入的技术频道，后者承载寄存器扫描、Falcon 退出路径分析和 DMEM 栈探索。对这一描述的置信度为**中等**：档案逐字引用了当初的意图，频道结构也可以直接观察到，但没有证据表明双团队协议曾真正配备人员运行。

---

## 净室输入语料库

净室允许自己建立在以下输入之上，并为每一项给出了相应理由：

| 输入 | 被视为干净输入的理由 |
|---|---|
| **"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"**，2026 年 6 月，Zenodo 记录 `20916112`，ResearchGate 出版物 `408132536`，共 16 页 | 发布在科学出版物网站上，并已向厂商披露。被指定为唯一的净室输入文档。2026-06-26 开始传阅；2026-07-16T06:07:12Z 以 `main.pdf` 的文件名贴入净室服务器 |
| `NVIDIA/open-gpu-kernel-modules`（标签 `610.43.02`、`610.43.03` 以及更早的 `580.x`） | NVIDIA 自己发布的源码 |
| **调试版** `booter_load` 二进制 | 它作为 C 数组编译进 NVIDIA 自己的 `.ko`，并以 `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c` 的形式发布在 open-gpu-kernel-modules 树中。使用 Nouveau 固件提取工具（已针对 GA100 打补丁）提取。摸索出这条路径花了群组两天时间 |
| NVIDIA 的**公开 AES-128-ECB 测试密钥** | 来源是 NVIDIA 公开的 Jetson Secure Boot 文档。密钥由 MD5 初始化向量 `...0123456789abcdef...` 和作为最后一个字节的密钥编号构成。频道内发布了一个不含任何 NVIDIA 材料、自包含且属于公有领域的 Rijndael 解密器和密钥验证器（`rijndael-tool.zip`） |
| **GA100 熔丝与寄存器参考表**：15 张 Ampere 卡上的 120 个寄存器 | 完全通过只读 MMIO 探测参与者拥有或租用的硬件得出。见[熔丝与 OTP](../hardware/fuses-and-otp.md) |
| 从卡本身以及 A100 对比部件读取的 BAR0 寄存器 | 对自有硬件进行的设备侧测量 |

频道内形成的加密问题判断非常明确：NVIDIA 的错误**不是**使用了简单的测试密钥，而是**在调试分支和生产分支中发布了完全相同的二进制**，并且为一个存在严重漏洞的二进制签名。

### 15 卡差分语料库

寄存器级的来源溯源论证建立在下面这张表上。它比较了 `tools/mmio-probe/probe.sh` 读取的 120 个寄存器，样本包括：

- **2 × CMP 170HX 10 GB**，实物卡，分别于 2026-05-05 和 2026-05-07 探测
- **通过 GPU 租赁服务商租用的 11 张卡**：A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A16、A5000、A6000、RTX 3080、RTX 3080 Ti、RTX 3090、RTX 3090 Ti。（熔丝表中有一列是工程样品部件，但该列的任何行都没有数值。）
- **2 × Drive A100 32 GB**（`GA100-550F-A1`、PG199），实物卡，于 2026-05-31 探测

恰好有五组寄存器能够区分同一晶片上的 170HX 与 A100：SM 速度选择、PCIe 引导代际、NVLink 禁用、ECC 启用以及 FBPA CFG1 几何布局。

两张实物 170HX 卡在关键寄存器上也被证明完全一致：**120 个寄存器中有 107 个逐字节相同**，其余 13 个差异全部属于按晶片变化的分档伪影，包括熔丝裁剪掩码及其 FBIO/STATUS 镜像、每张卡各自的 `FEAT_OVR_SM_SPD` 编码、`FEAT_OVR_QUADRO`、HBM 晶片身份寄存器，以及跟随熔丝裁剪结果变化的每-FBPA 回读值。每一条限制熔丝都完全匹配。这个结果使得把一张卡上推导出的配置方案推广到另一张卡成为合理做法。

---

## 寄存器值的来源标准

2026-07-02，频道内接受了以下说法，作为发布目标寄存器集合的依据：

> 显存几何布局来自 VBIOS 和 BAR0 地址空间读取；至于其他一切，都可以把一张 A100 的 BAR0 输出与一张 170HX 的输出做差分，然后把所有值改成 A100 的值来推导。

生成干净的 `booter_load` 汇编时，只使用了 NVIDIA 的开源驱动数据和 NVIDIA 的公开测试密钥。120 个寄存器的跨变体熔丝表为这一主张提供了独立支撑：它直接展示了 A100 与 170HX 之间的差异，没有引用任何内部文档。

---

## 关键技术事实：调试版在关键处等同于生产版

整套净室工作方法依赖一个实证结果。如果 `booter_load` 的 `-debug` 编译版本包含额外字节，那么从可读的调试反汇编中得到的每个 gadget 地址都会发生偏移，在生产晶片上也就无法使用；要得到正确偏移量，唯一途径将是无法解密的生产二进制，或者泄露的源码。

这个疑虑于 2026-07-02 被提出，并在同一时期通过两种方式被推翻：

- 调试版和生产版二进制的大小**完全相同**。
- 完全依据调试反汇编构建的 ROP 链**在生产晶片上正确执行**。

> [!NOTE]
> **未解问题**
>
> “大小相同，再加上一条成功执行的链”只能证明这个具体实例成立，不能证明两者在构造上等同。源集中的文档没有记录对 `IMAGE_DBG` 和 `IMAGE_PROD` blob 进行实际字节级比较，而 bindata 档案使这项比较非常容易完成。只要对 `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c` 中的两个条目计算哈希即可定论，但从未有人发布过该哈希。

另一个相关争论是：只要触碰 GSP 签名，是否就已经破坏了净室工作的干净性。一方认为，篡改签名按定义就会使结果不干净。反方的观点没有被驳倒：面向返回编程只复用已存在于签名二进制中的代码，不需要访问 NVIDIA 源码，因此从合法解密的二进制构建 ROP 链仍然是干净的；唯一可能不干净的元素是载荷本身，前提是它被复制而不是推导出来的。生产版 Booter 从未被修改：每个可工作的工具都会加载未修改的签名映像，只在 `PATCH_LOC 0x8900` 将分离出来的 384 字节签名重新拼接回去。

---

## 2026-07-18 的来源溯源评估

一份标题为 **"Assessment: Is patch.diff Derived from LAPSUS$-Leaked Information?"** 的文档于 **2026-07-18T18:40:16Z** 发布，恰好是 `patch.diff` 于 **2026-07-18T18:01:15Z** 发布 **39 分钟**之后。两个时间戳都由 Discord 消息 snowflake 解码到毫秒级。

**范围。** 针对 `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03` 的补丁。

**净室来源语料库，恰好三项，不多不少：**

1. `paper.md`（Canary 预印本）
2. `how_to.discord.html` 和 `discussion.discord.html`，即净室服务器两个频道的导出转写
3. `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03`

评估者无法取得泄露缓存进行比较；评估报告本身也把这一点列为其结论的限制。

**方法。** 将补丁与这三个来源进行比较，然后把补丁干净地应用到克隆的仓库上，在上下文中检查结果。

**裁决原文：** “The available evidence does not support a conclusion that this patch is derived from LAPSUS$-leaked information.”（现有证据不足以支持“该补丁源自 LAPSUS$ 泄露信息”这一结论。）

### 评估将哪些内容归类为干净

| 类别 | 内容 | 记录在案的裁决 |
|---|---|---|
| **干净，来自论文**（九个概念） | 栈金丝雀引用字漏洞（§5.1-5.3，Thesis 1）；通过无界签名长度复制触发的 DMA 溢出（§3.2，§5.5）；通过签名 Booter 进入 SEC2 Falcon HS 模式（§2.2，§5.4）；统一填充值 **V = `0x4a7`**（§5.5，仿真器轨迹）；溢出签名大小 **SIGSZ = `0xf800`**（§5.5）；HS 代码执行后的枢轴——解锁 PLM（§6.1）；特性覆盖影子寄存器概念（§2.1）；来自 HS 的 WPR2 teardown（§8.5）；以 GPU 为防御者、已取得 root 权限的主机为攻击者这一颠倒的威胁模型（§2.3） | “Clean. These concepts are fully documented in the paper and require no special access.”（干净。这些概念在论文中都有完整记录，不需要特殊访问权限。） |
| **干净，来自开源驱动树**（内核内部 API） | `memdescCreate`、`memdescMapInternal`、`memdescFlushCpuCaches`、`memdescGetSize`、`memdescGetPhysAddr`；`pmaRegisterRegion`、`pmaGetRegionInfo`、`pmaGetFreeMemory`、`pmaGetTotalMemory`；`MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`；`os_open_and_read_file`；`kgspExecuteBooterLoad_HAL`、`kgspPopulateWprMeta_HAL`；`FB_REGION_DESCRIPTOR`、`PMA_REGION_DESCRIPTOR`；`NV_FLAG_PERSISTENT_SW_STATE`；`GPU_REG_RD32`/`GPU_REG_WR32`；`NV2080_CTRL_CMD_FB_GET_FB_REGION_INFO_PARAMS` | “Clean. Any competent kernel module developer can discover these by reading the source.”（干净。任何称职的内核模块开发者都能通过阅读源码发现这些。）每个具名符号都存在于发布版补丁集中 |
| **干净但较早**（八项内容，存在于日期为 2026-07-09 至 2026-07-17 的公开转写中） | 特性覆盖地址 `0x823804`、`0x82381c`、`0x823820`、`0x9a0204`、`0x100ce0`；WPR2 寄存器 `0x1fa824`/`0x1fa828` 以及作为阻碍因素的 WPR2 carve；FB 几何布局 PLM 地址 `0x100b10`/`0x100b38` 和 `0x9a0148`/`0x9a014C`/`0x9a0108`/`0x9a010C`；将 `0x8403C4` 用作 `resetPLM`；三个具名退出策略（`secure_teardown`、提前退出 `0x8117`、`multiwrite_then_mutexfree_cleanexit`）；某些寄存器在 FLR 后仍然保持；用于直接控制 SEC2 的非安全 ucode 加载器；从 `D[0xFFC4]` 到 `D[0xFFF0]` 的 DMEM 栈探索 | “Clean, but overlapping.”（干净，但存在重叠。） |

表格中有一处引用是错误的。“WPR2 teardown from HS”被对应到论文 §8.5；但 §8.5 的标题是 “Persistence across FLR”（跨 FLR 的持久性），论证的是保存在常电域中的覆盖值如何把一次短暂利用变成持久状态。该节既没有讨论 WPR2 teardown，也没有讨论 ROP。论文中唯一提到 ROP 的地方是 §5.5 的一条引用。实际影响是，发布版补丁在每次 Booter 运行前后显式保存和恢复 WPR2 的做法，并没有像表格暗示的那样得到论文覆盖。评估报告另外正确地把 WPR2 处理归因于公开转写，因此这是引用错误，而不是实质性错误。

### 评估报告关于外部来源的三个论据

以下内容被记录为论据，而不是事实。

1. **负面证据。** 补丁不包含 NVIDIA 内部代码注释、不含泄露构建中具有识别性的变量名、不使用泄露的签名密钥（利用过程没有伪造签名），也不包含那些无法通过 BAR0 探测发现的内部专属寄存器名。论文的伦理声明直接印证了关键一点：“We extracted no signing keys and forged no signature.”（我们没有提取签名密钥，也没有伪造签名。）
2. **大锤论证。** `patch.diff` 在 `subdevice_ctrl_gpu_regops.c` 的 `gpuValidateRegOps` 中插入 `return NV_OK;` 作为第一条语句，使原函数体变成死代码。它是无条件的，影响所有 GPU，而不只是 CMP 170HX，并且完全关闭了控制面板的寄存器读写校验。由此提出的推断是：“The sledgehammer approach suggests an external developer who needed a quick bypass and didn't care about collateral damage to other GPUs or security... An internal NVIDIA engineer or someone with leaked docs would likely make a surgical change.”（这种大锤式做法说明开发者是外部人员，需要快速绕过限制，并不在意对其他 GPU 或安全性造成附带损害……内部 NVIDIA 工程师或持有泄露文档的人更可能进行精准修改。）
3. **伪装式命名。** `SEC2_DEBUG_PRI_*`、`kgspSec2PostblTiming*` 和 `SEC2_DEBUG` 日志前缀在 NVIDIA 代码库中无处存在，“PostBL Timing”是一个听起来合理、实际却虚构的功能名称。整体方案看起来像是试图把利用代码伪装成合法的生产或调试功能；对于拥有合法访问权限的人来说，这种伪装“would be unnecessary for someone with legitimate access”（没有必要）。发布版代码逐字保留了这些命名，并在 `0002-booter-verify.patch` 中定义了 `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM 0x00823804`、`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED 0x0082381c`、`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820`、`SEC2_DEBUG_PRI_FBPA_CFG1 0x009a0204` 和 `SEC2_DEBUG_PRI_MMU_LMR 0x00100ce0`。

> [!CAUTION]
> **`gpuValidateRegOps` 绕过不在发布版工具中**
>
> 这个无条件绕过确实存在，而且很严重：任何拥有 `NV_GPU_REG_OP` 访问权限的进程，都可以在机器上的任意 NVIDIA GPU 上读取或写入任意 GPU 寄存器。它**只存在于泄露的 `patch.diff` 中**。发布版 `cmpunlocker` 补丁集完全没有修改 `subdevice_ctrl_gpu_regops.c`，`gpuValidateRegOps` 这个字符串也不出现在 `master` 或十二个未发布分支中的任何一个。任何把这个漏洞归咎于 `cmpunlocker` 的文字都是错误的。

### 唯一剩余的疑点

有两项内容被评为 HIGH，且当时未能排除：完整 ROP 链的 DMEM 字节偏移量（`0x1100`、`0x5b40`、`0xf754` 到 `0xf7f8`），以及把 `writeAddr`/`writeValue` 映射到 DMEM 栈槽的 gadget 链。后者被描述为 `_kgspSec2PostblTimingFillPayload` 在大小为 `0xf800` 字节的签名缓冲区内，以精确字节偏移写入 **24 个特定的 32 位值**。

当时的推理分为四点：

| # | 论据 |
|---|---|
| (a) | 论文描述了统一填充 ROP 链的概念，但没有公开特定版本的 DMEM 布局 |
| (b) | 这些偏移量与 Booter 版本有关，出错会导致崩溃（`MB0=0x31`、`IMEM_MISS_INS` 或金丝雀校验失败），而不是得到一个可工作的利用 |
| (c) | 社区当时正在探索它认为不同的偏移量范围 |
| (d) | 推导这些偏移量需要周期精确的 Falcon 仿真器和特定的 Booter 二进制、NVIDIA 内部关于栈帧布局的文档，或者泄露的 Booter 源码 |

评估报告提出的缓解理由是：论文所描述的仿真器方法足以复现这项分析。其原话是：“The ROP chain offsets are the only element that would require significant independent work to produce without leaked documentation, and the paper explicitly describes how to do that work.”（ROP 链偏移量是唯一一个在没有泄露文档时需要大量独立工作才能产出的元素，而论文明确描述了如何完成这项工作。）

数量统计是正确的：发布版载荷恰好包含 **24** 次 `_kgspSec2PostblTimingPutU32` 调用，位于载荷偏移量 `0x1100`、`0x5b40`、`0xf754`、`0xf758`、`0xf75c`、`0xf76c`、`0xf774`、`0xf780`、`0xf788`、`0xf78c`、`0xf790`、`0xf794`、`0xf798`、`0xf79c`、`0xf7a0`、`0xf7a4`、`0xf7b0`、`0xf7b8`、`0xf7c4`、`0xf7c8`、`0xf7d8`、`0xf7e0`、`0xf7f4`、`0xf7f8`。

---

## 后来的分析对剩余疑点确立了什么

疑点 (c) 和 (d) 后来都站不住脚。下面的修正来自重新阅读归档工件和发布版源码，而不是引用评估报告的内容。

### (c) 是基址偏移造成的表象

载荷通过 DMA 被加载到 DMEM `0x800`，因此**载荷偏移量 + `0x800` = DMEM 地址**。两个看似“不同”的范围其实是同一个范围：

| 补丁偏移量 | DMEM 地址 | 评估报告自己表格中的状态 |
|---|---|---|
| `0xf754` | `D[0xFF54]` | 标记为 HIGH |
| `0xf76c` | `D[0xFF6C]` | 标记为 HIGH |
| `0xf7c4` | `D[0xFFC4]` | 列为**干净但较早** |
| `0xf7f8` | `D[0xFFF8]` | 标记为 HIGH |

“干净但较早”的列表已经包含 `D[0xFFC4]` 到 `D[0xFFF0]`，覆盖评估报告标记为 HIGH 的 22 个栈槽中的四个。按照评估报告自己的记账方式，HIGH 范围的一部分早已被标记为干净。也就是说，同一个栈槽被引用时，补丁偏移量被视为可疑，而 DMEM 地址却被视为干净。

### (d) 被带日期的公开工件推翻

发布版 ROP 链中的每一个代码地址，都是净室自己解密的调试版 Booter 反汇编中的指令边界；该反汇编在补丁发布**十七天前**就已经公开。

| 工件 | 发布时间 | 提供的内容 |
|---|---|---|
| `booter_load_ga100_dbg_seccode.fuc5.asm`（545,149 B） | 2026-07-01T12:40:37Z | 原始 envydis 输出；链中的每个地址 `0x0cbd`、`0x0ccb`、`0x10aa`、`0x10b9`、`0x1fbd`、`0x582d`、`0x7f2f`、`0x815a`、`0x0d66`、`0x04d4` 都恰好对应一行指令 |
| `...annotated.fuc5.asm` | 2026-07-03T17:12:52Z | 每个函数的横幅注释 |
| `...annotated.fuc5_v2.asm`（607,702 B，11,875 行） | 2026-07-09T03:03:21Z | 每条 `lcall` 都带有说明被调用者名称的内联注释 |
| **寄存器 Gadget 图谱** | 2026-07-10T13:40:14Z | 由该反汇编自动生成。它把 `0x0cbd` 列为“`$r10 <- $r0`、canary(r15==r9)、via-call、`mpopaddret $r3 0x4`”，把 `0x1fbd` 列为“`$r11 <- $r10`、canary(r15==r9)、via-call、`mpopaddret $r2 0x4`”，与它们在发布版链中的作用完全一致，包括产生帧步长的 `mpopaddret` 尾声 |
| `cmpunlocker` 初始提交 `9b9fb2f`、`common/constants.yaml` | 2026-07-14T21:47:02-07:00 = 2026-07-15T04:47:02Z | `dmem_layout: dma_target 0x0800, payload_size 0xF800, guard_addr 0x6340, canary 0xFACEB13D`；`booter_addrs: bar0_write_gadget 0x10B9`；`payload_frames: frame_start_addr 0xFF48, frame_stride 0x18, frame_field_offsets {r0 0x00, r1 0x04, r2 0x08, r3 0x0C, saved_reg 0x10, return_addr 0x14}` |
| `ROP_CHAINS_1180f8_nibble_writeup_20260715.md` | 2026-07-15T18:48:10Z | 以文字记录了同一个网格：“N BAR0-master writes via the light `0x10b9` self-chain、**+0x18 DMEM per write**”，并把 `D[0xFF50]`、`D[0xFF54]`、`D[0xFF5C]`、`D[0xFF68]`、`D[0xFF6C]`、`D[0xFF74]`、`D[0xFF80]`、`D[0xFF84]` 列成表格 |

**发布版补丁中的全部 22 个栈槽偏移量，都准确落在这个由六个字段组成、步长为 `0x18` 的网格中的具名字段上，没有一个未对齐命中。** 24 个值中剩下的两个是守卫字（`0x5b40` 映射到 `D[0x6340]`）和 `0x1100`（映射到 `D[0x1900]`）。

其余非 gadget 常量也都有来源：`0xf800`、`0x800`、`0x6340` 和 `0x4a7` 来自论文的仿真器轨迹，并且也在评估报告自己的“干净，来自论文”列表中；`0xc0deca7e` 是论文公开的守卫桩值；`0x5b40 = 0x6340 - 0x800` 是对论文中两个数字做的算术；`D[0xFFB0]` 处的 `0x0000ffbc` 是一个指向帧网格的自引用 DMEM 栈指针；`D[0xFF90]` 处的 `0x00008e18` 位于 Booter 代码映像之外（反汇编在 `0x86ff` 结束），它指向带注释清单中由指令行 `0x0d39`、`0x0da1` 和 `0x0e1b` 记录的寄存器描述符表区域 `0x8e04`/`0x8e08`。

### 净室自己的链与发布版链有关，但不是复制品

净室 Python 解锁器和发布版 C 链共享缓冲区基址 `0x800`、大小 `0xF800`、守卫地址 `0x6340` 以及 `0xFF48`/`0x18` 的六字段帧网格。两者有两个明显区别：

| | 净室 Python（`payload/build.py`，提交 `9b9fb2f`） | 发布版 C（`0001-sec2-postbl-plm-ss-cfg.patch`） |
|---|---|---|
| 金丝雀字面量 | `0xFACEB13D`（项目代号） | `0xc0deca7e`（论文公开的桩值） |
| 链的形状 | 一个自链接 gadget `0x10B9`，每次写入使用一帧 | 经过 `0x0cbd`、`0x1fbd`、`0x815a`、`0x582d` 的更长链 |
| 终止符 | `0x0000810D` | `0x00000ccb`（释放 ACR 互斥锁），然后是 `0x00007f2f`，正好对应公开转写中命名的 `multiwrite_then_mutexfree_cleanexit` 策略 |

这个利用的代号 **FACEB13D** 的读音是 “fake bird”，指的是必须被击败的栈守卫金丝雀，不是 Falcon。列出的障碍包括通过隐蔽性实现安全、栈金丝雀、安全级别 L0 到 L3、不可变的引导 ROM、安全协处理器、代码的 AES 加密以及代码的 RSA 签名。

---

## 泄露的概念验证

### 重分发的安装包

净室算力解锁器发布并被克隆到 GitHub 约三天后，一个名为 “Chinese unlock” 的包出现在俄罗斯 Telegram 上。根据当时做出的评估，它是泄露的私有概念验证，而不是独立完成的工作。

多名独立审查者检查后的包结构如下：

```text
cmp170hx-unlock-610.43.03.zip
├── install.sh                              # 检查后评估为安全
├── NVIDIA-Linux-x86_64-610.43.03.run       # 与官方安装器逐字节相同
├── open-gpu-kernel-modules-610.43.03/      # 打过补丁的源码 + 预编译二进制
└── README.txt                              # 无关内容
```

将包内源码与 `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03` 做差分后，得到 `patch.diff`，大小为 **35,867 字节、887 行、涉及 11 个文件**。所有修改都局限在开源内核模块组件中，没有改动任何闭源二进制。推荐的安全处理方式是删除包内的 open-modules 文件夹，从上游执行 `git clone`，应用 `patch.diff`，重新编译，最后再运行 `install.sh`。

档案大小的报告并不一致：一份记录给出 537.2 MB，同时指出内部 `.run` 为 461.5 MB；另一份记录给出约 520 MB。此外，一个来源中出现了第二个文件名 `cmp170hx-unlock-610.43.03.tar.zst`。两个文件名可能都是真实的，即同一个载荷被以两种格式重分发。

一名同时持有这两份工件的人表示，补丁与私有驱动修改指南中的代码**逐字相同**。对于档案结构和 diff 大小，置信度为**高**（有多名审查者，且 diff 文件本身已归档）；对于“泄露而非重新发现”的归因，置信度为**中等**，因为它建立在归因存在争议的一方提供的一次字节比较之上。

独立检查还确认了重分发解锁器的两点情况：它写入的权限级别掩码表与公开仓库完全相同，没有解锁额外功能，**不会**启用 PCIe Gen2，并且只能识别 8 GB 卡（“currently this unlocker only supports 8G cards and can't recognize the 10G card”）。

### 泄露的 shell 脚本

另有一个算力解锁 shell 脚本以 `CMP170HX_Compute_Unlock_v8_3.sh` 的名称公开泄露，于 2026-07-14 被发布到一个公共 GitHub 仓库，很快又被删除。作者将其描述为“just the compute only logic that was posted here, with some minor modifications to attempt to run on multiple GPU's vs 1. Nothing new sadly”（只是这里发布过的算力逻辑，做了一些尝试让它支持多张 GPU 而不是一张的小修改，可惜没有任何新内容），实现方式是针对每张卡复制注入代码块，并写死 PCIe ID。它不包含任何显存解锁内容。

### 博客的说法

一篇报道此事的中文博客声称有两名黑客独立完成了显存解锁，并展示了一张团队 `booter_load` 代码的截图，其中函数名和注释都完全不同。不同的命名既可能来自独立完成的反汇编与注释流程（这正是净室自己的命名产生的方式），也可能来自对复制材料的重新注释。

> [!NOTE]
> **未解问题**
>
> 截图是否是利用公开提示独立解密得到的，始终没有定论。下一步应将截图中的指令地址与 `booter_load_ga100_dbg_seccode.fuc5.asm` 进行比较。如果地址与调试构建匹配，那么作者就必须使用公开的 Jetson 测试密钥对其解密，这才是干净的路径。

---

## 70 分钟的采用窗口

这是当时的来源溯源评估不可能知道的一段记录，它由 git 作者时间戳、`diff -Naur` 头部的 mtime 以及解码后的消息 snowflake 确立。

| 时间（UTC） | 事件 |
|---|---|
| 2026-07-18T18:01:15Z | `patch.diff` 发布到 `#general-how-to-cleanroom` |
| 2026-07-18T18:26:26Z | 发布版 `cmpunlocker` 补丁集中的每个文件都带有这个 `diff -Naur` 头部 mtime（`2026-07-18 11:26:26 -0700`）。同一棵代码树在同一时刻写出，距离发布 25 分钟 |
| 2026-07-18T18:40:16Z | 来源溯源评估发布，处于这个窗口的中间 |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` 在 `memory` 分支上创建，距发布 **70 分钟** |
| 2026-07-18T20:51:36Z | `6b7d9ee "FULL WORKING THING"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` 合并到 `master` |

推导方向没有歧义：在 `06fabf2` 之前，发布版仓库中**没有任何驱动补丁**，而 `patch.diff` 只支持 8 GB 的 `0x20C2` 卡。

### 两者实际有哪些差异

将归档的 `patch.diff` 中每一条新增行，与 `driver/patches/0001` 到 `0006` 的拼接结果逐条比较：

| 项目 | 数值 |
|---|---|
| `patch.diff` | 35,867 B、887 行、11 个文件 |
| `cmpunlocker` 补丁集 | 890 行、6 个补丁文件、10 个目标文件 |
| 两者字节级完全相同的新增行 | **638** |
| `patch.diff` 独有的行 | **19** |
| `cmpunlocker` 独有的行 | **43** |

`patch.diff` 独有的 19 行中，每一行要么是 `cmpunlocker` 按配置档处理的内容所对应的 8 GB 专用硬编码形式，要么是 `cmpunlocker` 增加设备 ID 的日志行，要么就是 `gpuValidateRegOps` 中的这一行：

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_PCI_DEVICE_ID 0x20C2
NvU32 cfg1Value    = 0x02779000U;
NvU32 lmrValue     = 0x0000020BU;
NvU64 targetFbBytes = 0x0000001000000000ULL;  /* 64GB */
/* 加上 devId == 0x20C2 守卫 */
```

`cmpunlocker` 独有的 43 行全部是 10 GB（`0x2082`）对应的内容：包括拆分为 `SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID 0x20C2` 和 `SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID 0x2082`、`cfg1Value = 0x02669000U` / `lmrValue = 0x0000028AU` 分支、`targetFbBytes ... : 0x0000000A00000000ULL`，以及双设备 ID 守卫。除此之外没有其他差异。这些几何值就是[显存几何布局](../unlock/memory-geometry.md)文档记录的规范值。

---

## 两种读法，尚无定论

证据之间确实存在张力，而现有源集无法解决这一点。这里完整列出两种读法，因为读者有权自行衡量它们。

=== "A 面：按净室自身规则属于干净结果"

    发布版 ROP 载荷中的每个常量，都可以从早于 `patch.diff` 的、带日期的公开材料或净室派生材料独立推导出来：gadget 地址来自 2026-07-01 发布的反汇编，gadget 语义来自 2026-07-10 发布的图谱，帧网格来自 2026-07-15T04:47Z 的公开 git 提交，缓冲区、守卫、填充和大小常量来自 2026 年 6 月的论文。净室已经在同一个网格上，使用相同的缓冲区、相同的守卫地址和相同的 `reg_write_indirect` BAR0 写入原语，独立构建出一条可工作的 ROP 链（它从 `0x10b9` 进入，而发布版链从 `0x10aa` 进入），并在四天前公开发布了这条链。按这种读法，净室遵守了自己的规则（“secret knowledge is admissible only if the same information can be shown to be derivable from public sources”，即只有能够证明同一信息可以从公开来源推导出来时，秘密知识才可采信），因此评估报告的否定性裁决是正确的，甚至低估了公开证据的支持力度。

=== "B 面：不属于干净结果"

    发布版代码不是对 `patch.diff` 的净室重新实现。它**就是** `patch.diff`，在后者出现 70 分钟后逐字采用，只移除了一处有害改动并增加了一个设备 ID 分支。原则上可以推导出来，并不等于实际上就是这样推导出来的；而按照几名参与者对净室规则的理解（“it is dirty, 100%”，即“它是脏的，百分之百”），无论其中的信息是否可以独立获得，这条规则都禁止使用该工件。材料被清除而不是经过裁决，但工具最终还是采用了这份代码。

**什么可以解决这个问题。** 现有材料中没有这样的证据。两份私有驱动修改指南可以证明 `patch.diff` 是否确实是私人群组的代码；采用代码的维护者若作出说明，则可以证明代码是复制而来，还是独立收敛写成。现有源集中两者都不存在。

> [!NOTE]
> **未解问题**
>
> 同一问题还有一个范围更小、可以实际处理的版本：补丁 `0004`（BAR0 PRAMIN 钳制）和 `0005`（CE 清理变通方案）是 `cmpunlocker` 自己原创的，还是同样存在于私有指南中？它们在 `patch.diff` 和 `cmpunlocker` 之间逐字节相同，因此是一起进入发布版的；但关于 `patch.diff` 的社区摘要只描述了签名劫持、打开 PLM、寄存器写入、重建签名、`fb_length` 欺骗和后期 PMA 扩展，没有提到 PRAMIN 钳制或 CE 清理变通方案。只有那些指南能够作出定论。

---

## 学术论文及其披露立场

这份预印本既是整个工作的唯一指定净室输入，也是其方法论基础。论文摘要称，CMP 170HX 与旗舰 A100 使用“the same die as a flagship A100 but is fuse-crippled on three commercial axes: SM math rate (throttled to 1/32), memory capacity (10 GB instead of 80 GB), and PCIe link (Gen1 instead of Gen4)”（与旗舰 A100 使用同一颗晶片，但在三个商业维度上受到熔丝限制：SM 数学速率被限制为 1/32、显存容量为 10 GB 而不是 80 GB、PCIe 链路为 Gen1 而不是 Gen4）；同时指出“all three caps are soft”（这三个上限都是软限制），并给出“roughly 31-62x compute, 8x capacity, 2x link”（算力约提升 31-62 倍、容量提升 8 倍、链路提升 2 倍）的概略增益。它与 `arXiv:2505.03782` 不是同一篇论文，后者只是它引用的参考文献 [13]。

作者有意拒绝在发表前设置禁运期。第 10 节记录称，这项工作只在单张卡上进行实验室测试，不涉及转售，不对晶片作持久性修改，不提取签名密钥，也不伪造签名；测量结束后，显卡被恢复到原生配置。厂商的产品安全团队是在**发表的同时**而不是事先获知此事。下面记录的是作者提出的理由，不代表本页认同这一立场：

> Coordinated disclosure assumes the vendor's remedy protects the user, which does not hold in an inverted threat model where the defender is the device and the adversary is its owner. A private embargo window would let the vendor burn the relevant anti-rollback fuses on already-shipped hardware, permanently removing that capability from the very users this work concerns, before those users could learn of it or act.
>
> 协调披露假设厂商的补救措施能够保护用户；但在“设备是防御者、设备所有者是攻击者”的颠倒威胁模型中，这个假设并不成立。私下设置禁运期会让厂商在已经发货的硬件上烧断相关的反回滚熔丝，在相关用户得知此事或采取行动之前，永久移除这项工作所关注的用户原本拥有的能力。

论文还描述了作者针对 Booter 指令流构建的静态检查器：它把 DMA-as-copy 摘要提升到 IR 中，把 DMA 视为污染源，在 DMA 汇点应用有界写检查（`L <= S - o`），并在感知 link-map 的布局邻接处提升告警级别。作为差分门运行时，它将开源内核时代 Booter 的签名读取传输标记为唯一的无界汇点，并在更早的 Booter 家族上以零误报通过。置信度为**中等**。该检查器没有在归档材料中发布，也没有独立方复现。

给实现者的实用脚注：论文用“3-4 BAR0 value changes”（改动 3-4 个 BAR0 值）来描述这项工作，这一表述误导了每一位独立复现者。三四次写入本身很简单，真正的难点是**先**打开四个 PLM。见[权限级别掩码](../unlock/privilege-level-masks.md)。

---

## 一宗后续法律事件

**NVIDIA 于 2026-07-17 对至少一个 `cmpunlocker` fork 发出 DMCA 删除通知**，使该仓库下线。接收通知者称通知直接来自 NVIDIA，并停止了项目的公开工作。其他人推测这是自动化过滤器触发的执法，并指出当时已经存在许多 fork；随后有人建议对 fork 重命名和重写。置信度为**中等**。报告来自当事人的一手陈述，仓库下线也可以直接观察到，但源集中没有删除通知文件。本页内容不构成法律建议，本维基也不对事件的是非曲直表态。

---

## 本维基读者的来源卫生

下面三条警告都直接来自前述记录。

> [!CAUTION]
> **不要引用项目的 `docs` 分支**
>
> `docs/ARCHITECTURE.md` 声称 `cmpunlocker` 会向 SS0 和 SS1 都写入 `0xffffffff`。发布版补丁实际写入的是 `0x0082381c = 0x88888888` 和 `0x00823820 = 0x00000008`。同一分支还擅自编造了代码和转写中都不存在的缩写展开（SS 是“Suspension State”，PLM 是“Program Logic Modules”，PMM 是“Permute Mask Model”，LMR 是“LM (Local Memory) Request register”，PMA 是“Power Management Array”），声称存在一条不存在的 `SEC2_DEBUG: Executing unlock sequence...` 日志，并在发布版脚本实际名为 `remove.sh` 时，指示用户运行 `sudo ./uninstall.sh --yes`。这个分支只有七个提交，并不具备权威性。

> [!WARNING]
> **流传最广的架构笔记自评只有约 10% 得到证明**
>
> 这些笔记的作者发布时附带了如下说明：“I do hold some notes. I try to double-check each statement, but this work can not be given to LLMs, so it is goes REALLY slow. This is what I have now. I do not state that this information is accurate, I would say, just ~10% has reliable proofs/sources.”（我确实保存了一些笔记。我尽量对每条陈述进行复核，但这项工作不能交给 LLM，所以进展真的非常慢。这就是我目前拥有的内容。我不声称这些信息准确，只能说大约 10% 有可靠的证明或来源。）另一个针对尝试编写汇总文章者的警告是：“most of things known about throttling mechanism are based on hypotheses and some experiments that do not contradict them... if you simply collect all points mentioned in chat you will likely get many wrong conclusions and it will get your llm insane.”（关于节流机制的大部分已知内容都建立在假设和一些并不与假设矛盾的实验上……如果只是把聊天中提到的所有要点收集起来，很可能会得出许多错误结论，还会把你的 llm 搞疯。）被点名为可靠起始材料的三个来源是 Zenodo 论文、公开的 GA100 熔丝参考表以及带注释的 `booter_load` 汇编。这个警告应特别附在架构笔记上，不要附在寄存器转储或反汇编上，因为后两者的证据支持明显更充分。

项目中使用的函数名都是根据行为推断出来的，并非从符号表读取；二进制没有符号。两个文档之间有一对名称不一致：LLM 概览将 `0xd66` 和 `0xccb` 称为 `regtable_reverse_lookup` 和 `regtable_rw_indexed`，而 ROP 写稿将它们称为 ACR 互斥锁的获取和释放。代码支持后者的互斥锁解释；发布版链把 `0x00000ccb` 放在 `D[0xFFF4]`，紧接在干净退出地址 `0x00007f2f` 之前，因此发布版代码依赖的是互斥锁这一解释。

---

## 带日期的工件索引

本页中所有带有解码时间戳的内容，按时间顺序列出如下。

| 日期和时间（UTC） | 工件或事件 |
|---|---|
| 2026-05-05 / 2026-05-07 | 两张实物 CMP 170HX 10 GB 卡被探测（每张 120 个寄存器） |
| 2026-05-31 | Drive A100 32 GB（PG199）被探测；15 卡熔丝参考表完成 |
| 2026-06-26 | Canary 预印本在解锁器服务器中传阅 |
| 2026-06-27 | 净室规则集作为频道政策发布 |
| 2026-06-30 | 公开 AES-128-ECB 测试密钥和 `rijndael-tool.zip` 在频道内发布 |
| 2026-07-01T12:40:37Z | 原始调试版 Booter 反汇编发布（545,149 B） |
| 2026-07-02 | 调试版与生产版的等同性得到确认；寄存器来源标准获接受 |
| 2026-07-03T17:12:52Z | 带注释的反汇编发布 |
| 2026-07-09T03:03:21Z | 带注释的反汇编 v2 发布（607,702 B，11,875 行） |
| 2026-07-10T13:40:14Z | 寄存器 Gadget 图谱发布 |
| 2026-07-14T21:47:02-07:00 | `cmpunlocker` 初始提交 `9b9fb2f`，包含帧网格常量 |
| 2026-07-15T18:48:10Z | `ROP_CHAINS_1180f8` 写稿，记录 `+0x18 DMEM per write` |
| 2026-07-16T06:07:12Z | 论文以 `main.pdf` 的形式贴入净室服务器 |
| 2026-07-17 | 至少一个 fork 收到 DMCA 删除通知 |
| 2026-07-18T18:01:15Z | `patch.diff` 发布 |
| 2026-07-18T18:26:26Z | 发布版补丁集文件的 mtime |
| 2026-07-18T18:40:16Z | LAPSUS$ 来源溯源评估发布 |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` 合并到 `master` |

---

## 参见

- [项目时间线](timeline.md)，包含技术里程碑的完整日期序列
- [工具谱系](tool-lineage.md)，记录哪些工具取代了哪些工具，以及哪些工具已经废弃
- [失败路线](dead-ends.md)，记录尝试过并被反驳的方法
- [ROP 链](../unlock/rop-chain.md)，本页讨论其载荷的来源
- [六个驱动补丁](../unlock/driver-patches.md)
- [Falcon 与 Booter](../unlock/falcon-and-booter.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)，120 个寄存器的差分语料库
- [方法论](../appendix/methodology.md)和[外部来源](../appendix/external-sources.md)
