# 驱动版本：支持范围与原因

## 本页内容

本页说明 CMP 170HX 解锁器针对哪些 NVIDIA 驱动版本构建，解释支持列表为何如此短，介绍将安装器指向其他版本时会发生什么，并说明未发布的回移植分支对 595、590 和 580 实际提供了什么。

简短结论是：**当前发布版 `master` 恰好支持两个版本，即 `610.43.03`（默认版本）和 `610.43.02`，并且按完整字符串精确匹配。其他任何版本都会导致构建直接失败。** 这两个版本都已在真实硬件上完成启动测试。低于 610 的版本只存在于一个未发布分支中，目前仅完成源码验证；现有记录中没有任何人曾在 170HX 上启动测试过这些版本。

需要特别区分一个容易混淆的问题：170HX 完全可以在普通出厂 NVIDIA 驱动上正常运行，只是不会在这些驱动上完成**解锁**。能否驱动运行与能否解锁，是两个彼此独立的问题。

---

## `master` 的支持列表

`driver/VERSION` 按以下顺序包含两行：

```text
610.43.03
610.43.02
```

第一行是默认构建目标。`common/constants.yaml` 的 `driver_versions` 下也列出了同样的两个版本。`install.sh` 和 `driver/build.sh` 都会将 `driver/VERSION` 读入 `SUPPORTED_VERSIONS`，然后调用按完整字符串匹配的 `version_supported()`。这里没有范围检查，没有“610 或更高版本”的比较，也没有模糊匹配。

如果已安装的驱动不属于这两个版本，安装会直接失败，并显示：

```text
Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.
```

### 如何检测已安装的版本

`install.sh` 会按顺序尝试以下四个来源，并在第一个成功提供版本号的来源处停止：

| 顺序 | 来源 |
|---|---|
| 1 | `/proc/driver/nvidia/version` |
| 2 | `nvidia-smi --query-gpu=driver_version` |
| 3 | 探测 `/lib/firmware/nvidia/<supported>/` 目录 |
| 4 | `/lib/firmware/nvidia/` 下按名称排序最高的目录 |

随后，构建流程会下载匹配的上游源码 tarball：

```text
https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz
```

该文件会缓存到 `driver/.build/` 下，并在每次运行时重新进行干净解压。`cmpunlocker` 仓库本身不包含任何 NVIDIA 代码。

> [!NOTE]
> **下载没有校验和**
>
> `build.sh` 使用 `curl -L --fail` 获取 tarball，但不会进行任何校验。整个代码树中都没有记录 SHA-256。在 `driver/VERSION` 或 `common/constants.yaml` 中为每个版本记录预期哈希，是一项显而易见但尚未实现的改进。

---

## 为什么特指 610.43.0x

原因有四个，以下按约束强度从高到低排列。

**补丁 hunk 锚定于特定的源码树。** 六个补丁文件会在 `set -euo pipefail` 环境下通过 `patch -p1` 应用；只要有一个 hunk 被拒绝，构建就会中止。`kernel_gsp.c`、`g_kernel_gsp_nvoc.h`、`osinit.c`、`kernel_gsp_tu102.c` 和 `nv.c` 中的行号、周围上下文及结构体布局，都会在不同上游版本之间发生变化。参见[六个驱动补丁](../unlock/driver-patches.md)。

**解锁必须通过修改开源内核模块实现。** 专有 NVIDIA 驱动“has different boot paths and cannot be patched the same way”（采用不同的启动路径，无法用相同方式打补丁）。在 GA100 上，开源模块也只能使用 GSP 路径：使用 `NVreg_EnableGpuFirmware=0` 加载时，会直接因 `0x62` 固件初始化错误而失败，因此这块晶片不存在切换到 CPU-RM 的备用路径。

**610 是明确提出的最低版本。** 在被问及如何与第三方 P2P 驱动共存时，维护者的原话是“it needs to be **610 or above**”（需要 **610 或更高版本**）。但实际的 `master` 比这句话更加严格：它拒绝任何不完全等于两个白名单字符串之一的版本。

**两个版本都有实际运行记录。** 以下是来自两台机器的独立运行时捕获：

```text
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64 610.43.02 Release Build
              (dvs-builder@U22-I3-H05-01-2) Tue May 19 11:24:27 UTC 2026
GCC version:  gcc version 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1)
kernel:       6.8.0-136-generic
```

> [!WARNING]
> **这份捕获来自解锁未触发的机架**
>
> 应将其理解为 `610.43.02` 存在且可以安装的证据，而不是该版本完成解锁的证据。`dvs-builder` 构建字符串来自 NVIDIA 自身，因此当时加载的是**出厂模块**，而不是打过补丁的模块；同一台机架上的 `verify.sh` 报告每张 GPU 都是 `MISSING`，`dmesg` 中也没有 `SEC2_DEBUG` 记录。不要将此代码块中的 gcc 或内核版本视为已知可用的构建环境。

此外，还有一条独立记录：`NVIDIA-SMI 610.43.03 / KMD Version: 610.43.03 / CUDA UMD Version: 13.3`。目前流传的一个打包版 NixOS 模块会强制断言 `config.hardware.nvidia.package.version == "610.43.03"`。

每个实验性分支，包括完整的 PCIe Gen2 系列和 80 GB 尝试，也只列出 `610.43.03` 和 `610.43.02`。唯一的例外是回移植分支。

---

## `610.43.02` 还是 `610.43.03`？

> [!NOTE]
> **未解问题**
>
> 这个问题至今无人回答。“is 610.43.02 or 610.43.03 more reliable?”（610.43.02 还是 610.43.03 更可靠？）曾于 2026-07-24 在频道中直接提出，但一直没有答复。两个版本都出现过成功解锁的记录。`610.43.03` 之所以是默认版本，只是因为它位于 `driver/VERSION` 的第一行。
>
> 这个实验并不复杂，但没有人实际执行过：从现有安装中收集 `driver_version` 元数据文件和 `SEC2_DEBUG` 中 PLM 打开成功率，然后进行比较。

实际建议是：**选择默认的 `610.43.03`。** 如果某张卡在其中一个版本上无法干净解锁，尝试另一个版本是成本低且合理的诊断步骤，但目前没有证据表明换版本一定会有帮助。

---

## 固定版本

> [!WARNING]
> **基于推理的建议，不是实测结论**
>
> 针对未来 NVIDIA 驱动修补这一漏洞，推荐的长期缓解措施是**将驱动固定在 610**，类似 P100 和 V100 操作者将版本固定在 580 左右。至少有一位操作者已经将软件包固定版本作为预防措施。这只是尚未受到反驳的推理，并非已经演示过的必要条件：目前不存在会造成阻断的驱动，而且 GitHub 上已经发布的开源内核模块也无法被召回。

---

## 出厂驱动：可以运行，但不会解锁

170HX 可以在完全未打补丁的驱动上完成枚举并运行 CUDA。在 Ubuntu 24.04 上，配合 CUDA 12.8 的 `nvidia-driver-570` 开箱即用；Ubuntu 22.04 上的 `nvidia-driver-535-server` 也有正常工作的报告。由于驱动的 PCI ID 表中没有 `0x20C2` 对应的产品名称，`nvidia-smi` 会在计算能力 8.0 下将这张卡显示为 `NVIDIA Graphics Device`。这个命名特征可以帮助你快速确认当前看到的是 CMP 部件。

使用出厂驱动时，显卡处于锁定状态：显存容量保持出厂值，算力节流保持出厂状态，链路为 PCIe Gen1 x4。

---

## 与版本相关的硬性要求

| 要求 | 详情 |
|---|---|
| 安全启动 | 必须**关闭**。打过补丁的模块未签名；启用时，dmesg 会显示 `nvidia: module verification failed: signature and/or required key missing - tainting kernel`。如果 `/sys/firmware/efi` 存在、系统安装了 `mokutil`，并且 `mokutil --sb-state` 报告已启用，`install.sh` 会显示 `Secure Boot is enabled. Disable it before installing unsigned patched modules.` 并直接失败。在非 EFI 系统或未安装 `mokutil` 的系统上，这项检查会静默跳过。 |
| 驱动家族 | 仅支持 nvidia-open。专有 blob 无法用相同方式打补丁。 |
| 操作系统 | **仅支持 Linux。** GSP 启动路径是 Linux 专属的；Windows WDDM 驱动在根本上不同。 |
| 内核头文件 | `/lib/modules/$(uname -r)/build` 必须存在。 |
| 工具链 | 需要 `python3`。`master` **不使用 PyYAML**，发布版脚本中也**没有任何显式的 GCC 版本检查**。“Requires gcc 13+ and PyYAML”来自第三方 `unlock-cmp-170hx` 指南仓库，另外六个分支中还残留了一份 `requirements.txt`；这并不是 cmpunlocker 的要求。泄露包的 README 只要求 root 权限和内核头文件。 |
| 网络 | 首次安装时需要，用于获取上游 tarball。 |

完整流程参见[安装](install.md)，还原操作参见[卸载](uninstall.md)。

---

## 回移植分支：`clanker/driver-port`

> [!WARNING]
> **实验性：已完成源码验证，但从未进行启动测试**
>
> 对 595、590 和 580 的支持位于一个未发布分支中。该分支自己的 README 原文声明：
>
> > `595.71.05, 590.48.01, and 580.105.08 are source-verified (patches apply cleanly and the unlock logic matches the 610.43.0x path) but have not yet been boot-tested on physical CMP 170HX hardware.`
> > （`595.71.05、590.48.01 和 580.105.08` 已通过源码验证（补丁可以干净应用，解锁逻辑与 610.43.0x 路径一致），但还没有在实体 CMP 170HX 硬件上完成启动测试。）
>
> 该分支于 2026-07-21 宣布，并明确征集测试者。**截至 2026-07-28，现有记录中没有任何成功确认。** 在显卡真正启动之前，构建成功本身不构成任何证据。

分支当前提交为 `153cd6d`，日期为 2026-07-21。

### 它改动了什么

它几乎没有结构性改动。`driver/patches/` 被拆成四个按主版本号划分的子目录，每个目录都包含相同的六个补丁文件名；`build.sh` 只增加了两行：

```diff
-PATCH_DIR="${SCRIPT_DIR}/patches"
+BRANCH="${VERSION%%.*}"
+PATCH_DIR="${SCRIPT_DIR}/patches/${BRANCH}"
```

该分支中的 `install.sh` 与 `master` **逐字节相同**：仅支持单 GPU，使用 `head -1`，没有 `verify.sh`，也没有 `gpu_inventory`。如果还需要多卡或 PCIe Gen2 支持，就无法从这个分支获得。参见[多卡](multi-gpu.md)。

### 这是重新锚定，而不是重写

四个目录中的每个寄存器值、PLM 条目、载荷偏移量、静态信息重写和 PMA 函数都逐字符相同。具体来说：

- 补丁 `0004` 和 `0005` 在全部四个版本目录里逐字节相同（相同 md5）。
- 补丁 `0002` 和 `0006` 在 590 和 610 之间逐字节相同。
- `0003` 新增的 `+` 行在四个目录中完全相同。
- `0001` 新增的 `+` 行在 610 与 580/590/595 之间仅相差**额外添加的一行空行**，除此之外没有任何差异。

### 各目录的补丁大小

| 目录 | 0001 | 0002 | 0003 | 0004 | 0005 | 0006 | 总计 |
|---|---|---|---|---|---|---|---|
| `580` | 19,700 | 3,957 | 10,377 | 861 | 1,642 | 497 | **37,034** |
| `590` | 19,647 | 3,988 | 10,377 | 861 | 1,642 | 603 | **37,118** |
| `595` | 19,638 | 3,957 | 10,364 | 861 | 1,642 | 531 | **36,993** |
| `610` | 19,741 | 3,988 | 10,580 | 861 | 1,642 | 603 | **37,415** |

`610` 目录是 **`master` 补丁集的逐字节副本**。这次移植没有改变发布版路径中的任何内容。

### 移植必须适配的上游差异

其中只有一项属于语义差异，其余都是上下文或锚点发生了漂移。

| 分歧 | 610 | 595 | 590 | 580 |
|---|---|---|---|---|
| `_kgspCreateSignatureMemdesc` 中的 Memdesc 标志 | 由 `if (confComputeForceUnprotAlloc(pGpu))` 控制 | 无条件设置 `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` | 与 595 相同 | 与 595 相同 |
| `osinit.c` 中晚期 PMA 钩子的上下文 | 位于 `goto shutdown;` 之后 | 位于 `goto shutdown;` 之后 | 位于 `consoleDisabled = NV_FALSE;` 之后 | 位于 `consoleDisabled = NV_FALSE;` 之后 |
| GSP 静态信息末尾上下文 | `NV_ASSERT_OK_OR_GOTO(status, kgspInitGspTraceCrashBuffer(...), done);` | 存在 | **不存在** | 存在 |
| 静态信息 hunk 锚点 | `@@ -5164` | `@@ -5070` | `@@ -4065` | `@@ -4198` |
| `KernelGsp` 字段插入锚点 | `@@ -544,6 +544,8 @@` | `@@ -541` | `@@ -525` | `@@ -524` |
| 插入点之后的字段 | `GspSystemInfo *pSystemInfo; NvU32 regTableSize; PACKED_REGISTRY_TABLE *pRegTable;` | 与 610 相同 | `LIBOS_LOG_DECODE logDecode; LIBOS_LOG_DECODE logDecodeVgpuPartition[48]; RM_LIBOS_LOG_MEM rmLibosLogMem[7];` | 与 590 相同 |
| 补丁 0006 的末尾上下文 | `(void)rm_get_gpu_uuid_raw(sp, nv);` | 与 610 相同 | 与 610 相同 | `{ const NvU8 *uuid = rm_get_gpu_uuid_raw(sp, nv);` |
| 补丁 0006 锚点 | `@@ -1521` | `@@ -1531` | `@@ -1521` | `@@ -1481` |
| 补丁 0002 的相邻符号 | `void kgspConfigureFalcon_TU102(` | `static NvBool _kgspIsProcessorSuspended(OBJGPU *pGpu, void *pVoid);` | 与 610 相同 | 与 595 相同 |
| 补丁 0002 锚点 | `@@ -57` / `@@ -545` / `@@ -565` | `@@ -55` / `@@ -500` / `@@ -520` | 与 610 相同 | `@@ -54` / `@@ -516` / `@@ -536` |

无保护分配差异是唯一的行为差异，而且它让 610 之前的源码树略微更宽松，而不是更严格。

### 版本列表内部不一致

> [!CAUTION]
> **十二个白名单版本中有七个没有经过验证的补丁锚点**
>
> 分支的 `driver/VERSION` 列出**十二**个版本：
>
> ```text
> 610.43.03  610.43.02
> 595.71.05  595.58.03  595.45.04
> 590.48.01
> 580.105.08 580.95.05  580.82.09  580.82.07  580.76.05  580.65.06
> ```
>
> 但实际只有**四**个补丁目录，而 `build.sh` 使用 `BRANCH="${VERSION%%.*}"`，也就是**只按主版本号**选择目录。因此，`595.45.04` 会使用 `595.71.05` 的 hunk 打补丁，`580.65.06` 会使用 `580.105.08` 的 hunk 打补丁。十二个版本中有五个具备某种证据：`610.43.03` 和 `610.43.02` 已通过启动测试，`595.71.05`、`590.48.01` 和 `580.105.08` 是分支 README 称为已完成源码验证的三个版本。其余七个版本（`595.58.03`、`595.45.04`、`580.95.05`、`580.82.09`、`580.82.07`、`580.76.05`、`580.65.06`）完全依赖 `patch -p1` 的模糊匹配。
>
> 与此同时，同一分支中的 `common/constants.yaml` 只列出**五**个版本（`610.43.03`、`610.43.02`、`595.71.05`、`590.48.01`、`580.105.08`），与 `VERSION` 不一致。`install.sh` 接受这十二个版本中的任意一个，因此用户无需进行任何特殊操作，就可能进入未经验证的状态。
>
> 这里的失败风险是根据代码阅读得出的推断，并非已经观察到补丁被拒绝。测试完全离线且机械化：下载另外七个 tarball，分别针对对应的主版本补丁目录运行 `patch -p1 --dry-run`。不需要硬件。

---

## 应该运行哪个版本？

| 情况 | 建议 |
|---|---|
| 正常安装、单卡、希望正常工作 | 在 **610.43.03** 上使用 `master`。这是唯一得到广泛一手确认的组合。 |
| 单卡在 610.43.03 上表现异常 | 尝试 **610.43.02**。两个版本都在白名单中，也都出现过成功解锁。 |
| 多张 170HX 卡 | `master` 可以工作，并已在多 GPU 主机上得到确认，包括 Proxmox 直通下的 8 张卡。注意 `install.sh` 自动检测存在风险，应显式传入 `--profile`。参见[多卡](multi-gpu.md)。 |
| 需要 PCIe Gen2 | 只能使用分支，而且仅支持 610。参见[PCIe Gen2](../unlock/pcie-gen2.md)。 |
| 因其他应用而必须固定在 595、590 或 580 | 回移植分支是唯一选择，而你将成为第一个启动测试它的人。请在一台即使损坏也能接受的机器上进行，并无论成功与否都报告 `POST-BooterLoad verify` 这一行。 |
| 希望让 170HX 与 Volta 或 Maxwell 卡共存 | 这正是 580 回移植分支的动机：580 覆盖从 980 Ti 到 A100 的所有型号。除了该分支的源码，目前没有其他地方回答这个问题。 |

> [!CAUTION]
> **在裸机上开发驱动补丁具有破坏性**
>
> 有开发者报告，每次把 `nvidia.ko` 部署搞坏后都需要重装操作系统。公认的解决办法是在 VM 或容器中测试修改后的驱动。对于 Proxmox 直通，具体应使用 **SeaBIOS，而不是 UEFI/OVMF**：UEFI 会产生与解锁器完全不起作用时非常相似的 RM init 和适配器错误，至少有两人因此误判问题并浪费了大量时间。

---

## 切换版本或分支

受支持的操作路径是**先移除，再安装**。维护者的原话是：“In fact, I would always recommend to remove the old one before adding the new one.”（事实上，我总是建议先移除旧版本，再添加新版本。）

```bash
sudo ./remove.sh --yes
```

无论是 `master` 还是 `docs` 分支，都不存在 `uninstall.sh`，不论 `docs/INSTALLATION.md` 中写了什么。

不过，这只是操作建议，并非硬性规则。一名克隆其他分支并覆盖现有安装的测试者报告安装无法工作，先卸载后便恢复正常；至少另外两名测试者直接覆盖安装没有遇到问题。非正式共识是大多数人会直接覆盖安装，但没人找出造成差异的因素。

每次安装后，模块旁的 `/lib/modules/$(uname -r)/updates/cmpunlocker/` 目录中都会写入三个元数据文件：

| 文件 | 内容 |
|---|---|
| `driver_version` | 例如 `610.43.03` |
| `card_profile` | `8gb` 或 `10gb` |
| `unlock_geometry` | `64GB` 或 `40GB` |

**内核模块中的任何代码都不会读取这些文件。** 它们只是安装时的记录。打过补丁的内核在启动时唯一会读取的文件，是可选的 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。如果需要确认实际加载的版本，请读取 `cat /proc/driver/nvidia/version`（其中**不应**出现 `dvs-builder`），并使用 `sudo dmesg | grep SEC2_DEBUG` 进行确认。

---

## 本页的未解问题

> [!NOTE]
> **未解问题**
>
> 1. **610.43.02 还是 610.43.03 更可靠？** 这个问题被反复提出，但从未得到回答。
> 2. **595 / 590 / 580 的回移植版本能否启动？** 每个分支只需有一名测试者报告 `dmesg | grep SEC2_DEBUG` 和 `POST-BooterLoad verify` 行，就能得到结论。
> 3. **回移植分支 `VERSION` 中那七个未经验证的次版本是否真的能应用？** 可以通过 `patch -p1 --dry-run` 在离线环境中回答。
> 4. **回移植分支是否会与 Gen2 或多卡系列合并。** 这些分支是独立开发的，目前选择其中一个就意味着放弃另一个。合并在结构上并不复杂，因为回移植只改变 `PATCH_DIR` 的计算方式；但仍需针对 580、590 和 595 的源码重新生成 Gen2 补丁 `0007` 和 `0008`。
> 5. **WSL 和 HiveOS 支持。** 两者都有人询问过，但都没有得到回答，也没有任何一方的证据。

---

## 相关页面

- [六个驱动补丁](../unlock/driver-patches.md)
- [安装](install.md) 和[验证](verify.md)
- [排障](troubleshooting.md)
- [多卡](multi-gpu.md)
- [PCIe Gen2](../unlock/pcie-gen2.md)
- [未解问题](../frontier/open-questions.md)
