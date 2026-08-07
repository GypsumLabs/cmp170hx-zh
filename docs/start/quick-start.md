# 快速上手

**本页内容：** 使用当前发布版 `cmpunlocker` 的 `master` 分支，介绍从出厂状态的 CMP 170HX 到完成解锁的最短正确路径。文中给出每一步的精确命令和预期输出，以及一张根据失败情况指向对应页面的路由表。这里没有任何实验性内容：下面的一切都包含在当前发布树中。

整个流程是：安装 nvidia-open `610.43.03`（或 `610.43.02`），运行 `sudo ./install.sh`，冷启动，然后检查 `nvidia-smi`。8 GB 卡最终会得到 **65536 MiB**，10 GB 卡最终会得到 **40960 MiB**。SM 的完整计算吞吐也会同时解锁。改动仅涉及寄存器：不会写入闪存，运行 `sudo ./remove.sh --yes` 即可将显卡恢复到出厂状态。

> [!WARNING]
> **快速上手不会带来什么**
>
> - **没有 PCIe Gen2。** 当前发布的 `master` 只含补丁 `0001` 到 `0006`。Gen2 补丁（`0007-pcie-gen2.patch`、`0008-pcie-gen2-probe-retrain.patch`）在未发布的实验分支上。你将停留在 Gen1、2.5 GT/s。参见[PCIe Gen2](../unlock/pcie-gen2.md)。
> - **没有 x16 链路位宽。** 卡出厂时通道 4-15 的交流耦合电容已被移除，因此只能训练为 x4。恢复 x16 需要手工焊接 24 颗 0402 220 nF X7R 电容。这在物理上与链路速率是彼此独立的，也不会改变 PCIe 代数。参见[物理改装](../operations/physical-mods.md)。
> - **10 GB 卡上没有 80 GB。** 那个配置被构建、测试，并作为不稳定而放弃。参见[80 GB 层](../frontier/80gb.md)。
> - **没有 ECC、没有 NVLink、没有点对点。** ECC 和 NVLink 通过 OTP 熔丝禁用，没有已知的恢复开关。点对点传输同样不可用，但尚未确定这是由熔丝禁用，还是由驱动门控。参见[点对点](../frontier/p2p.md)。
> - **仅限 Linux。** 解锁依赖 Linux 的 GSP 启动路径。Windows 使用的是完全不同的驱动模型。
>
> 在 Gen1 x4 下，预期主机到设备带宽约为 **0.85 GB/s**（clpeak 实测）。跳过上面两个硬件/分支项目，实际付出的主要代价就是这一点。

---

## 前置条件清单

| 要求 | 检查 | 备注 |
|---|---|---|
| x86-64 Linux，root | `id -u` 在 `sudo` 下返回 `0` | `install.sh` 以 `Run as root: sudo ./install.sh` 终止 |
| 一块 CMP 170HX | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082'` | `20c2` = 8 GB SKU，`2082` = 10 GB SKU |
| **nvidia-open 610.43.03 或 610.43.02** | `cat /proc/driver/nvidia/version` | 精确字符串匹配。其它任何版本都会中止安装 |
| 内核头文件 | `ls -d /lib/modules/$(uname -r)/build` | 软件包 `linux-headers-$(uname -r)` 或 `kernel-devel` |
| 安全启动 **已禁用** | `mokutil --sb-state` | 补丁模块未签名 |
| 网络访问 | 仅首次安装 | `build.sh` 下载匹配的出厂版 `open-gpu-kernel-modules` tarball |
| `python3`、`curl`、`patch`、`make`、C 工具链 | `command -v python3 curl patch make gcc` | `master` 上不用 PyYAML，发布脚本里也没有显式 GCC 版本检查 |
| 一个 initramfs 工具 | `update-initramfs`、`dracut` 或 `mkinitcpio` | 没有它构建会警告，启动时可能会优先加载出厂模块 |
| 供电：1 × EPS 8-pin | 额定 300 W 的接口 | 需要 2 × PCIe-to-EPS 转接线。参见[供电与 PSU](../operations/power-and-psu.md) |
| 散热：强制风 | 被动散热片，卡上无风扇 | 参见[散热](../operations/cooling.md) |
| 一张具备显示输出能力的 GPU，或能无头 POST 的板卡 | 170HX 没有视频输出 | 据报告，至少有一块主板在只安装 170HX 时拒绝 POST |

> [!NOTE]
> **卡不解锁也能用**
>
> 出厂状态的 170HX 使用普通发行版驱动即可正常工作（已确认 `nvidia-driver-570` 加 Ubuntu 24.04 上的 CUDA 12.8 可以运行）。`nvidia-smi` 会将它命名为 `NVIDIA Graphics Device`，计算能力显示为 8.0，因为驱动的 PCI ID 表中没有 `0x20C2` 对应的产品名称。在动任何东西之前，可以把这一点作为预检合理性检查。显卡能被驱动正常使用，与显卡能否解锁是两回事。

---

## 第 0 步：确认你拥有哪张卡

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'
nvidia-smi --query-gpu=memory.total,driver_version --format=csv
```

| PCI ID | 物理容量 | 解锁到 | CFG1 `0x009a0204` | LMR `0x00100ce0` |
|---|---|---|---|---|
| `10de:20c2` | 8 GB | **64 GB**（65536 MiB） | `0x02779000` | `0x0000020B` |
| `10de:2082` | 10 GB | **40 GB**（40960 MiB） | `0x02669000` | `0x0000028A` |
| `10de:20b0` | 因卡而异 | **不解锁** | n/a | n/a |

`install.sh` 能检测全部三个 ID，但驱动内的门控函数 `_kgspSec2PostblTimingEnabled()` 只接受 `0x20C2` 和 `0x2082`。`20b0` 卡可以正常完成安装，但之后永远不会解锁；安装器会警告 `This card reports 0x20b0; install will continue, but unlock may not activate.` 更多细节：[识别你的卡](identify-your-card.md)。

---

## 第 1 步：安装 nvidia-open 610.43.0x

使用你的发行版提供的方式，或 NVIDIA `.run` 安装器均可，只要最终得到的开源内核模块版本正好是 `610.43.03` 或 `610.43.02`。继续前先验证：

```bash
cat /proc/driver/nvidia/version
# NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  610.43.03  Release Build ...
nvidia-smi
```

`610.43.03` 是默认构建目标（`driver/VERSION` 的第一行）。

> [!NOTE]
> **未解问题**
>
> `610.43.02` 和 `610.43.03` 哪个更可靠，这个问题被反复提出，却始终没有答案。两个版本都有人成功解锁。`610.43.03` 只是列表中的第一个。

可以考虑将驱动包固定在 610 系列，这样发行版升级就不会悄悄把你带到不受支持的版本。参见[驱动版本](../procedures/driver-versions.md)。

## 第 2 步：获取工具并运行

```bash
git clone https://github.com/amoghmunikote/cmpunlocker
cd cmpunlocker
sudo ./install.sh
```

只有在自动检测错误或 `nvidia-smi` 不可用时，才需要强制指定配置档位：

```bash
sudo ./install.sh --profile=8gb     # 8 GB 卡  -> 64 GB 几何布局
sudo ./install.sh --profile=10gb    # 10 GB 卡 -> 40 GB 几何布局
```

自动检测会读取 `nvidia-smi --query-gpu=memory.total`，并按以下范围选择配置档位：
`>= 60000 MiB -> 8gb`（已解锁的卡）、`35000-59999 -> 10gb`、`7680-8704 -> 8gb`、
`9728-10752 -> 10gb`。其它任何值都以 `Could not detect 8GB vs 10GB card` 中止。

**预期输出**：共六个编号步骤，所有输出都会通过 tee 写入 `logs/install_YYYYmmdd_HHMMSS.log`：

```text
Step 1/6: Verifying root privileges
✓ Running as root
Step 2/6: Detecting CMP 170HX GPU
✓ GPU detected: 0000:0b:00.0 (10de:20c2)
Step 3/6: Selecting card memory profile
✓ Detected stock/reported memory 8192 MiB → profile 8gb
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
Step 4/6: Verifying nvidia-open (610.43.03,610.43.02)
✓ NVIDIA driver 610.43.03 is supported
✓ Kernel headers present for 6.8.0-136-generic
Step 5/6: Building and installing patched modules
...
Step 6/6: Done
Profile: 8gb → expect ~65536 MiB after unlock
```

传入的配置档位仅是元数据。在当前发布版的 `master` 上，两种几何布局都已编译进打过补丁的 `kernel_gsp.c`，并在 GSP 启动时根据当前 PCI 设备 ID 选择。因此，即使配置档位检测错误，也只会写入错误的标签，不会生成错误的几何布局。

下面两行构建日志看起来吓人，但并不表示有问题：
`Skipping BTF generation for .../nvidia*.ko due to unavailability of vmlinux`（内核调试元数据，无关紧要），和 `[drm] No compatible format found`（卡没有显示输出）。

## 第 3 步：冷启动

`build.sh` 会尝试热重载模块。如果成功，可以跳过这一步；但冷启动是可靠路径，也是安装器推荐的做法。

```bash
sudo shutdown -h now
```

然后在 PSU 处断电或拔掉电源线，等待 **60 秒**，让电容放电并清除 WPR2，再开机。热重启会让 WPR2 保持启用状态，两者并不等价。

## 第 4 步：验证

```bash
nvidia-smi
# 8 GB 卡：  ~65536 MiB
# 10 GB 卡： ~40960 MiB

sudo dmesg | grep SEC2_DEBUG
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile   # 8gb or 10gb
```

一条健康的 `SEC2_DEBUG` 日志轨迹会依次打印：WPR 元数据转储、`saved WPR2 lo=... hi=...`、四条
`PLM[n] ...` 行、一行 `PLMs:` 汇总、`POST-WRITE` 行、`WPR meta updated`
行、`normal BooterLoad status=0x0`、一条最终的 `POST-BooterLoad verify`，然后是静态信息的前后对比。
PLM 行形状如下（一条逐字存档的行，其余遵循相同格式）：

```text
SEC2_DEBUG: PLM[3] FEAT(0x823804) attempt=0 status=0xffff reg=0xffffffff
```

预期回读：

| 行 | 寄存器 | 预期值 |
|---|---|---|
| `PLM[0] WPR_CFG` | `0x001fa7cc` | `0xfffff0ff`（**不是** `0xffffffff`） |
| `PLM[1] FBPA` | `0x009a0148` | `0xffffffff` |
| `PLM[2] WPR` | `0x001fa7c4` | `0xffffffff` |
| `PLM[3] FEAT` | `0x00823804` | `0xffffffff` |
| `POST-WRITE SS0` | `0x0082381c` | `0x88888888` |
| `POST-WRITE SS1` | `0x00823820` | `0x00000008` |
| `POST-WRITE CFG1` | `0x009a0204` | `0x02779000`（8 GB）/ `0x02669000`（10 GB） |
| `POST-WRITE LMR` | `0x00100ce0` | `0x0000020B`（8 GB）/ `0x0000028A`（10 GB） |

> [!NOTE]
> **忽略这三类看起来吓人的日志行**
>
> - 每条 PLM 行上的 `status=0xffff` 是**正常的**。载荷 Booter 运行本来就该被拒绝；成败由寄存器回读判断，绝不看状态。来自 `s_executeBooterUcode_TU102` 的 `0x31` 是同一个道理。
> - `SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload`
>   属于正常路径。那个文件只是开发调试用的覆盖接口。
> - 第三方文档声称 "all PLMs must show `0xffffffff`" 是错的。`WPR_CFG` 设计上就是 `0xfffff0ff`。
>
> **必须**读零的那一行是 `SEC2_DEBUG: normal BooterLoad status=0x0`。

算力解锁应通过吞吐确认，而不是通过某个时钟字段确认。解锁卡上持续的 SM 时钟为 1410 MHz（`nvidia-smi -pl 300` 下为 1470 MHz）。`nvidia-smi --query-gpu=clocks.max.sm` 报告 1935 MHz，但这是一个置信度较低的报告最大值字段，并非可达到的时钟：VBIOS 表中的最大值是 1695 MHz。请改用真实基准测试。参见[性能](../operations/performance.md)。

---

## 如果失败，去这里

| 症状或精确消息 | 可能原因 | 去往 |
|---|---|---|
| `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)` | 卡未枚举、板卡未能无头 POST、安装不到位或供电问题 | [识别你的卡](identify-your-card.md)、[排障](../procedures/troubleshooting.md) |
| `Installed driver is X, but cmpunlocker requires one of: 610.43.03,610.43.02.` | 不支持的驱动版本 | [驱动版本](../procedures/driver-versions.md) |
| `Secure Boot is enabled. Disable it before installing unsigned patched modules.` | 安全启动开启 | [安装](../procedures/install.md) |
| `Kernel headers missing for <kver>` | 没有 `linux-headers-$(uname -r)` | [安装](../procedures/install.md) |
| `Could not detect 8GB vs 10GB card` | `nvidia-smi` 不存在或 `memory.total` 超出范围 | 用 `--profile=8gb` 或 `--profile=10gb` 重跑 |
| 构建在下载期间停止 | 无网络，或 tarball 标签无法访问 | [安装](../procedures/install.md) |
| `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win` | depmod 解析或 initramfs 仍持有出厂模块 | [排障](../procedures/troubleshooting.md) |
| `Loaded nvidia srcversion (X) != patched (Y)` | 热重载后出厂模块仍驻留 | 冷启动，然后[排障](../procedures/troubleshooting.md) |
| 重启后 `nvidia-smi` 仍显示 8192 / 10240 MiB | PLM 打开未生效，或运行的是出厂模块 | 完整断电冷循环，然后[排障](../procedures/troubleshooting.md) |
| **完全没有** `SEC2_DEBUG` 行 | 补丁模块从未运行 | [排障](../procedures/troubleshooting.md)、[验证](../procedures/verify.md) |
| `WPR2 already up` / `RmInitAdapter failed! (0x62:0x40:2028)` / `No devices were found` | GSP 启动留下了已编程的 WPR2 | [恢复](../procedures/recovery.md) |
| Xid 119，`Timeout after 60s ... Expected function 4097 (GSP_INIT_DONE)` | GSP 从未到达 RM 初始化 | [恢复](../procedures/recovery.md) |
| `nvidia-smi` 报告 "driver/library version mismatch" | 用户态与已加载模块不匹配 | [排障](../procedures/troubleshooting.md) |
| 多卡机箱里没有卡解锁 | 同一条 `updates` 搜索路径下同时存在出厂版和补丁版 `nvidia.ko`，depmod 会任意加载其中一个 | [多卡](../procedures/multi-gpu.md) |
| Xid 31，`FAULT_INFO_TYPE_REGION_VIOLATION`，卡在重启前不可用 | 分配超出了窗口顶部的可用范围 | [LLM 推理](../operations/llm-inference.md)、[排障](../procedures/troubleshooting.md) |
| 链路仍报告 Gen1 x4 | `master` 上符合预期：那里不带任何 Gen2 补丁 | [PCIe Gen2](../unlock/pcie-gen2.md) |

提交支持工单前，请收集 `sudo dmesg | grep SEC2_DEBUG` 和最新的 `logs/install_*.log`。响应可能较慢，并且由单人维护者处理。

---

## 回滚

```bash
sudo ./remove.sh --yes
```

卸载器是 `remove.sh`，需要传入 `--yes` 或 `-y`。**不存在 `uninstall.sh`**，尽管某个分支的 `INSTALLATION.md` 这样写。它会删除每个内核下的 `/lib/modules/*/updates/cmpunlocker/`，重新运行 `depmod`，重建 initramfs，清除旧版 systemd 残留和 `/opt/cmpunlocker` 残留，并重新加载出厂模块。如果 GPU 没有干净地恢复，就重启系统。一位测试者报告说，两张卡之后都恢复了正常挖矿，这也是将该改动称为非破坏性的依据。至今没有确认过永久变砖的情况。完整细节：[卸载](../procedures/uninstall.md)。

在分支之间切换时，维护者建议先卸载再安装。这是指导而非硬性规则：一位测试者遇到的问题通过先卸载得到修复，至少另有两位测试者则成功地直接在已有安装上继续安装。

---

## 接下来去哪里

- [正确验证](../procedures/verify.md)，包括确认解锁的 VRAM 是真实显存，而不是地址别名折叠。
- 在无法更换的卡上运行之前，先看[风险](risks.md)。
- 阅读[显存几何布局](../unlock/memory-geometry.md)和[算力节流](../unlock/compute-throttle.md)，了解那四次寄存器写入实际做了什么。
- [驱动补丁](../unlock/driver-patches.md)，逐个 hunk 通读全部六个补丁。
- [术语表](glossary.md)，了解 PLM、WPR2、SEC2、GSP-RM、FBPA、LMR 和 CFG1。
