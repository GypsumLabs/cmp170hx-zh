# SEC2 Falcon 与 Booter Load 微码

**本页覆盖内容。** 整个 CMP 170HX 解锁运行其上的安全协处理器：SEC2 Falcon 是什么、"Booter Load" 微码做什么、重度安全模式如何进入和离开、booter 映像在两个地址空间内的内部布局、GSP 签名缓冲区位于何处，以及打过补丁的驱动究竟如何调用 booter。利用本身见[ROP 链](rop-chain.md)；它打开的掩码见[权限级别掩码](privilege-level-masks.md)。

**两句话的关键结果。** NVIDIA 自签名、AES 加密的 `booter_load` 微码被正常加载和认证，随后在认证*已经*成功之后，被一个由主机驱动控制的签名缓冲区破坏。全程没有伪造签名、没有提取密钥、也从不执行任何攻击者提供的指令：booter 摇身变成解锁的执行引擎，同时逐字节保持为 NVIDIA 发货的微码。

---

## 1. 为什么会有 Booter

GA100 晶片携带两个在这里相关的截然不同的处理器。

| 处理器 | 位置 | 核心 | 密码 | 角色 |
|---|---|---|---|---|
| SEC2 Falcon | BAR0 `0x00840000` | Falcon v4/v5，16 位哈佛 | AES + RSA + SCP 机密 | 安全协处理器。能解密和验证它自己的代码映像。 |
| GSP | BAR0 `0x00110000` / `0x00111000` | NVIDIA RISC-V（NVRISCV） | 无 | 运行 GSP-RM，资源管理器固件。 |

因为 GSP RISC-V 核心没有任何密码功能，它无法验证自己的映像，所以验证被委托给一个叫 *booter* 的 SEC2 Falcon 微码。存在两个 booter——`booter_load` 和 `booter_unload`；本页讲 `booter_load`。

booter **不是**[VBIOS](../hardware/vbios.md) 的一部分。它作为 `nvidia.ko` 里一个编译进 BINDATA 数组随驱动包发货，并且按版本区分，正如它验证的加密 GSP 固件一样。在驱动 610 里，GA100 数组是：

```text
kgspBinArchiveBooterLoadUcode_GA100_BINDATA_LABEL_IMAGE_DBG_data[]
  在 src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c
  DATA SIZE (bytes): 60160
  COMPRESSED SIZE (bytes): 34145
```

因此运行利用不需要单独的 booter 文件——驱动已经带着它。

解锁攻击的引导链，端到端是：上电时从 SPI 闪存加载 VBIOS、一颗晶片上 Falcon 验证 VBIOS、芯片进入安全模式、驱动提供 `gsp_tu10x.bin` 而其签名被 Falcon 检查、随后驱动用 GSP 客户端读取显存容量并暴露设备。解锁攻击第四步，即在 booter 要 DMA 的 GSP 签名缓冲区里植入一个载荷。

---

## 2. Falcon 安全模型

自 Maxwell 以来 Falcon 有三种执行模式。

| 模式 | 如何进入 | 它能做什么 |
|---|---|---|
| 非安全（NS） | 加载任何代码，设 BOOTVEC、STARTCPU | 唯一不需要 NVIDIA 签名微码就能到达的模式。被限制于许多寄存器和 DMA。 |
| 轻度安全（LS） | 只能从重度安全上下文（GM20x 及以后） | 介于 NS 和 HS 之间。 |
| 重度安全（HS） | 当 PC 落在一个标为安全的代码块上、MAC 比较成功后由硬件授予 | Falcon 变成黑盒：内部状态无法从外部读写。在 LEVEL2/L3 运行，能重写权限级别掩码并编程受保护区域。 |

项目的 "L0 到 L3" 权限级别词汇指的就是同一个模型。这些级别如何按寄存器被强制执行，见[权限级别掩码](privilege-level-masks.md)。

`booter_load` 永远不能在 NS 模式执行。它的主体是 AES 加密的，只能在 HS 模式的 Falcon 内被解密。Falcon 通过运行 0x100 字节明文 NS 前导、然后发出那条解密代码、验证它并切换到 HS 的特殊指令来进入 HS。这个后果是架构层面的，也是整个解锁被塑造成现在这个样子的原因：

> [!NOTE]
> **塑造一切的那条规则**
>
> 解锁里每次 HS 特权寄存器写都必须从被劫持的真实 booter 内部发出。自制微码做不到，因为自制微码无法被弄到在 HS 运行。

HS 进入例程（按为 Tegra TSEC 逆向、在 GA100 SEC2 上结构相同的推断）计算 `microcode_start = (*SEC & 0xFF) << 8` 和 `microcode_size = ((*SEC >> 24) & 0xFF) << 8`，把微码的 Davies-Meyer MAC 算进 `$c5`，然后运行：

```asm
csecret $c3, 0x1
ckeyreg $c3
cenc     $c3, $c7
ckeyreg  $c3
cenc     $c4, $c5
csigcmp  $c4, $c6
```

零的开始值或大小值会触发 `OP_SECURE_FAULT`。要认证必须满足四个条件：微码页必须映射在一个预先选择的虚拟地址、标为机密、该信息载入 `SEC` 寄存器，且密码寄存器 6 里有一个有效 MAC。

> [!WARNING]
> **两种不同的验证方案，不要混为一谈**
>
> 不可变引导 ROM 对 HS booter 映像的检查，在语料库里被描述为一次 RSA-3K 检查，而一个 384 字节签名块确实随映像在 `PATCH_LOC = 0x8900` 发货。另一条路径是，booter *自己*对它加载的 GSP 映像的验证，被追溯到 `_acrVerifySignature_TU10X` → `_acrCalculateDmhash_TU10X` → `_acrDeriveLsVerifKeyAndEncryptDmHash_TU10X` → `_acrMemcmp`，那是 Davies-Meyer 哈希加一次从一个 `csecret` 派生的 AES 密钥派生，该路径上没有 RSA。booter 确实含一个单独在别处使用的 PKA/modexp 块（`rsa_pubkey_load 0x4768`、`pka_modexp_run 0x54ab`）。对这条调和的置信度为中等：档案里没人用恰好这些术语陈述过它。

两种方案都没有被解锁破坏。

---

## 3. 哈佛架构：两个绝不能混用的地址空间

> [!CAUTION]
> **IMEM 地址和 DMEM 地址看起来一样，却不能互换**
>
> SEC2 Falcon 是一颗**哈佛架构**核心，有独立的 16 位指令内存（IMEM）和 16 位数据内存（DMEM）空间。作为 IMEM 地址的 `0x6340` 是毫无意义的代码；作为 DMEM 地址的 `0x6340` 是栈金丝雀守卫全局。几份流传的文档把两者混进单一 "memory map"，是错的。本维基上每个地址都被标注为 IMEM、DMEM、CSB（Falcon I/O）或 BAR0。

| 属性 | IMEM | DMEM |
|---|---|---|
| 大小 | `0x10000`（64 KB） | `0x10000`（64 KB） |
| Falcon 虚拟窗口 | `0x4000000`-`0x400FFFF` | `0x4010000`-`0x401FFFF` |
| 块对齐 | 256 字节（`FLCN_BLK_ALIGNMENT`） | 256 字节 |
| 利用碰什么 | 无 | `0x0800`-`0xFFFF` |

因为 GSP 签名缓冲区活在 DMEM 里，签名 DMA 只能粉碎 DMEM、永远无法写入 IMEM。这一单一事实正是利用是"对已签名映像的纯返回定向编程"而非代码注入的原因。它也意味着 DMEM 的 16 位空间本身无法寻址一个 32 位 BAR0 寄存器，所以载荷需要一个驱动 Falcon BAR0 master 的 gadget。

全篇还会出现另外两个空间：

- **CSB / Falcon I/O**，由 `iord` / `iowrs I[...]` 寻址。例如 `I[0x1000]` 是 MAILBOX0、`I[0x9100]` 是 `FALCON_CSBERRSTAT`、`I[0x1c000]`/`I[0x1c100]`/`I[0x1c200]` 是 BAR0 master。
- **BAR0 / PRI**，主机对特权寄存器接口的 32 位视角。主机、SEC2 和 GSP RISC-V 都经 PRI 通信；PLM 门控它的区域。

---

## 4. 从主机看到的 SEC2：BAR0 寄存器图

SEC2 位于 `NV_PSEC_BASE = 0x00840000`，是一颗 Falcon 核心而非 RISC-V（`HWCFG2` 位 10 读 0）。完整偏移量，由一台 GPU `10de:20c2` 上一个能工作的无驱动 C 加载器验证：

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
| `RESET_PRIV_LEVEL_MASK` | `+0x3c4` | `0x008403c4` | 复位 PLM。见第 9 节。 |
| `PRIVSTATE_PLM` | `+0x3d0` | `0x008403d0` | 仅具名，从未写测试过 |
| `SCP_CTL_P2PRX` | `+0x530` | `0x00840530` | 位3 SFK_LOADED |
| `KFUSE_LOAD_CTL` | `+0x11ec` | `0x008411ec` | 读它触发 SFK 加载 |

GSP 侧，作对比：`NV_FALCON2_GSP_BASE = 0x00111000`、`RISCV_STATUS 0x00111240`、`RISCV_CPUCTL 0x00111268`、GSP `MAILBOX0 0x00110040`、GSP FBIF 基址 `0x00110600`。

`EXCI` 解码为 `expc = ((exci >> 28) << 20) | (exci & 0xFFFFF)`、`excause = (exci >> 20) & 0x1F`，原因 `0x08` ILL_INS、`0x09` INV_INS、`0x0a` MISS_INS、`0x0b` DHIT_INS（IMEM 块存在但未经 BROM 认证）、`0x0d` SP_OVERFLOW、`0x0f` BRKPT_INS、`0x10` DMEM_MISS、`0x11` DMEM_DHIT、`0x12` DMEM_PAFAULT、`0x13` DMEM_PERM、`0x15` BROM_CALL、`0x16` KMEM_VIOLATION、`0x17` BMEM_PERM。

---

## 5. Booter Load 映像

### 5.1 文件布局

| 区域 | 偏移量 | 内容 |
|---|---|---|
| NS 引导程序 | `0x0000`-`0x0100` | 明文。256 字节。 |
| HS 代码 | `0x0100`-`0x8600` 或 `0x0100`-`0x8700`；**来源相差 256 字节** | AES-128-ECB 加密。 |
| 数据（`osData`） | 算术上是 `0x8700` 起；`0x8600` 也被引用 | 第 11 节的 `hsSigDmemAddr = patchLoc - dataOffset` 推导需要 `0x8700`（`0x8900 - 0x8700` = DMEM `0x200`），34,304 字节的安全代码测量也一样（`0x0100`-`0x8700` 是 34,304 字节；`0x0100`-`0x8600` 只有 34,048）。两条证据线指同一方向，所以 `0x8600` 是较弱的读数。对齐解密偏移量前对你自己的映像验证。 |
| 签名 | `0x8900`（`PATCH_LOC`） | 384 字节 |

未压缩代码大小是 `0x8700` = 34,560 字节。分析的调试签名构建的实测段大小为：34,304 字节安全代码、25,600 字节数据、256 字节非安全代码。原始提取的 GA100 文件被零填充到 60,100 字节；编译进的 BINDATA 块是 60,160 字节。

加密区域恰好从 `0x100` 开始（16 的倍数），那里第一条解密指令是：

```text
89 fc ff 00    mov $r9 0xfffc
```

### 5.2 密码破解

让明文反汇编无需任何泄露源码即可实现的发现：

> [!NOTE]
> **调试和量产 booter 映像包含完全相同的明文代码**
>
> 只有 AES 密钥不同。调试映像是用一把非机密的编号测试密钥加密的，所以量产 HS 代码可以通过解密调试映像被读取。底层密码学发现在 2026 年 5 月；它于 2026-07-01 被应用到 GA100。

实用标记：

| 量 | 值 |
|---|---|
| 调试密钥编号 | 37 |
| 那个密钥下尾部零填充的 AES-128-ECB 密文 | `717D1494 EACA317F F1061952 58B38377` |
| 反汇编器 | `envytools` / `envydis` |

如果上面那个 16 字节常量恰好出现在文件自己的零区域之前，说明调试块被正确提取且对齐正确；如果它用测试密钥工具解密回零，则解密无误。量产块显示不同的尾部模式。一个错过会花掉数小时的工作流细节：4 字节轮密钥必须按与人类可读形式**相反**的顺序喂给 AES/Rijndael 工具，因为密钥编号位于最后一轮密钥而非第一轮（置信度：中等；单条可操作指令，但它描述的工作流显然产生了正确输出）。

### 5.3 提取

提取是通过打补丁 NVIDIA 自己的 `extract-firmware-nouveau.py`、让它只产出 GA100 量产和调试 booter 完成的，解析 `kgspBinArchiveBooter{Load,Unload}Ucode_GA100_BINDATA_LABEL_IMAGE_{PROD,DBG}_data` 和匹配的 `..._SIG_{PROD,DBG}_data`。**GA100 的签名大小是每个签名 384 字节**，而 TU10x 只用 16，所以调用是 `booter('ga100','load',384,'prod')` 及其三个兄弟。所有非 GA100 芯片（tu102、tu116、ga102、ad102、gh100、gb100、gb202）都被从 `main()` 里注释掉。

第二个变体 `extract-firmware-nouveau-ga100-raw.py` 剥离所有容器结构（带 `0x10de` 魔数和 6 个 dword 的 `nvfw_bin_hdr`、带 9 个 dword 的 `nvfw_hs_header_v2`、签名块、`patch_loc` / `patch_sig` / `fuse_ver` / `engine_id` / `ucode_id` / `num_sigs` 和描述符），只把原始固件写到 `booter_{load,unload}_{prod,dbg}-<ver>_raw.bin`。这个原始布局喂给 envydis 和 objdump，是之后所有工具链的输入。

第二条提取路径可以从一个已加载的出厂驱动出发：用设了位 25 自动递增的 `IMEMC 0x840180` 和用于偏移量 `0`..`0x8700` 的 `IMEMD 0x840184` 读 SEC2 IMEM，用 `DMEMC 0x8401c0` / `DMEMD 0x8401c4` 读 DMEM，然后拼接 IMEM(NS+HS) + DMEM。

Booter 几何布局也可以**不用反汇编器**恢复，只需扫描原始映像的前 `0x100` 字节：`imm_before(ns, ff9f04)` 给出 NS 末尾、`imm_before(ns, fd9e04bb9002b69410)` 给出 DMEM 偏移量，其中 `imm_before` 要求标记前四个位置处的字节是 `0x89`（`mov $r9 imm24` 操作码），然后组装小端 24 位立即数。若任一标记缺失、或 `dmem <= base`，解析器会抛 "not an ACR booter image"。加载随后把 `img[0:ns]` 非安全地写到 IMEM 0、把 `img[ns:dmem]` 带置位的 SECURE 位 `1 << 28` 写到 `IMEM[ns]`、把 `img[dmem:]` 写到 DMEM 0。

### 5.4 版本可移植性

| 驱动分支 | GA100 `booter_load` | gadget 地址有效？ |
|---|---|---|
| 515 时代 | 不同的构建；金丝雀全局在 `0x2B20` 或 `0x2D20` | 否 |
| 580 到 610 | **逐位相同**（跨 580.173.02、580.159.04、580.159.03、610.43.02、595.84 验证） | 是 |

因此本维基上每个 ROP gadget 地址在整个 580-610 范围内都成立、无需重新推导。515 booter 是本项目之前被公开反汇编的那个，它不携带这个漏洞。

已发表论文的跨版本语料跨越分支 450、460、470、510（两个点发布）、515、525、535、560、570 和 580。510 SEC2 booter 的签名路径只用常量或钳制的 DMA 长度、没有按元数据大小的复制；580 booter 表现出无界复制；525 映像无法恢复，因为 booter 打包方式变了。

> [!NOTE]
> **未解问题：第一个受影响的分支**
>
> 溢出在 **510 中缺失**、在 **580 中存在**，分支 515 到 570 **无法确定**。要定论，需恢复并分析 515、535、560 和 570 的 GA100 booter，检查是否存在按元数据大小的复制。

### 5.5 谱系命名

GA100 使用 **Turing 代**固件：GSP 块是 `gsp_tu10x.bin`、SEC2 booter 是 Turing 谱系的 `booter_load`。这在 NVIDIA 自己的树 `nouveau/extract-firmware-nouveau.txt` 里有所陈述，并被失败路径上 TU102 后缀的 RM 符号佐证（`kgspBootstrap_TU102`、`s_executeBooterUcode_TU102`）。一次频道内更正后的正确命名：

| 前缀 | 覆盖 |
|---|---|
| `tu10x` | 全部 Turing |
| `ga100` | 仅 A100 和 CMP 170HX |
| `ga10x` | 其它 Ampere（GA102、RTX 3090、CMP 90HX） |

因为 170HX 加载 Turing `booter_load`，它继承了 Turing booter 的 DMA/签名溢出。加载 Ampere booter 的卡是否从那条路径继承它，有争议且未解决；见[未解问题](../frontier/open-questions.md)。

---

## 6. Booter 内部：IMEM 函数图

这张表里所有地址都是解密调试签名映像 `booter_load_ga100_dbg_seccode.fuc5.asm` 的 **IMEM**（代码）地址。带注释的清单 `booter_load_ga100_dbg_seccode.annotated.fuc5_v2.asm` 包含 10,934 行未修改代码，带按函数横幅。

| IMEM | 符号 | 角色 |
|---|---|---|
| `0x0100` | `_start` | 入口点。十阶段 HS 序言。 |
| `0x04a7` | （自循环） | `3e a7 04 00 B lbra 0x4a7`。载荷填充 dword 的旋转停靠。 |
| `0x04d0` | `_start` 出口 | |
| `0x04d4` | `dma_copy_block` | 真正的 DMA-到-DMEM 循环（`xdld`）。**溢出的帧。** |
| `0x0602` | `dma_dispatch_descriptors` | 提交最多四个子描述符，打标 `r14 = 0xa0..0xa3` |
| `0x0c7c` | `regblock_read_guarded` | |
| `0x0cbd` | elevator | `0x0c7c` 里的 `mov $r10 $r0` |
| `0x0ccb` | `regtable_rw_indexed` | 对寄存器描述符表的索引访问；以 `mpopaddret $r5 0x8` 结束 |
| `0x0d66` | ACR 互斥锁获取 | 若 id 字节读 0 或 `0xff` 则错误 `0x1a`，坏类型 `0x1c` |
| `0x0e85` | `memcpy` | |
| `0x0aa1` | `tgt_falcon_bringup` | 拉起目标 Falcon；错误 `0x1c`、`0x11` |
| `0x1034` | `watchdog_set` | 用 `0x1312d00`（20,000,000）播种 `I[0x1c300]` |
| `0x1064` | `mailbox_wait_ready` | 轮询 `I[0x1c000]` 位 [14:12]：0 完成，1 旋转，否则错误 `0x15` |
| `0x10aa` | `reg_write_indirect` / `_acrlibBar0RegWrite_TU10X` | **任意 BAR0 写原语。** 约 70 个调用点。 |
| `0x10b9` | （中途进入） | 跳过 `r10`/`r11` 到 `r0`/`r1` 的编组 |
| `0x10ff` | `mpopaddret $r3 0x4` | `0x10aa` 的尾声；让写自我链接 |
| `0x1196` | `reg_read_indirect` | |
| `0x14cf` | `tlb_scan_invalidate` | 刷新映像自身的过时映射，范围 `[0, 0x8700)` |
| `0x154a` | `wpr_desc_validate` | +0 处魔数 `0x371a60b3`、+4 处 `0xdc3aae21`；错误 `0x89`-`0x90` |
| `0x19a2` | `va_to_pa_walk` | 三级软件页遍历；错误 `0x2` |
| `0x1b44` | `set_1180f8_bit24` | 把 `0x01000000` OR 进 `0x001180f8` |
| `0x1ba3` | `check_1180f8_2724` | 要求 `0x001180f8[27:24] == 0`，否则错误 `0x88` |
| `0x1c0e` | `set_1180f8_top_nibble`（finalize） | 清除 [31:28] 并 OR `(r0 << 28)`；尾声 `0x1c72` |
| `0x1c75` | `check_1180f8_nibbles` | 要求 [31:28] == 0 **且** [23:20] == 0，否则错误 `0x29` |
| `0x1d0f` | `report_status` | 把 `$r0` 写进 MAILBOX0 |
| `0x1d3b` | `f100_field_save_restore` | 经 DMEM `0x1900` 对寄存器 `0xf100` 位 [4:6] 的 RMW |
| `0x1e09` | `scp_key_derive` | 带硬件机密 `0x37` 或 `0x36` 的 `csecret $c7` |
| `0x1f92` | `read_820344_820348` | |
| `0x1fb9` / `0x1fbd` / `0x1fca` | elevators | 见[ROP 链](rop-chain.md) |
| `0x21f4` | `image_dma_loader` | 调用点 `0x2725` |
| `0x2120` | `chunked_dma_copy` | 对寄存器 `0x4b00` 的 `0x100` 字节块 |
| `0x22ba` | `booter_load_wpr_main` | 错误 `0x5`、`0x89`、`0x8a`、`0x96`、`0x98`、`0x9c`、`0xa4` |
| `0x27fa` | `0x22ba` 内的重接点 | 写 `D[0x6f8]`/`D[0x6fc]`/`D[0x648]`；**不**碰任何 WPR2 寄存器 |
| `0x28ac` | `wpr_region_check` | 错误 `0x5` |
| `0x291e` | `wpr_region_program` | 实际写 `0x001fa824`/`0x001fa828`；拒绝空区域 |
| `0x2e80` | `image_auth_decrypt` | 流式 `0x100` 字节块，密钥句柄 `0x17d78414` |
| `0x3747` | `image_copy_verify` | 正常返回 `0x2740` |
| `0x37b3` | 签名 DMA 调用点 | `lcall 0x4d4` |
| `0x37b7` | DMA 后结果检查 | `ld $r9 D[$r1+0x50]` |
| `0x399a` | `ls_sig_verify` | 要求 `r10 == 0x700`；错误 `0x98` |
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
| `0x7dd9` | `__stack_chk_fail` / `panic()` | 把 `0x47` 写进 MAILBOX0，在 `0x7def` 旋转 |
| `0x7de9` | （panic 主体） | 打印 `$r15` 里的任何东西。每个调试 ROP 的基础。 |
| `0x7df3` | `memcmp_ct` | 恒定时间比较 |
| `0x7e76` | `secure_teardown` | 永不返回 |
| `0x7eef` | 密码自清零扫描 | 在 `secure_teardown` 内 |
| `0x7f2f` | `secure_teardown` 里的退出 gadget | 已发布的载荷的终止符 |
| `0x7f82` | **`main`** | |
| `0x8137` | `booter_load_wrap` | |
| `0x815a` | `booter_load_wrap` 的金丝雀检查尾 / 栈吞噬器 | 见下面的注 |
| `0x8224` | `csb_write` | 存储是 `0x8232` 处的 `iowrs I[$r10] $r11` |
| `0x8262` | 裸 `ret` | 有用的对齐 gadget |
| `0x8264` | `csb_read` | |
| `0x8307` | `fbif_set_bit800` | 在掩码 `0x0ffff8ff` 下把位 `0x800` 设进 `0x001fa814`/`0x001fa818` |

> [!NOTE]
> **已解决：`0x815a` 在 `booter_load_wrap` 内**
>
> 一份目录叫它 "the main canary-check tail"；另一份把它注释为 "a stack-eater in `booter_load_wrap` that checks the canary and does nothing"（`booter_load_wrap` 里一个检查金丝雀却什么都不做的栈吞噬器）。带注释的 v2 清单定论了它。`main` 从 `0x7f82` 跑到 `0x8134`，那里它自己的金丝雀检查以 `mpopaddret $r0 0x10` 结束。`booter_load_wrap` 从 `0x8137` 跑到 `0x8173`，以 `mpopaddret $r0 0x4` 结束，下一个函数横幅是 `0x8176` 处的 `nibble_rmw`。因此 `0x815a` 位于 `booter_load_wrap` 内，由 `0x8150` 处跳过 `boot_mode_dispatch (0x683f)` 调用的 `bra b32 $r10 0x0 e 0x815a` 到达。它是那个包装器的金丝雀检查尾；`main` 自己的尾是 `0x811d` 处单独一块。第二份目录是对的。

---

## 7. 引导流程

### 7.1 `_start`（IMEM `0x0100`）：十阶段 HS 序言

1. 在 `0x0107` 清理 SCP 状态（`csigclr` / `csecret` / `cxor`）。每个 `csecret $cN 0x0` 都紧接一个 `cxor $cN $cN`，所以寄存器组在被配置的那一刻就被清零。
2. 在 `0x014b` 清除每个通用寄存器 `$r0`..`$r15`。
3. 在 `0x016b` 停用 Falcon，轮询 `I[0x9100]` 位 31。
4. 在 `0x02b3` 清除中断使能标志 `ie0` / `ie1` / `ie2` 和定时器/异常标志（`mov $r9 0x10` / `0x11` / `0x12` / `0x18`，各被 `bclr $flags $r9` 跟随）。
5. **阶段 5** 设置陷阱向量 `$tv = 0xeb` 并清除 `$cauth` 安全-故障使能位：`mov $r9 0xeb; mov $tv $r9; mov $r9 $cauth; mov $r15 -0x80001; and $r9 $r15; mov $cauth $r9`。
6. **阶段 6** 按序触碰 CSB `0x4e00`（掩码 `0xff000000`，然后 OR `0x80003000`）、`0x10100`（OR `0x101`，旋转到位 `0x100` 清除，以 `0x400` 次迭代为界）、`0x14000`（设 `0x7fff`）、`0x14100`（保留低 16 位，OR `0x03ff0000`）、`0x14b00`（OR `0xff00`），然后又 `0x10100`（OR `0x1000`）。
7. 经 `crnd` 在 `0x0433` 处做 SCP 自配置。
8. 在 `0x0463` 验证 SCP 并扫描 DMEM `0x6330`..`0x6340`。
9. **阶段 9** 清除 `0x10100` 位 `0x1000`（AND `-0x1001`），并把栈金丝雀安装在 DMEM `0x6340`，取自扫描 DMEM `0x6330`..`0x6340` 时找到的第一个非零字。
10. 在 `0x04cc` 处 `lcall 0x7f82` 进入 `main()`；在 `0x04d0` 处退出。

### 7.2 `main`（IMEM `0x7f82`）

`main` 按序编排：`f100_field_save_restore (0x1d3b)`；权限级别掩码和孔径编程；`tgt_falcon_bringup (0xaa1)`；`chipid_gate (0x6a71)`；描述符验证；`regtable_reverse_lookup (0xd66)`；`tlb_scan_invalidate (0x14cf)`；`booter_load_wrap (0x8137)`（它调用 `booter_load_wpr_main (0x22ba)`）；finalize 提交 `(0x1c0e)`；`report_status (0x1d0f)`；成功后 `secure_teardown (0x7e76)`。

在 MAIN.2、紧接 `watchdog_set` 之后，Booter Load 在 **CSB** 空间写入四个固定的权限级别掩码和孔径值：

```asm
I[0x12000] = 0x11111101
I[0x12400] = 0x00000111
I[0x12600] = 0x11111111
I[0x12100] = 0x00011100
```

每个值都被内联的 fail-closed 断言跟随，所以其中任何一个的 CSB 错误都会把 Falcon 楔死在无限自分支里。

`chipid_gate` 读寄存器 `0xa00` 位 [28:20]，只接受芯片 ID `0x170` 和 `0x171`。跳线 `0x170` 无条件通过；跳线 `0x171` 额外要求寄存器 `0x10200` 的位 20 置位，否则错误 `0x4b`。CMP 170HX 上 BAR0 `0x00000000` 处的 `PMC_BOOT_0` 读 `0x170000a1`，所以实现 ID `0x170` 通过。见[GA100 硅片](../hardware/ga100-silicon.md)。

`main` 的尾，精确地：

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

**DMEM `0xFFEC` 是喂给退出状态、并决定是否运行 teardown 的槽。** 这由一次硬件 A/B 定论，反驳了一个竞争的 `0xFFE4` 假设，并与已发表的 ROP v3 注释 "FFEC 00000000 <- Return value to main() to indicate success ($r0)" 匹配。把 `D[0xFFEC]` 设为 `0xDEADBEEF`，会让 `0x001180f8` 从 `0x11000000` 移到 `0xf1000000`，恰好符合 `(r0 << 28)` 模型的预测。

### 7.3 booter 实际为 GPU 做什么

两件超出 GSP 移交的事要紧：

- **显存时钟和时序编程。** `memcfg_program (0x79cc)` 读 BAR0 `0x20414`、`0x136658`、`0x136e58` 和 `0x136458`，打包提取的位字段并写 `0x11824c` 和 `0x118250`。`memcfg_apply_poll (0x7a64)` 只在 `0x11824c` 位 0 置位时运行，然后以超时 100000（错误 `0xa6`）轮询 `0x136600`、`0x136e00` 和 `0x136400`。`memcfg_timing_program (0x7c65)` 从派生自 `0x137178` 和 `0x136604` 的基常量 `0x32a` 计算缩放的时序和带宽值，超时 125000（错误 `0xa7`）。`const_out_write (0x797a)` 提供固定常量 `0x68`、`0x555`、`0x5be`、`0x5a0`。
- **目标 Falcon 拉起。** `tgt_falcon_init_reset (0x9da)` 写 `0x3f0c = 0xa0100`、用 `0xfeed0000` OR 索引的八个字填充 `0x3f40` 处的寄存器组、然后用 `0x3f00 = 3` 和 `0x104 = 1` 结束。`mailbox_write_d000 (0xb28)` 为位 `0x1c0000` 轮询 `0xd000`、把数据写到 `0xd200`、命令写到 `0xd100`。`tgt_falcon_handshake (0xbc9)` 验证一个 `0xbadf0000` 哨兵和一个 `0x3f20`..`0x3f40` 范围，错误 `0x38`。

`booter_load_wpr_main` 的 finalize 尾拉响 GSP RISC-V 移交：在 `0x286a` booter 经 `0x1b44` 设置 `SECURE_SCRATCH_14`（`0x001180f8`）的位 24，然后 `0x2874` 调用 `reg_init (0x68ed)`，它写 GSP `FBIF_CTL 0x00110624 = 0x90`（ALLOW_PHYS_NO_CTX 位 7 加位 4）、`0x00110684 = 1` 和 `0x0011126c = 1`。任何意味着移交给 GSP-RM 的链都必须让它运行或复现那三次写。`0x110684` 和 `0x11126c` 的字段名是推断的，未经头文件确认。

---

## 8. DMEM 图

这里所有地址都是 **DMEM**。`0x100` 之下什么都不分配，这正是 "staged in low DMEM 的 mega-ROP" 被排除的原因。

| DMEM | 内容 | 备注 |
|---|---|---|
| `0x0000`-`0x00FF` | 未分配 | |
| `0x0200` | booter 自己的 HS 签名 | 加载前被打进映像（`hsSigDmemAddr = patchLoc - dataOffset`，`0x8900 - 0x8700`）。**不是**溢出的那个缓冲区。 |
| `0x0530` | DMA/引擎配置描述符结构 | |
| `0x0600`-`0x06FF` | `WprMeta`，一个 256 字节结构 | +0 处魔数 `0x371a60b3`、+4 处 `0xdc3aae21`。在 DMA 目标下方，所以溢出从不碰它。 |
| `0x0700` | 映像描述符 | `ls_sig_verify` 要求 `r10 == 0x700` |
| **`0x0800`** | **GSP-RM LS 签名缓冲区** | **DMA 目的地。利用。** |
| `0x103c` 起 | 密码会话描述符 | 字段 `0x1004`、`0x107c`、`0x1080`、`0x1100` |
| `0x1900` | `f100` 字段保存槽 | 已发布的载荷把 `0x00000007` 种在这 |
| `0x1904` / `0x190c` / `0x1914` | `va_to_pa_walk` 的 PTE 缓存 | |
| `0x1a00` / `0x2a00` / `0x3a00` | 页缓冲 | |
| `0x2383` | 寄存器描述符表 | 被 `0xF800` 载荷粉碎；错误 `0x35` 的来源 |
| `0x5f00` | 固件请求头 | `'FREE'` / `'HEAP'` 魔数 |
| `0x6330`-`0x633F` | 阶段 9 扫描的临时区 | |
| **`0x6340`** | **栈金丝雀守卫全局** | 25408 十进制 |
| `0x8700` | booter 代码/数据的末尾 | |
| `0x8e08` | 寄存器描述符表 | 也被粉碎 |
| 约 `0xFF3C`-`0xFFFF` | 活调用栈 | 从顶部向下增长 |

### 栈金丝雀

每次启动都会从硬件 RNG 生成一个新的随机值，保存在 DMEM `0x6340` 的全局里。每个受保护函数把它复制到栈帧边界、在退出时重读并比较；一旦不匹配就调用 `0x7dd9` 处的 `panic()`。规范序言是 `mov $rX 0x6340; ld b32 $r9 D[$rX]`；尾声是 `cmp b32 $r15 $r9; bra e <ok>; lcall 0x7dd9`。

因为该值每次启动都会从硬件 RNG 重新生成，所以无法离线猜测，但也无需猜测。守卫全局活在可写数据内存里，恰好被它要检测的那个溢出可达，因此载荷用同一个选定值覆写全局**和**每个重建的金丝雀槽，于是每个尾声比较都通过。这就是已发表论文的 Thesis 1：Falcon 栈金丝雀在 *引用字完整性* 上失败，而非在熵上。在这个映像里，工具链把守卫放在只读数据段的尾部，而在扁平 MPU 映射的映像里，那落在可写数据跨度内。没有 RELRO 等效、没有守卫页、也没有 MPU 只读映射。

---

## 9. BAR0 master、CSB 纪律和邮箱

### 9.1 BAR0 master

Falcon 只能通过 Falcon CSB 空间里一个间接、互斥门控的邮箱到达外部 BAR0 寄存器，没有内存映射的 "direct" 路径。

| CSB 端口 | 角色 |
|---|---|
| `I[0x1c100]` | 目标 PRI 地址（完整 32 位） |
| `I[0x1c200]` | 数据。对读而言，结果回到这里。 |
| `I[0x1c000]` | 命令：**`0x800000f2` = 写，`0x800000f1` = 读** |
| `I[0x1c300]` | 看门狗，被 `watchdog_set (0x1034)` 用 `0x1312d00`（20,000,000）播种 |

booter 也用这条路径做自己的事：`0x29b8 -> 0x10aa` 写 WPR2 寄存器，而 finalize 例程对 `0x001180f8` 的写字面上是 `1c4b: r10=0x1180f8 ; lcall 0x10aa`。对应的读出现在 `1c35: r10=0x1180f8 ; lcall 0x1196`。

### 9.2 Fail-closed CSB 访问

**booter 里每次 CSB 访问都是 fail-closed 的。** 每次访问后，代码都会采样 CSB 错误状态 `I[0x9100]` 位 31，即 `FALCON_CSBERRSTAT.VALID`——一个**故障标志**，表示上一次 CSB 访问出错了，**不是**忙或完成轮询。原始内联序言出错时分支到自身、把 Falcon 永远楔死；两个辅助函数则改为报告状态 `0x15` 并退出。

```asm
mov  rX 0x9100
iords
shr  0x1f
bra
self-lbra
```

那个惯用语内联出现约 25 次，另加两个辅助函数。`csb_read (0x8264)` 还会用 `0xffff0000` 掩码返回的数据，并测试 PRI 毒哨兵 `0xbadf0000`，带一个白名单（`0x208c` 处的 `reg_whitelist_40f00`，覆盖 `[0x40f00, 0x41f00)` 步长 `0x100`）和一条对寄存器 `0x1c200`、`0xc00`、`0xb00` 和 `0xd500` 的重试路径。

### 9.3 MAILBOX0 语义

Falcon I/O `0x1000` 是 Falcon 自己的 MAILBOX0，主机可见于 BAR0 `0x00840040`，MAILBOX1 在 `0x00840044`（`CSB 0x1000 / 64 = falcon 0x40`）。从主机在 PL0 直接读 BAR0 `0x1000` 返回 `0xbadf5040`，解决了一个长期混淆。

MAILBOX0 是利用期间唯一可观察的通道，统一规则是：

> [!NOTE]
> **任何经 `report_status` 的返回路径上，MAILBOX0 等于 `$r0`**
>
> MAILBOX0 读 `0x31` 只意味着 `report_status` 从未执行。booter 自己在 ucode 偏移量 `0x7a` 处印下 `0x31`（`mov $r15 0x31 / mov $r9 0x1000 / iowrs I[$r9] $r15`），作为它第一个活性标记，覆写驱动种下的 WprMeta 物理地址参数。

实测：返回地址 `0x8117`（原始退出，跳过 `report_status`）给出 MB0 `0x31`；`0x810d` 当 `r0 = 0` 时给出 MB0 `0x0`、当 `0xcafe` 被种下时给出 `0xcafe`；`0x8d4` 给出 `0x0b`。

实用分类：`0x47` = 栈金丝雀检查失败、Falcon 在 `panic()` 自循环里；`0x31` = `report_status` 从未运行；`0x96` = 金丝雀完好地正常引导。

### 9.4 状态码

| 码 | 来源 | 含义 |
|---|---|---|
| `0x01` | `antirollback_version 0x59c4` | 存储的版本超过候选 |
| `0x05` | `wpr_region_check 0x28ac` / `wpr_region_program 0x291e` | WPR 上限 < 基址，或空区域 |
| `0x11` | `pka_ready_check 0x580f` / `pka_status_check 0x5473` | |
| `0x15` | `csb_read` / `csb_write` / `mailbox_wait_ready` / `reg_read_indirect` | CSB/PRI 访问故障 |
| `0x1c` | 通用 | 坏参数 |
| `0x23` / `0x4e` | `verify_reg_bitlen` | |
| `0x29` | `check_1180f8_nibbles 0x1c75`（从 `0x80a5` 调用） | `0x001180f8` [31:28] 或 [23:20] 非零 |
| `0x2d` | `firmware_load_main` | |
| `0x31` | PC `0x7a` | 入口活性标记；`report_status` 未到达 |
| `0x32` | `check_reg_4f00` | |
| `0x35` | `regtable_rw_indexed` | `0x2383`/`0x8E08` 处的 DMEM 描述符表读零 |
| `0x38` | `tgt_falcon_handshake 0xbc9` | |
| `0x47` | `__stack_chk_fail 0x7dd9` | 金丝雀不匹配，然后挂起 |
| `0x4b` | `chipid_gate 0x6a71` | 跳线 `0x171` 而无 `0x10200` 位 20 |
| `0x54` | 未知 | 只在 PG199 板上观察到。见下。 |
| `0x59` | 驱动侧 | `dmem.bin` 缺失。良性。 |
| `0x5c` | `antirollback_version` | 孔径检查 |
| `0x62` | PKA 路径 | |
| `0x63`-`0x6d` | `pka_modexp_run 0x54ab` | `0x6c` = 超时 |
| `0x6e` | `check_10200_820434` | |
| `0x74` | `check_reg_118128` | |
| `0x88` | `check_1180f8_2724 0x1ba3` | `0x001180f8[27:24]` 非零 |
| `0x89`-`0x90` | `wpr_desc_validate 0x154a` | `0x8e`/`0x8f` 是 `0x1ffff` 对齐和 `0xfff` 字段检查 |
| `0x96` | 正常 | 金丝雀完好地引导 |
| `0x98` | `ls_sig_verify 0x399a` / `booter_load_wpr_main` | |
| `0x9c` / `0xa4` | `booter_load_wpr_main` | |
| `0x9e` | `range_validate_windows` | |
| `0x9f` | `hw_state_gate`、`dma_region_lock_setup` | |
| `0xa5` | `firmware_load_main` | |
| `0xa6` / `0xa7` | memcfg 路径 | |

主机侧，作对比：`NV_ERR_TIMEOUT = 0x00000065`、`NV_ERR_MEMORY_ERROR = 0x72`、`NV_ERR_GENERIC = 0xffff`。观察到的复合 `RmInitAdapter` 失败包括 `0x62:0x40:2028`、`0x62:0x55` 和 `0x62:0x65:2674`。

> [!NOTE]
> **未解问题：Booter 状态 `0x54`**
>
> 把一份修改过的 cmpunlocker 应用在一块 PG199 板上失败于 `s_executeBooterUcode_TU102: Booter failed 0x54`，尽管 CFG1 和 LMR 写入落地、PLM 打开了。每个其它状态码都通过定位它在反汇编里的写站点被钉死；同一个方法应该对 `0x54` 有效，而反汇编在手。

---

## 10. 离开重度安全模式，以及复位 PLM

IMEM `0x7e76` 处的 `secure_teardown` 是设计的退出。它重新启用 `0x10100` DMA 孔径（OR `0x101`，旋转到位 `0x100` 清除，以 `0x400` 次迭代为界）、设 `$cauth |= 0x80000`（位 19，在停机前抑制中断和异常），然后对 `$c0`..`$c7` 各发出 `csecret $cN 0x0` 接 `cxor $cN $cN`，用 `r14 = 0` 从 0 到 `0x10000` 循环 `st b32 D[$r9] $r14; add $r9 0x4`，清除 `r0`..`r15`，并执行原始 `exit` 操作码（`f8 02`）。它永不返回。那个 `exit` 正是让 Falcon 掉出 HS 模式、从而允许加载新代码的关键。

从 `main` 到达它需要 `0x8113` 处的 `r0 == 0` 分支到 `0x8119`。若 `r0` 非零，则走 `0x8117 exit`，根本没有 teardown。

**错误路径总是按此顺序调用 `report_status (0x1d0f)` 然后 `secure_teardown (0x7e76)`**：这对调用出现在 `0x873`/`0x877`、`0x88a`/`0x88e` 和 `0x8a7`/`0x8ab`。成功路径两者都不调用，为 GSP 移交保留密码与环境完好。因此一个流传的 "mailbox XOR teardown" 框架是错的：错误路径两者都做。

### 复位 PLM，`0x008403C4`

SEC2 复位源 PLM 门控 `+0x3c0` 处的 SEC2 `FALCON_ENGINE` 复位控制。它发射后的值决定 SEC2 能否再次被复位。

| 值 | 含义 |
|---|---|
| `0xff` | 完全打开。干净的闲置、SBR 后、SEC2 未使用。一次主机 PL0 `kflcnReset` 会接受。 |
| `0xdf` | 出厂驱动在其 GSP 引导 teardown 后留下的正常工作状态。仍允许复位。 |
| `0xcf` | 在驱动的 GSP 预备重新锁上 PLM（位 4 清除）后观察到。 |
| `0x8f` | HS-退出污染。低半字节 `0xf` = 所有级别可读；高半字节 `0x8` = 写锁定到安全源，所以 PL0 复位写被弹回。 |

规则：`reset_allowed = resetPLM in {0xff, 0xdf}`。`0xdf = 0x8f | 0x50`。

关键是，`0x8f` 是在 **HS 到 NS 退出转变时由硬件锁存**的，不由任何 booter 指令写入：静态分析在 booter 里发现零条对 `0x8403C4` 的指令引用。离开 HS 会让硬件把每个 HS 门控的 PLM 重新保护到安全默认值。实测：在 `0x8117` 处取原始退出会留下 resetPLM `0xff`；让 `secure_teardown` 运行则会重新锁存到 `0x8f`。

> [!NOTE]
> **未解问题：`resetPLM = 0x8f` 会阻止加载新 SEC2 ucode 吗？**
>
> 一份报告说 SEC2 在 `0x8f` 时可重载（Hello World 触发、MAILBOX0 从 `0x0` 变 `0x31`）；另一份说加载新 ucode 需要 SFTRESET、而复位 PLM 门控它，并报告 `NS load mismatch (HS-locked, needs --flr)`。一个可能的调和——NS 重载有效、HS 签名重载无效——被提出但从未定论。一次受控实验能回答它：在一个已知 `0x8f` 下，背靠背加载一个 NS ucode 和一个 HS 签名 ucode，并记录每个的 `CPUCTL` 和加载器错误字符串。

已发布的驱动完全绕开这套纪律：它**从不读或写 `0x008403C4`**。对已发布的仓库 grep `0x008403c4`、`0x001180f8`、`0x001fa81c` 或 `0x001fa820` 会得到零引用。驱动内路径改走驱动自己的 `kflcnReset`/FWSEC 序列来重发 Booter Load，补丁 `0002` 通过记录 `SEC2_DEBUG: kflcnReset for FWSEC: 0x%x` 和 `SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x` 确认这一点。

---

## 11. 签名缓冲区

这是整个解锁围绕的核心对象。

| 属性 | 出厂 | 解锁下 |
|---|---|---|
| 分配 | `NV_ALIGN_UP(pGspFw->signatureSize, 256)`；观察到 4,096 字节 | `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL` = 63,488 字节 |
| 对齐 | 256 字节，`ADDR_SYSMEM` | 256 字节，`ADDR_SYSMEM` |
| DMEM 目的地 | `0x0800` | `0x0800` |
| DMEM 触及范围 | `0x17FF` | `0xFFFF`，恰好 DMEM 顶部 |
| 长度来源 | `WprMeta.sizeOfSignature` | `WprMeta.sizeOfSignature` |

booter 逐字从 `WprMeta.sizeOfSignature` 取复制长度、不做任何边界检查，而驱动同时控制缓冲区内容和那个字段。放大是一个 15.5 倍因子。出厂签名的 DMA 只到达 DMEM `0x17FF`，这正是正常引导能保持 `0x2383` 和 `0x8E08` 处寄存器描述符表完整的原因。

DMA 目标 `0x800` 由 IMEM `0x37ad` 处的 `mov $r10 0x800` 设置，随后 `0x37b3` 处 `lcall 0x4d4`。接下来发生什么见[ROP 链](rop-chain.md)。

> [!NOTE]
> **不是矛盾**
>
> `kernel_gsp_booter.c:329` 计算 `pUcode->hsSigDmemAddr = patchLoc - pUcode->dataOffset`，带 `patchLoc = 0x8900` 和 `dataOffset = 0x8700` 时，会把一个签名放在 DMEM `0x200`。那是 **booter 自己的 HS 签名**，加载前被打进 booter 映像。DMEM `0x800` 是 booter 从 sysmem DMA 的 **GSP-RM LS 签名**落下的地方，那才是溢出的。两个不同的缓冲区。置信度：中等，因为这条调和与每个观察一致，但没人明确陈述过它。

还有一个属性对解锁的持久化故事要紧：**出厂 AES-MAC 签名在几何改动后仍有效**，因为它覆盖的是静态 GSP 固件映像，而非运行时 WPR 元数据或硬件几何布局；WPR 元数据由驱动在运行时计算。一条相反方向的早期说法已被其作者明确撤回。

---

## 12. 已发布的驱动如何调用 Booter Load

本节一切直接读自已发布的 `master` 上的 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 和 `0002-booter-verify.patch`。完整补丁集见[驱动补丁](driver-patches.md)。

### 12.1 门

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID  0x2082
```

`_kgspSec2PostblTimingEnabled()` 把 `pGpu->idInfo.PCIDeviceID >> 16` 与恰好这两个值比较。一张 `install.sh` 也会 grep 到的 `10de:20b0` 卡会安装却不解锁。目标驱动版本是 `610.43.03`（默认）和 `610.43.02`；构建在其它任何版本上硬性失败。

### 12.2 按顺序的序列

1. **`_kgspCreateSignatureMemdesc`** 把签名 memdesc 分配在 `0x0000f800` 而非 `NV_ALIGN_UP(pGspFw->signatureSize, 256)`。改作他用之前，出厂签名字节被复制进 `pKernelGsp->pStockSignatureData` / `stockSignatureSize`——即加到 `g_kernel_gsp_nvoc.h` 里 `KernelGsp` 的两个新字段。记录 `SEC2_DEBUG: saved stock signature (%llu bytes)`，在卡上报告 4096。
2. **可选外部载荷。** `os_open_and_read_file()` 尝试把 `SEC2_POSTBL_TIMING_DMEM_PATH = "/lib/firmware/nvidia/ga100/gsp/dmem.bin"` 读进新缓冲区。成功则记录 `SEC2_DEBUG: loaded %llu bytes from %s`；缺失则记录 `SEC2_DEBUG: %s not found (0x%x), using built-in payload`（带 `0x59`），并回退到预置了 `writeAddr = 0x009a0148`、`writeValue = 0xffffffff` 的内置载荷。无论哪种情况都调用 `memdescFlushCpuCaches()`。
3. **保存 WPR2。** 读一次 `0x001fa824`（低）和 `0x001fa828`（高），记录 `SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x`。
4. **PLM 循环。** 对四个表条目的每个，最多尝试两次：

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

    失败记录 `SEC2_DEBUG: FAILED to open <name> after 2 attempts`。表和它的精确值见[权限级别掩码](privilege-level-masks.md)。

5. **循环后再恢复一次 WPR2。**
6. **四条 PL0 处的普通主机写**，不再需要利用：`0x0082381c = 0x88888888`（SS0）、`0x00823820 = 0x00000008`（SS1）、`0x009a0204 = cfg1Value`、`0x00100ce0 = lmrValue`。然后 `SEC2_DEBUG: POST-WRITE SS0=… SS1=… CFG1=… LMR=…`。见[算力节流](compute-throttle.md) 和[显存几何布局](memory-geometry.md)。
7. **`kgspSec2PostblTimingRebuildStockSignature()`** 释放并销毁 `0xf800` memdesc，用 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 在 `NV_ALIGN_UP(stockSignatureSize, 256)` 分配替换，把 `pStockSignatureData` 复制回去，并把 `pWprMeta->sysmemAddrOfSignature` / `sizeOfSignature` 重新指向。失败以 `SEC2_DEBUG: rebuild stock signature failed: 0x%x` 中止引导。
8. **`kgspPopulateWprMeta_HAL` 运行第二次**，让 WPR 元数据反映加宽的 FB。卡上 dmesg 显示 `WPR meta updated fbSize=0x0000001000000000 …` 紧接 `normal BooterLoad status=0x0`。

这就是为什么 GSP-RM 能在*同一*次驱动加载里正常引导：利用和真实引导在一次加载内顺序发生，不需要冷启动等效的移交。

### 12.3 重新填充辅助函数

`kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp, writeAddr, writeValue)` 用 `memdescMapInternal(..., TRANSFER_FLAGS_NONE)` 映射 memdesc，为那一个 `(writeAddr, writeValue)` 对重写整个 `0xf800` 字节载荷，取消映射，对签名 memdesc 调用 `memdescFlushCpuCaches()`，重新发布 `pWprMeta->sysmemAddrOfSignature = memdescGetPhysAddr(...)` 和 `pWprMeta->sizeOfSignature = memdescGetSize(...)`，然后对 `pWprMetaDescriptor` 刷新 CPU 缓存。memdesc 为 NULL 时返回 `NV_ERR_INVALID_STATE`，映射失败时返回 `NV_ERR_INSUFFICIENT_RESOURCES`。把签名长度 `0xf800` 交给 booter **就是**溢出。

缓存刷新不是可选的。签名 DMA 是非连贯的，没有显式刷新，Falcon 就会读到陈旧的 RAM。

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

每次发射恰好执行**一次**任意 BAR0 写。

### 12.6 读日志

> [!WARNING]
> **寄存器回读是唯一有效的成功标准**
>
> 每次载荷执行都记录 `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` 和 `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`，**而寄存器写入仍然落地**。在 `s_executeBooterUcode_TU102` 里，seccode 错误在每次运行后留在 MAILBOX0，`mailbox0 != 0` 就返回 `NV_ERR_GENERIC`（`0xffff`）。已发布的循环的成功测试是精确的回读相等，那正是正确的测试。项目 README 也说同样的事：早期 PLM 轮次期间的 `0x31` / `0xffff` 等 Booter 状态码，只要最终引导成功就往往无害。

见[验证](../procedures/verify.md) 和[排障](../procedures/troubleshooting.md)。

## 13. 无驱动调用，作对比

一族独立 Python 和 C 工具（`refire_chain_v2.py` 到 `v9.py`、`load_gsp_sec2_falcon.c`、`load_custom_bin.py`）在没有任何 NVIDIA 驱动的情况下发射 booter。它们**不在**已发布的仓库里，而本领域大部分表面矛盾在把两个代码库分开后都会消解。这些工具要紧，因为寄存器纪律大多是在那里学到的。见[工具谱系](../history/tool-lineage.md)。

在 SEC2 上运行非安全代码是琐碎的、除公开文档外什么都不需要：把二进制 DMA 进 IMEM、设 `BOOTVEC`、发 `STARTCPU`、然后如果代码用 `exit` 就轮询 `CPUCTL` 位 4（HALTED）。完整无驱动引导序列是：引擎复位、等待 DMA 清理、`ALLOW_PHYS_NO_CTX`、物理 DMA 孔径、DMA IMEM + DMEM、设 `BOOTVEC`、设邮箱、`STARTCPU`、轮询 HALTED。

复位序列，如实现且工作的：

```text
if SCTL (SEC2+0x240) 有 HSMODE（位 1）置位：
    写 SFTRESET (SEC2+0x07c) = 1 并回读
pulse ENGINE (SEC2+0x3c0)：1 然后 0
轮询 DMACTL (SEC2+0x10c) 直到清理位 0x6 清除，忽略 0xffffffff 读
轮询 SCP_P2PRX (SEC2+0x530) 位 3，带 KFUSE_CTL (SEC2+0x11ec) 位 0 置位、位 1 清除
把 AUTH_EN（1 << 14）OR 进 SCTL
```

默认超时 10.0 s；失败路径报告 "scrub timeout"。Booter 加载随后用 IMEMC/IMEMD 带自动递增和每 256 字节 IMEM 标签，对 HS 区域置位 SECURE 位 `1 << 28`。孔径被强制为物理模式：在 `0x00840600`/`0x604`/`0x608` 写 `FBIF_TRANSCFG[0..2] = 4, 5, 6`，然后在 `0x00840624` 处 `FBIF_CTL |= 0x80`，最后 `start_wait`，此时 MAILBOX0/1 已被设为 WprMeta 物理地址的低、高半。

一个独立 C 程序在硬件上执行完整九步无驱动引导，并从 `FALCON_MAILBOX0` 读到一个停机返回值 `0xb`：加载路径在没有 NVIDIA 驱动的情况下工作，尽管 Falcon 以非零状态停机。

无驱动路径发现的两个进一步要求，已发布的驱动都通过其它手段满足：

- **缓存刷新。** 一个 17 字节 JIT 组装的 x86-64 桩（`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`，即 `clflush [rdi]` / `add rdi,64` / `sub rsi,64` / `jg` / `mfence` / `ret`）被映射为 `PROT_EXEC`，并在载荷、radix3 和 WprMeta 缓冲上运行，向上取整到 64 字节缓存行。`refire_chain_v6.py` 用 `MAP_HUGETLB`（`0x40000`）分配 2 MiB 巨页、mlock 它们，并检查存在位后按 `(entry & ((1<<55)-1)) * 4096` 从 `/proc/self/pagemap` 解析物理地址。
- **一个最小 radix3 页表。** `stage_radix3()` 分配 `0x6000` 字节并写三个 64 位描述符（PDE2 在 `0x0000` 到 `phys+0x1000`、PDE1 在 `0x1000` 到 `phys+0x2000`、PDE0 在 `0x2000` 到 `phys+0x3000`），让数据页和 bootloader 主体保持清零，然后刷新。没有它，booter 的签名前 DMA 以原因 `0x9` 失败。WprMeta 模板是 256 字节，从一次真实 10 GB 引导捕获，只覆盖了 radix3 指针（`+0x10`）、radix3 大小（`+0x18`）、bootloader 指针（`+0x20`）、bootloader 大小（`+0x28`）、签名指针（`+0x48`）和签名大小（`+0x50`，设成 `0xF800`）。

注意两条路径在邮箱语义上也不同：独立加载器用 5 s 超时轮询 HALTED 然后读 `0x840040` 期望 `0x31` / `0x96` / `0x47`，而驱动内路径无论结果都报告 `0xffff`。

---

## 14. 本页的开放问题

> [!NOTE]
> **无驱动发射能移交给出厂驱动吗？**
>
> 出厂驱动通过经典的两次加载 "mutex horns" 拒绝发射后的 SEC2 状态：`0x31`（互斥锁持有）、`0x62`（WPR2 up）和 `0x29`（一个 `0x001180f8` 错误，因为 `mutexfree` 终止符留下 `0xf0000000`、`0xf` 顶半字节触发检查）。这在几何一致时甚至在 10 GB 上也会失败，证明被发射扰动的是 SEC2 / `0x001180f8` 的移交状态，不是几何布局、也不是写次数。提出过两个修复：让终止符把 `0x001180f8` 顶半字节留零，或从打过补丁的驱动内部分阶段做几何布局。**已发布的解锁器选了第二个。**

> [!NOTE]
> **不带 FLR 跨过 RmInitDone 墙**
>
> `whole_stack_rejoin` 终止符在利用后不带 FLR 重启 SEC2、让 booter 完成、GSP-RM RISC-V 核心启动，但 init 从不完成。这是同一个 `0x65` 引导墙。`0x001180f8` 是 `NV_PGC6_BSI_SECURE_SCRATCH_14`，位 26 是 `BOOT_STAGE_3_HANDOFF`（INIT = 0，DONE = 1），只有 HS 里的 SEC2 能设它。预写 DONE 没用：读路径被 PLM 下毒，所以 `0x001180f8` 回读 `0xdead5ec1`；而一次下毒读的上位 26 已经读成 1，产生一个假 DONE，之后反而杀死 GSP-RM。两个候选根修复是：保留 booter 成功路径，让 SEC2 启动它自己的 RTOS 并自设 DONE；或恢复 AON `SECURE_SCRATCH` PLM/priv 状态——而那今天只能靠一次功率域复位达成。

> [!NOTE]
> **移植到其它 CMP 卡**
>
> CMP 50HX 是 TU102、用一套完全不同的显存访问控制寄存器。CMP 90HX 是带 10 GB GDDR6X、没有额外物理显存的 GA102，所以只有算力解锁才有意义。既定规则是：同一个 Turing booter、脚本和利用适用于任何 SEC2 接受 Turing 代 AES 和 RSA 密钥的卡。一位测试者报告，TU10x `booter_load` 在一张 GA102 CMP 90HX 上加载、SS0/SS1 PLM 写成功，同时自我限定写入的值 "were not right"（不对）、并警告一次阳性测试不够。对 GA102 booter 的另一次独立静态分析得出结论：因为大小被严格验证，不存在溢出点。没人跑过决定性测试：在 GA102 上加载 TU10x booter，并尝试一次带回读的已知良好单 PLM 写。

> [!NOTE]
> **Windows 和非 Linux**
>
> 漏洞位于 GPU 固件里、不依赖 OS。当前实现是 Linux，而 Unix 主机或开源驱动都不是硬性要求，但一个 Windows 移植被描述为远不止几行工作。

> [!NOTE]
> **恢复一个 `csecret`**
>
> 三个索引映射到三个能力：`secret(6)` 解密 ECB 固件块（会产出 121.7 KB 明文固件加 Booter 代码）；`secret(2)` 伪造内容 MAC（那条路线的 CFG1 显存解锁和 PCIe 速度解锁两者的前提）；`secret(0)` 是启用带 `SKIP_VBIOS_SIG` 的 HULK 证书的调试绕过。**没有任何 csecret 被恢复过。** 三个都仍是需要电压毛刺硬件的差分故障分析目标。没有 **Booter 解密密钥**，加密的 booter 就无法重建（只能经调试密钥路线读取）；没有 **VBIOS 调试密钥**，VBIOS 就无法重新签名或进入调试模式。当前解锁通过把出厂的签名 booter 复用作执行引擎，绕开了这两者。

> [!NOTE]
> **同一 bug 类的第二个实例**
>
> 论文（第 5.5 节）指出，GSP-RM 自己的驻留块携带同一 bug 类的第二个实例，那里的守卫全局是一个**公开的硬编码常量**、而非 RNG 播种。没有发布地址、没有在其上构建利用、档案里也没人验证过它。

### 记录的否定结果

- **`envytools` 无法佐证任何这些。** 它的 Falcon 密码页有 Introduction、IO registers、Interrupts、"Submitting crypto commands: ccmd"、"Code authentication control" 和 "Crypto xfer control" 的小节标题，**每个都标着 "Todo: write me"**。没有关于 AES 引擎、密钥处理、签名代码认证、安全模式进出、代码页签名检查或任何 CMAC/CBC-MAC 方案的文档。记录下来，以免有人再搜。envytools 也只把 Falcon 硬件记录到 v5（GK208+）、不含任何 Ampere 或 GA100 覆盖；它的寄存器图（`UC_CTRL 0x100`、`UC_ENTRY 0x104`、`UC_CAPS 0x108`、`UC_STATUS 0x128`、`CODE_INDEX 0x180`、`CODE 0x184`、`DATA_INDEX[0-7] 0x1c0`、`SCRATCH0 0x040`）只是结构背景，**绝对不能**用来验证 GA100 寄存器地址。
- **通过返回到 IMEM `0x100` 的 `_start` 重新进入 booter**（带连续两个签名）被测试，并以邮箱里同样的 `0x31` 失败。`0x00` 处的轻度安全引导程序在 Falcon 进入 HS 模式时被抹掉，所以没有可返回的东西。
- **通过跳过 `secure_teardown` 收获活 SCP 机密** 在提出的当天就被两条对抗性逐字节静态迹线反驳：`0x107`-`0x147` 处的序言把每个机密立即自 XOR 成零、真正的密钥使用是 `0x1e20`-`0x1e70` 处的 AES 验证、`0x1e74`-`0x206e` 处的清理扫描连续三次背靠背自清零、最后一个密码操作是 `0x206e` 处的 `cxor $c0, $c0`。从 `0x2070` 到 `0x7eef` 有**零**个密码操作，而劫持点（`0x37b3` 处 `lcall 0x4d4`）恰好坐在那个密码静默缺口内。跳过节省不了什么，因为寄存器组在大约 0x1500 字节更早的代码处就已经空了。
- **逆向 booter 以获得 HS 签名特权** 被它自己的提议者放弃。即使从硅片提取 AES 密钥，RSA 私钥仍缺失：晶片只持有公钥。剩下的理论路线是启用调试模式并用调试 RSA 私钥，但一颗物理熔丝在量产卡上禁用调试模式，只有工程样品启用它。
- **主机侧 PCI 设备 ID 欺骗到 A100 ID（`0x20b0`）** 不可能：VBIOS/devinit 在驱动或 GSP 有机会之前就以卡级设备 ID 为键，而它对所有 GA100 卡甚至 Turing 卡都是同一个 booter，所以没有任何下游东西按主机 ID 分支。

---

## 相关页面

- [解锁如何工作，端到端](how-it-works.md)
- [ROP 链](rop-chain.md)
- [权限级别掩码](privilege-level-masks.md)
- [驱动补丁](driver-patches.md)
- [寄存器参考](register-reference.md) 和[寄存器索引](../appendix/register-index.md)
- [术语表](../start/glossary.md)
- [死路](../history/dead-ends.md)
