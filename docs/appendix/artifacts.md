# 保留工件

**本页涵盖内容。** 本页目录列出 CMP 170HX 解锁工作中留存下来的技术工件：Falcon 固件反汇编、gadget 图谱、ROP 载荷生成器、只读探测脚本、寄存器转储、驱动补丁文件以及长篇说明文档。对于每件工件，本页记录其内容、大小、出现时间以及重要性。这是一张一手证据地图，不是教程。至于这些工件共同确立了什么，请参见[解锁如何工作](../unlock/how-it-works.md)和[寄存器参考](../unlock/register-reference.md)。

两个数字可以概括这个集合。两个 Discord 服务器中归档了**131 个文本和代码文件**，另有**总计 1,121 个附件**（其余绝大部分是截图和照片）。此外，还对发布版解锁器的**13 棵 git 树**（`master` 加 12 个未发布分支）以及少数外部仓库和 gist 做了快照。以下内容全部来自这些资料。

> [!NOTE]
> **命名与归属**
>
> 工件仅按文件名、大小和日期引用。本维基任何地方都不记录作者身份。有些文件发布过不止一次，有时出现在不同频道，有时只做过轻微编辑；发生这种情况时，文中会特别指出，因为把重复发布误算为独立观察是一个真实发生过的错误，源材料中至少出现过一次。

---

## 1. Falcon 固件反汇编

SEC2 的 `booter_load` 微码是整个利用的目标。它是一份经过 AES 加密、RSA-3072-PSS 签名的 Heavy Secure（HS）Falcon 映像，大小约为 **60,160 字节**，并在 `PATCH_LOC = 0x8900` 处插入了 384 字节的分离签名。调试变体使用 NVIDIA 的公开 AES-128-ECB 测试密钥解密；调试映像与生产映像大小相同，正是这一点使净室逆向反汇编成为可能。参见[Falcon 与 Booter](../unlock/falcon-and-booter.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `booter_load_515_dbg_disasm.asm.txt` | 389,197 B | 2026-06-30 | **515 分支** Booter 的反汇编，作为制作 580 等价版本的可运行模板发布。这是资料库中的第一份固件清单。 |
| `booter_load_ga100_dbg_seccode.fuc5.asm` | 545,149 B | 2026-07-01 | 解密后的 GA100 调试安全核心的原始 `envydis -m fuc5` 输出。这是基础工件：后续工具使用的每个 gadget 地址，都是该文件中的一条指令边界。发布于 2026-07-01T12:40:37Z。 |
| `booter_load_ga100_dbg_seccode.annotated.fuc5.asm` | 591,794 B | 2026-07-03 | 同一份清单，增加了由 LLM 生成的逐函数和逐代码块注释。 |
| `booter_load_ga100_dbg_seccode.annotated.fuc5_v2.asm` | 607,702 B | 2026-07-09 | 工作参考版本：11,875 行，带逐函数横幅；每个 `lcall` 都带有以内联注释命名被调用函数，格式为 `lcall 0x1234 // my_function($r10, $r11)`。2026-07-18 重新发布了一份不可变备份，专门用于防止搜索会话意外编辑它。 |
| `booter_load_ga100_OVERVIEW.md` | 14,164 B | 2026-07-03 | 将原始汇编输入语言模型后生成的 Booter 叙述式通读文档。 |

> [!WARNING]
> **概览文档从其生成方式上就未经验证**
>
> 概览发布时附带作者的免责声明：作者“完全不知道其中哪部分是幻觉”。它至少有一处自相矛盾：第 2 节正确地将 CSB `0x9100` 的位 31 识别为 `FALCON_CSBERRSTAT.VALID`，即故障标志；但它自己的关键常量表仍将该位称为忙/轮询位。故障标志这一解释是正确的，因为代码在该位被置位时跳转到自循环，而不是在该位保持置位期间持续循环。项目中的所有函数名（`csb_write`、`memcpy`、`wpr_region_program` 等）都是**根据行为推断出来的**；二进制没有符号表。请以带注释的清单为准，它逐字节保留了原始指令行。

代码映像结束于 `0x86ff`。载荷中任何高于该地址的地址都是 DMEM 指针，而不是代码地址。

---

## 2. 从反汇编派生的 Gadget 目录

这些工件把一份 600 kB 的清单转化成了可以用来构建 ROP 链的资料。它们的重要性远超自身大小，因为正是它们证明了发布版利用中的常量可以从净室资料推导出来。参见[ROP 链](../unlock/rop-chain.md)和[净室与来源溯源](../history/clean-room-and-provenance.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `register_gadget_atlas.md` | 33,060 B | 2026-07-10 | 根据原始反汇编自动生成。只有当跨过程可达性分析证明目标寄存器在 `ret` 时仍保持已设置的值（包括在被调用函数内部）时，才会列出该 gadget。它还给出每个寄存器的可控性总结（可通过 `mpopaddret` 弹出、mov-setter、ld-setter、清零器）以及每行的注意事项：`canary(r15==r9)` 表示该路径会执行栈金丝雀比较，`via-call` 表示会执行真实的子函数，`data-branch` 表示条件分支依赖于你必须设置的状态。发布于 2026-07-10T13:40:14Z。 |
| `Bar0RegWrite.txt` | 2,769 B | 2026-07-02 | 手工提取的 `0x10aa` BAR0 写例程清单，逐条列出指令，展示 `mov $r3 0x6340` / `ld b32 $r9 D[$r3]`（加载金丝雀）以及随后的参数移动。这是整个利用所建立的基础原语。 |
| `DIRECT_ENGINE_FINDINGS.md` | 4,503 B | 2026-07-15 | 对 `0x8224` 直接写 gadget 的分析：先执行 `iowrs I[$r10] $r11`，随后进行 `0x9100` CSB 状态检查并进入 `lcall 0x1d0f` 报告路径。 |
| `The_missing_piece_per-FBPA_hal` | 2,353 B | 2026-07-12 | 一个关于每个 FBPA 半容量熔丝的假设，其中命名了 `FUSE_HALF_FBPA_EN 0x82049C`、`STATUS_HALF_FBPA 0x820C00`、`CTRL_OPT_FBPA 0x820818` 和 `STATUS_FBP 0x820D38`。它以**假设**而非结果的形式保留：`STATUS_FBPA` 到底可写，还是纯粹的熔丝合并输出，曾有人提出这个问题，但从未得到回答。 |

图谱中关于 `0x0cbd`（“`$r10 <- $r0`、canary(r15==r9)、via-call、`mpopaddret $r3 0x4`”）和 `0x1fbd`（“`$r11 <- $r10`、canary(r15==r9)、via-call、`mpopaddret $r2 0x4`”）的条目，准确描述了这些 gadget 在发布版驱动补丁中承担的角色，而这发生在该补丁出现前八天。

---

## 3. Booter 提取和固件补丁工具

| 工件 | 大小 | 日期 | 用途 |
|---|---:|---|---|
| `extract-firmware-nouveau.py` | 32,942 B | 2026-07-01 | 为 GA100 打过补丁的 Nouveau 固件提取器。原版脚本会失败，因为生成的 C 数组名采用 `kgspBinArchiveBooter{LOAD}Ucode_{GPU}_BINDATA_LABEL_IMAGE_{fuse.upper()}_data` 形式，而熔丝后缀在某些架构上存在、在另一些架构上不存在。它会生成 `booter_load_dbg/prod`、`booter_unload_dbg/prod` 和 bootloader blob。 |
| `extract-firmware-nouveau-ga100-raw.py` | 32,972 B | 2026-07-05 | 同一工具的进一步修改版：输出去除头部和签名的原始 Booter，并在开头保留 `0x100` 个未加密字节。 |
| `fwsec_patch.py` | 1,655 B | 2026-06-30 | 第一代 FWSEC 补丁器。 |
| `fwsec_overcopy_test.sh` | 2,543 B | 2026-06-30 | 证明驱动补丁器有效的实验：覆盖一个节并观察效果。 |
| `load_custom_bin.py` | 16,937 B | 2026-07-01 | 独立 Falcon 加载器，包含 argparse `[-h] [--pci] [--dmem-out ADDR NDWORDS] [--timeout] [--no-engine-reset] [--quiet]`，另加一个位置参数形式的二进制文件。 |
| `patcher.py` | 15,753 B | 2026-07-02 | GSP 固件补丁器：签名绕过加上一个“thermal trampoline”，针对驱动 580.159.03 编写。 |
| `patch_gsp.py` | 2,563 B | 2026-07-11 | 对 `gsp_tu10x.bin` 执行 ELF64 手术：解析 `e_shoff 0x28`、`e_shentsize 0x3A`、`e_shnum 0x3C`、`e_shstrndx 0x3E`，定位 `.fwsignature_ga100`，就地覆盖，将 `sh_size` 补丁为 `0xF800`，把 `.shstrtab` 追加到文件末尾，并重写 `e_shoff`。 |
| `scan_dmem.py` | 10,160 B | 2026-07-16 | 更安全的 ELF 变体，使用 pyelftools，并遵守 `sh_addralign` 将替换节追加到文件末尾。它还驱动一次完整的 DMEM 扫描：以 4 为步长遍历 `DMEM_ADDR`，为每个值构建一个转储载荷，补丁固件，重新加载模块，并可选择执行 FLR。 |

还有一条值得保留的独立更正：**`gsp_tu10x.bin` 从来不是反汇目标。** 它是 Booter 验证的 GSP RISC-V ELF 载荷，而不是 Booter。Ghidra 从中生成了约 100 MB 的 C 代码，`riscv64-unknown-elf-objdump` 生成了约 1.5 GB 的汇编。真正的目标大小约为 25 kB，反汇编后约为 390 kB。这个文件仍然是正确的*投递载体*，这正是混淆一直存在的原因。

---

## 4. ROP 载荷生成器和载荷清单

载荷清单是从 DMEM 地址到值的纯文本表格，由人工编写并人工检查。它们是这个集合中最易读的工件，也是理解这条链的最佳入口。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `170HX_ROP_payload_v1.txt` | 2,530 B | 2026-07-05 | 第一条链。金丝雀全局值为 `6340 = FACEB13D`；写入值 `02779000` 位于 `FF3C`，目标是 `$r0`；金丝雀地址位于 `FF40`/`FF44`。发布时明确标注为未经测试。 |
| `170HX_ROP_payload_v2.txt` | 2,648 B / 2,918 B | 2026-07-08 | 同一天发布的两个修订版本。第二个版本修复了一个 bug，并将 `main()` 的返回地址移到 `0x8119`。 |
| `170HX_ROP_payload_v3.txt` | 3,034 B | 2026-07-09 | 执行四次 BAR0 写入，并通过 `booter_load_wpr_main()` 重新接回，尝试释放 WPR2。文件头注明，PLM 解锁后仍必须由主机设置 `FEAT_OVR_SM_SPD` 和 `FEAT_OVR_SM_SPD_1`。 |
| `stack_gen.py` | 4,482 B | 2026-07-04 | 帧生成器：先放置一个 `mpopaddret $r6 0x4` 块，然后每帧放置三个 5 词的 `mpopaddret $r2 0x4` 块；返回地址为 `0x1fb9`、`0x1fbd`、`0x8224`，退出地址为 `0x79e7`，`payload_size` 为 `0xF700`，`dma_target` 为 `0x0900`，`stack_start` 为 `0xf75c`。 |
| `builder.py` | 9,810 B | 2026-07-01 | 载荷构建器，模式 A（节流写入、停机退出）。其文件头准确指出了漏洞：IMEM `0x29C4` 处的 `booterVerifyLsSignatures_TU10X` 在没有边界检查的情况下，以 `$r10 = 0x0900` 和 `size = sizeOfSignature` 调用 `lcall 0x0601`（`booterIssueDma_HAL`）。 |
| `payloadn.py`、`payload-lnject.py`、`payload_v3.py` | 2,285 / 4,592 / 2,200 B | 2026-07-08 到 07-09 | 连续几代 Python 载荷注入器。 |
| `unlc.py` | 1,919 B | 2026-07-12 | 最小的主机侧演示器：FEAT PLM 打开后，SS0 和 SS1 就是普通的 BAR0 写入。这个两步模型正是发布版补丁实现的模型。 |

> [!CAUTION]
> **`stack_gen.py` v1 不可能正常工作**
>
> 它的首个版本将每个金丝雀槽都清零。必须将 `D[0x6340]` 中的参考字复制到每一帧，否则 `0x7dd9` 处的 `__stack_chk_fail` 就会触发。作者在发布时标记了这一问题，后续载荷会将标记写入每一帧。保留它是因为这种失败模式具有启发性，而不是因为该文件可用。

### 免驱动 refire 链

`refire_chain_v6.py`（**27,769 B**，2026-07-24）只使用 Python 标准库，从用户空间执行完整的解锁过程，**不加载 NVIDIA 驱动**。它将 BAR0 映射为 16 MiB，将 SEC2 视为基址 `0x00840000`，复位 Falcon，将 NS 代码以非安全方式加载到 IMEM 0，将 HS 代码以安全方式加载到 `IMEM[ns]`，加载 DMEM，将 MAILBOX0/1 设置为 WprMeta 物理地址，启动 CPU，然后反复溢出已签名 Booter 的签名读取 DMA。模式包括：`--compute`、`--memory 40`、`--memory 80`、`--pcie-gen2`、`--pcie-retrain`、`--all`。

> [!WARNING]
> **实验性**
>
> 这是一条并行的、未进入发布版的路径，不属于 `cmpunlocker`。它的前置条件很严格：需要 root 权限、将 GPU 从任何 nvidia 驱动解绑、一份已签名的 GA100 `booter_load` HS 映像、执行 `echo 16 | sudo tee /proc/sys/vm/nr_hugepages`，以及设置 `intel_iommu=off` 或 `iommu=pt`，以确保 DMA 物理地址就是宿主机物理地址。它只提供一个**10 GB WprMeta 模板**，因此不能未经修改就应用到 `0x20C2` 卡上。它的 `--memory 80` 模式声称“80 GB LMR HW-verified”，最合理的解释是寄存器接受了写入，而不是 80 GB 可用。参见[80 GB 问题](../frontier/80gb.md)。

---

## 5. 只读探测和表征工具

这些工具从未过时。它们是测量仪器，不是解锁器，至今仍是验证本页任何说法的正确方式。

| 工件 | 大小 | 日期 | 用途 |
|---|---:|---|---|
| `probe.sh`（mmio-probe） | 19,061 B | 首见 2026-05-31，归档副本 2026-07-07 | 自包含的 bash 加内联 Python。以只读方式 mmap `/sys/bus/pci/devices/<BDF>/resource0`，转储约 120 至 130 个具名寄存器，以及位于 `FBPA_BASE 0x900000`、步长为 `FBPA_STRIDE 0x4000` 的 24 个每-FBPA 读数。输出 `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv` 和 `probe.log`，并打包为 `/tmp/mmio-probe-<host>-<stamp>.tar.gz`。它还可以选择编译 CUDA PTX 特殊寄存器转储器（`nvcc -arch=sm_70`），因此 SM 数量是**测量**出来的，而不是直接报告的。**它从不写入 BAR0。** |
| `ga100_topology_report.py` | 4,848 B，之后为 8,128 B | 2026-07-24 | 以只读方式 mmap BAR0，只转储决定 GA100 板卡枚举出多少个 SM 的寄存器，用于跨卡比较。第二个修订版增加了 InfoROM 抓取。 |
| `pcielink.sh` | 4,944 B | 2026-07-24 | 标准 PCIe 现场报告收集器。在端点和父桥上分别解码 `CAP_EXP+0c.l`（LnkCap）、`+2c.l`（LnkCap2）、`+10.w`（LnkCtl）、`+12.w`（LnkSta）、`+24.l`（DevCap2）、`+28.w`（DevCtl2）、`+30.w`（LnkCtl2）、`+32.w`（LnkSta2），此外还收集 sysfs 速度和位宽、`nvidia-smi pcie.link.gen`、AER 计数器以及 dmesg 中 `SEC2_DEBUG` 行的数量。 |
| A100 探测套件：`probe.py` + `README.md` + `sweep.sh` | 9,132 / 3,022 / 3,007 B | 2026-07-20 | 在一张**捐赠 A100**上的三步可选写入工作流：先只读盘点，然后由 `sweep.sh` 强制使用 Gen1/2/3，并通过 EXIT 陷阱自动恢复；最后由 `probe.py write-test --confirm` 写入 `0x880a8`、`0x8c044` 和 `0x88088`，并立即恢复，将每一项分类为 `WROTE-OK` 或 `REJECTED(PLM?)`。掩码读取哨兵值为 `0xBADF5040`。同日还有一个更早的 11,472 B 版本 `probe.py`。 |
| `check_fold.py` | 未作为文件归档 | 2026-07-24 | 判断解锁后的 VRAM 是否真实存在的权威测试：分配全部空闲 VRAM 减去 2 GiB，使用 PTX `sm_80` 内核将每个 64 KB 页写入其自身索引，再读回每一页。结果必须是连续的，因为折叠会在通道交错偏移处产生别名。输出 `REAL, NO FOLD` 或 `FOLD/mismatch @<pageindex>`。 |
| `cuda_dbg.py` | 未作为文件归档 | 2026-07-19 | 更轻量的别名测试：先调用 `cuMemGetInfo_v2`，然后依次在 64、60、56、52、48、44、42 GiB 处调用 `cuMemAlloc_v2`，直到某个分配成功；在偏移量 0 写入 `0xAAAA0000`，在 40 GiB 处写入 `0xBBBB0000`，再读取偏移量 0。如果读回 `0xBBBB0000`，就表示地址空间发生了别名。 |

> [!NOTE]
> **`probe.sh` 中记录的两个缺陷**
>
> 它的文件头第 9 行承诺存在一个实际上不存在的 `/dev/mem` 回退；解析部分最后以 `ERROR: cannot find resource0` 和 `exit 2` 收尾。此外，这份目录早于解锁工作，因此没有记录 `0x001fa7c4`、`0x001fa7cc`、`0x001fa824`/`0x001fa828`、`0x009a0148` 或 `0x00100ce0`：这五个寄存器正是发布版解锁实际操作的对象。补上它们是任何人都能做的最有价值的单项改动，而且不需要硬件。

读取 BAR0 需要 root **以及** `CAP_SYS_RAWIO`，而容器化的 GPU 宿主机会丢弃该能力；随后探测器会报错：即使是 root，也无法打开 `.../resource0 (EPERM)`。

---

## 6. 寄存器转储和捕获日志

原始捕获是寄存器参考中大部分核心证据的基础。参见[寄存器索引](register-index.md)。

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `regs_01.txt` | 16,103 B | 2026-07-12 | 一张出厂状态卡上的定向、带注释寄存器读数：`SM_ISSUE_RATE_MODIFIER 0x00504204 = 0xbadf1201`、`FECS_FEAT_OVERRIDE 0x00409664 = 0xbadf5040`、`FEAT_OVR_ECC_PLM 0x00823800 = 0xffffff8f`、`FEAT_OVR_PLM 0x00823804 = 0xffffff8f`、`FEAT_OVR_QUADRO 0x00823808 = 0x00000081`（资料来源将 `0x00000081` 归因于一次*解锁后*探测，而不是出厂状态卡，因此不要把这一项读数理解为二者中的任何一种）、`FEAT_OVR_ECC 0x0082380c = 0x00888888` 等，每项都带有一行用途说明。 |
| PLM 范围扫描（`save.sh`） | 13,544 B 原始 / 12,265 B 清理后 | 2026-07-16 / 07-18 | 一份覆盖 `0x823800` 到 `0x823FFC` 的 `script(1)` typescript，共有**510 个地址/值对**，墙上时钟耗时 28 秒（`Script started 22:51:04+07:00`、`Script done 22:51:32+07:00`），还完整保留了操作者最初笨拙地输入命令行的过程。`0x823800` 到 `0x82382C` 这一块中有**十一**个寄存器处于活动状态，另加 `0x823B00`，总计**十二个**活动 dword。两个地址 `0x823828` 和 `0x823850` 完全没有出现在转储中，这就是扫描包含 510 对、而不是完整步长为 4 的窗口扫描应产生的 512 对的原因。其他所有读数都是 `0xBADF5040`。**两天后在另一个频道发布的清理副本，在全部 510 对上都与原始副本逐字节相同。它是一次观察，不是两次。** |
| `a100.json` | 84,011 B | 2026-07-20 | 一张真实 A100 的完整盘点，用作解释 170HX 熔丝读数的差分参考。 |
| `a100_native_unbound.json`、`gen_native.json`、`gen1.json`、`gen2.json`、`gen3.json` | 33,259 / 33,259 / 33,273 / 33,271 / 33,271 B | 2026-07-20 | 来自捐赠 A100 的强制代际扫描集合。对该卡进行的写入测试没有成功，因此只有读取数据。 |
| `a100-80g.json` | 1,367 B | 2026-07-20 | 一张租用的 A100 80 GB 的简短转储。 |
| `registers.json` | 23,254 B | 2026-07-25 | 一张 **CMP 90HX** 的探测转储，用于跨产品家族比较。 |
| `ga100_topology_output.txt` | 3,345 B | 2026-07-24 | 一张运行中卡的拓扑报告输出。 |
| `reg-ref-a100-vs-170hx.csv` | 1,857 B | 2026-07-27 | 两天内对真实 A100 与原生 8 GB 170HX 进行的跳线和熔丝比较，用于寻找 PCIe Gen3 跳线。**负面结果本身就是发现**；该方法被判定为失败路线，而且 170HX 一侧缺少完整的每-FBPA 捕获。 |
| `00_33_31_scanning_lspci.txt` | 16,427 B | 2026-06-25 | 早期的完整 `lspci` 扫描。 |
| `dmesg_large.txt` | 7,405 B | 2026-07-09 | 一次实验的内核日志，该实验用于测试签名之后的 DMEM 中是否还有任何重要内容。 |
| `bendy2pcielink.txt` | 2,579 B | 2026-07-24 | 一份归档的 `pcielink.sh` 现场报告。 |

---

## 7. 驱动补丁文件和安装器时期 shell 脚本

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `patch.diff` | 35,867 B | 2026-07-18 | 跨 11 个文件共 887 行：将泄露包中捆绑的 open-modules 树与上游标签 `610.43.03` 做差分后提取出的 diff。发布于 18:01:15Z。它在历史上具有决定性作用：参见[净室与来源溯源](../history/clean-room-and-provenance.md)。 |
| `cmpunlocker` 发布版补丁集 | 37,415 B | 2026-07-18 | 六个补丁，共 890 行，涉及 10 个目标文件：`0001-sec2-postbl-plm-ss-cfg.patch`（19,741 B）、`0002-booter-verify.patch`（3,988 B）、`0003-late-pma.patch`（10,580 B）、`0004-bar0-pramin-clamp.patch`（861 B）、`0005-ce-scrub-workarounds.patch`（1,642 B）、`0006-persistent-sw-state.patch`（603 B）。 |
| `0007-pcie-gen2.patch`、`0008-pcie-gen2-probe-retrain.patch` | **2026-07-29 合并至 `master`**（提交 `2e0a2c02`） | 自 2026-07-23 起 | Gen2 工作，先在分支上开发一周，随后合并。`0007` 通过 Booter 载荷原语写入包含 23 项的 `xp3gTable`；`0008` 将 `nv_cmp170hx_retrain_gen2()` 添加到 `kernel-open/nvidia/nv.c`。参见[PCIe Gen2](../unlock/pcie-gen2.md)。 |
| `mod.txt` | 1,725 B | 2026-07-12 | 一段手写的内核 hunk，定义 `CMP170HX_WPR2_SAFE_LIMIT 0x0A00000000ULL`（40 GB），并在附带警告的情况下将超过该值的 `pWprMeta->fbSize` 限制在此值。它是对 WPR2 大小问题的早期、独立表达。 |
| `Guide_SM.sh` | 9,127 B | 2026-07-12 | 完整流水线驱动脚本：阶段 1、FLR、卸载、解锁。 |
| `nuke.sh` | 7,359 B | 2026-07-16 | PLM 批量测试 v3：补丁 GSP、ROP、FLR、终止、FLR，并在不加载驱动的情况下读取 PLM。它在 9 个三轮周期中执行 27 地址持久性扫描，每轮包含两次 FLR。使用 `CANARY_ADDR 0x6340` 处的金丝雀 `0xFACEB13D`，以及 `DMA_TARGET 0x0800`。 |
| `test_580.sh`（三个修订版）、`test_580v6.sh`、`scaffold_580.sh`、`driver.sh`、`a.sh`、`b.sh` | 3.8 到 7.7 kB | 2026-07-08 到 07-12 | 580 分支的实验 harness，包括一个 STRAP 写入修复和一次 `0x65` 状态搜索。 |
| `cmp170hx-gen2-setup.sh` | 12,389 B | 2026-07-26 | 独立的 Gen2 启用器，不同于驱动内分支方法。它自己的文件头准确说明了范围：Gen1 约为 0.85 GB/s，Gen2 约为 1.71 GB/s，恰好提升 2 倍；64 GB 解锁、算力和 HBM 带宽不受影响，不刷写 VBIOS，也不修改内核命令行。 |
| `build-llama-170hx.sh` | 3,802 B | 2026-07-27 | 为这张卡构建可复现的 llama.cpp 容器。 |

> [!CAUTION]
> **`gpuValidateRegOps` 绕过仅存在于 `patch.diff` 中**
>
> `patch.diff` 在 `gpuValidateRegOps` 的第一条语句插入 `return NV_OK;`，对所有 GPU 无条件生效，从而完全禁用寄存器读写验证。该改动**不在**发布版 `cmpunlocker` 树中，也不在全部十二个未发布分支中。任何将它归因于发布版工具的文字都是错误的。

---

## 8. 长篇说明文档和现场手册

| 工件 | 大小 | 日期 | 论证内容 |
|---|---:|---|---|
| `ROP_CHAINS_1180f8_nibble_writeup_20260715.md` | 9,628 B | 2026-07-15 | 将交接状态问题整理成需求表：在一次免驱动触发之后，`resetPLM 0x8403C4` 必须读为 `0xff`（因为 `0x8f` 会阻止 SEC2 SFTRESET），必须清除 WPR2 `0x1FA824/28`，并且 `1180f8` 的位 [31:28] 必须为 `0x1`。前两项已经解决，半字节问题尚未解决。文档还记录了每次写入的 `+0x18 DMEM` 帧步长，并将 `D[0xFF50]` 到 `D[0xFF84]` 制成表格。发布于 2026-07-15T18:48:10Z。 |
| `WRITEUP.md` + `WRITEUP_EXPLAINED.md` | 12,950 + 12,335 B | 2026-07-23 | 对 `0x2082` 卡进行的 FFMA 节流调查：实测 0.315 TFLOPS，而理论值为 25.27 TFLOPS；**对 GSP 固件做了 14 个二进制补丁，并修改了多个内核模块，但没有一项改变节流**。其结论是，该限制由熔丝强制执行，固件无法触及；这是一个有价值的负面结果，只有完全不同的 SEC2 路线能够推翻它。 |
| `CMP_170HX_40GB_UNLOCK_GUIDE.md` | 11,994 B | 2026-07-22 | 端到端说明一次加载 40 GB 的驱动补丁：只需一次 `modprobe`，不需要 FLR，不交换固件，并逐步写出 `modprobe` 时的执行顺序。 |
| `PCIE_GEN1_LOCK.md` | 15,467 B | 2026-07-24 | PCIe 速度上限现场手册。开篇即将**速度**与**位宽**分开，并明确将位宽问题（C1100 到 C1350 的 24 颗电容焊接改装）排除在范围之外。状态行是：“Software and keyless-firmware surface exhausted; remaining paths are physical.”（软件和无钥固件层面已无可用空间；剩余路径属于物理层面。） |
| `ga100_fbpa_hbm_timing_registers.md` | 23,682 B | 2026-07-25 | 定义广播 FBPA 范围 `0x009A0000` 到 `0x009A3FFF` 内 `0x9A0200` 到 `0x9A0300` 的 HBM 时序寄存器，并给出关键观察：`CONFIG0.USE_TIMING_REGS`（`0x9A0290` 的位 31）读数为 **0**，因此活动参数是内部生成的 `TIMING*_GEN` 影子，而不是原始的 `TIMING*`/`CONFIG*` 值。 |
| `untitled.md` | 5,814 B | 2026-07-17 | 个人架构笔记，发布时附带作者自己的评价：大约**百分之十**具有可靠证明或来源；同时警告，将聊天中的所有观点汇编成文档会产生许多错误结论。 |
| `README.txt` | 4,637 B | 2026-07-18 | 泄露包的配套说明。 |

---

## 9. 基准测试、调优和工作负载工件

| 工件 | 大小 | 日期 | 内容 |
|---|---:|---|---|
| `170hx-tuning-guide.md` | 26,987 B | 2026-07-27 | 与 `170tune` harness 一同发布。它针对一张明确命名的参考卡编写（GA100、70 SM、已解锁 64 GB、驱动 610.43.03、300 W VBIOS `92.00.6D.00.0A`、PCIe Gen2 x4），并明确说明每张卡的晶体管特性不同；在将任何偏移量用于其他卡之前，必须先执行“qualifying a new card”流程。它也记录了已经关闭的失败路线，避免同一条路被重复走两次。 |
| `170HX-benchmark-results.md` | 5,290 B | 2026-07-27 | 八张已解锁 64 GB 卡，驱动 610.43.02、`sm_80`、PCIe **Gen1 x4**，且没有电容改装。逐卡 torch GEMM 结果：FP16 张量为 162.7 TFLOPS，BF16 张量为 171.4 TFLOPS。 |
| `GLM-5.2-benchmark-report.md` | 7,999 B | 2026-07-24 | 一份值得保留的负面结果报告：无法加载 467 GB 的 4 位量化模型，因为主机只有 88 GB 系统 RAM，远低于 llama.cpp 在加载时执行计算图 pass 所需的内存；RSS 被卡在约 87.6 GB，始终没有进展。这是主机侧失败，不是显卡限制。 |
| `cublas_benchmark1` | 826,072 B | 2026-07-16 | 一个动态链接到 `ld-linux-x86-64.so.2` 的 x86-64 ELF 可执行文件。这是一个**分发给他人运行的编译二进制**，不是结果日志。 |

这些数字在上下文中的含义，请参见[性能](../operations/performance.md)和[LLM 推理](../operations/llm-inference.md)。

---

## 10. 未保留的内容

明确说明缺口也是这份目录的一部分。

- **没有 Booter 二进制文件。** 工具会引用签名的 HS 映像及其分离签名（`booter_load_580_image.bin`、`booter_load_580_sig.bin`，预期位于 `cmp170hx_boot_bins/verified_hs/` 下），但档案中没有这些文件。
- **没有 8 GB WprMeta 捕获。** 免驱动链使用的 256 字节模板来自一次真实的 10 GB 启动。捕获 8 GB 等价物是一项规模很小且没有阻塞因素的任务。
- **没有调试版和生产版 Booter 映像的哈希比较。** bindata 档案可以轻松完成这项工作，并确定两份映像是逐字节相同，还是只有大小相同。
- **没有仿真器。** 学术论文中描述的 Falcon 仿真器从未发布。
- **没有驱动修改指南。** 能够解决若干来源溯源问题的两份私人文档不在这组来源中。
- **`master` 上没有 `verify.sh`**，它的任何分支副本中也没有 Gen2 检查。
- **`master` 没有 `tools/` 目录。** `probe.sh`、`pcielink.sh`、`check_fold.py`、`cuda_dbg.py`、A100 探测套件和 refire 链都在仓库外分发。克隆仓库不会得到其中任何一个。

---

## 相关页面

- [解锁如何工作](../unlock/how-it-works.md)
- [Falcon 与 Booter](../unlock/falcon-and-booter.md)
- [ROP 链](../unlock/rop-chain.md)
- [驱动补丁](../unlock/driver-patches.md)
- [寄存器参考](../unlock/register-reference.md)和[寄存器索引](register-index.md)
- [工具谱系](../history/tool-lineage.md)
- [外部来源](external-sources.md)
- [方法论](methodology.md)
