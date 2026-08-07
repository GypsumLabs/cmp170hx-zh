# 验证解锁

**本页内容。** 本页说明如何用证据而不是希望证明解锁确实生效：每种 SKU 的 `nvidia-smi` 应报告什么，如何逐行读取 `SEC2_DEBUG` 内核日志，已安装的元数据文件能说明什么、不能说明什么，分支专属的 `verify.sh` 如何工作，如何确认额外显存是真实显存而不是地址别名，以及如何确认**算力**解锁。算力解锁与显存容量完全是两个独立结果，需要单独测量。

重点是：8 GB 卡上的 `nvidia-smi` 报告 **65536 MiB**，或 10 GB 卡上的 `nvidia-smi` 报告 **40960 MiB**，只能证明显存几何布局写入成功，不能证明算力解锁。算力解锁依靠两次寄存器写入（SS0 `0x0082381c` = `0x88888888`、SS1 `0x00823820` = `0x00000008`），而这两次写入对 `nvidia-smi` 不可见。确认它们的唯一方式，是从 `SEC2_DEBUG` 日志回读寄存器，或测量吞吐量。

---

## 三层验证及其证据

| 层 | 含义 | 主要证据 | 次要证据 |
|---|---|---|---|
| 显存**容量** | CFG1 + LMR 几何布局，以及 GSP `fb_length` 和 PMA 重写 | `nvidia-smi` 总显存 | `SEC2_DEBUG: POST-WRITE ... CFG1=... LMR=...` |
| 显存**真实性** | 报告的容量由不同的物理 DRAM 支持，而不是地址别名 | `check_fold.py` 报告 `REAL, NO FOLD` | 运行大型 `gpu_burn` 或 `cuda_memtest` 且全程无错误 |
| 算力**吞吐量** | FEAT PLM 打开后写入 SS0/SS1 | `SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008` | 与锁定基线对比的 FP32/OpenCL 基准测试 |

一张卡可能通过其中一层，却在另一层失败。算力解锁可以挺过功能级复位，而显存几何布局不能；这正是算力解锁早于显存解锁发布的原因。

---

## 各 SKU 的 `nvidia-smi` 预期

| 项目 | 8 GB 卡（`10de:20c2`） | 10 GB 卡（`10de:2082`） |
|---|---|---|
| 出厂 `memory.total` | 8192 MiB | 10240 MiB |
| 解锁后 `memory.total` | **65536 MiB** | **40960 MiB** |
| 写入的 CFG1 `0x009a0204` | `0x02779000` | `0x02669000` |
| 写入的 LMR `0x00100ce0` | `0x0000020B` | `0x0000028A` |
| 写入的 GSP `fb_length` | `0x0000001000000000`（64 GiB） | `0x0000000A00000000`（40 GiB） |
| 报告的产品名称 | 在出厂驱动上为 `NVIDIA Graphics Device`，因为 PCI ID 表没有市场名称 | 相同 |
| 计算能力 | 8.0 | 8.0 |
| SM 数量 | 70（4480 个 CUDA 核心） | 70 |
| PCIe 链路（出厂状态） | gen 1、最大 gen 1、位宽 4 | gen 1、最大 gen 1、位宽 4 |

```bash
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,clocks.max.sm,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current --format=csv
```

读取结果时：

- **8 GB 卡报告 8192 MiB，表示解锁没有触发。** 这是泄露分发版 README 中用于失败分诊的判断行，而且判断是正确的：PLM 没有打开，因此后续操作也没有发生。
- **出厂容量和目标容量之间的任何数值都不表示“部分解锁”。** 几何布局是一组根据 PCI 设备 ID 选定的固定 CFG1 + LMR 值；它要么写入成功，要么没有写入成功。

> [!CAUTION]
> **81920 MiB 不是成功**
>
> 如果一张 10 GB 卡报告约 81920 MiB，而 CUDA 看到 85,545,582,592 字节（79.67 GiB），说明它运行的是实验性的 80 GB 档位，而不是发布版的 40 GB 配置。`cudaMalloc` 分配 77 GiB 可以成功，但访问约 40 GB 以上区域的内核会导致 GPU 致命丢失，与功耗上限无关。报告的 Xid 代码包括 Xid 31（有人将其描述为无害），以及 CUDA 显存测试后的 Xid 154；最主要的已报告症状是卡死。单独把 Xid 31 视为该故障的特征，是旁观者提出的说法，出现故障的卡的操作者并未证实这一点。80 GB 配置已经试验过并被放弃。见[80 GB](../frontier/80gb.md)。所有提及该配置的文档都记录它不稳定；`80` 分支 README 中的 “Working” 行属于文档错误。

> [!NOTE]
> **`clocks.max.sm = 1935 MHz` 是报告字段，不是可达到的时钟**
>
> `install.sh` 建议把检查 `clocks.max.sm` 作为验证第 4 步，而且解锁卡确实会报告 1935 MHz。应将这个数字视为**低置信度**信息，而不是工作时钟：VBIOS 表中的最大图形时钟为 1695 MHz，实际晶片上限在 +350 偏移下约为 1604-1614 MHz。所有持续测量都停留在标称 **1410 MHz**，或在 `-pl 300` 下达到 **1470 MHz**。见[调优](../operations/tuning.md)。

---

## `SEC2_DEBUG` dmesg 轨迹

每个解锁动作都会以 `SEC2_DEBUG:` 前缀记录。这个前缀，以及 `SEC2_DEBUG_PRI_*` 寄存器名称和 `kgspSec2PostblTiming*` 函数名称，在出厂版 610.43.03 源码中都不存在；“PostBL Timing”是一个仿造 NVIDIA 风格创造的功能名称。实际操作很简单，只需执行：

```bash
sudo dmesg | grep SEC2_DEBUG
sudo dmesg | grep -c SEC2_DEBUG      # 计数会随构建版本和显卡数量变化，见下文
```

> [!NOTE]
> **日志行数不是通过/失败判据**
>
> 每个归档中的计数都不同，没有任何一个计数可以作为指纹。唯一归档的单卡 8 GB 捕获包含 **29** 行；唯一归档的双卡 Gen2 分支 `610.43.03` 引导日志包含 **134** 行。`pcielink.sh` 报告工具在两台独立的双卡 Gen2 设备上打印过 `SEC2_DEBUG lines=152`（一台是 HiveOS 主机，另一台是 Unraid 主机），记录中还出现过 34（Gen1 构建）和 80（Gen2 构建）。不要因为行数不匹配就判断安装失败，判据是下面的寄存器回读行。

在健康引导过程中，这些日志大致按以下顺序输出。

| 日志行（格式） | 阶段 | 读取方式 |
|---|---|---|
| `SEC2_DEBUG: saved stock signature (4096 bytes)` | 载荷覆盖签名缓冲区之前 | 如果缺少此行，或大小不正确，磁盘上的 GSP 固件可能仍然是从固件时代的前身版本打过补丁的版本 |
| `SEC2_DEBUG: loaded 63488 bytes from /lib/firmware/nvidia/ga100/gsp/dmem.bin` | 载荷来源 | 仅当你有意放置覆盖载荷时才会出现 |
| `SEC2_DEBUG: <path> not found (0x59), using built-in payload` | 载荷来源 | **正常。** `0x59` 是无害状态；此时使用目标为 `0x009a0148 = 0xffffffff` 的内置载荷 |
| `SEC2_DEBUG: WPR meta fbSize=... wprEnd=... heapSize=...` | 第一次 `kgspPopulateWprMeta_HAL` | 这是解锁前的几何布局，因此这里的 `fbSize` 仍然反映出厂容量 |
| 携带 `status=0xffff` 的每个 PLM 尝试行 | 四项 PLM 循环 | **每次载荷运行都预期出现。** 载荷运行结束后，Booter 总会在 mailbox0 中留下一个错误 |
| `SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff` | PLM 循环结果 | 这是决定性的 PLM 判定，见下表 |
| `FAILED to open %s after 2 attempts` | PLM 循环失败 | 每个 PLM 最多尝试两次；该行会指出未能打开的 PLM |
| `SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)` | 主机寄存器写入 | **本页最有用的一行。** 将四个值全部与上面的 SKU 表进行比较 |
| `SEC2_DEBUG: WPR meta updated fbSize=... wprStart=... wprEnd=... heapOffset=... heapSize=...` | 第二次 `kgspPopulateWprMeta_HAL` | 此时应与扩大的几何布局一致 |
| `SEC2_DEBUG: normal BooterLoad status=0x%x` | 真实引导过程中的 Booter 运行 | 这一行应为 `NV_OK`，不同于载荷运行时的状态 |
| `SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...` | 引导后的回读 | 只有正常 BooterLoad 返回 `NV_OK` 时才会打印。**这是证明解锁挺过真实 GSP 引导的证据** |
| `SEC2_DEBUG: static-info BEFORE` / `AFTER` | GSP 静态配置重写 | `fb_length` 和最后一个 FB 区域扩大 |
| `SEC2_DEBUG_HEAP: fbAddrSpace=... mapRam=... fbTotal=... fbUsable=... heapTotal=... regionBytes=... publicBytes=... numRegions=...` | 堆创建后 | PMA 操作的诊断信息 |
| `SEC2_DEBUG: late PMA extension status=0x%x` | 显存伪装的第二阶段 | `0x0` 表示成功。非零状态表示额外显存从未注册到分配器，即使几何布局写入成功也一样 |
| `SEC2_DEBUG: rebuild stock signature failed: 0x%x` | 仅在失败时出现 | 如果无法恢复出厂签名，整个初始化过程会中止 |

### 正确读取 PLM 行

| PLM | 地址 | 预期值 | 注意 |
|---|---|---|---|
| WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | **不是** `0xffffffff`。这是代码写入的值，也是代码检查的值 |
| FBPA | `0x009a0148` | `0xffffffff` | 同时也是内置载荷的默认目标 |
| WPR | `0x001fa7c4` | `0xffffffff` | |
| FEAT | `0x00823804` | `0xffffffff` | 出厂值为 `0xffffff8f`；始终开启，可以挺过功能级复位 |

### 日志缺失时

环形缓冲区会轮转。对于显存状态正确的卡，缺少 `SEC2_DEBUG` 轨迹是警告而不是失败，`verify.sh` 也按此处理。要强制获取一条新的轨迹，可以冷启动后立即执行 grep，或增大内核日志缓冲区。

---

## 已安装的元数据文件

```bash
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile      # 8gb | 10gb | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry   # 64GB | 40GB | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version    # 例如 610.43.03
cat /lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory     # 仅分支提供，见 multi-gpu.md
```

这些是由 `build.sh` 写入的单行文件。**内核模块中没有任何代码会读取它们。** 它们记录的是安装器所“相信”的内容，而不是驱动实际执行的操作。如果一台机器上的 8 GB 卡启动后报告 65536 MiB，但 `card_profile` 却是 `10gb`，这是元数据错误而不是解锁错误，因为几何布局是在 GSP 引导时根据 PCI 设备 ID 选择的。打过补丁的内核在引导时唯一会读取的文件，是可选的 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。

另外还有两项有用的检查：

```bash
cat /proc/driver/nvidia/version        # 如果补丁模块正在运行，不应显示 dvs-builder
cat /sys/module/nvidia/srcversion      # 与下方结果比较：
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

`srcversion` 不匹配，表示当前运行的是出厂模块。这与[多卡](multi-gpu.md)中描述的多 GPU depmod 歧义属于同一类失败。

---

## `verify.sh`

> [!WARNING]
> **实验性：仅分支提供的脚本**
>
> `verify.sh` **不存在于** `master`。它只存在于 `multiple-cards`、`Gen2`、`far` 和 `deced` 分支。`master` 上同样没有 `tools/` 目录或测试套件。

`verify.sh` 是一个多 GPU 安装后检查器。它需要 `nvidia-smi`，缓存
`nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits` 的结果，然后枚举 GPU：优先使用已安装的 `gpu_inventory` 文件；如果没有该文件，则回退到 `lspci -nn | grep -iE '10de:20c2|10de:2082'`。

它会为每个 GPU 分类报告的容量：

| 配置档位 | `is_unlocked_memory` | `is_stock_memory` |
|---|---|---|
| `8gb` | `>= 60000` MiB | `7680`-`8704` MiB |
| `10gb` | `35000`-`59999` MiB | `9728`-`10752` MiB |

然后打印四种状态之一：

| 状态 | 含义 |
|---|---|
| `OK` | 容量处于解锁窗口内 |
| `STOCK` | 仍然是锁定容量 |
| `MISSING` | BDF 完全不在 `nvidia-smi` 输出中 |
| `UNEXPECTED` | 对于该配置档位，容量既不是出厂值，也不是解锁值 |

之后，它会在 `dmesg` 中搜索 `SEC2_DEBUG`，打印最后八条匹配行作为样本，打印已安装的 `card_profile` 和 `unlock_geometry`，最后以以下两种结果之一结束：

```text
✓ All 4 unlockable GPU(s) report unlocked memory
```

退出码为 0；或者：

```text
✗ 1 GPU(s) failed unlock verification. Cold reboot if modules were just installed.
```

退出码为非零。

两个已知缺口：

- **`verify.sh` 从不检查 PCIe Gen2**，即使在 Gen2 分支谱系中也不检查。在 `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 中搜索 “pcie” 都会得到零个匹配。链路验证完全需要手动进行，见[PCIe Gen2](../unlock/pcie-gen2.md)。
- **`verify.sh` 从不检查算力。** 显存容量是唯一的通过判据。

---

## 确认显存真实存在而不是地址别名

报告容量和可用容量是两个不同的主张。需要排除的失败模式是**折叠**：地址空间发生回绕，使高地址成为低地址的别名。

`check_fold.py` 是权威测试。它不在仓库中：与 `cuda_dbg.py` 一样，它以 gist 或频道附件的形式在仓库之外发布，因此需要单独获取，不要指望克隆仓库时得到它。该工具会分配全部空闲 VRAM 减去 2 GiB 的空间，用 PTX `sm_80` 的 `fill` 内核写入每个 64 KB 页自己的索引，然后用 `chk` 内核读回每个页面；它使用 `st.global.wt.u32` 写入和 `ld.global.cv.u32` 读取来避免缓存影响。测试必须是稠密的，因为折叠会在通道**交错**偏移处产生别名：`LOW[0]` 会映射到 `(40 GiB + interleave)`，而不是 `(40 GiB + 0)`，所以稀疏探测会产生假阴性。

| 输出 | 退出码 | 含义 |
|---|---|---|
| `REAL, NO FOLD` | 0 | 该容量由不同的物理 DRAM 支持 |
| `FOLD/mismatch @<pageindex>` | 1 | 在该页面检测到地址别名 |
| error | 2 | harness 本身存在问题 |

更轻量和更重量级的替代方案：

- `cuda_dbg.py` 是快速别名测试：先调用 `cuMemGetInfo_v2`，然后依次尝试以 64、60、56、52、48、44、42 GiB 调用 `cuMemAlloc_v2`，直到某个大小分配成功；接着用 `cuMemsetD32_v2` 在偏移 0 写入 `0xAAAA0000`，在 40 GiB 处写入 `0xBBBB0000`，再读回偏移 0 的内容。如果偏移 0 读到 `0xBBBB0000`，说明地址空间发生别名。该工具会泄漏它的分配，因此每次驱动加载后只能运行一次。
- `cuda_memtest` 1.2.3 是维护者推荐的社区验证工具，遇到第一个错误就退出。在 80 GB 配置上，它会打印 `Attached to device 0 successfully.`，然后无限期卡住，除非将分配上限限制为 39 GB。这个卡死是对 `80` 分支 README 中 “Working” 声明的主要反证，而不是一个微弱信号。
- 泄露分发版的 README 建议在 64 GB 卡上运行 `./gpu_burn -m 63500 -d 30`，预期显存错误数为零。

> [!WARNING]
> **折叠测试 harness 曾经产生过假阳性**
>
> 一个早期的折叠/别名 harness 曾把*原生、未解锁*显存报告为折叠：一次将系统恢复到一致的原生状态（10240 MiB、驱动 610.43.03、CFG1 `0x02449000`）后的对照运行，分配了 9 GiB 的真实原生显存，却在五次测试中报告 “4608 chunks, 4608 corrupt/aliased”，这是不可能的。这一事件从事后看使大量早期“40 GB 处发生折叠”的结论失效。应信任 `check_fold.py` 的稠密测试方法，并将临时脚本给出的任何折叠结果视为尚未证明，直到原生对照运行干净结束。

---

## 确认算力吞吐量，并与显存容量区分

算力解锁是打开 FEAT PLM 后对 SS0 和 SS1 执行的一对写入。这些写入是由主机 CPU 发起的 `GPU_REG_WR32` 调用；PLM 打开后不涉及利用，而且对两个 SKU 都是**无条件执行**的。

| 寄存器 | 地址 | 锁定状态 | 解锁状态 |
|---|---|---|---|
| SS0（`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED`） | `0x0082381c` | 例如 `0x53540175` | `0x88888888` |
| SS1（`..._SM_SPEED_1`） | `0x00823820` | | `0x00000008` |
| FEAT_OVR_PLM | `0x00823804` | `0xffffff8f` | `0xffffffff` |

### 第 1 步：回读寄存器

`POST-WRITE` 和 `POST-BooterLoad verify` 两行都会包含 SS0 和 SS1。如果正常 BooterLoad 之后两者分别读为 `0x88888888` 和 `0x00000008`，就表示本次引导中的算力已解锁。这是成本最低、最直接的确认方式，即使某张卡的显存解锁失败，也可以使用这种方式。

### 第 2 步：测量吞吐量

寄存器回读只能证明写入成功，不能证明晶片的行为确实发生了变化。健康解锁卡的参考数据如下：

| 项目 | 数值 | 备注 |
|---|---|---|
| SM 数量 | 70 | 使用 PTX `%smid` 转储器测量，而不仅仅是读取报告值 |
| 理论 FP32 | 12.63 TFLOPS | 4480 核心 x 2 x 1410 MHz |
| 持续 SM 时钟 | 1410 MHz，`-pl 300` 下为 1470 MHz | 基础时钟为 1140 MHz |
| TDP / 软件最大功耗上限 | 250 W / 300 W | 只有搭载 NVIDIA OC mining VBIOS 的卡支持 300 W；在出厂 CMP VBIOS 上，`nvidia-smi -pl` 范围为 100-250 W |
| HBM 带宽，实测 | 一个**范围**：1305.86-1600 GB/s | 取决于工具和访问模式，没有单一的规范数值 |
| HBM 理论峰值 | 1555.2 GB/s（1448.4 GiB/s） | 1215 MHz DDR x 5120-bit |

应使用算力基准测试，而不是显存基准测试：项目自己的概念验证截图使用了 [OpenCL-Benchmark](https://github.com/ProjectPhysX/OpenCL-Benchmark)，也有人使用 `clpeak` 和 `mixbench`。应在解锁前的同一张卡上，使用同一个基准测试、同一个驱动和同一个功耗上限进行对比。见[性能](../operations/performance.md)。

### 关于 FMA 锁定的说明

除 SS0/SS1 之外，该部件的 FP32 融合乘加吞吐量还受到限制，但可以通过编译器标志绕过：`nvcc -fmad=false`；对 OpenCL 使用 `#pragma OPENCL FP_CONTRACT OFF`，并通过宏遮蔽 `fma()`/`mad()`；对 SYCL 使用 clang 的 `-ffp-contract=off`。一个 2023 年的**锁定卡** FluidX3D 案例在移除 FMA 后达到 7,681 MLUPs/s，性能提升 3.4 倍；另一份 2023 年报告则通过相同方法，将锁定卡的 FP32 从 0.395 提升到 6.285 TFLOPS。这些都是解锁前的数值。SS0/SS1 写入后，FP32 FFMA 不再受到节流（普通构建可达到 12.2-12.8 TFLOPS），也不再需要 no-FMA/no-DP4A 补丁。**基准测试接近 6.25 TFLOPS 的卡，表现出的是解锁失败特征，而不是 FMA 收缩伪影**。见[性能](../operations/performance.md)。

---

## 完整验证清单

> [!WARNING]
> **`check_fold.py` 和 `cuda_dbg.py` 不在仓库中**
>
> 两者都是以 gist 和频道附件的形式在仓库之外发布的，必须单独获取。克隆仓库不会得到其中任何一个。

```bash
# 1. 正确的模块正在运行
cat /proc/driver/nvidia/version                       # 不应显示 dvs-builder
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko

# 2. 本次引导执行过解锁
sudo dmesg | grep SEC2_DEBUG | grep -E 'PLMs|POST-WRITE|POST-BooterLoad|late PMA'

# 3. 容量
nvidia-smi --query-gpu=memory.total --format=csv,noheader

# 4. 容量是真实的
python3 -u check_fold.py <BDF>                         # 预期：REAL, NO FOLD   （仓库外脚本，不在仓库中）

# 5. 算力
#    从 POST-WRITE 行读取 SS0/SS1，然后将 FP32 与锁定基线进行基准对比

# 6. 多卡设备（分支脚本）
sudo ./verify.sh
```

如果任何一步失败，请参考按症状组织的[排障](troubleshooting.md)；[恢复](recovery.md)介绍了如何处理卡死的显卡。
