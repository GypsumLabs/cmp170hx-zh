# 故障排查

**本页覆盖内容。** 本页按实际症状索引 CMP 170HX 解锁的所有已记录失败模式，包括 dmesg 字符串、Xid 编号、Booter 状态码、`RmInitAdapter` 三元组、`nvidia-smi` 读数、构建错误以及主机层面的异常。每个条目都说明症状、已确认的原因和修复方法；证据不足之处会标注置信度。

**从这里开始。** 下面两条命令可以回答大多数问题：

```bash
sudo dmesg | grep SEC2_DEBUG      # 解锁路径跑了吗，它回读了什么？
nvidia-smi                        # 8 GB 卡 -> ~65536 MiB，10 GB 卡 -> ~40960 MiB
```

如果 `dmesg | grep SEC2_DEBUG` 完全没有输出，说明打过补丁的模块从未运行：请转到[已安装但仍是出厂状态](#stock-memory)。如果有输出，且 PLM 行已经达到目标值，但显存仍显示出厂容量，请转到[显存仍显示出厂大小](#stock-memory)并检查 initramfs。如果引导根本没有进行到这一步，请转到[GSP 引导失败](#gsp-boot)。

以下两条规则可以避免大多数误判：

1. **`WPR_CFG` 读到 `0xfffff0ff` 是正确的。** 四个权限级别掩码（PLM）中只有三个目标值是 `0xffffffff`。见[PLM 回读值](#benign-wprcfg)。
2. **PLM 尝试阶段的 Booter 状态 `0x31` 和 `0xffff` 是预期现象。** 解锁过程本来就会让这些运行失败。真正需要关注的只有 `SEC2_DEBUG: normal BooterLoad status=0x0`。见[PLM 尝试阶段的 Booter 错误](#benign-booter-31)。

---

## 症状索引 { #index }

| 你看到的 | 去往 |
|---|---|
| dmesg 里完全没有 `SEC2_DEBUG` 行 | [已安装但仍是出厂状态](#stock-memory) |
| 安装后 `nvidia-smi` 显示 8192 MiB 或 10240 MiB | [显存仍显示出厂大小](#stock-memory) |
| `[WARN] Loaded nvidia srcversion (…) != patched (…)` | [srcversion 不匹配](#srcversion-mismatch) |
| `Resolved nvidia.ko is not under updates/cmpunlocker/` | [模块解析](#module-resolution) |
| `nvidia-smi`: driver/library version mismatch | [版本不匹配](#version-mismatch) |
| 解锁曾经生效、但关机后不再保持 | [解锁不持久](#not-persistent) |
| 安装器什么都没做就退出 | [安装器拒绝运行](#install-refuses) |
| `Could not detect 8GB vs 10GB card` | [档位检测](#profile-detect) |
| `This card reports 0x…; install will continue` | [第三个设备 ID `20b0`](#device-id-20b0) |
| `WPR_CFG=0xfffff0ff` 看起来不对 | [PLM 回读值](#benign-wprcfg) |
| `Booter failed with non-zero error code: 0x31` | [良性 Booter 错误](#benign-booter-31) |
| `dmem.bin not found (0x59)` | [缺失 `dmem.bin`](#benign-0x59) |
| `Skipping BTF generation … vmlinux` | [良性构建噪声](#benign-btf) |
| `[drm] No compatible format found` | [良性 DRM 消息](#benign-drm) |
| `cudaHostRegister of 439781.26 MiB failed` | [良性 llama.cpp 警告](#benign-cudahostregister) |
| 卡显示为一个通用的 "NVIDIA display device" | [通用枚举](#benign-generic-device) |
| `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042)` | [Gen2 重训练假阴性](#benign-retrain-false-negative) |
| `unexpected WPR2 already up, cannot proceed with booting GSP` | [WPR2 已 up](#wpr2-already-up) |
| `RmInitAdapter failed! (0x62:0x40:2028)` | [WPR2 已 up](#wpr2-already-up) |
| `RmInitAdapter failed! (0x62:0x55:2028)` | [状态码目录](#codes-rminit) |
| `RmInitAdapter failed! (0x62:0x65:2028)` | [状态码目录](#codes-rminit) |
| `RmInitAdapter failed! (0x62:0x40:2674)` | [第二 GPU 初始化失败](#rminit-2674) |
| `RmInitAdapter failed! (0x62:0xffff:2119)` 带 Booter `0x29` | [脏的 SEC2 退出](#rminit-2119) |
| `RmInitAdapter failed!` `0x24:0x72`、`BAR 0/BAR 2 failed.` | [BAR2 自检失败](#bar2-0x72) |
| `GSP didn't boot`、状态 `0x65` | [GSP 超时 `0x65`](#gsp-0x65) |
| Xid 119、60 秒、函数 4097 `GSP_INIT_DONE` | [Xid 119，60 秒](#xid119-60s) |
| Xid 119、6 秒、函数 103 `GSP_RM_ALLOC` | [Xid 119，6 秒](#xid119-6s) |
| Booter 错误 `0x35` | [Booter `0x35`](#booter-0x35) |
| PG199 / A100D 上的 Booter 错误 `0x54` | [Booter `0x54`](#booter-0x54) |
| `rpc_result = 0xFFFF`、NULL `GSP-LOG[RM]` | [RM init 早期停滞](#rpc-ffff) |
| `falconMailbox 0:00000031`、`riscvPc 00000000` | [Falcon 核心转储](#falcon-coredump) |
| `0xbadfXXXX` 寄存器读 | [`0xbadf` 分类](#codes-badf) |
| 执行利用后没有任何变化、`resetPLM 0xff -> 0x8f` | [总线主控被清除](#bus-master) |
| `PLMs: 1/9 open (fired 8 closed)`、`resetPLM=0x00cf` | [驱动仍已加载](#driver-loaded) |
| `modprobe -r nvidia` 拒绝、`nvidia 15835136 2` | [模块不肯卸载](#module-stuck) |
| DMEM 写被静默丢弃 | [DMEM 在 HS 中锁定](#dmem-locked) |
| CFG1 写弹回 `0x02449000` | [PLM 打开与写之间的 FLR](#flr-between) |
| 卡运行数天后出现“退化”、`SEC2 MBOX0 = 0x0` | [已删除的固件目录](#firmware-deleted) |
| 内核交换后构建失败 | [构建失败](#build) |
| 安装解锁器后 PCIe 仍在 Gen1 | [Gen2 停在 Gen1](#gen2-still-gen1) |
| 黑屏、文本控制台、`cmpretrain.service` 失败 | [黑屏](#black-screen) |
| Xid 31、`FAULT_INFO_TYPE_REGION_VIOLATION` | [Xid 31](#xid31) |
| 杀掉一个 CUDA 作业后 Xid 45 | [Xid 45](#xid45) |
| 过度配置的卡上 Xid 154 | [Xid 154](#xid154) |
| vLLM 在 `gpu-memory-utilization 0.95` 崩溃 | [vLLM 余量](#vllm) |
| 到处 `cuInit` 返回 999 | [`cuInit` 999](#cuinit999) |
| gpu-burn 报告数千个显存错误 | [老化测试错误](#burn-errors) |
| `nvidia-smi --gpu-reset`: "GPU is being used by another process" | [复位拒绝](#gpu-reset-busy) |
| 解锁工作但 CUDA 不 | [一台主机上 CUDA 坏](#cuda-clean-host) |
| 多卡机架：每张卡都停在出厂 | [静默多卡失败](#multicard) |
| 服务器装上卡后无法 POST | [主机无法启动](#no-post) |
| 卡运行一小时后从总线掉线 | [卡从总线掉线](#off-bus) |

---

## 1. 健康的引导应是什么样 { #healthy-boot }

一次成功的解锁引导会按以下顺序打印这些 `SEC2_DEBUG` 行：

1. `SEC2_DEBUG: saved stock signature (4096 bytes)`、紧跟
   `SEC2_DEBUG: <path> not found (0x59), using built-in payload`
2. WPR meta 转储：`SEC2_DEBUG: WPR meta fbSize=… wprEnd=… heapSize=…`
3. `SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x`
4. 四条 `SEC2_DEBUG: PLM[%u] %s(0x%x) attempt=%u status=0x%x reg=0x%08x` 行
5. `SEC2_DEBUG: PLMs: FEAT=… FBPA=… WPR=… WPR_CFG=…`
6. `SEC2_DEBUG: POST-WRITE SS0=… SS1=… CFG1=… LMR=… (devId=0x%x)`、仅在失败后跟
   `SEC2_DEBUG: rebuild stock signature failed: 0x%x`
7. `SEC2_DEBUG: WPR meta updated fbSize=… wprStart=… wprEnd=… heapOffset=… heapSize=…`
8. `SEC2_DEBUG: normal BooterLoad status=0x0`
9. `SEC2_DEBUG: POST-BooterLoad verify PLM=… SS0=… SS1=… CFG1=… LMR=…`
10. GSP static-info BEFORE/AFTER 对

两个签名打印都来自 `_kgspCreateSignatureMemdesc`，该函数在 `_kgspBootGspRm` 之前运行，因此这两行会出现在整个过程的开头，而不是序列中间。`POST-BooterLoad verify` 行才是决定性的证据：它是在真实 GSP 引导**之后**回读得到的，证明解锁状态仍然存在。

**预期值：**

| 日志字段 | 预期 | 备注 |
|---|---|---|
| `PLM[0] WPR_CFG(0x1fa7cc)` | `reg=0xfffff0ff` | 不是 `0xffffffff` |
| `PLM[1] FBPA(0x9a0148)` | `reg=0xffffffff` | |
| `PLM[2] WPR(0x1fa7c4)` | `reg=0xffffffff` | |
| `PLM[3] FEAT(0x823804)` | `reg=0xffffffff` | AON 常电域，能够挺过 FLR |
| 任何 PLM 行中的 `status=` | `0xffff` | 这是预期值；应以回读结果为准 |
| `SS0 (0x0082381c)` | `0x88888888` | 锁定卡读例如 `0x53540175` |
| `SS1 (0x00823820)` | `0x00000008` | |
| `CFG1 (0x009a0204)` | `0x02779000`（8 GB 卡）/ `0x02669000`（10 GB 卡） | 出厂两个都 `0x02449000` |
| `LMR (0x00100ce0)` | `0x0000020B`（8 GB 卡）/ `0x0000028A`（10 GB 卡） | 出厂 `0x00000208` / `0x00000288` |
| `normal BooterLoad status` | `0x0` | 唯一必须为零的状态 |

`POST-WRITE` 中出现任何其他 CFG1/LMR 配对，都说明当前使用了错误的档位配置。各值的含义见[显存几何布局](../unlock/memory-geometry.md)。

共有三个日志标签，全部以 `LEVEL_ERROR` 级别输出，因此无需额外的调试标志即可看到：

| 标签 | 由谁发出 | 内容 |
|---|---|---|
| `SEC2_DEBUG` | 补丁 0001、0002、0003 | PLM、寄存器和 Booter 阶段：0001 中有 14 个日志字符串，0002 中有 7 个，0003 另有 `late PMA extension status=0x%x` |
| `SEC2_DEBUG_HEAP` | 补丁 0003 | `fbAddrSpace=%lluMB mapRam=%lluMB fbTotal=%lluMB fbUsable=0x%llx heapTotal=0x%llx regionBytes=0x%llx publicBytes=0x%llx numRegions=%u`（一个字符串） |
| `SEC2_DEBUG_LATE_PMA` | 补丁 0003 | 每-FB 区域描述符加 `pma_total 0x%llx->0x%llx pma_free 0x%llx->0x%llx`（10 个字符串） |

**完整验证块：**

```bash
nvidia-smi                                                     # ~65536 MiB 或 ~40960 MiB
nvidia-smi --query-gpu=memory.total,clocks.max.sm --format=csv
sudo dmesg | grep SEC2_DEBUG
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile  # 8gb 或 10gb
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry
```

一份归档的正常结果原样显示为 `65536 MiB, 1935 MHz`。注意，`clocks.max.sm = 1935 MHz` 只是**报告字段**，并不代表实际可达到的时钟频率：持续 SM 时钟为 1410 MHz，使用 `-pl 300` 时为 1470 MHz。见[性能](../operations/performance.md)。

完整安装后清单见[验证](verify.md)。

---

## 2. 看起来像失败却不是的消息 { #benign }

### 2.1 PLM 尝试阶段的 Booter 错误 { #benign-booter-31 }

**症状。**

```text
s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31
kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff
```

后面紧跟一条在 `reg=` 中显示目标值的 PLM 行。

**为什么这不是问题。** 补丁 0001 会在每次 PLM 尝试中故意用利用载荷覆盖 GSP 签名缓冲区，因此 Booter Load **本来就应该**拒绝这些运行：等到它报告签名错误时，注入的链已经执行完毕。成功与否只看 PLM 寄存器的回读值，不能看 Booter 状态。最坏情况下，真正的引导 Booter Load 之前会出现 8 次此类失败（4 个 PLM，每个最多尝试 2 次）。

**必须成功的那行**是 `SEC2_DEBUG: normal BooterLoad status=0x0`。

### 2.2 `dmem.bin not found (0x59)` { #benign-0x59 }

```text
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
```

这是正常路径。外部 `dmem.bin` 是通过 `os_open_and_read_file` 读取的开发覆盖接口；`0x59` 是该函数表示“文件未找到”的状态。每次已归档的成功解锁引导都出现过这一行。内置回退载荷以 FBPA PLM 为目标（`writeAddr = 0x009a0148`、`writeValue = 0xffffffff`），之后 PLM 循环会在每次迭代中重新写入目标值。

它前面那行 `SEC2_DEBUG: saved stock signature (4096 bytes)` 确认这个驱动上的出厂 GSP 签名是 4096 字节。

### 2.3 构建期间的 `Skipping BTF generation` { #benign-btf }

```text
Skipping BTF generation for .../nvidia.ko due to unavailability of vmlinux
```

这是良性消息。BTF 是与解锁无关的内核调试元数据；模块仍会正常构建和加载。它可能出现在 `nvidia-peermem.ko`、`nvidia-modeset.ko`、`nvidia-drm.ko`、`nvidia.ko` 和 `nvidia-uvm.ko` 上。之后真正需要关注的是 `[ OK ] Patched NVIDIA modules loaded`。

### 2.4 DRM "no compatible format" 消息 { #benign-drm }

```text
[drm] Initialized nvidia-drm 0.0.0 20160202 ... on minor 1
[drm] No compatible format found
[drm] Cannot find any crtc or sizes
```

这是良性消息。CMP 170HX 没有显示输出。

### 2.5 llama.cpp `cudaHostRegister` 警告 { #benign-cudahostregister }

```text
ggml_cuda_host_malloc: cudaHostRegister of 439781.26 MiB failed: unknown error
```

这不是致命错误：加载会继续，基准测试也能完成。不要把它和会直接终止进程的真实分配崩溃混为一谈。

### 2.6 通用设备枚举 { #benign-generic-device }

在 Linux 监控工具（例如 Mission Center）中，卡被枚举为通用的 "NVIDIA display device" 是正常现象。在出厂驱动上，`nvidia-smi` 也会将其报告为 `NVIDIA Graphics Device`，计算能力为 8.0，因为驱动的 PCI ID 表没有为 `0x20C2` 提供产品名称。这是确认目标确实是 CMP 部件的快捷方法。

### 2.7 Gen2 重训练 "completed without Gen2 link" { #benign-retrain-false-negative }

```text
CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)
```

这是一个**假阴性**：`0x1042` *确实*表示已经训练为 Gen2 x4 链路。解码如下：速度字段 `[3:0] = 2`（5.0 GT/s），位宽字段 `[9:4] = 4`（x4）。驱动的成功条件还要求 `PCI_EXP_LNKSTA_DLLLA`（Data Link Layer Link Active，数据链路层链路激活，位 13，即 `0x2000`）置位；但 `0x1042` 的位 13 为 0，所以链路明明已经是 Gen2，检查仍会失败。报告 `0x7042`（位 13 置位）的主机会从同一段代码打印成功消息。两台主机上的 4 张卡都观察到了这种矛盾组合。

请改用以下任一项确认：

```bash
nvidia-smi --query-gpu=pcie.link.gen.current --format=csv
cat /sys/bus/pci/devices/0000:$BDF/current_link_speed
```

> [!NOTE]
> **未解问题**
>
> DLLLA 位读零是否指示那些主机之间一个真实、尽管良性的链路层差异、而非只是一个报告伪影，从未被调查。

### 2.8 "所有 PLM 必须显示 `0xffffffff`" { #benign-wprcfg }

第三方文档（`docs/DEBUGGING.md`、`docs/ARCHITECTURE.md`，以及发布版 README 中较为温和的一种说法）声称每个 PLM 都应回读为 `0xffffffff`。这个说法过于笼统。发布版的 `plmTable[]` 实际是：

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

而循环的成功谓词是 `if (regVal == plmTable[plmIdx].value)`。一次健康引导打印 `SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff`。

---

## 3. 已安装，但卡仍处于出厂状态 { #stock-memory }

这是最常见的一类报告。解锁代码本身没有问题；要么当前运行的不是打过补丁的模块，要么模块没有获得一次可以实际执行解锁的干净引导。

### 3.1 `nvidia-smi` 显示 8192 MiB 或 10240 MiB { #stock-size }

**原因。** PLM 解锁没有生效，或者出厂模块仍在运行。

**修复。** 检查 `sudo dmesg | grep SEC2_DEBUG`。

* **完全没有输出**：说明打过补丁的模块从未运行。依次排查 3.2 至 3.5。
* **有输出，但 PLM 没有达到目标值**：说明解锁链运行过但失败了。执行一次完全断电关机（仅重启操作系统*不够*）后重试。见[冷启动](recovery.md#cold-boot)。
* **有输出，且 `POST-WRITE` 正确，但显存仍为出厂容量**：问题更可能在第二阶段的显存处理流程，而不是寄存器写入。请收集 `SEC2_DEBUG_HEAP` 和 `SEC2_DEBUG_LATE_PMA` 行，以及 `late PMA extension status=0x%x` 的值。

泄露的发行版 README 采用相同的分诊方法：`nvidia-smi` 显示 65536 MiB 是成功判据，显示 8192 MiB 则表示 PLM 解锁失败。它还要求执行一次**冷**重启，而不是热重启。

### 3.2 srcversion 不匹配 { #srcversion-mismatch }

**症状。**

```text
[WARN] Loaded nvidia srcversion (…) != patched (…)
[WARN] Modules installed but the running driver is still stock (or unload failed).
```

**原因。** 出厂版 `nvidia.ko` 仍驻留，无法卸载。`build.sh` 会尝试热重载（停止 `nvidia-persistenced` 和 `nvidia-fabricmanager`，对 4 个模块执行 `modprobe -r`，然后重新加载），并将 `/sys/module/nvidia/srcversion` 与已安装模块的 `modinfo -F srcversion` 进行交叉核对。

**修复。** 冷重启（`shutdown -h now`、然后上电），然后确认：

```bash
cat /proc/driver/nvidia/version      # 必须不说 dvs-builder
sudo dmesg | grep SEC2_DEBUG         # 必须有输出
```

一位测试者确认冷重启解决了这个问题。

### 3.3 模块解析：出厂模块仍优先 { #module-resolution }

**症状。** `build.sh` 打印 `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`。

这是模块解析问题最早出现的信号。模块优先级为 `updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`，这是普通的 depmod 排序方式（因此不需要 `dpkg-divert`）。`build.sh` 会运行 `depmod -a "${KVER}"`，然后通过 `modprobe -n -v nvidia` 实际验证解析结果。

> [!CAUTION]
> **多 GPU 风险**
>
> 在多 GPU 系统上，打过补丁的 `nvidia.ko` 和出厂版 `nvidia.ko` 可能同时位于同一个 `updates` depmod 搜索项下。此时 **depmod 会任意选择一个，并静默丢弃另一个**。一位测试者将一次多卡失败的根因准确定位到这里：只在 updates 搜索路径中保留 cmpunlocker 版本，重启后确认多卡运行恢复正常。

### 3.4 initramfs 仍携带出厂模块 { #initramfs }

`build.sh` 的分支副本（`memory`、`ecc`、`housekeeping`、`PG199`）逐字保留了这段解释：“NVIDIA often loads from initramfs. If only updates/dkms is packed there, stock modules win at boot even when updates/cmpunlocker is preferred by depmod.”（NVIDIA 经常从 initramfs 加载模块。如果其中只打包了 updates/dkms，那么即使 depmod 更偏好 updates/cmpunlocker，出厂模块仍会在引导时优先加载。）Master 删除了这条注释，但保留了相同的行为：`build.sh` 按可用性依次调用 `update-initramfs -u -k "${KVER}"`、`dracut --force --kver "${KVER}"` 或 `mkinitcpio -P`；如果这些工具都不存在，则警告 `No initramfs tool found, rebuild manually before rebooting`。

这是一条看似合理的“已安装但显存仍显示出厂大小”的可能原因，且排查成本低，值得优先排除。不过，这只是脚本自身的推断，并不是现场已诊断出的失败：资料库中的聊天报告没有任何一处提到 initramfs、initrd、dracut 或 mkinitcpio。如果看到该警告，请手动重建 initramfs，然后执行冷启动。

### 3.5 维护者分诊：三步 { #triage-three-step }

“安装完成但卡仍处于出厂状态”时，标准分诊步骤如下：

```bash
# 第 1 步 - 构建目标是你实际引导的内核吗？
uname -r
ls -la /lib/modules/$(uname -r)/updates/cmpunlocker/
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry

# 第 2 步 - 运行中的模块是打过补丁的那个吗？
modprobe -n -v nvidia
modinfo -F filename,srcversion,version nvidia
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko

# 第 3 步 - 卡和日志说什么？
nvidia-smi --query-gpu=name,memory.total,driver_version,pci.bus_id --format=csv
sudo dmesg | grep -E "SEC2_DEBUG|NVRM|nvidia"
cat /proc/driver/nvidia/version
```

第 1 步中目录缺失，说明构建针对的是不同于当前引导内核的版本。第 2 步中，解析出的路径必须包含 `/updates/cmpunlocker/`，且运行中的 srcversion 必须等于 cmpunlocker `.ko` 的 srcversion；两者不匹配就表示出厂模块仍在运行。

注意，这 3 个元数据文件**仅用于记录元数据**。内核模块不会读取它们；几何布局是在运行时根据 PCI 设备 ID 选择的。`--profile` 检测错误只会写入错误元数据，**不会**导致错误的几何布局。

### 3.6 `nvidia-smi`: driver/library version mismatch { #version-mismatch }

**原因。** 前一个内核模块仍驻留。

**修复，按安全性排序：** 重启；或者重载内核模块；或者安装与之匹配的 `nvidia-smi` 构建。禁用版本不匹配检查只能掩盖问题，不能修复问题。

> [!CAUTION]
> **版本不匹配的 `nvidia-smi` 会静默使所有测量失效**
>
> NVML 拒绝跨版本通信，因此使用版本不匹配的二进制进行解锁验证没有意义。一次持续数天的测量系列就因此作废（用户态为 580.159.03，而内核模块来自另一个构建）。如果用户态和模块版本不同，那么此前取得的每一个 `memory.total` 读数都无效。

### 3.7 解锁没挺过一次关机 { #not-persistent }

**原因。** 系统中残留了旧版 NVIDIA 驱动和/或旧版 `cmpunlocker` systemd 服务。

**修复。** 删除所有旧内核模块**和**旧的 `cmpunlocker` 服务，然后重新安装。当前发布版 `remove.sh` 会同时完成这两项工作：停止、禁用并删除 `/etc/systemd/system/cmpunlocker.service`，终止 `/opt/cmpunlocker/daemon/watchdog.py`，删除 `/lib/modules/*/updates/cmpunlocker/`，针对每个内核运行 `depmod -a`，重建 initramfs，并重新加载出厂模块。见[卸载](uninstall.md)和[恢复](recovery.md)。

当前发布版工具不需要 systemd 守护进程：补丁 0006 为两个设备 ID 设置 `NV_FLAG_PERSISTENT_SW_STATE`，这实际上就是内置的持久化模式。

### 3.8 安装器拒绝运行 { #install-refuses }

`install.sh` 在以下情况下会直接失败，不执行任何操作：

| 条件 | 消息 / 行为 |
|---|---|
| 不是 root | 立即退出 |
| `lspci -nn` 中没有 `10de:20b0`、`10de:20c2` 或 `10de:2082` | 退出 |
| 安全启动启用 | `Secure Boot is enabled. Disable it before installing unsigned patched modules.` |
| `/lib/modules/$(uname -r)/build` 中缺少内核头文件 | 退出 |
| 检测到的驱动不在 `driver/VERSION` 里 | `Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.` |
| 显存总量落在每个档位桶之外 | `Could not detect 8GB vs 10GB card` |

安全启动检查仅在 `/sys/firmware/efi` 存在**且** `mokutil` 位于 PATH 中时执行；在非 EFI 系统或没有 `mokutil` 的系统上，检查会被静默跳过，之后未签名模块会因 `nvidia: module verification failed: signature and/or required key missing - tainting kernel` 而加载失败。

驱动版本检测顺序：`/proc/driver/nvidia/version`，然后 `nvidia-smi --query-gpu=driver_version`、然后扫 `/lib/firmware/nvidia/<supported>/`、然后 `/lib/firmware/nvidia/` 下排序最高的目录。见[驱动版本](driver-versions.md)。

### 3.9 检测到错误的卡档位 { #profile-detect }

`detect_card_profile()` 读取出厂状态下的 `nvidia-smi memory.total`，并按以下范围分档：

| 报告的 `memory.total` | 档位 |
|---|---|
| ≥ 60000 MiB | `8gb`（一张已解锁的 64 GB 卡） |
| 35000 到 59999 MiB | `10gb`（一张已解锁的 40 GB 卡） |
| 7680 到 8704 MiB | `8gb` |
| 9728 到 10752 MiB | `10gb` |
| 其它任何值 | 致命 `Could not detect 8GB vs 10GB card` |

前两个范围的存在，是为了让已解锁卡重新安装时仍能识别出正确档位。如果检测结果错误或 `nvidia-smi` 不可用，可以手动指定：

```bash
sudo ./install.sh --profile=8gb    # 或 --profile=10gb
```

### 3.10 第三个设备 ID `10de:20b0` { #device-id-20b0 }

`install.sh` 检测到 `10de:20b0` 后会发出警告，但继续执行：

```text
In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
This card reports 0x20b0; install will continue, but unlock may not activate.
```

补丁 0001 和 0002 中的每个解锁动作**以及每条 `SEC2_DEBUG` 日志**都只对 `0x20C2` / `0x2082` 生效。它们通过 `_kgspSec2PostblTimingEnabled()` 进行门控，该函数测试 `pGpu->idInfo.PCIDeviceID >> 16`。因此，`20b0` 卡可以正常完成安装，但会沿完全出厂的路径引导，并且在 `dmesg | grep SEC2_DEBUG` 中应当没有任何输出。

> [!NOTE]
> **未解问题**
>
> 一位使用 A100 工程样品晶片（`20B0`、8192 MB、2048-bit、4096 个 CUDA 核心、Samsung 8Hi HBM2）的测试者报告了 `NVRM initialization error`，*并且*称 `SEC2_DEBUG` 证明寄存器确实被写入。出厂构建不可能在 `20B0` 卡上打印这些日志。因此，要么当时运行的是加入了 ES ID 的修改构建，要么这些日志来自同一主机上的另一张卡。现有记录无法判定是哪一种。

---

## 4. GSP 引导失败 { #gsp-boot }

### 4.1 WPR2 已 up { #wpr2-already-up }

**症状。**

```text
NVRM: _kgspBootGspRm: unexpected WPR2 already up, cannot proceed with booting GSP
NVRM: (the GPU is likely in a bad state and may need to be reset)
NVRM: RmInitAdapter: Cannot initialize GSP firmware RM
NVRM: RmInitAdapter failed! (0x62:0x40:2028)
NVRM: rm_init_adapter failed, device minor number 0
```

最后以 `nvidia-smi` 的 `No devices were found` 结束。这是利用执行后最常见的失败之一，至少有 3 位测试者报告了完全相同的现象。

**原因。** 先前的一次 Booter 运行写入了 WPR2 MMU 寄存器，随后却异常中断。因此下一次 modprobe 时，驱动发现 WPR2 已经处于 up 状态，便拒绝继续。

**修复（净室逆向工程阶段）。** 完整卸载驱动，然后通过 `echo 1 > /sys/bus/pci/devices/0000:BDF/reset` 执行 FLR；如果仍不行，则执行一次冷断电循环。

当前发布版补丁还会在 PLM 循环前保存一次 `0x001fa824` / `0x001fa828` 中的 WPR2 lo/hi 值，在**每一次** Booter Load 尝试前重写这两个寄存器，并在循环结束后再次重写。它从不清除这两个寄存器。

### 4.2 Xid 119，60 秒超时，函数 4097 { #xid119-60s }

**症状。**

```text
Xid 119: Timeout after 60s of waiting for RPC response from GPU0 GSP!
  Expected function 4097 (GSP_INIT_DONE)
GSP RPC buffer contains function 4098 (GSP_RUN_CPU_SEQUENCER)
kflcnWaitForHalt_TU102: Timeout waiting for Falcon to halt
NV_ERR_TIMEOUT (0x00000065)  from kflcnWaitForHalt_HAL at kernel_gsp.c:5386 (or :5449)
falconMailbox 0:00000031
... then: WPR2 already up
```

**原因。** GSP RISC-V 核心从未到达 RM init：引导过程是**卡住**的，而不是被拒绝。

**修复。** 先复位以清除 WPR2，再重试：首先使用 FLR；如果 FLR 未能清除它，则使用 SBR 或执行冷断电循环。见[恢复](recovery.md)。

**支持细节。** 前面的 `_threadNodeCheckTimeout` 显示 Falcon 停止等待超时为 4000 ms；GSP 事件本身耗时 59 秒。在一次捕获中，CPU 到 GSP 的 RPC 历史只有条目 0 `SET_REGISTRY` 和条目 -1 `GSP_SET_SYSTEM_INFO`，说明 GPU 从未越过早期引导阶段。该现象在 2 台主机、2 个内核和 2 个驱动构建（580.159.03 和 580.167.08）上都被捕获过。

### 4.3 Xid 119，6 秒超时，函数 103 { #xid119-6s }

**这是与 4.2 不同的失败。** 应根据函数编号和超时时长区分两者。

**症状。** Xid 119 带 6 秒超时和函数 103（`GSP_RM_ALLOC`）、在一次部分成功的引导之后：GPU 到达一个运行状态（nvidia-drm 已加载、`GSP_RM_CONTROL` 和 `FREE` RPC 在 224 到 5222 µs 内完成），然后每次 `nvidia-smi` 挂起、对连续序号（184、185、186）重复 Xid 约每 6 秒一次。

**修复。** 复位显卡；这种状态无法在原地恢复。

### 4.4 `GSP didn't boot`，状态 `0x65` { #gsp-0x65 }

**症状。** dmesg 里 `GSP didn't boot` 带状态 `0x65`。

**原因。** 构造的签名缓冲区或 Booter 序列使 GSP 无法启动。`0x65` 是驱动侧的 `NV_ERR_TIMEOUT`。

**修复。** 完全断电循环并重试。对报告它的测试者来说，只移除旧内核模块**不足够**。

> [!CAUTION]
> **`0x65` 不是 `0x31`**
>
> `0x65` 是驱动侧 `NV_ERR_TIMEOUT`；`0x31` 是一个邮箱值。它们发生在不同阶段。决定性测试：WPR2 错误来自寄存器写本身，而一个完全没有写的两加载过程仍撞上 `0x65`。一条声称两个码是同一回事的早期说法、在一小时内被一次受控的无写运行反驳。

为什么 FLR 有时无法恢复 `0x65` 卡死状态，见[恢复](recovery.md#flr-vs-sbr)。

### 4.5 Booter 错误 `0x35` { #booter-0x35 }

**症状（仅限独立运行的无驱动工具）。** Booter 返回 `0x35`。

**原因。** `regtable_rw_indexed` 读取 DMEM `0x2383` 和 `0x8e08` 处的寄存器描述符表时读到了零。出厂签名只有 `0x1000` 字节，因此其 DMA 只到达 DMEM `0x17FF`，不会破坏这些表。利用载荷必须为 `0xF800` 字节，使其帧到达 `0xF748` 处的栈；这样 DMA 会将 DMEM `0x0800` 到 `0xFFFF` 的内容覆盖，并把这些表清零。MAIN.6 阶段在 DMA 前读取完整的表，MAIN.7 阶段在 DMA 后验证到表已清零，于是触发 `0x35`。

**修复（无驱动路径）。** 在载荷偏移 `0x1B83`（DMEM `0x2383`）和 `0x8608`（DMEM `0x8E08`）处加入原始出厂表内容。这些内容不存在于任何平面文件中，而是由 bootloader 在运行时根据 bootloader 代码和/或 boot descriptor 中的常量生成；因此，重建这些内容本身就是一个重要的子问题。加入修复后，研究者立即报告 GSP-RM 成功启动。

> [!NOTE]
> **在已发布的路径上不可达**
>
> 已发布的驱动内补丁从不撞 `0x35`。`kgspSec2PostblTimingRebuildStockSignature()` 在真实 GSP-RM 引导前恢复真实的 4096 字节签名，所以那次引导的 DMA 只到 DMEM `0x17FF`、描述符表保持完整。`0x1B83`/`0x8608` 恢复不在已发布的载荷里、那里也不需要。
> *（置信度：中等；从已发布的代码加 2026-07-20 根因分析推理、未独立插桩。）*

### 4.6 Booter 错误 `0x54` { #booter-0x54 }

> [!NOTE]
> **未解问题**
>
> **症状（PG199 / A100D、`10DE:20BB`、出厂 32768 MiB）：**
>
> ```text
> kgspBootstrap_TU102: kflcnResetIntoRiscv 0x0
> s_executeBooterUcode_TU102: Booter failed 0x54
> ```
>
> 失败前到达的状态：`MMU_LMR 0x0000020a -> 0x0000020b`；`FBPA_CFG1` 出厂 `0x22779000`、一个变体清位 29 给出 `0x02779000`、另一个留下 `0x22779000`；`SS0 0x53540175` 和 `SS1 0x00000000` 刻意不变；WPR2 `07f68000/07fefe00 -> 1ffffe00/0`；PLM `ffffff8f/0004cb8f -> opened`。WPR2 留在 failed-init 状态、因为 GSP 从不完成初始化。
>
> **没人能说 `0x54` 是什么意思。** 它只在 A100D / PG199 硬件上观察到、从不在 170HX 上。寄存器写可演示地落地，所以问题很窄：找到 Booter 状态枚举。注意名为 `PG199` 的分支不含 A100D 支持，所以这项工作活在仓库之外。

### 4.7 `RmInitAdapter failed! (0x62:0x40:2674)` { #rminit-2674 }

**症状。** 多-GPU 箱里一张 GPU 上完全没有成功初始化、而同箱另一张 GPU 到达 Xid 119。

**原因。** 未确立。它是一个真实、可复现的签名。在一张 OEM BTC B250 矿板上观察、内核 6.8.0-134-generic、驱动 580.159.03、Intel SPT PCH 根端口带 ACS 变通方案启用。

### 4.8 `RmInitAdapter failed! (0x62:0xffff:2119)`，脏的 SEC2 退出 { #rminit-2119 }

**症状。**

```text
s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x29
_kgspBootGspRm: SEC2_DEBUG: FAILED to open FBPA_008 (0x9a0008) after 2 attempts reg=0xffffff8f
kgspInitRm_IMPL: Max GSP-RM boot attempts exceeded: 4/4
NVRM: RmInitAdapter failed! (0x62:0xffff:2119)
```

**原因。** PLM 被一次脏的 SEC2 退出部分锁住。`reg=0xffffff8f` 就是关键线索：`0x8f` 是 "secure_teardown ran" 标记值。Booter `0x29` 来自 `check_1180f8_nibbles`、它要求 `0x001180f8` 的进入顶半字节是 `0`。

**可复现的 A/B 对照。** 不写几何寄存器、不写算力寄存器，也不写 `0x1180f8` 时，执行利用可以继续得更远，只在 `FBPA_00C (0x9a000c)` 失败；仅加入一次 `0x1180f8 = 0x17100000` 写入后，`FBPA_008` 和 `FBPA_00C` 都会失败。

**修复。** 先获得一次干净的 SEC2 退出：执行冷启动，然后不加入额外写入，再次执行利用。

### 4.9 `0x24:0x72`、`BAR 0/BAR 2 failed.` { #bar2-0x72 }

**症状。** `RmInitAdapter failed!` 带 `0x24:0x72` 或 `0x72`、日志字符串 `"BAR 0/BAR 2 failed."` 在 `journal.c:4081`、即 `NV_ERR_MEMORY_ERROR`。

**原因。** 这不是显存损坏，也不是 SCP 加密失败。前后探测表明，BAR0 到 vidmem 的路径仍能读回写入的模式 `0xabcdabcd`。真正失败的是 `kbusVerifyBar2` 中的第二项 BAR2 虚拟地址（经 MMU 转换）测试：真实 Booter 在 `0x2777000` 到 `0x27fee00` 之间划出 WPR2，并在正常 ACR 工作期间设置 FBIF `0x800` 位；驱动的 BAR2 测试缓冲区和实例块恰好落入了这个写保护区域。

**修复。** 离开重度安全模式时，先将 WPR2 拆除并恢复为：

```text
0x1FA824 = 0x1FFFFE00
0x1FA828 = 0x00000000
```

**备用方案，从未实际使用。** BAR2 自检可以通过 `PDB_PROP_GPU_BROKEN_FB`、`gpuIsCacheOnlyModeEnabled` 或 `kbusIsBar2TestSkipped` 跳过。这些入口是在 `0x24:0x72` 仍阻塞引导时从源码中找到的；但 WPR2 teardown 先解决了底层原因，因此它们只被记录，没有进行测试。

一次无驱动的利用运行也会产生同样的 `0x72`：它让 GPU 的 BAR2/L2/MMU（POST/DEVINIT）状态保持 ACR 配置，导致 CPU-RM 的显存自检失败。

### 4.10 RM init 带 `rpc_result = 0xFFFF` 停滞 { #rpc-ffff }

> [!WARNING]
> **实验性**
>
> 历史性的净室逆向工程阶段单次加载重接路径。如果重接部分成功，可能到达 GSP-RM init，却仍以 `RPC_HDR->rpc_result = 0xFFFF`（`NV_ERR_GENERIC`）停滞，并且 `GSP-LOG[RM]` 缓冲区为 NULL，说明 RM init 很早就失败了。当时 Booter 已完成（WPR2 已设置、`BOOTVEC = 0xfd00`、`finalize_1180f8` 观察到 `0x17100000`，而已知良好值为 `0x11000000`）；驱动因 MBOX0 被破坏为 `0x31` 而重新设置 GSP 引导参数，恢复 `WprMeta.sizeOfSignature = 0x1000`，并因 HS 锁定寄存器产生假阴性而绕过 `kflcnIsRiscvActive`。该状态在 2026-07-07 被记录为“the current wall”；RM 侧根因始终未查明，整条路线后来被驱动内补丁取代。*（置信度：中等。）*

一个相关状态是：失败的 GSP 交接表现为 Xid 119 / `GSP_INIT_DONE` 超时，同时 mailbox0 = `0x31`、`finalize_1180f8 = 0x11000000`、`BOOTVEC = 0xfd00`。Booter 在该状态下完成了认证路径，但 RISC-V GSP 没有启动，因为没有发出 BCR 写入。在 `0x37b7` 和 `0x37cc` 返回时，结果相同。

下面是完整栈成功重接后的参考“good landing”状态，供对比：

| 可观察量 | 良好值 | 含义 |
|---|---|---|
| `finalize 0x1180f8` | `0x11000000` | `[31:28]` 里半字节 1 加 authenticate 的位 24；位 26（`BOOT_STAGE_3_HANDOFF`）**未**设 |
| `GSP_FALCON_MAILBOX0` | `0x31` | GSP-RM 活着 |
| `GSP BOOTVEC` | `0xfd00` | |
| SEC2 resetPLM | `0x8f` | `secure_teardown` 跑了 |
| SEC2 MBOX0 | `0x0` | `report_status` 写了 r0 = 0 |
| `RV_STATUS 0x111240` | `0x33` 或 `0x35` | RISC-V 核心运行（它从未启动时 `0x0`） |

### 4.11 一次卡住引导的 Falcon 核心转储 { #falcon-coredump }

一次卡住引导的非破坏性 Falcon 核心转储读：

```text
falconMailbox 0:00000031        # PC 劫持成功
riscvPc       00000000          # RISC-V 核心空闲
riscvCpuctl   00000010
riscv mailboxes 0,1,2,3 = 0
riscvIrqmask / riscvIrqdest / riscvPrivErrStat / riscvPrivErrInfo
  / riscvPrivErrAddr / riscvHubErrStat = 0
falconIrqstat 00000000
falconIrqmode 0000fc24
fbifInstblk   00000000
fbifCtl       00000190
fbifThrottle  80000064
fbifAchkBlk   0:a2286560 1:370b1788
fbifAchkCtl   0/0
fbifCg1       0000000f
```

**解读：** 溢出已经取得 Booter 的控制权，但 GSP 核心从未启动。也就是说，利用使引导过程卡住，而不是被签名检查拒绝。

### 4.12 可诊断性：补丁 0002 添加什么 { #patch-0002 }

补丁 0002 的目的就是让 GSP 引导失败变得可诊断。它将致命的 `NV_ASSERT_OK_OR_RETURN` 宏改为记录状态的检查，并产生：

```text
SEC2_DEBUG: FWSEC cmd is NULL, aborting
SEC2_DEBUG: kflcnReset for FWSEC: 0x%x
SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x
SEC2_DEBUG: FWSEC: pPreparedFwsecCmd=%p frtsSize=0x%x
SEC2_DEBUG: FWSEC status=0x%x
```

用户在工单中通常需要粘贴的大多数 `SEC2_DEBUG` 行都来自这里。

### 4.13 签名大小阳性对照 { #sigtest }

如果你看到这个、它是一个**阳性对照**、不是失败：

```text
_kgspCreateSignatureMemdesc: kgsp: TEST sig override active:
  orig first 4096 B + /tmp/sig tail, total 23360 B, orig size: 4096
kgspBootstrap_TU102: [sigtest] DEVICE IS UP: GSP booted and RISCV is active
  (Booter accepted the signature)
```

这次运行在 580.167.08 上演示了漏洞。它 60 秒后仍撞上通常的 Xid 119 / WPR2-already-up 路径。

已发布的签名缓冲区是 `0xf800` 字节（`SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL`、63,488 字节）、**不是** `0xf700`。一次社区复现受阻于 GSP 二进制里 `fwsignature_ga100` 节只有 `0x1000` 字节、而载荷硬编码为 `0xf700`；解决方案是停止补丁固件，改为从驱动放大 `pSignatureMemdesc`。

---

## 5. 状态码目录 { #codes }

### 5.1 Booter 和 GSP 状态码 { #codes-booter }

| 码 | 含义 | 备注 |
|---|---|---|
| `0x00` | SEC2 MAILBOX0 干净退出 / GSP-RM 干净引导 | |
| `0x2` | 无效签名 | |
| `0x29` | 坏 finalize 半字节，来自 `check_1180f8_nibbles` | 要求 `0x1180f8` 的进入顶半字节是 `0` |
| `0x31` | Booter 拒绝 / SEC2 MAILBOX0 里的默认状态 | **视上下文而定**，见下 |
| `0x35` | DMEM 寄存器描述符表读零 | 仅无驱动路径，见[4.5](#booter-0x35) |
| `0x47` | 金丝雀不匹配 panic | |
| `0x54` | 只在 A100D / PG199 上观察到 | 含义**未知**，见[4.6](#booter-0x54) |
| `0x59` | 可选 `dmem.bin` 的文件未找到 | 良性，见[2.2](#benign-0x59) |
| `0x60` | 在过渡到 `0xffff` 时看到 | |
| `0x62` | 驱动侧 `NV_ERR_RESET_REQUIRED`；也是一个固件-init 失败状态 | RmInitAdapter 三元组的首字段 |
| `0x65` | 驱动侧 `NV_ERR_TIMEOUT` | 见[4.4](#gsp-0x65) |
| `0x72` | `NV_ERR_MEMORY_ERROR`、BAR2 自检 | 见[4.9](#bar2-0x72) |
| `0xfe` | CPU-RM ACR 检测到发射后的 SEC2 状态 | 只有 FLR 清除它 *（置信度：中等）* |
| `0xffff` | Booter Load 失败 / GSP-RM init 失败 | 每次载荷趟都预期 |
| `0xFFFFFFFF` | GSP 邮箱未读 | |
| `0x15` | Booter 的 `csb_write` 错误路径，报告进 SEC2 MAILBOX0 | |

从实时 dmesg 读取的状态码置信度较高，但对 `0x54` 和 `0xffff` 机制的归因置信度较低。一种说法认为，`0xffff` 是因为 Booter 在几何布局改变后于 FB 顶部划出了 WPR2，而该区域没有实际后备；这一点尚未定论。

**邮箱地址。** SEC2 MAILBOX0 是 BAR0 `0x00840040`；GSP 邮箱是 `0x00110040`。

> [!NOTE]
> **未解问题**
>
> **邮箱 `0x31` 的含义仍未确定。** 目前有 3 种互不兼容的解读：(a)“初始值 / 尚未写入”，这一说法已**明确撤回**，因为后来确认 `0x31` 是被写入的值（它是驱动引导参数的物理地址，但已被破坏），并且健康的 GSP 引导会将 `0x110040` 重置为 0；(b)“ACR 互斥锁仍被占用”，这是早期最有影响力的解读；(c)“SEC2 Booter 自身的成功标志”，此时驱动的 `0x65` 只是等待完成 60 秒超时，因为 SEC2 停留在 `0x8f` teardown 状态。还有第 4 种用法：在良好落地状态中，`GSP_FALCON_MAILBOX0 = 0x31` 被解释为“GSP-RM 正在运行”。
> **请把 `0x31` 当作观察结果，而不是诊断结论。** 要解决这个问题，需要 SEC2 Booter 自身的状态枚举，或一次能够证明 ACR 互斥锁空闲、却仍产生 `0x31` 的受控实验。

### 5.2 `RmInitAdapter` 三元组 { #codes-rminit }

开头的 `0x62` 表示 `NV_ERR_RESET_REQUIRED`。

| 三元组 | 含义 |
|---|---|
| `(0x62:0x40:2028)` | WPR2 已 up，见[4.1](#wpr2-already-up) |
| `(0x62:0x55:2028)` | `DEVICE FAILED TO COME UP: RISCV not active after Booter Load` |
| `(0x62:0x65:2028)` | RmInitDone 超时 |
| `(0x62:0x40:2674)` | 第二张 GPU 上的初始化失败、根因未知，见[4.7](#rminit-2674) |
| `(0x62:0xffff:2119)` | `0x29` / FBPA-open 路径，见[4.8](#rminit-2119) |
| `0x24:0x72:1220` | 10 GB 下、`RmInitNvDevice` 里的一次冷启动下游阶段；与 BAR2 案例不同的阶段 |

### 5.3 SEC2 复位 PLM 可观察值 { #codes-resetplm }

这些值从地址 `0x8403C4` 报告。GSP 中对应的地址是 `0x001103d0`。

| 值 | 含义 |
|---|---|
| `0xff` | 干净；总线主控健康 |
| `0x8f` | `secure_teardown` 跑了（位 `[6:4]` 从 `0x7` 变 `0x0`） |
| `0x00cf` | 驱动仍已加载的部分发射状态 |

*（置信度：中等。它在多次运行中始终被用作可观察标记，但有人质疑 `0x8403C4` 处寄存器的身份，因为该地址不在熔丝清单中，而且从未有独立文档记录。见[寄存器参考](../unlock/register-reference.md)。）*

FLR 清除 SEC2 复位-PLM 污染：`0x8f` 变成 `0xff`。

### 5.4 `0xbadfXXXX` 读 { #codes-badf }

`0xbadfXXXX` 读数表示**权限或目标存在性失败，而不是存储的数据**。

| 模式 | 含义 | 例子 |
|---|---|---|
| `0xbadf5040` | 读被权限级别掩码阻挡 | `FECS_FEAT_OVERRIDE 0x00409664`、`FECS_FEAT_READOUT_1 0x00409668`、第二个特性覆盖组 `0x00823830`-`0x0082383c` |
| `0xbadf1100` | PRI 目标不存在 | `PMC_BOOT_42 0x0000a800`、GA100 上的 `FUSE_OPT_FBIO_OLD 0x00021c14` |
| `0xbadf20NN`（`0xbadf2010`-`0xbadf201b`） | 目标存在，但 FBPA 分区已被熔丝裁剪禁用 | 低字节编码实例 |
| `0xbadf1002` | GA10x 变体的不存在哨兵 | 在 `0x00021C14` |
| `0xbadf5108` | 从 PL0 读 AON 安全临时区 | `0x001180f8`、`0x001182d0` |
| `0xbadf` 前缀一般 | Priv 阻挡的回读 | 例如 GSP falcon 发射块 `0x110280`-`0x110298` |

*（3 个主要类别的置信度较高，具体分类措辞的置信度为中等。）*

### 5.5 其它驱动错误码 { #codes-other }

**CUDA 失败中出现 `NV_ERR_INSUFFICIENT_RESOURCES (0x1A)`**，说明 WPR meta 的第二次处理没有识别解锁后的容量。使用 `dmesg | grep -E 'Xid|NVRM.*rror'` 检查。*（置信度：中等；结论来自发布版指南，没有独立复现和修复验证。）*

**来自 `NVA06F_CTRL_CMD_STOP_CHANNEL` 的 `NV_ERR_RESET_REQUIRED (0x62)`** 在 `nv_gpu_ops.c:11190`、当分配越过设备真实解码边界时出现（一张过度配置的卡上在 40 GB 观察到）：

```text
nvAssertOkFailedNoLog: Assertion failed: Reset required [NV_ERR_RESET_REQUIRED] (0x00000062)
  returned from pRmApi->Control(...)
```

显卡在该边界以下运行正常；分配一旦越过边界，通道停止就会失败。

**FLR 后写入 DMEM 出现 `EXCI 0x0a (MISS_INS)`**，说明 Booter 已不再驻留于 IMEM：它被 FLR 移除了。

---

## 6. 静默失败与操作陷阱 { #silent }

### 6.1 `rmmod nvidia` 清除总线主控 { #bus-master }

> [!CAUTION]
> **资料库中最重要的操作陷阱**
>
> **`rmmod nvidia` 会清除 PCI `COMMAND.BusMaster`。** SEC2 Booter 需要通过 DMA 从系统内存获取 ROP 载荷，因此总线主控关闭后，它什么也取不到，只会使用空载荷运行、不执行任何 ROP，最后以故障退出。**日志中不会提到 DMA。** 所有写入都会被弹回，唯一可见的现象是 `resetPLM` 从 `0xff` 变为 `0x8f`。

**诊断：**

```bash
setpci -s <bdf> COMMAND
# 0x0102 = 坏了（总线主控位清除）
# 0x0546 = 良好（位 2、Bus Master、置位）
```

**修复。** 执行利用前重新启用总线主控：

```bash
sudo setpci -s <bdf> COMMAND=0x0546
```

refire 工具已在 `prepare()` 中加入 `ensure_bus_master()` 调用，可自动修复这一状态。修复后，每次执行利用时 `resetPLM` 都保持为 `0xff`。

这个陷阱适用于独立运行的无驱动工具。当前发布版驱动内补丁运行在已加载的驱动中，而总线主控在这种情况下按定义就是开启的。

### 6.2 驱动仍已加载时执行利用 { #driver-loaded }

**症状。**

```text
PLMs: 1/9 open (fired 8 closed)
resetPLM=0x00cf
PRE  CFG1=0x02449000 LMR=0x00000288
POST CFG1=0x02449000 LMR=0x00000288
decode=0x70000300
CSTATUS=0/24
WPR2=['0x2779000','0x27fee00']
STATE NOT CLEAN, FLR + re-fire
EXIT_CODE=1
```

**修复。** 卸载驱动。驱动卸载后，相同命令会得到 `PLMs: 9/9 open (fired 0 closed)`、`resetPLM=0x00ff`、`CSTATUS=20/24` 和 `READY`。同一硬件上的失败与修复在几分钟内连续观察到。

### 6.3 正确卸载驱动 { #teardown }

仅执行 `modprobe -r` 不够。有效的顺序如下：

```bash
systemctl stop nvidia-persistenced      2>/dev/null || true
systemctl disable nvidia-persistenced   2>/dev/null || true
systemctl stop gdm3 sddm lightdm display-manager 2>/dev/null || true
killall -9 Xorg Xwayland nvidia-persistenced     2>/dev/null || true
sleep 2
modprobe -r nvidia-uvm      2>/dev/null || true
modprobe -r nvidia_drm      2>/dev/null || true
modprobe -r nvidia_modeset  2>/dev/null || true
modprobe -r nvidia          2>/dev/null || true
sleep 2
lsmod | grep -q nvidia && rmmod -f nvidia_uvm nvidia_drm nvidia_modeset nvidia
```

每一步都有错误保护，因此在 `set -e` 下，缺失的服务不会导致脚本中止。随后执行 FLR：

```bash
echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset
sleep 3
```

这个 harness 共运行了 9 个解锁周期。

### 6.4 模块不肯卸载 { #module-stuck }

`nvidia` 模块经常无论如何都拒绝卸载，并留下：

```text
nvidia 15835136 2
drm    753664 7 drm_kms_helper,drm_display_helper,nvidia,drm_buddy,i915,ttm
```

`drm` 对 `i915` 的依赖，是应在无头或不使用 NVIDIA 显示输出的主机上执行解锁的实际原因之一。该系统上的模块大小为：`nvidia_modeset` 2248704、`nvidia_uvm` 2039808。*（置信度：中等；在同一份运行日志中反复观察到。）*

### 6.5 DMEM 写被静默丢弃 { #dmem-locked }

**原因。** 一旦 `nvidia.ko` 将 SEC Falcon 引导至重度安全（HS）模式，`DMEM_PRIV_LEVEL_MASK`（`0x00840284`）中的写保护读数就会变为 0，所有 DMEM 写入都会被丢弃。Falcon 处于 HS 模式时，DMEM 既不能读取，也不能写入。

**检测。**

```text
mask    = read32(0x00840284)
rd_prot = mask & 0x7
wr_prot = (mask >> 4) & 0x7      # 0 意味着 LOCKED
```

功能测试：通过 DMEMC0/DMEMD0 将 `0xDEADBEEF` 写入 DMEM`[0x000]`，然后读回验证。

**修复。** 一次 ENGINE 复位：

```text
wr32(PSEC_ENGINE, 0x1); sleep 10 ms; wr32(PSEC_ENGINE, 0x0)
poll DMATRFCMD for IDLE && !FULL
poll DMACTL & 0x6 == 0                 # scrub complete
check SCP_CTL_P2PRX bit 3 (SFK_LOADED)
check KFUSE_LOAD_CTL bit 0 set, bit 1 clear
```

或者执行断电循环，并在加载 `nvidia.ko` 之前运行这些步骤。

### 6.6 存在活动 CUDA 上下文时执行利用 { #live-cuda-context }

在活动 CUDA 上下文旁执行利用**确实**可以打开 FB 几何 PLM（`0x00100b10`：`0xffffff8f -> 0xffffffff`），但随后会使 `nvidia-smi` 挂起，因为让 SEC2 停留在 HS（spin-park）状态会破坏驱动的健康检查路径。恢复方法是执行一次 `FALCON_ENGINE` 复位；它会清除 HS 状态，但不会修改 FB 内容。*（置信度：中等。）*

### 6.7 在 `0x82xxxx` 块外写安全寄存器 { #resetplm-8f }

在 `0x82xxxx` 块之外写入任何安全寄存器，都会使 SEC2 复位 PLM 再次变为 `0x8f`，从而阻塞出厂的 `kflcnReset`，并使第二次 Booter Load 以 `0x65` 失败。已知会触发该问题的寄存器包括：`0x1183A4`（容量暂存区）、`0x9A0204`（FBPA strap）和 `0x1FA8xx`（WPR）。只有对 `0x82xxxx` 的写入不受影响。**这正是算力容易解锁而显存解锁失败的原因。** *（置信度：中等；症状可复现，并始终带有 `resetPLM=0x8f` 标记，但寄存器身份曾受到质疑。）*

### 6.8 用一次复位把 PLM 打开和几何写分开 { #flr-between }

**症状。** 同一条流水线能够打开算力 PLM，但对 `0x009A0204` 的 CFG1 写入被弹回；3 次尝试都读回出厂值 `0x2449000` 而不是 `0x2779000`，最后显示 `Pipeline complete: 0/1 GPU(s) unlocked`。

**原因。** FB 几何 PLM **不在** AON 常电域中，而特性覆盖 PLM `0x00823804` **位于**其中。先打开 PLM、执行 FLR、再写入几何布局的分阶段流水线，会因 FLR 丢失 FB 几何 PLM 状态。

**修复。** 不要用复位将 PLM 打开和几何写入分开。当前发布版补丁会在一次 GSP 引导中完成这两项操作。见[恢复：哪些状态能挺过复位](recovery.md#state-persistence)。

### 6.9 删除或不匹配的固件 { #firmware-deleted }

**症状。** 出现持续数天且无法复现的“model degradation”，同时 `SEC2 MBOX0 = 0x0`（Booter 根本没有加载）。

**原因。** `/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` 已被删除，而且 `.04` 用户态的 `nvidia-smi` 不会在 `.03` 模块上触发 GPU init。

**修复。** 恢复版本匹配的固件目录，并使用版本匹配的 `nvidia-smi`。恢复固件后，之前的正常状态立即得到复现。

**当时记录的实际教训：** 让代理修改驱动时，应保留 diff 或变更日志，因为重新安装驱动会静默丢失所有必要的注入。

### 6.10 磁盘上一个陈旧的已补丁 `gsp_tu10x.bin` { #stale-firmware }

如果这台机器曾使用过 cmpunlocker 的**固件打补丁前身**，则在运行驱动内补丁**之前**必须将 `gsp_tu10x.bin` 恢复为出厂版本：

```bash
GSP_DIR=/lib/firmware/nvidia/610.43.03
sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
```

**原因。** 驱动会在引导时将固件签名保存为“stock”。如果磁盘上的固件仍是打过补丁的版本，驱动保存的就会是**利用载荷**；随后干净的 GSP-RM 引导会通过 DMA 取到错误的 ROP 链。成功标志是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

### 6.11 重复驱动加载把错误码向前走 { #nondeterminism }

重复加载 CPU-RM 驱动会逐渐清理脏设备，并使错误码向前推进。单变量对照显示，单独执行一次 MMU-invalidate 时仍停在 `0x24`；因此之前从 `0x24 -> 0x25` 的推进来自**双重加载**（CPU-RM 自身的部分初始化清理了状态），而不是 MMU 写入。这也解释了观察到的非确定性：脏设备的清理过程本身具有非确定性，所以每次执行利用的结果都带有噪声。*（置信度：中等；底层清理机制从未得到确认。）*

---

## 7. 构建失败 { #build }

`build.sh` 在 `set -euo pipefail` 下运行，因此任何 hunk 失败都会中止构建。它将 `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz` 下载到 `driver/.build/`（默认缓存目录，可通过 `CMPUNLOCKER_BUILD_DIR` 覆盖），每次运行都会删除并重新解压一棵干净的源码树，使用 `patch -p1` 按字典序应用 `patches/*.patch`，然后运行 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`。构建耗时约 5 分钟*（仅有一份报告，实际时间取决于硬件）*。

| 失败 | 原因 | 修复 |
|---|---|---|
| `Installed driver is X, but cmpunlocker requires one of: 610.43.03,610.43.02.` | 精确字符串版本白名单 | 安装 610.43.03 或 610.43.02 nvidia-open |
| 内核头文件错误、`/lib/modules/$(uname -r)/build` 缺失 | 没有为**当前运行的**内核安装头文件 | 安装匹配的头文件，或引导到实际构建所针对的内核 |
| 补丁 hunk 被拒绝 | 上游 tarball 错误，或 `.build/` 树已过期 | 脚本每次运行都会重新解压；确认当前处于预期分支 |
| `python3: command not found` | `build.sh` 需要 `python3` | 安装它。**master 不使用 PyYAML**，发布版脚本中也**没有显式的 GCC 版本检查** |
| 首次安装时没有网络 | 无法下载 tarball | 预先准备好 `driver/.build/` |
| `No initramfs tool found, rebuild manually before rebooting` | `update-initramfs`、`dracut` 和 `mkinitcpio` 都不存在 | 手工重建 initramfs，见[3.4](#initramfs) |
| Ubuntu 经 mainline 交换内核后构建坏 | 内核交换破坏了 NVIDIA 610 open 驱动构建 | 用发行版内核 |

需要明确说明的前置条件包括：关闭 Secure Boot（模块未签名）、使用 nvidia-open 610.43.0x（专有驱动“has different boot paths and cannot be patched the same way”）、**仅支持 Linux**（GSP 引导路径是 Linux 专属）、使用 root，并且模块必须针对当前运行的内核编译。构建会安装**5 个**模块（`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko`、`nvidia-peermem.ko`），权限模式为 `0644`，目录为 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。只有 `nvidia.ko` 携带解锁代码，其余 4 个是出厂模块的重建版本。

由于补丁通过 glob 应用，将名为 `0007-*.patch` 的第三方 diff 放入 `driver/patches/` 后，就能与解锁补丁系列正常组合。这是叠加 P2P 补丁的文档化机制。见[驱动补丁](../unlock/driver-patches.md)。

**安装前先移除旧版本。** 维护者在切换分支时遵循的规则是“always remove the old one before adding the new one.”（添加新版本前总是先移除旧版本。）一位测试者克隆 Gen2 分支并覆盖安装在已有版本上，结果无法运行；先卸载后问题得到解决。这是操作建议而非硬性规则：至少还有 2 位测试者成功进行了覆盖安装。先移除旧版本是*受支持的*路径。*（置信度：中等；没有人找出其中的区别因素。）*

---

## 8. PCIe Gen2 问题 { #gen2 }

> [!WARNING]
> **实验性**
>
> **`master` 上不发货任何 PCIe Gen2 补丁。** 补丁 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`、加 `tools/retrain.sh`、只存在于分支 `Gen2`、`far`、`debug-gen2`（只 0007 和 `tools/retrain.sh`）和 `deced` 上。`verify.sh` 是一个独立工具、发货于 `Gen2`、`far`、`deced` 和 `multiple-cards`，见[11.2](#verify-sh)。本节一切适用于实验分支。

请记住，**速度和位宽是彼此独立的结果**。从 Gen1 到 Gen2 属于驱动和固件解锁；超过 x4 位宽则需要在通道 4 到 15 上物理焊接 24 颗 0402 X7R 电容。两者互不影响。见[PCIe Gen2](../unlock/pcie-gen2.md)和[物理改装](../operations/physical-mods.md)。

### 8.1 Gen2 在某些机器上工作、另一些不 { #gen2-hardcoded-bdf }

**根因：PCI 地址 `0a:00.0` 被硬编码。** 硬编码位于*用户态辅助工具* `tools/retrain.sh` 的 3 处（`SYS=/sys/bus/pci/devices/0000:0a:00.0`、`GPU, UP = "0a:00.0", "09:01.0"` 以及 `resource0` 路径），**不在**内核补丁中：`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2` 和 `deced` 分支之间逐字节相同。

分支 `deced`（提交消息为“Stupid mistake - it appears to be hardcoded”）用 `find_gpu_bdf()` 取代了硬编码：通过 `lspci -d 10de:20c2` / `lspci -d 10de:2082` 查找显卡，最多等待 120 秒直到 `resource0` 和 `nvidia-smi -L` 可用，并使用 `readlink -f` 推导上游桥。**`Gen2` 和 `far` 分支仍保留硬编码。**

### 8.2 安装后 PCIe 仍在 Gen1 { #gen2-still-gen1 }

**第一项检查：IOMMU 直通模式。** `Gen2`、`far` 和 `deced` 的安装器都会通过 `/etc/default/grub` 或 `/etc/kernel/cmdline`，将 `intel_iommu=on iommu=pt`（Intel）或 `amd_iommu=on iommu=pt`（AMD）追加到内核命令行，替换冲突的条目，将文件备份为 `*.cmpunlocker.bak`，重新生成引导配置；各分支自己的 `remove.sh` 会恢复这些改动。`--no-iommu` 可禁用此行为。Master 不会修改这些配置，因此应使用安装时的同一分支执行卸载。IOMMU 还必须在 BIOS/UEFI 中启用（VT-d / AMD-Vi / SVM）。

**第二项检查：检出是否为最新版本？** 在 2026-07-29 之前，Gen2 补丁只存在于分支中；许多用户因为使用的是 `master` 而反复失败。Gen2 现在已经合并到 `master`，因此需要排除的原因是检出版本早于这次合并。

**第三项检查：重训练可能提前退出。** 独立的 `retrain.sh` 会在以下 4 种情况下打印原因并提前退出：

| 消息 | 条件 |
|---|---|
| `retrain: BAR0 dead; skip` | BAR0 或 CYA 读 `0xFFFFFFFF` |
| `retrain: DIS_G2 still set; skip` | `DIS_G2`（BAR0 `0x8c2c0` 位 2）仍置位 |
| `retrain: Cap Gen1; skip` | 链路能力低于 Gen2 |
| `retrain: preconditions failed; skip` | 写后前置条件失败 |

在 `nvidia-smi` 不可用、显存读数为 `[N/A]`、链路已经是 Gen2，或最大链路代不是 2、3、4 时，它还会以状态 0 **静默**退出。

驱动内重训练在 probe 时执行，并在 `msleep(50)` 后最多轮询 2 秒（20 次尝试 × 100 ms）。它会清除 BAR0 `0x8c2c0` 的位 2（DIS_G2），强制将 `0x8c040` 的位 `[19:18]` 设为 2，向 `0x8872c` 写入 `0x00000006`，在 GPU 和上游桥上同时设置 `PCI_EXP_LNKCTL2_TLS_5_0GT`，然后在上游桥上设置 `PCI_EXP_LNKCTL_RL`（重训练链路）。失败时输出：

```text
CMP Gen2: no upstream PCIe bridge; skipping link retrain
CMP Gen2: cannot map BAR0; skipping link retrain
CMP Gen2: PCIe capability access failed (%d); skipping link retrain
```

此外，还可能出现[2.7](#benign-retrain-false-negative)中描述的假阴性。

### 8.3 根端口不肯改变速度 { #gen2-root-port }

> [!WARNING]
> **实验性**
>
> 有记录，但未经独立确认。如果 `sudo dmesg | grep "SEC2_DEBUG.*Root port"` 显示 "upstream port not valid"，说明芯片组驱动没有枚举上游端口；建议的变通方法是执行 `setpci -s <root_port> <offset>.w=0002`，然后重训练链路。如果 "Root port LnkCtl2" 显示写入成功但速度仍为 1，根端口可能不支持定向改变速度；建议通过 `setpci -s <root_port> <link_ctrl>.w` 将位 5 置位，发起一次由根端口执行的重训练。**资料库中没有任何测量结果证明这些变通方法成功。**

### 8.4 虚拟机里的 Gen2 { #gen2-vm }

Proxmox 直通下显存和算力解锁可以正常工作（一位操作者直通了 8 张 8 GB 卡，全部成功解锁）。**截至 2026-07-24，PCIe Gen2 链路速度修改在 VM 中无法工作**，维护者也已承认这一点。重训练序列是否需要访问被虚拟机监控程序拦截的配置空间或链路层，目前尚未确定。

> [!NOTE]
> **未解问题**
>
> 一台主机（ASUS X99-A、LGA2011）在尝试 IOMMU/虚拟化设置和全部 4 个插槽后报告：其中一个插槽只有 Gen2 x1，其余插槽为 Gen1 x4。该问题报告于 2026-07-27，恰好是硬编码 BDF 修复提交的当天。插槽相关性正是硬编码 BDF 会造成的现象，因此很可能已经在 `deced` 分支中修复，但从未得到确认。

### 8.5 `RMPcieLinkSpeed` 分裂 { #gen2-linkspeed }

> [!NOTE]
> **未解问题**
>
> 两组分支使用了不同的注册表值，而每位作者都认为自己的值正确：`debug-gen2` 和 `Gen2` 写入 `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`，`far` 和 `deced` 则写入 `…=0x2`（由名为 "Remove clamp link to Gen1" 的提交引入）。README 声称 Gen2 可用的 `Gen2` 分支使用 `0x1`。**没有 A/B 引导测试。** 不能把任一值当作规范值。在同一张卡上进行一次三方引导对比即可解决这个问题。

---

## 9. 黑屏 { #black-screen }

### 9.1 运行解锁脚本时黑屏 { #black-screen-script }

> [!NOTE]
> **未解问题**
>
> 一位测试者于 2026-07-20 报告运行解锁脚本时出现黑屏。其本人未经验证的猜测是安装了错误的驱动，但拒绝继续调试。该讨论中的两位测试者所用主机都限制在 PCIe Gen3。没有任何结论得到确立。

### 9.2 一般无头引导 { #headless }

CMP 170HX 没有视频输出，因此有些主板在它作为唯一显卡时无法 POST（据报告，ASRock X370-I 就会拒绝启动）。请准备一张具备显示输出的第三张卡，或确认主板支持无头启动。另见[主机无法启动](#no-post)。

---

## 10. 运行时、CUDA 和工作负载失败 { #runtime }

### 10.1 Xid 31，MMU 故障，区域违规 { #xid31 }

**症状。** 出现带有 `FAULT_INFO_TYPE_REGION_VIOLATION` 的 `Xid 31` MMU 故障；在重启前，该卡无法用于 CUDA。一份捕获显示：

```text
ENGINE GRAPHICS HUBCLIENT_FE  faulted @ 0x7fad_3a200000 ... ACCESS_TYPE_VIRT_WRITE
ENGINE CE2      HUBCLIENT_HSCE2 faulted @ 0xf_f7400000 ... ACCESS_TYPE_PHYS_WRITE
```

**原因。** 分配超出了已解锁窗口的可用上限。物理地址 `0xf_f7400000` 对应 63.86 GiB，正好位于 64 GB 窗口顶部。

**修复。** 少向该 GPU 卸载一层 LLM。恢复需要完整重启。*（建议的修复未确认实际执行。）*

> [!NOTE]
> **Xid 31 本身不是 80 GB 签名**
>
> 在 80 GB 配置下，访问超过约 40 GB 的内核会导致致命的 GPU 丢失，与功耗上限无关。报告的 Xid 包括 Xid 31（有人称其无害）以及 CUDA 显存测试后的 Xid 154；最常见的症状是挂起。仅凭 Xid 31 是旁观者提出的判断，故障卡的操作者并未确认它就是该问题的特征。已确认的 80 GB 情况还包括：报告约 81920 MiB / 85,545,582,592 字节，且 `cudaMalloc` 分配 77 GiB 成功。见[80 GB](../frontier/80gb.md)。

### 10.2 杀掉 CUDA 作业后 Xid 45 { #xid45 }

使用 SIGKILL 终止正在运行的 CUDA 验证内核，可能会使显卡因 Xid 45 进入卡死状态，并迫使系统执行复位循环。发布版工具明确警告：应在**前台**运行，绝不要在运行中使用 SIGKILL；在内核启动之间按 Ctrl-C 则没有问题。64 GB 卡上的密集填充/检查内核运行时间很长（超过 100 万个 64 KB 页面），因此将其放到后台后再终止的诱惑很大。*（置信度：中等；这是经验性操作警告，没有附带 dmesg 捕获。）*

### 10.3 过度配置配置上的 Xid 154 { #xid154 }

在过度配置的 80 GB 配置中，Xid 154 是 CUDA 显存测试后的主要失败，并将显卡限制为每次执行利用只能保留一个 CUDA 上下文。一位测试者只能让 GSP-RM 工作，无法让 CPU-RM 工作；另一位则必须在每次尝试之间对整个系统执行冷循环，而不能只重载驱动。两人都确认 CUDA 可以物理访问这些显存；未解之处在于驻留和稳定性，而不是地址可达性。两位测试者在不同硬件上独立复现了该问题。

> [!NOTE]
> **未解问题**
>
> 4 GB/channel 解码重新启用，以及 CUDA `719` → Xid 45 → Xid 154 链，是同一个原子故障的两种结果，目前无法分离。对 40 GB 以上页面执行原子操作时会发生故障（由于设备只能解码 40 GB，该页面由 UVM 保留在主机上）；CPU-RM 会将页面迁移到更高地址并重新启用 4 GB/channel，但同一故障会污染 CUDA 上下文，依次表现为 `719 unspecified launch failure`、Xid 45 和 Xid 154。尝试进行干净交接（使用一个小型托管“keeper”切换解码，释放它，再分配非托管的 77 GiB）仍然会报错。另有一个被注意到但未测试的相关开关：`PDB_PROP_GPU_RECOVERY_SQUASH_XID154`。

### 10.4 vLLM 在高显存利用率崩溃 { #vllm }

**症状。** vLLM 卡在 `gpu-memory-utilization 0.95` 崩溃。

**原因。** 解锁后的几何布局暴露 65052 MB，但实际可用容量只有 64733 MB，因此在 0.95 利用率下余量非常小。

**修复。** 降至 0.9 后显卡恢复。另一次持续时间较长的多卡会话中，只有在 0.95 利用率和超大上下文下出现过瞬态 "GPU requires reset"，且自行恢复。**建议：将利用率保持在 0.90 或以下。** *（置信度：中高。）* 见[LLM 推理](../operations/llm-inference.md)。

### 10.5 到处 `cuInit` 返回 999 { #cuinit999 }

**症状。** 每个框架 `cuInit` 返回 999、而 `nvidia-smi` 仍报告健康。

**原因。** 反复对运行中的多 GPU 作业执行 `kill -9`，留下约 32 个僵尸 CUDA 进程，导致主机 CUDA 运行时卡死。

**修复。** 主机重启。**这在容器内无法修复。** 不要 `kill -9` 活的多-GPU 作业。

在同一台完整的 8 卡主机上进行的整个会话中，数百次 60 秒健康检查样本均没有硬件故障（**0** 次）。这是操作者引起的失败，而不是硬件问题。

### 10.6 分配越过真正可用容量 { #alloc-crash }

分配超过真正可用的容量时，即使 `nvidia-smi` 报告了更大的数字，基准测试仍会崩溃。`llama-server` 在 3 张分别报告 81920 MiB 的卡上占用 37798 / 47400 / 53960 MiB，导致运行崩溃。重启后，同一机架中的每张卡只能加载约 32 GB（27734 / 31758 / 32754 MiB），基准测试则正常完成，结果与 10 GB → 40 GB 配置大致相同。

### 10.7 老化测试下的显存错误 { #burn-errors }

**症状。** 一张卡被解锁到超出稳定几何布局的范围后，在运行算力老化测试几分钟内便积累显存错误：

```text
2.1%  proc'd: 777 (12153 Gflop/s)   errors: 24433  (WARNING!)  temps: 85 C
```

错误会在最初几分钟内出现。12153 Gflop/s 说明算力解锁已经生效。**稳定的 10 GB → 40 GB 配置可以无错误地通过 5 分钟 gpu-burn**；8 GB → 64 GB 配置也稳定，并已用于生产。

> [!NOTE]
> **未解问题**
>
> 这些 85 °C 下的 gpu-burn 错误究竟由温度还是显存超频引起，从未确定。一种观点是“too hot, dial it back”（太热了，降低频率）；另一种观点是“85 °C is within spec”（85 °C 在规格范围内），而且核心与显存温度只相差几度；第三位观察者则认为这是 HBM 硬件错误。另有人报告，2 张温度保持在 73 °C 以下的卡没有任何错误。分支作者最终采取的措施是降低显存倍率，而不是加强散热。发生故障的卡使用 Samsung 显存。能够解决这一争议的测试是：在相同倍率下对同一张卡强制散热，将温度保持在 70 °C 以下。见[热设计](../hardware/thermals.md)。

> [!WARNING]
> **实验性**
>
> 还有一种相关说法，置信度很低，且作者本人也有所保留：“normal stress tests don't load an unlocked card because the fuses rely on the math being thrown at them.”（正常压力测试不会真正给解锁卡施加负载，因为熔丝是否生效取决于提交给它的计算内容。）该说法从未在已知良好的工作负载上验证。它很重要，因为这将决定 gpu-burn 是否足以作为稳定性测试。背景是：一位测试者在打补丁前使用标准压力测试时，无法将显卡功耗推过 68 W。

### 10.8 `nvidia-smi --gpu-reset` 拒绝 { #gpu-reset-busy }

> [!NOTE]
> **未解问题**
>
> `nvidia-smi --gpu-reset` 在没有任何进程持有显卡时仍以 "GPU is being used by another process" 失败。**尚未解决。** 下一步应使用 `fuser -v /dev/nvidia*` 和 `lsof /dev/nvidia*` 列出持有者，并检查是否存在泄露的 `nvidia-persistenced`，或存在会导致 `cuInit=999` 的僵尸 CUDA 进程。
>
> 同一时间段还报告了相关的恢复困难：冷启动后，有时必须实际拔下并重新插入显卡的 PCIe 电源线缆；此外，一个 CUDA alias 测试会泄露其分配，因此每次测试之间都需要先执行 SBR 恢复，再重载驱动。

### 10.9 解锁工作但 CUDA 不 { #cuda-clean-host }

**解决过一个案例的分诊步骤：将显卡移到干净主机。** 怀疑原主机的软件栈存在问题，但根因从未确认。在归咎于解锁之前，应先在干净主机上测试显卡。*（置信度：中等。）*

注意，这张卡在完全未打补丁的**出厂版** Linux NVIDIA 驱动上也能运行（Ubuntu 24.04 上 `nvidia-driver-570` 加 CUDA 12.8 可直接工作）。因此，“显卡能否被驱动”和“显卡是否已解锁”是两个可以分别测试的问题。

### 10.10 纯粹作为运行时变通方案存在的补丁 { #runtime-patches }

有 3 个发布版补丁专门用于修复解锁后的运行时故障。如果正在调试运行时故障，应知道这些补丁已经应用：

| 补丁 | 它做什么 |
|---|---|
| 0004 `bar0-pramin-clamp` | 当 `0x20C2`/`0x2082` 上 `fbAddrSpaceSizeMb > 0x2000` 时把 BAR0 PRAMIN 窗口钳回出厂 8 GB 派生的偏移量 `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`、这样几何布局改动后窗口不会落到真实孔径之外。注意一张 10240 MB 的 10 GB 卡已经超过 `0x2000`，所以那里也接合 |
| 0005 `ce-scrub-workarounds` | 强制 `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY`（而非 `..._COMPRESSIBLE_DISABLE_PLC`）并为这些卡禁用基于 VAS 的 CE 清理路径 |
| 0006 `persistent-sw-state` | 为两个设备 ID 设置 `NV_FLAG_PERSISTENT_SW_STATE`、这样 RM 在最后一个客户端关闭时不会拆除软件状态 |

---

## 11. 多卡系统 { #multicard }

### 11.1 解锁在多 GPU 系统上静默无效 { #multicard-silent }

**症状。** 热重启和冷重启后，5 张 8 GB 卡都保持出厂状态；验证器针对每个 BDF（01:00.0、05:00.0、06:00.0、07:00.0、12:00.0）报告 `MISSING` 和 `✗ 0000:01:00.0: not found in nvidia-smi`，每张 `20c2 / 8gb` 卡都预期约 65536 MiB，同时还报告 `! No SEC2_DEBUG lines in dmesg`。

**原因。** 早期工具没有处理多卡。同一测试者使用相同驱动时，单卡系统可以正常工作。

**修复。** 在双卡 HiveOS 案例中，先运行 `remove.sh`，重启，再重新安装；之后两张卡都以 40 GB 启动。后来增加了 `multiple-cards` 分支和 `verify.sh`，但它们**尚未合并到 master**：master 中的 `install.sh` 仍使用 `head -1`，只取 `lspci` 匹配结果的第一行。

另见[depmod 任意选择一个模块](#module-resolution)；那是表现相同但彼此独立的另一种多 GPU 失败。

### 11.2 读 `verify.sh` 输出 { #verify-sh }

> [!WARNING]
> **实验性**
>
> `verify.sh` 仅存在于 `deced`、`multiple-cards`、`Gen2` 和 `far` 分支。以下 3 条诊断字符串需要认识：
>
> * `<bdf>: not found in nvidia-smi` 带状态 `MISSING`
> * `No SEC2_DEBUG lines in dmesg (logs may have rotated; unlock can still be OK if memory is unlocked)`
> * 致命的 `<N> GPU(s) failed unlock verification. Cold reboot if modules were just installed.`
>
> 它会将设备 ID 映射到档位（`20c2 -> 8gb -> 65536 MiB`、`2082 -> 10gb -> 40960 MiB`），并从 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory` 读取显卡清单。

### 11.3 HiveOS 十卡案例 { #hiveos }

> [!NOTE]
> **未解问题**
>
> HiveOS beta 24.04 配置 10 张 CMP 170HX 和 nvidia 610.43.03 时，`install.sh` 可以顺利完成，但冷重启后打过补丁的模块没有加载。除重新运行安装外没有尝试其他措施，也没有发布修复。最有希望的下一步是执行三步分诊（[3.5](#triage-three-step)），重点比较 `/sys/module/nvidia/srcversion` 与 cmpunlocker `.ko` 的值，并检查 HiveOS 自己的驱动包是否覆盖安装了打过补丁的模块，或者 initramfs / DKMS 的排序是否让出厂模块优先。这两个候选原因都被提出过，但尚未确认。

见[多 GPU](multi-gpu.md)。

---

## 12. 主机与硬件层面的失败 { #host }

### 12.1 服务器装卡后无法启动 { #no-post }

**症状。** 没有蜂鸣码、没有主板诊断 LED、"No display adapter, press F1" 已被禁用。

**已记录案例中的原因：与 GPU 无关。** 更换 PCI 插槽后，网络接口名称发生变化（从一个 `XXX5XX` 可预测名称变为 `XXX6XX`），因此主机虽然能够无头启动，却没有 IP。

**修复。** 修正网络配置。

**排查时的一般建议：** 使用正确的电源线缆（不带转接头的 ATX/EPS 类连接器，带转接头的 PCIe 连接器），一次只测试一张 GPU，并预期硬件变更后需要重启 2 到 3 次。显卡使用 1 个 EPS 8-pin（额定 300 W），需要 2 × PCIe-to-EPS 转接头。见[供电与 PSU](../operations/power-and-psu.md)。

### 12.2 虚拟机 { #vm }

**Proxmox 直通需要 SeaBIOS，而不是 UEFI/OVMF。** 使用 UEFI 时会出现 RM init / adapter 失败，看起来就像利用根本没有生效。一位用户在意识到旧的可用 VM 使用 SeaBIOS 之前，花了很长时间排查 "rm init adapt failures"；另一位成员也立即认出这是自己无法复现问题的原因。

至少有一部分利用开发是在 QEMU Q35 VM 中直通的 GPU 上完成的，而不是裸机（`QEMU Standard PC (Q35 + ICH9, 2009)`、BIOS `rel-1.17.0-0-gb52ca86e094d-prebuilt.qemu.org 04/01/2014`、GPU 位于 `0000:01:00`、Ubuntu 内核 6.8.0-136-generic、nvidia-modeset 580.159.03）。该环境中的崩溃产生了坏帧指针栈展开警告，故障路径经过 `nvidia_drm`/`nvidia_modeset`（`EnumerateGpus -> AllocateDevice -> nvkms_open_gpu`）。

VM 中显存和算力解锁可以工作，但 PCIe Gen2 不行，见[8.4](#gen2-vm)。

### 12.3 卡掉下 PCIe 总线 { #off-bus }

**症状。** 显卡运行约 1 小时后永久从 PCIe 总线掉线，之后不再被检测到。如果 BAR0 读到 `0xffffffff`，说明显卡已经脱离总线。先按照[恢复](recovery.md#reset-ladder)中的恢复阶梯操作，包括执行 `echo 1 > /sys/bus/pci/devices/$BDF/remove`，然后执行 `echo 1 > /sys/bus/pci/rescan`。

如果显卡始终无法恢复，原因可能在硬件。这是一个在 A100/170HX 级硬件上完成完整诊断的实例：

**原因。** GS7155NVTD 3.3 V LDO 损坏，将 `PS_5V_PGOOD` 网络拉成对地 5 欧姆短路，阻止 MP1475DJ 5 V 转换器启动。其表现是打嗝模式保护：SW 节点出现几十纳秒的瞬时脉冲，并在几十微秒后重试。

**诊断路径。** 12 V 输入电感对地呈高阻，插槽 12 V 没有短路（排除了严重的核心短路）；核心侧输出电感没有电压，也没有开关动作。拆下 MP1475DJ 后，其空焊盘的引脚 1（Power Good）对地测得 5 欧姆。

**修复。** 更换 MP1475DJ 和 GS7155NVTD，然后从 U816 将 `PS_5V_PGOOD` 跨接过来。修复结果是：3V3_SEQ 恢复，开关动作恢复，NVVDD 1.0 V 和 PEXVDD 恢复，GA100 重新出现在 PCIe 总线上。`PS_5V_PGOOD` 为负责对 PEXVDD、NVVDD、1V35 和 1V8 进行上电时序控制的 SN74LV1T08 AND 门供电，并启用产生 3V3_SEQ 的 LDO。

> [!CAUTION]
> **信任一颗新焊的 GS7155NVTD 前先做台架测试**
>
> 将 7.68 千欧反馈电阻更换为 20 千欧，把输出从 3.3 V 重新设定为 1.8 V，在 5 V 电源轨注入 3.3 V，确认输出稳定为 1.8 V，然后恢复 7.68 千欧电阻。需要防范的风险是**反馈引脚开路**（QFN 上可能由冷焊点导致）：这会让 LDO 误判为持续欠压，并将输出推到最大，把完整的 5 V 加到 3.3 V 电源轨上，摧毁几乎所有 3.3 V 逻辑。对于这块 8 到 12 层的电路板，返工参考条件是：在能够拆下芯片前，用 420 °C 热风加热 2 分钟。GS7155NVTD 是 GSTEK 的 QFN 器件，其完整数据手册受 NDA 保护。

### 12.4 到货时的卡况 { #dirty-cards }

退役矿卡到货时可能非常脏：积满灰尘、PCIe 挡板生锈、散热器内部有盐壳、金手指裸露且没有连接器保护盖。使用前需要清洁、重新涂导热膏并更换导热垫。**外观状况不能预测解锁失败：** 一张外观明显脏污的显卡第一次尝试就成功解锁到 64 GB。*（多个独立开箱报告对卡况本身的置信度较高；但“不能预测失败”的结论只基于一个样本，置信度为中等。没有发布过批次级解锁良率。）*

> [!WARNING]
> **实验性**
>
> 一种尚未受到质疑、但没有数据支持的观点认为，长期散热不足的 HBM“should be dead by now unless it's had a very low operating time”（除非运行时间极短，否则现在应该已经损坏），并且 HBM 一旦超过安全温度就会快速退化。许多显卡可能几乎没有运行过，因为 CMP 170HX 于 9 月发布，而到 11 月市场就已无利可图。没有失效率或温度数据支持或反驳这一观点。

2026 年 7 月下旬价格上涨期间，卖家使用的“defective batch”（有缺陷批次）说法**不能**证明存在真实的硬件缺陷群体：它只是取消那些已经展示过正常显卡的商品列表时使用的借口。在已记录的案例中，没有实际发货或诊断出有缺陷的显卡。

### 12.5 挺过冷启动的不可中断睡眠卡死 { #d-state }

**症状。** 一张 10 GB 卡进入了“uninterruptible sleep”状态；该状态在约 5 次冷重启后仍然存在，并阻止 Ubuntu 关机。

**原因。** 是自动加载的补丁内核驱动，而不是显卡本身。

**修复。** 断开显卡后引导（或者使用 `blacklist nvidia`），然后清理系统。*（置信度：中等；受影响的测试者在恢复后确认了根因。）*

该问题更严重的变体在[恢复](recovery.md#bricking)中有如实讨论。

---

## 13. 升级与报告 { #escalation }

`install.sh` 会将带时间戳的日志写入 `logs/install_YYYYMMDD_HHMMSS.log`；`remove.sh` 会写入 `logs/remove_YYYYMMDD_HHMMSS.log`。仓库目录不可写时，`remove.sh` 会回退到 `/tmp`；`install.sh` 不会回退，而是直接在启动时中止。**提交支持请求时，请附上最新的安装日志。**

一份有用的报告应包含：

1. 操作系统和版本、内核（`uname -r`）
2. GPU 型号和驱动版本
3. 整个主机的 `lspci -nn`
4. 完整的 `sudo dmesg | grep SEC2_DEBUG`
5. 最新的安装日志
6. `cat /lib/modules/$(uname -r)/updates/cmpunlocker/{driver_version,card_profile,unlock_geometry}`

响应由单一操作者处理，速度较慢：第一份有记录的 Gen2 工单等待了约 10.5 小时才收到首次回复（06:21 提交，16:59 回复）。

---

## 14. 尚无已知修复的症状 { #unsolved }

> [!NOTE]
> **未解问题**
>
> 记录这些问题，是为了避免它们被再次当作新问题发现。目前没有任何一个问题有已发布的解决方案。
>
> * **Ubuntu 24.04、内核 6.8.0-111-generic、驱动 610.43.03 中冷重启后出现 `NVRM initialization error`。** 冷重启（此前曾为同一测试者清除 srcversion 不匹配）没有帮助。日志中存在 `SEC2_DEBUG` 行，寄存器也确实被写入，这更像寄存器写入后的初始化失败，而不是解锁链失败，但没有人继续追查。下一步应捕获 `SEC2_DEBUG` 块**之后**的完整 dmesg，包括 `normal BooterLoad status` 行和任何 `RmInitAdapter` 三元组，以确定失败发生在流程中的哪个阶段。
> * **执行利用后，普通驱动第一次 `insmod` 立即触发 kernel panic 并重启。** 该问题于 2026-07-01 被提出过一次，此后没有回复。下一步是捕获 panic（使用串行控制台或 `pstore`）；可比的 QEMU 捕获中故障路径经过 `nvidia_drm`/`nvidia_modeset`，因此在执行利用前卸载这些模块是成本较低的首项测试。
> * **缺少 iGPU 或 BMC 显示设备是否会影响 GSP？** 目前只有一次观察，既没有确认，也没有反例或错误字符串。在一台主机上于 BIOS 中禁用 BMC 显示设备，进行一次 A/B 测试即可回答这个问题。
> * **80 GB 不稳定：`cuda_memtest` 在重启后立即通过一次完整的 80 GB 测试，之后每次重试都失败。** 100 W 功耗限制和供电假设都已经排除。对重启的依赖指向显存训练或刷新状态。这是 80 GB 档位目前最具体的线索。见[80 GB](../frontier/80gb.md)。
> * **Ubuntu 与 Arch 之间的显存解锁差异。** 一种解释是两个 PCIe 设备之间存在显存地址冲突：某个非 170HX、非 2080 设备（可能是 M.2 SSD）试图读取 IOMMU 拒绝的地址。受影响测试者的解释则是 Ubuntu 安装配置错误。目前只有变通方案（在另一块 M.2 SSD 上安装不同操作系统）得到验证。当时建议的第一项诊断是 `lspci -s 06:00.0`。
> * **PLM 的预期数量。** 独立工具报告 "9/9 open"，而一位审查者认为应为 "0 or 26, not 1"（0 或 26，而不是 1）。当前发布版驱动内路径恰好打开 4 个 PLM。这些是不同的 PLM 清单，但现有记录没有将 9 项或 26 项清单映射到发布版的 4 项 `plmTable`。

整个项目未解决事项的完整清单见[未解问题](../frontier/open-questions.md)和[状态板](../frontier/status-board.md)。

---

## 相关页面

* [恢复](recovery.md)：冷启动、FLR、SBR，以及哪些状态能够实际保持
* [验证](verify.md)：完整安装后清单
* [安装](install.md)：受支持流程
* [卸载](uninstall.md)：`remove.sh` 和手动回滚
* [驱动版本](driver-versions.md)：支持哪些版本，以及哪些版本经过引导测试
* [多 GPU](multi-gpu.md)：多卡安装
* [权限级别掩码](../unlock/privilege-level-masks.md)：PLM 表的作用
* [寄存器参考](../unlock/register-reference.md)：本页命名的每个寄存器
* [失败路线](../history/dead-ends.md)：已经尝试并被反驳的假设
