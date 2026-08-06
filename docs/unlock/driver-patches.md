# 六个驱动补丁，逐个

## 本页覆盖内容

出货 CMP 170HX 解锁不是固件刷写、不是用户态守护进程、也不是二进制编辑。它是**六个编号补丁文件**、应用到 NVIDIA 的 `open-gpu-kernel-modules` 版本 610.43.03 或 610.43.02 的一份未修改检出、本地编译、安装为五个内核模块。本页逐个走每个补丁：它改变什么、在哪个源文件里、为什么需要它、丢掉它会怎样失败。

整个解锁（权限级别掩码打开、算力节流写、显存几何写）住在**补丁 0001** 里，在 `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c` 内。其它五个补丁存在，是因为一颗突然声称 64 GiB 帧缓冲的 GA100 破坏了驱动里几个下游假设：致命断言触发、PRAMIN 窗口落出范围、物理内存分配器从不知道新内存、复制引擎清理器选错 PTE kind、RM 在客户端之间拆除软件状态。0002 到 0006 每个恰好修复其中一个。

如果本页只记一条命令：

```bash
sudo dmesg | grep SEC2_DEBUG
```

补丁集发出的几乎每一行都带那个前缀。唯一例外是补丁 0001 降级的 WPR2 警告 `WPR2 already up before GSP boot; continuing for recovery`，它在 `LEVEL_WARNING` 打印、不带 `SEC2_DEBUG:` 标签。

---

## 补丁系列一览

按文件名顺序、用 `patch -p1`、对一份新解压的出厂树应用。

| # | 文件 | 字节 | 行 | 主要源文件 | 角色 |
|---|---|---|---|---|---|
| 0001 | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,278 | 463 | `gpu/gsp/kernel_gsp.c` | 利用：打开 PLM、写 SS0/SS1/CFG1/LMR、加宽 `fb_length` |
| 0002 | `0002-booter-verify.patch` | 3,901 | 87 | `gpu/gsp/arch/turing/kernel_gsp_tu102.c` | 软化四个致命断言，打印引导后回读证明 |
| 0003 | `0003-late-pma.patch` | 10,317 | 263 | `gpu/mem_mgr/mem_mgr.c`、`nvalloc/unix/src/osinit.c` | 把新内存注册给物理内存分配器 |
| 0004 | `0004-bar0-pramin-clamp.patch` | 841 | 20 | `gpu/bus/arch/maxwell/kern_bus_gm107.c` | 让 PRAMIN 窗口保持在可达 BAR0 空间内 |
| 0005 | `0005-ce-scrub-workarounds.patch` | 1,604 | 38 | `mem_mgr/arch/turing/mem_mgr_tu102.c`、`mem_mgr/mem_scrub.c` | 强制清理器进入物理模式、用普通 PTE kind |
| 0006 | `0006-persistent-sw-state.patch` | 584 | 19 | `kernel-open/nvidia/nv.c` | 在 PCI 探测时设置持久软件状态标志 |

总计：**六个补丁 36,525 字节**，触碰**十个不同源文件**。行数含 diff 头。字节数是带 LF 行尾的仓库 blob 大小。在 Windows 上、带 `core.autocrlf=true` 的检出会让每个文件每行膨胀一个字节，这正是常被引用的 37,415 字节总数从哪来的。

系列触碰的文件完整清单：

```text
src/nvidia/generated/g_kernel_gsp_nvoc.h
src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c
src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c
src/nvidia/arch/nvalloc/unix/src/osinit.c
src/nvidia/inc/kernel/gpu/mem_mgr/mem_mgr.h
src/nvidia/src/kernel/gpu/mem_mgr/mem_mgr.c
src/nvidia/src/kernel/gpu/bus/arch/maxwell/kern_bus_gm107.c
src/nvidia/src/kernel/gpu/mem_mgr/arch/turing/mem_mgr_tu102.c
src/nvidia/src/kernel/gpu/mem_mgr/mem_scrub.c
kernel-open/nvidia/nv.c
```

`driver/build.sh` 下载 `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`、缓存到 `driver/.build/` 下、每次运行删除并重新解压一棵干净树，然后循环：

```bash
for p in "${patches[@]}"; do patch -p1 < "${p}"; done
```

脚本在 `set -euo pipefail` 下运行，所以单个被拒 hunk 中止构建。因为循环是 `driver/patches/*.patch` 的一个普通 glob，一个第三方 diff 作为 `0007-*.patch` 放进去会和系列干净组合。那个的唯一条记录案例见[P2P](../frontier/p2p.md)。

五个模块被构建并安装到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko`、`nvidia-peermem.ko`。只有 `nvidia.ko` 携带解锁代码；其它四个是出厂重建、存在是为了让整套有匹配的 `srcversion`。

---

## 六个补丁共享的设备门

每个解锁站点都测试 PCI 设备 ID 的**上 16 位**、对照两个已知的 170HX SKU。补丁 0001 给 `kernel_gsp.c` 加共享辅助函数：

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID  0x2082

static NvBool _kgspSec2PostblTimingEnabled(OBJGPU *pGpu)
{
    NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;
    return (devId == SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID ||
            devId == SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID);
}
```

值得内化的后果：

- 任何其它 GA100 SKU，包括同一机箱里的 A100，都会在装上打过补丁的模块时走完全出厂路径。补丁在它上面是惰性的。
- `install.sh` 对 `lspci` grep `10de:20b0|10de:20c2|10de:2082`，所以一张 `20b0` 卡成功安装、然后永不解锁，因为驱动内门不列出 `0x20B0`。安装器这么说了：`This card reports 0x${DEVID}; install will continue, but unlock may not activate.`
- 补丁 0006 是 `>> 16` 形式的唯一例外。它在 `kernel-open/nvidia/nv.c` 里、PCI 探测时、在 `OBJGPU` 存在之前运行，所以它比较原始的 `nv->pci_info.device_id`。

几何布局在**运行时从设备 ID** 选择，不在安装时。两个档位都烘焙进补丁 0001，所以安装器上的 `--profile=` 只改打印的横幅和元数据文件。见[显存几何布局](memory-geometry.md)。

---

## 0001 `sec2-postbl-plm-ss-cfg`：利用

这才是那个补丁。其它一切都是支持。它是 19,278 字节、约 460 行 diff，做七个不同改动。

### 1. GSP 对象上的两个新字段

插入 `src/nvidia/generated/g_kernel_gsp_nvoc.h`、紧随 `MEMORY_DESCRIPTOR *pSignatureMemdesc;` 之后，hunk 锚点 `@@ -544,6 +544,8 @@`：

```c
NvU8 *pStockSignatureData;
NvU64 stockSignatureSize;
```

真实的 GSP 固件签名在载荷覆盖缓冲区之前被复制进这些字段，记录为 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

> [!CAUTION]
> **先恢复出厂 GSP 固件**
>
> 如果机器跑过 cmpunlocker 的固件打补丁前身，安装驱动补丁前把 `gsp_tu10x.bin` 恢复到出厂。驱动把固件携带的任何签名保存为 "stock"（出厂）。如果磁盘上的固件仍被补丁过，它把**利用载荷**保存为出厂，随后一次干净的 GSP-RM 引导就 DMA 错误的 ROP 链。
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
> ```

### 2. 一个超大的签名缓冲区

`_kgspCreateSignatureMemdesc` 通常分配 `NV_ALIGN_UP(pGspFw->signatureSize, 256)` 字节，实际操作是 4096。设备门为真时它改分配 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL`（63,488 字节）在 `ADDR_SYSMEM`、256 字节对齐，因为 SEC2 Booter 的 DMA 引擎要求。

那个超大缓冲区就是整个利用载体：已签名 Booter 用一次无界 DMA 读它并砸自己栈。机制在[ROP 链](rop-chain.md) 和[Falcon 与 Booter](falcon-and-booter.md) 覆盖。

### 3. 载荷

`_kgspSec2PostblTimingFillPayload` 用 dword `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7` 填满整个缓冲区，然后恰好覆盖 **24 个 dword**，全部由一个按字节的辅助函数 `_kgspSec2PostblTimingPutU32` 小端写：

| 偏移量 | 值 | 角色 |
|---|---|---|
| `0x1100` | `0x00000007` | 栈/控制字 |
| `0x5b40` | `0xc0deca7e` | 假栈金丝雀 |
| `0xf754` | `writeValue` | **每个 PLM 趟被补丁** |
| `0xf758` | `0xc0deca7e` | 金丝雀 |
| `0xf75c` | `0x00000cbd` | gadget |
| `0xf76c` | `writeAddr` | **每个 PLM 趟被补丁** |
| `0xf774` | `0x00001fbd` | gadget |
| `0xf780` | `0x00000000` | |
| `0xf788` | `0x000010aa` | **BAR0 写 gadget** |
| `0xf78c` | `0x0000815a` | 尾 |
| `0xf790` | `0x00008e18` | 尾 |
| `0xf794` | `0xc0deca7e` | 金丝雀 |
| `0xf798` | `0x0000815a` | 尾 |
| `0xf79c` | `0x00000000` | |
| `0xf7a0` | `0xc0deca7e` | 金丝雀 |
| `0xf7a4` | `0x00001fbd` | gadget |
| `0xf7b0` | `0x0000ffbc` | 尾 |
| `0xf7b8` | `0x0000582d` | 尾 |
| `0xf7c4` | `0xc0deca7e` | 金丝雀 |
| `0xf7c8` | `0x00000cbd` | gadget |
| `0xf7d8` | `0x00000003` | |
| `0xf7e0` | `0x00001fbd` | gadget |
| `0xf7f4` | `0x00000ccb` | 尾 |
| `0xf7f8` | `0x00007f2f` | 尾 |

24 个里只有两个在趟之间变化：`0xf76c` 处的 `writeAddr` 和 `0xf754` 处的 `writeValue`。链是一个通用单寄存器写原语、每个目标重发一次。

载荷可从磁盘覆盖。`_kgspCreateSignatureMemdesc` 先尝试 `os_open_and_read_file("/lib/firmware/nvidia/ga100/gsp/dmem.bin", pSignatureVa, 0xf800)`。成功时记录 `SEC2_DEBUG: loaded 63488 bytes from ...`。正常路径上那个文件不存在，驱动记录一个良性状态 `0x59` 并回退到内置填充：

```text
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
```

内置默认武装 `writeAddr = 0x009a0148`、`writeValue = 0xffffffff`，PLM 循环每次迭代立即覆盖它。

> [!NOTE]
> **`0xFACEB13D` 不是出货金丝雀**
>
> 更早的独立 harness 在 `CANARY_ADDR = 0x6340` 带 `DMA_TARGET = 0x0800` 用 `0xFACEB13D`。那是出货 `0x5b40` 金丝雀（`0x5b40 + 0x0800 = 0x6340`）的同一个槽、不同的字面量。读出货代码时预期 `0xc0deca7e`。

### 4. PLM 循环

插入的块坐在 `kernel_gsp.c` 的 `kgspInitRm` 路径里，紧接 `kgspPrepareForBootstrap_HAL(...)` 返回**之后**、不在它里面。hunk 锚点 `@@ -4821,6 +4844,117 @@`。

四个权限级别掩码、每个最多两次尝试。PLM 是一个按寄存器访问控制寄存器：它决定哪个权限级别可以读或写它守护的寄存器。见[权限级别掩码](privilege-level-masks.md)。

```c
/* plmTable[] 条目，逐字取自补丁 0001 */
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

> [!WARNING]
> **四个中三个目标是 `0xffffffff`，WPR_CFG 不是**
>
> `0x001fa7cc` 处的 `WPR_CFG` 被刻意打开到 **`0xfffff0ff`**。循环的成功谓词是 `if (regVal == plmTable[plmIdx].value)`，所以 `0xfffff0ff` 是一个**通过**。项目自己的 `docs/DEBUGGING.md` 说 "All the PLMs must show `0xffffffff`"、`README.md` 说 "Expected: PLMs opening to 0xffffffff"。两者都是宽松措辞。不要把 `WPR_CFG=0xfffff0ff` 读成失败。

每次尝试周围驱动保存并恢复写保护区域 2 的边界。循环前读 `wpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824U)` 和 `wpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828U)`；每次尝试写回两者、为那个 `{address, value}` 对重新填充载荷，然后调用：

```c
kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
    memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
```

并回读目标寄存器。循环后它最后恢复一次 `wpr2Lo`/`wpr2Hi`。最坏情况是**正常引导 Booter Load 之前的八次 Booter Load 执行**。

> [!NOTE]
> **每次载荷趟的 `status=0xffff` 是预期的**
>
> `s_executeBooterUcode_TU102` 在每次运行后发现 seccode 留在 mailbox0 里的一个错误码，所以 `kgspExecuteBooterLoad_HAL` 在载荷趟无条件返回 `NV_ERR_GENERIC`（`0xffff`）。那是注入链已经执行*之后*提出的无效签名抱怨。**寄存器回读是唯一有效的成功标准。**
> `kgspExecuteBooterLoad_TU102` 还在每次运行前执行 `kflcnReset(SEC2)`，所以 SEC2 在趟之间不累积状态。这些早期趟期间 Booter 状态 `0x31` 也被容忍。

失败打印 `FAILED to open %s after 2 attempts`。成功打印：

```text
SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff
```

### 5. 四次主机寄存器写

PLM 打开后，主机 CPU **直接**写解锁寄存器。这一步不涉及利用，这是关键的架构洞见：ROP 链只需要买到写访问，之后一切都是普通 MMIO 存储。

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* FBPA CFG1 */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* MMU LMR   */
```

| 设备 ID | 卡 | `cfg1Value` | `lmrValue` | `targetFbBytes` | 结果 |
|---|---|---|---|---|---|
| `0x20C2` | 8 GB | `0x02779000` | `0x0000020B` | `0x0000001000000000` | 65536 MiB |
| `0x2082` | 10 GB | `0x02669000` | `0x0000028A` | `0x0000000A00000000` | 40960 MiB |

SS0 和 SS1 对**两个 SKU 无条件**写。`common/constants.yaml` 与代码一致（`ss0: "0x88888888"`、`ss1: "0x00000008"`）。

> [!CAUTION]
> **文档分支对 SS0 和 SS1 是错的**
>
> `docs/ARCHITECTURE.md` 声称 cmpunlocker 对 SS0 和 SS1 都写 `0xffffffff`、并显示匹配的预期 dmesg 行。它不写。对着那些字符串验证一次解锁会把一张工作卡看起来坏了。代码自 2026-07-18 起就写 `0x88888888` / `0x00000008`。见[算力节流](compute-throttle.md)。

随后一行回读：

```text
SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)
```

### 6. 出厂签名重建，和第二次 WPR meta 趟

`kgspSec2PostblTimingRebuildStockSignature()` 释放并用 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 在 `NV_ALIGN_UP(stockSignatureSize, 256)` 重新创建 `pSignatureMemdesc`、把保存的出厂签名复制回来、把 `pWprMeta->sysmemAddrOfSignature` 和 `pWprMeta->sizeOfSignature` 重置为新描述符。如果它返回任何非 `NV_OK`，`_kgspBootGspRm` 传播那个状态、引导以 `SEC2_DEBUG: rebuild stock signature failed: 0x%x` 中止。

`kgspPopulateWprMeta_HAL()` 随后被**第二**次调用（它已在 PLM 工作前、出厂位置被调用过）。第一次调用记录 `SEC2_DEBUG: WPR meta fbSize=... wprEnd=... heapSize=...`；第二次记录 `SEC2_DEBUG: WPR meta updated fbSize=... wprStart=... wprEnd=... heapOffset=... heapSize=...`。第二次调用让驱动的 WPR2 摆放与现在加大的几何布局一致。

### 7. WPR2 降级和 GSP 静态信息重写

两个更多编辑完成该补丁。

"WPR2 already up" 致命错误被**降级、不删除**。在现有 `if (kgspIsWpr2Up_HAL(...) && !pGpu->getProperty(pGpu, PDB_PROP_GPU_PREINITIALIZED_WPR_REGION))` 守卫内，锚点 `@@ -4805,14 +4820,22 @@`，两行 `NV_PRINTF(LEVEL_ERROR, ...)` 和 `return NV_ERR_INVALID_STATE;` 变成一行：

```c
NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n");
```

执行直落进 `kgspPopulateWprMeta_HAL`。这是强制性的：解锁运行 Booter Load 最多八次，而 Booter Load 让 WPR2 保持 up。

然后，在 `@@ -5164,6 +5285,53 @@`、`kgspInitRm` 收到 GSP 静态配置信息之后，补丁重写它：`pGSCI->fb_length = targetFbBytes`，如果最后一个 FB 区域的 `limit` 低于 `targetFbBytes - 1` 则设 `limit = targetFbBytes - 1`、`reserved = limit - base + 1`、`supportCompressed = NV_TRUE`、`supportISO = NV_TRUE`、`performance = 20`。记录为 `SEC2_DEBUG: static-info BEFORE/AFTER`。

### 没有 0001 会怎样

一切。没有解锁。卡以出厂 8192 或 10240 MiB、带算力节流引导。

---

## 0002 `booter-verify`：断言和证明

只碰 `src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c`。三个任务。

**它命名五个寄存器。** 这些 define 纯粹为这个文件里的日志：

```c
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM        0x00823804
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED   0x0082381c
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820
#define SEC2_DEBUG_PRI_FBPA_CFG1                   0x009a0204
#define SEC2_DEBUG_PRI_MMU_LMR                     0x00100ce0
```

注意名字：SS0 和 SS1 的 `FEATURE_OVERRIDE_SM_SPEED` 和 `_SM_SPEED_1`。那是代码自己对算力节流寄存器的命名，读起来像时钟或吞吐控制、而非一个簇使能位掩码。

**它把四个致命断言转成记录的日志状态检查**，在 `kgspBootstrap_TU102` 里：`pPreparedFwsecCmd != NULL` 上的 `NV_ASSERT_OR_RETURN`、`NV_ASSERT_OK_OR_RETURN(kflcnReset_HAL)`、FWSEC 状态断言、和 `NV_ASSERT_OK_OR_RETURN(kflcnResetIntoRiscv_HAL)`。

**它打印决定性的证明行。** 真实 `kgspExecuteBooterLoad_HAL` 之后，只对两个设备 ID，打印 `SEC2_DEBUG: normal BooterLoad status=0x%x`，然后、只有当那个状态是 `NV_OK` 时：

```text
SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...
```

那是显示解锁挺过真实 GSP 引导、而非仅仅载荷趟的回读。

### 没有 0002 会怎样

控制流实际上不变：替换物仍在任何非 `NV_OK` 结果时 `return status`、从 FWSEC 或两个 Falcon 复位，正如断言那样。0002 买到的是诊断。没有它，没有任何东西命名四个步骤里哪个失败、带什么状态，而唯一的引导后验证行消失——那是每个排障流程要的那一行。见[验证](../procedures/verify.md)。

---

## 0003 `late-pma`：让内存可分配

补丁 0001 告诉 GSP-RM 帧缓冲更大。那不等于让额外内存可分配。物理内存分配器（PMA）仍必须被告知。补丁 0003 有**四个 hunk** 加一个钩子。

1. `src/nvidia/inc/kernel/gpu/mem_mgr/mem_mgr.h` 里 `memmgrSec2DebugLateExtendHighPmaRegion` 的一个前向声明。
2. `kmemsysPostHeapCreate_HAL` 之后的一条诊断：`SEC2_DEBUG_HEAP: fbAddrSpace=... mapRam=... fbTotal=... fbUsable=... heapTotal=... regionBytes=... publicBytes=... numRegions=...`
3. `memmgrSec2DebugLateExtendHighPmaRegion()` 本身，约 180 行。
4. 另一个 CeUtils 虚拟模式排除，附加到 `mem_mgr.c` 的 compbit-backing 条件。第一个在补丁 0005（`mem_scrub.c`）；全系列里有两个。补丁 0005 的第二个 hunk 是 PTE-kind 覆盖（`NV_MMU_PTE_KIND_GENERIC_MEMORY`），不是虚拟模式守卫。

加 `src/nvidia/arch/nvalloc/unix/src/osinit.c` 里调用它、在 `RmInitAdapter` 晚期、记录 `SEC2_DEBUG: late PMA extension status=0x%x` 的钩子。

函数本身：

```text
stockFbBytes = 0x200000000ULL           /* 8 GiB，为两个 SKU 硬编码 */
candidate    = 最高-limit 的 Ram.fbRegion[] 条目，满足
               bRsvdRegion && !bInternalHeap && limit >= stockFbBytes
pmaRegion    = [ NV_MAX(base, stockFbBytes), limit ]，bSupportCompressed = NV_TRUE
早退         如果 pmaIsPmaManaged 已覆盖该范围
pmaRegisterRegion(pPma, numPmaRegions, NV_FALSE, &pmaRegion, 0, NULL)
然后，仅在 NV_OK 时：
  split   -> 追加公共 FB_REGION_DESCRIPTOR [8 GiB, limit]，带
             bRsvdRegion = NV_FALSE、bInternalHeap = NV_FALSE、
             bSupportCompressed = NV_FALSE；把保留区域钳到 stockFbBytes - 1
  或
  in-place-> 清除 bRsvdRegion
最后  memmgrRegenerateFbRegionPriority()
```

如果需要拆分且 `numFBRegions >= MAX_FB_REGIONS`，它返回 `NV_ERR_INSUFFICIENT_RESOURCES` 而非拆分。

> [!NOTE]
> **`stockFbBytes` 在 10 GB 卡上也是 8 GiB**
>
> `0x200000000ULL` 为两个档位硬编码。在 `0x2082` 卡上边界因此是 8 GiB、而非卡原生的 10 GiB。这在出货代码里、不是本维基的笔误。

### 没有 0003 会怎样

额外帧缓冲被报告却从不交给 PMA，所以区域保持保留、高于出厂大小的分配失败。这是 "nvidia-smi shows 65536 MiB" 和 "you can actually allocate 63 GB"（你真能分配 63 GB）之间的区别。

---

## 0004 `bar0-pramin-clamp`：让 PRAMIN 可达

最小也最有趣的补丁：`src/nvidia/src/kernel/gpu/bus/arch/maxwell/kern_bus_gm107.c` 里一个十行 hunk。PRAMIN 是 BAR0 里一个 CPU 经它到达帧缓冲内存的滑动窗口。出厂代码把它放在帧缓冲顶部：

```c
offsetBar0 = (pMemoryManager->Ram.fbAddrSpaceSizeMb << 20) - DRF_SIZE(NV_PRAMIN);
```

补丁加，对 `0x20C2` 或 `0x2082` 且 `Ram.fbAddrSpaceSizeMb > 0x2000`（8192 MB）时：

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

注意阈值是 8192 MB，所以钳制在一张出厂 10 GB 卡上也会生效，不只在一张解锁的卡上。

### 没有 0004 会怎样

PRAMIN 孔径从 65536 MB 计算、落出可达 BAR0 空间。GA100 BAR0 是一个 16 MiB PRI 孔径；放在 64 GiB 地址空间顶部的一个窗口根本无法经它寻址。

---

## 0005 `ce-scrub-workarounds`：物理模式清理

`master` 上两个 hunk。

`mem_mgr_tu102.c` 里，清理器的 PTE-kind 辅助函数用 `ENG_GET_GPU(pMemoryManager)` 获取 GPU、对两个设备 ID 早退：

```c
*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY;   /* 而非 */
/*         NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC */
```

`mem_scrub.c` 里，`if (memmgrUseVasForCeMemoryOps(pMemoryManager))` 守卫获得：

```c
&& ((pGpu->idInfo.PCIDeviceID >> 16) != 0x20C2
 && (pGpu->idInfo.PCIDeviceID >> 16) != 0x2082)
```

所以 `DRF_DEF(0050, _CEUTILS_FLAGS, _VIRTUAL_MODE, _TRUE)` 永不被设、复制引擎清理器在**物理**模式运行。另一个虚拟模式排除在补丁 0003。

### 没有 0005 会怎样

清理器用一个可压缩的 PTE kind、跨一个 MMU 表并非为之构建的帧缓冲尝试虚拟模式复制引擎操作。这是你最可能想跳过、却绝不该跳过的补丁。

---

## 0006 `persistent-sw-state`：不需要守护进程

共十九行、其中九行是加的代码，在 `kernel-open/nvidia/nv.c`、`@@ -1521,6 +1521,15 @@`、插在 IRQ 设置错误路径之后、`(void)rm_get_gpu_uuid_raw(sp, nv);` 之前：

```c
if (nv->pci_info.device_id == 0x20C2)
{
    nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;
}
else if (nv->pci_info.device_id == 0x2082)
{
    nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;
}
```

两个分支相同、能合并成一个条件。美观问题，不是 bug。

`NV_FLAG_PERSISTENT_SW_STATE` 是一个为 SR-IOV 虚拟功能而存在的 `nv.h` 标志。在这里改作它用，它阻止 RM 在最后一个客户端关闭时拆除软件状态。它实际就是内置持久化模式，也是当前设计不需要 systemd 看门狗的原因。更早几代的工具确实需要一个；`remove.sh` 仍清理当前安装器从不创建的遗留 `cmpunlocker.service` 和 `/opt/cmpunlocker/daemon/watchdog.py`。见[工具谱系](../history/tool-lineage.md)。

### 没有 0006 会怎样

RM 在最后一个客户端退出时拆除 GPU 软件状态。在一张几何布局于驱动加载期间确立的卡上，那种拆除-再构建循环正是你在 CUDA 进程之间不想要的。

---

## 读一次成功的引导

```bash
sudo dmesg | grep SEC2_DEBUG
```

预期序列，按顺序：

| 行 | 来自 | 含义 |
|---|---|---|
| `saved stock signature (4096 bytes)` | 0001 | 真实签名被复制走 |
| `<dmem.bin path> not found (0x59), using built-in payload` | 0001 | 正常，无覆盖文件 |
| `WPR meta fbSize=... wprEnd=... heapSize=...` | 0001 | 第一次 WPR meta 趟 |
| 每-PLM 行，`status=0xffff` | 0001 | 每次载荷趟都预期 |
| `PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff` | 0001 | 全部四个打开 |
| `POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x...)` | 0001 | 解锁寄存器被写 |
| `WPR meta updated fbSize=...` | 0001 | 第二次 WPR meta 趟 |
| `normal BooterLoad status=0x0` | 0002 | 真实引导成功 |
| `POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...` | 0002 | 挺过真实引导 |
| `static-info BEFORE/AFTER` | 0001 | `fb_length` 加宽，GSP 返回其静态配置后 |
| `late PMA extension status=0x0` | 0003 | 新内存可分配 |

610.43.03 上一次工作的双卡 8 GB 引导的一份参考捕获包含 **152** 条 `SEC2_DEBUG` 行（中等置信度、单一捕获）。轨迹缺失本身不证明失败，因为内核环形缓冲区会轮转。

> [!NOTE]
> **行数不是可靠的跨构建指纹**
>
> 34（Gen1 构建）/ 80（Gen2 构建）被高置信度记录，而另一次独立的 Gen2 分支 610.43.03 引导在中等置信度下数到 152。不要把不匹配读成安装失败。

---

## 命名，以及它为什么看起来像一个 NVIDIA 功能

补丁用虚构的 NVIDIA 风格名字伪装自己。`SEC2_DEBUG_PRI_*`、`kgspSec2PostblTiming*` 和 `SEC2_DEBUG:` 日志前缀在出厂 610.43.03 源码里**任何地方都不出现**。"PostBL Timing" 是一个听上去合理却是虚构的功能名。两次独立审查把这读成把利用代码刻意伪装成制造或调试功能，并作为反 NVIDIA 内部作者身份的证据，因为一个有合法内部访问权的人不需要伪装。实际后果是那个有用的：单次 grep 就在引导日志里找到每一条解锁行。

> [!NOTE]
> **要忽略的虚构缩写展开**
>
> `docs` 分支把 PLM 展开成 "Program Logic Modules"、SS0/SS1 展开成 "Suspension State" 寄存器、PMA 展开成 "Power Management Array"，并引入一个代码里任何地方都不出现的 "SEC2 Booter PMM"。四个全错。PLM 是权限级别掩码；PMA 是物理内存分配器（`pmaRegisterRegion`、`pmaGetFreeMemory`、`PMA_REGION_DESCRIPTOR`、`pmaIsPmaManaged`）；代码自己对 SS0/SS1 的命名是 `FEATURE_OVERRIDE_SM_SPEED` 和 `_SM_SPEED_1`。不要传播这些展开。

---

## 出货系列**不**含什么

几条被广泛复述的说法描述的是 cmpunlocker `master` 之外的工件。验证过六个补丁里都不存在：

| 说法 | 现实 |
|---|---|
| `gpuValidateRegOps` 被桩成 `return NV_OK` | 不存在。对 `subdevice_ctrl_gpu_regops.c` 根本没有任何改动。发布前的 `patch.diff`、以及显然泄露的包确实携带了对寄存器操作权限验证的无条件绕过；它在发布前被去掉。那是真实的安全改进、不是清理。 |
| 对 `pWprMeta->fbSize` 的 `CMP170HX_WPR2_SAFE_LIMIT 0x0A00000000ULL` 钳制 | 被提出，从未出货。发布的设计加宽 `fb_length` 和最后一个 FB 区域、只钳制 BAR0/PRAMIN 窗口。 |
| 把除 `0x00000000`/`0x00000031` 外的一切当活的邮箱值容差 | 被提出，从未出货。字面量 `0x00000031` 在仓库里任何地方都不出现。 |
| `0x00100ce4` LMR-lock 清除/重新锁定变通方案 | 在出货代码里任何地方都不出现。被记录为一份 40 GB 指南里的未测试应急方案，其片段还瞄准了错误的文件（`kernel_gsp_tu102.c`；LMR 写在 `kernel_gsp.c`）。 |
| 对 `gsp_tu10x.bin` 的任何 ELF 手术 | 没有。那是第一代方法，2026-07-18 被取代。 |
| PCIe Gen2 补丁 `0007`/`0008` | 不在 `master` 上。仅分支。见[PCIe Gen2](pcie-gen2.md)。 |
| `kflcnIsRiscvActive` 绕过 | 六个补丁里都不存在。 |

master 的补丁集是 `0001` 到 `0006`、没有别的。

---

## 相关页面

- [解锁如何工作](how-it-works.md)，端到端引导故事
- [权限级别掩码](privilege-level-masks.md)，四个 PLM 目标的细节
- [显存几何布局](memory-geometry.md)，CFG1、LMR 和容量算术
- [算力节流](compute-throttle.md)，SS0 和 SS1
- [驱动版本](../procedures/driver-versions.md)，为什么 610.43.0x 以及回移植做什么
- [寄存器参考](register-reference.md) 和[寄存器索引](../appendix/register-index.md)
- [排障](../procedures/troubleshooting.md)，当 `SEC2_DEBUG` 轨迹提前停止时
