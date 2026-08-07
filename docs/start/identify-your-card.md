# 识别你的卡

**本页内容。** 如何精确确定你持有哪一款 CMP 170HX，从而确定适用哪个解锁档位。包括 `lspci` 设备 ID、子系统 ID、板卡和 GPU 料号、解锁前后 `nvidia-smi` 报告的内容、散热器下方的晶片标记、用于区分两个 SKU 的寄存器级指纹，以及 `install.sh` 在安装时运行的精确档位检测阶梯。最后是一张从“你观察到的”到“你得到的”的决策表。

**核心结论，一句话。** 有两种 170HX SKU，它们解锁到不同容量：**8 GB 卡，PCI ID `10de:20c2`，解锁到 64 GB**；**10 GB 卡，PCI ID `10de:2082`，解锁到 40 GB**。永远不要搞混。第三个 ID `10de:20b0` 会被安装器检测到，但它**不是** 170HX，也不会解锁。本页其它一切内容都是对这一个区分的佐证。

最快的回答：

```bash
lspci -nn | grep -i nvidia
```

如果方括号里的配对读作 `[10de:20c2]`，你有一张 8 GB 卡，将走向 64 GB。如果读作 `[10de:2082]`，你有一张 10 GB 卡，将走向 40 GB。

---

## 1. `lspci`：权威识别

两个 SKU 在同一个人类可读名称下枚举，所以仅凭名称什么也看不出来。方括号里的厂商:设备配对才是关键。

```bash
lspci -nn | grep -i '10de:20c2\|10de:2082\|10de:20b0'
```

8 GB 卡上的预期输出：

```text
0a:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
```

10 GB 卡上的预期输出：

```text
81:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:2082] (rev a1)
```

注意类别：它是 `3D controller`，不是 `VGA compatible controller`，因为这张卡没有显示输出。`rev a1` 是 GA100 晶片修订，两者相同。

对于子系统 ID（这是第二条独立确认），要求详细输出：

```bash
sudo lspci -nn -vv -s 0a:00.0 | head -8
```

```text
0a:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
        Subsystem: NVIDIA Corporation GA100 [CMP 170HX] [10de:1585]
        Control: I/O- Mem+ BusMaster+ SpecCyc- MemWINV- VGAMon- FastB2B- DisINTx+
        Capabilities: [60] Power Management version 3
```

子系统 `10de:1585` 是 8 GB 卡，子系统 `10de:1557` 是 10 GB 卡。子系统 ID 是这张卡上唯一一个**可以**由 VBIOS 设置的标识，所以应把它当作佐证，而不是决定性证据。主设备 ID 已熔入晶片：`FUSE_DEVID_SW_OVR_DIS`（`0x00820584`）在每张被探测的卡上都读为 1，因此软件无法覆盖它，跳线电阻也不能改变它。

sysfs 在无需 root 的情况下给出同样的两个值：

```bash
BDF=0000:0a:00.0
cat /sys/bus/pci/devices/$BDF/device            # 0x20c2
cat /sys/bus/pci/devices/$BDF/subsystem_device  # 0x1585
```

---

## 2. `nvidia-smi`：报告的显存和料号

`nvidia-smi` 不会报告有用的产品名。两个 SKU 都显示为 **`NVIDIA Graphics Device`**，Linux 监控工具显示通用的 “NVIDIA display device” 条目属于正常行为。容量字段和料号才是有用的信息。

```bash
nvidia-smi --query-gpu=name,memory.total,pci.device_id,pci.sub_device_id,vbios_version \
           --format=csv
```

出厂状态的 8 GB 卡：

```text
name, memory.total [MiB], pci.device_id, pci.sub_device_id, vbios_version
NVIDIA Graphics Device, 8192 MiB, 0x20C210DE, 0x158510DE, 92.00.67.00.01
```

出厂状态的 10 GB 卡：

```text
NVIDIA Graphics Device, 10240 MiB, 0x208210DE, 0x155710DE, 92.00.66.00.02
```

成功解锁后，同一条命令在 8 GB 卡上报 **65536 MiB**，在 10 GB 卡上报 **40960 MiB**。输出中的其它内容都不变。

板卡和 GPU 料号可以通过完整查询获得：

```bash
nvidia-smi -q | grep -E 'Board Part Number|GPU Part Number|VBIOS Version|Bus Id'
```

```text
    VBIOS Version                         : 92.00.6D.00.0A
    Board Part Number                     : 900-11001-0108-000
    GPU Part Number                       : 20C2-105-A1
```

> [!CAUTION]
> **不匹配的 `nvidia-smi` 会使本页的所有读数失效**
>
> NVML 拒绝跨驱动版本通信，所以通过版本不匹配的 `nvidia-smi` 二进制读取到的 `memory.total` 毫无意义。有一轮持续数天的测量正是因此失效：使用 580.159.03 用户态，却搭配了另一个内核模块构建。如果 `nvidia-smi` 打印 “driver/library version mismatch”，先修复这个问题，再相信它报告的任何内容。参见[排障](../procedures/troubleshooting.md#version-mismatch)。

---

## 3. 物理标记

如果卡已从机器中取出，或散热器已拆下，有三处标记可读。

| 标记 | 8 GB 卡 | 10 GB 卡 |
|---|---|---|
| ASIC（晶片）标记 | `GA100-105F-A1` | `GA100-105A-A1` |
| 板卡料号 | `900-11001-0108-000` | `900-11001-0105-000` |
| GPU 料号 | `20C2-105-A1` | `2082-105-A1` |
| PCB 丝印，在金手指上方 | `180-11001-DAAA-B15`（也见过：`180-11001-DAAA-B35`、`180-11001-DAAA-045`） | 同一板卡家族 |
| 板卡 ID | 未记录 | `0x8100` |

两处丝印字符串属于同一个板卡家族；末尾字段是修订或变体代码，两者都曾在 USB 显微镜下被拍过照。170HX 封装图例也读作 `NVIDIA / B KR 2120A1 / TBSG42.M0W e1`。作为对比，与 170HX 一起拍过照的零售 Tesla A100 40 GB 晶片标记为 `GA100-883AA-A1`，所以中间那个 `-105x-` 字段才是表示 "CMP" 的部分。

> [!WARNING]
> **实验性：此处没有 10 GB 晶片标记的照片**
>
> 8 GB 卡上的 `GA100-105F-A1` 由一张拆解照片和 TechPowerUp 数据库确认，两个独立来源在变体字符串上一致。10 GB 卡的 `GA100-105A-A1` 来自文档化的规格表，在本语料库中没有任何地方独立拍照确认。读取晶片还需要拆掉散热器，所以这是本页最不实用的识别途径：用 `lspci`。

板卡和 GPU 料号是更有用的物理标识，因为 `nvidia-smi` 无需拆解就能报告它们，而且它们在两台主机上检查过的四张 8 GB 卡上完全一致。

---

## 4. VBIOS 版本，以及为什么它们决定不了任何事

```bash
nvidia-smi --query-gpu=vbios_version --format=csv,noheader
```

| VBIOS | SKU | 构建日期 | 备注 |
|---|---|---|---|
| `92.00.67.00.01` | 8 GB（`0x20C2`，子系统 `0x1585`） | 2021-05-14 | 出厂量产映像，364 MHz 显存字段，250 W |
| `92.00.6D.00.0A` | 8 GB | 2022-04-07 | 300 W "OC mining" 映像，432 MHz 显存字段，允许核心时钟偏移 |
| `92.00.6D.00.09` | 8 GB | 2021-11-01 | 带 300 W 上限但没有显存超频。不在 TechPowerUp 收集中。*（置信度：中高；一位研究者持有该文件。）* |
| `92.00.66.00.02` | 10 GB（`0x2082`，子系统 `0x1557`） | 2021-04-23 | 唯一一款 10 GB 映像 |

**VBIOS 版本对解锁能否生效毫无影响。** 这由一位核心研究者直接断言，并由一个四卡双主机对比独立佐证——其中两张卡在 `92.00.67.00.01` 上、两张在 `92.00.6D.00.0A` 上，产生了完全相同的解锁和 Gen2 结果。完整的映像清单参见[VBIOS](../hardware/vbios.md)，包括哪些流传的映像被错误标注、哪些绝不能刷写。

---

## 5. 寄存器级指纹

这些需要 BAR0 访问，用于确认有歧义的情况或交叉核对一次探测转储，而不是用于例行识别。

| 寄存器 | 8 GB（`0x20C2`） | 10 GB（`0x2082`） |
|---|---|---|
| `PMC_BOOT_0` | `0x170000a1` | `0x170000a1`（每个 GA100 都如此） |
| `FUSE_PCIE_DEVIDA` `0x008204d8` | `0x000020c2` | `0x00002082` |
| `FUSE_PCIE_DEVIDB` `0x0082056c` | **有争议**：2026-07-19 对一张 `0x20c2` 卡的探测读 `0x000020c2`；`DEVIDB = DEVIDA + 0x40` 规则预测 `0x00002102`（参见[板卡与变体](../hardware/board-and-variants.md)） | `0x000020c2` |
| `FUSE_SKU_ID` `0x00821060` | `0x80` | `0x68` |
| `OPT_GPC_DISABLE` `0x00820350` | **按晶片而异，不按 SKU 而异：不要用于识别** | **按晶片而异，不按 SKU 而异：不要用于识别** |
| `NV_PTOP_FS4` `0x0002241c` | `0x00000000` | `0x00000081` |
| 出厂 CFG1 `0x009a0204` | `0x02449000` | `0x02449000`（两者相同） |
| 出厂 LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| 出厂每-FBPA `CSTATUS_RAMAMOUNT` | `0x200`（512 MiB） | `0x200`（512 MiB） |
| HBM `MRS_2` `0x009a0334` | `0x00200019` | `0x002000cf` |
| HBM `MRS_WL_RL` `0x009a0338` | `0x003000eb` | `0x003000ea` |
| `FBPA_HBM_CFG0` `0x009a038c` | `0x000000a7` | `0x000000a7` |

注意**出厂 CFG1 在两个 SKU 上都是 `0x02449000`**，所以仅凭 CFG1 无法告诉你拥有哪张卡；LMR 可以。`NV_PTOP_FS4` 是最干净的单寄存器区分点，位 0 是 `GEN2_PCIE`，位 7 是 `GEN2_PCIE_SPEED`，这使得 8 GB 卡的 `0x00000000` 读数是更有意思的那一半。

> [!WARNING]
> **`OPT_GPC_DISABLE` 不是 SKU 指纹**
>
> GPC 熔丝裁剪掩码按晶片而异，不按 SKU 而异。在两个 SKU 的 170HX 卡上观察到的值包括 `0x13`、`0x15`、`0x23`、`0x25`、`0x45`、`0x85`、`0xa8` 和 `0xd0`，而它们全都仍然枚举出 70 个 SM。永远不要硬编码某个熔丝裁剪值，也不要据此推断 SKU。应改用 `FUSE_SKU_ID` `0x00821060`（8 GB 卡上为 `0x80`，10 GB 卡上为 `0x68`）。

由 SKU 衍生的结构性差异：

| 属性 | 8 GB 卡 | 10 GB 卡 |
|---|---|---|
| 总线宽度 | 4096-bit | 5120-bit |
| HBM 堆叠 | **未解问题。** 一张去盖的 8 GB 卡明显可见六堆；一份晶片照片资料声称其中两堆是虚设的。两种读数都与实测总线宽度相容，因此仅凭总线宽度无法定论 | 报告 5 堆 |
| 激活的 FBPA | 24 中的 16（8 个 FBP） | 24 中的 20（10 个 FBP） |
| 每-FBPA 容量，出厂 | 512 MiB（`_CSTATUS_RAMAMOUNT` = `0x200`，CFG1 层 `0x44`） | 512 MiB（相同） |
| 每-FBPA 容量，解锁后 | 4096 MiB（`0x1000`，层 `0x77`） | 2048 MiB（`0x800`，层 `0x66`） |
| 显存时钟 | **未解问题**，见下方说明框 | 1215 MHz，当前等于最大值，没有余量 |
| 解锁到 | **64 GB** | **40 GB** |

> [!NOTE]
> **未解问题：出厂 8 GB 显存时钟**
>
> 出厂状态的 8 GB 显存时钟尚未确定：1458 MHz（一次扫描和 TechPowerUp）、1728 MHz（`nvidia-smi -q` 的 Supported Clocks，标注为 "432 MHz × 4"）、1890 MHz（解锁后的 64 GB 在 300 W 下运行 `gpu_burn` 时由 `nvtop` 显示）。1215 MHz 是 10 GB 卡的数值，这一点很确定。一个看似合理的解释是：出厂状态为 1458、OC VBIOS 为 1728、使用 OC VBIOS 超频后为 1890；但这一解释尚未证实。另有观点认为 1728 MHz 来自 POST 时的 FWSEC devinit，而不是 OC VBIOS，因为八份转储 ROM 中都没有出现 Memory Clock Table。读取原始 FBPA PLL 就能解决这个问题。

具体哪些 FBP 被熔丝裁剪禁用因卡而异。一份 10 GB 转储读到 `FBP_DEFECTIVE` = `0x840`（FBP6、FBP11），与 A100 PCIe 40/80 GB 部件相同，但该读数对应的卡身份存在争议（一个来源将其归因于 8 GB 卡）；另一份 10 GB 探测则读到 `OPT_FBP_DISABLE` = `0x00000009`（FBP 0 和 3）。置信度中等，证据只有一份转储。10 GB 卡上的每次干净解锁触发都报告 `CSTATUS=20/24`。
参见[显存子系统](../hardware/memory-subsystem.md) 和[熔丝与 OTP](../hardware/fuses-and-otp.md)。

---

## 6. 第三个设备 ID：`10de:20b0`

`install.sh` 会 grep 三个 ID：

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

但驱动内门 `_kgspSec2PostblTimingEnabled()` 只接受 **`0x20C2` 和 `0x2082`**。因此 `20b0` 卡可以正常完成安装，却永远不会解锁。安装器会明确提示这一点，然后继续：

```text
! In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
! This card reports 0x20b0; install will continue, but unlock may not activate.
```

`0x20b0` 是 A100 SXM4 40 GB 的设备 ID，也出现在一块 A100 工程样品上（8192 MB、2048-bit、4096 个 CUDA 核心、Samsung 8Hi HBM2）。README 中较早的 “unlock is `0x20C2`-gated” 表述已经过时：自 “Unlock isn't gated anymore” 提交以来，`0x2082` 一直是同等重要的目标。

两条相关备注：

* 补丁 0001 和 0002 中每条 `SEC2_DEBUG` 打印都由这两个相同的设备 ID 控制，因此 `20b0` 卡上的出厂构建应该不会向 `dmesg` **打印任何内容**。有一份报告称 `20b0` 工程样品上出现了 SEC2_DEBUG 行，但原因尚未确定，最可能是使用了修改过的构建，或同一主机中还有第二张卡。
* `0x20BB` 是 Drive A100 / PG199 部件（出厂状态为 32768 MiB）。名为 `PG199` 的分支**完全没有添加任何内容**：其代码树与 `ecc` 分支逐字节相同，提交列表为空，任何地方都没有提到 PG199、`0x20BB` 或 A100D。它没有增加检测、不包含 A100D 支持，也没有改动 `lspci` grep 或驱动内门。不存在 PG199 解锁。

参见[排障](../procedures/troubleshooting.md#device-id-20b0)。

---

## 7. 安装时档位检测阶梯

`install.sh` 在 6 步中的第 3 步选择档位。要么你传 `--profile`，要么 `detect_card_profile()` 读取报告的显存并分档：

```bash
nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1
```

| 报告的 `memory.total` | 选定的档位 | 为何存在这个窗口 |
|---|---|---|
| `>= 60000` MiB | `8gb` | 在**已解锁的** 64 GB 卡上重装 |
| `35000`-`59999` MiB | `10gb` | 在已解锁的 40 GB 卡上重装 |
| `7680`-`8704` MiB | `8gb` | 出厂状态的 8 GB 卡（8192 MiB） |
| `9728`-`10752` MiB | `10gb` | 出厂状态的 10 GB 卡（10240 MiB） |
| 其它任何值 | **致命** | 打印 `unknown:<mib>`，然后 `Could not detect 8GB vs 10GB card. Re-run with --profile=8gb or --profile=10gb` |

然后横幅打印下面之一：

```text
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
==> Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)
```

> [!WARNING]
> **在混合 GPU 主机上自动检测不安全**
>
> `detect_card_profile()` 取 `nvidia-smi` 顺序里的**第一张 GPU**，它不一定是 `lspci` 找到的那张 CMP。至少有两人复现过这样的情况：一台同时装有 RTX 3080 10 GB 和 8 GB CMP 170HX 的主机从 3080 检测出了“10GB”；另有一份独立报告称 CMP 50HX 被误检为 10 GB 170HX。如果第一张 GPU 报告的容量落在四个窗口之外，例如是 24 GB 卡，安装会立即失败。
>
> 在任何含多张 NVIDIA 卡的主机上，始终显式传 `--profile`：
>
> ```bash
> sudo ./install.sh --profile=8gb     # 8 GB 物理卡  -> 64 GB
> sudo ./install.sh --profile=10gb    # 10 GB 物理卡 -> 40 GB
> ```

安装后，记录的档位在以下位置可读：

```bash
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile      # 8gb or 10gb
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry   # 64GB or 40GB
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
```

内核模块中没有任何代码会读取这三个文件。它们供人和 `verify.sh` 使用；后者将 `20c2 -> 8gb -> 65536 MiB` 与 `2082 -> 10gb -> 40960 MiB` 对应起来。注意，`verify.sh` 并**不**随 `master` 发布：它只存在于 `multiple-cards`、`Gen2`、`far` 和 `deced` 分支中，并从 `lspci` 推导这个映射；读取 `card_profile` 和 `unlock_geometry` 只是为了将它们打印出来。

---

## 8. 决策表

| 你观察到的 | 卡 | 档位 | 解锁后 `nvidia-smi` | 写入的 CFG1 / LMR |
|---|---|---|---|---|
| `[10de:20c2]`，子系统 `10de:1585`，8192 MiB | 8 GB CMP 170HX | `8gb` | **65536 MiB** | `0x02779000` / `0x0000020B` |
| `[10de:2082]`，子系统 `10de:1557`，10240 MiB | 10 GB CMP 170HX | `10gb` | **40960 MiB** | `0x02669000` / `0x0000028A` |
| `[10de:20c2]`，已报告 65536 MiB | 8 GB，已解锁 | `8gb` | 不变 | 每次启动重新应用 |
| `[10de:2082]`，已报告 40960 MiB | 10 GB，已解锁 | `10gb` | 不变 | 每次启动重新应用 |
| `[10de:20b0]` | A100 SXM4 40 GB 或 A100 工程样品 | 安装并警告 | **不变** | 无；驱动内门拒绝它 |
| `[10de:20bb]`，32768 MiB | Drive A100 / PG199 | 完全检测不到 | **不变** | 无；不存在 PG199 解锁 |
| 任何其它 `10de:` ID | 不是 170HX | 安装器退出 | n/a | n/a |
| `[10de:2082]` 被强制到 80 GB 几何布局 | 10 GB，过度配置 | 归档的 `80` 分支 | 报告 81920 MiB | `0x02779000` / `0x0000028A` |

> [!CAUTION]
> **80 GB 那一行不是受支持的选项**
>
> 归档的 `80` 分支把 10 GB 卡编程为报告 81920 MiB，但卡在超过约 40 GB 后就不可用：几分钟内便会挂起，出现 Xid 154 和老化测试错误。每个提到它的来源都将其标记为不稳定或否决，而且这与功耗上限无关。它实际编程的是一个三处不一致的组合（CFG1 `0x02779000` 配 LMR `0x0000028A` 和 80 GiB 的 `fb_length`），这本身很可能就是原因。参见[80 GB](../frontier/80gb.md)。

---

## 9. 如果你还是不确定

运行全部三项检查并对比。它们应当一致；如果不一致，以 `lspci` 设备 ID 为准，因为它熔在晶片里，VBIOS 或跳线都改不了。

```bash
# 1. 熔进晶片的设备 ID：权威
lspci -nn | grep -iE '10de:(20b0|20c2|2082)'

# 2. 子系统 ID 和料号：佐证（子系统可由 VBIOS 设置）
nvidia-smi --query-gpu=pci.sub_device_id,vbios_version --format=csv,noheader
nvidia-smi -q | grep -E 'Board Part Number|GPU Part Number'

# 3. 报告的容量：安装器自动检测将看到的
nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits
```

一张能在未打补丁的出厂驱动上枚举并运行、报告 `NVIDIA Graphics Device` 和计算能力 8.0 的卡，无论它看起来多脏，都是一张健康的 170HX。退役矿卡带着厚重的灰尘、生锈的挡板和散热器里的盐渍到来，而外观状况从未预测过解锁失败：一张肉眼可见脏污的卡第一次尝试就干净地解锁到 64 GB。

---

## 相关页面

* [这是什么卡](what-is-this-card.md)：方向性总览
* [风险](risks.md)：开始前请阅读
* [快速开始](quick-start.md) 和[安装](../procedures/install.md)
* [验证](../procedures/verify.md)：确认解锁确实生效
* [多卡](../procedures/multi-gpu.md)：为什么安装器里的 `head -1` 在矿机上很重要
* [板卡与变体](../hardware/board-and-variants.md)：物理板卡的细节
* [VBIOS](../hardware/vbios.md)：每一款已知映像及其改动
* [显存几何布局](../unlock/memory-geometry.md)：CFG1 和 LMR 实际做什么
* [熔丝与 OTP](../hardware/fuses-and-otp.md)：跨变体熔丝表
* [术语表](glossary.md)
