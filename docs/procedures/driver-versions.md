# 驱动版本：支持什么、为什么

## 本页覆盖内容

CMP 170HX 解锁针对哪些 NVIDIA 驱动版本构建、为什么清单这么短、把安装器指向任何其它东西会发生什么、以及未发布回移植分支对 595、590 和 580 实际提供什么。

短答案：**出货 `master` 恰好支持两个版本，`610.43.03`（默认）和 `610.43.02`，按精确字符串匹配。对任何其它版本构建硬失败。** 两者都在真实硬件上启动测试过。610 以下的一切只存在于一个未发布分支上、是源码验证的、而且从没被记录在案的任何人启动测试过。

注意那个让人绊倒的区别：170HX 在普通出厂商 NVIDIA 驱动上完美运行。它只是不在它们上**解锁**。能被驱动和能被解锁是分开的问题。

---

## `master` 上的支持清单

`driver/VERSION` 含两行、按此顺序：

```text
610.43.03
610.43.02
```

第一行是默认构建目标。`common/constants.yaml` 在 `driver_versions` 下镜像同样的两个。`install.sh` 和 `driver/build.sh` 都把 `driver/VERSION` 读进 `SUPPORTED_VERSIONS` 并调用一次精确字符串 `version_supported()`。没有范围检查、没有 "610 or newer" 比较、没有模糊匹配。

如果你的已安装驱动不是那两个之一，安装死掉、带：

```text
Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.
```

### 如何检测已安装版本

`install.sh` 试四个来源、按顺序、在第一个产出版本的来源处停止：

| 顺序 | 来源 |
|---|---|
| 1 | `/proc/driver/nvidia/version` |
| 2 | `nvidia-smi --query-gpu=driver_version` |
| 3 | 一次对 `/lib/firmware/nvidia/<supported>/` 的目录探测 |
| 4 | `/lib/firmware/nvidia/` 下排序最高的目录 |

然后构建下载匹配的上游源码 tarball：

```text
https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz
```

它被缓存在 `driver/.build/` 下、每次运行干净重新解压。cmpunlocker 仓库本身不运送任何 NVIDIA 代码。

> [!NOTE]
> **下载无校验和**
>
> `build.sh` 用 `curl -L --fail` 抓取 tarball、不验证任何东西。树里任何地方都没有记录的 SHA-256。在 `driver/VERSION` 或 `common/constants.yaml` 里记录每个版本的预期哈希是一个明显、未实现的改进。

---

## 为什么恰好 610.43.0x

四个原因、按硬度递减。

**补丁 hunk 锚定到那个源码树。** 六个补丁文件在 `set -euo pipefail` 下用 `patch -p1` 应用。单个被拒 hunk 就中止构建。`kernel_gsp.c`、`g_kernel_gsp_nvoc.h`、`osinit.c`、`kernel_gsp_tu102.c` 和 `nv.c` 里的行号、周围上下文和结构布局都在上游发布之间移动。见[六个驱动补丁](../unlock/driver-patches.md)。

**解锁必须是开源内核模块的补丁。** 专有 NVIDIA 驱动 "has different boot paths and cannot be patched the same way"（有不同的引导路径、无法以同样方式打补丁）。开源模块在 GA100 上也是仅 GSP：用 `NVreg_EnableGpuFirmware=0` 加载直接以 `0x62` 固件初始化错误失败，所以这颗硅片上没有 CPU-RM 逃生口。

**610 是既定下限。** 维护者本人被问及与第三方 P2P 驱动共存时的措辞是 "it needs to be **610 or above**"（它需要是 **610 或以上**）。实践中 `master` 比那句话更严格：它拒绝任何不是两个白名单字符串之一的东西。

**两个版本都有野外证据。** 来自两台机器的独立运行时捕获：

```text
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64 610.43.02 Release Build
              (dvs-builder@U22-I3-H05-01-2) Tue May 19 11:24:27 UTC 2026
GCC version:  gcc version 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1)
kernel:       6.8.0-136-generic
```

> [!WARNING]
> **那份捕获来自解锁没触发的一台机架**
>
> 把它读作 `610.43.02` 存在且能安装的证据、不是它解锁了的证据。`dvs-builder` 构建字符串是 NVIDIA 自己的，所以那里加载的模块是**出厂**那个、不是打过补丁的；在同一台机架上 `verify.sh` 报告每张 GPU `MISSING`、`dmesg` 里没有 `SEC2_DEBUG` 行。不要把这个块里的 gcc 或内核版本读作一个已知良好的构建环境。

以及，分开地，`NVIDIA-SMI 610.43.03 / KMD Version: 610.43.03 / CUDA UMD Version: 13.3`。一个流传的打包 NixOS 模块硬断言 `config.hardware.nvidia.package.version == "610.43.03"`。

每个实验性分支、包括整个 PCIe Gen2 谱系和 80 GB 尝试，也只列 `610.43.03` 和 `610.43.02`。回移植分支是唯一例外。

---

## `610.43.02` 还是 `610.43.03`？

> [!NOTE]
> **未解问题**
>
> 没人回答过这个。"is 610.43.02 or 610.43.03 more reliable?"（610.43.02 还是 610.43.03 更可靠？）这个问题在频道里于 2026-07-24 被直接问、从未回答。两个版本上都有成功解锁。`610.43.03` 只是因为它排在 `driver/VERSION` 第一行才是默认。
>
> 实验很琐碎、没人跑过：从现有已安装基收集 `driver_version` 元数据文件加 `SEC2_DEBUG` PLM-打开成功率并比较。

实用指导：**取 `610.43.03`，默认那个。** 如果一张卡在其中之一上拒绝干净解锁，试另一个是廉价且合法的诊断步骤，但没有任何一方证据说它会有帮助。

---

## 钉住

> [!WARNING]
> **理性建议、不是测量结果**
>
> 推荐的对未来 NVIDIA 驱动堵上这个洞的长期缓解是**把驱动钉在 610**、与 P100 和 V100 操作者钉在约 580 一样。至少一位操作者已经把包钉住作为预防。这是未受挑战的推理、而非被演示的需求：不存在阻断性的驱动，而且 GitHub 上已发布的开源内核模块无法被召回。

---

## 出厂驱动：能驱动、不解锁

170HX 在完全未打补丁的驱动上枚举并跑 CUDA。Ubuntu 24.04 上 `nvidia-driver-570` 配 CUDA 12.8 开箱即用，Ubuntu 22.04 上 `nvidia-driver-535-server` 也被报告可工作。`nvidia-smi` 在计算能力 8.0 下把卡叫 `NVIDIA Graphics Device`，因为驱动的 PCI ID 表没有 `0x20C2` 的市场名。那个命名怪癖是确认你在看一颗 CMP 部件的快捷方式。

出厂驱动下卡是锁定的：出厂容量、出厂算力节流、PCIe Gen1 x4。

---

## 随版本同行的硬要求

| 要求 | 详情 |
|---|---|
| 安全启动 | 必须**关**。打过补丁的模块未签名；开着时 dmesg 显示 `nvidia: module verification failed: signature and/or required key missing - tainting kernel`。`/sys/firmware/efi` 存在、`mokutil` 存在且 `mokutil --sb-state` 报告启用时，`install.sh` 死掉、带 `Secure Boot is enabled. Disable it before installing unsigned patched modules.` 在非 EFI 系统、或没装 `mokutil` 的系统上，检查被静默跳过。 |
| 驱动家族 | 仅 nvidia-open。专有 blob 无法以同样方式打补丁。 |
| 操作系统 | **仅 Linux。** GSP 引导路径是 Linux 专属；Windows WDDM 驱动根本不同。 |
| 内核头文件 | `/lib/modules/$(uname -r)/build` 必须存在。 |
| 工具链 | 需要 `python3`。`master` 上**没有 PyYAML**、出货脚本里任何地方**没有显式 GCC 版本检查**。"Requires gcc 13+ and PyYAML" 来自第三方 `unlock-cmp-170hx` 指南仓库（加六个分支上的一个残留 `requirements.txt`），不是 cmpunlocker。泄露包的 README 只要 root 和内核头文件。 |
| 网络 | 首次安装需要、用于抓取上游 tarball。 |

完整流程见[安装](install.md)、还原见[卸载](uninstall.md)。

---

## 回移植分支：`clanker/driver-port`

> [!WARNING]
> **实验性：源码验证、从未启动测试**
>
> 595、590 和 580 支持是一个未发布分支。它自己的 README 逐字声明：
>
> > `595.71.05, 590.48.01, and 580.105.08 are source-verified (patches apply cleanly and the unlock logic matches the 610.43.0x path) but have not yet been boot-tested on physical CMP 170HX hardware.`
> > （`595.71.05、590.48.01 和 580.105.08` 是源码验证的（补丁干净应用、解锁逻辑匹配 610.43.0x 路径）但还没在物理 CMP 170HX 硬件上启动测试过。）
>
> 该分支于 2026-07-21 宣布、带一个明确的测试者请求。**截至 2026-07-28 记录任何地方都没有成功确认。** 在一张卡启动前、把一次成功构建当作无证据。

分支 tip `153cd6d`、2026-07-21。

### 它改变什么

几乎没有结构性东西。`driver/patches/` 变成四个按主版本号的子目录、每个持有同样的六个补丁文件名，而 `build.sh` 获得一个两行编辑：

```diff
-PATCH_DIR="${SCRIPT_DIR}/patches"
+BRANCH="${VERSION%%.*}"
+PATCH_DIR="${SCRIPT_DIR}/patches/${BRANCH}"
```

分支上的 `install.sh` 与 master **逐字节相同**：单 GPU、`head -1`、没有 `verify.sh`、没有 `gpu_inventory`。如果你还想要多卡或 PCIe Gen2，你无法从这个分支得到它们。见[多卡](multi-gpu.md)。

### 是一次重新锚定练习、不是重写

每个寄存器值、PLM 条目、载荷偏移量、静态信息重写和 PMA 函数在全部四个目录里都逐字符相同。具体说：

- 补丁 `0004` 和 `0005` 在全部四个版本目录里逐字节相同（相同 md5）。
- 补丁 `0002` 和 `0006` 在 590 和 610 之间逐字节相同。
- `0003` 新增的 `+` 行在全部四个里相同。
- `0001` 新增的 `+` 行在 610 与 580/590/595 之间按**恰好一个额外加的空行**不同、其它什么也不差。

### 每个目录的补丁大小

| 目录 | 0001 | 0002 | 0003 | 0004 | 0005 | 0006 | 总计 |
|---|---|---|---|---|---|---|---|
| `580` | 19,700 | 3,957 | 10,377 | 861 | 1,642 | 497 | **37,034** |
| `590` | 19,647 | 3,988 | 10,377 | 861 | 1,642 | 603 | **37,118** |
| `595` | 19,638 | 3,957 | 10,364 | 861 | 1,642 | 531 | **36,993** |
| `610` | 19,741 | 3,988 | 10,580 | 861 | 1,642 | 603 | **37,415** |

`610` 目录是 **`master` 补丁集的逐字节副本**。移植里没有任何东西改变出货路径。

### 移植必须吸收的上游分歧

其中只有一个是语义的；其余是上下文和锚点漂移。

| 分歧 | 610 | 595 | 590 | 580 |
|---|---|---|---|---|
| `_kgspCreateSignatureMemdesc` 里的 Memdesc 标志 | 门控在 `if (confComputeForceUnprotAlloc(pGpu))` | `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` 无条件 | 与 595 相同 | 与 595 相同 |
| `osinit.c` 里晚期-PMA 钩子上下文 | 跟在 `goto shutdown;` 后 | 跟在 `goto shutdown;` 后 | 跟在 `consoleDisabled = NV_FALSE;` 后 | 跟在 `consoleDisabled = NV_FALSE;` 后 |
| GSP 静态信息尾上下文 | `NV_ASSERT_OK_OR_GOTO(status, kgspInitGspTraceCrashBuffer(...), done);` | 存在 | **缺失** | 存在 |
| 静态信息 hunk 锚点 | `@@ -5164` | `@@ -5070` | `@@ -4065` | `@@ -4198` |
| `KernelGsp` 字段插入锚点 | `@@ -544,6 +544,8 @@` | `@@ -541` | `@@ -525` | `@@ -524` |
| 插入点后跟的字段 | `GspSystemInfo *pSystemInfo; NvU32 regTableSize; PACKED_REGISTRY_TABLE *pRegTable;` | 与 610 相同 | `LIBOS_LOG_DECODE logDecode; LIBOS_LOG_DECODE logDecodeVgpuPartition[48]; RM_LIBOS_LOG_MEM rmLibosLogMem[7];` | 与 590 相同 |
| 补丁 0006 尾上下文 | `(void)rm_get_gpu_uuid_raw(sp, nv);` | 与 610 相同 | 与 610 相同 | `{ const NvU8 *uuid = rm_get_gpu_uuid_raw(sp, nv);` |
| 补丁 0006 锚点 | `@@ -1521` | `@@ -1531` | `@@ -1521` | `@@ -1481` |
| 补丁 0002 邻近符号 | `void kgspConfigureFalcon_TU102(` | `static NvBool _kgspIsProcessorSuspended(OBJGPU *pGpu, void *pVoid);` | 与 610 相同 | 与 595 相同 |
| 补丁 0002 锚点 | `@@ -57` / `@@ -545` / `@@ -565` | `@@ -55` / `@@ -500` / `@@ -520` | 与 610 相同 | `@@ -54` / `@@ -516` / `@@ -536` |

无保护分配差异是唯一行为性的、它让 610 前的树稍微更宽松而非更紧。

### 版本清单内部不一致

> [!CAUTION]
> **十二个白名单版本里七个没有验证过的补丁锚点**
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
> 却只有**四**个补丁目录存在，而 `build.sh` 用 `BRANCH="${VERSION%%.*}"`、即**仅按主版本号**选一个。所以 `595.45.04` 用 `595.71.05` hunk 打补丁、`580.65.06` 用 `580.105.08` hunk 打补丁。十二个里五个带一些证据：`610.43.03` 和 `610.43.02` 启动测试过，`595.71.05`、`590.48.01` 和 `580.105.08` 是分支 README 叫源码验证的那三个。剩下七个（`595.58.03`、`595.45.04`、`580.95.05`、`580.82.09`、`580.82.07`、`580.76.05`、`580.65.06`）完全依赖 `patch -p1` 模糊匹配。
>
> 同时同一分支上的 `common/constants.yaml` 只列**五**个版本（`610.43.03`、`610.43.02`、`595.71.05`、`590.48.01`、`580.105.08`）、与 `VERSION` 不一致。`install.sh` 接受十二个中任何一个，所以用户无需做任何不寻常的事就能到达未验证状态。
>
> 这里的失败风险是读代码的推理推断、不是观察到的补丁拒绝。测试完全离线且机械：下载七个额外 tarball 中的每一个、对着主版本补丁目录跑 `patch -p1 --dry-run`。不需要硬件。

---

## 你该跑哪个？

| 情况 | 推荐 |
|---|---|
| 正常安装、一张卡、想要它工作 | `master` 在 **610.43.03** 上。这是唯一有广泛一手确认的组合。 |
| 一张卡、610.43.03 行为异常 | 试 **610.43.02**。两者都白名单、两者都产出过成功解锁。 |
| 多张 170HX 卡 | `master` 有效、并已在多卡主机上确认过、包括 Proxmox 直通下的 8 张卡。注意 `install.sh` 自动检测危险、显式传 `--profile`。见[多卡](multi-gpu.md)。 |
| 你需要 PCIe Gen2 | 仅分支、且仅 610。见[PCIe Gen2](../unlock/pcie-gen2.md)。 |
| 你被另一个应用钉在 595、590 或 580 | 回移植是你唯一选择、而你会是第一个启动它的人。在你能承受弄坏的机器上做、并无论如何报告 `POST-BooterLoad verify` 行。 |
| 你想让 170HX 与 Volta 或 Maxwell 卡共存 | 这正是 580 回移植的动机：580 覆盖从 980 Ti 到 A100 的一切。移植以源码形式、别无它处地回答了它。 |

> [!CAUTION]
> **裸机上的驱动补丁开发是破坏性的**
>
> 一位开发者报告每次搞砸 `nvidia.ko` 部署后就需要重装操作系统。公认的补救是在 VM 或容器里测试修改过的驱动。对 Proxmox 直通具体说，用 **SeaBIOS、不要用 UEFI/OVMF**：UEFI 产生看起来恰好像利用根本不工作的 RM init 和适配器失败，而那个误诊让至少两人花掉大量时间。

---

## 切换版本或分支

受支持路径是**先卸载、再安装**。维护者的措辞："In fact, I would always recommend to remove the old one before adding the new one."（事实上，我总是建议在加新的之前移除旧的。）

```bash
sudo ./remove.sh --yes
```

没有 `uninstall.sh`、在 `master` 或 `docs` 分支上都没有、不管 `docs/INSTALLATION.md` 说什么。

话虽如此，这是指导而非硬规则。一位克隆了不同分支、在现有安装之上安装的测试者报告它不工作、先卸载就修好了；至少另两位测试者在上层安装没有问题了，非正式共识是大多数人就直接装上去。没人识别出区分因素。

任何安装后，三个元数据文件被写在模块旁的 `/lib/modules/$(uname -r)/updates/cmpunlocker/`：

| 文件 | 内容 |
|---|---|
| `driver_version` | 例如 `610.43.03` |
| `card_profile` | `8gb` 或 `10gb` |
| `unlock_geometry` | `64GB` 或 `40GB` |

**内核模块里没有任何东西读它们。** 它们是安装时记账。打过补丁的内核引导时唯一读的文件是可选 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。如果你需要知道实际加载的是哪个版本，读 `cat /proc/driver/nvidia/version`（它**不应**说 `dvs-builder`）并用 `sudo dmesg | grep SEC2_DEBUG` 确认。

---

## 本页的开放问题

> [!NOTE]
> **未解问题**
>
> 1. **610.43.02 还是 610.43.03 更可靠？** 被反复问、从未回答。
> 2. **595 / 590 / 580 移植能启动吗？** 每个分支一位测试者报告 `dmesg | grep SEC2_DEBUG` 和 `POST-BooterLoad verify` 行就定论了。
> 3. **移植分支 `VERSION` 里那七个未验证的点发布能应用吗？** 可用 `patch -p1 --dry-run` 离线回答。
> 4. **移植分支和 Gen2 或多卡谱系会不会合并。** 它们独立开发。当前选一个意味着放弃另一个。合并结构上简单、因为移植只改 `PATCH_DIR` 计算，但需要针对 580、590 和 595 源码重新生成 Gen2 补丁 `0007` 和 `0008`。
> 5. **WSL 和 HiveOS 支持。** 两者都被问过、都没回答、任何一方都没有证据。

---

## 相关页面

- [六个驱动补丁](../unlock/driver-patches.md)
- [安装](install.md) 和[验证](verify.md)
- [排障](troubleshooting.md)
- [多卡](multi-gpu.md)
- [PCIe Gen2](../unlock/pcie-gen2.md)
- [未解问题](../frontier/open-questions.md)
