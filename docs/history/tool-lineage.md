# 工具谱系：该用什么，哪些已失效

## 本页覆盖内容

目前存在四代 CMP 170HX 工具，而且它们的时间范围彼此重叠，因此“更新”并不总是意味着“取代”。本页从 2026 年 6 月第一次手动 BAR0 写入开始，追溯到发布版驱动内补丁集及其上层分支结构，并明确说明哪些路线已经失效，避免读者继续误用。

**如果你只想要短答案：**

- 要**解锁显卡**，使用 `cmpunlocker` 的 `master`：`install.sh`、`driver/build.sh` 和六个补丁。其余内容都属于历史方案或实验方案。
- 要**测量显卡**，使用第 0 代只读工具（`probe.sh`、`pcielink.sh`、`check_fold.py` 和 VBIOS 转储器）。这些工具从未被淘汰。
- **不要**使用任何 Python ROP 解锁器、任何 GSP ELF 补丁器，也不要使用第 1 代的 systemd 持久化守护进程。那一代的所有持久化机制都已被取代。
- **不要**指望在仓库中找到测量工具。`master` 没有 `tools/` 目录；`probe.sh`、`pcielink.sh`、`check_fold.py`、`cuda_dbg.py`、A100 探测套件和 `refire_chain*.py` 脚本都是通过 gist 和频道附件在仓库外分发的。

---

## 谱系一览

| 代 | 时期 | 工具 | 状态 |
|---|---|---|---|
| **0：只读表征** | 2026-05-31 至今 | `probe.sh`（mmio-probe）、`z1_dump_and_parse_vbios.sh` + `z2_parse_vbios_table.py`、`pcielink.sh`、A100 `probe.py`/`sweep.sh`、`cuda_dbg.py`、`check_fold.py`、`cuda_memtest` | **当前。** 从未被淘汰。这些是测量仪器，不是解锁器 |
| **1：手动 BAR0 写入和 Python ROP 解锁器** | 2026-06-22 到 2026-07-17 | `deploy.py --path sec2-rop`、`deploy.py --path vbios-memory`、`load_custom_bin.py`、`unlc.py`、`stack_gen.py`、`patch_gsp.py`、`payload-lnject.py`、`scan_dmem.py`、`nuke.sh`、`b.sh`、`falcon_emulator.py`、systemd `cmp170hx-unlock.service` | **已废弃。** 这里每个持久化机制都被取代了 |
| **2：发布版驱动补丁（`cmpunlocker`）** | 2026-07-14 至今 | `install.sh`、`driver/build.sh`、`driver/patches/0001`-`0006`、`remove.sh`、`common/constants.yaml`、`driver/VERSION` | **当前且规范。** 这就是 `master` 上发布的内容 |
| **3：免驱动 SEC2 refire 链** | 2026-07-22 至今 | `refire_chain.py`（v1）、`refire_chain_v2.py`、`refire_chain_v6.py` | **当前但具实验性。** 一条平行的非发布路线，不属于 `cmpunlocker` |
| **4：未合并特性分支** | 2026-07-18 至今 | `multiple-cards`、`clanker/driver-port`、`80`、`debug-gen2` 到 `Gen2` 到 `far` 到 `deced`、加 `docs`、`ecc`、`housekeeping`、`memory`、`PG199` | **实验性。** 坐在第 2 代之上 |

---

## 第 0 代：测量仪器

这些工具早于解锁方案出现，最初用于熔丝表征，至今仍是正确的选择。整个项目的基本验证纪律也由此形成：**每次写入后，都要用 `probe.sh` 回读寄存器，不要只相信某个工具声称操作成功。**

### `probe.sh`（tools/mmio-probe）

这是一个自包含的 bash 加内联 Python 工具，以只读方式 mmap `/sys/bus/pci/devices/<BDF>/resource0`，转储约 120 至 130 个具名寄存器以及 24 个逐 FBPA 读数。它**从不向 BAR0 写入**。

```bash
./probe.sh [pci_id]      # default filter 10de:
# output to ${OUTDIR:-/tmp/mmio-probe-$(date +%s)}
```

| 属性 | 值 |
|---|---|
| 访问模式 | `os.open(..., os.O_RDONLY)`、`mmap.mmap(fd, 0, access=mmap.ACCESS_READ)`、`struct.unpack_from('<I', bar, off)` |
| 输出 | `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv`、`probe.log`、打包到 `/tmp/mmio-probe-$(hostname)-YYYYmmdd-HHMMSS.tar.gz` |
| `registers.json` 键 | `targets`（名称到偏移量/值/原因的映射）、`fbpa_capacity`、`fbpa_cfg0` |
| 每-FBPA 常量 | `FBPA_BASE = 0x900000`、`FBPA_STRIDE = 0x4000`、`CSTATUS_RAM = 0x20C`、`FBPA_COUNT_TO_PROBE = 24` |
| 派生地址 | fbpa00 CSTATUS_RAMAMOUNT `0x0090020C`、fbpa01 `0x0090420C`、fbpa23 `0x0095C20C`；CFG0 在偏移量 `0x200`；广播 CFG0 `0x009A0200`、CFG1 `0x009A0204` |
| 可选 CUDA 步骤 | 用 `nvcc -arch=sm_70 -O2` 编译并运行 `sr_dump.cu`，以 `dump_sr<<<p.multiProcessorCount, 32>>>()` 启动，报告每个 SM 的 `%smid`、`%warpid`、`%nsmid`、`%nwarpid`、`%lanemask_eq`，因此 **SM 数量是测量出来的，而不是由工具直接报告的**（170HX 上为 70）。如果没有 `nvcc`，则记录一行日志并跳过 |

`gpu-summary.csv` 会记录 `driver_version` 和 `vbios_version`，因此可以把一次探测结果对应到具体的 VBIOS。该工具基于 MODS/MATS 构建，预计可以移植到其他显卡，但必须注意“registers may be in diff ranges etc though”（寄存器可能位于不同范围等）。

读取 BAR0 不仅需要 root，还需要 `CAP_SYS_RAWIO`；容器化 GPU 主机通常会丢弃这一能力，因此探测会报出 `cannot open .../resource0 (EPERM) even as root`。如果 `mmap` 以 EBUSY 或 EACCES 失败，说明 BAR 仍被 NVIDIA 驱动占用：

```bash
sudo systemctl stop nvidia-persistenced; sudo nvidia-smi -pm 0
# or, more forcefully
echo <BDF> | sudo tee /sys/bus/pci/drivers/nvidia/unbind
```

GA100 的 BAR0 是一个 16 MiB 的 PRI 地址窗口（`0x1000000`）。偏移量 0 处的 `PMC_BOOT_0` 可用于识别晶片：`0x170000a1` 表示 GA100，`0xb72000a1` 表示 GA102，`0xb74000a1` 表示 GA104。

> [!WARNING]
> **注释中宣称的 `/dev/mem` 回退并不存在**
>
> 文件头部注释第 9 行写着 `# Falls back to /dev/mem path if resource0 fails.`（resource0 失败时回退到 /dev/mem 路径）。但 resource0 解析代码实际以 `log "ERROR: cannot find resource0 for $PCI_BDF"; ... exit 2` 结束。这条回退路径从未实现。

### VBIOS 工具

`z1_dump_and_parse_vbios.sh` 通过三个 sysfs 命令（`echo 1 > .../rom`、`cat`、`echo 0 >`）无损转储 VBIOS；如果带前缀的路径不可用，则回退到不带前缀的 sysfs 路径，最后再回退到 `nvflash --save`。它**对闪存始终是只读的**，不存在写入路径。没有可用转储方式时退出 2，转储为空时退出 3。

`z2_parse_vbios_table.py` 通过四个魔数定位 ROM 结构：偏移量 0 处的 `NVGI`、根据 `+0x18` 处的 ROM 头指针找到的 `PCIR`、BIT 模式 `ff b8 42 49 54 00`，以及绝对偏移 `0x2000` 处的 `RFRD`。CFG1 跳线表则通过步长为 1 的扫描自动定位，扫描范围为 `0x30000` 到 `0xB0000`，寻找连续的 16 个 4 字节条目，且每个条目的字节 +2 属于 `{0x44,0x55,0x66,0x77}`、字节 +3 属于 `{0x02,0x22}`。

> [!WARNING]
> **解析器有四处标签已经过时**
>
> `extract_cfg1_strap_table` 的 docstring 引用了“~0x3FB18 in A100 PCIe”，但对比表将其放在 `0x4285A`；`extract_rfrd` 把 RFRD 称为“power table”（功耗表），实际上它是映像布局描述符，`field_0C` 是经 MAC 验证的范围大小，而不是功耗上限；`extract_fbpa_tier_table` 可能匹配到 CFG1 表本身，从而报告重复项；`find_subsystem_id` 则只是桩函数。任何逐字引用工具输出标签的人，都会把这四处错误一起传播出去。见 [VBIOS](../hardware/vbios.md)。

### `pcielink.sh`

这是标准的 PCIe 现场报告收集器，也是任何链路相关 bug 报告都应附上的工具。它会自动发现 `10de:20c2` / `10de:2082`（否则回退到任意 NVIDIA 3D 控制器），并在端点及其父桥上分别解码：

| 能力偏移量 | 字段 |
|---|---|
| `CAP_EXP+0c.l` | LnkCap |
| `CAP_EXP+2c.l` | LnkCap2 |
| `CAP_EXP+10.w` | LnkCtl |
| `CAP_EXP+12.w` | LnkSta |
| `CAP_EXP+24.l` | DevCap2 |
| `CAP_EXP+28.w` | DevCtl2 |
| `CAP_EXP+30.w` | LnkCtl2 |
| `CAP_EXP+32.w` | LnkSta2 |

此外，它还会收集 sysfs 链路速度和位宽、`nvidia-smi pcie.link.gen`、AER 计数器，以及包含 OPT 熔丝三元组的 `SEC2_DEBUG` dmesg 行数。该工具在两台彼此独立、均已解锁的双卡 Gen2 主机上打印过 `SEC2_DEBUG lines=152`，两台主机分别运行 HiveOS 和 Unraid，且都带有 `OPT=00000001/00000001/16680000`。

> [!NOTE]
> **行数不是可靠的跨构建指纹**
>
> 已记录的数值各不相同：归档的单卡 8 GB 捕获为 29，归档的双卡 Gen2 分支 `610.43.03` 日志为 134，报告工具在 Gen1 构建和 Gen2 构建上分别为 34 和 80，而 `pcielink.sh` 在两台双卡 Gen2 主机上为 152。因此，不要把数值不匹配解读为安装失败。

### A100 探测套件

这是一个包含三个步骤、可选择执行写入的工作流，用于构建 Gen2 差异对比：

```bash
python3 probe.py which
sudo python3 probe.py inventory --out a100_native.json   # read-only
sudo ./sweep.sh                                          # forces Gen1/2/3, auto-restores via EXIT trap
sudo python3 probe.py write-test --confirm               # writes then immediately restores
```

`write-test` 会访问 `0x880a8`（将目标速度设为 2）、`0x8c044`（设为 `0x00000002`）和 `0x88088`（重训练位 5），并将每项分类为 `WROTE-OK` 或 `REJECTED(PLM?)`。掩码读哨兵值是 `0xBADF5040`。套件中的任何操作都不会写入熔丝，也不会跨重启持久化。请在 GPU 空闲时运行，因为 sweep 会对当前活动链路执行重训练。

### VRAM 验证器

| 工具 | 它证明什么 | 机制 |
|---|---|---|
| **`check_fold.py`** | **权威工具。** 验证解锁后的 VRAM 是否真实、而不是地址别名 | 分配全部空闲 VRAM 减去 2 GiB，用 PTX `sm_80` 的 `fill` 内核将每个 64 KB 页的索引写入该页，再用 `chk` 内核读回每个页面。测试必须是稠密的：折叠会在某个通道**交错**偏移处产生别名，因此 `LOW[0]` 映射到的是 `(40 GiB + interleave)`，而不是 `(40 GiB + 0)`；稀疏探测会产生假阴性。工具通过 ctypes 使用 `libcuda`，并用 `st.global.wt.u32` 和 `ld.global.cv.u32` 绕过缓存。输出为 `REAL, NO FOLD` 或 `FOLD/mismatch @<pageindex>`；真实显存退出 0，折叠退出 1，错误退出 2 |
| `cuda_dbg.py` | 较轻量的别名测试 | 先调用 `cuMemGetInfo_v2`，然后尝试在 64、60、56、52、48、44、42 GiB 处调用 `cuMemAlloc_v2`，直到某次成功；在偏移量 0 写入 `0xAAAA0000`，在 40 GiB 处写入 `0xBBBB0000`，再读取偏移量 0。若读回 `0xBBBB0000`，说明地址空间发生别名。该工具不会释放分配，因此每次驱动加载只能运行一次 |
| `cuda_memtest` 1.2.3 | 社区 VRAM 验证工具 | 遇到第一个错误就退出。在解锁卡上报告 `global memory size=85545582592`。在 80 GB 档位会先打印 `Attached to device 0 successfully.`，然后无限挂起，除非将上限设为 39 GB |

> [!CAUTION]
> **一个更早的折叠 harness 本身就有问题**
>
> 一次 SBR 将显卡恢复到一致的原生状态（10240 MiB、驱动 610.43.03、CFG1 `0x02449000`）后，对照测试分配了 9 GiB 的真实原生内存，却在五轮测试中都报告“4608 chunks、4608 corrupt/aliased”，也就是声称原生内存发生了“折叠”，这是不可能的。同一个 harness 更早还曾报告 10 GiB 在第 1 轮以约 26.6 GB/s 完全别名，而第 2 至第 5 轮的速度却是 197 至 198 GB/s。这一结果使一批关于 40 GB 处发生折叠的结论事后失效。请使用 `check_fold.py`，不要采用任何更早 harness 的输出。

整个测试期间使用的标准驱动拆卸流程仍然正确：

```bash
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
echo 1 | sudo tee /sys/bus/pci/devices/<BDF>/reset
```

---

## 第 1 代：手动 BAR0 写入和 Python ROP 解锁器

### 当时的工作方式

2026-07-12 的实际手动流程发生在驱动内补丁出现之前：

```text
run the ROP script -> FLR -> kill the NVIDIA driver -> FLR again -> run the SM unlock script
```

流程从 TTY 执行，使用 580.159.04 开源内核模块；`patch_gsp.py` 会将 ROP 载荷拼入 `gsp_tu10x.bin`。`unlc.py` 展示了发布版补丁仍沿用的两步模型：利用只需打开 FEAT PLM，之后 SS0 和 SS1 就可以通过普通主机写入完成修改。

### 工具及其失效原因

| 工具 | 角色 | 命运 |
|---|---|---|
| `deploy.py --path sec2-rop` | 编排器，将 63,232 B 载荷写入 `/var/lib/cmp170hx/payload.bin`，并安装 systemd 单元 | 被驱动内投递取代。它的首个版本还因为把 `--verify` 传给不接受该参数的 `load_custom_bin.py` 而中止（退出码 2，不是硬件失败）。2026-06-24 修复 |
| `deploy.py --path vbios-memory` | 重写 VBIOS 中的 CFG1 跳线档位 | **从未成功。** 它产生 `[vbios-memory] ERROR: Not a PCI Option ROM (bad magic at 0x00)`，因为它预期的是内部映像，而不是原始 ROM 转储。整个 VBIOS-显存方案于 2026-06-23 放弃 |
| `load_custom_bin.py` | 加载 Falcon 二进制并转储 DMEM | 其投递原语被吸收到 refire 链中 |
| `unlc.py` | PLM 打开后的主机侧 SS0/SS1 写入器 | 它所体现的模型保留在补丁 0001 中，但脚本本身已不存在 |
| `stack_gen.py` | ROP 栈构建器 | 首个版本**将所有金丝雀槽清零**，因此不可能工作：`D[0x6340]` 处的金丝雀必须复制到每个帧中，否则会触发 `__stack_chk_fail`（`0x7dd9`）。常量为 `exit_addr 0x79e7`、`payload_size 0xF700`、`dma_target 0x0900`、`stack_start 0xf75c` |
| `patch_gsp.py`、`payload-lnject.py` | 对 `gsp_tu10x.bin` 执行 ELF 手术：解析位于 `e_shoff 0x28` 的 ELF64 头、读取 `e_shentsize 0x3A`、`e_shnum 0x3C`、`e_shstrndx 0x3E`，寻找 `.fwsignature_ga100`，就地覆盖，将 `sh_size` 改为 `0xF800`，把 `.shstrtab` 追加到 EOF，并重写 `e_shoff` | 已被取代。580.159.04 blob 中的 `.fwsignature_ga100` 位于文件偏移量 `0x1D09F0F` |
| `scan_dmem.py` | 使用 pyelftools 的较安全 ELF 补丁变体，将替换节追加到 EOF、遵守 `sh_addralign`，并扫描 DMEM | 已被取代 |
| `nuke.sh`、`b.sh` | PLM 持久性扫描：9 个三写周期共 27 个候选地址，每周期执行两次 FLR，且不加载驱动 | 它们使用的金丝雀字面量是 `0xFACEB13D`，位于 `CANARY_ADDR = 0x6340`，对应 `DMA_TARGET = 0x0800` |
| `falcon_emulator.py` | 本地 Falcon 仿真器 | 不承担关键功能；论文自带的仿真器从未发布 |
| `cmp170hx-unlock.service` | systemd 持久化服务，轮询 `/proc/driver/nvidia/gpus/<BDF>/clients`，每当新的 CUDA 进程打开 GPU 时在 250 ms 内重新应用解锁 | 已被取代。守护进程会在进程打开与重新应用之间发生竞态，也无法挺过一次驱动重载 |
| `/opt/cmpunlocker/daemon/watchdog.py` | 另一种守护进程设计 | 已被取代 |

### 两个值得理解的取代

**磁盘上的 GSP 固件补丁变成驱动内的签名 memdesc。** 直到 2026-07-17，人们一直认为必须把载荷拼入发布版 GSP ELF。期间曾有三个彼此独立的 ELF 补丁器。它们的流水线会将补丁后的 blob 复制到 `/lib/firmware/nvidia/580.159.04/gsp_tu10x.bin`，加载驱动，确认 PLM 读数为 `0xFFFFFFFF`，再恢复原始文件。补丁 `0001` 通过在内存中分配并填充 `0xf800` 大小的 `pSignatureMemdesc`，彻底取代了这套流程。这样既不需要 ELF 手术，也不需要备份和恢复固件文件，还避免了磁盘上遗留补丁 blob 的风险；载荷也可以在两次 Booter 发射之间重新构建。**残留：** `remove.sh` 仍会删除五种 `gsp_tu10x.bin.cmpunlocker.*` 后缀文件。

**用户态守护进程持久化变成补丁内核模块。** 现在，每次补丁模块在 `kgspBootstrap` 中引导 GSP 时都会执行解锁：不需要守护进程，不需要轮询，也不存在重新应用的时间窗口。**残留：** `remove.sh` 仍会停止一个 `cmpunlocker` systemd 单元，并通过 `pkill` 结束看门狗。

### 外泄 ROP 和配方目录

第 1 代有两项工件值得作为技术记住，而不是作为仍可使用的工具记住。

原始 Booter 栈是从晶片中逐 word 恢复的，方法是使用由 gadget `0x7de9` 构建的外泄 ROP。该 gadget 会将选定的 DMEM word 写入 SEC2 邮箱，因此每次引导都能泄露一个 dword。在 DKMS 下大约需要 **35 次引导，每次约 90 s**，每轮约一小时。`D[0xFF74]` 以下的区域无法泄露，因为 ROP 本身就位于那里。由于金丝雀在每次引导时都会重新随机生成，运行两次转储并进行 diff，就能准确找出哪些槽位存放金丝雀，将原本的限制转化为一种分析手段。

当时维护着一个参数化的 ROP 配方目录，其中有八个具名配方。它们在重接点（`0x37b7` 或 `0x37cc`）、劫持 gadget、栈布局和破坏大小（`0xF800`、`0xF810`、`0xF820`）上有所不同：`rejoin_short_37cc`、`whole_stack_37b7`（保护值 `0xFACEB13D`）、`dummy_shift_37cc`、`srw_v1_37b7`、`srw_v2_37cc`、`waa_37cc`、`waa_37b7`、`waa_3747`。研究链标准化的多写模式是 `0x4d4(r0=addr,r1=val,RA=0x10b9) -> [0x10b9 write -> 0x10aa-epi] xN -> TERM`。其中 `0x10b9` 的中途进入形式属于净室逆向和免驱动工具；发布版载荷改用 `0x000010aa`，而发布版代码树中完全没有字符串 `10b9`。见 [ROP 链](../unlock/rop-chain.md)。

---

## 插曲：最初的 `cmpunlocker` 是免驱动 Python

在 **2026-07-14T21:47:02-07:00** 至 **2026-07-18T19:11Z** 之间，公开的 `cmpunlocker` 仓库还不包含任何驱动补丁。它发布的是 `payload/build.py`、`payload/gsp_patch.py`、`payload/pipeline.py`、`payload/bar0.py`、`payload/driver.py`、`unlock/compute.py` 和一个 `daemon/` 看门狗。

它的流水线是：定位 `/lib/firmware/nvidia/*/gsp_tu10x.bin` 并备份，构建一个 `0xF800` 字节的 ROP 载荷，将其拼入 `.fwsignature_ga100` ELF 节，加载原厂模块，执行 FLR，强制卸载，再执行一次 FLR；随后通过 BAR0 从主机写入 SS0 `0x0082381C = 0x88888888` 和 SS1 `0x00823820 = 0x00000008`，最后恢复原始固件。

它的 ROP 构建器为每次写入生成一个帧，使用的仍是当前沿用的帧布局：

```yaml
dmem_layout:   { dma_target: 0x0800, payload_size: 0xF800, guard_addr: 0x6340, canary: 0xFACEB13D }
booter_addrs:  { bar0_write_gadget: 0x10B9 }
payload_frames:
  frame_start_addr: 0xFF48
  frame_stride:     0x18
  frame_field_offsets: { r0: 0x00, r1: 0x04, r2: 0x08, r3: 0x0C, saved_reg: 0x10, return_addr: 0x14 }
```

末尾带有一个返回到 `0x0000810D` 的清零终止帧。它执行的三次写入是 `0x009A0204 = 0x02779000`、`0x00100CE0 = 0x0000020B` 和 `0x00823804 = 0xFFFFFFFF`。

---

## 第 2 代：`cmpunlocker` 发布版驱动补丁

这是规范工具。仓库标语是：“A tool to unlobotomize your NVIDIA card!”（让你的 NVIDIA 显卡摆脱“脑叶切除”状态的工具）。

### `master` 中实际有什么

顶层恰好有八项：

```text
.github/pull_request_template.md
.gitignore
LICENSE
README.md
common/constants.yaml
driver/
install.sh
remove.sh
```

其中**没有** `verify.sh`、**没有** `tools/` 目录、**没有** `probe.sh`、**没有** `requirements.txt`（该文件于 2026-07-19 在 `7019bc2` 中删除），**也没有**测试套件。

### `install.sh`

它分六步执行：检查 root 权限、检测 GPU、选择档位、检查驱动 / Secure Boot / 头文件、构建并安装，最后完成。全部输出都会通过 tee 写入 `logs/install_$(date +%Y%m%d_%H%M%S).log`。

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

如果没有匹配项，安装器会以 `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)` 退出；对于其他设备 ID，它会警告 `In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.`。因此，`10de:20b0` 显卡可以完成安装，但不会被解锁。

`detect_card_profile()` 读取 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1`，并按四个区间映射档位：`>= 60000 MiB` 映射到 `8gb`（表示已解锁），`35000-59999` 映射到 `10gb`，`7680-8704` 映射到 `8gb`，`9728-10752` 映射到 `10gb`。其他数值都会打印 `unknown:<mib>`，随后安装器退出并提示传入 `--profile=8gb|10gb`。

> [!CAUTION]
> **混合 GPU 主机上的自动检测不安全**
>
> `detect_card_profile()` 读取的是 **`nvidia-smi` 列表中的第一张 GPU**，而不是 `lspci` 找到的那张 CMP。比如一台同时安装 RTX 3080 10 GB 和 8 GB CMP 170HX 的系统，会从 RTX 3080 读出“10GB”，从而选择错误档位。至少有两位用户复现了这一问题，其他 CMP SKU 也曾被误判为 10 GB 170HX 卡。**在混合 GPU 主机上始终显式传入 `--profile`。**

Secure Boot 是硬性门槛：如果 `/sys/firmware/efi` 存在、`mokutil` 可用，并且 `mokutil --sb-state` 报告已启用，安装器就会拒绝继续。驱动版本必须精确匹配 `driver/VERSION` 中的一行（`610.43.03`、`610.43.02`）。检测顺序为 `/proc/driver/nvidia/version`、`nvidia-smi --query-gpu=driver_version`、探测 `/lib/firmware/nvidia/<version>/` 目录，最后检查按排序取得的最高版本 `/lib/firmware/nvidia/*/`。内核头文件必须存在于 `/lib/modules/$(uname -r)/build`。

### `driver/build.sh`

它从不携带 NVIDIA 代码，而是通过 `curl -L --fail` 下载 `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`，将其缓存到 `driver/.build/` 下并干净解压；随后用 `patch -p1` 应用每个 `driver/patches/*.patch`，清理 `_out` 和 `conftest`，再使用 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build` 构建。最后，它会将 `nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko` 和 `nvidia-peermem.ko` 以 0644 权限安装到 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。

它还会在该目录写入三个单行元数据文件：`driver_version`、`card_profile`（`8gb` 或 `10gb`）以及 `unlock_geometry`（`64GB` 或 `40GB`）。随后执行 `depmod -a "${KVER}"`，并在 `update-initramfs -u -k`、`dracut --force --kver` 和 `mkinitcpio -P` 中选择第一个可用命令重建 initramfs。

它还会交叉验证补丁模块是否真正生效。重载前，它运行 `modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'`；如果结果不在 `updates/cmpunlocker/` 下，就警告 `Resolved nvidia.ko is not under updates/cmpunlocker/ - stock may still win`。重载后，它将 `/sys/module/nvidia/srcversion` 与 `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko` 比较；如果不匹配，就警告 `Loaded nvidia srcversion (X) != patched (Y)`，清除 `reload_ok`，并建议冷重启后执行 `cat /proc/driver/nvidia/version  (should NOT say dvs-builder)`。

> [!WARNING]
> **`--profile` 已不再选择显存几何布局**
>
> 在 `memory` 分支快照中，`--profile` 确实会通过构建时的 Python 正则重写来选择 CFG1 和 LMR；但当前 `master` 已不是这样。补丁 `0001` 包含 `build.sh` 守卫所查找的全部六个标记，因此重写脚本只会打印 `runtime device-id geometry (profile metadata=<label>)`，然后在不修改任何内容的情况下退出。显存几何布局会在 GSP 引导时根据 `pGpu->idInfo.PCIDeviceID >> 16` 选择。现在，`--profile` 只影响打印的横幅、`EXPECTED_MIB` 和元数据文件。2026-07-18 之前编写的说明在这一点上都是错误的。

### 六个补丁

| # | 文件 | 字节 |
|---|---|---|
| 0001 | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 |
| 0002 | `0002-booter-verify.patch` | 3,988 |
| 0003 | `0003-late-pma.patch` | 10,580 |
| 0004 | `0004-bar0-pramin-clamp.patch` | 861 |
| 0005 | `0005-ce-scrub-workarounds.patch` | 1,642 |
| 0006 | `0006-persistent-sw-state.patch` | 603 |
| | **总计** | **37,415** |

补丁 `0001` 包含完整的解锁逻辑：它将 `pSignatureMemdesc` 扩大到 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL`（63,488 字节），用 `SEC2_POSTBL_TIMING_FILL_DWORD 0x000004a7U` 填充，再将 ROP 栈放入其中，并针对每次 PLM 尝试重新运行 `kgspExecuteBooterLoad_HAL`。**不会对 `gsp_tu10x.bin` 执行 ELF 手术。**

PLM 表有四个条目，每个条目最多尝试两次。WPR2 的低位/高位（`0x001fa824`/`0x001fa828`）会在循环前保存，在每次尝试前重写一次，并在循环结束后再重写一次：

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },   /* note: NOT 0xffffffff */
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

随后执行四次普通的主机寄存器写入：

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* 0x02779000 (20C2) / 0x02669000 (2082) */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* 0x0000020B (20C2) / 0x0000028A (2082) */
```

补丁 `0001` 还将出厂代码中的硬错误 `WPR2 already up` 放宽为 `NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n")`，并将 `pGSCI->fb_length` 重写为 `0x0000001000000000ULL`（64 GB）或 `0x0000000A00000000ULL`（40 GB），同时更新最后一个 FB 区域的 `limit`、`reserved`、`supportCompressed`、`supportISO` 和 `performance = 20`。

内置载荷可以在运行时由 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`（`SEC2_POSTBL_TIMING_DMEM_PATH`）覆盖，驱动通过 `os_open_and_read_file` 加载 `0xf800` 字节。如果文件不存在，驱动会记录 `SEC2_DEBUG: <path> not found (0x%x), using built-in payload`（报告码为 `0x59`，属于良性状态），然后回退到编译进模块的填充数据，其默认单次写入为 `0x009a0148U = 0xffffffffU`。

> [!WARNING]
> **发布版载荷的标记字是 `0xc0deca7e`，不是 `0xFACEB13D`**
>
> `0xc0deca7e` 出现在载荷偏移量 `0x5b40`、`0xf758`、`0xf794`、`0xf7a0` 和 `0xf7c4`。更早的独立 harness 在 `CANARY_ADDR = 0x6340`、对应 `DMA_TARGET = 0x0800` 的位置使用 `0xFACEB13D`。由于 `0x5b40 + 0x0800 = 0x6340`，两者指向同一个槽位，只是字面量不同。阅读发布版代码时，不要想当然地寻找 `0xFACEB13D`。

发布版驱动内栈和独立免驱动链共享**同一套尾部配方**：在载荷偏移量 `0xf78c` 至 `0xf7f8` 的范围内，补丁 0001 写入非零 gadget 序列 `0x815a, 0x8e18, 0x815a, 0x1fbd, 0xffbc, 0x582d, 0xcbd, 0x3, 0x1fbd, 0xccb, 0x7f2f`，并将载荷 word `0x1100` 设为 `0x00000007`。

### `common/constants.yaml`

这是仓库中的机器可读事实基准，与补丁 0001 中的 C 代码完全一致：

```yaml
driver_versions: [610.43.03, 610.43.02]
gpu: { vendor_id: 10de, device_ids: [20c2, 2082] }
compute: { ss0: "0x88888888", ss1: "0x00000008" }
profiles:
  8gb:  { stock_mib: 8192,  unlocked_mib: 65536, cfg1: "0x02779000", lmr: "0x0000020B", fb_bytes: "0x0000001000000000" }
  10gb: { stock_mib: 10240, unlocked_mib: 40960, cfg1: "0x02669000", lmr: "0x0000028A", fb_bytes: "0x0000000A00000000" }
```

### `remove.sh`

卸载器是 `remove.sh`，需要传入 `--yes` 或 `-y`。**整个代码树中都没有 `uninstall.sh`**，无论 `docs` 分支如何描述。它的流程是：停止并禁用遗留的 `cmpunlocker` systemd 单元，执行 `pkill -f /opt/cmpunlocker/daemon/watchdog.py`；删除 `/lib/modules/*/updates/cmpunlocker` 并为每个内核运行 `depmod -a`；重建 initramfs；删除 `/lib/firmware/nvidia/*/gsp_tu10x.bin.cmpunlocker.{bak,patched,tmp,cleanup,pat}`；移除 `/opt/cmpunlocker`；最后停止显示管理器和 `nvidia-persistenced`，强制卸载四个模块，再次执行 `modprobe nvidia`。HiveOS 上的一名测试者报告，运行后两张卡都恢复了挖矿能力；“mod 无破坏性”的说法就是基于这一条报告，置信度为中等。

操作流程见[安装](../procedures/install.md)、[验证](../procedures/verify.md)和[卸载](../procedures/uninstall.md)。

---

## 第 3 代：免驱动 SEC2 refire 链

> [!WARNING]
> **实验性**
>
> 这是一条平行路线，不属于 `cmpunlocker`，也不应该被用于生产环境中的显卡解锁。它之所以值得记录，是因为它是唯一仍在追求项目最初目标的工作线：在不修改驱动的情况下完成解锁。

`refire_chain_v6.py`（27,769 字节，2026-07-24 发布）在用户态执行完整解锁，**不加载 NVIDIA 驱动**，只使用标准库（`os`、`sys`、`mmap`、`ctypes`、`struct`、`time`、`subprocess`）。它将 BAR0 映射为 16 MiB，把 SEC2 的基址视为 `0x00840000`，复位 Falcon，将 NS 代码以非安全方式加载到 IMEM 0，再通过标签寄存器将 HS 代码以安全方式加载到 `IMEM[ns]`；随后加载 DMEM，将 MAILBOX0/1 设置为 WprMeta 的物理地址，启动 CPU，并反复触发签名 Booter 的签名读取 DMA 溢出。

操作流程：

```bash
echo 16 | sudo tee /proc/sys/vm/nr_hugepages
sudo rmmod nvidia_uvm nvidia
BDF=$(python3 -c 'import refire_chain_v6 as V; print(V.resolve_bdf())')
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sudo python3 refire_chain_v6.py --all
```

支持的模式包括：`--compute`（只关闭 SM 和张量节流，常开且具有 FLR 粘性）、`--memory 40`（真实且稳定的档位）、`--memory 80`（80 GB 档位）、`--pcie-gen2`（仅修改 LnkCap2 cap）和 `--pcie-retrain`。环境变量覆盖项为 `CMP_BDF`、`CMP_BOOTER_IMG`、`CMP_BOOTER_SIG`。`--all` 会让显卡保持 READY 状态，以便之后无 FLR 加载驱动。除 `--pcie-retrain`（纯主机写入）外，所有模式都要求解绑 GPU 并配置巨页。

前置条件很严格：需要 root；GPU 必须与所有 NVIDIA 驱动**解绑**；需要一个签名的 GA100 `booter_load` HS ucode 映像（约 60,160 字节，384 字节 RSA-3072-PSS 签名内嵌在 `0x8900`）；需要 16 个巨页；还需要在内核命令行中设置 `intel_iommu=off` 或 `iommu=pt`，使 DMA 物理地址对应主机物理地址。工具会分配一个物理连续的 2 MiB 巨页并对其执行 `mlock`，通过 `/proc/self/pagemap` 解析物理地址（位 63 必须置位，否则会报 `page not present (need hugepages)`），然后调用手工组装的 clflush 加 mfence 桩（`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`），因为“sig-DMA is NONCOHERENT, must hit RAM not CPU cache”（sig-DMA 不具备一致性，必须访问 RAM 而不是 CPU 缓存）。

有一项内部细节需要注意：必须运行 `stage_radix3()`，否则 Booter 在签名前执行的 DMA 会以原因 `0x9` 失败。该函数分配 `0x6000` 字节并写入三级链（`[0x0000] = phys+0x1000`、`[0x1000] = phys+0x2000`、`[0x2000] = phys+0x3000`），然后刷新。WprMeta 模板是从一次真实的 10 GB 引导中捕获的 256 字节结构，只覆盖签名指针（`0x48`）、签名大小（`0x50` = `0xF800`）、radix3 指针（`0x10`）、radix3 大小（`0x18`）、bootloader 指针（`0x20`）和 bootloader 大小（`0x28`）。它的前两个 word 是 WPR 描述符魔数 `0x371a60b3` 和 `0xdc3aae21`。

### 版本谱系

| 版本 | 改动 |
|---|---|
| v1（`refire_chain.py`） | 为每个 PLM 硬编码一个紧凑的双写载荷 |
| v2 | 载荷改为通用写入引擎，接收扁平的 `[(addr, value), ...]` 列表，不包含 WprMeta 或显存几何布局知识。WprMeta 只在投递层构建一次，用作签名 DMA 溢出的触发器。投递原语 `Bar0, alloc, flush, reset_sec2, load_booter, wpr_meta, start_wait, stage_radix3, geometry, fire, PATCHLOC` 原样复用了经硬件验证的 v1 实现。载荷大小为 `0xF800`，入口尾部常量为 `TAIL0 = 0x815a` |
| v6 | 增加上述模式标志、BDF 解析和环境变量覆盖 |

> [!CAUTION]
> **可移植性限制：仅支持 10 GB 卡**
>
> 发布版链携带的是从 **10 GB** 引导中捕获的 WprMeta 模板，不能未经修改地用于 `0x20C2` 8 GB 卡。生成 8 GB 模板是一项已经记录的开放任务：在 8 GB 卡正常进行驱动 GSP 引导时捕获 `pWprMeta`，然后替换模板。由于实际只会覆盖六个字段，风险较低，但目前还没有人完成这项工作。

---

## 第 4 代：尚未合并的分支

已捕获十二个未发布分支的快照（**加上发布版 `master`，共十三棵代码树**）：`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`。远程仓库中共有十六个未发布分支 ref；其中 `code-simplification`、`dual-geometry-fix`、`fix` 和 `v0.1` 没有快照，本维基也没有在任何地方分析它们。见[方法论](../appendix/methodology.md)。

| 分支 | Tip | 它加什么 | 裁决 |
|---|---|---|---|
| `memory` | 2026-07-18 | 最初的驱动内显存解锁，使用单一内置几何布局 | 已合并到 `master` |
| `housekeeping` | 2026-07-18 | `43c762d "Add 2082 (10GB) device support to all patches"`；同时删除 `.ai/CONTEXT.md` 代理指令文件 | 修复后合并 |
| `ecc` | `bb4d669`、2026-07-18 | 单次提交，标题为 "Fixed dual geometry support"。**不包含 ECC 代码** | 已合并。ECC 已由熔丝关闭，目前没有已知的解锁手段 |
| `multiple-cards` | `b1cb6d8`、2026-07-18（07-19 宣布） | 用 `profile_from_devid()`（`20c2` 映射到 `8gb`、`2082` 映射到 `10gb`，其他值不支持）取代 `detect_card_profile()`；遍历**每一条**匹配的 `lspci` 行，构建五个并行数组，并增加将 `SKIP_GEOMETRY_REWRITE=1` 的第三个 `mixed` 档位。导出 `CMPUNLOCKER_GPU_INVENTORY`，持久化到 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`，每张 GPU 一行，格式为 `0000:0b:00.0 20c2 8gb 65536`。增加 `verify.sh` | 未合并。见[多 GPU](../procedures/multi-gpu.md) |
| `80` | `3c53aca`、2026-07-19 | 将补丁 0001 的 10 GB 分支改写为 `cfg1Value = 0x02779000U`（**8 GB** 卡的 CFG1），配合 `lmrValue = 0x0000028AU` 和 `targetFbBytes = 0x0000001400000000ULL` | **不要使用。** 不稳定 |
| `clanker/driver-port` | `153cd6d`、2026-07-21 | 使用按分支划分的补丁目录 `driver/patches/{580,590,595,610}/`，由 `BRANCH="${VERSION%%.*}"` 选择。在 `driver/VERSION` 中列出十二个版本，在 `constants.yaml` 中列出五个版本，形成一个已被承认的内部不一致。它的 `install.sh` 与 master **逐字节相同** | 未合并；610 以下版本从未进行启动测试 |
| `debug-gen2` | `746d9f7 "PCIe Gen 2 works!"`、2026-07-23 | 补丁 0001-0007，以及作为 systemd oneshot 安装的 `tools/retrain.sh` 和 `tools/cmpretrain.service` | 被 `Gen2` 取代 |
| `Gen2` | `2f27474`、2026-07-24；tip `a4de322`、2026-07-26 | `2f27474 "Gen2 + multiple-card support"` 增加 `0008-pcie-gen2-probe-retrain.patch`、多卡支持和 `verify.sh`，并**删除** `tools/cmpretrain.service`（保留 `tools/retrain.sh`）。tip `a4de322` 是一次纯 `master` 合并，只修改 `.github/pull_request_template.md` | 当前 Gen2 基线 |
| `far` | `8854d3e "Remove clamp link to Gen1"`、2026-07-26 | 相对于 `Gen2` 只有一行变化：将 `RMPcieLinkSpeed` 从 `0x1` 改为 `0x2` | |
| `deced` | `2326599`、2026-07-27 | 用 `find_gpu_bdf()` 取代 `tools/retrain.sh` 中硬编码的 BDF。**档案中最新的 Gen2 代码树** | |
| `docs` | `651b6d5`、2026-07-27 | 七次文档提交 | **不具权威性。** 见下文 |
| `PG199` | | Drive A100 对比快照 | 仅供参考 |

### 仅分支工具

`verify.sh` 是一个**仅存在于分支中**的多 GPU 安装后检查器，`master` 上没有它。它优先使用已安装的 `gpu_inventory`，否则通过 `lspci -nn | grep -iE '10de:20c2|10de:2082'` 枚举 GPU。`is_unlocked_memory` 将 `8gb` 的 `>= 60000 MiB` 和 `10gb` 的 `35000..59999 MiB` 视为解锁状态；`is_stock_memory` 接受 `7680..8704` 和 `9728..10752`。每张 GPU 的状态为 `OK`、`STOCK`、`MISSING` 或 `UNEXPECTED`。如果缺少 `SEC2_DEBUG` dmesg 轨迹，只会给出警告而不会失败，因为环形缓冲区可能已经轮转。

> [!NOTE]
> **未解问题**
>
> **`verify.sh` 从不检查 PCIe Gen2，即使在 Gen2 分支谱系中也是如此。** 在 `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 中 grep “pcie”都没有命中。Gen2 验证完全依赖用户手动运行 `nvidia-smi`。修复并不复杂：查询 `nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max`，或者复用 `pcielink.sh` 对 `CAP_EXP+12.w` 的 LnkSta 解码。

### Gen2 谱系中的取代关系

**用户态重训练脚本变成驱动内探测阶段重训练。** `debug-gen2` 会安装 `/usr/local/sbin/retrain.sh` 和 `cmpretrain.service`（`Type=oneshot`、`ExecStartPre=/bin/sleep 15`、`WantedBy=multi-user.target`）。从 `Gen2` 开始，`0008-pcie-gen2-probe-retrain.patch` 在 `kernel-open/nvidia/nv.c` 中加入 `nv_cmp170hx_retrain_gen2()`；它只对 `gpu->device == 0x20c2 || gpu->device == 0x2082` 生效，在探测阶段通过 `pci_upstream_bridge(gpu)` 执行重训练。安装器会主动禁用 `cmpretrain.service` 和 `cmp-gen2-retrain.service`，并用 `rm -f` 删除辅助脚本，同时打印 `Removed legacy PCIe retrain helpers`。挂在 `multi-user.target` 之后、等待 15 秒再执行的 oneshot 既脆弱，又无法在驱动声明设备之前运行。

Gen2 谱系的安装器还会写入 `/etc/modprobe.d/cmp-pcie-gen2.conf` 并配置 IOMMU：除非传入 `--no-iommu`，否则会将 `intel_iommu=on iommu=pt` 或 `amd_iommu=on iommu=pt` 追加到内核命令行。

> [!CAUTION]
> **`Gen2` 实际安装了 Gen1 钳制**
>
> `debug-gen2` 和 `Gen2` 写入 `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`，在尝试启用 Gen2 的同时又将链路钉死在 Gen1。`far` 和 `deced` 则写入 `0x2`。哪个值才正确**仍然没有结论**：两种写法都出现在发布代码中，分别属于其作者确信正确的分支，而且没有 A/B 启动测试。只需在一张卡上进行一次三方启动对比，就能确定答案。

> [!CAUTION]
> **不要照着 `docs` 分支操作**
>
> `docs/INSTALLATION.md` 第 40 行写着 `sudo ./uninstall.sh --yes`（但不存在这样的文件）；`docs/ARCHITECTURE.md` 第 81-82 行声称 `SEC2_DEBUG: SS0 = 0xffffffff` / `SS1 = 0xffffffff`，而发布版代码实际写入 `0x88888888` 和 `0x00000008`；`docs/DEBUGGING.md` 第 15 行说 “All the PLMs must show `0xffffffff`”，但 `0x001fa7cc` 处的 WPR_CFG 实际被打开到 `0xfffff0ff`。该分支还杜撰了代码中任何地方都不存在的缩写展开。

---

## 社区 fork 与相邻工具

发布后的几天内，至少有六个公开仓库 fork 了该项目或重新实现了解锁。

| 仓库 | 性质 |
|---|---|
| `amoghmunikote/cmpunlocker` | 上面描述的参考实现 |
| 几个个人 fork，其中一个带有 `combined-multiple-cards-gen2` 分支 | Fork；其中一个将 Gen2 工作与多卡支持结合。根据本维基的匿名化政策，省略拥有者姓名 |
| `abobasixseven/unlock-cmp-170hx` | **不是技术文章。** 这是一个 AI 代理执行提示，只有 `README.md` 和 `cmp90_compute_unlock_prompt.md` 两个文件；二者都以类似 `EXECUTE STEP BY STEP: 5 (preparation) -> 6 (installation) -> 6.5 (cold reboot) -> 7 (verification)` 的行结尾，并且全文硬编码了一个具体家目录。它的寄存器表与发布版补丁匹配，但其中的说明文字和 PCIe Gen2 章节只是二手总结，不是一手测量 |
| `theneocorp/cmppatcher` | 一种真正不同的方案：直接补丁 NVIDIA 驱动的**二进制文件**，使补丁可以跨驱动更新保留。报告称该方案恢复了 3D 加速并绕过了 FP32 FMA 限制 |

相邻、非解锁工具：

| 工具 | 用途 |
|---|---|
| `CMPGPU-patch-script`（`optimize-cmp-cuda.py`） | 交互式 llama.cpp 源码补丁器，包含五个彼此独立的优化组，每组默认值为 `n`：`fp32_fma_flag`（将 `-fmad=false` 加入 CUDA_FLAGS）、`fp32_fma_split`（将 `fmaf(...)` 重写为 `__fadd_rn(__fmul_rn(...), ...)`）、`math_intrinsics`、`dp2a`、`fp16_bf16_cuda_core`。七个文件中共有十一项 PatchSpec；使用 `.cmp-bak` 备份，并支持 `--dry-run`、`--no-backup`、`--restore`。其 README 警告，在非 170HX 的 CC 8.x 设备上性能可能**下降** |
| `170tune`（`/usr/local/bin/170hx-oc`） | 调优和资格测试 harness，用于测量、限制并恢复时钟和电压设置，并坚持认为“完成一次基准测试不等于获得证据”。它附带一份 26,987 字节的调优指南。其设置是否能跨重启持久化仍是未解问题。见[调优](../operations/tuning.md) |
| `cmp170hx-gen2-setup.sh`（12,389 B、2026-07-26） | 独立的 Gen2 设置工件，不同于 `Gen2` 分支的驱动内方案，并随附一份 `PCIE_GEN1_LOCK.md` 分析 |
| `unlock_host_610.sh` | 面向 nvidia-open 610.43.03 的主机侧脚本：从 `vfio-pci` 解绑，清除 `driver_override`，结束 `nvidia-persistenced`，卸载四个模块，执行 `modprobe ecdh_generic ecc ecdsa_generic`（该模块有密码学依赖），`insmod kernel-open/nvidia.ko`，断言 `/sys/module/nvidia/version == 610.43.03`，`insmod nvidia-uvm.ko`，将 BDF 写入 `/sys/bus/pci/drivers/nvidia/bind`，然后用 `mknod` 创建设备节点。绑定会触发 `RmInit`，进而触发驱动内解锁 |

### FMA 变通方案家族

FP32 FMA 限制是在编译时绕过的，与任何解锁方案无关：OpenCL 使用 `#pragma OPENCL FP_CONTRACT OFF` 并通过宏遮蔽 `fma()` 和 `mad()`，CUDA 使用 `nvcc -fmad=false`，SYCL 使用 clang 的 `-ffp-contract=off`。必须同时抑制显式调用和 `a * b + c` 的隐式融合，数值结果也会从一次舍入变为两次舍入。

---

## Booter 提取工具链

只有在研究利用本身时才需要这套工具链；解锁显卡不需要它。

获取可读 Booter 反汇编结果的文档化流程如下：

```text
extract the debug binary from the NVIDIA .ko with the Nouveau extraction tool
  -> decrypt with rijndael-tool using NVIDIA's public test key
  -> check it is not compressed (NVIDIA uses a compressor called binHex)
  -> disassemble with envytools (envydis, target fuc5)
  -> annotate
```

`nouveau/extract-firmware-nouveau.py` 必须针对 GA100 打补丁，因为生成的 C 数组名变成了 `kgspBinArchiveBooter{LOAD}Ucode_{GPU}_BINDATA_LABEL_IMAGE_{fuse.upper()}_data` 这一形式。原始脚本通过 `--debug-fused` 参数选择 prod 或 debug ucode，默认选择 prod；它还需要来自匹配的**闭源**驱动包的固件 `.bin` 文件。固件版本列在 `version.mk` 中，*不是*开源分支的版本号。

在开源驱动中，签名的 HS ucode 位于 `src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`，包含三个档案条目：`..._IMAGE_PROD`（使用 NVIDIA 自有的 bindata 压缩器压缩，不是普通 zlib）、`..._SIG_PROD`（未压缩的 384 字节数组）和 `..._PATCH_LOC`（4 字节，值为 `0x8900`）。映像大小约为 60,160 字节。

另一种提取方法是：通过 SEC2 Falcon 窗口，从已加载的原厂驱动中实时转储 Booter，基址为 `0x840000`。为启用自动递增读取，写入 `IMEMC (0x840180) = off | (1 << 25)`，然后循环读取 `IMEMD (0x840184)`，其中 `off = 0 ... 0x8700`；DMEM 也采用同样方法，通过 `DMEMC (0x8401c0)` / `DMEMD (0x8401c4)` 读取。置信度为**中等**：流程描述具体，寄存器地址也看起来正确，但从未有人公开捕获的转储，而且必须在驱动通过 PIO 加载 Booter 后、复用 SEC2 之前立即读取。

生产版 Booter 既不能修改，也不能直接读取，因为它使用强密钥加密。因此，利用方案通过栈改变**执行流**，而不是修改代码，从而不需要重新签名。

> [!NOTE]
> **未解问题**
>
> `envydis` 使用 `fuc5` 目标可以成功反汇编 GA100 Booter，尽管 envytools 的表面定义将 `fuc6` 分配给 GP102 及之后的部件。envytools 已约 8 年没有更新；有人建议用 `envyhooks` 作为继任者，但它缺少等效功能；`faucon` 只支持 fuc5。170HX SEC2 在正式定义上究竟属于 fuc5 还是 fuc6，仍未确定。下一步是对同一映像分别进行 fuc5 和 fuc6 解码，再比较哪些指令只有其中一个目标能够连贯解码。

---

## 已失效路径总览

不要采用以下任何路线。

| 失效路线 | 原因 | 应改用 |
|---|---|---|
| 在磁盘上补丁 `gsp_tu10x.bin`（`patch_gsp.py`、`payload-lnject.py`、`scan_dmem.py`） | 已被驱动内签名 memdesc 取代，而且会在磁盘上留下补丁 blob | `cmpunlocker` 补丁 `0001` |
| systemd 持久化（`cmp170hx-unlock.service`、`watchdog.py`） | 进程打开与重新应用之间存在竞态，无法挺过驱动重载 | `/lib/modules/.../updates/cmpunlocker/` 中的补丁模块 |
| `deploy.py --path vbios-memory` | 从未成功；当时修改后的 VBIOS 会产生无法工作的设备 | 寄存器级解锁 |
| `stack_gen.py` v1 | 将所有金丝雀槽清零，触发 `0x7dd9` 处的 `__stack_chk_fail` | 任意后续版本的载荷构建器 |
| 手动五步 TTY 流程 | 已于 2026-07-18 被取代 | `sudo ./install.sh` |
| 将 `--profile` 用作几何布局选择器 | 在 `master` 上已降级为元数据标签 | GSP 引导时按 PCI ID 选择几何布局 |
| `sudo ./uninstall.sh --yes` | 不存在这个文件 | `sudo ./remove.sh --yes` |
| `Gen2`/`far`/`deced` 中的 `tools/retrain.sh` | 已是死代码；安装器会删除它，补丁 0008 会在内核中执行重训练 | 补丁 `0008` |
| `80` 分支 | 超过约 40 GB 后不稳定 | 10 GB 卡使用 40 GB 档位 |
| `docs` 分支 | 存在有记录的事实错误 | 本维基和源码 |
| 除 `check_fold.py` 以外的任何折叠 harness | 更早的 harness 曾将原生内存错误报告为折叠 | `check_fold.py` |
| 把 `gsp_tu10x.bin` 当作 Booter 解密 | 它是 GSP RISC-V ELF 载荷，不是 SEC2 Falcon Booter。Ghidra 从中生成约 100 MB 的 C 代码，objdump 生成约 1.5 GB 的汇编 | 反汇编 `booter_load_ga100_*.bin`，其大小约 25 kB，生成的汇编约 390 kB |

---

## 参见

- [项目时间线](timeline.md)：记录上述每次取代发生的日期
- [净室与来源溯源问题](clean-room-and-provenance.md)
- [失败路线](dead-ends.md)
- [六个驱动补丁](../unlock/driver-patches.md)和[ROP 链](../unlock/rop-chain.md)
- [安装](../procedures/install.md)、[验证](../procedures/verify.md)和[排障](../procedures/troubleshooting.md)
- [寄存器参考](../unlock/register-reference.md)和[寄存器索引](../appendix/register-index.md)
