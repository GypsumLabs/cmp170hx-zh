# 寄存器参考

## 本页覆盖内容

NVIDIA CMP 170HX（GA100）上，本项目里任何人读、写或争论过的每一个硬件寄存器，按功能块组织，带它的地址、名称、作用、出厂值、存在的话解锁后的值、是否有[权限级别掩码](privilege-level-masks.md)门控主机写入、其内容是否挺过功能级复位（FLR），以及哪个补丁或工具碰它。

本页唯一最重要的一个事实：**出货解锁整体是四个权限级别掩码打开，接四次普通主机寄存器写。** 这里其它一切都是上下文、诊断或未发布的工作。

| 步骤 | 地址 | 写入的值 | 机制 |
|---|---|---|---|
| PLM 打开 0 | `0x001fa7cc` | `0xfffff0ff` | Booter Load 重发 |
| PLM 打开 1 | `0x009a0148` | `0xffffffff` | Booter Load 重发 |
| PLM 打开 2 | `0x001fa7c4` | `0xffffffff` | Booter Load 重发 |
| PLM 打开 3 | `0x00823804` | `0xffffffff` | Booter Load 重发 |
| 解锁写 0 | `0x0082381c` | `0x88888888` | 普通主机 `GPU_REG_WR32` |
| 解锁写 1 | `0x00823820` | `0x00000008` | 普通主机 `GPU_REG_WR32` |
| 解锁写 2 | `0x009a0204` | `0x02779000`（8 GB 卡）/ `0x02669000`（10 GB 卡） | 普通主机 `GPU_REG_WR32` |
| 解锁写 3 | `0x00100ce0` | `0x0000020B`（8 GB 卡）/ `0x0000028A`（10 GB 卡） | 普通主机 `GPU_REG_WR32` |

上面的一切都直接读自出货 `master` 上的 `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`。叙述版见[解锁如何工作](how-it-works.md)，逐补丁分解见[驱动补丁](driver-patches.md)。

---

## 阅读约定

### 地址对值

这是档案里最常见的混淆来源，所以它有自己的规则：**`Address` 列里的一切都是 BAR0 字节偏移量；`Value` 列里的一切都是 32 位数据。** 几个解锁值本身就是看似合理的地址，而几个载荷槽含有完全不是 BAR0 寄存器的 Falcon IMEM 地址。页面底部[不是 BAR0 地址的数字](#数字不是-bar0-地址)一节列出每一处这种陷阱。

本页所有 BAR0 偏移量都是相对 BAR0 起点（区域 0）的绝对值。手工读一个：

```bash
# GPU 0000:05:00.0 上的 BAR0 偏移量 0x009a0204
sudo dd if=/sys/bus/pci/devices/0000:05:00.0/resource0 \
        bs=4 count=1 skip=$((0x009a0204 / 4)) 2>/dev/null | xxd -e -g4
```

### 列含义

- **PLM-gated**：对某寄存器的 PL0（普通主机）写，是否被静默丢弃，直到权限级别掩码从重度安全（HS）Falcon 上下文被打开。"静默"是字面意思：一条早期流水线记录了 `Write failed - wrote 0x2779000, read 0x2449000` 三次，却没有任何地方报告错误。
- **FLR**：该值是否挺过 `echo 1 > /sys/bus/pci/devices/<bdf>/reset`。整张寄存器图里只有三个寄存器已知能挺过，而这种不对称正是算力解锁比显存解锁早数周出货的原因。
- **Touched by**：出货补丁、未发布分支补丁或净室工具。"read only"（只读）意思是项目里有东西为诊断读它，却没有任何东西写它。

### 哨兵值

读回下面其中一个不是数据：

| 哨兵 | 含义 |
|---|---|
| `0xbadf0000`（与 `0xffff0000` 掩码） | 通用 PRI 毒值，被 Booter 自己的 `csb_read` 检测 |
| `0xbadf1100` | PRI 毒值，在 SEC2 注入点看到的 `0x85080` / `0x85084`、以及 `0x00021c14` / `0x0000a800`（GA100 上缺失的寄存器） |
| `0xbadf1201` | 没加载驱动时 `0x00504204` 和整个 `0x00407xxx` SKED 块返回 |
| `0xbadf2010`、`0xbadf2011`、`0xbadf2013`、`0xbadf2017`、`0xbadf2018` | 被地板清扫（禁用）FBPA 的 CSTATUS 读 |
| `0xbadf5040` | 权限违规哨兵；`0x00409664` / `0x00409668` 在每一张被探测的 Ampere 卡上都返回它，XVE 影子对非特权读者返回它 |
| `0xbadf5108` | 对一个安全 PLM 的主机 PL0 读 |
| `0xdead5ec1` | 对 `0x001180f8` 的 PLM-毒化读；注意这种模式里位 26 已读作 1、产生一个假 BOOT_STAGE_3 "DONE" |
| 整个孔径上的 `0xffffffff` | BAR0 映射死了（卡掉下总线），不是一个解锁的 PLM |

---

## SEC2 Falcon（BAR0 + `0x840000`）

SEC2 是安全协处理器，其签名的 `booter_load` ucode 被利用劫持。它是一个 Falcon v4 核心，不是 RISC-V（`FALCON_HWCFG2` 位 10 读 0）。见[Falcon 与 Booter](falcon-and-booter.md)。

| 地址 | 名称 | 功能 | 备注 |
|---|---|---|---|
| `0x00840040` | `FALCON_MAILBOX0` | Booter 运行后的状态字 | 每次带载荷的运行上 `0x31`；目标寄存器的回读是唯一有效判决 |
| `0x00840044` | `FALCON_MAILBOX1` | 第二个邮箱 | |
| `0x0084007c` | `SFTRESET` | 软复位；写 1 并回读 | 仅当 `SCTL` HSMODE（位 1）置位时 |
| `0x00840084` | `FALCON_RM` | Falcon 资源管理器临时区 | |
| `0x008400f4` | `FALCON_HWCFG2` | 位 10 = RISCV | 在 SEC2 上读 0（Falcon 核心） |
| `0x00840100` | `FALCON_CPUCTL` | 位 1 = STARTCPU 脉冲，位 4 = HALTED（只读） | |
| `0x00840104` | `FALCON_BOOTVEC` | 引导向量 | |
| `0x0084010c` | `FALCON_DMACTL` | 轮询直到清扫位 `0x6` 清除 | `0xffffffff` 读意味着窗口尚未响应、不是失败 |
| `0x00840110` | `FALCON_DMATRFBASE` | DMA 基址 | |
| `0x00840114` | `FALCON_DMATRFMOFFS` | DMEM/IMEM 偏移量 | |
| `0x00840118` | `FALCON_DMATRFCMD` | DMA 命令 | |
| `0x0084011c` | `FALCON_DMATRFFBOFFS` | FB 偏移量 | |
| `0x00840128` | `FALCON_DMATRFBASE1` | DMA 基址高位 | |
| `0x00840180` / `0x00840184` | `IMEMC` / `IMEMD` | IMEM 端口、自动递增、每 256 字节标签 | 安全标签位是 `1 << 28`；用于把已加载的 booter 在 0..`0x8700` 范围读回 |
| `0x00840240` | `SCTL` | 安全控制；HSMODE = 位 1，`AUTH_EN` = `1 << 14` | 引擎复位后观察到 `0x3000` 到 `0x3002` |
| `0x00840284` | SEC2 `DMEM_PLM` | DMEM 权限掩码 | 轻度安全模式下 `0xff`（完全打开） |
| `0x008403c0` | `FALCON_ENGINE` | 位 0 = RESET；脉冲 1 然后 0 | 引擎复位门是 `(resetPLM & 0x77) == 0x77` |
| `0x008403c4` | **SEC2 复位 PLM** | 决定 SEC2 能否再次被复位 | `0xff` 干净，一次成功 `booter_unload` 后 `0xdf`，`secure_teardown` 后 `0x8f`（阻塞 SFTRESET）。`reset_allowed = {0xff, 0xdf}`。**被 FLR 清到 `0xff`。** 每个净室发射工具都把它当作就绪门读 |
| `0x00840480` / `0x00840484` | SEC2 发射后状态 | `0` 到 `0x1` 和 `0` 到 `0x11100` | HS-退出副作用，从不恢复 |
| `0x00840530` | `SCP_P2PRX` | 无驱动复位期间轮询位 3 | |
| `0x008411ec` | `KFUSE_CTL` | 轮询位 0 置位、位 1 清除 | |

> [!NOTE]
> **Falcon 内部地址是另一个空间**
>
> 在运行中的 Booter 内部，`I[0x1c100]` / `I[0x1c200]` / `I[0x1c000]` 是 Falcon CSB 空间里的 BAR0-master 地址、数据和命令端口（`0x800000f2` = 写、`0x800000f1` = 读），而 `I[0x1c300]` 是用 `0x1312d00`（20,000,000）播种的看门狗。`I[0x12000]`、`I[0x12100]`、`I[0x12400]` 和 `I[0x12600]` 是 Booter 在 `main()` 早期编程的 Falcon 本地孔径/PLM 字。这些都不是 BAR0 偏移量，也都不能从主机 poked。同样，`0x9100` 是 `FALCON_CSBERRSTAT`，其位 31 是每次 CSB 访问后的 fail-closed 故障标志。见[ROP 链](rop-chain.md)。

## GSP RISC-V 与 BSI 安全临时区（BAR0 + `0x110000` / `0x118000`）

| 地址 | 名称 | 功能 | 备注 |
|---|---|---|---|
| `0x00110624` | GSP `FBIF_CTL` | 孔径控制 | Booter `reg_init (0x68ed)` 写 `0x90`（`ALLOW_PHYS_NO_CTX` 位 7 加位 4） |
| `0x00110684` | GSP FBIF 伴生 | | 被 `reg_init` 写 `1` |
| `0x0011126c` | GSP RISC-V 伴生 | | 被 `reg_init` 写 `1` |
| `0x00111240` | `RISCV_STATUS` | GSP 核心状态 | `0x35` = RISC-V 活跃；`0x0` = 从未启动 |
| `0x00111268` | `RISCV_CPUCTL` | GSP 核心控制 | |
| `0x00118244` / `0x00118248` | WPR 分阶段对 | 被 `booter_load_wpr_main (0x22ba)` 读然后清零 | |
| `0x0011824c` / `0x00118250` | memcfg 交接 | 被 `memcfg_program (0x79cc)` 写；`memcfg_apply_poll` 只在 `0x11824c` 位 0 置位时运行 | |
| `0x001180f0` | AON LMR 影子 | 显存范围值的常电影子 | **在 FLR 时回退**；不是持久杠杆 |
| `0x001180f8` | `NV_PGC6_BSI_SECURE_SCRATCH_14` | 位 26 = `BOOT_STAGE_3_HANDOFF`（INIT 0，DONE 1） | 由 SEC2 在 HS 上下文里在 GPU 侧设置；主机驱动只轮询它。引导挂起 `0x65` 就是那次轮询超时。Booter 自己的入口检查要求位 [31:28] == 0（否则错误 `0x29`）且位 [27:24] == 0（否则 `0x88`）。**出货链从不写这个寄存器。** |
| `0x001182d0` | AON 安全临时区 | | 在 PL3 可达 |
| `0x00118f78` | 辅助临时区 | | 每一张被调查的卡上都读 `0x00000000` |

> [!NOTE]
> **未解问题：正确的 `0x001180f8` 交接值**
>
> `0x11000000`、`0x13100000` 和 `0x17100000` 都被提出过。`0x17100000` 被测量同时满足 Booter 的 `0x29` 检查和主机 DONE 轮询，但写它也导致 `FBPA_008` 和 `FBPA_00C` 两者的 Booter PLM 打开失败。出货链通过从不碰该寄存器绕开整个问题。见[未解问题](../frontier/open-questions.md)。

## WPR 块（`0x001fa7xx` / `0x001fa8xx`）

写保护区域。解锁必须在每次 Booter 重发周围保存和恢复 WPR2，因为第二次 `booter_load` 否则会以 "WPR2 already up" 中止。

| 地址 | 名称 | 功能 | 出厂 | 被谁碰 |
|---|---|---|---|---|
| `0x001fa7c4` | `WPR_PLM` | WPR 区域寄存器上的权限掩码 | `0x0004cb8f` | 出货补丁 0001、PLM 索引 2、打开到 `0xffffffff` |
| `0x001fa7c8` | `MMU_LOCK` PLM | 写半字节 `0x8` = 仅 L3/HS | `0x0004cb8f` | 只读 |
| `0x001fa7cc` | `WPR_CFG_PLM`（WPR 掩码 PLM） | WPR 允许掩码上的权限掩码 | `0x0004cb8f` | 出货补丁 0001、PLM 索引 0、打开到 **`0xfffff0ff`**、不是 `0xffffffff` |
| `0x001fa814` | WPR 读允许掩码 | 位 [7:4] 处的模式字段 | | Booter `fbif_set_bit800 (0x8307)` 在掩码 `0x0ffff8ff` 下设位 `0x800` |
| `0x001fa818` | WPR 写允许掩码 | 同上 | | 相同 |
| `0x001fa81c` | `WPR1_ADDR_LO` | 位 [31:4] 里的值，`<< 12` | | 被净室重发链清除 |
| `0x001fa820` | `WPR1_ADDR_HI` | | | 相同 |
| `0x001fa824` | `WPR2_ADDR_LO` | 位 [31:4] 里的值，`<< 12` | 空/INIT = `0x0fffffff` | **被出货补丁在每次 Booter 尝试前保存并重新武装**；净室 teardown 值是 `0x1ffffe00` |
| `0x001fa828` | `WPR2_ADDR_HI` | `HI = 0` 让 `kgspIsWpr2Up()` 返回 false | 空/INIT = `0` | 相同 |
| `0x001fa82c` / `0x001fa830` | memlock 范围 LO / HI | | AHESASC 后（空）`0x1ffffff0` / `0x00000000` | 只读 |

野外的实测 WPR2 值：一块 10 GB 卡上在 10 GB 对比 40 GB A/B 的两条腿里刻出 `0x02777000`；一次 40 GB 净室发射后 `[0x1ffffe00, 0x027fee00]`；一块 PG199 参考板上 `07f68000/07fefe00`。RM 每次引导在一个新鲜的 FB 地址重新分配 WPR2，这就是静态烘焙的 WprMeta 停在 `0xf0000000`（失败）、而活值给出 `0x11000000` 的原因。

---

## 权限级别掩码：完整目录

PLM 是一个 32 位字、由半字节编码的权限，守护另一个寄存器或寄存器组。`0xffffff8f` 是常见锁定态（写仅第 3 级）；`0xffffffff` 完全打开；`0x0004cb8f` 是 WPR 对的锁定态。编码见[权限级别掩码](privilege-level-masks.md)。

### 被出货 `master` 写（四条目、按此顺序、每个最多两次尝试）

| 索引 | 地址 | 代码里的标签 | 写入的值 | 备注 |
|---|---|---|---|---|
| 0 | `0x001fa7cc` | `WPR_CFG` | `0xfffff0ff` | 那个例外：**不是** `0xffffffff` |
| 1 | `0x009a0148` | `FBPA` | `0xffffffff` | 也是内置回退载荷目标 |
| 2 | `0x001fa7c4` | `WPR` | `0xffffffff` | |
| 3 | `0x00823804` | `FEAT` | `0xffffffff` | 唯一的 AON 条目；挺过 FLR |

每次尝试从循环前保存的值重新武装 `0x001fa824` / `0x001fa828`、为那一个（地址、值）对重新填满整个 `0xf800` 字节载荷、发射 Booter Load、并回读目标。成功纯由回读相等定义。来自一张 8 GB 卡上 2026-07-19 dmesg 捕获的时序：PLM[0] 在 11.32 s、PLM[1] 11.50 s、PLM[2] 11.68 s、PLM[3] 11.86 s，每次 Booter 趟约 180 ms。

### Gen2 家族分支添加的（总共九条目）

分支 `Gen2`、`debug-gen2`、`far` 和 `deced` 携带一个相同的修改版补丁 0001，其 `plmTable[]` 有九行、其循环边界是 `plmIdx < 9`。五条额外条目，全部写 `0xffffffff`：

| 地址 | 标签 | 目的 |
|---|---|---|
| `0x00088ff4` | `XVE` | XVE 配置空间影子 PLM；必需是因为否则对 PCIe 影子的主机读返回 `0xbadf5040` |
| `0x00088ab4` | `XVE_B` | 第二个 XVE 能力 PLM |
| `0x00088ff8` | `XVE_C` | 第三个 XVE 能力 PLM |
| `0x00823b00` | `FEAT2`（行重映射器 PLM） | 出厂 `0xffffff8f`；一次 in-HS 扫描在 FLR 后读它 `0xffffffff`，所以它可能常开，但打开它没让几何布局持久 |
| `0x008200fc` | `OPT_PLM`（别名：`FUSE_SS_PLM`） | 一次扫描里在出厂卡上已读 `0xffffffff`、另一次读 `0x000003ff`；**永不被出货 master 写** |

> [!WARNING]
> **实验性**
>
> 九条目表只存在于未发布分支上。全部九条都被报告在一台双卡机的两张 GPU 上第一次尝试成功。见[PCIe Gen2](pcie-gen2.md)。

### FB-几何 PLM 集（仅净室工具）

`refire_chain_v9.py` 用 `FB_GEO_PLMS = [0x00100b10, 0x009a0148, 0x009a014c, 0x009a0008, 0x009a000c]`。最早的 HS 配方用一个加 `0x00100b38` 的六条目变体。打开任何一个都需要 L3。

**这些没有一个把 FB 几何布局移进常电域。** 一个专门的存活脚本（`geo_flr_survival_map_20260716.sh`）打开了全部六个加 `FUSE_SS_PLM`，发现 CFG1、CSTATUS 和 LMR 仍在 FLR 时回退。那个否定结果，正是出货设计在每次模块加载时、于 GSP 引导路径内重新应用几何布局、而不是尝试让它粘住的原因。

### 26 寄存器 PLM 调查

`nuke.sh` 用一次冷启动基线加九个 FLR 周期分类了这个候选集：

```text
0x008200D0  0x008200D4  0x008200D8  0x008200DC  0x008200E0  0x008200E4
0x008200E8  0x008200EC  0x008200F0  0x008200F4  0x008200FC
0x00823800  0x00823804  0x00823B00
0x009A0008  0x009A000C  0x009A0148  0x009A014C  0x009A0168  0x009A03F0
0x009A0554  0x009A0BFC
0x00100B10  0x00100B38  0x00100B84  0x00100B9C
```

一次 580.159.04 扫描、两次 FLR、没有驱动加载时的实测回读：

| 寄存器 | 值 | 读法 |
|---|---|---|
| `0x8200D4`、`D8`、`E0`、`E4`、`E8`、`EC`、`F0`、`F4`、`FC`、`0x823800`、`0x823804`、`0x823B00` | 打开 | 报告 UNLOCKED |
| `0x8200D0`、`0x8200DC` | `0xffffff8f` | 锁定 |
| `0x9A0008`、`0x9A000C`、`0x9A0148`、`0x9A014C`、`0x9A03F0` | `0xffffff8f` | 锁定 |
| `0x9A0168`、`0x9A0554`、`0x00100B9C` | `0xffffffcf` | 锁定 |
| `0x9A0BFC` | `0x00000000` | |
| `0x00100B10`、`0x00100B38` | `0xffffff8f` | 锁定 |
| `0x00100B84` | `0xffffff88` | 锁定 |

一次解锁后的一次**出厂**驱动加载之后，只有 `0x00823804` 保持打开。`0x001fa7cc` 和 `0x001fa7c4` 重新锁到 `0x0004cb8f`、`0x009a0148` 读 `0xffffff8f`，而针对 `0x009a0008`、`0x00100b10` 和 `0x00100b38` 的主机写测试读 `0xfffffe8e`。

---

## 显存几何布局：FBPA 和 MMU

完整叙述见[显存几何布局](memory-geometry.md)；硬件背景见[显存子系统](../hardware/memory-subsystem.md)。

### 解锁实际写的两个寄存器

| 地址 | 名称 | 功能 | 出厂（两个 SKU） | 8 GB 卡解锁 | 10 GB 卡解锁 | PLM-gated | FLR |
|---|---|---|---|---|---|---|---|
| `0x009a0204` | `NV_PFB_FBPA_CFG1`（广播） | 每个显存分区的寻址深度 | `0x02449000` | `0x02779000` | `0x02669000` | 是、经 `0x009a0148` | **否** |
| `0x00100ce0` | MMU 本地显存范围（LMR） | MMU 看到的总 FB 大小 | `0x00000208`（8 GB）/ `0x00000288`（10 GB） | `0x0000020B` | `0x0000028A` | 是 | **否** |

两者都由补丁 0001 在 SS0/SS1 之后无条件写、在运行时从 `pGpu->idInfo.PCIDeviceID >> 16` 选择：

```c
if (devId == SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID) {   /* 0x20C2 */
    cfg1Value = 0x02779000U;  // 8GB 卡：64GB 解锁
    lmrValue  = 0x0000020BU;
} else {
    cfg1Value = 0x02669000U;  // 10GB 卡：40GB 解锁
    lmrValue  = 0x0000028AU;
}
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);
```

**CFG1 编码。** 位 [23:16] 的档位字节是杠杆：`0x44` 出厂（12 行位，每 FBPA 512 MiB）、`0x66`（14 行位，2048 MiB 每 FBPA）、`0x77`（15 行位，4096 MiB 每 FBPA）。总容量是寻址深度乘以熔丝决定的活-FBPA 数；CFG1 不改变存在多少个 FBPA。探测目录字段解码是 `SUBP[1:0]`、`COL[15:12]`、`ROWA[19:16]`、`BANK[25:24]`；在观察过的每个 HBM 部件上，COL 停在 `0x9`、BANK 停在 `0b10`。GDDR6 部件读到不同的 COL 半字节，这正是为什么 `0x9` 是一个显存类型常量、而非 "5 stacks" 标志。

`0x02779000` 字面上就是出厂 A100 PCIe 80 GB CFG1 字，`0x02669000` 是出厂 A100 PCIe 40 GB 和 SXM4 40 GB 字。解锁恢复真正的 A100 几何布局，而非发明常量。

**LMR 编码。** `size_MiB = MAG[9:4] << SCALE[3:0]`，等价地 `bytes = MAG << (SCALE + 20)`。MAG 按 SKU 恒定（8 GB 卡上 32、10 GB 卡上 40）、等于活-FBPA 数的两倍。SCALE 是解锁改变的东西。

| LMR | MAG | SCALE | 解码为 | 状态 |
|---|---|---|---|---|
| `0x00000208` | 32 | 8 | 8192 MiB | 出厂 8 GB 卡 |
| `0x00000288` | 40 | 8 | 10240 MiB | 出厂 10 GB 卡 |
| `0x0000020B` | 32 | 11 | 65536 MiB | 出货 8 GB 档位 |
| `0x0000028A` | 40 | 10 | 40960 MiB | 出货 10 GB 档位 |
| `0x0000028B` | 40 | 11 | 81920 MiB | `80` 分支上惰性的元数据，但被净室重发脚本真发射过，见下 |
| `0x0000020A` | 32 | 10 | 32768 MiB | PG199 Drive 参考板上的出厂值 |

**CFG1 单独不够。** 一次受控三方对比：没有显存写给出 CPU-RM 失败 `0x24`（`kbusVerifyBar2`）；40 GB CFG1 配出厂 10 GB LMR 仍给 `0x24`；CFG1 加匹配的 LMR 到达 `0x25`（StateLoad）。GSP-RM 另外把 LMR 当主寄存器：CFG1 在 40 GB 而 LMR 留在 `0x288` 时，`kgspBootstrap` 把 CSTATUS 从 `0x800` 回退到 `0x200`。

### FBPA 广播孔径（`0x009a0000` 到 `0x009a3fff`）

| 地址 | 名称 | 出厂 / 实测 | 备注 |
|---|---|---|---|
| `0x009a0008` | FB-几何 PLM | `0xffffff8f` | 在净室 `FB_GEO_PLMS` 清单里 |
| `0x009a000c` | FB-几何 PLM | `0xffffff8f` | 相同 |
| `0x009a0148` | **FBPA PLM** | `0xffffff8f` | 被出货补丁 0001 打开到 `0xffffffff` |
| `0x009a014c` | FB-几何 PLM | `0xffffff8f` | 净室清单 |
| `0x009a0164` | `FBPA_NUM_ACTIVE`（`NUM_ACTIVE_FBPS`） | 8 GB 卡上 `0x00000008` | |
| `0x009a0168` | PLM 候选 | `0xffffffcf` | 仅调查 |
| `0x009a0200` | `FBPA_CFG0_BROADCAST` | 170HX 和 A100 40G/80G 上 `0x07981800`；参考 GA100/Drive 部件上 `0x06981800` | 在每个活每-FBPA 实例上相同 |
| `0x009a0204` | `FBPA_CFG1_BROADCAST` | 见上 | 参考 GA100 和 A100 32 GB Drive 读 `0x22779000`、只在位 29 上不同于 CMP 目标 |
| `0x009a020c` | `FBPA_CSTATUS` 广播 | 解锁的 170HX 上 `0x00001000` 对比 A100 80 GB 上 `0x00000fff` | |
| `0x009a0224` | `TIMING1` | `0x12050d12`（R2W 18，W2R 13，R2P 5，W2P 18） | 编程的 CONFIG 值 |
| `0x009a0290` | `CONFIG0` | `0x1255b93c` | 位 31 `USE_TIMING_REGS` = 0 |
| `0x009a0294` | `CONFIG1` | `0x38d4841b` | CL 27, WL 8, RD_RCD 18, WR_RCD 13, QPOP_OFFSET 14 |
| `0x009a0298` | `CONFIG2` | `0x88130b11` | tWR 19, W2R_BUS 8, R2W_BUS 8, RPRE 1, WPRE 1, CDLR 11 |
| `0x009a02b0` | `TIMING0_GEN` | tRC 60, tRFC 441, tRAS 42 | 生成的影子，实际生效的那个 |
| `0x009a02b4` | `TIMING1_GEN` | R2W 29, W2R 20, W2P 28 | |
| `0x009a02b8` | `TIMING2_GEN` | RD_RCD 18, WR_RCD 13, RRD 6 | |
| `0x009a02c0` | `TIMING4_GEN` | FAW 21 | 原始 `TIMING4` 持有一个陈旧的 FAW 40 |
| `0x009a02d8` | `TIMING9_GEN` | CCDL 4, CCDS 2 | |
| `0x009a02e0` | `TIMING16_GEN` | RP 18 | |
| `0x009a0300` | `FBPA_MRS_0` | 170HX / A100 / Drive A100 上 `0x00000003` | GDDR6 部件不同 |
| `0x009a0304` | `FBPA_MRS_1` | 每张卡上 `0x00100000` | |
| `0x009a0320` | `FBPA_MRS_8`（MR8 密度） | 全部 15 张卡上 `0x00200000` | **不是**容量限制 |
| `0x009a0334` | `FBPA_MRS_2` | `0x00200019`（8 GB CMP）、`0x002000cf`（10 GB CMP 和 A100 40G） | |
| `0x009a0338` | `FBPA_MRS_WL_RL` | `0x003000eb`（8 GB CMP）、`0x003000ea`（10 GB CMP） | |
| `0x009a038c` | `FBPA_HBM_CFG0` | 170HX / A100 上 `0x000000a7`；Drive A100 上 `0x000000a6` | `dual_rank[0]`、`dual_rank_bank[1]`、`SID_VAL[11]` |
| `0x009a03f0` | PLM 候选 | `0xffffff8f` | 仅调查 |
| `0x009a0470` | `FBPA_ECC_CTRL` | `0` 配 `MASTER_EN` 只读 | 见[ECC](../frontier/ecc.md) |
| `0x009a0554` | PLM 候选 | `0xffffffcf` | 仅调查 |
| `0x009a0838` / `0x009a083c` | `FBPA_VEND_ID_C0` / `C1` | 全部 15 张卡上 `0x00000000` | 这里不暴露厂商 ID |
| `0x009a0974` | `FBPA_TRAINING_STATUS` | `0x00000000` = FINISHED | SUBP0[1:0], SUBP1[3:2]，值 2 = ERROR |
| `0x009a0bfc` | PLM 候选 | `0x00000000` | 仅调查 |
| `0x009a3cb4` / `b8` / `bc` | `I1500_INSTR` / `MODE` / `DATA` | `0x0000000f` / `0x00000008` / `0x40000000` | IEEE 1500 HBM 测试端口 |
| `0x009a3cc0` / `cc4` / `cc8` | `I1500_SHADOW_WIR` / `WDR` / `STATUS` | `0x000000f0`（只读）/ 按晶片 / `0x00000000`（空闲） | 8 GB 卡上 `WDR` 是 `0x8000f000`、10 GB 卡上 `0x8273ff83` |

### 每-FBPA 单播孔径

每个 FBPA 寄存器的实例 *n* 位于 `0x00900000 + n*0x4000`，n = 0..23：

| 寄存器 | 地址 | 备注 |
|---|---|---|
| 每-FBPA `CFG0` | `0x00900200 + n*0x4000` | 两个 SKU 的每个活实例上 `0x07981800` |
| 每-FBPA `CFG1` | `0x00900204 + n*0x4000` | 只在一个没有 devinit 的无驱动上下文里必须手写 |
| 每-FBPA `CSTATUS_RAMAMOUNT` | `0x0090020c + n*0x4000` | 验证目标：`0x200` 出厂、40 GB 档位 `0x800`、64/80 GB 档位 `0x1000` |

> [!NOTE]
> **步长是 `0x4000`，不是 `0x400`**
>
> 一份已裁决文档携带一个掉零笔误。步长是 `0x4000`，被广播孔径是 `0x009a0000`-`0x009a3fff`、即恰好 `0x4000` 宽所佐证。

每-FBPA 容量随 LMR SCALE 为 `2^(SCALE+1)` MiB，恰好是 CSTATUS_RAMAMOUNT 报告的值。交叉核对：`0x800` x 20 个 FBPA = 40960 MiB；`0x1000` x 16 个 FBPA = 65536 MiB。一个被地板清扫的 FBPA 改返回一个 `0xbadf20xx` 哨兵。

**在出货驱动路径里一次广播写就够了**，而出货驱动完全不写任何每-FBPA 寄存器。在一个没有 devinit 的无驱动运行时里，广播单独不移动 CSTATUS，全部 24 个实例都必须手写。广播是 PRI 特权环硬件机制还是软件步骤，从未被直接插桩。

### MMU / FB 枢纽

| 地址 | 名称 | 值 | 备注 |
|---|---|---|---|
| `0x00100800` | `FBHUB_NUM_ACTIVE_LTCS` | `10de:20c2` 上 `0x00000010`（16）；`10de:2082` 上 `0x00000014`（20） | `0x14` 在 A100 PCIe 40G/80G 上也一样 |
| `0x00100b10` | FB-几何 PLM | `0xffffff8f` | 净室 `FB_GEO_PLMS` 条目 |
| `0x00100b38` | FB-几何 PLM | `0xffffff8f` | 仅六-PLM 变体 |
| `0x00100b84` | PLM 候选 | `0xffffff88` | 仅调查 |
| `0x00100b90` | `FBHUB_MEM_PART_BCFG0` | `0x00000603` | 与每张卡上文档化的 init 匹配 |
| `0x00100b98` | `SYSMEM_HSHUB_CONNECTION_CFG` | `0x00000003`（BOTH，PCIe 路由） | |
| `0x00100b9c` | PLM 候选 | `0xffffffcf` | 仅调查 |
| `0x00100ce0` | MMU 本地显存范围 | 见上 | |
| `0x00100ec0` | `MMU_NUM_ACTIVE_LTCS` | 10 GB SKU 和全部三个 A100 SKU 上 `0x05001414`；8 GB SKU 上报告 `0x04001410` | 按 SKU 的划分是一个未解问题、不是分歧；`...1410` 与 16 个 LTC 一致、`...1414` 与 20 个一致 |

### L2 / LTC

| 地址 | 名称 | 值 | 备注 |
|---|---|---|---|
| `0x0017e22c` | L2/LTC 地址映射寄存器 | 原生 `0x00280404` | 从不被任何东西编程，40 GB 却有效 |
| `0x0017e2a0` / `0x0017e2a4` | 每-LTC 解码 | | 被净室 v8 工具瞄准 |
| `0x001402b4` | LTC 伴生 | 尝试写 `0x00a00030` | 没移动 40 GiB 折叠 |

净室 v7 到 v8 的改动把 `DECODE_VAL` 从 `0x60000300`（每通道 2 GB）驱到 `0x10000300`（每通道 4 GB）。在 170HX 上该值全程停在 `0x70000300`，仍然无法解释。见[80 GB 问题](../frontier/80gb.md)。

---

## 特性覆盖与算力（`0x008238xx`）

这个块就是算力解锁。叙述见[算力节流](compute-throttle.md)。

| 地址 | 名称 | 出厂 170HX | 解锁 | PLM-gated | FLR | 被谁碰 |
|---|---|---|---|---|---|---|
| `0x00823800` | `FEAT_OVR_ECC_PLM` | `0xffffff8f`（单独 A100 SXM4 40G 读 `0x0000abcf`） | 打开时 `0xffffffff` | 是一个 PLM | 未知 | Gen2 分支 `xp3gTable`，永不被 master |
| `0x00823804` | **`FEAT_OVR_PLM`** | `0xffffff8f` | `0xffffffff` | 是一个 PLM | **挺过**（AON 岛） | 出货补丁 0001、PLM 索引 3 |
| `0x00823808` | `FEAT_OVR_QUADRO` | **按晶片且无法解释：见下注** | | | | 只读 |
| `0x0082380c` | `FEAT_OVR_ECC` | `0x00888888` | | | | 只读 |
| `0x00823810` | `FEAT_OVR_ECC_1` | `0x002aaaaa` | | | | 只读 |
| `0x00823814` | `FEAT_READOUT_0` | `0x00000233`（只读）；一块参考 GA100 板读 `0xef8ff100` | | 只读 | | 字段布局未文档化 |
| `0x00823818` | **`FEAT_READOUT_1`** | `0x016db6ed` | **`0x00000000`** | 只读 | | 最干净的 "这张卡解锁了吗" 测试 |
| `0x0082381c` | **`FEAT_OVR_SM_SPEED_SELECT`（SS0）** | 因卡而异：`0x53540175`、`0x12103060` | `0x88888888` | 是、经 `0x00823804` | **挺过** | 出货补丁 0001 |
| `0x00823820` | **`FEAT_OVR_SM_SPEED_SELECT_1`（SS1）** | 因卡而异：`0x00000000`、`0x00000003` | `0x00000008` | 是 | **挺过** | 出货补丁 0001 |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` | 两个 170HX SKU 上 `0x00000000` | | | | 只读 |
| `0x00823828` | `FEAT_READOUT_2` | 170HX 上 `0x00000000`；全部 A100 和 Drive 部件上 `0x00000007` | | 只读 | | 只读 |
| `0x0082382c` | `FEAT_READOUT_2`（一份转储里的别名） | `0x0000000a` | | 只读 | | 两份转储之间的命名未定论 |
| `0x00823b00` | 行重映射器 PLM（`FEAT2`） | `0xffffff8f` | 打开时 `0xffffffff` | 是一个 PLM | 一次扫描在 FLR 后读它打开 | 仅 Gen2 家族补丁 0001 |

> [!NOTE]
> **未解问题：`0x00823808` `FEAT_OVR_QUADRO` 在每份转储里读不同**
>
> 按晶片且无法解释。实测：`0x00100183`（出厂、PLM 范围扫描、中等）、`0x00000081`（解锁后探测、中等）、`0x00000181` / `0x00000182`（两块物理 170HX 单元、高、13 个分级差异之一）、`0x01000282`（A100 80 GB）。只读。**开放问题：** 为什么该值跨三份转储都不同；解锁或驱动里的某个东西可能在碰 Quadro-对-消费级分类字，那可能是驱动可见功能类的杠杆。下一步：在一张卡上于出货序列每个阶段前后重读这个寄存器。

**SS0/SS1 编码什么。** `0x0082381c` 持有 IMLA0-3、FMLA16、FMLA32、FFMA 和 DP 的八个 4 位字段；`0x00823820` 持有 IMLA4 的第九个字段。每个半字节最好读作 `[enable | 3-bit speed]`，所以 `0x8` 意思是 "override enabled, speed 0 = full rate"（覆盖启用、速度 0 = 全速）。`0x88888888` 因此在全部八个 SS0 单元上说 "覆盖启用、全速"，`0x00000008` 对 IMLA4 做同样的事。档案里没有任何出厂转储有任一半字节大于或等于 `8`。这个编码是推断的、未文档化。

> [!CAUTION]
> **不要用 SS0/SS1 回读作按部件参考**
>
> 它们是运行时状态，不是熔丝状态。同一 A100 80 GB 设备 ID 的两份归档转储不一致（`0x00112011`/`0x00000002` 对比 `0x00343015`/`0x00000004`）。改用 `0x00823818 == 0`。

两次写都需要；只写一个不够。两者在两个 SKU 上、在全部十二个未发布分支里都相同：没有任何分支试过不同的算力值。

---

## 熔丝与 OTP 影子（`0x0082xxxx`）

除非注明，这些是只读的熔丝感测反射。见[熔丝与 OTP](../hardware/fuses-and-otp.md)。

### 熔丝控制

| 地址 | 名称 | 170HX | 备注 |
|---|---|---|---|
| `0x00820000` | `FUSE_FUSECTRL` | `0xe0040000` | 组里全部 15 张卡上相同 |
| `0x00820040` | `FUSE_EN_SW_OVERRIDE` | `0x00000000` | 消费级和工程样品部件上 `0x00000001`；在 170HX 上可写且持久、却什么都没可观察地改变 |
| `0x00820078` | `FUSE_EN_PROGRAM` | `0x00000001` | 全部 15 张卡 |
| `0x0082007c` | `FUSE_DIS_PROGRAM` | `0x00000000` | GA10x 上 `0xbadf5040` |
| `0x00820080` | `FUSE_BYPASS_STATUS` | `0x00000000` | GA10x 上 `0xbadf5040` |
| `0x00820084` | `FUSE_DIS_SW_OVR` | `0x00000001` | 全部 15 张卡；HS 写被弹回 |
| `0x0082038c` | `FUSE_QUADRO_WR_SEC`（`OPT_SECURE_FEATURE_OVERRIDE_QUADRO_WR_SECURE`） | `0x00000001` | 允许 `0x00823804` 被打开 |
| `0x008203f0` | **`FUSE_FEAT_OVR_DIS`（`OPT_FEATURE_FUSES_OVERRIDE_DISABLE`）** | `0x00000000` | **主灭杀熔丝，未烧断。这个单一零就是整个解锁存在的原因。** |
| `0x008203f4` | `OPT_INTERNAL_SKU` | `0` | |
| `0x0082074c` | `FUSE_OPT_SECURE_GSP` | `0x00000001` | 全部 15 张卡 |
| `0x00820618` | `FUSE_FBPA_MEM_WR_SEC` | `0x00000001` | 全部 15 张卡 |
| `0x00821060` | `OPT_SKU_ID` | `0x00000068`（10 GB、`0x2082`）；`0x00000080`（8 GB、`0x20C2`） | 两块物理探测单元都是 10 GB 且读 `0x68`；`0x80` 值来自一次对 8 GB 卡的净室硅片读 |

### SM 速度选择熔丝（节流本身）

全部在 170HX 上读 `0x00000005`（3 位字段，0 = 全速、5 = 除以 32）、在 A100 SXM4 40 GB、A100 PCIe 40/80 GB、A10、A5000、A6000、Drive A100 和 96-SM `0x20bb` DRIVE-PG199-PROD 部件上读 `0x00000000`。**它们不被解锁改变**：覆盖取代它们。

| 地址 | 名称 | 170HX | 备注 |
|---|---|---|---|
| `0x008200fc` | `FUSE_SS_PLM` / `OPT_PLM` | 一次扫描 `0xffffffff`、另一次 `0x000003ff` | 一个寄存器的两个名字：`OPT_PLM` 是分支代码标签、`FUSE_SS_PLM` 是净室工具命名。不被 master 写 |
| `0x00820224` | `FUSE_SS_DP` | `0x00000001` | 单独的 1 位熔丝（0 全速，1 降低） |
| `0x0082059c` | `FUSE_SS_FFMA` | `0x00000005` | |
| `0x008207d4` | `FUSE_SS_FMLA16` | `0x00000005` | |
| `0x008207d8` | `FUSE_SS_FMLA32` | `0x00000005` | RTX 3070 读 1 |
| `0x008207dc` | `FUSE_SS_IMLA0` | `0x00000005` | |
| `0x008207e0` | `FUSE_SS_IMLA1` | `0x00000005` | |
| `0x008207e4` | `FUSE_SS_IMLA2` | `0x00000005` | |
| `0x008207e8` | `FUSE_SS_IMLA3` | `0x00000005` | |
| `0x008207ec` | `FUSE_SS_IMLA4` | `0x00000005` | RTX 3070 读 1 |

### PCIe 熔丝

| 地址 | 名称 | 170HX | 探测的每个其它 Ampere 部件 | 备注 |
|---|---|---|---|---|
| `0x0082057c` | `FUSE_PCIE_GEN23_DIS`（`OPT_PCIE_BOOT_GEN23_DISABLE`） | `0x00000001` | `0x00000000` | **硬只读。** 从主机、HS ROP 和 Booter 载荷尝试过；总是以 `rd=0x00000001` 失败。Gen2 反正有效 |
| `0x00820580` | `FUSE_PCIE_GEN3_DIS`（`OPT_PCIE_BOOT_GEN3_DISABLE`） | `0x00000001` | `0x00000000` | |
| `0x00820520` | `FUSE_PCIE_MAGIC_D` | `0x16680000`（位 25 置位 = `GEN4_SPEED_DISABLED`，NVIDIA bug 2220334） | A100 和 Drive GA100 上 `0x00200000` | 可写性有争议 |
| `0x00820584` | `FUSE_DEVID_SW_OVR_DIS` | `0x00000001` | `0x00000001` | |
| `0x00820394` | `OPT_PCIE_LANE_DISABLE` | `0x00000000` | `0x00000000` | x4 位宽是板级的、不是熔断的证明 |
| `0x0082082c` | `CTRL_OPT_PCIE_LANE` | `0x00000000` | `0x00000000` | |
| `0x00820c2c` | `STATUS_OPT_PCIE_LANE` | `0x00000000` | `0x00000000` | |
| `0x008204d8` | `OPT_PCIE_DEVIDA` | `0x000020c2`（8 GB）、`0x00002082`（10 GB） | A100 `0x20b2` | SKU 身份熔丝 |
| `0x0082056c` | `OPT_PCIE_DEVIDB` | 两个 SKU 上 `0x000020c2` | A100 `0x20f2`；PG199 `0x000020fb` | 10 GB 卡上 DEVIDA 和 DEVIDB 不一致 |
| `0x00820148` | OTP 备用位 | `0x00000000` | | 永不可设置 |

> [!NOTE]
> **未解问题：`0x00820520` 可写吗？**
>
> 一份分析把位 25 标注 "(writable)"；一个净室工具作为一条工作 Gen2 链的一部分把 `0x00200000` 写给它；PCIe 实地手册把它列为只读；而出货 Gen2 补丁只读它。没人发布过一次写后回读。Gen4 反正不可测试，因为没有正在做它的人有 Gen4 主机。见[Gen3 和 Gen4](../frontier/pcie-gen3-gen4.md)。

### NVLink 熔丝

| 地址 | 名称 | 170HX | 备注 |
|---|---|---|---|
| `0x00820684` | `FUSE_NVLINK_DIS`（`OPT_NVLINK_DISABLE`） | `0x00000007`（[2:0] 全部三位） | A100 SXM4 40G / PCIe 40G / PCIe 80G / A10 / A5000 / A6000 / RTX 3090 / 3090 Ti 上 `0x00000000`；RTX 3080 / 3080 Ti 上 `0x00000001`；Drive A100 上也是 `0x00000007` |
| `0x00820db8` | `STATUS_OPT_NVLINK` | `0x00000007`（只读镜像） | 与 Drive A100 共享 |
| `0x008209b8` | `CTRL_OPT_NVLINK` | `0x00000000`（位 15:0，每链路） | 覆盖影子在每张被探测的卡上都读零 |
| `0x00820820` | `CTRL_OPT_PERLINK` | | 从未写测试过 |

整个 `0x00823800`-`0x0082382c` 块里没有任何 FEAT_OVR 条目为 NVLink 存在，也没有任何分支含 NVLink 代码。见[NVLink](../frontier/nvlink.md)。

### 地板清扫熔丝

按卡、不按 SKU。每张被调查的 170HX 都落到 70 SM、无论哪些 GPC 关闭。

| 地址 | 名称 | 实测 | 备注 |
|---|---|---|---|
| `0x00820350` | `OPT_GPC_DISABLE` | 四张不同卡上 `0x85`、`0x45`、`0x13`、`0xa8` | HS 写被弹回，值被锁存 |
| `0x00820364` | `OPT_FBP_DISABLE` | `0x00000840`（10 GB 卡）、`0x00000852`（社区转储）、`0x00000009` / `0x00000180`（两个单元） | |
| `0x00820368` | `OPT_FBPA_DISABLE` | `0x000000c3`（10 GB 卡：FBPA 00/01/06/07 关闭，20 活）、`0x00c0330c`（8 GB 卡：FBPA 02/03/08/09/12/13/22/23 关闭，16 活） | |
| `0x0082036c` | `OPT_FBIO_DISABLE` | 镜像 `0x00820368` | |
| `0x008202c4` | `OPT_ROP_L2_DISABLE` | 镜像 `0x00820368` | |
| `0x00820398` | `OPT_SPARE_FS` | `0x00000000` | |
| `0x008205c4` | `OPT_GPC_DEFECTIVE` | 几张 DISABLE 置了三个位的卡上 `0x00000000`；一块 10 GB 卡上 `0x81` | "disabled" 和 "defective" 是分开的掩码：一些被禁用的 GPC 是物理完好的硅片 |
| `0x008205cc` | `OPT_FBP_DEFECTIVE` | `0x00000840`（10 GB 卡） | |
| `0x008205d0` / `0x008205d4` / `0x008205e8` | `OPT_FBPA_DEFECTIVE` / `FBIO_DEFECTIVE` / `ROP_L2_DEFECTIVE` | 各 `0x00c03000` | |
| `0x00820818` | `CTRL_OPT_FBPA` | `0x00000000` | 不存在覆盖 |
| `0x00820838 + i*4` | `FUSE_CTRL_OPT_TPC_GPC(i)` | `0x00000000` | **只减（减性）**：写它从不加回一个 TPC |
| `0x00820938` | `CTRL_OPT_FBP` | `0x00000000` | |
| `0x00820840` | MIG 使能 | 出厂 `0`；设位 0 启用 MIG、被报告为持久 | **不在出货树里**；一次全仓库 grep `0x820840` 返回空 |
| `0x00820c00` | `STATUS_HALF_FBPA` | `0` | 没有半容量熔丝要恢复 |
| `0x00820c14` | `STATUS_OPT_FBIO` | `0x00c0330c`（8 GB 卡） | |
| `0x00820c18` | `STATUS_OPT_FBPA` | `0x00c0330c` / `0x000000c3` | **这是正确地址；`0x00820c14` 是 FBIO** |
| `0x00820c1c` | `STATUS_OPT_GPC` | 总是镜像 `0x00820350` | |
| `0x00820c38 + i*4` | `FUSE_STATUS_OPT_TPC_GPC(i)` | 一张卡上 GPC0/3/5 = `0xff`、其它 = `0x01` | |
| `0x00820d38` | `STATUS_FBP` | 一个单元上 `0x00000180` | |

### 拓扑标量（`0x0002xxxx`）

只读，且它们描述完整的 GA100 晶片、而非被收获的部件。

| 地址 | 名称 | 170HX |
|---|---|---|
| `0x0002241c` | `NV_PTOP_FS4` | 8 GB 卡（`0x20c2`）上 `0x00000000`；10 GB 卡（`0x2082`）上 `0x00000081`，在 A100 80 GB、RTX 3070、GA10x 和 Drive `0x20bb` 上也是。位 0 是 `GEN2_PCIE`，位 7 是 `GEN2_PCIE_SPEED` |
| `0x00022430` | `PTOP_SCAL_NUM_GPCS` | `0x00000008`（GA10x 读 7） |
| `0x00022434` | `PTOP_SCAL_TPC_PER_GPC` | `0x00000008` |
| `0x00022454` | `PTOP_SCAL_NUM_LTCS` | `0x00000018`（24） |
| `0x00022458` | `PTOP_SCAL_FBPA_PER_FBP` | `0x00000002`（RTX 3090 读 1） |
| `0x0002246c` | `PTOP_SCAL_NUM_NVLINK` | `0x0000000c`（12）；GA10x 读 4 |
| `0x00022470` | `PTOP_FS_STATUS` | `0x0000003f`；位0 TPC、位1 GPC、位2 FBP、位3 ROP、位4 FBIO |
| `0x00120078` | `RING_ENUM_GPC` | 每张 170HX 上 `5`；从未被任何写尝试移动 |
| `0x00001404` | `PBUS_SW_SCRATCH(1)` | 全部被调查的卡上 `0x20042000`、位 14 = 0 |
| `0x00000000` | `PMC_BOOT_0` | 每个有效 GA100 上 `0x170000a1`；GA10x 对照读 `0xb74000a1` |
| `0x008204bc` | `OPT_SLT_REV` | 被 `ga100_topology_report.py` 读取 |

---

## PCIe：XVE、XP3G 和 XP-PL

本节一切**都是未发布分支材料**。出货 `master` 只含补丁 `0001` 到 `0006`、`constants.yaml` 里没有 `pcie:` 块，而对其安装器、卸载器、README 和构建脚本对 `gen2|gen 2|pcie|iommu|retrain|RMPcieLinkSpeed` 的一次不区分大小写 grep 返回零命中。见[PCIe Gen2](pcie-gen2.md) 和[PCIe 子系统](../hardware/pcie-subsystem.md)。

> [!WARNING]
> **实验性**
>
> 补丁 `0007-pcie-gen2.patch` 存在于分支 `debug-gen2`、`Gen2`、`far` 和 `deced` 上；`0008-pcie-gen2-probe-retrain.patch` 在 `Gen2`、`far` 和 `deced` 上。这里没有任何东西被合并到 master。

### XVE 配置空间影子（BAR0 基址 `0x88000`）

配置读每次访问都从这个影子新鲜而来，这就是为什么在运行时重写它然后强制重训练会让主机重新读修正后的能力。PCIe Express 能力坐在配置偏移量 `0x78`，所以配置 `0x78 + X` 映射到 BAR0 `0x88078 + X`。

| 地址 | 配置偏移量 | 名称 | 出厂 | 0007 之后 | 备注 |
|---|---|---|---|---|---|
| `0x00088084` | CAP_EXP+0x0c | `LINK_CAP`（LnkCap） | `0x00456101` | `0x00456102` | 位 20（DLL Link Active Reporting Capable）**清除**，这破坏 0008 的成功测试 |
| `0x00088088` | CAP_EXP+0x10 | `LINK_CTRL_STATUS` | LnkSta `0x1041` | `0x1042` | `PCIE_LINK_SPEED_OF(stat) = ((stat) >> 16) & 0xF` |
| `0x000880a4` | CAP_EXP+0x2c | `LINK_CAP2`（LnkCap2） | `0x00000002`（仅 2.5 GT/s） | `0x00000006`（G1/G2） | 硬件只读、标 `R-EVF`：`setpci` 写被静默丢弃 |
| `0x000880a8` | CAP_EXP+0x30 | `LINK_CTRL_2`（LnkCtl2） | `0x0000` / 寄存器读 `0x00000001` | 位[3:0] = `0x2`，位[19:16] = `0xF` | A100 这里读 `0x001f0004` |
| `0x0008841c` | | `PRIV_MISC_1` | `0x20340500` | `0x20342d00` | 设位 11 和 13、清位 12 和 14；**第一次尝试就成功并挺过 BooterLoad** |
| `0x0008860c` | | `VSEC_DEVICE` | `0x00000800` | 想要 `0x00000801` | **写在硅片上两次失败**；回读停在 `0x00000800` |
| `0x00088610` | | `VSEC_HIERARCHY` | `0x00001001` | 清位 12、设位 0 | Booter 阶段后的普通主机写 |
| `0x0008872c` | | LTSSM / `XVE_OVR` | | `0x00000006` | 补丁自己的日志叫它 "skip mid-boot retrain"。值 `0x2` 和 `0xa` 在 VFIO 下暴露额外的 Gen2 行为、却最终楔住 QEMU 函数 |
| `0x00088ab4` | | `XVE_B` PLM | | `0xffffffff` | Gen2 家族 PLM 表 |
| `0x00088ce4` | | 未命名 | `0x0000003f` | | A100 读 `0x00000014` |
| `0x00088fe8` / `0x00088fec` / `0x00088ff0` | | `XVE_D0` / `D4` / `D8` PLM | | `0xffffffff` | `xp3gTable` 条目 |
| `0x00088ff4` | | `XVE` PLM | | `0xffffffff` | Gen2 家族 PLM 表 |
| `0x00088ff8` | | `XVE_C` PLM | | `0xffffffff` | Gen2 家族 PLM 表 |

### XP3G PHY 速率覆盖块（`0x0008e1xx`）

| 地址 | 名称 | 0007 写入的值 | 备注 |
|---|---|---|---|
| `0x0008e100` | `XP3G_STATUS` 基址 | （读） | |
| `0x0008e110` | `XP3G_OVR0` | `0x00000001` | 一次更早的独立探测里观察到回读 `0x00000004` |
| `0x0008e11c` | `XP3G_OVR3` | `0x00000004` | |
| `0x0008e120` | `XP3G_VAL0` | `0x00000000` | |
| `0x0008e12c` | `XP3G_VAL3` | `0x00200000` | |
| `0x0008e1b0` | `XP3G_PLM` | `0xffffffff` | 干净打开；回读 `0xffffffff` |
| `0x0008e1b4` | `XP3G_PLM4` | `0xffffffff` | |
| `0x0008e1b8` | `XP3G_PLM8` | `0xffffffff` | |
| `0x0008e1bc` | `XP3G_PLMC` | `0xffffffff` | |

一次 PLM 打开下的隔离 XP3G 覆盖把速率字段驱到一个 Gen3 能力的 `0x00340036`、链路仍在 Gen1 训练。那反驳了 XP3G 作为一个独立杠杆，但它是后来工作的那个组合的一个组件。

### XP-PL 链路配置块（`0x0008cxxx`）

作为**普通主机 BAR0 写**写入、在 Booter 阶段之后、不带任何特权提升：

| 地址 | 名称 | 操作 | 备注 |
|---|---|---|---|
| `0x0008c040` | `LINK_CONFIG_0` | 位[19:18] `MAX_RATE` = `0x2` | 读-改-写：清掩码 `0x000c0000`，然后 OR 进 `2 << 18` |
| `0x0008c044` / `0x0008c048` / `0x0008c04c` | LINK_CONFIG 簇 | （拒绝 HS 写） | 一个与工作的三个*不同*的簇 |
| `0x0008c080` | 链路 WIDTH | A100 读 `0x00001010` | |
| `0x0008c1c0` | `PL_LINK_RATE` | `= 0x00240036` | A100 读 `0x00040036` |
| `0x0008c2c0` | `CYA_0` | 清位 2（`DIS_G2`） | 中央杠杆 |

### 0007 写的 OPTB PLM 块

十个寄存器、`0x008200d0`、`d4`、`d8`、`dc`、`e0`、`e4`、`e8`、`ec`、`f0`、`f4`，全部设 `0xffffffff`，加 `0x00823800` `FEAT_OVR_ECC_PLM` 和 `0x0082057c` `OPT_GEN23`（尝试 `0x00000000`，总是失败）。

### `0007` 的写计数

`xp3gTable` 有 **23** 条目：18 次 PLM 打开加 5 次值写。`VSEC_DEVICE 0x0008860c` 和 `PRIV_MISC_1 0x0008841c` 在表外处理，给出 **25 次 Booter 路由的写**。每个两次尝试、每次前重新武装 `0x001fa824` / `0x001fa828`。然后是六次普通主机写：`0x00088610`、`0x000880a8`、`0x0008c2c0`、`0x0008c040`、`0x0008c1c0` 和 `0x0008872c`。

### 从注入点被 PROT-wall 或毒化的寄存器

| 地址 | 行为 |
|---|---|
| `0x00088070`、`0x0008808c`、`0x00088090` | 读返回 0，写被忽略 |
| `0x00085080`、`0x00085084` | 读 `0xbadf1100`；"GSP writes `0x85084`" 是真的，但在一个注入点永远达不到的权限级别 |
| `0x00409664`、`0x00409668` | 每一张 Ampere 卡（包括未节流的）上 `0xbadf5040` |

> [!NOTE]
> **不要复述 `0x8808c` 为 LnkCap2 镜像**
>
> 一份实地手册把 `NV_XVE_LINK_CAPABILITIES_2` 列为 "cfg 0xA4 / BAR0 mirror `0x8808c`"，那是内部自相矛盾的。XVE 镜像基址在 `0x88000` 时，配置 `0xA4` 映射到 `0x880a4`，而补丁 0007 和独立 `pcielink.sh` 都用的正是它。

---

## 图形、SKED 和 FECS：调查过、从未使用

出货树里没有任何东西碰这些。一次全仓库 grep `0x504204`、`0x8200fc`、`0x82038c`、`0x8203f0`、`0x823818`、`0x820224`、`0x82059c` 和 `0x820840` 返回零命中。

| 地址 | 名称 | 170HX | 判决 |
|---|---|---|---|
| `0x00407000` | `SKED_HW_BLK` | `0x00004042`（驱动前 `0xbadf1201`） | |
| `0x00407010` | `SKED_PM_UNK10` | `0x00000000` | |
| `0x00407020` | `SKED_TRAP` | `0x00000000` | |
| `0x00407024` | `SKED_TRAP_EN` | `0x3dfffffc`、与 A100 相同；RTX 3090 读 `0xbdfffffc`（仅位 31） | |
| `0x00407054` | `SKED_UNK54` | `0x60000600`（驱动前）或 `0x600000c0`；**A100 和 RTX 3090 上都 `0`** | GSP 固件里被引用最多的未文档化 SKED 寄存器（13 处引用）、也是 13 卡组里唯一在 170HX 上非零、在对照上为零的寄存器。从未写测试过。驱动在 GR init 时清除它 |
| `0x00408970` | `gpcMask` | `0xdc`、每次强制尝试后重新断言 | 死路 |
| `0x00409664` | `FECS_FEAT_OVERRIDE` | `0xbadf5040` | 在每一张 Ampere 卡上都读被阻止，所以该值不携带信息 |
| `0x00409668` | `FECS_FEAT_READOUT_1` | `0xbadf5040` | 相同 |
| `0x00504204` | `SM_ISSUE_RATE_MODIFIER` | 带驱动 `0x00000005`、不带 `0xbadf1201` | **不是**节流：在 13 张对比 Ampere 卡和每颗速度选择熔丝都 0 的 96-SM `0x20bb` GA100 上读 `0x00000005`。主机可写；清零它不改变任何东西 |

> [!NOTE]
> **未解问题：`0x00504204` 对一张已解锁的卡施加残余限制吗？**
>
> 没人跑过明显的 A/B：在解锁卡上把它写 0 并重跑基准套件。写原语已经存在。

---

## 载荷偏移量表

Booter 的 LS 签名验证（IMEM `0x29c4` 处的 `booterVerifyLsSignatures_TU10X`）执行一次无界 DMA、其长度直接从 `WprMeta` 里的 `sizeOfSignature` 取。驱动把它设成 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800`（63,488 字节），而 DMA 目的地是 DMEM `0x0800`，所以载荷 1:1 映射到 DMEM `0x0800`..`0xffff`（`0x0800 + 0xf800 = 0x10000`，恰好 64 KB DMEM 的顶部）。**DMEM 地址 = 载荷偏移量 + `0x800`。**

缓冲区里每个 dword 先被填 `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7`（15,872 个 dword），然后恰好 24 个槽被覆盖：

| 载荷偏移量 | DMEM | 值 | 角色 |
|---|---|---|---|
| 全部 | `0x0800`-`0xffff` | `0x000004a7` | 背景填充 dword |
| `0x1100` | `0x1900` | `0x00000007` | 目的未识别 |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **写进栈守卫全局的假金丝雀** |
| `0xf754` | `0xff54` | *writeValue* | 值参数、最低尾槽 |
| `0xf758` | `0xff58` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf75c` | `0xff5c` | `0x00000cbd` | |
| `0xf76c` | `0xff6c` | *writeAddr* | 地址参数 |
| `0xf774` | `0xff74` | `0x00001fbd` | |
| `0xf780` | `0xff80` | `0x00000000` | |
| `0xf788` | `0xff88` | `0x000010aa` | **BAR0-master 写 gadget（`reg_write_indirect`）** |
| `0xf78c` | `0xff8c` | `0x0000815a` | |
| `0xf790` | `0xff90` | `0x00008e18` | |
| `0xf794` | `0xff94` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf798` | `0xff98` | `0x0000815a` | |
| `0xf79c` | `0xff9c` | `0x00000000` | |
| `0xf7a0` | `0xffa0` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf7a4` | `0xffa4` | `0x00001fbd` | |
| `0xf7b0` | `0xffb0` | `0x0000ffbc` | |
| `0xf7b8` | `0xffb8` | `0x0000582d` | |
| `0xf7c4` | `0xffc4` | `0xc0deca7e` | 保存-金丝雀槽 |
| `0xf7c8` | `0xffc8` | `0x00000cbd` | |
| `0xf7d8` | `0xffd8` | `0x00000003` | |
| `0xf7e0` | `0xffe0` | `0x00001fbd` | |
| `0xf7f4` | `0xfff4` | `0x00000ccb` | 见下方未解问题 |
| `0xf7f8` | `0xfff8` | `0x00007f2f` | 最外层槽 |

这张表在出货 `master` 和全部十二个归档分支里**逐字节相同**（用校验和与一次 `0xc0deca7eU` 的 grep 验证，它在每份副本里恰好出现五次）。

**表引用的承重 DMEM 地址：**

| DMEM | 含义 |
|---|---|
| `0x0100` 及以下 | 这里什么都没分配，这杀死了"低 DMEM 里分阶段的大 ROP"的想法 |
| `0x0530` | DMA/引擎配置描述符 |
| `0x0600` | `WprMeta`，一个 256 字节结构 |
| `0x06fc` | IMEM `0x27fa` 的 `r4 == 0` 分支上 Booter 存 `0xa0a0a0a0` 的地方；**与** `0x1fa824`/`0x1fa828` WPR2 寄存器**无关** |
| `0x0800` | DMA'd 签名缓冲区的基址，即载荷偏移量 0 |
| `0x103c` 起 | 密码会话描述符 |
| `0x2383`、`0x8e08` | 寄存器描述符表，被载荷线性粉碎 |
| `0x6340` | **栈金丝雀全局**，25408 十进制 |
| `0x8700` | booter 代码/数据的末尾 |
| `0xffec` | 喂 `main` 的退出状态、决定 `secure_teardown` 是否运行的槽 |

> [!NOTE]
> **未解问题：DMEM `0xfff4` 处的 `0x00000ccb`**
>
> `0x0ccb` 是 `regtable_rw_indexed`，它索引的正是载荷粉碎的 DMEM `0x2383` 和 `0x8e08` 处的描述符表，而一次 2026-07-06 隔离矩阵显示每条携带写入的重接链都死在 `0xccb`。出货载荷却把 `0x00000ccb` 种在 `0xfff4`、解锁可演示地工作。通过追踪展开期间 `0xfff4` 是否曾被载入 PC、还是只是一个永不被返回穿过的帧里活过的保存槽来定论。

> [!NOTE]
> **未解问题：无法解释的载荷常量**
>
> DMEM `0x1900` 处 `0x00000007`、`0xffd8` 处 `0x00000003`、`0x0000582d`、`0x0000ffbc`、`0x00008e18`、`0x0000815a`（两次）、`0x00000cbd`（两次）、`0x00001fbd`（三次）、`0x00007f2f`，以及填充 dword `0x000004a7` 本身。ROP 写作命名了一个邻近 gadget 族（`0x1fb9`、`0x1fca`、`0x814e`、`0x8173`、`0x7f82`），所以这些很可能是翻译后的同一个尾。对带注释的反汇编过一次应该能解决全部。

### 载荷覆盖钩子

`SEC2_POSTBL_TIMING_DMEM_PATH = "/lib/firmware/nvidia/ga100/gsp/dmem.bin"` 被读进新创建的 `0xf800` 缓冲区、缺失时回退到内置模板（预置 `writeAddr 0x009a0148`、`writeValue 0xffffffff`）。缺失以状态 `0x59` 报告、是良性的。

### 档案里的载荷变体

| 变体 | 大小 | DMA 基址 | 金丝雀值 | 金丝雀槽 |
|---|---|---|---|---|
| 出货 `master` 和全部 12 个分支 | `0xf800` = 63,488 B | `0x0800` | `0xc0deca7e` | `0x6340`、`0xff58`、`0xff94`、`0xffa0`、`0xffc4` |
| 净室 ROP 写作（2026-07-07/08/13） | `0xf800` | `0x0800` | `0xfaceb13d` | `0x6340`、`0xff58`、`0xff94`、`0xffdc`、`0xfff4` |
| 被取代的 `builder.py` / `patcher.py` | `0xf700` = 63,232 B | `0x0900` | `0xdead2c20` 在 `0x2c20` | 生产映像偏移量，无一被复用 |

金丝雀**值**是任意的、只要它在守卫全局和每个保存副本间一致；**地址 `0x6340` 才是承重事实**。一条给出 `0x6440` 的一次性消息是笔误：`0x5b40 + 0x900 = 0x6440` 是更早文档化 DMA 基址 `0x0900` 给出的结果。

---

## 不是 BAR0 地址的数字

这里每一条都至少一次被误认为寄存器地址。

| 数字 | 它实际是什么 |
|---|---|
| `0x02449000`、`0x02669000`、`0x02779000` | FBPA CFG1 **值**（出厂、40 GB 档位、64/80 GB 档位）。聊天里流传的半字节移位拼写 `0x24490000`、`0x26690000`、`0x27790000` 是抄写笔误 |
| `0x00000208`、`0x0000020B`、`0x00000288`、`0x0000028A`、`0x0000028B` | MMU LMR **值** |
| `0x0000001000000000`、`0x0000000A00000000`、`0x0000001400000000`、`0x0000000200000000` | 64 GiB、40 GiB、80 GiB 和 8 GiB 字节数（`targetFbBytes` / `fb_length` / `stockFbBytes`） |
| `0x88888888`、`0x00000008` | SS0 和 SS1 **值** |
| `0x0000f800`、`0x000004a7`、`0xc0deca7e`、`0xfaceb13d` | 载荷大小、填充 dword、金丝雀值 |
| `0x000010aa`、`0x000010b9`、`0x00001196`、`0x00001064`、`0x00008224`、`0x00008264`、`0x00008262`、`0x00007f82`、`0x0000814e`、`0x00008137`、`0x00008173`、`0x00008117`、`0x00008119`、`0x0000810d`、`0x00000ccb`、`0x00001fbd`、`0x00007f2f` | **Booter 内的 Falcon IMEM 地址**，不是 BAR0 偏移量。`0x10aa` 是 `reg_write_indirect`；从 `0x10b9` 进入跳过 `r10`/`r11` 复制 |
| `0x0001c000`、`0x0001c100`、`0x0001c200`、`0x0001c300`、`0x00009100`、`0x00012000` | Falcon CSB 空间（`I[...]`），从主机够不到 |
| `0x00200000` | `FUSE_PCIE_MAGIC_D` 的 A100/Drive 值，以及单独写给 `XP3G_VAL3` 的值 |
| `0x00240036`、`0x00340036` | `PL_LINK_RATE` 值（出货的 Gen2 那个，和什么都没训练成的 Gen3 能力那个） |
| `0x1ffffe00` | WPR2_LO teardown **值** |
| `0x800000f1`、`0x800000f2` | BAR0-master 读和写**命令字** |
| `0x1312d00` | BAR0-master 看门狗种子，20,000,000 十进制 |
| `0x0000abcf`、`0x0004cb8f`、`0xffffff8f`、`0xfffffe8e`、`0xffffffcf`、`0xffffff88`、`0xfffff0ff` | PLM **内容** |
| `0x170000a1` | 识别 GA100 硅片的 `PMC_BOOT_0` 值 |

---

## 交叉参考：哪个补丁或工具碰哪个寄存器

| 补丁 / 工具 | 写的寄存器 | 读的寄存器 |
|---|---|---|
| `0001-sec2-postbl-plm-ss-cfg.patch`（master） | `0x001fa7cc`、`0x009a0148`、`0x001fa7c4`、`0x00823804`（PLM）；`0x001fa824`、`0x001fa828`（重新武装）；`0x0082381c`、`0x00823820`、`0x009a0204`、`0x00100ce0`（解锁） | 上面全部，加 GSP 静态信息 `fb_length` 和最后 FB 区域的 `limit`、`reserved`、`supportCompressed`、`supportISO`、`performance`（= 20） |
| `0002-booter-verify.patch` | 无 | `0x00823804`、`0x0082381c`、`0x00823820`、`0x009a0204`、`0x00100ce0`（项目自己的规范五寄存器验证行） |
| `0003-late-pma.patch` | 无 | 用 `0x200000000`（8 GiB）拆分点于出厂区域和晚期-PMA 扩展之间、**对两个 SKU 都如此**，包括真实出厂大小是 `0x280000000` 的 10 GB 卡 |
| `0004-bar0-pramin-clamp.patch` | 无 | 当 `0x20C2` 和 `0x2082` 上 `Ram.fbAddrSpaceSizeMb > 0x2000` 时把 PRAMIN 窗口钳到 `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)` |
| `0005-ce-scrub-workarounds.patch` | 无 | 强制 `NV_MMU_PTE_KIND_GENERIC_MEMORY` 并禁用两个设备 ID 上的虚拟模式 CE 清扫 |
| `0006-persistent-sw-state.patch` | 无 | 为 `0x20C2` 和 `0x2082` 设置 `NV_FLAG_PERSISTENT_SW_STATE` |
| `0007-pcie-gen2.patch`（分支） | 23 条目 `xp3gTable`，加 `0x0008860c`、`0x0008841c`、`0x00088610`、`0x000880a8`、`0x0008c2c0`、`0x0008c040`、`0x0008c1c0`、`0x0008872c` | `0x00088084`、`0x000880a4`、`0x00088088`、`0x0082057c`、`0x00820580`、`0x00820520`、`0x0008e1b0` |
| `0008-pcie-gen2-probe-retrain.patch`（分支） | BAR0 `0x8c2c0`、`0x8c040`、`0x8872c`；GPU 和桥上的 PCIe 能力 `LNKCTL2`；仅桥上的 `LNKCTL` Retrain Link | GPU `LNKSTA`，以 100 ms 轮询 20 次 |
| 分支 `80` 补丁 `0001` | 与 master 相同，除了 10 GB 路径上 `cfg1Value = 0x02779000U` 和 `targetFbBytes = 0x0000001400000000ULL` | |
| Gen2 家族补丁 `0001` | master 的四个 PLM 加 `0x00088ff4`、`0x00088ab4`、`0x00088ff8`、`0x00823b00`、`0x008200fc` | |
| `probe.sh` / `ga100_topology_report.py` | 无 | `0x00000000`、`0x00820350`、`0x00820c1c`、`0x008205c4`、`0x00120078`、`0x00022430`、`0x00001404`、`0x00118f78`、`0x008204d8`、`0x008204bc`、每-GPC `OPT_DISABLE` / `RECONFIG` / `CTRL_OPT` / `STATUS` / `RECONF_OVR`；`FBPA_BASE = 0x900000`、`FBPA_STRIDE = 0x4000` |
| `nuke.sh` | 每周期三写 ROP，全部目标 `0xffffffff` | 26-PLM 候选集 |
| `refire_chain_v2/v6/v9.py` | `0x001fa824`（teardown `0x1ffffe00`）、FB-geo PLM 集、`0x009a0204`、一个变体里 `0x00820520` | 就绪门 `0x009a0204`、`0x008403c4` |
| `geo_flr_survival_map_20260716.sh`、`plm_flr_survival_20260716.sh`、`fire_vram_featovr_sweep.sh` | 打开 PLM，然后 FLR | 整个 26 寄存器 PLM 调查 |

---

## FLR 存活表

这是塑造整个项目的那种不对称：算力比显存早几周出货，因为算力状态在常电岛里、显存状态不在。

| 寄存器 | 挺过 FLR？ | 证据 |
|---|---|---|
| `0x0082381c`（SS0） | **是** | 一张 10 GB 卡上前后测量 |
| `0x00823820`（SS1） | **是** | 相同 |
| `0x00823804`（`FEAT_OVR_PLM`） | **是** | 26 寄存器调查里唯一标为 AON 的 PLM |
| `0x00823b00`（行重映射器 PLM） | 大概 | 一次 in-HS 扫描在 FLR 后读 `0xffffffff`，但打开它没让几何布局持久 |
| `0x009a0204`（CFG1） | **否** | `0x02779000` 回退到 `0x02449000` |
| 每-FBPA CFG1 | **否** | 同一次扫描 |
| 每-FBPA CSTATUS | **否** | 相同 |
| `0x00100ce0`（LMR） | **否** | `0x20b` 回退到 `0x288` |
| FB-几何 PLM | **否**（它们重新锁上） | |
| `0x001180f0`（AON LMR 影子） | **否**（尽管常开却回退） | |
| `0x008403c4`（SEC2 复位 PLM） | **被清到** `0xff` | FLR 移除 `0x8f` HS 污染 |

几何布局**确实**挺过一次无次级总线复位的驱动卸载重载：卸载后 `0x009a0204` 仍读 `0x02669000`、`0x00100ce0` 仍读 `0x0000028a`，而一次新加载再次枚举 40960 MiB。完整复位路径（PERST、`nvidia-smi --gpu-reset`、`echo 1 > /sys/bus/pci/devices/<bdf>/reset`）用锁定的 CMP 表重跑签名的 DevInit、丢弃一切。

---

## 你可能在这些寄存器旁看到的状态码

| 码 | 在哪 | 含义 |
|---|---|---|
| `0xffff` | `kgspExecuteBooterLoad_TU102` 返回 | **每次**载荷运行都返回、无论成败。寄存器回读是唯一有效判决 |
| `0x31` | SEC2 `MAILBOX0` | 跳过 `report_status` 的原始退出路径上、未被触碰的驱动植入参数，**不是** Booter 错误码 |
| `0x15` | Booter 状态 | CSB 访问错误 |
| `0x29` | Booter 状态 | `check_1180f8_nibbles (0x1c75)` 门处 `0x001180f8` 位 [31:28] 非零 |
| `0x88` | Booter 状态 | `check_1180f8_2724 (0x1ba3)` 处 `0x001180f8` 位 [27:24] 非零 |
| `0x5` | Booter 状态 | `wpr_region_check (0x28ac)` 失败，包括空区域 |
| `0x47` | Booter 状态 | 栈检查失败 |
| `0x59` | 驱动日志 | `dmem.bin` 缺失、良性 |
| `0x62` | CPU-RM | `NV_ERR_RESET_REQUIRED`；`RmInitAdapter` 三元组 `(0x62:0x40:2028)` 是 WPR2-already-up 情形。作为 Booter `MAILBOX0` 码、`0x62` 反而属于 PKA 路径 |
| `0x65` | 驱动 | `NV_ERR_TIMEOUT`，第 3 阶段交接轮询超时 |
| `0x96` | Booter 状态 | 正常 |
| `0x24` / `0x25` | CPU-RM | `kbusVerifyBar2` 失败 / 到达 StateLoad；CFG1-对-LMR 判别器 |
| `Xid 31`、`Xid 154`、`Xid 119` | 内核 | `80` 分支上超过约 40 GB 的致命 GPU 丢失；80 GB 下的多上下文失败；GSP RPC 超时 |

每个该做什么见[排障](../procedures/troubleshooting.md)。

---

## 相关页面

- [解锁如何工作](how-it-works.md) 和[概述](overview.md)
- [权限级别掩码](privilege-level-masks.md)、[Falcon 与 Booter](falcon-and-booter.md)、[ROP 链](rop-chain.md)
- [显存几何布局](memory-geometry.md)、[算力节流](compute-throttle.md)、[PCIe Gen2](pcie-gen2.md)、[驱动补丁](driver-patches.md)
- [熔丝与 OTP](../hardware/fuses-and-otp.md)、[显存子系统](../hardware/memory-subsystem.md)、[PCIe 子系统](../hardware/pcie-subsystem.md)
- [术语表](../start/glossary.md) 了解 PLM、FLR、WPR、FBPA、LMR、AON、HS、PL0/PL3
- [寄存器索引](../appendix/register-index.md) 看扁平字母序地址清单
