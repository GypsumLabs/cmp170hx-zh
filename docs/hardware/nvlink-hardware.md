# NVLink 硬件

## 本页内容

CMP 170HX 上 NVLink 的状态：板上物理上有什么、熔丝怎么说、你在启动日志里看到什么以及它为什么有误导性，以及精确地说哪些门是关着的。解锁尝试、提案和开放研究在 [NVLink 前沿](../frontier/nvlink.md)；本页是硬件描述。

**一句话总结：CMP 170HX 上的 NVLink 不工作，对任何人都从来没工作过，而且是被一颗 OTP 熔丝而非软件禁用的。** 链路没有损坏，连接器物理上存在于 PCB 上，晶片按完整十二链路 GA100 配置扩展，而这些都无济于事，因为 `0x00820684` 处的 `FUSE_NVLINK_DIS` 读 `0x00000007`，且不存在能推翻它的覆盖寄存器。解锁器中没有任何代码碰 NVLink，在 master 或十二个未发布分支上都一样。

---

## 熔丝证据

在 2026 年 5 月跨卡调查的两块物理 170HX 单元上测得，并在 2026-05-07 至 2026-07-27 之间至少五次，在 `0x20C2`（8 GB）和 `0x2082`（10 GB）两个 SKU 的活卡上独立地从 BAR0 重读。

| 寄存器 | 地址 | 170HX | A100 ×3 | A10 / A5000 / A6000 | RTX 3080 / 3080 Ti | RTX 3090 / 3090 Ti | Drive A100 32 GB | 含义 |
|---|---|---|---|---|---|---|---|---|
| `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | `0x00820684` | `0x00000007` | `0x00000000` | `0x00000000` | `0x00000001` | `0x00000000` | `0x00000007` | 禁用掩码，字段 `[2:0]`。三个位全部置位 |
| `STATUS_OPT_NVLINK` | `0x00820DB8` | `0x00000007` | `0x00000000` | `0x00000000` | `0x00000001` | `0x00000000` | `0x00000007` | 只读有效状态，标注为 16 位 |
| `FUSE_NVLINK_DEFECTIVE` | `0x0082068C` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | 有缺陷链路掩码。**零：硅片完好** |
| `FUSE_NVLINK_DIS_CP`（`..._DISABLE_CP`） | `0x00820688` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | 关键路径禁用，未使用 |
| `FUSE_NVLINK_MASK_SEC` | `0x00820704` | `0x00000005` | `0x00000005` | `0x00000085` | `0x00000085` | `0x00000085` | `0x00000005` | 掩码写安全，8 位。按架构而非按档位划分 |
| `FUSE_NVLINK_PHYS_DMG` | `0x00820BD4` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | 损坏标志上的写安全位。各处一致 |
| `FUSE_NVLIPT_RST_DIS` | `0x00821100` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | NVLink IP 复位条件禁用 |
| `CTRL_OPT_NVLINK` | `0x008209B8` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | 有效每链路控制，位 `[15:0]` |
| `CTRL_OPT_PERLINK` | `0x00820820` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | 每链路控制，位 `[11:0]` |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246C` | `0x0000000c` | `0x0000000c` | `0x00000004` | `0x00000004` | `0x00000004` | `0x0000000c` | 晶片内建的链路：**12** |

三个读数直接得出结论：

1. **禁用是刻意的分区，不是报废分级。** `FUSE_NVLINK_DEFECTIVE` 这个会记录一条坏链路组的字段，在 170HX 以及 15 卡调查中每一个返回值的卡上都读 `0x00000000`；A16 列读的是 `BAR0` 占位符，因为它的 BAR0 太小够不到大多数熔丝寄存器，而 ES 列是空白的。如果 NVIDIA 因为这些链路测试失败而熔断它们，这个寄存器就是会被写入的地方，而它是空的。
2. **晶片携带完整的 GA100 NVLink 配置。** `PTOP_SCAL_NUM_NVLINK = 0x0000000c` 描述内建在硅片里的十二条链路，且不受禁用熔丝影响。它与全部三个 A100 SKU 和 Drive A100 逐字节相同。
3. **禁用经由 STATUS 路径到达，而不是经控制覆盖。** 两个 `CTRL_OPT` 寄存器都读零，所以没有东西设置它们；原始熔丝直接传播进只读状态寄存器。这与卡上其它每个地板清扫是同一个模式，在[熔丝与 OTP](fuses-and-otp.md) 中有记录。

### 它不是挖矿 SKU 专属限制

DRIVE A100 32 GB（PG199、`GA100-550F-A1`、`FUSE_PCIE_DEVIDA` = `0x000020bb`、`FUSE_PCIE_DEVIDB` = `0x000020fb`），在两张物理板上测得，读取的 `FUSE_NVLINK_DIS` = `0x00000007` 和 `STATUS_OPT_NVLINK` = `0x00000007` 完全相同。全部三个常规 A100 SKU 读 `0x00000000`。因此一个 NVLink 熔断关闭的 GA100 对 NVIDIA 来说是正常发货的东西，这削弱了任何说这个特定禁用是加密货币挖矿对策、因此可能有个对应的逃生门的理论。

还要注意，一些文章里提到的、也读 `7` 的 `0x20bb` "A100 级对比卡" **就是**这块 Drive A100，不是第四个 A100 SKU。设备 ID 匹配。

### 两条值得记住的更正

> [!NOTE]
> **未解问题：3 位禁用字段对 12 条物理链路**
>
> `FUSE_NVLINK_DIS[2:0]` = `0x7` 配 `PTOP_SCAL_NUM_NVLINK` = 12，而 `STATUS_OPT_NVLINK` 被标注为一个 16 位字段却也读 `0x00000007`。工作假设（语料库中没有任何东西确认）是**每组 4 条链路的 3 个链路组**（12 = 3 × 4），这能解释反复出现的 "all groups"（所有组）措辞以及 RTX 3080 相对其 `PTOP_SCAL_NUM_NVLINK` = `0x4` 的 `0x1`。什么能定论它：一块带已知 *部分* NVLink 地板清扫的 A100 作对比，或 GA100 上 `NV_FUSE_OPT_NVLINK_DISABLE` 字段宽度的厂商文档。语料库中两者都不存在。

---

## 物理板

CMP 170HX 复用 A100 板布局。**NVLink 边缘接口的金手指物理上存在，且存在三个桥连接器位置。** 这一点由 2023 年 10 月的一次外部拆解确立，并在 2026 年得到卡主认可。

> [!NOTE]
> **更正："CMP PCB 完全没有 NVLink 连接器"说的是 90HX**
>
> "机箱有一个 NVLink 连接器的开口，但 PCB 没有它"这一观察在档案中出现两次：一次归因于 170HX，一次带更完整的上下文、即 "the same unknown brand also makes an RTX 3080 20 GB [which] uses a PCB with the NVLink connectors"（同一个不知名品牌也做一款用带 NVLink 连接器的 PCB 的 RTX 3080 20 GB），归因于 **CMP 90HX**。90HX 是一款 GA102 RTX 3080 级挖矿板，恰好就是那句 RTX 3080 20 GB 兄弟备注所描述的。应用到 170HX 上，这个说法与拆解证据矛盾。把归因于 170HX 的实例，以及一篇短文里的括注 "CMP boards have no NVLink connector"（CMP 板没有 NVLink 连接器），都当作误归属。

### 导流罩挡路

铝导流罩盖住了连接器区域。在它被机械加工、移除或更换之前，什么都装不进去。这与 Tesla P100 情况相同：NVIDIA 在 A100 上用橡胶帽盖住连接器，官方桥卡扣在 A100 外壳上，而 170HX 没有这个外壳。存在一张用打磨机开了口的 P100 照片，其电气结果未知。有一款水冷头被报告为让 NVLink 区域裸露。重新设计冷却器以获得物理访问，被命名为这个领域的实用第一步，先于任何电气工作。参见[散热](../operations/cooling.md)。

### 贴装还是缺件：倾向缺件，但未定论

这是关于这块板最有后果的开放问题，因为它决定熔丝绕过是否还有用。证据的份量在缺件一侧：记录中唯一的直接 A100-对-CMP 板卡对比报告缺件，而反方主张是从原理图而非从板卡读出来的。

**缺件的证据。** 2023 年拆解称 "because the CMP 170HX uses the same NVIDIA A100 circuit board, the gold fingers of the NVLink interface exist, but the feature is unsupported with all components unpopulated on the PCB"（因为 CMP 170HX 用同一块 NVIDIA A100 电路板，NVLink 接口的金手指存在，但该功能不受支持、PCB 上所有元件都未贴装），并单独称 "ICs related to the NVLink interface are also missing"（与 NVLink 接口相关的 IC 也缺失）。据 A100 原理图，一位研究者识别出 GPU 上方五颗具体缺件的电阻：`R234`（000）、`R237`（NP）、`R236`（1k）、`R1024`（000）和 `R238`（000），全部来自第 17 页，外加 `R976`、`R1029` 和 `R1030`，以及三颗没有可见走线的 GPU 对地端接电阻。另一位参与者回忆起 NVLink 电源的缺失部件。

那份清单是在两块板都在视野内时产出的：这些电阻 "are populated on a genuine A100, but missing on CMP"（在真 A100 上是贴装的，在 CMP 上缺失）。

**贴装的证据。** 项目自己的 VBIOS 对比表记录 "NVLink bridge: external bridge absent (PCB fully populated)"（NVLink 桥：外部桥缺失（PCB 完全贴装）），这是一行项目文档而非一次检查。在电阻清单贴出的两小时前，另一位研究者说 "I do not believe there are any missing NVLink components. According to the schematics, the GPU die is connected directly to the edge connectors"（我不认为有任何缺失的 NVLink 元件。根据原理图，GPU 晶片直接连接到边缘连接器），把混淆归咎于桥携带主动元件 "including a ROM chip"（包括一颗 ROM 芯片）。后来对一块官方 A100 桥的直接检查发现没有 EEPROM 也没有时钟发生器，所以那个陈述的依据不成立。

**复杂化的细节：** `R237` 在 A100 原理图里自己就标着 **NP**（未贴装），所以那五颗里至少有一颗在真 A100 上也是预期缺失的。这干净地说明了用眼睛对比有多容易误导。

**什么能定论它：** 一块去导流罩的 170HX 和一块真 A100 在这些设计编号处的并排高分辨率照片，或从 NVLink 边缘金手指到 BGA 球 `F1` 和 `G1` 的连通性检查。两者都不存在。注意 `R976` 落在这颗至少有 82 行球的封装上晶片下方的球 `F51`，没有专业红外 SMD 返工或晶片移除就无法够到；`R1029` 和 `R1030` 连接到晶片边缘的 `F1` 和 `G1`，可以用细线够到。

即便完美的返工也把 `FUSE_NVLINK_DIS` 留在 `0x00000007`。

---

## 启动日志里出现什么

每次带 NVIDIA 驱动加载的 170HX 启动都产生这一行：

```text
nvidia-nvlink: Nvlink Core is being initialized, major device number 236
```

**它是良性的，也不是链路训练的证据。** 它源于 `nvidia-nvlink.ko` 软件核心库里的 `nvlink_linux.c:344`，宣布模块已加载。它记录在 `DBG_INFO`，在早期模块加载期间、GPU 和 GSP 启动之前触发，并且在几乎任何 NVIDIA GPU 的每一次驱动加载时都会出现。"236" 是一个由 `alloc_chrdev_region` 动态分配的 Linux 字符设备主号，每次启动都可能不同，所以日志里出现不同的数字也不代表什么。

权威检查一条命令：

```console
$ nvidia-smi nvlink -s
Device does not have or support Nvlink.
```

那个输出在语料库中只记录过一次，来自 2026-07-24 一台租用的、带解锁的 64 GiB 卡的 8 卡主机，所以把它当作与熔丝一致而非一次广泛调查。想要确定性就用熔丝佐证它：

```bash
# STATUS_OPT_NVLINK，只读有效状态
sudo python3 - <<'EOF'
import mmap, struct
BDF = '0000:81:00.0'
with open(f'/sys/bus/pci/devices/{BDF}/resource0','rb') as f:
    bar = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for name, off in (('FUSE_NVLINK_DIS', 0x00820684),
                      ('STATUS_OPT_NVLINK', 0x00820DB8),
                      ('FUSE_NVLINK_DEFECTIVE', 0x0082068C),
                      ('PTOP_SCAL_NUM_NVLINK', 0x0002246C)):
        print(f'{name:22s} 0x{off:08x} = 0x{struct.unpack_from("<I", bar, off)[0]:08x}')
EOF
```

在任何 CMP 170HX 上预期：`0x00000007`、`0x00000007`、`0x00000000`、`0x0000000c`。

---

## 为什么它保持锁定

四扇独立的门，每扇因不同原因关闭。四扇都必须打开。第五节记录解锁器从不尝试其中任何一扇。

### 1. 这个值来自 OTP，不是软件

禁用从一个 OTP 熔丝 `0x00820684` 读出，并镜像进一个只读状态寄存器。在驱动、VBIOS 签名区或未签名的 FwSec 尾部中，没有任何产生它的软件设置。2026-07-27 仍在流传的 "NVLink 也是软件锁" 的说法，就是错的。

### 2. 没有可写的 FEAT_OVR 寄存器

算力解锁通过打开 `0x00823804` 的 `FEAT_OVR_PLM` 并写入同块的特性覆盖寄存器来工作。明显的问题是同样的招数能否够到 NVLink。它不能，因为这个块里没有任何 NVLink 条目。`0x00823800` 到 `0x0082382C` 的完整清单：

| 地址 | 寄存器 |
|---|---|
| `0x00823800` | `FEAT_OVR_ECC_PLM` |
| `0x00823804` | `FEAT_OVR_PLM` |
| `0x00823808` | `FEAT_OVR_QUADRO` |
| `0x0082380C` | `FEAT_OVR_ECC` |
| `0x00823810` | `FEAT_OVR_ECC_1` |
| `0x00823814` | `FEAT_READOUT_0` |
| `0x00823818` | `FEAT_READOUT_1` |
| `0x0082381C` | `FEAT_OVR_SM_SPD` |
| `0x00823820` | `FEAT_OVR_SM_SPD_1` |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` |
| `0x00823828` | `FEAT_READOUT_2` |
| `0x0082382C` | `FEAT_OVR_ECC_2` |

十二个寄存器，覆盖 ECC、Quadro 分类字、SM 速度选择、行重映射器，以及三个回读。没有任何给 NVLink 的。"`FUSE_FEAT_OVR_DIS` 在所有卡上都读零，所以对 NVLink 掩码的 FEAT_OVR 式攻击至少不是明显被排除的" 这个论证，结论是错的、关于熔丝却是对的：它**确实**被排除，因为没有这样的寄存器可写。

### 3. CTRL_OPT 覆盖路径被熔丝禁用

`0x008209B8` 的 `CTRL_OPT_NVLINK` 被记录为有效的每链路使能，它读零，并被描述为可写。它是整个语料库中被引用最多的候选杠杆。它在这里也几乎肯定是惰性的，因为 `0x00820040` 的 `FUSE_EN_SW_OVERRIDE` 在两块 170HX 单元、全部三个 A100 SKU 和 Drive A100 上读 `0x00000000`，而每个消费级和工程样品部件读 `0x00000001`。`0x00820084` 的 `FUSE_DIS_SW_OVR` 在每张卡上都读 `0x00000001`。在未签名 FwSec VBIOS 尾部（`0x43A00` 到 `0x47700`）偏移量 `0x47341` 处找到的 25 项 `NV_FUSE_CTRL_OPT_*` 表，在 13 块被探测的 GA100 卡上都读全零，在这块硬件上是惰性的。

> [!NOTE]
> **未解问题：从来没人执行过那次写入**
>
> 在所有 31 份归档的解锁器附件和每一个净室工件中，NVLink 只作为熔丝读出出现。没有探测脚本、没有覆盖尝试、没有记录的写入。强烈的先验是，对 `0x008209B8` 的一次写入会被丢弃，`STATUS_OPT_NVLINK` 保持 `0x00000007`。这个否定仍然值得记录在案，因为现在语料库无法说明它是否被尝试过。这个实验是在一张可牺牲的卡上做一次读-写-读，然后重读 `0x00820DB8`。

### 4. 没有找到可欺骗的熔丝消费方

CMP DevInit 固件**读取** `0x820684`。DevInit 反汇编中 `0x1482xxxx` 访问（MMIO `0x82xxxx`）的完整清单是 `0x820C14` 和 `0x820D38`（FBIO 和 FBP 地板清扫）、`0x820684`（`FUSE_NVLINK_DIS`）、`0x82380C` 和 `0x823814`、`0x820520`（`MAGIC_D`）和 `0x820148`。任何源码中都没有写入它，也从未点名任何有效的覆盖消费方。没有人追踪过 DevInit 读取该值后拿它做了什么，这是这个领域里唯一一个仍可处理的软件问题。

### 5. 解锁器里根本没有 NVLink 代码

在整个已发布的 `master` 树上 grep `nvlink` 和每一个 NVLink 寄存器地址都一无所获：不在 `common/constants.yaml`、`driver/build.sh`、`driver/VERSION`、`install.sh`、`remove.sh`、`README.md`，也不在六个补丁的任何一补。`constants.yaml` 只声明两个驱动版本、两个设备 ID、算力值和两个显存档位。

在全部十二个未发布分支（`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`）中，NVLink 的全部存在就一个词。`housekeeping` 和 `memory` 分支加了一张特性状态表，相关行读：

```markdown
| ECC          | Planned |
| NVLink       | Planned |
```

---

## NVLink 本来会值多少钱

包含进来，因为缺失功能的代价不断被往两个方向错误陈述。

| 量 | 值 | 置信度 |
|---|---|---|
| A100 PCIe 每桥 NVLink | 200 GB/s | 高 |
| A100 PCIe 每对总计、全部三桥 | 600 GB/s | 高 |
| 记录的 Ampere PCIe 拓扑 | 2 个 GPU，需要全部三桥 | 高 |
| Ampere 端口结构 | 4 子端口 × 4 通道 @ 每通道 50 Gbps = 每端口 800 Gbps 原始（来源称 200 Gbps；分解和这个数字不可能都对） | 中等 |
| GA102 第三代每链路 | 14.0625 GB/s 双向，四个 x4 链路 | 高 |
| GA102 第三代总计 | 56.25 GB/s 双向，两 GPU 之间 112.5 GB/s 总聚合 | 高 |
| 今天 170HX 的互连基线 | PCIe Gen 1 x4，约 1 GB/s | 高 |

NVSwitch，以及任何比一对更宽的东西，只存在于像 DGX 这样的 SXM 平台内。官方 A100 桥是一块**裸无源 PCB**：没有时钟发生器、没有 EEPROM、没有重定时器、没有包处理 ASIC，经直接检查确立，并对 SXM2 底板独立佐证。消费级 RTX 3090 桥确实带一个时钟发生器，据信是因为 NVIDIA 不能假定消费级主板提供相同的 PCIe 参考时钟。从 Ampere 到 H200 NVL 一代的所有桥都被评估为无源。

这实际为推理买多少本身就未定论：一对 RTX 3090 在 vLLM 张量并行下的一个一手测量只显示约 10% 的吞吐提升，而同一类配置的第三方公布数字显示约 48%。模型、量化、批大小和并发度不同或未说明。说 170HX 因为基线是 Gen 1 x4 而非 Gen 4 x16 会多得多的论证，只是推理，在熔丝还在时无法测试。参见[LLM 推理](../operations/llm-inference.md)。

关于聚合算术，注意四张解锁的 8 GB 卡给出 256 GB（4 × 65536 MiB），四张解锁的 10 GB 卡给出 160 GB（4 × 40960 MiB）。一个被广泛引用的四张 10 GB 卡的 320 GB 数字假设了 80 GB 配置，而它被尝试过并发现不稳定。参见[80 GB](../frontier/80gb.md)。

**今天可用的替代方案是 PCIe 点对点，不是 NVLink。** 参见[点对点](../frontier/p2p.md)。

---

## 常见错误答案

| 说法 | 为什么它看起来对 | 什么推翻它 |
|---|---|---|
| "NVLink 在启动日志里，加个桥就行" | dmesg 行真的每次启动都出现 | 那是软件核心库在 `DBG_INFO`、GPU 启动前宣布它加载了 |
| "NVLink 是软件锁的" | 170HX 的其它几个限制确实如此 | 这个值来自 OTP，并镜像进一个只读寄存器 |
| "名为 HULK 的加密是拦路虎" | 它是唯一已发表的解释，在一个看起来很权威的页面 | 该网站维护者于 2026-07-20 否认它，页面作者自己也称其过时；任何熔丝读取、VBIOS 转储或 DevInit 反汇编都没有佐证它 |
| "`PHYS_DMG = 1` 意味着链路被标记损坏" | 寄存器名说物理损坏 | 它在包括健康 A100 在内的全部十四张被探测卡上读 `1`。它是一个写安全位 |
| "3090 读 `0` 条链路，所以 170HX 相对 0 放弃 12 条" | 这是项目自己探测脚本里的一条注释 | 在除 A16 外的每个 GA10x 部件上都实测 `0x4` |
| "这些晶片 NVLink 测试失败，因此分级" | 报废分级通常就是这样 | `FUSE_NVLINK_DEFECTIVE` 在每张被探测的卡上都 = `0x00000000` |
| "Titan V 的 NVLink 在 VBIOS 里被禁用，所以这是固件门控的" | 在更早的 NVIDIA 部件上是个真实先例 | 在 170HX 上这个值来自一颗 OTP 熔丝，不是 VBIOS 设置。机制不迁移 |
| "写 `CTRL_OPT_NVLINK` 就能打开" | 被记录为有效每链路使能，读零，被描述为可写 | `FUSE_EN_SW_OVERRIDE` = `0`。强烈先验，从未真正测试过 |

更多，带日期和来源，见[死路](../history/dead-ends.md)。

---

## 状态

| 问题 | 状态 |
|---|---|
| NVLink 在 170HX 上可用吗？ | 否，而且没有已知路径 |
| 硅片损坏吗？ | 否。`DEFECTIVE` = `0x00000000` |
| 连接器在板上吗？ | 是，金手指和三个位置。被导流罩挡住 |
| 连接器区域贴装了吗？ | **未解决。** 双方都有直接证据 |
| 有人尝试过寄存器级解锁吗？ | 否。在任何卡上一次都没有 |
| 有人在 170HX 上装过桥吗？ | 否。语料库中从来没有任何人同时有卡和桥 |
| 解锁器里有 NVLink 代码吗？ | 否。两个分支 README 表里有一个词 "Planned" |

## 相关页面

- [熔丝与 OTP](fuses-and-otp.md)，本页所依据的完整熔丝调查
- [NVLink 前沿](../frontier/nvlink.md)，每一次尝试、提案和开放问题
- [点对点](../frontier/p2p.md)，可用跨 GPU 替代方案
- [PCIe 子系统](pcie-subsystem.md)，你确实拥有的互连
- [板卡与变体](board-and-variants.md)，PCB 本身
- [多卡](../procedures/multi-gpu.md)，无 NVLink 运行多张卡
- [未解问题](../frontier/open-questions.md)
