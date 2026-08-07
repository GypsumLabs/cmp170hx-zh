# SEC2 Falcon 与 Booter Load 微码

**本页覆盖内容。** 本页介绍 CMP 170HX 解锁所依赖的安全协处理器：SEC2 Falcon 的作用、"Booter Load" 微码执行的工作、重度安全模式的进入与退出、booter 映像在两套地址空间中的布局、GSP 签名缓冲区的位置，以及打过补丁的驱动如何准确调用 booter。利用链本身见[ROP 链](rop-chain.md)，它打开的掩码见[权限级别掩码](privilege-level-masks.md)。

**两句话的关键结果。** NVIDIA 自己签名并用 AES 加密的 `booter_load` 微码会先按正常流程加载并通过认证，认证*已经*成功后，才被主机驱动控制的签名缓冲区破坏。整个过程既没有伪造签名，也没有提取密钥，更没有执行攻击者提供的指令；booter 在逐字节仍是 NVIDIA 发布版本的前提下，成为解锁的执行引擎。

---

## 1. 为什么会有 Booter

GA100 晶片上有两个与本主题直接相关、但性质完全不同的处理器。

| 处理器 | 位置 | 核心 | 密码功能 | 角色 |
|---|---|---|---|---|
| SEC2 Falcon | BAR0 `0x00840000` | Falcon v4/v5，16 位哈佛 | AES + RSA + SCP 机密 | 安全协处理器，负责解密并验证自身代码映像。 |
| GSP | BAR0 `0x00110000` / `0x00111000` | NVIDIA RISC-V（NVRISCV） | 无 | 运行资源管理器固件 GSP-RM。 |

GSP RISC-V 核心没有密码功能，因而不能自行验证映像。验证工作被交给 SEC2 Falcon 上名为 *booter* 的微码。系统中有两个 booter：`booter_load` 和 `booter_unload`；本页只讨论 `booter_load`。

booter **不是**[VBIOS](../hardware/vbios.md) 的组成部分。它和所验证的加密 GSP 固件一样，按版本随驱动发布，并作为编译进 `nvidia.ko` 的 BINDATA 数组提供。驱动 610 中的 GA100 数组如下：

```text
kgspBinArchiveBooterLoadUcode_GA100_BINDATA_LABEL_IMAGE_DBG_data[]
  位于 src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c
  DATA SIZE (bytes): 60160
  COMPRESSED SIZE (bytes): 34145
```

因此运行该利用不需要另行准备 booter 文件，驱动包本身已经包含它。

完整的引导链是：上电后从 SPI 闪存加载 VBIOS；晶片上的 Falcon 验证 VBIOS；晶片进入安全模式；驱动提供 `gsp_tu10x.bin`，由 Falcon 验证其签名；最后驱动通过 GSP 客户端读取显存容量并让设备对外可用。解锁针对的是第四步，即把载荷放入 booter 将要 DMA 的 GSP 签名缓冲区。

---

## 2. Falcon 安全模型

自 Maxwell 起，Falcon 提供三种执行模式。

| 模式 | 如何进入 | 它能做什么 |
|---|---|---|
| 非安全（NS） | 加载任意代码，设置 BOOTVEC 和 STARTCPU | 唯一无需 NVIDIA 签名微码即可进入的模式，但许多寄存器和 DMA 对它受限。 |
| 轻度安全（LS） | 只能从重度安全上下文进入（GM20x 及以后） | 权限介于 NS 与 HS 之间。 |
| 重度安全（HS） | PC 落入标记为安全的代码块且 MAC 比较成功后由硬件授予 | Falcon 变成黑盒，外部不能读写其内部状态；它以 LEVEL2/L3 运行，可以重写权限级别掩码并编程受保护区域。 |

项目中所谓的 "L0 到 L3" 权限级别就是这套模型。各级别如何在寄存器级别被强制执行，见[权限级别掩码](privilege-level-masks.md)。

`booter_load` 永远不能在 NS 模式下执行。它的主体经过 AES 加密，只能由处于 HS 模式的 Falcon 解密。Falcon 先运行 0x100 字节的明文 NS 前导，再发出特殊指令解密并验证主体，随后切换到 HS。这个架构事实直接决定了解锁的形态：

> [!NOTE]
> **决定整个方案的规则**
>
> 解锁过程中的每一次 HS 特权寄存器写入，都必须由被劫持的真实 booter 内部发出。自制微码无法做到这一点，因为它不可能被安排在 HS 模式运行。

HS 进入例程据 Tegra TSEC 的逆向结果推断，在 GA100 SEC2 上具有相同结构。它计算 `microcode_start = (*SEC & 0xFF) << 8` 和 `microcode_size = ((*SEC >> 24) & 0xFF) << 8`，将微码的 Davies-Meyer MAC 计算到 `$c5`，然后执行：

```asm
csecret $c3, 0x1
ckeyreg $c3
cenc     $c3, $c7
ckeyreg  $c3
cenc     $c4, $c5
csigcmp  $c4, $c6
```

开始地址或大小为零都会触发 `OP_SECURE_FAULT`。认证必须同时满足四项条件：微码页映射到预先选定的虚拟地址；页面被标记为机密；这些信息已载入 `SEC` 寄存器；密码寄存器 6 中存在有效 MAC。

> [!WARNING]
> **不要混淆两套不同的验证方案**
>
> 不可变引导 ROM 对 HS booter 映像的检查，在资料中被描述为 RSA-3K 检查；映像确实在 `PATCH_LOC = 0x8900` 附带一个 384 字节签名块。另一条路径是 booter *自身*验证它加载的 GSP 映像。这条路径可追溯为 `_acrVerifySignature_TU10X` → `_acrCalculateDmhash_TU10X` → `_acrDeriveLsVerifKeyAndEncryptDmHash_TU10X` → `_acrMemcmp`，其本质是 Davies-Meyer 哈希加上由 `csecret` 派生的 AES 密钥派生，不使用 RSA。booter 另有一段独立的 PKA/modexp 代码（`rsa_pubkey_load 0x4768`、`pka_modexp_run 0x54ab`）供其他流程使用。这个调和结论的置信度为中等，因为资料中没有人用完全相同的术语明确表述过它。

解锁没有破坏其中任何一套方案。

---

## 3. 哈佛架构：两个绝不能混用的地址空间

> [!CAUTION]
> **IMEM 与 DMEM 地址外观相同，但绝不能互换**
>
> SEC2 Falcon 是**哈佛架构**核心，拥有彼此独立的 16 位指令内存（IMEM）和 16 位数据内存（DMEM）。把 `0x6340` 当作 IMEM 地址时，它只是无意义的代码；把它当作 DMEM 地址时，它却是栈金丝雀守卫全局变量。流传的一些文档把两套空间混成一个 "memory map"，这是错误的。本维基中的每个地址都会明确标注为 IMEM、DMEM、CSB（Falcon I/O）或 BAR0。

| 属性 | IMEM | DMEM |
|---|---|---|
| 大小 | `0x10000`（64 KB） | `0x10000`（64 KB） |
| Falcon 虚拟窗口 | `0x4000000`-`0x400FFFF` | `0x4010000`-`0x401FFFF` |
| 块对齐 | 256 字节（`FLCN_BLK_ALIGNMENT`） | 256 字节 |
| 利用碰什么 | 无 | `0x0800`-`0xFFFF` |

GSP 签名缓冲区位于 DMEM，因此签名 DMA 只能破坏 DMEM，绝不可能写入 IMEM。仅凭这一点就能确定该利用属于在已签名映像上进行的纯 ROP，而不是代码注入。同时，DMEM 的 16 位地址空间本身无法寻址 32 位 BAR0 寄存器，所以载荷必须借助能够驱动 Falcon BAR0 master 的 gadget。

全篇还会出现另外两个空间：

- **CSB / Falcon I/O**，由 `iord` / `iowrs I[...]` 寻址。例如 `I[0x1000]` 是 MAILBOX0、`I[0x9100]` 是 `FALCON_CSBERRSTAT`、`I[0x1c000]`/`I[0x1c100]`/`I[0x1c200]` 是 BAR0 master。
- **BAR0 / PRI**，主机对特权寄存器接口的 32 位视角。主机、SEC2 和 GSP RISC-V 都经 PRI 通信；PLM 门控它的区域。

---

## 4. 从主机看到的 SEC2：BAR0 寄存器图

SEC2 的基址是 `NV_PSEC_BASE = 0x00840000`，它是 Falcon 核心而不是 RISC-V；读取 `HWCFG2` 的位 10 得到 0。下面的完整偏移表已由运行在 `10de:20c2` GPU 上的无驱动 C 加载器验证：

| 寄存器 | 偏移量 | 绝对地址 | 备注 |
|---|---|---|---|
| `IRQSCLR` | `+0x004` | `0x00840004` | |
| `IRQSTAT` | `+0x008` | `0x00840008` | |
| `MAILBOX0` | `+0x040` | `0x00840040` | Falcon CSB `I[0x1000]` 的主机别名 |
| `MAILBOX1` | `+0x044` | `0x00840044` | |
| `SFTRESET` | `+0x07c` | `0x0084007c` | PL0 写对 HSMODE 无作用 |
| `FALCON_RM` | `+0x084` | `0x00840084` | |
| `EXCI` | `+0x0d0` | `0x008400d0` | 异常信息 |
| `HWCFG2` | `+0x0f4` | `0x008400f4` | 位 10 = RISCV |
| `CPUCTL` | `+0x100` | `0x00840100` | 位1 STARTCPU，位3 IREADY，位4 HALTED，位5 STOPPED，位6 ALIAS_EN |
| `BOOTVEC` | `+0x104` | `0x00840104` | |
| `DMACTL` | `+0x10c` | `0x0084010c` | 位1 DMEM_SCRUB_PENDING，位2 IMEM_SCRUB_PENDING |
| `DMATRFBASE` | `+0x110` | `0x00840110` | `(phys >> 8) & 0xFFFFFFFF` |
| `DMATRFMOFFS` | `+0x114` | `0x00840114` | |
| `DMATRFCMD` | `+0x118` | `0x00840118` | 位0 FULL，位1 IDLE，位2-3 SEC，位4 IMEM，位5 WRITE，位8-10 SIZE（`0x6` = 256 B），位12-14 CTXDMA，位16 SET_DMTAG |
| `DMATRFFBOFFS` | `+0x11c` | `0x0084011c` | |
| `DMATRFBASE1` | `+0x128` | `0x00840128` | `((phys >> 8) >> 32) & 0x1FF` |
| `CPUCTL_ALIAS` | `+0x130` | `0x00840130` | |
| `TRACEPC` | `+0x14c` | `0x0084014c` | 位 [23:0] = PC 快照 |
| `IMEMC0` | `+0x180` | `0x00840180` | 位24 AINCW，**位28 SECURE**，位23:8 BLK，位7:2 OFFS |
| `IMEMD0` | `+0x184` | `0x00840184` | |
| `IMEMT0` | `+0x188` | `0x00840188` | |
| `DMEMC0` | `+0x1c0` | `0x008401c0` | |
| `DMEMD0` | `+0x1c4` | `0x008401c4` | |
| `SCTL` | `+0x240` | `0x00840240` | 位0 LSMODE，位1 HSMODE（只读），位14 AUTH_EN |
| `IMEM_PRIV_LEVEL_MASK` | `+0x280` | `0x00840280` | |
| `DMEM_PRIV_LEVEL_MASK` | `+0x284` | `0x00840284` | 在 LS 模式读 `0xFF` 完全打开 |
| `FBIF_TRANSCFG(n)` | `+0x600 + 4n` | `0x00840600`+ | TARGET 位 [1:0]：0 LOCAL_FB，1 COHERENT_SYSMEM，2 NONCOHERENT_SYSMEM；MEM_TYPE 位 2 = PHYSICAL |
| `FBIF_CTL` | `+0x624` | `0x00840624` | 位 7 = ALLOW_PHYS_NO_CTX |
| `FALCON_ENGINE` | `+0x3c0` | `0x008403c0` | 位0：1 = 复位，0 = 运行 |
| `RESET_PRIV_LEVEL_MASK` | `+0x3c4` | `0x008403c4` | 复位 PLM。见第 10 节。 |
| `PRIVSTATE_PLM` | `+0x3d0` | `0x008403d0` | 仅具名，从未写测试过 |
| `SCP_CTL_P2PRX` | `+0x530` | `0x00840530` | 位3 SFK_LOADED |
| `KFUSE_LOAD_CTL` | `+0x11ec` | `0x008411ec` | 读它触发 SFK 加载 |

作为对照，GSP 一侧使用 `NV_FALCON2_GSP_BASE = 0x00111000`、`RISCV_STATUS 0x00111240`、`RISCV_CPUCTL 0x00111268`、GSP `MAILBOX0 0x00110040`，以及 GSP FBIF 基址 `0x00110600`。

`EXCI` 的解码方式是 `expc = ((exci >> 28) << 20) | (exci & 0xFFFFF)`，以及 `excause = (exci >> 20) & 0x1F`。原因码包括 `0x08` ILL_INS、`0x09` INV_INS、`0x0a` MISS_INS、`0x0b` DHIT_INS（IMEM 块存在但未通过 BROM 认证）、`0x0d` SP_OVERFLOW、`0x0f` BRKPT_INS、`0x10` DMEM_MISS、`0x11` DMEM_DHIT、`0x12` DMEM_PAFAULT、`0x13` DMEM_PERM、`0x15` BROM_CALL、`0x16` KMEM_VIOLATION 和 `0x17` BMEM_PERM。

---

## 5. Booter Load 映像

### 5.1 文件布局

| 区域 | 偏移量 | 内容 |
|---|---|---|
| NS 引导程序 | `0x0000`-`0x0100` | 明文。256 字节。 |
| HS 代码 | `0x0100`-`0x8600` 或 `0x0100`-`0x8700`；**来源相差 256 字节** | AES-128-ECB 加密。 |
| 数据（`osData`） | 算术上是 `0x8700` 起；`0x8600` 也被引用 | 第 11 节的 `hsSigDmemAddr = patchLoc - dataOffset` 推导需要 `0x8700`（`0x8900 - 0x8700` = DMEM `0x200`），34,304 字节的安全代码测量也一样（`0x0100`-`0x8700` 是 34,304 字节；`0x0100`-`0x8600` 只有 34,048）。两条证据线指同一方向，所以 `0x8600` 是较弱的读数。对齐解密偏移量前对你自己的映像验证。 |
| 签名 | `0x8900`（`PATCH_LOC`） | 384 字节 |

未压缩代码大小为 `0x8700`，即 34,560 字节。所分析调试签名构建的实测分段是：34,304 字节 HS 代码、25,600 字节数据和 256 字节 NS 代码。原始提取的 GA100 文件会用零填充到 60,100 字节，而编译进驱动的 BINDATA 块大小为 60,160 字节。

加密区域恰好从 `0x100` 开始（16 的倍数），那里第一条解密指令是：

```text
89 fc ff 00    mov $r9 0xfffc
```

### 5.2 密码破解

这一发现使得无需任何泄露源码也能进行明文反汇编：

> [!NOTE]
> **调试版和量产版 booter 映像的明文代码完全相同**
>
> 两者只有 AES 密钥不同。调试映像使用非机密的编号测试密钥加密，因此解密调试映像即可读出量产 HS 代码。底层密码学发现于 2026 年 5 月，并于 2026-07-01 应用于 GA100。

实用标记：

| 量 | 值 |
|---|---|
| 调试密钥编号 | 37 |
| 那个密钥下尾部零填充的 AES-128-ECB 密文 | `717D1494 EACA317F F1061952 58B38377` |
| 反汇编器 | `envytools` / `envydis` |

如果上面的 16 字节常量紧挨着文件自身的零区域出现，说明调试块提取正确且偏移对齐；用测试密钥工具解密后重新得到零，也能证明解密成功。量产块的尾部模式不同。一个容易漏掉、却会浪费数小时的细节是：喂给 AES/Rijndael 工具的 4 字节轮密钥，顺序必须与人类可读形式**相反**，因为密钥编号位于最后一轮密钥而不是第一轮。置信度为中等：这是一条单独的操作性结论，但所描述的流程确实产生了正确输出。

### 5.3 提取

提取过程是给 NVIDIA 自己的 `extract-firmware-nouveau.py` 打补丁，使其只输出 GA100 的量产版和调试版 booter。脚本解析 `kgspBinArchiveBooter{Load,Unload}Ucode_GA100_BINDATA_LABEL_IMAGE_{PROD,DBG}_data` 及匹配的 `..._SIG_{PROD,DBG}_data`。**GA100 每个签名的大小是 384 字节**，而 TU10x 只使用 16 字节，因此调用形式为 `booter('ga100','load',384,'prod')` 及其另外三个组合。所有非 GA100 芯片（tu102、tu116、ga102、ad102、gh100、gb100、gb202）都从 `main()` 中注释掉了。

第二个变体 `extract-firmware-nouveau-ga100-raw.py` 会去掉全部容器结构，包括带 `0x10de` 魔数和 6 个 dword 的 `nvfw_bin_hdr`、带 9 个 dword 的 `nvfw_hs_header_v2`、签名块、`patch_loc` / `patch_sig` / `fuse_ver` / `engine_id` / `ucode_id` / `num_sigs` 以及描述符，只将原始固件写入 `booter_{load,unload}_{prod,dbg}-<ver>_raw.bin`。这个原始布局随后交给 envydis 和 objdump，也是后续所有工具链的输入。

还有一条路径从已加载的出厂驱动获取映像：设置位 25 以启用自动递增，通过 `IMEMC 0x840180` 和 `IMEMD 0x840184` 读取偏移 `0`..`0x8700` 的 SEC2 IMEM，再通过 `DMEMC 0x8401c0` / `DMEMD 0x8401c4` 读取 DMEM，最后拼接 IMEM(NS+HS) 与 DMEM。

无需反汇编器也能恢复 Booter 的几何布局：扫描原始映像前 `0x100` 字节即可。`imm_before(ns, ff9f04)` 得到 NS 末尾，`imm_before(ns, fd9e04bb9002b69410)` 得到 DMEM 偏移；`imm_before` 要求标记前四个位置的字节为 `0x89`（`mov $r9 imm24` 操作码），然后组装小端序 24 位立即数。如果任一标记不存在，或 `dmem <= base`，解析器会抛出 "not an ACR booter image"。加载时，`img[0:ns]` 以非安全方式写入 IMEM 0，`img[ns:dmem]` 写入 `IMEM[ns]` 并设置 SECURE 位 `1 << 28`，`img[dmem:]` 则写入 DMEM 0。

### 5.4 版本可移植性

| 驱动分支 | GA100 `booter_load` | gadget 地址有效？ |
|---|---|---|
| 515 时代 | 不同的构建；金丝雀全局在 `0x2B20` 或 `0x2D20` | 否 |
| 580 到 610 | **逐位相同**（跨 580.173.02、580.159.04、580.159.03、610.43.02、595.84 验证） | 是 |

因此，本维基列出的每个 ROP gadget 地址在 580-610 的整个范围内都有效，不需要重新推导。515 booter 是本项目之前公开反汇编的版本，并不包含这个漏洞。

已发表论文使用的跨版本资料覆盖 450、460、470、510（两个点版本）、515、525、535、560、570 和 580 分支。510 SEC2 booter 的签名路径只使用常量或经过限制的 DMA 长度，没有按元数据大小复制；580 booter 则出现无界复制；525 映像因 booter 的打包方式发生变化而无法恢复。

> [!NOTE]
> **未解问题：最早受影响的驱动分支**
>
> **510 中没有**溢出，**580 中存在**溢出，而 515 到 570 分支目前**无法确定**。要得到结论，必须恢复并分析 515、535、560 和 570 的 GA100 booter，检查其中是否存在按元数据大小执行的复制。

### 5.5 谱系命名

GA100 使用 **Turing 代**固件：GSP 块名为 `gsp_tu10x.bin`，SEC2 booter 是 Turing 谱系的 `booter_load`。NVIDIA 自己的树 `nouveau/extract-firmware-nouveau.txt` 明确说明了这一点；失败路径上的 TU102 后缀 RM 符号（`kgspBootstrap_TU102`、`s_executeBooterUcode_TU102`）也提供了佐证。经过频道内更正后，命名关系如下：

| 前缀 | 覆盖 |
|---|---|
| `tu10x` | 全部 Turing |
| `ga100` | 仅 A100 和 CMP 170HX |
| `ga10x` | 其它 Ampere（GA102、RTX 3090、CMP 90HX） |

由于 170HX 加载的是 Turing `booter_load`，它继承了 Turing booter 的 DMA/签名溢出。加载 Ampere booter 的显卡是否也会从该路径继承这一问题，仍有争议且尚未解决；见[未解问题](../frontier/open-questions.md)。

---

## 6. Booter 内部：IMEM 函数图

下表中的所有地址，都是解密后的调试签名映像 `booter_load_ga100_dbg_seccode.fuc5.asm` 的 **IMEM**（代码）地址。带注释清单 `booter_load_ga100_dbg_seccode.annotated.fuc5_v2.asm` 共包含 10,934 行未修改代码，并以函数横幅分隔。

| IMEM | 符号 | 角色 |
|---|---|---|
| `0x0100` | `_start` | 入口点。十阶段 HS 序言。 |
| `0x04a7` | （自循环） | `3e a7 04 00 B lbra 0x4a7`。载荷填充 dword 用来停在这里自旋。 |
| `0x04d0` | `_start` 出口 | |
| `0x04d4` | `dma_copy_block` | 执行实际 DMA 到 DMEM 的循环（`xdld`）。**发生溢出的栈帧。** |
| `0x0602` | `dma_dispatch_descriptors` | 最多提交四个子描述符，并将其标记为 `r14 = 0xa0..0xa3` |
| `0x0c7c` | `regblock_read_guarded` | |
| `0x0cbd` | elevator | `0x0c7c` 里的 `mov $r10 $r0` |
| `0x0ccb` | `regtable_rw_indexed` | 对寄存器描述符表的索引访问；以 `mpopaddret $r5 0x8` 结束 |
| `0x0d66` | ACR 互斥锁获取 | id 字节读到 0 或 `0xff` 时返回错误 `0x1a`，类型错误时返回 `0x1c` |
| `0x0e85` | `memcpy` | |
| `0x0aa1` | `tgt_falcon_bringup` | 拉起目标 Falcon；错误 `0x1c`、`0x11` |
| `0x1034` | `watchdog_set` | 用 `0x1312d00`（20,000,000）播种 `I[0x1c300]` |
| `0x1064` | `mailbox_wait_ready` | 轮询 `I[0x1c000]` 的位 [14:12]：0 表示完成，1 表示继续自旋，其余值返回错误 `0x15` |
| `0x10aa` | `reg_write_indirect` / `_acrlibBar0RegWrite_TU10X` | **任意 BAR0 写原语。** 约有 70 个调用点。 |
| `0x10b9` | （中途进入） | 跳过 `r10`/`r11` 到 `r0`/`r1` 的编组 |
| `0x10ff` | `mpopaddret $r3 0x4` | `0x10aa` 的尾声；让写自我链接 |
| `0x1196` | `reg_read_indirect` | |
| `0x14cf` | `tlb_scan_invalidate` | 使映像自身的陈旧映射失效，范围为 `[0, 0x8700)` |
| `0x154a` | `wpr_desc_validate` | +0 处魔数 `0x371a60b3`、+4 处 `0xdc3aae21`；错误 `0x89`-`0x90` |
| `0x19a2` | `va_to_pa_walk` | 软件实现的三级页表遍历；错误 `0x2` |
| `0x1b44` | `set_1180f8_bit24` | 把 `0x01000000` OR 进 `0x001180f8` |
| `0x1ba3` | `check_1180f8_2724` | 要求 `0x001180f8[27:24] == 0`，否则错误 `0x88` |
| `0x1c0e` | `set_1180f8_top_nibble`（finalize） | 清除 [31:28] 后 OR 入 `(r0 << 28)`；尾声位于 `0x1c72` |
| `0x1c75` | `check_1180f8_nibbles` | 要求 [31:28] == 0 **且** [23:20] == 0，否则错误 `0x29` |
| `0x1d0f` | `report_status` | 把 `$r0` 写进 MAILBOX0 |
| `0x1d3b` | `f100_field_save_restore` | 通过 DMEM `0x1900` 对寄存器 `0xf100` 的位 [4:6] 执行 RMW |
| `0x1e09` | `scp_key_derive` | 带硬件机密 `0x37` 或 `0x36` 的 `csecret $c7` |
| `0x1f92` | `read_820344_820348` | |
| `0x1fb9` / `0x1fbd` / `0x1fca` | elevators | 见[ROP 链](rop-chain.md) |
| `0x21f4` | `image_dma_loader` | 调用点 `0x2725` |
| `0x2120` | `chunked_dma_copy` | 对寄存器 `0x4b00` 的 `0x100` 字节块 |
| `0x22ba` | `booter_load_wpr_main` | 可能返回错误 `0x5`、`0x89`、`0x8a`、`0x96`、`0x98`、`0x9c`、`0xa4` |
| `0x27fa` | `0x22ba` 内的重接点 | 写入 `D[0x6f8]`/`D[0x6fc]`/`D[0x648]`；**不会**触及 WPR2 寄存器 |
| `0x28ac` | `wpr_region_check` | 错误 `0x5` |
| `0x291e` | `wpr_region_program` | 实际写 `0x001fa824`/`0x001fa828`；拒绝空区域 |
| `0x2e80` | `image_auth_decrypt` | 以 `0x100` 字节为块流式处理，密钥句柄为 `0x17d78414` |
| `0x3747` | `image_copy_verify` | 正常返回 `0x2740` |
| `0x37b3` | 签名 DMA 调用点 | `lcall 0x4d4` |
| `0x37b7` | DMA 后结果检查 | `ld $r9 D[$r1+0x50]` |
| `0x399a` | `ls_sig_verify` | 要求 `r10 == 0x700`，否则返回错误 `0x98` |
| `0x3c8f` | `firmware_load_main` | DMEM `0x5f00` 处魔数 `'FREE'` / `'HEAP'` |
| `0x4768` | `rsa_pubkey_load` | 模数零填充到 `0x200`，`e = 0x10001` |
| `0x54ab` | `pka_modexp_run` | 错误 `0x63`-`0x6d`（`0x6c` 超时） |
| `0x59c4` | `antirollback_version` | 密钥句柄 `0x17d78400`；错误 `0x5c`、`0x1` |
| `0x683f` | `boot_mode_dispatch` | |
| `0x68ed` | `reg_init` | 写 `0x110624 = 0x90`、`0x110684 = 1`、`0x11126c = 1` |
| `0x6a71` | `chipid_gate` | 只接受芯片 ID `0x170` 和 `0x171`；错误 `0x4b` |
| `0x6abd` | `rsa4096_pubkey_load` | 四张 512 字节表 |
| `0x76ee` | `fb_size_compute` | 解码 LMR。见[显存几何布局](memory-geometry.md)。 |
| `0x79cc` | `memcfg_program` | |
| `0x7a64` | `memcfg_apply_poll` | 超时 100000，错误 `0xa6` |
| `0x7c65` | `memcfg_timing_program` | 超时 125000，错误 `0xa7`，基常量 `0x32a` |
| `0x7dd9` | `__stack_chk_fail` / `panic()` | 向 MAILBOX0 写入 `0x47`，随后在 `0x7def` 自旋 |
| `0x7de9` | （panic 主体） | 输出 `$r15` 中的值，是所有调试 ROP 的基础。 |
| `0x7df3` | `memcmp_ct` | 恒定时间比较 |
| `0x7e76` | `secure_teardown` | 永不返回 |
| `0x7eef` | 密码自清零扫描 | 位于 `secure_teardown` 内部 |
| `0x7f2f` | `secure_teardown` 里的退出 gadget | 发布版载荷使用的终止符 |
| `0x7f82` | **`main`** | |
| `0x8137` | `booter_load_wrap` | |
| `0x815a` | `booter_load_wrap` 的金丝雀检查尾 / 栈吞噬器 | 见下方说明 |
| `0x8224` | `csb_write` | 存储是 `0x8232` 处的 `iowrs I[$r10] $r11` |
| `0x8262` | 裸 `ret` | 有用的对齐 gadget |
| `0x8264` | `csb_read` | |
| `0x8307` | `fbif_set_bit800` | 在掩码 `0x0ffff8ff` 下，将位 `0x800` 写入 `0x001fa814`/`0x001fa818` |

> [!NOTE]
> **已解决：`0x815a` 位于 `booter_load_wrap` 内部**
>
> 一份目录称它为 "the main canary-check tail"；另一份注释为 "a stack-eater in `booter_load_wrap` that checks the canary and does nothing"（`booter_load_wrap` 中检查金丝雀但不执行其他工作的栈吞噬器）。带注释的 v2 清单解决了这一歧义：`main` 从 `0x7f82` 运行到 `0x8134`，自身的金丝雀检查在这里以 `mpopaddret $r0 0x10` 结束；`booter_load_wrap` 从 `0x8137` 运行到 `0x8173`，以 `mpopaddret $r0 0x4` 结束，下一个函数横幅则在 `0x8176` 的 `nibble_rmw`。因此 `0x815a` 明确位于 `booter_load_wrap` 内，由 `0x8150` 处跳过 `boot_mode_dispatch (0x683f)` 调用的 `bra b32 $r10 0x0 e 0x815a` 到达。它是包装器的金丝雀检查尾；`main` 自己的尾是 `0x811d` 的独立代码块。第二份目录才是正确的。

---

## 7. 引导流程

### 7.1 `_start`（IMEM `0x0100`）：十阶段 HS 序言

1. 在 `0x0107` 擦除 SCP 状态（`csigclr` / `csecret` / `cxor`）。每条 `csecret $cN 0x0` 后面都紧跟 `cxor $cN $cN`，因此寄存器组一完成配置就会被清零。
2. 在 `0x014b` 清空全部通用寄存器 `$r0`..`$r15`。
3. 在 `0x016b` 让 Falcon 进入静默状态，并轮询 `I[0x9100]` 的位 31。
4. 在 `0x02b3` 清除中断使能标志 `ie0` / `ie1` / `ie2` 以及定时器/异常标志；具体做法是依次将 `0x10` / `0x11` / `0x12` / `0x18` 放入 `$r9`，每次后执行 `bclr $flags $r9`。
5. **阶段 5** 设置陷阱向量 `$tv = 0xeb`，并清除 `$cauth` 的安全故障使能位：`mov $r9 0xeb; mov $tv $r9; mov $r9 $cauth; mov $r15 -0x80001; and $r9 $r15; mov $cauth $r9`。
6. **阶段 6** 按顺序访问 CSB `0x4e00`（先应用掩码 `0xff000000`，再 OR `0x80003000`）、`0x10100`（OR `0x101`，等待位 `0x100` 清零，最多循环 `0x400` 次）、`0x14000`（写入 `0x7fff`）、`0x14100`（保留低 16 位并 OR `0x03ff0000`）和 `0x14b00`（OR `0xff00`），最后再次访问 `0x10100`（OR `0x1000`）。
7. 在 `0x0433` 通过 `crnd` 完成 SCP 自配置。
8. 在 `0x0463` 验证 SCP，并扫描 DMEM `0x6330`..`0x6340`。
9. **阶段 9** 清除 `0x10100` 的位 `0x1000`（与 `-0x1001` 做 AND），再把栈金丝雀安装到 DMEM `0x6340`。金丝雀取自扫描 DMEM `0x6330`..`0x6340` 时找到的第一个非零字。
10. 在 `0x04cc` 执行 `lcall 0x7f82` 进入 `main()`，并在 `0x04d0` 退出。

### 7.2 `main`（IMEM `0x7f82`）

`main` 按以下顺序组织流程：`f100_field_save_restore (0x1d3b)`；权限级别掩码和孔径编程；`tgt_falcon_bringup (0xaa1)`；`chipid_gate (0x6a71)`；描述符验证；`regtable_reverse_lookup (0xd66)`；`tlb_scan_invalidate (0x14cf)`；调用 `booter_load_wpr_main (0x22ba)` 的 `booter_load_wrap (0x8137)`；finalize 提交 `(0x1c0e)`；`report_status (0x1d0f)`；成功后执行 `secure_teardown (0x7e76)`。

在 MAIN.2 中，紧随 `watchdog_set` 之后，Booter Load 会在 **CSB** 空间写入四个固定的权限级别掩码和孔径值：

```asm
I[0x12000] = 0x11111101
I[0x12400] = 0x00000111
I[0x12600] = 0x11111111
I[0x12100] = 0x00011100
```

每次写入后都有内联的 fail-closed 断言。四次写入中的任何一次发生 CSB 错误，都会让 Falcon 进入无限自分支并永久卡死。

`chipid_gate` 读取寄存器 `0xa00` 的位 [28:20]，只接受芯片 ID `0x170` 和 `0x171`。跳线值为 `0x170` 时无条件通过；值为 `0x171` 时，还必须设置寄存器 `0x10200` 的位 20，否则返回错误 `0x4b`。CMP 170HX 在 BAR0 `0x00000000` 处读取 `PMC_BOOT_0` 得到 `0x170000a1`，因此实现 ID `0x170` 能够通过。见[GA100 硅片](../hardware/ga100-silicon.md)。

`main` 的尾部准确如下：

```asm
0x80fe:  r9 = sp+8 = 0xFFEC          ; DMEM
0x8101:  r10 = D[0xFFEC]
0x8103:  lcall 0x1c0e                ; finalize / set_1180f8_top_nibble
0x8107:  if r0 != 0 skip
0x810b:  r0 = r10 = D[0xFFEC]
0x810d:  mov r10, r0
0x810f:  lcall 0x1d0f                ; report_status -> MAILBOX0 = r0
0x8113:  if r0 == 0 -> 0x8119
0x8117:  exit                        ; 原始 HS 停机
0x8119:  lcall 0x7e76                ; secure_teardown
```

**DMEM `0xFFEC` 是退出状态的输入槽，也决定是否执行 teardown。** 一次硬件 A/B 实验排除了另一种 `0xFFE4` 假设，并与已发表的 ROP v3 注释 "FFEC 00000000 <- Return value to main() to indicate success ($r0)" 相符。将 `D[0xFFEC]` 设为 `0xDEADBEEF` 后，`0x001180f8` 从 `0x11000000` 变为 `0xf1000000`，正好符合 `(r0 << 28)` 模型的预测。

### 7.3 booter 实际为 GPU 做什么

除了 GSP 移交之外，booter 还承担两项重要工作：

- **显存时钟与时序编程。** `memcfg_program (0x79cc)` 读取 BAR0 `0x20414`、`0x136658`、`0x136e58` 和 `0x136458`，打包提取出的位字段，再写入 `0x11824c` 和 `0x118250`。只有 `0x11824c` 的位 0 已设置时，`memcfg_apply_poll (0x7a64)` 才会运行；它以 100000 为超时上限轮询 `0x136600`、`0x136e00` 和 `0x136400`，失败返回 `0xa6`。`memcfg_timing_program (0x7c65)` 使用由 `0x137178` 和 `0x136604` 推导出的基常量 `0x32a`，计算缩放后的时序和带宽值，超时上限为 125000，错误为 `0xa7`。`const_out_write (0x797a)` 则提供固定常量 `0x68`、`0x555`、`0x5be` 和 `0x5a0`。
- **拉起目标 Falcon。** `tgt_falcon_init_reset (0x9da)` 写入 `0x3f0c = 0xa0100`，再把 `0xfeed0000` 与索引 OR 后得到的八个字填入 `0x3f40` 处的寄存器组，最后写 `0x3f00 = 3` 和 `0x104 = 1`。`mailbox_write_d000 (0xb28)` 轮询 `0xd000` 的位 `0x1c0000`，将数据写到 `0xd200`、命令写到 `0xd100`。`tgt_falcon_handshake (0xbc9)` 验证 `0xbadf0000` 哨兵和 `0x3f20`..`0x3f40` 范围，失败时返回 `0x38`。

`booter_load_wpr_main` 的 finalize 尾部会启动交给 GSP RISC-V 的移交：在 `0x286a`，booter 通过 `0x1b44` 设置 `SECURE_SCRATCH_14`（`0x001180f8`）的位 24；随后 `0x2874` 调用 `reg_init (0x68ed)`，写入 GSP `FBIF_CTL 0x00110624 = 0x90`（ALLOW_PHYS_NO_CTX 位 7 加位 4）、`0x00110684 = 1` 和 `0x0011126c = 1`。任何要把控制权交给 GSP-RM 的链，都必须让这三次写入实际发生或自行重现。`0x110684` 和 `0x11126c` 的字段名仍是推断，尚未用头文件确认。

---

## 8. DMEM 图

本节所有地址均属于 **DMEM**。`0x100` 以下完全没有分配内容，因此可以排除“在低位 DMEM 中 staged 的 mega-ROP”这一方案。

| DMEM | 内容 | 备注 |
|---|---|---|
| `0x0000`-`0x00FF` | 未分配 | |
| `0x0200` | booter 自身的 HS 签名 | 加载前写入映像（`hsSigDmemAddr = patchLoc - dataOffset`，`0x8900 - 0x8700`）。**不是**发生溢出的缓冲区。 |
| `0x0530` | DMA/引擎配置描述符结构 | |
| `0x0600`-`0x06FF` | `WprMeta`，256 字节结构 | +0 处为魔数 `0x371a60b3`，+4 处为 `0xdc3aae21`。它位于 DMA 目标下方，因此溢出不会触及。 |
| `0x0700` | 映像描述符 | `ls_sig_verify` 要求 `r10 == 0x700` |
| **`0x0800`** | **GSP-RM LS 签名缓冲区** | **DMA 目标，也是利用入口。** |
| `0x103c` 起 | 密码会话描述符 | 字段 `0x1004`、`0x107c`、`0x1080`、`0x1100` |
| `0x1900` | `f100` 字段保存槽 | 发布版载荷会在这里写入 `0x00000007` |
| `0x1904` / `0x190c` / `0x1914` | `va_to_pa_walk` 的 PTE 缓存 | |
| `0x1a00` / `0x2a00` / `0x3a00` | 页缓冲 | |
| `0x2383` | 寄存器描述符表 | 会被 `0xF800` 载荷破坏，也是错误 `0x35` 的来源 |
| `0x5f00` | 固件请求头 | `'FREE'` / `'HEAP'` 魔数 |
| `0x6330`-`0x633F` | 阶段 9 扫描的临时区 | |
| **`0x6340`** | **栈金丝雀守卫全局变量** | 十进制值 25408 |
| `0x8700` | booter 代码/数据的末尾 | |
| `0x8e08` | 寄存器描述符表 | 也被粉碎 |
| 约 `0xFF3C`-`0xFFFF` | 当前调用栈 | 从地址空间顶部向下增长 |

### 栈金丝雀

每次启动都会由硬件 RNG 生成新随机值，并存入 DMEM `0x6340` 的全局变量。每个受保护函数都会把它复制到栈帧边界，退出时重新读取并比较；不匹配就调用 `0x7dd9` 的 `panic()`。标准序言是 `mov $rX 0x6340; ld b32 $r9 D[$rX]`，尾声是 `cmp b32 $r15 $r9; bra e <ok>; lcall 0x7dd9`。

由于该值每次启动都会由硬件 RNG 重新生成，离线猜测并不可行，但利用也不需要猜测。守卫全局位于可写数据内存中，而检测它的溢出恰好可以到达那里；载荷只需用同一个选定值覆盖全局变量**以及**所有重建的金丝雀槽，所有尾声比较就都会通过。这正是论文的 Thesis 1：Falcon 栈金丝雀失败的不是熵，而是*引用字完整性*。在该映像中，工具链把守卫放在只读数据段末尾；但在扁平 MPU 映射下，它落入了可写数据范围。这里没有 RELRO 等效机制、没有守卫页，也没有 MPU 只读映射。

---

## 9. BAR0 master、CSB 纪律和邮箱

### 9.1 BAR0 master

Falcon 只能通过 Falcon CSB 空间中一个间接且由互斥锁门控的邮箱访问外部 BAR0 寄存器，不存在内存映射的 "direct" 路径。

| CSB 端口 | 角色 |
|---|---|
| `I[0x1c100]` | 目标 PRI 地址（完整 32 位） |
| `I[0x1c200]` | 数据。对读而言，结果回到这里。 |
| `I[0x1c000]` | 命令：**`0x800000f2` = 写，`0x800000f1` = 读** |
| `I[0x1c300]` | 看门狗，被 `watchdog_set (0x1034)` 用 `0x1312d00`（20,000,000）播种 |

booter 自己也通过这条路径工作：`0x29b8 -> 0x10aa` 用于写 WPR2 寄存器，finalize 例程对 `0x001180f8` 的写入在指令层面就是 `1c4b: r10=0x1180f8 ; lcall 0x10aa`；对应的读取则是 `1c35: r10=0x1180f8 ; lcall 0x1196`。

### 9.2 Fail-closed CSB 访问

**booter 中的每次 CSB 访问都是 fail-closed。** 每次访问后，代码都会读取 CSB 错误状态 `I[0x9100]` 的位 31，也就是 `FALCON_CSBERRSTAT.VALID`。它是表示“上一次 CSB 访问出错”的**故障标志**，**不是**忙状态或完成状态轮询。原始内联序言在出错时跳转回自身，让 Falcon 永久卡死；两个辅助函数则报告状态 `0x15` 后退出。

```asm
mov  rX 0x9100
iords
shr  0x1f
bra
self-lbra
```

这种惯用的内联序列出现约 25 次，此外还出现在两个辅助函数中。`csb_read (0x8264)` 还会用 `0xffff0000` 掩码处理返回值，检查 PRI 毒哨兵 `0xbadf0000`，使用白名单（`0x208c` 处的 `reg_whitelist_40f00`，覆盖 `[0x40f00, 0x41f00)`，步长 `0x100`），并为寄存器 `0x1c200`、`0xc00`、`0xb00` 和 `0xd500` 提供重试路径。

### 9.3 MAILBOX0 语义

Falcon I/O `0x1000` 是 Falcon 自己的 MAILBOX0；主机通过 BAR0 `0x00840040` 看到它，MAILBOX1 位于 `0x00840044`（`CSB 0x1000 / 64 = falcon 0x40`）。主机在 PL0 直接读取 BAR0 `0x1000` 会得到 `0xbadf5040`，这解释了一个长期存在的地址混淆。

利用期间唯一可观察的通道是 MAILBOX0，核心规则如下：

> [!NOTE]
> **凡是经过 `report_status` 返回的路径，MAILBOX0 都等于 `$r0`**
>
> 读到 MAILBOX0 为 `0x31`，只能说明 `report_status` 尚未执行。booter 会在 ucode 偏移 `0x7a` 处先写入 `0x31`（`mov $r15 0x31 / mov $r9 0x1000 / iowrs I[$r9] $r15`），把它作为第一个存活标记；这一写入会覆盖驱动预先放入的 WprMeta 物理地址参数。

实测结果是：返回到 `0x8117`（原始退出，跳过 `report_status`）时 MB0 为 `0x31`；从 `0x810d` 返回时，`r0 = 0` 得到 MB0 `0x0`，预先写入 `0xcafe` 则得到 `0xcafe`；`0x8d4` 返回 `0x0b`。

实际排查时可按如下方式分类：`0x47` 表示栈金丝雀检查失败，Falcon 正在 `panic()` 自循环中；`0x31` 表示 `report_status` 没有运行；`0x96` 表示金丝雀完整且引导正常。

### 9.4 状态码

| 码 | 来源 | 含义 |
|---|---|---|
| `0x01` | `antirollback_version 0x59c4` | 已存储版本高于候选版本 |
| `0x05` | `wpr_region_check 0x28ac` / `wpr_region_program 0x291e` | WPR 上限 < 基址，或空区域 |
| `0x11` | `pka_ready_check 0x580f` / `pka_status_check 0x5473` | |
| `0x15` | `csb_read` / `csb_write` / `mailbox_wait_ready` / `reg_read_indirect` | CSB/PRI 访问出错 |
| `0x1c` | 通用 | 参数无效 |
| `0x23` / `0x4e` | `verify_reg_bitlen` | |
| `0x29` | `check_1180f8_nibbles 0x1c75`（从 `0x80a5` 调用） | `0x001180f8` [31:28] 或 [23:20] 非零 |
| `0x2d` | `firmware_load_main` | |
| `0x31` | PC `0x7a` | 入口存活标记；尚未到达 `report_status` |
| `0x32` | `check_reg_4f00` | |
| `0x35` | `regtable_rw_indexed` | `0x2383`/`0x8E08` 处的 DMEM 描述符表读零 |
| `0x38` | `tgt_falcon_handshake 0xbc9` | |
| `0x47` | `__stack_chk_fail 0x7dd9` | 金丝雀不匹配，随后挂起 |
| `0x4b` | `chipid_gate 0x6a71` | 跳线 `0x171` 而无 `0x10200` 位 20 |
| `0x54` | 未知 | 目前只在 PG199 板上观察到。见下文。 |
| `0x59` | 驱动侧 | 找不到 `dmem.bin`，属于无害情况。 |
| `0x5c` | `antirollback_version` | 孔径检查 |
| `0x62` | PKA 路径 | |
| `0x63`-`0x6d` | `pka_modexp_run 0x54ab` | `0x6c` = 超时 |
| `0x6e` | `check_10200_820434` | |
| `0x74` | `check_reg_118128` | |
| `0x88` | `check_1180f8_2724 0x1ba3` | `0x001180f8[27:24]` 非零 |
| `0x89`-`0x90` | `wpr_desc_validate 0x154a` | `0x8e`/`0x8f` 对应 `0x1ffff` 对齐检查和 `0xfff` 字段检查 |
| `0x96` | 正常 | 金丝雀完整，引导成功 |
| `0x98` | `ls_sig_verify 0x399a` / `booter_load_wpr_main` | |
| `0x9c` / `0xa4` | `booter_load_wpr_main` | |
| `0x9e` | `range_validate_windows` | |
| `0x9f` | `hw_state_gate`、`dma_region_lock_setup` | |
| `0xa5` | `firmware_load_main` | |
| `0xa6` / `0xa7` | memcfg 路径 | |

作为对照，主机侧错误码是 `NV_ERR_TIMEOUT = 0x00000065`、`NV_ERR_MEMORY_ERROR = 0x72` 和 `NV_ERR_GENERIC = 0xffff`。实际观察到的复合 `RmInitAdapter` 失败包括 `0x62:0x40:2028`、`0x62:0x55` 以及 `0x62:0x65:2674`。

> [!NOTE]
> **未解问题：Booter 状态码 `0x54`**
>
> 在一块 PG199 板上使用修改版 cmpunlocker 时，流程失败于 `s_executeBooterUcode_TU102: Booter failed 0x54`，但 CFG1 和 LMR 写入已经生效，PLM 也已打开。其他每个状态码都能通过在反汇编中定位其写入位置来确定；同样的方法应该也能解出 `0x54`，而且所需反汇编已经具备。

---

## 10. 离开重度安全模式，以及复位 PLM

IMEM `0x7e76` 的 `secure_teardown` 是设计好的退出路径。它重新启用 `0x10100` DMA 孔径（OR `0x101`，等待位 `0x100` 清零，最多循环 `0x400` 次），设置 `$cauth |= 0x80000`（位 19，在停机前屏蔽中断和异常），随后对 `$c0`..`$c7` 逐一执行 `csecret $cN 0x0` 和 `cxor $cN $cN`。接着以 `r14 = 0` 从 0 循环到 `0x10000`，执行 `st b32 D[$r9] $r14; add $r9 0x4`，清空 `r0`..`r15`，最后执行原始 `exit` 操作码（`f8 02`）。它不会返回；正是这个 `exit` 让 Falcon 离开 HS 模式，从而可以加载新代码。

从 `main` 进入该路径，必须在 `0x8113` 处满足 `r0 == 0` 并分支到 `0x8119`。如果 `r0` 非零，就会走 `0x8117 exit`，完全跳过 teardown。

**错误路径始终先调用 `report_status (0x1d0f)`，再调用 `secure_teardown (0x7e76)`**：这两次调用分别成对出现在 `0x873`/`0x877`、`0x88a`/`0x88e` 和 `0x8a7`/`0x8ab`。成功路径反而不会调用其中任何一个，以便为 GSP 移交保留完整的密码状态和运行环境。因此流传的 "mailbox XOR teardown" 说法不对，错误路径会执行两者。

### 复位 PLM，`0x008403C4`

SEC2 的复位源 PLM 控制着 `+0x3c0` 处 SEC2 `FALCON_ENGINE` 的复位控制。复位动作完成后留下的值，决定 SEC2 是否还能再次复位。

| 值 | 含义 |
|---|---|
| `0xff` | 完全开放。对应干净闲置、SBR 之后或 SEC2 尚未使用的状态；主机 PL0 的 `kflcnReset` 可以执行。 |
| `0xdf` | 出厂驱动完成 GSP 引导 teardown 后留下的正常工作状态，仍允许复位。 |
| `0xcf` | 驱动准备重新锁定 PLM（清除位 4）后观察到的状态。 |
| `0x8f` | HS 退出污染状态。低半字节 `0xf` 表示所有级别可读，高半字节 `0x8` 表示写入锁定到安全源，因此 PL0 的复位写入会被拒绝。 |

规则是：`reset_allowed = resetPLM in {0xff, 0xdf}`，并且 `0xdf = 0x8f | 0x50`。

重要的是，`0x8f` 是在 **HS 转 NS 的退出转换期间由硬件锁存**的，并不是任何 booter 指令写入的结果：静态分析在 booter 中找不到对 `0x8403C4` 的指令引用。离开 HS 后，硬件会把所有由 HS 门控的 PLM 重新保护为安全默认值。实测表明，在 `0x8117` 执行原始退出会留下 resetPLM `0xff`；让 `secure_teardown` 跑完则会将其重新锁存为 `0x8f`。

> [!NOTE]
> **未解问题：`resetPLM = 0x8f` 是否会阻止加载新的 SEC2 ucode？**
>
> 一份报告称 SEC2 在 `0x8f` 状态下仍可重新加载（Hello World 能运行，MAILBOX0 从 `0x0` 变为 `0x31`）；另一份报告则称加载新 ucode 需要 SFTRESET，但 SFTRESET 又受复位 PLM 门控，并出现 `NS load mismatch (HS-locked, needs --flr)`。一种可能的解释是 NS 重载有效，而 HS 签名重载无效，但至今没有定论。可以进行受控实验验证：在已知 `0x8f` 状态下连续加载一个 NS ucode 和一个 HS 签名 ucode，分别记录 `CPUCTL` 和加载器错误字符串。

发布版驱动完全绕过了这套纪律：它**从不读取或写入 `0x008403C4`**。对发布仓库 grep `0x008403c4`、`0x001180f8`、`0x001fa81c` 或 `0x001fa820`，得到的引用数为零。驱动内部路径改用自己的 `kflcnReset`/FWSEC 序列重新发射 Booter Load；补丁 `0002` 通过记录 `SEC2_DEBUG: kflcnReset for FWSEC: 0x%x` 和 `SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x` 证实了这一点。

---

## 11. 签名缓冲区

这是整个解锁机制围绕的核心对象。

| 属性 | 出厂 | 解锁下 |
|---|---|---|
| 分配 | `NV_ALIGN_UP(pGspFw->signatureSize, 256)`；观察到 4,096 字节 | `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL` = 63,488 字节 |
| 对齐 | 256 字节，`ADDR_SYSMEM` | 256 字节，`ADDR_SYSMEM` |
| DMEM 目的地 | `0x0800` | `0x0800` |
| DMEM 触及范围 | `0x17FF` | `0xFFFF`，恰好 DMEM 顶部 |
| 长度来源 | `WprMeta.sizeOfSignature` | `WprMeta.sizeOfSignature` |

booter 直接从 `WprMeta.sizeOfSignature` 读取复制长度，完全不做边界检查；而缓冲区内容和这个字段都由驱动控制。长度因此被放大了 15.5 倍。出厂签名的 DMA 只到达 DMEM `0x17FF`，所以正常引导能够保留 `0x2383` 和 `0x8E08` 处的寄存器描述符表。

DMA 目标 `0x800` 由 IMEM `0x37ad` 的 `mov $r10 0x800` 设置，随后在 `0x37b3` 调用 `lcall 0x4d4`。后续执行过程见[ROP 链](rop-chain.md)。

> [!NOTE]
> **两处地址并不矛盾**
>
> `kernel_gsp_booter.c:329` 计算 `pUcode->hsSigDmemAddr = patchLoc - pUcode->dataOffset`；代入 `patchLoc = 0x8900` 和 `dataOffset = 0x8700` 后，签名位于 DMEM `0x200`。这是 **booter 自身的 HS 签名**，在加载前被写入 booter 映像。DMEM `0x800` 则是 booter 从 sysmem DMA 下来的 **GSP-RM LS 签名**所在位置，真正发生溢出的是这个缓冲区。两者是不同的缓冲区。置信度为中等：该解释与所有观察一致，但没有资料明确如此表述。

还有一个性质关系到解锁能否持久工作：**显存几何布局改变后，出厂 AES-MAC 签名仍然有效**。这是因为签名覆盖的是静态 GSP 固件映像，而不是运行时 WPR 元数据或硬件几何布局；WPR 元数据由驱动在运行时计算。此前有过相反的说法，但作者已经明确撤回。

---

## 12. 已发布的驱动如何调用 Booter Load

本节内容全部直接取自发布版 `master` 中的 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 和 `0002-booter-verify.patch`。完整补丁集见[驱动补丁](driver-patches.md)。

### 12.1 门

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID  0x2082
```

`_kgspSec2PostblTimingEnabled()` 会将 `pGpu->idInfo.PCIDeviceID >> 16` 与这两个值精确比较。`install.sh` 也会 grep 到 `10de:20b0`，但该卡只能完成安装，不会解锁。目标驱动版本是 `610.43.03`（默认）和 `610.43.02`；使用其他版本构建会直接失败。

### 12.2 按顺序的序列

1. **`_kgspCreateSignatureMemdesc`** 将签名 memdesc 分配为 `0x0000f800`，而不是 `NV_ALIGN_UP(pGspFw->signatureSize, 256)`。在复用这块内存之前，先把出厂签名字节复制到 `pKernelGsp->pStockSignatureData` / `stockSignatureSize`，这两个字段是添加到 `g_kernel_gsp_nvoc.h` 中 `KernelGsp` 的新字段。日志 `SEC2_DEBUG: saved stock signature (%llu bytes)` 会记录保存结果，实卡上报告为 4096。
2. **可选外部载荷。** `os_open_and_read_file()` 会尝试把 `SEC2_POSTBL_TIMING_DMEM_PATH = "/lib/firmware/nvidia/ga100/gsp/dmem.bin"` 读入新缓冲区。读取成功时记录 `SEC2_DEBUG: loaded %llu bytes from %s`；文件不存在时记录带 `0x59` 的 `SEC2_DEBUG: %s not found (0x%x), using built-in payload`，并回退到内置载荷，该载荷预先设置 `writeAddr = 0x009a0148`、`writeValue = 0xffffffff`。无论哪条路径都会调用 `memdescFlushCpuCaches()`。
3. **保存 WPR2。** 分别读取一次 `0x001fa824`（低位）和 `0x001fa828`（高位），并记录 `SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x`。
4. **PLM 循环。** 对表中的四个条目逐一处理，每个条目最多尝试两次：

    ```c
    for (plmIdx = 0; plmIdx < 4; plmIdx++)
        for (attempt = 0; attempt < 2 && !opened; attempt++) {
            GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
            GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
            kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
                                              plmTable[plmIdx].addr,
                                              plmTable[plmIdx].value);
            kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
                memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
            regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
            opened = (regVal == plmTable[plmIdx].value);
        }
    ```

    失败时记录 `SEC2_DEBUG: FAILED to open <name> after 2 attempts`。表项及其精确值见[权限级别掩码](privilege-level-masks.md)。

5. **循环结束后再次恢复 WPR2。**
6. **在 PL0 执行四次普通主机写入**，不再需要利用：`0x0082381c = 0x88888888`（SS0）、`0x00823820 = 0x00000008`（SS1）、`0x009a0204 = cfg1Value` 和 `0x00100ce0 = lmrValue`。随后记录 `SEC2_DEBUG: POST-WRITE SS0=… SS1=… CFG1=… LMR=…`。见[算力节流](compute-throttle.md)和[显存几何布局](memory-geometry.md)。
7. **`kgspSec2PostblTimingRebuildStockSignature()`** 释放并销毁 `0xf800` memdesc，使用 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 在 `NV_ALIGN_UP(stockSignatureSize, 256)` 处分配替代 memdesc，将 `pStockSignatureData` 复制回去，并重新设置 `pWprMeta->sysmemAddrOfSignature` / `sizeOfSignature`。失败时以 `SEC2_DEBUG: rebuild stock signature failed: 0x%x` 中止引导。
8. **第二次运行 `kgspPopulateWprMeta_HAL`**，使 WPR 元数据反映扩大的 FB。实卡 dmesg 会显示 `WPR meta updated fbSize=0x0000001000000000 …`，紧接着出现 `normal BooterLoad status=0x0`。

这解释了 GSP-RM 为什么能在*同一次*驱动加载中正常启动：利用过程和真实引导在同一次加载中按顺序完成，不需要等价于冷启动的额外交接。

### 12.3 重新填充辅助函数

`kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp, writeAddr, writeValue)` 用 `memdescMapInternal(..., TRANSFER_FLAGS_NONE)` 映射 memdesc，为那一个 `(writeAddr, writeValue)` 对重写整个 `0xf800` 字节载荷，取消映射，对签名 memdesc 调用 `memdescFlushCpuCaches()`，重新发布 `pWprMeta->sysmemAddrOfSignature = memdescGetPhysAddr(...)` 和 `pWprMeta->sizeOfSignature = memdescGetSize(...)`，然后对 `pWprMetaDescriptor` 刷新 CPU 缓存。memdesc 为 NULL 时返回 `NV_ERR_INVALID_STATE`，映射失败时返回 `NV_ERR_INSUFFICIENT_RESOURCES`。把签名长度 `0xf800` 交给 booter **就是**溢出。

缓存刷新不是可选步骤。签名 DMA 是非一致性的；不显式刷新时，Falcon 可能读取到过期的 RAM 内容。

### 12.4 补丁做的两个通融

- **WPR2 已 up。** 致命路径

    ```c
    NV_PRINTF(LEVEL_ERROR, "unexpected WPR2 already up, cannot proceed with booting GSP\n");
    return NV_ERR_INVALID_STATE;
    ```

    变成 `NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n")`。重复的 booter 发射会让 WPR2 保持 up，每次发射都会重新划分它。空/INIT 状态是 LO `0x0fffffff`、HI `0`，而 **HI = 0 会让 `kgspIsWpr2Up()` 返回 false**。已发布的驱动恢复*保存的*那一对，而非写一个空区域。

- **`0002-booter-verify.patch`** 把 `kgspBootstrap_TU102` 里几处 `NV_ASSERT_OK_OR_RETURN` 站点转成记录的日志状态检查，并为设备 ID `0x20C2` / `0x2082` 加一个 post-BooterLoad 五个寄存器的回读：

    ```c
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM        0x00823804
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED   0x0082381c
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820
    #define SEC2_DEBUG_PRI_FBPA_CFG1                   0x009a0204
    #define SEC2_DEBUG_PRI_MMU_LMR                     0x00100ce0
    ```

### 12.5 booter 运行多少次

| 情况 | Booter Load 发射 |
|---|---|
| 每个 PLM 首次尝试就打开 | 4 次利用发射 + 1 次正常引导 = **5** |
| 每个 PLM 都需要两次尝试 | 8 次利用发射 + 1 次正常引导 = **9** |

每次发射都会恰好执行**一次**任意 BAR0 写入。

### 12.6 读日志

> [!WARNING]
> **只有寄存器回读能够证明成功**
>
> 每次载荷执行都会记录 `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` 和 `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`，**但寄存器写入仍会生效**。在 `s_executeBooterUcode_TU102` 中，seccode 错误每次运行后都会留在 MAILBOX0；只要 `mailbox0 != 0`，函数就返回 `NV_ERR_GENERIC`（`0xffff`）。发布版循环用精确的寄存器回读相等作为成功条件，这才是正确判断。项目 README 也说明，早期 PLM 轮次出现的 `0x31` / `0xffff` 等 Booter 状态码，只要最终引导成功，通常并不表示失败。

见[验证](../procedures/verify.md) 和[排障](../procedures/troubleshooting.md)。

## 13. 无驱动调用，作对比

有一组独立的 Python 和 C 工具（从 `refire_chain_v2.py` 到 `v9.py`，以及 `load_gsp_sec2_falcon.c`、`load_custom_bin.py`）可以在没有 NVIDIA 驱动的情况下发射 booter。它们**不属于**发布仓库；把这两套代码库分开后，本领域看似的大多数矛盾都会消失。这些工具仍然重要，因为大部分寄存器操作纪律都是从中摸索出来的。见[工具谱系](../history/tool-lineage.md)。

在 SEC2 上运行 NS 代码很直接，除了公开文档不需要其他条件：将二进制 DMA 到 IMEM，设置 `BOOTVEC`，发出 `STARTCPU`；如果代码会执行 `exit`，再轮询 `CPUCTL` 的位 4（HALTED）。完整的无驱动引导顺序是：复位引擎，等待 DMA 清理，设置 `ALLOW_PHYS_NO_CTX` 和物理 DMA 孔径，DMA 写入 IMEM + DMEM，设置 `BOOTVEC`，设置邮箱，发出 `STARTCPU`，最后轮询 HALTED。

实际实现且能够工作的复位序列如下：

```text
if SCTL (SEC2+0x240) 有 HSMODE（位 1）置位：
    写 SFTRESET (SEC2+0x07c) = 1 并回读
pulse ENGINE (SEC2+0x3c0)：1 然后 0
轮询 DMACTL (SEC2+0x10c) 直到清理位 0x6 清除，忽略 0xffffffff 读
轮询 SCP_P2PRX (SEC2+0x530) 位 3，带 KFUSE_CTL (SEC2+0x11ec) 位 0 置位、位 1 清除
把 AUTH_EN（1 << 14）OR 进 SCTL
```

默认超时为 10.0 s，失败路径报告 "scrub timeout"。随后加载 Booter：使用带自动递增的 IMEMC/IMEMD，并为每个 256 字节 IMEM 块设置标签，在 HS 区域设置 SECURE 位 `1 << 28`。孔径会被强制为物理模式：在 `0x00840600`/`0x604`/`0x608` 写入 `FBIF_TRANSCFG[0..2] = 4, 5, 6`，再在 `0x00840624` 执行 `FBIF_CTL |= 0x80`，最后调用 `start_wait`；此时 MAILBOX0/1 已设置为 WprMeta 物理地址的低、高半部。

一个独立 C 程序曾在真实硬件上执行完整的九步无驱动引导，并从 `FALCON_MAILBOX0` 读到停机返回值 `0xb`。这证明即使没有 NVIDIA 驱动，加载路径也能工作，尽管 Falcon 最终以非零状态停机。

无驱动路径还发现了两个额外要求，发布版驱动分别通过其他手段满足：

- **缓存刷新。** 一个 17 字节、JIT 组装的 x86-64 桩（`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`，即 `clflush [rdi]` / `add rdi,64` / `sub rsi,64` / `jg` / `mfence` / `ret`）被映射为 `PROT_EXEC`，并对载荷、radix3 和 WprMeta 缓冲区执行，范围向上取整到 64 字节缓存行。`refire_chain_v6.py` 使用 `MAP_HUGETLB`（`0x40000`）分配 2 MiB 巨页并锁定，再检查存在位，根据 `(entry & ((1<<55)-1)) * 4096` 从 `/proc/self/pagemap` 解析物理地址。
- **最小 radix3 页表。** `stage_radix3()` 分配 `0x6000` 字节并写入三个 64 位描述符：PDE2 从 `0x0000` 指向 `phys+0x1000`，PDE1 从 `0x1000` 指向 `phys+0x2000`，PDE0 从 `0x2000` 指向 `phys+0x3000`；数据页和 bootloader 主体保持清零，随后执行刷新。没有它，booter 在签名前执行的 DMA 会以原因 `0x9` 失败。WprMeta 模板大小为 256 字节，取自一次真实的 10 GB 引导捕获，只覆盖 radix3 指针（`+0x10`）、radix3 大小（`+0x18`）、bootloader 指针（`+0x20`）、bootloader 大小（`+0x28`）、签名指针（`+0x48`）和签名大小（`+0x50`，设为 `0xF800`）。

还要注意，两条路径的邮箱语义不同：独立加载器以 5 s 超时轮询 HALTED，然后读取 `0x840040`，预期得到 `0x31` / `0x96` / `0x47`；驱动内部路径则无论实际结果如何都报告 `0xffff`。

---

## 14. 本页的开放问题

> [!NOTE]
> **无驱动发射能否交给出厂驱动继续处理？**
>
> 出厂驱动通过经典的两次加载 "mutex horns" 拒绝发射之后的 SEC2 状态：`0x31`（互斥锁仍持有）、`0x62`（WPR2 已启动）和 `0x29`（`0x001180f8` 错误，因为 `mutexfree` 终止符留下 `0xf0000000`，顶半字节 `0xf` 触发检查）。即使几何布局一致，在 10 GB 卡上也会失败，这说明发射改变的是 SEC2 / `0x001180f8` 的移交状态，而不是几何布局或写入次数。曾提出两种修复：让终止符保留 `0x001180f8` 的顶半字节为零，或者从打过补丁的驱动内部逐阶段完成几何布局。**发布版解锁器选择了后者。**

> [!NOTE]
> **不经过 FLR 越过 RmInitDone 这堵墙**
>
> `whole_stack_rejoin` 终止符会在利用后不经 FLR 重启 SEC2，让 booter 完成并启动 GSP-RM RISC-V 核心，但 init 永远不会完成。这就是同一堵 `0x65` 引导墙。`0x001180f8` 是 `NV_PGC6_BSI_SECURE_SCRATCH_14`，其位 26 为 `BOOT_STAGE_3_HANDOFF`（INIT = 0，DONE = 1），只有 HS 中的 SEC2 能设置它。预先写入 DONE 没有帮助：读取路径受 PLM 影响，`0x001180f8` 回读为 `0xdead5ec1`；而带毒值的读取会让位 26 看起来已经为 1，制造假 DONE，最终反而导致 GSP-RM 失败。候选根本修复有两个：保留 booter 的成功路径，让 SEC2 启动自身 RTOS 并自行设置 DONE；或者恢复 AON `SECURE_SCRATCH` 的 PLM/priv 状态，而目前只有功率域复位能做到后者。

> [!NOTE]
> **移植到其他 CMP 卡**
>
> CMP 50HX 使用 TU102，显存访问控制寄存器完全不同。CMP 90HX 是带 10 GB GDDR6X、没有额外物理显存的 GA102，因此只有算力解锁对它有意义。现有规则认为，同一套 Turing booter、脚本和利用适用于所有 SEC2 接受 Turing 代 AES 与 RSA 密钥的显卡。一名测试者报告，TU10x `booter_load` 能在 GA102 CMP 90HX 上加载，SS0/SS1 PLM 写入也成功，但同时承认写入的值 "were not right"（不正确），并警告一次阳性结果不足以证明兼容。另一份针对 GA102 booter 的独立静态分析认为，长度经过严格验证，因此不存在溢出点。决定性测试仍未进行：在 GA102 上加载 TU10x booter，并尝试一次已知可行、带回读验证的单 PLM 写入。

> [!NOTE]
> **Windows 及非 Linux 系统**
>
> 漏洞存在于 GPU 固件中，与 OS 无关。当前实现面向 Linux；Unix 主机或开源驱动也不是硬性要求，但资料认为 Windows 移植远不止修改几行代码。

> [!NOTE]
> **恢复某个 `csecret`**
>
> 三个索引对应三种能力：`secret(6)` 用于解密 ECB 固件块（可得到 121.7 KB 明文固件及 Booter 代码）；`secret(2)` 用于伪造内容 MAC（也是通过该路径进行 CFG1 显存解锁和 PCIe 速度解锁的前提）；`secret(0)` 是调试绕过，可启用带 `SKIP_VBIOS_SIG` 的 HULK 证书。**目前没有任何 csecret 被恢复。** 三者仍是需要电压毛刺硬件的差分故障分析目标。没有 **Booter 解密密钥**，就无法重建加密 booter，只能通过调试密钥路径读取；没有 **VBIOS 调试密钥**，就不能重新签名 VBIOS 或以调试模式运行。当前解锁通过复用出厂签名 booter 作为执行引擎，绕过了这两项需求。

> [!NOTE]
> **同一 bug 类的另一个实例**
>
> 论文（第 5.5 节）指出，GSP-RM 自身的驻留块还包含同一 bug 类的第二个实例，其中守卫全局是**公开的硬编码常量**，而不是由 RNG 播种。该实例没有公开地址，也没有据此构建利用，资料中无人验证过它。

### 已记录的否定结果

- **`envytools` 无法为上述内容提供佐证。** 它的 Falcon 密码页面列出了 Introduction、IO registers、Interrupts、"Submitting crypto commands: ccmd"、"Code authentication control" 和 "Crypto xfer control"，但**每个标题都标记为 "Todo: write me"**。其中没有 AES 引擎、密钥处理、签名代码认证、安全模式进入与退出、代码页签名检查或 CMAC/CBC-MAC 方案的文档。这里记录这一点，是为了避免重复搜索。envytools 对 Falcon 硬件的记录也只到 v5（GK208+），没有 Ampere 或 GA100 覆盖；其寄存器图（`UC_CTRL 0x100`、`UC_ENTRY 0x104`、`UC_CAPS 0x108`、`UC_STATUS 0x128`、`CODE_INDEX 0x180`、`CODE 0x184`、`DATA_INDEX[0-7] 0x1c0`、`SCRATCH0 0x040`）只能作为结构背景，**绝不能**用来验证 GA100 寄存器地址。
- **通过返回 IMEM `0x100` 的 `_start` 重新进入 booter**（连续提供两个签名）已经测试过，但邮箱仍以 `0x31` 失败。Falcon 进入 HS 模式时会擦除 `0x00` 处的轻度安全引导程序，因此没有可供返回的代码。
- **跳过 `secure_teardown` 以窃取活动 SCP 机密**在提出当天就被两条逐字节的对抗性静态追踪否定：`0x107`-`0x147` 的序言会立即将每个机密自 XOR 为零；真正使用密钥的是 `0x1e20`-`0x1e70` 的 AES 验证；`0x1e74`-`0x206e` 的清理扫描连续执行三次自清零；最后一条密码操作是 `0x206e` 的 `cxor $c0, $c0`。从 `0x2070` 到 `0x7eef` **没有**密码操作，劫持点（`0x37b3` 的 `lcall 0x4d4`）正好处于这段密码静默区间。跳过 teardown 并不能保留任何东西，因为寄存器组早在约 0x1500 字节之前就已清空。
- **通过逆向 booter 获得 HS 签名权限**已被提出者自己放弃。即使从晶片提取 AES 密钥，RSA 私钥仍然缺失，因为晶片只保存公钥。理论上的剩余路线是启用调试模式并使用调试 RSA 私钥，但量产卡上的物理熔丝禁用了调试模式，只有工程样品启用了它。
- **在主机侧将 PCI 设备 ID 欺骗为 A100 ID（`0x20b0`）**不可行：VBIOS/devinit 在驱动或 GSP 介入前就使用卡级设备 ID，且所有 GA100 卡甚至 Turing 卡使用的都是同一个 booter，因此下游没有按主机 ID 分支的逻辑。

---

## 相关页面

- [解锁如何工作，端到端](how-it-works.md)
- [ROP 链](rop-chain.md)
- [权限级别掩码](privilege-level-masks.md)
- [驱动补丁](driver-patches.md)
- [寄存器参考](register-reference.md) 和[寄存器索引](../appendix/register-index.md)
- [术语表](../start/glossary.md)
- [死路](../history/dead-ends.md)
