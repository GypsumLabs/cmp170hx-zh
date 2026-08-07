# 安装解锁器

**本页内容。** 本页介绍当前发布版 `cmpunlocker` 驱动补丁在 CMP 170HX 上完整且受支持的安装流程：开始前必须满足的条件、准确的命令、`install.sh` 和 `driver/build.sh` 各步骤的作用、卡片档位的选择方式（以及需要强制指定档位的情况）、冷重启的重要性，以及一次正确的安装在屏幕输出和 `dmesg` 中应呈现的结果。

简要流程：安装 nvidia-open **610.43.03** 或 **610.43.02**，禁用安全启动，安装内核头文件，然后从仓库克隆目录运行 `sudo ./install.sh`，最后执行冷启动。脚本会针对你的驱动版本下载 NVIDIA 原厂的 `open-gpu-kernel-modules` tarball，应用六个补丁，构建五个内核模块，并将它们安装到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。整个过程不会向显卡的 VBIOS 写入任何内容，也不会修改磁盘上的固件文件。8 GB 卡（`10de:20c2`）解锁后会报告 **65536 MiB**，10 GB 卡（`10de:2082`）解锁后会报告 **40960 MiB**。

解锁机制本身见[解锁如何工作](../unlock/how-it-works.md)，补丁系列见[驱动补丁](../unlock/driver-patches.md)。本页只介绍实际操作流程。

---

## 前置条件

| 要求 | 详情 | 强制检查位置 |
|---|---|---|
| 操作系统 | Linux，x86-64。此解锁**没有 Windows 安装路径**。 | 不检查；补丁只适用于 Linux 的 GSP 引导路径 |
| 权限 | root（`sudo ./install.sh`） | `install.sh` 第 1 步、`build.sh` |
| 显卡 | `10de:20c2`（8 GB）或 `10de:2082`（10 GB）。`10de:20b0` 会被检测到，但**不会**被解锁。 | `install.sh` 第 2 步（`lspci` grep）以及驱动内的设备门控 |
| 驱动 | nvidia-**open** `610.43.03`（默认）或 `610.43.02`，必须精确匹配字符串 | `install.sh` 第 4 步和 `driver/build.sh`，两者都以 `driver/VERSION` 为准 |
| 内核头文件 | `/lib/modules/$(uname -r)/build` 必须存在 | `install.sh` 第 4 步和 `build.sh` |
| 安全启动 | 必须禁用；补丁模块未签名 | `install.sh` 第 4 步，通过 `mokutil --sb-state` 检查 |
| 网络 | 首次安装时必须能访问 `github.com`，以下载源码 tarball | `build.sh` 中的 `curl -L --fail` |
| 工具链 | `python3`、`patch`、`make`、`curl`，以及可正常工作的内核构建环境 | `build.sh` 只检查 `python3` |

实际使用时需要特别注意：

- **必须使用 nvidia-open，不能使用专有驱动。** 封闭驱动采用不同的引导路径，无法按相同方式打补丁。显卡在原厂驱动下可以正常*运行*（有测试者在 Ubuntu 24.04 上开箱使用 `nvidia-driver-570` 和 CUDA 12.8，另有报告称 Ubuntu 22.04 上的 `nvidia-driver-535-server` 也可以使用），但“驱动能正常运行”和“显卡已解锁”是两回事。见[驱动版本](driver-versions.md)。
- **安全启动检查是有条件的。** 只有在 `/sys/firmware/efi` 存在**且** `mokutil` 位于 `PATH` 中时，脚本才会执行检查。在非 EFI 机器上，或在未安装 `mokutil` 的机器上，检查会静默跳过；最终仍可能得到被内核拒绝加载的模块。`dmesg` 中的症状是 `nvidia: module verification failed: signature and/or required key missing - tainting kernel`。
- **不需要 PyYAML，也不检查 GCC 版本。** `build.sh` 使用带标准库的普通 `python3`，不会测试编译器版本。网上流传的“需要带 PyYAML 的 python3 / gcc 13+”来自第三方 `unlock-cmp-170hx` 指南仓库，而不是这些脚本；六个 cmpunlocker 分支中还残留着一份锁定 `pyyaml>=5.1` 的 `requirements.txt`，但没有任何分支脚本导入 `yaml`。泄露的预构建包 README 只要求 root 权限和内核头文件。已有报告称，在 Ubuntu 26.04 LTS、内核 7.0.0-27-generic 上可以成功构建（使用 `Gen2` 分支，且多次重启后仍正常）。
- **请在一台即使损坏也能接受的机器上操作。** 裸机上反复尝试驱动补丁的破坏性很高；一位开发者报告说，每次 `nvidia.ko` 部署失败后都需要重装操作系统。见[风险](../start/risks.md)。

> [!CAUTION]
> **固件打补丁时代留下的状态**
>
> 如果这台机器曾经运行过 `cmpunlocker` 的**固件打补丁前身**，请在安装驱动补丁**之前**将 `gsp_tu10x.bin` 恢复为原厂版本：
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp "$GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak" "$GSP_DIR/gsp_tu10x.bin"
> ```
>
> 驱动补丁会在启动期间把固件签名保存为“stock”。如果磁盘上的固件仍是打过补丁的版本，驱动保存的就会是利用载荷；随后，干净的 GSP-RM 引导会 DMA 错误的 ROP 链。之后应检查是否出现成功日志 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

---

## 安装命令

```bash
git clone https://github.com/amoghmunikote/cmpunlocker
cd cmpunlocker
sudo ./install.sh
```

自动检测结果不正确或 `nvidia-smi` 不可用时，可以强制指定档位：

```bash
sudo ./install.sh --profile=8gb     # 8 GB physical card  -> 64 GB geometry
sudo ./install.sh --profile=10gb    # 10 GB physical card -> 40 GB geometry
sudo ./install.sh --help
```

只接受这三类参数形式（`--profile=8gb|8GB|10gb|10GB`、`-h`、`--help`）。传入任何其他参数都会以状态码 1 退出，并输出 `Unknown argument: <arg>`。

所有输出都会通过 tee 写入检出目录中的 `logs/install_<YYYYmmdd_HHMMSS>.log`，因此必须从可写目录运行。

---

## `install.sh` 的逐步行为

脚本在 `set -euo pipefail` 下执行六个编号步骤。

### 第 1/6 步：检查 root 权限

如果 `[[ "${EUID}" -eq 0 ]]` 不成立，脚本就会失败，并输出 `Run as root: sudo ./install.sh`。

### 第 2/6 步：检测 GPU

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

没有匹配结果会直接失败，并输出 `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)`。注意这里的 `head -1`：**master 是单卡安装器**。它只记录第一条匹配结果中的 BDF（总线、设备、功能地址）和设备 ID。机架中有多张卡时，请参见[多卡](multi-gpu.md)。

如果检测到的设备 ID 既不是 `20c2` 也不是 `2082`，脚本会发出警告，但**继续安装**：

```text
! In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
! This card reports 0x20b0; install will continue, but unlock may not activate.
```

这个警告与实际行为一致。驱动内的门控函数 `_kgspSec2PostblTimingEnabled()` 只接受 `0x20C2` 和 `0x2082`，因此 `20b0` 卡会获得完整的补丁模块，但解锁路径永远不会针对它触发。README 中较早的“unlock is `0x20C2`-gated”说法已经过时；从提交 `0f9aca5`“Unlock isn't gated anymore”开始，`0x2082` 就一直是正式支持的目标。

### 第 3/6 步：选择卡片档位

脚本要么使用 `--profile` 覆盖值，要么调用 `detect_card_profile()`。后者读取 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1`，并按以下四个范围进行映射：

| 报告的 `memory.total` | 选定的档位 | 设置该范围的原因 |
|---|---|---|
| `>= 60000` MiB | `8gb` | 在**已经解锁**为 64 GB 的卡上重新安装 |
| `35000`-`59999` MiB | `10gb` | 在已经解锁为 40 GB 的卡上重新安装 |
| `7680`-`8704` MiB | `8gb` | 原厂 8 GB 卡（8192 MiB） |
| `9728`-`10752` MiB | `10gb` | 原厂 10 GB 卡（10240 MiB） |
| 其他任何值 | 直接失败 | 输出 `unknown:<mib>`，然后输出 `Could not detect 8GB vs 10GB card. Re-run with --profile=8gb or --profile=10gb` |

随后，横幅会输出以下两行中的一行：

```text
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
==> Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)
```

> [!WARNING]
> **混合 GPU 主机不适合自动检测**
>
> `detect_card_profile()` 取的是 `nvidia-smi` 顺序中的**第一张 GPU**，而这张卡不一定就是 `lspci` 检测到的 CMP。一台同时安装 RTX 3080 10 GB 和 8 GB CMP 170HX 的主机，至少有两人复现了从 3080 误检测出“10GB”的情况。另有报告称，其他 CMP SKU（50HX）也会被误判为 10 GB 170HX。在当前 `master` 中，后果只是元数据错误；但在包含任何其他 NVIDIA 显卡的主机上，稳妥做法是**始终显式传入 `--profile`**。如果第一张 GPU 报告的容量不在四个范围内（例如 24 GB 卡），安装会直接失败。

### 第 4/6 步：检查安全启动、驱动版本和头文件

- 安全启动：如果 `/sys/firmware/efi` 存在、`mokutil` 存在，并且 `mokutil --sb-state` 匹配 `SecureBoot enabled`，脚本会失败并输出 `Secure Boot is enabled. Disable it before installing unsigned patched modules.`
- 驱动版本检测顺序：
  1. `/proc/driver/nvidia/version`
  2. `nvidia-smi --query-gpu=driver_version`
  3. 探测 `/lib/firmware/nvidia/<supported-version>/` 目录
  4. `/lib/firmware/nvidia/` 下按排序结果最高的目录
- 检测出的字符串必须与 `driver/VERSION` 中的一行完全匹配，否则输出：`Installed driver is <detected>, but cmpunlocker requires one of: 610.43.03,610.43.02.`
- `/lib/modules/$(uname -r)/build` 必须存在，否则输出 `Kernel headers missing for <kver>. Install linux-headers-<kver> or kernel-devel.`

### 第 5/6 步：构建并安装

`install.sh` 会为 `driver/build.sh` 添加执行权限，然后以 exec 方式运行它，并在环境中设置 `CMPUNLOCKER_DRIVER_VERSION` 和 `CMPUNLOCKER_CARD_PROFILE`。详见下一节。

### 第 6/6 步：输出后续步骤横幅

脚本会输出预计的解锁后容量，然后列出四项编号的后续步骤：提醒执行冷重启（`sudo shutdown -h now`），以及三个验证命令（`nvidia-smi`、`sudo dmesg | grep SEC2_DEBUG` 和 `nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader`）；最后输出安装日志路径。

---

## `driver/build.sh` 的行为

1. **重新验证** root 权限、版本是否与 `driver/VERSION` 一致、补丁目录、内核头文件以及 `python3` 是否存在。
2. **下载** `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`。它使用 `curl -L --fail` 将文件下载到 `driver/.build/`（可通过 `CMPUNLOCKER_BUILD_DIR` 覆盖缓存位置）。如果缓存中已有 tarball，就会复用缓存。仓库中不包含任何 NVIDIA 源代码。
3. **每次都进行干净解压**：先执行 `rm -rf "${SRC_DIR}"`，再解压 tarball，避免上一次失败的构建污染本次构建。
4. **按字典序应用所有 `driver/patches/*.patch`**：使用 `patch -p1` 逐个应用。当前发布版补丁系列包含六个文件，总大小为 37,415 字节：

   | 补丁 | 字节数 | 作用 |
   |---|---|---|
   | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 | 完整的解锁逻辑：载荷、[PLM](../unlock/privilege-level-masks.md) 循环、SS0/SS1/CFG1/LMR 写入以及 `fb_length` 重写 |
   | `0002-booter-verify.patch` | 3,988 | 将四个引导断言改为软失败，并输出 Booter Load 后的回读值 |
   | `0003-late-pma.patch` | 10,580 | 将 8 GiB 以上的新显存注册到物理内存分配器 |
   | `0004-bar0-pramin-clamp.patch` | 861 | 将 BAR0/PRAMIN 窗口限制在原厂 8192 MB 偏移量 |
   | `0005-ce-scrub-workarounds.patch` | 1,642 | 强制复制引擎清理器使用物理模式 |
   | `0006-persistent-sw-state.patch` | 603 | 设置 `NV_FLAG_PERSISTENT_SW_STATE`，替代旧的看门狗守护进程 |

   由于这个循环是在 `set -euo pipefail` 下执行的普通 glob，将名为 `0007-*.patch` 的第三方 diff 放入该目录即可自然叠加；任何 hunk 应用失败都会中止构建。P2P 补丁就是以这种方式叠加的（见[P2P](../frontier/p2p.md)）。
5. **执行档位处理。** 内嵌的 Python 脚本会检查打过补丁的 `kernel_gsp.c` 是否已经包含全部六个标记（`SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID`、`..._10GB_PCI_DEVICE_ID`、`0x02779000U`、`0x02669000U`、`0x0000001000000000ULL`、`0x0000000A00000000ULL`）。在 `master` 上六个标记都存在，因此脚本会输出 `runtime device-id geometry (profile metadata=64GB)`，然后不修改任何内容直接退出。下面的正则替换分支只是针对单 SKU 补丁保留的旧回退逻辑，当前不会执行。
6. **写入三个元数据文件**到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：`driver_version`、`card_profile`（`8gb` / `10gb`）和 `unlock_geometry`（`64GB` / `40GB`）。**内核模块不会读取其中任何一个文件。** 这些文件供人和 `verify.sh` 使用。补丁内核在启动时唯一会读取的文件是可选的 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。
7. **构建模块**：执行 `rm -rf src/nvidia/_out src/nvidia-modeset/_out kernel-open/conftest`、`make clean`，然后执行 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`。已有报告称，在现代 CPU 上构建需要**2 到 5 分钟**。这个范围来自两份书面资料（泄露的预构建包 README 写的是“约 2-5 分钟”，一份流传的 40 GB 解锁指南写的是“现代 CPU 上约 5 分钟”）；没有人提供过计时测量结果。
8. **安装五个模块**：以 `0644` 权限安装到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko`、`nvidia-peermem.ko`（由 `find` 找到，并排除 `*/conftest/*`）。只有 `nvidia.ko` 包含解锁代码；另外四个是原厂模块的重建版本，用于保持整个模块集合的版本一致。
9. **执行 `depmod -a "${KVER}"`。** 模块优先级遵循普通的 depmod 排序：`updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`，因此不需要使用 `dpkg-divert`。
10. **重建 initramfs**：按顺序尝试使用 `update-initramfs -u -k`、`dracut --force --kver`、`mkinitcpio -P` 中第一个可用的工具；如果都不可用，则警告 `No initramfs tool found, rebuild manually before rebooting`。master 的 `build.sh` 在这里没有注释，但分支副本（`memory`、`ecc`、`housekeeping`、`PG199`）逐字解释了原因：NVIDIA 经常从 initramfs 加载，如果其中只打包了 `updates/dkms`，那么即使 depmod 更偏好 `updates/cmpunlocker`，启动时仍会优先加载原厂模块。这是一条“已安装但显存仍显示原厂容量”的合理可能路径，但它只是脚本作者的推理，并非已经诊断确认的实际故障：聊天语料中任何地方都没有出现 *initramfs*、*initrd*、*dracut* 或 *mkinitcpio* 这些词。只有完成 initramfs 步骤后，`build.sh` 才会执行经验检查，确认补丁模块确实具有优先级：`modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'`；如果结果不在 `updates/cmpunlocker/` 下，则警告 `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`。
11. **尝试热重载**：停止 `nvidia-persistenced` 和 `nvidia-fabricmanager`，对 `nvidia_drm`、`nvidia_uvm`、`nvidia_modeset`、`nvidia` 执行 `modprobe -r`，然后重新加载模块。接着将 `/sys/module/nvidia/srcversion` 与 `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko` 进行比较；如果不一致，则警告 `Loaded nvidia srcversion (X) != patched (Y)`，并清除脚本自己的成功标志。

> [!WARNING]
> **下载的 tarball 没有完整性检查**
>
> `build.sh` 使用 `curl -L --fail` 获取 NVIDIA tag tarball，并在没有任何校验和或签名验证的情况下缓存它；代码树中也没有其他完整性检查。在不可信网络环境中，请在首次构建前自行验证缓存的 tarball。

---

## 冷重启

热重启不够，一般情况下热重载也不够。整个项目（包括泄露的预构建发行包自带的 README）给出的要求都是执行**冷**重启：完全断电，然后重新通电。

```bash
sudo shutdown -h now
# then power on
```

原因如下，按最容易导致问题的顺序排列：

1. 解锁代码在补丁模块的 GSP 引导过程中运行。如果热重载失败，或 initramfs 中仍保留原厂模块，导致当前运行的 `nvidia.ko` 仍是原厂版本，解锁代码就永远不会执行。
2. 正在使用的模块（X11、显示管理器、persistenced 守护进程或 CUDA 进程）会阻止 `modprobe -r`；此时 `build.sh` 会输出 `Could not unload nvidia modules (in use), cold reboot required`。
3. 显存几何布局**无法**跨越功能级复位或断电循环保留，因此干净的冷启动才是明确的初始状态，补丁驱动会从头重新应用全部设置。只有 SS0、SS1 以及位于 `0x00823804` 的 FEAT PLM 位于常电域中。

如果热重载成功，`build.sh` 会明确报告，此时可以立即验证。如果热重载失败，脚本会自行输出恢复步骤。

---

## 一次正确的运行结果

下面的内容由脚本自身的字面输出字符串拼接而成，并不是一次完整捕获的终端记录，因此可变部分应视为占位符。

```text
╔════════════════════════════════════════╗
║               cmpunlocker              ║
╚════════════════════════════════════════╝

━━━ Step 1/6: Verifying root privileges ━━━
✓ Running as root

━━━ Step 2/6: Detecting CMP 170HX GPU ━━━
✓ GPU detected: 0000:0b:00.0 (10de:20c2)

━━━ Step 3/6: Selecting card memory profile ━━━
✓ Detected stock/reported memory 8192 MiB → profile 8gb
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)

━━━ Step 4/6: Verifying nvidia-open (610.43.03,610.43.02) ━━━
✓ NVIDIA driver 610.43.03 is supported
✓ Kernel headers present for 6.8.0-136-generic

━━━ Step 5/6: Building and installing patched modules ━━━
[INFO]  Building against open-gpu-kernel-modules 610.43.03
[ OK ]  Using cached tarball .../driver/.build/open-gpu-kernel-modules-610.43.03.tar.gz
[INFO]  Applying unlock patches...
[INFO]    0001-sec2-postbl-plm-ss-cfg.patch
...
[ OK ]  All patches applied
runtime device-id geometry (profile metadata=64GB)
[ OK ]  Memory profile 8gb: CFG1=0x02779000 LMR=0x0000020B fb=0x0000001000000000 (64GB)
[ OK ]  Modules built
[ OK ]  Installed nvidia.ko
[ OK ]  depmod complete
[ OK ]  initramfs rebuilt
[INFO]  modprobe will load: /lib/modules/6.8.0-136-generic/updates/cmpunlocker/nvidia.ko
[ OK ]  Patched NVIDIA modules loaded
[ OK ]  Build and install finished. Verify with: nvidia-smi

━━━ Step 6/6: Done ━━━
Profile: 8gb → expect ~65536 MiB after unlock
```

启动后，决定性的证据会出现在内核日志中：

```bash
sudo dmesg | grep SEC2_DEBUG
```

一次健康的 8 GB 解锁会产生下面这些日志。作为数量参考，归档的单卡 8 GB 捕获总共包含 **29** 行 `SEC2_DEBUG`，归档的双卡 Gen2 分支启动日志包含 **134** 行：

```text
SEC2_DEBUG: saved stock signature (4096 bytes)
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
SEC2_DEBUG: late PMA extension status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

> [!NOTE]
> **不要把日志行数当作通过/失败标准**
>
> 不同构建之间的日志行数不是可靠的指纹。已有记录包括：归档的单卡 8 GB 捕获为 **29** 行，归档的双卡 Gen2 分支 `610.43.03` 日志为 **134** 行，报告工具中的 Gen1 构建和 Gen2 构建分别为 34 行和 80 行，以及 `pcielink.sh` 在两台独立的双卡 Gen2 机架上输出的 `SEC2_DEBUG lines=152`。不要因为行数不一致就判断安装失败；上面显示的寄存器回读行才是判断标准。

以下三点经常会让首次安装者误以为出错，但它们都属于正常现象：

- `WPR_CFG=0xfffff0ff` 表示**通过**，不是失败。四个 PLM 中只有三个目标值是 `0xffffffff`。
- 每次载荷尝试中出现 Booter 状态 `0xffff` 都是预期行为，无论该次尝试成功还是失败。唯一有效的成功标准是寄存器回读值。
- `dmem.bin` 显示 `not found (0x59)` 没有问题，这表示使用了内置载荷。

接下来阅读[验证解锁](verify.md)，了解完整的日志解码，以及显存容量和算力之间的区别。如果出现问题，请查看[排障](troubleshooting.md)。

---

## 重装、升级和切换分支

维护者明确建议，在不同分支之间切换时**先卸载，再安装**：“In fact, I would always recommend to remove the old one before adding the new one.” 一位克隆 `Gen2` 分支并在已有安装上直接安装的测试者报告说安装没有生效，先卸载后便恢复正常。至少另外两位测试者直接覆盖安装没有遇到问题，非正式共识是多数人都“just sending it on top”。这个失败案例确实存在，但并不普遍，也没人找出造成差异的具体因素。先卸载再安装是*受支持*的路径：

```bash
sudo ./remove.sh --yes     # in the OLD checkout
sudo ./install.sh          # in the NEW checkout
```

见[卸载](uninstall.md)。

---

## 特定环境注意事项

> [!WARNING]
> **实验性：虚拟化**
>
> 显存和算力解锁可以在 **Proxmox GPU 直通**环境下工作：一位操作者直通了八张 8 GB CMP 170 卡，全部成功解锁。目前记录有两个限制：
>
> - 使用 **SeaBIOS，不要使用 UEFI/OVMF**。UEFI 会产生看起来与利用代码完全没有生效相同的 RM init 和适配器失败。这一原因最初由实际排查确认，随后立即得到另一位此前一直无法复现结果的用户佐证。
> - 截至 2026-07-24，PCIe Gen2 链路速度修改在虚拟机中**无法工作**；维护者已确认这是一个尚待调试的问题。见[PCIe Gen2](../unlock/pcie-gen2.md)。

> [!NOTE]
> **未解问题：缺少显示设备是否会影响 GSP？**
>
> 一位操作者观察到，与存在显示设备的系统相比，同时没有 iGPU 和 BMC 显示设备的系统似乎更容易让 GSP 出问题。没有人回复确认、反驳或提供错误字符串。在一台机器上于 BIOS 中禁用 BMC 显示设备，并分别捕获 `dmesg` 进行 A/B 对比，才能解决这个问题。

对于这套补丁，Windows 是一条失败路线：解锁是基于 Linux 开源内核模块实现的，而 GSP 引导路径也是 Linux 专属的。Windows 机器可以通过 GRID 或数据中心驱动配合注入硬件 ID 来*驱动* 170HX，但那只能得到一张可正常工作的卡，而不是一张已解锁的卡。

---

## 相关页面

- [快速上手](../start/quick-start.md)查看精简版流程
- [识别你的卡](../start/identify-your-card.md)先确认手中的 SKU
- [验证](verify.md)、[排障](troubleshooting.md)、[恢复](recovery.md)
- 如果机架中有多张卡，请查看[多卡](multi-gpu.md)
- [驱动版本](driver-versions.md)介绍仅支持 610 版本的限制和未发布的移植版本
- [驱动补丁](../unlock/driver-patches.md)说明每个补丁实际修改的内容
