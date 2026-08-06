# 安装解锁

**本页覆盖内容。** 已发布的 `cmpunlocker` 驱动补丁在 CMP 170HX 上的完整、受支持安装流程：开始前必须具备什么、精确命令、`install.sh` 和 `driver/build.sh` 每步做什么、卡档位如何选择（以及何时强制它）、为什么冷重启要紧、以及正确的一次运行在屏幕和 `dmesg` 里长什么样。

短版：安装 nvidia-open **610.43.03** 或 **610.43.02**，禁用安全启动，安装内核头文件，然后在仓库克隆中运行 `sudo ./install.sh`，最后冷启动。脚本为你的驱动版本下载 NVIDIA 出厂的 `open-gpu-kernel-modules` tarball，依次应用六个补丁、构建五个内核模块，并把它们安装到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。全程不会向卡的 VBIOS 写入任何内容，也不会修改磁盘上的任何固件文件。一张 8 GB 卡（`10de:20c2`）解锁后报告 **65536 MiB**，一张 10 GB 卡（`10de:2082`）解锁后报告 **40960 MiB**。

解锁本身的原理见[解锁如何工作](../unlock/how-it-works.md)，补丁系列见[驱动补丁](../unlock/driver-patches.md)。本页只讲操作流程。

---

## 前置条件

| 要求 | 详情 | 由谁强制 |
|---|---|---|
| 操作系统 | Linux，x86-64。此解锁**没有 Windows 路径**。 | 不检查；补丁只为 Linux GSP 引导路径存在 |
| 权限 | root（`sudo ./install.sh`） | `install.sh` 第 1 步、`build.sh` |
| 卡 | `10de:20c2`（8 GB）或 `10de:2082`（10 GB）。`10de:20b0` 会被检测到却**不**被解锁。 | `install.sh` 第 2 步（`lspci` grep），和驱动内设备门 |
| 驱动 | nvidia-**open** `610.43.03`（默认）或 `610.43.02`，精确字符串匹配 | `install.sh` 第 4 步和 `driver/build.sh`，两者都对 `driver/VERSION` |
| 内核头文件 | `/lib/modules/$(uname -r)/build` 必须存在 | `install.sh` 第 4 步和 `build.sh` |
| 安全启动 | 禁用；补丁模块未签名 | `install.sh` 第 4 步、经 `mokutil --sb-state` |
| 网络 | 首次安装时可达 `github.com`、用于源码 tarball | `build.sh` 里的 `curl -L --fail` |
| 工具链 | `python3`、`patch`、`make`、`curl`、一个可工作的内核构建环境 | `build.sh` 只检查 `python3` |

实际要紧的注意事项：

- **要用 nvidia-open，不是专有驱动。** 封闭驱动有不同的引导路径，无法以同样方式打补丁。卡在出厂驱动上*运行*得很好（一位测试者开箱即在 Ubuntu 24.04 上用 `nvidia-driver-570` 配合 CUDA 12.8，Ubuntu 22.04 上的 `nvidia-driver-535-server` 也见有报告），但"能被驱动"和"能被解锁"是两回事。见[驱动版本](driver-versions.md)。
- **安全启动检查是有条件的。** 它只在 `/sys/firmware/efi` 存在**且** `mokutil` 位于 `PATH` 时运行。在非 EFI 机器或没装 `mokutil` 的机器上，检查会被静默跳过，你最终可能仍留下一个内核拒绝加载的模块。`dmesg` 里的症状是 `nvidia: module verification failed: signature and/or required key missing - tainting kernel`。
- **没有 PyYAML、没有 GCC 版本检查。** `build.sh` 用带标准库的普通 `python3`，不做任何编译器版本测试。网上流传的 "python3 with PyYAML / gcc 13+" 前置条件来自第三方 `unlock-cmp-170hx` 指南仓库，而不是这些脚本；一个钉住 `pyyaml>=5.1` 的残留 `requirements.txt` 也残留在六个 cmpunlocker 分支上，不过没有任何分支脚本 import `yaml`。泄露的预构建包 README 只要求 root 访问权限和内核头文件。一次在 Ubuntu 26.04 LTS、内核 7.0.0-27-generic 上报告了可工作的构建（`Gen2` 分支，多次重启存活）。
- **在你能承受弄坏的机器上进行。** 裸机上的驱动补丁反复尝试破坏性足够大——一位开发者报告，每次 `nvidia.ko` 部署搞砸后都得重装操作系统。见[Risks](../start/risks.md)。

> [!CAUTION]
> **固件打补丁时代的遗留状态**
>
> 如果这台机器跑过 `cmpunlocker` 的**固件打补丁前身**，在安装驱动补丁**之前**把 `gsp_tu10x.bin` 恢复到出厂：
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp "$GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak" "$GSP_DIR/gsp_tu10x.bin"
> ```
>
> 打过补丁的驱动在引导时把固件的签名保存为 "stock"。如果磁盘上的固件仍被打过补丁，驱动会把利用载荷保存为出厂，随后一次干净的 GSP-RM 引导就 DMA 错误的 ROP 链。事后要找的成功行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

---

## 命令

```bash
git clone https://github.com/amoghmunikote/cmpunlocker
cd cmpunlocker
sudo ./install.sh
```

自动检测错误或 `nvidia-smi` 不可用时强制档位：

```bash
sudo ./install.sh --profile=8gb     # 8 GB 物理卡  -> 64 GB 几何布局
sudo ./install.sh --profile=10gb    # 10 GB 物理卡 -> 40 GB 几何布局
sudo ./install.sh --help
```

只接受那三种标志形式（`--profile=8gb|8GB|10gb|10GB`、`-h`、`--help`）。任何其它参数都会以 `Unknown argument: <arg>` 退出 1。

所有输出都 tee 到检出内的 `logs/install_<YYYYmmdd_HHMMSS>.log`，所以要从一个可写目录运行。

---

## `install.sh` 逐步做什么

脚本在 `set -euo pipefail` 下是六个编号步骤。

### 第 1/6 步：root

`[[ "${EUID}" -eq 0 ]]` 或死掉、带 `Run as root: sudo ./install.sh`。

### 第 2/6 步：GPU 检测

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

没有匹配是致命的：`No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)`。注意 `head -1`：**master 是一个单卡安装器。** 它只记录第一行匹配的 BDF（总线、设备、功能地址）以及那一个设备 ID。机架多于一张卡时见[多卡](multi-gpu.md)。

如果检测到的设备 ID 既不是 `20c2` 也不是 `2082`，脚本警告并**继续**：

```text
! In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
! This card reports 0x20b0; install will continue, but unlock may not activate.
```

那是准确的。驱动内门 `_kgspSec2PostblTimingEnabled()` 只接受 `0x20C2` 和 `0x2082`，所以一张 `20b0` 卡会得到完全打过补丁、却从不为其触发的模块。README 里更旧的 "unlock is `0x20C2`-gated" 措辞已经过时；自提交 `0f9aca5` "Unlock isn't gated anymore" 起，`0x2082` 就是头等目标。

### 第 3/6 步：卡档位

要么用 `--profile` 覆盖、要么由 `detect_card_profile()` 决定，它读 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1` 并映射四个窗口：

| 报告的 `memory.total` | 选定的档位 | 为什么有这个窗口 |
|---|---|---|
| `>= 60000` MiB | `8gb` | 在**已解锁的** 64 GB 卡上重装 |
| `35000`-`59999` MiB | `10gb` | 在已解锁的 40 GB 卡上重装 |
| `7680`-`8704` MiB | `8gb` | 出厂 8 GB 卡（8192 MiB） |
| `9728`-`10752` MiB | `10gb` | 出厂 10 GB 卡（10240 MiB） |
| 其它任何值 | 致命 | 打印 `unknown:<mib>`，然后 `Could not detect 8GB vs 10GB card. Re-run with --profile=8gb or --profile=10gb` |

然后横幅打印下面之一：

```text
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
==> Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)
```

> [!WARNING]
> **自动检测在混合 GPU 主机上不安全**
>
> `detect_card_profile()` 取 `nvidia-smi` 顺序里的**第一张 GPU**，它不一定是 `lspci` 找到的那张 CMP。一张 RTX 3080 10 GB 与 8 GB CMP 170HX 并存的主机上，至少两人从 3080 检测出 "10GB"。另一份报告把其它 CMP SKU（一张 50HX）误检为 10 GB 170HX。在当前 `master` 上后果只是错误的元数据，但在任何带其它 NVIDIA 卡的主机上，安全的习惯是**始终显式传 `--profile`**。如果第一张 GPU 报告的大小落在四个窗口之外（比如一张 24 GB 卡），安装会直接死掉。

### 第 4/6 步：安全启动、驱动版本、头文件

- 安全启动：如果 `/sys/firmware/efi` 存在且 `mokutil` 存在且 `mokutil --sb-state` 匹配 `SecureBoot enabled`，死掉、带 `Secure Boot is enabled. Disable it before installing unsigned patched modules.`
- 驱动版本检测顺序：
  1. `/proc/driver/nvidia/version`
  2. `nvidia-smi --query-gpu=driver_version`
  3. 一次对 `/lib/firmware/nvidia/<supported-version>/` 的目录探测
  4. `/lib/firmware/nvidia/` 下排序最高的目录
- 检测到的字符串必须精确匹配 `driver/VERSION` 里的一行，否则：`Installed driver is <detected>, but cmpunlocker requires one of: 610.43.03,610.43.02.`
- `/lib/modules/$(uname -r)/build` 必须存在，否则 `Kernel headers missing for <kver>. Install linux-headers-<kver> or kernel-devel.`

### 第 5/6 步：构建并安装

`install.sh` chmod 并 exec `driver/build.sh`，环境里有 `CMPUNLOCKER_DRIVER_VERSION` 和 `CMPUNLOCKER_CARD_PROFILE`。见下一节。

### 第 6/6 步：后续步骤横幅

打印预期的解锁后大小，然后四个编号的后续步骤：一次冷重启提醒（`sudo shutdown -h now`）和三个验证命令（`nvidia-smi`、`sudo dmesg | grep SEC2_DEBUG`、和 `nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader`），随后安装日志的路径。

---

## `driver/build.sh` 做什么

1. **重新验证** root、`driver/VERSION` 里的版本、补丁目录、内核头文件、和 `python3` 的存在。
2. **下载** `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`、用 `curl -L --fail` 到 `driver/.build/`（用 `CMPUNLOCKER_BUILD_DIR` 覆盖缓存位置）。缓存的 tarball 被复用。仓库里不运送任何 NVIDIA 代码。
3. **每次干净解压**：`rm -rf "${SRC_DIR}"` 然后 untar，这样一次失败的先前构建无法污染下一次。
4. **用 `patch -p1` 按 glob（字典序）顺序应用每个 `driver/patches/*.patch`**。已发布的系列是六个文件、总计 37,415 字节：

   | 补丁 | 字节 | 它做什么 |
   |---|---|---|
   | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 | 整个解锁：载荷、[PLM](../unlock/privilege-level-masks.md) 循环、SS0/SS1/CFG1/LMR 写、`fb_length` 重写 |
   | `0002-booter-verify.patch` | 3,988 | 软失败四个引导断言、打印 post-BooterLoad 回读 |
   | `0003-late-pma.patch` | 10,580 | 把 8 GiB 之上的新内存注册给物理内存分配器 |
   | `0004-bar0-pramin-clamp.patch` | 861 | 把 BAR0/PRAMIN 窗口钳到出厂 8192 MB 偏移量 |
   | `0005-ce-scrub-workarounds.patch` | 1,642 | 强制复制引擎清理器进入物理模式 |
   | `0006-persistent-sw-state.patch` | 603 | 设置 `NV_FLAG_PERSISTENT_SW_STATE`、取代旧看门狗守护进程 |

   因为循环是 `set -euo pipefail` 下的普通 glob，把名为 `0007-*.patch` 的第三方 diff 丢进那个目录就能干净地叠加，任何失败的 hunk 都会中止构建。P2P 补丁就是这样分层的（见[P2P](../frontier/p2p.md)）。
5. **跑档位步骤。** 一个内联 Python 脚本检查打过补丁的 `kernel_gsp.c` 是否已含全部六个标记（`SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID`、`..._10GB_PCI_DEVICE_ID`、`0x02779000U`、`0x02669000U`、`0x0000001000000000ULL`、`0x0000000A00000000ULL`）。在 `master` 上六个都存在，所以它打印 `runtime device-id geometry (profile metadata=64GB)` 并在不编辑任何东西的情况下退出。它下面的正则替换分支是给单-SKU 补丁的死遗产回退。
6. **写三个元数据文件** 进 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：`driver_version`、`card_profile`（`8gb` / `10gb`）、`unlock_geometry`（`64GB` / `40GB`）。**内核模块里没有任何东西读它们。** 它们是为人、也为 `verify.sh` 而存在的。打过补丁的内核引导时唯一读的文件是可选 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。
7. **构建**：`rm -rf src/nvidia/_out src/nvidia-modeset/_out kernel-open/conftest`、`make clean`，然后 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`。报告的构建时间是**现代 CPU 上 2 到 5 分钟**。这个范围来自两份书面分布（泄露预构建包的 README 说 "~2-5 min"、一份流传的 40 GB 解锁指南说 "~5 minutes on a modern CPU"）；没人贴过计时测量。
8. **安装五个模块**、模式 `0644`、进 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko`、`nvidia-peermem.ko`（由 `find` 找到、排除 `*/conftest/*`）。只有 `nvidia.ko` 携带解锁代码；其它四个是出厂重建、运来让模块集保持版本一致。
9. **`depmod -a "${KVER}"`**。模块优先级是普通 depmod 排序：`updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`，这就是为什么不需要 `dpkg-divert`。
10. **用第一个可用的重建 initramfs**：`update-initramfs -u -k`、`dracut --force --kver`、`mkinitcpio -P`，否则警告 `No initramfs tool found, rebuild manually before rebooting`。master 的 `build.sh` 这里没带注释，但分支副本（`memory`、`ecc`、`housekeeping`、`PG199`）逐字解释了推理：NVIDIA 常从 initramfs 加载，如果那里只打包 `updates/dkms`，即使 depmod 偏好 `updates/cmpunlocker`、出厂模块也会在引导时胜出。那是 "已安装却显存仍显示出厂大小" 的一条貌似合理路线，却是脚本的推理而非诊断出的野外失败：*initramfs*、*initrd*、*dracut* 和 *mkinitcpio* 这些词在聊天语料库里任何地方都不出现。只有在 initramfs 步骤之后 `build.sh` 才跑它的经验检查、确认补丁模块确实胜出：`modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'`，警告 `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`。
11. **尝试一次热重载**：停止 `nvidia-persistenced` 和 `nvidia-fabricmanager`、对 `nvidia_drm`、`nvidia_uvm`、`nvidia_modeset`、`nvidia` `modprobe -r`，然后重载。然后它对比 `/sys/module/nvidia/srcversion` 与 `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko`，不匹配时警告 `Loaded nvidia srcversion (X) != patched (Y)` 并清除它自己的成功标志。

> [!WARNING]
> **对下载的 tarball 没有完整性检查**
>
> `build.sh` 用 `curl -L --fail` 抓取 NVIDIA tag tarball 并以无校验和或签名验证的方式缓存它、树里任何地方都没有。在不可信网络上，在首次构建前自己验证缓存的 tarball。

---

## 冷重启

热重启不够、一般情况热重载也不够。整个项目的指示、包括泄露预构建分发自己的 README，都是**冷**重启：完全断电、然后上电。

```bash
sudo shutdown -h now
# 然后上电
```

原因，按咬人多寡排序：

1. 解锁在打过补丁的模块的 GSP 引导里运行。如果因为热重载失败或 initramfs 仍持有出厂模块、运行中的 `nvidia.ko` 仍是出厂那个，解锁从不执行。
2. 使用中的模块（X11、一个显示管理器、一个 persistenced 守护进程、一个 CUDA 进程）阻塞 `modprobe -r`，而 `build.sh` 打印 `Could not unload nvidia modules (in use), cold reboot required`。
3. 显存几何布局**不**挺过功能级复位或断电循环，所以一次干净的冷启动就是那个良定义状态：打过补丁的驱动从中从头重新应用一切。只有 SS0、SS1 和 `0x00823804` 处的 FEAT PLM 住在常电岛里。

如果热重载确实成功，`build.sh` 会这么说、你可以立即验证。如果没有，脚本自己打印恢复指示。

---

## 正确的一次运行长什么样

下面由脚本自己的字面输出字符串拼成（不是一份单一捕获的转写），所以把可变部分当作占位符。

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

启动后立即、决定性的证据在内核日志里：

```bash
sudo dmesg | grep SEC2_DEBUG
```

一张健康的 8 GB 解锁产生这些行。作为规模参考、归档的单卡 8 GB 捕获总共含 **29** 条 `SEC2_DEBUG` 行、归档的双卡 Gen2 分支引导日志含 **134** 条：

```text
SEC2_DEBUG: saved stock signature (4096 bytes)
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
SEC2_DEBUG: late PMA extension status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

> [!NOTE]
> **不要把行数当作通过/失败测试**
>
> 行数不是可靠的跨构建指纹。记录的值：归档单卡 8 GB 捕获上 **29**、归档双卡 Gen2 分支 `610.43.03` 日志上 **134**、报告工具上 34（Gen1 构建）和 80（Gen2 构建）、以及 `pcielink.sh` 在两台独立双卡 Gen2 机架上打印的 `SEC2_DEBUG lines=152`。不要把不匹配读成安装失败。上面那些寄存器回读行才是判据。

三样东西经常吓到首次安装者，它们全都是正常的：

- `WPR_CFG=0xfffff0ff` 是一个**通过**。四个 PLM 里只有三个目标 `0xffffffff`。
- 每次载荷趟的逐尝试 Booter 状态 `0xffff` 都预期、无论成败。寄存器回读是唯一有效成功判据。
- `dmem.bin` 的 `not found (0x59)` 是良性的；用内置载荷。

下一步读[验证解锁](verify.md) 看完整日志解码和显存-对比-算力的区别。如果哪里不对，去[排障](troubleshooting.md)。

---

## 重装、升级和切换分支

维护者设定的规则是，在分支之间切换时**先卸载、再安装**："In fact, I would always recommend to remove the old one before adding the new one."（事实上，我总是建议在加新的之前移除旧的。）一位克隆 `Gen2` 分支、在现有安装之上安装的测试者报告它不工作，先卸载就修好了。至少另两位测试者直接之上安装没有问题，非正式共识是大多数人 "just sending it on top"（直接装上去）。那个失败是真实的、却不普遍，而且没人识别出差异因素。先卸载是*受支持*的路径：

```bash
sudo ./remove.sh --yes     # 在 OLD 检出里
sudo ./install.sh          # 在 NEW 检出里
```

见[卸载](uninstall.md)。

---

## 环境特定注意事项

> [!WARNING]
> **实验性：虚拟化**
>
> 显存和算力解锁在 **Proxmox GPU 直通** 下工作：一位操作者直通了八张 8 GB CMP 170 卡，全部解锁。记录了两个约束：
>
> - 用 **SeaBIOS，不要用 UEFI/OVMF**。UEFI 会产生看起来恰好像利用根本不工作的 RM init 和适配器失败。这曾被一手根因定位，并立即得到一位此前一直无法复现结果的第二人佐证。
> - PCIe Gen2 链路速度改动截至 2026-07-24 在 VM 里**不**工作，被维护者承认为一个开放调试项。见[PCIe Gen2](../unlock/pcie-gen2.md)。

> [!NOTE]
> **未解问题：缺失的显示设备会搅乱 GSP 吗？**
>
> 一位操作者观察到 GSP 在没 iGPU 也没 BMC 显示设备的系统上似乎比有显示设备的系统更不高兴。没人用确认、反驳或错误字符串回应。在 BIOS 里禁用 BMC 显示设备、捕获 `dmesg` 的一次机器上 A/B 能定论它。

对这份补丁 Windows 是一条死路：解锁是针对 Linux 开源内核模块实现的，而 GSP 引导路径是 Linux 专属的。Windows 机器可以用 GRID 或数据中心驱动加一个注入的硬件 ID *驱动* 一张 170HX，但那只会给你一张能工作的卡、而不是一张解锁卡。

---

## 相关页面

- [快速上手](../start/quick-start.md) 看浓缩版
- [识别你的卡](../start/identify-your-card.md) 先确认你持有哪个 SKU
- [验证](verify.md)、[排障](troubleshooting.md)、[恢复](recovery.md)
- [多卡](multi-gpu.md) 如果机架多于一张卡
- [驱动版本](driver-versions.md) 看 610-only 约束和未发布移植
- [驱动补丁](../unlock/driver-patches.md) 看每个补丁实际改什么
