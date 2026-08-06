# 显存几何布局：容量解锁如何工作

**本页覆盖内容。** CMP 170HX 被做成报告和使用比出厂更多帧缓冲的精确机制：携带几何布局的两个寄存器、按 SKU 的值、为什么这两个寄存器必须一致、把报告的内存变成可分配内存的驱动侧管道，以及持久性规则。物理基底（HBM 堆叠、分区、地板清扫、带宽）见[显存子系统](../hardware/memory-subsystem.md)。

头条在这里只陈述一次、通篇反复强调，因为搞混它正是这个主题里最常见的错误：

> **一张 8 GB CMP 170HX（`10de:20c2`）解锁到 64 GB。一张 10 GB CMP 170HX（`10de:2082`）解锁到 40 GB。** 绝不反过来。10 GB 卡的 80 GB 配置被尝试过，超过约 40 GB 就不可用。

已发布的解锁器里整个显存几何布局机制是**两次主机寄存器写**：

| 寄存器 | 地址 | 角色 |
|---|---|---|
| `NV_PFB_FBPA_CFG1`，广播 | `0x009a0204` | 每分区寻址深度（容量*档位*） |
| `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`（LMR） | `0x00100ce0` | MMU 对总帧缓冲大小的声明 |

解锁里其它一切的存在，都是为了那两次写落地、让 GSP-RM 和 CPU-RM 相信它们、并让由此产生的空间可分配。

---

## 按 SKU 的值表

这是权威表。里面对每个数字，已发布的 `common/constants.yaml`、`driver/build.sh`、`install.sh` 和 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 里的硬编码分支之间都一致。

| 量 | 8 GB 卡 `10de:20c2` | 10 GB 卡 `10de:2082` |
|---|---|---|
| 出厂容量 | 8192 MiB | 10240 MiB |
| **解锁容量** | **65536 MiB（64 GB）** | **40960 MiB（40 GB）** |
| 出厂 CFG1 `0x009a0204` | `0x02449000` | `0x02449000`（相同） |
| **解锁 CFG1** | **`0x02779000`** | **`0x02669000`** |
| 出厂 LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| **解锁 LMR** | **`0x0000020B`** | **`0x0000028A`** |
| `targetFbBytes` / GSP `fb_length` | `0x0000001000000000`（64 GiB） | `0x0000000A00000000`（40 GiB） |
| 元数据里的 `unlocked_mib` | 65536 | 40960 |
| 出厂每-FBPA `CSTATUS_RAMAMOUNT` | `0x200`（512 MiB） | `0x200`（512 MiB） |
| 解锁每-FBPA `CSTATUS_RAMAMOUNT` | `0x1000`（4096 MiB） | `0x800`（2048 MiB） |
| 活 FBPA | 16 | 20 |
| CFG1 档位字节 `[23:16]` | `0x77` | `0x66` |
| `install.sh` 横幅 | `Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)` | `Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)` |

第三个设备 ID `10de:20b0` 会被安装器的 `lspci` 扫描检测到，但**不会**被解锁：驱动内门只接受 `0x20C2` 和 `0x2082`，所以一张 `20b0` 卡会构建并安装一个解锁从不触发的驱动。master 的 `README.md` 仍说解锁是 `0x20C2` 门控的；那种措辞已过时，代码在全部六个补丁里都门控在两个 ID 上。

几何布局在**运行时按 PCI 设备 ID** 选择，而非在构建时。两个档位都编译进同一个模块：

```c
NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;

if (devId == 0x20C2) { cfg1Value = 0x02779000U; lmrValue = 0x0000020BU; }  /* 8 GB  -> 64 GB */
else                 { cfg1Value = 0x02669000U; lmrValue = 0x0000028AU; }  /* 10 GB -> 40 GB */
```

---

## CFG1 编码什么

CFG1 编码**每显存分区的寻址深度**。它不编码容量，也不编码堆叠数。

档位字节坐在位 `[23:16]`。每个半字节是一个行地址计数、偏移 8：

| 档位字节 | 行位 | 每 FBPA 容量 | 完整 CFG1 字 |
|---|---|---|---|
| `0x44` | 12 | 512 MiB | `0x02449000`（出厂，两个 SKU） |
| `0x66` | 14 | 2048 MiB | `0x02669000`（10 GB 卡到 40 GB） |
| `0x77` | 15 | 4096 MiB | `0x02779000`（8 GB 卡到 64 GB） |

因此总容量是 `档位 × 活 FBPA 数`，而 FBPA 数由熔丝决定、CFG1 不碰。**同一个字 `0x02779000` 在 16 分区的 8 GB CMP 上给出 64 GB、在 20 分区的 A100 上给出 80 GB。** 它是一个每分区跳线，不是每卡跳线。

该寄存器的探测目录字段解码是 `SUBP[1:0]`、`COL[15:12]`、`ROWA[19:16]`、`BANK[25:24]`。跨每个观察过的 HBM 部件，`COL` 停在 `0x9`、`BANK` 停在 `0b10`；只有行地址半字节会移动。GDDR6 部件读到不同的 `COL` 值（A10/A5000/RTX 3090/3090 Ti 上 `0x4266b000`、A6000 上 `0x4277b000`、RTX 3080/3080 Ti 上 `0x4266a000`），这正是为什么 `0x9` 半字节是一个显存类型常量、而非 "5 stacks" 标志。

**这些不是魔法常量。** `0x02779000` 字面上就是在真实 A100 PCIe 80 GB 硅片（PCI `0x20b5`）上测得的出厂 CFG1 值，连同 LMR `0x0000028b`。`0x02669000` 同理是 A100 PCIe 40 GB 和 A100 SXM4 40 GB 上的出厂值。解锁恢复的是真正的 A100 几何布局。一颗参考 GA100 读 `0x22779000`，只在位 29 上不同。那个位**把每-FBPA 寻址深度减半**：2026-07-27 一张被驱动到 `CFG1 = 0x22779000` 的 170HX，把每-FBPA `CSTATUS_RAMAMOUNT` 保持在 `0x800`（2048 MiB）而非 `0x1000`，记录为 `tier=0x77 HALVED -> 2048 MiB/FBPA x20 = 40960 MiB (40 GB)`；相比之下，解锁的 8 GB 卡在档位 `0x77` 解锁后，其活 FBPA 每个都读 `0x00001000`。位 29 是否还做别的事，从未确立。

同一个字也住在 VBIOS 里。自至少 Pascal 起，显存类型/大小/厂商由硬件引脚 STRAP0 到 STRAP2 选中的 16 个显存配置跳线之一决定。CFG1 跳线表是 16 条目、每条约 4 字节，以小端排列成 `00 90 TT 02`，即 `u32 = 0x02TT9000`，逐位就是寄存器值。已发布的 CMP 硬件上只有跳线 4 被填充。见[VBIOS](../hardware/vbios.md)。

---

## LMR 编码什么

`0x00100ce0` 处的 MMU 本地显存范围寄存器把总帧缓冲大小声明为一个幅值/标度对：

```text
size_MiB = LOWER_MAG[9:4] << LOWER_SCALE[3:0]
```

等价地 `bytes = MAG << (SCALE + 20)`。`MAG` 按 SKU 恒定、等于**活 FBPA 数的两倍**；`SCALE` 才是解锁改动的部分。

| LMR 值 | MAG | SCALE | 解码为 | 状态 |
|---|---|---|---|---|
| `0x00000208` | 32 | 8 | 8192 MiB | 出厂，8 GB 卡 |
| `0x00000288` | 40 | 8 | 10240 MiB | 出厂，10 GB 卡 |
| `0x0000020B` | 32 | 11 | 65536 MiB | **已发布的，8 GB 卡到 64 GB** |
| `0x0000028A` | 40 | 10 | 40960 MiB | **已发布的，10 GB 卡到 40 GB** |
| `0x0000028B` | 40 | 11 | 81920 MiB | 对 80 GB 正确；从一个脚本实验性发射过，从未发布 |
| `0x0000028C` | 40 | 12 | 163840 MiB | 一次 PRAMIN 运行真的接受的一个玩笑值 |

解锁在 **8 GB 卡上给标度半字节加 +3**、**在 10 GB 卡上加 +2**。按 CFG1 术语，8 GB 卡的差是 `+0x00330000`（位 16、17、20、21）、10 GB 卡是 `+0x00220000`（位 17、21）。

> [!NOTE]
> **未解问题：`LOWER_MAG` 是 [9:4] 处的 6 位还是 [10:4] 处的 7 位？**
>
> 真实使用里一切都在 6 位下工作。宽度从未从 `dev_fb.h` 读出。这是一次头文件查找，而非实验，也是 `0x28B` 对 `0x50A` 争论和一个干净答案之间横着的最后一样东西。

---

## 为什么 CFG1 和 LMR 必须匹配

它们是同一个事实的两次独立声明，而 GPU 会让它们彼此对照。

硬件上的一次受控三方对比：

| 配置 | 结果 |
|---|---|
| 完全没有显存写入 | CPU-RM 在 `0x24`（`kbusVerifyBar2`）失败 |
| 40 GB CFG1 跳线配出厂 10 GB LMR（`0x288`） | 仍 `0x24` |
| 40 GB CFG1 **加匹配的 LMR**（`0x28A`） | 到达 `0x25`（StateLoad） |

没有 LMR 就没有配置能到达 StateLoad。**CFG1 单独不够；LMR 是一个硬前提。**

**GSP-RM 在自己的引导期间把 LMR 当作主寄存器。** CFG1 设成 40 GB 档位、LMR 却留在 `0x288` 时，GSP-RM 会在 `kgspBootstrap` 期间把 `CSTATUS` 从 `0x800` 回退到 `0x200`。LMR 连贯地设成 `0x28A` 时，插桩的转储在全部四个检查点（包括 Bootstrap 后）读到 `CSTATUS=0x800 LMR=0x28a CFG1=0x2669000 WprMeta.fbSize=0xa00000000`。FWSEC 本身不会回退几何布局。

这正是未合并 `80` 分支撞上的那个失败：见下方[80 GB 尝试，以及它为何不连贯](#the-80-gb-attempt-and-why-it-is-incoherent)。

---

## 已发布的写入序列

解锁由 `_kgspSec2PostblTimingEnabled()` 门控，它读 `NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;` 并对 `0x20C2` **或** `0x2082` 返回真。

### 第 1 步：打开四个 PLM

主机（PL0）对 CFG1 的写入，在 FB 几何权限级别掩码打开之前会被**静默丢弃**。一条早期流水线记录了 `Write failed - wrote 0x2779000, read 0x2449000` 三次，却完全没有报告错误。原因是熔丝 `OPT_SECURE_FBPA_MEM_WR_SECURE`（`0x00820618`）= `1`，它把 FBPA 显存配置写限制到特权代码。

已发布的 `plmTable[]` 有**恰好四个条目**，按此顺序打开，每个通过一次 Booter Load 趟最多重试两次，保存的 WPR2 低/高对在每次尝试前重写、循环后再一次：

| 顺序 | 地址 | 写入的值 | 标签 |
|---|---|---|---|
| 0 | `0x001fa7cc` | **`0xfffff0ff`** | `WPR_CFG` |
| 1 | `0x009a0148` | `0xffffffff` | `FBPA` |
| 2 | `0x001fa7c4` | `0xffffffff` | `WPR` |
| 3 | `0x00823804` | `0xffffffff` | `FEAT` |

注意 WPR_CFG 的目标是 `0xfffff0ff`，**不是** `0xffffffff`。README 和 `DEBUGGING.md` 里 "all PLMs must show `0xffffffff`" 的文本是宽松措辞。出厂值是 FEAT 和 FBPA 的 `0xffffff8f`、WPR 对的 `0x0004cb8f`。

如果一个 PLM 两次尝试都失败，驱动会记录 `SEC2_DEBUG: FAILED to open <name> after 2 attempts`，并**照样继续**到几何写。WPR2 低/高（`0x001fa824` / `0x001fa828`）只被保存和恢复；已发布的驱动从不为它们设新值。见[权限级别掩码](privilege-level-masks.md) 和[ROP 链](rop-chain.md)。

> [!NOTE]
> **命名有争议，地址没有**
>
> 寄存器目录工作把 `0x001fa7c4` 命名为 `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`、即 LMR PLM，而已发布的 `plmTable` 把它标成 "WPR"、把 `0x001fa7cc` 标成 "WPR_CFG"。地址和值没有争议，功能结果相同。依赖地址。`0x001fa7c0` **不是** LMR PLM，在已发布的树任何地方都不出现；把它放在多写链首位会让 ROP 链故障。

### 第 2 步：四次主机寄存器写

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);  /* SS0：算力节流关闭      */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);  /* SS1：算力节流关闭      */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);    /* FBPA CFG1，广播别名     */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);     /* MMU 本地显存范围         */
```

CFG1 在 LMR **之前**写。全部四个随后回读并打印：

```text
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
```

前两次写是[算力解锁](compute-throttle.md)、对两个 SKU 无条件发出。它们只因为共享同一个窗口而被包含在这里。

### 第 3 步：仅广播

**已发布的驱动只把 CFG1 写给广播别名 `0x009a0204`。** 它不循环 `0x00900204 + n*0x4000` 处的 24 个每-FBPA 实例；对整个仓库里每个补丁、脚本和 YAML 文件中那些地址的一次 grep 返回零命中。因此，读已发布的安装器的 dmesg 会恰好看到一个 CFG1 值，而不是二十个。

这是上下文相关的，区分要紧：

| 上下文 | 什么足够 |
|---|---|
| 驱动 / devinit 路径（已发布的工具） | 对 `0x009a0204` 的一次广播写 |
| 无 devinit 的无驱动运行时（净室 refire 链） | 广播单独不移动 CSTATUS；**全部 24 个每-FBPA CFG1 实例必须在 `0x00900204 + n*0x4000` 处手工写**，并通过读 `0x0090020C + n*0x4000` 处的 `CSTATUS_RAMAMOUNT` 验证 |

五个 PLM 的 `FB_GEO_PLMS = [0x00100b10, 0x009a0148, 0x009a014c, 0x009a0008, 0x009a000c]` 清单和 24 实例循环，属于**单独的、未发布的免驱动工具链**，不属于已发布的安装器。读任何报告时都要把两条路径分开。见[工具谱系](../history/tool-lineage.md)。

> [!NOTE]
> **未解问题：广播是一个 PRI 特权环硬件机制吗？**
>
> 一位原本相信广播是 GSP-RM 里一个软件步骤的研究者划掉了那个信念、提出可能是特权环，但它从未被直接插桩。它要紧，因为它决定一次写是在每个上下文都保证足够、还是只在 devinit 跟随时才保证。实验：FB-geo PLM 打开、没有 devinit，只写广播，然后读全部 24 个每-FBPA CFG1 镜像，看值是否传播——即使 CSTATUS 不移动。

### 第 4 步：重建出厂签名并引导 GSP

postbl 路径用 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800` 字节（63,488）的 ROP 载荷替换 GSP 签名缓冲区，填充 dword `0x000004a7`，并在固定偏移量（`0x1100`、`0x5b40`、`0xf754` 到 `0xf7f8`，以 `0x00007f2f` 结束）处覆盖。如果 `/lib/firmware/nvidia/ga100/gsp/dmem.bin` 存在，则加载它替代；缺失时使用内置回退载荷、带 `0x009a0148 = 0xffffffff` 的单一默认写，缺失报告为 `0x59`、属良性。

GSP 引导前，`kgspSec2PostblTimingRebuildStockSignature()` 释放超大的载荷 memdesc，分配 `NV_ALIGN_UP(stockSignatureSize, 256)`，把保存的出厂签名复制回来，更新 `pWprMeta->sysmemAddrOfSignature` 和 `sizeOfSignature`。如果重建失败，GSP 引导被中止。这一步让一个其它方面正常的 GSP-RM 引导能跑在改动后的几何布局之上。

随后 `kgspPopulateWprMeta_HAL` 被重跑，让 WPR 元数据匹配新的帧缓冲：

| 字段 | 之前（8 GB 卡） | 之后（64 GB） |
|---|---|---|
| `fbSize` | `0x0000000200000000` | `0x0000001000000000` |
| `wprEnd` | `0x00000001fff00000` | `0x0000000ffff00000` |
| `wprStart` | （n/a） | `0x0000000ff7400000` |
| `heapOffset` | （n/a） | `0x0000000ff7500000` |
| `heapSize` | `0x0000000006900000` | `0x0000000006e00000` |
| 保存的 WPR2 | `lo=0x1ffffe00 hi=0x00000000` | 不变 |

10 GB 卡上对应的 `fbSize` 转变是 `0x0000000280000000` 到 `0x0000000a00000000`。

补丁 `0001` 还**无条件**把上游的 "unexpected WPR2 already up, cannot proceed with booting GSP" 硬失败（`return NV_ERR_INVALID_STATE`）降级为警告（`WPR2 already up before GSP boot; continuing for recovery`），所以一张留脏的卡仍能引导。

> [!CAUTION]
> **那个 WPR2 降级不门控在 CMP 设备 ID 上**
>
> 它适用于打过补丁的模块驱动的**每一块 GPU**。在混合系统上，打过补丁的模块会在无关硬件上静默越过一个真正坏的 WPR2 状态。不要把模块安装在你关心其它 GPU 的机器上。

---

## 让空间成真，而不只是报告

寄存器几何布局单独给你 `nvidia-smi` 里的一个数字。另外四个补丁把它变成 CUDA 能分配的内存。

### GSP 静态信息和 FB 区域（补丁 `0001`）

`kgspInitRm` 之后，对 devId `0x20C2` 或 `0x2082`：

- `pGSCI->fb_length` 被 `targetFbBytes` 覆盖（8 GB 卡上 `0x0000001000000000`、10 GB 卡上 `0x0000000A00000000`）。
- 如果 `0 < numRegions <= NV2080_CTRL_CMD_FB_GET_FB_REGION_INFO_MAX_ENTRIES`，驱动取 `fbRegion[numRegions-1]`，当 `limit < targetFbBytes - 1` 时设 `limit = targetFbBytes - 1`、`reserved = limit - base + 1`、`supportCompressed = NV_TRUE`、`supportISO = NV_TRUE`、`performance = 20`。

记录为 `SEC2_DEBUG: static-info BEFORE/AFTER: fb_length=... numRegions=...`。**没有这个，驱动不会报告加宽的大小**，因为在 GSP 固件启用时 CPU-RM 不自己给帧缓冲定大小：它经 RPC 在 `GspStaticConfigInfo` 里从 GSP-RM 接收 `fbSize`。

64 GB 引导上观察：`static-info BEFORE: fb_length=0x1000000000 numRegions=5`，最后 `region[4] base=0xff7300000 limit=0xfffffffff reserved=0x8d00000`。

### 晚期 PMA 扩展（补丁 `0003`）

`memmgrSec2DebugLateExtendHighPmaRegion()` 从 `osinit.c` 在 GPU 初始化后调用，门控在两个设备 ID 上。它是把报告的内存变成**可分配**内存的步骤。它扫 `Ram.fbRegion[]`，找满足 `bRsvdRegion && !bInternalHeap && limit >= stockFbBytes && base <= limit` 的最高-limit 区域，构建一个带 `base = NV_MAX(candidate->base, 0x200000000)` 和 `bSupportCompressed = NV_TRUE` 的 `PMA_REGION_DESCRIPTOR`，并调用 `pmaRegisterRegion(pPma, numPmaRegions, NV_FALSE, &pmaRegion, 0, NULL)`。

成功时它拆分或取消保留候选：

- 如果 `candidate->base < 0x200000000`，追加一个新的公共 FB 区域（`base = 0x200000000`、`limit` = 旧 limit、`rsvdSize = 0`、`bRsvdRegion = NV_FALSE`、`bInternalHeap = NV_FALSE`、`bSupportCompressed = NV_FALSE`），把原始截断到 `limit = 0x1ffffffff`、钳制它的 `rsvdSize`、递增 `numFBRegions`，然后调用 `memmgrRegenerateFbRegionPriority()`。
- 否则就地清除 `bRsvdRegion`、`rsvdSize`、`bInternalHeap` 和 `bSupportCompressed`。

早退：PMA 未初始化则 `NV_OK`（`SEC2_DEBUG_LATE_PMA: no PMA, skipped`）、范围为空、或 `pmaIsPmaManaged()` 已覆盖；需要拆分但 `numFBRegions >= MAX_FB_REGIONS` 则 `NV_ERR_INSUFFICIENT_RESOURCES`。

64 GB 卡上的实测效果：

```text
SEC2_DEBUG_LATE_PMA: registering candidate=6 base=0xff7300000 limit=0xfffffffff ... pma_region_id=1
SEC2_DEBUG_LATE_PMA: status=0x0 pma_total 0xfd8f50000->0xfe1c50000 pma_free 0xfd8f50000->0xfe1c50000
```

那个差是 `0x8d00000` 字节 = 147,849,216 字节 = **恰好 141.0 MiB**。"约 +136 MiB" 和 "约 141 MiB" 都在流传；141.0 MiB 是这个差，而别处的约 136 MiB 数值指的是 WPR carve——那是另一回事。

解锁的 64 GB 卡上完整 FB 区域布局，七个区域：

| 区域 | 基址 | 上限 | 标志 |
|---|---|---|---|
| 0 | `0x0` | `0x1007ffff` | rsvd=1, rsvdSize `0x10080000` |
| 1 | `0x10080000` | `0xfe8fcffff` | rsvd=0 |
| 2 | `0xfe8fd0000` | `0xff42dffff` | rsvd=0, rsvdSize `0xb310000`, intHeap=1 |
| 3 | `0xff42e0000` | `0xff430ffff` | rsvd=1, intHeap=1 |
| 4 | `0xff4310000` | `0xff720ffff` | rsvd=1, rsvdSize `0x2f00000` |
| 5 | `0xff7210000` | `0xff72fffff` | rsvd=1 |
| 6 | `0xff7300000` | `0xfffffffff` | rsvd=1, rsvdSize `0x8d00000`, **扩展候选** |

同一次引导的堆汇总：

```text
SEC2_DEBUG_HEAP: fbAddrSpace=65536MB mapRam=0MB fbTotal=65536MB fbUsable=0xfe4260000
                 heapTotal=0x1000000000 regionBytes=0x1000000000 publicBytes=0xfd8f50000 numRegions=7
```

### BAR0/PRAMIN 钳制（补丁 `0004`）

在 `kern_bus_gm107.c` 里，对 devId `0x20C2` 或 `0x2082` 且 `Ram.fbAddrSpaceSizeMb > 0x2000`（8192 MB）时，`offsetBar0` 被强制为：

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

即 PRAMIN 窗口被钉回**出厂 8 GiB** 地址空间、而非跟踪加大的那个。这对任何用 PRAMIN 探测高物理内存的人都要紧：解锁后，PRAMIN 默认到不了新空间的顶部。补丁文件在 master 和全部四个驱动系列移植目录之间逐字节相同（md5 `8e6a2b1c03df6d3388243db82ebbb9b4`）。

### CE 清理变通方案（补丁 `0005`，加 `0003` 里的一个 hunk）

压缩在解锁卡上被刻意在三处禁用，全部门控在两个设备 ID 上：

1. `mem_mgr_tu102.c` 里，清理器的 PTE-kind 选择器返回 `NV_MMU_PTE_KIND_GENERIC_MEMORY` 而非默认的 `NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`。
2. `mem_scrub.c` 里，CeUtils 守卫变成 `if (memmgrUseVasForCeMemoryOps(pMemoryManager) && ((pGpu->idInfo.PCIDeviceID >> 16) != 0x20C2 && (pGpu->idInfo.PCIDeviceID >> 16) != 0x2082))`，让 CeUtils 保持物理模式而非虚拟模式。
3. `mem_mgr.c` 里（补丁 `0003` 的第三个 hunk），同样的设备 ID 排除被加到被 `bUseRawModeComptaglineAllocation` / `bOneToOneComptagLineAllocation` 守护的 `ceUtilsParams.flags |= DRF_DEF(0050_CEUTILS, _FLAGS, _VIRTUAL_MODE, _TRUE)` 路径上。

没有这些，复制引擎清理器会绊在加宽空间里的压缩分配上。

### 持久软件状态（补丁 `0006`）

`NV_FLAG_PERSISTENT_SW_STATE` 在 `nv.c` 里对两个设备 ID 设置，在两个带相同主体的独立 `if`/`else if` 分支里。

### 已发布的代码里一个真实的对称性

`stockFbBytes = 0x200000000ULL /* 8GB */` 在补丁 `0001` 和 `0003` 里都被硬编码，并用于**两个**设备 ID，包括真实出厂大小是 `0x280000000` 的 10 GB 卡。PRAMIN 钳制同理对 `0x2000` MB 比较。在补丁 `0001` 里该变量被声明、却从不引用（死代码）；在补丁 `0003` 里它是出厂区域和晚期-PMA 扩展区域之间的拆分点。

> [!NOTE]
> **未解问题：8 GiB 的 `stockFbBytes` 在 10 GB 卡上要紧吗？**
>
> 解锁在 `0x2082` 上可演示地工作，所以任何效果都是微妙的。检查是纯读日志练习：在一张解锁到 40 GB 的 10 GB 卡上读 `SEC2_DEBUG_LATE_PMA: region[...]` 和 `SEC2_DEBUG_HEAP:` dmesg 行，确认 `publicBytes` 计入完整 40 GiB、而非丢失 8 到 10 GiB 那一小片。没人贴出过。

---

## 时序：整个过程约一秒

来自一张 8 GB 卡走到 64 GB 的完整 dmesg 捕获：

```text
11.13 s  出厂签名保存
11.32 s  PLM[0] WPR_CFG
11.50 s  PLM[1] FBPA
11.68 s  PLM[2] WPR
11.86 s  PLM[3] FEAT              （每次 Booter 趟约 180 ms）
11.86 s  POST-WRITE 和 WPR-meta 更新
12.07 s  正常 BooterLoad status=0x0
         POST-BooterLoad verify PLM=0xffffffff SS0=0x88888888 SS1=0x00000008
                                CFG1=0x02779000 LMR=0x0000020b
12.64 s  堆创建
12.72 s  晚期 PMA 扩展 status=0x0
```

注意 `BooterLoad` 每次重发运行都报告 `status=0xffff`，无论成功与否；回读是唯一判决。

---

## 持久性：几何布局对比算力

这是显存解锁最重要的操作属性，也是算力解锁先于显存解锁发布的原因。

| 事件 | 算力（SS0 `0x0082381c`、SS1 `0x00823820`、FEAT PLM `0x00823804`） | 显存几何布局（CFG1、每-FBPA CFG1、CSTATUS、LMR、FB-geo PLM、AON LMR 影子 `0x001180f0`） |
|---|---|---|
| 驱动卸载重载，无 SBR | 挺过 | **挺过** |
| 功能级复位（FLR） | **挺过**（常电岛） | **回退** |
| 重启 / 断电循环 | 回退 | 回退 |
| DEVINIT | 回退 | 回退 |

在 10 GB 卡上跨一次 FLR 测得：CFG1 `0x9A0204` 写的 `0x2779000` 回退到 `0x2449000`；LMR `0x100CE0` 写的 `0x20b` 回退到 `0x288`；而 SS0 `0x82381C` = `0x88888888`、SS1 `0x823820` = `0x8` 都挺过。SEC2 复位-PLM 污染也被 FLR 清除（`0x8f` 到 `0xff`）。

几何布局**确实**挺过一次无 SBR 的驱动卸载重载：卸载后寄存器仍读 `0x009a0204` = `0x02669000`、`0x00100ce0` = `0x0000028a`，而一次新加载又在 610.43.03 上枚举出 40960 MiB。

### 没有任何 PLM 把几何布局移进常电域

一次 **11-PLM in-HS 几何布局存活扫描** 穷尽地定论了这点。对全部 11 个候选，in-HS pre-FLR 状态相同（`CFG1=0x2669000 CSTATUS0=0x800 LMR=0x28a amap=0x200404 resetPLM=0x8f`），而每个 post-FLR 读都回退到 `CFG1=0x2449000 CSTATUS0=0x200 LMR=0x288 amap=0x280404`。只有 `0x008200fc`、`0x00823800`、`0x00823804` 和 `0x00823b00` 保持打开（`PLM=0xffffffff`，AON = 是）；`0x00100b10`、`0x00100b38`、`0x009a0148`、`0x009a014c`、`0x009a0008`、`0x009a000c` 和 `0x00118128` 全部重新锁到 `0xffffff8f`。卡恢复到 `boot0=0x170000a1 resetPLM=0xff`。那次扫描的标题是 "welp, no dice"。

**这是已发布的设计之所以在每次模块加载时、于 GSP 引导路径内重新应用几何布局、而非刷写或锁存一个永久状态的结构性原因。** 已发布的工具打开的四个 PLM 里，只有 FEAT（`0x00823804`）挺过 FLR，所以 FLR 之后主机侧发出的 CFG1/LMR 写会被阻塞。几何写必须发生在与 PLM 打开相同的无-FLR 窗口内。

### 推论：驱动无法静默撤销它

GA100 上的 `kmemsysReadUsableFbSize_GP102` 是只读的，而开源 CPU 侧 RM 从 LMR `0x00100ce0` 计算 `fbSize`、而非从 L2 amap。一个假设说出厂 RM 在引导时读 `0x44` 档位、把 CFG1/CSTATUS 重写回出厂档位并重新锁上 FB-geo PLM，被**测量反驳**：一次完整干净驱动引导后和一次无 SBR 的驱动卸载重载后，`0x009a0204` 仍读 `0x02669000`、`0x00100ce0` 仍读 `0x0000028a`。观察到的回退被追到操作者诱发的 FLR。

---

## 验证它落地

按可信度排序，最可信的放最后：

1. **`nvidia-smi --query-gpu=memory.total` 证明不了什么。** 驱动可以被补丁成打印任何数字，而内存静默折叠。多人恰恰被这点误导，包括一条在 64 GB 几何布局之上从 `nv-linux.c` 强制 `fb_size` 到约 80 GB 的早期流程。
2. **寄存器回读。** `0x0090020C + n*0x4000` 处的 `CSTATUS_RAMAMOUNT` 是最便宜可靠的检查：40 GB 档位是 `0x800`、64 GB 档位是 `0x1000`。预期被地板清扫的分区返回 `0xbadf20NN`，所以 10 GB 卡上 24 个中 20 个、8 GB 卡上 24 个中 16 个是正确的全过结果，而不是 24 个中 24 个。免驱动链用 `CSTATUS == 0x800` 作为它的验证谓词。
3. **一次稠密折叠测试。** 写每个页自己的索引，再读每个页回来。如果一条地址线缺失，内存会折叠、两个地址持有相同数据；而一个写和读同一区域的常规 memtest 抓不到这个。

> [!CAUTION]
> **不要对折叠测试做稀疏采样**
>
> 一次稀疏探测（每 N MB 一个词）在折叠卡上会给出**假阴性**，因为折叠在一个通道交错偏移量处别名、而非在相同的字节偏移量处：`LOW[0]` 映射到 `40GiB + interleave`，而不是 `40GiB + 0`，所以一次稀疏测试会写一个伙伴、却检查一个不同的地址。参考检查器分配全部空闲 VRAM 减 2 GiB，经一个 PTX 内核写每个 64 KiB 页自己的索引，再读每个页回来；真实为 0 退出、折叠为 1。也要先写全部数据、再读全部数据：交错读/写会引起从约 48 GB 开始变得很慢的争用。还要边走边驱逐 L2，否则读会由缓存提供。在驱逐方法论被采纳之前取得的任何折叠结果都应被丢弃。
> `SIGKILL` 掉测试期间一个活着的 CUDA 内核，可能以 **Xid 45** 楔住卡、强制一次复位循环。

一次成功的 8 GB 到 64 GB 解锁呈现为：

```text
NVIDIA-SMI 610.43.03   Driver Version: 610.43.03   CUDA Version: 13.0
NVIDIA CMP 170HX        0MiB / 65536MiB      34W / 250W     42C     P0
```

CUDA 经 ctypes 返回 `cuInit` 0、`cuDeviceGetCount` 1、`cuDeviceGetName` `NVIDIA CMP 170HX`、`cuDeviceTotalMem` 64.0 GB、属性 75/76 给出计算能力 8.0。卡名也可能显示为 `Unknown`，那是正常的。

> [!WARNING]
> **`clocks.max.sm = 1935 MHz` 是一个报告字段，不是可达时钟**
>
> 它出现在与容量相同的 `nvidia-smi` 查询里，常被引用为 64 GB 签名的一部分。VBIOS 表最大图形时钟是 1695 MHz，实际硅片天花板在 +350 偏移下约 1604 到 1614 MHz。持续 SM 时钟标称 1410 MHz（`-pl 300` 下 1470 MHz）。把 1935 MHz 当低置信度，见[算力节流](compute-throttle.md)。

截至档案窗口末尾的稳定性判决：**8 GB 到 64 GB 稳定且投入生产；10 GB 到 40 GB 稳定；10 GB 到 80 GB 报告大小、但超过约 40 GB 就不可用。** 一张 64 GB 卡约一小时后 `gpu_burn` 零错误通过，多个独立拥有者复现了它，8 GB 卡上没有一例失败的 64 GB 解锁。一张解锁到 40 GB 的 10 GB 卡，通过一次 5 分钟 `gpu-burn`、一次 30 GiB CUDA 写/回读烧机零不匹配、一次 37 GiB 带标签自驱逐折叠测试无折叠。

---

## 打包：构建如何选档位

`install.sh detect_card_profile()` 是在 `nvidia-smi --query-gpu=memory.total` 上的四级梯子，不在 PCI ID 上：

| 报告的 MiB | 档位 | 为什么 |
|---|---|---|
| `>= 60000` | `8gb` | 一张已解锁的 64 GB 卡，所以重装选同一个档位 |
| `>= 35000` 且 `< 60000` | `10gb` | 一张已解锁的 40 GB 卡 |
| `7680` 到 `8704` | `8gb` | 出厂窗口，为保留 FB 留 ±512 MiB 容差 |
| `9728` 到 `10752` | `10gb` | 出厂窗口 |
| 其它任何值 | 失败 | 打印 `unknown:<mib>` 并死掉、告诉你传 `--profile=8gb` 或 `--profile=10gb` |

`nvidia-smi` 缺失或返回非数值时该函数立即返回 1。

**`driver/build.sh` 不读 `common/constants.yaml`。** 树里任何地方的脚本、补丁或 Makefile 都不读那个文件。构建脚本在一个 bash `case` 里按档位硬编码自己的 CFG1/LMR/fb_bytes，然后对 `kernel_gsp.c` 跑一个 Python 重写器。因为 master 的补丁 `0001` 已包含重写器检查的全部六个标记（`..._8GB_PCI_DEVICE_ID`、`..._10GB_PCI_DEVICE_ID`、`0x02779000U`、`0x02669000U`、`0x0000001000000000ULL`、`0x0000000A00000000ULL`），重写器总是早退、打印 `runtime device-id geometry (profile metadata=<label>)`。**在 master 上，构建时的几何布局重写从不触发。** bash 档位只影响标签、预期大小消息和 `card_profile` 标记文件。

`constants.yaml` 是文档。它的内容碰巧在 master 上正确，所以没有错误值出过货；但该文件没有权威性，单独编辑它不改变任何被编译的东西。读分支的任何人都必须查 `build.sh` 和补丁，不要查 YAML。

安装输出路径：
`/lib/modules/$(uname -r)/updates/cmpunlocker/{driver_version,card_profile,unlock_geometry}`。
卸载是 `sudo ./remove.sh --yes`；已发布的仓库里没有 `uninstall.sh`。

---

## 80 GB 尝试，以及它为何不连贯

> [!CAUTION]
> **`80` 分支未合并、不稳定、内部自相矛盾**
>
> 它记录在这里，好让找到它的人理解它实际编程的是什么。不要在你需要的卡上跑它。

未合并的 `80` 分支把一张 10 GB 卡瞄准 81920 MiB。两次提交：`02ce75c` "Trying an 80GB unlock instead of 40GB" 和 `3c53aca` "Correct LMR for 80GB"。它的 README 声称 "Memory geometry (64GB on 8GB cards, 80GB on 10GB cards) | Working ✓"。那个声称是假的，在一到两天内就被分支自己的测试者反驳。把它记为文档缺陷，而不是结果。

**它实际区别在于：** 恰好一个补丁文件、两行。补丁 `0002` 到 `0006` 与 master 逐字节相同。`0001-sec2-postbl-plm-ss-cfg.patch` 只在 `cfg1Value = 0x02669000U` 变成 `0x02779000U`、`targetFbBytes ... 0x0000000A00000000ULL` 变成 `0x0000001400000000ULL` 上不同，另加 `build.sh`、`install.sh` 和 `constants.yaml`。（"没有补丁文件与 master 不同" 的说法是错的。）

**它实际编程什么**，逐行代码验证：

| 层 | 值 | 解码为 |
|---|---|---|
| CFG1 `0x009a0204` | `0x02779000`（档位 `0x77`） | 每 FBPA 4096 MiB × 20 活 = **81920 MiB** |
| LMR `0x00100ce0` | `0x0000028A` | 40 << 10 = **40960 MiB** |
| `targetFbBytes` / GSP `fb_length` | `0x0000001400000000` | **80 GiB** |

那是一个**三方不一致**；而按上面的 CFG1/LMR 连贯规则，它正是让 GSP-RM 在 2026-07-13 实验里回退几何布局的那一类 CFG1/LMR 不匹配。那个实验用了不同的一对——CFG1 `0x02669000` 对出厂 `0x288` LMR——所以机制是类似的而非相同的。

`80/common/constants.yaml` 确实携带 `lmr: "0x0000028B"` 和 `unlocked_mib: 81920`，但 `build.sh` 从不读那个文件。`80/driver/build.sh` 第 93 行设 `LMR="0x0000028A"`，`80/install.sh` 第 138 行打印 `Unlock geometry: 80GB (CFG1=0x02779000 LMR=0x0000028A)`，分支的补丁 `0001` 烘焙 `lmrValue = 0x0000028AU`。构建时重写也被短路：双设备守卫测试 `0x02779000U`、`0x0000020BU`、`0x0000028AU`、`0x0000001000000000ULL` 和 `0x0000001400000000ULL`，全部存在，所以 Python 重写器在替换任何东西之前就退出。**提交 `3c53aca` "Correct LMR for 80GB" 只改了惰性元数据。** 每个跑过 `80` 分支的测试者——无论该提交前后——都编程了 CFG1 `0x02779000` + LMR `0x0000028A` + `fb_length` 80 GiB。

分支还加了一个 master 没有的安装器梯级、`if (( mem_mib >= 75000 )); then echo "10gb"`、放在 `>= 60000` 测试之前，因为没有它一张 81920 MiB 卡会重新检测成 8 GB 卡。master 没有这样的梯级，因为 master 从不产生 81920 MiB 的卡。

**失败签名很精确，但它的每个组成部分都来自单一报告者，没有任何部分被独立复现。** `nvidia-smi` 显示约 81920 MiB、CUDA 报告 `global memory size=85545582592` 字节（79.67 GiB）。77 GiB 的 `cudaMalloc` 和 `cudaMemset` 都成功。一位测试者报告 `cuda_memtest` 在重启后立即完成一次、随后每次运行都失败，并在分配被封顶在 39 GB 之前、`Attached to device 0 successfully.` 之后挂起；第二位操作者在同样的测试后看到 Xid 154，却对第一位操作者的错误明确说 "I don't know what errors [they] are getting."。触碰超过约 40 GB 的内核会造成致命 GPU 丢失、通常需要完整重启。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 内存测试后的 Xid 154；主导报告症状是挂起。Xid 31 单独出现是一个旁观者提出的，并未被持故障卡的操作者佐证为*那个*签名。一位测试者的模型加载在 20 GB 以上失败，另一位在 40 到 60 GB 频段失败。这些失败**与功耗上限无关**。一个小组报告，一张在 40 GB 下干净运行的卡，在 80 GB 的一次 `gpu-burn` 运行里有 2,796 个错误。该配置也只在每次驱动加载时工作一次，而且在至少一个系统上，需要一次冷断电循环而非驱动重载才能再次发射。

注意折叠边界恰好落在 **40 GiB**，匹配分支实际编程的 LMR。下面的免驱动结果让这个匹配看起来是因果而非巧合。

> [!WARNING]
> **实验性：连贯三重奏被发射过，折叠消失了**
>
> 连贯集合**不是**通过重建分支达到的。它是在 2026-07-23 到 2026-07-27 之间由一个净室 refire 脚本达到的，记录 `CFG1=0x02779000 LMR=0x0000028b CST=20/24 resetPLM=0x00ff`，带 L2 解码 `0x10000300`，在 GSP-RM 和 CPU-RM 下都报告 81920 MiB。随后一次稠密带标签写/回读跨 77.5 GiB 返回 310 个块中 310 个正确、**无折叠**；一次更晚的运行在出厂引导时序下到达 72 GiB。限制是真实的：每次发射在 Xid 154 之前约一个 CUDA 上下文、边界之上约 79% 峰值带宽、顶部约 2 GiB 未测、且只有两位操作者。它未发布、也不是一条安装路径。
>
> **已发布的 master 给 10 GB 卡 40 GB，而 40 GB 是受支持的配置。**
> 在 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` 里用 `lmrValue = 0x0000028BU` **并且**在 `driver/build.sh` 里用 `LMR="0x0000028B"`（不只 `constants.yaml`，它不被读）重建分支，仍未尝试——而那正是会告诉你驱动能否承载发射脚本所承载的几何布局的做法。见[80 GB 问题](../frontier/80gb.md)。

一个中间梯级也从没试过。每通道档位很粗（512 / 2048 / 4096 MiB），所以 10 GB 卡上的 48、56 或 64 GB 单靠档位无法到达；它需要 CFG1 钉在档位 `0x77`，驱动可见大小经 `targetFbBytes` 和晚期-PMA 区域上限钳制。在频道里被直接问"10 GB 卡能否解锁到稳定的 60 GB"时，答案是 "I don't believe its been tried."（我不认为被试过）。

---

## 值得知道的死路

- **刷一个不同的 VBIOS。** "16 GB" 170HX 映像（TechPowerUp 239457）和 10 GB 映像（268984）都被刷到一颗接受未签名和不匹配 ROM 的工程样品 GA100 上。板两次都仍报告 8 GB。容量不是加载哪个 ROM 的函数；它跟随跳线选择的 CFG1 字。另一点：把 8 GB VBIOS 刷到 10 GB 卡上会让卡无法引导，归因于设备 ID 不匹配。
- **一次 MAC 伪造的 VBIOS 显存解锁。** 它需要在 `0x41D53`（250 W 170HX）或 `0x41F53`（300 W）翻转一个字节。把 `44` 翻到 `66` 只到 40 GB 几何布局；要到 64 GB 需要 `44` 到 `77`。没有达成过 MAC 伪造，而字节级映射是中等置信度、从未经验测试。
- **L2/LTC amap `0x0017e22c` 作为大于 10 GB 的门。** 这是团队一周多的根因工作模型。写成文字的同一天就被反驳：一次运行在 `0x17e22c` 一直坐在它原生的 `0x00280404`、从未被编程的情况下到达了真实的 40 GB。已发布的驱动里任何补丁、master 或 12 个未发布分支快照上**根本**不含 `0x17Exxxx` 地址。一个声称已发布的 `plmTable` 写 LTC 解码簇（`0x17E2B4`/`A0`/`E4`/`FC`）的说法就是假的。
- **"神秘 PLM" `SEC2_DEBUG_PRI_FBPA_CFG1 0x009a0204`。** `0x009a0204` 是 CFG1 数据寄存器本身，不是 PLM。FBPA PLM 是 `0x009a0148`。
- **每秒寄存器重新应用循环。** 一个第三方提交每秒重写几何寄存器。两位有经验的审查者和一位从未需要它的测试者都否定了它：这个循环会和驱动在算力重定时上相争，与显存解锁毫无关系。
- **`ecc` 分支。** 不含任何 ECC 代码。单一提交 "Fixed dual geometry support"，补丁目录与 master 逐字节相同。
- **"LMR 在 `0x1183A4`。"** 那是 GP102 的本地显存范围位置。验证过的 GA100 地址是 `0x00100ce0`。
- **半字节移位转写。** `0x26690000`、`0x27790000` 和 `0x24490000` 都在聊天里流传。验证过的形式是 `0x02669000`、`0x02779000` 和 `0x02449000`。
- **`docs` 分支。** 它把 CFG1/LMR 表弄对了，却杜撰一个缩写、把 LMR 展开成 "LM Request"。寄存器是 `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`，Local Memory **Range**。同一分支还把 SS0/SS1 错写成 `0xffffffff`/`0xffffffff`；正确的值是 `0x88888888` 和 `0x00000008`。

完整目录见[死路](../history/dead-ends.md)。

---

## 到达同一批寄存器的替代路线

已发布的安装器是一个打过补丁的内核模块，但它不是唯一被演示过的路径。

> [!WARNING]
> **实验性：免驱动可重发 ROP 链**
>
> 一条重入 SEC2 ROP 链被硬件证明，能让 CFG1 = `0x02669000` 存活进一次干净、未修改的 GSP-RM 驱动引导，无 FLR 无 SBR（`BooterLoad 0x0`）。两个赋能技巧：每次发射把它的有用写与一次 WPR2_LO teardown 配对（`0x1fa824` 设成 `0x1ffffe00`、`0x1fa828` 设成 `0x00000000`，即起始大于结束、一个空区域），因为每次 booter 运行都会重新划出 WPR2，把它留 up 会污染下一次溢出；以及让 ACR 互斥锁经干净的 `0x7f2f` 尾释放、把 `resetPLM` 留成 `0xff`。就绪谓词：广播 CFG1 等于目标**且** SEC2 复位 PLM（BAR0 `0x8403c4`，falcon 偏移量 `0x3c4`）读 `0xff`。在这个链里，WPR2_HI 必须作为**最后**一次发射被清除、在主机 CFG1 写之后——因为 `kgspIsWpr2Up_HAL` 读 WPR2_HI VAL 字段，一个出厂驱动否则会以 `NV_ERR_INVALID_STATE` 退出。这个工具链不在已发布的仓库里。

> [!WARNING]
> **实验性：一个未修改驱动的 Python 解锁器**
>
> 一个在驱动加载前运行的脚本在相反结论被得出不可能的第二天被演示：没有打过补丁的 `.ko`、没有安装器。它原则上是已知最干净的路线。它不在已发布的树或任何归档分支里，所以已发布的产品仍是打过补丁的模块路径。

> [!NOTE]
> **泄露的概念验证有何不同**
>
> 泄露的包在 GSP-RM 加载前立即补丁主机内存里的 `WprMeta` 结构，这正是它必然带修改过的开源内核模块的原因。净室方法改开相关的 PLM 并直接写几何寄存器。中等置信度：这是由一个同时持有两样工件的人陈述的，未被独立重新推导。

先于驱动补丁的历史社区 stage-1 poke 集合是五次写：`0x009A0204` = `0x02669000`、`0x00100CE0` = `0x0000028A`、`0x00823804` = `0xFFFFFFFF`、`0x0082381C` = `0x88888888`、`0x00823820` = `0x00000008`。生成器在单次溢出里交付最多五次写、用无害的 `(0x000014A0, 0)` 条目把任何更短的清单填到恰好五个，所以退出帧偏移量保持不变。已发布的驱动在一个方面不同：它经一次 Booter 趟打开 `0x00823804`、而非从主机直接写它。

---

## 参见

- [显存子系统](../hardware/memory-subsystem.md)，物理分区和档位
- [权限级别掩码](privilege-level-masks.md)
- [ROP 链](rop-chain.md) 和[Falcon 与 Booter](falcon-and-booter.md)
- [驱动补丁](driver-patches.md)，按顺序的全部六个补丁
- [算力节流](compute-throttle.md)，同一个窗口的 SS0/SS1 那一半
- [寄存器参考](register-reference.md)
- [验证](../procedures/verify.md) 和[排障](../procedures/troubleshooting.md)
- [80 GB 问题](../frontier/80gb.md)
- [术语表](../start/glossary.md)
