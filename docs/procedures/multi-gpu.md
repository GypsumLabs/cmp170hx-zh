# 运行多张卡

**本页覆盖内容。** 当一台主机有不止一张 CMP 170HX 时会发生什么：为什么出货 `master` 在多卡机架上有效、尽管它是一个单卡安装器、未发布的 `multiple-cards` 分支添加了什么（按-BDF 分类、`gpu_inventory` 文件、`mixed` 档位和 `SKIP_GEOMETRY_REWRITE`）、以及只在盒子里有至少两张 GPU 时才出现的失败模式。

提前给的关键结果：**解锁本身已经是按-GPU 的。** 自提交 `7fe49b6` 起、打过补丁的 `nvidia.ko` 携带两种几何布局、并在 GSP 引导时从 `pGpu->idInfo.PCIDeviceID >> 16` 选择一个，所以机器里的每张卡都以正确的大小独立解锁、不管安装器怎么想。`master` 上是单卡的只有*安装器的*记账：它取第一行匹配的 `lspci`、从一次 `nvidia-smi` 读猜测一个档位、并写一组元数据文件。`multiple-cards` 和 `Gen2` 分支用一个真实的按-设备清单取代那段记账。

多卡操作在实践中确认可用：一位操作者在 Proxmox 下直通了八张 8 GB CMP 170 卡、全部解锁。对一个六卡机架的更早建议是先试 `master`，而一位多 GPU 用户后来确认 master 工作得很好。

---

## `master` 在多卡主机上做什么

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

那个 `head -1` 就是全部故事。`install.sh` 记录一个 BDF 和一个设备 ID，然后调用 `detect_card_profile()`，它读 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1`、再次取第一项、这次是 *nvidia-smi* 顺序而非 *lspci* 顺序。两种排序不保证一致。

在当前 `master` 上的后果：

| 场景 | 结果 |
|---|---|
| 4x 8 GB 卡 | 有效。全部四张解锁到 65536 MiB。档位元数据说 `8gb`、碰巧是对的 |
| 4x 10 GB 卡 | 有效。全部四张解锁到 40960 MiB |
| 混合 8 GB + 10 GB | **每张卡的几何布局仍正确**，因为它在 GSP 引导时按设备 ID 选择。只有 `card_profile` / `unlock_geometry` 对输掉抛硬币的类型是错的 |
| CMP 卡加一张无关的 NVIDIA GPU | 档位可能从*另一张*卡检测到。仍只是一个元数据错误，除非另一张卡的大小落在全部四个检测窗口之外，那种情况下安装**死掉** |
| 存在一张 `10de:20b0` 卡 | 只有当它是*第一*行匹配的 `lspci` 时才被警告；坐在一张 `20c2` 或 `2082` 卡后面时 `head -1` 完全隐藏它、不打任何警告。无论哪种方式它都不被解锁，因为驱动内门只接受 `0x20C2` 和 `0x2082` |

> [!WARNING]
> **在混合-GPU 主机上始终传 `--profile`**
>
> 一张 RTX 3080 10 GB 与一张 8 GB CMP 170HX 并存的主机，被至少两人复现为从 3080 检测出 "10GB" 并选 10 GB 档位。另一份报告有另一个 CMP SKU（一张 50HX）被误检为 10 GB 170HX。在当前 `master` 上这只会给元数据文件贴错标签，但显式传 `--profile=8gb` 或 `--profile=10gb` 的习惯零成本、还移除整整一类令人困惑的输出。

---

## `multiple-cards` 分支

> [!WARNING]
> **实验性：未发布分支**
>
> `multiple-cards`（tip `b1cb6d8` "Added support for multiple cards"，提交于 2026-07-18、宣布于 2026-07-19）截至 tip `cc872cb`（2026-07-23）**没有**合并进 `master`。同一个安装器也经提交 `2f27474` "Gen2 + multiple-card support" 折进 `Gen2` 谱系。本节一切都是分支代码。

### 按-BDF 分类

`detect_card_profile()` 被 `profile_from_devid()` 取代：

```bash
profile_from_devid() {
    case "$1" in
        20c2) echo "8gb" ;;
        2082) echo "10gb" ;;
        *) echo "unsupported" ;;
    esac
}

expected_mib_for_profile() {
    case "$1" in
        8gb) echo "65536" ;;
        10gb) echo "40960" ;;
        *) echo "" ;;
    esac
}
```

然后安装器走 `lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'` 的**每一**行（经 `mapfile`、不用 `head -1`）并构建五个平行数组：BDF、设备 ID、档位、预期 MiB、当前 MiB。当前 MiB 来自一次缓存的 `nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits` 查找、按总线 ID 而非索引匹配。

总线 ID 通过一个共享的 `normalize_bus_id()` 比较，它转小写并把一个短的 `BB:DD.F` 展开成 `0000:BB:DD.F`，所以 `lspci` 和 `nvidia-smi` 拼写比较相等。同一个函数逐字存在于 `verify.sh` 里。

一张 `20b0` 卡在这里被分类为 `unsupported` 并**跳过**、带 `GPU <bdf> (10de:20b0), unlock path not gated for this ID; skipping`，这是对 master（它警告并继续、选那张卡）的一个行为差异。如果每张检测到的卡都不受支持，分支安装器以 `No unlockable CMP 170HX GPUs found (need 10de:20c2 and/or 10de:2082)` 死掉。

典型的第 2 步输出：

```text
✓ GPU 0000:0b:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0c:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0d:00.0 (10de:2082) → 10gb (current 10240 MiB, expect ~40960 MiB unlocked)
==> Inventory: 3 unlockable (2× 8gb, 1× 10gb)
```

### `mixed` 档位

当 `COUNT_8GB > 0` 和 `COUNT_10GB > 0` 都成立时，`CARD_PROFILE` 变成一个第三个值、`mixed`：

```text
✓ Mixed variants detected → profile mixed (runtime geometry by PCI ID)
==> Unlock geometry: 64GB for 20c2 / 40GB for 2082 (chosen at GSP boot per GPU)
```

一个 `--profile=` 覆盖在混合清单上被**显式丢弃**、带 `--profile=8gb ignored for mixed inventory; card_profile stays mixed (each card unlocks by PCI ID)`。在同类清单上覆盖被尊重、但警告它只是元数据。分支的帮助文本让这个降级显式化：`Force 8GB metadata label (geometry is still chosen per PCI ID)`。

### `SKIP_GEOMETRY_REWRITE`

分支上的 `driver/build.sh` 获得第三个 case 和一个守卫标志：

```bash
SKIP_GEOMETRY_REWRITE=0
case "${PROFILE}" in
    8gb|8GB)   CFG1="0x02779000"; LMR="0x0000020B"; FB_BYTES="0x0000001000000000"; UNLOCK_LABEL="64GB" ;;
    10gb|10GB) CFG1="0x02669000"; LMR="0x0000028A"; FB_BYTES="0x0000000A00000000"; UNLOCK_LABEL="40GB" ;;
    mixed|MIXED)
        PROFILE="mixed"
        CFG1="0x02779000"; LMR="0x0000020B"; FB_BYTES="0x0000001000000000"
        UNLOCK_LABEL="mixed"
        SKIP_GEOMETRY_REWRITE=1
        ;;
esac

if [[ "${SKIP_GEOMETRY_REWRITE}" -eq 1 ]]; then
    info "mixed profile: runtime device-id geometry (no build-time CFG1/LMR rewrite)"
else
    python3 - ... <<'PY'
    ...
fi
```

那段代码片段里有两件值得注意：

1. 在 `mixed` 模式里 `CFG1` / `LMR` / `FB_BYTES` 变量仍被赋成**8 GB** 值、却从未被使用。它们是混合主机如果丢掉标志*并且*重写可达时、会试图为每张卡烘焙的值；第 2 点解释为什么它不可达。
2. `SKIP_GEOMETRY_REWRITE` 是叠加在一个已有安全网之上的双保险。它跳过的内联 Python 步骤已经以一个六标记检查开头、检查两种烘焙几何布局、并以 `runtime device-id geometry (profile metadata=<label>)` 退出、不编辑任何东西。在任何源自 `7fe49b6` 的树上，重写无论如何都是空操作。只有某人重新引入一个单-SKU 补丁时该标志才要紧。

`unlock_geometry` 在那个模式下以字面量字符串 `mixed` 被写、`card_profile` 也写成 `mixed`。

### `gpu_inventory` 文件

`install.sh` 导出 `CMPUNLOCKER_GPU_INVENTORY`、`build.sh` 把它持久化到 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`、每张可解锁 GPU 一行、空白分隔：

```text
BDF              devid  profile  expected_mib
0000:0b:00.0     20c2   8gb      65536
0000:0c:00.0     20c2   8gb      65536
0000:0d:00.0     2082   10gb     40960
```

真实文件没有表头行；上面的列是为可读性加标的。如果变量为空，`build.sh` 把文件截断到零字节、而非留下一个陈旧的。

像其它三个元数据文件一样，**内核模块里没有任何东西读它。** 它唯一的消费者是 `verify.sh`，它偏好它而非活 `lspci` 枚举，这样一张已掉下总线的卡被报告为 `MISSING`、而非静默从检查中消失。

### `verify.sh` 在多卡机架上

```bash
sudo ./verify.sh
```

从 `gpu_inventory` 枚举（如果可读且非空），否则回退到 `lspci -nn | grep -iE '10de:20c2|10de:2082'`。每张 GPU 它针对窗口 `>= 60000` MiB（8gb）和 `35000`-`59999` MiB（10gb）打印 `OK`、`STOCK`、`MISSING` 或 `UNEXPECTED`，然后总结：

```text
✓ All 3 unlockable GPU(s) report unlocked memory
```

或以 `<n> GPU(s) failed unlock verification. Cold reboot if modules were just installed.` 失败。完整细节、包括它不检查的两件事，见[验证](verify.md#verifysh)。

---

## 已知的多卡失败模式

### 1. depmod 静默挑一个 `nvidia.ko`

本页最有价值的一项。一个打过补丁的和一个出厂的 `nvidia.ko` 可能都落在单一的 `updates` depmod 搜索项下，那种情况下 **depmod 任意挑一个、静默丢掉另一个**。一位测试者把一个多卡失败精确根因到这一点、只在 updates 搜索路径里保留 cmpunlocker 变体、重启、然后确认多卡操作工作。

这是与 `build.sh` 警告的 `srcversion` 不匹配相同的失败类：运行中的模块不是打过补丁的那个，所以没有卡解锁。用它诊断：

```bash
modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'
find /lib/modules/$(uname -r)/updates -name 'nvidia.ko'
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

第一条命令里任何不在 `updates/cmpunlocker/` 下的、或第二条里多于一个 `nvidia.ko` 的，就是 bug。

### 2. 一个陈旧的 initramfs 彻底胜过 depmod

与单卡情形相同、却在机架上更糟，因为一个部分结果看起来像一个按卡的问题、而非一个模块加载问题。`build.sh` 自己重建 initramfs、无法时警告 `No initramfs tool found, rebuild manually before rebooting`。如果某些卡在*同一次*引导里解锁、另一些不，这不是原因；如果*没有*卡解锁，它很可能就是。

### 3. 从错误的 GPU 误检测档位

上文已覆盖。在 `master` 上是纯元数据错误，除了当它让安装死掉时。

### 4. `verify.sh` 的 lspci 回退丢掉 `0x20B0`

`install.sh` grep `10de:20b0|10de:20c2|10de:2082` 然后警告或跳过 `20b0`，但 `verify.sh` 的回退路径只 grep `10de:20c2|10de:2082`。一个含 `20b0` 卡的机架会在安装器和验证器里显示不同的设备数。无害、却令人困惑。

### 5. 虚拟化约束

- **Proxmox 直通对显存和算力有效**：八张 8 GB 卡直通、全部解锁。
- **用 SeaBIOS、不要用 UEFI/OVMF。** UEFI 产生看起来恰好像利用根本不工作的 RM init 和适配器失败。这被一手根因定位、并立即被一个其无法复现恰好同因的第二人佐证。
- **截至 2026-07-24 PCIe Gen2 链路训练在 VM 里不工作**，被维护者承认是一个开放的调试项。

### 6. 多租户使用中的主机级卡死

一位操作者的租户杀掉了一个表现不佳的 `llama.cpp` 运行（约 121 t/s）、留下毁掉驱动状态的幽灵进程。恢复需要操作者做的一次主机重启，因为卡无法从 Docker 容器内重启。在任何租赁机架上规划带外重启访问。见[恢复](recovery.md)。

### 7. 互连，不是安装器

几份 "多卡很慢" 的报告是链路带宽问题、不是解锁问题：

- 每张卡默认都是 Gen1 x4。到 Gen2 是未发布分支上的一个软件改动；超过 x4 位宽需要焊接交流耦合电容。这两个是各自独立的成果。见[PCIe 子系统](../hardware/pcie-subsystem.md) 和 [PCIe Gen2](../unlock/pcie-gen2.md)。
- **NVLink 熔断关闭**、这张卡上 P2P 缺失。`llama-server --split-mode row` 与层拆分命令一起被传开、却被标注 "benchmark-only on these links"（仅在这些链路上做基准），与张量并行式拆分在 Gen1 x4 下不可行一致。
- 一条被频繁引用的经验法则（"x4 给 10-30% 加速、x8 或更好是理想"、对多 GPU LLM 服务而言）是作为经验法则提供的、**没在 170HX 上测过**。把它当中等置信度。见[LLM 推理](../operations/llm-inference.md)。

### 8. P2P 分层

`aikitoria` P2P 补丁可以通过把它丢进 `driver/patches/` 作为 `0007-unlock-p2p.patch` 分层在 cmpunlocker 之上，因为 `build.sh` 按 glob 顺序应用每个 `*.patch`。它在一个纯-170HX 系统上是否有用未解决：一位测试者报告 "It doesn't seem to take effect on the 170HX... It only has an effect on them if there are other models of GPUs on the same machine"（它在 170HX 上似乎没生效……只有当机器上还有其它型号 GPU 时才对它们有效），而另一位在同一台还含两张 RTX 3090 的机架上报告 P2P 加 cmpunlocker 工作，那恰好是第一份报告说唯一能工作的混合型号情形。双方都同意 P2P 受带宽约束、在 Gen1 x4 下收益甚微。见[P2P](../frontier/p2p.md)。

---

## 今天对多卡机架的推荐流程

1. 安装任何东西前盘点硬件：

   ```bash
   lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'
   nvidia-smi --query-gpu=pci.bus_id,name,memory.total --format=csv
   ```

   确认每张卡的设备 ID。见[识别你的卡](../start/identify-your-card.md)。

2. 如果所有卡类型相同，从 `master` 安装、带一个显式档位：

   ```bash
   sudo ./install.sh --profile=8gb     # 或 --profile=10gb
   ```

   对一个真正混合的 8 GB + 10 GB 机架，`master` 仍产生每张卡的正确几何布局；你放弃的只有准确的元数据和 `verify.sh`。如果你想要那些，用 `multiple-cards` 分支并接受它未发布。

3. 冷启动。`sudo shutdown -h now`，然后上电。

4. 逐张验证**每张**卡、不只第一张：

   ```bash
   nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv
   sudo dmesg | grep 'POST-WRITE'      # 每张解锁的 GPU 一行、带它的 devId
   ```

   `POST-WRITE` 行携带 `(devId=0x...)`，所以一个混合 SKU 机架应同时显示 `CFG1=0x02779000 LMR=0x0000020b` 和 `CFG1=0x02669000 LMR=0x0000028a` 行。

5. 如果恰好一张卡错了，怀疑那张卡（插装、供电、转接卡）。如果全部错了，怀疑模块加载（失败模式 1 和 2）。

---

## 合并状态

> [!NOTE]
> **未解问题：多卡、IOMMU 和 Gen2 应该合并进 master 吗、以什么顺序？**
>
> `multiple-cards`（`b1cb6d8`、独立）和 `Gen2` 谱系（折进它）都没有截至 `cc872cb` 合并。障碍是捆绑：整体合并 `Gen2` 会把实验性 PCIe 链路重训练补丁（`0007-pcie-gen2.patch`、`0008-pcie-gen2-probe-retrain.patch`）和它们未经验证的寄存器写拖进稳定路径。多卡安装器改动自包含、可以被单独 cherry-pick，而 `mixed` 档位已经工作、因为 master 的补丁 0001 烘焙了两种几何布局。分开地，`clanker/driver-port`（580/590/595/610 支持）和 Gen2 谱系独立开发、从未合并，所以今天选一个意味着放弃另一个。见[状态板](../frontier/status-board.md) 和[驱动版本](driver-versions.md)。

---

## 相关页面

- [安装](install.md)、[验证](verify.md)、[卸载](uninstall.md)
- [排障](troubleshooting.md) 看按症状优先的诊断
- [驱动补丁](../unlock/driver-patches.md) 看让按卡几何布局工作的设备-ID 门
- [PCIe 子系统](../hardware/pcie-subsystem.md) 看链路实际能带什么
