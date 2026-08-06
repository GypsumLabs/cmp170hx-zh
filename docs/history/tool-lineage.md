# 工具谱系：用什么、什么死了

## 本页覆盖内容

四代 CMP 170HX 工具并存，且时间上彼此重叠，所以"更新"并不总意味着"取代"。本页从 2026 年 6 月第一次手动 BAR0 poke 一路追溯到出货的驱动内补丁集及其上的分支结构，并直白说明哪些路径已死，免得有人再踩进去。

**如果你只想要短答案：**

- 要**解锁一张卡**、用 `cmpunlocker` `master`：`install.sh` 加 `driver/build.sh` 加六个补丁。其它一切都是历史或实验。
- 要**测量一张卡**、用第 0 代只读工具（`probe.sh`、`pcielink.sh`、`check_fold.py`、VBIOS 转储器）。这些从未被废弃。
- **不要**用任何 Python ROP 解锁器、任何 GSP ELF 补丁器、或第 1 代任何 systemd 持久化守护进程。那一代每个持久化机制都被取代了。
- **不要**期望在仓库里找到测量工具。`master` 没有 `tools/` 目录。`probe.sh`、`pcielink.sh`、`check_fold.py`、`cuda_dbg.py`、A100 探测套件和 `refire_chain*.py` 脚本都是作为 gist 和频道附件带外分发的。

---

## 谱系一览

| 代 | 时期 | 工具 | 状态 |
|---|---|---|---|
| **0：只读表征** | 2026-05-31 至今 | `probe.sh`（mmio-probe）、`z1_dump_and_parse_vbios.sh` + `z2_parse_vbios_table.py`、`pcielink.sh`、A100 `probe.py`/`sweep.sh`、`cuda_dbg.py`、`check_fold.py`、`cuda_memtest` | **当前。** 从未被废弃。这些是测量仪器、不是解锁器 |
| **1：手动 BAR0 poke 和 Python ROP 解锁器** | 2026-06-22 到 2026-07-17 | `deploy.py --path sec2-rop`、`deploy.py --path vbios-memory`、`load_custom_bin.py`、`unlc.py`、`stack_gen.py`、`patch_gsp.py`、`payload-lnject.py`、`scan_dmem.py`、`nuke.sh`、`b.sh`、`falcon_emulator.py`、systemd `cmp170hx-unlock.service` | **已废弃。** 这里每个持久化机制都被取代了 |
| **2：出货驱动补丁（`cmpunlocker`）** | 2026-07-14 至今 | `install.sh`、`driver/build.sh`、`driver/patches/0001`-`0006`、`remove.sh`、`common/constants.yaml`、`driver/VERSION` | **当前且规范。** 这是 `master` 上发货的 |
| **3：免驱动 SEC2 refire 链** | 2026-07-22 至今 | `refire_chain.py`（v1）、`refire_chain_v2.py`、`refire_chain_v6.py` | **当前但实验性。** 一条平行、非发货路径；不是 `cmpunlocker` 的一部分 |
| **4：未合并特性分支** | 2026-07-18 至今 | `multiple-cards`、`clanker/driver-port`、`80`、`debug-gen2` 到 `Gen2` 到 `far` 到 `deced`、加 `docs`、`ecc`、`housekeeping`、`memory`、`PG199` | **实验性。** 坐在第 2 代之上 |

---

## 第 0 代：测量仪器

这些工具先于解锁出现，为熔丝表征而建，至今仍是正确的工具。整个项目的治理纪律正源于此：**任何写入之后，都要用 `probe.sh` 回读寄存器，而不是轻信某个工具声称的成功。**

### `probe.sh`（tools/mmio-probe）

一个自包含的 bash 加内联 Python 工具，它只读地 mmap `/sys/bus/pci/devices/<BDF>/resource0` 并转储约 120 到 130 个具名寄存器加 24 个每-FBPA 读。它**从不对 BAR0 写**。

```bash
./probe.sh [pci_id]      # 默认过滤 10de:
# 输出到 ${OUTDIR:-/tmp/mmio-probe-$(date +%s)}
```

| 属性 | 值 |
|---|---|
| 访问模式 | `os.open(..., os.O_RDONLY)`、`mmap.mmap(fd, 0, access=mmap.ACCESS_READ)`、`struct.unpack_from('<I', bar, off)` |
| 输出 | `registers.json`、`lspci.txt`、`nvidia-smi.txt`、`gpu-summary.csv`、`probe.log`、打包到 `/tmp/mmio-probe-$(hostname)-YYYYmmdd-HHMMSS.tar.gz` |
| `registers.json` 键 | `targets`（名字到偏移量/值/为什么）、`fbpa_capacity`、`fbpa_cfg0` |
| 每-FBPA 常量 | `FBPA_BASE = 0x900000`、`FBPA_STRIDE = 0x4000`、`CSTATUS_RAM = 0x20C`、`FBPA_COUNT_TO_PROBE = 24` |
| 派生地址 | fbpa00 CSTATUS_RAMAMOUNT `0x0090020C`、fbpa01 `0x0090420C`、fbpa23 `0x0095C20C`；CFG0 在偏移量 `0x200`；广播 CFG0 `0x009A0200`、CFG1 `0x009A0204` |
| 可选 CUDA 步骤 | 用 `nvcc -arch=sm_70 -O2` 编译并运行 `sr_dump.cu`、以 `dump_sr<<<p.multiProcessorCount, 32>>>()` 启动、报告每 SM 的 `%smid`、`%warpid`、`%nsmid`、`%nwarpid`、`%lanemask_eq`、所以 **SM 数被测量、而非被报告**（170HX 上 70）。`nvcc` 缺失时带日志行跳过 |

`gpu-summary.csv` 捕获 `driver_version` 和 `vbios_version`，这正是把一次探测结果绑定到具体 VBIOS 的关键。该工具建在 MODS/MATS 之上，预期可移植到其它卡，但也带着"registers may be in diff ranges etc though"（寄存器可能在不同范围等）这个注意。

读 BAR0 需要 root **加** `CAP_SYS_RAWIO`，而容器化的 GPU 宿主会丢弃它；探测随后会以 `cannot open .../resource0 (EPERM) even as root` 抛出。如果 `mmap` 以 EBUSY 或 EACCES 失败，说明 NVIDIA 驱动持有 BAR：

```bash
sudo systemctl stop nvidia-persistenced; sudo nvidia-smi -pm 0
# 或、更强力地
echo <BDF> | sudo tee /sys/bus/pci/drivers/nvidia/unbind
```

GA100 BAR0 是一个 16 MiB PRI 孔径（`0x1000000`）；偏移量 0 处的 `PMC_BOOT_0` 识别芯片：`0x170000a1` GA100、`0xb72000a1` GA102、`0xb74000a1` GA104。

> [!WARNING]
> **宣传的 `/dev/mem` 回退不存在**
>
> 头部注释第 9 行读 `# Falls back to /dev/mem path if resource0 fails.`（在 resource0 失败时回退到 /dev/mem 路径。）resource0 解析块实际以 `log "ERROR: cannot find resource0 for $PCI_BDF"; ... exit 2` 结束。那条代码路径从未被写过。

### VBIOS 工具

`z1_dump_and_parse_vbios.sh` 通过三个 sysfs 命令（`echo 1 > .../rom`、`cat`、`echo 0 >`）无破坏地转储 VBIOS，并以无前缀的 sysfs 路径、再以 `nvflash --save` 作为回退。它**对闪存是只读的**：不存在写路径。没有转储方法存在时退出 2，转储为空时退出 3。

`z2_parse_vbios_table.py` 通过四个魔数定位 ROM 结构：偏移量 0 处的 `NVGI`、经 `+0x18` 处 ROM 头指针的 `PCIR`、BIT 模式 `ff b8 42 49 54 00`、和绝对 `0x2000` 处的 `RFRD`。CFG1 跳线表通过一次 `0x30000` 到 `0xB0000` 的步长-1 扫描自动定位、找 16 个连续 4 字节条目、其字节+2 在 `{0x44,0x55,0x66,0x77}` 里、字节+3 在 `{0x02,0x22}` 里。

> [!WARNING]
> **解析器的标签在四处过时**
>
> 它的 `extract_cfg1_strap_table` docstring 引用 "~0x3FB18 in A100 PCIe" 而对比表把它放在 `0x4285A`；`extract_rfrd` 叫 RFRD 一个 "power table"（功耗表）而它是一个映像布局描述符、`field_0C` 是 MAC 验证的范围大小、不是功耗上限；`extract_fbpa_tier_table` 能匹配 CFG1 表本身并报告一个重复；`find_subsystem_id` 是一个桩。任何逐字引用工具输出标签的人都会传播全部四个。见[VBIOS](../hardware/vbios.md)。

### `pcielink.sh`

标准 PCIe 现场报告收集器，也是应该附到任何链路相关 bug 报告上的东西。它自动发现 `10de:20c2` / `10de:2082`（回退到任何 NVIDIA 3D 控制器），并在端点和它的父桥两者上解码：

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

加 sysfs 链路速度和位宽、`nvidia-smi pcie.link.gen`、AER 计数器，以及带 OPT 熔丝三元组的 `SEC2_DEBUG` dmesg 行数。该工具在两台独立解锁的双卡 Gen2 机架（一台 HiveOS、一台 Unraid）上打印 `SEC2_DEBUG lines=152`，配 `OPT=00000001/00000001/16680000`。

> [!NOTE]
> **行数不是可靠的跨构建指纹**
>
> 每个记录的值都不同：归档单卡 8 GB 捕获上 29、归档双卡 Gen2 分支 `610.43.03` 日志上 134、报告工具上 34（Gen1 构建）和 80（Gen2 构建）、`pcielink.sh` 在两台双卡 Gen2 机架上 152。不要把不匹配读成一次失败的安装。

### A100 探测套件

一个三步、可选写工作流、用来构建 Gen2 差分：

```bash
python3 probe.py which
sudo python3 probe.py inventory --out a100_native.json   # 只读
sudo ./sweep.sh                                          # 强制 Gen1/2/3、经 EXIT 陷阱自动恢复
sudo python3 probe.py write-test --confirm               # 写然后立即恢复
```

`write-test` 碰 `0x880a8`（目标速度到 2）、`0x8c044`（到 `0x00000002`）和 `0x88088`（重训练位 5），把每个分类为 `WROTE-OK` 或 `REJECTED(PLM?)`。掩码读哨兵是 `0xBADF5040`。套件里没有任何东西写熔丝或跨重启持久。请在 GPU 空转时运行：sweep 会重训练活链路。

### VRAM 验证器

| 工具 | 它证明什么 | 机制 |
|---|---|---|
| **`check_fold.py`** | **权威。** 解锁的 VRAM 是否真实、非别名 | 分配全部空闲 VRAM 减 2 GiB、用 PTX `sm_80` `fill` 内核写每个 64 KB 页自己的索引、用 `chk` 内核读每个页回来。必须稠密：折叠在一个通道-**交错**偏移量处别名、所以 `LOW[0]` 映射到 `(40 GiB + interleave)`、不是 `(40 GiB + 0)`、一次稀疏探测给出假阴性。用 `libcuda` 经 ctypes、`st.global.wt.u32` 和 `ld.global.cv.u32` 挫败缓存。输出 `REAL, NO FOLD` 或 `FOLD/mismatch @<pageindex>`；真实退出 0、折叠 1、错误 2 |
| `cuda_dbg.py` | 更轻的别名测试 | `cuMemGetInfo_v2`、然后在 64、60、56、52、48、44、42 GiB 的 `cuMemAlloc_v2` 直到一个成功；在偏移量 0 写 `0xAAAA0000`、在 40 GiB 写 `0xBBBB0000`、读偏移量 0。读回 `0xBBBB0000` 意味着空间别名。它泄漏它的分配、所以每次驱动加载跑一次 |
| `cuda_memtest` 1.2.3 | 社区 VRAM 验证器 | 遇到第一个错误就退出。在一张解锁卡上报告 `global memory size=85545582592`。在 80 GB 档位上打印 `Attached to device 0 successfully.` 然后无限期挂起、除非封顶在 39 GB |

> [!CAUTION]
> **一个更早的折叠 harness 自己坏了**
>
> 一次 SBR 回到一致原生态（10240 MiB、驱动 610.43.03、CFG1 `0x02449000`）后的对照运行分配了 9 GiB 真原生内存、并跨五次趟报告 "4608 chunks、4608 corrupt/aliased"、即原生内存"折叠"、那是不可能的。同一个 harness 更早曾报告 10 GiB 在第 1 趟以约 26.6 GB/s 被完全别名、然后在第 2 到 5 趟以 197 到 198 GB/s。这追溯性地使一批 fold-at-40 GB 结论失效。用 `check_fold.py`、不要用任何更早 harness 的输出。

整个测试中使用的标准驱动拆掉序列、仍然正确：

```bash
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
echo 1 | sudo tee /sys/bus/pci/devices/<BDF>/reset
```

---

## 第 1 代：手动 BAR0 poke 和 Python ROP 解锁器

### 那个时代长什么样

2026-07-12 的工作手动流程，发生在任何驱动内补丁存在之前：

```text
run the ROP script -> FLR -> kill the NVIDIA driver -> FLR again -> run the SM unlock script
```

从 TTY 跑，在开源内核模块 580.159.04 上，ROP 载荷由 `patch_gsp.py` 拼进 `gsp_tu10x.bin`。`unlc.py` 演示了出货补丁仍沿用的两步模型：利用只须打开 FEAT PLM，之后 SS0 和 SS1 就是普通的主机写。

### 工具以及每个怎么死的

| 工具 | 角色 | 命运 |
|---|---|---|
| `deploy.py --path sec2-rop` | 编排器、写一个 63,232 B 载荷到 `/var/lib/cmp170hx/payload.bin`、装一个 systemd 单元 | 被驱动内投递取代。它的首个发布也因把 `--verify` 传给 argparse 不接受它的 `load_custom_bin.py` 而中止（退出码 2、不是硬件失败）。2026-06-24 修复 |
| `deploy.py --path vbios-memory` | 重写 VBIOS 里的 CFG1 跳线档位 | **从没工作。** 产生 `[vbios-memory] ERROR: Not a PCI Option ROM (bad magic at 0x00)`：它预期内部映像、而非原始 ROM 转储。整个 VBIOS-显存方法于 2026-06-23 被放弃 |
| `load_custom_bin.py` | 加载一个 Falcon 二进制并转储 DMEM | 被吸收进 refire 链的投递原语 |
| `unlc.py` | PLM 打开后的主机侧 SS0/SS1 写器 | 它的模型存活在补丁 0001 内；脚本没有 |
| `stack_gen.py` | ROP 栈构建器 | 首个发布**把所有金丝雀槽清零**、不可能工作：`D[0x6340]` 处的金丝雀必须被复制进每个帧、否则 `__stack_chk_fail`（`0x7dd9`）触发。常量是 `exit_addr 0x79e7`、`payload_size 0xF700`、`dma_target 0x0900`、`stack_start 0xf75c` |
| `patch_gsp.py`、`payload-lnject.py` | 对 `gsp_tu10x.bin` 的 ELF 手术：解析 `e_shoff 0x28` 处的 ELF64 头、`e_shentsize 0x3A`、`e_shnum 0x3C`、`e_shstrndx 0x3E`、找 `.fwsignature_ga100`、就地覆写、把 `sh_size` 补丁到 `0xF800`、把 `.shstrtab` 追加到 EOF、重写 `e_shoff` | 被取代。`.fwsignature_ga100` 在 580.159.04 blob 里坐在文件偏移量 `0x1D09F0F` |
| `scan_dmem.py` | 用 pyelftools 的更安全 ELF 补丁变体、把替换节在 EOF 追加、遵守 `sh_addralign`、加 DMEM 扫描 | 被取代 |
| `nuke.sh`、`b.sh` | PLM 持久性扫描（27 个候选地址、9 个三写周期、每周期两个 FLR、无驱动加载） | 它们的金丝雀字面量是 `CANARY_ADDR = 0x6340` 配 `DMA_TARGET = 0x0800` 处的 `0xFACEB13D` |
| `falcon_emulator.py` | 本地 Falcon 仿真 | 非承重；论文自己的仿真器从未发布 |
| `cmp170hx-unlock.service` | systemd 持久化、轮询 `/proc/driver/nvidia/gpus/<BDF>/clients`、每当一个新 CUDA 进程打开 GPU 时在 250 ms 内重新应用 | 被取代。守护进程在进程打开对重新应用之间赛跑、无法挺过一次驱动重载 |
| `/opt/cmpunlocker/daemon/watchdog.py` | 替代守护进程设计 | 被取代 |

### 两个值得理解的取代

**磁盘上 GSP 固件补丁变成驱动内签名 memdesc。** 到 2026-07-17 前，人们相信载荷必须被拼进发货的 GSP ELF。存在三个独立的 ELF 补丁器。流水线把打过补丁的 blob 复制到 `/lib/firmware/nvidia/580.159.04/gsp_tu10x.bin`、加载驱动、验证 PLM 读 `0xFFFFFFFF`，然后恢复原版。补丁 `0001` 通过把 `pSignatureMemdesc` 分配在 `0xf800` 并在内存里填满它，取代了全部这些。无 ELF 手术、无需要备份或恢复的固件文件、无在磁盘上留下打过补丁 blob 的风险，而且载荷能在 Booter 发射之间重建。**残留：** `remove.sh` 仍删除五个 `gsp_tu10x.bin.cmpunlocker.*` 后缀。

**用户态守护进程持久化变成打过补丁的内核模块。** 解锁现在在打过补丁的模块每次引导 GSP 时、于 `kgspBootstrap` 内运行：无守护进程、无轮询、无重新应用窗口。**残留：** `remove.sh` 仍停一个 `cmpunlocker` systemd 单元并 `pkill` 看门狗。

### 外泄 ROP 和配方目录

两个第 1 代工件值得作为技术而非工具记住。

原始 booter 栈从硅片一次一个词地被恢复，借助一个由 gadget `0x7de9` 构建的外泄 ROP：那个 gadget 把一个选定的 DMEM 字写进 SEC2 邮箱，所以每次引导漏出一个 dword。DKMS 下约 **35 次引导、每次约 90 s**，即每趟约一小时。`D[0xFF74]` 之下的区域无法被泄露，因为 ROP 自己坐在那里。由于金丝雀每次引导都会重新随机，跑两遍转储并 diff 就能精确揭示哪些槽是金丝雀：一个把限制变成技术的东西。

八个具名 ROP 配方被维护为一个参数化目录，在重接点（`0x37b7` 对比 `0x37cc`）、劫持 gadget、栈风格和粉碎大小（`0xF800`、`0xF810`、`0xF820`）上各不相同：`rejoin_short_37cc`、`whole_stack_37b7`（守卫 `0xFACEB13D`）、`dummy_shift_37cc`、`srw_v1_37b7`、`srw_v2_37cc`、`waa_37cc`、`waa_37b7`、`waa_3747`。研究链标准化的多写模式是 `0x4d4(r0=addr,r1=val,RA=0x10b9) -> [0x10b9 write -> 0x10aa-epi] xN -> TERM`。那个 `0x10b9` 中途进入形式属于净室和免驱动工具：出货载荷种 `0x000010aa` 代替，而字符串 `10b9` 出现在出货树里任何地方都不。见[ROP 链](../unlock/rop-chain.md)。

---

## 插曲：第一个 `cmpunlocker` 是免驱动 Python

在 **2026-07-14T21:47:02-07:00** 和 **2026-07-18T19:11Z** 之间、公开 `cmpunlocker` 仓库不含任何种类的驱动补丁。它发货 `payload/build.py`、`payload/gsp_patch.py`、`payload/pipeline.py`、`payload/bar0.py`、`payload/driver.py`、`unlock/compute.py` 和一个 `daemon/` 看门狗。

它的流水线：定位 `/lib/firmware/nvidia/*/gsp_tu10x.bin`、备份它、构建一个 `0xF800`-字节 ROP 载荷、把它拼进 `.fwsignature_ga100` ELF 节、加载出厂商模块、FLR 复位、激进卸载、再 FLR 复位、从主机经 BAR0 写 SS0 `0x0082381C = 0x88888888` 和 SS1 `0x00823820 = 0x00000008`，然后恢复原版固件。

它的 ROP 构建器每次写发一个帧、在一个仍在使用的网格上：

```yaml
dmem_layout:   { dma_target: 0x0800, payload_size: 0xF800, guard_addr: 0x6340, canary: 0xFACEB13D }
booter_addrs:  { bar0_write_gadget: 0x10B9 }
payload_frames:
  frame_start_addr: 0xFF48
  frame_stride:     0x18
  frame_field_offsets: { r0: 0x00, r1: 0x04, r2: 0x08, r3: 0x0C, saved_reg: 0x10, return_addr: 0x14 }
```

带一个返回到 `0x0000810D` 的零终止符帧。它的三次写是 `0x009A0204 = 0x02779000`、`0x00100CE0 = 0x0000020B` 和 `0x00823804 = 0xFFFFFFFF`。

---

## 第 2 代：`cmpunlocker`、出货驱动补丁

这是规范工具。仓库标语："A tool to unlobotomize your NVIDIA card!"（一个给你的 NVIDIA 卡去脑叶的工具！）。

### `master` 实际含什么

恰好八个顶级项：

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

**没有** `verify.sh`、**没有** `tools/` 目录、**没有** `probe.sh`、**没有** `requirements.txt`（2026-07-19 在 `7019bc2` 删除）**也没有** `master` 上的测试套件。

### `install.sh`

六步：root 检查、GPU 检测、档位选择、驱动 / 安全启动 / 头文件检查、构建并安装、完成。一切都 tee 到 `logs/install_$(date +%Y%m%d_%H%M%S).log`。

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

没有匹配时以 `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)` 死掉、并对任何其它设备 ID 警告 `In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.`。一张 `10de:20b0` 卡因此安装却不解锁。

`detect_card_profile()` 读 `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1` 并映射四个窗口：`>= 60000 MiB` 到 `8gb`（已解锁）、`35000-59999` 到 `10gb`、`7680-8704` 到 `8gb`、`9728-10752` 到 `10gb`。其它任何值打印 `unknown:<mib>` 而安装器死掉、告诉你传 `--profile=8gb|10gb`。

> [!CAUTION]
> **自动检测在混合-GPU 主机上不安全**
>
> `detect_card_profile()` 读 **`nvidia-smi` 顺序里的第一张 GPU**、不是 `lspci` 找到的 CMP。一张带 RTX 3080 10 GB 配 8 GB CMP 170HX 的系统从 3080 检测出 "10GB" 并选错档位。被至少两位用户复现；其它 CMP SKU 也被误检测为 10 GB 170HX 卡。**在混合-GPU 主机上始终显式传 `--profile`。**

安全启动是一个硬门：如果 `/sys/firmware/efi` 存在、`mokutil` 存在且 `mokutil --sb-state` 报告启用、安装器拒绝。驱动版本必须精确匹配 `driver/VERSION`（`610.43.03`、`610.43.02`）里的一行、按顺序从 `/proc/driver/nvidia/version`、然后 `nvidia-smi --query-gpu=driver_version`、然后 `/lib/firmware/nvidia/<version>/` 的一次目录探测、然后排序最高的 `/lib/firmware/nvidia/*/` 检测。内核头文件必须存在于 `/lib/modules/$(uname -r)/build`。

### `driver/build.sh`

它从不运送 NVIDIA 代码。它用 `curl -L --fail` 下载 `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`、缓存它在 `driver/.build/` 下、干净解压、用 `patch -p1` 应用每个 `driver/patches/*.patch`、清除 `_out` 和 `conftest` 后用 `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build` 构建、并把 `nvidia.ko`、`nvidia-modeset.ko`、`nvidia-uvm.ko`、`nvidia-drm.ko` 和 `nvidia-peermem.ko` 以模式 0644 安装进 `/lib/modules/$(uname -r)/updates/cmpunlocker/`。

它在那里写三个单行元数据文件：`driver_version`、`card_profile`（`8gb` 或 `10gb`）和 `unlock_geometry`（`64GB` 或 `40GB`）、然后跑 `depmod -a "${KVER}"` 并经 `update-initramfs -u -k`、`dracut --force --kver` 或 `mkinitcpio -P` 里第一个可用的重建 initramfs。

它还交叉核对打过补丁的模块赢了。重载前它跑 `modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'` 并警告 `Resolved nvidia.ko is not under updates/cmpunlocker/ - stock may still win`。重载后它对比 `/sys/module/nvidia/srcversion` 与 `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko`、不匹配时警告 `Loaded nvidia srcversion (X) != patched (Y)`、清除 `reload_ok`、并建议一次冷重启加 `cat /proc/driver/nvidia/version  (should NOT say dvs-builder)`。

> [!WARNING]
> **`--profile` 不再选择几何布局**
>
> 在 `memory` 分支快照上、`--profile` 真正经一次构建时 Python 正则重写选择 CFG1 和 LMR。在当前 `master` 上它不。补丁 `0001` 含 `build.sh` 守卫找的全部六个标记、所以重写打印 `runtime device-id geometry (profile metadata=<label>)` 并在不编辑任何东西的情况下退出。几何布局在 GSP 引导时从 `pGpu->idInfo.PCIDeviceID >> 16` 选择。`--profile` 现在只影响打印的横幅、`EXPECTED_MIB` 和元数据文件。2026-07-18 前写的指示对此是错的。

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

补丁 `0001` 携带整个解锁：它把 `pSignatureMemdesc` 放大到 `SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL`（63,488 字节）、用 `SEC2_POSTBL_TIMING_FILL_DWORD 0x000004a7U` 填满它、往里放一个 ROP 栈、并为每次 PLM 尝试重跑 `kgspExecuteBooterLoad_HAL`。**对 `gsp_tu10x.bin` 不发生 ELF 手术。**

PLM 表四个条目、每个最多两次尝试、WPR2 低/高（`0x001fa824`/`0x001fa828`）在循环前保存、在每次尝试前重写、循环后再一次：

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },   /* 注意：不是 0xffffffff */
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

然后四次普通主机寄存器写：

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* 0x02779000 (20C2) / 0x02669000 (2082) */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* 0x0000020B (20C2) / 0x0000028A (2082) */
```

补丁 `0001` 还把出厂 `WPR2 already up` 硬错误放宽成 `NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n")`、并把 `pGSCI->fb_length` 重写到 `0x0000001000000000ULL`（64 GB）或 `0x0000000A00000000ULL`（40 GB）加最后一个 FB 区域的 `limit`、`reserved`、`supportCompressed`、`supportISO` 和 `performance = 20`。

内置载荷可在运行时从 `/lib/firmware/nvidia/ga100/gsp/dmem.bin`（`SEC2_POSTBL_TIMING_DMEM_PATH`）覆盖、`os_open_and_read_file` 加载 `0xf800` 字节。缺席时驱动记录 `SEC2_DEBUG: <path> not found (0x%x), using built-in payload`（报告码是 `0x59`、良性）并回退到编译进的填充、其默认单写是 `0x009a0148U = 0xffffffffU`。

> [!WARNING]
> **出货载荷的标记字是 `0xc0deca7e`、不是 `0xFACEB13D`**
>
> `0xc0deca7e` 出现在载荷偏移量 `0x5b40`、`0xf758`、`0xf794`、`0xf7a0` 和 `0xf7c4`。更早的独立 harness 在 `CANARY_ADDR = 0x6340` 配 `DMA_TARGET = 0x0800` 处用 `0xFACEB13D`。`0x5b40 + 0x0800 = 0x6340`、所以它是同一个槽带一个不同的字面量。读出货代码时不要假设 `0xFACEB13D`。

出货驱动内栈和独立免驱动链共享**同一条尾配方**：在载荷偏移量 `0xf78c` 到 `0xf7f8`、补丁 0001 写非零 gadget 序列 `0x815a, 0x8e18, 0x815a, 0x1fbd, 0xffbc, 0x582d, 0xcbd, 0x3, 0x1fbd, 0xccb, 0x7f2f`、并设载荷字 `0x1100 = 0x00000007`。

### `common/constants.yaml`

仓库里的机器可读地面真、与补丁 0001 里的 C 精确匹配：

```yaml
driver_versions: [610.43.03, 610.43.02]
gpu: { vendor_id: 10de, device_ids: [20c2, 2082] }
compute: { ss0: "0x88888888", ss1: "0x00000008" }
profiles:
  8gb:  { stock_mib: 8192,  unlocked_mib: 65536, cfg1: "0x02779000", lmr: "0x0000020B", fb_bytes: "0x0000001000000000" }
  10gb: { stock_mib: 10240, unlocked_mib: 40960, cfg1: "0x02669000", lmr: "0x0000028A", fb_bytes: "0x0000000A00000000" }
```

### `remove.sh`

卸载器是 `remove.sh`，它需要 `--yes` 或 `-y`。**树里任何地方都没有 `uninstall.sh`**，不管 `docs` 分支怎么说。五步：停并禁用一个遗留 `cmpunlocker` systemd 单元并 `pkill -f /opt/cmpunlocker/daemon/watchdog.py`；`rm -rf /lib/modules/*/updates/cmpunlocker` 并逐内核 `depmod -a`；重建 initramfs；删除 `/lib/firmware/nvidia/*/gsp_tu10x.bin.cmpunlocker.{bak,patched,tmp,cleanup,pat}`；移除 `/opt/cmpunlocker`；然后停显示管理器和 `nvidia-persistenced`、强制卸载那四个模块并再次 `modprobe nvidia`。一位 HiveOS 上的测试者报告跑它后两张卡回到挖矿，那是"mod 非破坏性"这一声称的依据（单一报告，中等置信度）。

见[安装](../procedures/install.md)、[验证](../procedures/verify.md) 和[卸载](../procedures/uninstall.md) 看操作流程。

---

## 第 3 代：免驱动 SEC2 refire 链

> [!WARNING]
> **实验性**
>
> 这是一条平行路径、不是 `cmpunlocker` 的一部分、也不是任何人该为生产使用解锁一张卡跑的东西。它要紧、因为它是仍追求"不改驱动就解锁"这个创始目标的唯一一条工作线。

`refire_chain_v6.py`（27,769 字节，2026-07-24 发布）从用户态执行整个解锁，**没有 NVIDIA 驱动加载**，只用 stdlib（`os`、`sys`、`mmap`、`ctypes`、`struct`、`time`、`subprocess`）。它把 BAR0 映射为 16 MiB、把 SEC2 当作基址 `0x00840000`、复位 Falcon、把 NS 代码非安全地加载到 IMEM 0、用标签寄存器把 HS 代码安全地加载到 `IMEM[ns]`、加载 DMEM、把 MAILBOX0/1 设为 WprMeta 物理地址、启动 CPU，然后反复溢出签名 Booter 的签名读 DMA。

操作流程：

```bash
echo 16 | sudo tee /proc/sys/vm/nr_hugepages
sudo rmmod nvidia_uvm nvidia
BDF=$(python3 -c 'import refire_chain_v6 as V; print(V.resolve_bdf())')
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sudo python3 refire_chain_v6.py --all
```

模式：`--compute`（只关 SM 和张量节流、常开、FLR-粘性）、`--memory 40`（真实稳定的档位）、`--memory 80`（80 GB 档位）、`--pcie-gen2`（只 LnkCap2 cap）、`--pcie-retrain`。环境覆盖：`CMP_BDF`、`CMP_BOOTER_IMG`、`CMP_BOOTER_SIG`。`--all` 把卡留成一次无-FLR 驱动加载的 READY。每个模式都需要 GPU 解绑和巨页设置、除了 `--pcie-retrain`、它是纯主机写。

前置条件严格：root；GPU **解绑**任何 NVIDIA 驱动；一个签名的 GA100 `booter_load` HS ucode 映像（约 60,160 字节，384 字节 RSA-3072-PSS 签名烘焙在 `0x8900`）；16 个巨页；内核命令行 `intel_iommu=off` 或 `iommu=pt`，好让 DMA 物理地址是宿主物理的。它分配一个物理连续的 2 MiB 巨页、`mlock` 它、经 `/proc/self/pagemap` 解析物理地址（位 63 必须置位，否则 `page not present (need hugepages)`），并调用一个手工组装的 clflush 加 mfence 桩（`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`），因为"sig-DMA is NONCOHERENT, must hit RAM not CPU cache"（sig-DMA 是非连贯的，必须命中 RAM 而非 CPU 缓存）。

值得知道的内部细节：`stage_radix3()` 必须运行，否则 Booter 的签名前 DMA 会以原因 `0x9` 失败。它分配 `0x6000` 字节并写一个三级链（`[0x0000] = phys+0x1000`、`[0x1000] = phys+0x2000`、`[0x2000] = phys+0x3000`），然后刷新。WprMeta 模板是一个从真实 10 GB 引导捕获的 256 字节结构，只有签名指针（`0x48`）、签名大小（`0x50` = `0xF800`）、radix3 指针（`0x10`）、radix3 大小（`0x18`）、bootloader 指针（`0x20`）和 bootloader 大小（`0x28`）被覆盖。它前两个词是 WPR 描述符魔数 `0x371a60b3` 和 `0xdc3aae21`。

### 版本谱系

| 版本 | 改动 |
|---|---|
| v1（`refire_chain.py`） | 硬编码一个紧凑的双写载荷、每 PLM 一次 |
| v2 | 载荷变成一个通用写引擎、接受一个扁平 `[(addr, value), ...]` 列表、零 WprMeta 或几何布局知识。WprMeta 在投递层只作为签名-DMA 溢出触发器被建一次。投递原语 `Bar0, alloc, flush, reset_sec2, load_booter, wpr_meta, start_wait, stage_radix3, geometry, fire, PATCHLOC` 从硬件验证过的 v1 逐字复用。载荷大小 `0xF800`、入口尾常量 `TAIL0 = 0x815a` |
| v6 | 加模式标志、BDF 解析和上面的环境覆盖 |

> [!CAUTION]
> **可移植性限制：只 10 GB 卡**
>
> 发布的链携带一个从 **10 GB** 引导捕获的 WprMeta 模板。它不能被未修改地应用到一个 `0x20C2` 8 GB 卡。产出一个 8 GB 模板是一个记录在案的任务：在一次正常驱动 GSP 引导期间从一张 8 GB 卡捕获 `pWprMeta` 并替换它。反正只有六个字段被覆盖、所以风险低、但没人做过它。

---

## 第 4 代：未合并分支

十二个未发布分支快照被捕获（**算上出货 `master` 是十三棵树**）：`80`、`Gen2`、`PG199`、`clanker/driver-port`、`debug-gen2`、`deced`、`docs`、`ecc`、`far`、`housekeeping`、`memory`、`multiple-cards`。远程上存在十六个未发布分支 ref；`code-simplification`、`dual-geometry-fix`、`fix` 和 `v0.1` 没被快照、本维基任何地方也没被分析。见[方法论](../appendix/methodology.md)。

| 分支 | Tip | 它加什么 | 裁决 |
|---|---|---|---|
| `memory` | 2026-07-18 | 原始驱动内显存解锁、单一烘焙几何布局 | 合并进 `master` |
| `housekeeping` | 2026-07-18 | `43c762d "Add 2082 (10GB) device support to all patches"`；也移除 `.ai/CONTEXT.md` 代理指令文件 | 修复后合并 |
| `ecc` | `bb4d669`、2026-07-18 | 单一提交、"Fixed dual geometry support"。**不含 ECC 代码** | 合并。ECC 熔断关闭、无已知杠杆 |
| `multiple-cards` | `b1cb6d8`、2026-07-18（07-19 宣布） | 用 `profile_from_devid()`（`20c2` 到 `8gb`、`2082` 到 `10gb`、否则不支持）取代 `detect_card_profile()`、走**每**行匹配的 `lspci`、构建五个平行数组、加一个设 `SKIP_GEOMETRY_REWRITE=1` 的第三个 `mixed` 档位。导出 `CMPUNLOCKER_GPU_INVENTORY`、持久化为 `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`、每 GPU 一行、形式 `0000:0b:00.0 20c2 8gb 65536`。加 `verify.sh` | 未合并。见[多 GPU](../procedures/multi-gpu.md) |
| `80` | `3c53aca`、2026-07-19 | 把补丁 0001 的 10 GB 臂重写到 `cfg1Value = 0x02779000U`（**8 GB** 卡的 CFG1）配 `lmrValue = 0x0000028AU` 和 `targetFbBytes = 0x0000001400000000ULL` | **不要用。** 不稳定 |
| `clanker/driver-port` | `153cd6d`、2026-07-21 | 按分支补丁目录 `driver/patches/{580,590,595,610}/`、由 `BRANCH="${VERSION%%.*}"` 选择。在 `driver/VERSION` 里列十二个版本、在 `constants.yaml` 里列五个、一个被承认的内部不一致。它的 `install.sh` 与 master 的**逐字节相同** | 未合并、610 以下从未启动测试 |
| `debug-gen2` | `746d9f7 "PCIe Gen 2 works!"`、2026-07-23 | 补丁 0001-0007、加作为 systemd oneshot 安装的 `tools/retrain.sh` 和 `tools/cmpretrain.service` | 被 `Gen2` 取代 |
| `Gen2` | `2f27474`、2026-07-24；tip `a4de322`、2026-07-26 | `2f27474 "Gen2 + multiple-card support"` 加 `0008-pcie-gen2-probe-retrain.patch`、多卡支持和 `verify.sh`、并**删除** `tools/cmpretrain.service`（`tools/retrain.sh` 留下）。tip `a4de322` 是一次纯 `master` 合并、只碰 `.github/pull_request_template.md` | 当前 Gen2 基 |
| `far` | `8854d3e "Remove clamp link to Gen1"`、2026-07-26 | 相对 `Gen2` 恰好一行改动：`RMPcieLinkSpeed` `0x1` 到 `0x2` | |
| `deced` | `2326599`、2026-07-27 | 用 `find_gpu_bdf()` 替换 `tools/retrain.sh` 里硬编码的 BDF。**档案里最新的 Gen2 树** | |
| `docs` | `651b6d5`、2026-07-27 | 七个文档提交 | **不权威。** 见下 |
| `PG199` | | Drive A100 对比快照 | 仅参考 |

### 仅分支工具

`verify.sh` 是一个**仅分支**的多 GPU 安装后检查器，不存在于 `master` 上。它偏好已安装的 `gpu_inventory`，否则经 `lspci -nn | grep -iE '10de:20c2|10de:2082'` 枚举。`is_unlocked_memory` 接受 `8gb` 的 `>= 60000 MiB` 和 `10gb` 的 `35000..59999 MiB`；`is_stock_memory` 接受 `7680..8704` 和 `9728..10752`。每 GPU 状态是 `OK`、`STOCK`、`MISSING` 或 `UNEXPECTED`。一条缺失的 `SEC2_DEBUG` dmesg 轨迹只是警告而非失败，因为环形缓冲区会轮转。

> [!NOTE]
> **未解问题**
>
> **`verify.sh` 从不检查 PCIe Gen2、即使在 Gen2 分支谱系上也是。** grep `Gen2/verify.sh`、`far/verify.sh` 和 `deced/verify.sh` 找 "pcie" 返回零命中。Gen2 验证完全留给用户手工跑 `nvidia-smi`。修复小：查询 `nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max`、或复用 `pcielink.sh` 的 `CAP_EXP+12.w` LnkSta 解码。

### Gen2 谱系取代

**用户态重训练脚本变成驱动内探测时重训练。** `debug-gen2` 装 `/usr/local/sbin/retrain.sh` 和 `cmpretrain.service`（`Type=oneshot`、`ExecStartPre=/bin/sleep 15`、`WantedBy=multi-user.target`）。从 `Gen2` 起，`0008-pcie-gen2-probe-retrain.patch` 在 `kernel-open/nvidia/nv.c` 里加 `nv_cmp170hx_retrain_gen2()`，门控在 `gpu->device == 0x20c2 || gpu->device == 0x2082` 上，它在探测时走 `pci_upstream_bridge(gpu)` 并重训练。安装器主动禁用 `cmpretrain.service` 和 `cmp-gen2-retrain.service` 并 `rm -f` 辅助脚本，打印 `Removed legacy PCIe retrain helpers`。一个挂在 `multi-user.target` 之后的 15 秒 sleep oneshot 是脆弱的，而且不能在驱动声明设备前运行。

Gen2 谱系安装器也写 `/etc/modprobe.d/cmp-pcie-gen2.conf` 并配置 IOMMU、把 `intel_iommu=on iommu=pt` 或 `amd_iommu=on iommu=pt` 追加到内核命令行、除非传 `--no-iommu`。

> [!CAUTION]
> **`Gen2` 装了一个 Gen1 钳制**
>
> `debug-gen2` 和 `Gen2` 写 `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`、在尝试启用 Gen2 的同时把链路钉在 Gen1。`far` 和 `deced` 写 `0x2`。哪个值是对的**真的未解决**：两种拼写都发货、在各自作者都相信自己对的分支上、而且不存在 A/B 引导测试。一张卡上的一次三方引导对比能定论它。

> [!CAUTION]
> **不要跟随 `docs` 分支**
>
> `docs/INSTALLATION.md` 第 40 行说 `sudo ./uninstall.sh --yes`（没有这样的文件）；`docs/ARCHITECTURE.md` 第 81-82 行声称 `SEC2_DEBUG: SS0 = 0xffffffff` / `SS1 = 0xffffffff` 而出货代码写 `0x88888888` 和 `0x00000008`；`docs/DEBUGGING.md` 第 15 行说 "All the PLMs must show `0xffffffff`" 而 `0x001fa7cc` 处的 WPR_CFG 被打开到 `0xfffff0ff`。那个分支还杜撰代码里任何地方都不存在的缩写展开。

---

## 社区 fork 和相邻工具

发布后几天内至少六个公开仓库 fork 或重新实现了解锁。

| 仓库 | 性质 |
|---|---|
| `amoghmunikote/cmpunlocker` | 上面描述的参考实现 |
| 几个个人 fork、一个带 `combined-multiple-cards-gen2` 分支 | Fork；一个把 Gen2 工作与多卡支持结合。按本维基的匿名化政策省略拥有者名字 |
| `abobasixseven/unlock-cmp-170hx` | **不是一份写稿。** 一个 AI 代理执行提示：只有 `README.md` 和 `cmp90_compute_unlock_prompt.md`、都以 `EXECUTE STEP BY STEP: 5 (preparation) -> 6 (installation) -> 6.5 (cold reboot) -> 7 (verification)` 这类行结尾、通篇硬编码一个具体家目录。它的寄存器表匹配出货补丁、但它的散文和 PCIe Gen2 章是次要总结、不是一手测量 |
| `theneocorp/cmppatcher` | 一种真正不同的方法：直接补丁 NVIDIA 驱动**二进制**、这样补丁跨驱动更新持久。报告 3D 加速和 FP32 FMA 绕过 |

相邻、非解锁工具：

| 工具 | 用途 |
|---|---|
| `CMPGPU-patch-script`（`optimize-cmp-cuda.py`） | 交互式 llama.cpp 源码补丁器、带五个独立优化组、每个默认 `n`：`fp32_fma_flag`（把 `-fmad=false` 加到 CUDA_FLAGS）、`fp32_fma_split`（把 `fmaf(...)` 重写成 `__fadd_rn(__fmul_rn(...), ...)`）、`math_intrinsics`、`dp2a`、`fp16_bf16_cuda_core`。七个文件里十一个 PatchSpec 条目；`.cmp-bak` 备份；`--dry-run`、`--no-backup`、`--restore`。它的 README 警告性能在非 170HX CC 8.x 设备上可能**下降** |
| `170tune`（`/usr/local/bin/170hx-oc`） | 调优和资格 harness、它测量、门控并恢复时钟和电压设置、把"一次完成的基准测试当无证据"。运一个 26,987 字节的调优指南。它的设置是否跨重启持久是一个开放问题。见[调优](../operations/tuning.md) |
| `cmp170hx-gen2-setup.sh`（12,389 B、2026-07-26） | 独立 Gen2 设置工件、不同于 `Gen2` 分支的驱动内方法、带一份 `PCIE_GEN1_LOCK.md` 分析发布 |
| `unlock_host_610.sh` | nvidia-open 610.43.03 的主机侧脚本：从 `vfio-pci` 解绑、清 `driver_override`、杀 `nvidia-persistenced`、卸载那四个模块、`modprobe ecdh_generic ecc ecdsa_generic`（模块有密码依赖）、`insmod kernel-open/nvidia.ko`、断言 `/sys/module/nvidia/version == 610.43.03`、`insmod nvidia-uvm.ko`、把 BDF 回显进 `/sys/bus/pci/drivers/nvidia/bind`、然后 `mknod` 设备节点。绑定触发 `RmInit`、因此触发驱动内解锁 |

### FMA 变通方案家族

FP32 FMA 封锁在编译时被绕过、不由任何解锁：OpenCL 经 `#pragma OPENCL FP_CONTRACT OFF` 加 `fma()` 和 `mad()` 的宏遮蔽、CUDA 经 `nvcc -fmad=false`、SYCL 经 clang `-ffp-contract=off`。显式调用和 `a * b + c` 的隐式收缩都必须被抑制、而数值后果是两次舍入而非一次。

---

## Booter 提取工具链

只在你自己处理利用本身时需要、不是解锁一张卡。

可读 Booter 反汇编的文档化配方：

```text
用 Nouveau 提取工具从 NVIDIA .ko 提取调试二进制
  -> 用 rijndael-tool 和 NVIDIA 的公开测试密钥解密
  -> 检查它没被压缩（NVIDIA 用一个叫 binHex 的压缩器）
  -> 用 envytools（envydis、目标 fuc5）反汇编
  -> 加注释
```

`nouveau/extract-firmware-nouveau.py` 必须为 GA100 打补丁，因为生成的 C 数组名改成了 `kgspBinArchiveBooter{LOAD}Ucode_{GPU}_BINDATA_LABEL_IMAGE_{fuse.upper()}_data` 形式。出厂商脚本经一个 `--debug-fused` 键选择 prod 或 debug ucode，默认 prod，而且它需要匹配**封闭源码**驱动包里的固件 `.bin` 文件，其版本列在 `version.mk` 里，*不是*开源分支版本号。

在开源驱动里，签名的 HS ucode 活在 `src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`，带三个档案条目：`..._IMAGE_PROD`（用 NVIDIA 自己的 bindata 压缩器压缩，不是普通 zlib）、`..._SIG_PROD`（未压缩，一个 384 字节数组）和 `..._PATCH_LOC`（4 字节 = `0x8900`）。映像约 60,160 字节。

一个替代提取从已加载的出厂商驱动经 SEC2 Falcon 窗口在基址 `0x840000` 活转储 booter：写 `IMEMC (0x840180) = off | (1 << 25)` 用于自动递增读，并循环读 `IMEMD (0x840184)` 对 `off = 0 ... 0x8700`；DMEM 同理经 `DMEMC (0x8401c0)` / `DMEMD (0x8401c4)`。置信度 **中等**：流程具体、寄存器地址看起来对，但从未贴出过捕获转储，而读必须在驱动 PIO-加载 booter 后立即进行，在它复用 SEC2 之前。

生产 booter 无法被修改甚至读取：它用一把强密钥加密。利用因此经栈改变**执行流**，而非代码，无需重新签名。

> [!NOTE]
> **未解问题**
>
> `envydis` 带 `fuc5` 目标成功反汇编 GA100 booter、尽管 envytools 表名义上把 `fuc6` 分配给 GP102 及以后的部件。envytools 已约 8 年没更新；`envyhooks` 被建议作继任者、却缺乏等效功能；`faucon` 只目标 fuc5。170HX SEC2 正式是 fuc5 还是 fuc6 未定论。下一步：diff 同一个映像的 fuc5 和 fuc6 解码、找只有一方目标连贯解码的指令。

---

## 已废弃路径、一览

不要跟任何这些。

| 死路径 | 为什么 | 用代替 |
|---|---|---|
| 在磁盘上补丁 `gsp_tu10x.bin`（`patch_gsp.py`、`payload-lnject.py`、`scan_dmem.py`） | 被驱动内签名 memdesc 取代；在磁盘上留下一个打过补丁的 blob | `cmpunlocker` 补丁 `0001` |
| systemd 持久化（`cmp170hx-unlock.service`、`watchdog.py`） | 在进程打开对重新应用之间赛跑；无法挺过一次驱动重载 | `/lib/modules/.../updates/cmpunlocker/` 里打过补丁的模块 |
| `deploy.py --path vbios-memory` | 从没工作；那时一份修改的 VBIOS 产生一个不工作的设备 | 寄存器级解锁 |
| `stack_gen.py` v1 | 把所有金丝雀槽清零；`0x7dd9` 处的 `__stack_chk_fail` 触发 | 任何更晚的载荷构建器 |
| 手动五步 TTY 流程 | 2026-07-18 被取代 | `sudo ./install.sh` |
| `--profile` 作几何布局选择器 | 在 `master` 上被降级成元数据标签 | 几何布局在 GSP 引导时按 PCI ID 选择 |
| `sudo ./uninstall.sh --yes` | 没有这样的文件 | `sudo ./remove.sh --yes` |
| `Gen2`/`far`/`deced` 上的 `tools/retrain.sh` | 死代码；安装器删除它、补丁 0008 在内核里重训练 | 补丁 `0008` |
| `80` 分支 | 约 40 GB 之上不稳定 | 10 GB 卡上 40 GB |
| `docs` 分支 | 记录在案的事实错误 | 本维基、和源码 |
| 除 `check_fold.py` 外任何折叠 harness | 一个更早 harness 把原生内存报告为折叠 | `check_fold.py` |
| 把 `gsp_tu10x.bin` 当它是 booter 来解密 | 它是 GSP RISC-V ELF 载荷、不是 SEC2 Falcon booter。Ghidra 从它发约 100 MB 的 C、objdump 约 1.5 GB 的汇编 | 反汇编 `booter_load_ga100_*.bin`、约 25 kB、约 390 kB 汇编 |

---

## 参见

- [项目时间线](timeline.md)、上面每次取代背后的日期
- [净室与来源溯源问题](clean-room-and-provenance.md)
- [死路](dead-ends.md)
- [六个驱动补丁](../unlock/driver-patches.md) 和[ROP 链](../unlock/rop-chain.md)
- [安装](../procedures/install.md)、[验证](../procedures/verify.md)、[排障](../procedures/troubleshooting.md)
- [寄存器参考](../unlock/register-reference.md) 和[寄存器索引](../appendix/register-index.md)
