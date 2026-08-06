# 权限级别掩码

**本页覆盖内容。** GA100 上 PLM 是什么、掩码位如何编码、出货解锁打开的恰好四个掩码以及每个被打开到的精确值、四个中为何有一个被刻意只部分打开、哪些掩码挺过功能级复位、哪些不能，以及未发布 PCIe 分支改用的九掩码表。执行打开的机制见[ROP 链](rop-chain.md)；它运行其上的微码见[SEC2 Falcon 与 Booter Load 微码](falcon-and-booter.md)。

**开头的关键结果。** 解锁按固定顺序恰好打开四个掩码，而其中只有三个被打开到全一：

| 顺序 | 名称 | BAR0 地址 | 写入的值 |
|:---:|---|---|---|
| 0 | `WPR_CFG` | `0x001fa7cc` | **`0xfffff0ff`** |
| 1 | `FBPA` | `0x009a0148` | `0xffffffff` |
| 2 | `WPR` | `0x001fa7c4` | `0xffffffff` |
| 3 | `FEAT` | `0x00823804` | `0xffffffff` |

> [!CAUTION]
> **`WPR_CFG` 打开到 `0xfffff0ff`，不是 `0xffffffff`**
>
> `0x001fa7cc` 的位 [11:8] 被刻意保持清除。项目 README 和 `docs` 分支都把解锁描述成"把 PLM 打开到 `0xffffffff`"，或声称一次成功解锁后所有 PLM 都必须读 `0xffffffff`。这种措辞对第一条目并不精确，会让任何凭肉眼验证的人把一次正确的解锁误判为失败。一张卡显示 `0x001fa7cc = 0xfffff0ff`、其余三个在 `0xffffffff`，是**正确的**。

---

## 1. PLM 是什么

主机、SEC2 Falcon 和 GSP NVRISC-V 核心都通过 **PRI**——一个共享的特权寄存器接口——与 GPU 的内部寄存器通信。主机看向 PRI 的窗口是 BAR0。PRI 并不是平坦且开放的：它的区域被 **Privilege Level Masks（权限级别掩码）** 门控，每个受保护区域一个小寄存器，声明哪些权限级别可以读区域、哪些可以写、以及哪些片上源一开始就被允许发出那些访问。

Falcon 家族的权限级别运行 L0 到 L3，映射到[falcon-and-booter.md](falcon-and-booter.md#2-the-falcon-security-model) 描述的 Falcon 执行模式：

| 级别 | 谁 | 典型触及范围 |
|---|---|---|
| L0 | 经 BAR0 的主机，以及非安全 Falcon 代码 | 普通寄存器 |
| L1 / L2 | 轻度安全 Falcon 上下文 | 中间 |
| L3 | 重度安全 Falcon 代码 | 一切，包括 PLM 本身 |

整个解锁之所以存在，是因为改变卡显存几何布局和算力节流的寄存器，被只允许 L3 写入的掩码门控；而在这颗晶片上到达 L3 的唯一方式，是在已签名重度安全微码内运行。一旦一个 PLM 从 HS 内部被重写为允许 L0 写入，普通主机 BAR0 写入就不再需要任何利用。这个枢轴就是出货解锁的整个架构。

> [!WARNING]
> **PLM 意思是 Privilege Level Mask（权限级别掩码）**
>
> 项目自己的 `docs` 分支（`cmpunlocker-branches/docs/docs/ARCHITECTURE.md`）把 PLM 展开成 "Program Logic Modules"，还杜撰了 "PMM (Permute Mask Model)"、"LMR (LM Request)"、"SS0/SS1 (Suspension State)" 和 "PMA (Power Management Array)"，全都是杜撰。NVIDIA 头文件里底层的寄存器名是 `PRIV_LEVEL_MASK`。那份文档里没有一样东西应该被带进对这个硬件的描述。见[死路](../history/dead-ends.md)。

---

## 2. 位编码

整个项目使用、且与晶片上每个观察值一致的编码：

| 字段 | 位 | 含义 |
|---|---|---|
| `READ_PROTECTION` | [3:0] | 哪些级别可以读 |
| `WRITE_PROTECTION` | [7:4] | 哪些级别可以写 |
| `SOURCE_ENABLE` | [23:8] | 哪些片上源可以发出访问 |

常见值：

| 值 | 读法 |
|---|---|
| `0xFFFFFF8F` | 所有级别可读，写仅 L3，所有源启用。**这颗晶片上的锁定基线。** |
| `0xFFFFFFFF` | 完全打开：所有级别读和写，所有源。 |
| `0xFFFFFFCF` | 另一种观察到的写锁模式。 |
| `0x0004CB8F` | 解锁后、普通驱动加载把 `WPR` 和 `WPR_CFG` 重新锁到的值。 |
| `0xFFFFFE8E` | 普通驱动加载后在 `0x009A0008`、`0x00100B10` 和 `0x00100B38` 上观察到的。 |
| `0x0000008F` / `0x000000DF` | SEC2 复位 PLM 上看到的仅低字节模式。 |

对精确三字段分解的置信度，作为工作模型是高：它匹配每一个观察到的基线、每一个观察到的解锁后值，以及出货解锁器对 `0xFFFFFFFF` 的选择。它是从行为推断的，而非从一份发布头文件读出。

编码的两个实际后果：

- **`0x000000FF` 不是"打开"。** 它只设置 READ 和 WRITE 半字节、把 `SOURCE_ENABLE` 留成 0，而那会阻塞一切。ROP v2 正是因为这个原因把 `0x000000FF` 写给 `0x00823804`、结果毫无用处；每一个更晚的载荷和出货补丁都写 `0xFFFFFFFF`。
- **PLM 拒绝越界值。** 即使其它掩码已打开，向一个 PLM 写入诸如 `0xff` 的任意值也会被弹回。因此对 PLM 值的暴力破解受硬件接受的编码约束，而非受整个 32 位空间约束。至少两人在两张不同卡上直接观察过。

---

## 3. 解锁打开的四个掩码

### 3.1 该表，与源码里出现的完全一致

```c
static const struct {
    NvU32 addr;
    NvU32 value;
    const char *name;
} plmTable[] = {
    { 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
    { 0x009a0148U, 0xffffffffU, "FBPA"    },
    { 0x001fa7c4U, 0xffffffffU, "WPR"     },
    { 0x00823804U, 0xffffffffU, "FEAT"    },
};
```

这张表在出货 `master` 和除四个 Gen2 家族分支外的每个归档分支里逐字节相同，后者扩展它（第 6 节）。

### 3.2 每个门控什么

| 名称 | 地址 | 门控 | 解锁为什么需要它 |
|---|---|---|---|
| `WPR_CFG` | `0x001fa7cc` | WPR 掩码/配置寄存器 `0x001fa814` / `0x001fa818`，以及一般的 WPR 区域块 | 写保护区域机制必须能跨重复的 Booter 发射被重新武装 |
| `FBPA` | `0x009a0148` | FBPA（帧缓冲分区）寄存器孔径，包括 `0x009a0204` 处的广播 CFG1 | 发射后主机 PL0 必须能写 CFG1。见[显存几何布局](memory-geometry.md)。 |
| `WPR` | `0x001fa7c4` | WPR1/WPR2 地址寄存器 `0x001fa81c`-`0x001fa828` | WPR2 低/高必须由主机在每次发射前重新武装 |
| `FEAT` | `0x00823804` | 特性覆盖块 `0x00823800`-`0x00823FFC`，包括 SS0 `0x0082381c` 和 SS1 `0x00823820` | 主机 PL0 必须能写算力节流覆盖。见[算力节流](compute-throttle.md)。 |

`FEAT` 对持久性而言是有趣的那个，因为它位于一个常电域里。见第 5 节。

### 3.3 出厂值

| 寄存器 | 出厂读数 | 备注 |
|---|---|---|
| `0x00823804` `FEAT_OVR_PLM` | `0xffffff8f` | 在**每一张**被探测的 Ampere 卡上读相同：两块 170HX 单元、A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A5000、A6000、RTX 3080 / 3080 Ti / 3090 / 3090 Ti 和 Drive A100 |
| `0x00823800` `FEAT_OVR_ECC_PLM` | `0xffffff8f` | 只有 A100 SXM4 40G 读 `0x0000abcf`，未解释 |
| `0x00823B00`（行重映射器 PLM） | `0xFFFFFF8F` | |
| `0x009a0148` `FBPA` | `0xFFFFFF8F` | |
| `0x001fa7c4` / `0x001fa7cc` | 锁定 | 普通驱动加载后重新锁到 `0x0004CB8F` |

整个 `0x823800`-`0x823FFC` 窗口里，在锁定卡上只有三个寄存器读 `0xFFFFFF8F`：`0x823800`、`0x823804` 和 `0x823B00`。那个共享值正是把它们识别为守护该块的 PLM 的标志。但它们并不是仅有的可读 dword：2026-07-16 对整块窗口的一次范围扫描，在锁定卡上于 PL0 返回了十二个活 dword——连续的一段 `0x823800`-`0x82382C` 加 `0x823B00`——以及到 `0x823FFC` 为止每个其它 dword 的 `0xBADF5040`。

---

## 4. 打开如何执行

四个条目的机制都一样，值得细读，因为成功标准并不是日志行所暗示的。

```c
savedWpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824);
savedWpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828);
/* SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x */

for (plmIdx = 0; plmIdx < 4; plmIdx++) {
    opened = NV_FALSE;
    for (attempt = 0; attempt < 2 && !opened; attempt++) {
        GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
        GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
        kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
                                          plmTable[plmIdx].addr,
                                          plmTable[plmIdx].value);
        kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
            memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
        regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
        opened = (regVal == plmTable[plmIdx].value);   /* 精确相等 */
    }
    /* SEC2_DEBUG: FAILED to open <name> after 2 attempts */
}
GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
```

要紧的点：

- **每次尝试一次 Booter Load 发射、每次发射一次任意 BAR0 写。** 载荷携带单个 `(writeAddr, writeValue)` 对，所以打开四个掩码要花四到八次发射。
- **WPR2 低/高在每一次尝试前重新武装**，最多八次，循环结束后再一次；因为每次发射都会重新划出 WPR2，随后一次 Booter Load 否则会以 "WPR2 already up" 中止。出货驱动恢复*保存的*那一对；它不写无驱动工具所写的常量 `0x1FFFFE00` / `0`。
- **成功是精确回读相等**，而非 Booter 状态。每次发射都报告 `status=0xffff` 并记录 `Booter failed with non-zero error code: 0x31`，无论结果如何。寄存器回读是唯一有效的判决。
- **一条目的失败不会中止循环。** 它记录日志并继续。

出货 `master` 每次尝试记录一行，循环后记录一行汇总：

```text
SEC2_DEBUG: PLM[%u] %s(0x%x) attempt=%u status=0x%x reg=0x%08x
SEC2_DEBUG: PLMs: FEAT=0x%08x FBPA=0x%08x WPR=0x%08x WPR_CFG=0x%08x
```

一条真实行读 `SEC2_DEBUG: PLM[3] FEAT(0x823804) attempt=0 status=0xffff reg=0xffffffff`，带索引到名称映射 `PLM[0]=WPR_CFG, PLM[1]=FBPA, PLM[2]=WPR, PLM[3]=FEAT`。未发布分支用相同的每条目格式。

fork 线程里流传的更短 `SEC2_DEBUG: PLM FEAT before:` / `PLM FEAT after:` 对**不是**出货字符串：对出货仓库 grep 找不到这样的文本。它引用的值（锁定 `0xFFFFFF8F`、打开 `0xFFFFFFFF`）对 `FEAT` 是对的，但不要把那行本身当作 `dmesg` 里要寻找的东西。

如果掩码事后仍读它的锁定值，说明打开没有发生；记录在案的补救是另一次冷启动。见[排障](../procedures/troubleshooting.md)。

### 4.1 循环后发生什么

四个掩码打开后，驱动在 PL0 执行四次普通主机 `GPU_REG_WR32()` 调用，不再需要任何利用：

| 寄存器 | 值 | 目的 |
|---|---|---|
| `0x0082381c`（SS0） | `0x88888888` | 算力节流 |
| `0x00823820`（SS1） | `0x00000008` | 算力节流 |
| `0x009a0204`（CFG1） | `0x02779000`（8 GB 卡）/ `0x02669000`（10 GB 卡） | 显存几何布局 |
| `0x00100ce0`（LMR） | `0x0000020B`（8 GB 卡）/ `0x0000028A`（10 GB 卡） | 显存几何布局 |

> [!WARNING]
> **`docs` 分支对 SS0 和 SS1 是错的**
>
> `ARCHITECTURE.md` 声称 `SEC2_DEBUG: SS0 = 0xffffffff` 和 `SS1 = 0xffffffff`，并打印一行代码里任何地方都不存在的预期日志行 `SEC2_DEBUG: Executing unlock sequence...`。出货代码写的是 SS0 = `0x88888888`、SS1 = `0x00000008`。同一文档里的几何布局表（8 GB 到 64 GB 带 `0x02779000`/`0x0000020B`，10 GB 到 40 GB 带 `0x02669000`/`0x0000028A`）却是正确的。

---

## 5. 持久性：哪些掩码挺过复位

这种不对称是 PLM 集合里最具后果的单一属性，也是算力解锁先于显存解锁出货的原因。

| 寄存器 | 挺过 FLR？ | 备注 |
|---|---|---|
| `FEAT` `0x00823804` | **是** | 常电（AON）功率域 |
| SS0 `0x0082381c`、SS1 `0x00823820` | **是** | AON |
| `WPR` `0x001fa7c4`、`WPR_CFG` `0x001fa7cc` | 否 | 普通驱动加载后重新锁到 `0x0004CB8F` |
| `FBPA` `0x009a0148` | 否 | 又读 `0xFFFFFF8F` |
| CFG1 `0x009a0204`、每-FBPA CFG1、`CSTATUS`、LMR `0x00100ce0` | 否 | 几何布局**不**挺过 |
| AON LMR 影子 `0x001180f0` | 否 | |
| SEC2 复位 PLM `0x008403C4` | 污染被清除：`0x8f` 回到 `0xff` | FLR 是唯一清除它的东西 |

解锁后、普通驱动加载之后，只有 `0x00823804` 处的 `FEAT` 保持解锁。580.159.04 上、没有驱动加载、两次 FLR 之后的一次更大扫描报告 `0x8200D4`、`0x8200D8`、`0x8200E0`、`0x8200E4`、`0x8200E8`、`0x8200EC`、`0x8200F0`、`0x8200F4`、`0x8200FC`、`0x823800`、`0x823804` 和 `0x823B00` 为 UNLOCKED；而 `0x8200D0` 和 `0x8200DC` 读 `0xFFFFFF8F`、`0x9A0008` / `0x9A000C` / `0x9A0148` / `0x9A014C` / `0x9A03F0` 读 `0xFFFFFF8F`、`0x9A0168` / `0x9A0554` / `0x100B9C` 读 `0xFFFFFFCF`、`0x9A0BFC` 读 `0x00000000`、`0x100B10` / `0x100B38` 读 `0xFFFFFF8F`、`0x100B84` 读 `0xFFFFFF88`。

从那次扫描得出的区分：持久 PLM 位于常电功率域上；复位 PLM 需要每次引导重新解锁。

> [!NOTE]
> **未解问题：一次系统的 AON 分类**
>
> 一个名为 `nuke.sh` 的实验完整规定了工作：每周期构建一个三写 ROP 载荷、补丁 GSP、加载驱动、FLR、杀掉驱动、再 FLR、在没有驱动加载时读 26 个候选 PLM，跑九个周期、先做一次冷启动基线。候选集：`0x008200D0, D4, D8, DC, E0, E4, E8, EC, F0, F4, FC`；`0x00823800`、`0x00823804`、`0x00823B00`；`0x009A0008, 000C, 0148, 014C, 0168, 03F0, 0554, 0BFC`；`0x00100B10, B38, B84, B9C`。方法论和候选清单在档；由此产生的分类表不在档。

因为几何布局挺不过 FLR，所以对算力解锁有效的 "attack、FLR、reload a clean driver"（攻击、FLR、重载干净驱动）技巧无法承载显存解锁：清除 GSP-RM 损坏的 FLR，同时也清除了 LMR 写入。正是那个约束迫使设计走向驱动内、同加载的方案。

---

## 6. 未发布分支上的九掩码表

> [!WARNING]
> **实验性**
>
> 四个未发布分支 `Gen2`、`debug-gen2`、`far` 和 `deced` 把表从四条目扩展到**九条**并循环 `plmIdx < 9`。这段代码不在 `master` 上、没有出货消费方，而且对最要紧的条目的回读结果在源码里没记录。见[PCIe Gen2](pcie-gen2.md)。

| 顺序 | 名称 | 地址 | 值 | 状态 |
|:---:|---|---|---|---|
| 0 | `WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` | 与出货相同 |
| 1 | `FBPA` | `0x009a0148` | `0xffffffff` | 与出货相同 |
| 2 | `WPR` | `0x001fa7c4` | `0xffffffff` | 与出货相同 |
| 3 | `FEAT` | `0x00823804` | `0xffffffff` | 与出货相同 |
| 4 | `XVE` | `0x00088ff4` | `0xffffffff` | 添加 |
| 5 | `XVE_B` | `0x00088ab4` | `0xffffffff` | 添加 |
| 6 | `XVE_C` | `0x00088ff8` | `0xffffffff` | 添加 |
| 7 | `FEAT2` | `0x00823b00` | `0xffffffff` | 添加；也是行重映射器 PLM |
| 8 | `OPT_PLM` | `0x008200fc` | `0xffffffff` | 添加 |

需要三个 XVE 掩码，是因为 PCIe 影子寄存器受 PLM 保护、拒绝主机读取：主机读会返回 `0xbadf5040`。

最终的免驱动工具用了同一张九条目表，并报告一次引导里两块 GPU 上全部九条都在第一次尝试成功，记录为 `PLM[n] NAME(addr) attempt=0 status=0xffff reg=0xffffffff`，其中前四条逐字节与出货表交叉核对，包括部分的 `0xfffff0ff`。

那个结果与一个独立的、具体的观察存在张力：

> [!NOTE]
> **未解问题：`FEAT2` `0x00823b00` 真的打开吗？**
>
> 一位研究者在 2026-07-22 报告 `0x00823b00` **拒绝** SEC2 链，因为它的 `SOURCE_ENABLE` 字段不把 sec2-HS 列入白名单，而且 SEC2 ROP 只能打开其 `SOURCE_ENABLE` 允许它的掩码。同一时期的另一条陈述："There are other primitives that allow PLM opening. Not all L3 access is equal. Regops via bar0 or via sec2 `iowrs`."（还有其它允许打开 PLM 的原语。不是所有 L3 访问都平等。经 bar0 或经 sec2 `iowrs` 的 regops。）分支代码记录每条目的回读，所以在一张卡上跑一次引导就能定论它。

### 6.1 `0x008200FC`：两个名字、三种读数、无定论

> [!NOTE]
> **未解问题**
>
> `0x008200FC` 处的寄存器在分支源码里叫 `OPT_PLM`、在净室工具里叫 `FUSE_SS_PLM`。**它们是同一个寄存器**，本维基把两个别名放在同一条目上。它读什么、是否可写，尚未定论：
>
> | 日期 | 报告 |
> |---|---|
> | 2026-07-09 | "PLM = `0x000003FF`（目标 `0xFFFFFFFF`）……FUSE 写失败，寄存器物理上看似只读。主机直接 `writel` 也被封顶在 `0x3FF`。" |
> | 2026-07-16 | "在整个 Ampere 产线上读 `0xffffffff`（对所有级别打开）" |
> | 2026-07-23/24 | 九-PLM 工具包括它并报告 `PLM[8] OPT_PLM(0x8200fc) attempt=0 status=0xffff reg=0xffffffff`，即成功 |
>
> 可能的定论方向：一个卡状态差异、命名混淆，或该寄存器只在其它掩码打开后才可写。可在冷启动的卡上、任何解锁之前，然后在九个打开的每一个之后、同一单元上，读 `0x008200FC` 来定论。
>
> 早期 ROP 链（v2 和 v3）写 `0x008200FC = 0xFFFFFFFF` 且写失败。它被正确诊断为不必要：可工作的算力解锁只用 `FEAT_OVR_PLM` `0x00823804` 加 SS0/SS1。**出货 `master` 不写它。**

---

## 7. 存在多少个 PLM

远比最初估计的多。计数从 1、到 3、到 "5 个重要、大概 10 到 15 个"，而发射日志最终在不同集合里枚举出 9、10 和 27 个不同的掩码。最早的估计来自一份公开 GA100 熔丝和寄存器 gist，写于 "even before we knew what a PLM was"（在我们甚至不知道 PLM 是什么之前）。

一次只读调查在 170HX 上编目了 **26 个不同的 PLM 寄存器**，并确立了第 2 节的位编码。另一次独立枚举，计数了社区驱动的启动时链在一块卡上打开的 **27 个掩码**：`FEAT`、`FBPA`、`WPR`、`WPR_CFG`、六个 `XVE` 掩码、`FUSE_FAM_A`、十个 `FUSE_PLM` 掩码和六个 `XP_PL` 掩码。置信度：中等——一份一手寄存器级报告，被第二位研究者佐证。

每个 PLM 都位于它保护的寄存器附近。打开一个，就允许来自 L0 到 L3 的所有权限级别写入。

> [!NOTE]
> **未解问题：一个寄存器的 PLM 地址能从寄存器自己的地址推导出来吗？**
>
> 被直接问过、从未回答。出货集合（`FEAT 0x00823804`、`FBPA 0x009a0148`、`WPR 0x001fa7c4`、`WPR_CFG 0x001fa7cc`）相对它守护的寄存器不遵循任何明显的偏移规则，尽管"它们都放在寄存器附近"的观察成立。下一步：跨一个孔径做一次全 PLM 扫描，看掩码是否占据每个块的一个固定子范围。

> [!NOTE]
> **未解问题：LMR 的 PLM 在哪？**
>
> 没人定位到门控 LMR `0x00100CE0` 的掩码。一个候选 FBHUB 表被贴出（`0x100B10 = 0xFFFFFF8F`、`0x100B38 = 0xFFFFFF8F`、`0x100B84 = 0xFFFFFF88`、`0x100B9C = 0xFFFFFFCF`），但贴出者否定了它、后来报告找不到。出货驱动却能在打开 `WPR_CFG`、`FBPA`、`WPR` 和 `FEAT` 后从主机成功写 LMR，所以**那四个中有一个已经门控它**。对出货表做一次四方消融，就能识别出是哪个。

> [!NOTE]
> **未解问题：显存解锁实际需要多少个 FBPA 侧掩码**
>
> 一个立场认为需要四个 FBPA 掩码（`0x9A0148`、`0x9A014C`、`0x9A0008`、`0x9A000C`）加 LMR 加复位 PLM，且 `0x100b10` 被证明不必要。第二个立场被有力论证：认为 CFG1 和 LMR 单独就够、FBPA 掩码由 CFG1 广播自动设置。出货代码通过恰好打开**一个** FBPA 掩码 `0x009a0148`、然后从主机写 CFG1 和 LMR，部分地定论了这个问题——所以既不是 "four" 也不是 "none" 是出货答案。它还削减了第三个数据点：免驱动的 `geometry_chain()` 打开**五个** FB 几何掩码、包括 `0x100b10`。定论方式：在同一个卡上，一次一条目地消融两个清单。
>
> 一个相关测量收窄了问题：**对 `0x009A0204` 处 CFG1 的一次重度安全广播写，会传播到全部 20 个每-FBPA `CSTATUS` 寄存器**（每个活 FBPA 上 `0x200` 到 `0x800`），所以 HS 完全绕过 FBPA 掩码。打开它们只在需要于 `0x00900204 + n*0x4000` 处做主机-PL0 每-FBPA 写时才必要。

---

## 8. SEC2 复位 PLM，`0x008403C4`

这是与上面四个同类的一个 PLM，但它不是解锁打开的那个。它守护 SEC2 Falcon 自己的复位控制（SEC2 + `0x3c0` 处的 `FALCON_ENGINE`），也是免驱动工具有一套完整 "clean SEC2" 纪律的原因。

| 值 | 状态 |
|---|---|
| `0xff` | 完全打开。干净的闲置、SBR 后。主机 PL0 复位会生效。 |
| `0xdf` | 普通驱动 GSP 引导 teardown 后的正常工作状态。仍允许复位。 |
| `0xcf` | 驱动 GSP-prime 重新锁上 PLM 后（位 4 清除）。 |
| `0x8f` | 重度安全退出污染。写锁定到安全源；PL0 复位写被弹回。 |

`reset_allowed = resetPLM in {0xff, 0xdf}`，且 `0xdf = 0x8f | 0x50`。`0x8f` 是在 HS 到 NS 退出转变时由硬件锁存的，不由任何 booter 指令写入。主机 PL0 一旦读到 `0x8f`，就无法再写 `0xff`、`0xdf` 或 `0xffffffff`；只有 HS 写能降低它，而只有 FLR 或 SBR 能把它清回 `0xff`。在那个状态下，`0x8f` 以错误对 `0x62:0x55` 阻塞 GSP-RM 引导，并阻塞一次 PL0 发出的 SEC2 `SFTRESET`。

主机侧过程检查的引擎复位门是 `(value & 0x77) == 0x77`。

> [!NOTE]
> **出货驱动从不碰它**
>
> 对出货仓库 grep 会得到 `0x008403c4` 的零引用。整套 clean-SEC2 纪律属于免驱动工具。驱动内路径改经驱动自己的 `kflcnReset`/FWSEC 序列重发 Booter Load，所以它从不需要一次主机发出的 SFTRESET。对该解释的置信度：中等——它是推断，因为没人陈述过它。定论方式：在出货驱动下、4 到 8 次 PLM 趟的每一次前后，读 `0x008403C4`。

完整细节，包括出货载荷无论如何都把它留在 `0xff` 的 `D[0x1900] = 7` 机制，见[falcon-and-booter.md](falcon-and-booter.md#10-leaving-heavy-secure-mode-and-the-reset-plm) 和[rop-chain.md](rop-chain.md#73-why-the-exit-is-clean)。

---

## 9. 为什么掩码是唯一的杠杆

值得陈述 PLM 方法取代了什么，因为熔丝证据干净地关死了替代方案。跨 15 张 Ampere 卡测得：

| 熔丝 | 地址 | 读数 | 后果 |
|---|---|---|---|
| `FUSE_QUADRO_WR_SEC` | `0x0082038C` | 全部 15 张上 `0x00000001` | 门控 `0x823804` 特性覆盖 PLM 的自封熔丝在**每个地方都烧断** |
| `FUSE_FEAT_OVR_DIS` | `0x008203F0` | 全部 15 张上 `0x00000000` | 会永久锁定所有特性覆盖的主灭杀开关**没被烧断**。这就是这一切为何能行。 |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | 170HX、全部三个 A100 SKU 和 Drive A100 上 `0x00000000`；每个消费级和 ES 部件上 `0x00000001` | CTRL_OPT 软件熔丝覆盖路径在熔丝层被禁用，所以未签名 FwSec 尾里的 25 条目 CTRL_OPT 表在这些卡上惰性 |
| `FUSE_OPT_SECURE_GSP` | `0x0082074C` | 全部 15 张上 `0x00000001` | GSP 调试被禁用、GSP 只接受签名生产固件，这正是解锁必须走签名缓冲区路线的原因 |
| `FUSE_DIS_SW_OVR` | `0x00820084` | 全部 15 张上 `0x00000001` | 不可 HS 写：2026-07-27 在一块 8 GB 卡上、带两个活对照探测，值被弹回。仍开放的东西更窄：`DIS_SW_OVR = 1` 是否真的*锁定* `FUSE_EN_SW_OVERRIDE`——因为它在覆盖工作的消费级卡上也读 `1` |
| `FUSECTRL` | `0x00820000` | 全部 15 张上 `0xe0040000` | |
| `FEATURE_OVERRIDE_QUADRO` | `0x00823808` | 按晶片且未解释：`0x00100183`（出厂 PLM 范围扫描）、`0x00000081`（**解锁后**探测，非出厂读数）、`0x00000181` / `0x00000182`（两块物理 170HX 单元）、`0x01000282`（A100 80 GB） | 只读。为什么该值在不同转储之间不同是一个开放问题；见[寄存器参考](register-reference.md) |

2026-05-31 关于"仅主机寄存器写入"的 "CONFIRMED DEAD"（已确认死亡）判决，作为诊断完全成立：`FEAT_OVR_PLM` 和 `FEAT_OVR_ECC_PLM` 都在 `0xffffff8f`（仅第 3 级）、`FUSE_QUADRO_WR_SEC = 1` 封死那个掩码、`FUSE_EN_SW_OVERRIDE = 0` 禁用 CTRL_OPT 覆盖表、`FECS_FEAT_OVERRIDE` 读返回 `0xbadf5040`。那份文档缺少的是到达第 3 级的方法，而它正确预测了答案会是 "needs Falcon HS"（需要 Falcon HS）。

完整熔丝图见[熔丝与 OTP](../hardware/fuses-and-otp.md)。

> [!NOTE]
> **一个值得保留的否定结果**
>
> 经特权总线、从非安全 Hello-World ucode 运行 LMR 和 CFG1 写入被尝试过、不起作用，正如 NVIDIA 自己的 Falcon-Security 文档所预测：NS 限制寄存器和物理内存访问，而这些寄存器上的掩码要求最高级别。一个更晚的、看似确认"NS 完全无法到达外部 BAR0"的免驱动探测，被**其作者自己撤回**——因为失败的测试用了一个 `D[0x14000000]` 窗口，它别名到 Falcon 的本地 DMEM、因此从没探测 BAR0。没有报告替换测量。

> [!NOTE]
> **未解问题：掩码打开后 PL0 能到达几何寄存器吗？**
>
> 赌注很大。因为 `0x00823804` 处的 SS0/SS1 掩码常开并挺过 FLR，如果主机 PL0 能在一次一次性 HS 打开后，到达 `0x00900204 + n*0x4000` 处的 CFG1、`0x00100CE0` 处的 LMR 和 SS0/SS1，那么存在一条无需进一步重度安全工作的永久路径。下一步：用一个正确映射的外部孔径窗口重跑被撤回的探测，并逐个检查每个寄存器。

---

## 10. 手工验证一张卡

解锁后要回读的四个值，以及一张正确卡显示的：

```text
0x001fa7cc  ->  0xfffff0ff     WPR_CFG   （不是 0xffffffff）
0x009a0148  ->  0xffffffff     FBPA
0x001fa7c4  ->  0xffffffff     WPR
0x00823804  ->  0xffffffff     FEAT
```

以及那些掩码启用的四次解锁写：

```text
0x0082381c  ->  0x88888888     SS0
0x00823820  ->  0x00000008     SS1
0x009a0204  ->  0x02779000  （8 GB 卡）  /  0x02669000  （10 GB 卡）
0x00100ce0  ->  0x0000020b  （8 GB 卡）  /  0x0000028a  （10 GB 卡）
```

注意后两个不挺过 FLR 或断电循环，而只有 `0x00823804`、`0x0082381c` 和 `0x00823820` 挺过。见[验证](../procedures/verify.md)。

---

## 相关页面

- [SEC2 Falcon 与 Booter Load 微码](falcon-and-booter.md)
- [ROP 链](rop-chain.md)
- [显存几何布局](memory-geometry.md) 和[算力节流](compute-throttle.md)
- [驱动补丁](driver-patches.md)
- [PCIe Gen2](pcie-gen2.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)
- [寄存器参考](register-reference.md) 和[寄存器索引](../appendix/register-index.md)
- [术语表](../start/glossary.md)
