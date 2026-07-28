# Measured performance

**What this page covers.** Every reproducible throughput number for the CMP 170HX: compute
rates per datatype before and after the unlock, HBM bandwidth, PCIe bandwidth at each link
configuration that anyone has actually reached, and how all of it compares against a real
A100. Test conditions are stated on every row. Tuning levers (clock offsets, power limits,
profiles) live on [tuning.md](tuning.md); inference-specific numbers live on
[llm-inference.md](llm-inference.md).

**The headline result.** The compute unlock is a register write, not a clock change. Writing
SS0 `0x0082381c` = `0x88888888` and SS1 `0x00823820` = `0x00000008` (after opening the FEAT
PLM at `0x00823804`) takes FP32 from **0.30-0.41 TFLOPS to 12.2-12.8 TFLOPS**, a **26-32x**
gain, at unchanged clocks. Nothing in the shipping unlocker touches core clock, memory clock,
power limit or PCIe link speed, so every figure below is a stock-clock figure unless it says
otherwise. See [compute-throttle.md](../unlock/compute-throttle.md) for the mechanism.

**The control that proves the mechanism.** In the same-card A/B where FP32 moves 30.7x,
memory bandwidth moves from **1592 GB/s to 1599 GB/s**, a ratio of 1.0x. NVIDIA restricted the
instruction issue rate, not the memory subsystem.

---

## How to read these numbers

- **Stock clocks throughout.** Sustained SM clock is 1410 MHz (1470 MHz with
  `nvidia-smi -pl 300`), base 1140 MHz. The `clocks.max.sm = 1935 MHz` field that `nvidia-smi`
  reports post-unlock is a *reported field*, not an achievable clock; it is a single report,
  never re-checked, and the VBIOS table maximum is 1695 MHz. Treat 1935 MHz as low confidence.
- **The throttle is per-instruction-class.** It is not a global multiplier. On a clean CMP 90HX
  the ratios were FP64 1/64, FP32 1/32, FP16 1x (untouched), INT32 1/2, INT8 1/16. The 170HX
  follows the same pattern with different divisors, which is why one datatype can look normal
  while another is 30x down.
- **Two INT8 numbers are both real.** The tensor MMA path and the library/OpenCL path differ by
  7.6x. Do not average them.
- **Compression is off.** Shipping patch `0005-ce-scrub-workarounds.patch` forces
  `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY` for `0x20C2` and `0x2082`, where stock returns
  `NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`. Any bandwidth comparison against a
  real A100 must note this.
- **Two measurement gotchas that produce garbage.** `CUBLAS_COMPUTE_16F` with a `float`
  alpha/beta pointer returns instantly and reports an absurd 10748 TFLOPS: that is a no-op, not
  a result, so use the fp32-accumulate rows. And CUDA 13 removed `cudaDeviceProp::clockRate` and
  `memoryClockRate`, so query `cudaDeviceGetAttribute` with `cudaDevAttrClockRate` /
  `cudaDevAttrMemoryClockRate` instead.

!!! warning "Theoretical peaks masquerading as measurements"
    Three separate figures in circulation are tool-computed device properties, not run results.
    `1769.47 GB/sec` is exactly `864 MHz x 4 x 4096 bits / 8`; `12633.60 GFlops` is exactly
    `4480 x 2 x 1410 MHz`. Both are derived from the clock and bus-width fields printed two
    lines above them in the same mixbench dump. **No card has ever measured 1769 GB/s.** The
    same 12633.6 GFLOPS reappears in a second dump as "4480 cores, 12.634 TFLOPs/s", again as a
    device property.

---

## Compute: locked versus unlocked

All rows measured on compute-unlocked cards at stock clocks unless noted. The locked column is
the same silicon before the SS0/SS1 writes.

| Datatype / path | Locked | Unlocked | Ratio | Conditions |
|---|---|---|---|---|
| FP32 non-tensor | 0.30 / 0.40 / 0.41 TFLOPS | 12.58 TFLOPS | 28.4x-30.7x | 1024³ / 4096³ / 8192³ modded sweep, same card |
| FP32 SGEMM | 393 Gflop/s | 12,233-12,256 Gflop/s | 31x | gpu-burn, peak 67 C |
| FP32 (rented cohort) | 0.39 TFLOPS | 12.6 TFLOPS | 32.3x | mean of 8 cards, driver 610.43.02 |
| FP64 non-tensor | 0.20 TFLOPS | 6.223-6.31 TFLOPS | ~31x | 1/2 of FP32, the full unrestricted GA100 rate |
| FP64 tensor | 197 / 191 Gflop/s (paper) | 11.6-11.96 TFLOPS | 59x-62x (paper) | 11,668 / 11,786 Gflop/s DGEMM / FP64 tensor |
| TF32 tensor | 2.96-3.21 TFLOPS | 79-94 TFLOPS | 15x-28x | widest spread of any datatype |
| FP16 tensor | 6.01 TFLOPS | 158.7-190 TFLOPS | ~27x | fp32 accumulate at the low end |
| BF16 tensor | 6.41 TFLOPS | 164.4-192.7 TFLOPS | ~28x | ceiling 202.1 TFLOPS |
| INT8 tensor MMA | 1.60 TOPS | 335.0-335.6 TOPS | n/a | per-instruction microbenchmark |
| INT8 library / OpenCL | 1.60 TOPS | 43.33-47.894 TOPS | 27.0x | torch, cuBLAS, OpenCL-Benchmark |
| INT4 tensor MMA | n/a | 320.2 TOPS | n/a | `mma_s4s4s32_8_8_32` |
| FP4 / FP6 / FP8 MMA | not supported | not supported | n/a | expected for sm_80 |

### FP32, the load-bearing number

Seven tools on at least a dozen distinct cards land inside a 12.2-12.8 TFLOPS band.

| Value | Tool / conditions |
|---|---|
| 12.72 TFLOPS | torch GEMM 8192² |
| 12.76 TFLOPS | `gemm_probe.cu` n=8192, 30 iterations |
| 12.58 TFLOPS | 8192³ modded sweep |
| 12,565.14 GFLOPS | clpeak, driver 13.0 / CUDA 13.3 |
| 12.493 TFLOPs/s | OpenCL-Benchmark, 10 GB to 40 GB card |
| 12.6 TFLOPS | mean of eight rented cards |
| 12,233-12,256 Gflop/s | paper Table 2, gpu-burn |
| 12,229-12,254 Gflop/s | sustained burn-in, 268435456 B buffers, 24 iterations |
| 11.1 TFLOPS | per-instruction scalar `fma_fp32` microbenchmark (lower bound) |

The theoretical peak for a 70-SM GA100 at 1410 MHz is 12,633.6 GFLOPS, so the card achieves
roughly 99% of arithmetic peak. Locked, independent measurements sit at 0.3159 TFLOPS FFMA / 0.32 / 0.39
TFLOPS / 393 Gflop/s SGEMM / 367 GFLOPS clpeak, all inside the 1/32 issue-rate model.

### FP64 has two rates and they must not be conflated

Non-tensor FP64 runs at exactly **1/2 of FP32** (6.223 TFLOPs/s OpenCL, 6308.65 GFLOPS clpeak,
~6,200 GFLOPS DGEMM, 5.6 TFLOPS for a pure scalar `fma_fp64` microbenchmark). FP64 **tensor**
runs at roughly **2x that** (11.65 TFLOPS, 11.96 TFLOPS clpeak WMMA fp64 8x8x4, 11.6 TFLOPS
across eight rented cards, 11,668-11,786 Gflop/s in the paper). The 1/2 ratio is the full
unrestricted GA100 rate: FP64 is genuinely restored, not partially.

### Tensor throughput detail

| Datatype | Value | Tool / shape |
|---|---|---|
| TF32 | 79.0 TFLOPS | 8 rented cards, torch GEMM |
| TF32 | 80.59 / 84.75 / 51.53 TFLOPS | 8192³ / 4096³ / 1024³ modded sweep |
| TF32 | 81.35 TFLOPS | torch GEMM 8192² |
| TF32 | 83.2 TFLOPS | `mma_tf32tf32f32_16_16_8` |
| TF32 | 88.9-91.9 TFLOPS | `gemm_probe.cu` n=8192 |
| TF32 | 89.69 TFLOPS | clpeak `mma.sync m16n8k8` |
| TF32 | 94,103 Gflop/s | paper, gpu-burn, 64 C |
| FP16 (fp32 acc) | 158.7-160.0 TFLOPS | `gemm_probe.cu` n=8192 |
| FP16 (fp32 acc) | 162.7 TFLOPS | 8 rented cards |
| FP16 | 174.11 TFLOPS | 4096³ modded sweep |
| FP16 | 175.79 TFLOPS | torch GEMM 4096² |
| FP16 (fp32 acc) | 179.1 TFLOPS | `mma_f16f16f32`, both tile shapes |
| FP16 (fp16 acc) | 180.2 / 180.3 TFLOPS | `mma_f16f16f16_16_16_16` / `_32_8_16` |
| FP16 (fp16 acc) | 189.66 TFLOPS | clpeak `mma.sync m16n8k16` |
| BF16 | 164.4 TFLOPS | `mma_bf16bf16f32`, both tile shapes |
| BF16 | 171.4 TFLOPS | 8 rented cards |
| BF16 | 180.09 TFLOPS | torch GEMM 4096² |
| BF16 | 183.75 TFLOPS | 4096³ modded sweep |
| BF16 | 188.1-192.7 TFLOPS | `gemm_probe.cu` n=8192, fp32 accumulate |
| BF16 ceiling | 202.1 TFLOPS | arithmetic: 2048 x 70 SM x 1410 MHz, verified exact |

Two spreads are unexplained and are recorded as such. TF32 varies 19% across seven tools while
FP16 and BF16 stay tight. FP16 with fp16 accumulate reads consistently *above* FP16 with fp32
accumulate, where on A100 the two should be the same rate; the likeliest explanation is that
mmapeak-style microbenchmarks keep operands in shared memory and therefore flatter the card.

!!! question "Open problem: INT4 measures below INT8"
    `mma_s4s4s32_8_8_32` returns **320.2 TOPS** against INT8's 335.0/335.6 TOPS. On Ampere INT4
    tensor throughput should be roughly 2x INT8. Nobody re-ran it. The INT8 side is sound (two
    tile shapes agree); the INT4 side is one run. Re-running the INT4 shape with a longer target
    time and varied tiles is the cheapest open lead in this domain.

!!! question "Open problem: the INT8 library path is 7.6x below the INT8 tensor path"
    Direct MMA gives 335 TOPS; torch, cuBLAS and OpenCL all land at 43-48 TOPS. Either those
    libraries are not issuing IMMA on this device, or the unlock leaves an INT8 issue-rate
    restriction partially in place. The suggested test is an explicit `CUBLAS_COMPUTE_32I` GEMM
    with INT8 inputs against the raw MMA figure.

### Silicon-to-silicon reproducibility

Eight unlocked 64 GB cards from one rental, benchmarked in a single session on driver 610.43.02
at PCIe Gen1 x4, showed **under 2.5% per-card spread** and **8/8 passes** on a full byte-compare
VRAM integrity test. Eight cards, one report.
Stock cards, no capacitor mod, no Gen2.

| FP16 | BF16 | TF32 | FP32 (locked) | FP64 | INT8 | HBM |
|---|---|---|---|---|---|---|
| 162.7 TFLOPS | 171.4 TFLOPS | 79.0 TFLOPS | 12.6 TFLOPS (0.39) | 11.6 TFLOPS | 44.1 TOPS | 1600 GB/s |

This is the strongest evidence in the archive that the unlock lands identically across cards.

### Failed-unlock signature

If BF16 comes back around **12 TFLOPS instead of ~185**, the payload did not land. One user
reporting mixbench 12 BF16 TFLOPS, clpeak 367 GFLOPS and a custom GEMM at 6.25 TFLOPS was
diagnosed as seeing "the performance of tf32 in locked mode" against the known 202 TFLOPS
ceiling, accepted the diagnosis and retried. An order-of-magnitude shortfall against 202 TFLOPS
is the tell. See [verify.md](../procedures/verify.md).

Note also that **gaming frame rates are not a valid verification method**: one tester measured
identical FPS with and without the compute unlock while LLM and CUTLASS throughput clearly
moved. The unlock targets SM issue rate, not the graphics path.

---

## Memory bandwidth

| Quantity | Value | Conditions |
|---|---|---|
| Theoretical peak | 1555.2 GB/s = 1448.4 GiB/s | 1215 MHz DDR x 5120-bit; the two figures are the same number in different units |
| Peak line of a real sweep | 1448 GiB/s | 79.3 GiB total / 79.0 free |
| Measured, 8 rented 64 GB cards | 1600 GB/s | identical across all eight |
| Stock versus modded, same card | 1592 to 1599 GB/s (1.0x) | 256 MB working set, the unlock control row |
| OpenCL coalesced read / write | 1305.86 / 1521.62 GB/s | 10 GB to 40 GB card, driver 580.159.03 |
| OpenCL misaligned read / write | 789.82 / 161.76 GB/s | same card |
| One OpenCL test | 1333 GB/s | stock VBIOS |
| 2023 external review ceiling | 1355 GB/s | used for its roofline ridge points |

!!! note "There is no single canonical HBM number"
    Measured HBM bandwidth spans **1305.86 GB/s to 1600 GB/s** and no methodology reconciles
    the range. Partial reconciliation: the 8 GB card carries 4 stacks of faster HBM2e
    (4096-bit) while the 10 GB card carries 5 stacks of slower HBM2 (5120-bit), and
    read/write/misaligned patterns differ by nearly 10x *within a single tool*. Quote the range,
    not a point estimate. Separately, "1493 GB/s datasheet" and "1555 GB/s theoretical at full
    boost" are different quantities (the first is the A100 40 GB PCIe datasheet figure, the
    second is what 1215 MHz x 5120-bit computes to) and are frequently used interchangeably in
    circulating documents.

### The 79% plateau above an 8 GiB offset

Measured on a 10 GB card fired to the abandoned 80 GB geometry, with a 1 GB memset sweep:

| Offset | Bandwidth | Percent of peak | Time |
|---|---|---|---|
| 0 GB | 1416 GiB/s | 98% | 0.70-0.71 ms |
| 1 GB | 1422 GiB/s | 98% | 0.70-0.71 ms |
| 2 GB | 1416 GiB/s | 98% | 0.70-0.71 ms |
| 4 GB | 1419 GiB/s | 98% | 0.70-0.71 ms |
| 8 GB through 76 GB | 1147-1151 GiB/s (flat) | 79% | ~0.87 ms |

The gap closes entirely with a large enough chunk: at a 32 GB chunk the sweep gives
1452 GiB/s (100%) at offset 0 against 1443 GiB/s (100%) at offset 40 GB, versus
1419 vs 1149 GiB/s for a 1 GB chunk.

Two shipping-code facts bear on this without settling it:

- `0004-bar0-pramin-clamp.patch` pins the BAR0 window to `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`
  whenever `devId` is `0x20C2` or `0x2082` and `fbAddrSpaceSizeMb > 0x2000`. That is a genuine
  8 GiB discontinuity in shipping code at exactly the offset of the observed step, but PRAMIN is
  a CPU-side BAR0 aperture and the sweep was a device-side memset, so causality is **not**
  established.
- `0001-sec2-postbl-plm-ss-cfg.patch` extends the last FB region to `targetFbBytes - 1` with
  `supportCompressed = NV_TRUE`, `supportISO = NV_TRUE` and `performance = 20`. The resource
  manager therefore models the whole unlocked range as uniform-performance memory and has no way
  to prefer the fast region.

!!! question "Open problem: does the plateau exist on shipping geometries?"
    The sweep was only ever run on the abandoned 80 GB configuration. Repeating the identical
    offset and chunk sweeps on a shipping 8 GB to 64 GB card would settle whether this is a
    property of any unlocked geometry or an artefact of the over-fire. See
    [80gb.md](../frontier/80gb.md).

---

## PCIe bandwidth by link configuration

Two independent mechanisms, never to be conflated. **Link speed** (Gen1 to Gen2) is a
driver/firmware change and exists only on unreleased branches. **Link width** (x4 to x16) is a
physical board modification: 12 of the 16 lanes ship with their AC-coupling capacitors
depopulated, and restoring them means hand-soldering 24 0402 parts. See
[pcie-gen2.md](../unlock/pcie-gen2.md) and [physical-mods.md](physical-mods.md).

| Link configuration | How reached | Measured bandwidth | Tool / conditions | Confidence |
|---|---|---|---|---|
| Gen1 x4 (stock, shipping unlock) | nothing required | send 0.80 / receive 0.84 / bidirectional 0.81 GB/s | One OpenCL-Benchmark screenshot, relayed from an outside hardware group, on a 10 GB-to-40 GB card; the tool printed the link as "Gen1 x16" | medium |
| Gen1 x4 | nothing required | ~0.85 GB/s | clpeak | high |
| Gen1 x4 under inference load | nothing required | ~1.0 GB/s, did not ramp | 8-card rig, device max reported Gen2 x16 | high |
| Gen1 x16 | capacitor mod only | 2.88 GB/s (nominal ~4 GB/s) | one report, one modded card, tool unnamed; the measurer expected 3.2 GB/s and was told the gap is Gen1 signal overhead | medium |
| Gen2 x4 | `Gen2`-family branch only | send 1.68 / receive 1.71 GB/s | OpenCL-Benchmark, one archived screenshot, unmodded card; the setup script independently predicts "~0.85 to ~1.7 GB/s, exactly 2x" | medium |
| Gen1 → Gen2 on a cap-modded card that negotiated x8 | branch **and** a partial capacitor mod | 1.67 → 3.24 GB/s | one A/B, single card, Asus Prime Z370 / i3-8100 / 8 GB RAM. Not a Gen2 x4 figure: 3.24 GB/s is above the ~2.0 GB/s Gen2 x4 ceiling because the link was x8 | medium |
| Gen2 x4 (vendor claim) | distributed package README | "2 GB/s" | not independently logged, not achievable on shipping `master` | low |
| Gen2 x16 | branch **and** full 24-capacitor mod | 6.63-6.67 GB/s (~83% of the 8 GB/s line rate); nvtop TX 7.061 GiB/s | `ocl_pcie_bw` | medium |

!!! warning "Experimental: Gen2 x16 is one rig, one day"
    Gen2 x16 has been observed **once**, on 2026-07-26, on a capacitor-modded card also running
    the `Gen2` branch. There is no burn-in, no AER counters over time and no second rig, so
    stability at Gen2 x16 is unestablished. Shipping `master` contains patches `0001`-`0006`
    only, with no `pcie:` block in `constants.yaml`, so any Gen2 result is
    experimental-branch-only.

Also relevant: **12 of 24 capacitors populated yields x8**, because width negotiation falls back
to the next legal width (16, 8, 4, 1). An x8 result after a mod means incomplete or bridged
solder work, not a distinct hardware limit.

### How much PCIe actually costs you

PCIe sensitivity is engine- and topology-dependent, and the two headline results are not in
conflict.

| Case | Change | Result |
|---|---|---|
| Single card, llama.cpp | x4 to x16 (same generation) | pp 439 to 448, tg 81.91 to 85.75 (about +2%) |
| Three cards, llama.cpp | x4 to x16 | pp 441 to 461, tg 86 to 89 |
| Three cards, GLM-5.2 with almost all of the model on CPU (one layer plus buffers on the GPUs) | Gen1 x4 run to a later "gen2 x4 attempt" | pp2048 33.44 ± 0.37 to 48.22 ± 1.36 t/s (**+44.2%**), tg512 5.90 ± 0.03 to 6.39 ± 0.09, time-to-first-response 61,253.57 ± 675.94 ms to 42,510.25 ± 1,217.69 ms (**-30.6%**). Both percentages are computed here from two separately posted runs, not stated by the tester |
| Single card, `Qwen3.6-27B-MTP-UD-Q8_K_XL` on ik_llama with MTP, model fully VRAM-resident | Gen1 x4 to Gen2 x4, "all other factors unchanged" | pp2048 328.81 to 449.41 t/s, pp8192 363.25 to 493.86, tg128 38.15 to 41.52, tg512 37.69 to 40.12. Same tester as the row above, runs five days apart |
| Single card, model load | Gen1 x4 | ~30 s, a one-time cost |
| Graphics (BeamNG.drive) | Gen1 x16 versus x4, cap mod done | 15 fps versus 5 fps, "still awful" either way |

The reconciliation: single-card work is largely bandwidth-local (weights are resident, only the
model load crosses the link), while multi-card and CPU-offload prefill is link-bound. Caveat
carried from the source for the +44.2% row: the post-Gen2 run used a Q4-labelled quant where the
pre-Gen2 run was unlabelled, so the prompt-processing delta may be overstated. A Q2_K_XL quant on
the same rig at Gen2 x4 gave pp2048 49.00 ± 1.08 and tg512 6.81 ± 0.06. The single-card row
complicates the picture rather than settling it: that model was entirely resident in VRAM, and
neither the tester nor anyone in the channel could explain why the link speed moved it at all.
Both rows are the same tester; there is no independent Gen2 x4 inference measurement.
Full tables and conditions on [llm-inference.md](llm-inference.md).

!!! question "Open problem: nobody has measured Gen2 x16 on a multi-card LLM rig"
    The Gen2 x16 bandwidth figure and the Gen1-to-Gen2 inference runs were
    measured on different systems and never combined. The 2x2 matrix of {Gen1, Gen2} x {x4, x16}
    on one rig with one model would settle both this and the width-versus-generation dispute.

---

## Thermals and power, in brief

Full treatment is on [thermals.md](../hardware/thermals.md), [cooling.md](cooling.md) and
[power-and-psu.md](power-and-psu.md); what matters for benchmarking is here.

| Observation | Value |
|---|---|
| Sustained full-rate GEMM burn-in | 12,229-12,254 Gflop/s flat while the die went 62 to 64 to 69 to 71 to 73 C over ~30-40 s, zero errors |
| Peak load temperatures (paper) | 67 C FP32, 64 C FP64 tensor and TF32 tensor; a full-capability part throttles only above ~85 C |
| Default `gpu_burn` | ~70 C ± 2 |
| Idle draw / stock cap | ~42 W / 250 W on the controlled rig |
| Power under hashcat versus FP32 burn | 160+ W versus 60-75 W (2023, locked card) |

**Practical rule: do not validate stability or cooling with a conventional FP32 burn-in.** This
card is hard to load. Integer and memory benchmarks pull far more power than FP32 tools do.

The accepted post-unlock validation recipe:

```bash
# github.com/wilicc/gpu-burn
make COMPUTE=80
./gpu_burn -tc -m 90% 1200          # 20 minutes, tensor cores, 90% of VRAM
# variant used by one distributed package, expecting 0 memory errors:
./gpu_burn -m 63500 -d 30
```

Reported clean runs: 30 minutes on a tuned single card; 2 hours on each of four 8 GB to 64 GB
cards with no instability; a 5-minute pass on a 10 GB to 40 GB card. Ensure adequate cooling
first.

!!! danger "Never validate the 80 GB geometry as if it worked"
    Firing a 10 GB card to 80 GB produces gpu-burn errors, independently reproduced. 10 GB cards
    ship at 40 GB for this reason. See [80gb.md](../frontier/80gb.md).

Memory overclocking was reported to buy about **+2.5%** (gpu_burn 12,180 Gflop/s average at
default versus 12,472-12,485 Gflop/s sustained) at a cost of about 5 C (70 C ± 2 versus 75-77 C).
Note that no branch named `mem_overclock` exists in the archived branch set, and no archived
branch contains any clock, boost or p-state code at all: a grep across all thirteen trees for
overclock/memclk/pstate/boost returns nothing. The result stands as a tester report that cannot
be checked against code.

---

## Comparison with the A100

The 170HX carries a **complete GA100 die** (826 mm², `PMC_BOOT_0` = `0x170000a1`, identical to
all three A100 SKUs and the Drive A100), floorswept to 70 of the die's SMs. So the honest
comparison is "same architecture, fewer SMs, worse I/O, no ECC, no NVLink".

| Property | CMP 170HX (unlocked) | A100 40 GB reference | Notes |
|---|---|---|---|
| Die | GA100, 826 mm² | GA100, same die | `PMC_BOOT_0` `0x170000a1` on both |
| SMs / CUDA cores | 70 / 4480 | 108 / 6912 (A100 SXM4 40 GB) | 5 active GPCs, 35 TPCs |
| Compute capability | 8.0 (sm_80) | 8.0 | identical ISA, no FP8, no NVFP4 |
| L2 cache | 32 MB (32768 KB) | n/a | TechPowerUp's 8 MB for the 170HX is wrong, corroborated by latency-spike measurement |
| Capacity | 64 GB (8 GB SKU) or 40 GB (10 GB SKU) | 40 GB | see [memory-geometry.md](../unlock/memory-geometry.md) |
| Bus width | 4096-bit (8 GB, 4 stacks) / 5120-bit (10 GB, 5 stacks) | 5120-bit | GPU-Z on an A100-PCIE-40GB reports 5120-bit, 1555.2 GB/s, 1215 MHz memory |
| HBM bandwidth | 1305.86-1600 GB/s measured | 1493 GB/s datasheet | the eight-card 1600 GB/s figure is above the A100 40 GB datasheet number |
| Host link | Gen1 x4 stock; Gen2 x4 on a branch; x16 only after soldering | PCIe 4.0 x16 | the single largest gap |
| NVLink / P2P | fused off, no lever found; 0 of 56 GPU pairs report peer access | present | see [nvlink.md](../frontier/nvlink.md), [p2p.md](../frontier/p2p.md) |
| ECC | fused off, no telemetry | on | see [ecc.md](../frontier/ecc.md) |
| Memory compression | forced off by the shipping patch | on | affects any bandwidth comparison |
| MIG | only a `1g.64gb` profile exists; standard A100 profiles are rejected | full profile set | |

### Application-level comparisons

The FluidX3D and hashcat rows below were measured in 2023 on a **locked** card, before the
register unlock existed. The FluidX3D rows used the no-FMA source workaround; hashcat was run
unmodified, being integer work that the FP32 FMA throttle does not reach. They are the only whole-application
comparisons against a named A100 in the archive, and they are a floor, not a ceiling, for what
an unlocked card should do.

| Workload | CMP 170HX | A100 | Ratio |
|---|---|---|---|
| FluidX3D FP32/FP32, no-FMA | 7681 MLUPs/s at 1175 GB/s (458 steps/s) | 8526 MLUPs/s (A100 40 GB PCIe) | 90.1% |
| FluidX3D FP32/FP16S, no-FMA | 12386 MLUPs/s at 954 GB/s (738 steps/s) | 16035 MLUPs/s | 77.2% (and +11.7% over an RTX 4090's 11091) |
| hashcat MD5 | 43930.0 MH/s (53.01 ms) @ Accel:64 Loops:512 Thr:1024 Vec:1 | ~64900 MH/s | 67.7% (also slower than an RTX 3080's 54000.1 MH/s) |
| GLM-5.2 decode, 8-way pipeline parallel | 30.2 t/s on 8 unlocked 64 GB cards | the circulated reference recipe targeted 8x A100 80 GB at an expected ~40 t/s | see [llm-inference.md](llm-inference.md) |

Note on the FluidX3D rows: with FMA enabled on the locked card the same kernel is *compute*-bound
at 2276 MLUPs/s and only 348 GB/s. Dropping to FP32/FP16S halves memory traffic to 173 GB/s but
leaves throughput at 2250 MLUPs/s. Flat throughput across halved bandwidth is the diagnostic
signature of the throttle. With FMA removed the kernel becomes memory-bound again, achieving
1175 GB/s, which is 87% of that review's 1355 GB/s ceiling.

A single-A100 GLM-5.2 figure of **55 tok/s** circulates as a comparison baseline. It is
second-hand with no configuration attached and is rated low confidence.

### Roofline selection rule

From the 2023 external review, still the best guidance for deciding whether a kernel suits this
card in its **locked** state: useful below **0.3 FLOPs/byte** of arithmetic intensity with stock
FMA, or below **4.6 FLOPs/byte** after disabling FMA. Those ridge points follow from 394 GFLOPS
and 6250 GFLOPS over a 1355 GB/s measured ceiling (0.291 and 4.61 exactly). After the compute
unlock the FP32 ridge moves out by roughly the same 30x factor, so the rule stops binding: an
unlocked card is a normal memory-bound GA100 for most kernels.

Two worked examples of the rule in action:

- A SYCL FDTD kernel at 0.25 FLOPs/byte needed **no** workaround at all on a locked card:
  10110 MC/s and 1156992 MiB/s (16777216 cells x 1000 timesteps in 1.66 s), about 1.5x a
  Radeon VII / Instinct MI50's ~6000 MC/s, using unmodified source. Its achieved 181.98 GFLOPS
  never approaches the 394 GFLOPS throttled ceiling. Note 1156992 MiB/s is base-2 and so looks
  smaller than the base-10 GB/s figures elsewhere.
- FluidX3D at 1.7 FLOPs/byte (261 FP32 + 102 INT32 ops over 153 B of traffic, 363 ops per cell
  update) sits above the locked ridge and is exactly where the FMA workaround pays.

---

## Tools and the evidentiary standard

The community standard for a claimed unlock is a screenshot of
`ProjectPhysX/OpenCL-Benchmark`. AI-written summaries were explicitly rejected as proof.

| Tool | Use | Caveat |
|---|---|---|
| `ProjectPhysX/OpenCL-Benchmark` | proof-of-unlock artefact, full-device dump | **does not measure tensor cores at all**; reading only its output leads to "the card does 12.5 TFLOPS" and misses the ~190 TFLOPS tensor path |
| mixbench (CUDA) | compute sweep | prints theoretical peaks next to measurements; see the warning above |
| cuBLAS tensor tests / torch GEMM sweeps | representative tensor numbers | torch GEMM reads from HBM, so it is more representative than MMA microbenchmarks |
| `ReinForce-II/mmapeak` | per-instruction MMA sweep | optimistic: operands stay in shared memory |
| `gemm_probe.cu` | highest published FP32 and BF16 numbers | its TF32 (88.9-91.9) is below the paper's 94.1 |
| clpeak | full-device dump | explicitly **unsuitable** for measuring the FMA/DP4A patches |
| gpu-burn | stability and sustained flops | build with `make COMPUTE=80` |
| `ocl_pcie_bw` | PCIe bandwidth | the tool behind the Gen2 x16 figure |

!!! note "Superseded: mmapeak screenshots as proof of ownership"
    One widely reposted mmapeak image was shown to be recycled: byte-identical figures with zero
    run-to-run variance across an original, a blog repost and a forum comment, which does not
    happen across real repeated runs. Ask for a fresh run with variance, not a screenshot.

---

## Non-LLM workload results

| Workload | Result | Conditions |
|---|---|---|
| SDXL 1024², 30 steps | 4.73 s (6.35 it/s, 10.5 GB) versus 7.59 s (3.95 it/s) on an RTX 3090 = **1.60x** | identical script |
| Wan2.1-T2V, 81 frames at 480p | 73.4 s (0.91 s/frame, 18.5 GB) versus 132.8 s = **1.81x** | identical script |
| LTX-Video, 81 frames | 11.0 s (0.14 s/frame, 15.9 GB) versus 20.0 s = **1.82x** | identical script |
| Wan2.1, 129 frames at 720p | 1,485 s using 33.3 GB versus **OOM** on the 3090's 24 GB | identical script |
| pearlhash mining | 3 TH to 147 TH after the unlock (~49x, one tester); 140-170 "th" at 200 W after a wildrig update | the Pearl network's aggregate hashrate doubled after the unlocker was released |
| Gravity bench, 50k asteroids | 18 FPS | best reported; unlock state not stated |
| FurMark | 56 fps | pre-memory-unlock |

Diffusion is the standout non-LLM fit: the workload is compute-bound and fits entirely in VRAM,
so the Gen1 x4 link never bites.

!!! question "Open problem: the mining unit is uninterpretable"
    "140-170 th @ 200 W" is reported with no unit expansion and no second per-card source. The
    network-level doubling is solid; the per-card figure is not usable as written.

---

## Open questions in this domain

1. Why INT4 measures below INT8.
2. Why the INT8 library path sits 7.6x below the INT8 tensor path.
3. Whether the 79%-of-peak bandwidth plateau above 8 GiB applies to shipping 64 GB and 40 GB
   geometries.
4. Whether the `n_ubatch` scheduling cliff seen on a CMP 100-210 (pp512 353.59 to 977.20 with
   flash attention off, 380.96 to 1159.39 with it on, a 3.04x gain from one flag) also exists on
   a 70-SM 170HX. This is the single cheapest untested lead in the archive: sweep `n_ubatch`
   from 48 to 80 with `llama-bench`.
5. Why TF32 spreads 79-94 TFLOPS when BF16 and FP16 are tight.
6. Whether the Gen2 x16 bandwidth result translates into multi-card LLM throughput.
7. What practical P2P bandwidth between two 170HX cards is, if any.

See [open-questions.md](../frontier/open-questions.md) and
[dead-ends.md](../history/dead-ends.md) for the full register.
