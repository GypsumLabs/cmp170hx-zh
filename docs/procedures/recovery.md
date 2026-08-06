# 恢复

**本页覆盖内容。** 当一张 CMP 170HX 无法初始化时如何把它弄回工作状态：从最便宜到最激烈的复位阶梯、冷启动做了热重启不做的事、FLR 清除什么、只有次级总线复位（SBR）清除什么、每种复位恰好留下哪种寄存器状态、如何移除打过补丁的模块并恢复出厂系统，以及对真实变砖风险的诚实评估。

**短答案。** 解锁写寄存器。它不写熔丝、不写 VBIOS、不写 EEPROM，在已发布的工具上也不写固件文件。它碰到的每个几何寄存器都是易失的，断电即回退，这意味着**一张无法起来的卡几乎总可以通过断电恢复**。整个语料库里从未确认过永久变砖。一份一手报告与"无持久状态"模型相矛盾，已在下文[变砖风险](#变砖) 里诚实记录；它至今仍未解释。

如果你只有一分钟：关闭机器、关掉 PSU 开关或拔掉插头、等 60 秒、重新上电。那单一动作解决绝大多数卡死。

---

## 1. 复位阶梯 { #reset-ladder }

往下走这张清单。每级都比上一级更具破坏性，而每一级只在前一级失败时才值得试。

| # | 级 | 命令 | 清除什么 |
|---|---|---|---|
| 1 | 重载驱动 | `modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia && modprobe nvidia` | 仅驱动侧软件状态 |
| 2 | 功能级复位（FLR） | `sudo rmmod nvidia_uvm nvidia`；`echo 1 \| sudo tee /sys/bus/pci/devices/$BDF/reset` | 引擎、WPR2、PL0 临时区、SEC2 复位-PLM 污染、Falcon IMEM 内容；**重新感测熔丝** |
| 3 | PCI 分离与重扫 | 见[3.4](#分离与重扫) | 读取 BAR0 `0xffffffff` 的掉总线卡；之后必须恢复总线主控 |
| 4 | 次级总线复位（SBR） | 在上游桥上发出 | 一切 FLR 清除的、**加**常电（AON / PGC6 "GC6 island"）功率域 |
| 5 | 完全断电冷启动 | PSU 开关关闭或拔掉线缆、等 60 s | 一切，包括电容持有的状态 |
| 6 | 物理移除卡 | 把它拿出放置一段时间 | 最后手段；在一个无法解释的案例里用过一次 |

第 2 级完整：

```bash
sudo rmmod nvidia_uvm nvidia
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
```

第 5 级在实践中是主要恢复工具。记录的一手建议很直白："lots of cold boots required from the way this gets wedged"（鉴于它卡死的方式，需要大量冷启动），同时建议关机时把 PCIe 电源从卡上拔掉。

**为什么阶梯既有 FLR 又有 SBR。** FLR 复位引擎却**不**复位 AON 岛，所以一个根植于 AON 临时区的 `0x65` 卡死能挺过 FLR，而 SBR 会清除它。见[FLR 对比 SBR](#flr-对比-sbr)。

*（置信度：阶梯本身高；AON 机制中等。）*

---

## 2. 冷启动对比热重启 { #cold-boot }

**热重启不是一次复位。** 它让 WPR2 保持 up，板卡电容保持充电。已发布流程里所有在一次失败解锁后要求的 "a reboot" 都指**冷**重启，而这一区别至关重要：同一个挺过五次 `reboot` 循环的症状，常常在第一次真正的断电循环时被清除。

### 流程 { #cold-boot-procedure }

```bash
sudo systemctl poweroff
```

1. 等完全关机。SSH 掉线、风扇停。
2. 关掉 PSU 开关，或拔掉电源线缆。
3. **等 60 秒** 让电容放电、WPR2 复位。
4. 重新插上并上电。

60 秒等待在已发布指南的每个阶段都被规定为硬性要求，而且它与已发布的补丁的 WPR2 保存-恢复行为一致。同一个流程对 PLM-not-opened 和 VRAM-still-8-GB 两种症状也都如此规定。

有些卡在冷启动后还额外需要物理拔下并重插它们的 PCIe 电源线缆才肯正常。那是报告的摩擦、不是解释的机制。

### 何时冷启动是强制而非建议 { #cold-boot-required }

* 一次不解锁的首次引导之后。一次 OS 重启明确不够。
* `[WARN] Modules installed but the running driver is still stock` 之后。
* 一次 `GSP didn't boot` / 状态 `0x65` 失败之后。一位测试者确认仅移除旧内核模块不够。
* 首次安装打过补丁的模块之后（仅分支 `verify.sh` 在自己的失败字符串里这么说："Cold reboot if modules were just installed."）。
* 过度配置的 80 GB 配置的尝试之间，那里一位测试者不得不冷循环整个系统、而不只是重载驱动。

---

## 3. 详解复位 { #resets }

### 3.1 功能级复位（FLR） { #flr }

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sleep 3
```

FLR 抹掉 PL0 临时区写并**重新感测熔丝**。一次普通 `modprobe` 重载不会抹掉配置空间写，FLR 会。这曾用 `0x14A0` 处的 PL0 scratchpad 作代理测试，并得到利用原始作者的佐证。

**一次成功的 FLR 确实清除 WPR2。** `WPR2_LO` / `WPR2_HI` / GSP 邮箱的分阶段测量：

| 阶段 | WPR2_LO | WPR2_HI | GSP 邮箱 |
|---|---|---|---|
| 冷启动（WPR2 禁用） | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| ROP 发射后（Booter 设置了它） | `0x01F77000` | `0x01FFEE00` | `0x8FAE1000` |
| FLR 之后 | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| 随后加载出厂驱动 | `nvidia-smi` 工作、8192 MiB | | |

FLR 也清除 SEC2 复位-PLM 污染：`0x8f` 变成 `0xff`。

**FLR 把 Booter 从 Falcon IMEM 移除。** FLR 后写 DMEM、`EXCI 0x0a (MISS_INS)` 恰好意味着那个：Booter 不再驻留，因为 FLR 移除了它。

### 3.2 次级总线复位（SBR） { #flr-vs-sbr }

SBR 在上游桥而非设备上发出，它掉电并重新初始化 FLR 不去碰的常电功率域。

**为什么 FLR 有时无法恢复一个 `0x65` 卡死。** `SECURE_SCRATCH_14`（`0x001180f8`）住在 PGC6 "GC6 island" 常电功率域、被标为 RW-4R（priv-masked）。AON 临时区挺过引擎复位和 FLR，所以一个 un-DONE 的交接，加上会让 Booter 自己对 `0x1180f8` 的 DIO 读返回 `0xdead5ec1` 的毒化 PLM 和特权状态，会径直挺过 FLR。SBR 掉电并重新初始化 AON 功率域、清除临时区、让一次新鲜的 Booter 能跑第 3 阶段并自己设 DONE。

*（置信度：中等。经验模式 "FLR 不清除它、SBR 清除" 被反复观察；附带的 AON / GC6 描述未被验证。）*

### 3.3 每种复位留下什么 { #state-persistence }

这张表是本页核心。它既解释了解锁为何不持久、又解释了卡为何难以永久损坏。

| 状态 | 挺过 `modprobe` 重载 | 挺过 FLR | 挺过 SBR | 挺过断电循环 |
|---|---|---|---|---|
| SS0 `0x0082381c` = `0x88888888` | 是 | **是**（AON） | 未确立 | 否 |
| SS1 `0x00823820` = `0x00000008` | 是 | **是**（AON） | 未确立 | 否 |
| `FEAT_OVR_PLM` `0x00823804` | 是 | **是**（AON） | 未确立 | 否 |
| CFG1 `0x009a0204` | 是 | 否 | 否 | 否 |
| 每-FBPA CFG1（`0x00900204 + n*0x4000`） | 是 | 否 | 否 | 否 |
| CSTATUS_RAMAMOUNT | 是 | 否 | 否 | 否 |
| MMU LMR `0x00100ce0` | 是 | 否 | 否 | 否 |
| FB-几何 PLM | 是 | 否 | 否 | 否 |
| AON LMR 影子 `0x001180f0` | 是 | 否 | 否 | 否 |
| WPR2 边界 `0x001fa824` / `0x001fa828` | 是 | **否**、复位到 `0x1FFFFE00` / `0x0` | 否 | 否 |
| SEC2 复位-PLM 污染（`0x8f`） | 是 | **否**、回到 `0xff` | 否 | 否 |
| `SECURE_SCRATCH_14` `0x001180f8`（AON） | 是 | **是** | **否** | 否 |
| Falcon IMEM 内容（Booter 驻留） | 是 | 否（`EXCI 0x0a`） | 否 | 否 |
| PL0 临时区（代理 `0x14A0`） | 是 | 否 | 否 | 否 |
| PCI `COMMAND.BusMaster` | 被 `rmmod nvidia` 清除 | 复位到默认 | 复位 | 复位 |
| 熔丝 | 是 | **重新感测**、值不变 | 重新感测 | 重新感测 |
| VBIOS、EEPROM、磁盘上固件 | 是 | 是 | 是 | **是** |

**两个后果直接随之而来。**

*算力先于显存发布，就是因为 FLR 不对称。* SS0、SS1 和特性覆盖 PLM 坐在常电岛里、挺过 FLR，整个显存几何布局却不挺。这就是旧 FLR 系流水线能跨复位解锁算力、却每次丢掉几何布局的原因，也是已发布的补丁要在**一次** GSP 引导里、中间不带复位地打开 PLM 并写几何布局的原因。见[显存几何布局](../unlock/memory-geometry.md) 和[算力节流](../unlock/compute-throttle.md)。

*解锁写的任何东西都不挺过断电循环。* 一张断电的卡回来是出厂状态。这是下面变砖评估背后唯一、也最重要的一个事实。

### 3.4 卡掉下总线 { #detach-rescan }

如果 BAR0 读 `0xffffffff`，卡掉线了。分离并重扫，然后恢复总线主控：

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/remove
echo 1 | sudo tee /sys/bus/pci/rescan
sudo setpci -s ${BDF#0000:} COMMAND=0x0546
```

`setpci` 这一步很关键。`0x0546` 设了位 2（Bus Master）；`0x0102` 没有，而一张总线主控关闭的卡，在独立工具朝它发射时会静默什么都不做，日志里任何地方都没有 DMA 错误。完整失败模式见[总线主控被清除](troubleshooting.md#bus-master)。

如果卡完全不再出现、而且冷启动后也从不出现，原因可能是硬件而非状态。见[卡掉下 PCIe 总线](troubleshooting.md#off-bus) 看一次完全诊断的板级失败（一个把 `PS_5V_PGOOD` 短路的死 GS7155NVTD LDO）及其维修。

### 3.5 复位前拆掉驱动 { #teardown }

驱动持有设备时 FLR 不可靠。工作的拆掉顺序是：

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

nvidia 模块常常无论如何都拒绝卸载，留下 `nvidia 15835136 2`、`drm` 被包括 `i915` 在内的七个用户持有。那条依赖链，正是要在无头或非 NVIDIA 显示的主机上做解锁工作的一个实用原因。

### 3.6 一张预先卡死的卡 { #boot-pre-wedged }

如果机器无法关机、或卡在你干预前再次卡死，驱动在自动加载并重新卡死它。让卡断开引导、或从引导器命令行列入模块黑名单，然后清理：

```text
# GRUB 内核命令行，一次引导
modprobe.blacklist=nvidia,nvidia_uvm,nvidia_drm,nvidia_modeset
```

一张 10 GB 卡曾困在一个不可中断睡眠状态、挺过约五次冷重启并阻止 Ubuntu 关机。**原因是自动加载的补丁内核驱动，不是卡。** 让卡断开引导并做清理，解决了它。*（置信度：中等；受影响测试者在恢复后识别了根因。）*

---

## 4. 移除打过补丁的模块 { #remove }

### 4.1 受支持路径 { #remove-sh }

```bash
sudo ./remove.sh --yes
```

`remove.sh` 没有 `--yes` 或 `-y` 就拒绝运行。它跑五步，写 `logs/remove_YYYYMMDD_HHMMSS.log`，仓库目录不可写时回退到 `/tmp`。它做什么：

* 停止显示管理器、`modprobe -r` 失败时强制 `rmmod`。
* 停止、禁用并删除遗留 `/etc/systemd/system/cmpunlocker.service`、杀掉任何遗留 `/opt/cmpunlocker/daemon/watchdog.py` 进程。两者都是一个已废弃看门狗设计的遗存，当前安装器从不创建它们。
* 移除**每个内核**下的 `/lib/modules/*/updates/cmpunlocker/`、逐内核跑 `depmod -a`。
* 删除遗留 `/opt/cmpunlocker` 安装目录。
* 删除固件打补丁时代遗留：对每个 `/lib/firmware/nvidia/*/gsp_tu10x.bin` 移除 `.cmpunlocker.bak`、`.cmpunlocker.patched`、`.cmpunlocker.tmp`、`.cmpunlocker.cleanup` 和 `.cmpunlocker.pat`。
* 重建 initramfs 并重载出厂模块。

> [!CAUTION]
> **没有 `uninstall.sh`**
>
> `docs` 分支上的文档引用 `sudo ./uninstall.sh --yes`。**不存在这样的脚本**、在 master 或 docs 分支本身上都没有。正确命令是 `sudo ./remove.sh --yes`，而那个分支自己的 `ARCHITECTURE.md` 就这么说。

master 的 `remove.sh` **不**碰内核命令行。IOMMU 配置及其撤销存在于 `Gen2`、`far` 和 `deced` 分支上，那里 `remove.sh` 恢复 `*.cmpunlocker.bak` 并打印 `Reverted IOMMU kernel parameters (effective after reboot)` 或 `No IOMMU config backup found, kernel command line left as-is`。

以一次冷重启结束。然后确认出厂模块回来了：

```bash
cat /proc/driver/nvidia/version          # 应显示一个 dvs-builder 发布构建
sudo dmesg | grep SEC2_DEBUG             # 应打印不出东西
nvidia-smi                               # 8192 MiB 或 10240 MiB
```

见[卸载](uninstall.md)。

### 4.2 三层手动回滚 { #rollback-tiers }

每一层以一次冷重启结束。只有前一层没恢复一个可工作的出厂栈时才升级。

**第 1 层：手工撤销模块安装。**

```bash
sudo systemctl stop nvidia-persistenced
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo rm -rf /lib/modules/$(uname -r)/updates/cmpunlocker/
sudo depmod -a
# 恢复备份的出厂商 nvidia.ko，然后：
sudo apt install --reinstall nvidia-driver-610-open
```

**第 2 层：** `sudo ./remove.sh --yes`。

**第 3 层：** 完全移除 610 栈并安装 580。

### 4.3 撤销先前的实验 { #undo-experiments }

一台用于解锁开发的机器会积累静默破坏一次干净安装的状态。重装前撤销全部：

* 删除 `/etc/modprobe.d/blacklist-nvidia-manual.conf`。
* 移除任何 dpkg diverts。
* 恢复 `nvidia-lib-bak`。
* 从 `/lib/firmware/nvidia/610.43.03/` 和 `/lib/firmware/nvidia/580.173.02/` 下的 `.stock` / `.backup` / `.bak` 副本恢复出厂 `gsp_tu10x.bin`。

> [!CAUTION]
> **一个陈旧的已补丁 `gsp_tu10x.bin` 毒化驱动内解锁**
>
> 如果这台机器用过固件打补丁前身，在跑驱动内补丁**之前**恢复出厂 blob：
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
> ```
>
> 驱动在引导时把固件的签名保存为 "stock"。如果固件仍被打过补丁，它保存**利用载荷**、随后一次干净的 GSP-RM 引导就 DMA 错误的 ROP 链。事后要找的成功行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

### 4.4 恢复版本匹配的固件目录 { #restore-firmware }

一个被删除或不匹配的 `/lib/firmware/nvidia/<version>/` 目录会产生一个看起来像渐进硬件退化的失败。一次无法复现的多日 "model degradation"，最终查明是 `/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` 被删除，再加上一个不会在一个 `.03` 模块上触发 GPU init 的 `.04` 用户态 `nvidia-smi`。那种状态下 `SEC2 MBOX0 = 0x0` 意味着 Booter 根本没加载。恢复版本匹配的固件目录立即复现先前工作状态。

保留任何驱动修改的 diff 或变更日志。重装一个新驱动静默丢弃每次需要的注入。

### 4.5 回到一张出厂、从未碰过的卡 { #restore-stock }

硬件里没有任何要撤销的东西。解锁是主线上 NVIDIA 驱动之上的一个补丁、不是固件替换，所以一旦打过补丁的模块消失、机器经历过断电循环，卡逐位就是开始时的卡：CFG1 `0x02449000`、LMR `0x00000208` 或 `0x00000288`、每-FBPA `CSTATUS_RAMAMOUNT` `0x200`、SS0 回到它的锁定值。

卡也在**出厂** Linux NVIDIA 驱动上、完全不带补丁地运行（Ubuntu 24.04 上 `nvidia-driver-570` 加 CUDA 12.8 开箱即用，Ubuntu 22.04 上 `nvidia-driver-535-server` 也被报告过），报告为 `NVIDIA Graphics Device`、计算能力 8.0。能被驱动和能被解锁是两回事，而确认前者是证明卡挺过了你做的任何事的好方法。

---

## 5. 到底有多少变砖风险？ { #bricking }

### 5.1 证据 { #bricking-evidence }

**语料库任何地方都从未确认永久变砖。** 具体声称及其处置：

| 声称 | 处置 |
|---|---|
| 净室工作期间一张卡被变砖 | 一个 LLM 代理在忘了卡可以复位后得出的错误结论 |
| "CMP 170HX 卡被解锁或 NVIDIA 下毒驱动变砖" | 不存在一手报告。被引用的具体公开案例被评估为一张被推到 80 GB 的 10 GB 卡 |
| 一次主板 PCH 失败由 170HX 测试引起 | 原帖用了 "coincidentally" 这个词；没有确立因果机制。只记录为风险轶事 |
| 2026 年 7 月下旬涨价期间卖家描述 "defective batch"（有缺陷批次） | 用作对已展示过可工作卡的列表的取消借口。记录在案的案例里没有发出或诊断过有缺陷的卡 |

结构论证比报告缺失更强。已发布的解锁：

* 只写易失寄存器，全部断电回退；
* 不烧熔丝（主灭杀熔丝 `0x008203f0` 读 `0x00000000` 且从不写）；
* 不刷 VBIOS 或任何 EEPROM；
* 在已发布的工具上不修改 `/lib/firmware` 下任何文件（更早的固件打补丁一代确实改、这正是 `remove.sh` 仍为它清理的原因）；
* 被 `remove.sh` 加一次断电循环完全还原。

### 5.2 那份对不上号的报告 { #bricking-contradiction }

> [!NOTE]
> **未解问题**
>
> 一份一手描述一张 10 GB 卡困着三个卡住的 D 状态线程、FLR、SBR、PCI 分离重挂**或一次完整的 PSU 断电冷启动**都无法清除："when I rebooted, the registers were still written, and the D-threads were still there... card booted pre-wedged"（我重启时寄存器仍写着、D 线程也还在……卡以预先卡死状态启动）。恢复最终需要按住电源开关、关掉插线板、并物理移除卡几个小时。
>
> 该观察在频道内被质疑、仍无法解释。它**矛盾**那其它方面证据充分的 "mod 不改持久状态" 模型，这正是它值得解决而非丢弃的原因。当时提出的原因是 "booting a patched proprietary blob for cpu rm after a driverless payload delivery"（一次无驱动载荷投递后为 cpu rm 引导一个打过补丁的专有 blob）。同一份描述的另外两个卡死：一个由代理写 `FUSE_SS_PLM` 风格寄存器引起（需要一次完整断电循环）、一个来自 "enter `0x10aa` at `0x10b9`" 硬变砖了一个测试台。
>
> 什么能定论它：一次这样冷启动后立即的寄存器值新鲜捕获、带一张功率状态照片。

在那解决之前，诚实的话是：**模型说断电循环总是赢、在每个可复现案例里它也的确赢了，但一位可信操作者报告了一个挺过它的状态。**

### 5.3 真实风险实际上是什么 { #real-risks }

最接近工作的人点名的残余风险并不稀奇：

1. **普通二手硬件故障。** 这些是退役矿卡。语料库里那个完全诊断的永久性外观失败是一颗板上死的 3.3 V LDO、与解锁完全无关，而且可以在元件级修复。见[卡掉下总线](troubleshooting.md#off-bus)。
2. **补丁集在积极变化。** 破坏安装的是分支变动、不是硅片。
3. **HBM 的热损坏。** 长期欠冷退化 HBM。记录里那个失败的老化测试卡带显存超频在 85 °C 运行；无错误卡停在 73 °C 以下。*（置信度：中等；不存在失效率数据。）* 见[热设计](../hardware/thermals.md)。
4. **让卡跑在稳定几何布局之外。** 8 GB 卡在 64 GB 稳定且在产；10 GB 卡在 40 GB 稳定；10 GB 卡在 80 GB 报告容量、超过约 40 GB 却不可用：触碰更多的内核造成致命 GPU 丢失、与功耗上限无关。报告的 Xid 码包括 Xid 31（被描述为无害）和 CUDA 显存测试后的 Xid 154；主导报告症状是挂起、连同老化测试错误。Xid 31 单独是旁观者提出的，并未被带故障卡的操作者佐证为*那个*签名。它毁的是工作负载，不是卡。见[80 GB](../frontier/80gb.md)。
5. **活任务的操作者错误。** `kill -9` 活的多卡任务卡死主机 CUDA 运行时（约 32 个僵尸进程、`cuInit` 返回 999）并需要主机重启。对一个验证内核 SIGKILL 可能以 Xid 45 卡死卡。在一次完整的 8 卡会话里、数百个 60 秒健康样本中、只要工作负载被正确驱动就有 **0** 个硬故障。

> [!CAUTION]
> **真实硬件风险在哪**
>
> 这个项目里唯一有真正、不可逆硬件风险的地方是**电容改装**：24 × 0402 220 nF X7R 部件手工焊在 C1100 到 C1350 范围、在一块需要 420 °C 热风 2 分钟才能把芯片抬起来的 8 到 12 层板上。那是焊接风险、不是固件风险，在[物理改装](../operations/physical-mods.md) 里单独覆盖。还要注意电容改装只改通道**数**。它从不改变 PCIe 代数。

### 5.4 一个实用安全姿态 { #posture }

* 保持卡的出厂行为可验证：开始前知道它能在一颗未打补丁的出厂商驱动上枚举并运行。
* 优先无头或非 NVIDIA 显示的主机，这样模块才能真的卸载。
* 在实用处、在 VM 或容器里做解锁开发。一位开发者报告在裸机上每次搞砸 `nvidia.ko` 部署后就需要重装操作系统。
* 把驱动钉在 610、作为对未来 NVIDIA 发布堵上这个洞的长期预防，就像 P100 和 V100 用户钉在约 580 那样。*（置信度：中等；理性建议，目前还不需要，因为没有阻断性的驱动存在。）*
* 不要 `kill -9` 活任务。不要在你关心的硬件上跑过度配置的几何布局。
* 求助前，捕获 `sudo dmesg | grep SEC2_DEBUG` 和最新的安装日志。见[升级](troubleshooting.md#escalation)。

---

## 相关页面

* [排障](troubleshooting.md)：症状到原因到修复、已索引
* [卸载](uninstall.md)：完整 `remove.sh`
* [安装](install.md)：受支持安装流程
* [验证](verify.md)：确认一个良好状态
* [Risks](../start/risks.md)：这份评估的方向层面版本
* [权限级别掩码](../unlock/privilege-level-masks.md)：哪些 PLM 是 AON、哪些不是
* [显存几何布局](../unlock/memory-geometry.md)：为什么几何布局不挺过复位
* [寄存器参考](../unlock/register-reference.md)：本页命名的每个寄存器
