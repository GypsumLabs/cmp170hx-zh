# 算力节流以及如何移除它

**本页覆盖内容。** NVIDIA 用来削弱 CMP 170HX 算术吞吐的机制、击败它的精确寄存器和值、熔丝本身为何从不被碰、实测改进是什么、名字最有希望的寄存器（`SM_ISSUE_RATE_MODIFIER`）为何是一条死路，以及算力解锁为何挺过功能级复位而[显存解锁](memory-geometry.md)不能。

**短版。** 限制是一个**指令发射速率分频器**，实现为 `OPT_SM_SPEED_SELECT` 块里的九个一次性可编程熔丝，在这个 SKU 上全部设到它们的最大分频（除以 32）、在每个 A100 上设到零。熔丝不能改，解锁也不尝试改。它转而打开一个权限级别掩码——`0x00823804` 处的 `FEAT_OVR_PLM`，从仅 L3（`0xffffff8f`）到完全打开（`0xffffffff`）——用 SEC2 Booter 作为特权写原语，然后执行**两次普通主机寄存器写**：

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0：FEATURE_OVERRIDE_SM_SPEED_SELECT   */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1：FEATURE_OVERRIDE_SM_SPEED_SELECT_1 */
```

那两个 dword 就是整个算力解锁。FP32 从 0.395 TFLOPS 升到约 12.7 到 12.9 TFLOPS（约 **32x**），FP64 和每个张量路径都随之回来；而覆盖挺过 FLR，是因为 `0x00823804` 位于常电域里。这里没有任何东西被写进卡的 BIOS；打过补丁的驱动会在每次 GSP 引导时重新应用该序列。

---

## 第 1 层：熔丝

节流是按算术单元进行的。九个熔丝、一个共享权限级别掩码。熔丝值 `0` 是全速；`5` 是最大分频、除以 32。`FUSE_SS_DP` 是一个一位熔丝：`0` 是全速、`1` 是降低，所以 `1` 是*它*的最大值。

| 熔丝 | 地址 | 管辖 | 170HX | A100 / A10 / A5000 / A6000 / DRIVE A100 | RTX 3080-3090 Ti |
|---|---|---|---|---|---|
| `FUSE_SS_DP` | `0x00820224` | FP64（1 位） | `0x00000001` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FFMA` | `0x0082059c` | FP32 融合乘加 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FMLA16` | `0x008207d4` | FP16 MLA | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FMLA32` | `0x008207d8` | FP32 MLA | `0x00000005` | `0x00000000` | `0x00000001` |
| `FUSE_SS_IMLA0` | `0x008207dc` | 整型 MLA 0，也作 DP4A | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA1` | `0x008207e0` | 整型 MLA 1 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA2` | `0x008207e4` | 整型 MLA 2 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA3` | `0x008207e8` | 整型 MLA 3 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA4` | `0x008207ec` | 整型 MLA 4 | `0x00000005` | `0x00000000` | `0x00000001` |
| `FUSE_SS_PLM` | `0x008200fc` | 块上的共享 PLM | `0xffffffff` | `0xffffffff` | `0xffffffff` |

这些读数来自 2026-05-07 到 2026-07-27 之间、跨两个 SKU 的至少五次独立 170HX 探测，另加一个 11 卡租用对比组和两块物理 DRIVE A100（PG199）板。这些值是一个**产品线常量**：在每张 170HX 上都相同，这正是固定解锁配方安全的原因。把它与下面的覆盖寄存器对比——后者是按晶片的。

> [!NOTE]
> **一个被频繁复述的不精确**
>
> 说 "all 9 speed select fuses at `0x5`" 的摘要很宽松。八个熔丝读 `0x5`；第九个 `FUSE_SS_DP` 读 `0x1`——那是它自己的最大值，因为它是一个一位字段。

### 产品档位签名

`FUSE_SS_FMLA32` 和 `FUSE_SS_IMLA4` 把被探测的 Ampere 组分成恰好三个档位：

| 值 | 部件 |
|---|---|
| `0x00000000` | A100 SXM4 40G、A100 PCIe 40G、A100 PCIe 80G、A10、A5000、A6000、DRIVE A100 |
| `0x00000001` | RTX 3080、RTX 3080 Ti、RTX 3090、RTX 3090 Ti |
| `0x00000005` | **CMP 170HX，两块单元** |

`0x1` 档位是众所周知的、对带 FP32 累加的 FP16 张量吞吐的消费级减半。CMP 节流并非特殊机制：它是同一个机制被转到它的最大分频。

### 为什么你不能只改熔丝

四条独立路线被尝试并关闭：

- **写 `OPT_SM_SPEED_SELECT` 寄存器。** 它们是 OTP 熔丝*影子*，无论权限如何都只读。`FUSE_SS_PLM`（`0x008200fc`）在每张卡上宽开，看起来像疏忽，却一无所获。
- **FUSECTRL 软件熔丝覆盖路径。** 在这个部件上关闭：`NV_FUSE_FUSECTRL 0x00820000 = 0xe0040000`、`FUSE_EN_SW_OVERRIDE 0x00820040 = 0x00000000`、`ENABLE_FUSE_PROGRAM_STATUS 0x00820078 = 0x00000001`、`DISABLE_FUSE_PROGRAM_STATUS 0x0082007c = 0x00000000`、`BYPASS_FUSES_STATUS 0x00820080 = 0x00000000`、`DISABLE_SW_OVERRIDE_STATUS 0x00820084 = 0x00000001`。一块 GA10x 对照卡共享 FUSECTRL 值、却有 `EN_SW_OVERRIDE = 0x00000001`，这证明寄存器工作、在这里被刻意关闭。
- **FECS 镜像。** `FECS_FEAT_OVERRIDE 0x00409664` 和 `FECS_FEAT_READOUT_1 0x00409668` 在全部 15 张被探测的 Ampere 卡（包括未节流的）上都返回 PRI 权限违规哨兵 `0xbadf5040`，所以该值是一个读阻断指示、而非数据。
- **物理重新熔断硅片。** 2024 年被命名为一条攻击路径，从未尝试，已被覆盖寄存器取代。

---

## 第 2 层：FEATURE_OVERRIDE 块

`0x00823800` 块是一组**级别高于熔丝**的寄存器。在锁定卡上对 `0x00823800` 到 `0x00823ffc` 的一次完整范围扫描只返回十三个活 dword；每个其它偏移量返回 `0xbadf5040`。

| 寄存器 | 地址 | 出厂 170HX | 角色 |
|---|---|---|---|
| `FEATURE_OVERRIDE_ECC PLM` | `0x00823800` | `0xffffff8f` | ECC 覆盖组上的 PLM（与 `0x00823804` 不同的寄存器） |
| **`FEATURE_OVERRIDE PLM`（FEAT_OVR_PLM）** | **`0x00823804`** | **`0xffffff8f`** | **那扇门。出厂仅 L3。常电岛** |
| `FEATURE_OVERRIDE_QUADRO` | `0x00823808` | 两块物理 170HX 单元上 `0x00000181` / `0x00000182`；其它转储读 `0x00100183`（出厂 PLM 范围扫描）和 `0x00000081`（解锁后探测）；A100 80 GB 读 `0x01000282` | 按晶片、13 个分级差异之一、且未解释。只读。为什么该值在不同转储之间不同是一个开放问题；见[寄存器参考](register-reference.md) |
| `FEATURE_OVERRIDE_ECC` | `0x0082380c` | `0x00888888` | SM_LRF / L1 / LTC / DRAM / CBU ECC 控制 |
| `FEATURE_OVERRIDE_ECC_1` | `0x00823810` | `0x002aaaaa` | icache / FECS / GPCCS / PMU / HUBMMU ECC |
| `FEATURE_READOUT`（READOUT_0） | `0x00823814` | `0x00000233` | Quadro 位 [5:0] 加 ECC 状态 [31:12]，只读 |
| **`FEATURE_READOUT_1`** | **`0x00823818`** | **`0x016db6ed`** | **只读有效 SM 速度选择，全部九个单元** |
| **`FEATURE_OVERRIDE_SM_SPEED_SELECT`（SS0）** | **`0x0082381c`** | 按晶片 | **IMLA0-3、FMLA16、FMLA32、FFMA、DP：八个 4 位字段** |
| **`FEATURE_OVERRIDE_SM_SPEED_SELECT_1`（SS1）** | **`0x00823820`** | 按晶片 | **第九个字段，IMLA4** |
| `FEATURE_OVERRIDE_ROW_REMAPPER` | `0x00823824` | `0x00000000` / `0x00000001` | 在 `0x00823b00` 有自己的 PLM |
| `FEATURE_READOUT_2` | `0x00823828` | `0x00000000` | |
| `FEATURE_OVERRIDE_ECC_2` | `0x0082382c` | `0x0000000a` | LTC_CBC 和 SM_URF ECC |
| `FEAT2 PLM`（ROW_REMAPPER PLM） | `0x00823b00` | `0xffffff8f` | 只被 Gen2 家族分支打开 |

> [!CAUTION]
> **SS0 和 SS1 是按晶片的分级值。绝不把一张卡的读数当规范。**
>
> 组里实测的出厂 SS0：170HX `0x51261070`、另一张 170HX `0x10206152`、第三张 `0x71066125`、第四张 `0x12103060`；一块 `0x20bb` GA100 参考板（未节流、`FEAT_READOUT_1` = 0）`0x53540175`；A100 SXM4 40G `0x10413004`；A100 PCIe 40G `0x14604062`；A100 PCIe 80G `0x72020072`；A10 `0x11303071`；A5000 `0x63573073`；A6000 `0x14170072`；RTX 3080 `0x03676064`；RTX 3080 Ti `0x10551033`；RTX 3090 `0x06740057`；RTX 3090 Ti `0x30403100`；DRIVE A100 `0x25045144`。两个*同一个* A100 80 GB 设备 ID 的归档转储彼此不一致（`0x00112011`/`0x00000002` 对 `0x00343015`/`0x00000004`），所以这些是运行时状态，不是稳定的熔丝状态。用 `FEATURE_READOUT_1`（`0x00823818`），不要用 SS0/SS1，作参考目标。

`FEATURE_READOUT_1` 是唯一稳定且有意义的值：它在两块物理 170HX 卡上都读 `0x016db6ed`（尽管它们的 SS0/SS1 不同），在每张 A100 和 DRIVE A100 上读 `0x00000000`、在全部四张 RTX 30 系列部件上读 `0x00400080`。**`0x00823818 == 0` 是可用的最干净 "这张卡解锁了吗" 测试。**

### 半字节编码

每个 SS0 半字节最好读作 `[enable | 3-bit speed]`。`0x8` 设置位 3（覆盖使能）、配位 [2:0] = 0（速度 0，全速）。所以 `0x88888888` 意思是全部八个 SS0 单元上 "override enabled, full rate"（覆盖启用、全速），而 `0x00000008` 对 SS1 里单独的 IMLA4 做同样的事。

> [!WARNING]
> **编码是推断的，不是文档化的**
>
> 语料库里不存在这个字段布局的 NVIDIA 文档。该读数由三个观察支持：档案里任何地方没有一份出厂转储有任何半字节大于或等于 8——即出厂硅片上覆盖使能位清除、字段内容是 don't-care；`0x00823818` 处的有效读出在写入后归零；以及性能结果匹配。它从未被逐字段确认。在解锁卡上对 SS0 做一次单半字节扫描、看 `0x00823818` 的哪些位移动，会同时定论这个和读出解码。

### 门链

```text
FUSE_QUADRO_WR_SEC (0x0082038c) = 1
        允许
FEAT_OVR_PLM (0x00823804) 从 0xffffff8f 打开到 0xffffffff
        允许
PL0 主机写 SS0 (0x0082381c) 和 SS1 (0x00823820)
        它们
级别高于 OPT_SM_SPEED_SELECT 熔丝
```

两个门控熔丝在同一个卡上测得：`OPT_SECURE_FEATURE_OVERRIDE_QUADRO_WR_SECURE`（`0x0082038c`）= `0x00000001` 和 `OPT_SECURE_GSP`（`0x0082074c`）= `0x00000001`。

而在这一切之上：

> [!NOTE]
> **让这一切成为可能的那颗熔丝**
>
> `0x008203f0` 处的 `OPT_FEATURE_FUSES_OVERRIDE_DISABLE`（`FUSE_FEAT_OVR_DIS`）在 CMP 170HX 上读 `0x00000000`。探测把它标注为 "MASTER KILL: if YES all overrides permanently locked"（主灭杀：若是，所有覆盖被永久锁定）。如果 NVIDIA 烧断了那一颗熔丝，本页每一条路线都会永久关闭。它在每张被探测的卡上都读零，包括 GA10x 对照。

注意 `FEAT_OVR_PLM 0x00823804` 在**全部十五张**被探测的 Ampere 部件上读 `0xffffff8f`（仅 L3），包括每一张 A100。170HX 在这里并不特殊。解锁的全部难度在于到达 L3 去改变它——这正是[SEC2 Booter 路径](falcon-and-booter.md)所做的。只有 SS0 和 SS1 在 PL0 可主机写；PLM 本身必须被一个高安全模式的 Falcon 写。正如一份分析所说，若非如此，任何 NVIDIA 卡都能不带利用被解锁。

---

## 出货代码实际做什么

来自分支 `master` 的 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`，在 GSP 引导路径内，由 `_kgspSec2PostblTimingEnabled()` 门控在 PCI 设备 ID 上，它接受 `0x20C2`（8 GB）**和** `0x2082`（10 GB）：

```c
static const struct { NvU32 addr; NvU32 value; const char *name; } plmTable[] = {
    { 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
    { 0x009a0148U, 0xffffffffU, "FBPA" },
    { 0x001fa7c4U, 0xffffffffU, "WPR" },
    { 0x00823804U, 0xffffffffU, "FEAT" },
};

NvU32 wpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824U);
NvU32 wpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828U);

for (plmIdx = 0; plmIdx < 4; plmIdx++)
{
    NvBool opened = NV_FALSE;
    for (attempt = 0; attempt < 2 && !opened; attempt++)
    {
        GPU_REG_WR32(pGpu, 0x001fa824U, wpr2Lo);        /* 每次尝试前重新武装 WPR2 */
        GPU_REG_WR32(pGpu, 0x001fa828U, wpr2Hi);

        plmStatus = kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
            plmTable[plmIdx].addr, plmTable[plmIdx].value);
        if (plmStatus != NV_OK)
            continue;

        plmStatus = kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
            memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));

        NvU32 regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
        if (regVal == plmTable[plmIdx].value)
            opened = NV_TRUE;
    }
}
```

然后，PLM 打开后：

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0  */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1  */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* CFG1（显存几何布局） */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* LMR  （显存几何布局） */
```

值得注意的点：

- 载荷携带**一个**（地址、值）对，而 Booter Load 被**每个 PLM 重发一次**、**每个最多 2 次尝试**，WPR2 边界在 `0x001fa824` / `0x001fa828`、每次尝试周围保存并恢复。成功由**回读**判断，而非由 Booter 状态——后者无论成败每次都返回 `0xffff`。
- 四个 PLM 里只有**三个**到 `0xffffffff`。`WPR_CFG 0x001fa7cc` 被写成 `0xfffff0ff`。任何说 "all PLMs must show `0xffffffff`" 的文档都是宽松措辞。
- **SS0 和 SS1 对两个 SKU 都相同。** 只有 `cfg1Value` 和 `lmrValue` 由设备 ID 选择。它们见[显存几何布局](memory-geometry.md)。
- 出货顺序是 SS0、SS1、CFG1、LMR，随后单行回读日志。
- **SS0 和 SS1 都必须被写。** 只写一个不够。
- `common/constants.yaml` 记录 `compute: ss0: "0x88888888"` / `ss1: "0x00000008"`，但 `install.sh` 和 `driver/build.sh` 都不读那个文件。值硬编码在补丁里。把 YAML 当作碰巧与代码一致的文档。
- SS0/SS1 在全部十二个未发布分支里逐字节相同。没有分支试过不同的算力值；所有算力实验都先于这些值被定下。

---

## 验证解锁

第二个出货补丁 `0002-booter-verify.patch` 定义了项目自己认为决定性的规范五寄存器集，并在每次 Booter Load 后记录它们：

| 符号 | 地址 |
|---|---|
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM` | `0x00823804` |
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED` | `0x0082381c` |
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1` | `0x00823820` |
| `SEC2_DEBUG_PRI_FBPA_CFG1` | `0x009a0204` |
| `SEC2_DEBUG_PRI_MMU_LMR` | `0x00100ce0` |

```bash
sudo dmesg | grep SEC2_DEBUG
```

一张成功的 8 GB 卡打印：

```text
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
```

一张 8 GB 卡上解锁后的寄存器状态，相对一张锁定的对比卡：

| 寄存器 | 地址 | 锁定 | 解锁 |
|---|---|---|---|
| `FEAT_OVR_PLM` | `0x00823804` | `0xffffff8f` | `0xffffffff` |
| SS0 | `0x0082381c` | 按晶片，例如 `0x12103060` | `0x88888888` |
| SS1 | `0x00823820` | 按晶片，例如 `0x00000003` | `0x00000008` |
| `FEAT_READOUT_1` | `0x00823818` | `0x016db6ed` | `0x00000000` |
| `FUSE_SS_FFMA` 等 | `0x0082059c` 等 | `0x00000005` | **`0x00000005`，不变** |

最后一行是"这是一个覆盖而非熔丝编辑"的硬确认：一次成功解锁后，熔丝影子仍读 `5`（DP 仍读 `1`），而有效读出是零。

> [!WARNING]
> **`clocks.max.sm` 不是一个好的验证信号**
>
> `install.sh` 打印 `nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader` 作为它的算力验证步骤，而一份解锁后报告从它读到 `1935 MHz`。每一次持续测量都反驳把那个读作工作时钟：VBIOS 表最大图形时钟是 1695 MHz，实际硅片天花板在 +350 偏移下约 1604 到 1614 MHz。持续 SM 时钟是 **1410 MHz**（`-pl 300` 下 1470 MHz）。把 1935 MHz 当作一个报告字段、单一报告、低置信度。一个更好的功能检查是，NVML GPC 时钟 VF 偏移范围回到 `[-1000 .. +1000]` 而非 `[0 .. 0]`；见[调优](../operations/tuning.md)。

---

## 实测改进

锁定的 FP32 融合乘加吞吐测为 **394.77 GFLOPS**，在 float、float2、float4、float8 和 float16 之间*相同*。跨向量宽度的这种完美平坦，是指令发射限制而非带宽或占用限制的签名。算术恰好闭合：4480 通道在 1410 MHz 的理论 FP32 是 12.634 TFLOPS，而 12.634 / 32 = 394.8 GFLOPS。

那个五位数**不是**社区测量。它来自一张出厂、从未解锁的卡的一次公开 2023 clpeak 回顾，也是匹配的无-FMA 对照（float 6285.48 GFLOPS，约快 16 倍）和锁定 FP64 182.72 GFLOPS 的来源。社区记录只携带同一量的四舍五入重述：一次 8 卡基准测试报告里的 0.39 TFLOPS、以及作为 12.28 / 32 而*反向计算*（而非实测）的 0.38 TFLOPS。除非直接引用外部 clpeak 运行，否则请引用为**约 0.39 TFLOPS**。

### 首张完整前后表（2026-07-06，一张卡）

作为渲染图片而非工具输出贴出，伴随着私有验证频道里第一份 "I have compute unlock working"（我的算力解锁可用了）报告。来源附件：`archive/cleanroom/1523499947490541640_PNG_image.png`。

| 数据类型 | 节流 | 解锁 | 比值 |
|---|---|---|---|
| FP64 | 0.20 TF/s | 12.91 TF/s | 63.0x |
| FP32 IEEE | 0.41 TF/s | 12.69 TF/s | 31.0x |
| INT8 | 1.63 TOP/s | 50.50 TOP/s | 30.9x |
| BF16 | 6.40 TF/s | 184.86 TF/s | 28.9x |
| FP16 | 6.52 TF/s | 153.92 TF/s | 23.6x |
| INT4 | 11.55 TOP/s | 259.34 TOP/s | 22.5x |
| INT1 | 46.16 TOP/s | 1038.89 TOP/s | 22.5x |
| TF32 | 90.72 TF/s | 90.09 TF/s | 1.0x，标为 "untouched"（未触碰）（有争议） |

> [!NOTE]
> **为什么这个日期在时间线的解锁里程碑前六天**
>
> [timeline.md](../history/timeline.md) 把 "compute unlock works on hardware"（算力解锁在硬件上可用）定到 **2026-07-12**。那是第一次*社区复现的*解锁。这张表先于它，因为私有验证频道在 **2026-07-06 01:24** 就有算力可用了，就在同一消息里报告了 INT4 和 INT8 用 CUTLASS TN 形状调优打到 300 和 600。两个日期不冲突；它们标记私有首亮和公开复现。
>
> 把数字本身当作一张图片该有的谨慎对待：没点名工具、没陈述时钟或 flop 计数约定、八行里没有一行被逐位复现过。节流列在种类上被外部 clpeak 回顾佐证（锁定的 FP64 182.72 GFLOPS 对这里的 0.20 TF/s；锁定的 FP32 394.77 GFLOPS 对 0.41 TF/s），而解锁的 FP16 和 BF16 行坐在更晚的 8 卡分布里。TF32 行被彻底争议。

### 独立确认

| 测量 | 值 | 条件 |
|---|---|---|
| SGEMM FP32 | 12.28 TFLOPS | 2026-07-12，验证频道外首次报告完整 SM 解锁、cc 8.0；约一分钟后被一次独立的 gpu-burn 运行以 12229 Gflop/s、0 错误、62 C 佐证 |
| DGEMM FP64 | 11.48 TFLOPS | 同一次运行（张量 DMMA 路径，见下） |
| FP32，OpenCL-Benchmark | 12.890 TFLOPs/s | 64 GB 解锁卡、驱动 610.43.03 |
| FP64，OpenCL-Benchmark | 6.421 TFLOPs/s（FP32 的 1/2） | 同一次运行 |
| FP16，OpenCL-Benchmark | 48.740 TFLOPs/s（FP32 的 4x） | 同一次运行 |
| INT8，OpenCL-Benchmark | 49.362 TIOPs/s | 同一次运行 |
| FP32 非张量 | 12.6 到 12.76 TFLOPS | 2026-07-27，一张调优卡加一个 8 卡租用 |
| FP16 张量 | 158.7 到 162.7 TFLOPS | 同一次行动 |
| BF16 张量 | 171.4 到 192.7 TFLOPS | 同一次行动 |
| TF32 张量 | 79.0 到 91.9 TFLOPS | 同一次行动 |
| INT8 | 44.1 TOPS | 同一次行动，仍被门控 |

### FP64 分布是两条路径，不是一场争议

约 6.3 和约 12 TFLOPS FP64 之间的表面冲突已被**定论**，定论的方式是 2026-07-15 的一次 clpeak 转储——在一次运行里、一张卡上打印了两个数字（sm_80、70 SMs、7890 MB、驱动 13.0）：

| 路径 | 指令 | 测得 |
|---|---|---|
| FP64 非张量 | 普通 `double` FMA | **6.31 TFLOPS**（`double : 6308.65` GFLOPS） |
| FP64 张量 | `wmma`/`mma` `fp64xfp64+fp64` 8x8x4（DMMA） | **11.96 TFLOPS**（`wmma_fp64 : 11.96`） |

非张量数字是架构的 1:2 速率：同一次运行 FP32（`float : 12565.14` GFLOPS）的一半。张量数字是 GA100 暴露的第二条 FP64 数据路径，也是 11.48 到 12.91 TFLOPS 簇的来源。所以 OpenCL-Benchmark 的 6.421 TFLOPs/s 和 DGEMM 的 11.48 TFLOPS 从没在测同一件事，也不涉及 flop 计数错误。

陈述为：**FP64 非张量约 6.3 TFLOPS、FP64 张量约 12 TFLOPS。** 两者都被解锁完全恢复。同一次转储也是张量行的最干净单次运行来源：`wmma_fp16` 179.19、`fp16_f16acc` 189.66、`wmma_bf16` 179.19、`wmma_tf32` 89.69 TFLOPS。

### 解锁前的张量核崩塌

对照 A800 的周期级测量显示节流对 `mma.sync` 做了什么：

| 战团 | 170HX（节流） | A800 对照 |
|---|---|---|
| 1 | 256.40 周期 | 24.64 周期 |
| 4 | 256.34 周期 | 24.55 周期 |
| 5 | 374.65 周期 | |
| 8 | 513.83 周期 | |
| 16 | 1026.20 周期 | |
| 32 | 2039.46 周期 | 71.45 周期 |

在任何占用下，墙钟吞吐从未超过约 0.082 TFLOPs，对照 A800 的 1.807910 TFLOPs。约 10 倍的每指令惩罚，被每 SM 并行最多 4 个战团 `mma.sync` 的硬限制复合。

---

## 解锁不改变什么

- **它不加 SM。** 解锁前后都是 70 SM、`smid` 0..69 无缺口。卡已经处在它的硅片熔丝下限。见[GA100 硅片](../hardware/ga100-silicon.md)。
- **它不提时钟速度。** 频道内规范表述是 "compute limit yes, bus speed no"（算力限制可以、总线速度不行）。超频是一个单独的 NVML 杠杆；见[调优](../operations/tuning.md)。
- **它不改 PCIe 链路速度或位宽。** Gen2 活在未发布分支上（[PCIe Gen2](pcie-gen2.md)），位宽是一次焊接活（[物理改装](../operations/physical-mods.md)）。
- **它不恢复 INT8 / IMMA。** 解锁的 INT8 测 44.1 TOPS，比同一张卡上的 FP16 约慢 **3.7x**；而 A100 上 INT8 比 FP16 约快 2x。IMLA 熔丝读同一个 `0x5`、SS0 覆盖半字节被相同地设置，实测 IMMA 速率却不跟随。对推理的实际后果：用 W4A16（AWQ 或 GPTQ，INT4 权重配 BF16 激活）并完全避开 W8A8；KV 缓存必须是 BF16。见[LLM 推理](../operations/llm-inference.md)。
- **标量 FP16 从不被节流**，即使在锁定卡上：GA100 以 FP32 fma 速率的 4x 跑 16 位 hfma，锁定卡实测约 42 到 50 TFLOPS 标量 FP16（mixbench 41869 GFLOPS；OpenCL half2-fma 约 48 到 50 TFLOPS）。这就是锁定卡当时已经能用于 LLM token 生成的原因，也是给定 `FUSE_SS_FMLA16` 读 `0x5` 的一个常驻谜题。
- **HBM 带宽和 L2 不受触碰。** 一次同卡 A/B 测得出厂 1592 GB/s 对改装 1599 GB/s、比值 1.0x，在同一张表里 FP32 移动了 30.7x。完整的 32 MB L2 和约 12.5 TIOPS 的 INT32 在出厂时同样不受限制。合在一起，这些界定了节流触碰什么：FP32 FFMA、DP、DP4A 和张量 MMA 路径。

---

## 为什么 `SM_ISSUE_RATE_MODIFIER`（`0x00504204`）不是节流

这是整个领域里最诱人的假线索，值得直白陈述：**`0x00504204` 不是 CMP 节流寄存器，出货解锁也从不碰它。** 对出货树做一次仓库级 grep `0x504204` 返回零命中。

证据：

| 观察 | 细节 |
|---|---|
| 170HX 上读 `0x00000005` | 恰好是节流熔丝值，因此有吸引力 |
| 它在 A100 SXM4 40G、A100 PCIe 40G 和 80G、A10、A5000、A6000、RTX 3080 / 3080 Ti / 3090 / 3090 Ti 和 DRIVE A100 上也读 `0x00000005` | 全速部件，相同的值 |
| 它在一个 96 SM 的 `0x20bb` GA100 上读 `0x00000005`、其每个 `FUSE_SS_*` 都读 `0` | 决定性的反测量，2026-07-27 |
| 它可主机写、清零它不产生性能变化 | 熔丝参考表里记录的空结果 |
| 一块 GA10x 对照（`0x2484`）在那里读 `0x00000007` | 该值在任何部件上都不跟踪节流 |
| 驱动前 170HX 在那个偏移量返回 `0xbadf1201` | 全部五个相邻 SKED 寄存器也一样 |

这个寄存器确实有一个真实的 NVIDIA 侧消费方。对 GSP 固件的逆向工程，在 VA `0x01607b78` 找到一个读注册表键 `RMOverrideSmSpeedSelect`、并把一个存在标志加一个覆盖 dword 存进 GPU 配置结构的 init 函数；它在 VA `0x01155dcc` 被消费，被四个 VA `0x01175a48` 到 `0x01175b2c` 的辅助函数消费，存在标志检查在 `0x014853e4` 和 `0x01491f34`。那个覆盖流进 PROD_DIFF 清单、最终瞄准 `SM_ISSUE_RATE_MODIFIER`、经 HAL 抽象到达（`0x504204` 甚至不作为字面量出现在固件里）。**名字是对的；目标寄存器是错的。**

一个相关且有教益的死路：在 GSP 固件内欺骗 `speed_select` 熔丝值、好让 PROD_DIFF 编程 `SM_ISSUE_RATE_MODIFIER = 0`。对 `gsp_ga10x.bin` 的十四个固件补丁、加 `nvidia.ko` 的十二次编辑，把 FFMA 从 0.3159 TFLOPS 移到 0.3146 TFLOPS——一个 0.4% 的差、被称为测量噪声。它因两个独立原因失败：FECS 经一个横跨 `0x20000000` 到 `0x23050000` 的 priv 窗口到达 GPU 寄存器，而 `SM_ISSUE_RATE_MODIFIER` 住的 SM 寄存器空间（`0x20504xxx`）在其中完全缺失，所以 FECS 物理上无法写它——即使 PROD_DIFF 清单完美；而且 GSP-RM 反正被 NVIDIA 签名。

> [!NOTE]
> **未解问题：`0x00504204` 对一张已解锁的卡施加任何残余限制吗？**
>
> 没人跑过明显的 A/B：在一张 **SS0/SS1 已设**的卡上把 `0x00504204` 写零、再重跑基准套件。寄存器可主机写、写原语在 ROP 工具链里存在、答案是或否。这是算力领域最易处理的开放问题。第二个、相关的未知是，GA100 上那个偏移量的 `0xbadf1201` 是 "privilege-blocked"（被权限阻止）还是 "not decoded"（未解码）：整个 `0x00504xxx` 和 `0x00407xxx` 孔径在 170HX 上返回同一个哨兵，而 GA10x 对照到处返回真实值——这指向一个地址解码差异、而非每寄存器阻止。一个读到真实 `0x00000005` 的 `0x20bb` GA100 让那复杂化。

---

## 为什么算力挺过 FLR

`0x00823804` 处的 `FEAT_OVR_PLM` 坐在**常电（AON）域**里。它是 26 寄存器 PLM 调查里唯一标为 AON 的 PLM，而帧缓冲几何 PLM 里没有一个是。一旦打开，它跨功能级复位保持打开，经它写的 SS0/SS1 值也保持写入。

| FLR 下的行为 | 寄存器 |
|---|---|
| **挺过** | SS0 `0x0082381c`、SS1 `0x00823820`、`FEAT_OVR_PLM` `0x00823804` |
| **不挺过** | CFG1 `0x009a0204`、每-FBPA CFG1、CSTATUS、LMR `0x00100ce0`、FB 几何 PLM（重新上锁）、以及 AON LMR 影子 `0x001180f0`（回退） |
| **被 FLR 清除** | SEC2 复位-PLM 污染（`0x8f` 回到 `0xff`） |

这由一次专门的 FLR 存活扫描（`plm_flr_survival_20260716.sh` 加 `fire_vram_featovr_sweep.sh`）确立、并被第二位测试者提前两天独立佐证。

```bash
# Function Level Reset，每个解锁 harness 都用
echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset
```

**这种不对称是算力解锁先于显存解锁出货的唯一个别原因。** 算力写在常电域里粘住；显存几何写在第一次复位就丢失——这就是显存路径需要一次两加载、无-FLR 工作流的原因。

两个常被混为一谈的澄清：

- **寄存器本身是易失的。** 移除电源就失去它们。出货驱动补丁改变的不是硬件行为，而是打过补丁的模块会在**每次 GSP 引导**、对设备 `0x20C2` 或 `0x2082` 重新应用整套 PLM 打开加 SS0/SS1 序列。所以对用户的说法是 "persists across reboot"（跨重启持久），而硬件的说法 "nothing survives a power cycle"（没有东西挺过断电循环）底下仍是真的。
- **不带驱动加载写 SS0/SS1、然后加载出厂驱动不工作。** 写入明显落地，但出厂驱动会重新锁上 PLM：`0x00823804` 回读 `0xffffff8f`、节流分频器回到 `5`。那个失败模式正是驱动内 GSP 引导路径方法存在的原因。

---

## 剩余的开放问题

> [!NOTE]
> **这个领域的开放问题**
>
> 1. **`0x00504204` 在解锁卡上要紧吗？** 见上。一次 A/B 定论它。
> 2. **为什么 INT8 / IMMA 仍被门控？** IMLA 熔丝读 `0x5`、覆盖半字节与 FMA 的那些被相同地设置，实测 IMMA 却不跟随。下一步：把 `0x00823818` 转储与一个按数据类型的微基准测试并排，看有效 IMLA 字段是否真的是零，并在 `SM_SPEED_SELECT` 块外找一个单独的 DP4A/IMMA 门。
> 3. **隔离 SS1 对 FP64 的效果。** "SS1 nerfs 64-bit compute"（SS1 削弱 64 位算力）的说法严格说是未测试的 2026-07-14 预测，碰巧坐在一个正确的 FP64 测量旁。一次去掉 `0x00823820` 写的单行构建、随后跑 OpenCL FP64 测试，会给答案（若信念正确，预期 6.421 对约 0.19 TFLOPs/s）。
> 4. **解码 `FEATURE_READOUT_1`（`0x00823818`）。** 对出厂 `0x016db6ed` 的一次朴素九乘三位 LSB 优先解包给出 `[5,5,3,3,3,3,3,3,1]`，与熔丝不匹配（均匀 5 配 DP 为 1，预测 `0x01b6db6d`）。要么字段顺序或宽度假设错，要么读出是一个仲裁后的有效速率。无论解码如何，`== 0` 仍是实际的成功测试。
> 5. **为什么 `FUSE_SS_FMLA16 = 0x5` 似乎不节流 FP16？** 很可能因为 FMLA16 管辖一个不同于打包半 CUDA 核心路径的张量/MLA 路径，但没人测过同一张卡两个状态下的 FP16 标量和 FP16 张量。
> 6. **TF32 出厂时被节流吗？** 一张表说 `90.72 → 90.09 TF/s`（未触碰）；另一张、不同卡上，在 1024³、4096³ 和 8192³ 说 `2.96 → 51.53`、`3.01 → 84.75` 和 `3.21 → 80.59 TFLOPS`。两者不可能都对。在由 `0x00823818 != 0x00000000` 确认锁定的一张卡上跑一次 TF32 GEMM 会定论它。
> 7. **`0x008200fc` 可写吗、冷读什么？** 一次扫描 `0xffffffff`、另一次 `0x000003ff`、九-PLM 分支尝试 `status=0xffff` 且没记录回读。该寄存器在净室工具里叫 `FUSE_SS_PLM`、在分支源码里叫 `OPT_PLM`；它们是同一个寄存器。

---

## 相关页面

- [解锁如何工作，端到端](how-it-works.md)
- [SEC2 Falcon 与 Booter 原语](falcon-and-booter.md)
- [权限级别掩码](privilege-level-masks.md)
- [显存几何布局解锁](memory-geometry.md)
- [驱动补丁](driver-patches.md)
- [完整寄存器参考](register-reference.md)
- [GA100 硅片与地板清扫](../hardware/ga100-silicon.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)
- [验证流程](../procedures/verify.md)
- [性能](../operations/performance.md) 和[调优](../operations/tuning.md)
- [术语表](../start/glossary.md)
