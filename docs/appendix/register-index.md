# 寄存器索引

## 本页覆盖内容

这是一张**扁平的查找表，收录本项目任何文档中出现过的所有 BAR0 寄存器地址，并按数值地址升序排列。** 它只为快速回答一个问题：你刚在 `dmesg` 输出、补丁或某人的脚本中看到一个陌生的十六进制地址，想知道它属于哪个模块，以及具体有什么作用。

本页有意保持简洁。每一行只提供一句话的含义说明，以及一个指向详细解释页面的链接。关于出厂值、解锁值、PLM 门控、FLR 后是否保留，以及这些结论背后的推理，请参阅[寄存器参考](../unlock/register-reference.md)，那是本索引的配套说明页。

两条最省时的规则：

- **地址列中的所有内容都是 BAR0 字节偏移量**，以 region 0 的起点为基准。有些解锁*值*看起来像合理的地址，但实际上并不是。如果你的数字不在本索引中，先不要认定索引不完整，请先检查[不是 BAR0 地址的数字](../unlock/register-reference.md#numbers-that-are-not-bar0-addresses)。
- **读操作返回 `0xbadf....` 时，返回值不是数据。** 这是 PRI 毒值，或表示权限违规的哨兵值。参见[哨兵值](../unlock/register-reference.md#sentinel-values)。

项目尚未确认寄存器用途的行会标注 **尚未文档化**。这个标记很重要：它表示档案资料中没有人解析出该寄存器的用途，而不是本索引漏写了说明。

在 BDF 为 `0000:05:00.0` 的显卡上手工读取一个地址：

```bash
sudo dd if=/sys/bus/pci/devices/0000:05:00.0/resource0 \
        bs=4 count=1 skip=$((0x009a0204 / 4)) 2>/dev/null | xxd -e -g4
```

### 下文使用的模块缩写

| 模块 | 含义 |
|---|---|
| `PMC` / `PBUS` | 主控和总线暂存区 |
| `PTOP` | 拓扑标量，描述完整 GA100 晶片 |
| `XVE` | PCIe 配置空间影子，BAR0 基址为 `0x88000` |
| `XP-PL` | PCIe 物理层链路配置，位于 `0x0008cxxx` |
| `XP3G` | PCIe PHY 速率覆盖数组，位于 `0x0008e1xx` |
| `FBHUB` / `MMU` | 帧缓冲枢纽和内存管理单元，位于 `0x001xxxxx` |
| `PMU` | 电源管理单元 Falcon，位于 `0x0010axxx` |
| `GSP` | GSP RISC-V 核心及其 Falcon 外壳，位于 `0x0011xxxx` |
| `BSI` | 常电（AON）引导和安全暂存区，位于 `0x001180xx` |
| `LTC` | 二级缓存切片 |
| `WPR` | 写保护区域控制，位于 `0x001fa7xx` / `0x001fa8xx` |
| `SKED` / `FECS` / `SM` | 图形和算力前端 |
| `FUSE` | 熔丝和 OTP 影子，位于 `0x0082xxxx` |
| `FEAT_OVR` | 特性覆盖模块，位于 `0x008238xx` |
| `SEC2` | 安全协处理器 Falcon，基址为 BAR0 + `0x840000` |
| `FBPA` | 帧缓冲分区，广播地址为 `0x009axxxx`、单播地址为 `0x0090xxxx` |

---

## 索引

| 地址 | 名称 | 模块 | 一行含义 | 细节 |
|---|---|---|---|---|
| `0x00000000` | `PMC_BOOT_0` | PMC | 晶片身份；每个有效 GA100 都是 `0x170000a1` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00001404` | `PBUS_SW_SCRATCH(1)` | PBUS | 软件暂存区；所有受调查显卡都是 `0x20042000`，且位 14 清零 | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x0002241c` | `NV_PTOP_FS4` | PTOP | 位 0 为 `GEN2_PCIE`，位 7 为 `GEN2_PCIE_SPEED`；8 GB 卡为 `0x00000000`，10 GB 卡为 `0x00000081` | [PCIe 子系统](../hardware/pcie-subsystem.md) |
| `0x00022430` | `PTOP_SCAL_NUM_GPCS` | PTOP | 完整晶片的 GPC 数量：`8` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022434` | `PTOP_SCAL_TPC_PER_GPC`（`NUM_TPC_GPC`） | PTOP | 每个 GPC 的 TPC 数量：`8` | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022438` | `PTOP_SCAL_NUM_FBPS` | PTOP | 完整晶片的 FBP 数量：`0x0000000c`（12） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0002243c` | `PTOP_SCAL_NUM_FBPAS` | PTOP | 完整晶片的 FBPA 数量：`0x00000018`（24） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00022454` | `PTOP_SCAL_NUM_LTCS` | PTOP | L2 切片数量：`0x00000018`（24） | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00022458` | `PTOP_SCAL_FBPA_PER_FBP` | PTOP | 每个 FBP 的 FBPA 数量：`0x00000002`（一张 RTX 3090 读到 1） | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0002246c` | `PTOP_SCAL_NUM_NVLINK` | PTOP | 完整晶片的 NVLink 数量：`0x0000000c`（12） | [NVLink 硬件](../hardware/nvlink-hardware.md) |
| `0x00022470` | `PTOP_FS_STATUS` | PTOP | 熔丝裁剪状态位向量：`0x0000003f`；位 0 为 TPC，位 1 为 GPC，位 2 为 FBP，位 3 为 ROP，位 4 为 FBIO | [拓扑标量](../unlock/register-reference.md#topology-scalars-0x0002xxxx) |
| `0x00085080` | （未命名） | PRIV | 从 SEC2 注入点读取 `0xbadf1100`；GSP 会以该利用无法达到的权限写入它 | [被 PROT 阻挡的寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00085084` | （未命名） | PRIV | 同上 | [被 PROT 阻挡的寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00088070` | （未命名） | XVE | 读取返回 0，写入被忽略；**尚未文档化** | [被 PROT 阻挡的寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x00088084` | `LINK_CAP`（LnkCap） | XVE | PCIe 链路能力影子；出厂为 `0x00456101`，Gen2 补丁后为 `0x00456102` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088088` | `LINK_CTRL_STATUS`（LnkSta） | XVE | 已协商的链路状态；出厂为 `0x10410040`（LnkSta 在位 [31:16]，LnkCtl 在 [15:0]），Gen2 时为 `0x1042xxxx`。速度 = `(value >> 16) & 0xF` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x0008808c` | （未命名） | XVE | 读取为 0，写入被忽略。**不是** LnkCap2 镜像，尽管某份现场手册如此声称 | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088090` | （未命名） | XVE | 读取为 0，写入被忽略；**尚未文档化** | [被 PROT 阻挡的寄存器](../unlock/register-reference.md#registers-that-are-prot-walled-or-poisoned-from-the-injection-point) |
| `0x000880a4` | `LINK_CAP2`（LnkCap2） | XVE | 支持的链路速度向量；出厂为 `0x00000002`（仅 2.5 GT/s），补丁后为 `0x00000006`（Gen1+Gen2）。对 `setpci` 而言硬件只读 | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x000880a8` | `LINK_CTRL_2`（LnkCtl2） | XVE | 目标链路速度；补丁将位 [3:0] 设为 `0x2`，将位 [19:16] 设为 `0xF` | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008841c` | `PRIV_MISC_1` | XVE | Gen2 使能位；`0x20340500` 变为 `0x20342d00`（设置 11 和 13，清除 12 和 14）。第一次尝试即成功，并在 Booter Load 后仍然保留 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008860c` | `VSEC_DEVICE` | XVE | 厂商专用设备字；补丁试图将 `0x00000800` 改为 `0x00000801`，但**在晶片上写入失败** | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x00088610` | `VSEC_HIERARCHY` | XVE | 厂商专用层级字；出厂为 `0x00001001`，补丁通过普通主机写入清除位 12 并设置位 0 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008872c` | LTSSM 覆盖（`XVE_OVR`） | XVE | 写入 `0x00000006` 以跳过引导过程中的重新训练。在 VFIO 下，`0x2` 和 `0xa` 会暴露额外的 Gen2 行为，但最终会使函数卡死 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x00088ab4` | `XVE_B` PLM | XVE | 权限级别掩码，由九项 Gen2 系列 PLM 表打开至 `0xffffffff` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00088ce4` | （未命名） | XVE | 170HX 上为 `0x0000003f`，A100 上为 `0x00000014`；VBIOS 的一个模块通过掩码合并计算它。含义**尚未文档化** | [VBIOS](../hardware/vbios.md) |
| `0x00088fe8` | `XVE_D0` PLM | XVE | 权限级别掩码，由 `xp3gTable` 打开至 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088fec` | `XVE_D4` PLM | XVE | 权限级别掩码，由 `xp3gTable` 打开至 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088ff0` | `XVE_D8` PLM | XVE | 权限级别掩码，由 `xp3gTable` 打开至 `0xffffffff` | [XVE 影子](../unlock/register-reference.md#xve-config-space-shadow-bar0-base-0x88000) |
| `0x00088ff4` | `XVE` PLM | XVE | PCIe 配置空间影子的权限级别掩码；没有它，主机读取会返回 `0xbadf5040` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00088ff8` | `XVE_C` PLM | XVE | 第三个 XVE 能力权限级别掩码，已打开至 `0xffffffff` | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x0008c040` | `LINK_CONFIG_0` | XP-PL | 位 [19:18] 为 `MAX_RATE`；补丁通过读-改-写将其设为 `0x2` | [XP-PL 模块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c044` / `0x0008c048` / `0x0008c04c` | LINK_CONFIG 簇 | XP-PL | 与那三个可用寄存器不同的另一组簇；对这些地址的 HS 写入被拒绝。字段布局**尚未文档化** | [XP-PL 模块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c080` | 链路位宽寄存器 | XP-PL | A100 读取为 `0x00001010`；在 170HX 上从未作为调节手段使用。位宽由板级限制决定，而不是由此寄存器决定 | [物理改装](../operations/physical-mods.md) |
| `0x0008c1c0` | `PL_LINK_RATE` | XP-PL | PHY 速率字；Gen2 设置为 `0x00240036`（A100 读取为 `0x00040036`） | [XP-PL 模块](../unlock/register-reference.md#xp-pl-link-config-block-0x0008cxxx) |
| `0x0008c2c0` | `CYA_0` | XP-PL | 位 2 是 `DIS_G2` 保护位，必须清除。这是 Gen2 的核心调节项 | [PCIe Gen2](../unlock/pcie-gen2.md) |
| `0x0008e100` | `XP3G_STATUS` 基址 | XP3G | 四个 dword 组成的状态数组，第 *n* 个槽位位于基址 + 4*n*；只读 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e10c` | `XP3G_STATUS3` | XP3G | 状态数组的第 3 个槽位 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e110` | `XP3G_OVR0` | XP3G | 覆盖使能槽 0，写入 `0x00000001`（每个槽位采用 one-hot） | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e11c` | `XP3G_OVR3` | XP3G | 覆盖使能槽 3，写入 `0x00000004` | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e120` | `XP3G_VAL0` | XP3G | 覆盖值槽 0，写入 `0x00000000`。始终先写值，再写使能 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e12c` | `XP3G_VAL3` | XP3G | 覆盖值槽 3，写入 `0x00200000`（A100 的 `FUSE_PCIE_MAGIC_D` 值） | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b0` | `XP3G_PLM` | XP3G | XP3G 模块的权限级别掩码；可以干净地打开至 `0xffffffff` | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b4` | `XP3G_PLM4` | XP3G | 第二个 XP3G 权限级别掩码 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1b8` | `XP3G_PLM8` | XP3G | 第三个 XP3G 权限级别掩码 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x0008e1bc` | `XP3G_PLMC` | XP3G | 第四个 XP3G 权限级别掩码 | [XP3G 模块](../unlock/register-reference.md#xp3g-phy-rate-override-block-0x0008e1xx-0x0008e1xx) |
| `0x00100800` | `FBHUB_NUM_ACTIVE_LTCS` | FBHUB | 活动 L2 切片数量：8 GB 卡为 `0x10`（16），10 GB 卡以及 A100 PCIe 40/80 GB 为 `0x14`（20） | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b10` | FB 几何 PLM | FBHUB | 净室工作链打开的五个 `FB_GEO_PLMS` 之一；锁定值为 `0xffffff8f`。打开它**不会**让显存几何布局在 FLR 后保留 | [FB 几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x00100b38` | FB 几何 PLM | FBHUB | 只出现在最早的 HS 配方中，作为第六项 | [FB 几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x00100b84` | PLM 候选 | FBHUB | 读取为 `0xffffff88`；它保护什么内容**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x00100b90` | `FBHUB_MEM_PART_BCFG0` | FBHUB | 显存分区广播配置；每张卡都是 `0x00000603` | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b98` | `SYSMEM_HSHUB_CONNECTION_CFG` | FBHUB | sysmem 路由；`0x00000003`（BOTH、PCIe） | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x00100b9c` | PLM 候选 | FBHUB | 读取为 `0xffffffcf`；它保护什么内容**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x00100ce0` | MMU 本地显存范围（LMR） | MMU | **MMU 看到的总 FB 大小。** 两个显存几何写入目标之一。出厂值为 `0x00000208` / `0x00000288`，解锁值为 `0x0000020B`（64 GB）/ `0x0000028A`（40 GB）。编码方式为 `MiB = MAG[9:4] << SCALE[3:0]` | [显存几何布局](../unlock/memory-geometry.md) |
| `0x00100ec0` | `MMU_NUM_ACTIVE_LTCS` | MMU | 10 GB SKU 和全部三个 A100 SKU 为 `0x05001414`；8 GB SKU 报告为 `0x04001410`。这种按 SKU 划分的原因仍是**未解问题**，不是资料冲突：`...1410` 与 16 个 LTC 一致，`...1414` 与 20 个一致 | [MMU / FB 枢纽](../unlock/register-reference.md#mmu-fb-hub) |
| `0x0010a040` | PMU `FALCON_MAILBOX0` | PMU | PMU Falcon 邮箱 0；PL0 可写，读取为 `0x00000300` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x0010a044` | PMU `FALCON_MAILBOX1` | PMU | PMU Falcon 邮箱 1；PL0 可写，读取为 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110040` | GSP `FALCON_MAILBOX0` | GSP | 普通 32 位寄存器，不是 FIFO。PL0 可写；健康的 GSP 引导会将其复位为 0。**这不是 `s_executeBooter` 读取的邮箱**（后者属于 SEC2，地址为 `0x00840040`） | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110044` | GSP `FALCON_MAILBOX1` | GSP | PL0 可写，读取为 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110180` / `0x00110184` | GSP `IMEMC` / `IMEMD` | GSP | GSP 指令内存端口对 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x001101c0` / `0x001101c4` | GSP `DMEMC` / `DMEMD` | GSP | GSP 数据内存端口对，用于传递 WPR 地址 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00110624` | GSP `FBIF_CTL` | GSP | 孔径控制；Booter 的 `reg_init` 写入 `0x90`（`ALLOW_PHYS_NO_CTX` 位 7 加位 4） | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00110684` | GSP FBIF 伴随寄存器 | GSP | 由 `reg_init` 写入 `1`；用途**尚未文档化** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00111040` | GSP Falcon 外壳 `MAILBOX0` | GSP | 与 `0x00110040` 不同；PL0 可写，读取为 `0x00000000` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00111240` | `RISCV_STATUS` | GSP | GSP 核心状态。非零表示 RISC-V 核心已启动（健康引导中曾分别报告 `0x35` 和 `0x33`）；`0x0` 表示它从未启动 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00111268` | `RISCV_CPUCTL` | GSP | GSP 核心控制 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x0011126c` | GSP RISC-V 伴随寄存器 | GSP | 由 `reg_init` 写入 `1`；用途**尚未文档化** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x001180f0` | AON LMR 影子 | BSI | 显存范围值的常电域影子。**会在 FLR 时恢复**，因此不是持久化调节手段 | [FLR 后保留情况](../unlock/register-reference.md#the-flr-survival-table) |
| `0x001180f8` | `NV_PGC6_BSI_SECURE_SCRATCH_14` | BSI | 位 26 = `BOOT_STAGE_3_HANDOFF`。由 SEC2 在 HS 上下文中从 GPU 侧设置；主机驱动只负责轮询它，启动挂起 `0x65` 就是该轮询超时。**发布版链从不写入它** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00118244` / `0x00118248` | WPR 阶段暂存对 | BSI | 由 `booter_load_wpr_main` 读取后清零 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x0011824c` / `0x00118250` | memcfg 交接 | BSI | 由 `memcfg_program` 写入；只有 `0x0011824c` 的位 0 置位时才会执行 apply 轮询 | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x001182d0` | AON 安全暂存区 | BSI | PL3 可访问；内容**尚未文档化** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00118f78` | 辅助暂存区 | BSI | 所有受调查显卡都读取为 `0x00000000`；用途**尚未文档化** | [GSP 与 BSI](../unlock/register-reference.md#gsp-risc-v-and-bsi-secure-scratch-bar0-0x110000-0x118000) |
| `0x00120078` | `RING_ENUM_GPC` | PRIV ring | 每张 170HX 都读取为 `5`；任何写入尝试都没有改变它 | [GA100 晶片](../hardware/ga100-silicon.md) |
| `0x001402b4` | LTC 伴随寄存器 | LTC | 曾尝试写入 `0x00a00030`，但没有改变 40 GiB 折叠结果。字段布局**尚未文档化** | [80 GB 问题](../frontier/80gb.md) |
| `0x0017e22c` | L2/LTC 地址映射寄存器 | LTC | 原生值为 `0x00280404`；从未被任何代码编程，但 40 GB 配置仍然可用 | [L2 / LTC](../unlock/register-reference.md#l2-ltc) |
| `0x0017e2a0` / `0x0017e2a4` | 每个 LTC 的解码寄存器 | LTC | 净室 v8 工具曾针对它们进行探测；在 170HX 上 `DECODE_VAL` 始终为 `0x70000300`，原因仍未解释 | [80 GB 问题](../frontier/80gb.md) |
| `0x001fa7c4` | `WPR_PLM` | WPR | WPR 区域寄存器的权限级别掩码。锁定值为 `0x0004cb8f`；**发布版 PLM 索引 2，已打开至 `0xffffffff`** | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x001fa7c8` | `MMU_LOCK` PLM | WPR | 写入半字节 `0x8` 表示仅限 L3/HS；值为 `0x0004cb8f`。本项目只读取它 | [WPR 模块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa7cc` | `WPR_CFG_PLM` | WPR | WPR 允许掩码的权限级别掩码。**发布版 PLM 索引 0，已打开至 `0xfffff0ff`，而不是 `0xffffffff`。** 这个例外确实存在，以补丁为准 | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x001fa814` | WPR 读允许掩码 | WPR | 模式字段位于 [7:4]；Booter 在掩码 `0x0ffff8ff` 下设置位 `0x800` | [WPR 模块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa818` | WPR 写允许掩码 | WPR | 同上 | [WPR 模块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa81c` / `0x001fa820` | `WPR1_ADDR_LO` / `HI` | WPR | WPR1 范围，值位于 [31:4]，再左移 12 位；由净室重新触发链清除 | [WPR 模块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x001fa824` | `WPR2_ADDR_LO` | WPR | **在 PLM 循环前保存，并在每次 Booter 尝试前重新设置**，否则第二次 `booter_load` 会以 “WPR2 already up”（状态 `0x62`）中止。空状态/INIT 读取为 `0x0fffffff` | [解锁如何工作](../unlock/how-it-works.md) |
| `0x001fa828` | `WPR2_ADDR_HI` | WPR | 同一组寄存器中的高位部分；`HI = 0` 会使 `kgspIsWpr2Up()` 返回 false。空状态/INIT 读取为 `0` | [解锁如何工作](../unlock/how-it-works.md) |
| `0x001fa82c` / `0x001fa830` | memlock 范围 LO / HI | WPR | AHESASC 之后（空状态）为 `0x1ffffff0` / `0x00000000`；只读 | [WPR 模块](../unlock/register-reference.md#wpr-block-0x001fa7xx-0x001fa8xx) |
| `0x00407000` | `SKED_HW_BLK` | SKED | 带驱动 `0x00004042`、不带 `0xbadf1201` | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407010` | `SKED_PM_UNK10` | SKED | 读取为 `0x00000000`；含义**尚未文档化** | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407020` | `SKED_TRAP` | SKED | 读 `0x00000000` | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407024` | `SKED_TRAP_EN` | SKED | `0x3dfffffc`、与 A100 相同 | [图形、SKED 与 FECS](../unlock/register-reference.md#graphics-sked-and-fecs-investigated-never-used) |
| `0x00407054` | `SKED_UNK54` | SKED | 驱动加载前为 `0x60000600` 或 `0x600000c0`，而在 A100 和 RTX 3090 上**为 0**。这是 GSP 固件中被引用最多的未文档化 SKED 寄存器。从未进行写入测试；功能**尚未文档化** | [未解问题](../frontier/open-questions.md) |
| `0x00408970` | `gpcMask` | GR | 某张卡上为 `0xdc`，每次强制尝试后都会重新断言。已确认是一条失败路线 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00409664` | `FECS_FEAT_OVERRIDE` | FECS | 在**每一颗**被探测的 Ampere 卡上返回 `0xbadf5040`、节流与否、所以该值不携带关于这张卡的任何信息 | [算力节流](../unlock/compute-throttle.md) |
| `0x00409668` | `FECS_FEAT_READOUT_1` | FECS | 相同、到处 `0xbadf5040` | [算力节流](../unlock/compute-throttle.md) |
| `0x00504204` | `SM_ISSUE_RATE_MODIFIER` | SM | **不是**算力节流：13 张对比 Ampere 卡和一颗每个速度选择熔丝都在 0 的 96-SM GA100 上读 `0x00000005`。主机可写；清零它什么都不改变。无驱动加载时 `0xbadf1201` | [算力节流](../unlock/compute-throttle.md) |
| `0x00820000` | `FUSE_FUSECTRL` | FUSE | 熔丝控制器、群组里全部 15 张卡上 `0xe0040000` 相同 | [熔丝与 OTP](../hardware/fuses-and-otp.md) |
| `0x00820040` | `FUSE_EN_SW_OVERRIDE` | FUSE | 170HX 和 A100 上 `0x00000000`、消费级和工程样品部件上 `0x00000001`。在 170HX 上可写且持久、却不会带来任何可观察的改变、这正是排除软件熔丝覆盖路线的原因 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820078` | `FUSE_EN_PROGRAM` | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x0082007c` | `FUSE_DIS_PROGRAM` | FUSE | `0x00000000`；GA10x 上 `0xbadf5040` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820080` | `FUSE_BYPASS_STATUS` | FUSE | `0x00000000`；GA10x 上 `0xbadf5040` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820084` | `FUSE_DIS_SW_OVR` | FUSE | 全部 15 张卡上 `0x00000001`；高安全写被弹回。软件熔丝覆盖被永久阻塞 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008200d0` .. `0x008200f4` | `OPTB_D0` .. `OPTB_F4` PLM | FUSE | 十个连续的权限级别掩码（`d0`、`d4`、`d8`、`dc`、`e0`、`e4`、`e8`、`ec`、`f0`、`f4`），全部由 Gen2 `xp3gTable` 写为 `0xffffffff`。`0x008200d0` 和 `0x008200dc` 读取时仍锁定为 `0xffffff8f`，其余八个读取时已打开。**每个掩码保护什么内容尚未文档化** | [OPTB PLM 模块](../unlock/register-reference.md#optb-plm-block-written-by-0007) |
| `0x008200fc` | `FUSE_SS_PLM` / `OPT_PLM` | FUSE | 一个寄存器有两个名称（`OPT_PLM` 是分支代码标签，`FUSE_SS_PLM` 是净室工具名称）。它保护速度选择熔丝模块和 `OPT_FB_CONFIG`。**发布版 `master` 从不写入它。** 一次扫描读到 `0xffffffff`，另一次读到 `0x000003ff`；它是否可写**仍是未解问题** | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00820148` | OTP 备用位 | FUSE | `0x00000000`，从未能够设置；用途**尚未文档化** | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820224` | `FUSE_SS_DP` | FUSE | 双精度速度选择熔丝、一个单独 1 位字段：170HX 上 `0x00000001`（降低） | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008202c4` | `OPT_ROP_L2_DISABLE` | FUSE | 镜像 `0x00820368` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820328` | `OPT_FB_CONFIG` | FUSE | 4 位显存拓扑选择器，由 PLM `0x008200fc` 保护。在 `probe.sh` 中有记录，但从未进行写入测试 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820340` | `OPT_MEMORY_LOCKED_ENABLED`（`FUSE_MEM_LOCKED`） | FUSE | 该组全部 15 张卡都是 `0x00000001`，表示显存配置名义上不能在运行时更改。但它不会阻止解锁，因为发布版链本来就会重写 CFG1 和 LMR | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820350` | `OPT_GPC_DISABLE` | FUSE | 每张卡的 GPC 禁用掩码：四张不同显卡分别为 `0x85`、`0x45`、`0x13`、`0xa8`。HS 写入会被弹回，数值已锁存 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820364` | `OPT_FBP_DISABLE` | FUSE | FBP 禁用掩码：10 GB 卡为 `0x00000840`（关闭 FBP 6 和 11），一份社区转储为 `0x00000852`，另外两个单元为 `0x00000009` 和 `0x00000180` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820368` | `OPT_FBPA_DISABLE` | FUSE | FBPA 禁用掩码：10 GB 卡为 `0x000000c3`（20 个活动实例），8 GB 卡为 `0x00c0330c`（16 个活动实例）。**决定 FBPA 数量的是它，而不是 CFG1** | [显存子系统](../hardware/memory-subsystem.md) |
| `0x0082036c` | `OPT_FBIO_DISABLE` | FUSE | 镜像 `0x00820368` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x0082038c` | `FUSE_QUADRO_WR_SEC` | FUSE | `0x00000001`；正是它允许 `0x00823804` 被完全打开 | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820394` | `OPT_PCIE_LANE_DISABLE` | FUSE | 170HX 和所有对照部件都是 `0x00000000`。**这证明 x4 位宽是板级电容问题，而不是熔丝造成的** | [PCIe 子系统](../hardware/pcie-subsystem.md) |
| `0x00820398` | `OPT_SPARE_FS` | FUSE | `0x00000000` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008203f0` | `FUSE_FEAT_OVR_DIS`（`OPT_FEATURE_FUSES_OVERRIDE_DISABLE`） | FUSE | **总控制熔丝，`0x00000000` 表示尚未烧断。正是这一个 0 让整个解锁机制成为可能** | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008203f4` | `OPT_INTERNAL_SKU` | FUSE | `0` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x0082049c` | `OPT_HALF_FBPA_ENABLE` | FUSE | 24 位的每 FBPA 半容量位掩码；非零表示容量减半。来自 `probe.sh` 记录 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x008204bc` | `OPT_SLT_REV` | FUSE | 硅片批次/测试修订、被 `ga100_topology_report.py` 读取 | [熔丝与 OTP](../hardware/fuses-and-otp.md) |
| `0x008204d8` | `OPT_PCIE_DEVIDA` | FUSE | SKU 身份熔丝：`0x000020c2`（8 GB）、`0x00002082`（10 GB）；A100 读 `0x20b2` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820520` | `FUSE_PCIE_MAGIC_D` | FUSE | 170HX 上为 `0x16680000`，位 25 已设置（`GEN4_SPEED_DISABLED`，NVIDIA bug 2220334）；A100 和 Drive GA100 上为 `0x00200000`。**它是否可写仍是未解问题** | [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md) |
| `0x0082056c` | `OPT_PCIE_DEVIDB` | FUSE | 两块实体 10 GB 单元都是 `0x000020c2`，因此 10 GB 卡上的 DEVIDA 与 DEVIDB 不一致。8 GB 的值**存在争议**：2026-07-19 对一张 `0x20c2` 卡进行的一次探测读到 `0x000020c2`，但在全部 11 个有数据的部件上成立的 `DEVIDB = DEVIDA + 0x40` 规则推算值为 `0x00002102` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x0082057c` | `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | FUSE | 两个 170HX SKU 都是 `0x00000001`，其他 14 个 Ampere 部件都是 `0x00000000`。**硬件只读**：从主机、HS ROP 和 Booter 载荷发起的尝试都始终读回 `0x00000001`。但 Gen2 仍然可用 | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820580` | `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | FUSE | 两个 170HX SKU 上 `0x00000001` | [Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md) |
| `0x00820584` | `FUSE_DEVID_SW_OVR_DIS` | FUSE | 170HX 和每个对比部件上 `0x00000001` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x0082059c` | `FUSE_SS_FFMA` | FUSE | 融合乘加速度选择、170HX 上 `0x00000005`（除以 32） | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008205c4` | `OPT_GPC_DEFECTIVE` | FUSE | 几张卡的 DISABLE 掩码设有 3 个位时读为 `0x00000000`，一张 10 GB 卡读为 `0x81`。“Disabled”和“defective”是两个独立的掩码 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008205cc` | `OPT_FBP_DEFECTIVE` | FUSE | 10 GB 卡为 `0x00000840`，恰好与 `OPT_FBP_DISABLE` 相同，因此该单元没有“禁用但仍正常”的 FBP | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008205d0` / `0x008205d4` / `0x008205e8` | `OPT_FBPA_DEFECTIVE` / `FBIO_DEFECTIVE` / `ROP_L2_DEFECTIVE` | FUSE | 各自都是 `0x00c03000` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820618` | `FUSE_FBPA_MEM_WR_SEC`（`OPT_SECURE_FBPA_MEM_WR_SECURE`） | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00820670` | `OPT_FB_FALCON_PRI_ACCESS_DISABLE` | FUSE | `0x00000000`，意味着**某个 Falcon 仍保留对 FB 寄存器的 PRI 访问权限**。SEC2 Booter 的 ROP 链正是依赖这一点 | [ROP 链](../unlock/rop-chain.md) |
| `0x00820684` | `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | FUSE | `0x00000007`、[2:0] 全部三位设置、对比 A100 和大多数消费级部件上 `0x00000000` | [NVLink](../frontier/nvlink.md) |
| `0x0082074c` | `FUSE_OPT_SECURE_GSP` | FUSE | 全部 15 张卡上 `0x00000001` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x008207d4` | `FUSE_SS_FMLA16` | FUSE | 170HX 上 `0x00000005`、每个未节流 Ampere 部件上 `0x00000000` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207d8` | `FUSE_SS_FMLA32` | FUSE | `0x00000005`；一张 RTX 3070 读 1 | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207dc` | `FUSE_SS_IMLA0` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e0` | `FUSE_SS_IMLA1` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e4` | `FUSE_SS_IMLA2` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207e8` | `FUSE_SS_IMLA3` | FUSE | `0x00000005` | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x008207ec` | `FUSE_SS_IMLA4` | FUSE | `0x00000005`；一张 RTX 3070 读到 1。解锁后，全部九个速度选择熔丝仍为 `0x5`，因为覆盖值取代了它们 | [SM 速度选择熔丝](../unlock/register-reference.md#sm-speed-select-fuses-the-throttle-itself) |
| `0x00820800` | `CTRL_OPT_HALF_FBPA` | FUSE | 半容量熔丝的合并覆盖状态、来自 `probe.sh` 目录 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820818` | `CTRL_OPT_FBPA` | FUSE | `0x00000000`，不存在覆盖 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820820` | `CTRL_OPT_PERLINK` | FUSE | 每-NVLink 覆盖影子；从没写测试过 | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x0082082c` | `CTRL_OPT_PCIE_LANE` | FUSE | `0x00000000` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820834` | `CTRL_OPT_FB_CONFIG` | FUSE | `OPT_FB_CONFIG` 的合并覆盖状态 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820838 + i*4` | `FUSE_CTRL_OPT_TPC_GPC(i)` | FUSE | 每个 GPC 的 TPC 覆盖，`0x00000000`。**仅能移除（减性操作）**：写入它从不会重新启用 TPC | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820840` | MIG 使能 | FUSE | 出厂值为 `0`；据一份报告，设置位 0 可启用并持久保留 MIG。**目前只有这一份报告，而且仓库级 grep 查找 `0x820840` 没有结果** | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820938` | `CTRL_OPT_FBP` | FUSE | `0x00000000` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x008209b8` | `CTRL_OPT_NVLINK` | FUSE | 位 [15:0]，每链路一个；每张受探测显卡都读取为 `0x00000000` | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x00820c00` | `STATUS_HALF_FBPA` | FUSE | `0`，因此没有需要恢复的半容量熔丝 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c14` | `STATUS_OPT_FBIO` | FUSE | 8 GB 卡上为 `0x00c0330c`。**这是 FBIO，不是 FBPA** | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c18` | `STATUS_OPT_FBPA` | FUSE | `0x00c0330c` / `0x000000c3`。这是 FBPA 状态影子的正确地址 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c1c` | `STATUS_OPT_GPC` | FUSE | 始终镜像 `0x00820350` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c2c` | `STATUS_OPT_PCIE_LANE` | FUSE | `0x00000000` | [PCIe 熔丝](../unlock/register-reference.md#pcie-fuses) |
| `0x00820c30` | `STATUS_OPT_SPARE_FS` | FUSE | `OPT_SPARE_FS` 的只读镜像 | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820c34` | `STATUS_OPT_FB_CONFIG` | FUSE | `OPT_FB_CONFIG` 的只读镜像 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x00820c38 + i*4` | `FUSE_STATUS_OPT_TPC_GPC(i)` | FUSE | 每个 GPC 的 TPC 状态；某张卡上 GPC0/3/5 读取为 `0xff`，其余读取为 `0x01` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820d38` | `STATUS_FBP` | FUSE | 某个单元上为 `0x00000180` | [熔丝裁剪](../unlock/register-reference.md#floorsweep-fuses) |
| `0x00820db8` | `STATUS_OPT_NVLINK` | FUSE | `0x00000007`、`0x00820684` 的只读镜像；与 Drive A100 共享 | [NVLink 熔丝](../unlock/register-reference.md#nvlink-fuses) |
| `0x00821060` | `OPT_SKU_ID` | FUSE | 8 GB 卡（`0x20C2`）上 `0x00000080`；10 GB 卡（`0x2082`）上 `0x00000068` | [熔丝控制](../unlock/register-reference.md#fuse-control) |
| `0x00823800` | `FEAT_OVR_ECC_PLM` | FEAT_OVR | 权限级别掩码，出厂值为 `0xffffff8f`。**这是与 `0x00823804` 不同的寄存器**，经常有人抄错。由 Gen2 `xp3gTable` 打开，`master` 从不打开它 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823804` | `FEAT_OVR_PLM` | FEAT_OVR | **控制 SS0/SS1 的权限级别掩码。** 出厂值为 `0xffffff8f`，发布版 PLM 索引 3，已打开至 `0xffffffff`。它是常电域中唯一的条目，因此**在 FLR 后仍然保留** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823808` | `FEAT_OVR_QUADRO` | FEAT_OVR | **按晶片变化，含义尚未解释。** 观测值包括：`0x00100183`（出厂状态、PLM 范围扫描，中等）、`0x00000081`（解锁后探测，中等）、`0x00000181` / `0x00000182`（两块实体 170HX，高置信度，13 项分级差异之一）、`0x01000282`（A100 80 GB）。只读。**未解问题：** 为什么三份转储中的值都不同。解锁流程或驱动可能正在修改 Quadro 与消费级分类字，而它也许正是控制驱动可见特性类别的调节项。下一步是在一张卡上，于发布版序列的每个阶段前后重新读取该寄存器 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x0082380c` | `FEAT_OVR_ECC` | FEAT_OVR | `0x00888888`；只读 | [ECC](../frontier/ecc.md) |
| `0x00823810` | `FEAT_OVR_ECC_1` | FEAT_OVR | `0x002aaaaa`；只读 | [ECC](../frontier/ecc.md) |
| `0x00823814` | `FEAT_READOUT_0` | FEAT_OVR | 170HX 上只读为 `0x00000233`；一块参考 GA100 板读取为 `0xef8ff100`。**字段布局尚未文档化** | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823818` | `FEAT_READOUT_1` | FEAT_OVR | 节流状态为 `0x016db6ed`，**解锁状态为 `0x00000000`。这是判断显卡是否解锁的最简洁单寄存器测试**，而且比回读 SS0 可靠得多 | [验证](../procedures/verify.md) |
| `0x0082381c` | `FEAT_OVR_SM_SPEED_SELECT`（SS0） | FEAT_OVR | **算力解锁写入 0。** 包含 8 个 4 位字段（IMLA0-3、FMLA16、FMLA32、FFMA、DP），写入 `0x88888888` 表示启用覆盖并使用全速。出厂值因卡而异。**FLR 后仍然保留** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823820` | `FEAT_OVR_SM_SPEED_SELECT_1`（SS1） | FEAT_OVR | **算力解锁写入 1。** 第九个字段是 IMLA4，写入 `0x00000008`。两个寄存器都必须写入。**FLR 后仍然保留** | [算力节流](../unlock/compute-throttle.md) |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` | FEAT_OVR | 两个 170HX SKU 上 `0x00000000`；只读 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823828` | `FEAT_READOUT_2` | FEAT_OVR | 170HX 上 `0x00000000`、全部 A100 和 Drive 部件上 `0x00000007`；只读 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x0082382c` | `FEAT_READOUT_2`（一份转储中的别名） | FEAT_OVR | `0x0000000a`。**两份转储对命名尚未达成一致**，字段布局也尚未文档化 | [特性覆盖](../unlock/register-reference.md#feature-override-and-compute-0x008238xx) |
| `0x00823b00` | 行重映射器 PLM（`FEAT2`） | FEAT_OVR | 出厂值为 `0xffffff8f`，仅由 Gen2 系列补丁打开至 `0xffffffff`。一次 HS 内扫描在 FLR 后读取到它处于打开状态，因此它可能属于常电域，但打开它**不会**让显存几何布局持久保留 | [Gen2 PLM 表](../unlock/register-reference.md#added-by-the-gen2-family-branches-nine-entries-total) |
| `0x00830040` | NVDEC `MAILBOX0` | NVDEC | 从 PL0 访问时被阻挡且只读，读取为 `0xbadf1100` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840040` | SEC2 `FALCON_MAILBOX0` | SEC2 | **这是 `s_executeBooter` 实际读取的邮箱。** 每次携带载荷运行都读取到 `0x31`；这是驱动在原始退出路径上写入、之后未被改动的参数，不是 Booter 错误码。只有寄存器回读结果可以作为有效判定 | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840044` | SEC2 `FALCON_MAILBOX1` | SEC2 | 第二个邮箱；从 PL0 访问时被阻挡且只读 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084007c` | `SFTRESET` | SEC2 | 软复位：写入 1 后读回；只有 `SCTL` 的 HSMODE（位 1）已设置时才有效 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840084` | `FALCON_RM` | SEC2 | 资源管理器临时区 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008400f4` | `FALCON_HWCFG2` | SEC2 | 位 10 = RISCV、读 **0**、确认 SEC2 是一颗 Falcon v4 核心而非 RISC-V | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840100` | `FALCON_CPUCTL` | SEC2 | 位 1 = STARTCPU 脉冲、位 4 = HALTED（只读） | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840104` | `FALCON_BOOTVEC` | SEC2 | 引导向量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084010c` | `FALCON_DMACTL` | SEC2 | 轮询直到清理位 `0x6` 清零；读取为 `0xffffffff` 表示窗口尚未响应，不表示失败 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840110` | `FALCON_DMATRFBASE` | SEC2 | DMA 基址 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840114` | `FALCON_DMATRFMOFFS` | SEC2 | DMEM/IMEM 偏移量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840118` | `FALCON_DMATRFCMD` | SEC2 | DMA 命令 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x0084011c` | `FALCON_DMATRFFBOFFS` | SEC2 | 帧缓冲偏移量 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840128` | `FALCON_DMATRFBASE1` | SEC2 | DMA 基址高 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840180` / `0x00840184` | `IMEMC` / `IMEMD` | SEC2 | IMEM 端口对，自动递增，每 256 字节带标签；安全标签位为 `1 << 28`。用于读回已加载 Booter 的 `0` 到 `0x8700` 范围 | [ROP 链](../unlock/rop-chain.md) |
| `0x00840240` | `SCTL` | SEC2 | 安全控制；HSMODE = 位 1、`AUTH_EN` = `1 << 14`。一次引擎复位后观察到 `0x3000` 到 `0x3002` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x00840284` | SEC2 `DMEM_PLM` | SEC2 | DMEM 权限掩码；LS 模式下 `0xff`（完全打开） | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008403c0` | `FALCON_ENGINE` | SEC2 | 位 0 = RESET；脉冲 1 然后 0。引擎复位门是 `(resetPLM & 0x77) == 0x77` | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008403c4` | SEC2 复位 PLM | SEC2 | **决定 SEC2 是否还能再次复位；每个净室触发工具都会把它读取为就绪门。** 干净状态为 `0xff`，成功执行一次 `booter_unload` 后为 `0xdf`，执行 `secure_teardown` 后为 `0x8f`（此时会阻挡 `SFTRESET`）。`reset_allowed = {0xff, 0xdf}`。**FLR 会将其清为 `0xff`** | [恢复](../procedures/recovery.md) |
| `0x00840480` / `0x00840484` | SEC2 触发后状态 | SEC2 | 作为退出 HS 的副作用，分别从 `0` 变为 `0x1` 和从 `0` 变为 `0x11100`，之后不再恢复。字段布局**尚未文档化** | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00840530` | `SCP_P2PRX` | SEC2 | 免驱动复位期间轮询位 3 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x008411ec` | `KFUSE_CTL` | SEC2 | 轮询位 0 设置、位 1 清除 | [SEC2 Falcon](../unlock/register-reference.md#sec2-falcon-bar0-0x840000) |
| `0x00900200 + n*0x4000` | 每个 FBPA 的 `CFG0` | FBPA | CFG0 寄存器的单播实例 *n*（n = 0..23）；两个 SKU 的每个活动实例都是 `0x07981800` | [每个 FBPA 的孔径](../unlock/register-reference.md#per-fbpa-unicast-aperture) |
| `0x00900204 + n*0x4000` | 每个 FBPA 的 `CFG1` | FBPA | 单播寻址深度寄存器。**发布版驱动从不写它**；驱动路径只需向 `0x009a0204` 执行一次广播写入。在没有 devinit 的免驱动运行时，必须手工写入全部 24 个实例 | [每个 FBPA 的孔径](../unlock/register-reference.md#per-fbpa-unicast-aperture) |
| `0x0090020c + n*0x4000` | 每个 FBPA 的 `CSTATUS_RAMAMOUNT` | FBPA | **验证目标**：出厂值 `0x200`（每个 FBPA 512 MiB），40 GB 档位为 `0x800`，64 GB 档位为 `0x1000`。被熔丝裁剪的 FBPA 会返回 `0xbadf20xx` 哨兵值 | [验证](../procedures/verify.md) |
| `0x009a0008` | FB 几何 PLM | FBPA | 锁定值为 `0xffffff8f`，属于净室 `FB_GEO_PLMS` 列表。它具体保护什么内容**尚未文档化** | [FB 几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a000c` | FB 几何 PLM | FBPA | 同上 | [FB 几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a0040` | FBFLCN `MAILBOX0` | FBPA | FB Falcon 邮箱；从 PL0 访问时被阻挡且只读，读取为 `0x00003fff` | [Falcon 与 Booter](../unlock/falcon-and-booter.md) |
| `0x009a0148` | **FBPA PLM** | FBPA | 控制 CFG1 的权限级别掩码。出厂值为 `0xffffff8f`，**发布版 PLM 索引 1，已打开至 `0xffffffff`**。当 `dmem.bin` 缺失时，它也是内置回退载荷的目标 | [PLM 表](../unlock/register-reference.md#written-by-shipping-master-four-entries-in-this-order-up-to-two-attempts-each) |
| `0x009a014c` | FB-几何 PLM | FBPA | `0xffffff8f`；只净室列表 | [FB-几何 PLM 集](../unlock/register-reference.md#the-fb-geometry-plm-set-clean-room-tools-only) |
| `0x009a0164` | `FBPA_NUM_ACTIVE`（`NUM_ACTIVE_FBPS`） | FBPA | 8 GB 卡上 `0x00000008` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0168` | PLM 候选 | FBPA | 读取为 `0xffffffcf`；只出现在 26 项寄存器调查中，它保护什么内容**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0200` | `FBPA_CFG0_BROADCAST` | FBPA | 170HX 和 A100 40/80 GB 上 `0x07981800`；一颗参考 GA100 Drive 部件上 `0x06981800` | [FBPA 孔径](../unlock/register-reference.md#fbpa-broadcast-aperture-0x009a0000-to-0x009a3fff) |
| `0x009a0204` | `NV_PFB_FBPA_CFG1`（广播） | FBPA | **每个显存分区的寻址深度，也是档案中被引用最多的寄存器。** 两个 SKU 的出厂值都是 `0x02449000`，解锁值为 `0x02779000`（64 GB）/ `0x02669000`（40 GB）。档位字节位于 [23:16]：`0x44` / `0x66` / `0x77`。**FLR 后不会保留** | [显存几何布局](../unlock/memory-geometry.md) |
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
| `0x009a03f0` | PLM 候选 | FBPA | `0xffffff8f`；仅用于调查，它保护什么内容**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0470` | `FBPA_ECC_CTRL` | FBPA | 读取为 `0`，且 `MASTER_EN` 只读。ECC 已由熔丝关闭，没有已知的调节手段 | [ECC](../frontier/ecc.md) |
| `0x009a0554` | PLM 候选 | FBPA | `0xffffffcf`；仅用于调查，**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a0838` / `0x009a083c` | `FBPA_VEND_ID_C0` / `C1` | FBPA | 全部 15 张卡上 `0x00000000`、所以 HBM 厂商 ID 不在这里暴露 | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a0974` | `FBPA_TRAINING_STATUS` | FBPA | `0x00000000` = FINISHED。SUBP0 在 [1:0]、SUBP1 在 [3:2]；值 2 意味着 ERROR | [排障](../procedures/troubleshooting.md) |
| `0x009a0bfc` | PLM 候选 | FBPA | 读取为 `0x00000000`；仅用于调查，**尚未文档化** | [26 项寄存器 PLM 调查](../unlock/register-reference.md#the-26-register-plm-survey) |
| `0x009a3cb4` / `0x009a3cb8` / `0x009a3cbc` | `I1500_INSTR` / `MODE` / `DATA` | FBPA | IEEE 1500 HBM 测试端口；`0x0000000f` / `0x00000008` / `0x40000000` | [显存子系统](../hardware/memory-subsystem.md) |
| `0x009a3cc0` / `0x009a3cc4` / `0x009a3cc8` | `I1500_SHADOW_WIR` / `WDR` / `STATUS` | FBPA | `0x000000f0` 只读 / 按晶片 / `0x00000000` 空闲。`WDR` 在 8 GB 卡上读 `0x8000f000`、10 GB 卡上 `0x8273ff83` | [显存子系统](../hardware/memory-subsystem.md) |

> [!NOTE]
> **看起来相邻、实际上无关的寄存器**
>
> `0x00823800` 和 `0x00823804` 只相隔 4 个字节，作用却完全不同：`0x00823800` 是 `FEAT_OVR_ECC_PLM`，`0x00823804` 是控制算力解锁的 `FEAT_OVR_PLM`。同样，`0x00820c14` 是 FBIO 状态，`0x00820c18` 是 FBPA 状态。这两对地址都曾在流传的笔记中被写反。

---

## 载荷偏移量

这些**不是 BAR0 地址。** 它们是字节偏移量，指向驱动交给 Booter 的 `0x0000f800` 字节（63,488 字节）假签名缓冲区；Booter 会将该缓冲区 DMA 到 SEC2 DMEM `0x0800`。因此：

> [!NOTE]
> **换算规则**
>
> **DMEM 地址 = 载荷偏移量 + `0x800`。** 缓冲区与 DMEM 的 `0x0800`..`0xffff` 范围一一对应，因为 `0x0800 + 0xf800 = 0x10000`，正好到达 64 KB DMEM 的顶部。

整个缓冲区先填入 dword `0x000004a7`，然后恰好覆盖 24 个槽位。下表中的每个值都直接取自 `0001-sec2-postbl-plm-ss-cfg.patch` 中的 `_kgspSec2PostblTimingFillPayload()`；这张表在**发布版 `master` 及全部 12 个归档分支中逐字节相同**。其中两个槽位是参数：目标写入地址和要写入的值。其余内容全部属于 ROP 尾部。

| 载荷偏移量 | DMEM 地址 | 值 | 角色 |
|---|---|---|---|
| （全部） | `0x0800`-`0xffff` | `0x000004a7` | 背景填充 dword；为什么使用这个常量**尚未文档化** |
| `0x1100` | `0x1900` | `0x00000007` | **尚未文档化** |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **写入栈保护全局变量的伪造金丝雀。** 关键事实是地址 `0x6340`；只要与每个保存副本一致，具体数值可以任意 |
| `0xf754` | `0xff54` | *writeValue* | 值参数，尾部最低槽位 |
| `0xf758` | `0xff58` | `0xc0deca7e` | 保存的金丝雀槽位 |
| `0xf75c` | `0xff5c` | `0x00000cbd` | Falcon IMEM 地址；作用**尚未文档化** |
| `0xf76c` | `0xff6c` | *writeAddr* | BAR0 地址参数 |
| `0xf774` | `0xff74` | `0x00001fbd` | “elevator” gadget 家族中的 IMEM 地址 |
| `0xf780` | `0xff80` | `0x00000000` | **尚未文档化** |
| `0xf788` | `0xff88` | `0x000010aa` | **BAR0 主控写入 gadget，`reg_write_indirect`。** 正是这个槽位让整个利用获得写入原语 |
| `0xf78c` | `0xff8c` | `0x0000815a` | IMEM 地址；作用**尚未文档化** |
| `0xf790` | `0xff90` | `0x00008e18` | IMEM 地址；作用**尚未文档化** |
| `0xf794` | `0xff94` | `0xc0deca7e` | 保存的金丝雀槽位 |
| `0xf798` | `0xff98` | `0x0000815a` | 同一 IMEM 地址的第二份副本 |
| `0xf79c` | `0xff9c` | `0x00000000` | **尚未文档化** |
| `0xf7a0` | `0xffa0` | `0xc0deca7e` | 保存的金丝雀槽位 |
| `0xf7a4` | `0xffa4` | `0x00001fbd` | 第二份副本 |
| `0xf7b0` | `0xffb0` | `0x0000ffbc` | IMEM 地址；作用**尚未文档化** |
| `0xf7b8` | `0xffb8` | `0x0000582d` | IMEM 地址；作用**尚未文档化** |
| `0xf7c4` | `0xffc4` | `0xc0deca7e` | 保存的金丝雀槽位 |
| `0xf7c8` | `0xffc8` | `0x00000cbd` | 第二份副本 |
| `0xf7d8` | `0xffd8` | `0x00000003` | **尚未文档化** |
| `0xf7e0` | `0xffe0` | `0x00001fbd` | 第三份副本 |
| `0xf7f4` | `0xfff4` | `0x00000ccb` | `regtable_rw_indexed`，也是一个未解问题：它索引的正是被载荷破坏的描述符表，但解锁仍然有效 |
| `0xf7f8` | `0xfff8` | `0x00007f2f` | 最外层槽位；作用**尚未文档化** |

金丝雀 `0xc0deca7e` 在每份副本中恰好出现五次：一次位于 `0x5b40`，另外四次位于载荷偏移量 `0xf758`、`0xf794`、`0xf7a0`、`0xf7c4`。

> [!NOTE]
> **未解问题：无法解释的载荷常量**
>
> 24 个槽位中有 15 个尚未确认用途，合计包含 10 种不同的常量。ROP 分析文档列出了一个相邻的 gadget 家族（`0x1fb9`、`0x1fca`、`0x814e`、`0x8173`、`0x7f82`），因此这些常量很可能是同一段尾部平移后的结果，但尚无人通过带注释的反汇编加以确认。参见[ROP 链](../unlock/rop-chain.md)和[未解问题](../frontier/open-questions.md)。

### 载荷引用的关键 DMEM 地址

这些地址与上表的 DMEM 地址列属于同一地址空间；这里按 DMEM 地址列出，因为反汇编就是这样引用它们的。

| DMEM 地址 | 含义 |
|---|---|
| `0x0100` 及以下 | 此处没有分配任何内容，这正是“在低位 DMEM 中分阶段放置 mega-ROP”这一设想被否定的原因 |
| `0x0530` | DMA 和引擎配置描述符 |
| `0x0600` | `WprMeta`、一个 256 字节结构 |
| `0x06fc` | Booter 在 `r4 == 0` 分支中存放 `0xa0a0a0a0` 的位置。**与 `0x001fa824` / `0x001fa828` 这两个 WPR2 寄存器无关**，尽管数字恰好相似 |
| `0x0800` | DMA 签名缓冲区的基址，即载荷偏移量 0 |
| `0x103c` 起 | 加密会话描述符 |
| `0x2383` 和 `0x8e08` | 寄存器描述符表，会被载荷线性覆盖 |
| `0x6340` | 栈金丝雀全局、25408 十进制 |
| `0x8700` | Booter 代码和数据的末尾 |
| `0xffec` | 提供给 `main` 的退出状态槽，用于决定是否执行 `secure_teardown` |

### 跨变体的载荷大小和金丝雀

| 变体 | 缓冲区大小 | DMA 基址 | 金丝雀值 |
|---|---|---|---|
| 已发布的 `master` 和全部 12 个分支 | `0x0000f800` = 63,488 B | `0x0800` | `0xc0deca7e` |
| 净室 ROP 写稿 | `0x0000f800` | `0x0800` | `0xfaceb13d` |
| 被取代的 `builder.py` / `patcher.py` | `0x0000f700` = 63,232 B | `0x0900` | `0xdead2c20` 位于 `0x2c20` |

被取代工具使用的 DMA 基址 `0x0900`，正是某条归档消息将金丝雀地址写成 `0x6440` 的原因：`0x5b40 + 0x900 = 0x6440`。发布版路径使用基址 `0x0800`，因此金丝雀位于 `0x6340`。

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
