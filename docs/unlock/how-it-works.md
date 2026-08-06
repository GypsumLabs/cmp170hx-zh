# 解锁如何工作

**本页覆盖内容。** 完整的机制，端到端，按它在启动时发生的顺序，附每一步存在的原因。一位胜任的工程师应该能读本页而不打开源码就理解整个设计。逐寄存器细节在[寄存器参考](register-reference.md)；Falcon 内部在[Falcon 与 Booter](falcon-and-booter.md)；载荷构造在[ROP 链](rop-chain.md)。

一句话版本：驱动把 GSP 签名缓冲区放大到 `0x0000f800`、用精心构造的 Falcon ROP 载荷填满它、对每个权限级别掩码各重跑一次 NVIDIA 自己签名的 SEC2 Booter Load 以获得一条 Heavy-Secure 权限级别的任意 BAR0 写、打开四个 PLM、写四个普通主机寄存器、恢复真实签名，然后让 GSP 带着打进它报告的静态信息里的新几何布局正常引导。

---

## 为什么必须这样做

三条实测的约束逼出整个设计。每一条都是艰难发现的。

**1. 显存几何布局不挺过复位，但算力解锁能。** 在一次功能级复位上测得：

| 寄存器 | 挺过 FLR？ |
|---|---|
| `SS0 0x0082381c` | **是** |
| `SS1 0x00823820` | **是** |
| `FEAT_OVR_PLM 0x00823804` | **是**（常电岛） |
| `CFG1 0x009a0204` | 否，回退到 `0x02449000` |
| 每-FBPA CFG1、CSTATUS | 否 |
| `LMR 0x00100ce0` | 否，回退到出厂值 |
| FB 几何 PLM | 否，它们重新上锁 |
| AON LMR 影子 `0x001180f0` | 否，回退 |
| SEC2 复位-PLM 污染 | 被 FLR **清除**（`0x8f` 变回 `0xff`） |

在一份 26 寄存器调查里，`FEAT_OVR_PLM` 是唯一标为常开的 PLM。这种不对称正是算力解锁比显存解锁早几周出货的唯一原因，也是显存解锁不能用旧的算力配方（"发射、FLR、然后从主机写"）的原因。

**2. 帧缓冲几何布局没有常开影子。** 花了几小时扫寻一个，因为 SS0 有一个可找的 AON 影子、一篇已发表论文描述了该概念。在全部六个 FB 几何 PLM 加上 `FUSE_SS_PLM` 都打开的情况下，CFG1、CSTATUS 和 LMR 仍会在 FLR 时回退、从不在冷启动时持久。一次专门的 FLR 存活映射运行得出结论：没有任何 PLM 把 FBPA 配置移进常电域。因此几何布局必须在**每次**模块加载时重新应用。

**3. 出厂驱动会重新锁上无驱动工具打开的东西。** 在没有驱动加载的情况下从主机写 `0x009A0204`、`0x0082381C` 和 `0x00823804` 有效，写入明显落地，然后加载出厂驱动把 `0x00823804` 回读为 `0xffffff8f`、节流分频器恢复到 5。那个失败正是驱动内方法存在要解决的。

再加一个排序约束：**GSP-RM 在自己的引导期间把 LMR 当主寄存器。** 当 CFG1 设成 40 GB 档位但 LMR 留在出厂 `0x288` 时，GSP-RM 在 `kgspBootstrap` 期间把每-FBPA `CSTATUS_RAMAMOUNT` 从 `0x800` 回退到 `0x200`。所以几何布局必须在*真实* Booter Load 启动 GSP-RM **之前**就位，而不是之后。

维护者得出的结论：在 `_kgspBootGspRm` 内做这一切，介于驱动拥有一条它控制的签名缓冲区的点、与真实 Booter Load 运行的点之间。

---

## 第 0 步：解锁坐在 GA100 引导链的哪里

```text
上电
  └─ GFW / DEVINIT        来自闪存的签名固件；读 RAMCFG 跳线，
                          锁存 L2 地址映射。尚无 RM。永远锁定。
  └─ CPU 侧 RM（nvidia.ko）
       ├─ kgspPopulateWprMeta      把硬件几何布局 / LMR 读进 WprMeta.fbSize，
       │                           决定 WPR2 摆放
       ├─ kgspPrepareForBootstrap  运行 FWSEC / FRTS（VBIOS devinit）
       └─ kgspBootstrap            ◀── 解锁在这里运行，在 _kgspBootGspRm 内
            └─ SEC2 Booter Load    签名 Falcon ucode；划分 WPR2，启动 GSP-RM
  └─ GSP-RM                        封闭的 RISC-V 固件，跑在 GPU 上
```

因为冷启动总是用锁定的 CMP 跳线表运行签名的 DevInit，首次枚举总是显示出厂容量、出厂 Gen1 链路和节流就位。普通的 `rmmod` / `modprobe` **不**重跑 DevInit（没有断言 PERST），这就是上一次加载写的几何布局能挺过驱动重载、却不能挺过复位的原因。

---

## 第 1 步：驱动加载并检测设备 ID

补丁 0001 给 `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c` 加了一个门辅助函数：

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

**为什么移位。** `pGpu->idInfo.PCIDeviceID` 打包厂商和设备；设备半是上 16 位。补丁 0001 到 0005 里每个解锁站点都用同样的方式测试。补丁 0006 是唯一的例外，比较原始 `nv->pci_info.device_id`，因为它在 PCI 探测时运行于 `kernel-open/nvidia/nv.c`、在 `OBJGPU` 存在之前。

**为什么是运行时门而非构建时门。** 两个几何布局档位都编译进同一个模块：

```c
if (devId == 0x20C2) { cfg1Value = 0x02779000U; lmrValue = 0x0000020BU; }
else                 { cfg1Value = 0x02669000U; lmrValue = 0x0000028AU; }
```

`driver/build.sh` 仍包含一个以前重写这些常量的内联 Python 步骤，但在 `master` 上它检测到两个几何布局都已存在，并以 `runtime device-id geometry (profile metadata=<label>)` 退出、不编辑任何东西。因此一个误检测的 `--profile` 会写错误的元数据，却不可能产生错误的几何布局。

任何其它 GA100 SKU，包括 `10de:20b0`，即使装上补丁模块也走出厂路径。

---

## 第 2 步：签名缓冲区被放大到 `0xf800`

`_kgspCreateSignatureMemdesc` 通常分配 `NV_ALIGN_UP(pGspFw->signatureSize, 256)` 字节，在这个平台上是 4096。当设备门为真时它改分配 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL`（63,488 字节）在 `ADDR_SYSMEM`，256 字节对齐。覆盖任何东西之前，真实签名字节被复制到两个新的 `KernelGsp` 字段里：

```c
NvU8 *pStockSignatureData;
NvU64 stockSignatureSize;
```

记录为 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

**为什么恰好 0xf800。** 这就是整个利用。bug 是 **Booter 的 LS 签名验证里的一次无界 DMA**：IMEM `0x29C4` 处的 `booterVerifyLsSignatures_TU10X` 调用 `booterIssueDma_HAL`，DMEM 目的地固定、传输长度直接从 `WprMeta` 的 `sizeOfSignature` 取、没有任何边界检查。DMA 目的地是 **DMEM `0x0800`**，而 Falcon DMEM 是 64 KB。所以：

```text
0x0800（DMA 基址）+ 0xF800（长度）= 0x10000（DMEM 末尾）
```

载荷 1:1 映射到 DMEM `0x0800`..`0xFFFF`，也就是 Booter 运行时用的每一块东西，包括它的栈、它的保存返回地址、和栈金丝雀全局。恰好选 `0xf800` 让最后一个载荷字节落在最后一个 DMEM 字节上。（算术自洽：载荷在偏移量 `0x5b40` 写假金丝雀，而 `0x5b40 + 0x800 = 0x6340`，即独立反汇编的金丝雀全局地址。）

**为什么这是 ROP 而非代码执行。** Falcon 把指令存在 IMEM、数据存在 DMEM。溢出只到达 DMEM。它给出对 Falcon 调用栈上返回地址的控制，所以攻击必须由已签名 booter 映像里已有的 gadget 构建。

**缓冲区不含什么。** 早期一个来自固件拼接时代的信念是，缓冲区必须以真实、有效的签名开头，因为把整个 `0xF800` 区域零填充让出厂 booter 以邮箱 `0x31` 退出。出货载荷不保留它：`_kgspSec2PostblTimingFillPayload()` 从偏移量 0 向上给每个 dword 写 `0x000004a7`，从不把签名字节复制回来。保存的出厂字节只活在 `pStockSignatureData` 里，直到第 7 步把它们放回去。邮箱 `0x31` 也是成功的载荷回合所报告的，所以单独看它不是签名有效性的判决。

`_kgspCreateSignatureMemdesc` 还尝试对 `/lib/firmware/nvidia/ga100/gsp/dmem.bin` 调用 `os_open_and_read_file()`，失败时记录 `SEC2_DEBUG: <path> not found (0x59), using built-in payload`。状态 `0x59` 是良性且预期的。

---

## 第 3 步：载荷被写入

`_kgspSec2PostblTimingFillPayload(buffer, writeAddr, writeValue)` 先把缓冲区的每个 dword 填上 `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7`，然后覆盖这些槽。DMEM 列就是载荷偏移量加 `0x800`：

| 载荷偏移量 | DMEM | 值 | 角色 |
|---|---|---|---|
| 全部 | `0x0800`-`0xFFFF` | `0x000004a7` | 填充 dword |
| `0x1100` | `0x1900` | `0x00000007` | `f100_field_save_restore` 门；让 SEC2 复位 PLM 停在 `0xff` |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **假金丝雀写入守卫全局** |
| `0xf754` | `0xFF54` | *writeValue* | 值参数 |
| `0xf758` | `0xFF58` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf75c` | `0xFF5C` | `0x00000cbd` | |
| `0xf76c` | `0xFF6C` | *writeAddr* | 地址参数 |
| `0xf774` | `0xFF74` | `0x00001fbd` | |
| `0xf780` | `0xFF80` | `0x00000000` | |
| `0xf788` | `0xFF88` | `0x000010aa` | **BAR0-master 写 gadget** |
| `0xf78c` | `0xFF8C` | `0x0000815a` | |
| `0xf790` | `0xFF90` | `0x00008e18` | |
| `0xf794` | `0xFF94` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf798` | `0xFF98` | `0x0000815a` | |
| `0xf79c` | `0xFF9C` | `0x00000000` | |
| `0xf7a0` | `0xFFA0` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf7a4` | `0xFFA4` | `0x00001fbd` | |
| `0xf7b0` | `0xFFB0` | `0x0000ffbc` | |
| `0xf7b8` | `0xFFB8` | `0x0000582d` | |
| `0xf7c4` | `0xFFC4` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf7c8` | `0xFFC8` | `0x00000cbd` | |
| `0xf7d8` | `0xFFD8` | `0x00000003` | |
| `0xf7e0` | `0xFFE0` | `0x00001fbd` | |
| `0xf7f4` | `0xFFF4` | `0x00000ccb` | 见下面的未解问题 |
| `0xf7f8` | `0xFFF8` | `0x00007f2f` | 最外层槽 |

这个块在 `master` 和全部十二个归档分支里逐字节相同。魔法值 `0xc0deca7e` 在每份副本里恰好出现五次。

**为什么是假金丝雀。** booter 每次启动生成一个新鲜的随机栈金丝雀，把它存在 DMEM `0x6340` 的全局里。每个受保护函数把它复制到栈帧边界并在退出时重新比较；不匹配调用 `panic()`。因为该值每次启动重新生成，它无法离线猜测。载荷不需要猜它：它用 `0xc0deca7e` 覆写*全局*并把同一个常量写进每个重建的金丝雀槽，所以每个序言比较都通过、展开静默进行。

**为什么是 `0x000010aa`。** 那是 `reg_write_indirect`，booter 自己的任意 BAR0 写例程。它与 NVIDIA 的 `_acrlibBar0RegWrite_TU10X` 逐字节相同，并驱动 Falcon CSB 空间里一个间接、互斥门控的邮箱：

```text
I[0x1c100] = 目标 PRI 地址
I[0x1c200] = 数据
I[0x1c000] = 0x800000f2   （写；0x800000f1 是读）
```

booter 用它做自己的事，这正是该原语如何被识别。那一个 gadget 就是整个提权：它在 LEVEL2 内执行，在一个真实的、签名的、已验证的 HS 映像里。

**为什么每次发射只写一个寄存器。** 链在出去的路上必须重建 booter 的栈帧，而每次写花一个 `0x18` 字节帧。独立实现把硬上限放在每次发射两到六次写之间，无驱动引擎拒绝构建一到两次写之外的载荷。出货驱动每次发射做**一次**写并简单重发，这更简单也没有预算风险。

---

## 第 4 步：执行 Booter Load 以获得写原语

每一轮驱动调用：

```c
kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
    memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
```

`kgspExecuteBooterLoad_TU102` 在每次运行**之前**执行 `kflcnReset(SEC2)`，所以 SEC2 在轮次之间不累积状态。Booter 加载、通过它自己映像（未触碰且真实）的 RSA-3072 引导 ROM 检查、把自己解密进 HS 模式、开始验证 LS 签名、把 `0xf800` 字节 DMA 进 DMEM，并通过注入的返回地址而非它自己的展开。

> [!WARNING]
> **报告的状态总是失败，而这是预期的**
>
> 每个载荷轮次都记录 `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` 和 `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`，而寄存器写入仍然落地。seccode 在每次运行后在邮箱 0 里留下一个错误码，而 `mailbox0 != 0` 让 HAL 返回 `NV_ERR_GENERIC`（`0xffff`）。**寄存器回读是唯一有效的成功标准**，而它恰好是出货循环用的标准。不要把 `status=0xffff` 读成问题。

一次 Booter 轮次大约花 **180 ms**。

---

## 第 5 步：按顺序打开四个 PLM

权限级别掩码是一个按寄存器块的门：它决定哪些权限级别可以读或写它所覆盖的寄存器。在 PL0（来自内核驱动的一次普通主机 BAR0 写）时，目标寄存器根本无法写，而重要的是，**失败是静默的**。一条早期流水线在没有任何地方报告错误的情况下记录了三次 `Write failed - wrote 0x2779000, read 0x2449000`。

出货 `plmTable[]` 恰好四项，按此顺序打开：

| 索引 | 名称 | 地址 | 写入的值 | 为什么需要 |
|---|---|---|---|---|
| 0 | WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | 门控 booter 验证、驱动操纵的 WPR 配置块 |
| 1 | FBPA | `0x009a0148` | `0xffffffff` | 门控 FBPA 孔径，包括 `CFG1 0x009a0204`。也是内置回退载荷目标 |
| 2 | WPR | `0x001fa7c4` | `0xffffffff` | 门控 WPR 区域寄存器 |
| 3 | FEAT | `0x00823804` | `0xffffffff` | `FEAT_OVR_PLM`。门控特性覆盖块，即 SS0 和 SS1 |

> [!WARNING]
> **WPR_CFG 打开到 `0xfffff0ff`，不是 `0xffffffff`**
>
> 分发 README 和 `docs/ARCHITECTURE.md` 都说每个 PLM 应读 `0xffffffff`。代码对条目 0 写并验证 `0xfffff0ff`。把 `0xfffff0ff` 当规范：它是出货循环既写也核对的值。

每个条目最多**两次尝试**。尝试循环是：

```text
for each plmTable entry:
    for attempt in 1..2:
        GPU_REG_WR32(0x001fa824, wpr2Lo)      # 重新装填 WPR2 低
        GPU_REG_WR32(0x001fa828, wpr2Hi)      # 重新装填 WPR2 高
        kgspSec2PostblTimingRefillPayload(addr, value)
        kgspExecuteBooterLoad_HAL(...)         # 返回 0xffff；忽略
        if GPU_REG_RD32(addr) == value: break  # 回读是判决
restore wpr2Lo / wpr2Hi one final time
```

**为什么每次尝试前必须重新装填 WPR2。** WPR2 由 ADDR_LO `0x001fa824` 和 ADDR_HI `0x001fa828` 控制。当 HI 为零时 `kgspIsWpr2Up()` 返回 false。每次 Booter Load 轮次划分 WPR2 并让它保持 up；第二次 Booter Load 会以 "WPR2 already up" 中止。在每次尝试前保存循环前的值并重写它们，把寄存器放回驱动和 booter 都期望的状态。同一个问题也是补丁 0001 把 `_kgspBootGspRm` 里的致命路径降级的原因：

```c
/* 出厂 */
NV_PRINTF(LEVEL_ERROR, "unexpected WPR2 already up, cannot proceed with booting GSP\n");
return NV_ERR_INVALID_STATE;

/* 打补丁 */
NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n");
```

然后执行直接落入 `kgspPopulateWprMeta_HAL`。

**为什么 `FEAT_OVR_PLM` 能被打开。** 门链是 `FUSE_QUADRO_WR_SEC`（`0x0082038c`）= 1 允许打开 `0x00823804`；打开 `0x00823804` 允许 PL0 主机写 SS0/SS1；特性覆盖寄存器级别高于熔丝。而整条链存在只是因为 `0x008203f0` 处的主灭杀熔丝 `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` 在 170HX 上读 `0x00000000`。若它被烧断，任何权限级别都不存在软件路径。PLM 本身不是 PL0 可写的：它必须从一个 HS 模式的 Falcon 打开，"if this was not so, any Nvidia card could be unlocked without any exploit"（如果不是这样，任何 NVIDIA 卡都能不带任何利用被解锁）。

出货树对 `0x008200fc`（`FUSE_SS_PLM`，分支源码里叫 `OPT_PLM`）**什么都不写**。一条更早的合并配方要求打开它；它已被观察到在出厂卡上读 `0xffffffff`，所以打开它不必要。Gen2 家族分支确实加它，作为把表从四项变九项的五条额外条目之一。

---

## 第 6 步：算力和几何寄存器被写入

PLM 打开后，提权结束了。四条普通主机写落地整个解锁，不含任何利用：

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* FBPA CFG1 广播 */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* MMU 本地显存范围 */
```

随后一次回读记录为 `SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)`。

### SS0 和 SS1：算力去节流

`0x0082381c` 是 `NV_FUSE_FEATURE_OVERRIDE_SM_SPEED_SELECT`，持有 IMLA0-3、FMLA16、FMLA32、FFMA 和 DP 的八个 4 位字段。`0x00823820` 是 `..._SM_SPEED_SELECT_1`，持有 IMLA4 的第九个字段。每个半字节读作 `[enable | 3-bit speed]`：`0x8` 置位第 3 位（覆盖使能）配速度字段 0（全速）。所以 `0x88888888` 意味着全部八个 SS0 单元上 "override enabled, full rate"（覆盖启用、全速），`0x00000008` 对 IMLA4 单独做同样的事。

**为什么两者都要。** 只写一个不够；这被频道内独立强调，并反映在每对出货写入里。

**为什么这有效而熔丝仍烧着。** 节流按算术单元 OTP 熔断：`FUSE_SS_FFMA`、`FUSE_SS_FMLA16/32` 和 `FUSE_SS_IMLA0-4` 在 170HX 上全读 `0x5`（除以 32）、在每个被探测的 A100、A10、A5000、A6000 和 Drive A100 上读 `0x0`。一次成功解锁后那些熔丝影子**仍读 `0x5`**。有效速率由一个可写覆盖仲裁，它优先于熔丝，而非直接来自熔丝。确认是 `0x00823818` 处的 `FEAT_READOUT_1`、全部九个单元的有效速度选择，从 `0x016db6ed` 掉到 `0x00000000`。

### CFG1 和 LMR：几何布局

`0x009a0204` 是 FBPA CFG1 广播寄存器。它在位 [23:16] 的档位字节编码每个显存分区的寻址深度：`0x44` 出厂（12 行位，每 FBPA 512 MiB）、`0x66`（14 行位，2048 MiB）、`0x77`（15 行位，4096 MiB）。总容量是寻址深度乘以熔丝决定的活-FBPA 数，CFG1 不碰后者。两个出货值字面上就是真实 A100 部件的出厂 CFG1 字：`0x02779000` 是 A100 PCIe 80 GB 读的值，`0x02669000` 是 A100 PCIe 40 GB 和 SXM4 40 GB 读的值。解锁恢复真正的 A100 几何布局，而非发明常量。

`0x00100ce0` 是 MMU 本地显存范围。它把总帧缓冲大小编码为：

```text
size_MiB = MAG[9:4] << SCALE[3:0]
```

| 值 | 解码 | 含义 |
|---|---|---|
| `0x00000208` | 32 << 8 | 8192 MiB（出厂，8 GB 卡） |
| `0x00000288` | 40 << 8 | 10240 MiB（出厂，10 GB 卡） |
| `0x0000020B` | 32 << 11 | 65536 MiB（8 GB 卡解锁） |
| `0x0000028A` | 40 << 10 | 40960 MiB（10 GB 卡解锁） |
| `0x0000028B` | 40 << 11 | 81920 MiB（80 GB 尝试） |

MAG 按 SKU 恒定、等于活-FBPA 数的两倍。SCALE 是解锁改变的东西。

> [!WARNING]
> **`0x40A` 和 `0x50A` 是被反驳的，不是被观察到的**
>
> 两者都作为候选编码流传。`(0x40A >> 4) & 0x3F = 0` 和 `(0x50A >> 4) & 0x3F = 0x10`，所以两者在 6 位 MAG 字段下都无法解码，而一次 2026-07-11 在 10 GB 卡上对 `0x40A` 的尝试没移动任何一个寄存器。`LOWER_MAG` 字段的精确宽度（[9:4] 的 6 位对比 [10:4] 的 7 位）从未从 `dev_fb.h` 读出，仍是这里最后一个开放细节。

**为什么 LMR 是硬前提而非优化。** 在硬件上的一次受控三方对比：不写显存给 CPU-RM 在 `kbusVerifyBar2` 处失败 `0x24`；带出厂 10 GB LMR 的 40 GB CFG1 跳线仍给 `0x24`；跳线加匹配的 LMR 达到 `0x25`（StateLoad）。没有 LMR 就没有配置能达到 StateLoad。而按上面注意到的 GSP-RM 行为，一对不连贯的 CFG1/LMR 会在 `kgspBootstrap` 期间被回退。

**为什么一次广播写就够了。** `0x009A0000`-`0x009A3FFF` 是广播 FBPA 孔径；24 个每实例镜像坐在 `0x00900204 + n*0x4000`。出货驱动**不**写任何每-FBPA 寄存器却产出一张工作卡，因为 devinit 随后运行并传播该值。在一个没有 devinit 的无驱动运行时上下文里，单靠广播不移动 CSTATUS、所有每-FBPA 实例都必须手动写。传播是否是 PRI 特权环硬件机制从未被直接插桩。

---

## 第 7 步：出厂签名被重建

`kgspSec2PostblTimingRebuildStockSignature()` 释放并销毁 `0xf800` 载荷 memdesc、用 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 分配一个 `NV_ALIGN_UP(stockSignatureSize, 256)` 的新描述符、把 `pStockSignatureData` 复制回去，并把 `pWprMeta->sysmemAddrOfSignature` 和 `pWprMeta->sizeOfSignature` 重新指向新描述符。若失败，`_kgspBootGspRm` 返回那个状态、引导中止。

**为什么。** 下一次 Booter Load 是真实的那次：它必须正确划分 WPR2、通过它自己的签名验证、并启动 GSP-RM。如果过大的载荷缓冲区还挂着，那次运行会再次溢出 DMEM、GSP 永远不会启动。恢复真正的 4096 字节签名和它的真实长度，把出厂驱动会有的东西原样交给 Booter。

**为什么几何布局改动不使签名失效。** 出厂 AES-MAC 覆盖静态 GSP 固件映像、而非运行时 WPR 元数据、也非硬件几何布局。WPR 元数据由驱动在运行时计算。一条相反方向的说法被明确撤回，而出货的保存 / 注入 / 恢复流程是经验证明。

这一步也解释了一个现实世界的陷阱：如果机器以前跑过固件打补丁的前身，必须先恢复磁盘上的 `gsp_tu10x.bin`。否则驱动在第 2 步把*利用载荷*保存为"出厂"签名，干净的 GSP-RM 引导随后 DMA 错误的 ROP 链。要寻找的成功行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

---

## 第 8 步：WPR 元数据被重算

`kgspPopulateWprMeta_HAL()` 被调用**第二次**，在几何写入和签名重建之后。第一次调用在出厂位置运行、从旧的、小的帧缓冲计算 WPR2 摆放。第二次调用对着现在活着的几何布局重算，记录：

```text
SEC2_DEBUG: WPR meta updated fbSize=0x0000001000000000 wprStart=... wprEnd=... heapOffset=... heapSize=...
```

没有它，驱动的 WPR2 摆放和 booter 的划分会不一致，那正是设计定型前耗尽数天调试的那类失败（`0x55`、`0x65`）。

---

## 第 9 步：GSP 正常引导

真实的 Booter Load 现在未修改地运行。补丁 0002 添加确认回读：

```text
SEC2_DEBUG: normal BooterLoad status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=0xffffffff SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

第二行只在状态是 `NV_OK` 时打印，是解锁挺过真实 GSP 引导的决定性证明。它也是分诊报告时该要的那一行。补丁 0002 还额外把 `kgspBootstrap_TU102` 里的四个致命断言转成记录的日志状态检查，所以瞬时失败产生诊断而非死掉的适配器。

---

## 第 10 步：GSP 静态信息被打补丁，使新容量被宣告

打开几何寄存器改变硬件解码的东西。它不改变 GSP-RM 向驱动*报告*的东西。因此补丁 0001 在 `kgspInitRm` 收到它之后重写静态配置信息，门控在同样的两个设备 ID 上：

- `pGSCI->fb_length` 被设成 `targetFbBytes`：`0x20C2` 是 `0x0000001000000000`（64 GiB）、`0x2082` 是 `0x0000000A00000000`（40 GiB）。
- 如果最后 FB 区域的 `limit` 低于 `targetFbBytes - 1`，该区域被加宽：`limit = targetFbBytes - 1`、`reserved = limit - base + 1`、`supportCompressed = NV_TRUE`、`supportISO = NV_TRUE`、`performance = 20`。

记录为 `SEC2_DEBUG: static-info BEFORE` / `AFTER`。没有这个，驱动根本不会报告加宽的大小。

---

## 第 11 步：让额外容量真正可分配

四个补丁关闭 "区域存在" 与 "CUDA 能用它" 之间的差距。

**补丁 0003，晚期 PMA 扩展。** `memmgrSec2DebugLateExtendHighPmaRegion()` 从一个 `osinit.c` 里的钩子在堆创建后运行。它挑出 `bRsvdRegion && !bInternalHeap && limit >= 8 GiB` 的最高 FB 区域，用 `pmaRegisterRegion` 注册 `[max(base, 8 GiB), limit]`，然后要么把候选从 8 GiB 向上拆成一个新的公共 `FB_REGION_DESCRIPTOR`、要么就地取消保留，随后 `memmgrRegenerateFbRegionPriority`。若需要拆分且 `numFBRegions >= MAX_FB_REGIONS` 则返回 `NV_ERR_INSUFFICIENT_RESOURCES`。记录为 `SEC2_DEBUG: late PMA extension status=0x0`。

注意 `stockFbBytes = 0x200000000ULL`（8 GiB）被硬编码为**两个档位**的拆分点，包括真实出厂大小是 `0x280000000` 的 10 GB 卡。同一个常量在补丁 0001 里被声明且从未使用。

**补丁 0004，PRAMIN 钳制。** `kern_bus_gm107.c` 里一个十行 hunk。在出厂 `offsetBar0 = (Ram.fbAddrSpaceSizeMb << 20) - DRF_SIZE(NV_PRAMIN);` 之后它加：若设备 ID 匹配且 `Ram.fbAddrSpaceSizeMb > 0x2000`，按 `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)` 重算。**为什么：** PRAMIN 窗口偏移量来自帧缓冲大小。从 65536 MB 算出来会落在可达 BAR0 空间之外。把它钳回出厂 8 GiB 地址空间让孔径可用。

**补丁 0005，复制引擎清理变通方案。** 两个 hunk。在 `mem_mgr_tu102.c` 里清理器 PTE-kind 辅助函数对两个设备 ID 提前返回 `NV_MMU_PTE_KIND_GENERIC_MEMORY`，而非 `NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`。在 `mem_scrub.c` 里 `memmgrUseVasForCeMemoryOps()` 守卫获得一个设备 ID 排除，使 `DRF_DEF(0050, _CEUTILS_FLAGS, _VIRTUAL_MODE, _TRUE)` 永不被设置、清理器在物理模式下运行。

**补丁 0006，持久软件状态。** `kernel-open/nvidia/nv.c` 在 PCI 探测时给任一设备 ID 设置 `nv->flags |= NV_FLAG_PERSISTENT_SW_STATE` 的九行。该标志已为 SR-IOV 虚拟功能存在，被改用来让 RM 在最后一个客户端关闭时不拆除软件状态。这实际是内置持久化模式，也是出货设计不需要 systemd 守护进程的原因。（`remove.sh` 仍清理一个当前安装器从不创建的遗留 `cmpunlocker.service` 和一个 `watchdog.py`：被放弃的看门狗设计的遗存。）

---

## 整段时序

来自一份完整 8 GB dmesg 捕获的时间线，驱动加载到可用卡：

| 时间 | 事件 |
|---|---|
| 11.13 s | 出厂签名保存 |
| 11.32 s | PLM[0] WPR_CFG 打开 |
| 11.50 s | PLM[1] FBPA 打开 |
| 11.68 s | PLM[2] WPR 打开 |
| 11.86 s | PLM[3] FEAT 打开 |
| 11.86 s | POST-WRITE（SS0、SS1、CFG1、LMR）和 WPR-meta 更新 |
| 12.07 s | 正常 BooterLoad `status=0x0` |
| 12.07 s | POST-BooterLoad verify：`PLM=0xffffffff SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b` |
| 12.64 s | 堆创建 |
| 12.72 s | 晚期 PMA 扩展 `status=0x0` |

约一秒墙钟时间、四次 Booter 轮次、每次约 180 ms。

解锁做的一切都可以看到：

```bash
sudo dmesg | grep SEC2_DEBUG
```

`SEC2_DEBUG_PRI_*` 寄存器名、`kgspSec2PostblTiming*` 函数名和 `SEC2_DEBUG:` 前缀不出现在出厂 610.43.03 源码里。"PostBL Timing" 是一个发明的功能名，被两次独立审查读作把利用代码故意伪装成制造或调试功能。

---

## 之后什么挺过来

| 事件 | 算力解锁 | 显存几何布局 |
|---|---|---|
| 驱动卸载 / 重载，无复位 | 挺过 | **挺过**（寄存器仍读解锁值） |
| FLR（`echo 1 > /sys/bus/pci/devices/<bdf>/reset`） | 挺过 | **丢失** |
| 断电循环 / 冷启动 | 丢失 | 丢失 |

因为没有任何东西能挺过一次冷启动，整段在每次模块加载时重跑。那不是实现的局限；它是"帧缓冲几何布局没有常开影子"的直接后果。

---

## PCIe Gen2 楔入这段叙述的哪里

> [!WARNING]
> **实验性，仅分支**
>
> `0007-pcie-gen2.patch` 在 `@@ -4942,6 +4942,260 @@` 处、`devId` 打印之后、调用 `kgspSec2PostblTimingRebuildStockSignature()` **之前**，把它整个寄存器块注入 `kernel_gsp.c`。因此它恰好运行在第 5 和第 6 步描述的窗口内，此时 PLM 仍打开、构造的签名载荷仍提供任意 BAR0 写原语。它把一张 23 条目 `xp3gTable` 加两个更多寄存器通过 Booter 推入（25 次 Booter 路由的写），然后做普通主机 BAR0 写，然后把实际链路重训练留给补丁 0008 或用户态。完整细节在[PCIe Gen2](pcie-gen2.md)。

---

## 机制本身的开放问题

> [!NOTE]
> **未解问题**
>
> **链实际执行 `0x0ccb` 吗？** 一条硬约束被记录：没有 ROP 退出路径可以路由经 `regtable_rw_indexed (0x0ccb)`，因为 `0xF800` 载荷线性粉碎它在 DMEM `0x2383` 和 `0x8e08` 索引的描述符表，而一次 2026-07-06 的隔离矩阵显示每条携带写入的重接链都死在那里。然而出货载荷把 `0x00000ccb` 放在 DMEM `0xFFF4` 且有效。下一步是从 `0xFF54` 单步或模拟展开，记录 `0xFFF4` 是否曾弹进 PC、还是只是最外层帧里一个活过的保存槽。

> [!NOTE]
> **未解问题**
>
> **载荷偏移量 `0x1100` 处的 `0x00000007` 除了复位 PLM 还做别的事吗？** 它的主要角色已定：DMEM `0x1900` 是从 IMEM `0x1d3b` 到达的 `f100_field_save_restore` 槽，而 `0x7` 是让经 `secure_teardown` 的退出把 SEC2 复位 PLM 留在 `0xff` 而非通常 `0x8f` 污染的东西。它是否有任何进一步的作用从未被确立。

> [!NOTE]
> **未解问题**
>
> **`0x008200FC` 可写吗，冷卡上读什么？** 一次扫描报告 `0xffffffff`、另一次 `0x000003FF`。九-PLM Gen2 分支尝试返回 `status=0xffff` 且没记录回读。

更多在[未解问题](../frontier/open-questions.md) 和[状态板](../frontier/status-board.md)。途中试过并失败的东西见[死路](../history/dead-ends.md)。
