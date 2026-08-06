# 排障

**本页覆盖内容。** CMP 170HX 解锁的每一个有记录的失败模式、按你实际看到的症状索引：dmesg 字符串、Xid 编号、Booter 状态码、`RmInitAdapter` 三元组、`nvidia-smi` 读数、构建错误和主机级怪事。每个条目给出症状、已确立的原因和修复，记录单薄处标注置信度。

**从这里开始。** 两条命令回答大多数问题：

```bash
sudo dmesg | grep SEC2_DEBUG      # 解锁路径跑了吗，它回读了什么？
nvidia-smi                        # 8 GB 卡 -> ~65536 MiB，10 GB 卡 -> ~40960 MiB
```

如果 `dmesg | grep SEC2_DEBUG` 什么都不打印，打过补丁的模块从未运行：去[已安装却仍出厂](#stock-memory)。如果它打印了、PLM 行到达了它们的目标、显存却仍是出厂，去[显存仍显示出厂大小](#stock-memory) 并检查 initramfs。如果引导从未走到那么远，去[GSP 引导失败](#gsp-boot)。

两条防止大多数误报的规则：

1. **`WPR_CFG` 读 `0xfffff0ff` 是正确的。** 四个权限级别掩码（PLM）里只有三个目标 `0xffffffff`。见[PLM 回读值](#benign-wprcfg)。
2. **PLM 趟期间的 Booter 状态 `0x31` 和 `0xffff` 是预期的。** 解锁故意让那些运行失败。只有 `SEC2_DEBUG: normal BooterLoad status=0x0` 要紧。见[PLM 趟期间的 Booter 错误](#benign-booter-31)。

---

## 症状索引 { #index }

| 你看到的 | 去往 |
|---|---|
| dmesg 里完全没有 `SEC2_DEBUG` 行 | [已安装却仍出厂](#stock-memory) |
| 安装后 `nvidia-smi` 显示 8192 MiB 或 10240 MiB | [显存仍显示出厂大小](#stock-memory) |
| `[WARN] Loaded nvidia srcversion (…) != patched (…)` | [srcversion 不匹配](#srcversion-mismatch) |
| `Resolved nvidia.ko is not under updates/cmpunlocker/` | [模块解析](#module-resolution) |
| `nvidia-smi`: driver/library version mismatch | [版本不匹配](#version-mismatch) |
| 解锁工作过、却没挺过一次关机 | [解锁不持久](#not-persistent) |
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
| 发射在跑、什么都没变、`resetPLM 0xff -> 0x8f` | [总线主控被清除](#bus-master) |
| `PLMs: 1/9 open (fired 8 closed)`、`resetPLM=0x00cf` | [驱动仍已加载](#driver-loaded) |
| `modprobe -r nvidia` 拒绝、`nvidia 15835136 2` | [模块不肯卸载](#module-stuck) |
| DMEM 写被静默丢弃 | [DMEM 在 HS 中锁定](#dmem-locked) |
| CFG1 写弹回 `0x02449000` | [PLM 打开与写之间的 FLR](#flr-between) |
| 卡随天 "退化"、`SEC2 MBOX0 = 0x0` | [删除的固件目录](#firmware-deleted) |
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
| 服务器装上卡不 POST | [主机不引导](#no-post) |
| 卡运行一小时后从总线消失 | [卡掉下总线](#off-bus) |

---

## 1. 健康引导长什么样 { #healthy-boot }

一次成功的解锁引导按此顺序打印这些 `SEC2_DEBUG` 行：

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

两个签名打印都来自 `_kgspCreateSignatureMemdesc`，它先于 `_kgspBootGspRm` 运行，所以它们开启轨迹、而非坐在序列中间。`POST-BooterLoad verify` 行是决定性的证明：它在真实 GSP 引导**之后**回读，所以它显示解锁存活了。

**预期值。**

| 日志字段 | 预期 | 备注 |
|---|---|---|
| `PLM[0] WPR_CFG(0x1fa7cc)` | `reg=0xfffff0ff` | 不是 `0xffffffff` |
| `PLM[1] FBPA(0x9a0148)` | `reg=0xffffffff` | |
| `PLM[2] WPR(0x1fa7c4)` | `reg=0xffffffff` | |
| `PLM[3] FEAT(0x823804)` | `reg=0xffffffff` | 常开岛、挺过 FLR |
| 任何 PLM 行上的 `status=` | `0xffff` | 预期；回读才是判决 |
| `SS0 (0x0082381c)` | `0x88888888` | 锁定卡读例如 `0x53540175` |
| `SS1 (0x00823820)` | `0x00000008` | |
| `CFG1 (0x009a0204)` | `0x02779000`（8 GB 卡）/ `0x02669000`（10 GB 卡） | 出厂两个都 `0x02449000` |
| `LMR (0x00100ce0)` | `0x0000020B`（8 GB 卡）/ `0x0000028A`（10 GB 卡） | 出厂 `0x00000208` / `0x00000288` |
| `normal BooterLoad status` | `0x0` | 唯一必须为零的状态 |

`POST-WRITE` 里任何其它 CFG1/LMR 配对意味着错误档位在起作用。这些值什么意思见[显存几何布局](../unlock/memory-geometry.md)。

存在三个日志标签、全部在 `LEVEL_ERROR` 发出、所以无需额外调试标志就出现：

| 标签 | 由谁发出 | 内容 |
|---|---|---|
| `SEC2_DEBUG` | 补丁 0001、0002、0003 | PLM、寄存器和 Booter 阶段：0001 里 14 个日志字符串、0002 里 7 个、加 0003 里的 `late PMA extension status=0x%x` |
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

一份归档的良好结果逐字就是 `65536 MiB, 1935 MHz`。注意 `clocks.max.sm = 1935 MHz` 是一个**纯报告字段**、不是一个可达时钟：持续 SM 时钟是 1410 MHz、或 `-pl 300` 下 1470 MHz。见[性能](../operations/performance.md)。

完整安装后清单见[验证](verify.md)。

---

## 2. 看起来像失败却不是的消息 { #benign }

### 2.1 PLM 趟期间的 Booter 错误 { #benign-booter-31 }

**症状。**

```text
s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31
kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff
```

紧接着一条在 `reg=` 里显示目标值的 PLM 行。

**为什么没问题。** 补丁 0001 故意为每次 PLM 趟用一个利用载荷覆写 GSP 签名缓冲区，所以 Booter Load **本应**拒绝那些运行：到签名抱怨提出时，注入的链已经执行了。成功完全由回读 PLM 寄存器判断，绝不由 Booter 状态判断。最坏情况下，真实引导的 Booter Load 之前会有八个这样的失败（四个 PLM，每个最多两次尝试）。

**必须成功的那行**是 `SEC2_DEBUG: normal BooterLoad status=0x0`。

### 2.2 `dmem.bin not found (0x59)` { #benign-0x59 }

```text
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
```

这是正常路径。外部 `dmem.bin` 是一个用 `os_open_and_read_file` 读的开发覆盖钩子；`0x59` 是那个函数的文件未找到状态。每一份归档的成功解锁引导都显示这一行。内置回退载荷瞄准 FBPA PLM（`writeAddr = 0x009a0148`、`writeValue = 0xffffffff`），PLM 循环随后在每次迭代中重写它。

它前面那行 `SEC2_DEBUG: saved stock signature (4096 bytes)` 确认这个驱动上的出厂 GSP 签名是 4096 字节。

### 2.3 构建期间的 `Skipping BTF generation` { #benign-btf }

```text
Skipping BTF generation for .../nvidia.ko due to unavailability of vmlinux
```

良性。BTF 是与解锁无关的内核调试元数据；模块仍构建并加载。它出现在 `nvidia-peermem.ko`、`nvidia-modeset.ko`、`nvidia-drm.ko`、`nvidia.ko` 和 `nvidia-uvm.ko` 上。之后要紧的那行是 `[ OK ] Patched NVIDIA modules loaded`。

### 2.4 DRM "no compatible format" 消息 { #benign-drm }

```text
[drm] Initialized nvidia-drm 0.0.0 20160202 ... on minor 1
[drm] No compatible format found
[drm] Cannot find any crtc or sizes
```

良性。CMP 170HX 没有显示输出。

### 2.5 llama.cpp `cudaHostRegister` 警告 { #benign-cudahostregister }

```text
ggml_cuda_host_malloc: cudaHostRegister of 439781.26 MiB failed: unknown error
```

不致命：加载继续、基准测试完成。把它与一个会整个杀掉进程的真实分配崩溃区分开。

### 2.6 通用设备枚举 { #benign-generic-device }

卡在 Linux 监控工具（例如 Mission Center）里枚举为一个通用的 "NVIDIA display device" 是正常的。在出厂驱动上 `nvidia-smi` 也把它报告为 `NVIDIA Graphics Device`、计算能力 8.0，因为驱动的 PCI ID 表没有 `0x20C2` 的市场名。那是确认你在看一颗 CMP 部件的快捷方式。

### 2.7 Gen2 重训练 "completed without Gen2 link" { #benign-retrain-false-negative }

```text
CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)
```

这是一个**假阴性**：`0x1042` *就是*一个训练好的 Gen2 x4 链路。解码：速度字段 `[3:0] = 2`（5.0 GT/s）、位宽字段 `[9:4] = 4`（x4）。驱动的成功测试额外要求 `PCI_EXP_LNKSTA_DLLLA`（数据链路层链路活跃、位 13、`0x2000`），而 `0x1042` 位 13 清除，所以链路实际处于 Gen2 时检查却失败。报告 `0x7042`（位 13 置位）的主机从同一代码打印成功消息。两台主机上的四张卡显示那个矛盾配对。

改信这些之一：

```bash
nvidia-smi --query-gpu=pcie.link.gen.current --format=csv
cat /sys/bus/pci/devices/0000:$BDF/current_link_speed
```

> [!NOTE]
> **未解问题**
>
> DLLLA 位读零是否指示那些主机之间一个真实、尽管良性的链路层差异、而非只是一个报告伪影，从未被调查。

### 2.8 "所有 PLM 必须显示 `0xffffffff`" { #benign-wprcfg }

第三方文档（`docs/DEBUGGING.md`、`docs/ARCHITECTURE.md`、以及出货 README 里一个更温和的措辞）说每个 PLM 都应读 `0xffffffff`。那过于笼统。出货 `plmTable[]` 是：

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

而循环的成功谓词是 `if (regVal == plmTable[plmIdx].value)`。一次健康引导打印 `SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff`。

---

## 3. 已安装、卡却仍出厂 { #stock-memory }

这是最常见的一类报告。解锁代码没问题；打过补丁的模块不是运行中的那个、或者它没得到一次可在其中运行的干净引导。

### 3.1 `nvidia-smi` 显示 8192 MiB 或 10240 MiB { #stock-size }

**原因。** 要么 PLM 解锁没生效、要么出厂模块仍已加载。

**修复。** 检查 `sudo dmesg | grep SEC2_DEBUG`。

* **完全没有输出** 意味着打过补丁的模块从未运行。走一遍 3.2 到 3.5。
* **有输出、PLM 没到达它们的目标** 意味着解锁链运行并失败了：做一次完全断电关机（OS 重启*不足够*）并重试。见[冷启动](recovery.md#cold-boot)。
* **有输出、`POST-WRITE` 正确、显存仍出厂** 指向第二阶段显存管道而非寄存器写。捕获 `SEC2_DEBUG_HEAP` 和 `SEC2_DEBUG_LATE_PMA` 行以及 `late PMA extension status=0x%x` 值。

泄露的分发 README 用同样的分诊：`nvidia-smi` 显示 65536 MiB 是成功判据、8192 MiB 意味着 PLM 解锁失败。它还指示一次**冷**重启而非热重启。

### 3.2 srcversion 不匹配 { #srcversion-mismatch }

**症状。**

```text
[WARN] Loaded nvidia srcversion (…) != patched (…)
[WARN] Modules installed but the running driver is still stock (or unload failed).
```

**原因。** 出厂 `nvidia.ko` 仍驻留、无法被卸载。`build.sh` 尝试一次热重载（停 `nvidia-persistenced` 和 `nvidia-fabricmanager`、`modprobe -r` 那四个模块、重载）并对照已安装模块的 `modinfo -F srcversion` 交叉核对 `/sys/module/nvidia/srcversion`。

**修复。** 冷重启（`shutdown -h now`、然后上电），然后确认：

```bash
cat /proc/driver/nvidia/version      # 必须不说 dvs-builder
sudo dmesg | grep SEC2_DEBUG         # 必须有输出
```

一位测试者确认冷重启清除了它。

### 3.3 模块解析：出厂仍胜出 { #module-resolution }

**症状。** `build.sh` 打印 `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`。

这是一个模块解析问题最早的信号。模块优先级是 `updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`，那是普通 depmod 排序（这正是为什么不需要 `dpkg-divert`）。`build.sh` 跑 `depmod -a "${KVER}"` 然后用 `modprobe -n -v nvidia` 经验验证结果。

> [!CAUTION]
> **多-GPU 危险**
>
> 在多-GPU 系统上，打过补丁的和出厂的 `nvidia.ko` 可能都落在单一的 `updates` depmod 搜索项下，那种情况下 **depmod 任意挑一个、静默丢掉另一个**。一位测试者把一个多卡失败精确根因到这一点、只在 updates 搜索路径里保留 cmpunlocker 变体、重启、然后确认多卡操作工作。

### 3.4 initramfs 仍携带出厂模块 { #initramfs }

`build.sh` 的分支副本（`memory`、`ecc`、`housekeeping`、`PG199`）逐字携带解释："NVIDIA often loads from initramfs. If only updates/dkms is packed there, stock modules win at boot even when updates/cmpunlocker is preferred by depmod."（NVIDIA 常从 initramfs 加载。如果那里只打包 updates/dkms，即使 depmod 偏好 updates/cmpunlocker、出厂模块也在引导时胜出。）Master 去掉注释却保留行为：`build.sh` 按可用顺序调用 `update-initramfs -u -k "${KVER}"`、`dracut --force --kver "${KVER}"` 或 `mkinitcpio -P`；一个都不存在时警告 `No initramfs tool found, rebuild manually before rebooting`。

这是 "已安装、显存却仍显示出厂大小" 的一条貌似合理路线、值得先排除，因为它廉价，但它是脚本自己的推理，而非诊断出的野外失败：语料库任何地方的聊天报告都没提 initramfs、initrd、dracut 或 mkinitcpio。如果你看到那个警告，手工重建 initramfs 并冷启动。

### 3.5 维护者分诊：三步 { #triage-three-step }

"安装完成、卡却仍出厂" 的标准分诊：

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

第 1 步里一个缺失的目录意味着构建目标是一个不同于已引导的内核。第 2 步里解析路径必须含 `/updates/cmpunlocker/`、运行中的 srcversion 必须等于 cmpunlocker `.ko` 的 srcversion；不匹配意味着出厂仍在运行。

注意那三个元数据文件**只是元数据**。内核模块里没有任何东西读它们：几何布局在运行时从 PCI 设备 ID 选择。一个误检测的 `--profile` 写错误元数据、却**不**产生错误几何布局。

### 3.6 `nvidia-smi`: driver/library version mismatch { #version-mismatch }

**原因。** 前一个内核模块仍驻留。

**修复，按安全性排序：** 重启；或重载内核模块；或安装匹配的 `nvidia-smi` 构建。禁用版本不匹配检查掩盖问题、而非修复它。

> [!CAUTION]
> **一个不匹配的 `nvidia-smi` 静默使每次测量失效**
>
> NVML 拒绝跨版本通信，所以经一个不匹配二进制做的解锁验证毫无意义。一次多日的测量系列就这样失效了（一个 580.159.03 用户态配另一个内核模块构建）。如果你的用户态和模块版本不同，你取下的每一个 `memory.total` 读数都无效。

### 3.7 解锁没挺过一次关机 { #not-persistent }

**原因。** 更老 NVIDIA 驱动和/或更老 `cmpunlocker` systemd 服务的残留。

**修复。** 移除所有旧内核模块**和**旧 `cmpunlocker` 服务，然后重装。出货 `remove.sh` 现在两者都做：它停止、禁用并删除 `/etc/systemd/system/cmpunlocker.service`、杀掉 `/opt/cmpunlocker/daemon/watchdog.py`、移除 `/lib/modules/*/updates/cmpunlocker/`、逐内核跑 `depmod -a`、重建 initramfs、并重载出厂模块。见[卸载](uninstall.md) 和[恢复](recovery.md)。

出货工具不需要 systemd 守护进程：补丁 0006 为两个设备 ID 设置 `NV_FLAG_PERSISTENT_SW_STATE`、那实际就是内置持久化模式。

### 3.8 安装器拒绝运行 { #install-refuses }

`install.sh` 在这些情况下硬失败、什么都不做：

| 条件 | 消息 / 行为 |
|---|---|
| 不是 root | 立即死 |
| `lspci -nn` 里没有 `10de:20b0`、`10de:20c2` 或 `10de:2082` | 死 |
| 安全启动启用 | `Secure Boot is enabled. Disable it before installing unsigned patched modules.` |
| `/lib/modules/$(uname -r)/build` 处缺内核头文件 | 死 |
| 检测到的驱动不在 `driver/VERSION` 里 | `Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.` |
| 显存总量落在每个档位桶之外 | `Could not detect 8GB vs 10GB card` |

安全启动门只在 `/sys/firmware/efi` 存在**且** `mokutil` 在 PATH 上时运行；在非 EFI 系统或没有 `mokutil` 的系统上，检查会被静默跳过，未签名模块随后以 `nvidia: module verification failed: signature and/or required key missing - tainting kernel` 加载失败。

驱动版本检测顺序：`/proc/driver/nvidia/version`，然后 `nvidia-smi --query-gpu=driver_version`、然后扫 `/lib/firmware/nvidia/<supported>/`、然后 `/lib/firmware/nvidia/` 下排序最高的目录。见[驱动版本](driver-versions.md)。

### 3.9 检测到错误的卡档位 { #profile-detect }

`detect_card_profile()` 读出厂 `nvidia-smi memory.total` 并分桶：

| 报告的 `memory.total` | 档位 |
|---|---|
| ≥ 60000 MiB | `8gb`（一张已解锁的 64 GB 卡） |
| 35000 到 59999 MiB | `10gb`（一张已解锁的 40 GB 卡） |
| 7680 到 8704 MiB | `8gb` |
| 9728 到 10752 MiB | `10gb` |
| 其它任何值 | 致命 `Could not detect 8GB vs 10GB card` |

前两个范围存在、以便在已解锁的卡上重装仍检测到正确档位。如果检测错误或 `nvidia-smi` 不可用，强制它：

```bash
sudo ./install.sh --profile=8gb    # 或 --profile=10gb
```

### 3.10 第三个设备 ID `10de:20b0` { #device-id-20b0 }

`install.sh` 检测 `10de:20b0` 却警告并继续：

```text
In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
This card reports 0x20b0; install will continue, but unlock may not activate.
```

补丁 0001 和 0002 里的每一个解锁动作**和每一个 `SEC2_DEBUG` 打印**都只门控在 `0x20C2` / `0x2082` 上、经 `_kgspSec2PostblTimingEnabled()`、它测试 `pGpu->idInfo.PCIDeviceID >> 16`。一张 `20b0` 卡因此会干净安装、走完全出厂路径引导，并应在 `dmesg | grep SEC2_DEBUG` 里什么都不打印。

> [!NOTE]
> **未解问题**
>
> 一位带 A100 工程样品硅片（`20B0`、8192 MB、2048-bit、4096 个 CUDA 核心、Samsung 8Hi HBM2）的测试者报告了一个 `NVRM initialization error` *以及* `SEC2_DEBUG` 确认寄存器被写了。一个出厂构建无法在一张 `20B0` 卡上打印那些行。要么一个加了 ES ID 的修改构建在运行，要么那些行来自同一台主机里的另一张卡。记录无法裁决。

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

以 `nvidia-smi` 的 `No devices were found` 结束。这是主导的利用后失败、被至少三位测试者同样报告。

**原因。** 一次更早的 Booter 运行编程了 WPR2 MMU 寄存器然后脱轨，所以下次 modprobe 驱动看到 WPR2 已 up 并拒绝。

**修复（净室时代）。** 完全拆掉驱动，然后经 `echo 1 > /sys/bus/pci/devices/0000:BDF/reset` FLR，或一次冷断电循环。

出货补丁还在 PLM 循环前从 `0x001fa824` / `0x001fa828` 保存一次 WPR2 低/高、在**每一次** Booter Load 尝试前重写两个寄存器，并在循环后再重写一次。它从不清除它们。

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

**原因。** GSP RISC-V 核心从未到达 RM init：引导**卡住**了、而非被拒绝。

**修复。** 复位让 WPR2 被清除，然后重试：先 FLR、如果 FLR 不清除它就 SBR 或冷断电循环。见[恢复](recovery.md)。

**支持细节。** 它前面的 `_threadNodeCheckTimeout` 显示 4000 ms 的 Falcon-停机超时；GSP 事件本身花了 59 秒。一份捕获里 CPU 到 GSP 的 RPC 历史只含条目 0 `SET_REGISTRY` 和条目 -1 `GSP_SET_SYSTEM_INFO`、意味着 GPU 从未越过早期引导。在两台主机、两个内核和两个驱动构建（580.159.03 和 580.167.08）上捕获。

### 4.3 Xid 119，6 秒超时，函数 103 { #xid119-6s }

**这是与 4.2 不同的失败。** 按函数编号和超时长度区分它们。

**症状。** Xid 119 带 6 秒超时和函数 103（`GSP_RM_ALLOC`）、在一次部分成功的引导之后：GPU 到达一个运行状态（nvidia-drm 已加载、`GSP_RM_CONTROL` 和 `FREE` RPC 在 224 到 5222 µs 内完成），然后每次 `nvidia-smi` 挂起、对连续序号（184、185、186）重复 Xid 约每 6 秒一次。

**修复。** 复位卡；该状态无法原地恢复。

### 4.4 `GSP didn't boot`，状态 `0x65` { #gsp-0x65 }

**症状。** dmesg 里 `GSP didn't boot` 带状态 `0x65`。

**原因。** 精心构造的签名缓冲区 / Booter 序列让 GSP 无法启动。`0x65` 是驱动侧 `NV_ERR_TIMEOUT`。

**修复。** 完全断电循环并重试。对报告它的测试者来说，只移除旧内核模块**不足够**。

> [!CAUTION]
> **`0x65` 不是 `0x31`**
>
> `0x65` 是驱动侧 `NV_ERR_TIMEOUT`；`0x31` 是一个邮箱值。它们发生在不同阶段。决定性测试：WPR2 错误来自寄存器写本身，而一个完全没有写的两加载过程仍撞上 `0x65`。一条声称两个码是同一回事的早期说法、在一小时内被一次受控的无写运行反驳。

为什么 FLR 有时无法恢复一个 `0x65` 卡死、见[恢复](recovery.md#flr-vs-sbr)。

### 4.5 Booter 错误 `0x35` { #booter-0x35 }

**症状（仅独立 / 无驱动工具）。** Booter 返回 `0x35`。

**原因。** `regtable_rw_indexed` 读 DMEM `0x2383` 和 `0x8e08` 处的 DMEM 寄存器描述符表并发现零。出厂签名只有 `0x1000` 字节、所以它的 DMA 只到 DMEM `0x17FF`、让那些表保持完整。利用载荷必须是 `0xF800` 字节、这样它的帧到达 `0xF748` 处的栈、这让 DMA 覆写 DMEM `0x0800` 到 `0xFFFF` 并把表清零。阶段 MAIN.6 在 DMA 前读表（完整）、MAIN.7 在之后验证（清零）、触发 `0x35`。

**修复（无驱动路径）。** 在载荷偏移量 `0x1B83`（DMEM `0x2383`）和 `0x8608`（DMEM `0x8E08`）处包含原始出厂表内容。那些内容不在任何平面文件里：它们由引导加载器在运行时从引导加载器代码和/或引导描述符里的常量生成，所以重建它们本身就是一个大子问题。应用修复后研究者立即报告让 GSP-RM 启动了。

> [!NOTE]
> **在出货路径上不可达**
>
> 出货的驱动内补丁从不撞 `0x35`。`kgspSec2PostblTimingRebuildStockSignature()` 在真实 GSP-RM 引导前恢复真实的 4096 字节签名，所以那次引导的 DMA 只到 DMEM `0x17FF`、描述符表保持完整。`0x1B83`/`0x8608` 恢复不在出货载荷里、那里也不需要。
> *（置信度：中等；从出货代码加 2026-07-20 根因分析推理、未独立插桩。）*

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

**可复现 A/B。** 没有几何或算力写、也没有 `0x1180f8` 写的发射走得更远、只在 `FBPA_00C (0x9a000c)` 失败；加一次 `0x1180f8 = 0x17100000` 写让 `FBPA_008` 和 `FBPA_00C` 两者都失败。

**修复。** 拿到一个干净的 SEC2 退出：冷启动，然后不加额外写地重发。

### 4.9 `0x24:0x72`、`BAR 0/BAR 2 failed.` { #bar2-0x72 }

**症状。** `RmInitAdapter failed!` 带 `0x24:0x72` 或 `0x72`、日志字符串 `"BAR 0/BAR 2 failed."` 在 `journal.c:4081`、即 `NV_ERR_MEMORY_ERROR`。

**原因。** 不是显存损坏、也不是 SCP 加密失败。一次前后探测显示 BAR0 到 vidmem 的路径仍返回写的模式 `0xabcdabcd`。失败的是 `kbusVerifyBar2` 里的第二个、BAR2-虚拟（MMU 翻译）测试，因为真实 Booter 在 `0x2777000` 到 `0x27fee00` 划出 WPR2 并在它正常的 ACR 工作期间设置 FBIF `0x800` 位、而驱动的 BAR2 测试缓冲区 / 实例块落进那个写保护区域。

**修复。** 在离开重度安全模式时把 WPR2 拆回：

```text
0x1FA824 = 0x1FFFFE00
0x1FA828 = 0x00000000
```

**逃生门、从未动用。** BAR2 自检经 `PDB_PROP_GPU_BROKEN_FB`、`gpuIsCacheOnlyModeEnabled` 或 `kbusIsBar2TestSkipped` 可跳过。这些在 `0x24:0x72` 仍阻塞引导时从源码识别，但 WPR2 teardown 先修复了底层原因，所以它们只被记录、从未尝试。

一次无驱动利用运行产生相同的 `0x72` 映射：它让 GPU 的 BAR2/L2/MMU（POST/DEVINIT）状态保持 ACR 配置，所以 CPU-RM 的显存自检失败。

### 4.10 RM init 带 `rpc_result = 0xFFFF` 停滞 { #rpc-ffff }

> [!WARNING]
> **实验性**
>
> 历史、净室时代、单加载重接路径。一次部分成功的重接可以到达 GSP-RM init 仍以 `RPC_HDR->rpc_result = 0xFFFF`（`NV_ERR_GENERIC`）和一个 NULL `GSP-LOG[RM]` 缓冲区停滞、意味着 RM init 非常早就失败了。在那个状态 Booter 已完成（WPR2 设好、`BOOTVEC = 0xfd00`、`finalize_1180f8` 观察到 `0x17100000` 对照一个已知良好 `0x11000000`）、驱动因 MBOX0 被破坏成 `0x31` 而重新断言 GSP 引导参数、恢复了 `WprMeta.sizeOfSignature = 0x1000`、并因 HS 锁定的寄存器给出假阴性而绕过 `kflcnIsRiscvActive`。2026-07-07 记录为 "the current wall"；RM 侧根因从未识别、整条路线被驱动内补丁取代。*（置信度：中等。）*

一个相关状态：一次失败的 GSP 交接呈现为 Xid 119 / `GSP_INIT_DONE` 超时配 mailbox0 = `0x31`、`finalize_1180f8 = 0x11000000` 和 `BOOTVEC = 0xfd00`。那里 Booter 完成了它的认证路径、RISC-V GSP 却没启动，因为没有发出 BCR 写。在 `0x37b7` 和 `0x37cc` 返回给出相同结果。

一次成功全栈重接后的参考 "good landing" 状态、供对比：

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

**读法：** 溢出夺走了 Booter 的控制、GSP 核心却从未启动。利用让引导卡住、而非被签名检查拒绝。

### 4.12 可诊断性：补丁 0002 添加什么 { #patch-0002 }

补丁 0002 存在、专门为了让 GSP 引导失败可诊断。它把致命的 `NV_ASSERT_OK_OR_RETURN` 宏转成记录的日志状态检查、产生：

```text
SEC2_DEBUG: FWSEC cmd is NULL, aborting
SEC2_DEBUG: kflcnReset for FWSEC: 0x%x
SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x
SEC2_DEBUG: FWSEC: pPreparedFwsecCmd=%p frtsSize=0x%x
SEC2_DEBUG: FWSEC status=0x%x
```

用户被要求粘进工单的大多数 `SEC2_DEBUG` 行源自这里。

### 4.13 签名大小阳性对照 { #sigtest }

如果你看到这个、它是一个**阳性对照**、不是失败：

```text
_kgspCreateSignatureMemdesc: kgsp: TEST sig override active:
  orig first 4096 B + /tmp/sig tail, total 23360 B, orig size: 4096
kgspBootstrap_TU102: [sigtest] DEVICE IS UP: GSP booted and RISCV is active
  (Booter accepted the signature)
```

这次运行在 580.167.08 上演示了漏洞。它 60 秒后仍撞上通常的 Xid 119 / WPR2-already-up 路径。

出货签名缓冲区是 `0xf800` 字节（`SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL`、63,488 字节）、**不是** `0xf700`。一次社区复现受阻于 GSP 二进制里 `fwsignature_ga100` 节只有 `0x1000` 字节、而载荷硬编码为 `0xf700`；解决方案是停止补丁固件，改为从驱动放大 `pSignatureMemdesc`。

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

从活 dmesg 读出的码置信度高，对 `0x54` 和 `0xffff` 的机制归因则低。一种解读把 `0xffff` 归因于 Booter 在几何布局改动后、于 FB 顶部、把一个 WPR2 划进一个无后备的区域；这一点尚未解决。

**邮箱地址。** SEC2 MAILBOX0 是 BAR0 `0x00840040`；GSP 邮箱是 `0x00110040`。

> [!NOTE]
> **未解问题**
>
> **邮箱 `0x31` 是什么意思从未解决。** 存在三种不兼容的解读：(a) "初始值 / 尚未写入"，**被明确撤回**，因为 `0x31` 结果是一个被写的值（驱动的引导参数物理地址、被破坏）且因为一次健康 GSP 引导把 `0x110040` 复位到 0；(b) "ACR 互斥锁被持有"，早期站稳的那个解读；(c) "SEC2 Booter 自己的成功签名"，驱动的 `0x65` 那时只是一个 60 秒完成等待超时、由 SEC2 坐在 `0x8f` teardown 状态引起。第四种用法把 `GSP_FALCON_MAILBOX0 = 0x31` 读作良好落地状态里的 "GSP-RM alive"。
> **把 `0x31` 当一个观察、不是诊断。** 什么能解决它：SEC2 Booter 自己的状态枚举，或一个产生 `0x31`、带可证明自由的 ACR 互斥锁的受控实验。

### 5.2 `RmInitAdapter` 三元组 { #codes-rminit }

首 `0x62` 是 `NV_ERR_RESET_REQUIRED`。

| 三元组 | 含义 |
|---|---|
| `(0x62:0x40:2028)` | WPR2 已 up，见[4.1](#wpr2-already-up) |
| `(0x62:0x55:2028)` | `DEVICE FAILED TO COME UP: RISCV not active after Booter Load` |
| `(0x62:0x65:2028)` | RmInitDone 超时 |
| `(0x62:0x40:2674)` | 第二张 GPU 上的初始化失败、根因未知，见[4.7](#rminit-2674) |
| `(0x62:0xffff:2119)` | `0x29` / FBPA-open 路径，见[4.8](#rminit-2119) |
| `0x24:0x72:1220` | 10 GB 下、`RmInitNvDevice` 里的一次冷启动下游阶段；与 BAR2 案例不同的阶段 |

### 5.3 SEC2 复位 PLM 可观察值 { #codes-resetplm }

在地址 `0x8403C4` 报告。GSP 对应物是 `0x001103d0`。

| 值 | 含义 |
|---|---|
| `0xff` | 干净；总线主控健康 |
| `0x8f` | `secure_teardown` 跑了（位 `[6:4]` 从 `0x7` 变 `0x0`） |
| `0x00cf` | 驱动仍已加载的部分发射状态 |

*（置信度：中等。它被跨许多运行一致地用作可观察标记，但 `0x8403C4` 处的寄存器身份在频道内被质疑、理由是地址不在熔丝清单上，而且它从未被独立文档化。见[寄存器参考](../unlock/register-reference.md)。）*

FLR 清除 SEC2 复位-PLM 污染：`0x8f` 变成 `0xff`。

### 5.4 `0xbadfXXXX` 读 { #codes-badf }

`0xbadfXXXX` 读是**权限或存在性失败、不是存储的数据**。

| 模式 | 含义 | 例子 |
|---|---|---|
| `0xbadf5040` | 读被权限级别掩码阻挡 | `FECS_FEAT_OVERRIDE 0x00409664`、`FECS_FEAT_READOUT_1 0x00409668`、第二个特性覆盖组 `0x00823830`-`0x0082383c` |
| `0xbadf1100` | PRI 目标不存在 | `PMC_BOOT_42 0x0000a800`、GA100 上的 `FUSE_OPT_FBIO_OLD 0x00021c14` |
| `0xbadf20NN`（`0xbadf2010`-`0xbadf201b`） | 目标存在但 FBPA 分区被地板清扫 | 低字节编码实例 |
| `0xbadf1002` | GA10x 变体的不存在哨兵 | 在 `0x00021C14` |
| `0xbadf5108` | 从 PL0 读 AON 安全临时区 | `0x001180f8`、`0x001182d0` |
| `0xbadf` 前缀一般 | Priv 阻挡的回读 | 例如 GSP falcon 发射块 `0x110280`-`0x110298` |

*（置信度：对三个主要家族高、对精确分类措辞中等。）*

### 5.5 其它驱动错误码 { #codes-other }

**CUDA 失败上的 `NV_ERR_INSUFFICIENT_RESOURCES (0x1A)`** 指向 WPR meta 第二遍没有拾起解锁的容量。用 `dmesg | grep -E 'Xid|NVRM.*rror'` 检查。*（置信度：中等；来自出货指南、无独立复现加修复。）*

**来自 `NVA06F_CTRL_CMD_STOP_CHANNEL` 的 `NV_ERR_RESET_REQUIRED (0x62)`** 在 `nv_gpu_ops.c:11190`、当分配越过设备真实解码边界时出现（一张过度配置的卡上在 40 GB 观察到）：

```text
nvAssertOkFailedNoLog: Assertion failed: Reset required [NV_ERR_RESET_REQUIRED] (0x00000062)
  returned from pRmApi->Control(...)
```

卡在边界以下没问题、分配一旦越过它就在通道停止时失败。

**FLR 后写 DMEM 之后的 `EXCI 0x0a (MISS_INS)`** 意味着 Booter 不再驻留 IMEM：FLR 移除了它。

---

## 6. 静默失败和操作坑 { #silent }

### 6.1 `rmmod nvidia` 清除总线主控 { #bus-master }

> [!CAUTION]
> **语料库里唯一最具操作重要性的坑**
>
> **`rmmod nvidia` 清除 PCI `COMMAND.BusMaster`。** SEC2 Booter 经 DMA 从系统内存取 ROP 载荷，所以总线主控关闭时它取不到任何东西，只能带一个空载荷运行、不执行任何 ROP 并故障退出。**日志里没有任何地方提到 DMA。** 每个写都会弹回，唯一可见的痕迹是 `resetPLM` 从 `0xff` 变 `0x8f`。

**诊断：**

```bash
setpci -s <bdf> COMMAND
# 0x0102 = 坏了（总线主控位清除）
# 0x0546 = 良好（位 2、Bus Master、置位）
```

**修复。** 发射前重新启用总线主控：

```bash
sudo setpci -s <bdf> COMMAND=0x0546
```

一个 `ensure_bus_master()` 调用被加到 refire 工具的 `prepare()` 里、让它自愈。修复后 `resetPLM` 每次发射都停在 `0xff`。

这个坑适用于独立 / 无驱动工具。出货的驱动内补丁在活驱动内运行、那里总线主控按定义已开。

### 6.2 驱动仍已加载时发射 { #driver-loaded }

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

**修复。** 卸载驱动。驱动卸载后，同一个命令给出 `PLMs: 9/9 open (fired 0 closed)`、`resetPLM=0x00ff`、`CSTATUS=20/24` 和 `READY`。失败和修复在几分钟内、同一硬件上被背靠背观察到。

### 6.3 正确拆掉驱动 { #teardown }

单独 `modprobe -r` 不够。工作的顺序：

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

每步都有守卫、所以 `set -e` 下缺失服务不会中止脚本。随后的 FLR 是：

```bash
echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset
sleep 3
```

这个 harness 跑了九个解锁周期。

### 6.4 模块不肯卸载 { #module-stuck }

nvidia 模块常无论如何都拒绝卸载、留下：

```text
nvidia 15835136 2
drm    753664 7 drm_kms_helper,drm_display_helper,nvidia,drm_buddy,i915,ttm
```

经 `drm` 对 `i915` 的依赖是一个在无头或非-NVIDIA-显示主机上做解锁工作的实用原因。那个系统上的模块大小：`nvidia_modeset` 2248704、`nvidia_uvm` 2039808。*（置信度：中等；在同一份运行日志里反复观察。）*

### 6.5 DMEM 写被静默丢弃 { #dmem-locked }

**原因。** 一旦 `nvidia.ko` 把 SEC Falcon 引导进重度安全（HS）模式、`DMEM_PRIV_LEVEL_MASK`（`0x00840284`）写保护读 0、所有 DMEM 写被丢弃。Falcon 在 HS 时 DMEM 既不能读也不能写。

**检测。**

```text
mask    = read32(0x00840284)
rd_prot = mask & 0x7
wr_prot = (mask >> 4) & 0x7      # 0 意味着 LOCKED
```

功能测试：经 DMEMC0/DMEMD0 写 `0xDEADBEEF` 到 DMEM`[0x000]` 并读回来。

**修复。** 一次 ENGINE 复位：

```text
wr32(PSEC_ENGINE, 0x1); sleep 10 ms; wr32(PSEC_ENGINE, 0x0)
poll DMATRFCMD for IDLE && !FULL
poll DMACTL & 0x6 == 0                 # scrub complete
check SCP_CTL_P2PRX bit 3 (SFK_LOADED)
check KFUSE_LOAD_CTL bit 0 set, bit 1 clear
```

或断电循环并在加载 `nvidia.ko` 前运行。

### 6.6 活 CUDA 上下文旁发射 { #live-cuda-context }

在活 CUDA 上下文旁发射解锁**确实**打开 FB-几何 PLM（`0x00100b10`：`0xffffff8f -> 0xffffffff`），却随后挂起 `nvidia-smi`，因为让 SEC2 停在 HS（旋转停放）会使驱动的健康路径不稳定。恢复是一次 `FALCON_ENGINE` 复位，它清除 HS 状态却不碰 FB 内容。*（置信度：中等。）*

### 6.7 在 `0x82xxxx` 块外写安全寄存器 { #resetplm-8f }

在 `0x82xxxx` 外写任何安全寄存器会把 SEC2 复位 PLM 重新提高到 `0x8f`，这会阻塞出厂的 `kflcnReset`、让第二次 Booter Load 以 `0x65` 失败。具名罪魁祸首：`0x1183A4`（容量临时区）、`0x9A0204`（FBPA strap）、`0x1FA8xx`（WPR）。只有 `0x82xxxx` 写豁免。**这就是算力容易解锁、显存不行的原因。** *（置信度：中等；可复现症状带一致的 `resetPLM=0x8f` 标记，但寄存器身份被质疑。）*

### 6.8 用一次复位把 PLM 打开和几何写分开 { #flr-between }

**症状。** 同一条流水线在算力 PLM 上成功、`0x009A0204` 处的 CFG1 写却弹回、三次尝试都回读出厂 `0x2449000` 而非 `0x2779000`、以 `Pipeline complete: 0/1 GPU(s) unlocked` 结束。

**原因。** FB-几何 PLM **不在**常开（AON）岛里、而特性覆盖 PLM `0x00823804` **在**。一条打开 PLM、做一次 FLR、然后写几何的分阶段流水线会跨 FLR 丢掉 FB-几何 PLM 状态。

**修复。** 绝不用一次复位把 PLM 打开和几何写分开。出货补丁在一次 GSP 引导里做两者。见[恢复：什么挺过一次复位](recovery.md#state-persistence)。

### 6.9 删除或不匹配的固件 { #firmware-deleted }

**症状。** 一次多日、无法复现的 "model degradation"、带 `SEC2 MBOX0 = 0x0`（Booter 根本没加载）。

**原因。** `/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` 被删除了、而一个 `.04` 用户态 `nvidia-smi` 不会在 `.03` 模块上触发 GPU init。

**修复。** 恢复版本匹配的固件目录、用版本匹配的 `nvidia-smi`。恢复固件立即复现先前的工作状态。

**当时记录的实际教训：** 当代理修改驱动时、保留一个 diff 或变更日志，因为重装新驱动会静默丢弃所有需要的注入。

### 6.10 磁盘上一个陈旧的已补丁 `gsp_tu10x.bin` { #stale-firmware }

如果这台机器用过 cmpunlocker 的**固件打补丁前身**，跑驱动内补丁**之前**必须把 `gsp_tu10x.bin` 恢复到出厂：

```bash
GSP_DIR=/lib/firmware/nvidia/610.43.03
sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
```

**为什么。** 驱动在引导时把固件的签名保存为 "stock"。如果固件仍被打过补丁，它保存**利用载荷**，随后一次干净的 GSP-RM 引导就 DMA 错误的 ROP 链。成功行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

### 6.11 重复驱动加载把错误码向前走 { #nondeterminism }

重复的 CPU-RM 驱动加载会渐进清理一张脏设备、把错误码向前走。一个单变量对照显示一次单独的 MMU-invalidate 运行停在 `0x24`，所以更早的 `0x24 -> 0x25` 前进来自**双重加载**（CPU-RM 自己的部分 init 清理状态）、而非 MMU 写。这也解释了观察到的非确定性：脏设备的清理是非确定的，结果每次发射都有噪声。*（置信度：中等；底层清理机制从未确认。）*

---

## 7. 构建失败 { #build }

`build.sh` 在 `set -euo pipefail` 下运行，所以任何失败的 hunk 都中止构建。它下载 `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz` 进 `driver/.build/`（缓存、经 `CMPUNLOCKER_BUILD_DIR` 可覆盖）、每次运行删除并重新解压一棵干净树，用 `patch -p1` 按字典序应用 `patches/*.patch`，然后跑 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`。构建时间约 5 分钟 *（单一报告、依赖硬件）*。

| 失败 | 原因 | 修复 |
|---|---|---|
| `Installed driver is X, but cmpunlocker requires one of: 610.43.03,610.43.02.` | 精确字符串版本白名单 | 安装 610.43.03 或 610.43.02 nvidia-open |
| 内核头文件错误、`/lib/modules/$(uname -r)/build` 缺失 | 头文件没为**运行中**内核安装 | 安装匹配头文件，或引导你为之构建的内核 |
| 补丁 hunk 被拒 | 错误的上游 tarball、或一个陈旧的 `.build/` 树 | 脚本每次运行重新解压；检查你在你以为的分支上 |
| `python3: command not found` | `build.sh` 需要 `python3` | 安装它。**master 不用 PyYAML**、出货脚本里**没有显式 GCC 版本检查** |
| 首次安装无网络 | Tarball 下载 | 预置 `driver/.build/` |
| `No initramfs tool found, rebuild manually before rebooting` | `update-initramfs`、`dracut` 和 `mkinitcpio` 都不存在 | 手工重建 initramfs，见[3.4](#initramfs) |
| Ubuntu 经 mainline 交换内核后构建坏 | 内核交换破坏了 NVIDIA 610 open 驱动构建 | 用发行版内核 |

值得显式陈述的前置条件：安全启动关（模块未签名）、nvidia-open 610.43.0x（专有驱动 "has different boot paths and cannot be patched the same way"）、**仅 Linux**（GSP 引导路径是 Linux 专属）、root、和模块为运行中内核编译。构建安装**五个**模块（`nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko`、`nvidia-peermem.ko`）、模式 `0644`、进 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。只有 `nvidia.ko` 携带解锁代码；其它四个是出厂重建。

因为补丁按 glob 应用，把一个叫 `0007-*.patch` 的第三方 diff 丢进 `driver/patches/` 会和解锁系列干净组合。那是分层层 P2P 补丁的文档化机制。见[驱动补丁](../unlock/driver-patches.md)。

**安装前移除。** 切换分支时维护者的规则是 "always remove the old one before adding the new one."（加新的之前总是移除旧的。）一位克隆 Gen2 分支、在现有安装之上安装的测试者报告它不工作、先卸载就修好了。这是指导、不是硬法律：至少另两位测试者叠加安装成功了。先移除是*受支持的*路径。*（置信度：中等；没人识别出区分因素。）*

---

## 8. PCIe Gen2 问题 { #gen2 }

> [!WARNING]
> **实验性**
>
> **`master` 上不发货任何 PCIe Gen2 补丁。** 补丁 `0007-pcie-gen2.patch` 和 `0008-pcie-gen2-probe-retrain.patch`、加 `tools/retrain.sh`、只存在于分支 `Gen2`、`far`、`debug-gen2`（只 0007 和 `tools/retrain.sh`）和 `deced` 上。`verify.sh` 是一个独立工具、发货于 `Gen2`、`far`、`deced` 和 `multiple-cards`，见[11.2](#verify-sh)。本节一切适用于实验分支。

记住**速度和位宽是各自独立的成果**。Gen1 到 Gen2 是一个驱动和固件解锁。超过 x4 位宽需要物理焊接 24 颗 0402 X7R 电容到通道 4 到 15。两者互不改变。见[PCIe Gen2](../unlock/pcie-gen2.md) 和[物理改装](../operations/physical-mods.md)。

### 8.1 Gen2 在某些机器上工作、另一些不 { #gen2-hardcoded-bdf }

**根因：一个硬编码的 PCI 地址 `0a:00.0`。** 硬编码在 *用户态辅助* `tools/retrain.sh` 里的三处（`SYS=/sys/bus/pci/devices/0000:0a:00.0`、`GPU, UP = "0a:00.0", "09:01.0"`、和 `resource0` 路径），**不在**内核补丁里：`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2` 和 `deced` 之间逐字节相同。

分支 `deced`（提交消息："Stupid mistake - it appears to be hardcoded"）用 `find_gpu_bdf()` 取代它、它经 `lspci -d 10de:20c2` / `lspci -d 10de:2082` 发现卡、最多等 120 秒等 `resource0` 和 `nvidia-smi -L`、并用 `readlink -f` 推导上游桥。**分支 `Gen2` 和 `far` 仍含硬编码。**

### 8.2 安装后 PCIe 仍在 Gen1 { #gen2-still-gen1 }

**第一检查：IOMMU passthrough。** `Gen2`、`far` 和 `deced` 安装器都经 `/etc/default/grub` 或 `/etc/kernel/cmdline` 把 `intel_iommu=on iommu=pt`（Intel）或 `amd_iommu=on iommu=pt`（AMD）追加到内核命令行、替换冲突条目、把文件备份到 `*.cmpunlocker.bak`、重新生成引导配置、每个分支自己的 `remove.sh` 恢复它。`--no-iommu` 退出。Master 一个都不碰，所以请用你安装时用的同一分支卸载。IOMMU 也必须在 BIOS/UEFI 里启用（VT-d / AMD-Vi / SVM）。

**第二检查：你的检出是最新吗？** 2026-07-29 前 Gen2 补丁是仅分支的，用户反复因为他们在 `master` 上而失败。Gen2 现在在 `master` 里，所以一个早于那次合并的检出是要排除的东西。

**第三：重训练可能退出保命了。** 独立 `retrain.sh` 在四种情况下带打印的原因提前退出：

| 消息 | 条件 |
|---|---|
| `retrain: BAR0 dead; skip` | BAR0 或 CYA 读 `0xFFFFFFFF` |
| `retrain: DIS_G2 still set; skip` | `DIS_G2`（BAR0 `0x8c2c0` 位 2）仍置位 |
| `retrain: Cap Gen1; skip` | 链路能力低于 Gen2 |
| `retrain: preconditions failed; skip` | 写后前置条件失败 |

它还在 `nvidia-smi` 不可用、显存读 `[N/A]`、链路已是 Gen2、或最大链路代不是 2、3 或 4 时带状态 0 **静默**退出。

驱动内重训练在 probe 时运行、在 `msleep(50)` 后最多轮询 2 秒（20 次尝试 × 100 ms）。它清除 BAR0 `0x8c2c0` 位 2（DIS_G2），把 `0x8c040` 的位 `[19:18]` 强到 2，向 `0x8872c` 写入 `0x00000006`，在 GPU 和上游桥上同时设置 `PCI_EXP_LNKCTL2_TLS_5_0GT`，然后在上游桥上设置 `PCI_EXP_LNKCTL_RL`（重训练链路）。它的失败输出：

```text
CMP Gen2: no upstream PCIe bridge; skipping link retrain
CMP Gen2: cannot map BAR0; skipping link retrain
CMP Gen2: PCIe capability access failed (%d); skipping link retrain
```

加 [2.7](#benign-retrain-false-negative) 描述的假阴性。

### 8.3 根端口不肯改变速度 { #gen2-root-port }

> [!WARNING]
> **实验性**
>
> 有记录、未被独立确认。如果 `sudo dmesg | grep "SEC2_DEBUG.*Root port"` 说 "upstream port not valid"，芯片组驱动没有枚举上游端口；建议的变通方案是 `setpci -s <root_port> <offset>.w=0002` 随后一次链路重训练。如果 "Root port LnkCtl2" 显示写、速度却停在 1，根端口可能不支持定向速度改变；建议的修复是一次经 `setpci -s <root_port> <link_ctrl>.w` 带位 5 置位的根端口发起重训练。**语料库任何地方都没有任何变通方案成功的测量。**

### 8.4 虚拟机里的 Gen2 { #gen2-vm }

Proxmox 直通下显存和算力解锁工作（一位操作者直通了八张 8 GB 卡、全部解锁）。**截至 2026-07-24 PCIe Gen2 链路速度改动在 VM 里不工作**、被维护者承认。重训练序列是否需要虚拟机监控程序会拦截的配置空间或链路层访问，尚未确立。

> [!NOTE]
> **未解问题**
>
> 一台主机（ASUS X99-A、LGA2011）报告一个插槽里只有 Gen2 x1、其它是 Gen1 x4，在试过 IOMMU/虚拟化设置和全部四个插槽之后。它在 2026-07-27 报告、正好是硬编码-BDF 发现落地的同一天。插槽依赖正是硬编码 BDF 会产生的东西，所以这很可能已被分支 `deced` 修复，但它从未被确认。

### 8.5 `RMPcieLinkSpeed` 分裂 { #gen2-linkspeed }

> [!NOTE]
> **未解问题**
>
> 两个分支家族发货不同的注册表值、每个作者都相信自己的对：`debug-gen2` 和 `Gen2` 写 `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`，而 `far` 和 `deced` 写 `…=0x2`（由一个标题为 "Remove clamp link to Gen1" 的提交引入）。`Gen2` 分支、那个 README 声称 Gen2 工作的，发货 `0x1`。**不存在 A/B 引导测试。** 两个值都不应作为规范呈现。同一张卡上的一次三方引导比较就能解决它。

---

## 9. 黑屏 { #black-screen }

### 9.1 运行解锁脚本时黑屏 { #black-screen-script }

> [!NOTE]
> **未解问题**
>
> 一位测试者在 2026-07-20 报告运行解锁脚本时黑屏。他们自己未经证实的假设是错误驱动安装、并拒绝进一步调试。那条线程里的两位测试者都在限制到 PCIe Gen3 的主机上。什么都没确立。

### 9.2 一般无头引导 { #headless }

CMP 170HX 没有视频输出，所以某些板子不会把它当唯一卡 POST（一块 ASRock X370-I 被报告拒绝）。请另配一张带显示的卡，或确认板子能无头引导。也见[主机不引导](#no-post)。

---

## 10. 运行时、CUDA 和工作负载失败 { #runtime }

### 10.1 Xid 31，MMU 故障，区域违规 { #xid31 }

**症状。** `Xid 31` MMU 故障带 `FAULT_INFO_TYPE_REGION_VIOLATION`；卡在重启前无法在 CUDA 中使用。一份捕获显示：

```text
ENGINE GRAPHICS HUBCLIENT_FE  faulted @ 0x7fad_3a200000 ... ACCESS_TYPE_VIRT_WRITE
ENGINE CE2      HUBCLIENT_HSCE2 faulted @ 0xf_f7400000 ... ACCESS_TYPE_PHYS_WRITE
```

**原因。** 分配越过解锁窗口可用顶端。物理地址 `0xf_f7400000` 是 63.86 GiB、正好在 64 GB 窗口顶部。

**修复。** 少往那张 GPU 上卸载一层 LLM。恢复需要一次完整重启。*（建议的修复未被确认应用。）*

> [!NOTE]
> **Xid 31 本身不是 80 GB 签名**
>
> 在 80 GB 下，触碰超过约 40 GB 的内核造成致命 GPU 丢失、与功耗上限无关。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 显存测试后的 Xid 154；主导报告症状是挂起。Xid 31 单独是一个旁观者提出的、并未被带故障卡的操作者佐证为*那个*签名。已裁决的 80 GB 图景其余部分：报告约 81920 MiB / 85,545,582,592 字节、而 `cudaMalloc` 77 GiB 成功。见[80 GB](../frontier/80gb.md)。

### 10.2 杀掉 CUDA 作业后 Xid 45 { #xid45 }

用 SIGKILL 杀一个活 CUDA 验证内核可以以 Xid 45 卡死卡、强制一次复位循环。已发布的工具带有警示：在**前台**运行、绝不要中途 SIGKILL；内核启动之间 Ctrl-C 没问题。稠密填充/检查内核在 64 GB 卡上跑很久（超过一百万个 64 KB 页），所以把它们后台化再杀掉的诱惑很真实。*（置信度：中等；作为艰难赢得的操作警告陈述、未附 dmesg 捕获。）*

### 10.3 过度配置配置上的 Xid 154 { #xid154 }

Xid 154 是过度配置 80 GB 配置上 CUDA 显存测试后的主导失败、把卡限制到每次发射一个 CUDA 上下文。一位测试者只能让 GSP-RM 工作、无法让 CPU-RM 工作；另一位不得不在尝试之间冷循环整个系统、而非只重载驱动。两者都同意显存物理上可被 CUDA 到达：开放问题是驻留和稳定性、不是可寻址性。由两位测试者在不同硬件上独立复现。

> [!NOTE]
> **未解问题**
>
> 4 GB/通道解码重新启用和 CUDA `719` → Xid 45 → Xid 154 链是同一个原子故障的两个结果、无法分开。对一个 40 GB 之上页面的原子（由 UVM 持有在主机上、因为设备只解码 40 GB）故障；CPU-RM 把页向上迁移并重新启用 4 GB/通道，但同一个故障毒化 CUDA 上下文、呈现为 `719 unspecified launch failure`、然后 Xid 45、然后 Xid 154。干净交接的尝试（用一个小的托管 "keeper" 翻转解码、释放它、然后分配非托管 77 GiB）持续出错。一个相关旋钮、被注意到但未测试：`PDB_PROP_GPU_RECOVERY_SQUASH_XID154`。

### 10.4 vLLM 在高显存利用率崩溃 { #vllm }

**症状。** vLLM 卡在 `gpu-memory-utilization 0.95` 崩溃。

**原因。** 解锁的几何布局暴露 65052 MB、实际只有 64733 MB 可用，所以 0.95 处余量很薄。

**修复。** 降到 0.9、它恢复了卡。一次独立的长多卡会话只在 0.95 带一个巨大上下文看到一个瞬态 "GPU requires reset"、自恢复。**指导：把利用率保持在 0.90 或以下。** *（置信度：中高。）* 见[LLM 推理](../operations/llm-inference.md)。

### 10.5 到处 `cuInit` 返回 999 { #cuinit999 }

**症状。** 每个框架 `cuInit` 返回 999、而 `nvidia-smi` 仍报告健康。

**原因。** 反复 `kill -9` 活的多-GPU 作业留下约 32 个僵尸 CUDA 进程、卡死主机 CUDA 运行时。

**修复。** 主机重启。**这在容器内无法修复。** 不要 `kill -9` 活的多-GPU 作业。

跨同一个完整 8 卡会话、数百个 60 秒健康样本，有 **0** 个硬故障。这是操作者诱发的失败、不是硬件问题。

### 10.6 分配越过真正可用容量 { #alloc-crash }

分配越过真正可用容量时、即使 `nvidia-smi` 报告更大数字、基准测试也崩溃。`llama-server` 在三张各报告 81920 MiB 的卡上持有 37798 / 47400 / 53960 MiB 让运行崩溃。重启后同一机架每卡加载约 32 GB（27734 / 31758 / 32754 MiB）、基准测试完成、结果与 10 GB → 40 GB 配置大致相同。

### 10.7 老化测试下的显存错误 { #burn-errors }

**症状。** 一张解锁到其稳定几何布局之外的卡在算力老化测试的几分钟内积累显存错误：

```text
2.1%  proc'd: 777 (12153 Gflop/s)   errors: 24433  (WARNING!)  temps: 85 C
```

错误在前几分钟出现。12153 Gflop/s 数字表明算力解锁是活跃的。**稳定的 10 GB → 40 GB 配置干净通过一次 5 分钟 gpu-burn**、8 GB → 64 GB 配置稳定且在生产中。

> [!NOTE]
> **未解问题**
>
> 那些 85 °C gpu-burn 错误是热还是显存超频、从未解决。一种立场："too hot, dial it back"（太热、降下来）。另一种："85 °C is within spec"（85 °C 在规格内）、核心和显存温度相差几度之内；第三位观察者叫它一个 HBM 硬件错误。另一些人报告两张停在 73 °C 以下的卡零错误。分支作者实际的解决方案是降低显存倍率、而非要求更好散热。失败卡是一颗 Samsung-显存部件。什么能解决它：同一张卡、同一倍率、强制散热停在 70 °C 以下。见[热设计](../hardware/thermals.md)。

> [!WARNING]
> **实验性**
>
> 一个相关声称、以低置信度推进、被其作者自己对冲，是 "normal stress tests don't load an unlocked card because the fuses rely on the math being thrown at them."（正常压力测试不会给解锁卡加负载、因为熔丝依赖扔给它们的数学。）从未对一个已知良好工作负载测试过。它要紧、因为它决定 gpu-burn 是否是一个足够的稳定性测试。背景：一位测试者在打补丁前无法用一个标准压力测试把卡推过 68 W。

### 10.8 `nvidia-smi --gpu-reset` 拒绝 { #gpu-reset-busy }

> [!NOTE]
> **未解问题**
>
> `nvidia-smi --gpu-reset` 在没有任何进程持有它时以 "GPU is being used by another process" 失败。**未解决。** 下一步：用 `fuser -v /dev/nvidia*` 和 `lsof /dev/nvidia*` 枚举持有者，并检查一个泄露的 `nvidia-persistenced` 或一个产生 `cuInit=999` 的那类僵尸 CUDA 进程。
>
> 同一窗口内报告的相关恢复摩擦：冷启动后卡有时需要物理拔下并重插它的 PCIe 电源线缆，而一个 CUDA 别名测试泄露它的分配，所以一次 SBR 恢复加驱动重载在运行之间是必需的。

### 10.9 解锁工作但 CUDA 不 { #cuda-clean-host }

**解决一个案例的分诊步骤：把卡移到一台干净主机。** 原主机的软件栈是怀疑的罪魁祸首；根因从未确认。在责怪解锁之前，在一台干净主机里测卡。*（置信度：中等。）*

注意卡在完全不带补丁的**出厂** Linux NVIDIA 驱动上运行（Ubuntu 24.04 上 `nvidia-driver-570` 加 CUDA 12.8 开箱即用），所以 "卡可被驱动吗" 和 "卡被解锁吗" 是可以分开测试的两个问题。

### 10.10 纯粹作为运行时变通方案存在的补丁 { #runtime-patches }

三个出货补丁只存在来修复解锁后的运行时故障。如果你在调试一个运行时故障，知道这些已经应用了：

| 补丁 | 它做什么 |
|---|---|
| 0004 `bar0-pramin-clamp` | 当 `0x20C2`/`0x2082` 上 `fbAddrSpaceSizeMb > 0x2000` 时把 BAR0 PRAMIN 窗口钳回出厂 8 GB 派生的偏移量 `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`、这样几何布局改动后窗口不会落到真实孔径之外。注意一张 10240 MB 的 10 GB 卡已经超过 `0x2000`，所以那里也接合 |
| 0005 `ce-scrub-workarounds` | 强制 `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY`（而非 `..._COMPRESSIBLE_DISABLE_PLC`）并为这些卡禁用基于 VAS 的 CE 清理路径 |
| 0006 `persistent-sw-state` | 为两个设备 ID 设置 `NV_FLAG_PERSISTENT_SW_STATE`、这样 RM 在最后一个客户端关闭时不会拆除软件状态 |

---

## 11. 多卡机架 { #multicard }

### 11.1 解锁在一个多-GPU 机架上静默什么都不做 { #multicard-silent }

**症状。** 热和冷重启后全部五张 8 GB 卡都停在出厂；验证器对每个 BDF（01:00.0、05:00.0、06:00.0、07:00.0、12:00.0）报告 `MISSING` 和 `✗ 0000:01:00.0: not found in nvidia-smi`、每个 `20c2 / 8gb` 预期约 65536 MiB，再加上 `! No SEC2_DEBUG lines in dmesg`。

**原因。** 早期工具没有多卡处理。同一个人的单卡机架用相同驱动工作。

**修复。** 对双卡 HiveOS 案例：`remove.sh`、重启、重装。两张卡随后都以 40 GB 启动。一个 `multiple-cards` 分支和一个 `verify.sh` 随后被添加、却**没有合并进 master**：master 的 `install.sh` 仍经 `head -1` 只取第一行匹配的 `lspci`。

也见[depmod 任意挑一个模块](#module-resolution)，那是同一个外表下的一个独立多-GPU 失败。

### 11.2 读 `verify.sh` 输出 { #verify-sh }

> [!WARNING]
> **实验性**
>
> `verify.sh` 只存在于分支 `deced`、`multiple-cards`、`Gen2` 和 `far` 上。三个诊断字符串值得识别：
>
> * `<bdf>: not found in nvidia-smi` 带状态 `MISSING`
> * `No SEC2_DEBUG lines in dmesg (logs may have rotated; unlock can still be OK if memory is unlocked)`
> * 致命的 `<N> GPU(s) failed unlock verification. Cold reboot if modules were just installed.`
>
> 它把设备 ID 映射到档位（`20c2 -> 8gb -> 65536 MiB`、`2082 -> 10gb -> 40960 MiB`）并从 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory` 读一份清单。

### 11.3 HiveOS 十卡案例 { #hiveos }

> [!NOTE]
> **未解问题**
>
> HiveOS beta 24.04 带十张 CMP 170HX 和 nvidia 610.43.03：`install.sh` 干净完成、打过补丁的模块在冷重启后却没加载。除重跑安装外什么都没试、也没发布修复。最有希望的下一步：跑三步分诊（[3.5](#triage-three-step)）、专门对比 `/sys/module/nvidia/srcversion` 与 cmpunlocker `.ko`、并检查 HiveOS 自己的驱动包是否重装覆盖打过补丁的模块、或 initramfs / DKMS 排序是否让出厂在前。两个候选都被点名、却都未确认。

见[多卡](multi-gpu.md)。

---

## 12. 主机和硬件级失败 { #host }

### 12.1 服务器装上卡不引导 { #no-post }

**症状。** 没有蜂鸣码、没有主板诊断 LED、"No display adapter, press F1" 已被禁用。

**有文档案例里的原因：与 GPU 无关。** 改变 PCI 插槽把网络接口改名了（从一个 `XXX5XX` 到一个 `XXX6XX` 可预测名字），所以箱子能无头引导，却没有 IP。

**修复。** 修复网络配置。

**诊断时给出的一般建议：** 用正确的电源线缆（不带转接座的 ATX/EPS 式连接器、带转接座的 PCIe 连接器）、一次试一张 GPU、并预期硬件改动后两到三次重启。卡带一个 EPS 8-pin（额定 300 W），需要一个 2 × PCIe-to-EPS 转接座。见[供电与 PSU](../operations/power-and-psu.md)。

### 12.2 虚拟机 { #vm }

**Proxmox 直通需要 SeaBIOS、不要 UEFI/OVMF。** UEFI 产生看起来恰好像利用根本不工作的 RM init / 适配器失败。一个人在意识到他们旧的可用 VM 是 SeaBIOS 前、在 "rm init adapt failures" 上花掉大量时间；第二个成员立即认出它是自己无法复现的原因。

至少一部分利用开发是在一张直通进 QEMU Q35 VM 的 GPU 上完成的、而非裸机（`QEMU Standard PC (Q35 + ICH9, 2009)`、BIOS `rel-1.17.0-0-gb52ca86e094d-prebuilt.qemu.org 04/01/2014`、GPU 在 `0000:01:00`、Ubuntu 内核 6.8.0-136-generic、nvidia-modeset 580.159.03）。那里的崩溃发出一个坏帧指针栈展开警告，故障路径走 `nvidia_drm`/`nvidia_modeset`（`EnumerateGpus -> AllocateDevice -> nvkms_open_gpu`）。

VM 里显存和算力解锁工作；PCIe Gen2 不，见[8.4](#gen2-vm)。

### 12.3 卡掉下 PCIe 总线 { #off-bus }

**症状。** 一张卡运行一小时后永久掉下 PCIe 总线、不再被检测到。如果 BAR0 读 `0xffffffff`，说明卡掉线了。先试[恢复](recovery.md#reset-ladder) 里的恢复阶梯、包括 `echo 1 > /sys/bus/pci/devices/$BDF/remove` 随后 `echo 1 > /sys/bus/pci/rescan`。

如果它从不回来，原因可能是硬件。这是 A100/170HX 级硬件上一个得到完全诊断的实例：

**原因。** 一颗死的 GS7155NVTD 3.3 V LDO 把 `PS_5V_PGOOD` 网络短路到 5 欧姆、阻止 MP1475DJ 5 V 转换器启动。可见为打嗝模式保护：一个几十纳秒的瞬时 SW-节点脉冲、几十微秒后重试。

**诊断路径。** 12 V 输入电感对地读高阻抗、插槽 12 V 无短路（排除一个粗核心短路）；核心侧输出电感无电压也无开关；焊下 MP1475DJ 后、它空焊盘的引脚 1（Power Good）对地测 5 欧姆。

**修复。** 更换 MP1475DJ 和 GS7155NVTD、然后把 `PS_5V_PGOOD` 从 U816 跨接过去。结果：3V3_SEQ 返回、开关恢复、NVVDD 1.0 V 和 PEXVDD 返回、GA100 在 PCIe 上被重新检测到。`PS_5V_PGOOD` 馈给把 PEXVDD、NVVDD、1V35 和 1V8 排序的 SN74LV1T08 AND 门、并启用产生 3V3_SEQ 的 LDO。

> [!CAUTION]
> **信任一颗新焊的 GS7155NVTD 前先做台架测试**
>
> 把 7.68 千欧反馈电阻换成 20 千欧、把输出从 3.3 V 重新编程到 1.8 V、在 5 V 轨上注入 3.3 V、确认一个稳压后的 1.8 V、然后恢复 7.68 千欧部件。要防范的危险是一个**开路反馈引脚**（QFN 上一个可能的冷焊点失败）：它会让 LDO 看到永久欠压并把输出驱到最大、把完整 5 V 放到 3.3 V 轨上、毁掉几乎所有 3.3 V 逻辑。这块 8 到 12 层板的返工基准：任何芯片能拆下前、热风 420 °C 吹 2 分钟。GS7155NVTD 是一颗其完整数据手册在 NDA 下的 GSTEK QFN 部件。

### 12.4 到货时的卡况 { #dirty-cards }

退役矿卡到货时脏得吓人：厚重灰尘、生锈 PCIe 挡板、散热器里盐壳、金手指裸露且无连接器盖。使用前需要清洁、重打导热膏和换新导热垫。**外观状况不是解锁失败的预测器：** 一张肉眼可见脏污的卡，第一次尝试就干净解锁到 64 GB。*（对跨多个独立开箱的状况报告置信度高；对 "not a predictor" 结论、它建立在单一样本上、置信度中等。从未发布过批次级解锁良率。）*

> [!WARNING]
> **实验性**
>
> 一个未受挑战却无数据支撑的立场认为，长期欠冷的 HBM "should be dead by now unless it's had a very low operating time"（除非运行时间极短、现在应该早就死了），而且 HBM 一旦超过安全温度就快速退化。许多卡可能是近乎零小时、因为 CMP 170HX 于九月发布、市场到十一月就无利可图。没有失效率或温度数据支持或反驳它。

2026 年 7 月下旬涨价期间卖家说的 "defective batch"（有缺陷批次）措辞**不是**真实硬件缺陷群体的证据：它被用作对已展示过可工作卡的列表的取消借口。有文档的案例里没有实际发货或诊断过有缺陷的卡。

### 12.5 挺过冷启动的不可中断睡眠卡死 { #d-state }

**症状。** 一张 10 GB 卡困在一个挺过约五次冷重启、并阻止 Ubuntu 关机的 "uninterruptible sleep" 状态。

**原因。** 一个自动加载的补丁内核驱动、不是卡。

**修复。** 让卡断开引导（或 `blacklist nvidia`），然后清理。*（置信度：中等；根因由受影响的测试者在恢复后识别。）*

这个的一个更硬变体在[恢复](recovery.md#bricking) 里被诚实讨论。

---

## 13. 升级和报告 { #escalation }

`install.sh` 写一个带时间戳的日志到 `logs/install_YYYYMMDD_HHMMSS.log`；`remove.sh` 写 `logs/remove_YYYYMMDD_HHMMSS.log`。`remove.sh` 在仓库目录不可写时回退到 `/tmp`；`install.sh` 则不会，而是在启动时就中止。**把最新的安装日志附到任何支持请求。**

一份有用的报告包含：

1. 操作系统和版本、内核（`uname -r`）
2. GPU 型号和驱动版本
3. 整个主机的 `lspci -nn`
4. 完整的 `sudo dmesg | grep SEC2_DEBUG`
5. 最新的安装日志
6. `cat /lib/modules/$(uname -r)/updates/cmpunlocker/{driver_version,card_profile,unlock_geometry}`

响应是单操作者的、且慢：第一份文档化的 Gen2 工单等了约 10.5 小时才收到首次回复（06:21 开、16:59 回）。

---

## 14. 没有已知修复的症状 { #unsolved }

> [!NOTE]
> **未解问题**
>
> 这些被记录、以免被当作新问题重新发现。没有一个有已发布的解决。
>
> * **Ubuntu 24.04、内核 6.8.0-111-generic、驱动 610.43.03 上冷重启后的 `NVRM initialization error`。** 冷重启（先前为同一测试者清除了一个 srcversion 不匹配）没帮助。`SEC2_DEBUG` 行存在、寄存器在写、这指向一个寄存器写后的初始化失败、而非一个失败的解锁链，但没人追查。下一步：捕获 `SEC2_DEBUG` 块**之后**的完整 dmesg、包括 `normal BooterLoad status` 行和任何 `RmInitAdapter` 三元组，把失败放进序列。
> * **运行利用后立即、普通驱动第一次 `insmod` 上的内核 panic 加重启。** 2026-07-01 被问一次、从未回答。下一步：捕获 panic（串行控制台或 `pstore`）；可比较 QEMU 捕获里的故障路径走 `nvidia_drm`/`nvidia_modeset`，所以发射前卸载那些是第一个廉价测试。
> * **缺少 iGPU 或 BMC 显示设备会搅乱 GSP 吗？** 一个观察、无确认、无反驳、无错误字符串。一台机器上、BIOS 里禁用 BMC 显示设备的一次 A/B 能回答它。
> * **80 GB 不稳定：`cuda_memtest` 在重启后立即一次通过全部 80 GB、随后每次重试失败。** 功率限制到 100 W 和供电假设都已被排除。重启依赖指向显存训练或刷新状态。这是 80 GB 档位最具体的剩余线索。见[80 GB](../frontier/80gb.md)。
> * **Ubuntu-对比-Arch 显存解锁失败。** 一种解读：两个 PCIe 设备之间的一次显存地址冲突，一个非-170HX、非-2080 设备（大概一个 M.2 SSD）试图在 IOMMU 拒绝的地址读。受影响的测试者自己的解读：Ubuntu 安装就是配置错了。只有变通方案（在另一个 M.2 SSD 上的不同 OS 安装）被验证。当时推荐的第一诊断：`lspci -s 06:00.0`。
> * **PLM 的预期数量。** 独立工具报告 "9/9 open"、一位审查者预期 "0 or 26, not 1"（0 或 26、不是 1）。出货的驱动内路径打开恰好 4 个。这些是不同的 PLM 清单，但记录里没有任何东西把 9 条目或 26 条目清单映射到出货的 4 条目 `plmTable`。

整个项目未解决项的完整清单见[未解问题](../frontier/open-questions.md) 和[状态板](../frontier/status-board.md)。

---

## 相关页面

* [恢复](recovery.md)：冷启动、FLR、SBR 和什么实际持久
* [验证](verify.md)：完整安装后清单
* [安装](install.md)：受支持流程
* [卸载](uninstall.md)：`remove.sh` 和手动回滚
* [驱动版本](driver-versions.md)：支持并启动测试过哪些版本
* [多卡](multi-gpu.md)：多卡安装
* [权限级别掩码](../unlock/privilege-level-masks.md)：PLM 表做什么
* [寄存器参考](../unlock/register-reference.md)：本页命名的每个寄存器
* [死路](../history/dead-ends.md)：试过并反驳的假设
