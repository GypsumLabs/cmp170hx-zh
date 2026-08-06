# CMP 170HX 中的 GA100 晶片

**本页内容。** 物理硅片：工艺、晶体管数、晶片尺寸和封装；GPC / TPC / SM 层级，以及 170HX 实际有多少 SM、相对 A100 又如何；决定那个数量的地板清扫熔丝以及它们如何逐晶片变化；显存分区和缓存层级；计算能力以及随之而来的指令集；以及哪些固定功能引擎存在、被熔断关闭或物理缺失。

要旨：**CMP 170HX 携带与 NVIDIA A100 相同的 GA100 晶片**，TSMC 7 nm，542 亿晶体管，826 mm²。它是那颗晶片的一个收获分级，8 GB 卡上标记 `GA100-105F-A1`、10 GB 卡上标记 `GA100-105A-A1`，**8 个 GPC 中 5 个激活：35 TPC、70 SM、4480 个 FP32 通道、计算能力 8.0**。两个 SKU 都恰好枚举 70 个 SM。CMP 限制没有任何移除 SM 的部分，[算力解锁](../unlock/compute-throttle.md) 也不会加回任何 SM：挖矿专属的限制是一个放在独立熔丝里的发射速率分频器，而你得到的 SM 数就是该分级普通的硅片熔丝下限。

每张 170HX 都读 `PMC_BOOT_0`（`0x00000000`）= `0x170000a1`，这是 GA100 的芯片 ID 签名。GA10x 消费级对照在同一偏移量读 `0xb74000a1`，所以这一个 dword 就是足够的"这真是 GA100 吗"测试。

---

## 晶片与封装

| 属性 | 值 | 备注 |
|---|---|---|
| 架构 | Ampere GA100 | 与 A100 同一颗晶片，不是 CMP 专属的流片 |
| 工艺 | TSMC 7 nm（N7） | |
| 晶体管 | 542 亿 | 65.6 M/mm² 密度 |
| 晶片面积 | 826 mm² | 处于或接近 7 nm 掩模版极限（约 830 mm²） |
| 封装 | BGA-2743，约 55 × 55 mm | 散热器螺栓孔距 57 × 68 mm（中心到中心） |
| ASIC 标记，8 GB | `GA100-105F-A1` | GPU 料号 `20C2-105-A1` |
| ASIC 标记，10 GB | `GA100-105A-A1` | GPU 料号 `2082-105-A1` |
| 零售 A100 对比标记 | `GA100-883AA-A1` | 与 170HX 晶片并排拍过照 |
| `PMC_BOOT_0` `0x00000000` | `0x170000a1` | 在每个有效 GA100 上 |
| PCI 设备 ID | `10de:20c2`（8 GB）/ `10de:2082`（10 GB） | 参见[板卡与变体](board-and-variants.md) |
| 计算能力 | 8.0（`sm_80`） | OpenCL 3.0，CUDA 11+ |
| 基础 / 加速 SM 时钟 | 1140 MHz / 1410 MHz | `nvidia-smi -pl 300` 下观察到 1470 MHz |
| TDP / 最大软件功耗上限 | 250 W / 250 W（出厂 VBIOS） | `nvidia-smi -q` 报告 Min 100 W、Max 250 W；只有带 NVIDIA OC mining VBIOS 的卡才有 300 W。DevCap 里的插槽功耗上限是 75 W |

PCB 是 A100 40 GB PCIe 参考设计，故意删除了部件，所以板级缺失（VRM 相、NVLink 接口 IC、PCIe 交流耦合电容）与晶片级缺失是不同的话题。参见[物理改装](../operations/physical-mods.md) 和[板载供电](power-delivery.md)。

---

## GPC / TPC / SM 层级

GA100 的规模寄存器独立于熔断内容描述完整晶片。它们在 170HX 上和一个 A100 类参考部件上读相同：

| 规模寄存器 | 地址 | 值 | 含义 |
|---|---|---|---|
| `PTOP_SCAL_NUM_GPCS` | `0x00022430` | `0x8` | 完整晶片 8 个 GPC |
| `PTOP_SCAL_NUM_TPC_GPC` | `0x00022434` | `0x8` | 每 GPC 8 个 TPC → 64 TPC → 完整晶片 128 SM |
| `PTOP_SCAL_NUM_FBPS` | `0x00022438` | `0xc` | 12 个 FBP |
| `PTOP_SCAL_NUM_FBPAS` | `0x0002243c` | `0x18` | 24 个 FBPA（GA102 RTX 3090 读 6） |
| `PTOP_SCAL_NUM_LTCS` | `0x00022454` | `24` | 24 个 L2 缓存切片 |
| `PTOP_SCAL_FBPA_PER_FBP` | `0x00022458` | `2` | 每 FBP 2 个 FBPA |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246c` | `12` | 晶片上 12 个 NVLink 单元 |
| `PTOP_FS_STATUS` | `0x00022470` | `0x0000003f` | 地板清扫状态 |

因此完整 GA100 会是 128 SM / 8192 个 FP32 通道。没有任何产品发布过那个配置：每个 A100 SKU 都发布 108 SM / 6912 个着色单元，而 CMP 170HX 发布 70。

| 部件 | 活动 GPC | TPC | SM | FP32 通道 |
|---|---|---|---|---|
| 完整 GA100 晶片 | 8 | 64 | 128 | 8192 |
| A100 SXM4 / PCIe（所有 SKU） | 7（`FUSE_GPC_DISABLE` = `0x08` / `0x08` / `0x80`，三个被探测 SKU 各置一位） | 54 | 108 | 6912 |
| DRIVE A100（`0x20bb`，PG199） | 6（`FUSE_GPC_DISABLE` = `0x84`） | 48 | 96 | 6144 |
| **CMP 170HX，两个 SKU** | **5**（`RING_ENUM_GPC` = 5） | **35** | **70** | **4480** |

170HX 的数值是实测而非推断。解锁卡上的一个 PTX 特殊寄存器转储器报告 `SMs=70 warpsize=32`、`nsmid=70 nwarpid=64`，`smid` 值跨越 0..69 无缺口。一台 8 卡混合矿机在所有 8 个设备上枚举 `cu: 70`，而显存交替为 9990 MiB 和 7954 MiB，这是 SM 数不随 SKU 变化的最干净的单次演示。解锁卡上的 OpenCL-Benchmark 同样报告 70 个计算单元在 1410 MHz（4480 核心，理论 FP32 12.634 TFLOPs/s）。

注意 35 个 TPC 是奇数：五个活动 GPC 并不都带 8 个 TPC，这对收获部件是正常的。

---

## 地板清扫与按晶片分级

地板清扫是测试时通过烧断 OTP 熔丝禁用有缺陷或多余的单元。在 170HX 上它完全通过熔丝和 STATUS 路径工作：**每个 `CTRL_OPT` 覆盖寄存器都读零**，拓扑报告自己的汇总行是 `held back by CTRL_OPT: 0 TPC = 0 SM`。这意味着 70 SM 已经是这些晶片的熔丝下限，其上没有任何可放松的软件覆盖层。

| 寄存器 | 地址 | 作用 | 170HX 读数 |
|---|---|---|---|
| `OPT_GPC_DISABLE` | `0x00820350` | GPC 禁用掩码（熔丝） | 按晶片，置 3 位 |
| `STATUS_OPT_GPC` | `0x00820c1c` | 有效 GPC 掩码 | 总是镜像熔丝 |
| `OPT_GPC_DEFECTIVE` | `0x008205c4` | 哪些 GPC 真正坏 | 部分卡上 `0x00` |
| `RING_ENUM_GPC` | `0x00120078` | 环上枚举的 GPC | `5` |
| `CTRL_OPT_GPC` | `0x0082081c` | 软件地板清扫覆盖 | `0x00000000` |
| `CTRL_OPT_FBIO` / `_FBPA` / `_FBP` | `0x00820814` / `0x00820818` / `0x00820938` | 同上，显存侧 | `0x00000000` |
| `CTRL_OPT_PERLINK` / `_PCIE_LANE` / `_NVLINK` | `0x00820820` / `0x0082082c` / `0x008209b8` | 同上 | `0x00000000` |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | 是否启用 CTRL_OPT 层 | `0x00000000` |
| `gpcMask` | `0x00408970` | GR 侧 GPC 掩码 | `0xdc`，写入会重新断言 |
| `OPT_PCIE_DEVIDA` | `0x008204d8` | SKU 身份熔丝 | 8 GB 卡上报告 `0x20c2`（见下方备注） |
| `OPT_SLT_REV` | `0x008204bc` | 插槽 / 测试修订 | 按晶片 |

**掩码按单张卡而异，不按 SKU，也不随驱动版本变化。** 三轮独立调查记录了七个不同的 `OPT_GPC_DISABLE` 值，其中四个来自一个下午读的四张卡，全部禁用三个 GPC、全部合计 70 SM：

| `OPT_GPC_DISABLE` | 禁用的 GPC | 卡 |
|---|---|---|
| `0x85` | 0, 2, 7 | 10 GB |
| `0x45` | 0, 2, 6 | 8 GB |
| `0x13` | 0, 1, 4 | 8 GB |
| `0xa8` | 3, 5, 7 | 10 GB |
| `0xd0` | 4, 6, 7 | 熔丝表卡 |
| `0x23` | 0, 1, 5 | 熔丝表卡 |
| `0x15` | 0, 2, 4 | 10 GB |

部分被禁用的 GPC 标记为**物理完好**。用于高安全写入实验的那张 8 GB 卡上，`OPT_GPC_DEFECTIVE` 读 `0x00000000` 而 `OPT_GPC_DISABLE` 置了三位，所以三个被禁用的 GPC 都是健康的硅片，被熔断关闭以满足产品规格。一张 10 GB 卡上 `OPT_GPC_DEFECTIVE` = `0x81`（GPC 0 和 7 真正有缺陷），而 GPC 2 被禁用但有缺陷标记。

### 限制 / 分级的分界

对两张物理 170HX 卡的完整 120 寄存器 diff 发现 **107 个寄存器相同、13 个不同，而 13 个每一个都是分级值**。这是晶片上最有行动价值的工具链结果：

- **产品线常量，每张 170HX 相同，可在配方中安全硬编码：** 九个速度选择熔丝（`FUSE_SS_DP` = `0x1`，其余八个 = `0x5`）、`FUSE_PCIE_GEN23_DIS` = `0x1`、`FUSE_PCIE_GEN3_DIS` = `0x1`、`FUSE_NVLINK_DIS` = `0x7`、`FBPA_CFG1_BROADCAST` = `0x02449000`、`FUSE_PCIE_DEVIDB` = `0x20c2`、`FUSE_ECC_EN` = `0x0`、`FUSE_EN_SW_OVERRIDE` = `0x0`。（120 寄存器 diff 里的两张卡都是 10 GB 单元，所以任何按 SKU 而非按晶片变化的寄存器在那份 diff 里看起来都像常量。有两个是这样的：`FUSE_SKU_ID`（`0x00821060`）在 10 GB 卡上读 `0x68`、8 GB 卡上读 `0x80`，`FUSE_PCIE_DEVIDA`（`0x008204d8`）在 10 GB 卡上读 `0x2082`、8 GB 卡上读 `0x20c2`，而 `FUSE_PCIE_DEVIDB` 两者都是 `0x20c2`。DEVIDA 和 SKU_ID 都不安全硬编码，`lspci -nn` 仍是最简单的 SKU 测试。）
- **绝不能硬编码的按晶片值：** 所有地板清扫掩码及其 STATUS 镜像、`FEAT_OVR_SM_SPD`（`0x0082381c`）、`FEAT_OVR_SM_SPD_1`（`0x00823820`）、`FEAT_OVR_QUADRO`（`0x00823808`）、`I1500_DATA`、`I1500_SHADOW_WDR`，以及每次每-FBPA 回读。

这个分界就是为什么[算力解锁](../unlock/compute-throttle.md) 能发布两个固定魔法常量、却仍对每张卡正确，也是为什么任何拿你的卡对比"那个"出厂 SS0 值的工具都在对比噪声。

### 调查你自己的卡

只读调查工具 `ga100_topology_report.py`（v1 4848 字节；v2 8128 字节，增加一个 InfoROM 转储）读 `PMC_BOOT_0`、`OPT_GPC_DISABLE`、`STATUS_OPT_GPC`、`OPT_GPC_DEFECTIVE`、`RING_ENUM_GPC`、`PTOP_SCAL_NUM_GPCS`、`PBUS_SW_SCRATCH(1)`（`0x00001404`）、`0x00118f78`、`OPT_PCIE_DEVIDA`、`OPT_SLT_REV`，以及每-GPC 的 OPT_DISABLE / RECONFIG / CTRL_OPT / STATUS / RECONF_OVR 组。至少四人在两个 SKU 上运行过它，输出自洽。

> [!NOTE]
> **未解问题：缺失的 38 个 SM**
>
> 从 70 SM 到 A100 的 108，或晶片的 128，将是这块卡上可用最大的一笔增益，而在 `OPT_GPC_DEFECTIVE` = 0 的卡上，被禁用的 GPC 已知是完好的硅片。迄今为止找到的每条写入路径都被锁存。`FUSE_CTRL_OPT_TPC_GPC` 是只减（对一个活动 TPC 的 OR 测试甚至没让计数下降）；对 `OPT_GPC_DISABLE`、`STATUS_OPT_GPC`、`OPT_TPC_GPC2`（`0x00820768`）和 `DIS_SW_OVR`（`0x00820084`）的高安全写入全部回读不变——在一个携带两个阳性对照、证明写入原语是活的实验里；而用三种方式强制 `gpcMask`（RM 结构体、对 `0x00408970` 的主机 MMIO 写入、把 GSP 固件的 `andi` 补丁成 `li a4,255`）让软件栈报告 8 GPC / 112 SM，同时 `0x00408970` 每次都回读 `0xdc` 且 `cuInit` 段错误。未尝试的候选：一条经静态地板清扫掩码查询的 GSP-RPC 路径（类 `0x2080122a` / `0x2080122b`）、一次 GR 影子写入，或把写入原语移植到 PMU / GSP / FECS / GPCCS。参见[死路](../history/dead-ends.md)。

> [!WARNING]
> **实验性**
>
> 野外一张卡被报告为 CTRL_OPT 扫到 **56 SM** 而非熔丝下限的 70，夺回了 6 个 SM 达到 62，启用的其余 TPC 真的失败。这被描述为见过的第一张算力清扫卡，且未发布前/后寄存器转储。其它每张被调查的卡都已处在熔丝下限，那里 CTRL_OPT 不花任何代价。把低于 70 的 SM 数当作罕见而非正常。

---

## 显存分区与缓存层级

帧缓冲侧独立于图形侧被地板清扫。GA100 有 12 个 FBP，各带 2 个 FBPA，所以 24 个 FBPA，每个 256 位。每个 1024-bit HBM 接口其实是四个 256-bit 通道，这就是为什么部分堆叠启用是一个真实的硬件状态、FBPA 掩码显示部分而非干净的整堆失败。

| 量 | 8 GB SKU（`0x20c2`） | 10 GB SKU（`0x2082`） |
|---|---|---|
| 活动 FBPA | 24 中的 16 | 24 中的 20 |
| 活动 FBP | 12 中的 8 | 12 中的 10 |
| 显存总线宽度 | 4096-bit | 5120-bit |
| 出厂容量 | 8192 MiB | 10240 MiB |
| 解锁容量 | 65536 MiB | 40960 MiB |

地板清扫掩码再次按晶片变化。两张 10 GB 卡读 `FUSE_FBPA_DISABLE`（`0x00820368`）、`FUSE_FBIO_DISABLE`（`0x0082036c`）、`STATUS_FBPA`（`0x00820c18`）和 `STATUS_OPT_FBIO`（`0x00820c14`），一张全在 `0x0003c000`（FBPA 14 到 17 关闭）、另一张全在 `0x000000c3`（FBPA 0、1、6、7 关闭），都留下 20 个活动。被禁用的 FBPA 从它们的 CSTATUS 寄存器返回 `0xbadf20xx` 哨兵而非值，哨兵跟踪哪些 FBPA 关闭：禁用 FBPA 0、1、6、7 的卡上是 `0xbadf2010` 和 `0xbadf2013`，禁用 FBPA 14 到 17 的卡上是 `0xbadf2017` 和 `0xbadf2018`。一张 8 GB 卡的转储单独枚举了它的 12 个 FBP 半堆区域：FBP 1 和 4 禁用、FBP 6 和 11 有缺陷、其余八个活动，得到 8 × 8 GB = 64 GB，这正是解锁到达的容量。完整细节在[显存子系统](memory-subsystem.md) 和[显存几何布局](../unlock/memory-geometry.md)。

| 缓存层级 | 大小 | 依据 |
|---|---|---|
| 每 SM 的 L1 / 共享 | 192 KB | GA100 架构数值 |
| L2 | 32 MB（`32768 KB`） | CUDA `deviceQuery` 加一个独立的延迟尖峰微基准测试 |
| L2，完整 A100 | 40 MB | 供对比 |
| OpenCL 全局缓存 / 本地内存 | 1960 KB / 48 KB | 解锁卡上的 OpenCL-Benchmark |

> [!NOTE]
> **有争议**
>
> TechPowerUp 把 170HX 的 L2 列为 8 MB。运行时的 `deviceQuery` 数值 32768 KB 和一个独立的指针追逐延迟测量都说 32 MB，本维基用 32 MB。语料库中没有来源调和两者；一条显示工作集在哪里悬崖式掉落的已发布延迟/带宽曲线能定论它。还要注意正确的 TechPowerUp 条目是 `gpu-specs/cmp-170hx-8-gb.c3830`；较旧的 `c3824` URL 现在重定向到一张 AMD 卡。

HBM 带宽在这个部件上**不受限制**，也不随解锁改变（一次同卡 A/B 在 256 MB 工作集上测得出厂 1592 GB/s 对改装 1599 GB/s，比值 1.0x，在同一张表里 FP32 移动了 30.7x）。理论峰值是 5120-bit 上 1215 MHz DDR 的 1555.2 GB/s（= 1448.4 GiB/s）。实测数值根据工具和访问模式跨越 **1305.86 到 1600 GB/s**，不存在单一规范数值；参见[性能](../operations/performance.md)。

---

## 计算能力与指令集

计算能力 8.0（`sm_80`）固定了晶片能做什么、不能做什么，独立于任何熔丝：

- **每 SM 64 个 FP32 通道**，每 SM 64 个 warp，warp 大小 32。FP64 处于 GA100 的 1:2 比例，非张量 FP16 相对 FP32 为 4:1（架构上不寻常，也是锁定卡当时已经能用于 LLM token 生成的原因）。
- **280 个第三代张量核**（每 SM 4 个）、280 个 TMU、128 个 ROP。张量核存在且可用，不是熔断关闭：解锁卡实测 FP16 张量 158.7 到 190 TFLOPS、BF16 张量 164.4 到 192.7 TFLOPS。
- **没有 FP8、没有 NVFP4 硬件路径。** 那些需要 `sm_89`+ / `sm_120`。在这块卡上枚举受支持 MMA 形状的工具把 `mma_mxf8mxf8f32_16_8_32` 和 `mma_f8f8f16/f32_16_8_32` 列为不支持，这对 Ampere 是预期。INT8、INT4 和 INT1 在硬件中天生支持，尽管 INT1 与 INT8 共享 XNOR-popcount 路径，没有专用单元。
- 对推理的实际后果：`sm_80` 不支持 FP8 KV 缓存，所以 KV 必须是 BF16。

---

## 存在、被熔断关闭和缺失的引擎

| 引擎 / 功能 | 170HX 上的状态 | 证据 |
|---|---|---|
| CUDA 核心、张量核 | 存在，可用，出厂时发射速率被节流 | 参见[算力节流](../unlock/compute-throttle.md) |
| FP64 单元 | 存在，被解锁恢复 | 按 1:2 比例实测 |
| **NVENC** | **缺失。** GA100 晶片总体上不带视频编码器 | 频道内报告，与晶片的功能集一致 |
| **NVDEC** | 晶片级：按规格数据库为五实例第四代 NVDEC。驱动级：此 SKU 上不暴露。对 NVDEC falcon 邮箱 `0x00830040` 的一次探测返回 `0xbadf1100`，即被阻挡或只读 | 规格数据库，中等置信度；falcon 探测 |
| **显示引擎 / 输出** | **缺失。** 没有任何显示输出，`Slot Width: IGP`，无 DirectX / Vulkan / OpenGL 暴露 | 规格数据库和每一次 `lspci` 捕获，后者把设备命名为 `3D controller` |
| **NVLink** | **熔断关闭。** `FUSE_NVLINK_DIS` / `STATUS_OPT_NVLINK`（`0x00820db8`）= `0x7`；板还缺 NVLink 接口 IC。`0x00823800`-`0x0082382c` 块里没有 NVLink 寄存器，任何分支都不含 NVLink 代码 | 熔丝读取加拆解；参见[NVLink 硬件](nvlink-hardware.md) |
| **ECC** | **熔断关闭。** `FUSE_ECC_EN` = `0x0`，无遥测，无已知开关。`FEAT_READOUT_0` 的高 ECC 状态半字节读零，与熔丝一致 | 参见[ECC 前沿](../frontier/ecc.md) |
| **P2P** | 缺失。发布树或分支树里都没有 P2P 代码；唯一 MIG 档位报告 `P2P: No` | 参见[P2P 前沿](../frontier/p2p.md) |
| **MIG** | 硬件支持（`0x00820840` 的启用位 0），但只暴露一个档位 `1g.64gb`，所以 GPU 实际上无法被分区 | 社区发现，不在发布代码里 |
| **Resizable BAR** | 存在但限制到 64 MiB | `lspci` 能力 `[bb0]` |
| **FLR** | 存在（DevCap 里 `FLReset+`），且对每个解锁装置都承重 | `lspci -vvv` |

> [!NOTE]
> **未解问题：NVENC 是熔断关闭还是根本没造？**
>
> 频道内的陈述是 "nvenc is disabled ... idr if it's fused off or if it's fuse gated but it's not available by default if it has the hardware"（nvenc 被禁用……不确定它是熔断关闭还是熔丝门控，但如果它有硬件，默认也不可用）。没人报告过 NVENC 会话工作，也没提出任何解锁路径。明显的下一步是用破解算力节流的同一个差分方法：在 170HX 上和一个 A100 或 DRIVE A100 对照上读 `0x00820xxx` 块里 NVENC 相关的 `OPT_*_DISABLE` 熔丝并 diff。在那之前，假定卡没有硬件编码器。

---

## 为什么晶片对解锁重要

这颗特定硅片的三个属性是整个项目可行的原因：

1. **主清除熔丝未烧断。** `OPT_FEATURE_FUSES_OVERRIDE_DISABLE`（`0x008203f0`）读 `0x00000000`。若它被烧断，每个功能覆盖都会永久锁定，就不存在任何软件路径。
2. **限制熔丝是产品线常量，不是按晶片分级。** 一个配方适用于每张卡。
3. **DRIVE A100（`0x20bb`、PG199、`GA100-550F-A1`）是一个干净的阴性对照。** 两块物理板共享 170HX 的 NVLink 关闭和它的 `EN_SW_OVERRIDE` = 0 / `DIS_SW_OVR` = 1 状态，却把所有九个速度选择熔丝读为 `0x00000000`、`FEATURE_READOUT_1` = `0x00000000`，并在 96 SM 上有完整算力。那个单变量隔离正是证明 `OPT_SM_SPEED_SELECT` 熔丝块（且只有它）是算力限制的证据。

完整的熔丝图参见[熔丝与 OTP](fuses-and-otp.md)，覆盖如何被触达参见[算力节流](../unlock/compute-throttle.md)。
