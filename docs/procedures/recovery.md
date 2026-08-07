# 恢复

**本页涵盖内容。** 当一张 CMP 170HX 无法初始化时，如何让它恢复到可工作状态：从成本最低到最激进的复位阶梯；冷启动会做而热重启不会做的事情；FLR 会清除什么、只有次级总线复位（SBR）才会清除什么；每种复位分别会保留哪些寄存器状态；如何移除打过补丁的模块并恢复出厂系统；以及对实际变砖风险的诚实评估。

**简短结论。** 解锁过程会写入寄存器，但不会写入熔丝、VBIOS、EEPROM，也不会在当前发布版工具中写入固件文件。它触及的所有显存几何布局寄存器都是易失的，断电后会恢复，这意味着**一张无法正常启动的卡几乎总能通过断电恢复**。整个资料库中从未确认过永久变砖的情况。一份一手报告与“没有持久状态”的模型相矛盾，本文已在下方的[变砖风险](#bricking)中如实记录；该报告至今仍无法解释。

如果你只有一分钟：关闭机器，关掉 PSU 开关或拔掉电源线，等待 60 秒，然后重新上电。这个单一操作可以解决绝大多数卡死问题。

---

## 1. 复位阶梯 { #reset-ladder }

按下面的清单逐级尝试。每一级都比上一级更具破坏性，只有前一级失败时才值得尝试下一级。

| # | 级别 | 命令 | 清除内容 |
|---|---|---|---|
| 1 | 重载驱动 | `modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia && modprobe nvidia` | 仅驱动侧软件状态 |
| 2 | 功能级复位（FLR） | `sudo rmmod nvidia_uvm nvidia`；`echo 1 \| sudo tee /sys/bus/pci/devices/$BDF/reset` | 引擎、WPR2、PL0 临时区、SEC2 复位 PLM 污染、Falcon IMEM 内容；**重新感测熔丝** |
| 3 | PCI 分离并重扫 | 见[3.4](#detach-rescan) | BAR0 读取为 `0xffffffff` 的掉线卡；之后必须恢复总线主控 |
| 4 | 次级总线复位（SBR） | 在上游桥上发出 | FLR 清除的全部内容，**以及**常电（AON / PGC6 “GC6 island”）功率域 |
| 5 | 完全断电冷启动 | 关闭 PSU 开关或拔掉电源线，等待 60 s | 一切状态，包括电容保持的状态 |
| 6 | 物理移除显卡 | 将显卡移出并放置一段时间 | 最后手段；曾在一个无法解释的案例中使用过一次 |

第 2 级的完整操作：

```bash
sudo rmmod nvidia_uvm nvidia
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
```

实践中，第 5 级是主要的恢复手段。记录在案的一手建议非常直接：“lots of cold boots required from the way this gets wedged”（按照它进入卡死状态的方式，需要进行多次冷启动），同时还建议在关机时拔掉显卡上的 PCIe 电源线。

**为什么复位阶梯同时包含 FLR 和 SBR。** FLR 会复位引擎，但**不会**复位 AON 常电域，因此根植于 AON 临时区的 `0x65` 卡死状态可以挺过 FLR，而 SBR 会清除它。见[FLR 与 SBR 的区别](#flr-vs-sbr)。

*（置信度：复位阶梯本身为高；AON 机制为中。）*

---

## 2. 冷启动与热重启 { #cold-boot }

**热重启不是一次复位。** 热重启会保留 WPR2 处于启用状态，并让板卡电容继续带电。所有已发布流程在解锁失败后要求的“重启”，实际都指**冷启动**；这个区别至关重要：同一个能挺过五次 `reboot` 循环的症状，往往会在第一次真正的断电循环中被清除。

### 操作流程 { #cold-boot-procedure }

```bash
sudo systemctl poweroff
```

1. 等待系统完全关机。SSH 连接断开，风扇停止。
2. 关掉 PSU 开关，或拔掉电源线。
3. **等待 60 秒**，让电容放电并使 WPR2 复位。
4. 重新插上电源并开机。

已发布指南的每个阶段都把这 60 秒等待规定为硬性要求，这也与当前发布版补丁对 WPR2 的保存与恢复行为一致。对于 PLM 未打开和 VRAM 仍为 8 GB 这两种症状，同样规定必须执行这一流程。

有些卡在冷启动后还需要物理拔下并重新插好 PCIe 电源线，之后才能恢复正常。这是报告中提到的实际操作障碍，不是已经解释清楚的机制。

### 冷启动何时是强制要求，而不是建议 { #cold-boot-required }

* 第一次启动但未完成解锁之后。仅重启 OS 明确不够。
* 出现 `[WARN] Modules installed but the running driver is still stock` 之后。
* 出现 `GSP didn't boot` / 状态 `0x65` 失败之后。一名测试者确认，仅移除旧内核模块并不足够。
* 首次安装打过补丁的模块之后（仅某些分支中的 `verify.sh` 在自己的失败字符串中明确写道：“Cold reboot if modules were just installed.”）。
* 尝试过度配置的 80 GB 几何布局期间，每次尝试之间都需要冷循环整个系统，而不只是重载驱动；一名测试者不得不这样做。

---

## 3. 详细了解复位 { #resets }

### 3.1 功能级复位（FLR） { #flr }

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sleep 3
```

FLR 会抹除 PL0 临时区写入，并**重新感测熔丝**。普通的 `modprobe` 重载不会抹除配置空间写入，而 FLR 会。这一结论曾使用 `0x14A0` 处的 PL0 临时区作为代理进行测试，并得到该漏洞原始作者的佐证。

**一次成功的 FLR 确实会清除 WPR2。** 对 `WPR2_LO` / `WPR2_HI` / GSP 邮箱的分阶段测量如下：

| 阶段 | WPR2_LO | WPR2_HI | GSP 邮箱 |
|---|---|---|---|
| 冷启动（WPR2 禁用） | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| ROP 链执行后（Booter 已设置） | `0x01F77000` | `0x01FFEE00` | `0x8FAE1000` |
| FLR 之后 | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| 随后加载出厂驱动 | `nvidia-smi` 正常工作，8192 MiB | | |

FLR 还会清除 SEC2 复位 PLM 污染：`0x8f` 会变为 `0xff`。

**FLR 会从 Falcon IMEM 中移除 Booter。** FLR 后写入 DMEM 再出现 `EXCI 0x0a (MISS_INS)`，含义正是如此：Booter 不再驻留，因为 FLR 将其移除了。

### 3.2 次级总线复位（SBR） { #flr-vs-sbr }

SBR 是在上游桥上而不是设备本身发出，它会关闭并重新初始化 FLR 不会触及的常电功率域。

**为什么 FLR 有时无法恢复 `0x65` 卡死状态。** `SECURE_SCRATCH_14`（`0x001180f8`）位于 PGC6 “GC6 island”常电功率域中，并标记为 RW-4R（priv-masked）。AON 临时区可以挺过引擎复位和 FLR，因此，一个未完成 DONE 的交接，加上使 Booter 自己对 `0x1180f8` 的 DIO 读取返回 `0xdead5ec1` 的受污染 PLM 和权限状态，会直接挺过 FLR。SBR 会关闭并重新初始化 AON 功率域，清除临时区，使新的 Booter 能够运行第 3 阶段并自行设置 DONE。

*（置信度：中。经验模式“FLR 不清除它，SBR 可以”已被反复观察；与之关联的 AON / GC6 描述尚未验证。）*

### 3.3 每种复位会留下什么 { #state-persistence }

这张表是本页的核心。它既解释了解锁为什么不具备持久性，也解释了显卡为什么很难被永久损坏。

| 状态 | 能挺过 `modprobe` 重载 | 能挺过 FLR | 能挺过 SBR | 能挺过断电循环 |
|---|---|---|---|---|
| SS0 `0x0082381c` = `0x88888888` | 是 | **是**（AON） | 尚未确定 | 否 |
| SS1 `0x00823820` = `0x00000008` | 是 | **是**（AON） | 尚未确定 | 否 |
| `FEAT_OVR_PLM` `0x00823804` | 是 | **是**（AON） | 尚未确定 | 否 |
| CFG1 `0x009a0204` | 是 | 否 | 否 | 否 |
| 每个 FBPA 的 CFG1（`0x00900204 + n*0x4000`） | 是 | 否 | 否 | 否 |
| CSTATUS_RAMAMOUNT | 是 | 否 | 否 | 否 |
| MMU LMR `0x00100ce0` | 是 | 否 | 否 | 否 |
| FB 显存几何 PLM | 是 | 否 | 否 | 否 |
| AON LMR 影子 `0x001180f0` | 是 | 否 | 否 | 否 |
| WPR2 边界 `0x001fa824` / `0x001fa828` | 是 | **否**，复位为 `0x1FFFFE00` / `0x0` | 否 | 否 |
| SEC2 复位 PLM 污染（`0x8f`） | 是 | **否**，恢复为 `0xff` | 否 | 否 |
| `SECURE_SCRATCH_14` `0x001180f8`（AON） | 是 | **是** | **否** | 否 |
| Falcon IMEM 内容（Booter 驻留） | 是 | 否（`EXCI 0x0a`） | 否 | 否 |
| PL0 临时区（代理地址 `0x14A0`） | 是 | 否 | 否 | 否 |
| PCI `COMMAND.BusMaster` | 被 `rmmod nvidia` 清除 | 复位为默认值 | 复位 | 复位 |
| 熔丝 | 是 | **重新感测**，值不变 | 重新感测 | 重新感测 |
| VBIOS、EEPROM、磁盘上的固件 | 是 | 是 | 是 | **是** |

**两个后果可以直接由此推出。**

*由于 FLR 的不对称性，算力解锁早于显存解锁发布。* SS0、SS1 和特性覆盖 PLM 位于常电域中，可以挺过 FLR；完整的显存几何布局却不能。因此，旧的基于 FLR 的流程可以跨越复位保持算力解锁，却每次都会丢失显存几何布局。这也是当前发布版补丁要在**一次** GSP 启动中打开 PLM 并写入显存几何布局、期间不插入复位的原因。见[显存几何布局](../unlock/memory-geometry.md)和[算力节流](../unlock/compute-throttle.md)。

*解锁写入的任何内容都无法挺过断电循环。* 断电后的显卡会以出厂状态回来。这是下方变砖评估背后唯一且最重要的事实。

### 3.4 显卡已从总线掉线 { #detach-rescan }

如果 BAR0 读取为 `0xffffffff`，说明显卡已经脱离总线。先分离并重扫，然后恢复总线主控：

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/remove
echo 1 | sudo tee /sys/bus/pci/rescan
sudo setpci -s ${BDF#0000:} COMMAND=0x0546
```

`setpci` 这一步很重要。`0x0546` 设置了第 2 位（Bus Master），而 `0x0102` 没有设置；总线主控关闭的显卡在独立工具向它发起操作时会静默地什么也不做，日志中也不会出现任何 DMA 错误。完整失败模式见[总线主控被清除](troubleshooting.md#bus-master)。

如果显卡完全不再出现，并且冷启动后也从未重新出现，原因可能是硬件而不是状态。见[显卡从 PCIe 总线掉线](troubleshooting.md#off-bus)，其中记录了一起完整诊断过的板级故障（一颗已损坏、导致 `PS_5V_PGOOD` 短路的 GS7155NVTD LDO）及其维修方法。

### 3.5 复位前拆除驱动 { #teardown }

驱动仍持有设备时，FLR 不可靠。可行的拆除顺序如下：

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

nvidia 模块经常无论如何都拒绝卸载，留下 `nvidia 15835136 2`，同时 `drm` 被包括 `i915` 在内的七个用户持有。这条依赖链正是应在无头主机或不使用 NVIDIA 显示输出的主机上进行解锁工作的实际原因之一。

### 3.6 一张启动前就已卡死的显卡 { #boot-pre-wedged }

如果机器无法关机，或者显卡在你来得及干预前再次卡死，说明驱动正在自动加载并让它重新进入卡死状态。让显卡断开连接后启动，或者从引导器命令行将模块列入黑名单，然后进行清理：

```text
# GRUB 内核命令行，仅对本次启动生效
modprobe.blacklist=nvidia,nvidia_uvm,nvidia_drm,nvidia_modeset
```

曾有一张 10 GB 卡卡在不可中断睡眠状态中，挺过了约五次冷重启，并阻止 Ubuntu 关机。**原因是自动加载的打过补丁的内核驱动，而不是显卡本身。** 让显卡断开连接后启动并完成清理，解决了问题。
*（置信度：中；受影响的测试者在恢复后确定了根因。）*

---

## 4. 移除打过补丁的模块 { #remove }

### 4.1 受支持的路径 { #remove-sh }

```bash
sudo ./remove.sh --yes
```

`remove.sh` 没有 `--yes` 或 `-y` 时会拒绝运行。它会执行五个步骤，并将日志写入 `logs/remove_YYYYMMDD_HHMMSS.log`；如果仓库目录不可写，则回退到 `/tmp`。它会执行以下操作：

* 停止显示管理器；如果 `modprobe -r` 失败，则强制执行 `rmmod`。
* 停止、禁用并删除遗留的 `/etc/systemd/system/cmpunlocker.service`，同时杀掉任何遗留的 `/opt/cmpunlocker/daemon/watchdog.py` 进程。这两者都是已废弃看门狗设计的遗留物，当前安装器从不会创建它们。
* 删除**每个内核**下的 `/lib/modules/*/updates/cmpunlocker/`，并针对每个内核运行 `depmod -a`。
* 删除遗留的 `/opt/cmpunlocker` 安装目录。
* 删除固件打补丁时代留下的文件：针对每个 `/lib/firmware/nvidia/*/gsp_tu10x.bin`，移除 `.cmpunlocker.bak`、`.cmpunlocker.patched`、`.cmpunlocker.tmp`、`.cmpunlocker.cleanup` 和 `.cmpunlocker.pat`。
* 重建 initramfs 并重新加载出厂模块。

> [!CAUTION]
> **不存在 `uninstall.sh`**
>
> `docs` 分支上的文档引用了 `sudo ./uninstall.sh --yes`。**不存在这样的脚本**，master 分支和 docs 分支本身都没有。正确命令是 `sudo ./remove.sh --yes`，该分支自己的 `ARCHITECTURE.md` 也是这样写的。

master 的 `remove.sh` **不会**修改内核命令行。IOMMU 配置及其撤销只存在于 `Gen2`、`far` 和 `deced` 分支；在这些分支中，`remove.sh` 会恢复 `*.cmpunlocker.bak`，并打印 `Reverted IOMMU kernel parameters (effective after reboot)` 或 `No IOMMU config backup found, kernel command line left as-is`。

最后执行一次冷重启，然后确认出厂模块已恢复：

```bash
cat /proc/driver/nvidia/version          # 应显示一个 dvs-builder 发布构建
sudo dmesg | grep SEC2_DEBUG             # 应不打印任何内容
nvidia-smi                               # 8192 MiB 或 10240 MiB
```

见[卸载](uninstall.md)。

### 4.2 三层手动回滚 { #rollback-tiers }

每一层都以一次冷重启结束。只有上一层没有恢复出可工作的出厂软件栈时，才升级到下一层。

**第 1 层：手动撤销模块安装。**

```bash
sudo systemctl stop nvidia-persistenced
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo rm -rf /lib/modules/$(uname -r)/updates/cmpunlocker/
sudo depmod -a
# 恢复备份的出厂 nvidia.ko，然后：
sudo apt install --reinstall nvidia-driver-610-open
```

**第 2 层：** `sudo ./remove.sh --yes`。

**第 3 层：** 完全移除 610 软件栈，并安装 580。

### 4.3 撤销之前的实验 { #undo-experiments }

用于解锁开发的机器会积累一些状态，这些状态会在不知不觉中破坏一次干净安装。重新安装前，全部撤销：

* 删除 `/etc/modprobe.d/blacklist-nvidia-manual.conf`。
* 移除所有 dpkg diverts。
* 恢复 `nvidia-lib-bak`。
* 从 `/lib/firmware/nvidia/610.43.03/` 和 `/lib/firmware/nvidia/580.173.02/` 下的 `.stock` / `.backup` / `.bak` 副本恢复出厂版 `gsp_tu10x.bin`。

> [!CAUTION]
> **陈旧的打过补丁的 `gsp_tu10x.bin` 会污染驱动内解锁**
>
> 如果这台机器曾使用过固件打补丁的前身版本，请在运行驱动内补丁之前恢复出厂 blob：
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
> ```
>
> 驱动会在启动期间将固件签名保存为“stock”。如果固件仍然打过补丁，它保存的会是**漏洞利用载荷**，随后干净的 GSP-RM 启动会 DMA 错误的 ROP 链。之后应查找的成功日志行是 `SEC2_DEBUG: saved stock signature (4096 bytes)`。

### 4.4 恢复版本匹配的固件目录 { #restore-firmware }

删除或不匹配的 `/lib/firmware/nvidia/<version>/` 目录会产生一种看起来像硬件逐渐退化的故障。一次无法复现的、多日持续的“模型退化”最终被查明，是因为 `/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` 被删除，同时用户态的 `.04` 版本 `nvidia-smi` 不会在 `.03` 模块上触发 GPU 初始化。在这种状态下，`SEC2 MBOX0 = 0x0` 意味着 Booter 根本没有加载。恢复版本匹配的固件目录后，之前的工作状态立即重新出现。

保留所有驱动修改的 diff 或变更日志。重新安装一个全新的驱动会悄无声息地丢弃每一处必需的注入。

### 4.5 恢复为出厂且从未改动过的显卡 { #restore-stock }

硬件中没有任何需要撤销的内容。解锁是叠加在主线 NVIDIA 驱动之上的补丁，而不是替换固件；因此，打过补丁的模块消失、机器完成断电循环后，这张卡就逐位恢复为你开始时的状态：CFG1 `0x02449000`，LMR `0x00000208` 或 `0x00000288`，每个 FBPA 的 `CSTATUS_RAMAMOUNT` 为 `0x200`，SS0 恢复为锁定值。

这张卡也可以在**出厂版** Linux NVIDIA 驱动上完全不使用补丁运行（Ubuntu 24.04 上的 `nvidia-driver-570` 加 CUDA 12.8 开箱即用；Ubuntu 22.04 上的 `nvidia-driver-535-server` 也有成功报告），系统会将其识别为 `NVIDIA Graphics Device`，计算能力为 8.0。能被驱动正常使用和完成解锁是两件不同的事；确认前者是证明显卡经受住你所做操作的好方法。

---

## 5. 实际变砖风险究竟有多大？ { #bricking }

### 5.1 证据 { #bricking-evidence }

**整个资料库中从未确认过永久变砖。** 对具体说法的处理如下：

| 说法 | 处理结论 |
|---|---|
| 一张卡在净室工作期间被变砖 | 一个 LLM 代理忘记了显卡可以复位，因而得出了错误结论 |
| “CMP 170HX 卡会因为解锁或被 NVIDIA 污染的驱动而变砖” | 没有一手报告。被引用的具体公开案例被评估为一张被推到 80 GB 的 10 GB 卡 |
| 一次主板 PCH 故障由 170HX 测试导致 | 原帖使用了“coincidentally”一词；没有确立因果机制。仅作为风险轶事记录 |
| 2026 年 7 月下旬价格上涨期间卖家描述“defective batch”（有缺陷批次） | 被用作取消已展示过可工作显卡的商品列表的借口。已记录案例中没有卡被发出或被诊断为有缺陷 |

结构性论证比“没有报告”更有说服力。当前发布版解锁：

* 只写入易失寄存器，所有这些寄存器都会在断电后恢复；
* 不会烧断熔丝（主灭杀熔丝 `0x008203f0` 读取为 `0x00000000`，且从未被写入）；
* 不会刷写 VBIOS 或任何 EEPROM；
* 当前发布版工具不会修改 `/lib/firmware` 下的任何文件（更早的固件打补丁版本确实会修改，这正是 `remove.sh` 仍会为其执行清理的原因）；
* 通过 `remove.sh` 加一次断电循环即可完全撤销。

### 5.2 那份不符合模型的报告 { #bricking-contradiction }

> [!NOTE]
> **未解问题**
>
> 一份一手报告描述了一张 10 GB 卡：它被三个卡住的 D 状态线程卡死，FLR、SBR、PCI 分离并重新挂接，**甚至完整的 PSU 断电冷启动**都无法清除这些状态： “when I rebooted, the registers were still written, and the D-threads were still there... card booted pre-wedged”（我重启时寄存器仍然被写入，D 状态线程也还在……显卡以启动前就已卡死的状态启动）。最终的恢复需要在插线板关闭的情况下按住电源开关，并将显卡物理移除数小时。
>
> 频道内有人质疑这一观察结果，它至今仍无法解释。它**与**其他方面证据充分的“该修改不会改变持久状态”模型相矛盾，这正是为什么值得解决而不是直接否定它。当时提出的原因是“booting a patched proprietary blob for cpu rm after a driverless payload delivery”（在无驱动载荷投递之后，为 CPU-RM 启动一个打过补丁的专有 blob）。同一份报告中还记录了另外两次卡死：一次由代理写入 `FUSE_SS_PLM` 风格的寄存器引起（需要完整断电），另一次则是因为“enter `0x10aa` at `0x10b9`”而让一台测试台永久变砖。
>
> 能够定论的方法是：在发生这种冷启动后立即重新采集寄存器值，并附上电源状态照片。

在问题解决之前，诚实的说法是：**模型认为断电循环总能解决问题，而且在每个可复现案例中确实如此；但一名可信的操作者报告了一个挺过一次断电循环的状态。**

### 5.3 实际风险究竟是什么 { #real-risks }

最接近这项工作的人指出的残余风险并不神秘：

1. **普通的二手硬件故障。** 这些是退役矿卡。资料库中唯一一个经过完整诊断、看起来像永久性故障的案例，是板上一颗损坏的 3.3 V LDO，与解锁完全无关，而且可以进行元件级维修。见[显卡掉线](troubleshooting.md#off-bus)。
2. **补丁集正在积极变化。** 破坏安装的是分支频繁变化，而不是晶片本身。
3. **HBM 的热损坏。** 长期冷却不足会使 HBM 退化。记录中那张失败的老化测试卡在 85 °C、显存超频的条件下运行；无错误的卡都保持在 73 °C 以下。*（置信度：中；没有失效率数据。）* 见[散热](../hardware/thermals.md)。
4. **让显卡运行在稳定显存几何布局之外。** 8 GB 卡配置为 64 GB 时稳定且已用于生产；10 GB 卡配置为 40 GB 时稳定；10 GB 卡配置为 80 GB 时虽然会报告该容量，但超过约 40 GB 的部分不可用：访问更多显存的内核会导致 GPU 致命丢失，与功耗上限无关。报告的 Xid 代码包括 Xid 31（被描述为无害），以及 CUDA 显存测试后的 Xid 154；最主要的报告症状是卡死，并伴随老化测试错误。单独将 Xid 31 视为该故障的特征，是一名旁观者提出的说法，并未得到故障卡操作者的佐证。这会破坏工作负载，而不是显卡本身。见[80 GB](../frontier/80gb.md)。
5. **对正在运行的任务进行操作者错误操作。** 对正在运行的多 GPU 任务执行 `kill -9` 会使主机 CUDA 运行时卡死（大约产生 32 个僵尸进程，`cuInit` 返回 999），并需要重启主机。对验证内核执行 SIGKILL 可能会以 Xid 45 使显卡卡死。在一次完整的 8 卡会话中，数百次 60 秒健康采样表明，只要工作负载驱动方式正确，就有 **0** 次硬故障。

> [!CAUTION]
> **真正的硬件风险在哪里**
>
> 本项目中唯一具有真正不可逆硬件风险的地方是**电容改装**：在一块 8 到 12 层的电路板上，将 24 个 0402 220 nF X7R 元件手工焊接到 C1100 到 C1350 的区域；要抬起芯片，还需要先用 420 °C 热风加热 2 分钟。这是焊接风险，而不是固件风险，相关内容在[物理改装](../operations/physical-mods.md)中单独介绍。还要注意，电容改装只会改变通道**数量**，从不会改变 PCIe 代数。

### 5.4 实用的安全姿态 { #posture }

* 确保显卡的出厂行为可验证：开始之前，确认它能在未打补丁的出厂驱动上完成枚举并运行。
* 优先使用无头主机或不使用 NVIDIA 显示输出的主机，这样才能真正卸载模块。
* 在可行的情况下，在 VM 或容器中进行解锁开发。一名开发者报告称，在裸机上每次搞砸 `nvidia.ko` 部署后，都需要重新安装操作系统。
* 将驱动固定在 610，作为防止未来 NVIDIA 发布版本堵上该漏洞的长期预防措施，就像 P100 和 V100 用户将驱动固定在约 580 一样。*（置信度：中；这是基于推理的建议，目前还不需要执行，因为尚不存在会阻断解锁的驱动。）*
* 不要对正在运行的任务执行 `kill -9`。不要在你重视的硬件上运行过度配置的显存几何布局。
* 在寻求帮助前，采集 `sudo dmesg | grep SEC2_DEBUG` 的输出和最新的安装日志。见[升级处理](troubleshooting.md#escalation)。

---

## 相关页面

* [排障](troubleshooting.md)：按索引从症状定位原因和修复方法
* [卸载](uninstall.md)：完整介绍 `remove.sh`
* [安装](install.md)：受支持的安装流程
* [验证](verify.md)：确认状态正常
* [风险](../start/risks.md)：本评估的概览版
* [权限级别掩码](../unlock/privilege-level-masks.md)：哪些 PLM 属于 AON、哪些不属于
* [显存几何布局](../unlock/memory-geometry.md)：几何布局为什么无法挺过复位
* [寄存器参考](../unlock/register-reference.md)：本页提到的所有寄存器
