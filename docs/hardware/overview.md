# Hardware overview: complete specification

**What this page covers:** every established specification of the NVIDIA CMP 170HX, stock and
unlocked, for both SKUs, side by side. Where a figure is disputed, varies per unit, or has
never been measured, this page says so instead of choosing one quietly.

The headline: the CMP 170HX is a **GA100** part, the same die as the A100, carrying 70 SMs and
4480 CUDA cores at compute capability 8.0 on **both** SKUs. Its restrictions are four separate
mechanisms with four separate stories: an OTP-fused SM issue-rate throttle (defeated in
software), a strap-selected memory geometry (defeated in software), a PCIe **speed** cap
(defeated in software, on unreleased branches only) and a PCIe **width** cap that is a PCB
depopulation and can only be fixed with a soldering iron. NVLink and ECC are fused off with no
known lever. Whether NVLink is additionally depopulated at board level is unresolved.

> [!NOTE]
> **Corrections to the existing community wiki**
>
> Three errors circulate widely and are corrected here with evidence.
>
> 1. **SM count.** Both the 8 GB and the 10 GB SKU expose exactly **70 SMs / 4480 CUDA
>    cores**. This was verified by a tester holding both SKUs, by an eight-device
>    enumeration reporting `cu: 70` on all eight, and by four independent topology reports.
>    Any table giving a different SM count for the 10 GB card, or disagreeing with its own
>    notes, is wrong.
> 2. **"PCIe Gen 1 x4, firmware locked" is half right.** The *speed* cap is firmware and
>    fuse mediated and has been defeated in software. The *width* limit is not firmware at
>    all: 12 of the 16 lanes ship with their AC-coupling capacitors depopulated. The lane
>    fuses are clean (`OPT_PCIE_LANE_DISABLE` = `0x00000000`), and a stock unmodded card
>    running the Gen2 code reports `LnkCap: Speed 5GT/s, Width x16` while `LnkSta` still
>    reads `Width x4 (downgraded)`, which proves the limit is board-level. Note also that
>    Gen2 has never been reproduced under VM passthrough or over Thunderbolt.
> 3. **"Unlocked FP64 is 6.44 TFLOPS" versus "11.6 TFLOPS"** is a non-tensor versus tensor
>    confusion, not a contradiction. Both numbers are real. See
>    [Compute throughput](#compute-throughput-measured).

## Silicon

| Property | Value | Notes |
|---|---|---|
| GPU | GA100 | Same die as the A100 |
| ASIC marking | `GA100-105F-A1` | Cut-down GA100; GPU part number `20C2-105-A1` on 8 GB boards |
| `PMC_BOOT_0` (`0x000000`) | `0x170000a1` | Reads identically on every valid GA100. GA10x control reads `0xb74000a1` |
| Process | TSMC 7 nm | The die is described as sitting at the reticle limit for the node |
| Die size | **826 mm²** | Quoted as "roughly 830 mm²" in one teardown; same die |
| Transistors | 54.2 billion | NVIDIA's published GA100 figure. **No source in this project measures or independently verifies it** |
| Compute capability | 8.0 (`sm_80`) | Reported by every tool after unlock |
| GPCs (physical / active) | 8 / **5** | `PTOP_SCAL_NUM_GPCS` (`0x022430`) always reads `0x8` |
| TPCs / SMs | 35 / **70** | 2 SM per TPC; identical on both SKUs |
| CUDA cores | **4480** | 70 × 64 FP32 lanes per GA100 SM |
| Tensor cores | **280**, 3rd generation | Functional after unlock; measured at 158.7-190 TFLOPS FP16 tensor and 164.4-192.7 TFLOPS BF16 tensor |
| TMUs / ROPs | 280 / 128 | Specification database figure |
| Full GA100 for reference | 128 SM / 8192 CUDA cores | The A100 PCIe and SXM SKUs shipped 108 SM / 6912 cores; the Drive A100 (PG199) ships 96 SM |

### The SM harvest is per card, not per SKU

Every surveyed 170HX enumerates 5 GPCs / 35 TPC / 70 SM, and 70 is already the fuse floor:
`CTRL_OPT` costs a typical card nothing. Which GPCs are disabled varies per individual card
and does not vary with driver version. Four cards read in one afternoon:

| `OPT_GPC_DISABLE` (`0x820350`) | GPCs off | SKU |
|---|---|---|
| `0x85` | 0, 2, 7 | 10 GB |
| `0x45` | 0, 2, 6 | 8 GB |
| `0x13` | 0, 1, 4 | 8 GB |
| `0xa8` | 3, 5, 7 | 10 GB |

`STATUS_OPT_GPC` (`0x820c1c`) always mirrors it. Crucially, `OPT_GPC_DEFECTIVE` (`0x8205c4`)
reads `0x00000000` on several cards whose disable mask has three bits set, so those GPCs are
physically good silicon that was disabled to hit a product spec. There is something to win
there, but every write path found so far is latched: HS-privileged writes to `0x820350`,
`0x820c1c`, `0x820768` and `0x820084` all read back unchanged, and forcing `gpcMask`
(`0x408970`) three separate ways left it re-asserting to `0xdc` with `cuInit` segfaulting. One
rare card in the wild was `CTRL_OPT`-swept below the fuse floor to 56 SM and had 6 SM clawed
back. See [GA100 silicon](ga100-silicon.md) and [fuses and OTP](fuses-and-otp.md).

## Clocks

| Quantity | Value | Confidence / conditions |
|---|---|---|
| Base SM clock | 1140 MHz | Also the clock CPU-RM runs at, costing ~20% tensor throughput |
| Sustained SM clock (stock) | **1410 MHz** | Every sustained measurement in the corpus; 1425 MHz on the tuning reference card at +0 offset |
| Sustained SM clock at `-pl 300` | 1470 MHz | 8 GB card with the OC VBIOS |
| VBIOS table max graphics clock | 1695 MHz | VBIOS 92.00.6D.00.0A |
| Practical silicon ceiling | ~1604-1614 MHz | At +350 MHz offset, one reference card |
| `clocks.max.sm` as reported | 1935 MHz | **Low confidence, reported field only, not an achievable clock.** Single report, never re-checked. Do not treat it as an operating clock |
| Graphics clock steps | 100 steps, 1695 down to 210 MHz in 15 MHz decrements | `nvidia-smi -q` on 580.159.04 |
| Core clock floor | 210 MHz | Will not go lower |
| Memory clock, 10 GB SKU | **1215 MHz**, current = max | No headroom whatsoever; the memory-clock lock survives the unlock |
| Memory clock, 8 GB SKU | **Disputed: 1458, 1592 or 1728 MHz** | See below |
| Memory clock domain count | Exactly one | `Supported Clocks / Memory` lists a single entry; there is nothing to select |
| NVML GPC clock VF offset | `[-1000 .. +1000]` MHz on the **8 GB** card; `[0 .. 0]` on the 10 GB card | Works on 8 GB only: the shipped 8 GB VBIOS permits the range (`freqDelta` ±1000 at `0x47177`/`0x47179`, `0` on the 10 GB and A100 images). **Not** a valid unlock test on a 10 GB card |
| NVML MEM clock VF offset | `[0 .. 0]` | The driver refuses memory clock changes; `nvidia-smi -lmc` returns "not supported" |

> [!NOTE]
> **Open problem: the 8 GB card's real HBM clock**
>
> Three conventions are in circulation and none has been reconciled. The specification
> database and a 2023 `deviceQuery` say **1458 MHz** (reported as 729 MHz and doubled by
> convention), implying a 1492.99 GB/s ceiling. A 2026-07-27 direct measurement says
> **1728 MHz**, giving 3.456 Gbps/pin and a 1769 GB/s ceiling. A third account puts the
> 8 GB card at 398 MHz against 304 MHz on the A100, which times four gives **1592** and
> 1216 MHz. The measured 1679-1699 GB/s delivered read bandwidth rules out 1458 MHz for
> that run but does not choose between 1592 and 1728. What would settle it: a raw FBPA PLL
> register read with the divider chain published.

> [!CAUTION]
> **A run that completes is not evidence a clock offset is safe**
>
> On the tuning reference card at a 1400 MHz ceiling, +250 MHz passed three full-VRAM
> pattern sweeps with zero errors and +300 MHz passed four, but **+325 MHz silently
> corrupted memory without crashing**: three sweeps returned 6 errors, then 3, then 0. The
> safe window there is one 25 MHz step wide, and past it the failure mode is bad data rather
> than a crash. Gate every candidate setting on four full-VRAM sweeps, not two, and note
> that per-card silicon variance means a validated offset on one serial says nothing about
> another. Details and the full fault matrix are in [Tuning](../operations/tuning.md).

## Cache

| Level | Size | Notes |
|---|---|---|
| L2 | **32 MB** (`32768 KB`) | CUDA `deviceQuery`, `torch.cuda.get_device_properties().l2_cache_size` and an independent latency-spike microbenchmark all agree. TechPowerUp lists 8 MB; that figure is contradicted by three measurements. A full A100 has 40 MB |
| L1 / shared per SM | 192 KB | Specification database figure |

## Memory, per SKU, stock and unlocked

| Quantity | 8 GB SKU | 10 GB SKU |
|---|---|---|
| PCI ID | `10de:20c2` (`0x20C2`) | `10de:2082` (`0x2082`) |
| Memory type | HBM2e (SK Hynix) | HBM2 (Samsung). Vendor split inferred from clocks, stability and a GPU-Z read, not from package markings: see [board and variants](board-and-variants.md) |
| Stock reported capacity | 8192 MiB (CUDA reports 7961 MB) | 10240 MiB |
| **Unlocked capacity** | **65536 MiB (64 GB)** | **40960 MiB (40 GB)** |
| Active FBPAs / FBPs | 16 / 8 | 20 / 10 |
| Bus width | **4096-bit** | **5120-bit** |
| Stock CFG1 `0x009a0204` | `0x02449000` | `0x02449000` (identical on both SKUs) |
| Unlocked CFG1 | `0x02779000` | `0x02669000` |
| Stock LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| Unlocked LMR | `0x0000020B` | `0x0000028A` |
| `targetFbBytes` / `fb_length` | `0x0000001000000000` (64 GiB) | `0x0000000A00000000` (40 GiB) |
| Stock `CSTATUS_RAMAMOUNT` | `0x200` (512 MiB per FBPA) | `0x200` |
| Unlocked `CSTATUS_RAMAMOUNT` | `0x1000` (4096 MiB per FBPA) | `0x800` (2048 MiB per FBPA) |
| Floorswept FB units | 2 FBPs defective, 2 disabled (one card examined) | `OPT_FBPA_DISABLE` = `0xc3`; fbpa00/01/06/07 off |
| ECC | Fused off | Fused off |

The unlocked constants are not invented: `0x02779000` is literally the stock CFG1 word of an
A100 PCIe 80 GB, and `0x02669000` is the stock word of an A100 PCIe 40 GB and A100 SXM4 40 GB.
The unlock restores genuine A100 geometry. LMR encodes total framebuffer size as
`MiB = MAG[9:4] << SCALE[3:0]`, and per-FBPA capacity follows as `2^(SCALE+1)` MiB. Full
treatment in [memory geometry](../unlock/memory-geometry.md) and
[the memory subsystem](memory-subsystem.md).

> [!NOTE]
> **The memory geometry does not survive FLR or a power cycle; the compute unlock does**
>
> SS0, SS1 and `0x00823804` survive FLR; the CFG1/LMR geometry rewrite does not. This
> asymmetry is why compute shipped before memory, and it is why "no FLR" appears as a stated
> condition on the DtoD bandwidth rows below.

> [!WARNING]
> **The 80 GB configuration is not a third option**
>
> The experimental `80` branch is presented as working in its own README and is not. It
> programs CFG1 `0x02779000` with LMR `0x0000028A` and `fb_length` `0x0000001400000000`, a
> three-way disagreement between the three layers that is the best explanation for its fold at
> exactly 40 GiB (`constants.yaml`'s `0x0000028B` / `81920` is inert metadata that `build.sh`
> never reads). A clean-room script firing the coherent `LMR 0x0000028B` removes the fold, but
> it is unshipped and still loses the device after about one CUDA context. Cards report
> ~81920 MiB and a 77 GiB dense fill passes, but kernels touching
> more than roughly 40 GB cause fatal GPU loss, independent of power limit. Reported Xid codes
> include Xid 31 (described as harmless) and Xid 154 after CUDA memory tests; the dominant
> reported symptom is hangs. Xid 31 alone was suggested by a bystander and was not corroborated
> as *the* signature by the operator with the failing card. Only one CUDA context is available
> per fire. See
> [the 80 GB frontier page](../frontier/80gb.md).

## Memory bandwidth

| Quantity | Value | Basis |
|---|---|---|
| Theoretical peak, 10 GB SKU | 1555.2 GB/s = **1448.4 GiB/s** | 1215 MHz DDR × 5120-bit. These are the same number in different units, not two competing figures |
| Theoretical peak, 8 GB SKU | 1492.99 GB/s at 1458 MHz, or 1769 GB/s at 1728 MHz | Depends on which memory clock is correct (see above) |
| **Measured, unlocked** | **1305.86 - 1600 GB/s, a range** | No single canonical figure: the value depends on tool and access pattern. Do not quote a point estimate |
| Eight-card rental mean | ~1600 GB/s | Eight unlocked 64 GB cards, one methodology |
| HBM read, 8 GB unlocked | 1679.1 - 1699.3 GB/s | 24 GiB stream |
| DtoD, 10 GB at 40 GB | 1390 GB/s | Clean 610.43.03, no FLR |
| OpenCL coalesced read / write, 10 GB at 40 GB | 1305.86 / 1521.62 GB/s | Misaligned: 789.82 / 161.76 GB/s |
| Effect of the unlock on bandwidth | **None**: 1592 to 1599 GB/s | Same-card A/B control row, in the same table where FP32 moves 30.7x |
| mixbench "1769.47 GB/sec" | **Not a measurement** | Tool-computed theoretical peak: 864 MHz × 4 × 4096 bits / 8 = 1769.472 GB/s exactly |

## Compute throughput, measured

Locked and unlocked, at stock clocks. The unlock is a register write and changes no clock, so
every figure below is a stock-clock figure unless it says otherwise.

| Datatype / path | Locked | Unlocked | Gain |
|---|---|---|---|
| FP32 non-tensor (FFMA) | 0.30 - 0.41 TFLOPS | **12.2 - 12.8 TFLOPS** | 26x - 32x |
| FP32 theoretical | n/a | 12.63 TFLOPS (4480 × 2 × 1410 MHz) | Cards achieve ~99% of it |
| FP32 non-FMA (control) | 4.31 - 6.29 TFLOPS | unchanged | Never throttled |
| FP64 non-tensor | ~0.20 TF/s | **6.2 - 6.3 TFLOPS** | 1/2 of FP32, the full GA100 rate |
| FP64 tensor | n/a | **11.6 - 12.9 TFLOPS** | Roughly 2x the non-tensor rate |
| TF32 tensor | 2.96 - 3.21 TFLOPS | **79 - 94 TFLOPS** | 15x - 28x; widest spread of any datatype |
| FP16 tensor | 6.52 TF/s | **158.7 - 190 TFLOPS** | Higher figures use fp16 accumulate |
| BF16 tensor | 6.40 TF/s | **164.4 - 192.7 TFLOPS** | Ceiling is 2048 × 70 × 1410 MHz = 202.1 TFLOPS |
| FP16 scalar (non-tensor) | ~42 - 50 TFLOPS | unchanged | **Never throttled**, even on a locked card. GA100 runs 16-bit hfma at 4x its FP32 rate |
| INT32 | ~12.5 TIOPS | unchanged | ~62.5% of an A100's 20 TIOPS |
| INT8, tensor MMA microbenchmark | 1.60 TOPS | 335.0 - 335.6 TOPS | Direct `mma.s8s8s32` |
| INT8, library / serving path | 1.63 TOP/s | **44.1 TOPS, still gated** | ~3.7x *slower* than FP16, where an A100 is ~2x faster |
| INT4 tensor MMA | 11.55 TOP/s | 320.2 TOPS | |
| INT1 | 46.16 TOP/s | ~1039 TOP/s | Over one PetaOP/s |
| FP8 / FP6 / FP4 | n/a | **Not supported in hardware** | Expected for `sm_80`; the MMA sweep enumerates each as unsupported |

The practical consequence of the INT8 result is worth stating plainly: for inference, use
W4A16 (AWQ or GPTQ, INT4 weights with BF16 activations) and avoid W8A8 entirely; KV cache must
be BF16 because FP8 KV is unsupported on `sm_80`. See
[LLM inference](../operations/llm-inference.md) and
[performance](../operations/performance.md).

> [!NOTE]
> **The `deviceQuery` 8960-core and 25.27 TFLOPS figures are wrong**
>
> `deviceQuery` prints `Total SPs: 8960 (70 MPs x 128 SPs/MP)` and 25267.20 GFlops. The
> discrepancy is exactly 2x and is consistent with the tool applying the compute-capability
> 8.6 figure of 128 FP32 lanes per SM instead of GA100's 64. The arithmetic and every
> measured result favour 4480 cores and ~12.6 TFLOPS.

## PCIe

The two restrictions are independent and must never be conflated.

| Quantity | Stock, no unlock | With the unlocker | With the capacitor mod |
|---|---|---|---|
| Link speed | Gen1, 2.5 GT/s | **Gen2, 5 GT/s** | unchanged by the mod |
| Link width trained | x4 (of x16 wired) | x4 | **x16** (or x8 if the solder work is incomplete) |
| `LnkCap` | `0x00456101` | `0x00456102` | n/a |
| `LnkCap2` | `0x00000002` (2.5 GT/s only) | `0x00000006` (2.5 and 5.0) | n/a |
| `LnkCtl2` target | n/a | `0x0002` | n/a |
| `LnkSta` | `0x1041` | `0x1042` | n/a |
| `nvidia-smi` cur / max / width | `1, 1, 4` | `2, 2, 4` | width follows the solder |
| De-emphasis | −6 dB | −3.5 dB | n/a |

**Measured host bandwidth:**

| Configuration | Bandwidth | Confidence |
|---|---|---|
| Gen1 x4 (stock) | ~0.80 - 0.85 GB/s | high |
| Gen2 x4 | 1.68 - 1.71 GB/s | medium; one archived OpenCL-Benchmark screenshot, one unmodded card |
| Gen1 x16 (cap mod only) | 2.88 GB/s flat, error free | medium; nominal ~4 GB/s, the gap attributed to PCIe 1.1 signalling overhead |
| Gen2 x16 | 6.63 - 6.67 GB/s | **medium: one rig, one day (2026-07-26), one capture.** Stability at Gen2 x16 is unestablished |

**Why the width is x4:** 12 of the 16 lanes (lanes 4-15) ship with their AC-coupling
capacitors omitted, 2 per differential pair, so 24 parts in total, in the `C1100`-`C1350`
designator range. The specification is **0402, 220 nF (0.22 µF), X7R, 16 V or better**,
sourced from the NVIDIA A100 GA100-883 reference schematic P1001-B02 page 3 ("IO: PCIe
CONNECTOR"); the confirmed working part is Samsung `CL05B224KO5NNNC`. (The dielectric is
X7R. "XR7" is a common transposition.) Populating only 12 of the 24 yields x8, because PCIe
width negotiation falls back to the next legal width; an x8 result after a mod means
incomplete or bridged solder work, not a distinct hardware limit. The lane fuses are clean, so
nothing about the width is programmable. See [physical mods](../operations/physical-mods.md).

**Why the speed is Gen1:** two fuse shadows read blown on both 170HX SKUs and clear on
twelve other Ampere parts probed: `FUSE_PCIE_GEN23_DIS` (`0x0082057c`) = `0x00000001` and
`FUSE_PCIE_GEN3_DIS` (`0x00820580`) = `0x00000001`. `FUSE_PCIE_MAGIC_D` (`0x00820520`) reads
`0x16680000` with bit 25 (`GEN4_SPEED_DISABLED`) set, against `0x00200000` on a DRIVE GA100
reference part. Notably the Gen2 unlock works **despite** `OPT_GEN23` never being cleared:
every attempt to write it fails on silicon, and the lever turns out to be the
CYA_0 / LINK_CONFIG_0 / XP3G / PRIV_MISC_1 overrides instead. Gen3 and Gen4 remain unachieved:
Gen3 *advertisement* has been made to work, but `LnkSta` never left 2.5 GT/s. See
[the PCIe subsystem](pcie-subsystem.md), [Gen2](../unlock/pcie-gen2.md) and
[Gen3/Gen4](../frontier/pcie-gen3-gen4.md).

> [!WARNING]
> **Experimental: Gen2 is not in the shipping product**
>
> Shipping `master` contains patches `0001` through `0006` only, has no `pcie:` block in
> `constants.yaml`, and its "What Gets Unlocked" table has three rows with no PCIe entry.
> `0007-pcie-gen2.patch` exists on branches `debug-gen2`, `Gen2`, `far` and `deced`;
> `0008-pcie-gen2-probe-retrain.patch` on `Gen2`, `far` and `deced`. None has been merged.
> Gen2 is also not deterministic in the field, does not work under VM passthrough, and fails
> entirely over Thunderbolt 3 enclosures (Oculink works, because it is essentially a direct
> riser).

## NVLink, P2P and other absent features

| Feature | Status | Why |
|---|---|---|
| NVLink | **Fuse-disabled** | `FUSE_NVLINK_DIS` `0x00820684` = `0x00000007`, `STATUS_OPT_NVLINK` `0x00820DB8` = `0x00000007`, matching the Drive A100 parts. That alone closes the door. Whether the board-side NVLink components are populated is **unresolved**: direct evidence exists on both sides; see [NVLink hardware](nvlink-hardware.md). There is no NVLink register in the `0x00823800`-`0x0082382C` block and no NVLink code in any branch |
| Peer-to-peer (P2P) | Absent on this card | Never demonstrated; no fused-versus-driver-gated determination has been made |
| ECC | Fused off | `FBPA_ECC_CTRL` (`0x009a0470`) = 0 with `MASTER_EN` read-only; no telemetry; the branch named `ecc` contains no ECC code at all |
| NVENC | Unavailable | Whether fused off or fuse-gated is unknown; no NVENC session has been reported working |
| MIG | **Enables, but cannot partition** | Bit 0 of `0x00820840` turns it on and it is reported persistent, but only one profile (`1g.64gb`, 63.00 GiB, 70 SMs, P2P No) is exposed, so the GPU cannot actually be subdivided; `-cgi 9,3g.20gb -C` returns `Invalid Argument`. Not in the shipping tree |
| Resizable BAR | **Advertised but inert** | Capability present at `[bb0 v1]`; each BAR advertises exactly one supported size, and BAR1 stays at 64 MiB regardless of reported framebuffer size. The "ReBAR needs Gen3" objection has been rebutted. Untested on a Gen2-trained card |

## Power and electrical

| Quantity | Value |
|---|---|
| TDP / default power limit | **250 W** (stock VBIOS: default = maximum) |
| Power limit range, stock VBIOS | 100 W minimum to 250 W maximum. `nvidia-smi -pl` works; there is simply no headroom above stock |
| Power limit with the 300 W OC VBIOS | 300 W maximum; a 30-minute `gpu_burn` logged `POW 278 / 300 W`. Applies to the **8 GB** SKU; nobody in this corpus has verified it combined with the unlock on a 10 GB card |
| Slot power limit (`DevCap`) | **75 W**; everything above that comes from the auxiliary connector |
| External connector | **One 8-pin EPS (CPU-style)** socket carrying two internal 12 V rails, `12V_EXT1` and `12V_EXT2`. Rated 300 W. Cards ship with a dual 8-pin PCIe to 8-pin EPS Y adapter |
| Idle draw | 27 - 46 W, strongly temperature- and residency-dependent. A resident CUDA context pushes it from ~33 W to ~45 W |
| Performance states | **P0 only.** `nvidia-pstated` returns `NVAPI_ERROR`; the two-P-state fork produces no change |
| Rails | `3V3_PEX` (to 1.8 V by LDO), `12V_PEX` (to 5 V via MP1475, 1.35 V and PEXVDD via MP2988, HBMVPP 2.5 V via a second MP1475), `12V_EXT1`/`12V_EXT2` (NVVDD 1.0 V core and HBMVDD via MP2988 multiphase) |
| VRM population | **Depopulated relative to the A100.** Three power MOSFETs and coils absent per side, versus one per side on an A100 40 GB and none on an A100 80 GB; a second comparison put it at roughly 6 of about 20 phases. The 8 GB 64 GB unlock was reported to need no VRM work |

> [!CAUTION]
> **The 8-pin socket is EPS, not PCIe**
>
> An 8-pin PCIe cable is keyed differently from the card's EPS socket and can only be forced
> in, and the 12 V and ground lines are swapped on some pins between the two connector types.
> Forcing one in **will damage the card**. Use the supplied adapter: one leg for 150 W of
> budget, both legs for 300 W.
> Modular PSU cables are also vendor-specific with no standard modular-side pinout; reusing
> one across brands can destroy hardware.

Real measured draw by workload is much lower than the label suggests, and this is a
characteristic of the part rather than a fault: conventional FP32 burn-in reaches only about
60 W and tensor `gpu_burn` about 75 W, while integer and memory-bound workloads reach 160+ W
and sustained real loads land at 200-280 W. **Never validate stability or cooling with an FP32
burn-in on this card.** Raising the limit from 250 W to 300 W measured **+2.8%** on BF16 with
core and memory both below 65 C. Full detail in [power delivery](power-delivery.md) and
[power and PSUs](../operations/power-and-psu.md).

## Form factor, cooling and thermal limits

| Property | Value |
|---|---|
| Form factor | Full-length dual-slot PCIe add-in card |
| Thickness | ~40 mm / 1.57 in (dual-slot); the body clears the PCIe edge connector by roughly 5-6 mm |
| PCB | Nearly, if not completely, identical to the A100 40 GiB board. A100 waterblocks and A100 shrouds physically fit |
| Cooler | **Fully passive**: a bare heatsink with no fan, designed for forced air from high-RPM server chassis fans. `nvidia-smi` reports `Fan Speed : N/A` on every capture |
| Published CFM / static pressure / dBA / fin pitch | **None exists.** Any airflow number must come from community measurement |
| GPU shutdown temperature | 98 C |
| GPU slowdown temperature | 95 C |
| GPU max operating temperature | 85 C |
| Memory max operating temperature | 95 C |
| Practical throttle onset | ~80 C (one tester's telemetry; community design targets settled at 70 C core / 75-76 C memory hotspot) |

> [!CAUTION]
> **GA100 exhibits leakage-driven thermal runaway**
>
> Higher junction temperature raises CMOS leakage, which raises power, which raises
> temperature. Observed first-hand on a card dry-run with a waterblock fitted but no
> coolant: idle draw rose from **40 W to 60 W at 80 C and was still climbing**. If cooling
> fails outright, the part does not settle at its throttle point, it climbs past it. If you
> ever dry-run this card without coolant, power off within five minutes. Cooling solutions
> with measured results are compared in [cooling](../operations/cooling.md).

## Firmware, identification and APIs

| Property | Value |
|---|---|
| Detected PCI IDs | `10de:20c2` (8 GB), `10de:2082` (10 GB), `10de:20b0` (detected by the installer, **not** unlocked) |
| Unlock device gate | `_kgspSec2PostblTimingEnabled()` accepts `0x20C2` and `0x2082` only. A `20b0` card installs cleanly and simply does not unlock |
| VBIOS on Gen2-confirmed and OC cards | `92.00.6D.00.0A` (300 W ROM), BoardPN `900-11001-0108-000`, GPUPN `20C2-105-A1`, subsystem `0x158510DE` |
| Supported drivers (shipping `master`) | `610.43.03` (default) and `610.43.02`, exact match, build dies otherwise |
| Driver model | nvidia-open kernel modules, patched. Secure Boot must be off |
| CUDA | Compute capability 8.0 (`sm_80`). Build with `-DCMAKE_CUDA_ARCHITECTURES=80` |
| OpenCL | Works; OpenCL-Benchmark is the community's evidentiary standard for a claimed unlock |
| SYCL, PyTorch, cuBLAS, CUTLASS | All exercised in the corpus |
| Graphics | Functional but poor even after unlocking, and PCIe is the reason: BeamNG.drive measured 15 fps at Gen1 x16 and 5 fps at x4. This is not a gaming card |

## Comparison anchors

| Part | SMs / cores | Memory | Bus | Notes |
|---|---|---|---|---|
| CMP 170HX 8 GB, unlocked | 70 / 4480 | 64 GB HBM2e | 4096-bit | This card |
| CMP 170HX 10 GB, unlocked | 70 / 4480 | 40 GB HBM2 | 5120-bit | Same silicon, different harvest |
| A100 PCIe 40 GB | 108 / 6912 | 40 GB | 5120-bit | Stock CFG1 `0x02669000` |
| A100 PCIe 80 GB | 108 / 6912 | 80 GB | 5120-bit | Stock CFG1 `0x02779000`, LMR `0x0000028b` |
| A100 32 GB Drive (PG199) | 96 | 32 GB | 4096-bit | All nine speed-select fuses read 0; shares the 170HX's NVLink kill |
| CMP 90HX | GA102, GDDR6X | n/a | n/a | Different die entirely; no hidden VRAM, no NVLink fingers |

Where the unlocked card lands against an A100 has never been settled with matched benchmarks
on both parts. Estimates in circulation cluster at 70-75%, roughly consistent with the 70/108
SM ratio, with outliers in both directions. Spec-wise the unlocked 64 GB card is comparable to
an AMD Instinct MI210 on bandwidth, capacity and BF16/FP16 throughput, with the interconnect
being the clear point in AMD's favour.

## Related pages

- [What is this card](../start/what-is-this-card.md) for the plain-language introduction
- [GA100 silicon](ga100-silicon.md), [fuses and OTP](fuses-and-otp.md),
  [board and variants](board-and-variants.md)
- [Memory subsystem](memory-subsystem.md), [PCIe subsystem](pcie-subsystem.md),
  [power delivery](power-delivery.md), [thermals](thermals.md), [VBIOS](vbios.md)
- [The unlock, in overview](../unlock/overview.md) and the
  [register reference](../unlock/register-reference.md)
- [Glossary](../start/glossary.md) for any term above that is new to you
