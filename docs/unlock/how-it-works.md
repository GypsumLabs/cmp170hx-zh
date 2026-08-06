# 解锁如何工作

**本页覆盖内容。** 完整的机制，端到端，按它启动时发生的顺序展开，并说明每一步为何存在。一位称职的工程师应能读完本页、在不打开源码的情况下理解整个设计。逐寄存器细节见[寄存器参考](register-reference.md)；Falcon 内部见[Falcon 与 Booter](falcon-and-booter.md)；载荷构造见[ROP 链](rop-chain.md)。

一句话版本：驱动把 GSP 签名缓冲区放大到 `0x0000f800`，用精心构造的 Falcon ROP 载荷填满它，为每个权限级别掩码各重跑一次 NVIDIA 自签名的 SEC2 Booter Load，以获得一条 Heavy-Secure 权限级别的任意 BAR0 写；随后打开四个 PLM、写四个普通主机寄存器、恢复真实签名，再让 GSP 带着打进其静态信息的新几何布局正常引导。

---

## 为什么必须这样做

三条实测约束逼出了整个设计，每一条都是艰难摸索得来的。

**1. 显存几何布局挺不过复位，但算力解锁可以。** 在一次功能级复位上测得：

| 寄存器 | 挺过 FLR？ |
|---|---|
| `SS0 0x0082381c` | **是** |
| `SS1 0x00823820` | **是** |
| `FEAT_OVR_PLM 0x00823804` | **是**（常电域） |
| `CFG1 0x009a0204` | 否，回退到 `0x02449000` |
| 每-FBPA CFG1、CSTATUS | 否 |
| `LMR 0x00100ce0` | 否，回退到出厂值 |
| FB 几何 PLM | 否，它们重新上锁 |
| AON LMR 影子 `0x001180f0` | 否，回退 |
| SEC2 复位-PLM 污染 | 被 FLR **清除**（`0x8f` 变回 `0xff`） |

在一份 26 寄存器调查里，`FEAT_OVR_PLM` 是唯一标为常开的 PLM。这种不对称正是算力解锁比显存解锁早数周发布的原因，也解释了为何显存解锁不能用旧的算力配方（"发射、FLR、然后从主机写"）。

**2. 帧缓冲几何布局没有常开影子。** 团队花了几小时搜一个，因为 SS0 有一个可找到的 AON 影子、一篇已发表论文也描述了这一概念。在全部六个 FB 几何 PLM 加上 `FUSE_SS_PLM` 都打开的情况下，CFG1、CSTATUS 和 LMR 仍会在 FLR 时回退，且从不在冷启动时持久。一次专门的 FLR 存活映射运行得出结论：没有任何 PLM 能把 FBPA 配置移入常电域。因此几何布局必须在**每次**模块加载时重新应用。

**3. 出厂驱动会重新锁上无驱动工具打开的东西。** 在没有驱动加载的情况下，从主机写 `0x009A0204`、`0x0082381C` 和 `0x00823804` 有效，写入明显落地；但随后加载出厂驱动，会把 `0x00823804` 回读为 `0xffffff8f`，节流分频器也恢复到 5。那个失败正是驱动内方案要解决的。

再加一条排序约束：**GSP-RM 在自己的引导期间把 LMR 当作主寄存器。** 当 CFG1 设成 40 GB 档位、LMR 却留在出厂 `0x288` 时，GSP-RM 会在 `kgspBootstrap` 期间把每-FBPA `CSTATUS_RAMAMOUNT` 从 `0x800` 回退到 `0x200`。所以几何布局必须在*真实* Booter Load 启动 GSP-RM **之前**就位，而不是之后。

维护者得出的结论：在 `_kgspBootGspRm` 内完成这一切——介于驱动握有一条受其控制的签名缓冲区的时刻、与真实 Booter Load 运行的时刻之间。

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

因为冷启动总是用锁定的 CMP 跳线表运行签名的 DevInit，所以首次枚举总是显示出厂容量、出厂 Gen1 链路和节流就位。普通的 `rmmod` / `modprobe` **不会**重跑 DevInit（没有断言 PERST），这正是上一次加载写入的几何布局能挺过驱动重载、却挺不过复位的原因。

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

**为什么移位。** `pGpu->idInfo.PCIDeviceID` 同时打包厂商和设备；设备半是上 16 位。补丁 0001 到 0005 里每个解锁站点都用同样的方式测试。补丁 0006 是唯一例外，它比较原始 `nv->pci_info.device_id`，因为在 PCI 探测时它运行于 `kernel-open/nvidia/nv.c`，那时 `OBJGPU` 尚不存在。

**为什么是运行时门而非构建时门。** 两个几何布局档位都编译进同一个模块：

```c
if (devId == 0x20C2) { cfg1Value = 0x02779000U; lmrValue = 0x0000020BU; }
else                 { cfg1Value = 0x02669000U; lmrValue = 0x0000028AU; }
```

`driver/build.sh` 仍包含一个以前用于重写这些常量的内联 Python 步骤，但在 `master` 上它会检测到两个几何布局都已存在，随即以 `runtime device-id geometry (profile metadata=<label>)` 退出、不编辑任何内容。因此，一个被误检测的 `--profile` 只会写入错误的元数据，却不可能产生错误的几何布局。

任何其它 GA100 SKU，包括 `10de:20b0`，即使装上补丁模块，也走完全出厂的路径。

---

## 第 2 步：签名缓冲区被放大到 `0xf800`

`_kgspCreateSignatureMemdesc` 通常分配 `NV_ALIGN_UP(pGspFw->signatureSize, 256)` 字节，在这个平台上为 4096。当设备门为真时，它改为在 `ADDR_SYSMEM` 分配 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL`（63,488 字节），按 256 字节对齐。在覆盖任何内容之前，真实签名字节会被复制到两个新的 `KernelGsp` 字段里：

```c
NvU8 *pStockSignatureData;
NvU64 stockSignatureSize;
```

记录为 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

**为什么恰好 0xf800。** 这就是整个利用的核心。bug 是 **Booter 的 LS 签名验证里的一次无界 DMA**：IMEM `0x29C4` 处的 `booterVerifyLsSignatures_TU10X` 调用 `booterIssueDma_HAL`，其 DMEM 目的地固定、传输长度直接从 `WprMeta` 的 `sizeOfSignature` 取出、没有任何边界检查。DMA 目的地是 **DMEM `0x0800`**，而 Falcon DMEM 有 64 KB。于是：

```text
0x0800（DMA 基址）+ 0xF800（长度）= 0x10000（DMEM 末尾）
```

载荷 1:1 映射到 DMEM `0x0800`..`0xFFFF`，这正是 Booter 运行时用到的每一块内容，包括它的栈、它保存的返回地址、以及栈金丝雀全局。恰好选 `0xf800`，能让最后一个载荷字节落在最后一个 DMEM 字节上。（算术自洽：载荷在偏移量 `0x5b40` 写入假金丝雀，而 `0x5b40 + 0x800 = 0x6340`，正是独立反汇编所得的金丝雀全局地址。）

**为什么这是 ROP 而非代码执行。** Falcon 把指令存放在 IMEM、数据存放在 DMEM，而溢出只到达 DMEM。它只夺得了对 Falcon 调用栈上返回地址的控制，所以攻击必须由已签名 booter 映像中现成的 gadget 构建。

**缓冲区不含什么。** 固件拼接时代曾有一种早期观点：缓冲区必须以真实、有效的签名开头，因为把整个 `0xF800` 区域零填充会让出厂 booter 以邮箱 `0x31` 退出。已发布的载荷并不保留它：`_kgspSec2PostblTimingFillPayload()` 从偏移量 0 起给每个 dword 写入 `0x000004a7`，从不把签名字节复制回来。保存的出厂字节只活在 `pStockSignatureData` 里，直到第 7 步才放回。邮箱 `0x31` 也是成功载荷回合报告的值，所以单凭它不能作为签名有效性的判决。

`_kgspCreateSignatureMemdesc` 还会对 `/lib/firmware/nvidia/ga100/gsp/dmem.bin` 调用 `os_open_and_read_file()`，失败时记录 `SEC2_DEBUG: <path> not found (0x59), using built-in payload`。状态 `0x59` 属良性且符合预期。

---

## 第 3 步：写入载荷

`_kgspSec2PostblTimingFillPayload(buffer, writeAddr, writeValue)` 先把缓冲区的每个 dword 填上 `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7`，再覆盖下列槽位。DMEM 列即载荷偏移量加 `0x800`：

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

**为什么是假金丝雀。** booter 每次启动都会生成一个新鲜的随机栈金丝雀，并把它保存在 DMEM `0x6340` 的全局里。每个受保护函数把它复制到栈帧边界、在退出时重新比较；一旦不匹配就调用 `panic()`。由于该值每次启动都会重新生成，无法离线猜测。载荷根本不需要猜它：它用 `0xc0deca7e` 覆写*全局*，再把同一常量写进每个重建的金丝雀槽，于是每次退出比较都通过、展开静默完成。

**为什么是 `0x000010aa`。** 那是 `reg_write_indirect`，booter 自己的任意 BAR0 写例程。它与 NVIDIA 的 `_acrlibBar0RegWrite_TU10X` 逐字节相同，驱动 Falcon CSB 空间里一个间接、带互斥门控的邮箱：

```text
I[0x1c100] = 目标 PRI 地址
I[0x1c200] = 数据
I[0x1c000] = 0x800000f2   （写；0x800000f1 是读）
```

booter 自己也用这条路径做事，这正是该原语被识别出来的方式。那一个 gadget 就是整个提权所在：它在 LEVEL2 内、在一个真实的、签名的、已通过验证的 HS 映像中执行。

**为什么每次发射只写一个寄存器。** 链在返回途中必须重建 booter 的栈帧，而每次写入要花一个 `0x18` 字节的帧。独立实现把硬上限定在每次发射两到六次写之间，无驱动引擎也拒绝构建一到两次写以外的载荷。已发布的驱动每次发射只做**一次**写并简单重发，这更简单、也没有预算风险。

---

## 第 4 步：执行 Booter Load 以获得写原语

每一轮驱动调用：

```c
kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
    memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
```

`kgspExecuteBooterLoad_TU102` 在每次运行**之前**执行 `kflcnReset(SEC2)`，因此 SEC2 在轮次之间不累积状态。Booter 加载自身、通过自己映像（未触碰且真实）的 RSA-3072 引导 ROM 检查、把自己解密进 HS 模式、开始验证 LS 签名、把 `0xf800` 字节 DMA 进 DMEM，随后沿注入的返回地址展开，而不是自己的。

> [!WARNING]
> **报告的状态总是失败，而这是预期的**
>
> 每个载荷轮次都会记录 `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` 和 `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`，但寄存器写入仍然落地。seccode 在每次运行后在邮箱 0 里留下一个错误码，`mailbox0 != 0` 又让 HAL 返回 `NV_ERR_GENERIC`（`0xffff`）。**寄存器回读是唯一有效的成功标准**，而这恰好就是已发布的循环采用的标准。不要看到 `status=0xffff` 就当问题。

一次 Booter 轮次大约花 **180 ms**。

---

## 第 5 步：按顺序打开四个 PLM

权限级别掩码是一种按寄存器块划分的门：它决定哪些权限级别可以读或写它所覆盖的寄存器。在 PL0（来自内核驱动的一次普通主机 BAR0 写）时，目标寄存器根本无法写入，而关键在于，**失败是静默的**。一条早期流水线在没有任何地方报告错误的情况下，记录了三次 `Write failed - wrote 0x2779000, read 0x2449000`。

已发布的 `plmTable[]` 恰好四项，按此顺序打开：

| 索引 | 名称 | 地址 | 写入的值 | 为什么需要 |
|---|---|---|---|---|
| 0 | WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | 门控 booter 验证、驱动操纵的 WPR 配置块 |
| 1 | FBPA | `0x009a0148` | `0xffffffff` | 门控 FBPA 孔径，包括 `CFG1 0x009a0204`。也是内置回退载荷目标 |
| 2 | WPR | `0x001fa7c4` | `0xffffffff` | 门控 WPR 区域寄存器 |
| 3 | FEAT | `0x00823804` | `0xffffffff` | `FEAT_OVR_PLM`。门控特性覆盖块，即 SS0 和 SS1 |

> [!WARNING]
> **WPR_CFG 打开到 `0xfffff0ff`，不是 `0xffffffff`**
>
> 分发 README 和 `docs/ARCHITECTURE.md` 都说每个 PLM 都应读 `0xffffffff`。代码却对条目 0 写入并验证 `0xfffff0ff`。请把 `0xfffff0ff` 当作规范值：它是已发布的循环既写入也核对的值。

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

**为什么每次尝试前必须重新装填 WPR2。** WPR2 由 ADDR_LO `0x001fa824` 和 ADDR_HI `0x001fa828` 控制。当 HI 为零时 `kgspIsWpr2Up()` 返回 false。每次 Booter Load 轮次都会划分 WPR2 并让它保持 up；随后第二次 Booter Load 就会以 "WPR2 already up" 中止。在每次尝试前保存循环前的值并重写它们，能把寄存器放回驱动和 booter 都期望的状态。同一个问题也正是补丁 0001 把 `_kgspBootGspRm` 里致命路径降级的原因：

```c
/* 出厂 */
NV_PRINTF(LEVEL_ERROR, "unexpected WPR2 already up, cannot proceed with booting GSP\n");
return NV_ERR_INVALID_STATE;

/* 打补丁 */
NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n");
```

然后执行直接落入 `kgspPopulateWprMeta_HAL`。

**为什么 `FEAT_OVR_PLM` 能被打开。** 门链是这样的：`FUSE_QUADRO_WR_SEC`（`0x0082038c`）= 1 允许打开 `0x00823804`；打开 `0x00823804` 才允许 PL0 主机写 SS0/SS1；特性覆盖寄存器级别高于熔丝。而整条链之所以存在，只是因为 `0x008203f0` 处的主灭杀熔丝 `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` 在 170HX 上读 `0x00000000`。若它被烧断，任何权限级别都不存在软件路径。PLM 本身也不是 PL0 可写的：它必须从一个 HS 模式的 Falcon 打开，"if this was not so, any Nvidia card could be unlocked without any exploit"（若非如此，任何 NVIDIA 卡都能不带任何利用而被解锁）。

已发布的树对 `0x008200fc`（`FUSE_SS_PLM`，分支源码里叫 `OPT_PLM`）**什么都不写**。一条更早的合并配方曾要求打开它；但它已被观察到在出厂卡上读 `0xffffffff`，所以打开它并无必要。Gen2 家族分支确实会加上它，作为把表从四项扩到九项的五条额外条目之一。

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

`0x0082381c` 是 `NV_FUSE_FEATURE_OVERRIDE_SM_SPEED_SELECT`，持有 IMLA0-3、FMLA16、FMLA32、FFMA 和 DP 的八个 4 位字段。`0x00823820` 是 `..._SM_SPEED_SELECT_1`，持有 IMLA4 的第九个字段。每个半字节读作 `[enable | 3-bit speed]`：`0x8` 置位第 3 位（覆盖使能），配速度字段 0（全速）。因此 `0x88888888` 意味着全部八个 SS0 单元上 "override enabled, full rate"（覆盖启用、全速），`0x00000008` 则对 IMLA4 单独做同样的事。

**为什么两者都要。** 只写一个不够；这一点在社区频道里被独立强调，也体现在每一对已发布的写入中。

**为什么这有效而熔丝仍烧着。** 节流按算术单元做 OTP 熔断：`FUSE_SS_FFMA`、`FUSE_SS_FMLA16/32` 和 `FUSE_SS_IMLA0-4` 在 170HX 上全部读 `0x5`（除以 32），在每个被探测的 A100、A10、A5000、A6000 和 Drive A100 上读 `0x0`。一次成功解锁后，那些熔丝影子**仍读 `0x5`**。有效速率由一个可写的覆盖值仲裁，它优先于熔丝，而非直接来自熔丝。确认标准是 `0x00823818` 处的 `FEAT_READOUT_1`——全部九个单元的有效速度选择，从 `0x016db6ed` 降到 `0x00000000`。

### CFG1 和 LMR：几何布局

`0x009a0204` 是 FBPA CFG1 广播寄存器。它在位 [23:16] 的档位字节编码每个显存分区的寻址深度：`0x44` 出厂（12 行位、每 FBPA 512 MiB）、`0x66`（14 行位、2048 MiB）、`0x77`（15 行位、4096 MiB）。总容量是寻址深度乘以熔丝决定的活跃-FBPA 数，而 CFG1 不碰后者。两个已发布的值字面上就是真实 A100 部件的出厂 CFG1 字：`0x02779000` 是 A100 PCIe 80 GB 读到的值，`0x02669000` 是 A100 PCIe 40 GB 和 SXM4 40 GB 读到的值。解锁恢复的是真正的 A100 几何布局，而非自创常量。

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

MAG 按 SKU 恒定，等于活跃-FBPA 数的两倍；SCALE 才是解锁改动的部分。

> [!WARNING]
> **`0x40A` 和 `0x50A` 是被反驳的，不是被观察到的**
>
> 两者都曾作为候选编码流传。`(0x40A >> 4) & 0x3F = 0`、`(0x50A >> 4) & 0x3F = 0x10`，所以两者在 6 位 MAG 字段下都无法解码；而且一次 2026-07-11 在 10 GB 卡上对 `0x40A` 的尝试没有移动任何一个寄存器。`LOWER_MAG` 字段的精确宽度（[9:4] 的 6 位对比 [10:4] 的 7 位）从未从 `dev_fb.h` 读出，仍是这里最后一项未解决的细节。

**为什么 LMR 是硬前提而非优化。** 在硬件上做了一次受控三方对比：不写显存让 CPU-RM 在 `kbusVerifyBar2` 处以 `0x24` 失败；带出厂 10 GB LMR 的 40 GB CFG1 跳线仍给出 `0x24`；跳线加上匹配的 LMR 才达到 `0x25`（StateLoad）。没有 LMR，就没有任何配置能达到 StateLoad。而按上文注意到的 GSP-RM 行为，一对不连贯的 CFG1/LMR 会在 `kgspBootstrap` 期间被回退。

**为什么一次广播写就够了。** `0x009A0000`-`0x009A3FFF` 是广播 FBPA 孔径；24 个每实例镜像位于 `0x00900204 + n*0x4000`。已发布的驱动**不**写任何每-FBPA 寄存器却产出一张可用卡，因为 devinit 随后会运行并传播该值。在没有 devinit 的无驱动运行时环境里，单靠广播无法移动 CSTATUS，所有每-FBPA 实例都必须手动写入。该传播是否为 PRI 特权环的硬件机制，从未被直接插桩确认。

---

## 第 7 步：出厂签名被重建

`kgspSec2PostblTimingRebuildStockSignature()` 释放并销毁 `0xf800` 载荷 memdesc，用 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 分配一个 `NV_ALIGN_UP(stockSignatureSize, 256)` 的新描述符，把 `pStockSignatureData` 复制回去，并把 `pWprMeta->sysmemAddrOfSignature` 和 `pWprMeta->sizeOfSignature` 重新指向新描述符。若失败，`_kgspBootGspRm` 返回该状态、引导中止。

**为什么。** 下一次 Booter Load 才是真实的那次：它必须正确划分 WPR2、通过自己的签名验证、并启动 GSP-RM。如果过大的载荷缓冲区仍挂着，那次运行就会再次溢出 DMEM，GSP 永远启动不了。恢复真正的 4096 字节签名和它的真实长度，等于把出厂驱动会提供的东西原样交给 Booter。

**为什么几何布局改动不会使签名失效。** 出厂 AES-MAC 覆盖的是静态 GSP 固件映像，而非运行时 WPR 元数据，也非硬件几何布局；WPR 元数据由驱动在运行时计算。一条相反方向的说法已被明确撤回，而已发布的保存 / 注入 / 恢复流程就是经验的证明。

这一步也解释了一个现实世界的陷阱：如果机器以前运行过固件打补丁的前身，必须先恢复磁盘上的 `gsp_tu10x.bin`。否则驱动会在第 2 步把*利用载荷*保存为"出厂"签名，随后干净的 GSP-RM 引导就会 DMA 到错误的 ROP 链。应当寻找的成功行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

---

## 第 8 步：WPR 元数据被重算

`kgspPopulateWprMeta_HAL()` 被**第二次**调用，在几何写入和签名重建之后。第一次调用在出厂位置运行，从旧的、小的帧缓冲计算 WPR2 摆放；第二次调用则对着现在已生效的几何布局重算，并记录：

```text
SEC2_DEBUG: WPR meta updated fbSize=0x0000001000000000 wprStart=... wprEnd=... heapOffset=... heapSize=...
```

没有它，驱动的 WPR2 摆放与 booter 的划分就会不一致，而这正是设计定型前耗尽数天调试的那类失败（`0x55`、`0x65`）。

---

## 第 9 步：GSP 正常引导

真实的 Booter Load 现在未修改地运行。补丁 0002 添加确认回读：

```text
SEC2_DEBUG: normal BooterLoad status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=0xffffffff SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

第二行只在状态为 `NV_OK` 时打印，是解锁挺过真实 GSP 引导的决定性证明，也是分诊报告时应当索取的那一行。补丁 0002 还把 `kgspBootstrap_TU102` 里的四个致命断言转成带日志的状态检查，因此瞬时失败会产生诊断信息，而不是一块死掉的适配器。

---

## 第 10 步：GSP 静态信息被打补丁，使新容量被宣告

打开几何寄存器会改变硬件解码的结果，但不会改变 GSP-RM 向驱动*报告*的内容。因此补丁 0001 在 `kgspInitRm` 收到静态配置信息后重写它，门控在同样的两个设备 ID 上：

- `pGSCI->fb_length` 被设为 `targetFbBytes`：`0x20C2` 为 `0x0000001000000000`（64 GiB）、`0x2082` 为 `0x0000000A00000000`（40 GiB）。
- 如果最后 FB 区域的 `limit` 低于 `targetFbBytes - 1`，则加宽该区域：`limit = targetFbBytes - 1`、`reserved = limit - base + 1`、`supportCompressed = NV_TRUE`、`supportISO = NV_TRUE`、`performance = 20`。

记录为 `SEC2_DEBUG: static-info BEFORE` / `AFTER`。没有这一步，驱动根本不会报告加宽后的大小。

---

## 第 11 步：让额外容量真正可分配

四个补丁关闭了 "区域存在" 与 "CUDA 能用它" 之间的差距。

**补丁 0003，晚期 PMA 扩展。** `memmgrSec2DebugLateExtendHighPmaRegion()` 从一个 `osinit.c` 里的钩子在堆创建后运行。它挑出满足 `bRsvdRegion && !bInternalHeap && limit >= 8 GiB` 的最高 FB 区域，用 `pmaRegisterRegion` 注册 `[max(base, 8 GiB), limit]`，然后把该候选从 8 GiB 向上拆成一个新的公共 `FB_REGION_DESCRIPTOR`，或就地取消其保留，随后调用 `memmgrRegenerateFbRegionPriority`。若需要拆分且 `numFBRegions >= MAX_FB_REGIONS`，则返回 `NV_ERR_INSUFFICIENT_RESOURCES`。记录为 `SEC2_DEBUG: late PMA extension status=0x0`。

注意 `stockFbBytes = 0x200000000ULL`（8 GiB）被硬编码为**两个档位**的拆分点，包括真实出厂大小是 `0x280000000` 的 10 GB 卡。同一个常量在补丁 0001 里被声明却从未使用。

**补丁 0004，PRAMIN 钳制。** `kern_bus_gm107.c` 里一个十行的 hunk。在出厂 `offsetBar0 = (Ram.fbAddrSpaceSizeMb << 20) - DRF_SIZE(NV_PRAMIN);` 之后，它加了一条逻辑：若设备 ID 匹配且 `Ram.fbAddrSpaceSizeMb > 0x2000`，则按 `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)` 重算。**为什么：** PRAMIN 窗口偏移量源自帧缓冲大小，从 65536 MB 算出来会落在可达的 BAR0 空间之外；把它钳回出厂 8 GiB 地址空间，才能让孔径保持可用。

**补丁 0005，复制引擎清理变通方案。** 两个 hunk。在 `mem_mgr_tu102.c` 里，清理器的 PTE-kind 辅助函数对两个设备 ID 提前返回 `NV_MMU_PTE_KIND_GENERIC_MEMORY`，而非 `NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`。在 `mem_scrub.c` 里，`memmgrUseVasForCeMemoryOps()` 守卫获得一个设备 ID 排除，使 `DRF_DEF(0050, _CEUTILS_FLAGS, _VIRTUAL_MODE, _TRUE)` 永不被设置、清理器在物理模式下运行。

**补丁 0006，持久软件状态。** `kernel-open/nvidia/nv.c` 在 PCI 探测时为任一设备 ID 设置 `nv->flags |= NV_FLAG_PERSISTENT_SW_STATE`，共九行。该标志原本为 SR-IOV 虚拟功能存在，现被改用来让 RM 在最后一个客户端关闭时不拆除软件状态。这实际上是内置的持久化模式，也是已发布的设计无需 systemd 守护进程的原因。（`remove.sh` 仍会清理一个当前安装器从不创建的遗留 `cmpunlocker.service` 和一个 `watchdog.py`：那是被放弃的看门狗设计的遗存。）

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

`SEC2_DEBUG_PRI_*` 寄存器名、`kgspSec2PostblTiming*` 函数名和 `SEC2_DEBUG:` 前缀不出现在出厂 610.43.03 源码里。"PostBL Timing" 是一个自创的功能名，被两次独立审查解读为：把利用代码刻意伪装成制造或调试功能。

---

## 之后什么挺过来

| 事件 | 算力解锁 | 显存几何布局 |
|---|---|---|
| 驱动卸载 / 重载，无复位 | 挺过 | **挺过**（寄存器仍读解锁值） |
| FLR（`echo 1 > /sys/bus/pci/devices/<bdf>/reset`） | 挺过 | **丢失** |
| 断电循环 / 冷启动 | 丢失 | 丢失 |

因为没有任何东西能挺过一次冷启动，所以整段序列会在每次模块加载时重跑。那不是实现的局限，而是"帧缓冲几何布局没有常开影子"的直接后果。

---

## PCIe Gen2 楔入这段叙述的哪里

> [!WARNING]
> **实验性，仅分支**
>
> `0007-pcie-gen2.patch` 在 `@@ -4942,6 +4942,260 @@` 处、`devId` 打印之后、调用 `kgspSec2PostblTimingRebuildStockSignature()` **之前**，把它整个寄存器块注入 `kernel_gsp.c`。因此它恰好运行在第 5 和第 6 步描述的窗口内——此时 PLM 仍打开、构造的签名载荷仍提供任意 BAR0 写原语。它把一张 23 条目 `xp3gTable` 再加两个寄存器通过 Booter 推入（25 次 Booter 路由的写），然后做普通主机 BAR0 写，再把实际链路重训练留给补丁 0008 或用户态。完整细节见[PCIe Gen2](pcie-gen2.md)。

---

## 机制本身的开放问题

> [!NOTE]
> **未解问题**
>
> **链实际执行 `0x0ccb` 吗？** 一条硬约束曾被记录：任何 ROP 退出路径都不得路由经过 `regtable_rw_indexed (0x0ccb)`，因为 `0xF800` 载荷会线性粉碎它在 DMEM `0x2383` 和 `0x8e08` 索引的描述符表；而一次 2026-07-06 的隔离矩阵显示，每条携带写入的重接链都死在那里。然而已发布的载荷确实把 `0x00000ccb` 放在 DMEM `0xFFF4` 且有效。下一步是从 `0xFF54` 单步或模拟展开，记录 `0xFFF4` 究竟曾否弹进 PC，还是只是最外层帧里一个存活下来的保存槽。

> [!NOTE]
> **未解问题**
>
> **载荷偏移量 `0x1100` 处的 `0x00000007` 除了复位 PLM 还做别的事吗？** 它的主要作用已定：DMEM `0x1900` 是从 IMEM `0x1d3b` 到达的 `f100_field_save_restore` 槽，而 `0x7` 让经 `secure_teardown` 的退出把 SEC2 复位 PLM 留在 `0xff`、而非通常的 `0x8f` 污染。它是否还有任何进一步的作用，从未被确认。

> [!NOTE]
> **未解问题**
>
> **`0x008200FC` 可写吗，冷卡上读什么？** 一次扫描报告 `0xffffffff`、另一次 `0x000003FF`。九-PLM Gen2 分支尝试返回 `status=0xffff` 且没记录回读。

更多内容见[未解问题](../frontier/open-questions.md) 和[状态板](../frontier/status-board.md)。路上试过并失败的做法见[死路](../history/dead-ends.md)。
