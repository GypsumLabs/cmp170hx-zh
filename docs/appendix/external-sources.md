# 外部来源

**本页涵盖什么。** 一份带注释的参考书目，列出本维基所依赖的每个外部参考资料：`cmpunlocker` 仓库及其未发布分支、上游 NVIDIA 开源内核模块、170th Street 社区维基、独立拆解评测、TechPowerUp VBIOS 与规格数据库、学术论文、envytools 及 Falcon 工具族，以及社区 fork、gist 和 issue 线程。每个条目说明来源是什么以及**该信任到什么程度**，因为这里被广泛引用的若干来源在特定、可识别的方式上是错的。

商业挂牌、市场、厂商产品页以及任何采购相关的内容不在范围内、被刻意排除。

## 如何阅读信任列

| 评级 | 含义 |
|---|---|
| **Primary（主要）** | 你可以自己从工件重新推导该声称。源代码、一次带签名的测量，或一个你可以算哈希的文件。 |
| **Reliable（可靠）** | 独立、一手、且至少被佐证过一次。可自由引用，但要说明它是什么。 |
| **Use with care（谨慎使用）** | 确实有用，但带有已知的具体缺陷。引用前务必检查下面的缺陷清单。 |
| **Do not cite（不要引用）** | 已知含有自信的错误技术内容。只作为历史记录有用。 |

---

## 1. 解锁实现

### `github.com/amoghmunikote/cmpunlocker`（`master` 分支）

**信任：Primary（主要）。** 这是出货工具、也是任何可用代码表述之事的权威。标语："A tool to unlobotomize your NVIDIA card!"（一个给你的 NVIDIA 卡做解除"脑叶切除"的工具！）。2026-07-14 公开；首个提交 `9b9fb2f Initial commit`；归档的 `master` 顶端是 `cc872cb Moved PR template location`（2026-07-23）。

`master` 恰好包含八个顶层条目：`.github/pull_request_template.md`、`.gitignore`、`LICENSE`、`README.md`、`common/constants.yaml`、`driver/`、`install.sh`、`remove.sh`。**没有** `verify.sh`、**没有** `tools/` 目录、**没有** `probe.sh`、**没有** `requirements.txt`（2026-07-19 删除）也没有测试套件。卸载器是 `remove.sh --yes`；**`uninstall.sh` 在整棵树里都不存在**。

`common/constants.yaml` 是机器可读的基准真相、与补丁 `0001` 完全一致。注意一个读 README 不会告诉你的重要行为：在当前 `master` 上、`--profile` 不再选择几何布局。补丁 `0001` 在 GSP 引导时按 `pGpu->idInfo.PCIDeviceID >> 16` 分支、`build.sh` 的内联重写找到全部六个标记并无编辑地退出、而 `--profile` 只影响横幅、`EXPECTED_MIB` 和元数据文件。2026-07-18 前的指示在这点上已过时。见[驱动补丁](../unlock/driver-patches.md) 和[安装](../procedures/install.md)。

> [!WARNING]
> **README 对设备门控很松散**
>
> 它说解锁是 `0x20C2`-门控的、而驱动内门控 `_kgspSec2PostblTimingEnabled()` 接受 `0x20C2` **和** `0x2082`。Master 根本不出货 `DEBUGGING.md`："all PLMs must show `0xffffffff`" 那行活在 `docs` 分支上、而且它是错的、因为出货表把 WPR_CFG `0x001fa7cc` 打开到 `0xfffff0ff`。

### 十二个未发布分支

**信任：作为代码是 Primary（主要）、作为建议是 Experimental（实验性）。** 真实代码、未合并、且在若干案例里内部不一致。恰好有 **12** 个未发布分支快照（算上 `master` 是 13 棵树）：`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`。任何声称有十三或十四个*快照*的来源都在数错。注意该仓库在抓取时携带 **17 个分支引用**、所以有四个未发布引用从未被快照、也从未在本站任何地方被分析：`code-simplification`、`dual-geometry-fix`、`fix` 和 `v0.1`。

| 分支 | 顶端 | 它是什么 | 信任注意 |
|---|---|---|---|
| `multiple-cards` | `b1cb6d8`、2026-07-18 | 每-设备-ID 配置档、一个 `mixed` 配置档、`gpu_inventory`、和仅该分支有的 `verify.sh` | 自包含且最可能合并。它的 `verify.sh` lspci 回退静默丢弃 `10de:20b0`。 |
| `debug-gen2` -> `Gen2` -> `far` -> `deced` | `746d9f7` -> `a4de322` -> `8854d3e` -> `2326599` | PCIe Gen2 谱系。四个上都有 `0007-pcie-gen2.patch`；`0008-pcie-gen2-probe-retrain.patch` 自 `Gen2` 起。`deced`（2026-07-27）最新。 | 见下面的危险注意。 |
| `clanker/driver-port` | `153cd6d`、2026-07-21 | 每-分支补丁目录 `{580,590,595,610}/`。`driver/VERSION` 列出 **十二** 个版本、`constants.yaml` 却 **五** 个：一个被承认的内部不一致。它的 `install.sh` 与 master 的逐字节相同。 | `610` 目录是 master 的逐字节副本。**595、590 或 580 上从未报告过引导。** |
| `80` | `3c53aca`、2026-07-19 | 10 GB 卡的 80 GB 尝试 | 见下面的危险注意。 |
| `ecc` | `bb4d669`、2026-07-18 | 单一提交、"Fixed dual geometry support" | **不含任何 ECC 代码。** 名字有误导性。 |
| `housekeeping`、`memory` | 2026-07-18 | 中间开发状态 | `housekeeping` 的补丁本不会被应用：加 `0x2082` 臂时 `@@` hunk 数没有更新。 |
| `PG199` | | Drive A100 快照 | 仅作参考。 |
| `docs` | `651b6d5`、2026-07-27 | 散文文档 | **不要引用。** 见下文。 |

> [!CAUTION]
> **两个会坑你的分支缺陷**
>
> **`Gen2` 安装一个 Gen1 钳位。** `debug-gen2` 和 `Gen2` 把
> `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"` 写进
> `/etc/modprobe.d/cmp-pcie-gen2.conf`、在尝试启用 Gen2 的同时把链路钉在 Gen1。
> `far` 提交 `8854d3e "Remove clamp link to Gen1"` 把它改成 `0x2`。哪个值正确
> **真的未解决**：两者都出货、且不存在 A/B 引导测试。
>
> **`80` 分支不编程它元数据说的东西。** `80/common/constants.yaml` 携带
> `lmr: "0x0000028B"` 和 `81920`、但 `build.sh` 从不读那个文件。`80/driver/build.sh`
> 第 93 行设 `LMR="0x0000028A"`、`install.sh` 第 138 行打印 `CFG1=0x02779000 LMR=0x0000028A`、
> 补丁 `0001` 第 144 行烘焙 `lmrValue = 0x0000028AU`。提交 `3c53aca "Correct LMR for 80GB"`
> 只改了惰性元数据。每个跑过该分支的测试者都编程了 CFG1 `0x02779000`、
> LMR `0x0000028A` 和 `fb_length 0x0000001400000000`、一个三方不一致、那是该分支恰在 40 GiB 处折叠的最佳解释。该分支没有任何构建携带过
> 那个一致的值、尽管一个净室脚本 fire 过它。
> 见[80 GB 问题](../frontier/80gb.md)。

### `github.com/amoghmunikote/cmpunlocker` 分支 `docs`

**信任：不要引用。** 七个提交。它是项目自己的文档分支、而且它是一份有据可查的错误来源：`docs/ARCHITECTURE.md` 声称 `SS0 = 0xffffffff` 和 `SS1 = 0xffffffff`、而出货补丁写 `0x88888888` 和 `0x00000008`；`DEBUGGING.md` 说所有 PLM 必须读 `0xffffffff`；`docs/INSTALLATION.md` 和分支 README 两者都指示 `sudo ./uninstall.sh --yes`、一个不存在的文件；它还杜撰了在代码或聊天里任何地方都找不到的缩写展开（SS 为 "Suspension State"、PLM 为 "Program Logic Modules"、PMM 为 "Permute Mask Model"、LMR 为 "LM (Local Memory) Request register"、PMA 为 "Power Management Array"）。它还断言一条驱动从不发出的 `SEC2_DEBUG: Executing unlock sequence...` 日志行。

### `github.com/NVIDIA/open-gpu-kernel-modules`

**信任：Primary（主要）。** `build.sh` 安装时抓取的上游驱动源码（`archive/refs/tags/${VERSION}.tar.gz`）、以及带签名 booter blob 的来源。三个文件反复要紧：`src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`（持有 `IMAGE_{DBG,PROD}`、`HEADER_{DBG,PROD}`、`SIG_{DBG,PROD}` 和 `PATCH_LOC = 0x8900`）、`kernel_gsp_booter_tu102.c`、和 `nouveau/extract-firmware-nouveau.txt`。出货 `master` 上受支持的版本恰好是 `610.43.03`（默认）和 `610.43.02`；其它任何东西构建都会硬失败。见[驱动版本](../procedures/driver-versions.md)。

> [!NOTE]
> **下载无完整性检查**
>
> `build.sh` 用 `curl -L --fail` 抓取 tarball 并缓存它、整棵树里没有任何校验和或
> 签名验证。按版本记录一个预期 SHA-256 会是一行改进、而且还没做。

---

## 2. 社区文档

### 170th Street（`170th-street.gitbook.io/hx`）

**信任：谨慎使用。** 这张卡最大的社区维基、也是截至 2026-07-27 项目自己提名的文档站。它的结构覆盖硬件（完整规格、拆解指南、一张泄露的 NVIDIA A100 原理图页）、改装（PCIe 电容改装、水冷）、解锁、AI 和 ML 工作负载、基准、和一张 NVLink 布件研究页。它跑一个基于 issue 的贡献流程、它的 issue 跟踪线程 #1 持有大量早期研究讨论。

电容改装页是该流程的参考社区写稿、并被独立测量佐证、所以它安全。问题在别处：

- **它在 SM 数上自相矛盾。** `hardware/full-specifications.md` 给出一个带 70 个 SM、4,480 个 CUDA 核和 280 个张量核的 Compute 表、而它自己的 "Notes on Specification Discrepancies" 一节说 "8 GB variant: 56 SMs, 4,096-bit memory bus" 和 "10 GB variant: 70 SMs, 5,120-bit memory bus"、`introduction/what-is-the-cmp-170hx.md` 也重复这个分裂。在一张活 8 GB 卡上、用 PTX 特殊寄存器转储测得的值是 **70 个 SM**。
- **它的 PCIe 页过时了。** `hardware/full-specifications.md` 仍说 "PCIe Gen 1 x4 (firmware locked), ~1 GB/s"、它自己的时间线页仍把电容改装描述为未确认。两者都已被超越。
- **它的 FP16 对比混了标量与张量速率**、把 170HX 的标量性能对其它卡的张量核性能比较、这在频道内被指出。
- `cmpunlocker` 维护者被问 LnkCap 和 LnkCap2 值是否被证明是熔丝派生时、显式宣布它过时且不可信。

把它当一份组织良好的二级摘要。对照[寄存器参考](../unlock/register-reference.md) 或一次测量重新验证任何寄存器、熔丝或规格声称。

### 独立拆解评测（`niconiconi.neocities.org/tech-notes/nvidia-cmp-170hx-review/`）

**信任：Reliable（可靠）、且是参考书目里最好的物理观察来源。** 2023-10-25 发布、比解锁工作早两年半、所以完全不受它污染。它的关键发现、被频繁引用且从未被反驳：CMP 170HX 用的电路板与 A100 40 GiB 几乎如果不是完全相同的、唯一差别是 ASIC 型号 `GA100-105F-A1`、而且板上有大量未装元件、包括被省去的 VRM 相位（被去装的 DrMOS 晶体管及其输出电感）和 **缺失的 NVLink 相关 IC**。

最后这点比任何寄存器值都更要紧：缺失的 NVLink 接口 IC 对 NVLink 解锁是一个*物理*障碍、独立于固件里任何东西。见[NVLink](../frontier/nvlink.md)。该评测也是同一作者禁用-FMA 工作的来源、那是这张卡整个软件侧故事的起点。

评测附带的拆解照片托管在同一域名、是语料库里最高质量的 PCB 图像。

---

## 3. 规格与 VBIOS 数据库

### TechPowerUp VBIOS 合集

**信任：对 ROM 文件是 Primary（主要）、不要信任元数据列。** `.rom` 映像是真的且可哈希；TechPowerUp 自己对这些条目的 "Memory Size" 列无法追溯到文件内任何字段、而且不可靠。

合集里存在四个 CMP 170HX 映像：

| 条目 | 版本 | 构建 | 设备 / 子系统 | 标签 | 实际 |
|---|---|---|---|---|---|
| 257744 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | 8 GB | 出厂生产 8 GB 映像、364 MHz 显存字段、250 W |
| 239457 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | "16 GB" | 除 `flash_status_ledger` 外与 8 GB 映像**逐位相同**、那字段每次刷写都变、包括出厂时。16 GB 标签是错的。 |
| 268495 | `92.00.6D.00.0A` | 2022-04-07 | `10DE 20C2` / `10DE 1585` | "0 GB" | **300 W** ROM：432 MHz 显存字段、板功耗目标 250.0 W、上限 300.0 W、调整范围 -60% / +20%、MD5 `a58aae86e72b13d50603c15653350664`。0 GB 标签是错的。 |
| 268984 | `92.00.66.00.02` | 2021-04-23 | `10DE 2082` / `10DE 1557` | 10 GB | 10 GB 映像 |

> [!CAUTION]
> **'16 GB' 和 '0 GB' 映像都不解锁显存**
>
> 它们只在功耗和时钟字段上不同。把 239457 刷到一张 10 GB 卡上产生一个黄色
> 感叹号且无驱动接受、因为设备 ID 不匹配。把 8 GB VBIOS 刷到一张 10 GB 卡上让卡
> 无法引导。第三个修订、`92.00.6D.00.09`、日期 2021-11-01、存在于野外但不在 TechPowerUp 合集里：它已经携带
> 300 W 上限但没有显存超频。**VBIOS 版本对解锁是否工作没有影响**、在
> 两台跑 `92.00.67` 和 `92.00.6D.00.0A` 的主机上跨四张卡被确认。见[VBIOS](../hardware/vbios.md)。

同合集的可用对比条目：A100 PCIe 40 GB（277449）、A100（283106）、A30（262595、它的 `92.00.66.00.0x` 几乎与 10 GB 170HX 映像相同）、和 Tesla V100 16 GB（199146）。

### TechPowerUp GPU 规格数据库

**信任：谨慎使用。** 这张卡的正确条目是 `gpu-specs/cmp-170hx-8-gb.c3830`。

> [!CAUTION]
> **`c3824` URL 是一个陷阱**
>
> `gpu-specs/cmp-170hx.c3824` 返回 HTTP 200 并重定向到
> `/gpu-specs/radeon-pro-w6800x-duo.c3824`、一个 AMD 产品页。它被广泛流传、
> 包括在一个代理简报里。相邻 ID 供定位：`c3821` 是 A100 PCIe 80 GB、
> `c3822` 是 CMP 70HX、`c3823` 是 PG506-242。

TechPowerUp 在晶片尺寸（826 mm²）、着色单元（4,480 = 70 x 64）、TMU/ROP/张量核（280/128/280）和 L1（每 SM 192 KB）上可靠。它在要紧的两种方式上**错了两次**：它列 **8 MB L2**、而 deviceQuery 和独立延迟尖峰微基准都测到 **32 MB**、它把电源连接器描述为 "2x 8-pin"、而板上是一个携带两条逻辑 12 V 轨的 **EPS 8-pin**。它的 PG199 6144-bit 总线挂牌也被一位一手拥有者说错。它 CMP 部件的带宽数字被频道内标记为偶尔错误。

---

## 4. 学术与正式出版物

### "A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"

**信任：Primary（主要）、且是整个净室工作唯一指定的干净输入。** 2026 年 6 月、16 页、Zenodo 记录 **20916112**、镜像为 ResearchGate 出版物 **408132536**。2026-06-26 在解锁者服务器流传、2026-07-16T06:07:12Z 贴进净室服务器。

它的摘要说 CMP 170HX 是"与旗舰 A100 相同的晶片、但在三个商业轴上是熔丝残废的：SM 算力速率（节流到 1/32）、显存容量（10 GB 而非 80 GB）、和 PCIe 链路（Gen1 而非 Gen4）"、说"三个上限都是软的"、并报告约 31 到 62x 算力、8x 容量和 2x 链路的主要增益。

为什么它承重：净室规则指定它为唯一可接受的输入文档、理由是它发布在一个科学出版物站点上、且已被寄给厂商。它的 5.5 节仿真器迹线发布 `buffer = 0x800`、`SIGSZ = 0xf800`、均匀填充 `V = 0x4a7`、`guard@0x6340` 和守卫桩值 `0xc0deca7e`、那是出货载荷大量常量的来源。它的 8.5 节、"Persistence across FLR"、是常开岛里的覆盖值把一次性利用变成持久状态的论证。

两个注意。它的 "3-4 BAR0 value changes" 框架误导了每个独立实现者：难点完全在**先**打开四个 PLM、之后的 BAR0 写是琐碎的。而它的 Falcon 仿真器**从未被发布**、这关闭了复现其分析最直接的路线。一条二手报告说论文描述把卡稳定在约 35% 吞吐惩罚下、在此以低置信记录、未验证。

论文作者拒绝发布前禁运、在第 10 节论证协调披露假设厂商的补救保护用户、当防御者是设备而对手是它的主人时这不成立。

### arXiv:2505.03782

**信任：Reliable（可靠）、且经常与上面混淆。** "Exploration of Cryptocurrency Mining-Specific GPUs in AI Applications: A Case Study of CMP 170HX"、2025 年 4 月 30 日提交、分类 cs.AR 和 cs.DC。它报告 FP32 超过原能力 **15x**、某些精度下 LLM 推理超过 **3x**、通过在 CUDA 源码里禁用 FMA 收缩实现、在出厂固件上、用 OpenCL 基准、mixbench 和 LLAMA 基准测量。它是 Canary 论文的引用 [13]。**它不是利用论文**、而且有一段时间社区把两者混为一谈。

围绕这张卡积累的其它 Zenodo 记录：18994970、19002983、和 18995979（一份 170HX 张量核分析、据报被 arXiv 因分类、风险和术语拒绝）。

---

## 5. Falcon 逆向工程工具

### envytools / envydis（`envytools.readthedocs.io`、`github.com/envytools/envytools`）

**信任：对它覆盖的是 Reliable（可靠）、对它没覆盖的保持沉默。** 带 **`fuc5`** 目标的 `envydis` 成功反汇编 GA100 booter、产生的清单被独立审查并在硅片上正确执行。这有效、尽管 envytools 表名义上把 `fuc6` 分配给 GP102 及更晚部件（`fuc0 [G98, MCP77, MCP79]`、`fuc3 [GT215+]`、`fuc4 [GF119+]`、`fuc5 [GK208+]`、`fuc6 [GP102+, selected engines only]`）。170HX SEC2 是正式 fuc5 还是 fuc6 保持开放；频道内记录的实际答案是 "I picked whatever worked"（我选了管用的那个）。

> [!NOTE]
> **未解问题**
>
> envytools 大约八年没更新、而且它**完全无法佐证安全启动材料**：它的 Falcon 加密页
> 有标题没内容、它只文档化到 v5 的 Falcon 硬件版本、而且它没有本工作依赖的
> 若干寄存器条目。`gitlab.freedesktop.org/nouveau/envhooks` 上的 `envyhooks`
> 被建议为继任者、被发现缺乏等效功能。定案 fuc5 对 fuc6 需要
> 对同一映像两种解码做一个 diff、找只有一个目标能连贯解析的指令。

这个族里还有：

- **`github.com/vbe0201/faucon`**：一个 Falcon 仿真器、明确仅 fuc5。它的 `faucon-emu/src/cpu/instructions/data.rs` 被用作指令语义参考。
- **`github.com/CAmadeus/falcon-tools`**（`requiem` 子树）：Falcon 安全启动工具、密钥生成、载荷和逆向工程材料。需要 Python 3.6+、PyCryptodome、envytools、make 和 m4、不直接针对相关代的任何 NVIDIA GPU。
- **`github.com/karolherbst/nouveau_tools`**（`dbg_falcon.sh`）：一个 Falcon 调试辅助。
- **`hexkyz.blogspot.com`**（"Je ne sais quoi: Falcons over the Horizon"、2021 年 11 月）和 **switchbrew TSEC 页**：Falcon 安全模式行为的标准外部参考、包括 `$sr10` 语义和那条在停机前抑制中断和异常的位。
- **`github.com/ttabi/extract-firmware-nova`** 和 **`github.com/NVIDIA/nova`**（`drivers/gpu/nova-core/devinit.rs`、`vbios.rs`）：NVIDIA 内核驱动的 Rust 重写、有用因为它在普通源码里命名寄存器、而 C 驱动把它们藏在宏后面。

---

## 6. 社区 gist 和参考表

**信任：作为测量记录是 Primary（主要）。** 两个重要的 gist 在发布后都被删除、并被他人重新 fork、所以引用内容、不要引用某个特定 fork。

| Gist ID | 内容 | 为什么要紧 |
|---|---|---|
| `0480d2b2b35ad594e57b6543952be307` | **GA100 熔丝与寄存器参考表**（约 50 kB）加 `probe.sh`（约 19 kB） | 净室的差分语料：跨 15 张 Ampere 卡（2 张物理 170HX 10 GB、11 张云端租用、2 张物理 Drive A100 32 GB）读 120 个寄存器。确立**恰好五个**寄存器组把 170HX 与同一颗硅的 A100 区分开：SM 速度选择、PCIe 引导代、NVLink 禁用、ECC 使能、和 FBPA CFG1 几何布局。还确立两张物理 170HX 单元在 **120 个寄存器里 107 个** 上一致、全部 13 个差异是每-晶片分级伪影、那正是让解锁配方在卡之间可转移的原因。 |
| `84cd3921788d2ffbc1e9bf8b6f2c9396` | **GA100 VBIOS 对比表**（约 27 kB）加 `z1_dump_and_parse_vbios.sh` 和 `z2_parse_vbios_table.py` | 七个 ROM 被静态解析、CFG1 跳线表用启发式定位、显存训练条目被解码。转储脚本对闪存是只读的：不存在写路径。 |
| `da...`（A100 对比）、`dafea7b6663c13edc28b33872f6e51be` | 补充 VBIOS 对比材料 | 次要。 |

> [!WARNING]
> **VBIOS 解析器携带过时标签**
>
> `z2_parse_vbios_table.py` 的 docstring 与它自己的输出矛盾。它声称 A100 PCIe 跳线
> 表坐在约 `0x3FB18`、而对比表把它放在 `0x4285A`。它把 RFRD 标为
> "power table"、而 RFRD 是一个映像布局描述符、它的 `field_0C` 是一个 MAC-验证的
> 范围大小、不是功耗上限。它的 FBPA 分级提取器搜索 CFG1 表周围的一个窗口、
> 若没有其它符合就会匹配 CFG1 表本身。任何逐字用其输出标签的人都会传播所有这些。

---

## 7. Fork、重实现和相邻工具

至少有六个公共仓库在发布后几天内 fork 或重实现了解锁。没有一个对 `master` 有权威性。

| 仓库 | 它是什么 | 信任 |
|---|---|---|
| `arabel1a/cmpunlocker`（2026-07-15） | 早期 fork | 历史性 |
| 另外六个个人 fork 和重新打包 | Fork 和重新打包 | 历史性。其中一个携带 `combined-multiple-cards-gen2` 分支、一个值得注意的 Gen2 工作与多卡支持的社区合并。按本维基的匿名化政策省略拥有者名字。 |
| `asm64-hooligan/cmpunlocker` 分支 `mem_overclock` | 显存超频实验、乘数从 72 降到 70 | 实验性、单一作者、测试在频道内被请求 |
| `theneocorp/cmppatcher` | 一个**不同的方法**：直接补丁 NVIDIA 驱动**二进制**、让改动挺过驱动更新。报告 3D 加速和 FP32 FMA 绕过。 | 独立、此处未验证 |
| `abobasixseven/unlock-cmp-170hx` | **不是一份写稿。** 只含 `README.md` 和 `cmp90_compute_unlock_prompt.md`、两者都以 AI-agent 执行指令结尾、如 "EXECUTE STEP BY STEP: 5 -> 6 -> 6.5 -> 7"、并在其备份和克隆命令里硬编码一个用户的主目录。 | 谨慎使用。它的寄存器表匹配出货补丁；它的散文和 PCIe 章节是二级摘要、不是测量。 |
| `eastmoe/CMPGPU-patch-script`（`optimize-cmp-cuda.py`） | 交互式 llama.cpp 源码补丁器、带五个独立优化组、每个默认 no：`fp32_fma_flag`（加 `-fmad=false`）、`fp32_fma_split`（在 `quantize.cu` 里把 `fmaf(...)` 重写为 `__fadd_rn(__fmul_rn(...))`）、`math_intrinsics`、`dp2a`、`fp16_bf16_cuda_core`。跨七个文件 11 个 PatchSpec 条目、`.cmp-bak` 备份、`--dry-run`/`--no-backup`/`--restore`。 | Reliable（可靠）、它自己的 README 警告在非 170HX 的 CC 8.x 设备上性能可能**下降**。 |
| `cachenetics/170tune` | 调优和鉴定 harness、安装为 `/usr/local/bin/170hx-oc`；测量、门控和恢复时钟与电压设置、把"一次完成的基准当作什么都不是的证据"。 | 方法上 Reliable（可靠）。它是否跨重启持久化设置是一个它自己作者标记的未解问题。见[调优](../operations/tuning.md)。 |
| `Kepling5001/Miners`（`CMP170HX_Compute_Unlock_v8_3.sh`） | 一个被公开泄露并很快删除的算力解锁 shell 脚本。它的作者描述它为"just the compute only logic ... with some minor modifications to attempt to run on multiple GPU's vs 1. Nothing new"（只是纯算力逻辑……带一些小修改以尝试在多 GPU 而非 1 上跑。没有新东西） | 仅历史性。不含任何关于显存解锁的东西。 |
| `arabel1a/ml-on-cmp`、`arabel1a/gpu-micro-bench` | 微基准仓库 | 对它们发布的测量是 Reliable（可靠） |
| `Highwayaiexpose/CMP-170hx-64gb-LLM-benchmarks` | 解锁 64 GB 卡上的社区 LLM 基准合集 | 谨慎使用：平台特定、单一来源 |
| `InnovativeOSS117/Gaming-on-A100` | GA100 上图形工作 | 相邻；与显示输出和 3D 问题相关 |

### 第三方验证与测量工具

被反复使用且值得知道：`ComputationalRadiationPhysics/cuda_memtest`（v1.2.3、维护者推荐的 VRAM 验证器、在第一个错误时退出、**在 80 GB 配置档上无限挂起、除非封顶在 39 GB**）、`GpuZelenograd/memtest_vulkan`、`wilicc/gpu-burn`、`ProjectPhysX/OpenCL-Benchmark`、`ReinForce-II/mmapeak`（张量吞吐）、`zzc0721/torch-performance-test-data`（GEMM）、`sasha0552/nvidia-pstated`（空转功耗管理；见它的 issue #6）、和给没有可调整 BAR 固件支持的主机的 `xCuri0/ReBarUEFI`。

---

## 8. Issue 线程与讨论轨迹

**`github.com/dartraiden/NVIDIA-patcher` issue #73。** *信任：作为记录是 Reliable（可靠）、作为分析不可靠。* 这是整个努力开始的地方、2026 年 3 月、在 4 月搬到 Discord 之前。它还携带显存跳线解释（"each of the HBM2 stacks 上可寻址 RAM 的量由一个特定位置在 DMEM 区域里的 32 位字定义"）、跳线电阻讨论（R999/R1000 处的 Strap4、PCIE_CFG）、和首个公开 "40 GB confirmed working" 报告。注意 NVIDIA-patcher 项目**本身无法驱动 170HX**：它面向图形、它产出的是一个 GeForce-分类的 GPU 而非算力解锁。把它应用到 170HX 不影响 FP32 节流。

一条 2026 年 4 月的写稿从那线程被链接、在约 18 小时自动化分析后得出结论"FP throttle is hardware enforced and can't be overridden"（FP 节流是硬件强制的、无法覆盖）。它自己的页脚说它是在驱动 **535.288.01** 上执行的、那早于出货解锁器瞄准的 GSP 布局、它的结论被出货算力解锁反驳。它是一个精心文档化的错误答案的好例子。

**`github.com/ggml-org/llama.cpp`**：issue #24616（在 PCIe 1.1 x4 的 90HX 上达到 240 t/s pp512 的 CMP 专属补丁集）、issue #24730（无 DSA 注意力支持、那是为什么 GLM 类模型回退到稠密注意力并在此变得不可用的原因）、PR #19378（经 `--split-mode tensor` 的后端无关张量并行）、和讨论 #15013。见[LLM 推理](../operations/llm-inference.md)。

**`github.com/JustVugg/colibri`**、**`github.com/LaurieWired/tailslayer`**（刷新时序调优）、**`github.com/microsoft/Tutel`**、**`github.com/sgl-project/sglang`**、**`ikawrakow/ik_llama.cpp`**：为工作负载工作流传的相邻工具、源材料里没有一个在这张卡上被验证。

**FluidX3D issue #8（2023-10-27）。** 原始 FMA-禁用发现的功劳、比它 2023-12-06 到达 NVIDIA-patcher issue #73 早两个月。对 `src/lbm.cpp` 里 `LBM_Domain::device_defines()` 的两行补丁（索引 `d99202f..28aeb25`、约第 286 行）把 `#pragma OPENCL FP_CONTRACT OFF` 加宏遮蔽应用到每个生成的 OpenCL 程序、不碰内核源码、测到去掉 FMA 后 **7,681 MLUPs/s**、在 1175 GB/s：对 2,276 MLUPs/s 出厂值的 **3.4x** 改进。分开地、NVIDIA-patcher 线程上报的同一技术把 170HX FP32 从 **0.395 → 6.285 TFLOPS、一个 15.9 倍因子**。两者都是 2023 年锁定卡结果。（6.25 TFLOPS 是一个不同的、锁定模式自定义-GEMM 读数、在语料库里记录为一个失败-解锁特征：不要把它附到这个结果上。）

---

## 9. 被刻意排除的来源

- **各种商业和市场链接。** 采购在本维基范围之外。
- **分销商零件编号。** 电容改装零件的两个不同分销商 SKU 在流传、没有来源裁定哪个正确。本维基只引用厂商零件、Taiyo Yuden `MAASJ105SB7224KFCA01`（220 nF、6.3 V、X7R、0402）。见[物理改装](../operations/physical-mods.md)。
- **泄露材料。** 2022 年 2 月到 3 月的 NVIDIA 泄露缓存只在记录里作为来源溯源问题被引用。它的内容在此不被使用、引用或链接。见[净室与来源溯源](../history/clean-room-and-provenance.md)。
- **作为证据分享的 AI 聊天记录。** 语料库里有几十份被分享的助手对话。它们被记录为线索和文档化的幻觉、从不作为来源。
- **视频演示。** 存在几份、用几种语言。没有一份能对照寄存器或日志验证、所以没有一份被引用。

---

## 相关页面

- [保留工件](artifacts.md)
- [方法论](methodology.md)
- [净室与来源溯源](../history/clean-room-and-provenance.md)
- [工具谱系](../history/tool-lineage.md)
- [死路](../history/dead-ends.md)
