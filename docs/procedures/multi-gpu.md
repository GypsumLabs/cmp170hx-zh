# 运行多张卡

**本页涵盖内容。** 当一台主机有多张 CMP 170HX 时会发生什么：为什么已发布的 `master` 虽然是单卡安装器，却能在多卡系统上工作；未发布的 `multiple-cards` 分支增加了什么（按 BDF 分类、`gpu_inventory` 文件、`mixed` 配置和 `SKIP_GEOMETRY_REWRITE`）；以及机箱中有两张或更多 GPU 后才会出现的失败模式。

先说关键结论：**解锁本身已经按 GPU 独立进行。** 从提交 `7fe49b6` 起，打过补丁的 `nvidia.ko` 同时携带两种显存几何布局，并在 GSP 引导时根据 `pGpu->idInfo.PCIDeviceID >> 16` 选择其中一种。因此，无论安装器如何判断，机器中的每张卡都会按照正确的容量独立解锁。`master` 仍按单卡处理的只是*安装器的*记录逻辑：它取匹配到的第一行 `lspci` 输出，根据一次 `nvidia-smi` 读数猜测一个配置，并写入一组元数据文件。`multiple-cards` 和 `Gen2` 分支则用真正的按设备清单取代了这套记录逻辑。

多卡运行已经在实践中得到确认：一位操作者在 Proxmox 下直通了八张 8 GB CMP 170 卡，并且全部成功解锁。此前针对六卡系统的建议也是先尝试 `master`，后来一位多 GPU 用户确认 `master` 工作良好。

---

## `master` 在多卡主机上的行为

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

这个 `head -1` 就解释了全部问题。`install.sh` 记录一个 BDF 和一个设备 ID，然后调用 `detect_card_profile()`。该函数读取 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1`，再次只取第一项；但这一次采用的是 *nvidia-smi* 的顺序，而不是 *lspci* 的顺序。两种顺序并不保证一致。

在当前 `master` 上，结果如下：

| 场景 | 结果 |
|---|---|
| 4x 8 GB 卡 | 正常工作。四张卡都会解锁到 65536 MiB。配置元数据记录为 `8gb`，恰好也是正确的 |
| 4x 10 GB 卡 | 正常工作。四张卡都会解锁到 40960 MiB |
| 混合 8 GB + 10 GB | **每张卡的显存几何布局仍然正确**，因为布局是在 GSP 引导时按设备 ID 选择的。只有 `card_profile` / `unlock_geometry` 可能会把其中一种卡记录错，具体取决于哪种类型没有被第一项读数选中 |
| CMP 卡加一张无关的 NVIDIA GPU | 配置可能从*另一张*卡检测得到。这仍然只是元数据错误；但如果另一张卡的容量落在四个检测窗口之外，安装就会**失败** |
| 存在一张 `10de:20b0` 卡 | 只有当它是匹配到的 `lspci` 第一行时才会收到警告；如果它排在 `20c2` 或 `2082` 卡后面，`head -1` 会将它完全隐藏，也不会打印警告。无论哪种情况，它都不会被解锁，因为驱动内的门控只接受 `0x20C2` 和 `0x2082` |

> [!WARNING]
> **在混合 GPU 主机上始终传入 `--profile`**
>
> 至少有两人复现过这样的情况：主机同时安装 RTX 3080 10 GB 和 8 GB CMP 170HX，安装器却从 3080 检测出 "10GB"，并选择了 10 GB 配置。另一份报告显示，另一种 CMP SKU（一张 50HX）也被误检测为 10 GB 170HX。在当前 `master` 上，这只会导致元数据文件的标签错误；但养成显式传入 `--profile=8gb` 或 `--profile=10gb` 的习惯没有任何成本，还能消除一整类令人困惑的输出。

---

## `multiple-cards` 分支

> [!WARNING]
> **实验性：未发布分支**
>
> `multiple-cards`（tip `b1cb6d8` "Added support for multiple cards"，提交于 2026-07-18、于 2026-07-19 公布）截至 tip `cc872cb`（2026-07-23）**尚未**合并进 `master`。同一个安装器也通过提交 `2f27474` "Gen2 + multiple-card support" 纳入了 `Gen2` 分支线。本节内容全部针对分支代码。

### 按 BDF 分类

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

然后，安装器会处理 `lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'` 输出中的**每一**行（通过 `mapfile`，不再使用 `head -1`），并构建五个并行数组：BDF、设备 ID、配置、预期 MiB 和当前 MiB。当前 MiB 来自一次缓存的 `nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits` 查询，并按总线 ID 而不是索引进行匹配。

总线 ID 会通过共享的 `normalize_bus_id()` 进行比较。该函数会将 ID 转为小写，并把短格式 `BB:DD.F` 展开为 `0000:BB:DD.F`，因此 `lspci` 和 `nvidia-smi` 的写法可以相互匹配。`verify.sh` 中也原样包含了同一个函数。

一张 `20b0` 卡会在这里被归类为 `unsupported` 并**跳过**，同时打印 `GPU <bdf> (10de:20b0), unlock path not gated for this ID; skipping`。这不同于 `master` 的行为：`master` 会发出警告并继续处理，同时选中这张卡。如果检测到的所有卡都不受支持，分支安装器会以 `No unlockable CMP 170HX GPUs found (need 10de:20c2 and/or 10de:2082)` 退出失败。

典型的第 2 步输出：

```text
✓ GPU 0000:0b:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0c:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0d:00.0 (10de:2082) → 10gb (current 10240 MiB, expect ~40960 MiB unlocked)
==> Inventory: 3 unlockable (2× 8gb, 1× 10gb)
```

### `mixed` 配置

当 `COUNT_8GB > 0` 和 `COUNT_10GB > 0` 同时成立时，`CARD_PROFILE` 会变为第三种值 `mixed`：

```text
✓ Mixed variants detected → profile mixed (runtime geometry by PCI ID)
==> Unlock geometry: 64GB for 20c2 / 40GB for 2082 (chosen at GSP boot per GPU)
```

在混合清单上，`--profile=` 覆盖会被**显式丢弃**，并打印 `--profile=8gb ignored for mixed inventory; card_profile stays mixed (each card unlocks by PCI ID)`。在同质清单上，覆盖值会被采用，但程序会警告它只影响元数据。分支的帮助文本明确说明了这一点：`Force 8GB metadata label (geometry is still chosen per PCI ID)`。

### `SKIP_GEOMETRY_REWRITE`

分支上的 `driver/build.sh` 增加了第三个 case 和一个保护标志：

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

这段代码片段有两点值得注意：

1. 在 `mixed` 模式下，`CFG1` / `LMR` / `FB_BYTES` 变量仍会被赋为**8 GB**的值，但实际上从未使用。如果删除该标志且重写步骤可达，这些就是混合主机可能尝试为每张卡写入的值；第 2 点解释了为什么该步骤实际上不可达。
2. `SKIP_GEOMETRY_REWRITE` 是在已有安全保护之上增加的双保险。它跳过的内联 Python 步骤本身已经先检查两种烘焙的几何布局，共检查六个标记；随后以 `runtime device-id geometry (profile metadata=<label>)` 退出，不修改任何内容。在任何源自 `7fe49b6` 的代码树中，重写无论如何都是空操作。只有有人重新引入单一 SKU 补丁时，这个标志才会发挥作用。

在该模式下，`unlock_geometry` 会写入字面量字符串 `mixed`，`card_profile` 也会写入 `mixed`。

### `gpu_inventory` 文件

`install.sh` 会导出 `CMPUNLOCKER_GPU_INVENTORY`，`build.sh` 会将其持久化到 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`。文件中每张可解锁 GPU 占一行，列之间以空格分隔：

```text
BDF              devid  profile  expected_mib
0000:0b:00.0     20c2   8gb      65536
0000:0c:00.0     20c2   8gb      65536
0000:0d:00.0     2082   10gb     40960
```

实际文件没有表头行；上面的列名只是为了便于阅读而添加的。如果变量为空，`build.sh` 会将文件截断为零字节，而不是留下过期文件。

和另外三个元数据文件一样，**内核模块中没有任何代码会读取它。** 唯一使用它的是 `verify.sh`；`verify.sh` 会优先使用该文件，而不是实时枚举 `lspci`，这样掉出总线的卡会被报告为 `MISSING`，而不是静默地从检查中消失。

### `verify.sh` 在多卡系统上的行为

```bash
sudo ./verify.sh
```

如果 `gpu_inventory` 可读且非空，程序会从中枚举 GPU；否则回退到 `lspci -nn | grep -iE '10de:20c2|10de:2082'`。对于每张 GPU，程序会根据 `>= 60000` MiB（8gb）和 `35000`-`59999` MiB（10gb）这两个窗口，打印 `OK`、`STOCK`、`MISSING` 或 `UNEXPECTED`，然后汇总结果：

```text
✓ All 3 unlockable GPU(s) report unlocked memory
```

否则会以 `<n> GPU(s) failed unlock verification. Cold reboot if modules were just installed.` 报告失败。完整细节，包括它不会检查的两项内容，见[验证](verify.md#verifysh)。

---

## 已知的多卡失败模式

### 1. depmod 静默选择一个 `nvidia.ko`

这是本页最重要的一项。打过补丁的 `nvidia.ko` 和出厂版 `nvidia.ko` 可能同时位于 `updates` 下的同一个 depmod 搜索路径中；在这种情况下，**depmod 会任意选择其中一个，并静默丢弃另一个**。一位测试者最终确认，多卡失败的确切根因就是这个问题：他只在 updates 搜索路径中保留 cmpunlocker 变体，重启后确认多卡运行恢复正常。

这与 `build.sh` 警告的 `srcversion` 不匹配属于同一类失败：当前运行的模块不是打过补丁的版本，因此没有任何卡会解锁。可以使用以下命令诊断：

```bash
modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'
find /lib/modules/$(uname -r)/updates -name 'nvidia.ko'
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

如果第一条命令输出的路径不在 `updates/cmpunlocker/` 下，或者第二条命令找到多于一个 `nvidia.ko`，就是这个问题。

### 2. 过期的 initramfs 完全绕过 depmod

这与单卡情况相同，但在多卡系统上更难判断，因为部分成功的结果看起来像某张卡的问题，而不是模块加载问题。`build.sh` 会自行重建 initramfs；如果无法做到，会警告 `No initramfs tool found, rebuild manually before rebooting`。如果某些卡在*同一次*引导中解锁而另一些没有，原因就不是这个；如果*一张*卡都没有解锁，则很可能就是它。

### 3. 从错误的 GPU 检测配置

上文已经说明。在 `master` 上，这只是元数据错误，除非错误检测导致安装失败。

### 4. `verify.sh` 的 lspci 回退会遗漏 `0x20B0`

`install.sh` 会 grep `10de:20b0|10de:20c2|10de:2082`，然后警告或跳过 `20b0`；但 `verify.sh` 的回退路径只 grep `10de:20c2|10de:2082`。包含 `20b0` 卡的系统会因此在安装器和验证器中显示不同的设备数量。这个问题没有实际危害，但会令人困惑。

### 5. 虚拟化约束

- **Proxmox 直通对显存和算力有效**：八张 8 GB 卡完成直通后全部解锁。
- **使用 SeaBIOS，不要使用 UEFI/OVMF。** UEFI 会产生 RM init 和适配器失败，使症状看起来像利用本身没有生效。有人亲自追查并确认了这个根因，随后另一位用户也立即证实，其无法复现的问题同样由此造成。
- **截至 2026-07-24，PCIe Gen2 链路训练在 VM 中无法工作**，维护者已承认这是一个尚待调试的问题。

### 6. 多租户使用中的主机级卡死

一位操作者的租户终止了一次性能不佳的 `llama.cpp` 运行（约 121 t/s），却留下了破坏驱动状态的幽灵进程。由于无法从 Docker 容器内重启这些卡，恢复只能由操作者重启主机。租用多卡系统时，应确保拥有带外重启访问权限。见[恢复](recovery.md)。

### 7. 互连，而不是安装器

几份“多卡很慢”的报告其实是链路带宽问题，而不是解锁问题：

- 每张卡默认都是 Gen1 x4。升级到 Gen2 是未发布分支中的软件改动；超过 x4 的链路位宽则需要焊接交流耦合电容。这是两个完全独立的成果。见[PCIe 子系统](../hardware/pcie-subsystem.md)和 [PCIe Gen2](../unlock/pcie-gen2.md)。
- **NVLink 已通过熔丝关闭**，这张卡也不支持 P2P。`llama-server --split-mode row` 曾与按层拆分的命令一起流传，但被标注为 "benchmark-only on these links"（仅用于在这些链路上做基准测试），这与张量并行式拆分在 Gen1 x4 下不可行的判断一致。
- 一条经常被引用的经验法则（对多 GPU LLM 服务而言，“x4 可提升 10-30% 的速度，x8 或更高才理想”）只是作为经验法则提出的，**没有在 170HX 上进行测量**。其置信度应视为较低。见[LLM 推理](../operations/llm-inference.md)。

### 8. 叠加 P2P

可以将 `aikitoria` 的 P2P 补丁放入 `driver/patches/`，命名为 `0007-unlock-p2p.patch`，从而叠加在 cmpunlocker 之上，因为 `build.sh` 会按 glob 顺序应用所有 `*.patch`。但它在纯 170HX 系统上是否有实际作用仍未解决：一位测试者报告称，"It doesn't seem to take effect on the 170HX... It only has an effect on them if there are other models of GPUs on the same machine"（它在 170HX 上似乎没有生效……只有当同一台机器中还有其他型号的 GPU 时，才会对它们产生作用）；而另一位测试者在同一天报告称，在一台还装有两张 RTX 3090 的系统上，P2P 与 cmpunlocker 可以一起工作。这正是第一份报告所说的唯一可行的混合型号场景。双方都同意，P2P 受链路带宽限制，在 Gen1 x4 下收益很小。见[P2P](../frontier/p2p.md)。

---

## 当前多卡系统的推荐流程

1. 安装前先盘点硬件：

   ```bash
   lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'
   nvidia-smi --query-gpu=pci.bus_id,name,memory.total --format=csv
   ```

   确认每张卡的设备 ID。见[识别你的卡](../start/identify-your-card.md)。

2. 如果所有卡的类型相同，从 `master` 安装，并显式指定配置：

   ```bash
   sudo ./install.sh --profile=8gb     # or --profile=10gb
   ```

   对于真正混合 8 GB + 10 GB 的系统，`master` 仍会为每张卡生成正确的显存几何布局；你放弃的只有准确的元数据和 `verify.sh` 支持。如果需要这两项功能，可以使用 `multiple-cards` 分支，但必须接受它尚未发布。

3. 冷启动。执行 `sudo shutdown -h now`，然后重新上电。

4. **逐张**验证每一张卡，不要只验证第一张：

   ```bash
   nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv
   sudo dmesg | grep 'POST-WRITE'      # one line per unlocked GPU, with its devId
   ```

   `POST-WRITE` 行会携带 `(devId=0x...)`。因此，混合 SKU 系统应同时显示包含 `CFG1=0x02779000 LMR=0x0000020b` 和 `CFG1=0x02669000 LMR=0x0000028a` 的行。

5. 如果只有一张卡异常，应优先检查那张卡本身（插接、供电或转接卡）。如果所有卡都异常，应怀疑模块加载问题（失败模式 1 和 2）。

---

## 合并状态

> [!NOTE]
> **未解问题：多卡、IOMMU 和 Gen2 是否应合并进 master，以及应按什么顺序合并？**
>
> 截至 `cc872cb`，`multiple-cards`（独立的 `b1cb6d8`）和 `Gen2` 分支线（其中已纳入多卡支持）都尚未合并。障碍在于代码捆绑：整体合并 `Gen2` 会把实验性的 PCIe 链路重训练补丁（`0007-pcie-gen2.patch`、`0008-pcie-gen2-probe-retrain.patch`）及其未经验证的寄存器写入带入稳定路径。多卡安装器的改动彼此独立，可以单独 cherry-pick；而 `mixed` 配置之所以已经能够工作，是因为 `master` 的补丁 0001 已经烘焙了两种几何布局。另一方面，`clanker/driver-port`（支持 580/590/595/610）和 Gen2 分支线是独立开发的，从未合并，因此今天选择其中一个就意味着放弃另一个。见[状态板](../frontier/status-board.md)和[驱动版本](driver-versions.md)。

---

## 相关页面

- [安装](install.md)、[验证](verify.md)、[卸载](uninstall.md)
- [排障](troubleshooting.md)：按症状优先进行诊断
- [驱动补丁](../unlock/driver-patches.md)：了解使每张卡采用独立几何布局的设备 ID 门控
- [PCIe 子系统](../hardware/pcie-subsystem.md)：了解这些链路实际能够承载什么
