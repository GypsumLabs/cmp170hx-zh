# 验证解锁

**本页覆盖内容。** 如何带着证据而非希望证明一次解锁真正落地：每个 SKU 上 `nvidia-smi` 应说什么、如何逐行读 `SEC2_DEBUG` 内核日志行、已安装的元数据文件有什么含义、分支专属 `verify.sh` 如何工作、如何确认额外显存是*真实*的而非别名折叠、以及如何确认**算力**解锁——那是与显存容量完全分离的一个结果，需要它自己的测量。

**要点。** `nvidia-smi` 在 8 GB 卡上报 **65536 MiB**、在 10 GB 卡上报 **40960 MiB**，证明显存几何布局写落地了。它关于算力什么都证明不了。算力由两次对 `nvidia-smi` 不可见的寄存器写（SS0 `0x0082381c` = `0x88888888`、SS1 `0x00823820` = `0x00000008`）解锁，确认它们的唯一方式是从 `SEC2_DEBUG` 日志回读，或做基准测试。

---

## 三层，以及每一层的证据

| 层 | 它是什么 | 主要证据 | 次要证据 |
|---|---|---|---|
| 显存**容量** | CFG1 + LMR 几何布局、加 GSP `fb_length` 和 PMA 重写 | `nvidia-smi` 总显存 | `SEC2_DEBUG: POST-WRITE ... CFG1=... LMR=...` |
| 显存**真实性** | 报告的容量由不同的物理 DRAM 支持、而非别名 | `check_fold.py` 报告 `REAL, NO FOLD` | 一次零错误的大 `gpu_burn` 或 `cuda_memtest` 运行 |
| 算力**吞吐** | FEAT PLM 打开后写 SS0/SS1 | `SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008` | 一次对比锁定基线的 FP32/OpenCL 基准测试 |

一张卡可能通过一个、却失败另一个。算力解锁挺过功能级复位而显存几何布局不能，这恰是算力先于显存发布的原因。

---

## 每个 SKU 的 `nvidia-smi` 预期

| 量 | 8 GB 卡（`10de:20c2`） | 10 GB 卡（`10de:2082`） |
|---|---|---|
| 出厂 `memory.total` | 8192 MiB | 10240 MiB |
| 解锁 `memory.total` | **65536 MiB** | **40960 MiB** |
| 写的 CFG1 `0x009a0204` | `0x02779000` | `0x02669000` |
| 写的 LMR `0x00100ce0` | `0x0000020B` | `0x0000028A` |
| 写的 GSP `fb_length` | `0x0000001000000000`（64 GiB） | `0x0000000A00000000`（40 GiB） |
| 报告的产品名 | 出厂驱动上 `NVIDIA Graphics Device`，因为 PCI ID 表没有市场名 | 相同 |
| 计算能力 | 8.0 | 8.0 |
| SM 数 | 70（4480 个 CUDA 核心） | 70 |
| PCIe 链路（出厂） | gen 1、max 1、位宽 4 | gen 1、max 1、位宽 4 |

```bash
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,clocks.max.sm,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current --format=csv
```

读结果：

- **8 GB 卡上的 8192 MiB 意味着解锁没触发。** 那是泄露分发自己 README 里的失败分诊行，它是对的：PLM 打开，以及其后的一切，都没发生。
- **出厂大小和目标大小之间任何东西都不是部分解锁。** 几何布局是从 PCI 设备 ID 选出的一个固定 CFG1 + LMR 对；它要么落地、要么没有。

> [!CAUTION]
> **81920 MiB 不是成功**
>
> 一张 10 GB 卡报告约 81920 MiB、CUDA 看到 85,545,582,592 字节（79.67 GiB）的，跑的是实验性 80 GB 档位、不是已发布的 40 GB 档位。`cudaMalloc` 77 GiB 成功，但触碰超过约 40 GB 的内核造成致命 GPU 丢失、与功耗上限无关。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 显存测试后的 Xid 154；主导报告症状是挂起。Xid 31 单独是一个旁观者提出的、并未被带故障卡的操作者佐证为*那个*签名。80 GB 配置被尝试过并放弃。见[80 GB](../frontier/80gb.md)。提到它的每份文档都把它记录为不稳定；`80` 分支 README 的 "Working" 行是一个文档缺陷。

> [!NOTE]
> **`clocks.max.sm = 1935 MHz` 是一个报告字段、不是可达时钟**
>
> `install.sh` 建议把检查 `clocks.max.sm` 作为验证的第 4 步，而解锁卡确实报告 1935 MHz。把那个数字当作**低置信度**、而不是一个工作时钟：VBIOS 表里的最大图形时钟是 1695 MHz，实际硅片天花板在 +350 偏移下约 1604-1614 MHz。每次持续测量都停在 **1410 MHz** 标称、或 `-pl 300` 下 **1470 MHz**。见[调优](../operations/tuning.md)。

---

## `SEC2_DEBUG` dmesg 轨迹

每次解锁动作都以 `SEC2_DEBUG:` 前缀记录。那个前缀，连同 `SEC2_DEBUG_PRI_*` 寄存器名和 `kgspSec2PostblTiming*` 函数名，在出厂 610.43.03 源码的任何地方都不出现；"PostBL Timing" 是一个虚构的、貌似 NVIDIA 的功能名。实际后果是一次 grep：

```bash
sudo dmesg | grep SEC2_DEBUG
sudo dmesg | grep -c SEC2_DEBUG      # 计数随构建和卡数变化，见下
```

> [!NOTE]
> **行数不是通过/失败测试**
>
> 每个归档的计数都不同、没有一个是指纹。唯一归档的单卡 8 GB 捕获含 **29** 行。唯一归档的双卡 Gen2 分支 `610.43.03` 引导日志含 **134**。`pcielink.sh` 报告工具在两台独立双卡 Gen2 机架上打印 `SEC2_DEBUG lines=152`（一台 HiveOS 主机和一台 Unraid 主机），34（Gen1 构建）/ 80（Gen2 构建）也在记录中。不要把不匹配读成安装失败。下面那些寄存器回读行才是判据。

健康引导上这些行大致按这个顺序发出。

| 日志行（格式） | 阶段 | 如何读 |
|---|---|---|
| `SEC2_DEBUG: saved stock signature (4096 bytes)` | 载荷覆盖签名缓冲区之前 | 如果这行缺失或大小不对，磁盘上的 GSP 固件可能仍从固件时代前身被打过补丁 |
| `SEC2_DEBUG: loaded 63488 bytes from /lib/firmware/nvidia/ga100/gsp/dmem.bin` | 载荷来源 | 只有你刻意放置覆盖载荷时 |
| `SEC2_DEBUG: <path> not found (0x59), using built-in payload` | 载荷来源 | **正常。** `0x59` 是良性的；用目标 `0x009a0148 = 0xffffffff` 的内置载荷 |
| `SEC2_DEBUG: WPR meta fbSize=... wprEnd=... heapSize=...` | 第一次 `kgspPopulateWprMeta_HAL` | 解锁前几何布局，所以这里 `fbSize` 仍反映出厂大小 |
| 带 `status=0xffff` 的每-PLM 尝试行 | 四条目 PLM 循环 | **每次载荷趟都预期。** Booter 在载荷运行后总是在 mailbox0 留下一个错误 |
| `SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff` | PLM 循环结果 | 决定性的 PLM 判决。见下表 |
| `FAILED to open %s after 2 attempts` | PLM 循环失败 | 每个 PLM 最多两次尝试；这命名没打开的那个 |
| `SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)` | 主机寄存器写 | **本页唯一最有用的行。** 把四个值对比上面的 SKU 表 |
| `SEC2_DEBUG: WPR meta updated fbSize=... wprStart=... wprEnd=... heapOffset=... heapSize=...` | 第二次 `kgspPopulateWprMeta_HAL` | 现在与加宽的几何布局一致 |
| `SEC2_DEBUG: normal BooterLoad status=0x%x` | 真实引导的 Booter 运行 | 这个应该是 `NV_OK`、不像载荷趟 |
| `SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...` | 引导后回读 | 只在正常 BooterLoad 返回 `NV_OK` 时打印。**这是解锁挺过真实 GSP 引导的证明** |
| `SEC2_DEBUG: static-info BEFORE` / `AFTER` | GSP 静态配置重写 | `fb_length` 和最后 FB 区域被加宽 |
| `SEC2_DEBUG_HEAP: fbAddrSpace=... mapRam=... fbTotal=... fbUsable=... heapTotal=... regionBytes=... publicBytes=... numRegions=...` | 堆创建后 | PMA 工作的诊断 |
| `SEC2_DEBUG: late PMA extension status=0x%x` | 显存欺骗的第二阶段 | `0x0` 是成功。这里非零状态意味着额外显存从没注册给分配器、即使几何布局写落地了 |
| `SEC2_DEBUG: rebuild stock signature failed: 0x%x` | 仅失败 | 出厂签名无法恢复时整个 init 中止 |

### 正确读 PLM 行

| PLM | 地址 | 预期值 | 注意 |
|---|---|---|---|
| WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | **不是** `0xffffffff`。这是代码写的*和*检查的值 |
| FBPA | `0x009a0148` | `0xffffffff` | 也是内置载荷的默认目标 |
| WPR | `0x001fa7c4` | `0xffffffff` | |
| FEAT | `0x00823804` | `0xffffffff` | 出厂 `0xffffff8f`；常开、挺过功能级复位 |

### 当日志缺失时

环形缓冲区会轮转。显存正确的卡上缺失 `SEC2_DEBUG` 轨迹是一个警告、不是失败，而 `verify.sh` 就这么对待它。要强制一条新鲜轨迹，冷启动并立即 grep、或提高内核日志缓冲区大小。

---

## 已安装的元数据文件

```bash
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile      # 8gb | 10gb | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry   # 64GB | 40GB | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version    # 例如 610.43.03
cat /lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory     # 仅分支，见 multi-gpu.md
```

这些是 `build.sh` 写的单行文件。**内核模块里没有任何东西读它们。** 它们记录安装器*相信*了什么，不是驱动*做*了什么。一台 8 GB 卡以 65536 MiB 启动、`card_profile` 却是 `10gb` 的机器是一个元数据 bug，不是解锁 bug，因为几何布局在 GSP 引导时从 PCI 设备 ID 选择。打过补丁的内核引导时唯一读的文件是可选 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`。

两个进一步有用的检查：

```bash
cat /proc/driver/nvidia/version        # 如果打过补丁的模块是活的，不应说 dvs-builder
cat /sys/module/nvidia/srcversion      # 对比：
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

`srcversion` 不匹配意味着运行中的模块是出厂那个。那是与[多卡](multi-gpu.md) 描述的多卡 depmod 歧义同一类的失败。

---

## `verify.sh`

> [!WARNING]
> **实验性：仅分支脚本**
>
> `verify.sh` **不**存在于 `master` 上。它只在 `multiple-cards`、`Gen2`、`far` 和 `deced` 分支上。`master` 上也没有 `tools/` 目录、没有测试套件。

`verify.sh` 是一个多卡安装后检查器。它需要 `nvidia-smi`，缓存 `nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits`，然后枚举 GPU：优先使用已安装的 `gpu_inventory` 文件，否则回退到 `lspci -nn | grep -iE '10de:20c2|10de:2082'`。

每张 GPU 它分类报告的大小：

| 档位 | `is_unlocked_memory` | `is_stock_memory` |
|---|---|---|
| `8gb` | `>= 60000` MiB | `7680`-`8704` MiB |
| `10gb` | `35000`-`59999` MiB | `9728`-`10752` MiB |

并打印四种状态之一：

| 状态 | 含义 |
|---|---|
| `OK` | 在解锁窗口内 |
| `STOCK` | 仍处于锁定大小 |
| `MISSING` | BDF 完全不在 `nvidia-smi` 输出里 |
| `UNEXPECTED` | 对那个档位既非出厂也非解锁的大小 |

然后它 grep `dmesg` 找 `SEC2_DEBUG`、打印最后八条匹配行作样本、打印已安装的 `card_profile` 和 `unlock_geometry`，并以下面之一结束：

```text
✓ All 4 unlockable GPU(s) report unlocked memory
```

退出 0，或

```text
✗ 1 GPU(s) failed unlock verification. Cold reboot if modules were just installed.
```

退出非零。

两个已知缺口：

- **`verify.sh` 从不检查 PCIe Gen2**，即使在 Gen2 分支谱系上也如此。grep `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 找 "pcie" 返回零命中。链路验证完全手动；见[PCIe Gen2](../unlock/pcie-gen2.md)。
- **`verify.sh` 从不检查算力。** 显存大小是唯一的通过判据。

---

## 确认显存是真实的、非别名的

报告容量和可用容量是不同的主张。要排除的失败模式是**折叠**：地址空间回绕、让高地址别名低地址。

`check_fold.py` 是权威测试。它不在仓库里：像 `cuda_dbg.py` 一样，它作为 gist 或频道附件在带外分发，所以请单独获取它，别指望克隆能提供它。它分配全部空闲 VRAM 减 2 GiB，用一个 PTX `sm_80` `fill` 内核给每个 64 KB 页写入自己的索引，然后用一个 `chk` 内核把每页读回来，用 `st.global.wt.u32` 存储和 `ld.global.cv.u32` 加载来挫败缓存。它必须是稠密的，因为折叠在一个通道-**交错**偏移量处别名：`LOW[0]` 映射到 `(40 GiB + interleave)`、不是 `(40 GiB + 0)`，所以一次稀疏探测给出假阴性。

| 输出 | 退出码 | 含义 |
|---|---|---|
| `REAL, NO FOLD` | 0 | 容量由不同的物理 DRAM 支持 |
| `FOLD/mismatch @<pageindex>` | 1 | 在那个页检测到别名 |
| error | 2 | harness 问题 |

更轻和更重的替代：

- `cuda_dbg.py` 是一个快速别名测试：`cuMemGetInfo_v2`，然后 `cuMemAlloc_v2` 在 64、60、56、52、48、44、42 GiB 尝试、直到一个成功，然后 `cuMemsetD32_v2` 在偏移量 0 写 `0xAAAA0000`、在 40 GiB 写 `0xBBBB0000` 并读偏移量 0 回来。在偏移量 0 读到 `0xBBBB0000` 意味着空间别名。它泄漏它的分配，所以每次驱动加载跑一次。
- `cuda_memtest` 1.2.3 是维护者推荐的社区验证器；它遇到第一个错误就退出。在 80 GB 档位上它打印 `Attached to device 0 successfully.` 然后无限期挂起、除非分配被封顶在 39 GB。那个挂起是 `80` 分支 README "Working" 声称的主要反证、不是弱信号。
- 泄露分布的 README 建议在一张 64 GB 卡上跑 `./gpu_burn -m 63500 -d 30`、预期零显存错误。

> [!WARNING]
> **折叠 harness 产生过假阳性**
>
> 一个早期 fold/alias harness 把*原生、未解锁*显存报告为折叠：一次复位到一致原生态（10240 MiB、驱动 610.43.03、CFG1 `0x02449000`）后的对照运行分配了 9 GiB 真原生显存、却在五次趟里报告 "4608 chunks, 4608 corrupt/aliased"，那是不可能的。那事后追溯地使一批更早的 fold-at-40 GB 结论失效。信任 `check_fold.py` 的稠密方法，并把任何来自临时脚本的 fold 结果当作未证明、直到一次原生对照运行干净回来。

---

## 确认算力吞吐，区别于容量

算力解锁是 FEAT PLM 打开后对 SS0 和 SS1 的那对写。它们是来自主机 CPU 的 `GPU_REG_WR32` 调用，PLM 打开后不再涉及利用，而且对两个 SKU 都**无条件**。

| 寄存器 | 地址 | 锁定 | 解锁 |
|---|---|---|---|
| SS0（`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED`） | `0x0082381c` | 例如 `0x53540175` | `0x88888888` |
| SS1（`..._SM_SPEED_1`） | `0x00823820` | | `0x00000008` |
| FEAT_OVR_PLM | `0x00823804` | `0xffffff8f` | `0xffffffff` |

### 第 1 步：回读它们

`POST-WRITE` 和 `POST-BooterLoad verify` 两行都携带 SS0 和 SS1。如果正常 BooterLoad 后它们读 `0x88888888` 和 `0x00000008`，本次引导算力已解锁。这是最便宜、最直接的确认，而且在显存解锁失败的卡上也有效。

### 第 2 步：测吞吐

寄存器回读证明写落地了；它不证明硅片表现不同。健康解锁卡的参考数值：

| 量 | 值 | 备注 |
|---|---|---|
| SM 数 | 70 | 用 PTX `%smid` 转储器测量、不仅报告 |
| 理论 FP32 | 12.63 TFLOPS | 4480 核心 x 2 x 1410 MHz |
| 持续 SM 时钟 | 1410 MHz、`-pl 300` 下 1470 MHz | 基础 1140 MHz |
| TDP / 最大软件功耗上限 | 250 W / 300 W | 只有带 NVIDIA OC mining VBIOS 的卡是 300 W；出厂 CMP VBIOS 上 `nvidia-smi -pl` 范围 100-250 W |
| HBM 带宽、实测 | 一个**范围**、1305.86-1600 GB/s | 取决于工具和访问模式；没有单一规范数值 |
| HBM 理论峰值 | 1555.2 GB/s（1448.4 GiB/s） | 1215 MHz DDR x 5120-bit |

用算力基准测试、不要用显存测试：项目自己的概念验证截图用 [OpenCL-Benchmark](https://github.com/ProjectPhysX/OpenCL-Benchmark)，`clpeak` 和 `mixbench` 也在用。在解锁前同一张卡上、同一驱动、同一功耗上限下、与同一个基准测试对比。见[性能](../operations/performance.md)。

### 关于 FMA 封锁的一个注意事项

与 SS0/SS1 分开，这个部件上 FP32 融合乘加吞吐被限制，但可以用编译器标志绕开：`nvcc -fmad=false`、OpenCL 的 `#pragma OPENCL FP_CONTRACT OFF` 加对 `fma()`/`mad()` 的宏遮蔽、或 SYCL 的 clang `-ffp-contract=off`。一个 2023 **锁定卡** FluidX3D 案例在移除 FMA 后达到 7,681 MLUPs/s、提升 3.4 倍；另一份 2023 报告通过同一条路线把锁定卡 FP32 从 0.395 → 6.285 TFLOPS。这些都是解锁前的数字。SS0/SS1 写之后 FP32 FFMA 不再节流（普通构建 12.2-12.8 TFLOPS），no-FMA/no-DP4A 补丁也不再必要。**基准测试接近 6.25 TFLOPS 的卡是一个失败的解锁签名，不是 FMA 收缩伪影**。见[性能](../operations/performance.md)。

---

## 完整验证清单

> [!WARNING]
> **`check_fold.py` 和 `cuda_dbg.py` 不在仓库里**
>
> 两者都作为 gist 和频道附件带外发布、不经由仓库，必须单独获取。克隆得不到任何一个。

```bash
# 1. 正确的模块是活的
cat /proc/driver/nvidia/version                       # 不是 dvs-builder
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko

# 2. 解锁本次引导执行了
sudo dmesg | grep SEC2_DEBUG | grep -E 'PLMs|POST-WRITE|POST-BooterLoad|late PMA'

# 3. 容量
nvidia-smi --query-gpu=memory.total --format=csv,noheader

# 4. 容量是真实的
python3 -u check_fold.py <BDF>                         # 预期：REAL, NO FOLD   （带外脚本，不在仓库里）

# 5. 算力
#    从 POST-WRITE 行读 SS0/SS1，然后对锁定基线做 FP32 基准测试

# 6. 多卡机架（分支脚本）
sudo ./verify.sh
```

如果任何一步失败，[排障](troubleshooting.md) 按症状组织，[恢复](recovery.md) 覆盖卡死的卡。
