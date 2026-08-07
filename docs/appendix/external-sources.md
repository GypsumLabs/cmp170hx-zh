# 外部来源

**本页涵盖什么。** 本页是一份带注释的参考书目，列出本维基所依赖的所有外部资料：`cmpunlocker` 仓库及其未发布分支、NVIDIA 上游开源内核模块、170th Street 社区维基、独立拆解评测、TechPowerUp 的 VBIOS 与规格数据库、学术论文、envytools 及 Falcon 工具族，以及社区 fork、gist 和 issue 讨论串。每个条目都会说明来源的性质以及**可以信任到什么程度**，因为这里有几类被广泛引用的来源，存在明确且可具体指出的错误。

商业挂牌、市场平台、厂商产品页以及任何采购相关内容均不在本页范围内，并且已被有意排除。

## 如何阅读信任等级

| 评级 | 含义 |
|---|---|
| **Primary（主要）** | 你可以直接根据工件自行重新推导出相关结论。例如源代码、带签名的测量结果，或可以自行计算哈希的文件。 |
| **Reliable（可靠）** | 独立的一手资料，并且至少得到过一次佐证。可以放心引用，但应说明它具体是什么来源。 |
| **Use with care（谨慎使用）** | 确实有用，但存在已知的具体缺陷。引用前必须检查下方的缺陷清单。 |
| **Do not cite（不要引用）** | 已知包含看似自信、实则错误的技术内容。仅可作为历史记录使用。 |

---

## 1. 解锁实现

### `github.com/amoghmunikote/cmpunlocker`（`master` 分支）

**信任等级：Primary（主要）。** 这是发布版工具，也是所有能够用代码表达的内容的权威来源。其标语是：“A tool to unlobotomize your NVIDIA card!”（解除 NVIDIA 显卡的“脑叶切除”！）。该项目于 2026-07-14 公开；首个提交为 `9b9fb2f Initial commit`；归档的 `master` 分支顶端提交为 `cc872cb Moved PR template location`（2026-07-23）。

`master` 恰好包含八个顶层条目：`.github/pull_request_template.md`、`.gitignore`、`LICENSE`、`README.md`、`common/constants.yaml`、`driver/`、`install.sh` 和 `remove.sh`。其中**没有** `verify.sh`、**没有** `tools/` 目录、**没有** `probe.sh`、**没有** `requirements.txt`（该文件于 2026-07-19 被删除），也没有测试套件。卸载命令是 `remove.sh --yes`；**整棵目录树中都不存在 `uninstall.sh`**。

`common/constants.yaml` 是机器可读的基准真相，与补丁 `0001` 完全一致。这里有一个 README 不会告诉你的重要行为：在当前 `master` 上，`--profile` 已不再选择显存几何布局。补丁 `0001` 在 GSP 启动时根据 `pGpu->idInfo.PCIDeviceID >> 16` 进行分支；`build.sh` 的内联重写会找到全部六个标记，然后不做修改就退出；而 `--profile` 只影响横幅、`EXPECTED_MIB` 和元数据文件。2026-07-18 之前关于这一点的说明已经过时。参见[驱动补丁](../unlock/driver-patches.md)和[安装](../procedures/install.md)。

> [!WARNING]
> **README 对设备门控的描述不严谨**
>
> README 说解锁受 `0x20C2` 门控，但驱动内的门控函数 `_kgspSec2PostblTimingEnabled()` 同时接受 `0x20C2` **和** `0x2082`。发布版 `master` 根本没有 `DEBUGGING.md`：所谓“所有 PLM 都必须显示 `0xffffffff`”的说法来自 `docs` 分支，而且是错误的，因为发布版表会把 WPR_CFG `0x001fa7cc` 打开为 `0xfffff0ff`。

### 十二个未发布分支

**信任等级：作为代码是 Primary（主要），作为建议是 Experimental（实验性）。** 这些是真实但尚未合并的代码，而且有些分支内部并不一致。未发布分支快照恰好有 **12** 个（计入 `master` 后共有 13 棵代码树）：`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`。任何声称有十三或十四个*快照*的来源，都是数错了。需要注意的是，仓库在抓取时带有 **17 个分支引用**，因此有四个未发布引用从未被制作成快照，也没有在本站任何地方进行分析：`code-simplification`、`dual-geometry-fix`、`fix` 和 `v0.1`。

| 分支 | 顶端提交 | 内容 | 信任提示 |
|---|---|---|---|
| `multiple-cards` | `b1cb6d8`、2026-07-18 | 按设备 ID 划分的配置档、一个 `mixed` 配置档、`gpu_inventory`，以及只有该分支拥有的 `verify.sh` | 自包含，且最有可能被合并。它的 `verify.sh` 中的 `lspci` 回退路径会静默漏掉 `10de:20b0`。 |
| `debug-gen2` -> `Gen2` -> `far` -> `deced` | `746d9f7` -> `a4de322` -> `8854d3e` -> `2326599` | PCIe Gen2 谱系。四个分支都包含 `0007-pcie-gen2.patch`；从 `Gen2` 开始还包含 `0008-pcie-gen2-probe-retrain.patch`。`deced`（2026-07-27）是最新的。 | 见下方的危险提示。 |
| `clanker/driver-port` | `153cd6d`、2026-07-21 | 按分支划分的补丁目录 `{580,590,595,610}/`。`driver/VERSION` 列出 **12** 个版本，而 `constants.yaml` 只列出 **5** 个版本：这是项目已承认的内部不一致。它的 `install.sh` 与 `master` 逐字节相同。 | `610` 目录是 `master` 的逐字节副本。**从未有人报告过 595、590 或 580 能够启动。** |
| `80` | `3c53aca`、2026-07-19 | 针对 10 GB 卡的 80 GB 尝试 | 见下方的危险提示。 |
| `ecc` | `bb4d669`、2026-07-18 | 单一提交，标题为“Fixed dual geometry support” | **不包含任何 ECC 代码。** 这个名字会误导人。 |
| `housekeeping`、`memory` | 2026-07-18 | 中间开发状态 | `housekeeping` 的补丁实际上无法应用：加入 `0x2082` 分支时没有同步更新 `@@` hunk 数量。 |
| `PG199` | | Drive A100 快照 | 仅供参考。 |
| `docs` | `651b6d5`、2026-07-27 | 说明文档 | **不要引用。** 见下文。 |

> [!CAUTION]
> **两个会让你踩坑的分支缺陷**
>
> **`Gen2` 会安装一个 Gen1 钳制。** `debug-gen2` 和 `Gen2` 会把
> `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"` 写入
> `/etc/modprobe.d/cmp-pcie-gen2.conf`，也就是在尝试启用 Gen2 的同时，把链路固定为 Gen1。
> `far` 的提交 `8854d3e "Remove clamp link to Gen1"` 将其改为 `0x2`。究竟哪个值正确，
> **目前确实没有定论**：两个值都曾随代码发布，也不存在 A/B 启动测试。
>
> **`80` 分支实际编程的内容与其元数据不符。** `80/common/constants.yaml` 中写有
> `lmr: "0x0000028B"` 和 `81920`，但 `build.sh` 从不读取该文件。`80/driver/build.sh`
> 第 93 行将 `LMR` 设为 `"0x0000028A"`，`install.sh` 第 138 行打印
> `CFG1=0x02779000 LMR=0x0000028A`，补丁 `0001` 第 144 行则将
> `lmrValue = 0x0000028AU` 烘焙进代码。提交 `3c53aca "Correct LMR for 80GB"`
> 只修改了不会生效的元数据。所有运行过该分支的测试者实际编程的都是 CFG1 `0x02779000`、
> LMR `0x0000028A` 和 `fb_length 0x0000001400000000`；这三者彼此不一致，是该分支恰好在
> 40 GiB 处折返的最佳解释。尽管有一个净室脚本实际运行过该分支，但它的任何一次构建都没有
> 携带过彼此一致的值。参见[80 GB 问题](../frontier/80gb.md)。

### `github.com/amoghmunikote/cmpunlocker` 的 `docs` 分支

**信任等级：Do not cite（不要引用）。** 该分支有七个提交，是项目自己的文档分支，也是一个有明确记录的错误来源：`docs/ARCHITECTURE.md` 声称 `SS0 = 0xffffffff` 和 `SS1 = 0xffffffff`，但发布版补丁实际写入的是 `0x88888888` 和 `0x00000008`；`DEBUGGING.md` 声称所有 PLM 都必须读为 `0xffffffff`；`docs/INSTALLATION.md` 和该分支的 README 都指示执行 `sudo ./uninstall.sh --yes`，但这个文件并不存在；此外，它还捏造了代码和聊天记录中都找不到的缩写展开：SS 是“Suspension State”，PLM 是“Program Logic Modules”，PMM 是“Permute Mask Model”，LMR 是“LM (Local Memory) Request register”，PMA 是“Power Management Array”。它还声称驱动会输出 `SEC2_DEBUG: Executing unlock sequence...` 这一日志行，但驱动实际上从不输出该行。

### `github.com/NVIDIA/open-gpu-kernel-modules`

**信任等级：Primary（主要）。** 这是 `build.sh` 在安装时抓取的上游驱动源代码（`archive/refs/tags/${VERSION}.tar.gz`），也是带签名 Booter blob 的来源。反复用到的文件主要有三个：`src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`（包含 `IMAGE_{DBG,PROD}`、`HEADER_{DBG,PROD}`、`SIG_{DBG,PROD}` 和 `PATCH_LOC = 0x8900`）、`kernel_gsp_booter_tu102.c` 以及 `nouveau/extract-firmware-nouveau.txt`。发布版 `master` 支持的版本恰好是 `610.43.03`（默认版本）和 `610.43.02`；使用其他版本会导致构建直接失败。参见[驱动版本](../procedures/driver-versions.md)。

> [!NOTE]
> **下载内容没有完整性检查**
>
> `build.sh` 使用 `curl -L --fail` 抓取 tarball 并将其缓存，但整棵代码树中没有任何校验和或签名验证。按版本记录预期的 SHA-256 只需一行改动，但目前尚未实现。

---

## 2. 社区文档

### 170th Street（`170th-street.gitbook.io/hx`）

**信任等级：Use with care（谨慎使用）。** 这是关于这张卡规模最大的社区维基，也是截至 2026-07-27 项目自己指定的文档站点。它涵盖硬件（完整规格、拆解指南以及一页泄露的 NVIDIA A100 原理图）、改装（PCIe 电容改装、水冷）、解锁、AI 和 ML 工作负载、基准测试，以及一页 NVLink 元件布置研究。它采用基于 issue 的贡献流程，其 issue 跟踪器的第 #1 号讨论串包含大量早期研究讨论。

电容改装页面是该操作的社区参考说明，并得到独立测量的佐证，因此可以安全参考。问题出在其他地方：

- **它对 SM 数量的说法自相矛盾。** `hardware/full-specifications.md` 的 Compute 表列出 70 个 SM、4,480 个 CUDA 核心和 280 个张量核心；但它自己的“Notes on Specification Discrepancies”一节又写着“8 GB variant: 56 SMs, 4,096-bit memory bus”和“10 GB variant: 70 SMs, 5,120-bit memory bus”，`introduction/what-is-the-cmp-170hx.md` 也重复了这种分裂说法。在一张实际运行中的 8 GB 卡上，通过 PTX 特殊寄存器转储测得的数值是 **70 个 SM**。
- **它的 PCIe 页面已经过时。** `hardware/full-specifications.md` 仍写着“PCIe Gen 1 x4 (firmware locked), ~1 GB/s”，它自己的时间线页面也仍将电容改装描述为“尚未确认”。这两种说法都已经被后续证据推翻。
- **它的 FP16 对比混用了标量速率和张量速率**，拿 170HX 的标量性能去对比其他卡的张量核心性能；这一点已经在频道中被指出。
- 有人询问 `cmpunlocker` 维护者，LnkCap 和 LnkCap2 的值是否已证明来自熔丝；维护者明确表示该页面已经过时且不可信。

应将它视为一份组织良好的二级摘要。所有寄存器、熔丝或规格方面的说法，都要对照[寄存器参考](../unlock/register-reference.md)或实际测量重新验证。

### 独立拆解评测（`niconiconi.neocities.org/tech-notes/nvidia-cmp-170hx-review/`）

**信任等级：Reliable（可靠），也是本参考书目中最好的物理观察来源。** 该评测发布于 2023-10-25，比解锁工作早两年半，因此完全不受后者影响。它的关键发现被反复引用，也从未受到反驳：CMP 170HX 使用的电路板与 A100 40 GiB 几乎（如果不是完全）相同，唯一差别是 ASIC 型号 `GA100-105F-A1`；此外，电路板上有许多未装元件，包括被省略的 VRM 相位（未安装的 DrMOS 晶体管及其输出电感）和**缺失的 NVLink 相关 IC**。

最后这一点比任何寄存器值都更重要：缺失的 NVLink 接口 IC 是解锁 NVLink 的*物理*障碍，与固件中的任何内容都无关。参见[NVLink](../frontier/nvlink.md)。这篇评测也是同一作者进行 FMA 禁用工作的来源，而那项工作正是这张卡整个软件侧故事的起点。

评测附带的拆解照片托管在同一域名下，是现有资料中质量最高的 PCB 图像。

---

## 3. 规格与 VBIOS 数据库

### TechPowerUp VBIOS 合集

**信任等级：ROM 文件为 Primary（主要），不要信任元数据列。** `.rom` 映像是真实文件，可以计算哈希；但 TechPowerUp 这些条目的“Memory Size”列无法追溯到文件内部的任何字段，因此不可靠。

该合集包含四个 CMP 170HX 映像：

| 条目 | 版本 | 构建日期 | 设备 / 子系统 | 标注 | 实际情况 |
|---|---|---|---|---|---|
| 257744 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | 8 GB | 出厂生产用的 8 GB 映像，显存频率字段为 364 MHz，功耗为 250 W |
| 239457 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | “16 GB” | 除 `flash_status_ledger` 外，与 8 GB 映像**逐位相同**；该字段每次刷写都会变化，包括出厂刷写。16 GB 标签是错误的。 |
| 268495 | `92.00.6D.00.0A` | 2022-04-07 | `10DE 20C2` / `10DE 1585` | “0 GB” | **300 W** ROM：显存频率字段为 432 MHz，板卡功耗目标为 250.0 W，上限为 300.0 W，调整范围为 -60% / +20%，MD5 为 `a58aae86e72b13d50603c15653350664`。0 GB 标签是错误的。 |
| 268984 | `92.00.66.00.02` | 2021-04-23 | `10DE 2082` / `10DE 1557` | 10 GB | 10 GB 映像 |

> [!CAUTION]
> **“16 GB”和“0 GB”映像都不能解锁显存**
>
> 这两个映像的区别只在功耗和时钟字段。将 239457 刷入 10 GB 卡后，会出现黄色感叹号，驱动也不会接受该设备，因为设备 ID 不匹配。将 8 GB VBIOS 刷入 10 GB 卡则会导致显卡无法启动。另有第三个修订版 `92.00.6D.00.09`，日期为 2021-11-01，实际流通中存在，但不在 TechPowerUp 合集中：它已经带有 300 W 功耗上限，却没有显存超频。**VBIOS 版本不会影响解锁是否生效**；这一点已经在两台主机上的四张卡之间得到确认，两台主机分别运行 `92.00.67` 和 `92.00.6D.00.0A`。参见[VBIOS](../hardware/vbios.md)。

同一合集中的有用对比条目包括：A100 PCIe 40 GB（277449）、A100（283106）、A30（262595，其 `92.00.66.00.0x` 与 10 GB 170HX 映像几乎相同），以及 Tesla V100 16 GB（199146）。

### TechPowerUp GPU 规格数据库

**信任等级：Use with care（谨慎使用）。** 这张卡的正确条目是 `gpu-specs/cmp-170hx-8-gb.c3830`。

> [!CAUTION]
> **`c3824` URL 是一个陷阱**
>
> `gpu-specs/cmp-170hx.c3824` 返回 HTTP 200，然后重定向到 `/gpu-specs/radeon-pro-w6800x-duo.c3824`，也就是一个 AMD 产品页面。这个 URL 被广泛传播，甚至出现在一份 agent brief 中。用于定位的相邻 ID 为：`c3821` 是 A100 PCIe 80 GB，`c3822` 是 CMP 70HX，`c3823` 是 PG506-242。

TechPowerUp 关于晶片面积（826 mm²）、着色单元（4,480 = 70 x 64）、TMU/ROP/张量核心（280/128/280）和 L1（每个 SM 192 KB）的数据是可靠的。但它在两处重要问题上**确实有误**：它列出的是 **8 MB L2**，而 `deviceQuery` 和独立的延迟尖峰微基准都测得 **32 MB**；它将电源接口描述为“2x 8-pin”，但板卡实际使用的是一个**携带两条逻辑 12 V 供电轨的 EPS 8-pin**。此外，一位一手拥有者指出，它对 PG199 的 6144-bit 总线宽度标注也是错误的；频道中也有人指出，它给出的 CMP 部件带宽数字偶尔会出错。

---

## 4. 学术与正式出版物

### “A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor”

**信任等级：Primary（主要），也是整个净室逆向工作的唯一指定净室输入资料。** 该论文发表于 2026 年 6 月，共 16 页，Zenodo 记录编号为 **20916112**，并以 ResearchGate 出版物 **408132536** 的形式提供镜像。它于 2026-06-26 在解锁器服务器中流传，并于 2026-07-16T06:07:12Z 发布到净室服务器。

论文摘要称，CMP 170HX 使用的是“与旗舰 A100 相同的晶片，但在三个商业维度上受到熔丝裁剪限制：SM 算力速率（降至 1/32）、显存容量（10 GB 而不是 80 GB）以及 PCIe 链路（Gen1 而不是 Gen4）”；摘要还称“三个上限都是软限制”，并报告了约 31 至 62 倍的算力提升、8 倍的容量提升和 2 倍的链路提升。

它之所以是核心依据，是因为净室规则将它指定为唯一可接受的输入文档，理由是该文发表于科学出版物网站，并且已经发送给厂商。论文第 5.5 节的仿真器轨迹公开了 `buffer = 0x800`、`SIGSZ = 0xf800`、统一填充值 `V = 0x4a7`、`guard@0x6340` 以及守卫桩值 `0xc0deca7e`；发布版载荷中的大量常量都来自这里。第 8.5 节“Persistence across FLR”论证了，常电域中的覆盖值如何将一次性利用转变为持久状态。

有两点需要注意。论文用“3-4 BAR0 value changes”概括过程，这种表述误导了每一位独立实现者：真正的难点完全在于**先**打开四个 PLM，之后对 BAR0 的写入反而很简单。此外，论文的 Falcon 仿真器**从未发布**，因此无法通过最直接的途径复现其分析。另有一条二手报告称，论文描述了如何让显卡在约 35% 的吞吐损失下保持稳定；本页仅以低置信度记录这一说法，尚未验证。

论文作者拒绝了发布前禁运，并在第 10 节说明：协调披露假设厂商采取的补救措施能够保护用户；但当防御者是设备、攻击者是设备所有者时，这一假设并不成立。

### arXiv:2505.03782

**信任等级：Reliable（可靠），但经常与上一节的论文混淆。** 论文题为“Exploration of Cryptocurrency Mining-Specific GPUs in AI Applications: A Case Study of CMP 170HX”，于 2025 年 4 月 30 日提交，分类为 cs.AR 和 cs.DC。它报告称，通过在 CUDA 源码中禁用 FMA 收缩，在出厂固件上使用 OpenCL 基准、mixbench 和 LLAMA 基准进行测量后，FP32 性能超过原始能力的 **15 倍**，某些精度下的 LLM 推理性能超过 **3 倍**。它是 Canary 论文的参考文献 [13]。**它不是利用论文**，只是有一段时间社区将两者混为一谈。

围绕这张卡积累的其他 Zenodo 记录包括：18994970、19002983 和 18995979（后一项是 170HX 张量核心分析，据称因分类、风险和术语问题被 arXiv 拒绝）。

---

## 5. Falcon 逆向工程工具

### envytools / envydis（`envytools.readthedocs.io`、`github.com/envytools/envytools`）

**信任等级：对其覆盖的内容为 Reliable（可靠），对其未覆盖的内容则不作判断。** 使用 **`fuc5`** 目标的 `envydis` 成功反汇编了 GA100 Booter，生成的清单经过独立审查，并且已在真实晶片上正确执行。尽管 envytools 的表格名义上将 `fuc6` 分配给 GP102 及更晚的部件（`fuc0 [G98, MCP77, MCP79]`、`fuc3 [GT215+]`、`fuc4 [GF119+]`、`fuc5 [GK208+]`、`fuc6 [GP102+, selected engines only]`），这种组合仍然有效。170HX 的 SEC2 在形式上究竟属于 fuc5 还是 fuc6，仍未有定论；频道中记录的实际做法是：“I picked whatever worked”（哪个能用就选哪个）。

> [!NOTE]
> **未解问题**
>
> envytools 大约八年没有更新，而且**完全无法为安全启动相关材料提供佐证**：它的 Falcon 加密页面只有章节标题，没有正文；它记录的 Falcon 硬件版本只到 v5；本工作依赖的若干寄存器在其中也没有条目。有人曾提议以 `gitlab.freedesktop.org/nouveau/envyhooks` 上的 `envyhooks` 作为继任者，但后来发现它不具备等效功能。要确定 fuc5 还是 fuc6，需要对同一映像进行两种解码并比较结果，寻找只有其中一个目标能够连贯解析的指令。

同一工具族还包括：

- **`github.com/vbe0201/faucon`**：Falcon 仿真器，明确只支持 fuc5。其 `faucon-emu/src/cpu/instructions/data.rs` 被用作指令语义参考。
- **`github.com/CAmadeus/falcon-tools`**（`requiem` 子树）：Falcon 安全启动工具、密钥生成工具、载荷和逆向工程材料。需要 Python 3.6+、PyCryptodome、envytools、make 和 m4，并且没有直接针对相关代 NVIDIA GPU 的实现。
- **`github.com/karolherbst/nouveau_tools`**（`dbg_falcon.sh`）：Falcon 调试辅助工具。
- **`hexkyz.blogspot.com`**（“Je ne sais quoi: Falcons over the Horizon”，2021 年 11 月）以及 **switchbrew TSEC 页面**：Falcon 安全模式行为的标准外部参考，包括 `$sr10` 语义，以及在停机前抑制中断和异常的那个位。
- **`github.com/ttabi/extract-firmware-nova`** 和 **`github.com/NVIDIA/nova`**（`drivers/gpu/nova-core/devinit.rs`、`vbios.rs`）：NVIDIA 内核驱动的 Rust 重写版本。它们之所以有用，是因为 Rust 源码直接写出了寄存器名称，而 C 驱动将这些名称隐藏在宏后面。

---

## 6. 社区 gist 和参考表

**信任等级：作为测量记录是 Primary（主要）。** 两个重要 gist 在发布后都被删除，之后又被其他人重新 fork，因此应引用其中的内容，而不要引用某个特定 fork。

| Gist ID | 内容 | 重要性 |
|---|---|---|
| `0480d2b2b35ad594e57b6543952be307` | **GA100 熔丝与寄存器参考表**（约 50 kB），以及 `probe.sh`（约 19 kB） | 净室逆向工作的差分语料库：从 15 张 Ampere 卡上读取 120 个寄存器（2 张实体 170HX 10 GB、11 张云端租用的卡、2 张实体 Drive A100 32 GB）。它证明，恰好有 **五组**寄存器能够区分 170HX 与同一晶片的 A100：SM 速度选择、PCIe 启动代际、NVLink 禁用、ECC 启用和 FBPA CFG1 几何布局。它还证明，两张实体 170HX 在 **120 个寄存器中的 107 个**上读数一致，全部 13 个差异都是每颗晶片的分档伪影；这正是解锁配方能够在不同卡之间迁移的原因。 |
| `84cd3921788d2ffbc1e9bf8b6f2c9396` | **GA100 VBIOS 对比表**（约 27 kB），以及 `z1_dump_and_parse_vbios.sh` 和 `z2_parse_vbios_table.py` | 对七个 ROM 做了静态解析，通过启发式方法定位 CFG1 跳线表，并解码显存训练条目。转储脚本对闪存是只读的，不存在写入路径。 |
| `da...`（A100 对比）、`dafea7b6663c13edc28b33872f6e51be` | 补充 VBIOS 对比材料 | 次要来源。 |

> [!WARNING]
> **VBIOS 解析器带有过时标签**
>
> `z2_parse_vbios_table.py` 的 docstring 与它自己的输出相互矛盾。它声称 A100 PCIe 跳线表位于约 `0x3FB18`，而对比表将其定位在 `0x4285A`。它把 RFRD 标记为“power table”，但 RFRD 实际上是映像布局描述符，其中的 `field_0C` 是经过 MAC 验证的范围大小，而不是功耗上限。它的 FBPA 分档提取器会在 CFG1 表周围搜索一个窗口；如果没有其他内容符合条件，就会把 CFG1 表本身匹配出来。任何逐字采用其输出标签的人，都会把这些错误全部传播出去。

---

## 7. Fork、重实现和相邻工具

发布后的几天内，至少有六个公开仓库 fork 或重实现了这套解锁方案。没有任何一个仓库的权威性高于 `master`。

| 仓库 | 内容 | 信任等级 |
|---|---|---|
| `arabel1a/cmpunlocker`（2026-07-15） | 早期 fork | 历史记录 |
| 另外六个个人 fork 和重新打包版本 | Fork 和重新打包版本 | 历史记录。其中一个包含 `combined-multiple-cards-gen2` 分支，这是将 Gen2 工作与多卡支持合并起来的一项重要社区合并。根据本维基的匿名化政策，省略所有者姓名。 |
| `asm64-hooligan/cmpunlocker` 的 `mem_overclock` 分支 | 显存超频实验，将乘数从 72 降到 70 | 实验性、单一作者，测试已在频道中提出请求 |
| `theneocorp/cmppatcher` | **不同的方法**：直接修改 NVIDIA 驱动的**二进制文件**，使改动能够跨越驱动更新保留。报告称可以获得 3D 加速并绕过 FP32 FMA。 | 独立来源，本文未验证 |
| `abobasixseven/unlock-cmp-170hx` | **不是技术说明。** 只包含 `README.md` 和 `cmp90_compute_unlock_prompt.md`，两者结尾都有让 AI agent 执行的指令，例如“EXECUTE STEP BY STEP: 5 -> 6 -> 6.5 -> 7”，并且在备份和克隆命令中到处硬编码了某个用户的主目录。 | 谨慎使用。它的寄存器表与发布版补丁一致；但其中的说明文字和 PCIe 章节只是二级摘要，不是测量结果。 |
| `eastmoe/CMPGPU-patch-script`（`optimize-cmp-cuda.py`） | 交互式 llama.cpp 源码补丁工具，包含五组彼此独立、默认均为关闭的优化：`fp32_fma_flag`（加入 `-fmad=false`）、`fp32_fma_split`（在 `quantize.cu` 中将 `fmaf(...)` 重写为 `__fadd_rn(__fmul_rn(...))`）、`math_intrinsics`、`dp2a`、`fp16_bf16_cuda_core`。它在七个文件中包含 11 个 PatchSpec 条目，支持 `.cmp-bak` 备份以及 `--dry-run`/`--no-backup`/`--restore`。 | Reliable（可靠）；但其 README 自己也警告，在非 170HX 的 CC 8.x 设备上性能可能**下降**。 |
| `cachenetics/170tune` | 调优和鉴定工具，安装为 `/usr/local/bin/170hx-oc`；负责测量、门控和恢复时钟与电压设置，并将“一次完成的基准测试视为毫无证据” | 方法可靠。设置是否能跨重启保持，是其作者自己标记的未解问题。参见[调优](../operations/tuning.md)。 |
| `Kepling5001/Miners`（`CMP170HX_Compute_Unlock_v8_3.sh`） | 一个公开泄露后很快被删除的算力解锁 shell 脚本。作者称它是“just the compute only logic ... with some minor modifications to attempt to run on multiple GPU's vs 1. Nothing new”（只是纯算力逻辑……加了一些尝试在多张 GPU 而不是一张上运行的小改动，没有新内容） | 仅具历史价值。不包含任何显存解锁内容。 |
| `arabel1a/ml-on-cmp`、`arabel1a/gpu-micro-bench` | 微基准仓库 | 对其发布的测量结果而言可靠 |
| `Highwayaiexpose/CMP-170hx-64gb-LLM-benchmarks` | 解锁后的 64 GB 卡上的社区 LLM 基准合集 | 谨慎使用：特定平台、单一来源 |
| `InnovativeOSS117/Gaming-on-A100` | GA100 上的图形工作 | 相邻资料；与显示输出和 3D 问题有关 |

### 第三方验证与测量工具

反复使用、值得了解的工具包括：`ComputationalRadiationPhysics/cuda_memtest`（v1.2.3，维护者推荐的 VRAM 验证工具，遇到第一个错误即退出；在 80 GB 配置档上如果不限制在 39 GB，则会**无限挂起**）、`GpuZelenograd/memtest_vulkan`、`wilicc/gpu-burn`、`ProjectPhysX/OpenCL-Benchmark`、`ReinForce-II/mmapeak`（张量吞吐）、`zzc0721/torch-performance-test-data`（GEMM）、`sasha0552/nvidia-pstated`（空闲功耗管理；见其 issue #6），以及为没有可调整 BAR 固件支持的主机提供支持的 `xCuri0/ReBarUEFI`。

---

## 8. Issue 讨论串与讨论轨迹

**`github.com/dartraiden/NVIDIA-patcher` issue #73。** *信任等级：作为记录是 Reliable（可靠），作为分析则不可靠。* 整项工作的起点就在这里：事件始于 2026 年 3 月，随后于 4 月转移到 Discord。该讨论串还记录了显存跳线的解释（“每个 HBM2 堆栈中可寻址 RAM 的数量，由某个 DMEM 区域特定位置上的 32 位字定义”）、跳线电阻讨论（R999/R1000 处的 Strap4、PCIE_CFG），以及首次公开的“40 GB confirmed working”报告。需要注意，NVIDIA-patcher 项目**本身无法驱动 170HX**：它面向图形，生成的是 GeForce 类 GPU，而不是算力解锁结果。将它应用于 170HX 不会影响 FP32 节流。

该讨论串链接的一篇 2026 年 4 月技术说明，在约 18 小时的自动化分析后得出“the FP throttle is hardware enforced and can't be overridden”（FP 节流由硬件强制执行，无法覆盖）的结论。该页面自己的页脚说明，分析是在驱动 **535.288.01** 上进行的；这个版本早于发布版解锁器所针对的 GSP 布局，而且其结论已经被发布版算力解锁反驳。这是一个“记录十分详尽但答案错误”的典型例子。

**`github.com/ggml-org/llama.cpp`**：issue #24616（在 PCIe 1.1 x4 的 90HX 上达到 240 t/s pp512 的 CMP 专用补丁集）、issue #24730（不支持 DSA 注意力，这也是 GLM 类模型会回退到稠密注意力并在本卡上变得不可用的原因）、PR #19378（通过 `--split-mode tensor` 实现与后端无关的张量并行），以及讨论 #15013。参见[LLM 推理](../operations/llm-inference.md)。

**`github.com/JustVugg/colibri`**、**`github.com/LaurieWired/tailslayer`**（刷新时序调优）、**`github.com/microsoft/Tutel`**、**`github.com/sgl-project/sglang`**、**`ikawrakow/ik_llama.cpp`**：这些都是围绕工作负载流程流传的相邻工具，原始资料中没有任何一个经过这张卡的验证。

**FluidX3D issue #8（2023-10-27）。** 原始 FMA 禁用发现的功劳属于这个讨论串，比该技术于 2023-12-06 出现在 NVIDIA-patcher issue #73 中早两个月。针对 `src/lbm.cpp` 中 `LBM_Domain::device_defines()` 的两行补丁（索引 `d99202f..28aeb25`，约第 286 行），通过宏遮蔽将 `#pragma OPENCL FP_CONTRACT OFF` 应用到每个生成的 OpenCL 程序，而不修改内核源码。去除 FMA 后，在 1175 GB/s 下测得 **7,681 MLUPs/s**，相比出厂状态的 2,276 MLUPs/s 提升了 **3.4 倍**。此外，NVIDIA-patcher 讨论串报告，同一技术使 170HX 的 FP32 从 **0.395 → 6.285 TFLOPS，即 15.9 倍**。两者都是 2023 年锁定状态显卡的结果。（6.25 TFLOPS 是另一种锁定模式下的自定义 GEMM 读数，在资料库中被记录为解锁失败的特征；不要把它归到上述结果中。）

---

## 9. 有意排除的来源

- **各种商业链接和市场平台链接。** 采购内容不在本维基范围内。
- **分销商零件编号。** 电容改装所用零件曾流传过两个不同的分销商 SKU，但没有来源能够确定哪个是正确的。本维基只引用厂商零件：Taiyo Yuden `MAASJ105SB7224KFCA01`（220 nF、6.3 V、X7R、0402）。参见[物理改装](../operations/physical-mods.md)。
- **泄露材料。** 2022 年 2 月至 3 月的 NVIDIA 泄露缓存，只作为来源溯源问题出现在记录中。本文不使用、不引用，也不链接其中的内容。参见[净室与来源溯源](../history/clean-room-and-provenance.md)。
- **作为证据分享的 AI 聊天记录。** 资料库中有几十份被分享的助手对话。它们只被记录为线索和有文档记录的幻觉，从不作为来源使用。
- **视频教程。** 这类视频有多份，使用多种语言，但没有任何一份能够通过寄存器或日志进行验证，因此一份也不引用。

---

## 相关页面

- [保留工件](artifacts.md)
- [方法论](methodology.md)
- [净室与来源溯源](../history/clean-room-and-provenance.md)
- [工具谱系](../history/tool-lineage.md)
- [失败路线](../history/dead-ends.md)
