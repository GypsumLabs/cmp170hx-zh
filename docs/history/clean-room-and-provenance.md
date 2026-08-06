# 净室与来源溯源问题

## 本页覆盖内容

CMP 170HX 解锁是在一份明确的净室协议下开发的，而那份协议存在要回答的单个问题是：生成的代码能否在没有 2022 年 2 月 LAPSUS$ 对 NVIDIA 的泄露材料的情况下被产出。本页记录净室如何组织、它的规则是什么、它允许的输入是什么、当时的来源评估结论是什么、依据什么推理、后来的字节级比较确立了什么、以及一份泄露的私有概念验证如何在 2026-07-18 进入画面。

两个结果主导下面的一切。

1. **出货 ROP 载荷里的每个常量，除一个外，都已追溯到一份早于出货补丁的、带日期的公开或净室派生的工件。** Gadget 地址来自 2026-07-01 发布的解密调试-booter 反汇编、gadget 语义来自 2026-07-10 发布的自动生成图谱、DMEM 栈帧网格来自 2026-07-15T04:47Z 的一个公开 git 提交、缓冲区、守卫、填充和大小常量来自 2026 年 6 月的学术预印本。例外是种在载荷偏移量 `0x1100`（`D[0x1900]`）的 `0x00000007`、没有任何早于补丁的带日期工件解释它。载荷里其它什么都不需要泄露材料来推导。
2. **出货的 `cmpunlocker` 驱动补丁集，逐行地，就是泄露的 `patch.diff`**，加了 10 GB 双几何布局支持、移除一处敌对改动、在 `patch.diff` 贴出后 70 分钟被采纳。原则上的可推导性和事实上的推导不是一回事、而源材料没有解决哪一个发生了。

本页同时报告两者、陈述每一方的论证、然后就此打住。它不提供法律结论、而且本页任何地方都不点名任何人。代码本身见[六个驱动补丁](../unlock/driver-patches.md) 和[ROP 链](../unlock/rop-chain.md)；日期见[项目时间线](timeline.md)。

---

## 为什么净室一开始就存在

解锁不是在净室里开始的。它于 2026 年 3 月在一个公开 GitHub 问题跟踪器上开始、于 2026 年 4 月移到一个 Discord 服务器、到 2026 年 5 月已产出那个让 AES 加密、RSA 签名的 `booter_load` 代码能被读取的决定性密码学结果。2026 年 6 月、一条能在那个代码内部跳到任意地址的 ROP 链被演示并公开宣布。开发随后移进一个**七人**的私人群组、它产出了概念验证、日期为 2026 年 6 月的学术预印本、和两份内部**驱动修改指南**（一份算力、一份显存）。

那个私人群组做了两个塑造此后一切的决定：

- **发表论文、扣留利用代码**、并等待独立复现。
- **删除原始 Discord 服务器**、理由是它可能含从 NVIDIA 泄露的材料。

净室是为了从零复现被扣留的结果而创建的、只使用能展示来源的输入。它管理的威胁是 LAPSUS$ 泄露：据后来的来源评估所述、2022 年 2 月到 3 月的一次泄露约 **1 TB** 的 NVIDIA 数据、包括 GPU 驱动源码、内部硬件文档和固件签名密钥。泄露的缓存保持公开可定位（Internet Archive 在频道内被点名）、这正是一条规则而非一个假设被需要的原因。

---

## 规则集

治理标准、从 2026-06-27 起作为频道政策陈述、并在整个时期通过删除和封禁威胁执行：

1. **不得讨论任何 NVIDIA 机密。**
2. **只有能展示同一信息可从公开来源推导的机密知识才被采信。**
3. **发布泄露或非法材料会被封禁。** 这明确覆盖泄露源码、泄露原理图、以及从被删除的早期 Discord 带过来的任何文件。

2026 年 6 月预印本被指定为**唯一干净输入文档**、基于两点：它发布在一个科学出版物站点上、而且它已被发送给 NVIDIA。

规则 2 是承重的那条、也是 2026-07-18 事件施加最大压力的那条规则。见下文[两种读法、未解决](#两种读法未解决)。

---

## 净室与脏室：设想的对比实际的

第一提案里就提出了双队分裂。陈述的组织原则是常规的：一个**脏室**队执行逆向工程并产出不含任何非法内容的文档、一个什么都没看过、只从那些文档重新实现结果的**干净队**。

那个分裂大体被放弃了。实际成形的是一种**频道分裂、而非队伍分裂**：

| 设想 | 实际发生 |
|---|---|
| 脏室队、隔离、做 RE 并写规格 | 源集里没有任何文档把 "dirty room"（脏室）当作一个运作团队使用 |
| 干净队、零接触、只从那些规格实现 | 同一些人在频道之间工作 |
| 靠队伍成员资格强制分离 | 靠频道主题和采信规则强制分离 |

确实存在的频道是一个只携带工作值的 `#general-how-to-cleanroom` 指南频道、加更深的、携带寄存器扫描、Falcon 退出路径分析和 DMEM 栈探索的技术频道。对这个描述的置信度：**中等**：意图在档案里逐字引用、频道结构直接可观察、但双队协议没有被证明过曾被配备人员。

---

## 干净输入语料库

净室允许自己建立其上的一切、带各自的论证：

| 输入 | 为什么它被视为干净 |
|---|---|
| **"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"**、2026 年 6 月、Zenodo 记录 `20916112`、ResearchGate 出版物 `408132536`、16 页 | 发布在一个科学出版物站点上并向厂商披露。被指定为唯一干净输入文档。2026-06-26 传阅；2026-07-16T06:07:12Z 作为 `main.pdf` 贴进净室服务器 |
| `NVIDIA/open-gpu-kernel-modules`（标签 `610.43.02`、`610.43.03` 和更早的 `580.x`） | NVIDIA 自己发布的源码 |
| **调试** `booter_load` 二进制 | 编译为 NVIDIA 自己 `.ko` 里的一个 C 数组、并在 open-gpu-kernel-modules 树里发布为 `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`。用 Nouveau 固件提取工具（为 GA100 打补丁）提取。弄通这条路花掉群组两天 |
| NVIDIA 的**公开 AES-128-ECB 测试密钥** | 来源是 NVIDIA 公开的 Jetson Secure Boot 文档。密钥构造是 MD5 初始化向量 `...0123456789abcdef...`、密钥编号作最后字节。一个自包含、公域、含无 NVIDIA 材料的 Rijndael 解密器和密钥验证器（`rijndael-tool.zip`）在频道内发布 |
| **GA100 熔丝与寄存器参考表**：15 张 Ampere 卡上的 120 个寄存器 | 完全从对参与者拥有或租用硬件的只读 MMIO 探测产出。见[熔丝与 OTP](../hardware/fuses-and-otp.md) |
| 卡自身的 BAR0 寄存器读、和 A100 对比部件上的 | 拥有硬件的拥有者侧测量 |

频道内就加密达成的共识是尖锐的：NVIDIA 的错误**不是**使用琐碎测试密钥、而是**在调试和生产分支里发货恰好相同的二进制**、以及签名一个含严重漏洞的二进制。

### 15 卡差分语料库

寄存器级来源论证压在这张表上。它对比 `tools/mmio-probe/probe.sh` 在下面读的 120 个寄存器：

- **2 × CMP 170HX 10 GB**、物理、2026-05-05 和 2026-05-07 探测
- **11 张经 GPU 租赁提供商租的卡**：A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A16、A5000、A6000、RTX 3080、RTX 3080 Ti、RTX 3090、RTX 3090 Ti。（一个工程样品部件作为一列出现在熔丝表里、却在任何一行都不带值。）
- **2 × Drive A100 32 GB**（`GA100-550F-A1`、PG199）、物理、2026-05-31 探测

恰好五个寄存器组把一颗 170HX 与一颗同硅片的 A100 区分开：SM 速度选择、PCIe 引导代、NVLink 禁用、ECC 使能、和 FBPA CFG1 几何布局。

两块物理 170HX 单元也在要紧处被证明寄存器相同：**120 个寄存器中 107 个逐字节相同**、全部 13 个差异是按晶片分级伪影（地板清扫掩码和它们的 FBIO/STATUS 镜像、按单元的 `FEAT_OVR_SM_SPD` 编码、`FEAT_OVR_QUADRO`、HBM 硅片身份寄存器、以及跟随地板清扫的每-FBPA 回读）。每个限制熔丝都精确匹配。那个结果许可把一张卡派生的配方推广到另一张。

---

## 寄存器值的来源标准

2026-07-02 在频道内作为发布目标寄存器集的理由被接受：

> 显存几何布局来自 VBIOS 和读 BAR0 地址空间，而其它一切可以靠 diff 一颗 A100 的 BAR0 输出对一颗 170HX 的、把所有东西改成 A100 值来推导。

只用了 NVIDIA 开源驱动数据和 NVIDIA 的公开测试密钥来产出干净的 `booter_load` 汇编。120 寄存器跨变体熔丝表是该声称的独立背书：它直接展示 A100 对比 170HX 的差、不参照任何内部文档。

---

## 承重的技术事实：调试等于生产、在要紧处

整个净室方法依赖一个实证结果。如果 `booter_load` 的 `-debug` 编译携带额外字节、从可读调试反汇编派生的每个 gadget 地址都会被移位、在生产硅片上无用、而正确偏移量的唯一路线会是生产二进制（它无法被解密）或泄露源码。

该担忧于 2026-07-02 被提出、并在同一时期被两种方式反驳：

- 调试和生产二进制**大小完全相同**。
- 一条纯粹从调试反汇编构建的 ROP 链**在生产硅片上正确执行**。

> [!NOTE]
> **未解问题**
>
> "同大小加一条成功链"是一个按实例的证明、不是一个按构造的证明。源集里没有任何文档记录对 `IMAGE_DBG` 和 `IMAGE_PROD` blob 的实际字节级比较、而 bindata 档案使它琐碎地可行。由：哈希 `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c` 里两条目定论。没人发布过那个哈希。

一个相关争论是触碰 GSP 签名是否一开始就破坏干净性。一个阵营认为篡改签名按定义使结果不干净。反方未被反驳：面向返回编程复用已签名二进制里已存在的代码、不需要访问 NVIDIA 源码、所以一条从合法解密二进制构建的链是干净的、唯一貌似不干净的元素会是载荷本身、如果它被复制而非推导的话。生产 booter 从不被修改：每个工作的工具加载一个未修改的签名映像、只把分离的 384 字节签名在 `PATCH_LOC 0x8900` 拼接回去。

---

## 2026-07-18 来源评估

一份标题为 **"Assessment: Is patch.diff Derived from LAPSUS$-Leaked Information?"** 的文档在 **2026-07-18T18:40:16Z** 贴出、**恰好**在 `patch.diff` 自己于 **2026-07-18T18:01:15Z** 贴出后的 **39 分钟**。两个时间戳都从 Discord 消息 snowflake 解码到毫秒。

**范围。** 一个对 `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03` 的补丁。

**干净来源语料库、恰好三项、不多不少：**

1. `paper.md`（Canary 预印本）
2. `how_to.discord.html` 和 `discussion.discord.html`、净室服务器两个频道的导出转写
3. `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03`

评估者没有可用的泄露缓存对比、评估自己也把它记作对其结论的一个限制。

**方法。** 把补丁对那三个来源对比、然后把补丁干净应用到一份克隆的仓库、并把它放在上下文里检查。

**裁决、逐字：** "The available evidence does not support a conclusion that this patch is derived from LAPSUS$-leaked information."（现有证据不支持这个补丁派生自 LAPSUS$ 泄露信息的结论。）

### 评估把什么分类为干净

| 类 | 内容 | 记录在案的裁决 |
|---|---|---|
| **干净、来自论文**（九个概念） | 栈金丝雀引用字漏洞（§5.1-5.3、Thesis 1）；经无界签名长度复制的 DMA 溢出（§3.2、§5.5）；经签名 booter 的 SEC2 Falcon HS 模式进入（§2.2、§5.4）；均匀填充值 **V = `0x4a7`**（§5.5、仿真器迹线）；溢出签名大小 **SIGSZ = `0xf800`**（§5.5）；HS 代码执行后作为枢轴的 PLM 解锁（§6.1）；特性覆盖影子寄存器概念（§2.1）；来自 HS 的 WPR2 teardown（§8.5）；带 GPU 作防御者的被侵入宿主这个颠倒威胁模型（§2.3） | "Clean. These concepts are fully documented in the paper and require no special access."（干净。这些概念在论文里被完整记录、不需要特殊访问。） |
| **干净、来自开源驱动树**（内核内部 API） | `memdescCreate`、`memdescMapInternal`、`memdescFlushCpuCaches`、`memdescGetSize`、`memdescGetPhysAddr`；`pmaRegisterRegion`、`pmaGetRegionInfo`、`pmaGetFreeMemory`、`pmaGetTotalMemory`；`MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`；`os_open_and_read_file`；`kgspExecuteBooterLoad_HAL`、`kgspPopulateWprMeta_HAL`；`FB_REGION_DESCRIPTOR`、`PMA_REGION_DESCRIPTOR`；`NV_FLAG_PERSISTENT_SW_STATE`；`GPU_REG_RD32`/`GPU_REG_WR32`；`NV2080_CTRL_CMD_FB_GET_FB_REGION_INFO_PARAMS` | "Clean. Any competent kernel module developer can discover these by reading the source."（干净。任何称职的内核模块开发者都能通过读源码发现这些。）每个具名符号都存在于出货补丁集里 |
| **干净但早**（八个元素、存在于日期 2026-07-09 到 2026-07-17 的公开转写里） | 特性覆盖地址 `0x823804`、`0x82381c`、`0x823820`、`0x9a0204`、`0x100ce0`；WPR2 寄存器 `0x1fa824`/`0x1fa828` 和作为阻塞者的 WPR2 carve；FB-几何 PLM 地址 `0x100b10`/`0x100b38` 和 `0x9a0148`/`0x9a014C`/`0x9a0108`/`0x9a010C`；`0x8403C4` 作 `resetPLM`；三个具名退出策略（`secure_teardown`、过早退出 `0x8117`、`multiwrite_then_mutexfree_cleanexit`）；某些寄存器的 FLR 持久性；一个用于直接 SEC2 控制的非安全 ucode 加载器；从 `D[0xFFC4]` 到 `D[0xFFF0]` 的 DMEM 栈探索 | "Clean, but overlapping."（干净、但重叠。） |

那张表里有一个引用是错的。"WPR2 teardown from HS" 被映射到论文 §8.5；§8.5 标题是 "Persistence across FLR"（跨 FLR 的持久性）并论证、持有覆盖值的常开岛把一个瞬时利用变成持久状态。它不含 WPR2 teardown、也不含 ROP 讨论。论文唯一的 ROP 引用是 §5.5 里的单一引用。实际后果是、出货补丁围绕每次 Booter 趟的显式 WPR2 保存和恢复不被论文覆盖、尽管表暗示如此。评估分开地、正确地、把 WPR2 处理归因到公开转写、所以这是一个引用错误、而非实质错误。

### 评估关于外部起源的三个论证

这些被记录为论证、不是事实。

1. **负面证据。** 补丁不含 NVIDIA 内部代码注释、不含泄露构建的揭示性变量名、不使用泄露的签名密钥（利用不伪造签名）、也不含不是通过 BAR0 探测也可发现的内部专属寄存器名。论文的伦理陈述直接佐证关键点："We extracted no signing keys and forged no signature."（我们没有提取签名密钥、也没有伪造签名。）
2. **大锤论证。** `patch.diff` 把 `return NV_OK;` 插作 `subdevice_ctrl_gpu_regops.c` 里 `gpuValidateRegOps` 的第一条语句、把原主体留成死代码。它无条件、影响所有 GPU 而非只有 CMP 170HX、并完全禁用控制面板寄存器读/写验证。引出的推断："The sledgehammer approach suggests an external developer who needed a quick bypass and didn't care about collateral damage to other GPUs or security... An internal NVIDIA engineer or someone with leaked docs would likely make a surgical change."（大锤方法表明一个需要快速绕过、不在乎对其它 GPU 或安全附带损害的外部开发者……一个内部 NVIDIA 工程师或有泄露文档的人很可能会做一次外科手术式改动。）
3. **伪装命名。** `SEC2_DEBUG_PRI_*`、`kgspSec2PostblTiming*` 和 `SEC2_DEBUG` 日志前缀存在于 NVIDIA 代码库的任何地方都不、而 "PostBL Timing" 是一个貌似合理却虚构的功能名。该方案读作把利用代码伪装成一个合法制造或调试功能的尝试、那 "would be unnecessary for someone with legitimate access"（对合法访问的人不必要）。命名在出货代码里逐字存在、它定义 `0002-booter-verify.patch` 里的 `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM 0x00823804`、`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED 0x0082381c`、`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820`、`SEC2_DEBUG_PRI_FBPA_CFG1 0x009a0204` 和 `SEC2_DEBUG_PRI_MMU_LMR 0x00100ce0`。

> [!CAUTION]
> **`gpuValidateRegOps` 绕过不在出货工具里**
>
> 无条件绕过是真实且严重的：任何有 `NV_GPU_REG_OP` 访问的进程都能在机器里任意 NVIDIA GPU 上读或写任意 GPU 寄存器。它**只存在于泄露的 `patch.diff` 里**。出货的 `cmpunlocker` 补丁集**完全**不碰 `subdevice_ctrl_gpu_regops.c`、而字符串 `gpuValidateRegOps` 出现在 `master` 或十二个未发布分支的任何一个的任何地方都不。任何把这个洞归因于 `cmpunlocker` 的文字都是错的。

### 单一残余担忧

两项被评 HIGH 且留下未清除：完整 ROP 链 DMEM 字节偏移量（`0x1100`、`0x5b40`、`0xf754` 到 `0xf7f8`）和把 `writeAddr`/`writeValue` 经 DMEM 栈槽映射的 gadget 链、被描述为 `_kgspSec2PostblTimingFillPayload` 在 `0xf800`-字节签名缓冲区里精确字节偏移量处写 **24 个特定 32 位值**。

推理是四重的：

| # | 论证 |
|---|---|
| (a) | 论文描述均匀填充 ROP 链的概念、却没有发布版本专属 DMEM 布局 |
| (b) | 偏移量是 booter 版本专属的、弄错它们产生崩溃（`MB0=0x31`、`IMEM_MISS_INS`、或金丝雀失败）而非一个工作利用 |
| (c) | 社区在探索它相信的一个不同偏移量范围 |
| (d) | 推导它们需要一个周期保真的 Falcon 仿真器加专属 booter 二进制、栈帧布局的 NVIDIA 内部文档、或泄露的 booter 源码 |

它自己的既定缓解是、论文的仿真器方法论足以复现该分析。底线、逐字："The ROP chain offsets are the only element that would require significant independent work to produce without leaked documentation, and the paper explicitly describes how to do that work."（ROP 链偏移量是唯一一个在没有泄露文档的情况下产出需要大量独立工作的元素、而论文明确描述如何做那个工作。）

计数是对的：出货载荷恰好含 **24** 次 `_kgspSec2PostblTimingPutU32` 调用、在载荷偏移量 `0x1100`、`0x5b40`、`0xf754`、`0xf758`、`0xf75c`、`0xf76c`、`0xf774`、`0xf780`、`0xf788`、`0xf78c`、`0xf790`、`0xf794`、`0xf798`、`0xf79c`、`0xf7a0`、`0xf7a4`、`0xf7b0`、`0xf7b8`、`0xf7c4`、`0xf7c8`、`0xf7d8`、`0xf7e0`、`0xf7f4`、`0xf7f8`。

---

## 后来的分析确立了什么、关于那个残余担忧

担忧 (c) 和 (d) 不成立。下面的更正来自重读归档工件和出货源码、不是引用评估。

### (c) 是一个基址偏移量框架伪影

载荷被 DMA 到 DMEM `0x800`、所以**载荷偏移量 + `0x800` = DMEM 地址**。两个"不同"的范围是同一个范围：

| 补丁偏移量 | DMEM 地址 | 在评估自己表里的状态 |
|---|---|---|
| `0xf754` | `D[0xFF54]` | 标记 HIGH |
| `0xf76c` | `D[0xFF6C]` | 标记 HIGH |
| `0xf7c4` | `D[0xFFC4]` | 列为**干净但早** |
| `0xf7f8` | `D[0xFFF8]` | 标记 HIGH |

干净但早列表已经包含 `D[0xFFC4]` 到 `D[0xFFF0]`、它覆盖评估标记 HIGH 的 22 个栈槽中四个。按评估自己的记账、它标记 HIGH 的范围部分已经被标记为干净。评估在同一槽上、把补丁偏移量当可疑、把 DMEM 地址当干净。

### (d) 被带日期的公开工件反驳

出货 ROP 链里每个代码地址都是净室自己的解密调试-booter 反汇编里的一条指令边界、**早于补丁十七天**发布。

| 工件 | 发布 | 它提供什么 |
|---|---|---|
| `booter_load_ga100_dbg_seccode.fuc5.asm`（545,149 B） | 2026-07-01T12:40:37Z | 原始 envydis 输出；每个链地址 `0x0cbd`、`0x0ccb`、`0x10aa`、`0x10b9`、`0x1fbd`、`0x582d`、`0x7f2f`、`0x815a`、`0x0d66`、`0x04d4` 恰好匹配一条指令行 |
| `...annotated.fuc5.asm` | 2026-07-03T17:12:52Z | 每函数横幅 |
| `...annotated.fuc5_v2.asm`（607,702 B、11,875 行） | 2026-07-09T03:03:21Z | 每个 `lcall` 带一个命名被调者的内联注释 |
| **寄存器 Gadget 图谱** | 2026-07-10T13:40:14Z | 从那个反汇编机器生成。列出 `0x0cbd` 为 "`$r10 <- $r0`、canary(r15==r9)、via-call、`mpopaddret $r3 0x4`" 和 `0x1fbd` 为 "`$r11 <- $r10`、canary(r15==r9)、via-call、`mpopaddret $r2 0x4`"、精确地是它们在出货链里扮演的角色、包括产出帧步长的 `mpopaddret` 尾声 |
| `cmpunlocker` 初始提交 `9b9fb2f`、`common/constants.yaml` | 2026-07-14T21:47:02-07:00 = 2026-07-15T04:47:02Z | `dmem_layout: dma_target 0x0800, payload_size 0xF800, guard_addr 0x6340, canary 0xFACEB13D`；`booter_addrs: bar0_write_gadget 0x10B9`；`payload_frames: frame_start_addr 0xFF48, frame_stride 0x18, frame_field_offsets {r0 0x00, r1 0x04, r2 0x08, r3 0x0C, saved_reg 0x10, return_addr 0x14}` |
| `ROP_CHAINS_1180f8_nibble_writeup_20260715.md` | 2026-07-15T18:48:10Z | 散文里同一个网格："N BAR0-master writes via the light `0x10b9` self-chain、**每次写 +0x18 DMEM**"、把 `D[0xFF50]`、`D[0xFF54]`、`D[0xFF5C]`、`D[0xFF68]`、`D[0xFF6C]`、`D[0xFF74]`、`D[0xFF80]`、`D[0xFF84]` 制成表 |

**出货补丁里全部 22 个栈槽偏移量恰好落在那六字段、`0x18` 步长网格的一个具名字段上、零个未对齐命中。** 24 个值中剩余两个是守卫字（`0x5b40` 映射到 `D[0x6340]`）和 `0x1100`（映射到 `D[0x1900]`）。

剩余的非-gadget 常量也被说明：`0xf800`、`0x800`、`0x6340` 和 `0x4a7` 来自论文的仿真器迹线、且在评估自己的干净-来自-论文列表上；`0xc0deca7e` 是论文发布的守卫桩值；`0x5b40 = 0x6340 - 0x800` 是论文打印的两个数字上的算术；`D[0xFFB0]` 处的 `0x0000ffbc` 是一个指向帧网格的自引用 DMEM 栈指针；`D[0xFF90]` 处的 `0x00008e18` 超出 booter 的代码映像（反汇编止于 `0x86ff`）并指向带注释清单里指令行 `0x0d39`、`0x0da1` 和 `0x0e1b` 文档化的寄存器描述符表区域 `0x8e04`/`0x8e08`。

### 净室自己的链相关、却不是一份副本

净室 Python 解锁器和出货 C 链共享缓冲区基址 `0x800`、大小 `0xF800`、守卫地址 `0x6340` 和 `0xFF48`/`0x18` 六字段帧网格。它们以两种可见方式不同：

| | 净室 Python（`payload/build.py`、提交 `9b9fb2f`） | 出货 C（`0001-sec2-postbl-plm-ss-cfg.patch`） |
|---|---|---|
| 金丝雀字面量 | `0xFACEB13D`（项目代号） | `0xc0deca7e`（论文发布的桩） |
| 链形状 | 一个自链 gadget `0x10B9`、每次写一帧 | 经 `0x0cbd`、`0x1fbd`、`0x815a`、`0x582d` 的更长的链 |
| 终止符 | `0x0000810D` | `0x00000ccb`（ACR 互斥锁释放）然后 `0x00007f2f`、恰好是公开转写命名的 `multiwrite_then_mutexfree_cleanexit` 策略 |

利用的代号、**FACEB13D**、发音 "fake bird"（假鸟）、指那个必须被击败的栈守卫金丝雀、不是指 Falcon。列举的障碍是 obscurity 式安全、栈金丝雀、安全级别 L0 到 L3、一个不可变引导 ROM、一个安全协处理器、代码的 AES 加密、和代码的 RSA 签名。

---

## 泄露的概念验证

### 重分发的包

净室算力解锁器发布并克隆到 GitHub 后约三天、一个 "Chinese unlock" 浮现在俄罗斯 Telegram 上。它按当时作出的评估是泄露的私有概念验证、不是独立工作。

包结构、经多位独立审查者检查：

```text
cmp170hx-unlock-610.43.03.zip
├── install.sh                              # 检查后评估安全
├── NVIDIA-Linux-x86_64-610.43.03.run       # 与官方安装器逐字节相同
├── open-gpu-kernel-modules-610.43.03/      # 打过补丁的源码 + 预编译二进制
└── README.txt                              # 无关
```

把发货源码对 `NVIDIA/open-gpu-kernel-modules` 标签 `610.43.03` 做 diff 产出 `patch.diff`、**35,867 字节、887 行、11 个文件**。每个修改都隔离在开源内核模块组件里；没有封闭二进制被改动。推荐的安全处理是删除发货的 open-modules 文件夹、`git clone` 上游、应用 `patch.diff`、重编译、然后才跑 `install.sh`。

档案大小报告不一致（537.2 MB、在那个也给出内部 `.run` 461.5 MB 的账户里；约 520 MB、在另一个里）、而一个第二个文件名 `cmp170hx-unlock-610.43.03.tar.zst` 出现在一个来源里。两个文件名都可能是真的、同一个载荷被重分发两次。

一个持有两样工件的人报告 diff 与私有驱动修改指南里的代码**逐字相同**。置信度：**高**针对档案结构和 diff 大小（多位审查者、diff 文件本身被归档）；**中等**针对 "泄露而非重新发现" 的归因、它建立在一次来自一个有争议归因一方的单一字节比较上。

关于重分发解锁器再两点、来自独立检查：它写与公共仓库完全相同的权限级别掩码表、不解锁额外功能、**不**启用 PCIe Gen2、只识别 8 GB 卡（"currently this unlocker only supports 8G cards and can't recognize the 10G card"）。

### 泄露的 shell 脚本

分开地、一个算力解锁 shell 脚本以 `CMP170HX_Compute_Unlock_v8_3.sh` 公开泄露、2026-07-14 贴到一个公共 GitHub 仓库、很快被删除。它的作者把它描述为"just the compute only logic that was posted here、with some minor modifications to attempt to run on multiple GPU's vs 1. Nothing new sadly"（只是这里贴过的算力逻辑、带一些尝试跑多 GPU 而非 1 个的小改动。可惜没有新东西）、通过每卡重复注入块、带硬编码 PCIe ID 实现。它不含任何关于显存解锁的东西。

### 博客声称

一个报道此事的中国博客声称两名黑客独立解锁了显存、并展示了一个团队 `booter_load` 代码的截图、带完全不同的函数名和注释。不同的名字既与一次独立反汇编加注释趟（恰好是净室自己的名字如何被产出的）一致、也与对复制材料的重新加注释一致。

> [!NOTE]
> **未解问题**
>
> 那张截图是否用公开提示被独立解密从未定论。下一步：把截图里的指令地址对 `booter_load_ga100_dbg_seccode.fuc5.asm` 对比。如果它们匹配一个调试构建、作者就得用公开 Jetson 测试密钥解密它、那是干净路径。

---

## 70 分钟采纳窗口

这是当时的评估不可能知道的部分、它由 git 作者时间戳、`diff -Naur` 头 mtime 和解码的消息 snowflake 确立。

| 时间（UTC） | 事件 |
|---|---|
| 2026-07-18T18:01:15Z | `patch.diff` 贴到 `#general-how-to-cleanroom` |
| 2026-07-18T18:26:26Z | 出货 `cmpunlocker` 补丁集里每个文件都携带这个 `diff -Naur` 头 mtime（`2026-07-18 11:26:26 -0700`）。一棵树、写于一个瞬间、贴出后 25 分钟 |
| 2026-07-18T18:40:16Z | 来源评估被贴出、在窗口中间 |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` 在 `memory` 分支被编写、贴出后 **70 分钟** |
| 2026-07-18T20:51:36Z | `6b7d9ee "FULL WORKING THING"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` 合并进 `master` |

推导方向不模糊：出货仓库在 `06fabf2` 前**不含任何种类的驱动补丁**、而 `patch.diff` 只支持 8 GB `0x20C2` 卡。

### 两者实际差什么

把归档 `patch.diff` 的每个添加行对 `driver/patches/0001` 到 `0006` 的拼接对比：

| 量 | 值 |
|---|---|
| `patch.diff` | 35,867 B、887 行、11 个文件 |
| `cmpunlocker` 补丁集 | 890 行、6 个补丁文件、10 个目标文件 |
| 它们之间逐字节相同的添加行 | **638** |
| `patch.diff` 独有的行 | **19** |
| `cmpunlocker` 独有的行 | **43** |

19 行 `patch.diff` 独有行中每一行、要么是 `cmpunlocker` 做成每档位形式的某物的 8 GB 专属硬编码形式、要么是 `cmpunlocker` 用设备 ID 扩展的日志行、要么是 `gpuValidateRegOps` 里那单行 `+    return NV_OK;`：

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_PCI_DEVICE_ID 0x20C2
NvU32 cfg1Value    = 0x02779000U;
NvU32 lmrValue     = 0x0000020BU;
NvU64 targetFbBytes = 0x0000001000000000ULL;  /* 64GB */
/* 加 devId == 0x20C2 守卫 */
```

43 行 `cmpunlocker` 独有行中每一行都是 10 GB（`0x2082`）对应物：拆成 `SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID 0x20C2` 和 `SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID 0x2082`、`cfg1Value = 0x02669000U` / `lmrValue = 0x0000028AU` 分支、`targetFbBytes ... : 0x0000000A00000000ULL`、和双设备 ID 守卫。其它什么都不差。那些几何值是[显存几何布局](../unlock/memory-geometry.md) 文档化的规范值。

---

## 两种读法、未解决

证据与自己真实地处于张力中、而源集无法解决它。两种读法都在此完整陈述、因为读者有权权衡它们。

=== "A 面：按房间自己的规则干净"

    出货 ROP 载荷里每个常量都可从早于 `patch.diff` 的、带日期的公开或净室派生材料独立推导：gadget 地址来自 2026-07-01 发布的反汇编、gadget 语义来自 2026-07-10 发布的图谱、帧网格来自 2026-07-15T04:47Z 的一个公开 git 提交、缓冲区、守卫、填充和大小常量来自 2026 年 6 月论文。净室已独立地在同一网格上、用同一个缓冲区、同一个守卫地址和同一个 `reg_write_indirect` BAR0 写原语（从 `0x10b9` 进入、出货链从 `0x10aa` 进入）构建了一条工作 ROP 链、并已四天前公开发货它。按此读法、净室满足了它自己的规则（"secret knowledge is admissible only if the same information can be shown to be derivable from public sources"（机密知识只有能展示同一信息可从公开来源推导才被采信））、而评估的负面裁决是对的、事实上还被低估了。

=== "B 面：不干净"

    出货代码不是 `patch.diff` 的净室重新实现。它**就是** `patch.diff`、在它出现后 70 分钟逐字采纳、移除一处敌对改动、加一个设备 ID 分支。原则上的可推导性不是事实上的推导、而净室规则正如几位参与者所读的（"it is dirty, 100%"（它是脏的、100%））禁止使用那个工件、无论其中的信息是否可独立获得。材料被清除而非裁决、而工具反正采纳了代码。

**什么会定论它。** 现有材料里没有。两份私有驱动修改指南会确立 `patch.diff` 是否真的是私人群组的代码、而采纳维护者的一份陈述会确立代码是被复制还是收敛书写。两者都不存在于源集里。

> [!NOTE]
> **未解问题**
>
> 同一个问题的一个更窄、可处理的版本：补丁 `0004`（BAR0 PRAMIN 钳制）和 `0005`（CE 清扫变通方案）对 `cmpunlocker` 是原创的、还是也在私有指南里？它们的内容在 `patch.diff` 和 `cmpunlocker` 之间逐字节相同、所以它们一起进来、但 `patch.diff` 的社区摘要只描述签名劫持、PLM 打开、寄存器 poke、签名重建、`fb_length` 欺骗和晚期-PMA 扩展。它们没提 PRAMIN 钳制或 CE 清扫变通方案。只有指南能定论它。

---

## 学术论文及其披露立场

预印本是努力的唯一指定干净输入、也是它的方法论基础。它的摘要陈述 CMP 170HX 是"the same die as a flagship A100 but is fuse-crippled on three commercial axes: SM math rate (throttled to 1/32)、memory capacity (10 GB instead of 80 GB)、and PCIe link (Gen1 instead of Gen4)"（与旗舰 A100 同一颗晶片、却在三个商业轴上被熔丝削弱：SM 数学速率（节流到 1/32）、显存容量（10 GB 而非 80 GB）、和 PCIe 链路（Gen1 而非 Gen4））、"all three caps are soft"（三个 cap 都是软的）、并给出约 "roughly 31-62x compute、8x capacity、2x link"（约 31-62x 算力、8x 容量、2x 链路）的头条增益。它是与 `arXiv:2505.03782` 不同的一篇论文、后者被它引用为参考 [13]。

作者们刻意拒绝发表前禁运。第 10 节记录工作是单张卡上的实验室专属、无转售、无持久硅片改动、无提取签名密钥、无伪造签名、而且卡在测量后被恢复到原生配置。厂商的产品安全团队在**与发表同时**而非事先被通知。陈述的推理、在此记录为作者所论证的、而非一种背书：

> Coordinated disclosure assumes the vendor's remedy protects the user、which does not hold in an inverted threat model where the defender is the device and the adversary is its owner. A private embargo window would let the vendor burn the relevant anti-rollback fuses on already-shipped hardware、permanently removing that capability from the very users this work concerns、before those users could learn of it or act.（协调披露假设厂商的补救保护用户、这在一个防御者是设备、对手是其拥有者的颠倒威胁模型里不成立。一个私有禁运窗口会让厂商在已发货硬件上烧掉相关的反回滚熔丝、在那些用户能得知或行动前、永久地从这些工作所关切的用户身上移除那个能力。）

论文还描述了一个作者们建在 booter 指令流上的静态检查器：它把 DMA-as-copy 摘要提升进一个 IR、把 DMA 当污染源、在 DMA 汇处应用一个有界写检查（`L <= S - o`）、并在带链接映射感知的布局邻接处升级。作为一个差分门运行、它把开源内核时代 booter 的签名读传输标记为其单一无界汇、并以零误报通过更老的 booter 家族。置信度：**中等**。检查器没有发布在归档材料里、也没有独立方复现它。

给实现者的实用脚注：论文的 "3-4 BAR0 value changes"（3-4 个 BAR0 值改动）框架误导了每个独立复现者。三或四次写微不足道；全部难点是**先**打开四个 PLM。见[权限级别掩码](../unlock/privilege-level-masks.md)。

---

## 一个下游法律事件

**NVIDIA 于 2026-07-17 对至少一个 `cmpunlocker` fork 发出 DMCA 删除通知**、把那个仓库带下线。接收方说通知直接来自 NVIDIA 并停止了项目的公开工作。其它人推测它是自动化过滤器触发的执法、并指出许多 fork 已存在；建议流传要重命名和重写 fork。置信度：**中等**。报告是一手的、仓库可观察到下线、但源集里没有任何删除文档。这里没有任何东西是法律建议、而这个维基不对是非曲直采取立场。

---

## 本维基读者的来源卫生

三条直接跟在上面记录之后的警告。

> [!CAUTION]
> **不要引用项目的 `docs` 分支**
>
> `docs/ARCHITECTURE.md` 陈述 `cmpunlocker` 对 SS0 和 SS1 都写 `0xffffffff`。出货补丁写 `0x0082381c = 0x88888888` 和 `0x00823820 = 0x00000008`。同一个分支杜撰代码或转写里任何地方都不存在的缩写展开（SS 作 "Suspension State"、PLM 作 "Program Logic Modules"、PMM 作 "Permute Mask Model"、LMR 作 "LM (Local Memory) Request register"、PMA 作 "Power Management Array"）、断言一条不存在的 `SEC2_DEBUG: Executing unlock sequence...` 日志行、并在出货脚本是 `remove.sh` 时指示用户跑 `sudo ./uninstall.sh --yes`。它七个提交、而且它不是权威。

> [!WARNING]
> **流传最广的架构笔记自评约 10% 被证明**
>
> 它们的作者带这个警告发布它们："I do hold some notes. I try to double-check each statement、but this work can not be given to LLMs、so it is goes REALLY slow. This is what I have now. I do not state that this information is accurate、I would say、just ~10% has reliable proofs/sources."（我确实持有一些笔记。我尽量双重检查每条陈述、但这工作不能交给 LLM、所以它进行得真的非常慢。这是我现在的。我不声称这信息准确、我会说、只有约 10% 有可靠的证明/来源。）一个平行的警告给了任何尝试一份合并写稿的人："most of things known about throttling mechanism are based on hypotheses and some experiments that do not contradict them... if you simply collect all points mentioned in chat you will likely get many wrong conclusions and it will get your llm insane."（对节流机制已知的大部分东西基于假设和一些不矛盾的实验……如果你简单收集聊天里提到的所有点、你很可能得到许多错误结论、还会把你的 llm 搞疯。）被点名作可靠启动材料的三个来源是 Zenodo 论文、公开 GA100 熔丝参考表、和带注释的 `booter_load` 汇编。把这个警告特别附到架构笔记、不要附到寄存器转储或反汇编、后者被可证明地更好支持。

项目全篇使用的函数名是从行为推断的、不是从一个符号表读的：二进制没有符号。一对在两个文档之间命名不一致。`0xd66` 和 `0xccb` 在 LLM 概览里是 `regtable_reverse_lookup` 和 `regtable_rw_indexed`、在 ROP 写稿里却是 ACR 互斥锁获取和释放。代码支持互斥锁读法、而出货链把 `0x00000ccb` 放在它的干净退出 `0x00007f2f` 紧前的 `D[0xFFF4]`、所以互斥锁读法是出货代码依赖的那个。

---

## 带日期工件索引

本页每个携带解码时间戳的东西、按顺序。

| 日期和时间（UTC） | 工件或事件 |
|---|---|
| 2026-05-05 / 2026-05-07 | 两块物理 CMP 170HX 10 GB 卡被探测（各 120 个寄存器） |
| 2026-05-31 | Drive A100 32 GB（PG199）被探测；15 卡熔丝参考表完成 |
| 2026-06-26 | Canary 预印本在解锁器服务器里传阅 |
| 2026-06-27 | 净室规则集被陈述为频道政策 |
| 2026-06-30 | 公开 AES-128-ECB 测试密钥和 `rijndael-tool.zip` 在频道内发布 |
| 2026-07-01T12:40:37Z | 原始调试 booter 反汇编被贴出（545,149 B） |
| 2026-07-02 | 调试对比生产等价被定论；寄存器来源标准被接受 |
| 2026-07-03T17:12:52Z | 带注释反汇编被贴出 |
| 2026-07-09T03:03:21Z | 带注释反汇编 v2 被贴出（607,702 B、11,875 行） |
| 2026-07-10T13:40:14Z | 寄存器 Gadget 图谱被贴出 |
| 2026-07-14T21:47:02-07:00 | `cmpunlocker` 初始提交 `9b9fb2f`、携带帧网格常量 |
| 2026-07-15T18:48:10Z | `ROP_CHAINS_1180f8` 写稿、记录 "每次写 +0x18 DMEM" |
| 2026-07-16T06:07:12Z | 论文作为 `main.pdf` 贴进净室服务器 |
| 2026-07-17 | DMCA 对至少一个 fork 的删除 |
| 2026-07-18T18:01:15Z | `patch.diff` 被贴出 |
| 2026-07-18T18:26:26Z | 出货补丁集文件 mtime |
| 2026-07-18T18:40:16Z | LAPSUS$ 来源评估被贴出 |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` 合并进 `master` |

---

## 参见

- [项目时间线](timeline.md)、完整的带日期序列包括技术里程碑
- [工具谱系](tool-lineage.md)、哪些工具取代了哪些、哪些死了
- [死路](dead-ends.md)、试过并反驳的方法
- [ROP 链](../unlock/rop-chain.md)、其来源是本页主题的载荷
- [六个驱动补丁](../unlock/driver-patches.md)
- [Falcon 与 Booter](../unlock/falcon-and-booter.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)、120 寄存器差分语料库
- [方法论](../appendix/methodology.md) 和[外部来源](../appendix/external-sources.md)
