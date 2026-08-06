# PCIe Gen2 软件解锁

**本页覆盖内容**：把 CMP 170HX 从 PCIe Gen1（2.5 GT/s）带到 Gen2（5.0 GT/s）、无需硬件改装的完整寄存器机制、它如何在补丁 `0007` 和 `0008` 之间分配、重训练流程、IOMMU 依赖、modprobe 注册表键、以及它在合并前来自的分支谱系。它击败的硬件见[PCIe 子系统](../hardware/pcie-subsystem.md)。

> [!NOTE]
> **已出货：Gen2 于 2026-07-29 合并进 `master`**
>
> Gen2 头一周只在分支上。它在提交 `2e0a2c02`（"PCIe Gen 2 unlock!"）合并，`master` 现在带着 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`，连同 `0001` 到 `0006`。master 的 README 列出 `PCIe Gen 2 speeds | Working`。多台独立机器复现了它。
>
> 仅分支时期有两个细节仍成立、值得知道：`common/constants.yaml` 仍没有 `pcie:` 块，所以寄存器数据活在补丁里而非配置里；一位贡献者把这种方法描述为 "like a script spamming stuff and hoping it sticks"（像个脚本乱喷东西、希望它粘住）——那是对一个步骤之间无回读的 25 写序列的公道描述。它有效，而且不优雅。

## 结果，先说

Gen2 使链路**速度**翻倍。它不碰链路**位宽**，任何分支里都没有代码读或写位宽字段。一张打过 Gen2 补丁、未焊接的卡跑在 Gen2 x4。

| | 出厂，无解锁 | 带解锁器 |
|---|---|---|
| `LnkCap` | `0x00456101`（Gen1 最大，x16） | `0x00456102`（Gen2 最大，x16） |
| `LnkCap2` 受支持速度 | `0x00000002`（仅 2.5 GT/s） | `0x00000006`（2.5 和 5.0 GT/s） |
| `LnkCtl2` 目标 | `0x0000` | `0x0002` |
| `LnkSta` | `0x1041`（Gen1，x4） | `0x1042`（Gen2，x4） |
| `LnkSta2` | `0x0000` | `0x0001` 或 `0x0000`，因机器而异 |
| `DevCap2` / `DevCtl2` | `0x00070803` / `0x1400` | `0x00070813` / `0x0400`（一台机器 `0x7410`） |
| `nvidia-smi` 当前 / 最大 / 位宽 | 1, 1, 4 | 2, 2, 4 |
| 主机带宽 | 约 0.85 GB/s | 约 1.71 GB/s |
| AER 可纠正 / 非致命 / 致命 | 0 / 0 / 0 | 0 / 0 / 0 |

三台独立机器贴出了 Gen2 状态的完整机器生成转储：驱动 610.43.02 配内核 5.15.0-186-generic、驱动 610.43.03 配内核 6.12.54-Unraid 带两张卡、驱动 610.43.03 配内核 6.12.0-hiveos 带两张卡。

## 代码住在哪

| 分支 | `0007-pcie-gen2.patch` | `0008-pcie-gen2-probe-retrain.patch` | `tools/retrain.sh` | IOMMU 处理 | `RMPcieLinkSpeed` |
|---|---|---|---|---|---|
| `master`（出货） | 缺失 | 缺失 | 缺失 | 缺失 | 缺失 |
| `debug-gen2` | 有（畸形 hunk 头） | 缺失 | 已安装，自动发现 BDF，加 `cmpretrain.service` | 无 | `0x1` |
| `Gen2` | 有（头已修复） | 有 | 存在但从未安装，BDF 硬编码 | 自动 | `0x1` |
| `far` | 有 | 有 | 存在但从未安装，BDF 硬编码 | 自动 | `0x2` |
| `deced` | 有 | 有 | 存在但从未安装，BDF 再次自动发现 | 自动 | `0x2` |

### 分支谱系

```text
# 日期为提交者本地时间（-0700）
6621ffc  Effort on PCIe Gen 2                               2026-07-22
4bd6d4d  Fixed malformed patch                              2026-07-22
a9b2470  Delete requirements.txt
746d9f7  PCIe Gen 2 works!                                  2026-07-23   <- debug-gen2 的 tip
0901346  Fix malformed 0007-pcie-gen2 hunk line counts      2026-07-24
d88af88  Potential fix                                      2026-07-24
146da6f  Correct retraining                                 2026-07-24
2f27474  Gen2 + multiple-card support                       2026-07-24
7ea2c4f / 1605219 / bed923f / a14176b / e95784c
6a85e6c  IOMMU enablement as part of install script         2026-07-24
a4de322  (merge)                                            2026-07-26   <- Gen2 的 tip
8854d3e  Remove clamp link to Gen1                          2026-07-26   <- far 的 tip
2326599  Stupid mistake - it appears to be hardcoded        2026-07-27   <- deced 的 tip
```

"advertises Gen2 but will not retrain"（宣告 Gen2 却不肯重训练，`Effort on PCIe Gen 2`、2026-07-22 22:02:43 -0700，即 2026-07-23 05:02 UTC）与 "trains"（训练成功，`PCIe Gen 2 works!`、2026-07-23 18:21:35 -0700，即 2026-07-24 01:21 UTC）之间隔了约二十小时。结果于 2026-07-24 00:59 公开宣布，几小时内被多位独立测试者在不同硬件上复现。

`far` 是 `Gen2` 加恰好一个提交，其在整个树里唯一的内容改动是一行里的一个字符。`deced` 是 `far` 加一个提交，给安装器删除的一个脚本重新加回 BDF 自动发现。

## 机制

解锁有三个阶段。阶段 A 需要 SEC2 Booter 特权；阶段 B 只需要一个打开的 PLM；阶段 C 需要上游桥、根本无法从驱动内的 GSP 钩子里做。

```text
阶段 A  25 次 Booter 路由的写   （0007，kernel_gsp.c）      打开 PLM、设 XP3G 覆盖
阶段 B   6 次普通 BAR0 写       （0007，in-GSP hunk）      清除 DIS_G2、设 MAX_RATE
阶段 C   root-port 重训练       （0008 / retrain.sh / hammer） 实际改变链路速度
```

### 注入点

补丁 `0007` 把它的整个寄存器块注入 `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`、`@@ -4942,6 +4942,260 @@`、紧接现有 `devId` 打印之后、紧接 `plmStatus = kgspSec2PostblTimingRebuildStockSignature(pGpu, pKernelGsp);` **之前**。因此它在 SEC2 post-bootloader 解锁窗口内运行——此时 PLM 仍打开、构造的 Falcon 签名载荷仍通过 Booter Load 提供一条任意 BAR0 写原语。那是显存和算力解锁用的同一次提权；见[Falcon 与 Booter](falcon-and-booter.md) 和[如何工作](how-it-works.md)。

### 阶段 A：23 条目 `xp3gTable`

每条目是一个 `{address, value}` 对、经 Booter 载荷原语推入。对每条目，代码恢复 WPR2 低和高（`GPU_REG_WR32(pGpu, 0x001fa824U, wpr2Lo)` 和 `0x001fa828U, wpr2Hi`）、调用 `kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp, addr, value)`、调用 `kgspExecuteBooterLoad_HAL(...)`、回读目标，并重试一次（`xattempt < 2`），失败时打印 `SEC2_DEBUG: PCIe xp3g booter FAILED to set <name>`。

| # | 地址 | 名称 | 值 | 目的 |
|---|---|---|---|---|
| 1 | `0x0008e1b0` | `XP3G_PLM` | `0xffffffff` | PLM 打开 |
| 2 | `0x0008e1b4` | `XP3G_PLM4` | `0xffffffff` | PLM 打开 |
| 3 | `0x0008e1b8` | `XP3G_PLM8` | `0xffffffff` | PLM 打开 |
| 4 | `0x0008e1bc` | `XP3G_PLMC` | `0xffffffff` | PLM 打开 |
| 5 | `0x00088fe8` | `XVE_D0` | `0xffffffff` | PLM 打开 |
| 6 | `0x00088fec` | `XVE_D4` | `0xffffffff` | PLM 打开 |
| 7 | `0x00088ff0` | `XVE_D8` | `0xffffffff` | PLM 打开 |
| 8-17 | `0x008200d0`、`d4`、`d8`、`dc`、`e0`、`e4`、`e8`、`ec`、`f0`、`f4` | `OPTB_D0` .. `OPTB_F4`（**10** 个寄存器） | `0xffffffff` | PLM 打开 |
| 18 | `0x00823800` | `FEAT_OVR_ECC_PLM` | `0xffffffff` | PLM 打开 |
| 19 | `0x0082057c` | `OPT_GEN23` | `0x00000000` | 值写，**总是失败** |
| 20 | `0x0008e120` | `XP3G_VAL0` | `0x00000000` | 值写 |
| 21 | `0x0008e110` | `XP3G_OVR0` | `0x00000001` | 使能，槽 0 |
| 22 | `0x0008e12c` | `XP3G_VAL3` | `0x00200000` | 值写，导出为 `opt_magic_a100` |
| 23 | `0x0008e11c` | `XP3G_OVR3` | `0x00000004` | 使能，槽 3 |

十八个 PLM 打开加五个值写。两个更多寄存器在表**外**获得同样的两次尝试 Booter 处理，总共 **25 次 Booter 路由的写**：

| 地址 | 名称 | 操作 | 硅片上的结果 |
|---|---|---|---|
| `0x0008860c` | `VSEC_DEVICE` | 设位 0（`|= 1 << 0`） | **失败**：`pre=0x00000800 want=0x00000801`、回读 `0x00000800` 两次、然后 `PCIe VSEC_DEVICE booter FAILED` |
| `0x0008841c` | `PRIV_MISC_1` | 设位 11 和 13，清位 12 和 14 | 第一次尝试**成功**：`0x20340500` 变成 `0x20342d00`、真实 BooterLoad 后仍读 `0x20342d00` |

XP3G 覆盖块是三个平行的四-dword 数组：状态基址 `0x0008e100`、覆盖使能基址 `0x0008e110`、值基址 `0x0008e120`，槽 *n* 在基址 + 4*n*，所以槽 3 是基址 + `0xC`。值总是在使能之前写，所以覆盖从不锁存陈旧数据；而使能编码按槽 one-hot（槽 0 是 `0x1`、槽 3 是 `0x4`）。

> [!NOTE]
> **两个条目失败，Gen2 照样工作**
>
> `OPT_GEN23` 是一个纯 OTP 熔丝感测反射、没有写端口；每个权限级别的每次尝试都返回 `status=0xffff rd=0x00000001`。`VSEC_DEVICE` 也失败。出货补丁仍尝试两者、仍在这两者上失败、链路仍训练成 Gen2。工作的杠杆是 `CYA_0`、`LINK_CONFIG_0`、XP3G 覆盖和 `PRIV_MISC_1`。

> [!NOTE]
> **二手文档里的计数错误**
>
> 三个已发布的计数是错的、可直接对照补丁验证：OPTB 跑是**十个**寄存器（`D0, D4, D8, DC, E0, E4, E8, EC, F0, F4`），不是十一个也不是九个；该表在一个 **23** 条目表里打开 **18** 个 PLM，不是 22；以及晚 hunk 坐在 `kernel_gsp_tu102.c` 里、紧接 Booter Load 返回后——即 GSP-RM **开始运行之前**、不是之后。

### 阶段 B：普通 BAR0 写

`0x00088fe8` / `fec` / `ff0` 处的 XVE PLM 打开后，普通 `GPU_REG_WR32` 写入才落地。在那之前 priv 环会丢弃它们；一次对 `0x08c044` 的探测返回 priv 屏蔽的哨兵 `0xbadf5040` 并被跳过，而 `0x0880a8` 干净地写入并回读。

| 寄存器 | 地址 | 操作 | 备注 |
|---|---|---|---|
| `VSEC_HIERARCHY` | `0x00088610` | `hier = (hier & ~(1U << 12)) | (1U << 0)` | 位 12 门控 `PRIV_MISC_1` 重新编程；修改前活值 `0x00001001` |
| `LINK_CTRL_2` | `0x000880a8` | `lc2 = (lc2 & ~0xFU) | 0x2`，然后 `lc2 = (lc2 & ~0x000F0000U) | 0x000F0000U` | `[3:0]` 里目标链路速度 = 2，`[19:16]` 里 `0xF` |
| `CYA_0` | `0x0008c2c0` | `cya0 = cya0 & ~(1U << 2)` | 清除 `DIS_G2` chicken 位 |
| `LINK_CONFIG_0` | `0x0008c040` | `linkCfg = (linkCfg & ~0x000C0000U) | (0x2U << 18)` | `MAX_RATE` 字段 `[19:18]` 设成 2（5.0 GT/s）。CMP 出厂读 `0x800C4C00`、SPEED = 3 |
| `PL_LINK_RATE` | `0x0008c1c0` | `= 0x00240036` | 见下方注意事项 |
| LTSSM / `XVE_OVR` | `0x0008872c` | `= 0x00000006` | 日志行：`SEC2_DEBUG: PCIe XVE_OVR@8872c=0x%08x; skip mid-boot retrain` |

`CYA_0` 位 2 在**四个**独立位置被清除：`kernel_gsp.c` 的 in-GSP 站点、`kernel_gsp_tu102.c` 的晚站点、`tools/retrain.sh`、和补丁 `0008` 的 `nv_cmp170hx_retrain_gen2()`。`retrain.sh` 把仍置位的位 2 当作硬中止（`retrain: DIS_G2 still set; skip`）。

`PRIV_MISC_1` 是一个配对的使能和值 CYA 覆盖。补丁宏是 `PCIE_GEN2_PRIV_MISC_1_GEN2_EN = ((1U << 11) | (1U << 13))` 和 `PCIE_GEN2_PRIV_MISC_1_GEN2_VAL = ((1U << 12) | (1U << 14))`，请求的值是 `(misc1 | GEN2_EN) & ~GEN2_VAL`：断言两个覆盖使能、把两个值位驱动到零。

> [!NOTE]
> **`PL_LINK_RATE 0x00240036` 不是必需的**
>
> 该写只存在于 `0007` 的 in-GSP 路径。`tools/retrain.sh` 和补丁 `0008` 都不碰 `0x0008c1c0`，而两者都产生 Gen2。A100 强制-代扫描还显示整个 XP_PL 族（`0x8C044`、`0x8C048`、`0x8C04C`）在参考卡的每个代上都读 `0xbadf5040`，所以该族从没对一条工作链路验证过。`0x00240036` 的各个位编码什么在任何地方都没文档化。命名注意：`0x0008872c` 的地址被 `#define` 成 `PCIE_GEN2_LTSSM_ADDR`、而日志字符串叫它 `XVE_OVR`；那种歧义就在源码里。

### 晚 hunk

补丁 `0007` 在 `src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c`、`@@ -611,6 +611,44 @@` 有第二个 hunk。它把四次写作为普通 BAR0 访问、**不用** Booter 重新应用：`PRIV_MISC_1`、`CYA_0` 位 2 清除、`LINK_CONFIG_0` `MAX_RATE = 2`、和 `0x0008872c = 6`。它的日志行带 `late` 后缀。它门控在：

```c
NvU32 lateDevId = pGpu->idInfo.PCIDeviceID >> 16;
if ((lateDevId == 0x20C2 || lateDevId == 0x2082) && status == NV_OK)
```

因此一张 `10de:20b0` 卡完全不受 Gen2 处理，匹配项目其余部分的设备 ID 处理。见[识别你的卡](../start/identify-your-card.md)。

### `0007` 定义的具名地址

```c
#define PCIE_GEN2_LINK_CAP_ADDR        0x00088084U
#define PCIE_GEN2_LINK_CAP2_ADDR       0x000880a4U
#define PCIE_GEN2_LINK_CTRL_2_ADDR     0x000880a8U
#define PCIE_GEN2_LINK_CTRL_STATUS_ADDR 0x00088088U
#define PCIE_GEN2_PL_LINK_RATE_ADDR    0x0008c1c0U
#define PCIE_GEN2_LTSSM_ADDR           0x0008872cU
#define PCIE_GEN2_VSEC_DEVICE_ADDR     0x0008860cU
#define PCIE_GEN2_VSEC_HIERARCHY_ADDR  0x00088610U
#define PCIE_GEN2_XP3G_OVR_BASE        0x0008e110U
#define PCIE_GEN2_XP3G_VAL_BASE        0x0008e120U
#define PCIE_GEN2_XP3G_STATUS_BASE     0x0008e100U
#define PCIE_GEN2_OPT_GEN23_ADDR       0x0082057cU
#define PCIE_GEN2_OPT_GEN3_ADDR        0x00820580U
#define PCIE_GEN2_OPT_MAGIC_ADDR       0x00820520U
#define PCIE_GEN2_PRIV_MISC_1_ADDR     0x0008841cU
#define PCIE_LINK_SPEED_OF(stat)       (((stat) >> 16) & 0xFU)
```

两个值是 `const NvU32` 声明而非 `#define`：

```c
const NvU32 PCIE_GEN2_LINK_SPEED = 0x00000002U;
const NvU32 PCIE_GEN2_PL_LINK_RATE_VALUE = 0x00240036U;
```

`OPT_GEN3` 和 `OPT_MAGIC` 被读取并记录（在 `NV_PRINTF` 参数列表里、带 `OPT=%08x/%08x/%08x` 的格式、针对 GEN23 / GEN3 / MAGIC），但**从不写**。代码试图写的唯一熔丝选项寄存器是 `OPT_GEN23`，而那次写失败。任何地方都没有代码路径请求高于 2 的目标链路速度。

### PLM 表从四个长到九个

出货 master 武装四个 PLM 条目。Gen2 家族分支（`Gen2`、`debug-gen2`、`far`、`deced`，这方面四个逐字节相同）给 `0001-sec2-postbl-plm-ss-cfg.patch` 加五个，得到九个：

| 索引 | 地址 | 名称 | 目标值 | 在出货 master 上？ |
|---|---|---|---|---|
| 0 | `0x001fa7cc` | `WPR_CFG` | `0xfffff0ff` | 是 |
| 1 | `0x009a0148` | `FBPA` | `0xffffffff` | 是 |
| 2 | `0x001fa7c4` | `WPR` | `0xffffffff` | 是 |
| 3 | `0x00823804` | `FEAT` | `0xffffffff` | 是 |
| 4 | `0x00088ff4` | `XVE` | `0xffffffff` | 仅 Gen2 家族 |
| 5 | `0x00088ab4` | `XVE_B` | `0xffffffff` | 仅 Gen2 家族 |
| 6 | `0x00088ff8` | `XVE_C` | `0xffffffff` | 仅 Gen2 家族 |
| 7 | `0x00823b00` | `FEAT2` | `0xffffffff` | 仅 Gen2 家族 |
| 8 | `0x008200fc` | `OPT_PLM`（净室工具里也叫 `FUSE_SS_PLM`） | `0xffffffff` | 仅 Gen2 家族 |

每条目最多两次尝试、每次尝试前重新武装 WPR2 低和高。除 `WPR_CFG` 在 `0xfffff0ff`（这是正确的例外）外，全部九个回读 `0xffffffff`。完整细节在[权限级别掩码](privilege-level-masks.md)。

### `constants.yaml`

Gen2 分支加一个带恰好这些键的 `pcie:` 块：

```yaml
pcie:
  target_gen: 2
  link_speed_gen2: "0x2"
  xve_link_control_status: "0x00088088"
  xve_link_control_2: "0x000880a8"
  pl_link_rate_addr: "0x0008c1c0"
  pl_link_rate_value: "0x00240036"
  vsec_hierarchy_addr: "0x00088610"
  vsec_device_addr: "0x0008860c"
  xp_fuse_override_base: "0x0008e110"
  xp_fuse_override_val_base: "0x0008e120"
  opt_gen23_addr: "0x0082057c"
  opt_magic_a100: "0x00200000"
```

对机制核心的五个寄存器在 yaml 里**缺失**：`CYA_0` `0x0008c2c0`、`LINK_CONFIG_0` `0x0008c040`、`PRIV_MISC_1` `0x0008841c`、`LINK_CAP` `0x00088084` 和 `0x0008872c`。同一个提交还从 8gb 和 10gb 档位块里删掉了 `comment:` 行。出货 master 完全没有 `pcie:` 块。

## 补丁 0007 对补丁 0008

它们是**互补的，不是替代的**。

| | `0007-pcie-gen2.patch` | `0008-pcie-gen2-probe-retrain.patch` |
|---|---|---|
| 触碰的文件 | `kernel_gsp.c`、`kernel_gsp_tu102.c` | `kernel-open/nvidia/nv.c` |
| 需要的特权 | SEC2 Booter（写 PLM 保护的寄存器） | 除三个已解锁的 BAR0 寄存器和标准 PCIe 能力访问外不需要 |
| 它达成什么 | 把 `LINK_CAP` / `LinkCap2` 提高到 Gen2 | 从上游桥触发实际链路重训练 |
| 它不能做什么 | 重训练（明确谢绝："skip mid-boot retrain"） | 单独提高 `LINK_CAP` |
| 分支 | `debug-gen2`、`Gen2`、`far`、`deced` | `Gen2`、`far`、`deced` |
| hunk 大小 | 260 行（254 加）和 44 行（38 加） | 加 includes 加一个函数和一个调用点 |

`driver/build.sh` 按文件名顺序应用它们：

```bash
patches=("${PATCH_DIR}"/*.patch)
for p in "${patches[@]}"; do patch -p1 < "${p}"; done
```

### 补丁 0008 细节

`nv_cmp170hx_retrain_gen2()` 被加到 `kernel-open/nvidia/nv.c`、连同 includes `<linux/delay.h>`、`<linux/io.h>`、`<linux/pci.h>` 和 `<uapi/linux/pci_regs.h>`。调用被插在 `nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;` 之后、`(void)rm_get_gpu_uuid_raw(sp, nv);` 之前。

```text
除非 gpu->device 是 0x20c2 或 0x2082 否则返回
pci_upstream_bridge(gpu)                 -> 若 NULL 则退出
ioremap(pci_resource_start(gpu, 0), 0x90000)   /* 576 KiB，恰好够到达 0x8c2c0 */
清除 CYA_0 位 2           在 BAR0 0x8c2c0
设 MAX_RATE = 2           在 BAR0 0x8c040   ((v & ~0x000c0000) | (2 << 18))
写 0x00000006             到 BAR0 0x8872c，回读以冲刷 posted writes
iounmap
msleep(50)
在 GPU 和上游桥两者上都设 PCI_EXP_LNKCTL2_TLS_5_0GT
在上游桥上设 PCI_EXP_LNKCTL_RL
以 msleep(100) 轮询 LnkSta 20 次      /* 最坏 2.05 s */
```

> [!CAUTION]
> **0008 的成功测试在这张卡上永远无法通过**
>
> 谓词是：
>
> ```c
> if (!ret && (link_status & PCI_EXP_LNKSTA_DLLLA) &&
>     ((link_status & PCI_EXP_LNKSTA_CLS) >= PCI_EXP_LNKSTA_CLS_5_0GB))
> ```
>
> `PCI_EXP_LNKSTA_DLLLA` 是位 13（`0x2000`）。一张 Gen2 训练过的 170HX 读 `LnkSta = 0x1042`，而 `0x1042 & 0x2000 = 0`，所以即使 `0x1042 & 0xF = 2` 意味着 5.0 GT/s，谓词也失败。那个位**永远无法**在这个端口上设置：DLL Link Active Reporting Capable 是 `LnkCap` 位 20，而 GPU 的 `LnkCap = 0x00456102` 位 20 清除。上游根端口确实报告它（`LnkCap 0x007b7905`、`LnkSta 0x7042`），但 `0008` 从 **GPU** 读 `LnkSta`。
>
> 后果：在每张工作的 Gen2 170HX 上，补丁 `0008` 烧掉完整的 20 × 100 ms、然后以 `NV_DBG_ERRORS` 打印 `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)`。那条消息是一个假阴性。它已经误导过至少一份下游分析、得出 `0008` "runs too late"（跑得太晚）的结论。

日志级别约定复合了它。`0008` 里成功在 `NV_DBG_INFO` 打印，而全部四个失败路径在 `NV_DBG_ERRORS` 打印；`0007` 反过来，连例行的 pre 和 post 转储都在 `LEVEL_ERROR` 发出，所以它们活过默认 dmesg 过滤。**不要读 dmesg 来判断 Gen2 是否工作。** 读 `nvidia-smi --query-gpu=pcie.link.gen.current` 或 `lspci` 的 `LnkSta`。

## 重训练

重训练是实际改变链路速度的步骤，必须从**上游桥的** Retrain Link 位驱动，绝不由 GPU。Link Control 的位 5（`0x20`）只在 downstream 端口上有意义。语料库里每个实现都这么干：

| 实现 | 重训练调用 |
|---|---|
| `debug-gen2` `retrain.sh` | `pci_write(up, cap + 0x10, 2, ctl | 0x20)` |
| `Gen2` / `far` / `deced` `retrain.sh` | `setpci -s <UP> CAP_EXP+10.w=<cur|0x20>` |
| 补丁 `0008` | `pcie_capability_write_word(upstream, PCI_EXP_LNKCTL, upstream_ctl | PCI_EXP_LNKCTL_RL)` |
| 独立 hammer 脚本 | `setpci -s "${rp}" "CAP_EXP+0x10.w=...|0x20"` |

`pci_upstream_bridge()` 返回 NULL 时 `0008` 以 `CMP Gen2: no upstream PCIe bridge; skipping link retrain` 退出，而 `debug-gen2` 的 systemd 单元字面上命名为 `Description=CMP 170HX PCIe Gen2 upstream soft retrain`。

### 手动主机侧流程

```bash
# 1. 为你的 GPU 找到上游根端口
lspci -tv

# 2. 在 CAP_EXP+0x30 的 LNKCTL2 里设 Target Link Speed = 2（Gen2）
sudo setpci -s 64:00.0 CAP_EXP+0x30.L=2

# 3. 在 CAP_EXP+0x10 的 LNKCTL 里设 Retrain Link 位（0x20），保留当前位
sudo setpci -s 64:00.0 CAP_EXP+0x10.w=$(( LnkCtl | 0x20 ))

# 4. 从 GPU 验证
sudo lspci -vv -s <gpu_bdf> | grep -E "LnkCap:|LnkSta:"
```

`CAP_EXP+0x30.L=0x4` 形式目标是 Gen4、在这张卡上从未成功。内核 6.x 及以后在 bwctrl 服务里含 `pcie_set_target_speed()`，但它**不被导出**，所以 LNKCTL2 和 LNKCTL 写必须手工发出。

### `retrain.sh` 序列

`Correct retraining`（`146da6f`）相对于 `debug-gen2` 重排了脚本，后者先做 BAR0 写：

```text
pre-state 转储
  -> setpci -s <UP> CAP_EXP+30.w=<(cur & ~0xF) | 0x2>   （LNKCTL2 TLS = 2，在 UP 和 GPU 上）
  -> sleep 0.2
  -> 重新打开 BAR0，在 0x8C2C0 清除 DIS_G2，在 0x8C040 设 MAX_RATE = 2
  -> sleep 0.05
  -> 验证
  -> setpci -s <UP> CAP_EXP+10.w=<cur | 0x20>            （Retrain Link）
  -> sleep 2.0                                            （从 debug-gen2 的 1.5 升上来）
  -> 读 CAP_EXP+12.w，打印 "retrain: speed_after=<sta & 0xF>"
```

早退前提：`nvidia-smi` `memory.total` 为空或 `[N/A]`；`pcie.link.gen.current` 已经是 2；`pcie.link.gen.max` 不在 {2, 3, 4} 里；BAR0 或 CYA 读 `0xFFFFFFFF`；`DIS_G2` 仍置位；`LINK_CAP` 速度半字节低于 2；以及 BAR0 写后 "not alive or DIS_G2 set or mx != 2"。只有 Python 块里的检查打印 skip 行。前三个在 shell 包装器里跑、是带无输出的裸 `exit 0`，所以一次完全静默的运行是正常的，不是脚本没启动的证据。

每个实现都先等驱动起来。`debug-gen2` 用 systemd `ExecStartPre=/bin/sleep 15` 加 `for _ in $(seq 1 60); do nvidia-smi -L && break; sleep 1; done`。`Gen2`、`far` 和 `deced` 在 `resource0` 存在和 `nvidia-smi -L` 两者上轮询 `for i in $(seq 1 120)`。`0008` 在 probe 内跑，所以只需要 `msleep(50)` 加 20 × `msleep(100)`。

> [!WARNING]
> **实验性：`tools/retrain.sh` 在 Gen2、far 和 deced 上是死代码**
>
> 那些分支带一个它们自己安装器从 `/usr/local/sbin` 删除的脚本。对它们的安装器 grep `retrain` 只返回删除块。任何地方都没有 `install -m 0755 tools/retrain.sh`。要使用它必须作为 root 手工跑。更糟的是，`Gen2` 和 `far` 上脚本硬编码一位开发者的 PCI 地址（`SYS=/sys/bus/pci/devices/0000:0a:00.0`、`GPU, UP = "0a:00.0", "09:01.0"`、`PATH = "/sys/bus/pci/devices/0000:0a:00.0/resource0"`）并在任何其它机器上静默瞄准错误的设备。这是一次回归：`debug-gen2` 自动发现两者。`deced`（`2326599`）恢复发现，用
>
> ```bash
> find_gpu_bdf() {
>   for id in 10de:20c2 10de:2082; do
>     lspci -d "$id" -D 2>/dev/null | head -1 | cut -d' ' -f1
>   done | head -1
> }
> UP_BDF="$(basename "$(dirname "$(readlink -f "/sys/bus/pci/devices/$GPU_BDF")")")"
> ```
>
> 并在 120 次等待迭代的每一次重新轮询 `find_gpu_bdf`。脚本行数：`debug-gen2` 138、`Gen2` 106、`far` 106、`deced` 115。

### 独立的早引导 hammer

一个单独的社区设置脚本采取相反方法、尽可能早跑，因为 "late is the same as never"（晚了就等于永远不做）。它的模型：`0007` 的 `CYA_0`、`LINK_CONFIG_0` 和 `VSEC_DEVICE` 写仍持有时，端点**瞬态地**宣告 `LnkCap2 = 0x06`；窗口在引导后约 8 到 14 秒、GSP 引导期间打开，在 RM 清除 `VSEC_DEVICE` 位 0 时关闭。陈述的关键洞见是，能力不需要持久，因为窗口打开时训练成 Gen2 的链路在它关闭后保持训练。

实现：`/usr/local/sbin/cmp170hx-gen2-hammer` 以 `MAX_ITER=600`、`SLEEP_S=0.05`（30 秒覆盖）循环，两端把 LnkCtl2 目标设成 Gen2，每趟切换**根端口的** Retrain 位。它典型地在约第 30 次迭代、约 1.5 秒内成功。它的单元用 `DefaultDependencies=no`、`After=sysinit.target`、`Before=multi-user.target`、`Type=oneshot`、`TimeoutStartSec=120`、`WantedBy=sysinit.target`，并用 `strings /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko | grep -q 'SEC2_DEBUG: PCIe'` 检查已安装的驱动，记录到 `/var/log/cmp170hx-gen2.log`。

> [!NOTE]
> **未解问题：Gen2 窗口是瞬态的吗？**
>
> hammer 的瞬态窗口模型被一份归档的稳态转储（内核 6.12.0-hiveos、驱动 610.43.03、两张 `10de:20c2` 卡）矛盾，它**在引导完成后**读到 `LnkCap2 = 0x00000006` 和 `LnkCap = 0x00456102`。`0007` 自己的 dmesg 也显示 `VSEC_DEVICE` 写失败，所以 RM 应该清除的那个位可能从没置位过。双方都是一手。什么能定论它：从早引导到 60 秒、每 100 ms 对 `setpci -s <bdf> CAP_EXP+0x2c.l` 做一次带时间戳的轮询，在 AMD CachyOS 主机和 HiveOS 主机上各一次。在那之前，把瞬态窗口当一个主机的观察，不是卡的一个属性。

## Modprobe 注册表键

`install.sh` 第 5b 步写 `/etc/modprobe.d/cmp-pcie-gen2.conf`：

```text
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"
```

净室工具把该键记为承重，在一个带日期、2026-07-24 在卡上确认的 docstring 里：`"REQUIRES: driver loaded with NVreg_RegistryDwords=\"RmForceEnableGen2=1;RMPcieLinkSpeed=0x1\" (else the RM re-clamps Gen1 every retrain)."`（要求：驱动带……加载，否则 RM 每次重训练都把 Gen1 重新钳制。）分开地，同一个设置脚本把 `RmForceEnableGen2` 列在 "tested and confirmed unnecessary"（测试并确认不必要）的事物里，而没人显示过那个键单独做任何事。

> [!NOTE]
> **未解问题：`RMPcieLinkSpeed=0x1` 还是 `0x2`？**
>
> 两种拼写都出货。`debug-gen2`（`install.sh:191`）和 `Gen2`（`install.sh:280`）写 `0x1`；`far`（`install.sh:280`）和 `deced`（`install.sh:280`）写 `0x2`，由提交 `8854d3e` "Remove clamp link to Gen1" 引入。注意，`Gen2` 分支——那个 README 声称 Gen2 "Working ✓" 的——出货 `0x1`，而卡上确认是用 `0x1` 做的。两种读数内部都自洽，取决于该键意思是 "clamp to gen N"（钳制到代 N）还是 "enable up to gen N"（使能到代 N）。不存在 A/B 引导测试。两个值都不应作为规范呈现。什么能定论它：同一张卡和内核引导三次——无键、带 `0x1`、带 `0x2`——每次贴 `LnkSta`。便宜又决定性。

## IOMMU 使能

从提交 `6a85e6c`（2026-07-24）起，安装器自动配置 IOMMU passthrough。在那之前忘记它是 Gen2 结果失败最常见的原因。

`install.sh` 读 `/proc/cpuinfo`：对 `GenuineIntel` 选 `intel_iommu=on iommu=pt`，对 `AuthenticAMD` 选 `amd_iommu=on iommu=pt`，剥离任何现有 `intel_iommu=*`、`amd_iommu=*` 或 `iommu=*` 令牌，重写 `/etc/default/grub`（`GRUB_CMDLINE_LINUX_DEFAULT`，回退到 `GRUB_CMDLINE_LINUX`）或 `/etc/kernel/cmdline`，并取一个 `*.cmpunlocker.bak` 备份。`--no-iommu` 退出。它警告 IOMMU 也必须在 BIOS 或 UEFI 里启用（VT-d、AMD-Vi 或 SVM）。`remove.sh` 恢复备份、打印 `Reverted IOMMU kernel parameters (effective after reboot)`，或警告 `No IOMMU config backup found - kernel command line left as-is`。

`debug-gen2` 完全没有 IOMMU 处理，出货 master 也没有。`6a85e6c` 之前的手动配方：

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt"/' /etc/default/grub
sudo update-grub
sudo reboot
dmesg | grep -i iommu
```

> [!NOTE]
> **未解问题：IOMMU passthrough 真的必需吗？**
>
> 支持方：多位测试者从 "got 64GB memory, BUT still PCIe 1" 到一次 grub 改动后成功；维护者的 `DEBUGGING.md` 把它作为 "PCIe still at Gen1 after install"（安装后 PCIe 仍在 Gen1）的*唯一*补救；安装器现在自动做它。反对方：独立设置脚本把 `iommu=pt` 和 VT-d 列在 "tested and confirmed unnecessary"（测试并确认不必要）的事物里，而它确认的主机加 AMD HiveOS 成功案例**根本没做 grub 改动**。对 `iomem=relaxed` 也存在直接矛盾的单一测试者报告：一位测试者卡在 2.5 GT/s "until i messed with iommu configuration in grub / because mmap was failing"（直到我在 grub 里摆弄 iommu 配置 / 因为 mmap 失败），另一位跑了 `intel_iommu=on iommu=pt iomem=relaxed` 却一无所获。一个貌似合理却未演示的调和是：`iomem=relaxed` 只对基于用户态 `mmap` 的重训练要紧，IOMMU 模式只在某些芯片组上要紧。什么能定论它：在相同软件上做 {IOMMU off、on、pt} × {Intel、AMD} × {用户态 hammer、驱动内 0008} 的矩阵。

## 验证

```bash
# 预期 "2, 2"
nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max --format=csv

# 预期 "LnkSta: Speed 5GT/s"
sudo lspci -d 10de:20c2 -vv | grep -E 'LnkCap:|LnkSta:'
```

三条规则，按重要性：

1. **用 `LnkSta` 验证，绝不用 `LnkCap`。** 链路仍在以 Gen1 训练时，`LnkCap` 可能读 Gen2。那个陷阱是大多数经不起推敲的 "it works"（能工作）声称的既定来源。
2. **预期 sysfs 说谎。** 一张 Gen2 训练过的卡上，`/sys/bus/pci/devices/<bdf>/max_link_speed` 可能仍读 `2.5 GT/s`、而 `current_link_speed` 读 `5.0 GT/s`。一台机器报告一致的 `max 5.0 GT/s`；三张卡跨两台机器报告了不匹配。那是预期的、不是故障。
3. **主机带宽大致翻倍、从约 0.85 GB/s 到约 1.7 GB/s，才是真正的证明。**

`Gen2/verify.sh` 只检查**显存几何布局**、完全不包含 PCIe 检查，尽管分支 README 列出 `| PCIe Gen2 link (5GT/s, Device Max >= 2) | Working ✓ |`。见[验证](../procedures/verify.md)。

## 诊断字符串

| 来源 | 字符串 | 含义 |
|---|---|---|
| `0007` | `SEC2_DEBUG: PCIe xp3g booter FAILED to set <name>` | 一个 PLM 或熔丝写没经 Booter 落地 |
| `0007` | `SEC2_DEBUG: PCIe VSEC_DEVICE booter FAILED` | 在这颗硅片上预期；Gen2 仍工作 |
| `0007` | `SEC2_DEBUG: PCIe PRIV_MISC_1 booter FAILED` | 不预期；这个写通常第一次尝试成功 |
| `0007` | `SEC2_DEBUG: PCIe CYA_0 after clear DIS_G2: 0x%08x (bit2=%u)` | 信息性；`bit2` 应读 0 |
| `0007` | `SEC2_DEBUG: PCIe XVE_OVR@8872c=0x%08x; skip mid-boot retrain` | 信息性且刻意 |
| `0008` | `CMP Gen2: no upstream PCIe bridge; skipping link retrain` | 卡不在能重训练它的桥后面 |
| `0008` | `CMP Gen2: cannot map BAR0; skipping link retrain` | `ioremap` 失败 |
| `0008` | `CMP Gen2: PCIe capability access failed (<ret>); skipping link retrain` | 配置访问错误 |
| `0008` | `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)` | **假阴性。** `0x1042` *就是* Gen2 |
| `0008` | `CMP Gen2: PCIe link trained to Gen<n>` | 成功，但在 `NV_DBG_INFO` 发出、所以通常被过滤 |
| `retrain.sh` | `BAR0 dead; skip` / `DIS_G2 still set; skip` / `Cap Gen<n>; skip` / `BAR0 dead after TLS; skip` / `preconditions failed; skip` | 早退 |

用 `sudo dmesg | grep SEC2_DEBUG` 读全部。记录的计数：Gen1 构建、无 PCIe 补丁时 34 行，Gen2 构建 80 行，以及两张独立的双卡 Gen2 机器在 610.43.03 上 `pcielink.sh` 的 `SEC2_DEBUG lines=152`，各自在同一次输出里带 `OPT=00000001/00000001/16680000`。唯一归档的双卡 Gen2 分支 `610.43.03` 原始 dmesg 含 134 行，唯一归档的单卡捕获含 29。

> [!NOTE]
> **行数不是可靠的跨构建指纹**
>
> 记录的值是 29、34、80、134 和 152，取决于构建、分支和卡数。不要把不匹配读成安装失败。

> [!NOTE]
> **Booter 运行状态总是 `0xffff`**
>
> `kgspExecuteBooterLoad_HAL` 对每次载荷运行返回 `0xffff`，无论写入是否落地。每次运行后 seccode 错误码坐在 mailbox0，而 `mailbox0 != 0` 从 `s_executeBooterUcode_TU102` 产生 `NV_ERR_GENERIC`。对载荷运行，这是预期的 "invalid signature" 抱怨，在 priv 序列器脚本已经运行*之后*提出。**寄存器回读是唯一有效的成功标准。** 对真实 BooterLoad，`mailbox0 != 0` 是一个真实失败。

## 要求和约束

- **驱动**：nvidia-open `610.43.03`（默认）或 `610.43.02`，精确匹配。`debug-gen2` 和 `Gen2` 上的 `driver/VERSION` 与出货 master 相同，构建在其它任何版本上硬失败。因为 `0007` 补丁 `kernel_gsp.c` 和 `kernel_gsp_tu102.c`、`0008` 补丁 `kernel-open/nvidia/nv.c`，Gen2 工作被紧密绑定到那两个发布。见[驱动版本](../procedures/driver-versions.md)。
- **安全启动必须关闭。** `mokutil --sb-state` 报告 `SecureBoot enabled` 时 `install.sh` 死掉。
- **设备 ID** 必须是 `10de:20c2` 或 `10de:2082`。一张 `10de:20b0` 卡会安装、却得到 `unlock path not gated for this ID; skipping`。
- **裸金属或 Oculink。** 直通 VM 宣告 Gen2 却不训练；Thunderbolt 3 坞破坏整个解锁、不只是 PCIe。

### 持久性

冷启动总是用锁定的 CMP 表从闪存运行签名的 DevInit，所以首次枚举总是显示 Gen1。普通 `rmmod` 和 `modprobe` **不**重跑 DevInit（无 PERST），所以补丁会在每次 GSP 引导时重新触发、恢复寄存器值；但重训练必须在每次重载后重新触发。完整复位路径（PERST、`nvidia-smi --gpu-reset`、`echo 1 > /sys/bus/pci/devices/<bdf>/reset`）会重跑签名的 DevInit、丢弃修复。这个模型与每个观察一致，但从未被一次直接的 PERST 前后测量确认。

Gen2 家族上的 `remove.sh` 清理整个足迹：禁用并复位失败 `cmpretrain.service` 和 `cmp-gen2-retrain.service`、移除两个单元文件、`/usr/local/sbin/retrain.sh`、`/usr/local/sbin/cmp-gen2-retrain.sh` 和 `/etc/modprobe.d/cmp-pcie-gen2.conf`（`Removed PCIe Gen2 helpers`），然后恢复 `*.cmpunlocker.bak` 内核命令行备份。

## 已知失败模式

| 症状 | 状态 |
|---|---|
| `install.sh` 后 `nvidia-smi` 报 `2, 2`、重启后却报 `1, 1`、可复现 | 未解释。重跑 `install.sh` 每次都恢复。一位 NixOS 用户通过在内核层面应用补丁、让它在每次引导重新应用来回避它。工作假设：*打过补丁的*模块实际上不是引导时加载的那个。责怪重训练前先查 `modinfo`，并找重启后的 `SEC2_DEBUG: PCIe` 行 |
| 一个 Intel 平台从未到达 Gen2 | 一块 ASUS W890 SAGE、四个 PCIe 5.0 x16 槽、Ubuntu 24.04、内核 7.0.0-28-generic、两张卡。试过：`Gen2` 分支、`debug-gen2`、一个外部 fork、grub 行包括 `intel_iommu=on iommu=pt iomem=relaxed`、一张焊接过的卡和一张未改装的卡、槽 1 和 4。每次都：`LnkSta: Speed 2.5GT/s (downgraded), Width x4 (downgraded)` 而 `LnkCap` 正确宣告 5 GT/s。内核版本被一位把 CachyOS 回滚到 6.12-LTS 却无变化的独立测试者排除。对比工作案例：AMD、HiveOS Ubuntu 22.04、内核 6.12.0、根本没有任何 grub 改动 |
| Proxmox 或 VFIO 下的客户机 VM | 宣告能力、不发生训练。重训练需要从**宿主机**在物理根端口上驱动，因为客户机访问不了真实的上游桥 |
| Thunderbolt 3 | Booter Load 彻底失败（`0x15` / `0xffff`），所以这是算力和显存失败、不是 PCIe 的。用 Oculink |
| 第一份公开补丁应用不上 | `kernel_gsp_tu102.c` 上 `patch: **** malformed patch at line 264`。两个 hunk 头夸大了它们的行数：`@@ -4942,6 +4942,323 @@` 应是 `260`，`@@ -611,6 +611,50 @@` 应是 `44`。当天被 `0901346` 修复。`debug-gen2` 的 `0007` 对 `Gen2` 的一次完整 diff 显示恰好两行不同、都是 hunk 头；补丁主体在全部四个分支间逐字节相同。它之所以能活下来，只是因为 `build.sh` 用宽松的 `patch -p1` 而非 `git apply` |

还要注意，在补丁应用错误里看到 `kernel_gsp_tu102.c` **不**意味着补丁是给 Turing 的。`_TU102` 后缀的 GSP 函数正是 170HX 执行的；它们出现在工作 Ampere 卡上的 Booter 失败消息里（`s_executeBooterUcode_TU102`、`kgspExecuteBooterLoad_TU102`、`kgspBootstrap_TU102`）。

不要把这个 `0007` 和净室线的 `0007-pcie-gen4-shadow.patch` 混淆，后者被放弃在一个引导循环里。相同的编号、不同的补丁。

## 实测 Gen2 结果

| 量 | 值 | 条件 | 置信度 |
|---|---|---|---|
| 主机带宽，Gen2 x4 | 1.68 GB/s 发送、1.71 GB/s 接收 | OpenCL-Benchmark、一份归档截图、一张未改装卡 | 中等 |
| 主机带宽，Gen2 x4 | 约 1.71 GB/s | 设置脚本自己的预测、"约 0.85 到约 1.71 GB/s，恰好 2x"、在一台 AMD B650M / CachyOS 主机上验证。不是独立测量 | 低 |
| Gen1 x4 到 Gen2 x4，一次 A/B | 1.67 到 3.24 GB/s | OpenCL、一张只协商到 x8 的改装卡上 | 中等 |
| Gen2 x16 | 6.63 到 6.67 GB/s | `ocl_pcie_bw`、一台机器、2026-07-26、完整 24 电容改装 | 中等 |
| pp512 | 203.84 到 277.84 t/s | Q8 ik_llama 带 MTP、10 GB 卡解锁到 40 GB、`--spec-type mtp:n_max=2,p_min=0.0`、其它一切不变 | 高 |
| pp2048 | 328.81 到 449.41 t/s | 同一次 A/B | 高 |
| pp8192 | 363.25 到 493.86 ± 16.92 t/s | 同一次 A/B | 高 |
| tg128 | 38.15 到 41.52 ± 1.89 t/s | 同一次 A/B | 高 |
| tg512 | 37.69 到 40.12 t/s | 同一次 A/B | 高 |
| tg2048 | 36.78 到 37.90 t/s | 同一次 A/B | 高 |
| Gen2 下的 AER 计数器 | 0 / 0 / 0 | 两张 `0x20c2` 卡、内核 6.12.0-hiveos | 高 |
| Gen2 去加重 | -3.5 dB | `LnkSta2`、第一份确认的 Gen2 捕获 | 中等 |

预填充受益显著；token 生成几乎不动。那匹配算术：在 5120 隐藏维度下，fp16 激活是每 token 每跳 10,240 字节，所以解码流量远没到链路天花板。见[LLM 推理](../operations/llm-inference.md)。

## 开放问题

> [!NOTE]
> **未解问题：修复 0008 成功谓词**
>
> 整个 PCIe 领域最易处理的一项，一处改动。删掉 `PCI_EXP_LNKSTA_DLLLA` 项，或让它以 `PCI_EXP_LNKCAP_DLLLARC` 为条件，或从上游桥而非端点读 `LnkSta`。也把成功打印提到 `NV_DBG_ERRORS` 以匹配 `0007` 的约定。

> [!NOTE]
> **未解问题：0008 是足够、不必要、还是主动误导？**
>
> 三位独立测试者报告 `0008` 修复多卡 Gen2 并消除崩溃。独立设置脚本断言 `0008` 在能力窗口关闭后约三秒、于驱动 probe 时运行，并把它列在 "tested and confirmed unnecessary"（测试并确认不必要）的事物里。DLLLA 缺陷让**两个**立场都复杂化：`0008` 的失败消息在这张卡上无条件发出，所以它不是重训练失败的证据，同样三位测试者可能是在读经另一条路线到达 Gen2 的卡上的 `nvidia-smi`。什么能定论它：在 `0008` 存在、hammer 服务缺失的情况下安装 Gen2 分支，并在 hammer 已知成功的一台主机上、冷启动后检查 `pcie.link.gen.current`。

> [!NOTE]
> **未解问题：为什么有些用户得到 Gen2、有些没有？**
>
> `pcielink.sh` 报告被专门传开，好让内核、驱动、序列号、板卡料号和 VBIOS 能对照成功和失败相关联。在其它方面相同的 `900-11001-0108-000` 板上已经有两种 VBIOS 版本在证据里：`92.00.6D.00.0A` 和 `92.00.67.00.01`。下一步：按 VBIOS 和根端口型号制表，并测试记录在案的冷启动依赖（一次净室运行冷启动后需要重新打开 27 个 PCIe PLM 中的 18 个）。

> [!NOTE]
> **未解问题：把 Gen2 合并进 master**
>
> 树里可见的阻碍：`0007` 是一个通篇在 `LEVEL_ERROR` 记录的大型调试插桩 hunk；`tools/retrain.sh` 在 `Gen2` 和 `far` 上是死代码；`constants.yaml` 遗漏机制依赖的五个寄存器中的……；`verify.sh` 完全不检查 PCIe。多卡、IOMMU 和 Gen2 是否、以及以什么顺序合并，未决定。多卡安装器改动自包含、可以单独落地。

> [!NOTE]
> **未解问题：一个未解释的早期 Gen2 声称**
>
> 一份 2026-07-05 日期的验证净室交流把一次 Gen3 声称纠正为 "only 2.0 was"（只有 2.0 是）、把 Gen2 当作已经完成，比复现结果早三周、直接矛盾一份 2026-07-07 仍说 "We still need something for PCIe 2.0"（我们仍需要为 PCIe 2.0 做点什么）的消息。要么一个更早的独立结果从未传播，要么时间戳被错归。只有原始消息元数据能定论它。那条消息的技术内容（Gen3 是熔丝门控的）与其它一切一致、可以依赖；日期不能。

## 参见

- [PCIe 子系统](../hardware/pcie-subsystem.md)，熔丝、DevInit 表和位宽上限
- [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)，未解决的那一半
- [权限级别掩码](privilege-level-masks.md)，九条目 PLM 表
- [Falcon 与 Booter](falcon-and-booter.md)，`0007` 骑其上的写原语
- [驱动补丁](driver-patches.md)，完整 `0001` 到 `0008` 清单
- [寄存器参考](register-reference.md) 和[寄存器索引](../appendix/register-index.md)
- [排障](../procedures/troubleshooting.md)
- [状态板](../frontier/status-board.md)
