# 签名缓冲区溢出与 ROP 链

**本页覆盖内容。** 利用本身：SEC2 的 Booter Load 微码里无界的签名 DMA、栈金丝雀为何挡不住它、溢出所落的精确栈、gadget 词汇表、已发布的载荷的完整偏移量表，以及由此产生的任意 BAR0 写原语。Falcon、booter 映像和驱动调用序列的背景见[SEC2 Falcon 与 Booter Load 微码](falcon-and-booter.md)；该原语用来打开的掩码见[权限级别掩码](privilege-level-masks.md)。

**三句话的关键结果。** booter 用一个逐字取自主机提供字段、且没有任何边界检查的长度，把 GSP 签名复制进 DMEM；把该字段设为 `0xF800`，就会用攻击者选择的字节填满 DMEM `0x0800`..`0xFFFF`，包括栈金丝雀守卫全局、每个保存的金丝雀副本和每个保存的返回地址。由于 Falcon 是哈佛架构，溢出无法写入指令内存，所以结果不是代码注入，而是对厂商自签名微码的返回定向编程。已发布的驱动用这一点，在每次 Booter Load 发射中执行**恰好一次任意 BAR0 寄存器写**，并对它想触碰的每个寄存器各重发一次 booter。

---

## 1. 漏洞

被利用的缺陷是 Booter Load 的 LS 签名验证里一次无界 DMA。IMEM `0x29C4` 处的 `booterVerifyLsSignatures_TU10X` 执行 `lcall 0x0601`（`booterIssueDma_HAL`），DMEM 目的地固定、长度直接从 `WprMeta.sizeOfSignature` 取出。目的地由 IMEM `0x37ad` 处的 `mov $r10 0x800` 设置，传输经 IMEM `0x4d4` 的 `dma_copy_block` 进行、在 IMEM `0x37b3` 被调用。

| 字段 | 由谁控制 | 有界？ |
|---|---|---|
| 缓冲区内容 | 主机驱动（`pSignatureMemdesc`） | n/a |
| `WprMeta.sizeOfSignature` | 主机驱动 | **没有任何检查** |
| DMEM 目的地 | 固定在 `0x0800` | 固定 |

算术是精确的，也即整个利用：

```text
DMA 目的地  = DMEM 0x0800
已发布的长度    = 0xF800  （63,488 字节）
0x0800 + 0xF800  = 0x10000 = DMEM 顶部
```

> [!NOTE]
> **本页最重要的换算**
>
> **DMEM 地址 = 载荷偏移量 + `0x800`。** 等价地，载荷偏移量 = DMEM 地址减 `0x800`。载荷偏移量 `0xf754` **就是** DMEM `0xFF54`。载荷偏移量 `0x5b40` **就是** DMEM `0x6340`。引用 `0xF7xx` 偏移量的文档、与引用 `0xFFxx` DMEM 地址的文档，描述的是不同单位下的同一批字节，而不是两个不同的 booter 构建。一次把这种差异误读成分歧证据的出处审查是错误的。

两次独立的内部交叉检查确认了基址。其一，已发布的载荷在偏移量 `0x5b40` 写入假金丝雀，而 `0x5b40 + 0x800 = 0x6340`，正是独立确立的守卫全局。其二，偏移量 `0x1100` 映射到 DMEM `0x1900`，即有记录的 `f100` 字段保存槽。书面材料中 "highest tail slot 63448 (DMEM `0xFFD8`)" 和 "SP at `0xFF3C` for payload offset 63292" 在同一映射下精确复现。

> [!CAUTION]
> **溢出不提供代码执行**
>
> 指令活在 IMEM、数据活在 DMEM，位于两个独立的 16 位地址空间。签名 DMA 只落在 DMEM。攻击者控制的是 Falcon 调用栈上的返回地址集合，因此执行的每条指令都是已签名、已认证的 `booter_load` 映像的一个片段，任何时刻都不会运行未签名代码。早期一个 "overwrites IMEM" 模型已于 2026-06-30 被更正。

因为破坏发生在映像通过自己验证*之后*，脆弱的 booter 无法通过驱动更新来吊销：NVIDIA 签名并发布了该块，验证密钥又熔入硅片和不可变引导 ROM。对"不可吊销"这一说法的置信度为中等：关于不可变信任根的推理合理且无人挑战，但它从未针对加固驱动被经验演示过。

### 1.1 为什么复制长度之后不会被抓到

从溢出的 `0x4d4` 帧返回 `0x37b7`，会重新接入 booter 的真实映像验证（`0x2e80` 处的 `image_auth_decrypt`，AES 加 MAC，使用 `r2`..`r7` 里的 WprMeta 值）。那里的长度检查自然通过，因为已复制字节数（`0xF800`）等于 `WprMeta.sizeOfSignature`（`0xF800`）。这个过大的签名是自洽的。

### 1.2 实测的悬崖

机械溢出阈值是守卫减缓冲区：`0x6340 - 0x800 = 0x5b40`。

| 签名大小 | 溢出末尾 | 守卫 | 结果 |
|---|---|---|---|
| `0x5b00` | DMEM `0x6300` | 完好 | 卡引导。MB0 = `0x96`。 |
| `0x5b40` | DMEM `0x6340` | 恰好到达 | 实测的 panic 边界。 |
| `0x5c00` | DMEM `0x6400` | 被粉碎 | 中止。MB0 = `0x47`。 |
| `0xF800` | DMEM `0x10000` | 被粉碎，并被替换 | 利用。 |

`0x5B40` 边界通过在真实硬件上对载荷大小做二分搜索找到；`0x6340 - 0x5B40 = 0x800` 正是 DMA 基址最初被推导的方式。论文的 Falcon 仿真器界定了同一个阈值，并声明它与一次硬件长度扫描匹配。

16 KB 的 "overflow cliff" 由金丝雀全局坐在该点的 DMEM 造成，而非 booter 里任何大小检查。根本没有长度验证：booter 接受一切；一旦写入越过 DMEM `0x6340`，随机守卫被毁、每个返回函数都会 panic。由于 DMEM 是 16 位空间，在到达栈尾之前几乎可以写入 64 kB。

### 1.3 论文的仿真器迹线

2026 年 6 月预印本发布了同一个 booter 的 Falcon 仿真器迹线：

```text
REACHED SIG DMA: buffer=0x800 size=0xf800 overrun-end=0x10000 guard@0x6340

(A) 朴素非均匀签名，长度 0xf800：
    SIGSZ=0xf800 pc=0x7def spin=0x7def CANARY=True  MB0=0x47   <- 栈检查失败中止
(B) 带 V = 0x4a7 的均匀填充：
    SIGSZ=0xf800 pc=0x4a7  spin=0x4a7  CANARY=False MB0=0x31   <- 金丝雀通过，PC 被劫持到 V
```

`0x4a7` 和 `0xf800` 两者都逐字作为常量出现在已发布的内核补丁里。

---

## 2. 击败栈金丝雀

### 2.1 保护

Booter Load 里每个函数都受金丝雀保护。一个新鲜的高熵守卫字在 `_start` 阶段 9 被安装在 DMEM `0x6340`，取自 SCP 自配置后扫描 DMEM `0x6330`..`0x6340` 时找到的第一个非零字。每个受保护函数在进入时把它复制进自己的帧、退出时比较，一旦不匹配就调用 IMEM `0x7dd9` 处的 `__stack_chk_fail`。观察到的、来自一张真实 8 GB 卡的活金丝雀：DMEM `0xff94` 处 `0xcbee9c9f`、`0xffc4` 处 `0x3be0f4ab`、`0xfff4` 处 `0x941b798d`。三者各不相同，且每次启动都会随机生成。

`__stack_chk_fail` 完整如下：

`__stack_chk_fail` 完整地：

```asm
7dd9:  mov  $r15 0x6340
       ld b32 $r15 D[$r15]
       add  $sp -0x4
       mov  $r9 $sp
       st b32 D[$r9] $r15
       mov  $r15 0x47
       mov  $r9 0x1000        ; CSB MAILBOX0
       iowrs I[$r9] $r15
7def:  lbra 0x7def            ; 永远旋转
```

跳到 `0x7de9` 而非 `0x7dd9`，会把 `$r15` 里的任何东西打印到邮箱；这是项目期间构建的每个调试 ROP 的基础。

### 2.2 为什么它无效

守卫全局活在可写数据内存里，恰好被它要检测的那个溢出所可达。

> [!NOTE]
> **靠一致性而非预测来击败**
>
> 载荷用同一个值 `V` 覆写 DMEM `0x6340` 处的守卫全局**和**栈上每个保存-金丝雀槽。于是每个尾声都计算 `V == V`、通过，并返回进链。该值是任意的，保密性和熵都无关紧要。每次启动从硬件 RNG 重新播种守卫提供不了任何保护，因为对手根本不需要知道它。

没有 RELRO 等效、没有守卫页、也没有 MPU 只读映射。在论文仿真器里，种子只作为固定常量出现，因为密码协处理器被桩掉了。

### 2.3 哪个值

> [!CAUTION]
> **已发布的守卫值是 `0xc0deca7e`。它不是 `0xFACEB13D`。**
>
> `0xc0deca7e` 在已发布的载荷里恰好出现五次，在载荷偏移量 `0x5b40`、`0xf758`、`0xf794`、`0xf7a0` 和 `0xf7c4`（DMEM `0x6340`、`0xFF58`、`0xFF94`、`0xFFA0`、`0xFFC4`）。字符串 `FACEB13D` 在已发布的树或 12 个归档分支的任何一个里**任何地方都不出现**。任何把 `0xFACEB13D` 当作"那个"金丝雀值的文档描述的都是净室研究链，不是发布的解锁器。

| 值 | 它在哪里正确 |
|---|---|
| `0xc0deca7e` | 已发布的 `cmpunlocker` 驱动，master 和全部 12 个分支，逐字节相同 |
| `0xFACEB13D` | 净室研究载荷和无驱动工具，2026-07-04 采纳的约定 |
| 守卫地址 `0x6340` | **两者。** 这是承重事实。 |

`0xFACEB13D`（"fake bird"）在 `0xDEADC0DE` 和 `0xCAFEBABE` 被拒绝（过度使用、且可能存在于 NVIDIA 自己的代码里，那会让 DMEM 转储读起来有歧义）之后被采纳为约定。由于机制与值无关，两个标记都有效。

金丝雀复制槽在两条谱系之间也不同：研究链用 DMEM `0xFF58`、`0xFF94`、`0xFFDC`、`0xFFF4`；已发布的链用 `0xFF58`、`0xFF94`、`0xFFA0`、`0xFFC4`。

### 2.4 指针别名替代方案

`0x10b9` 多写链用的技巧完全不同：给 gadget 喂常量 `0x6340` 作为两个操作数槽里的*指针*，于是比较会加载 `D[0x6340]` 两次、并把它与自身比较。Gadget `0x1fb9` 是 `ld b32 $r15 D[$r1]; ld b32 $r9 D[$r2]; mov b32 $r11 $r10; mov b32 $r10 $r0; cmp b32 $r15 $r9; bra e 0x1fca`，所以当 `r1 = r2 = 0x6340` 时比较平凡地相等、守卫值为 0 也可接受。已发布的驱动则改回植入一个匹配的字。

### 2.5 填充 dword

`0xF800` 缓冲区的每个 dword 先被写入 `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7U`（15,872 个 dword），只有在那之后特定槽才被覆盖。`0x4a7` 不是任意的：IMEM `0x000004a7` 是一个自循环。

```asm
000004a7:  3e a7 04 00    B lbra 0x4a7
```

如果被劫持的 PC 落在任何未打算处，Falcon 会停靠在一个可观察的重度安全自循环里，而不是游荡进故障。这算一个诊断，而非功能要求，但已发布的驱动恰恰为此保留它。

---

## 3. 溢出落上的栈

溢出时刻 booter 有六帧深。这个布局通过一次对一张 8 GB 卡真实栈的逐字外泄（跨 35 次引导）重建，并独立从反汇编推导。仅靠手动重建曾失败，因为 `0x4d4` 处的 `dma_copy_block` 从至少 20 处被调用。

| DMEM | 内容 | 帧 |
|---|---|---|
| `0xFF3C` | 溢出时的 SP；保存的 r6 = `sizeOfRadix3Elf` | `0x4d4 dma_copy_block` |
| `0xFF40` | 保存的 r5 = `gspFwWprStart[63:32]` | |
| `0xFF44` | 保存的 r4 = `bootBinOffset[31:0]` | |
| `0xFF48` | 保存的 r3 = `sizeOfBootloader` | |
| `0xFF4C` | 保存的 r2 = `gspFwWprStart[31:0]` | |
| `0xFF50` | 保存的 r1（被设成 `0x600`，WprMeta 指针） | |
| `0xFF54` | 保存的 r0 | `mpopaddret $r6` pop 块的末尾 |
| `0xFF58` | 金丝雀副本（SP + `0x1c`） | |
| **`0xFF5C`** | **返回地址。ROP 入口点。** 出厂值 `0x37b7`。 | |
| `0xFF60`-`0xFF90` | 帧主体，保存的 r2-r7 = WprMeta FB 地址 | `0x3747 image_copy_verify` |
| `0xFF94` | 金丝雀 | |
| `0xFF98` | 返回地址 `0x2740` | |
| `0xFF9C`-`0xFFD0` | 帧主体（`$sp = 0xFF9C`） | `0x22ba booter_load_wpr_main` |
| `0xFFC4` | 金丝雀 | |
| `0xFFD4` | 返回地址 `0x814e` | |
| `0xFFD8` / `0xFFDC` | wrap 帧主体 | `0x8137 booter_load_wrap` |
| `0xFFE0` | 返回地址 `0x80d7` | |
| `0xFFE4`-`0xFFFC` | `main` 的帧 | `0x7f82 main` |
| `0xFFEC` | finalize 局部 `D[sp+8]`，出厂值 `0x1` | 喂 `0x001180f8[31:28]` |
| `0xFFF0` | `D[sp+0xc]`，出厂 `0x0c000000` | |
| `0xFFF4` | `main` 的金丝雀 | |
| `0xFFF8` | 返回地址 `0x4d0`（`_start` 退出） | |

实测的 580 booter 原始栈，从真实硅片外泄：

```text
0xff74=0x0        0xff78=0x0        0xff7c=0x0        0xff80=0x8
0xff84=0x600      0xff88=0x0        0xff8c=0x600      0xff90=0x0
0xff94=0xcbee9c9f 0xff98=0x2740     0xff9c=0xfff00000 0xffa0=0x1
0xffa4=0x8        0xffa8=0x8        0xffac-0xffc0=0x0 0xffc4=0x3be0f4ab
0xffc8=0x8700     0xffcc=0xb99e21e  0xffd0=0xd6a262d  0xffd4=0x814e
0xffd8=0xf4bbdeaa 0xffdc=0x98cf4f20 0xffe0=0x80d7     0xffe4=0x0
0xffe8=0x81664b1d 0xffec=0x1        0xfff0=0xc000000  0xfff4=0x941b798d
0xfff8=0x4d0      0xfffc=0x0
（部分，较低：FF60=0x1, FF64=0x520）
```

那份转储作者陈述的两个注意事项：`0xffd8` 实际是保存的 r0，所以那里的 "canary" 标签是错的；`FF68`/`FF70` 无法恢复，因为外泄 ROP 自己占用那些槽。

### 3.1 证明入口点

被劫持的返回地址通过对邮箱的一次受控实验被证明：带一个通常产生 MB0 = `0x31` 的大溢出，把载荷字节 63324-63327 换成 `panic()` 地址把邮箱改成 `0x47`。偏移量 63324 = `0xF75C`，而 `0xF75C + 0x800 = 0xFF5C`。

### 3.2 每次引导必须打补丁的五个字

五个栈字持有活 WprMeta 值，被溢出毁掉、恢复路径上没有任何东西重新推导它们。

| DMEM | 寄存器 | WprMeta 字段 | 载荷偏移量 |
|---|---|---|---|
| `0xFF3C` | r6 | `sizeOfRadix3Elf` | 63292 |
| `0xFF40` | r5 | `gspFwWprStart[63:32]` | 63296 |
| `0xFF44` | r4 | `bootBinOffset[31:0]` | 63300 |
| `0xFF48` | r3 | `sizeOfBootloader` | 63304 |
| `0xFF4C` | r2 | `gspFwWprStart[31:0]` | 63308 |

r7 里的 `gspFwOffset` 自动保留、不被注入。真实值在 IMEM `0x3768`-`0x3777` 计算（例如 `ld $r2 D[$r10+0x70]`、`ld $r6 D[$r10+0x18]`），由 `0x4d7` 处 `mpush $r6` 溢出到栈、由 `0x5ff` 处 `mpopaddret $r6` 恢复。因为 RM 每次引导都会把 WPR2 重新分配到一个新鲜 FB 地址（某次运行是 `0x277700000`，对比一个陈旧的烘焙进 `0x1_f7700000`），静态捕获无法复用。

DMEM `0x600` 处的 `WprMeta` 结构本身从不会被覆盖，因为它在 `0x700` 结束、低于 `0x800` DMA 目标；而恢复路径确实会重读它：`0xFF50` 处的 pop 槽被设为 `0x600`，返回后 `0x37b7` 立即执行 `ld $r9 D[$r1+0x50]`。只有 r2-r6 是无法重新推导的帧恢复副本。

> [!NOTE]
> **未解问题：WprMeta 溢出的寄存器分配**
>
> 三个来源里有两个给出 `0xFF3C` = 保存的 r6 = `sizeOfRadix3Elf 0x01d09ea0` 和 `0xFF4C` = 保存的 r2 = `gspFwWprStart 0xf7700000`。第三个给出相反的读法、且内部混乱。上面采用多数读法。通过重读 `0x22ba` 序言里的 pop 顺序来定论。

---

## 4. Falcon 栈机制

把这些搞错会静默杀死一条链，通常死在 `__stack_chk_fail`。

- **`mpush $rN` 在最高地址先推 r0**，递减到最后在 SP 所指的最低地址推 rN。`mpop` / `mpopaddret` 是严格 LIFO：rN 先出最低槽、r0 最后出最高槽。要给一个块里顶字位于地址 T 的 rK 植入值，把它写在 `T - 4*K`。
- **`mpopaddret $rN imm`** 恢复 `$r0` 到 `$rN`；立即数保留通常持栈金丝雀的额外字节，返回地址在其上。总 SP 前进是 `(N+1)*4 + imm + 4`：`$r6 0x4` 形式前进 SP `0x24`（9 个 dword：r0-r6、一个保留 dword、返回地址）、结束 `0x10aa` 的 `$r3 0x4` 形式 `0x18`、`$r2 0x4` 形式 `0x14`（5 个 dword）。已发布的载荷修好了全部三个：`0x4d4` 尾声让 SP 停在 `0xFF60`、`0x0cc8` `$r3` 尾声从 `0xFF74`（`0x00001fbd`）取返回地址、`0x1fca` `$r2` 尾声从 `0xFF88`（`0x000010aa`）取返回地址。硅片 `0x47` 邮箱探针记录的 `0x20` 和 `0x10` 数字数的是寄存器块加立即数，却够不到返回地址 pop。envytools 对 `mpopaddret` 完全没有文档条目，只有 `ret`。
- **栈指针可以前进，但永远不能回退。** 每个函数尾 `ret` 或 `mpopaddret` 都会递增它，且从 `$sp+4` 到 `$sp+40` 的每个增量都有一个对应的存在。裸 `ret` 把 `$sp` 递增 4。**booter 里不存在降低 SP 的 gadget**：`mov $sp $r9` 只出现在 `_start`（它重跑引导）里，所有 `mpush` / `add $sp -N` 形式也都活在函数序言内。
- **booter 在进入时清除 r0-r16**，所以链必须在单次加载内建立全部自己的寄存器状态。置信度：中等；与工作链设计一致，但从未单独确认。
- **`r0`-`r8` 是栈可 pop 的；`r9`-`r15` 不是。** `mpopaddret $rN` 从不超 N = 8。这正是逼出 elevator gadget 的约束，因为写引擎在 `r10`/`r11` 里取参数。

来自机器生成 gadget 图集的 setter 计数（mov / ld / zero），通过一次对 `booter_load_ga100_dbg_seccode.fuc5.asm` 的跨过程可达分析构建，只在目标寄存器在 `ret` 时仍持有 set 值才列出 gadget：

| Reg | mov | ld | zero | | Reg | mov | ld | zero |
|---|---|---|---|---|---|---|---|---|
| r0 | 78 | 2 | 3 | | r8 | 3 | 0 | 2 |
| r1 | 23 | 3 | 5 | | r9 | **0** | 131 | 0 |
| r2 | 25 | 4 | 2 | | r10 | 48 | - | 28 |
| r3 | 17 | 6 | 0 | | r11 | 6 | 3 | 9 |
| r4 | 15 | 4 | 2 | | r12 | 7 | 11 | 2 |
| r5 | 10 | 5 | 2 | | r13 | 10 | 6 | 5 |
| r6 | 3 | 5 | 1 | | r14 | 18 | 10 | 22 |
| r7 | 2 | 3 | 0 | | r15 | **0** | 131 | 0 |

几乎每条 gadget 路径都跑一个要求 `r15 == r9` 的金丝雀比较。图集记录了三类前提：`canary(r15==r9)`、`via-call`（路径执行一个验证过不篡改目标、但自己仍需状态的真实子函数）、和 `data-branch`（路径上有一个对寄存器值的条件分支）。可达分析保证的是寄存器被*保留*，而非任意值可达：`derefs-r11` 意味着 r11 被用作指针、必须是一个有效可写的 DMEM 地址。只有少数 gadget 完全没有前提，例如 `0x19bc`（`$r3 <- $r12`，终止符 `ret`）。

从二进制提取的多 pop 入口点：

| Pop 到 | 地址（部分） |
|---|---|
| `$r0` | `0x1ba0`、`0x1c0b`、`0x1cde`、`0x1d9f`、`0x202d`、`0x2089`，加 10 个 |
| `$r1` | `0x0bc6`、`0x0c79`、`0x1061`、`0x1218`、`0x1443`、`0x1547`，加 18 个 |
| `$r2` | `0x09d7`、`0x0b25`、`0x0ef0`、`0x0f88`、`0x12e7`、`0x1fca`，加 6 个 |
| `$r3` | `0x0b99`、`0x0cc8`、`0x0f36`、`0x10ff`、`0x13a4`、`0x21f1`，加 7 个 |
| `$r4` | `0x08fe`、`0x0a9e`、`0x2a62`、`0x3b53`、`0x4765`、`0x7c62`，加 1 个 |
| `$r5` | `0x0d63`、`0x0e49`、`0x1b41`、`0x29b5`、`0x7a61`、`0x85ce`，加 1 个 |
| `$r6` | `0x05ff`、`0x07d9`、`0x28a9`、`0x4674`、`0x60c5` |
| `$r7` | `0x38c3`、`0x7977`、`0x84cd` |
| `$r8` | `0x071a`、`0x22b7`、`0x3743`、`0x3c8c`、`0x4484`、`0x5ccb`，加 2 个 |

另一个已测试并确认的机械属性：**ROP 栈可以合法地延伸过 DMEM `0xFFFF` 并回绕到 `0x0000`**，所以链长不受 DMEM 顶部限制。它并没有修好它被提出的那个 `0x65` 错误。一个竞争的、更晚的分析认为，当几何写把栈移位时，被推过 `0xFFFF` 的 finalize 局部 "wraps and becomes uncontrollable"（回绕并变得不可控）。两者可能对不同槽都成立；没人陈述过边界，所以把回绕视为对链扩展可用、对 `main` 必须回读的值则不可用。

---

## 5. 任意 BAR0 写原语

### 5.1 引擎

IMEM `0x10aa` 处的 `reg_write_indirect` 就是整个原语。它的开源驱动符号是 `_acrlibBar0RegWrite_TU10X`，而且它**与** Turing acrlib 里 `0xd10` 处的那个例程**逐字节相同**：并排看，编码匹配（`f4 30 fc / f9 32 / 83 40 .. 00 / bf 39 / b2 a0 / b2 b1 / fe 42 01 / 90 22 10 / a0 29 / …`），只在金丝雀 DMEM 地址（GA100 上 `0x6340`，对 TU10X 上 `0x940`）和调用目标上不同。正是这样识别它，才找到了原语。

它按序做什么：

1. 从 `D[0x6340]` 把金丝雀载入 `$r9`（`mov $r3 0x6340`、`ld b32 $r9 D[$r3]`）。
2. `0x10b5` / `0x10b7`：`mov b32 $r0 $r10`、`mov b32 $r1 $r11`（编组参数）。
3. 从 `0x10b9`：把金丝雀保存到栈（`mov $r2 $sp`、`add $r2 0x10`、`st D[$r2] $r9`），然后用 `lcall 0x1064`（`mailbox_wait_ready`）获取邮箱互斥锁。
4. `csb_write(I[0x1c100] = 地址)`、`csb_write(I[0x1c200] = 值)`、`csb_write(I[0x1c000] = 0x800000f2)`，全部经 `0x8224` 的 `csb_write`。
5. 回读 `0x1c000`，再次等 ready。
6. 把保存的金丝雀与 `D[0x6340]` 验证。
7. 经 `0x10ff` 的 `mpopaddret $r3 0x4` 返回。

`0x1064` 处的 `mailbox_wait_ready` 轮询 `I[0x1c000]` 位 [14:12]：0 = 完成、1 = 继续旋转、其它任何值 = 错误 `0x15` 然后退出。读侧对应物是 `0x1196` 处的 `reg_read_indirect`，命令字 `0x800000f1`。

### 5.2 两个入口点、两种寄存器约定

这调和了源材料里一个长期表面矛盾。

| 入口 | 参数 | 谁用 |
|---|---|---|
| `0x10aa`（完整） | `r10` = 目标 BAR0 地址，`r11` = 值 | **已发布的驱动。** |
| `0x10b9`（中途） | `r0` = 地址，`r1` = 值 | 无驱动 `refire_chain*.py` 工具。 |

从 `0x10b9` 进入会跳过 `0x10b5`/`0x10b7` 的 `mov r0,r10` / `mov r1,r11` 复制，所以 ROP 可以直接从栈提供操作数。两个入口都到达同一个 `iowrs I[0x1c…]` 存储。源材料里的两个描述对它们各自的入口点都正确。

> [!CAUTION]
> **已发布的载荷用 `0x000010aa`，不是 `0x10b9`**
>
> 值 `0x000010aa` 被写在 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 的载荷偏移量 `0xf788`（DMEM `0xFF88`），而字符串 `10b9` 在已发布的树或 12 个分支的任何一个里**任何地方都不出现**。任何声称 "0x10b9" 被"每个工作载荷使用、包括编译进已发布的驱动补丁的那个"的说法都自相矛盾，在此予以更正。`0x10b9` 自链只是净室和无驱动工具构建，仅此而已。

### 5.3 代价

| 路径 | 每次写的栈 | 备注 |
|---|---|---|
| `0x10aa` 完整入口 | `+0x10` 的 main-SP 移位 | 已发布的。需要 elevator 加载 r10/r11。 |
| `0x10b9` 中途入口 | `+0x18` = 每写 24 字节 | 经 `mpopaddret $r3 0x4` 尾声自链。帧形状 `[r0=canary addr][r1=0][r2=value][r3=address][canary][RA]`。 |
| `0x8224` `csb_write` 直接 | 每写约 `0x60` 字节 | 有效，但需要对每个寄存器手搓地址、数据、命令和轮询。更多帧却无收益。 |

`+0x10` 对比 `+0x18` 的数字来自一次 2026-07-06 的分析、携带中等置信度。

`csb_write` 本身是一个可用的直接写 gadget、值得一读，因为它也展示了 fail-closed 惯用语：

```asm
8224:  add $sp -0x4
8228:  ld b32 $r15 D[$r15]
822a:  add $sp -0x4
822d:  mov $r9 $sp
8230:  st b32 D[$r9] $r15
8232:  iowrs I[$r10] $r11        ; 写到 Falcon I/O，而非外部 BAR0
8235:  mov $r9 0x9100
8239:  iords $r9 I[$r9]
823c:  shr b32 $r9 0x1f
823f:  bra b32 $r9 0x1 ne 0x824b
8243:  mov $r10 0x15
8245:  lcall 0x1d0f
8249:  exit
```

从链里调用 `0x8224` 的正确 elevator gadget 是 `0x1fb9` 和 `0x1fbd`。

### 5.4 首次演示

任意 BAR0 寄存器写从一条 HS ROP 链首次于 2026-07-03 在真实 8 GB 硅片上演示：寄存器 `0x0014a0` 从 `0x00000000` 变为 `0xcafebabe`，邮箱读到 `0x47`，因为链故意终止在 `panic()`。第二位研究者独立报告，能把任意字节写到任意 I/O 地址，通过写到 `0x1000` 并观察它出现在邮箱里加以验证。

> [!WARNING]
> **回读不是免费的**
>
> PL0 的主机无法回读其中许多寄存器，返回 `0xbadf5040` / `0xbadf50xx`。那是权限阻止的读指示，**不是**存储的毒值。对一次 HS 写的回读验证，需要 Falcon 内的读 gadget `0x1196` 或主机可见的邮箱别名。一旦相关 PLM 打开，主机就能正常读取——这正是已发布的驱动所依赖的。

### 5.5 原语能到达哪些寄存器

确认能工作：FEAT PLM `0x00823804`；WPR2 `0x001FA824`；以及在已发布的驱动里，WPR_CFG `0x001fa7cc` 打开到部分值 `0xfffff0ff`、FBPA `0x009a0148` 和 WPR `0x001fa7c4`。

> [!NOTE]
> **未解问题：邻居 WPR 寄存器上报告的失败**
>
> 一份单一来源的列表报告：那次测试时，对 WPR1_HI `0x001FA820`、WPR1_LO `0x001FA81C` 和 WPR_Mask `0x001FA7CC` 的写被确认*不*工作；而已发布的驱动却通过同一个原语成功打开 `0x001fa7cc`。要么更早的测试用了不同的值或不同的链，要么 `0xfffff0ff` 的部分打开恰好在完整 `0xffffffff` 打开失败的地方成功。对这份失败列表的置信度：中等。可通过一次尝试 `0x001fa7cc = 0xffffffff` 并回读的发射来定论，连同更早测试的精确载荷。

一个独立于原语的结构性限制是真实存在的：SEC2 ROP 只打开其 `SOURCE_ENABLE` 字段把 sec2-HS 列入白名单的 PLM。观察到 `0x00823b00` 因此拒绝链。见[权限级别掩码](privilege-level-masks.md)。

---

## 6. Gadget 词汇表

下面每个地址都是 **IMEM**，每个都是同一个已签名 `booter_load` 映像的一个片段。

| IMEM | 它是什么 | 在链中的角色 |
|---|---|---|
| `0x04a7` | `lbra 0x4a7` 自循环 | 填充 dword；停在 HS 的旋转停靠 |
| `0x04d0` | `_start` 退出 | 终止符 |
| `0x04d4` | `dma_copy_block` | 溢出的帧；`0x5ff` 处尾声 `mpopaddret $r6` |
| `0x0cbd` | `regblock_read_guarded (0x0c7c)` 里的 `mov $r10 $r0` | Elevator |
| `0x0ccb` | `regtable_rw_indexed`，以 `mpopaddret $r5 0x8` 结束 | 也被读作与 `0xd66` 获取配对的 ACR 互斥锁释放 |
| `0x10aa` | `reg_write_indirect` 完整入口 | **写**（r10 = 地址，r11 = 值） |
| `0x10b9` | 中途入口 | 自链写（r0 = 地址，r1 = 值） |
| `0x10ff` | `mpopaddret $r3 0x4` | `0x10aa` 的尾声；让写自链 |
| `0x1b41` | `mpopaddret $r5 0x4` | |
| `0x1b44` | `set_1180f8_bit24()` | Pop 四个字；重入链里的免互斥 gadget |
| `0x1c0e` | `set_1180f8_top_nibble()` | Finalize；经 `0xccb` 调用释放 ACR 互斥锁 |
| `0x1d9f` | `mpopaddret $r0 0x4` | 栈吞噬器 |
| `0x1fb9` | `ld $r15 D[$r1]; ld $r9 D[$r2]; mov $r11 $r10; mov $r10 $r0` | Elevator + 金丝雀别名 |
| `0x1fbd` | `read_820344_820348 (0x1f92)` 里的 `mov $r11 $r10; mov $r10 $r0` | **Elevator。** 已发布的载荷里用 3 次。 |
| `0x1fca` | pop `$r0,$r1,$r2` | Elevator 喂入 |
| `0x22ba` | `booter_load_wpr_main` | 重接 |
| `0x27fa` | `0x22ba` 内的重接点 | 见死路 |
| `0x28a9` | `mpopaddret $r6 0xc` | |
| `0x2d5a` / `0x2d75` | memcpy 蹦床（`$r12 = 0x10`、`lcall 0xe85`） | DMEM 外泄 |
| `0x582d` | `pka_ready_check (0x580f)` 内：把 `$r0 -> $r12`、调用 `regblock_read_guarded` | 尾 |
| `0x7de9` | `__stack_chk_fail` 内 | 把 `$r15` 打印到 MAILBOX0。每个调试 ROP。 |
| `0x7dd9` | `__stack_chk_fail` 入口 | 写 `0x47`，挂起 |
| `0x7e76` | `secure_teardown` | 永不返回；它后面什么都不能追加 |
| `0x7f2f` | `secure_teardown` 里的退出 gadget | **已发布的终止符** |
| `0x810d` / `0x8119` / `0x8137` | `main` / `booter_load_wrap` 里的站点 | 重接 |
| `0x814e` | 返回进 `booter_load_wrap` | 轻重接 |
| `0x815a` | 金丝雀检查尾 / 栈吞噬器 | 已发布的载荷里用 2 次 |
| `0x8224` | `csb_write` | 直接 Falcon-I/O 写 |
| `0x8262` | 裸 `ret` | 对齐填充 |
| `0x8e18` | clean-tail 展开 gadget | |
| `0xffbc` | 中间展开 gadget | |

> [!NOTE]
> **未解问题：几个已发布的尾字实际做什么**
>
> `0x00000cbd`（两次）、`0x00008e18`、`0x0000ffbc`、`0x0000582d`、DMEM `0xFFD8` 处 `0x00000003`、和两个 `0x0000815a` 条目没有发布的 gadget 注释。光按地址范围看，`0x0000ffbc` 和可能 `0x00008e18` 看起来像 DMEM 指针操作数而非 IMEM 代码地址，因为 booter 映像跑到约 `0x8200`；那是推断，未确立。也无法解释：DMEM `0x1900` 处 `0x00000007` 超出它的 resetPLM 作用，以及填充 dword `0x000004a7`。下一步：对这些地址跑现有的 `register_gadget_atlas.md` 生成器，因为图集格式已经记录前提和终止符。对带注释清单过一次应该能解决全部。

一个在硅片上确认能工作的最小调试 ROP，把 DMEM `0x800`-`0x804` 打印到邮箱然后挂起（gadget `0x0bc6`、`0x0bb9`、`0x7de9`）：

```text
c6 0b 00 00  00 08 00 00  00 08 00 00  55 55 55 55
b9 0b 00 00  55 55 55 55  55 55 55 55  55 55 55 55
e9 7d 00 00
```

放在载荷偏移量 **63324**；金丝雀必须在 **23360** 和 **63320** 处理。`0x55555555` 是可区分的填充，不是假金丝雀。

---

## 7. 已发布的载荷，逐字节

由 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 里的 `_kgspSec2PostblTimingFillPayload()` 生成。缓冲区的每个 dword 被设为 `0x000004a7`，然后 **24** 个 dword 用 `_kgspSec2PostblTimingPutU32()` 植入。

| 载荷偏移量 | DMEM | 值 | 角色 |
|---|---|---|---|
| 全部 | `0x0800`-`0xFFFF` | `0x000004a7` | 填充 / 旋转停靠 |
| `0x1100` | `0x1900` | `0x00000007` | `f100_field_save_restore` 门；让 resetPLM 停 `0xff` |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **守卫全局本身** |
| `0xf754` | `0xFF54` | *writeValue* | BAR0 写数据参数 |
| `0xf758` | `0xFF58` | `0xc0deca7e` | 帧金丝雀 |
| `0xf75c` | `0xFF5C` | `0x00000cbd` | **第一个返回地址**（elevator） |
| `0xf76c` | `0xFF6C` | *writeAddr* | BAR0 写地址参数 |
| `0xf774` | `0xFF74` | `0x00001fbd` | elevator |
| `0xf780` | `0xFF80` | `0x00000000` | |
| `0xf788` | `0xFF88` | `0x000010aa` | **写 gadget** |
| `0xf78c` | `0xFF8C` | `0x0000815a` | 尾基址 |
| `0xf790` | `0xFF90` | `0x00008e18` | |
| `0xf794` | `0xFF94` | `0xc0deca7e` | 帧金丝雀 |
| `0xf798` | `0xFF98` | `0x0000815a` | |
| `0xf79c` | `0xFF9C` | `0x00000000` | |
| `0xf7a0` | `0xFFA0` | `0xc0deca7e` | 帧金丝雀 |
| `0xf7a4` | `0xFFA4` | `0x00001fbd` | elevator |
| `0xf7b0` | `0xFFB0` | `0x0000ffbc` | |
| `0xf7b8` | `0xFFB8` | `0x0000582d` | |
| `0xf7c4` | `0xFFC4` | `0xc0deca7e` | 帧金丝雀 |
| `0xf7c8` | `0xFFC8` | `0x00000cbd` | |
| `0xf7d8` | `0xFFD8` | `0x00000003` | |
| `0xf7e0` | `0xFFE0` | `0x00001fbd` | elevator |
| `0xf7f4` | `0xFFF4` | `0x00000ccb` | ACR 互斥锁释放（有争议的读法） |
| `0xf7f8` | `0xFFF8` | `0x00007f2f` | **终止符，进 `secure_teardown`** |

十三个不同的非金丝雀、非操作数字出现：`0x4a7`、`0x7`、`0xcbd`（×2）、`0x1fbd`（×3）、`0x0`（×2）、`0x10aa`、`0x815a`（×2）、`0x8e18`、`0xffbc`、`0x582d`、`0x3`、`0xccb`、`0x7f2f`。

> [!NOTE]
> **处处逐字节相同**
>
> 这个载荷在已发布的 `master` 和全部 12 个归档分支之间相同：同样的 24 个 `PutU32` 调用、同样的偏移量、同样的值，通过校验和与 grep `0xc0deca7eU` 验证，它在每份副本里恰好出现 5 次。它在 `clanker_driver-port` 分支的 580、590、595 和 610 移植补丁集之间也逐字节相同。只有 PLM 表在分支之间不同，而 `80` 分支只改 10 GB 卡的 CFG1 和 `targetFbBytes`。

### 7.1 控制流

链很短。一次写、一次干净退出。

```text
0x4d4 dma_copy_block 尾声（mpopaddret $r6）
   pop r0..r6 从 DMEM 0xFF3C..0xFF54，然后从 0xFF5C 取 RA
        |
        v
0x0cbd   mov $r10 $r0          -> r10 = writeValue  （从 DMEM 0xFF54 加载）
        |
        v
0x1fbd   mov $r11 $r10         -> r11 = writeValue
         mov $r10 $r0          -> r10 = writeAddr   （从 DMEM 0xFF6C 重载）
        |
        v
0x10aa   reg_write_indirect(r10 = 地址, r11 = 值)
         I[0x1c100] = addr ; I[0x1c200] = value ; I[0x1c000] = 0x800000f2
        |
        v
0x815a -> 0x8e18 -> 0x1fbd -> 0xffbc -> 0x582d -> 0xcbd -> 0x1fbd -> 0xccb -> 0x7f2f
         （0x70 字节干净退出尾，结束在 secure_teardown 内）
```

置信度：高，通过把已发布的载荷的槽分配对照 `0xcbd`、`0x1fbd` 和 `0x10aa` 的反汇编寄存器流追踪推导。

### 7.2 尾

干净退出尾是一个固定 `0x70` 字节（112 字节）的 gadget 块，相对终止符槽摆放。用工具链的 `_TAIL` 字典、带 `_TAIL_END = 0x70` 表达：

```python
_TAIL = {0x00: 0x815a, 0x04: 0x8e18, 0x08: 0,      0x0c: 0x815a,
         0x10: 0,      0x14: 0,      0x18: 0x1fbd, 0x24: 0xffbc,
         0x2c: 0x582d, 0x38: 0,      0x3c: 0xcbd,  0x4c: 0x3,
         0x54: 0x1fbd, 0x68: 0xccb,  0x6c: 0x7f2f}
```

在已发布的载荷里，终止符槽基址是载荷偏移量 `0xf78c`（DMEM `0xFF8C`），尾跑到 `0xf7fc`（DMEM `0xFFFC`）；它写到的最高 dword 位于 `0xf7f8` = 63,480，结束于 63,484——在 63,488 字节缓冲区里四字节处。工具链列成 `0` 的 `+0x08`、`+0x14` 和 `+0x38` 槽是金丝雀槽，在已发布的载荷里携带 `0xc0deca7e`。

这个尾在无驱动工具里标为 HW-PROVEN、在 `refire_chain_v6.py` 和 `refire_chain_v9.py` 之间相同、并精确匹配已发布的载荷。

> [!NOTE]
> **谱系，精确地**
>
> *尾* 与 `refire_chain_v6._TAIL` 逐字节相同，`p(0x1100, 0x7)` 也匹配。*头* 则不是：v6 在载荷 `0xF750`/`0xF754` 相邻植入值和地址、RA `0x10b9` 在 `0xF75C`；而已发布的在 `0xf754` 植入值、RA `0x00000cbd` 在 `0xf75c`、地址在 `0xf76c`、`0x1fbd` 在 `0xf774`。谱系是真实的，但 "byte-for-byte the same chain" 是夸大其词。另外，已发布的载荷的两个 gadget 地址（`0x10aa` 和 `0x0ccb`）出现在补丁发布前三天发布的一篇社区 ROP 写作里、角色匹配。已发布的载荷是从社区链派生还是独立产生，光靠工件无法定论。

### 7.3 为什么退出是干净的

尾**穿过** `secure_teardown` 退出而非绕过它，却仍让 SEC2 复位 PLM 停在 `0xff`、而非通常的 `0x8f` 污染。机制是种在 DMEM `0x1900` 的 `0x00000007`：它路由经 IMEM `0x1d3b` 的 `f100_field_save_restore`——对寄存器 `0xf100` 位 [4:6] 的一次读-改-写，`r0 == 0` 时把字段保存到 DMEM `0x1900` 并清除它、`r0 != 0` 时从 `0x1900` 恢复它。寄存器 `0xf100` 在 PL0 处读到 `0xbadf5040`，因为它只在 HS teardown 上下文内可达。

> [!NOTE]
> **未解问题：`secure_teardown` 的主体实际执行吗？**
>
> `0x7f2f` 被描述为"`secure_teardown` 里的退出 gadget，从未被返回到"。完整 teardown 主体（SCP 清除、64 KB DMEM 清零、GPR 清除）是否在 `exit` 之前执行，还是 `0x7f2f` 落在它大部分之后，在档案里任何地方都没确立。这要紧，因为发射之间一次完整的 DMEM 清零会改变能携带过去的状态。定论方式：检查 `0x7f2f` 相对 SCP 清除和 DMEM 清零循环在 `secure_teardown` 主体内的字节偏移量。

> [!NOTE]
> **未解问题：已发布的载荷里的 `0x00000ccb`**
>
> 同一个调用的两种读法并存："`0xccb` 处的释放调用"（与 `0xd66` 获取配对）对比 "由 authenticate 置位位 24"。独立地，一条硬约束被陈述：没有 ROP 退出路径可以路由经 `regtable_rw_indexed (0x0ccb)`，因为 `0xF800` 载荷会线性粉碎它索引的 `0x2383` 和 `0x8e08` 处的寄存器描述符表；而一次 2026-07-06 的隔离矩阵显示，每条携带写入的重接链都死在 `0xccb`。然而已发布的载荷确实把 `0x00000ccb` 种在 DMEM `0xFFF4` 且有效。定论方式：追踪已发布的链展开期间 DMEM `0xFFF4` 是否曾被载入 PC，还是它只是一个永不被返回穿过的帧里的死保存槽。这是本领域最易处理的开放项，因为载荷和反汇编都在手。

---

## 8. 每次发射的写

> [!NOTE]
> **已发布的驱动每次 Booter Load 发射恰好做一次任意 BAR0 写**
>
> 载荷携带恰好一个 `(writeAddr, writeValue)` 对，位于载荷偏移量 `0xf76c` 和 `0xf754`。驱动对它想触碰的每个寄存器各重发一次 Booter Load，每个寄存器最多两次尝试，并回读验证。那就是每次驱动加载 4 到 8 次利用发射，再加一次正常引导。见[falcon-and-booter.md](falcon-and-booter.md#125-booter-运行多少次)。

写次数是*尾*的属性，而非机制的属性。这正是源材料里会出现五个不同答案的原因。

| 链 / 尾 | 每次发射的写 | 依据 |
|---|---|---|
| 已发布的驱动 | **1** | 从已发布的源码读出 |
| `refire_chain_v2.py`，完整互斥尾 | ≤ 2 | 硬编码 `raise ValueError("<=2 writes/fire (full mutex tail caps DMEM at stock SP)")` |
| mutexfree / `0x814e` 尾 | ≤ 4 | 最高槽 = `63392 + (N-1)*24`；N=4 给 63,464（合适），N=5 恰好溢出 `0xF800` 载荷 4 字节 |
| 压缩六写布局 | 6 | 6 × 24 B + 一个 9 字（36 B）尾 = 从 DMEM `0xFF48` 起 180 B；牺牲 `0x27fa` WPR2 重接和 `0x1d9f` 栈吞噬器 |
| 重入设计，开发者陈述 | 6 | 4 花在恢复 booter 检查的寄存器、2 载荷写、互斥锁在最后一次调用里释放 |

支撑算术：

- 额外写步长：`0x18` = 24 字节，由 `0x10aa` 的 `mpopaddret $r3 0x4` 尾声设置。
- 终止符槽公式：`63348 + (N-1)*0x18`。
- 终止符落地 SP：`E = 0x800 + 63392 + shift`，一次写给 DMEM `0xFFA0`、两次 `0xFFB8`、三次 `0xFFD0`。
- `multiwrite_then_814e` 参考：`term_slot = 63388`、SP `0xFFA0`。N = 3 写时 `term_slot = 63396`、`tail_shift = +8`、最高尾槽 63448（DMEM `0xFFD8`），在载荷最大 63,488 之下。
- 带 16 字（64 字节）替代尾的五段布局总计 184 字节（5 × 24 B + 64 B）、不适合从 DMEM `0xFF48` 起的 180 字节预算。已发布的五段布局用一个 15 字（60 字节）尾：120 B + 60 B = 恰好 180 B。

> [!NOTE]
> **未解问题：mutexfree 上限真的 4 还是真的 2？**
>
> 槽公式推导 ≤ 4；v2 引擎硬编码 ≤ 2，带注释 "full mutex tail caps DMEM at stock SP"。一次独立发布的 5 写 poke 布局把写 2-5 放在 DMEM `0xFF60`、`0xFF78`、`0xFF90`、`0xFFA8`，让最后的 `0x10aa` pop `0xFFC0`..`0xFFD0`，并从 `0xFFD4` 到 `0xFFFC` 跑一个固定的 12-dword 尾——这在算术上自洽且放得下。三个数字用了三个不同的尾，所以它们可能对各自的尾都正确，但没有任何来源陈述调和，5 写变体的精确尾字节也没给出。定论方式：计算每个引擎所发精确尾的最高占用槽，或发射一条五写和一条六写链并回读全部写。

---

## 9. 重接策略与终止符

不同终止符会权衡 SEC2 复位 PLM、ACR 互斥锁，以及 booter 自己的引导是否完成。

| 终止符 | 之后 resetPLM | ACR 互斥锁 | `0x001180f8` 半字节 | 结果 |
|---|---|---|---|---|
| 原始 `exit`（`f8 02`）在 `0x8117` | `0xff` | 搁浅 | 0 | 跳过 finalize。Booter Load 报告 `0x65`，MB0 `0x31`。 |
| 在 `0x4a7` 旋转停靠 | `0xff`（停在 HS） | 搁浅 | 不变 | 更早一次 `0x8403C4 = 0xff` 的 HS 写会粘住。 |
| `mutexrel3`（`0x1c0e` + 旋转） | | 释放 | 0 | |
| `814e` 带 fail_code = 1 | | | `0xf` | `0x814e -> main 0x80D7`；下一次 booter 报告 `0x29`。 |
| `mutexfree` | `0xff` | 释放 | 按写次数 0 或 `0xf` | 唯一达到打开 resetPLM、互斥锁释放和干净停机的组合。约 4 写封顶。 |
| `whole_stack_rejoin` | `0x8f` | 释放 | `0x1` | 用 `D[0xFFEC] = 1` 重建 `main` 的完整帧。唯一把 `0x001180f8` finalize 到 `0x11000000`（真实引导留下的）的终止符。达到 "RISC-V active"。 |
| 经 `0x7f2f` 的 `secure_teardown` | 若 `D[0x1900] = 7` 则 `0xff` | 不释放 | 从不写 | **已发布的。** |

在调用链更高处重接会释放栈：在 `0x814e`（SP `0xFFD6`）重接 `booter_load_wrap 0x8137`，而非在 `0x2740`（SP `0xFF98`）重接 `booter_load_wpr_main 0x22ba`，能省 62 字节、约三次额外写；而且 `0x22ba` 在 `$r10` 里收到非零返回值时反正做得很少。置信度：中等，从验证过的栈布局推得，并在操作上被重复的 Booter 轮次取代。

`multiwrite_then_814e` 是无驱动谱系的 HW-PROVEN 干净尾：它在 `0x814e` 处、带 `r10` 设成一个假失败码重接 `booter_load_wrap`，于是 SEC2 以干净的、load2 可恢复的方式退出 HS。尾形状：`0x1fca -> 0x1fb9 (r10 <- fail_code) -> 0x1fca -> 0x814e -> 0x8173 -> main`。写顺序被保留，且 `FUSE_SS_PLM` 必须是 `writes[0]`。

两个机械载荷 bug 值得当作一类记住，因为两种情况下链都"工作"了、却静默丢了一次写：一个是 `0xFF45` 对 `0xFF54` 的槽位笔误（偏移量 63316，写 1 的 `$r0` 槽）；另一个是把 `0x00008262` 留在 `0xFFBC`，它充当一个裸 `ret`，于是写 5 在 `0xFFB0`/`0xFFB4` 加载的操作数从没被发出。

---

## 10. 容易漏掉的要求

- **刷新 CPU 缓存。** 签名 DMA 是非连贯的；没有显式刷新，Falcon 就会读到陈旧的 RAM。无驱动工具 JIT 组装一个 17 字节 x86-64 桩并映射为 `PROT_EXEC`；已发布的驱动则在每次载荷重新填充后，对签名 memdesc 和 WPR-meta 描述符都调用 `memdescFlushCpuCaches()`。
- **不带驱动发射时，放置一个有效的 radix3 页表**，否则 booter 的签名前 DMA 会以原因 `0x9` 失败。
- **每次发射前重新装填 WPR2。** 每次发射都会重新划分 WPR2；否则第二次 Booter Load 会以 "WPR2 already up" 中止。已发布的驱动保存 `0x001fa824`/`0x001fa828` 一次，在最多 8 次尝试的每次之前重写保存的那一对，循环结束后再来一次。空/INIT 编码是 LO `0x0fffffff`（或无驱动工具写的 `0x1FFFFE00`）、HI `0`；而 HI = 0 正是让 `kgspIsWpr2Up()` 返回 false 的关键。
- **复位后只有第一次发射以 resetPLM `0xff` 落地。** 之后每次不带 FLR 的发射都卡在 HS 状态 `0x3002`。一次引擎复位（写 0 到 `0x8403C0`）能把 HS 从 `0x3000` 降到 `0x3002`、让 resetPLM 停在 `0xff`、经一次 modprobe 保持几何布局完好、并把 DMACTL 带回来，但重复发射仍以 `0x62:0x65:2674` 失败。

---

## 11. 原语实际用来做什么

一旦 HS 代码执行存在，它只被用作一个**枢轴**。链打开门控熔丝覆盖影子寄存器的权限级别掩码；之后，普通的 PL0 主机 BAR0 写就驱动覆盖、不再需要利用。那恰好是已发布的补丁的形状：四次利用驱动的 PLM 打开，接四次普通 `GPU_REG_WR32()` 调用。

产生它的设计约束在驱动存在之前就被陈述：ROP 写与保留映像验证所需的栈帧，竞争同一个 DMEM 范围 `0xFF3C`-`0xFFB8`，所以一条五写链和一次完整的 `0x37b7` 重建无法共存。陈述的解决方案是：只把真正需要 HS 的写留在 ROP 里，PLM 打开后在主机侧完成其余部分。

一个值得标记的测量消除了整整一类工作：**对 `0x009A0204` 处 CFG1 的一次重度安全广播写，会传播到全部 20 个每-FBPA `CSTATUS` 寄存器**——实测为一次跨每个活 FBPA 的 `0x200` 到 `0x800` 转变。HS 完全绕过 FBPA PLM；打开它们只在需要于 `0x00900204 + n*0x4000` 处做主机-PL0 每-FBPA 写时才必要。见[显存几何布局](memory-geometry.md)。

---

## 相关页面

- [SEC2 Falcon 与 Booter Load 微码](falcon-and-booter.md)
- [权限级别掩码](privilege-level-masks.md)
- [显存几何布局](memory-geometry.md) 和[算力节流](compute-throttle.md)
- [驱动补丁](driver-patches.md)
- [寄存器参考](register-reference.md)
- [死路](../history/dead-ends.md) 和[工具谱系](../history/tool-lineage.md)
- [净室与来源溯源](../history/clean-room-and-provenance.md)
- [术语表](../start/glossary.md)
