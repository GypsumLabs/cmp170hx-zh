# 卸载与还原

**本页涵盖的内容。** 如何干净地移除 `cmpunlocker` 驱动补丁，`remove.sh` 具体会操作什么、又会刻意保留什么，为什么从硬件层面看还原是安全的，以及那条被广泛复制、却会因为所指向的文件不存在而直接失败的指令。

简要步骤：

```bash
sudo ./remove.sh --yes
```

这就是全部受支持的卸载流程。它会删除**每个**已安装内核中的 `/lib/modules/*/updates/cmpunlocker/`，重新运行 `depmod`，重建 initramfs，清理两个已经废弃的第一代设计留下的残留，并重新加载出厂 NVIDIA 模块。显卡会在下一次冷启动后恢复为出厂报告的 8192 MiB 或 10240 MiB；热重启并不是一次复位，也没有确凿证据表明它能清除显存几何布局。

> [!CAUTION]
> **`uninstall.sh` 不存在**
>
> `docs` 分支中的 `docs/INSTALLATION.md` 第 40 行指示运行 `sudo ./uninstall.sh --yes`。**仓库中的任何位置都没有 `uninstall.sh`**，`master` 分支和 `docs` 分支本身都一样。运行它只会产生 shell 错误，什么也不会做；有些人因此认为“卸载器静默失败”（"the uninstaller silently failed"）。正确的命令是 `remove.sh --yes`。`docs` 分支还带有另外三个已知缺陷，因此不具备权威性：参见[验证](verify.md#the-sec2_debug-dmesg-trail)。

---

## 为什么还原是安全的

这套解锁机制不会在硬件中留下任何持久状态。它不会刷写 VBIOS、烧断熔丝或写入 EEPROM；从当前发布版设计开始，磁盘上的固件文件也不会被修改。解锁的实际机制，是打过补丁的内核模块每次启动 GSP 时执行一组易失性寄存器写入：

| 状态 | 能否挺过功能级复位？ | 能否挺过断电循环？ |
|---|---|---|
| SS0 `0x0082381c`、SS1 `0x00823820`、FEAT_OVR_PLM `0x00823804` | 能（常电域） | 不能 |
| CFG1、每个 FBPA 的 CFG1、CSTATUS、LMR `0x00100ce0`、显存几何布局 PLM、AON LMR 影子寄存器 `0x001180f0` | 不能 | 不能 |

移除打过补丁的模块后，这些写入就不会再发生。这就是还原的全部机制。一位使用 HiveOS 的测试者报告称，执行 `remove.sh` 后，两张卡都恢复了正常挖矿；这是一份将软件侧修改称为非破坏性的依据，但目前只有这一份一手报告。

物理改装完全是另一回事，本页的任何操作都**不会**撤销物理改装。如果显卡已经加装 PCIe 交流耦合电容，那就是焊接在硬件上的改动。参见[物理改装](../operations/physical-mods.md)。

---

## `remove.sh` 的逐步操作

没有 `--yes` 或 `-y` 时，脚本拒绝运行。直接调用它时，脚本会打印将要执行的操作摘要，然后以状态码 1 退出。

### 守卫和第 1 步：root

如果 `[[ "${EUID}" -eq 0 ]]` 不成立，脚本就会退出，并提示 `Run as root: sudo ./remove.sh --yes`。输出会通过 tee 同时写入检出目录中的 `logs/remove_<YYYYmmdd_HHMMSS>.log`；如果检出目录不可写，则回退到 `/tmp`。

### 第 2/5 步：停止遗留的 systemd 单元

停止并禁用 `cmpunlocker` 服务，删除 `/etc/systemd/system/cmpunlocker.service`，运行 `systemctl daemon-reload` 和 `reset-failed`，然后执行 `pkill -f /opt/cmpunlocker/daemon/watchdog.py`。

### 第 3/5 步：移除打过补丁的模块和遗留文件

- 对找到的每个 `/lib/modules/*/updates/cmpunlocker` 目录执行 `rm -rf`，所以清理的是**所有**已安装内核，而不只是当前运行的内核；随后执行 `depmod -a "${kernel}"`。
- 如果没有匹配项，则警告 `No patched kernel modules found`。
- 对每个受影响的内核重建 initramfs，使出厂模块重新打包进去。脚本会使用以下命令中第一个可用的命令：`update-initramfs -u -k`、`dracut --force --kver` 或 `mkinitcpio -P`。这一点在卸载时和安装时同样重要：如果 initramfs 仍然包含打过补丁的模块，系统就会继续加载它们。
- 在每个 `gsp_tu10x.bin` 旁边删除固件时代遗留的五个文件：`.cmpunlocker.bak`、`.cmpunlocker.patched`、`.cmpunlocker.tmp`、`.cmpunlocker.cleanup`、`.cmpunlocker.pat`。
- 如果 `/opt/cmpunlocker` 存在，则将其删除；否则警告 `/opt/cmpunlocker not found (ok for module-only installs)`。

> [!CAUTION]
> **这会删除你唯一一份补丁时代 `gsp_tu10x.bin` 的备份**
>
> 如果你正在从固件打补丁的前身方案迁移，并且**尚未**恢复出厂 GSP 固件，请在运行 `remove.sh` **之前**先恢复它。第 3 步会删除 `gsp_tu10x.bin.cmpunlocker.bak`，也就是原始 blob 的副本。先执行恢复：`sudo cp /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin.cmpunlocker.bak /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin`。

### 第 4/5 步：重新加载出厂驱动

只有在 `lsmod` 显示已加载 `nvidia` 模块时才会执行。顺序如下：

1. 停止 `gdm3`、`sddm`、`lightdm`、`display-manager`，然后停止 `nvidia-persistenced`。
2. 执行 `killall -9 Xorg Xwayland nvidia-persistenced`，等待 1 秒。
3. 执行 `modprobe -r nvidia_drm nvidia_uvm nvidia_modeset nvidia`，每个模块都忽略卸载失败，然后等待 1 秒。
4. 如果仍有模块处于加载状态，则对这四个模块执行 `rmmod -f`。
5. 执行 `modprobe nvidia`，然后依次加载 `nvidia-modeset`、`nvidia-uvm`、`nvidia-drm`。如果失败，则警告 `Could not reload NVIDIA driver, reboot to finish cleanup`。
6. 重启之前处于启用状态的第一个显示管理器。

> [!CAUTION]
> **第 4 步会终止图形会话**
>
> `remove.sh` 会停止显示管理器，并通过 `rmmod -f` 强制卸载模块。请从文本控制台或通过 SSH 运行它，不要在即将被终止的桌面会话中的终端里运行。在无头计算机上这没有影响；在工作站上，应预期显示会消失，并且可能要到重启后才会恢复。

### 第 5 步：摘要

脚本会打印日志路径；如果 GPU 或显示功能无法正常工作，还会提示执行 `sudo reboot`。

---

## `remove.sh` **不会**撤销什么

| 不会触碰的内容 | 为什么重要 | 手动操作 |
|---|---|---|
| 内核命令行 | `master` 的 `remove.sh` 完全不包含 `iommu` 或 `cmdline` 处理逻辑。IOMMU 配置存在于 `Gen2`、`far` 和 `deced` 分支中 | 如果你是从 `Gen2`、`far` 或 `deced` 分支安装的，请使用**同一分支中的** `remove.sh`。它会从 `<file>.cmpunlocker.bak` 恢复，并打印 `Reverted IOMMU kernel parameters (effective after reboot)`。如果改用 `master` 的 `remove.sh`，内核命令行会永久保持修改后的状态，同时留下孤立的 `/etc/default/grub.cmpunlocker.bak` |
| `/etc/modprobe.d/cmp-pcie-gen2.conf` | 该文件由 Gen2 谱系的安装器写入，其中包含 `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`（`far`/`deced` 上为 `0x2`）。`master` 从不创建或删除它 | 执行 `sudo rm /etc/modprobe.d/cmp-pcie-gen2.conf`，然后重建 initramfs |
| `/usr/local/sbin/retrain.sh`、`cmpretrain.service` | 仅由 `debug-gen2` 分支安装。`Gen2` 安装器会移除它们；`master` 不知道这些文件和服务 | 执行 `sudo systemctl disable --now cmpretrain.service; sudo rm -f /usr/local/sbin/retrain.sh` |
| `/lib/firmware/nvidia/ga100/gsp/dmem.bin` | 如果你在那里放置了自定义载荷覆盖文件，该文件会保留。未来的打过补丁的安装会将其读入载荷缓冲区，而不是执行内置填充；但第一次 `kgspSec2PostblTimingRefillPayload()` 会在任何 Booter Load 使用该缓冲区之前将其重写，因此在发布版路径中，这个文件不会产生实际效果 | 如果不是你有意放置的，请删除它 |
| `driver/.build/` 缓存 | 其中包含下载的 NVIDIA 源码 tarball 和解压后的源码树，在检出目录中可能占用数百 MB | 执行 `rm -rf driver/.build`，或直接删除整个克隆目录 |
| `logs/` | 安装和卸载过程的记录 | 保留它们；它们对排查问题很有用 |
| NVIDIA 驱动本身 | `remove.sh` 还原的是*补丁*，不是驱动软件包。nvidia-open 610.43.0x 仍会保持安装状态 | 使用你的发行版提供的软件包管理器 |
| 任何物理改动 | 电容改装、散热导流罩、电源转接线 | 不在本页范围内 |
| 显卡的 VBIOS | `cmpunlocker` 的任何部分都不会写入它 | 无需操作；参见[VBIOS](../hardware/vbios.md) |

显卡的非易失状态中也没有需要撤销的内容。每张已检查的显卡，其位于 `0x008203f0` 的主灭杀熔丝都读为 `0x00000000`（未烧断）；解锁路径中的任何操作都不会烧断熔丝或写入 OTP。参见[熔丝与 OTP](../hardware/fuses-and-otp.md)。

---

## 验证还原结果

```bash
# 每个内核中的模块都已消失
ls /lib/modules/*/updates/cmpunlocker 2>/dev/null   # 预期：完全没有输出

# 解析到并加载的都是出厂模块
modprobe -n -v nvidia
cat /proc/driver/nvidia/version                      # 现在应再次显示 dvs-builder

# 容量恢复为出厂值（仅在冷启动后检查）
nvidia-smi --query-gpu=memory.total --format=csv,noheader
#   8 GB 卡：  8192 MiB
#   10 GB 卡：10240 MiB

# 本次引导没有解锁活动
sudo dmesg | grep -c SEC2_DEBUG                      # 重启后预期为 0
```

执行 `remove.sh` 后，显卡会继续报告解锁后的容量，直到发生一次冷启动。这是正常现象，并不表示打过补丁的模块仍驻留，因为显存几何布局寄存器会在驱动卸载和重新加载后继续保留。应通过 `modprobe -n -v nvidia`、`/sys/module/nvidia/srcversion` 以及 `dmesg` 中不再出现 `SEC2_DEBUG` 行来判断是否还原成功，而不要根据 `memory.total` 判断。如果解锁后的容量在热重启后仍然存在，请完全关闭机器电源再试一次，然后再下结论：热重启并不是一次复位。如果在真正的冷启动后仍然存在，请检查 initramfs 是否确实重建；包含打过补丁的 `nvidia.ko` 的旧 initramfs 是最常见的原因，这与安装过程中的同类失败相对应。

---

## 切换分支前先卸载

维护者的规则是先移除旧安装，再添加新安装：“In fact, I would always recommend to remove the old one before adding the new one.”（事实上，我总是建议先移除旧版本，再添加新版本。）一位克隆 `Gen2` 分支并在现有安装上直接安装的测试者报告安装未能正常工作，先卸载后问题得到解决。

这是一项建议，不是绝对规则。至少还有两位测试者在原安装上直接叠加安装而没有遇到问题，非正式共识是大多数人都“just sending it on top”（直接覆盖安装）。那次失败确实存在，但并非普遍发生，也没有人找出导致差异的因素。先卸载是受支持的路径：

```bash
cd /path/to/old-checkout && sudo ./remove.sh --yes
cd /path/to/new-checkout && sudo ./install.sh
sudo shutdown -h now      # 冷启动
```

---

## 如果显卡已经卡死，而不只是打过补丁

`remove.sh` 适用于健康的系统。如果显卡处于异常状态，例如一次失败的引导留下 WPR2 up、Booter 停在执行中途、出现 `RmInitAdapter` 失败，或者显卡已经停止枚举，那么卸载模块不是正确的第一步。请前往[恢复](recovery.md)，其中介绍了通过 `/sys/bus/pci/devices/<BDF>/reset` 执行的功能级复位、按 `modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia` 顺序拆除模块，以及只有冷启动才能清除状态的情况。

一个实际的多租户案例可以说明两者的区别：某位操作者的租户终止了一个性能不佳的 `llama.cpp` 任务，却留下了破坏驱动状态的幽灵进程。由于无法从容器内部重启显卡，恢复过程需要操作者执行一次主机重启。继续卸载多少次都没有用。

---

## 相关页面

- [安装](install.md) 查看正向操作流程
- [验证](verify.md) 了解健康安装的状态，从而知道自己正在移除什么
- [排障](troubleshooting.md) 和[恢复](recovery.md)
- [多卡](multi-gpu.md)，其分支安装器会添加 `master` 的 `remove.sh` 不知道的文件
