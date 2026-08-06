# 解锁一览

**本页覆盖内容。** CMP 170HX 解锁实际做什么、不做什么、哪些部分出货、哪些只活在未发布分支上、两个按 SKU 的几何布局档位，以及接下来该去哪里看细节。这是整个解锁部分的入口。这里的每一个数字都是规范值；更深页面携带证据。

## 头条结果

出货的 `cmpunlocker` 补丁集移除 CMP 170HX 上的**两项**出厂限制，并添加一个便利标志。它移除 SM 速度选择节流，在 GA100 硅片上恢复约 30 倍 FP32 FMA 和完整张量吞吐，并重写帧缓冲几何布局，使 8 GB 卡枚举 **65536 MiB（64 GB）**、10 GB 卡枚举 **40960 MiB（40 GB）**。两者都在每次驱动加载的 GSP 引导路径内自动发生，约一秒钟，不需要焊接、不刷 VBIOS、不伪造签名。

机制是对 NVIDIA 自己签名的 SEC2 Booter Load ucode 的一次纯数据攻击：驱动把 GSP 签名缓冲区从约 4 KB 放大到 `0x0000f800`、用精心构造的 Falcon ROP 载荷填满它，并让 Booter 签名验证路径内的一次无界 DMA 覆写 Falcon 的栈。那在每次 Booter 运行里给出一条 Heavy-Secure 权限级别的任意 BAR0 写，被用来打开四个权限级别掩码。之后，普通的主机寄存器写入完成实际解锁。没有去盖晶片、没有提取密钥、RSA 引导 ROM 检查从未被破坏。完整叙述见[如何工作](how-it-works.md)。

> [!CAUTION]
> **这会废除一切并可能丢失数据**
>
> 打过补丁的内核模块未签名，所以安全启动必须关闭、内核被污染。给解锁的卡超频会在不崩溃的情况下静默损坏内存。10 GB 卡上的 80 GB 配置报告它无法可靠交付的容量。在跑任何超出出厂档位的东西之前，读[Risks](../start/risks.md) 和[调优](../operations/tuning.md)。

## 状态表

| 能力 | 状态 | 它住在哪 | 机制 |
|---|---|---|---|
| SM 速度选择节流被移除 | **已出货，稳定** | `master`，补丁 0001 | 打开 `FEAT_OVR_PLM 0x00823804` 后 `SS0 0x0082381c = 0x88888888`、`SS1 0x00823820 = 0x00000008` |
| 显存几何布局 8 GB 到 64 GB | **已出货，稳定，生产中** | `master`，补丁 0001 | `CFG1 0x009a0204 = 0x02779000`、`LMR 0x00100ce0 = 0x0000020B` |
| 显存几何布局 10 GB 到 40 GB | **已出货，稳定** | `master`，补丁 0001 | `CFG1 = 0x02669000`、`LMR = 0x0000028A` |
| 向 CUDA 宣告的容量 | **已出货** | `master`，补丁 0001 + 0003 | GSP 静态信息 `fb_length` 重写加一次晚期 PMA 区域扩展 |
| 内置持久化模式 | **已出货** | `master`，补丁 0006 | PCI 探测时设置 `NV_FLAG_PERSISTENT_SW_STATE`；不需要守护进程 |
| PCIe Gen1 到 Gen2（5 GT/s） | **实验性，仅分支** | `debug-gen2`、`Gen2`、`far`、`deced`；补丁 0007 / 0008 | 25 次 Booter 路由的寄存器写加普通 BAR0 写，然后上游桥重训练 |
| 超过 x4 的 PCIe 位宽 | **仅硬件** | 根本不是软件 | 24 颗手工焊接的 0402 交流耦合电容 |
| MIG（多实例 GPU） | **社区发现，未合并** | 树里任何地方都没有 | `0x820840` 的位 0；一位研究者、三份佐证的 `nvidia-smi` 输出 |
| 10 GB 卡到 80 GB | **尝试过并放弃** | `80` 分支 | 超过约 40 GB 真实使用就不可靠 |
| PCIe Gen3 / Gen4 | **未达到** | 任何地方都没有 | `FUSE_PCIE_GEN23_DIS` 和 `FUSE_PCIE_GEN3_DIS` 都读 `0x00000001` |
| ECC | **未达到** | 任何地方都没有 | 熔断关闭，没有找到杠杆；名为 `ecc` 的分支不含任何 ECC 代码 |
| NVLink | **未达到** | 任何地方都没有 | 熔丝禁用（`FUSE_NVLINK_DIS`）；不存在 FEAT_OVR 条目 |
| 超过 70 个 SM | **未达到** | 任何地方都没有 | 每条 GPC 禁用写入路径都被锁存，包括 HS 特权写 |
| 点对点（P2P） | **缺失** | 任何地方都没有 | 这张卡上不存在 |
| 更高时钟 | **不是解锁的一部分** | NVML，树外 | 通过 `nvmlDeviceSetGpcClkVfOffset` 的 GPC 时钟 VF 偏移；见[调优](../operations/tuning.md) |

解锁刻意不碰两样东西：**时钟速度**和**PCIe 总线速度**。频道内的规范表述是 "compute limit yes, bus speed no"（算力限制可以、总线速度不行），它与出货机制一致，后者在时钟表或 PCIe 配置块里什么都不写。

## 两个 SKU 档位

几何布局在**运行时按 PCI 设备 ID** 选择，不在构建时选择。两个档位都编译进同一个模块，而 `master` 上的 `driver/build.sh` 完全不做任何源码重写。

| 量 | 8 GB 卡 | 10 GB 卡 |
|---|---|---|
| PCI ID | `10de:20c2`（`0x20C2`） | `10de:2082`（`0x2082`） |
| 出厂容量 | 8192 MiB | 10240 MiB |
| 解锁容量 | **65536 MiB（64 GB）** | **40960 MiB（40 GB）** |
| 出厂 `CFG1 0x009a0204` | `0x02449000` | `0x02449000` |
| 解锁 `CFG1` | `0x02779000` | `0x02669000` |
| 出厂 `LMR 0x00100ce0` | `0x00000208` | `0x00000288` |
| 解锁 `LMR` | `0x0000020B` | `0x0000028A` |
| `targetFbBytes` / `fb_length` | `0x0000001000000000`（64 GiB） | `0x0000000A00000000`（40 GiB） |
| 活动 FBPA / FBP | 16 个 FBPA、8 个 FBP | 20 个 FBPA、10 个 FBP |
| 显存总线 | 4096-bit | 5120-bit |
| `SS0` / `SS1` | `0x88888888` / `0x00000008` | 相同 |
| SM 数 | 70（CC 8.0，4480 个 CUDA 核心） | 70（相同） |
| GPC 时钟偏移余量 | VBIOS `0x47177` / `0x47179` 持有 `freqDelta = ±1000` | 两者读 0 |

> [!WARNING]
> **永远不要把档位搞混**
>
> 8 GB 到 64 GB。10 GB 到 40 GB。把 8 GB 几何布局应用到 10 GB 卡上是一个有记录可查的失败模式，而 10 GB 卡的 80 GB 配置被尝试过并发现不稳定。见[显存几何布局](memory-geometry.md)。

**第三个**设备 ID `10de:20b0` 会被 `install.sh` 的 `lspci` 扫描匹配，但**不**被解锁：驱动内门 `_kgspSec2PostblTimingEnabled()` 只接受 `0x20C2` 和 `0x2082`。这样的卡干净安装、走出厂路径启动、从不触发。任何暗示解锁只由 `0x20C2` 门控的 README 措辞都已过时。

## 出货的与实验性的

**出货 `master`** 是应用到一份未修改的 `open-gpu-kernel-modules` tarball 上的六个编号补丁，共 37,415 字节：

| 补丁 | 大小 | 它做什么 |
|---|---|---|
| `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 B | 整个解锁：签名放大、载荷、PLM 循环、寄存器写、签名重建、静态信息重写 |
| `0002-booter-verify.patch` | 3,988 B | 把四个致命断言降级并添加 `POST-BooterLoad verify` 回读 |
| `0003-late-pma.patch` | 10,580 B | 把 8 GiB 之上的帧缓冲用 PMA 注册，使其可分配 |
| `0004-bar0-pramin-clamp.patch` | 861 B | 让 PRAMIN 窗口保持在可达的 BAR0 空间内 |
| `0005-ce-scrub-workarounds.patch` | 1,642 B | 强制复制引擎清理器进入物理模式 |
| `0006-persistent-sw-state.patch` | 603 B | 设置持久软件状态标志 |

`master` 上受支持的驱动版本恰好是 **`610.43.03`（默认）和 `610.43.02`**，按精确字符串匹配；构建在其它任何版本上硬性失败。仅 Linux、仅 nvidia-open、安全启动关闭。见[驱动版本](../procedures/driver-versions.md) 和[安装](../procedures/install.md)。

**十二个未发布分支快照**存在（算上 `master` 是十三棵树）：`80`、`Gen2`、`PG199`、`clanker_driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`。

> [!WARNING]
> **实验性**
>
> **PCIe Gen2** 只在 `Gen2` 家族出货。补丁 `0007-pcie-gen2.patch` 存在于 `debug-gen2`、`Gen2`、`far` 和 `deced` 上；`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2`、`far` 和 `deced` 上。Gen2 家族 PLM 表从四项增长到九项。Gen2 不确定、在 VM 直通下不工作，而且四个分支中两个（`Gen2` 和 `debug-gen2`）把 `RMPcieLinkSpeed` 设成 Gen1 枚举 `0x1`，`far` 和 `deced` 设成 `0x2`；没有任何 A/B 启动测试定论过哪个值对。见[PCIe Gen2](pcie-gen2.md)。

> [!WARNING]
> **实验性**
>
> **`clanker_driver-port`** 分支添加 `580/`、`590/`、`595/` 和 `610/` 补丁目录。每个寄存器值和载荷偏移量都与 `master` 逐字符相同，而 `610` 目录是它的一份逐字节副本。595 / 590 / 580 移植**仅源码验证**：补丁干净应用，没人报告过启动。

> [!WARNING]
> **`memory` 分支是单设备并硬编码 8 GB 档位**
>
> `memory` 先于双几何布局支持。它的补丁 `0001` 硬编码 `SEC2_POSTBL_TIMING_CMP_170HX_PCI_DEVICE_ID 0x20C2`、`cfg1Value = 0x02779000U` 和 `lmrValue = 0x0000020BU`，没有设备 ID 分支也没有 10 GB 路径：`0x2082` 卡在那个分支上根本不被解锁。不要期望运行时档位选择而从它构建。

`ecc` 分支根本不含任何 ECC 实现：全部六个驱动补丁都与 `master` 逐字节相同。`docs` 分支的 `ARCHITECTURE.md` 是一个文档缺陷、不应被引用：它把 SS0/SS1 叫 "Suspension State" 寄存器、声称两者都被写成 `0xffffffff`、把 PLM 展开为 "Program Logic Modules"，并打印代码里任何地方都不存在的日志行。

## 解锁买到什么，实测

日期 2026-07-06 的行来自一张随第一份私有 "compute unlock working" 报告贴出的单个渲染映像，而非来自具名工具输出。出处注意事项见[compute-throttle.md](compute-throttle.md)。

| 指标 | 锁定 | 解锁 | 备注 |
|---|---|---|---|
| FP32 IEEE（2026-07-06，一张卡） | 0.41 TF/s | 12.69 TF/s | 31.0x；理论上限 12.63 TFLOPS（4480 x 2 x 1410 MHz） |
| FP64 非张量 | 0.20 TF/s | 6.2-6.31 TF/s | FP32 的 1/2，完整 GA100 速率 |
| FP64 张量（DMMA） | n/a | 11.5-12.9 TF/s | 约为非张量速率的两倍。两个 FP64 数字并不矛盾：一次 clpeak 运行并排打印了 `double : 6308.65` GFLOPS 和 `wmma_fp64 : 11.96` TFLOPS |
| BF16 张量（2026-07-27，8 张租用卡） | 6.40 TF/s | 164.4-192.7 TF/s | 跨八张租用卡加一张调优参考卡 |
| FP16 张量（2026-07-27，8 张租用卡） | 6.52 TF/s | 158.7-190 TF/s | |
| INT8（2026-07-06，一张卡） | 1.63 TOP/s | 50.50 TOP/s | 30.9x。一场更晚的 8 租用卡行动（2026-07-27）在库路径上测得 44.1 TOPS、没有匹配的锁定基线；INT8 *张量*路径测得 335 TOPS |
| FP16 标量（非张量） | 约 42-50 TFLOPS | 不变 | 从不被节流，这正是锁定卡当时已可用于 token 生成的原因 |
| INT32 | 约 12.5 TIOPS | 不变 | 从不被节流 |
| HBM 带宽 | 1305.86-1600 GB/s | 不变 | 一个跨工具和访问模式的范围，不是一个数值 |
| 持续 SM 时钟 | 1410 MHz | 不变 | `-pl 300` 下 1470 MHz；`clocks.max.sm = 1935 MHz` 只是一个报告字段，低置信度 |

成功信号是 `0x00823818` 处的 `FEAT_READOUT_1` 读 `0x00000000`。出厂 170HX 读 `0x016db6ed`。那个单一寄存器是可用的最干净的 "这张卡被解锁了吗" 测试。

> [!NOTE]
> **未解问题**
>
> 解锁后 INT8 / IMMA 仍被门控，尽管 IMLA 覆盖半字节与 FMLA 和 FFMA 的设置方式相同。在 A100 上，INT8 大约比 FP16 快 2 倍；在解锁的 170HX 上它慢 3.7 倍。对推理的实际后果：用 W4A16（AWQ、GPTQ）并完全避开 W8A8。见[LLM 推理](../operations/llm-inference.md)。

## 它为什么能工作

三个事实支撑一切：

1. **主灭杀熔丝未烧断。** `0x008203f0` 处的 `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` 在 CMP 170HX 上读 `0x00000000`。若它被烧断，所有特性覆盖都会被永久锁定、不存在任何软件路径。
2. **GA100 加载 Turing 代固件。** GSP 映像是 `gsp_tu10x.bin`，SEC2 booter 是 Turing 谱系的 `booter_load`，它携带无界-DMA bug。GA100 的 `booter_load` 二进制在驱动分支 580 到 610 之间逐位相同。
3. **调试和量产 booter 映像包含相同的明文代码。** 只有 AES 密钥不同，而调试密钥是一把非机密的编号测试密钥，所以量产 HS 代码可以不靠任何泄露源码被读取。

该利用是对一个厂商签名 blob 的纯数据攻击，其验证密钥熔进不可变的硅片，所以这个脆弱的 booter 不能被驱动更新吊销。这是对信任模型的推断，不是已演示的结果。

## 更深页面的地图

| 页面 | 覆盖 |
|---|---|
| [如何工作](how-it-works.md) | 按启动顺序的完整端到端机制，以及为什么每一步是必要的 |
| [Falcon 与 Booter](falcon-and-booter.md) | SEC2 硬件接口、booter 提取与解密、内部结构、漏洞 |
| [ROP 链](rop-chain.md) | 载荷布局、gadget、栈金丝雀破解、终止符、写预算 |
| [权限级别掩码](privilege-level-masks.md) | PLM 是什么、四项出货表、九项 Gen2 表、FLR 存活 |
| [显存几何布局](memory-geometry.md) | CFG1 和 LMR 编码、每-FBPA 传播、为什么 LMR 是必需的、80 GB 墙 |
| [算力节流](compute-throttle.md) | SS0/SS1 语义、速度选择熔丝、门链、实测吞吐 |
| [驱动补丁](driver-patches.md) | 全部六个补丁逐 hunk、`install.sh`、`build.sh`、`remove.sh`、版本移植 |
| [PCIe Gen2](pcie-gen2.md) | 补丁 0007 和 0008、`xp3gTable`、重训练、分支历史 |
| [寄存器参考](register-reference.md) | 每个地址、每个实测值，按 SKU 和按对比部件 |

相邻材料：位宽上限和电容改装的 [PCIe 子系统](../hardware/pcie-subsystem.md)、焊接本身的[物理改装](../operations/physical-mods.md)、确认解锁成功的[验证](../procedures/verify.md)、它不触发时的[排障](../procedures/troubleshooting.md)、以及仍开放事项的[状态板](../frontier/status-board.md)。
