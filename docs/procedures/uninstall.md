# 卸载与还原

**本页覆盖内容。** 如何干净移除 cmpunlocker 驱动补丁、`remove.sh` 恰好碰什么、它刻意留下什么、为什么还原在硬件层面安全、以及那条被广泛复制的指示——它因所命名的文件不存在而注定失败。

短版：

```bash
sudo ./remove.sh --yes
```

那就是整个受支持的卸载。它删除**每个**已安装内核上的 `/lib/modules/*/updates/cmpunlocker/`、重跑 `depmod`、重建 initramfs、清理两个废弃第一代设计的残留，并重载出厂的 NVIDIA 模块。卡会在下次冷启动后回到它出厂报告的 8192 MiB 或 10240 MiB；热重启不是一次复位，也没有被确立能清除几何布局。

> [!CAUTION]
> **`uninstall.sh` 不存在**
>
> `docs` 分支上的 `docs/INSTALLATION.md` 第 40 行指示 `sudo ./uninstall.sh --yes`。**仓库任何地方都没有 `uninstall.sh`**，在 `master` 或 `docs` 分支本身上都没有。运行它会产生一个 shell 错误、什么都不做，有些人把这读作 "the uninstaller silently failed"（卸载器静默失败）。正确命令是 `remove.sh --yes`。`docs` 分支还带有另外三个已知缺陷、并不是权威：见[验证](verify.md#the-sec2_debug-dmesg-trail)。

---

## 为什么还原是安全的

这个解锁在硬件里没有任何持久的东西。没有 VBIOS 刷写、没有熔丝烧断、没有 EEPROM 写，而且自出货设计起，磁盘上也没有任何固件文件被修改。解锁是打过补丁的内核模块每次引导 GSP 时执行的一次易失寄存器写序列：

| 状态 | 挺过功能级复位？ | 挺过断电循环？ |
|---|---|---|
| SS0 `0x0082381c`、SS1 `0x00823820`、FEAT_OVR_PLM `0x00823804` | 是（常电岛） | 否 |
| CFG1 `0x009a0204`、每-FBPA CFG1、CSTATUS、LMR `0x00100ce0`、FB-几何 PLM、AON LMR 影子 `0x001180f0` | 否 | 否 |

移除打过补丁的模块，写就停止发生。那就是还原的全部机制。一位跑 HiveOS 的测试者报告 `remove.sh` 后两张卡恢复正常挖矿，那是把 mod 的软件侧称为非破坏性的依据（单一的一手报告）。

物理改装完全是另一回事、**不**被本页任何东西撤销。如果卡已装上 PCIe 交流耦合电容，那是焊接好的硬件。见[物理改装](../operations/physical-mods.md)。

---

## `remove.sh` 逐步做什么

脚本没有 `--yes` 或 `-y` 就拒绝运行。裸调用它时，它会打印将要做什么的摘要并退出 1。

### 守卫和第 1 步：root

`[[ "${EUID}" -eq 0 ]]` 或死掉、带 `Run as root: sudo ./remove.sh --yes`。输出 tee 到检出里的 `logs/remove_<YYYYmmdd_HHMMSS>.log`、检出不可写时回退到 `/tmp`。

### 第 2/5 步：停止遗留 systemd 单元

停止并禁用一个 `cmpunlocker` 服务、移除 `/etc/systemd/system/cmpunlocker.service`、跑 `systemctl daemon-reload` 和 `reset-failed`，然后 `pkill -f /opt/cmpunlocker/daemon/watchdog.py`。

### 第 3/5 步：移除打过补丁的模块和遗留文件

- 对找到的每个 `/lib/modules/*/updates/cmpunlocker` 目录（所以**所有**已安装内核、不只运行中那个）：`rm -rf`，然后 `depmod -a "${kernel}"`。
- 没匹配到时警告 `No patched kernel modules found`。
- 对每个碰过的内核重建 initramfs、这样出厂模块被重新打包，用第一个可用的 `update-initramfs -u -k`、`dracut --force --kver` 或 `mkinitcpio -P`。这一点在还原路径上同在安装路径上一样要紧：一个仍持有打过补丁模块的 initramfs 会继续加载它们。
- 在每个 `gsp_tu10x.bin` 旁删除五个固件时代遗留：`.cmpunlocker.bak`、`.cmpunlocker.patched`、`.cmpunlocker.tmp`、`.cmpunlocker.cleanup`、`.cmpunlocker.pat`。
- 移除 `/opt/cmpunlocker`（如果存在）、否则警告 `/opt/cmpunlocker not found (ok for module-only installs)`。

> [!CAUTION]
> **这会删除你唯一的补丁时代 `gsp_tu10x.bin` 备份**
>
> 如果你正从固件打补丁前身迁移、且**尚未**恢复出厂商 GSP 固件，在跑 `remove.sh` **之前**恢复它。第 3 步删除 `gsp_tu10x.bin.cmpunlocker.bak`、即原 blob 的副本。先恢复：`sudo cp /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin.cmpunlocker.bak /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin`。

### 第 4/5 步：重载出厂商驱动

只有 `lsmod` 显示一个 `nvidia` 模块时。按顺序：

1. 停止 `gdm3`、`sddm`、`lightdm`、`display-manager`，然后 `nvidia-persistenced`。
2. `killall -9 Xorg Xwayland nvidia-persistenced`，sleep 1。
3. `modprobe -r nvidia_drm nvidia_uvm nvidia_modeset nvidia`（每个忽略失败），sleep 1。
4. 若仍有东西已加载，`rmmod -f` 那四个模块。
5. `modprobe nvidia`，然后 `nvidia-modeset`、`nvidia-uvm`、`nvidia-drm`。失败时警告 `Could not reload NVIDIA driver, reboot to finish cleanup`。
6. 重启第一个曾启用的显示管理器。

> [!CAUTION]
> **第 4 步会杀掉你的图形会话**
>
> `remove.sh` 停止显示管理器并用 `rmmod -f` 强制卸载模块。从文本控制台或 SSH 跑它、不要从你正要终止的桌面会话里的一个终端跑。在无头计算箱上这无害；在工作站上、预期显示会消失、并可能到重启前都不回来。

### 第 5 步：摘要

打印日志路径、如果 GPU 或显示不工作就告诉你 `sudo reboot`。

---

## `remove.sh` **不**撤销什么

| 不碰 | 为什么要紧 | 手动操作 |
|---|---|---|
| 内核命令行 | master 的 `remove.sh` 完全不含 `iommu` 或 `cmdline` 处理。IOMMU 配置存在于 `Gen2`、`far` 和 `deced` 分支上 | 如果你从 `Gen2`、`far` 或 `deced` 安装，用**那个同一分支的** `remove.sh`，它从 `<file>.cmpunlocker.bak` 恢复并打印 `Reverted IOMMU kernel parameters (effective after reboot)`。改用 master 的 `remove.sh` 会让内核命令行被永久修改、并留下一个孤儿 `/etc/default/grub.cmpunlocker.bak` |
| `/etc/modprobe.d/cmp-pcie-gen2.conf` | 被 Gen2 谱系安装器写、带 `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`（或 `far`/`deced` 上 `0x2`）。master 从不创建它、也从不删除它 | `sudo rm /etc/modprobe.d/cmp-pcie-gen2.conf` 并重建 initramfs |
| `/usr/local/sbin/retrain.sh`、`cmpretrain.service` | 只被 `debug-gen2` 分支安装。`Gen2` 安装器移除它们；master 不知道它们 | `sudo systemctl disable --now cmpretrain.service; sudo rm -f /usr/local/sbin/retrain.sh` |
| `/lib/firmware/nvidia/ga100/gsp/dmem.bin` | 如果你在那里放了自定义载荷覆盖、它留下。未来一次打过补丁的安装把它读进载荷缓冲区、而非运行内置填充，但第一次 `kgspSec2PostblTimingRefillPayload()` 在任何 Booter Load 消费它之前重写那个缓冲区，所以在发布路径上该文件无效果 | 如果不是你刻意放的、删除它 |
| `driver/.build/` 缓存 | 下载的 NVIDIA 源码 tarball 和解压的树，检出内可能有几百 MB | `rm -rf driver/.build` 或直接删除克隆 |
| `logs/` | 安装和移除转写 | 保留它们；它们对排障有用 |
| NVIDIA 驱动本身 | `remove.sh` 还原的是*补丁*、不是驱动包。nvidia-open 610.43.0x 保持已安装 | 用你发行版的包管理器 |
| 任何物理的东西 | 电容改装、散热导流罩、电源转接线 | 超出范围 |
| 卡的 VBIOS | 永不被 cmpunlocker 的任何部分写 | 无事可做；见[VBIOS](../hardware/vbios.md) |

卡的易失状态里也没有任何要撤销的东西。主灭杀熔丝在 `0x008203f0` 在每张检查过的卡上都读 `0x00000000`（未烧断），而解锁路径里没有任何东西烧熔丝或写 OTP。见[熔丝与 OTP](../hardware/fuses-and-otp.md)。

---

## 验证还原

```bash
# 模块从每个内核消失
ls /lib/modules/*/updates/cmpunlocker 2>/dev/null   # 预期：完全无输出

# 出厂商模块是解析和加载的那个
modprobe -n -v nvidia
cat /proc/driver/nvidia/version                      # 现在应再说 dvs-builder

# 容量回到出厂（只在冷启动后）
nvidia-smi --query-gpu=memory.total --format=csv,noheader
#   8 GB 卡：  8192 MiB
#   10 GB 卡： 10240 MiB

# 本次引导没有解锁活动
sudo dmesg | grep -c SEC2_DEBUG                      # 重启后预期 0
```

`remove.sh` 之后卡会继续报告解锁后大小、直到一次冷启动。这是正常结果、不是打过补丁的模块仍驻留的证据，因为几何寄存器挺过一次驱动卸载和重载。用 `modprobe -n -v nvidia`、`/sys/module/nvidia/srcversion` 和 `dmesg` 里 `SEC2_DEBUG` 行的缺失来判定还原，而不要用 `memory.total`。如果解锁后大小在热重启后仍持续，完全断电再试一次、然后才下结论：热重启不是一次复位。如果在真正冷启动后仍持续，检查 initramfs 是否真的重建了：一个持有打过补丁的 `nvidia.ko` 的陈旧 initramfs 是常见原因，与安装侧的那次失败相对称。

---

## 切换分支前卸载

维护者的规则是移除旧安装再加新的："In fact, I would always recommend to remove the old one before adding the new one."（事实上，我总是建议在加新的之前移除旧的。）一位克隆 `Gen2` 分支、在现有安装之上安装的测试者报告它不工作、先卸载就修好了。

这是指导而非硬规则。至少另两位测试者叠加安装也没问题，非正式共识是大多数人 "just sending it on top"（直接装上去）。那个失败是真实的、却不普遍，没人识别出区分因素。先移除是受支持路径：

```bash
cd /path/to/old-checkout && sudo ./remove.sh --yes
cd /path/to/new-checkout && sudo ./install.sh
sudo shutdown -h now      # 冷启动
```

---

## 如果卡被卡死而非仅仅被打过补丁

`remove.sh` 为健康系统准备。如果卡处于坏状态（一次失败引导留下 WPR2 up、一个停在半途的 Booter、`RmInitAdapter` 失败、或一张已停止枚举的卡），卸载模块不是正确的第一步。去[恢复](recovery.md)，它覆盖经 `/sys/bus/pci/devices/<BDF>/reset` 的功能级复位、`modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia` 拆掉顺序、以及只有冷启动清除状态的情形。

一个实际的多租户例子说明区别：一位操作者的租户杀死了一个表现不佳的 `llama.cpp` 运行、留下毁掉驱动状态的幽灵进程。恢复需要由操作者执行的一次主机重启，因为卡无法从容器内重启。再多的卸载也没用。

---

## 相关页面

- [安装](install.md) 看正向流程
- [验证](verify.md) 看健康安装长什么样，这样你知道你在移除什么
- [排障](troubleshooting.md) 和[恢复](recovery.md)
- [多卡](multi-gpu.md)，其分支安装器添加了 master 的 `remove.sh` 不知道的文件
