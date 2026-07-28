# The GA100 die in the CMP 170HX

**What this page covers.** The physical silicon: process, transistor count, die size and package;
the GPC / TPC / SM hierarchy and how many SMs a 170HX actually has versus an A100; the
floorsweeping fuses that decide that number and how they vary from die to die; the memory
partition and cache hierarchy; compute capability and the instruction set that follows from it;
and which fixed-function engines are present, fused off, or physically absent.

The headline: **the CMP 170HX carries the same GA100 die as the NVIDIA A100**, TSMC 7 nm, 54,200
million transistors, 826 mm². It is a harvested bin of that die, marked `GA100-105F-A1` on the
8 GB card and `GA100-105A-A1` on the 10 GB card, with **5 of 8 GPCs active: 35 TPC, 70 SM,
4480 FP32 lanes, compute capability 8.0**. Both SKUs enumerate exactly 70 SMs. Nothing about the
CMP restriction removes SMs, and nothing in the [compute unlock](../unlock/compute-throttle.md)
adds any back: the mining-specific restriction is an issue-rate divider held in separate fuses,
and the SM count you get is the ordinary silicon fuse floor for this bin.

Every 170HX reads `PMC_BOOT_0` (`0x00000000`) = `0x170000a1`, which is the GA100 chip-ID
signature. A GA10x consumer control reads `0xb74000a1` at the same offset, so this one dword is a
sufficient "is this really a GA100" test.

---

## Die and package

| Property | Value | Notes |
|---|---|---|
| Architecture | Ampere GA100 | same die as A100, not a CMP-specific tape-out |
| Process | TSMC 7 nm (N7) | |
| Transistors | 54,200 million | 65.6 M/mm² density |
| Die area | 826 mm² | at or near the 7 nm reticle limit (~830 mm²) |
| Package | BGA-2743, roughly 55 × 55 mm | heatsink bolt pattern 57 × 68 mm centre-to-centre |
| ASIC marking, 8 GB | `GA100-105F-A1` | GPU part number `20C2-105-A1` |
| ASIC marking, 10 GB | `GA100-105A-A1` | GPU part number `2082-105-A1` |
| Retail A100 comparison marking | `GA100-883AA-A1` | photographed alongside a 170HX die |
| `PMC_BOOT_0` `0x00000000` | `0x170000a1` | on every valid GA100 |
| PCI device ID | `10de:20c2` (8 GB) / `10de:2082` (10 GB) | see [board and variants](board-and-variants.md) |
| Compute capability | 8.0 (`sm_80`) | OpenCL 3.0, CUDA 11+ |
| Base / boost SM clock | 1140 MHz / 1410 MHz | 1470 MHz observed at `nvidia-smi -pl 300` |
| TDP / maximum software power limit | 250 W / 250 W on stock VBIOS | `nvidia-smi -q` reports Min 100 W, Max 250 W; 300 W only on cards carrying the NVIDIA OC mining VBIOS. Slot power limit in DevCap is 75 W |

The PCB is the A100 40 GB PCIe reference design with parts deliberately deleted, so board-level
absences (VRM phases, NVLink interface ICs, PCIe AC-coupling capacitors) are a separate topic from
die-level absences. See [physical mods](../operations/physical-mods.md) and
[power delivery](power-delivery.md).

---

## GPC / TPC / SM hierarchy

GA100's scale registers describe the full die independently of what is fused on. They read the
same on a 170HX and on an A100-class reference part:

| Scale register | Address | Value | Meaning |
|---|---|---|---|
| `PTOP_SCAL_NUM_GPCS` | `0x00022430` | `0x8` | 8 GPCs on the full die |
| `PTOP_SCAL_NUM_TPC_GPC` | `0x00022434` | `0x8` | 8 TPCs per GPC → 64 TPC → 128 SM full die |
| `PTOP_SCAL_NUM_FBPS` | `0x00022438` | `0xc` | 12 FBPs |
| `PTOP_SCAL_NUM_FBPAS` | `0x0002243c` | `0x18` | 24 FBPAs (a GA102 RTX 3090 reads 6) |
| `PTOP_SCAL_NUM_LTCS` | `0x00022454` | `24` | 24 L2 cache slices |
| `PTOP_SCAL_FBPA_PER_FBP` | `0x00022458` | `2` | 2 FBPAs per FBP |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246c` | `12` | 12 NVLink units on the die |
| `PTOP_FS_STATUS` | `0x00022470` | `0x0000003f` | floorsweep status |

A full GA100 would therefore be 128 SM / 8192 FP32 lanes. No product ever shipped that
configuration: every A100 SKU ships 108 SM / 6912 shading units, and the CMP 170HX ships 70.

| Part | GPCs active | TPC | SM | FP32 lanes |
|---|---|---|---|---|
| Full GA100 die | 8 | 64 | 128 | 8192 |
| A100 SXM4 / PCIe (all SKUs) | 7 (`FUSE_GPC_DISABLE` = `0x08` / `0x08` / `0x80`, one bit set on each of the three probed SKUs) | 54 | 108 | 6912 |
| DRIVE A100 (`0x20bb`, PG199) | 6 (`FUSE_GPC_DISABLE` = `0x84`) | 48 | 96 | 6144 |
| **CMP 170HX, both SKUs** | **5** (`RING_ENUM_GPC` = 5) | **35** | **70** | **4480** |

The 170HX figure is measured, not inferred. A PTX special-register dumper on an unlocked card
reports `SMs=70 warpsize=32`, `nsmid=70 nwarpid=64`, with `smid` values spanning 0..69 with no
gaps. An 8-card mixed rig enumerated `cu: 70` on all eight devices while memory alternated between
9990 MiB and 7954 MiB, which is the cleanest single demonstration that SM count does not track
SKU. OpenCL-Benchmark on an unlocked card likewise reports 70 compute units at 1410 MHz
(4480 cores, 12.634 TFLOPs/s theoretical FP32).

Note that 35 TPC is an odd number: the five active GPCs do not all carry 8 TPCs, which is normal
for a harvested part.

!!! note "Superseded"
    Two widely repeated SM figures are wrong. `deviceQuery` prints
    `Total SPs: 8960 (70 MPs x 128 SPs/MP)` and `Compute throughput: 25267.20 GFlops`; that is the
    tool applying the compute-capability 8.6 figure of 128 FP32 lanes per SM instead of GA100's
    (cc 8.0) 64. The arithmetic settles it: 4480 × 2 × 1410 MHz = 12.63 TFLOPS exactly, and every
    measured unlocked FP32 result lands at 12.28 to 12.99 TFLOPS, not ~25. Separately, one
    published specification page claims "8 GB variant: 56 SMs". The register accounting on an
    8 GB card (`OPT_GPC_DISABLE` = `0x45`, `RING_ENUM_GPC` = 5, 35 active TPC) gives 70 SM, the
    same as the 10 GB card.

---

## Floorsweeping and per-die binning

Floorsweeping is the disabling of defective or surplus units by blowing OTP fuses at test time.
On the 170HX it works entirely through the fuse and STATUS path: **every CTRL_OPT override
register reads zero**, and the topology report's own summary line is
`held back by CTRL_OPT: 0 TPC = 0 SM`. That means the 70 SM figure already is the fuse floor for
these dies, and there is no software override layer sitting on top of it that could be relaxed.

| Register | Address | Role | 170HX reading |
|---|---|---|---|
| `OPT_GPC_DISABLE` | `0x00820350` | GPC disable mask (fuse) | per-die, 3 bits set |
| `STATUS_OPT_GPC` | `0x00820c1c` | effective GPC mask | always mirrors the fuse |
| `OPT_GPC_DEFECTIVE` | `0x008205c4` | which GPCs are genuinely bad | `0x00` on some cards |
| `RING_ENUM_GPC` | `0x00120078` | GPCs enumerated on the ring | `5` |
| `CTRL_OPT_GPC` | `0x0082081c` | software floorsweep override | `0x00000000` |
| `CTRL_OPT_FBIO` / `_FBPA` / `_FBP` | `0x00820814` / `0x00820818` / `0x00820938` | as above, memory side | `0x00000000` |
| `CTRL_OPT_PERLINK` / `_PCIE_LANE` / `_NVLINK` | `0x00820820` / `0x0082082c` / `0x008209b8` | as above | `0x00000000` |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | enables the CTRL_OPT layer at all | `0x00000000` |
| `gpcMask` | `0x00408970` | GR-side GPC mask | `0xdc`, re-asserts if written |
| `OPT_PCIE_DEVIDA` | `0x008204d8` | SKU identity fuse | `0x20c2` reported on an 8 GB card (see note below) |
| `OPT_SLT_REV` | `0x008204bc` | slot/test revision | per-die |

**The mask varies per individual card, not per SKU, and not with driver version.** Seven distinct
`OPT_GPC_DISABLE` values are on record across three separate surveys, four of them from four cards
read in a single afternoon, all with three GPCs disabled and all totalling 70 SM:

| `OPT_GPC_DISABLE` | GPCs disabled | Card |
|---|---|---|
| `0x85` | 0, 2, 7 | 10 GB |
| `0x45` | 0, 2, 6 | 8 GB |
| `0x13` | 0, 1, 4 | 8 GB |
| `0xa8` | 3, 5, 7 | 10 GB |
| `0xd0` | 4, 6, 7 | fuse-table card |
| `0x23` | 0, 1, 5 | fuse-table card |
| `0x15` | 0, 2, 4 | 10 GB |

Some of the disabled GPCs are marked **physically good**. On the 8 GB card used for the
high-security write experiments, `OPT_GPC_DEFECTIVE` read `0x00000000` while `OPT_GPC_DISABLE` had
three bits set, so all three disabled GPCs are healthy silicon fused off to hit a product spec. On
one 10 GB card `OPT_GPC_DEFECTIVE` = `0x81` (GPCs 0 and 7 genuinely defective) while GPC 2 was
disabled but not defective.

### The restriction / binning split

A full 120-register diff of two physical 170HX cards found **107 registers identical and 13
different, and every one of the 13 is a binning value**. This is the single most actionable
tooling result on the die:

- **Product-line constants, identical on every 170HX, safe to hard-code in a recipe:** the nine
  speed-select fuses (`FUSE_SS_DP` = `0x1`, the other eight = `0x5`),
  `FUSE_PCIE_GEN23_DIS` = `0x1`, `FUSE_PCIE_GEN3_DIS` = `0x1`, `FUSE_NVLINK_DIS` = `0x7`,
  `FBPA_CFG1_BROADCAST` = `0x02449000`, `FUSE_PCIE_DEVIDB` = `0x20c2`, `FUSE_ECC_EN` = `0x0`,
  `FUSE_EN_SW_OVERRIDE` = `0x0`. (Both cards in the 120-register diff were 10 GB units, so any
  register that varies by SKU rather than by die looks like a constant in that diff. Two do:
  `FUSE_SKU_ID` (`0x00821060`) reads `0x68` on a 10 GB card and `0x80` on an 8 GB card, and
  `FUSE_PCIE_DEVIDA` (`0x008204d8`) reads `0x2082` on a 10 GB card and `0x20c2` on an 8 GB card,
  while `FUSE_PCIE_DEVIDB` is `0x20c2` on both. Neither DEVIDA nor SKU_ID is safe to hard-code,
  and `lspci -nn` remains the simplest SKU test.)
- **Per-die values that must never be hard-coded:** all floorsweep masks and their STATUS mirrors,
  `FEAT_OVR_SM_SPD` (`0x0082381c`), `FEAT_OVR_SM_SPD_1` (`0x00823820`), `FEAT_OVR_QUADRO`
  (`0x00823808`), `I1500_DATA`, `I1500_SHADOW_WDR`, and every per-FBPA readback.

That split is why the [compute unlock](../unlock/compute-throttle.md) can ship two fixed magic
constants and still be correct on every card, and why any tool that compares your card against
"the" stock SS0 value is comparing against noise.

### Surveying your own card

The read-only survey tool `ga100_topology_report.py` (v1 4848 bytes; v2 8128 bytes, adding an
InfoROM dump) reads `PMC_BOOT_0`, `OPT_GPC_DISABLE`, `STATUS_OPT_GPC`, `OPT_GPC_DEFECTIVE`,
`RING_ENUM_GPC`, `PTOP_SCAL_NUM_GPCS`, `PBUS_SW_SCRATCH(1)` (`0x00001404`), `0x00118f78`,
`OPT_PCIE_DEVIDA`, `OPT_SLT_REV`, and the per-GPC OPT_DISABLE / RECONFIG / CTRL_OPT / STATUS /
RECONF_OVR set. At least four independent people have run it on both SKUs with self-agreeing
output.

!!! question "Open problem: the 38 missing SMs"
    Going from 70 SM to the A100's 108, or the die's 128, would be the single largest gain
    available on this card, and on cards where `OPT_GPC_DEFECTIVE` = 0 the disabled GPCs are known
    good silicon. Every write path found so far is latched. `FUSE_CTRL_OPT_TPC_GPC` is
    remove-only (an OR-test on an active TPC did not even drop the count); high-security writes to
    `OPT_GPC_DISABLE`, `STATUS_OPT_GPC`, `OPT_TPC_GPC2` (`0x00820768`) and `DIS_SW_OVR`
    (`0x00820084`) all read back unchanged, in an experiment that carried two positive controls
    proving the write primitive was live; and forcing `gpcMask` three separate ways (RM struct,
    host MMIO write to `0x00408970`, patching the GSP firmware's `andi` to `li a4,255`) made the
    software stack report 8 GPC / 112 SM while `0x00408970` read back `0xdc` every time and
    `cuInit` segfaulted. Untried candidates: a GSP-RPC path via the static floorsweeping-mask
    queries (classes `0x2080122a` / `0x2080122b`), a GR-shadow write, or porting the write
    primitive to PMU / GSP / FECS / GPCCS. See [dead ends](../history/dead-ends.md).

!!! warning "Experimental"
    One card in the wild was reported CTRL_OPT-swept to **56 SM** rather than the fuse floor of 70,
    and 6 SM were clawed back to reach 62, with the remaining TPCs genuinely failing when enabled.
    This is described as the first compute-swept card seen, and no before/after register dump was
    published. Every other surveyed card is already at its fuse floor, where CTRL_OPT costs
    nothing. Treat a below-70 SM count as rare, not normal.

---

## Memory partitions and the cache hierarchy

The framebuffer side is floorswept independently of the graphics side. GA100 has 12 FBPs, each
with 2 FBPAs, so 24 FBPAs at 256 bits each. Each 1024-bit HBM interface is really four 256-bit
channels, which is why partial-stack enablement is a real hardware state and FBPA masks show
partial rather than clean whole-stack failures.

| Quantity | 8 GB SKU (`0x20c2`) | 10 GB SKU (`0x2082`) |
|---|---|---|
| Active FBPAs | 16 (of 24) | 20 (of 24) |
| Active FBPs | 8 (of 12) | 10 (of 12) |
| Memory bus width | 4096-bit | 5120-bit |
| Stock capacity | 8192 MiB | 10240 MiB |
| Unlocked capacity | 65536 MiB | 40960 MiB |

The floorsweep masks again vary per die. Two 10 GB cards read `FUSE_FBPA_DISABLE` (`0x00820368`),
`FUSE_FBIO_DISABLE` (`0x0082036c`), `STATUS_FBPA` (`0x00820c18`) and `STATUS_OPT_FBIO`
(`0x00820c14`) all at `0x0003c000` on one unit (FBPAs 14 to 17 off) and `0x000000c3` on the other
(FBPAs 0, 1, 6, 7 off), both leaving 20 active. Disabled FBPAs return a `0xbadf20xx` sentinel from
their CSTATUS registers rather than a value, and the sentinel tracks which FBPAs are off:
`0xbadf2010` and `0xbadf2013` on the card with FBPAs 0, 1, 6, 7 disabled, `0xbadf2017` and
`0xbadf2018` on the card with FBPAs 14 to 17 disabled. A dump from an 8 GB card enumerated its 12 FBP
half-stack regions individually: FBP 1 and 4 disabled, FBP 6 and 11 defective, the other eight
active, giving 8 × 8 GB = 64 GB, which is exactly the capacity the unlock reaches. Full detail is
on [memory subsystem](memory-subsystem.md) and [memory geometry](../unlock/memory-geometry.md).

| Cache level | Size | Basis |
|---|---|---|
| L1 / shared, per SM | 192 KB | GA100 architectural figure |
| L2 | 32 MB (`32768 KB`) | CUDA `deviceQuery` plus an independent latency-spike microbenchmark |
| L2, full A100 | 40 MB | for comparison |
| OpenCL global cache / local memory | 1960 KB / 48 KB | OpenCL-Benchmark on an unlocked card |

!!! note "Disputed"
    TechPowerUp lists the 170HX with 8 MB of L2. The runtime `deviceQuery` figure of 32768 KB and
    an independent pointer-chase latency measurement both say 32 MB, and this wiki uses 32 MB. No
    source in the corpus reconciles the two; a published latency/bandwidth curve showing where the
    working set falls off a cliff would close it. Note also that the correct TechPowerUp entry is
    `gpu-specs/cmp-170hx-8-gb.c3830`; the older `c3824` URL now redirects to an AMD card.

HBM bandwidth is **not** restricted on this part and is unchanged by the unlock (a same-card A/B
measured 1592 GB/s stock versus 1599 GB/s modded at a 256 MB working set, a ratio of 1.0x, in the
same table where FP32 moved 30.7x). Theoretical peak is 1555.2 GB/s (= 1448.4 GiB/s) from
1215 MHz DDR on 5120-bit. Measured figures span **1305.86 to 1600 GB/s** depending on tool and
access pattern, and no single canonical number exists; see [performance](../operations/performance.md).

---

## Compute capability and instruction set

Compute capability 8.0 (`sm_80`) fixes what the die can and cannot do, independently of any fuse:

- **64 FP32 lanes per SM**, 64 warps per SM, warp size 32. FP64 at the GA100 1:2 ratio,
  non-tensor FP16 at 4:1 versus FP32 (architecturally unusual, and the reason locked cards were
  already usable for LLM token generation).
- **280 third-generation Tensor Cores** (4 per SM), 280 TMUs, 128 ROPs. The tensor cores are
  present and functional, not fused off: unlocked cards measure 158.7 to 190 TFLOPS FP16 tensor
  and 164.4 to 192.7 TFLOPS BF16 tensor.
- **No FP8 and no NVFP4 hardware path.** Those need `sm_89`+ / `sm_120`. A tool enumerating
  supported MMA shapes on this card lists `mma_mxf8mxf8f32_16_8_32` and
  `mma_f8f8f16/f32_16_8_32` as unsupported, which is expected for Ampere. INT8, INT4 and INT1 are
  native in hardware, though INT1 shares the INT8 XNOR-popcount path with no dedicated unit.
- Practical consequence for inference: FP8 KV cache is unsupported on `sm_80`, so KV must be BF16.

---

## Engines present, fused off, and absent

| Engine / feature | Status on the 170HX | Evidence |
|---|---|---|
| CUDA cores, Tensor Cores | Present, functional, issue-rate throttled at stock | see [compute throttle](../unlock/compute-throttle.md) |
| FP64 units | Present, restored by the unlock | measured at the 1:2 ratio |
| **NVENC** | **Absent.** The GA100 die generally carries no video encoder | reported in-channel and consistent with the die's feature set |
| **NVDEC** | Die-level: five instances of 4th-generation NVDEC per the specification database. Driver-level: not exposed on this SKU. A probe of the NVDEC falcon mailbox `0x00830040` returned `0xbadf1100`, i.e. blocked or read-only | specification database, medium confidence; falcon probe |
| **Display engine / outputs** | **Absent.** No display outputs of any kind, `Slot Width: IGP`, no DirectX / Vulkan / OpenGL exposure | specification database and every `lspci` capture, which names the device a `3D controller` |
| **NVLink** | **Fused off.** `FUSE_NVLINK_DIS` / `STATUS_OPT_NVLINK` (`0x00820db8`) = `0x7`; the board is also missing its NVLink interface ICs. No NVLink register appears in the `0x00823800`-`0x0082382c` block and no branch contains NVLink code | fuse read plus teardown; see [NVLink hardware](nvlink-hardware.md) |
| **ECC** | **Fused off.** `FUSE_ECC_EN` = `0x0`, no telemetry, no known lever. The high ECC-status nibbles of `FEAT_READOUT_0` read zero, consistent with the fuse | see [ECC frontier](../frontier/ecc.md) |
| **P2P** | Absent. No P2P code in any shipping or branch tree; the sole MIG profile reports `P2P: No` | see [P2P frontier](../frontier/p2p.md) |
| **MIG** | Hardware supports it (enable bit 0 of `0x00820840`), but only one profile, `1g.64gb`, is exposed, so the GPU cannot actually be partitioned | community finding, not in shipping code |
| **Resizable BAR** | Present but limited to 64 MiB | `lspci` capability `[bb0]` |
| **FLR** | Present (`FLReset+` in DevCap), and load-bearing for every unlock harness | `lspci -vvv` |

!!! question "Open problem: is NVENC fused off or simply not built?"
    The in-channel statement is "nvenc is disabled ... idr if it's fused off or if it's fuse gated
    but it's not available by default if it has the hardware." Nobody has reported an NVENC
    session working and no unlock path has been proposed. The obvious next step is the same
    differential method that cracked the compute throttle: read the NVENC-related `OPT_*_DISABLE`
    fuses in the `0x00820xxx` block on a 170HX and on an A100 or DRIVE A100 control and diff them.
    Until that is done, assume the card has no hardware encoder.

---

## Why the die matters to the unlock

Three properties of this specific silicon are what make the whole project possible:

1. **The master kill fuse is unblown.** `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` (`0x008203f0`) reads
   `0x00000000`. Had it been blown, every feature override would be permanently locked and no
   software path would exist.
2. **The restriction fuses are a product-line constant, not per-die binning.** One recipe works on
   every card.
3. **The DRIVE A100 (`0x20bb`, PG199, `GA100-550F-A1`) is a clean negative control.** Two physical
   boards share the 170HX's NVLink kill and its `EN_SW_OVERRIDE` = 0 / `DIS_SW_OVR` = 1 state, yet
   read all nine speed-select fuses at `0x00000000`, `FEATURE_READOUT_1` = `0x00000000` and have
   full compute at 96 SM. That single-variable isolation is what proved the `OPT_SM_SPEED_SELECT`
   fuse block, and nothing else, is the compute restriction.

See [fuses and OTP](fuses-and-otp.md) for the full fuse map, and
[compute throttle](../unlock/compute-throttle.md) for how the override is reached.
