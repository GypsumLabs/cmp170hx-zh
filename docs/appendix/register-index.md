# 寄存器索引

## 本页覆盖内容

这是一张**扁平的查找表，收录本项目中任何地方文档化的每一个 BAR0 寄存器地址，按数值地址升序排列。** 它的唯一用途是快速回答一个问题：你在 `dmesg` 的一行、一个补丁或某人的脚本里刚看到一个陌生的十六进制地址，想知道它属于哪个块、做什么用的。

它刻意保持浅显。每一行只给出含义的一句话和一个链接，指向真正解释该寄存器的页面。至于出厂值、解锁值、PLM 门控、FLR 存活以及背后的任何推理，请到[寄存器参考](../unlock/register-reference.md)查阅——那是本索引的解释配套。

两条最省时的规则：

- **地址列里的一切都是 BAR0 字节偏移量**，从 region 0 起点开始算起。有几个解锁*值*看上去像是合理的地址，其实并不是。如果你的数字不在本索引里，先别急着断定索引不完整，请检查[不是 BAR0 地址的数字](../unlock/register-reference.md#numbers-that-are-not-bar0-addresses)。
- **一个返回 `0xbadf....` 的读不是数据。** 它是 PRI 毒值或权限违规哨兵。见[哨兵值](../unlock/register-reference.md#sentinel-values)。

凡项目从未确认某个寄存器用途的地方，行内会标注 **not documented**。这个短语举足轻重：它表示档案里没人解开它，而不是此处遗漏未写。

手工读取 `0000:05:00.0` 处显卡上的一个地址：

```bash
sudo dd if=/sys/bus/pci/devices/0000:05:00.0/resource0 \
        bs=4 count=1 skip=$((0x009a0204 / 4)) 2>/dev/null | xxd -e -g4
```

### 下面用的块缩写

| 块 | 含义 |
|---|---|
| `PMC` / `PBUS` | 主控制和总线临时区 |
| `PTOP` | 拓扑标量、描述完整 GA100 晶片 |
| `XVE` | PCIe 配置空间影子、BAR0 基址 `0x88000` |
| `XP-PL` | PCIe 物理层链路配置、`0x0008cxxx` |
| `XP3G` | PCIe PHY 速率覆盖数组、`0x0008e1xx` |
| `FBHUB` / `MMU` | 帧缓冲枢纽和内存管理单元、`0x001xxxxx` |
| `PMU` | 电源管理单元 Falcon、`0x0010axxx` |
| `GSP` | GSP RISC-V 核心和它的 Falcon 壳、`0x0011xxxx` |
| `BSI` | 常开（AON）引导和安全临时区岛、`0x001180xx` |
| `LTC` | 二级缓存切片 |
| `WPR` | 写保护区域控制、`0x001fa7xx` / `0x001fa8xx` |
| `SKED` / `FECS` / `SM` | 图形和算力前端 |
| `FUSE` | 熔丝和 OTP 影子、`0x0082xxxx` |
| `FEAT_OVR` | 特性覆盖块、`0x008238xx` |
| `SEC2` | 安全协处理器 Falcon、BAR0 + `0x840000` |
| `FBPA` | 帧缓冲分区、广播 `0x009axxxx` 和单播 `0x0090xxxx` |

---

## 索引

| 地址 | 名称 | 块 | 一行含义 | 细节 |
|---|---|---|---|---|
| `0x00000000` | `PMC_BOOT_0` | PMC | 硅片身份；每个有效 GA100 上 `0x170000a1` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00001404` | `PBUS_SW_SCRATCH(1)` | PBUS | 软件临时区；被调查的每张卡上 `0x20042000`、位 14 清除 | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x0002241c` | `NV_PTOP_FS4` | PTOP | 位 0 `GEN2_PCIE`、位 7 `GEN2_PCIE_SPEED`；8 GB 卡上 `0x00000000`、10 GB 卡上 `0x00000081` | [PCIe 子系统](../hardware/pcie-subsystem.md) |
| `0x00022430` | `PTOP_SCAL_NUM_GPCS` | PTOP | 完整晶片的 GPC 数、`8` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022434` | `PTOP_SCAL_TPC_PER_GPC`（`NUM_TPC_GPC`） | PTOP | 每 GPC 的 TPC、`8` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022438` | `PTOP_SCAL_NUM_FBPS` | PTOP | 完整晶片的 FBP 数、`0x0000000c`（12） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0002243c` | `PTOP_SCAL_NUM_FBPAS` | PTOP | 完整晶片的 FBPA 数、`0x00000018`（24） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00022454` | `PTOP_SCAL_NUM_LTCS` | PTOP | L2 切片数、`0x00000018`（24） | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022458` | `PTOP_SCAL_FBPA_PER_FBP` | PTOP | 每 FBP 的 FBPA、`0x00000002`（一张 RTX 3090 读 1） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0002246c` | `PTOP_SCAL_NUM_NVLINK` | PTOP | 完整晶片的 NVLink 数、`0x0000000c`（12） | [NVLink 硬件](../hardware/nvlink-hardware.md) |
| `0x00022470` | `PTOP_FS_STATUS` | PTOP | 地板清扫状态位向量、`0x0000003f`；位 0 TPC、位 1 GPC、位 2 FBP、位 3 ROP、位 4 FBIO | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00085080` | （未命名） | PRIV | 从 SEC2 注入点读 `0xbadf1100`；GSP 在一个利用从未达到的权限写它 | [PROT 墙住寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00085084` | （未命名） | PRIV | 同上 | [PROT 墙住寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00088070` | （未命名） | XVE | 读返回 0、写被忽略；**not documented** | [PROT 墙住寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00088084` | `LINK_CAP`（LnkCap） | XVE | PCIe 链路能力影子；出厂 `0x00456101`、Gen2 补丁后 `0x00456102` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088088` | `LINK_CTRL_STATUS`（LnkSta） | XVE | 协商链路状态；出厂 `0x10410040`（LnkSta 在位 [31:16]、LnkCtl 在 [15:0]）、Gen2 时 `0x1042xxxx`。速度 = `(value >> 16) & 0xF` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x0008808c` | （未命名） | XVE | 读 0、写被忽略。**不是** LnkCap2 镜像、尽管一份实地手册这么说 | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088090` | （未命名） | XVE | 读 0、写被忽略；**not documented** | [PROT 墙住寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x000880a4` | `LINK_CAP2`（LnkCap2） | XVE | 受支持链路速度向量；出厂 `0x00000002`（仅 2.5 GT/s）、补丁后 `0x00000006`（Gen1+Gen2）。对 `setpci` 硬件只读 | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x000880a8` | `LINK_CTRL_2`（LnkCtl2） | XVE | 目标链路速度；补丁设位 [3:0] = `0x2` 和位 [19:16] = `0xF` | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008841c` | `PRIV_MISC_1` | XVE | Gen2 使能位；`0x20340500` 变 `0x20342d00`（设 11 和 13、清 12 和 14）。第一次尝试成功并挺过 Booter Load | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008860c` | `VSEC_DEVICE` | XVE | 厂商专属设备字；补丁想 `0x00000800` 变 `0x00000801`、而**写在硅片上失败** | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x00088610` | `VSEC_HIERARCHY` | XVE | 厂商专属层级字；出厂 `0x00001001`、补丁用普通主机写清位 12 设位 0 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008872c` | LTSSM 覆盖（`XVE_OVR`） | XVE | 写成 `0x00000006` 以跳过引导中重训练。`0x2` 和 `0xa` 在 VFIO 下暴露额外 Gen2 行为、但最终楔住函数 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x00088ab4` | `XVE_B` PLM | XVE | 权限掩码、被九条目 Gen2 家族 PLM 表打开到 `0xffffffff` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00088ce4` | （未命名） | XVE | 170HX 上 `0x0000003f`、A100 上 `0x00000014`；一个 VBIOS 块用掩码-合并计算它。含义 **not documented** | [VBIOS](../hardware/vbios.md) |
| `0x00088fe8` | `XVE_D0` PLM | XVE | 权限掩码、被 `xp3gTable` 打开到 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088fec` | `XVE_D4` PLM | XVE | 权限掩码、被 `xp3gTable` 打开到 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088ff0` | `XVE_D8` PLM | XVE | 权限掩码、被 `xp3gTable` 打开到 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088ff4` | `XVE` PLM | XVE | PCIe 配置影子上的权限掩码；没有它主机读返回 `0xbadf5040` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00088ff8` | `XVE_C` PLM | XVE | 第三个 XVE 能力权限掩码、打开到 `0xffffffff` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x0008c040` | `LINK_CONFIG_0` | XP-PL | 位 [19:18] `MAX_RATE`；补丁读-改-写它们到 `0x2` | [XP-PL 块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c044` / `0x0008c048` / `0x0008c04c` | LINK_CONFIG 簇 | XP-PL | 一个与工作的三个不同的簇；对它们的高安全写被拒绝。字段布局 **not documented** | [XP-PL 块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c080` | 链路位宽寄存器 | XP-PL | A100 读 `0x00001010`；从没在 170HX 上用作杠杆。位宽是一个板级限制、不是这个寄存器 | [物理改装](../operations/physical-mods.md) |
| `0x0008c1c0` | `PL_LINK_RATE` | XP-PL | PHY 速率字；为 Gen2 写成 `0x00240036`（A100 读 `0x00040036`） | [XP-PL 块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c2c0` | `CYA_0` | XP-PL | 位 2 是 `DIS_G2` chicken 位、必须被清除。中心 Gen2 杠杆 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008e100` | `XP3G_STATUS` 基址 | XP3G | 四个 dword 状态数组、槽 *n* 在基址 + 4*n*；只读 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e10c` | `XP3G_STATUS3` | XP3G | 状态数组的槽 3 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e110` | `XP3G_OVR0` | XP3G | 覆盖使能槽 0、写成 `0x00000001`（每槽 one-hot） | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e11c` | `XP3G_OVR3` | XP3G | 覆盖使能槽 3、写成 `0x00000004` | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e120` | `XP3G_VAL0` | XP3G | 覆盖值槽 0、写成 `0x00000000`。值总是先于使能被写 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e12c` | `XP3G_VAL3` | XP3G | 覆盖值槽 3、写成 `0x00200000`（A100 `FUSE_PCIE_MAGIC_D` 值） | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b0` | `XP3G_PLM` | XP3G | XP3G 块上的权限掩码；干净打开到 `0xffffffff` | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b4` | `XP3G_PLM4` | XP3G | 第二个 XP3G 权限掩码 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b8` | `XP3G_PLM8` | XP3G | 第三个 XP3G 权限掩码 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1bc` | `XP3G_PLMC` | XP3G | 第四个 XP3G 权限掩码 | [XP3G 块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x00100800` | `FBHUB_NUM_ACTIVE_LTCS` | FBHUB | 活动 L2 切片数、8 GB 卡上 `0x10`（16）/ 10 GB 卡和 A100 PCIe 40/80 GB 上 `0x14`（20） | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b10` | FB-几何 PLM | FBHUB | 净室链打开的五个 `FB_GEO_PLMS` 之一；锁定 `0xffffff8f`。打开它**不**让几何布局挺过 FLR | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x00100b38` | FB-几何 PLM | FBHUB | 只出现在最早 HS 配方的第六条目 | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x00100b84` | PLM 候选 | FBHUB | 读 `0xffffff88`；它守护什么 **not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x00100b90` | `FBHUB_MEM_PART_BCFG0` | FBHUB | 显存分区广播配置、每张卡上 `0x00000603` | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b98` | `SYSMEM_HSHUB_CONNECTION_CFG` | FBHUB | sysmem 路由、`0x00000003`（BOTH、PCIe） | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b9c` | PLM 候选 | FBHUB | 读 `0xffffffcf`；它守护什么 **not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x00100ce0` | MMU 本地显存范围（LMR） | MMU | **MMU 看到的总 FB 大小。** 两个几何写之一。出厂 `0x00000208` / `0x00000288`、解锁 `0x0000020B`（64 GB）/ `0x0000028A`（40 GB）。编码 `MiB = MAG[9:4] << SCALE[3:0]` | [显存几何布局](../unlock/memory-geometry.md) |
| `0x00100ec0` | `MMU_NUM_ACTIVE_LTCS` | MMU | 10 GB SKU 和全部三个 A100 SKU 上 `0x05001414`；8 GB SKU 上报告 `0x04001410`。按 SKU 的分裂是一个**开放问题**、不是分歧：`...1410` 与 16 个 LTC 一致、`...1414` 与 20 个一致 | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x0010a040` | PMU `FALCON_MAILBOX0` | PMU | PMU Falcon 邮箱 0；PL0 可写、读 `0x00000300` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x0010a044` | PMU `FALCON_MAILBOX1` | PMU | PMU Falcon 邮箱 1；PL0 可写、读 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110040` | GSP `FALCON_MAILBOX0` | GSP | 普通 32 位寄存器、不是 FIFO。PL0 可写、一次健康 GSP 引导把它复位到 0。**这不是 `s_executeBooter` 读的邮箱**（那是 SEC2 的、在 `0x00840040`） | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110044` | GSP `FALCON_MAILBOX1` | GSP | PL0 可写、读 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110180` / `0x00110184` | GSP `IMEMC` / `IMEMD` | GSP | GSP 指令内存端口对 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x001101c0` / `0x001101c4` | GSP `DMEMC` / `DMEMD` | GSP | GSP 数据内存端口对、携带 WPR 地址 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110624` | GSP `FBIF_CTL` | GSP | 孔径控制；Booter 的 `reg_init` 写 `0x90`（`ALLOW_PHYS_NO_CTX` 位 7 加位 4） | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00110684` | GSP FBIF 伴生 | GSP | 被 `reg_init` 写成 `1`；用途 **not documented** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00111040` | GSP Falcon-壳 `MAILBOX0` | GSP | 与 `0x00110040` 不同；PL0 可写、读 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00111240` | `RISCV_STATUS` | GSP | GSP 核心状态。非零意味着 RISC-V 核心启动了（健康引导上 `0x35` 和 `0x33` 都被报告）；`0x0` 意味着它从未启动 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00111268` | `RISCV_CPUCTL` | GSP | GSP 核心控制 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x0011126c` | GSP RISC-V 伴生 | GSP | 被 `reg_init` 写成 `1`；用途 **not documented** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x001180f0` | AON LMR 影子 | BSI | 显存范围值的常开影子。**FLR 时回退**、所以它不是持久杠杆 | [FLR 存活](../unlock/register-reference.md#the-flr-survival-table) |
| `0x001180f8` | `NV_PGC6_BSI_SECURE_SCRATCH_14` | BSI | 位 26 = `BOOT_STAGE_3_HANDOFF`。由 SEC2 在 HS 上下文里于 GPU 侧设置；主机驱动只轮询它、引导挂起 `0x65` 就是那次轮询超时。**出货链从不写它** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00118244` / `0x00118248` | WPR 分阶段对 | BSI | 被 `booter_load_wpr_main` 读然后清零 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x0011824c` / `0x00118250` | memcfg 交接 | BSI | 被 `memcfg_program` 写；apply 轮询只在 `0x0011824c` 位 0 设置时运行 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x001182d0` | AON 安全临时区 | BSI | 在 PL3 可达；内容 **not documented** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00118f78` | 辅助临时区 | BSI | 被调查的每张卡上读 `0x00000000`；用途 **not documented** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00120078` | `RING_ENUM_GPC` | PRIV ring | 每张 170HX 上读 `5`；从没被任何写尝试移动 | [GA100 硅片](../hardware/ga100-silicon.md) |
| `0x001402b4` | LTC 伴生 | LTC | 一次 `0x00a00030` 的写被尝试、没移动 40 GiB 折叠。字段布局 **not documented** | [80 GB 问题](../frontier/80gb.md) |
| `0x0017e22c` | L2/LTC 地址映射寄存器 | LTC | 原生 `0x00280404`；从没被任何东西编程、40 GB 却工作 | [L2 / LTC](../unlock/register-reference.md#l2-ltc) |
| `0x0017e2a0` / `0x0017e2a4` | 每-LTC 解码 | LTC | 被净室 v8 工具瞄准；在 170HX 上 `DECODE_VAL` 全程停 `0x70000300`、仍未解释 | [80 GB 问题](../frontier/80gb.md) |
| `0x001fa7c4` | `WPR_PLM` | WPR | WPR 区域寄存器上的权限掩码。锁定 `0x0004cb8f`；**出货 PLM 索引 2、打开到 `0xffffffff`** | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x001fa7c8` | `MMU_LOCK` PLM | WPR | 写半字节 `0x8` 意味着仅 L3/HS；`0x0004cb8f`。本项目里只读 | [WPR 块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa7cc` | `WPR_CFG_PLM` | WPR | WPR 允许掩码上的权限掩码。**出货 PLM 索引 0、打开到 `0xfffff0ff`、不是 `0xffffffff`。** 这个例外是真的、相信补丁 | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x001fa814` | WPR 读允许掩码 | WPR | 模式字段在位 [7:4]；Booter 在掩码 `0x0ffff8ff` 下设位 `0x800` | [WPR 块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa818` | WPR 写允许掩码 | WPR | 同上 | [WPR 块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa81c` / `0x001fa820` | `WPR1_ADDR_LO` / `HI` | WPR | WPR1 范围、值在位 [31:4] 左移 12；被净室 refire 链清除 | [WPR 块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa824` | `WPR2_ADDR_LO` | WPR | **PLM 循环前保存、每次 Booter 尝试前重新武装**、因为否则第二个 `booter_load` 以 "WPR2 already up"（状态 `0x62`）中止。空/INIT 读 `0x0fffffff` | [解锁如何工作](../unlock/how-it-works.md) |
| `0x001fa828` | `WPR2_ADDR_HI` | WPR | 同一配对；`HI = 0` 让 `kgspIsWpr2Up()` 返回 false。空/INIT 读 `0` | [解锁如何工作](../unlock/how-it-works.md) |
| `0x001fa82c` / `0x001fa830` | memlock 范围 LO / HI | WPR | AHESASC 后（空）`0x1ffffff0` / `0x00000000`；只读 | [WPR 块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x00407000` | `SKED_HW_BLK` | SKED | 带驱动 `0x00004042`、不带 `0xbadf1201` | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407010` | `SKED_PM_UNK10` | SKED | 读 `0x00000000`；含义 **not documented** | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407020` | `SKED_TRAP` | SKED | 读 `0x00000000` | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407024` | `SKED_TRAP_EN` | SKED | `0x3dfffffc`、与 A100 相同 | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407054` | `SKED_UNK54` | SKED | 驱动前 `0x60000600` 或 `0x600000c0`、而 A100 和 RTX 3090 上**为零**。GSP 固件里被引用最多的未文档化 SKED 寄存器。从没写测试过；功能 **not documented** | [未解问题](../frontier/open-questions.md) |
| `0x00408970` | `gpcMask` | GR | 一张卡上 `0xdc`、每次强制尝试后重新断言。一条关闭的死路 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00409664` | `FECS_FEAT_OVERRIDE` | FECS | 在**每一颗**被探测的 Ampere 卡上返回 `0xbadf5040`、节流与否、所以该值不携带关于这张卡的任何信息 | [算力节流](../unlock/compute-throttle.md) |
| `0x00409668` | `FECS_FEAT_READOUT_1` | FECS | 相同、到处 `0xbadf5040` | [算力节流](../unlock/compute-throttle.md) |
| `0x00504204` | `SM_ISSUE_RATE_MODIFIER` | SM | **不是**算力节流：13 张对比 Ampere 卡和一颗每个速度选择熔丝都在 0 的 96-SM GA100 上读 `0x00000005`。主机可写；清零它什么都不改变。无驱动加载时 `0xbadf1201` | [算力节流](../unlock/compute-throttle.md) |
| `0x00820000` | `FUSE_FUSECTRL` | FUSE | 熔丝控制器、群组里全部 15 张卡上 `0xe0040000` 相同 | [熔丝与 OTP](../hardware/fuses-and-otp.md) |
| `0x00820040` | `FUSE_EN_SW_OVERRIDE` | FUSE | 170HX 和 A100 上 `0x00000000`、消费级和工程样品部件上 `0x00000001`。在 170HX 上可写且持久、却不会带来任何可观察的改变、这正是排除软件熔丝覆盖路线的原因 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820078` | `FUSE_EN_PROGRAM` | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x0082007c` | `FUSE_DIS_PROGRAM` | FUSE | `0x00000000`；GA10x 上 `0xbadf5040` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820080` | `FUSE_BYPASS_STATUS` | FUSE | `0x00000000`；GA10x 上 `0xbadf5040` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820084` | `FUSE_DIS_SW_OVR` | FUSE | 全部 15 张卡上 `0x00000001`；高安全写被弹回。软件熔丝覆盖被永久阻塞 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008200d0` .. `0x008200f4` | `OPTB_D0` .. `OPTB_F4` PLM | FUSE | 十个连续权限掩码（`d0`、`d4`、`d8`、`dc`、`e0`、`e4`、`e8`、`ec`、`f0`、`f4`）、全部被 Gen2 `xp3gTable` 写成 `0xffffffff`。`0x008200d0` 和 `0x008200dc` 读锁定 `0xffffff8f`、其它八个读打开。**每个守护什么 not documented** | [OPTB PLM 块](../unlock/register-reference.md#optb-plm-block-written-by-0007) |
| `0x008200fc` | `FUSE_SS_PLM` / `OPT_PLM` | FUSE | 一个寄存器、两个名字（`OPT_PLM` 是分支代码标签、`FUSE_SS_PLM` 是净室工具名）。守护速度选择熔丝块和 `OPT_FB_CONFIG`。**出货 master 从不写它。** 一次扫描读 `0xffffffff`、另一次 `0x000003ff`、它是否可写**仍开放** | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00820148` | OTP 备用位 | FUSE | `0x00000000`、永不可设置；用途 **not documented** | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820224` | `FUSE_SS_DP` | FUSE | 双精度速度选择熔丝、一个单独 1 位字段：170HX 上 `0x00000001`（降低） | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008202c4` | `OPT_ROP_L2_DISABLE` | FUSE | 镜像 `0x00820368` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820328` | `OPT_FB_CONFIG` | FUSE | 4 位显存拓扑选择器、被 PLM `0x008200fc` 守护。在 `probe.sh` 里文档化、从没写测试过 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820340` | `OPT_MEMORY_LOCKED_ENABLED`（`FUSE_MEM_LOCKED`） | FUSE | 群组里全部 15 张卡上 `0x00000001`、意味着显存配置名义上不可运行时改变。它不阻塞解锁：出货链反正重写 CFG1 和 LMR | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820350` | `OPT_GPC_DISABLE` | FUSE | 每卡 GPC 禁用掩码：四张不同卡上 `0x85`、`0x45`、`0x13`、`0xa8`。高安全写被弹回、值被锁存 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820364` | `OPT_FBP_DISABLE` | FUSE | FBP 禁用掩码：10 GB 卡上 `0x00000840`（FBP 6 和 11 关）、社区转储上 `0x00000852`、另两个单元上 `0x00000009` 和 `0x00000180` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820368` | `OPT_FBPA_DISABLE` | FUSE | FBPA 禁用掩码：10 GB 卡上 `0x000000c3`（20 活）、8 GB 卡上 `0x00c0330c`（16 活）。**决定 FBPA 数的正是它，而不是 CFG1** | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0082036c` | `OPT_FBIO_DISABLE` | FUSE | 镜像 `0x00820368` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x0082038c` | `FUSE_QUADRO_WR_SEC` | FUSE | `0x00000001`；这是允许 `0x00823804` 被完全打开的东西 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820394` | `OPT_PCIE_LANE_DISABLE` | FUSE | 170HX 和每个对比部件上 `0x00000000`。**证明 x4 位宽是一个板级电容问题、不是熔丝** | [PCIe 子系统](../hardware/pcie-subsystem.md) |
| `0x00820398` | `OPT_SPARE_FS` | FUSE | `0x00000000` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008203f0` | `FUSE_FEAT_OVR_DIS`（`OPT_FEATURE_FUSES_OVERRIDE_DISABLE`） | FUSE | **主灭杀熔丝、在 `0x00000000` 未烧断。这个单一零就是整个解锁存在的原因** | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008203f4` | `OPT_INTERNAL_SKU` | FUSE | `0` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x0082049c` | `OPT_HALF_FBPA_ENABLE` | FUSE | 24 位每-FBPA 半容量位掩码；非零意味着容量减半。来自 `probe.sh` 目录 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x008204bc` | `OPT_SLT_REV` | FUSE | 硅片批次/测试修订、被 `ga100_topology_report.py` 读取 | [熔丝与 OTP](../hardware/fuses-and-otp.md) |
| `0x008204d8` | `OPT_PCIE_DEVIDA` | FUSE | SKU 身份熔丝：`0x000020c2`（8 GB）、`0x00002082`（10 GB）；A100 读 `0x20b2` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820520` | `FUSE_PCIE_MAGIC_D` | FUSE | 170HX 上 `0x16680000`、位 25 设置（`GEN4_SPEED_DISABLED`、NVIDIA bug 2220334）、对比 A100 和 Drive GA100 上 `0x00200000`。**它是否可写是一个开放问题** | [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md) |
| `0x0082056c` | `OPT_PCIE_DEVIDB` | FUSE | 两块物理 10 GB 单元上 `0x000020c2`、所以 10 GB 卡上 DEVIDA 和 DEVIDB 不一致。8 GB 值**有争议**：一次 2026-07-19 对一张 `0x20c2` 卡的探测读 `0x000020c2`、而跨全部 11 个带数据部件成立的 `DEVIDB = DEVIDA + 0x40` 规则预测 `0x00002102` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x0082057c` | `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | FUSE | 两个 170HX SKU 上 `0x00000001`、其它 14 颗 Ampere 部件上 `0x00000000`。**硬只读**：从主机、高安全 ROP 和 Booter 载荷尝试、总是回读 `0x00000001`。Gen2 反正工作 | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820580` | `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | FUSE | 两个 170HX SKU 上 `0x00000001` | [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md) |
| `0x00820584` | `FUSE_DEVID_SW_OVR_DIS` | FUSE | 170HX 和每个对比部件上 `0x00000001` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x0082059c` | `FUSE_SS_FFMA` | FUSE | 融合乘加速度选择、170HX 上 `0x00000005`（除以 32） | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008205c4` | `OPT_GPC_DEFECTIVE` | FUSE | 几张 DISABLE 掩码置了三个位的卡上 `0x00000000`、一张 10 GB 卡上 `0x81`。"Disabled" 和 "defective" 是分离的掩码 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008205cc` | `OPT_FBP_DEFECTIVE` | FUSE | 10 GB 卡上 `0x00000840`、恰好匹配 `OPT_FBP_DISABLE`、所以那个单元上没有禁用-但-好 FBP | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008205d0` / `0x008205d4` / `0x008205e8` | `OPT_FBPA_DEFECTIVE` / `FBIO_DEFECTIVE` / `ROP_L2_DEFECTIVE` | FUSE | 各 `0x00c03000` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820618` | `FUSE_FBPA_MEM_WR_SEC`（`OPT_SECURE_FBPA_MEM_WR_SECURE`） | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820670` | `OPT_FB_FALCON_PRI_ACCESS_DISABLE` | FUSE | `0x00000000`、意味着**一个 Falcon 保留对 FB 寄存器的 PRI 访问**。那个属性恰是 SEC2 Booter ROP 链依赖的东西 | [ROP 链](../unlock/rop-chain.md) |
| `0x00820684` | `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | FUSE | `0x00000007`、[2:0] 全部三位设置、对比 A100 和大多数消费级部件上 `0x00000000` | [NVLink](../frontier/nvlink.md) |
| `0x0082074c` | `FUSE_OPT_SECURE_GSP` | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008207d4` | `FUSE_SS_FMLA16` | FUSE | 170HX 上 `0x00000005`、每个未节流 Ampere 部件上 `0x00000000` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207d8` | `FUSE_SS_FMLA32` | FUSE | `0x00000005`；一张 RTX 3070 读 1 | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207dc` | `FUSE_SS_IMLA0` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e0` | `FUSE_SS_IMLA1` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e4` | `FUSE_SS_IMLA2` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e8` | `FUSE_SS_IMLA3` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207ec` | `FUSE_SS_IMLA4` | FUSE | `0x00000005`；一张 RTX 3070 读 1。解锁后，全部九个速度选择熔丝都停在 `0x5`，因为覆盖取代了它们 | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x00820800` | `CTRL_OPT_HALF_FBPA` | FUSE | 半容量熔丝的合并覆盖状态、来自 `probe.sh` 目录 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820818` | `CTRL_OPT_FBPA` | FUSE | `0x00000000`、无覆盖存在 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820820` | `CTRL_OPT_PERLINK` | FUSE | 每-NVLink 覆盖影子；从没写测试过 | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x0082082c` | `CTRL_OPT_PCIE_LANE` | FUSE | `0x00000000` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820834` | `CTRL_OPT_FB_CONFIG` | FUSE | `OPT_FB_CONFIG` 的合并覆盖状态 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820838 + i*4` | `FUSE_CTRL_OPT_TPC_GPC(i)` | FUSE | 每-GPC TPC 覆盖、`0x00000000`。**只移除（减性）**：写它从不加回一个 TPC | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820840` | MIG 使能 | FUSE | 出厂 `0`；设位 0 被报告启用 MIG 并持久。**单一报告、一次仓库级 grep 找 `0x820840` 一无所获** | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820938` | `CTRL_OPT_FBP` | FUSE | `0x00000000` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008209b8` | `CTRL_OPT_NVLINK` | FUSE | 位 [15:0]、每链路；每张被探测的卡上读 `0x00000000` | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x00820c00` | `STATUS_HALF_FBPA` | FUSE | `0`、所以没有要恢复的半容量熔丝 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c14` | `STATUS_OPT_FBIO` | FUSE | 8 GB 卡上 `0x00c0330c`。**这是 FBIO、不是 FBPA** | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c18` | `STATUS_OPT_FBPA` | FUSE | `0x00c0330c` / `0x000000c3`。这是 FBPA 状态镜像的正确地址 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c1c` | `STATUS_OPT_GPC` | FUSE | 总是镜像 `0x00820350` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c2c` | `STATUS_OPT_PCIE_LANE` | FUSE | `0x00000000` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820c30` | `STATUS_OPT_SPARE_FS` | FUSE | `OPT_SPARE_FS` 的只读镜像 | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c34` | `STATUS_OPT_FB_CONFIG` | FUSE | `OPT_FB_CONFIG` 的只读镜像 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820c38 + i*4` | `FUSE_STATUS_OPT_TPC_GPC(i)` | FUSE | 每-GPC TPC 状态；一张卡上 GPC0/3/5 读 `0xff`、其它读 `0x01` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820d38` | `STATUS_FBP` | FUSE | 一个单元上 `0x00000180` | [地板清扫熔丝](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820db8` | `STATUS_OPT_NVLINK` | FUSE | `0x00000007`、`0x00820684` 的只读镜像；与 Drive A100 共享 | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x00821060` | `OPT_SKU_ID` | FUSE | 8 GB 卡（`0x20C2`）上 `0x00000080`；10 GB 卡（`0x2082`）上 `0x00000068` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00823800` | `FEAT_OVR_ECC_PLM` | FEAT_OVR | 权限掩码、出厂 `0xffffff8f`。**一个与 `0x00823804` 不同的寄存器**、一个频繁的转写失误。被 Gen2 `xp3gTable` 打开、master 从不 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823804` | `FEAT_OVR_PLM` | FEAT_OVR | **门控 SS0/SS1 的权限掩码。** 出厂 `0xffffff8f`、出货 PLM 索引 3、打开到 `0xffffffff`。常开岛里唯一条目、所以它**挺过 FLR** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823808` | `FEAT_OVR_QUADRO` | FEAT_OVR | **按晶片且无法解释。** 观察到：`0x00100183`（出厂、PLM 范围扫描、中等）、`0x00000081`（解锁后探测、中等）、`0x00000181` / `0x00000182`（两块物理 170HX 单元、高、13 个分级差异之一）、`0x01000282`（A100 80 GB）。只读。**开放问题：** 为什么值跨全部三份转储都不同。解锁或驱动里的某个东西可能正在碰 Quadro-对比-消费级分类字、那可能是驱动可见特性类的杠杆。下一步：在一张卡上、出货序列的每个阶段前后重读这个寄存器 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x0082380c` | `FEAT_OVR_ECC` | FEAT_OVR | `0x00888888`；只读 | [ECC](../frontier/ecc.md) |
| `0x00823810` | `FEAT_OVR_ECC_1` | FEAT_OVR | `0x002aaaaa`；只读 | [ECC](../frontier/ecc.md) |
| `0x00823814` | `FEAT_READOUT_0` | FEAT_OVR | 170HX 上只读 `0x00000233`；一颗参考 GA100 板读 `0xef8ff100`。**字段布局 not documented** | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823818` | `FEAT_READOUT_1` | FEAT_OVR | 节流时 `0x016db6ed`、**解锁时 `0x00000000`。最干净的单个寄存器 "这张卡解锁了吗" 测试**、且比回读 SS0 可靠得多 | [验证](../procedures/verify.md) |
| `0x0082381c` | `FEAT_OVR_SM_SPEED_SELECT`（SS0） | FEAT_OVR | **算力解锁写 0。** 八个 4 位字段（IMLA0-3、FMLA16、FMLA32、FFMA、DP）、写成 `0x88888888` = 覆盖启用、全速。出厂值按卡而异。**挺过 FLR** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823820` | `FEAT_OVR_SM_SPEED_SELECT_1`（SS1） | FEAT_OVR | **算力解锁写 1。** 第九个字段、IMLA4、写成 `0x00000008`。两个写都需要。**挺过 FLR** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` | FEAT_OVR | 两个 170HX SKU 上 `0x00000000`；只读 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823828` | `FEAT_READOUT_2` | FEAT_OVR | 170HX 上 `0x00000000`、全部 A100 和 Drive 部件上 `0x00000007`；只读 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x0082382c` | `FEAT_READOUT_2`（一份转储里的别名） | FEAT_OVR | `0x0000000a`。**命名在两份转储之间未定**、字段布局 not documented | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823b00` | 行重映射器 PLM（`FEAT2`） | FEAT_OVR | 出厂 `0xffffff8f`、被 Gen2 家族补丁单独打开到 `0xffffffff`。一次 in-HS 扫描在 FLR 后读它打开、所以它可能常开、但打开它**不**让几何布局持久 | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00830040` | NVDEC `MAILBOX0` | NVDEC | 从 PL0 被阻塞/只读、读 `0xbadf1100` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840040` | SEC2 `FALCON_MAILBOX0` | SEC2 | **`s_executeBooter` 实际读的邮箱。** 每个携带载荷的运行上 `0x31`、那是原始退出路径上被驱动种下、未被触碰的参数、不是一个 Booter 错误码。寄存器回读是唯一有效判决 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840044` | SEC2 `FALCON_MAILBOX1` | SEC2 | 第二个邮箱；从 PL0 被阻塞/只读 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084007c` | `SFTRESET` | SEC2 | 软复位：写 1 并读回、只在 `SCTL` HSMODE（位 1）设置时有效 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840084` | `FALCON_RM` | SEC2 | 资源管理器临时区 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008400f4` | `FALCON_HWCFG2` | SEC2 | 位 10 = RISCV、读 **0**、确认 SEC2 是一颗 Falcon v4 核心而非 RISC-V | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840100` | `FALCON_CPUCTL` | SEC2 | 位 1 = STARTCPU 脉冲、位 4 = HALTED（只读） | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840104` | `FALCON_BOOTVEC` | SEC2 | 引导向量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084010c` | `FALCON_DMACTL` | SEC2 | 轮询直到清扫位 `0x6` 清除；`0xffffffff` 读意味着窗口还没响应、不是失败 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840110` | `FALCON_DMATRFBASE` | SEC2 | DMA 基址 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840114` | `FALCON_DMATRFMOFFS` | SEC2 | DMEM/IMEM 偏移量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840118` | `FALCON_DMATRFCMD` | SEC2 | DMA 命令 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084011c` | `FALCON_DMATRFFBOFFS` | SEC2 | 帧缓冲偏移量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840128` | `FALCON_DMATRFBASE1` | SEC2 | DMA 基址高 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840180` / `0x00840184` | `IMEMC` / `IMEMD` | SEC2 | IMEM 端口对、自动递增、每 256 字节标签；安全标签位是 `1 << 28`。用于把已加载的 Booter 在 0 到 `0x8700` 范围读回 | [ROP 链](../unlock/rop-chain.md) |
| `0x00840240` | `SCTL` | SEC2 | 安全控制；HSMODE = 位 1、`AUTH_EN` = `1 << 14`。一次引擎复位后观察到 `0x3000` 到 `0x3002` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840284` | SEC2 `DMEM_PLM` | SEC2 | DMEM 权限掩码；LS 模式下 `0xff`（完全打开） | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008403c0` | `FALCON_ENGINE` | SEC2 | 位 0 = RESET；脉冲 1 然后 0。引擎复位门是 `(resetPLM & 0x77) == 0x77` | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008403c4` | SEC2 复位 PLM | SEC2 | **决定 SEC2 能否再次被复位、每个净室 fire 工具把它读作一个就绪门。** 干净 `0xff`、一次成功 `booter_unload` 后 `0xdf`、`secure_teardown` 后 `0x8f`（它阻塞 `SFTRESET`）。`reset_allowed = {0xff, 0xdf}`。**被 FLR 清到 `0xff`** | [恢复](../procedures/recovery.md) |
| `0x00840480` / `0x00840484` | SEC2 发射后状态 | SEC2 | 作为 HS-退出副作用把 `0` 移到 `0x1` 和 `0` 移到 `0x11100`、从不恢复。字段布局 **not documented** | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840530` | `SCP_P2PRX` | SEC2 | 免驱动复位期间轮询位 3 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008411ec` | `KFUSE_CTL` | SEC2 | 轮询位 0 设置、位 1 清除 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00900200 + n*0x4000` | 每-FBPA `CFG0` | FBPA | CFG0 寄存器的单播实例 *n*（n = 0..23）；两个 SKU 的每个活实例上 `0x07981800` | [每-FBPA 孔径](../unlock/register-reference.md#per-fbpa-unicast-aperture) |
| `0x00900204 + n*0x4000` | 每-FBPA `CFG1` | FBPA | 单播寻址深度寄存器。**出货驱动从不写它**；驱动路径里一次到 `0x009a0204` 的广播写就够。在一个无 devinit 的免驱动运行时、全部 24 个必须手工写 | [每-FBPA 孔径](../unlock/register-reference.md#per-fbpa-unicast-aperture) |
| `0x0090020c + n*0x4000` | 每-FBPA `CSTATUS_RAMAMOUNT` | FBPA | **验证目标**：出厂 `0x200`（每 FBPA 512 MiB）、40 GB 档位 `0x800`、64 GB 档位 `0x1000`。被地板清扫的 FBPA 返回一个 `0xbadf20xx` 哨兵 | [验证](../procedures/verify.md) |
| `0x009a0008` | FB-几何 PLM | FBPA | 锁定 `0xffffff8f`；在净室 `FB_GEO_PLMS` 列表里。它精确守护什么 **not documented** | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a000c` | FB-几何 PLM | FBPA | 同上 | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a0040` | FBFLCN `MAILBOX0` | FBPA | FB Falcon 邮箱；从 PL0 被阻塞/只读、读 `0x00003fff` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x009a0148` | **FBPA PLM** | FBPA | 门控 CFG1 的权限掩码。出厂 `0xffffff8f`、**出货 PLM 索引 1、打开到 `0xffffffff`**。也是 `dmem.bin` 缺失时内置回退载荷目标 | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x009a014c` | FB-几何 PLM | FBPA | `0xffffff8f`；只净室列表 | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a0164` | `FBPA_NUM_ACTIVE`（`NUM_ACTIVE_FBPS`） | FBPA | 8 GB 卡上 `0x00000008` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0168` | PLM 候选 | FBPA | 读 `0xffffffcf`；只出现在 26 寄存器调查里、它守护什么 **not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0200` | `FBPA_CFG0_BROADCAST` | FBPA | 170HX 和 A100 40/80 GB 上 `0x07981800`；一颗参考 GA100 Drive 部件上 `0x06981800` | [FBPA 孔径](../unlock/register-reference.md#fbpa-broadcast-aperture-0x009a0000-to-0x009a3fff) |
| `0x009a0204` | `NV_PFB_FBPA_CFG1`（广播） | FBPA | **每个显存分区的寻址深度、档案里被引用最多的寄存器。** 两个 SKU 出厂 `0x02449000`、解锁 `0x02779000`（64 GB）/ `0x02669000`（40 GB）。档位字节在位 [23:16]：`0x44` / `0x66` / `0x77`。**不挺过 FLR** | [显存几何布局](../unlock/memory-geometry.md) |
| `0x009a020c` | `FBPA_CSTATUS` 广播 | FBPA | 解锁 170HX 上 `0x00001000` 对比 A100 80 GB 上 `0x00000fff` | [FBPA 孔径](../unlock/register-reference.md#fbpa-broadcast-aperture-0x009a0000-to-0x009a3fff) |
| `0x009a0224` | `TIMING1` | FBPA | 编程 HBM 时序、`0x12050d12`（R2W 18、W2R 13、R2P 5、W2P 18） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0290` | `CONFIG0` | FBPA | `0x1255b93c`；位 31 `USE_TIMING_REGS` = 0、所以生成的影子生效 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0294` | `CONFIG1` | FBPA | `0x38d4841b`（CL 27、WL 8、RD_RCD 18、WR_RCD 13、QPOP_OFFSET 14） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0298` | `CONFIG2` | FBPA | `0x88130b11`（tWR 19、W2R_BUS 8、R2W_BUS 8、RPRE 1、WPRE 1、CDLR 11） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02b0` | `TIMING0_GEN` | FBPA | 实际生效的生成影子：tRC 60、tRFC 441、tRAS 42 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02b4` | `TIMING1_GEN` | FBPA | R2W 29、W2R 20、W2P 28 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02b8` | `TIMING2_GEN` | FBPA | RD_RCD 18、WR_RCD 13、RRD 6 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02c0` | `TIMING4_GEN` | FBPA | FAW 21；原始 `TIMING4` 持有一个陈旧的 FAW 40 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02d8` | `TIMING9_GEN` | FBPA | CCDL 4、CCDS 2 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a02e0` | `TIMING16_GEN` | FBPA | RP 18 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0300` | `FBPA_MRS_0` | FBPA | HBM 模式寄存器 0、170HX、A100 和 Drive A100 上 `0x00000003` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0304` | `FBPA_MRS_1` | FBPA | 每张卡上 `0x00100000` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0320` | `FBPA_MRS_8`（MR8 密度） | FBPA | 全部 15 张卡上 `0x00200000`、所以它**不是**容量限制 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0334` | `FBPA_MRS_2` | FBPA | `0x00200019`（8 GB 卡）、`0x002000cf`（10 GB 卡和 A100 40 GB） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0338` | `FBPA_MRS_WL_RL` | FBPA | `0x003000eb`（8 GB 卡）、`0x003000ea`（10 GB 卡） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a038c` | `FBPA_HBM_CFG0` | FBPA | 170HX 和 A100 上 `0x000000a7`、Drive A100 上 `0x000000a6`。字段 `dual_rank[0]`、`dual_rank_bank[1]`、`SID_VAL[11]` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a03f0` | PLM 候选 | FBPA | `0xffffff8f`；只调查、它守护什么 **not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0470` | `FBPA_ECC_CTRL` | FBPA | 读 `0` 配 `MASTER_EN` 只读。ECC 熔断关闭、无已知杠杆 | [ECC](../frontier/ecc.md) |
| `0x009a0554` | PLM 候选 | FBPA | `0xffffffcf`；只调查、**not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0838` / `0x009a083c` | `FBPA_VEND_ID_C0` / `C1` | FBPA | 全部 15 张卡上 `0x00000000`、所以 HBM 厂商 ID 不在这里暴露 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0974` | `FBPA_TRAINING_STATUS` | FBPA | `0x00000000` = FINISHED。SUBP0 在 [1:0]、SUBP1 在 [3:2]；值 2 意味着 ERROR | [排障](../procedures/troubleshooting.md) |
| `0x009a0bfc` | PLM 候选 | FBPA | 读 `0x00000000`；只调查、**not documented** | [26 寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a3cb4` / `0x009a3cb8` / `0x009a3cbc` | `I1500_INSTR` / `MODE` / `DATA` | FBPA | IEEE 1500 HBM 测试端口；`0x0000000f` / `0x00000008` / `0x40000000` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a3cc0` / `0x009a3cc4` / `0x009a3cc8` | `I1500_SHADOW_WIR` / `WDR` / `STATUS` | FBPA | `0x000000f0` 只读 / 按晶片 / `0x00000000` 空闲。`WDR` 在 8 GB 卡上读 `0x8000f000`、10 GB 卡上 `0x8273ff83` | [显存子系统](../hardware/memory-subsystem.md) |

> [!NOTE]
> **看起来相邻却无关的寄存器**
>
> `0x00823800` 和 `0x00823804` 相隔四个字节、做不同的事：`0x00823800` 是 `FEAT_OVR_ECC_PLM`、`0x00823804` 是门控算力解锁的 `FEAT_OVR_PLM`。同样 `0x00820c14` 是 FBIO 状态、`0x00820c18` 是 FBPA 状态。两对都在流传的笔记里被换过。

---

## 载荷偏移量

这些**不是 BAR0 地址。** 它们是字节偏移量，指向驱动交给 Booter 的那个 `0x0000f800` 字节（63,488 字节）假签名缓冲区，Booter 会把它 DMA 到 SEC2 DMEM `0x0800`。因此：

> [!NOTE]
> **换算规则**
>
> **DMEM 地址 = 载荷偏移量 + `0x800`。** 缓冲区与 DMEM `0x0800`..`0xffff` 一一对应，因为 `0x0800 + 0xf800 = 0x10000`，恰好是 64 KB DMEM 的顶部。

整个缓冲区先用 dword `0x000004a7` 填满，然后恰好覆写 24 个槽。下面每个值都直接读自 `0001-sec2-postbl-plm-ss-cfg.patch` 里的 `_kgspSec2PostblTimingFillPayload()`，该表在**出货 `master` 和全部十二个归档分支里逐字节相同**。其中两个槽是参数：你要写入的地址和你要写入的值。其余一切都是 ROP 尾。

| 载荷偏移量 | DMEM 地址 | 值 | 角色 |
|---|---|---|---|
| （全部） | `0x0800`-`0xffff` | `0x000004a7` | 背景填充 dword；为什么是这个常量 **not documented** |
| `0x1100` | `0x1900` | `0x00000007` | **not documented** |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **写进栈守卫全局的假金丝雀。** 地址 `0x6340` 是承重事实；值任意、只要匹配每个保存副本 |
| `0xf754` | `0xff54` | *writeValue* | 值参数、最低尾槽 |
| `0xf758` | `0xff58` | `0xc0deca7e` | 保存金丝雀槽 |
| `0xf75c` | `0xff5c` | `0x00000cbd` | Falcon IMEM 地址；角色 **not documented** |
| `0xf76c` | `0xff6c` | *writeAddr* | BAR0 地址参数 |
| `0xf774` | `0xff74` | `0x00001fbd` | "elevator" gadget 家族里的 IMEM 地址 |
| `0xf780` | `0xff80` | `0x00000000` | **not documented** |
| `0xf788` | `0xff88` | `0x000010aa` | **BAR0-master 写 gadget、`reg_write_indirect`。** 这是让整个利用成为一个写原语的槽 |
| `0xf78c` | `0xff8c` | `0x0000815a` | IMEM 地址；角色 **not documented** |
| `0xf790` | `0xff90` | `0x00008e18` | IMEM 地址；角色 **not documented** |
| `0xf794` | `0xff94` | `0xc0deca7e` | 保存金丝雀槽 |
| `0xf798` | `0xff98` | `0x0000815a` | 同一个 IMEM 地址的第二份副本 |
| `0xf79c` | `0xff9c` | `0x00000000` | **not documented** |
| `0xf7a0` | `0xffa0` | `0xc0deca7e` | 保存金丝雀槽 |
| `0xf7a4` | `0xffa4` | `0x00001fbd` | 第二份副本 |
| `0xf7b0` | `0xffb0` | `0x0000ffbc` | IMEM 地址；角色 **not documented** |
| `0xf7b8` | `0xffb8` | `0x0000582d` | IMEM 地址；角色 **not documented** |
| `0xf7c4` | `0xffc4` | `0xc0deca7e` | 保存金丝雀槽 |
| `0xf7c8` | `0xffc8` | `0x00000cbd` | 第二份副本 |
| `0xf7d8` | `0xffd8` | `0x00000003` | **not documented** |
| `0xf7e0` | `0xffe0` | `0x00001fbd` | 第三份副本 |
| `0xf7f4` | `0xfff4` | `0x00000ccb` | `regtable_rw_indexed`、一个开放问题：它索引的恰是载荷砸碎的那些描述符表、解锁却工作 |
| `0xf7f8` | `0xfff8` | `0x00007f2f` | 最外槽；角色 **not documented** |

金丝雀 `0xc0deca7e` 在每份副本里恰好出现五次：`0x5b40` 处，以及载荷偏移量 `0xf758`、`0xf794`、`0xf7a0`、`0xf7c4` 处。

> [!NOTE]
> **开放问题：无法解释的载荷常量**
>
> 二十四个槽中有十五个没有确认角色，它们一共携带十种不同的常量。ROP 的写稿命名了一个邻近的 gadget 家族（`0x1fb9`、`0x1fca`、`0x814e`、`0x8173`、`0x7f82`），所以这些常量看起来像是同一个尾翻译而来，但没人走过带注释的反汇编来确认。见[ROP 链](../unlock/rop-chain.md) 和[未解问题](../frontier/open-questions.md)。

### 载荷引用的承重 DMEM 地址

与上面表格的右列处于同一空间，这里按 DMEM 地址给出，因为反汇编是这样引用它们的。

| DMEM 地址 | 含义 |
|---|---|
| `0x0100` 及以下 | 这里什么都没分配、那正是杀死"低 DMEM 里分阶段 mega-ROP"想法的东西 |
| `0x0530` | DMA 和引擎配置描述符 |
| `0x0600` | `WprMeta`、一个 256 字节结构 |
| `0x06fc` | Booter 在 `r4 == 0` 分支上存 `0xa0a0a0a0` 的地方。**与 `0x001fa824` / `0x001fa828` WPR2 寄存器无关**、尽管数字巧合 |
| `0x0800` | DMA'd 签名缓冲区的基址、即载荷偏移量 0 |
| `0x103c` 起 | 加密会话描述符 |
| `0x2383` 和 `0x8e08` | 寄存器描述符表、被载荷线性砸碎 |
| `0x6340` | 栈金丝雀全局、25408 十进制 |
| `0x8700` | Booter 代码和数据的末尾 |
| `0xffec` | 喂 `main` 的退出状态、决定 `secure_teardown` 是否运行的槽 |

### 跨变体的载荷大小和金丝雀

| 变体 | 缓冲区大小 | DMA 基址 | 金丝雀值 |
|---|---|---|---|
| 出货 `master` 和全部 12 个分支 | `0x0000f800` = 63,488 B | `0x0800` | `0xc0deca7e` |
| 净室 ROP 写稿 | `0x0000f800` | `0x0800` | `0xfaceb13d` |
| 被取代的 `builder.py` / `patcher.py` | `0x0000f700` = 63,232 B | `0x0900` | `0xdead2c20` at `0x2c20` |

被取代工具使用的 `0x0900` DMA 基址，正是某条归档消息把金丝雀地址写成 `0x6440` 的原因：`0x5b40 + 0x900 = 0x6440`。在出货路径上基址是 `0x0800`，金丝雀位于 `0x6340`。

---

## 相关页面

- [寄存器参考](../unlock/register-reference.md)、本索引的解释配套
- [权限级别掩码](../unlock/privilege-level-masks.md) 看 PLM 半字节编码
- [解锁如何工作](../unlock/how-it-works.md) 和[驱动补丁](../unlock/driver-patches.md)
- [显存几何布局](../unlock/memory-geometry.md)、[算力节流](../unlock/compute-throttle.md)、[PCIe Gen2](../unlock/pcie-gen2.md)
- [Falcon 与 Booter](../unlock/falcon-and-booter.md) 和[ROP 链](../unlock/rop-chain.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)、[显存子系统](../hardware/memory-subsystem.md)、[PCIe 子系统](../hardware/pcie-subsystem.md)
- [术语表](../start/glossary.md) 看 PLM、FLR、WPR、FBPA、LMR、AON、HS、PL0/PL3
- [保留工件](artifacts.md) 和[外部来源](external-sources.md)
