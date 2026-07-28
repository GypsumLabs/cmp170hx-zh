# Tuning an unlocked card

**What this page covers.** Getting the most out of an unlocked CMP 170HX: clocks and the one
working overclock lever, power limits, persistence mode, performance-state management, how much
VRAM you can actually allocate, and workload-level tuning. Measured baseline throughput is on
[performance.md](performance.md); inference-specific tuning is on
[llm-inference.md](llm-inference.md); cooling hardware is on [cooling.md](cooling.md).

**The three facts that shape everything here.**

1. **The only working overclock lever is the GPC clock VF offset via NVML**
   (`nvmlDeviceSetGpcClkVfOffset`, range `[-1000 .. +1000]` MHz). The memory-clock VF offset
   range is `[0 .. 0]` and the driver refuses it. `nvidia-smi` on 610.43.03 exposes only the
   negative direction (`--set-vf-derate`), which makes overclocking look unavailable, but NVML
   exports the full API.
2. **The offset is really an undervolt expressed as a frequency offset.** At a pinned 1350 MHz
   SM clock, going from +0 to +300 cut draw from **174.6 W to 132.0 W (-24.4%)** at identical
   throughput (179.7 versus 180.7 TFLOPS BF16). The best value in tuning this card is power
   saved, not throughput gained.
3. **Above roughly +300 MHz the failure mode is silent data corruption, not a crash.** A run
   that completes is not evidence a setting is safe.

!!! danger "Silent memory corruption above +300 MHz offset at a 1400 MHz ceiling"
    Measured with a full-VRAM pattern sweep as the gate: **+250** at 142.2 W passed 3 sweeps
    with 0 errors; **+300** at 138.5 W passed 4 sweeps with 0 errors; **+325** at 132.7 W gave
    **6 errors, then 3 errors, then 0 errors** across 3 sweeps; **+375** took a CUDA device
    fault under load. The safe window at a 1400 MHz ceiling is **one 25 MHz step wide** above
    +300, and past it you get bad data rather than a stack trace. Run four sweeps, not two, and
    prefer margin whenever two settings measure equal.

---

## Clocks

| Quantity | Value | Notes |
|---|---|---|
| Base clock | 1140 MHz | also what CPU-RM runs at when GSP is disabled |
| Sustained SM clock, stock | **1410 MHz** | canonical; every sustained measurement sits here |
| Sustained SM clock at `-pl 300` | **1470 MHz** | 300 W requires the OC VBIOS, see below |
| Sustained SM clock, tuning reference card | ~1425 MHz at +0, ~1571 MHz at +150, ~1647 MHz at +300 | single card |
| VBIOS table max graphics clock | 1695 MHz | reference card, VBIOS 92.00.6D.00.0A |
| Practical silicon ceiling | ~1604-1614 MHz at +350 offset | delivered work, not the reported number |
| `clocks.max.sm` as reported by `nvidia-smi` | 1935 MHz | **reported field only, low confidence, not an operating clock**; single report, never re-checked |
| Graphics clock steps | 100 steps, 1695 MHz down to 210 MHz in 15 MHz decrements | `nvidia-smi -q` on 580.159.04 / CUDA 13.0 |
| Memory clock domain | exactly **one** entry, `Supported Clocks / Memory: 1728 MHz` | there is nothing to select. The *stock* 8 GB memory clock is unresolved, see the box below |
| Core clock floor | 210 MHz | will not go lower, which is part of why idle power stays high |

The 10 GB card has **no clock headroom at all**: `nvidia-smi -q` reports Graphics 1140 MHz,
SM 1140 MHz, Memory 1215 MHz at capture, with Max Clocks Graphics 1410 MHz, SM 1410 MHz, Memory
1215 MHz (current equals max). Core-clock offset and memory-clock locks remain in place after
the unlock on 10 GB cards specifically.

!!! question "Open problem: the stock 8 GB memory clock is unresolved"
    The stock 8 GB memory clock is unresolved: 1458 MHz (one sweep and TechPowerUp), 1728 MHz
    (`nvidia-smi -q` Supported Clocks, noted as "432 MHz x 4"), 1890 MHz (`nvtop` during an
    unlocked 64 GB `gpu_burn` at 300 W). 1215 MHz is the 10 GB card and is solid. The plausible
    reconciliation (1458 stock, 1728 OC VBIOS, 1890 overclocked OC VBIOS) is unproven; a raw
    FBPA PLL read would settle it. This page prints 1728, 1890 and 1215 in different places for
    that reason.

!!! question "Open problem: the 1470 MHz ceiling on the 8 GB OC VBIOS is unexplained"
    VBIOS 92.00.6D.00.0A advertises Max Customer Boost Clocks of 1695 MHz graphics/SM, 1728 MHz
    memory (noted as 432 MHz x 4) and 1545 MHz video. Under `mmapeak` the card sat at
    **1470 MHz** with the power limit at 300 W, GPU-T reporting `PerfCap: None`, and the GPU
    drawing only ~150 W. Neither power nor an explicit performance cap explains it.

Memory clock locking is simply refused:

```console
$ nvidia-smi -lmc 1000
Setting locked Memory clocks is not supported for GPU 00000000:21:00.0.
```

Only the power limit and the GPC VF offset are adjustable through that path.

---

## The overclock / undervolt lever

### Validated tuning profiles

All rows below come from a **single reference card** (64 GB, driver 610.43.03, VBIOS
92.00.6D.00.0A, PCIe Gen2 x4). Conditions: sustained BF16 tensor GEMM, n=8192, 10-15 s soak,
NVML power sampled in-process. Every row passed the full-VRAM pattern sweep with
`mem_errors=0` at least twice.

| Profile | Offset | Clock ceiling | BF16 TFLOPS | Draw | GFLOPS/W | Versus stock |
|---|---|---|---|---|---|---|
| stock | +0 | none | 184.3 | 199.2 W | 925 | baseline |
| dense | +250 | 1200 MHz | 160.8 | 120.2 W | 1337 | -13% performance / -40% power |
| **eff (default)** | **+250** | **1350 MHz** | **180.3** | **132.0 W** | **1366** | **-2% performance / -34% power** |
| match | +250 | 1400 MHz | 186.5 | 142.2 W | 1311 | stock throughput at -29% power |
| balanced | +300 | 1470 MHz | 196.2 | 149.7 W | 1311 | +6% / -25% |
| perf | +350 | 1590 MHz | 212.2 | 181.2 W | 1171 | +15% / -9% |
| max | +350 | 1650 MHz | 215.3 | 186.1 W | 1157 | +17% at stock power |

The highest *validated* point at a 1400 MHz ceiling is **+250 to +300** (+300 passed 4 sweeps
with 0 errors). The companion GFLOP/W table's 1390 GFLOP/W peak is at 1400/+350, which was never
sweep-validated and sits between two failures (+325 corrupted, +375 faulted). The 1376 GFLOP/W
cell at 1350/+300 is in the same category: a single completed run, never gated by a pattern
sweep. The same 1350 ladder also contains 1350/+400, which passed two sweeps and then returned
`mem_errors=1` on a later one. The highest **sweep-validated** efficiency point is the shipped
`eff` profile: **1366 GFLOP/W at +250 / 1350 MHz** (180.3 TFLOPS, 132.0 W). Efficiency at a 1650
ceiling runs 1067 GFLOP/W at +250 to about 1149 GFLOP/W at +350; higher figures there come only
from offsets that faulted. The `eff` profile is the shipped default because it gives up 2% of
throughput for a third of the power.

### The voltage floor

At a 1350 MHz ceiling, everything above +250 draws the same power, so the correct choice is the
**lowest** offset that reaches the floor:

| Offset | +150 | +200 | +250 | +300 | +350 | +400 | +450 |
|---|---|---|---|---|---|---|---|
| Draw | 146.0 W | 140.9 W | **132.4 W** | 131.3 W | 132.1 W | 131.5 W | 132.5 W |

No better floor point exists between 1350 and 1400 MHz: `+400/1380` and `+375/1395` both fault
on the first run. This SKU reports no voltage telemetry at all (`nvidia-smi -q -d VOLTAGE` is
empty), so watts-at-fixed-clock is the only available proxy for voltage.

### Fault and hang boundaries

Same reference card. **+350 is the highest validated offset at a 1650 MHz ceiling.** The safe
offset is ceiling-dependent: at a 1400 MHz ceiling the highest validated offset is **+300**,
because 1400/+325 silently corrupts.

| Clock ceiling | Offset | TFLOPS | Power | Outcome |
|---|---|---|---|---|
| 1650 | +350 | 214.7 | 187 W | clean, 2 sweeps plus a selftest PASS (highest validated) |
| 1650 | +355 | 215.0 | 183 W | faulted by the third run, `illegal instruction` |
| 1650 | +360 | 217.3 | 182 W | fault |
| 1650 | +375 | 219.3 | 182 W | best single result on the card, then fault plus 1 memory error on the next sweep |
| 1650 | +400 | 210.7 | 179 W | clean but **slower** |
| 1590 | +400 | n/a | n/a | HANG |
| 1700 | +375 | n/a | n/a | HANG, "GPU requires reset", power cycle needed |
| any | +450 | n/a | n/a | hard crash; a warm reboot is not always sufficient |

Fault strings observed: `illegal instruction`, `illegal memory access`, `misaligned address`,
`cublas 14`.

**Why +400 can benchmark slower than +375:** Ampere's NAFLL has droop detection and stretches
the clock when voltage is inadequate. At +400 the requested VF point is far enough past the
curve that the stretcher engages continuously, so the clock *reads* 1650 MHz while delivered
work drops about 4% below +375. Between roughly +355 and +390 the part runs at the full
requested speed with too little margin, and that is exactly where the intermittent faults live.
**A higher offset that benchmarks slower is a warning sign, not a win.**

### Qualification ladder

Per-card silicon varies enough that a validated offset on one card must not be assumed on
another. The documented procedure:

1. Run `sudo nvml_oc` and confirm the GPC range is **not** `[0..0]`. (This doubles as the
   quickest test that a card is actually unlocked.)
2. `sudo 170hx-oc stock`, then `sudo oc_eff 10` for a baseline.
3. Ladder +150 to +300 with `oc_eff` at each step.
4. At the candidate point run the full-VRAM memory sweep and compute checksum
   (`170hx-test.sh --no-unlock`).
5. Stop at the first device fault and back off **one full step, not one bin**.
6. Record results per card.

### Real-workload gain

Overclocking buys far less on real workloads than on GEMM microbenchmarks. llama.cpp with MTP on
short chats:

| Model | Setting | Decode | Power | Core clock |
|---|---|---|---|---|
| Qwen3.6-35B-A3B-UD-Q8_K_XL | stock | 130 t/s | 170 W | 1445 MHz |
| Qwen3.6-35B-A3B-UD-Q8_K_XL | +200 offset | 144 t/s | 185 W | 1650 MHz |
| Qwen3.6-27B-UD-Q8_K_XL | stock | 55 t/s | 268 W | 1390 MHz |
| Qwen3.6-27B-UD-Q8_K_XL | +200 offset | 59 t/s | 287 W | 1565 MHz |

That is a **7-11% token-generation gain**. A second tester independently reported +200 MHz as
their own stable maximum.

### The 8 GB card overclocks; the 10 GB card does not

| Step | Clock | FP32 |
|---|---|---|
| session start | 1410 MHz | 12.08 TF/s |
| `nvidia-smi -pl 300` | 1470 MHz | 12.99 TF/s |
| offset +60 | 1515 MHz | 13.40 TF/s |
| offset +225 | 1695 MHz | **14.97 TF/s (+24%)** |

This works on the 8 GB part because VBIOS entries `0x47177` / `0x47179` hold
`freqDelta = +/-1000` there. Both read 0 on the A100 and on the CMP 10 GB. See
[vbios.md](../hardware/vbios.md).

---

## Power limits

| Quantity | Value | Source |
|---|---|---|
| Default / Current / Requested power limit | 250.00 W | `nvidia-smi -q`, unlocked card, driver 610.43.02 |
| Min power limit | 100.00 W | same capture |
| Max power limit, stock CMP VBIOS | **250.00 W** | same capture |
| Max power limit, NVIDIA 300 W "OC mining" VBIOS | **300 W** | `POW 278 / 300 W` observed under a 30-minute `gpu_burn` |
| Slot power limit (DevCap) | 75 W | the card needs its EPS connector |
| Power connector | 1 x EPS 8-pin (300 W rated), needs a 2 x PCIe-to-EPS adapter | see [power-and-psu.md](power-and-psu.md) |

So on stock firmware `nvidia-smi -pl` can only **lower** the card, between 100 W and 250 W.
There is no headroom above stock without the OC VBIOS, and that VBIOS is an 8 GB-card story:
after the memory unlock, 10 GB cards were confirmed to still carry the core-clock-offset lock
and the memory-clock lock, pinned at 1215 MHz. Nobody in the archive verified a 300 W VBIOS
combined with the unlock on a 10 GB card.

```bash
nvidia-smi -pl 160          # works; documented uses span 100/150/160/175/200/250 (and 300 on the OC VBIOS)
nvidia-smi -q -d POWER      # confirm Current / Min / Max / Default
```

The recurring assertion that "there is no way to power limit these cards" is **wrong**.

### Does raising the limit help?

Barely. Measured against the same tester's own 250 W baseline on a card with the faster-memory
VBIOS and a large blower, going to 300 W moved BF16 from **~180 to 185 TFLOPS (about +2.8%)**,
and thermals were not the limiter (core and memory both below 65 C). The conclusion drawn was
that the core simply does not want to clock higher.

Going the other way is nearly free. Power-limiting to **150 W cost no measured throughput** in
raw throughput stress tests (single source, specific to that workload class), and the whole
`eff` profile above exists because the power curve is steeply diminishing. In hashcat DES an
overclock-VBIOS card gave 1800 MHash at 190 W against a stock card's 1700 MHash at 150 W: a
26.7% power increase for 5.9% more performance, so power grows roughly 4.5x faster than
performance. Silicon leakage rising with temperature makes the curve worse when hot.

### What the card actually draws

| Workload | Draw |
|---|---|
| Idle | 27-46 W depending on card, temperature and residency; ~42 W typical on a running rig |
| Idle with a model resident in VRAM | rises from about 33 W to about 45 W (a resident CUDA context raises clocks) |
| `gpu_burn` FP32 / FP64 | ~60 W |
| `gpu_burn` with tensor cores | ~75 W, spikes past 100 W |
| CUTLASS BF16 (shape-optimised) | 186 W peak on a locked card; `mmapeak` post-unlock only ~150 W at 1470 MHz |
| hashcat (pure integer) | 160+ W |
| STREAM-like memory benchmark | 160+ W |
| FluidX3D with FMA disabled, FP32/FP16S | 180 W |
| llama.cpp, steady | 230-240 W |
| Diffusion | 250-260+ W |
| `gpu_burn` at a 300 W limit | 278 / 300 W |

!!! warning "Do not validate cooling or stability with an FP32 burn-in"
    This card is hard to load. A conventional FP32 burn-in reaches only 60-75 W where an integer
    or memory benchmark reaches 160+ W. Validate with hashcat, a memory sweep, or `gpu_burn -tc`
    plus a real workload, not with FP32 alone.

**Cooling the card better lowers its idle power**, which is the benign half of the leakage
feedback loop and the most likely explanation for the 30 W-versus-44 W idle spread across
testers.

For rigs: 20 cards idling at ~30 W each is roughly 600-700 W just to sit there. A six-card
llama.cpp layer-split system drew about **600 W total**, far under 6 x 250 W, because layer and
pipeline split do not saturate all GPUs simultaneously. Host platform choice dominates: a
dual-socket Xeon 6200 with Optane PMem 200 and 1.2 TB of memory idled at 400-600 W, against
~200-250 W for a dual EPYC 7713 with 1 TB DDR4, 80 W for a single EPYC 7D12 system, and 30 W for
an EPYC 7261 with one DIMM.

---

## Persistence mode and making settings survive

Overclock and power settings are **volatile**: they must be reapplied at every boot and after
every driver reload. The reference deployment uses a systemd oneshot:

```ini
[Unit]
After=nvidia-persistenced.service gen2-hammer.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/170hx-oc eff
ExecStop=/usr/local/bin/170hx-oc stock
```

The applier guards on PCI device ID `0x20C2` and loops over every GPU, so a non-170HX in the
slot is skipped and logged rather than overclocked. A representative log line:

```text
170hx-oc: GPU 0 (…) profile=eff offset=+250 clk_max=1350 power_limit=300 W
```

Notes on `nvidia-persistenced` itself:

- The patched module sets `NV_FLAG_PERSISTENT_SW_STATE` for both device IDs
  (`0006-persistent-sw-state.patch`), so RM does not tear down software state when the last
  client closes. That is effectively built-in persistence and is why no daemon is required;
  `nvidia-smi -q` on a fresh card nonetheless reports `Persistence Mode: Disabled`.
- **The unlock scripts require all NVIDIA services to be stopped.** `build.sh` stops
  `nvidia-persistenced` as part of its hot reload. Tearing the driver down reliably means
  stopping the display manager and the persistence daemon, not just `modprobe -r`. See
  [troubleshooting.md](../procedures/troubleshooting.md).

!!! danger "Do not install `nvidia-pstated` as a systemd service on an unlocked host"
    The unlock scripts need every NVIDIA service killed, and the interaction with a pstate daemon
    is untested. If you want to experiment with it, run it from a launcher instead.

---

## Performance-state (pstate) management

**The 170HX exposes only P0.** `NvAPI_GPU_SetForcePstate` returns `NVAPI_ERROR`, and the
community fork of `nvidia-pstated` that works on 2-P-state cards (P100, V100) was tried on a
170HX and produced **no change**. The daemon's defaults, for reference, are
`iterationsBeforeSwitch = 30`, `performanceStateHigh = 16`, `performanceStateLow = 8`,
`sleepInterval = 100`, `temperatureThreshold = 80`.

This is card-specific, not a fault in the tool: `nvidia-pstated` took a **CMP 90HX from 75 W to
5 W** idle, working across a multi-GPU setup and persisting across reboot.

!!! note "Superseded: 'pstated will fix 170HX idle power'"
    It cannot. The documented fallback for single-P-state cards is **application-clock locking**
    (`nvidia-smi -i N -ac <mem,gpu>` to idle, `nvidia-smi -i N -acp` or `-rac` to restore),
    implemented through `nvmlDeviceSetApplicationsClocks` rather than NvAPI. A fork added
    `enableClockFallback` with `clockFreqMemHigh` / `clockFreqGpuHigh` / `clockFreqMemLow` /
    `clockFreqGpuLow`. Measured savings on other hardware: ~13 W on a V100S PCIe, 16-18 W per GPU
    on V100 SXM2 with llama.cpp holding a model. **This has not been demonstrated on the 170HX**,
    and its single memory-clock domain is the obvious obstacle. On bare-idle V100 SXM2 the GPU
    clock dropped from 1530 to 135 MHz with no measured power reduction at all.

!!! question "Open problem: one P-state or two?"
    One account says the 170HX has two P-states; every posted capture shows only a single
    default P0, which is why the NvAPI call fails. The practical consequence is the same either
    way. `nvidia-smi -q -d PERFORMANCE` listing the supported P-state set would settle it.

The one untried lead for idle power is flashing PCIe A100 logic, which does contain several
P-states. Nobody has attempted it, and VBIOS work on this card is signature-constrained; see
[vbios.md](../hardware/vbios.md).

---

## Memory allocation limits and practical usable VRAM

| Card | Stock | Unlocked | What tools report |
|---|---|---|---|
| 8 GB (`10de:20c2`) | 8192 MiB | **65536 MiB (64 GB)** | `nvidia-smi` 65536 MiB; `gpu_burn` "Initialized device 0 with 65052 MB of memory (64733 MB available, using 58259 MB of it)" |
| 10 GB (`10de:2082`) | 10240 MiB | **40960 MiB (40 GB)** | 40459 MB reported in one capture; a controlled run used 17464 MiB of 40960 MiB |
| 10 GB fired to 80 GB | n/a | reports ~81920 MiB / 79.7 GiB | **unusable above ~40 GB** |

Practical allocation guidance:

- Budget roughly **1 GB of the 64 GB for driver and context overhead**: the gpu_burn capture
  above shows 65052 MB total and 64733 MB available before the tool takes 90%.
- **vLLM**: the 8-card GLM-5.2 recipe uses `--gpu-memory-utilization 0.90` and achieved 0.92
  utilisation in practice, yielding 438,107 tokens of KV. Keep utilisation at or below 0.90:
  0.95 crashed a card, because the unlocked geometry exposes 65052 MB with only 64733 MB
  actually available, so headroom at 0.95 is thin. The recipe also sets
  `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0`.
- **llama.cpp**: observed steady-state residency on a 4-card rig was 53G/64G, 60G/64G, 60G/64G
  and 56G/64G, with a prompt cache of 8192.000 MiB / 65536 tokens.
- The RM models the whole unlocked range as **uniform-performance memory**
  (`supportCompressed = NV_TRUE`, `supportISO = NV_TRUE`, `performance = 20` on the extended
  region), so allocation policy cannot prefer the fast region even where one exists. The
  measured bandwidth step above an 8 GiB offset (98% of peak below, a flat 79% above, closing
  entirely at a 32 GB chunk size) is invisible to the allocator. See
  [performance.md](performance.md).
- Shipping `master` clamps the BAR0/PRAMIN window to 8 GiB for both device IDs
  (`0004-bar0-pramin-clamp.patch`). This is a CPU-side aperture, not a device-side allocation
  limit, but it is the reason PRAMIN-based tools see only the first 8 GiB.
- The installer's **profile auto-detection** reads `nvidia-smi --query-gpu=memory.total` and
  maps `>= 60000 MiB` to the 8 GB profile and `35000-59999 MiB` to the 10 GB profile, so an
  already-unlocked card re-detects correctly. Stock windows are 7680-8704 MiB and
  9728-10752 MiB, with a ±512 MiB tolerance for reserved FB.

!!! danger "The 80 GB geometry is not more VRAM, it is less"
    A 10 GB card fired to 80 GB reports ~81920 MiB and 85,545,582,592 bytes, and `cudaMalloc` of
    77 GiB even succeeds, but kernels touching more than roughly 40 GB cause fatal GPU loss,
    independent of power limit. Reported Xid codes include Xid 31 (described as harmless) and
    Xid 154 after CUDA memory tests; the dominant reported symptom is hangs. Xid 31 alone was
    suggested by a bystander and was not corroborated as *the* signature by the operator with the
    failing card. For one tester model loading hung after roughly 20 GB, while a second tester
    with multiple cards saw failures in the 40 to 60 GB band; either way models
    that previously fit the 40 GB unlock stopped loading. Physical DRAM is present (a PRAMIN
    walk proved 80 distinct GiB), and on this branch the wall behaves like address decode. A
    script-driven coherent register set does reach real memory past 40 GiB, but it is unshipped
    and delivers roughly one CUDA context per fire. **8 GB cards go to 64 GB;
    10 GB cards go to 40 GB.** See [80gb.md](../frontier/80gb.md) and
    [memory-geometry.md](../unlock/memory-geometry.md).

!!! warning "There is no ECC and no ECC telemetry"
    ECC is fused off with no known lever, so a marginal overclock has no error-counter safety
    net. That is precisely why the qualification ladder above gates on a full-VRAM pattern sweep
    with a compute checksum. See [ecc.md](../frontier/ecc.md).

---

## Workload tuning

### Build and launch flags that matter

| Setting | Value | Why |
|---|---|---|
| CUDA architecture | `-DCMAKE_CUDA_ARCHITECTURES=80` | compute capability 8.0 is GA100; SM86 also works but 80 is correct |
| Backend | vLLM where it supports your model | "~1.8x" llama.cpp, from one tester on Qwen3.6 27B, one card, quants not matched |
| Parallelism across cards | pipeline, never tensor | TP is 2.3-2.8x worse at prefill at Gen1 x4 |
| MTP | on for single-stream llama.cpp, off for vLLM on the 35B MoE | +21% on one backend, -23% on the other |
| Quantisation | q4-class is the practical sweet spot on a 64 GB card | bf16 Qwen3.6 27B is 54-56 GB and leaves no KV headroom |
| Model family | prefer MoE for multi-card | less cross-device activation traffic per token |

### Roofline guidance

For a **locked** card the 2023 selection rule still stands: the card is useful below
**0.3 FLOPs/byte** of arithmetic intensity with stock FMA, or below **4.6 FLOPs/byte** after
disabling FMA (ridge points from 394 and 6250 GFLOPS over a 1355 GB/s measured ceiling). After
the compute unlock FP32 rises by roughly 30x while bandwidth is unchanged, so the ridge moves
out by the same factor and the rule stops binding: an unlocked card behaves like an ordinary
memory-bound GA100 for most kernels. (That last sentence is a derivation from the two canonical
figures, not a separately measured result.)

### The cheapest untested tuning lead

On a CMP 100-210, setting `n_ubatch 56` raised llama.cpp pp512 from 353.59 to **977.20 t/s**
with flash attention off and from 380.96 to **1159.39 t/s** with it on, a **3.04x** gain from one
flag, while tg128 was essentially unchanged. Small further gains held up to uBatch 62, then
performance collapsed. That card has 68 of 84 SMs, so the analogous tuning point on a 70-SM
170HX would be just below 70.

!!! question "Open problem: does the uBatch cliff exist on the 170HX?"
    Nobody has run the sweep. `llama-bench` with `n_ubatch` from 48 to 80 on a compute-unlocked
    170HX is a single afternoon of work and is the largest untested upside in the archive.

### Validating a tuning point

```bash
# 1. compute stability and sustained flops
make COMPUTE=80                       # github.com/wilicc/gpu-burn
./gpu_burn -tc -m 90% 1200

# 2. memory integrity: the gate that catches silent corruption
./170hx-test.sh --no-unlock           # full-VRAM pattern sweep + compute checksum

# 3. link and geometry sanity
nvidia-smi --query-gpu=memory.total,clocks.max.sm,pcie.link.gen.current,pcie.link.gen.max --format=csv
```

A clean 30-minute `gpu_burn` at a 300 W limit on an unlocked 8 GB to 64 GB card looked like
this: 225 iterations, checkpoints holding **12,472-12,485 GFLOP/s** with `errors: 0`,
temperatures rising only 75 C to 77 C, live telemetry `PCIe GEN 1@ 4x`,
`GPU 1440MHz MEM 1890MHz TEMP 76C FAN N/A POW 278 / 300 W`,
`GPU 100% MEM 57.534Gi/64.000Gi`, finishing `Tested 1 GPUs: GPU 0: OK`.

Thermals are not usually the constraint: a sustained GEMM burn held flat flops while the die
went 62 to 73 C over roughly 25-30 seconds, and a full-capability part throttles only above
~85 C. What does matter is that idle power and leakage rise together, so better cooling pays
twice. See
[cooling.md](cooling.md) and [thermals.md](../hardware/thermals.md).

### Efficiency reference points

| Metric | Value | Conditions |
|---|---|---|
| Best measured GFLOPS/W | 1390 GFLOP/W | ceiling 1400 MHz, offset +350. **Never sweep-validated, and bracketed by 1400/+325 CORRUPT and 1400/+375 fault. Not an operating point.** |
| Second-best measured | 1376 GFLOP/W | ceiling 1350 MHz, offset +300. **A single completed run, never gated by a pattern sweep. Not an operating point.** |
| Best *sweep-validated* GFLOPS/W | 1366 GFLOP/W | `eff` (shipped default), +250 / 1350 MHz, 180.3 TFLOPS at 132.0 W; passed the full-VRAM pattern sweep with `mem_errors=0` at least twice |
| Stock | 925 GFLOP/W | 184.3 TFLOPS at 199.2 W |
| LLM serving | 2.16 tok/s per watt | vLLM, Qwen3.6 27B int8, one card |
| Memory overclock (reported) | +2.5% flops for about +5 C | no clock or p-state code exists in any archived branch, so this cannot be checked against code |

---

## What does not work, in one list

- Memory clock locking (`nvidia-smi -lmc`): refused by the driver.
- Memory VF offset: range is `[0 .. 0]`.
- Raising the power limit above 250 W on stock VBIOS: not offered.
- P-state forcing (`nvidia-pstated`, `NvAPI_GPU_SetForcePstate`): the card exposes only P0.
- Core-clock offset on the 10 GB card: `freqDelta` is 0 in its VBIOS.
- Offsets above the ceiling-specific validated maximum: faults, hangs, or silent corruption. That
  maximum is +350 at a 1650 MHz ceiling but only **+300** at a 1400 MHz ceiling.
- Gaming, at any tuning point: 15 fps in BeamNG.drive at Gen1 x16 with the capacitor mod, 5 fps
  at x4, "still awful" either way. This is not a gaming card.
- ECC as a safety net: fused off.

See [open-questions.md](../frontier/open-questions.md) and
[dead-ends.md](../history/dead-ends.md).
