# 项目时间线

## 本页覆盖内容

CMP 170HX 如何从一颗熔丝削弱矿卡变成一张 64 GB、全速 GA100 的带日期记录、覆盖活跃期 **2026-06-22 到 2026-07-28**、带让它成为可能的更早背景。聊天时间戳是 UTC、除非显示本地偏移、凡时间给到秒都是从一个消息 snowflake 解码或从 git 作者时间戳读出。Git 行按**作者本地偏移**（大多 `-07:00`）定日期、这是提交呈现自己的方式；三个分支 tip 因此在这里比它们的 UTC 瞬间早一个日历日。

读者应该锚定的五个里程碑：

| 日期 | 里程碑 |
|---|---|
| **2026-07-12** | 算力解锁在硬件上工作。一个手动五步 TTY 流程抬起 1/32 FP32 节流；测到 12.28 TFLOPS SGEMM |
| **2026-07-14 / 15** | `cmpunlocker` 公开。首个发布是一个**免驱动 Python** 算力解锁器、完全不打驱动补丁 |
| **2026-07-18** | 显存几何布局出货。8 GB 到 **64 GB**、10 GB 到 **40 GB**、驱动内、一天内 |
| **2026-07-23 / 24** | 免驱动路径作为独立 Python refire 链回归、**PCIe Gen2** 被宣布 |
| **2026-07-26 / 27** | Gen2 分支谱系稳定；在一张电容改装卡上捕获一个 Gen2 x16 观察 |

这个时间线严格分开保持的两件事、按管束整个维基的规则：PCIe 链路**速度**（Gen1 到 Gen2、一个软件和固件解锁）和 PCIe 链路**位宽**（x4 到 x16、只能靠手工焊接 24 颗缺件电容达成）。它们是不同日期的不同成就。见[PCIe 子系统](../hardware/pcie-subsystem.md) 和[物理改装](../operations/physical-mods.md)。

---

## 史前：2021 到 2023

| 日期 | 事件 |
|---|---|
| **2021-04-23** | 最早出货 10 GB 卡的 VBIOS 构建日期（`92.00.66.00.02`、设备 `0x2082`） |
| **2021-05-14** | 8 GB 卡的 VBIOS 构建日期（`92.00.67.00.01`、设备 `0x20C2`） |
| **2021-09-01** | **CMP 170HX 发布。** GA100、826 mm²、542 亿晶体管、TSMC 7 nm N7、8 GB 或 10 GB HBM2e、250 W、无显示输出、无 DirectX/Vulkan/OpenGL/NVENC/NVDEC 暴露、为 Ethash 挖矿出售 |
| **2021-11-01** | 第三个 VBIOS 修订 `92.00.6D.00.09` 存在、但不在归档对比集里 |
| **2023-07-05** | 一个社区鼓风机转接座 STL 发布、第一个被广泛复用的 170HX 散热工件 |
| **2023-10-25** | **公开拆解与回顾。** 解锁前最重要的单份文档：它发布逐字 `lspci` 输出（Gen1 x4 在一个 x16 布线的插槽上训练、`SlotPowerLimit 75W`、`FLReset+`）、通道 4 到 15 上缺件的交流耦合电容、出厂 clpeak 和 mixbench 数字、以及张量核 "probably aren't working"（大概不工作）的结论 |
| **2023-10-27** | **FMA 禁用发现。** 发布到 FluidX3D 问题跟踪器、issue #8（评论 1779728815、1782734954、1782763214）并立即实现：关 FMA 收缩编译恢复约 16x FP32、达到约 6.25 TFLOPS |
| **2023-12-06** | FMA 结果两个月后带到 NVIDIA-patcher 问题跟踪器、issue #73。正是那个 issue 最终导致寄存器级破解 |

---

## 现代努力的起源：2026-03 到 2026-06-21

| 日期 | 事件 |
|---|---|
| **2026-03** | 工作重新在 NVIDIA-patcher 问题跟踪器、issue #73 上开始 |
| **2026-04** | 开发移到一个 Discord 服务器 |
| **2026-04-04** | 一份 AI 生成的写稿得出结论 "the FP throttle is hardware enforced and can't be overridden"（FP 节流是硬件强制、无法被覆盖）从 issue #73 被链接。它自己的页脚记录测试环境：Ubuntu 22.04、内核 5.15.0-174-generic、驱动 535.288.01、CMP 170HX（`0x2082`）、2026 年 4 月。后来被出货算力解锁彻底反驳 |
| **2026-05** | **决定性的密码学发现**：一条读取 AES 加密、RSA 签名的 `booter_load` 代码的路径 |
| **2026-05-05、2026-05-07** | **熔丝调查开始。** 两张物理 CMP 170HX 10 GB 卡用 `tools/mmio-probe/probe.sh` 完全探测、各 120 个寄存器。120 个寄存器中 107 个在两单元之间逐字节相同；全部 13 个差异是按晶片分级伪影。这是准许把配方从一张卡转移到另一张的结果 |
| **2026-05-31** | **熔丝调查完成。** 两张物理 Drive A100 32 GB（`GA100-550F-A1`、PG199）被探测、加入 11 张租用 Ampere 卡、得到一张 **15 卡、120 寄存器** 跨变体表。恰好五个寄存器组把一张 170HX 与一颗同硅片 A100 区分开：SM 速度选择、PCIe 引导代、NVLink 禁用、ECC 使能、FBPA CFG1 几何布局。`z1_dump_and_parse_vbios.sh` 和 `z2_parse_vbios_table.py` 同日落地、连同六个固件侧攻击路径的调查（三个 DFA 毛刺路线、一条 CH341A 刷写路径、电容改装、和软件 FMA 变通方案） |
| **2026-06** | 第一条能在 booter 里跳到任意地址的 ROP 链被演示并在开放服务器上宣布。开发移进一个**七人**私人群组、产出概念证明、论文、和两份内部驱动修改指南 |
| **2026-06（论文日期）** | **"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"**、16 页、Zenodo 记录 `20916112`、ResearchGate `408132536`。头条声称：三个 cap 都是软的；约 31-62x 算力、8x 容量、2x 链路 |

利用的代号是 **FACEB13D**、"fake bird"（假鸟）、按那个必须被击败的栈守卫金丝雀。列举的障碍是 obscurity 式安全、栈金丝雀、安全级别 L0 到 L3、不可变引导 ROM、一个安全协处理器、代码的 AES 加密、和代码的 RSA 签名。

---

## 2026-06-22 到 2026-06-30：首批公开工具和净室章程

| 日期 | 事件 |
|---|---|
| **2026-06-22** | 归档里首个带日期的工具失败：`deploy.py --path sec2-rop` 中止、因为它调用 `firmware/load_custom_bin.py --verify`、一个加载器的 argparse 不接受的参数。退出码 2、不是硬件失败。2026-06-24 修复 |
| **2026-06-23** | `deploy.py --path vbios-memory` 被尝试、从没工作：`ERROR: Not a PCI Option ROM (bad magic at 0x00)`。整个 VBIOS-显存方法被放弃。分开地、`CMPGPU-patch-script`（`optimize-cmp-cuda.py`）、一个带五组 FMA 和内在函数优化组的交互式 llama.cpp 源码补丁器被发布 |
| **2026-06-26** | Canary 预印本在解锁器服务器里传阅 |
| **2026-06-27** | **净室规则集被陈述为频道政策**：无 NVIDIA 机密；机密知识只有能从公开来源推导才可采信；发布泄露材料是封禁。论文被指定为唯一的干净输入文档。一个脏室/净室两队分裂被提议、随后大致放弃、改用频道分裂 |
| **2026-06-30** | 调试分支被证明只用一颗**公开 AES-128-ECB 测试密钥**混淆、构造为以密钥编号作最后字节的 MD5 初始化向量、来源是 NVIDIA 公开的 Jetson Secure Boot 文档。一个自包含公域解密器（`rijndael-tool.zip`）在频道内发布 |

完整章程及其后果见[净室与来源溯源问题](clean-room-and-provenance.md)。

---

## 2026-07-01 到 2026-07-11：booter 变得可读

这是 Falcon 安全协处理器停止是黑箱的那两周。

| 日期和时间 | 事件 |
|---|---|
| **2026-07-01T12:40:37Z** | **原始调试 booter 反汇编被贴出**：`booter_load_ga100_dbg_seccode.fuc5.asm`、545,149 字节、用 `envytools/envydis` 瞄准 `fuc5` 产生。出货利用后来用的每个 gadget 地址都是这个文件里的一条指令边界 |
| **2026-07-01** | 干净提取路径在频道内被接受：调试 `booter_load` 是 NVIDIA 自己 `.ko` 里的一个 C 数组、发布为 `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`。弄懂它花了两天。同日贴出的一个 4,196 字节描述符 blob 结果大多是零 |
| **2026-07-02** | **调试等于生产、在要紧处。** 两个二进制大小完全相同、一个纯粹从调试反汇编构建的链在生产硅片上运行。没有这个净室方法就会死。寄存器来源标准同日被接受：diff 一颗 A100 的 BAR0 对一张 170HX 的、把一切改成 A100 值 |
| **2026-07-03T17:12:52Z** | 带注释反汇编被贴出、取代一份其作者标记为未验证的 LLM 生成概览 |
| **2026-07-04** | **booter 栈从硅片外泄**、每次引导一个 dword、经 gadget `0x7de9` 把一个选定的 DMEM 字写到 SEC2 邮箱。约 35 次引导、DKMS 下每次约 90 s。`D[0xFF74]` 之下的区域无法泄露、因为 ROP 自己坐在那里。因为金丝雀每次引导重新随机、跑两遍转储并 diff 揭示哪些槽是金丝雀 |
| **2026-07-05T20:42:54Z** | `170HX_ROP_payload_v1.txt` 被贴出。为 GA100 数组命名打过补丁的 Nouveau 固件提取脚本被多位用户确认工作 |
| **2026-07-06** | 维护一个**八个具名 ROP 配方**的参数化目录、在重接点（`0x37b7` 对比 `0x37cc`）、劫持 gadget、栈风格和粉碎大小（`0xF800`、`0xF810`、`0xF820`）上不同 |
| **2026-07-09T03:03:21Z** | 带注释反汇编 **v2**、607,702 字节、11,875 行、每个 `lcall` 带一个命名被调者的内联注释 |
| **2026-07-09T10:17:09Z** | `170HX_ROP_payload_v3.txt` 被贴出 |
| **2026-07-10T13:40:14Z** | **寄存器 Gadget Atlas**、从反汇编自动生成、把每个 gadget 的寄存器效果、金丝雀条件和 `mpopaddret` 尾声制成表 |
| **2026-07-11** | 一张 10 GB 卡上一次 `0x40A` 的 LMR 编码尝试失败。分开地、CMP 100 系列是 Pascal 的声称被它自己的作者回退到 Volta |

> [!NOTE]
> **未解问题**
>
> 一条净室消息日期 **2026-07-05** 把 PCIe Gen2 当作已解锁、比复现结果早三周。要么一个从未传播的更早独立结果、要么一个误归属时间戳。只有原始消息元数据能定论它。

---

## 2026-07-12 到 2026-07-17：算力落地、仓库公开

### 算力解锁

**2026-07-12** 是节流下来的日期。工作手动流程、在任何驱动内补丁存在前：

```text
run the ROP script  ->  FLR  ->  kill the NVIDIA driver  ->  FLR again  ->  run the SM unlock script
```

FLR 意思是 `echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset`。它必须从 TTY 跑。驱动是 580.159.04 的开源内核模块、载荷由 `patch_gsp.py` 拼接进 `gsp_tu10x.bin`。`Guide_SM.sh` 把它实现为一个三写 ROP 阶段（CFG1 `0x02779000`、LMR `0x0000020B`、PLM `0xFFFFFFFF`）、一次 FLR、一次激进驱动卸载、第二次 FLR、然后经 `resource0` 带回读验证的主机写 `0x0082381C = 0x88888888` 和 `0x00823820 = 0x00000008`。

同日测得：首次完整 SM 解锁上 **12.28 TFLOPS SGEMM FP32**、由两位独立测试者报告。那张卡那次会话没取锁定基线。伴随它的 "32x" 是熔丝值 `0x5` 隐含的架构除数、引用的约 0.38 TFLOPS 出厂速率是 12.28 除以 32、不是一次分开测量。一个独立测得的约 0.39 TFLOPS 锁定速率佐证除数；见[性能](../operations/performance.md)。出厂 `FEATURE_OVERRIDE` 块被完整转储（`regs_01.txt`）、主灭杀熔丝 `0x008203f0` 被确认在 `0x00000000` 未烧断、那是这一切为何可能的理由。

到达那里花了 **超过 1100 次 fire**、其中只有约 50 次是真正不同的尝试、做工作的人后来如此说："I just couldn't have known that in advance."（我事先就是不可能知道。）

### 那周的其余部分

| 日期 | 事件 |
|---|---|
| **2026-07-12** | 在一个无 devinit 的免驱动上下文里、单独对 `0x009A0204` 的一次广播写不移动 CSTATUS；每个每-FBPA 实例必须在 `0x00900204 + n*0x4000`、n = 0..23 处写。驱动路径里单次广播写就够 |
| **2026-07-13** | **LMR 连贯性。** CFG1 被写、LMR 留在 `0x288` 时、GSP-RM 在 `kgspBootstrap` 期间把 CSTATUS 从 `0x800` 回退到 `0x200`。LMR 连贯设成 `0x28A` 时、插桩转储在全部四个检查点保持 `CSTATUS=0x800 LMR=0x28a CFG1=0x2669000 WprMeta.fbSize=0xa00000000`。一个平行净室服务器的算力解锁在此日期或之前公开、那是开源化的陈述论证 |
| **2026-07-14T21:47:02-07:00** | **`cmpunlocker` 初始提交 `9b9fb2f`。** 同日频道内宣布（宣布窗口和提交的 UTC 时间、2026-07-15T04:47:02Z、不干净排序；宣布时间近似）。发布是**免驱动 Python**：`payload/build.py`、`gsp_patch.py`、`pipeline.py`、`bar0.py`、`driver.py`、`unlock/compute.py` 和一个 `daemon/` 看门狗、完全不打驱动补丁 |
| **2026-07-14** | 几何布局被测量**不**挺过一次 FLR：CFG1 把 `0x2779000` 回退到 `0x2449000`、LMR 把 `0x20b` 回退到 `0x288`、而 SS0 和 SS1 都挺过。那个不对称是算力先于显存出货的原因。一个算力解锁 shell 脚本作为 `CMP170HX_Compute_Unlock_v8_3.sh` 泄露、随后迅速删除 |
| **2026-07-15** | 一个 `cmpunlocker` 仓库被分享的一小时内、测试者报告变砖机器和不引导的 10 GB 卡。那个窗口没确立根因、但 10 GB（`0x2082`）支持还不存在于任何驱动路径、所以怀疑方向正确。同日出现 fork。每-FBPA CFG0 在每张活分区上测得 `0x07981800` 相同 |
| **2026-07-15T18:48:10Z** | `ROP_CHAINS_1180f8` 写稿在散文中记录 `+0x18` DMEM 帧步长 |
| **2026-07-16T06:07:12Z`** | 论文作为 `main.pdf` 贴进净室服务器 |
| **2026-07-16** | **没有 PLM 把常开状态授予 FB 几何布局。** 六个 FB-几何 PLM 加 `FUSE_SS_PLM` 全部打开、CFG1、CSTATUS 和 LMR 仍挺 FLR 时回退、从不在冷启动持久（`geo_flr_survival_map_20260716.sh`）。这是出货设计在每次模块加载、于 GSP 引导路径内重新应用几何布局的结构原因。一份 **26 个不同 PLM 寄存器** 的目录同日完成 |
| **2026-07-17** | **NVIDIA 对至少一个 fork 发出 DMCA 删除通知**、把那个仓库带下线。主机 PL0 对 CFG1 的写被复现为直到 FB-几何 PLM 打开前静默丢弃（`Write failed - wrote 0x2779000, read 0x2449000`、三次、无错误信号）。流传最广的架构笔记以一个约 10% 已被证明的自我评级发布 |

> [!WARNING]
> **哪个仓库最先未解决**
>
> 2026-07-22 的三份独立一手复述把净室算力解锁器的发布放在 "about 10 days ago"（约 10 天前）、指向大约 2026-07-12、而 2026-07-13 的陈述说一个算力解锁 "was released and it's basically available to the public at this point in time"（已被发布、此时基本公开可用）。但源码被归档的那个仓库初始提交在 2026-07-14、而一个**不同拥有者**的同名仓库在 2026-07-15 正在被分享并变砖测试者。最可能的调和是至少两个不同账户下的同名仓库、"about 10 days ago" 是一个取整的回忆。归档树不能被假定是最早的净室发布。

---

## 2026-07-18：显存、一天内

项目里最密集的一天。时间戳是 UTC。

| 时间 | 事件 |
|---|---|
| **18:01:15** | `patch.diff` 被贴到 `#general-how-to-cleanroom`、从一个泄露的重分发包提取 |
| **18:26:26** | 成为出货补丁集的每个文件携带这个 `diff -Naur` 头 mtime。一棵树、写于一个瞬间 |
| **18:40:16** | LAPSUS$ 来源评估被贴出、在 `patch.diff` 后 39 分钟 |
| **19:11:01** | `06fabf2 "WORKING MEMORY UNLOCK"` 在 `memory` 分支、贴出后 **70 分钟**。提交删除整个免驱动 Python 流水线（`payload/*.py`、`daemon/` 看门狗、`.pylintrc`）并代之以六个驱动补丁 |
| **20:51:36** | `6b7d9ee "FULL WORKING THING"` |
| **21:37:17** | `99338ef "Goodbye lint"` 删除 `.github/workflows/pylint.yml` 和 `tests.yml`；`8206c16 "Goodbye tests"` 16 秒后跟随、移除最后一个测试文件 |
| **21:46:49** | `e4026e5 "Memory working!"` 合并进 `master` |

那晚出货、且仍在出货的：

| 卡 | PCI ID | 出厂 | 解锁 | CFG1 `0x009a0204` | LMR `0x00100ce0` | `targetFbBytes` |
|---|---|---|---|---|---|---|
| 8 GB | `10de:20c2` | 8192 MiB | **65536 MiB (64 GB)** | `0x02779000` | `0x0000020B` | `0x0000001000000000` |
| 10 GB | `10de:2082` | 10240 MiB | **40960 MiB (40 GB)** | `0x02669000` | `0x0000028A` | `0x0000000A00000000` |

出厂 CFG1 在**两个** SKU 上都是 `0x02449000`；出厂 LMR 是 `0x00000208`（8 GB）或 `0x00000288`（10 GB）。同在 2026-07-18：`multiple-cards` 分支被提交、`housekeeping` 分支给所有补丁加 `0x2082` 支持、master 提交 `0f9aca5 "Unlock isn't gated anymore"` 把安装门从仅 `0x20C2` 拓宽到 `0x20C2`/`0x2082`。

完整细节：[显存几何布局](../unlock/memory-geometry.md) 和[六个驱动补丁](../unlock/driver-patches.md)。

---

## 2026-07-19 到 2026-07-24：巩固、免驱动回归、和 Gen2

| 日期 | 事件 |
|---|---|
| **2026-07-19** | `multiple-cards` 分支被宣布。`80` 分支（`3c53aca "Correct LMR for 80GB"`）在 10 GB 卡上尝试 80 GB。`requirements.txt` 被删除（`7019bc2`）。`remove.sh` 被确认足够好地恢复一张卡去恢复挖矿。`cuda_dbg.py` 和 `cuda_memtest` 1.2.3 进入用作 VRAM 验证器。`unlock_host_610.sh` 被发布。项目负责人请角色持有者验证 10 GB 路径 |
| **2026-07-20 02:25** | A100 拥有者被请跑 `sudo python3 probe.py --check` 和 `--out a100.json`（`probe.py`、11,472 B） |
| **2026-07-20 16:40** | 一个 Gen2 专属探测套件被分发（`probe.py` 9,132 B、`README.md` 3,022 B、`sweep.sh` 3,007 B）"to probe and sweep registers on the A100 specifically for PCIe Gen 2"（在 A100 上专门为 PCIe Gen 2 探测和扫描寄存器）。一个带真 A100 访问的贡献者提供六份 JSON 转储。供体 A100 上的写测试不工作、所以只有读数据可用、维护者说那足够 |
| **2026-07-21** | `clanker/driver-port`（`153cd6d`）为 580/590/595/610 加按分支补丁目录。它确立 `gsp_tu10x.bin` 从不需要提取：带注释 blob 就是调试 Booter |
| **2026-07-22** | **整个开发历史的一手叙述被贴出**、独立在三个频道、确立三月到六月的序列。"Chinese unlock" 被评估为泄露的私有概念证明。几何布局被测量挺过一次无 SBR 的驱动卸载和重载。第一个 `refire_chain.py` 和它的 v2 通用写引擎重写落地。折叠检测 harness 被证明不可靠、追溯性地使一批更早的 fold-at-40 GB 结论失效。一条近免驱动 40 GB 路径被演示、仍移除一行驱动 |
| **2026-07-23** | **免驱动 Python 解锁器回归。** 一个独立显存解锁器脚本、在**驱动加载前**运行、不需要 FLR、被记录：先跑原始仅算力解锁（它确实执行一次 FLR）、然后跑显存脚本、然后加载一个干净未修改驱动。它的作者坦率说它是机器生成的、未完全理解："It is so cryptic, it is almost like a black box."（它太神秘了、几乎像一个黑箱。）`debug-gen2` 分支 tip 是 `746d9f7 "PCIe Gen 2 works!"`。`master` 到达它的归档 tip `cc872cb`、其最后两个提交加 `pull_request_template.md` 并把它移到 `.github/` 下。`docs/CONTRIBUTING.md` 指南和硬门控模板措辞（"I WILL REJECT ANY PR THAT DOES NOT FOLLOW THIS TEMPLATE!"）四天后、于 2026-07-27 在 `docs` 分支落地 |
| **2026-07-24** | **PCIe Gen2 被宣布。** `refire_chain_v6.py`（27,769 B）带模式标志 `--compute`、`--memory 40|80`、`--pcie-gen2`、`--pcie-retrain`、`--all` 发布。`pcielink.sh` 成为标准 PCIe 现场报告收集器。`check_fold.py`、解锁 VRAM 是否真实的权威测试、被发布。解锁被重述为非持久软件状态、而非固件修改：它必须每次 GSP 引导重新应用。维护者作为一个范围决定拒绝支持其它 Ampere CMP 卡 |

> [!WARNING]
> **实验性**
>
> Gen2 是真实的、被复现、**且未出货**。`master` 只携带补丁 `0001` 到 `0006`、`constants.yaml` 里没有 `pcie:` 块。`0007-pcie-gen2.patch` 存在于 `debug-gen2`、`Gen2`、`far` 和 `deced`；`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2`、`far` 和 `deced`。安装 Gen2 意味着跑一个未发布分支。见[PCIe Gen2](../unlock/pcie-gen2.md)。

---

## 2026-07-25 到 2026-07-28：归档里最后一周

| 日期 | 事件 |
|---|---|
| **2026-07-25** | 数天无人值守 LLM 代理工作没能产出一个 80 GB 解锁。`install.sh` 自动检测在混合-GPU 主机上被发现不安全：`detect_card_profile()` 读 `nvidia-smi` 顺序里第一张 GPU、不是 `lspci` 找到的 CMP、所以一张 RTX 3080 10 GB 在 8 GB 170HX 旁选错档位。始终显式传 `--profile`。对论文 Falcon 模拟器的请求被回答 "No, they did not" |
| **2026-07-26** | `Gen2` 分支到达它的 tip `a4de322`、那只是把 `master` 合并进 `Gen2`。分支的多卡支持、`verify.sh`、经补丁 `0008` 把重训练移进驱动、和删除 `tools/cmpretrain.service` 都两天前、在 2026-07-24 的 `2f27474 "Gen2 + multiple-card support"` 落地；`tools/retrain.sh` 留在树里。`far`（`8854d3e "Remove clamp link to Gen1"`）把 `RMPcieLinkSpeed` 从 `0x1` 改成 `0x2`。一个独立 `cmp170hx-gen2-setup.sh`（12,389 B）与一份 `PCIE_GEN1_LOCK.md` 分析一起发布 |
| **2026-07-26** | **Gen2 x16 被观察一次。** 一张跑 `Gen2` 分支的电容改装卡报告 `PCIe GEN 2@16x`、`ocl_pcie_bw` 在 6.63 到 6.67 GB/s、nvtop TX 在 7.061 GiB/s。一架机、一天、一张截图。置信度 **中等**；Gen2 x16 下的稳定性未确立 |
| **2026-07-27** | `deced`（`2326599 "Stupid mistake - it appears to be hardcoded"`）用 `find_gpu_bdf()` 查找替换 `tools/retrain.sh` 里硬编码的 `0a:00.0` BDF、尽管那个文件在那个谱系上是死代码。`docs` 分支到达 `651b6d5` 并被记录为非权威。一次猎寻 PCIe Gen3 跳线的两天 A100-对比-170HX 寄存器 diff 被宣布为死路；负结果就是发现。`170tune` 被发布。规范文档站点在 23:59 更新。一个多租户机架在一次被杀的 `llama.cpp` 运行后、其驱动状态被幽灵进程毁掉 |
| **2026-07-28** | 归档期结束。十二个未发布分支被快照（算上 `master` 是十三棵树）。远程上存在十六个未发布分支 ref；`code-simplification`、`dual-geometry-fix`、`fix` 和 `v0.1` 没被捕获、没被分析 |

---

## 里程碑总结

| 成就 | 日期 | 持久性 | 在 `master` 上出货？ |
|---|---|---|---|
| FP32 FMA 编译时变通方案（约 16x、6.25 TFLOPS） | 2023-10-27 | 源码级、每应用 | 不是一个驱动特性 |
| 算力节流移除（SS0/SS1、全速） | 2026-07-12 | 挺过 FLR（常开岛） | **是** |
| `cmpunlocker` 公开、免驱动 Python | 2026-07-14 / 15 | 每次引导重新应用 | 2026-07-18 移除 |
| 显存几何布局、8 GB 到 64 GB 和 10 GB 到 40 GB | 2026-07-18 | **不**挺过 FLR 或断电循环 | **是** |
| 多卡支持 | 2026-07-18 / 19 | 每次引导 | 否、仅分支 |
| 10 GB 卡上的 80 GB | 2026-07-19 | 尝试、约 40 GB 之上不稳定 | 否、而且不应 |
| 免驱动 SEC2 refire 链（v1 到 v6） | 2026-07-22 到 24 | 每次引导、GPU 必须解绑 | 否、平行路径 |
| PCIe Gen2（速度、x4） | 2026-07-24 | 每次引导、分支上驱动内 | 否、仅分支 |
| PCIe x16（位宽、靠焊接） | 硬件改装、任何日期 | 永久、物理 | 不是软件 |
| Gen2 x16 组合 | 2026-07-26、一次观察 | 未确立 | 否 |

> [!CAUTION]
> **80 GB 档位不是一个里程碑**
>
> `80` 分支报告约 81920 MiB 和 85,545,582,592 字节、`cudaMalloc` of 77 GiB 成功、但在 80 GB、触碰超过约 40 GB 的内核造成致命 GPU 丢失、与功耗上限无关。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 显存测试后的 Xid 154；主导报告症状是挂起。Xid 31 单独是一个旁观者提出的、并未被带故障卡的操作者佐证为*那个*签名。`cuda_memtest` 除非封顶在 39 GB 否则挂起。40 GB 反而出货。见[80 GB 问题](../frontier/80gb.md)。

---

## 参见

- [净室与来源溯源问题](clean-room-and-provenance.md)
- [工具谱系](tool-lineage.md)、以及哪些工具死了
- [死路](dead-ends.md)
- [解锁如何工作](../unlock/how-it-works.md) 和[算力节流](../unlock/compute-throttle.md)
- [未解问题](../frontier/open-questions.md)、截至 2026-07-28 什么仍未解决
