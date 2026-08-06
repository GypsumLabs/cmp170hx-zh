# 保留工件

**本页覆盖内容。** 一份 CMP 170HX 解锁努力中存活的**技术工件**目录：Falcon 固件反汇编、gadget 图谱、ROP 载荷生成器、只读探测脚本、寄存器转储、驱动补丁文件和长文写稿。对每个工件、本页记录它含什么、多大、何时出现、以及为何要紧。它是原始证据的一张地图、不是一个教程。对它们共同确立的东西、见[解锁如何工作](../unlock/how-it-works.md) 和[寄存器参考](../unlock/register-reference.md)。

两个数字框定整个集合。**131 个文本和代码文件**从两个 Discord 服务器被归档、连同**总共 1,121 个附件**（其余压倒性地是截图和照片）。分开地、**13 棵 git 树**的出货解锁器（`master` 加 12 个未发布分支）和少数外部仓库和 gist 被快照。下面一切都来自那些。

> [!NOTE]
> **命名与归属**
>
> 工件只以文件名、大小和日期被引用。本维基任何地方都不记录作者身份。几个文件被贴了不止一次、有时在不同频道、有时被轻微编辑；凡发生此情况它都会被指出、因为把一次重发当独立观察双计是一个真实错误、它在源材料里至少发生过一次。

---

## 1. Falcon 固件反汇编

SEC2 `booter_load` 微码是整个利用的对象。它是一个 AES 加密、RSA-3072-PSS 签名的重度安全（HS）Falcon 映像、约 **60,160 字节**、带 384 字节分离签名拼接在 `PATCH_LOC = 0x8900`。调试变体用 NVIDIA 的公开 AES-128-ECB 测试密钥解密、而调试和生产映像大小相同、这正是净室反汇编一开始可行的原因。见[Falcon 与 Booter](../unlock/falcon-and-booter.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `booter_load_515_dbg_disasm.asm.txt` | 389,197 B | 2026-06-30 | **515 分支** booter 的反汇编、作为产出 580 等价物的一个已工作模板发布。语料库里第一份固件清单。 |
| `booter_load_ga100_dbg_seccode.fuc5.asm` | 545,149 B | 2026-07-01 | 解密的 GA100 调试安全核心的原始 `envydis -m fuc5` 输出。这是基础工件：每个更晚工具使用的每个 gadget 地址都是这个文件里的一条指令边界。发布于 2026-07-01T12:40:37Z。 |
| `booter_load_ga100_dbg_seccode.annotated.fuc5.asm` | 591,794 B | 2026-07-03 | 同一份清单带 LLM 生成的每函数和每块注释。 |
| `booter_load_ga100_dbg_seccode.annotated.fuc5_v2.asm` | 607,702 B | 2026-07-09 | 工作参考：11,875 行、每函数横幅、每个 `lcall` 携带一条命名被调者的内联注释、形式 `lcall 0x1234 // my_function($r10, $r11)`。一份不可变备份副本于 2026-07-18 被重新发布、专门为了搜索会话不能意外编辑它。 |
| `booter_load_ga100_OVERVIEW.md` | 14,164 B | 2026-07-03 | 把原始汇编喂给一个语言模型生成的对 booter 的叙述性通读。 |

> [!WARNING]
> **概览文档按构造未被验证**
>
> 概览在它的作者"完全不知道其中哪部分是幻觉"的警示下发布。它至少在一点上自相矛盾：第 2 节正确识别 CSB `0x9100` 位 31 为 `FALCON_CSBERRSTAT.VALID`、一个故障标志、而它自己的关键常量表仍叫它一个忙/轮询位。故障读法正确、因为代码在位设置时分支到一个自循环、而非在位设置时循环。项目里的所有函数名（`csb_write`、`memcpy`、`wpr_region_program` 及其余）都**从行为推断**；二进制没有符号表。对带注释清单核对、它逐字节保留原始指令行。

代码映像在 `0x86ff` 结束。上面载荷里任何地址是 DMEM 指针、不是代码。

---

## 2. 从反汇编派生的 Gadget 目录

这些是把一份 600 kB 清单变成你能用来构建 ROP 链的工具的工件。它们远超自身大小地要紧、因为正是它们确立出货利用的常量可从净室材料派生。见[ROP 链](../unlock/rop-chain.md) 和[净室与来源溯源](../history/clean-room-and-provenance.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `register_gadget_atlas.md` | 33,060 B | 2026-07-10 | 从原始反汇编机器生成。只有跨过程可达性分析证明目标寄存器在 `ret` 时仍持有 set 值（包括在被调函数内部）才列出一个 gadget。携带每个寄存器的可控性总结（经 `mpopaddret` 可 pop、mov-setter、ld-setter、清零器）和每行注意：`canary(r15==r9)` 意思是路径跑一个栈金丝雀比较、`via-call` 意思是执行一个真实子函数、`data-branch` 意思是一个条件依赖你必须设置的状态。发布于 2026-07-10T13:40:14Z。 |
| `Bar0RegWrite.txt` | 2,769 B | 2026-07-02 | `0x10aa` BAR0 写例程的手工提取清单、逐指令、显示 `mov $r3 0x6340` / `ld b32 $r9 D[$r3]`（金丝雀加载）后跟参数移动。这是整个利用建在其上的原语。 |
| `DIRECT_ENGINE_FINDINGS.md` | 4,503 B | 2026-07-15 | 对 `0x8224` 直接写 gadget 的分析：`iowrs I[$r10] $r11` 后跟 `0x9100` CSB 状态检查和 `lcall 0x1d0f` 报告路径。 |
| `The_missing_piece_per-FBPA_hal` | 2,353 B | 2026-07-12 | 一个每-FBPA 半容量熔丝假设、命名 `FUSE_HALF_FBPA_EN 0x82049C`、`STATUS_HALF_FBPA 0x820C00`、`CTRL_OPT_FBPA 0x820818` 和 `STATUS_FBP 0x820D38`。作为一个**假设**、而非结果被保留：`STATUS_FBPA` 是否根本可写、还是纯粹是一个熔丝合并输出、被问了却从未回答。 |

图谱里 `0x0cbd`（"`$r10 <- $r0`、canary(r15==r9)、via-call、`mpopaddret $r3 0x4`"）和 `0x1fbd`（"`$r11 <- $r10`、canary(r15==r9)、via-call、`mpopaddret $r2 0x4`"）的条目、精确描述了那些 gadget 在出货驱动补丁里扮演的角色、在那个补丁存在前八天。

---

## 3. Booter 提取和固件补丁工具

| 工件 | 大小 | 日期 | 用途 |
|---|---:|---|---|
| `extract-firmware-nouveau.py` | 32,942 B | 2026-07-01 | 为 GA100 打补丁的 Nouveau 固件提取器。出厂脚本失败、因为生成的 C 数组名采取了 `kgspBinArchiveBooter{LOAD}Ucode_{GPU}_BINDATA_LABEL_IMAGE_{fuse.upper()}_data` 形式、熔丝后缀在某些架构上存在、另一些上缺失。产出 `booter_load_dbg/prod`、`booter_unload_dbg/prod` 和 bootloader blob。 |
| `extract-firmware-nouveau-ga100-raw.py` | 32,972 B | 2026-07-05 | 同一个工具、被进一步补丁为发出剥离头和签名的原始 booter、在头部留下 `0x100` 个未加密字节。 |
| `fwsec_patch.py` | 1,655 B | 2026-06-30 | 第一代 FWSEC 补丁器。 |
| `fwsec_overcopy_test.sh` | 2,543 B | 2026-06-30 | 证明驱动补丁器工作的实验：覆写一个节并观察效果。 |
| `load_custom_bin.py` | 16,937 B | 2026-07-01 | 独立 Falcon 加载器、argparse `[-h] [--pci] [--dmem-out ADDR NDWORDS] [--timeout] [--no-engine-reset] [--quiet]` 加一个位置参数二进制。 |
| `patcher.py` | 15,753 B | 2026-07-02 | GSP 固件补丁器：签名绕过加一个 "thermal trampoline"、对着驱动 580.159.03 写。 |
| `patch_gsp.py` | 2,563 B | 2026-07-11 | 对 `gsp_tu10x.bin` 的 ELF64 手术：解析 `e_shoff 0x28`、`e_shentsize 0x3A`、`e_shnum 0x3C`、`e_shstrndx 0x3E`、定位 `.fwsignature_ga100`、就地覆写、把 `sh_size` 补丁到 `0xF800`、把 `.shstrtab` 追加到文件末尾、重写 `e_shoff`。 |
| `scan_dmem.py` | 10,160 B | 2026-07-16 | 更安全的 ELF 变体、用 pyelftools 并把替换节在 EOF 追加、遵守 `sh_addralign`。也驱动一次完整 DMEM 扫描：以 4 步迭代 `DMEM_ADDR`、为每个值构建一个转储载荷、补丁固件、重载模块、可选 FLR。 |

一条值得保留的独立更正：**`gsp_tu10x.bin` 从不是反汇编目标。** 它是 booter 验证的 GSP RISC-V ELF 载荷、不是 booter。Ghidra 从它发出约 100 MB 的 C、`riscv64-unknown-elf-objdump` 约 1.5 GB 的汇编。真实目标约 25 kB、反汇编到约 390 kB。该文件仍是正确的*投递载体*、那正是混淆持续的原因。

---

## 4. ROP 载荷生成器和载荷清单

载荷清单是 DMEM 地址到值的纯文本表、手写并由肉眼审查。它们是集合里最易读的工件、也是理解链的最好入口点。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `170HX_ROP_payload_v1.txt` | 2,530 B | 2026-07-05 | 第一条链。金丝雀全局 `6340 = FACEB13D`；目标 `$r0` 的 `FF3C` 处写值 `02779000`；`FF40`/`FF44` 处金丝雀地址。显式作为未测试发布。 |
| `170HX_ROP_payload_v2.txt` | 2,648 B / 2,918 B | 2026-07-08 | 同一天两个修订。第二个修复一个 bug 并把 `main()` 的返回地址移到 `0x8119`。 |
| `170HX_ROP_payload_v3.txt` | 3,034 B | 2026-07-09 | 四次 BAR0 写、经 `booter_load_wpr_main()` 重接求可能的 WPR2 释放。头部注明 `FEAT_OVR_SM_SPD` 和 `FEAT_OVR_SM_SPD_1` 在 PLM 解锁后仍必须从主机设置。 |
| `stack_gen.py` | 4,482 B | 2026-07-04 | 帧生成器：一个初始 `mpopaddret $r6 0x4` 块然后每帧三个 5 词 `mpopaddret $r2 0x4` 块、返回地址 `0x1fb9`、`0x1fbd`、`0x8224`、退出 `0x79e7`、`payload_size 0xF700`、`dma_target 0x0900`、`stack_start 0xf75c`。 |
| `builder.py` | 9,810 B | 2026-07-01 | 载荷构建器、模式 A（节流写、停机退出）。它的头部精确命名漏洞：IMEM `0x29C4` 处的 `booterVerifyLsSignatures_TU10X` 以 `$r10 = 0x0900` 和 `size = sizeOfSignature`、无边界检查地调用 `lcall 0x0601`（`booterIssueDma_HAL`）。 |
| `payloadn.py`、`payload-lnject.py`、`payload_v3.py` | 2,285 / 4,592 / 2,200 B | 2026-07-08 到 07-09 | 连续几代 Python 载荷注入器。 |
| `unlc.py` | 1,919 B | 2026-07-12 | 最小主机侧演示器：一旦 FEAT PLM 打开、SS0 和 SS1 是普通 BAR0 写。这个两步模型恰是出货补丁实现的。 |

> [!CAUTION]
> **`stack_gen.py` v1 不可能工作**
>
> 它的首个发布清零每个金丝雀槽。`D[0x6340]` 处的参考字必须被复制进每个帧、否则 `0x7dd9` 处的 `__stack_chk_fail` 触发。作者发布时标记它、更晚的载荷把标记写进每个帧。保留因为它有教益、不是因为它可用。

### 免驱动 refire 链

`refire_chain_v6.py`（**27,769 B**、2026-07-24）从用户空间、**不加载 NVIDIA 驱动**、只用 Python 标准库执行整个解锁。它把 BAR0 映射为 16 MiB、把 SEC2 当作基址 `0x00840000`、复位 Falcon、把 NS 代码非安全地加载到 IMEM 0、把 HS 代码安全地加载到 `IMEM[ns]`、加载 DMEM、把 MAILBOX0/1 设为 WprMeta 物理地址、启动 CPU、并反复溢出签名 Booter 的签名读 DMA。模式：`--compute`、`--memory 40`、`--memory 80`、`--pcie-gen2`、`--pcie-retrain`、`--all`。

> [!WARNING]
> **实验性**
>
> 这是一条平行、非出货路径。它不是 `cmpunlocker` 的一部分。它的前置条件严格：root、GPU 从任何 nvidia 驱动解绑、一个签名 GA100 `booter_load` HS 映像、`echo 16 | sudo tee /proc/sys/vm/nr_hugepages`、和 `intel_iommu=off` 或 `iommu=pt`、好让 DMA 物理地址是宿主物理的。它只带一个 **10 GB WprMeta 模板**、所以不能未修改地应用到一张 `0x20C2` 卡。它的 `--memory 80` 模式声称 "80 GB LMR HW-verified"、那最可能意味着寄存器接受了写、而非 80 GB 可用。见[80 GB 问题](../frontier/80gb.md)。

---

## 5. 只读探测和表征仪器

这些从没被废弃。它们是测量仪器、不是解锁器、而且它们仍是验证本页任何声称的正确方式。

| 工件 | 大小 | 日期 | 它做什么 |
|---|---:|---|---|
| `probe.sh`（mmio-probe） | 19,061 B | 首见 2026-05-31、归档副本 2026-07-07 | 自包含 bash 加内联 Python。只读 mmap `/sys/bus/pci/devices/<BDF>/resource0` 并转储约 120 到 130 个具名寄存器加 24 个每-FBPA 读、在 `FBPA_BASE 0x900000`、`FBPA_STRIDE 0x4000`。发出 `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv`、`probe.log`、打包到 `/tmp/mmio-probe-<host>-<stamp>.tar.gz`。可选编译一个 CUDA PTX 特殊寄存器转储器（`nvcc -arch=sm_70`）、所以 SM 数被**测量**而非被报告。**它从不写 BAR0。** |
| `ga100_topology_report.py` | 4,848 B 然后 8,128 B | 2026-07-24 | 只读 BAR0 mmap、只转储决定一颗 GA100 板枚举多少 SM 的寄存器、用于跨单元比较。第二个修订加一个 InfoROM 抓取。 |
| `pcielink.sh` | 4,944 B | 2026-07-24 | 标准 PCIe 现场报告收集器。在端点和父桥两者上解码 `CAP_EXP+0c.l`（LnkCap）、`+2c.l`（LnkCap2）、`+10.w`（LnkCtl）、`+12.w`（LnkSta）、`+24.l`（DevCap2）、`+28.w`（DevCtl2）、`+30.w`（LnkCtl2）、`+32.w`（LnkSta2）、加 sysfs 速度和位宽、`nvidia-smi pcie.link.gen`、AER 计数器和 `SEC2_DEBUG` dmesg 行数。 |
| A100 探测套件：`probe.py` + `README.md` + `sweep.sh` | 9,132 / 3,022 / 3,007 B | 2026-07-20 | 在一颗**捐赠 A100** 上的三步可选写工作流：只读库存、然后 `sweep.sh` 经一个 EXIT 陷阱强制 Gen1/2/3 并自动恢复、然后 `probe.py write-test --confirm` 写并立即恢复 `0x880a8`、`0x8c044` 和 `0x88088`、把每个分类为 `WROTE-OK` 或 `REJECTED(PLM?)`。掩码读哨兵 `0xBADF5040`。同日一个更早的 11,472 B `probe.py` 先于它。 |
| `check_fold.py` | 未作为文件归档 | 2026-07-24 | 解锁 VRAM 是否真实的权威测试：分配全部空闲 VRAM 减 2 GiB、用 PTX `sm_80` 内核写每个 64 KB 页自己的索引、读每个页回来。必须稠密、因为折叠在一个通道交错偏移量处别名。输出 `REAL, NO FOLD` 或 `FOLD/mismatch @<pageindex>`。 |
| `cuda_dbg.py` | 未作为文件归档 | 2026-07-19 | 更轻的别名测试：`cuMemGetInfo_v2`、然后 `cuMemAlloc_v2` 在 64、60、56、52、48、44、42 GiB 直到一个成功；在偏移量 0 写 `0xAAAA0000`、在 40 GiB 写 `0xBBBB0000`、读偏移量 0。读回 `0xBBBB0000` 意味着空间别名。 |

> [!NOTE]
> **`probe.sh` 的两个文档化缺陷**
>
> 它头部第 9 行承诺一个不存在的 `/dev/mem` 回退；解析块以 `ERROR: cannot find resource0` 和 `exit 2` 结束。而该目录先于解锁、所以它不含 `0x001fa7c4`、`0x001fa7cc`、`0x001fa824`/`0x001fa828`、`0x009a0148` 或 `0x00100ce0` 的条目：出货解锁实际操纵的五个寄存器。加它们是任何人能做的唯一最有价值改动、且不需要硬件。

读 BAR0 需要 root **加** `CAP_SYS_RAWIO`、容器化 GPU 宿主会丢弃它；探测随后以 `cannot open .../resource0 (EPERM) even as root` 抛出。

---

## 6. 寄存器转储和捕获日志

原始捕获是寄存器参考大部分承重证据。见[寄存器索引](register-index.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `regs_01.txt` | 16,103 B | 2026-07-12 | 一张出厂卡上的定向、带注释寄存器读：`SM_ISSUE_RATE_MODIFIER 0x00504204 = 0xbadf1201`、`FECS_FEAT_OVERRIDE 0x00409664 = 0xbadf5040`、`FEAT_OVR_ECC_PLM 0x00823800 = 0xffffff8f`、`FEAT_OVR_PLM 0x00823804 = 0xffffff8f`、`FEAT_OVR_QUADRO 0x00823808 = 0x00000081`（来源把 `0x00000081` 归因于一次*解锁后*探测而非一张出厂卡、所以不要把这个读成任一个）、`FEAT_OVR_ECC 0x0082380c = 0x00888888`、和更多、每个带一行用途注。 |
| PLM 范围扫描（`save.sh`） | 13,544 B 原始 / 12,265 B 清理 | 2026-07-16 / 07-18 | 一个覆盖 `0x823800` 到 `0x823FFC` 的 `script(1)` 打字稿、**510 个地址/值对**、28 秒墙钟时间（`Script started 22:51:04+07:00`、`Script done 22:51:32+07:00`）、完整带操作者先笨拙敲命令。`0x823800` 到 `0x82382C` 块里**十一**个寄存器是活的、加 `0x823B00`、总共**十二**个活 dword。两个地址、`0x823828` 和 `0x823850`、完全不在转储里、那正是扫描携带 510 对而非完整步进-4 扫描该窗口会产生的 512 个的原因。其它一切读 `0xBADF5040`。**两天后贴到不同频道的清理副本在全部 510 对上逐字节等价。它是一次观察、不是两次。** |
| `a100.json` | 84,011 B | 2026-07-20 | 一颗真 A100 的完整库存、170HX 熔丝读数被对照解读的差分参考。 |
| `a100_native_unbound.json`、`gen_native.json`、`gen1.json`、`gen2.json`、`gen3.json` | 33,259 / 33,259 / 33,273 / 33,271 / 33,271 B | 2026-07-20 | 来自捐赠 A100 的强制代扫描集。那颗卡上的写测试没成功、所以只存在读数据。 |
| `a100-80g.json` | 1,367 B | 2026-07-20 | 一颗租用 A100 80 GB 的短转储。 |
| `registers.json` | 23,254 B | 2026-07-25 | 一颗 **CMP 90HX** 的探测转储、用于跨家族比较。 |
| `ga100_topology_output.txt` | 3,345 B | 2026-07-24 | 一张活卡上的拓扑报告输出。 |
| `reg-ref-a100-vs-170hx.csv` | 1,857 B | 2026-07-27 | 两天活 A100 对比原生 8 GB 170HX 的跳线和熔丝比较、猎寻一个 PCIe Gen3 跳线。**负结果就是发现**；该方法被宣布为一条死路、而 170HX 侧缺完整每-FBPA 捕获。 |
| `00_33_31_scanning_lspci.txt` | 16,427 B | 2026-06-25 | 早期完整 `lspci` 扫描。 |
| `dmesg_large.txt` | 7,405 B | 2026-07-09 | 测试签名后是否有任何要紧东西坐在 DMEM 里的实验的内核日志。 |
| `bendy2pcielink.txt` | 2,579 B | 2026-07-24 | 一份归档 `pcielink.sh` 现场报告。 |

---

## 7. 驱动补丁文件和安装器时代 shell 脚本

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `patch.diff` | 35,867 B | 2026-07-18 | 887 行、跨 11 个文件：通过把它捆绑的 open-modules 树对上游标签 `610.43.03` diff、从泄露包提取的 diff。发布于 18:01:15Z。历史上决定性：见[净室与来源溯源](../history/clean-room-and-provenance.md)。 |
| `cmpunlocker` 出货补丁集 | 37,415 B | 2026-07-18 | 六个补丁、890 行、10 个目标文件：`0001-sec2-postbl-plm-ss-cfg.patch`（19,741 B）、`0002-booter-verify.patch`（3,988 B）、`0003-late-pma.patch`（10,580 B）、`0004-bar0-pramin-clamp.patch`（861 B）、`0005-ce-scrub-workarounds.patch`（1,642 B）、`0006-persistent-sw-state.patch`（603 B）。 |
| `0007-pcie-gen2.patch`、`0008-pcie-gen2-probe-retrain.patch` | **2026-07-29 合并进 `master`**（提交 `2e0a2c02`） | 2026-07-23 起 | Gen2 工作、在分支上开发一周然后合并。`0007` 经 Booter 载荷原语推入一张 23 条目 `xp3gTable`；`0008` 把 `nv_cmp170hx_retrain_gen2()` 加到 `kernel-open/nvidia/nv.c`。见[PCIe Gen2](../unlock/pcie-gen2.md)。 |
| `mod.txt` | 1,725 B | 2026-07-12 | 一个手写内核 hunk、定义 `CMP170HX_WPR2_SAFE_LIMIT 0x0A00000000ULL`（40 GB）并带警告把它之上的 `pWprMeta->fbSize` 钳住。对 WPR2 定大小问题的一个早期、独立表达。 |
| `Guide_SM.sh` | 9,127 B | 2026-07-12 | 全流水线驱动：阶段 1、FLR、卸载、解锁。 |
| `nuke.sh` | 7,359 B | 2026-07-16 | PLM 批量测试 v3：补丁 GSP、ROP、FLR、杀、FLR、无驱动加载地读 PLM。在 9 个周期 x 3、每周期两个 FLR 里跑一个 27 地址持久性扫描。用 `CANARY_ADDR 0x6340` 处的金丝雀 `0xFACEB13D`、`DMA_TARGET 0x0800`。 |
| `test_580.sh`（三个修订）、`test_580v6.sh`、`scaffold_580.sh`、`driver.sh`、`a.sh`、`b.sh` | 3.8 到 7.7 kB | 2026-07-08 到 07-12 | 580 分支实验 harness、包括一个 STRAP 写修复和一个 `0x65` 状态猎寻。 |
| `cmp170hx-gen2-setup.sh` | 12,389 B | 2026-07-26 | 独立 Gen2 使能器、不同于驱动内分支方法。它自己的头部精确陈述范围：Gen1 约 0.85 GB/s 到 Gen2 约 1.71 GB/s、恰好 2x、64 GB 解锁、算力和 HBM 带宽不动、无 VBIOS 刷写、无内核命令行改动。 |
| `build-llama-170hx.sh` | 3,802 B | 2026-07-27 | 这张卡的可复现 llama.cpp 容器构建。 |

> [!CAUTION]
> **`gpuValidateRegOps` 绕过只在 `patch.diff` 里**
>
> `patch.diff` 把 `return NV_OK;` 作为 `gpuValidateRegOps` 的第一条语句插入、无条件、对所有 GPU、完全禁用寄存器读/写验证。那个改动**不在**出货 `cmpunlocker` 树里、也不在全部十二个未发布分支里。任何把它归因于出货工具的文字都是错的。

---

## 8. 长文写稿和实地手册

| 工件 | 大小 | 日期 | 它论证什么 |
|---|---:|---|---|
| `ROP_CHAINS_1180f8_nibble_writeup_20260715.md` | 9,628 B | 2026-07-15 | 交接状态问题、作为一个需求表陈述：一次免驱动 fire 后、`resetPLM 0x8403C4` 必须读 `0xff`（因为 `0x8f` 阻塞 SEC2 SFTRESET）、WPR2 `0x1FA824/28` 必须被清除、而 `1180f8` 位 [31:28] 必须是 `0x1`。前两个被解决；半字节没有。也文档化 `+0x18 DMEM per write` 帧步长并把 `D[0xFF50]` 到 `D[0xFF84]` 制成表。发布于 2026-07-15T18:48:10Z。 |
| `WRITEUP.md` + `WRITEUP_EXPLAINED.md` | 12,950 + 12,335 B | 2026-07-23 | 一张 `0x2082` 卡上的 FFMA 节流调查：0.315 TFLOPS 实测对 25.27 TFLOPS 理论、**GSP 固件十四个二进制补丁加多个内核模块修改、没有一个移动节流**。它的结论、限制是熔丝强制的且从固件不可达、是一个有价值的负结果、只被完全不同的 SEC2 路线反驳。 |
| `CMP_170HX_40GB_UNLOCK_GUIDE.md` | 11,994 B | 2026-07-22 | 单加载 40 GB 驱动补丁端到端解释：一次 `modprobe`、无 FLR、无固件交换、`modprobe` 时序序列被逐步写出。 |
| `PCIE_GEN1_LOCK.md` | 15,467 B | 2026-07-24 | PCIe 速度上限实地手册。以把**速度**与**位宽**分开并显式把位宽（C1100 到 C1350 的 24 颗电容焊接改装）排除在外开场。状态行："Software and keyless-firmware surface exhausted; remaining paths are physical."（软件和无钥固件表面已穷尽；剩余路径是物理的。） |
| `ga100_fbpa_hbm_timing_registers.md` | 23,682 B | 2026-07-25 | 广播 FBPA 范围 `0x009A0000` 到 `0x009A3FFF` 内 `0x9A0200` 到 `0x9A0300` 的 HBM 时序寄存器定义、带关键观察 `CONFIG0.USE_TIMING_REGS`（`0x9A0290` 的位 31）读 **0**、所以活参数是内部生成的 `TIMING*_GEN` 影子、不是原始 `TIMING*`/`CONFIG*` 值。 |
| `untitled.md` | 5,814 B | 2026-07-17 | 个人架构笔记、带作者自己的自评：大约**百分之十**有可靠证明或来源、加一个警告说把聊天里所有点汇总成文档会产生许多错误结论。 |
| `README.txt` | 4,637 B | 2026-07-18 | 泄露包的配套笔记。 |

---

## 9. 基准、调优和工作负载工件

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `170hx-tuning-guide.md` | 26,987 B | 2026-07-27 | 随 `170tune` harness 出货。对着一个具名参考卡（GA100、70 SM、64 GB 解锁、驱动 610.43.03、300 W VBIOS `92.00.6D.00.0A`、PCIe Gen2 x4）写、并显式说明每卡硅片各异、带任何偏移被信任于不同单元前的一个 "qualifying a new card" 流程。也是一份已关闭死路的记录、这样没一条被走两次。 |
| `170HX-benchmark-results.md` | 5,290 B | 2026-07-27 | 八张解锁 64 GB 卡、驱动 610.43.02、`sm_80`、PCIe **Gen1 x4**、无电容改装。每卡 torch GEMM：FP16 张量 162.7 TFLOPS、BF16 张量 171.4 TFLOPS。 |
| `GLM-5.2-benchmark-report.md` | 7,999 B | 2026-07-24 | 一份值得保留的负结果报告：467 GB 4 位量化无法加载、因为宿主的 88 GB 系统 RAM 远低于 llama.cpp 加载时计算图 pass 所需的、把 RSS 钉在约 87.6 GB 而无进展。一次宿主侧失败、不是卡限制。 |
| `cublas_benchmark1` | 826,072 B | 2026-07-16 | 一个 x86-64 ELF 可执行文件、动态链接到 `ld-linux-x86-64.so.2`。一个**分发给他人运行的编译二进制**、不是一个结果日志。 |

这些数字在上下文里意味着什么见[性能](../operations/performance.md) 和[LLM 推理](../operations/llm-inference.md)。

---

## 10. 什么没被保留

对缺口保持明确是目录的一部分。

- **没有 booter 二进制。** 签名的 HS 映像和它的分离签名被工具命名（`booter_load_580_image.bin`、`booter_load_580_sig.bin`、预期在 `cmp170hx_boot_bins/verified_hs/` 下）却不在档案里。
- **没有 8 GB WprMeta 捕获。** 免驱动链的 256 字节模板来自一次真实 10 GB 引导。捕获 8 GB 等价物是一个小、无阻塞的任务。
- **没有调试和生产 booter 映像的哈希比较。** bindata 档案让它琐碎、而且它会确立它们是逐字节相同还是仅相同大小。
- **没有仿真器。** 学术论文描述的 Falcon 仿真器从未被发布。
- **没有驱动修改指南。** 会解决几个来源溯源问题的两份私人文档不存在于这个源集里。
- **`master` 上没有 `verify.sh`**、它的任何分支副本里也没有 Gen2 检查。
- **`master` 没有 `tools/` 目录。** `probe.sh`、`pcielink.sh`、`check_fold.py`、`cuda_dbg.py`、A100 探测套件和 refire 链都被带外分发。克隆仓库不会给你任何一。

---

## 相关页面

- [解锁如何工作](../unlock/how-it-works.md)
- [Falcon 与 Booter](../unlock/falcon-and-booter.md)
- [ROP 链](../unlock/rop-chain.md)
- [驱动补丁](../unlock/driver-patches.md)
- [寄存器参考](../unlock/register-reference.md) 和[寄存器索引](register-index.md)
- [工具谱系](../history/tool-lineage.md)
- [外部来源](external-sources.md)
- [方法论](methodology.md)
