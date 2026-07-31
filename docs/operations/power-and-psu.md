# Power and PSU

## What this page covers

Getting power into a CMP 170HX in practice: the connector and the adapter it needs, how big
a PSU to buy, what the card actually draws at idle and under load, how to power-limit it
with `nvidia-smi`, and what a power limit does and does not do for stability. The on-board
rails, VRM topology and phase-depopulation story are on
[Power delivery](../hardware/power-delivery.md).

Four things to know before you wire anything:

- The card has **one 8-pin EPS (CPU-style) socket**, not a PCIe 8-pin. It ships with a
  dual-8-pin-PCIe-to-EPS Y adapter. **Forcing a PCIe cable into it will damage the card.**
- `lspci` reports `SlotPowerLimit 75 W` in DevCap, so everything above 75 W arrives on that
  one connector.
- Stock firmware gives **250 W default = 250 W maximum, 100 W minimum**. There is no
  headroom above stock. Only the NVIDIA-issued 300 W "OC mining" VBIOS raises the ceiling.
- `nvidia-smi -pl` **works fine** on this card. The recurring claim that "there is no way to
  power limit these cards" is wrong.

---

## The connector

| Property | Value |
|---|---|
| Physical connector | 1 x 8-pin EPS (CPU-style) |
| Logical rails behind it | **two** separate 12 V inputs, `12V_EXT1` and `12V_EXT2`, combined into one socket |
| EPS 8-pin rating | 300 W |
| PCIe 8-pin rating | 150 W |
| Supplied adapter | dual 8-pin PCIe to 8-pin EPS Y adapter, in the box |
| Per-pin capability | roughly 70-80 W per good-quality pin |
| PCIe slot contribution | `SlotPowerLimit 75 W` (DevCap) |

> [!CAUTION]
> **Never plug a PCIe 8-pin cable into the card's EPS socket**
>
> The two connectors are keyed differently and can only be forced together. **If forced, the
> 12 V and ground lines are swapped on some pins between the two connector types and the card
> will be damaged.** Use the supplied 2 x PCIe-to-EPS adapter, or a proper EPS cable for your
> PSU. Practical guidance from
> builders: at 150 W use one leg of the supplied adapter, at 300 W use both legs or source
> proper cables.

> [!CAUTION]
> **Do not reuse a modular PSU cable across PSU brands**
>
> Modular cables are vendor-specific with no standard modular-side pinout. Reusing one
> across brands can destroy hardware. A modular EPS12V cable must carry 4 x 12 V and
> 4 x GND on **both** ends.

Two mechanical gotchas reported first-hand:

- Most PSU-integrated EPS cables have **oversized retention clips that physically will not
  fit** the card's socket. This is the usual reason people fall back to the PCIe-to-EPS
  adapter even when their PSU has a spare EPS output.
- The supplied adapter expects **two** PCIe 8-pin (6+2) feeds. At least one build failed
  because the PSU provided 1 x PCIe 6+2 and 1 x 6-pin instead of two 6+2 connectors. Count
  your PSU's actual PCIe connectors before ordering cards.

Note also that several 3D-printed shrouds **block access to the EPS plug**. Test-fit with the
cable installed. See [Cooling](cooling.md).

---

## PSU sizing

| Build | Guidance | Basis |
|---|---|---|
| Two cards at 150 W each plus a mid-range desktop CPU | **~600 W on the 12 V rail** minimum (two cards plus a Ryzen 5 3600 estimated at about 400 W total) | connector ratings plus builder consensus |
| Five cards at 250 W each (~1250 W of GPU load) | **1600-2000 W** | builder consensus |
| Any build | budget **75 W of the card's draw to the slot** and the rest to the EPS connector | `lspci` DevCap |

Size against your intended power limit, not against 250 W, if you are going to run
`-pl 160` or `-pl 200`: the throughput cost is small (see below) and it changes the PSU
class you need for a dense rig.

For multi-card rigs, budget idle as well as load. Twenty cards sitting at about 30 W each is
roughly **600-700 W just to exist**, on the order of $1000/yr at average US electricity
prices. A six-card llama.cpp layer-split system drew about **600 W total**, far under
6 x 250 W, because a pipeline split does not saturate every GPU simultaneously.

Host platform choice can dominate the whole rig's idle figure. Measured contrast points:

| Host | Idle |
|---|---|
| Dual Intel Xeon 6200 + Optane PMem 200, 1.2 TB | **400-600 W**, even with low P-states |
| Dual EPYC 7713 + 1 TB DDR4 | ~200-250 W |
| Single EPYC 7D12, whole system | 80 W |
| EPYC 7261 with one 8 GB stick | 30 W |

---

## Measured idle draw

Idle sits at **27-46 W** and is strongly temperature- and residency-dependent.

| Card / condition | Idle draw |
|---|---|
| 10 GB card | **27 W** (attributed to the lower memory clock) |
| Stock card, 2023 review | ~30 W |
| 8 GB card, second owner | 30-35 W |
| 8 GB card, measured beside the 10 GB card | **33 W** |
| Three unlocked 40 GB cards, `nvtop` | 34 / 33 / 36 W |
| Locked 8 GB card in a cold room, 29 C | 37 W |
| Unlocked 10 GB card, `nvidia-smi -q` instantaneous | **37.51 W** |
| 8 GB card, one owner | 44 W |
| Unlocked card in P0 at 61-62 C | 44 W |
| Any card with an LLM held resident in VRAM | **~33 W rises to ~45 W** |

Three confounders explain the spread, and they have never been varied one at a time:

1. **Variant.** The 8 GB card reads higher than the 10 GB card, attributed to memory clock.
2. **Die temperature.** Leakage rises with temperature, so a cooler card genuinely idles
   lower. See [Thermals](../hardware/thermals.md).
3. **Resident CUDA context.** Holding a model in VRAM raises core clocks and costs roughly
   +12 W, enough to spin system fans up.

> [!NOTE]
> **Open problem: nobody has isolated the idle-power variables**
>
> What would settle it: one card, one host, `nvidia-smi` idle draw logged at three
> controlled die temperatures, with and without a resident CUDA context.

### There is no idle P-state, and no tool fixes that

- The card exposes only **P0** in every capture, and `NvAPI_GPU_SetForcePstate` returns
  `NVAPI_ERROR` on single-P0 cards.
- `nvidia-pstated` **does not help the 170HX**. The community fork that works on 2-P-state
  cards (P100, V100) was tried and produced no change. The same daemon takes a CMP 90HX from
  **75 W to 5 W**, which is why expectations were high.
- The application-clock fallback (`nvidia-smi -i N -ac <mem,gpu>`, restored with `-rac`,
  implemented via `nvmlDeviceSetApplicationsClocks` rather than NvAPI) saves 13 W on a
  V100S and 16-18 W per GPU on V100 SXM2, but **has never been demonstrated on the 170HX**.
  Its single memory-clock domain is the obvious obstacle: on the 170HX there is exactly one
  supported memory clock to select.
- The core clock floor is 210 MHz and the memory clock is effectively fixed, which is the stated
  reason idle power stays high. The 10 GB figure is 1215 MHz; the 8 GB figure is unresolved (see
  below).

> [!NOTE]
> **Open problem: the stock 8 GB memory clock is unresolved**
>
> The stock 8 GB memory clock is unresolved: 1458 MHz (one sweep and TechPowerUp), 1728 MHz
> (`nvidia-smi -q` Supported Clocks, noted as "432 MHz x 4"), 1890 MHz (`nvtop` during an
> unlocked 64 GB `gpu_burn` at 300 W). 1215 MHz is the 10 GB card and is solid. The plausible
> reconciliation (1458 stock, 1728 OC VBIOS, 1890 overclocked OC VBIOS) is unproven; a raw
> FBPA PLL read would settle it.

> [!CAUTION]
> **Do not install `nvidia-pstated` as a systemd service on an unlocked 170HX host**
>
> The unlock scripts require all NVIDIA services to be killed, and the interaction with a
> resident pstate daemon is untested. Run it from a launcher instead, if you run it at
> all.

> [!NOTE]
> **Open problem: would an A100 PCIe VBIOS expose more P-states?**
>
> This is the one untried lead after `nvidia-pstated` and the clock-fallback fork both
> failed: "the pci-e a100 bios has several p-states so I'm fairly certain p-stated would
> work on that". The PCIe A100 is documented with several performance states and a claimed
> 5 W idle. Nobody has attempted the flash. It should only be tried on a spare card with a
> hardware programmer available for recovery (GPU EEPROMs are 1.8 V, so a CH341A needs a
> 1.8 V adapter).

---

## Measured load draw

**The card is hard to load.** Draw by workload, on stock firmware unless noted:

| Workload | Draw |
|---|---|
| `gpu_burn`, FP32 and FP64 | **~60 W** |
| `gpu_burn` with Tensor Cores | ~75 W, spikes to 100+ W |
| The failing 80 GB LLM workload | never above ~80 W |
| `mmapeak` at 1470 MHz, power limit set to 300 W | ~150 W, `PerfCap: None` |
| Hashcat (pure integer) | 160+ W |
| Self-written STREAM-like memory benchmark | 160+ W |
| FluidX3D with FMA disabled, FP32/FP16S | 180 W |
| CUTLASS BF16, shape-optimised, locked 8 GB card | 186 W peak |
| Sustained 100% load at the stock cap | **208 W at 61 C** |
| llama.cpp inference | **230-240 W** steady (29 tok/s reported by that tester) |
| Diffusion workloads | 250-260+ W |
| Peak field draw on stock air | 254 W at 60 C (8-card rental) |
| 30-minute `gpu_burn` at a 300 W limit, unlocked 64 GB | **278 / 300 W** |

> [!WARNING]
> **Never validate stability or cooling with a conventional FP32 burn-in**
>
> A healthy 170HX legitimately reports **under 75 W** in an FP32 stress test, because so
> much of the die is fused off and FP32 throughput is what the CMP lockdown targeted. Use
> an **integer or memory** benchmark, or a real inference workload, to load the card. In
> 2023 this exact behaviour was misread as a hardware fault before an independent AIDA64
> run on a separate card on Windows showed the same low draw: the FP32 lockdown is the
> cause and the low power is the effect.

The cleanest full-envelope evidence is a 30-minute `gpu_burn` on an unlocked 8 GB card at a
300 W limit:

```text
Initialized device 0 with 65052 MB of memory (64733 MB available, using 58259 MB of it), using FLOATS
...
225 iterations, checkpoints holding 12,472-12,485 GFLOP/s, errors: 0
Tested 1 GPUs:
        GPU 0: OK
```

with live telemetry `GPU 1440MHz MEM 1890MHz TEMP 76C FAN N/A POW 278 / 300 W`, temperatures
rising only from 75 C to 77 C over the half hour.

---

## Power limiting with `nvidia-smi`

```bash
# Read the whole power block
nvidia-smi -q -d POWER

# Set a limit (watts). Requires root. Applies to the running driver, not persistently.
sudo nvidia-smi -pl 200

# Multi-card: target one device
sudo nvidia-smi -i 0 -pl 160

# Log draw and clocks while you validate
nvidia-smi --query-gpu=power.draw,power.limit,clocks.sm,temperature.gpu \
  --format=csv -l 1
```

Verbatim from `nvidia-smi -q` on an unlocked 10 GB card, driver `610.43.02`:

| Field | Value |
|---|---|
| Instantaneous Power Draw | 37.51 W |
| Current Power Limit | 250.00 W |
| Requested Power Limit | 250.00 W |
| Default Power Limit | 250.00 W |
| **Min Power Limit** | **100.00 W** |
| **Max Power Limit** | **250.00 W** |
| Average Power Draw | N/A |

So on stock firmware `-pl` can only **lower** the card, between 100 W and 250 W. Values
confirmed working across many testers: `-pl 100`, `-pl 150`, `-pl 160`, `-pl 175`,
`-pl 200`, `-pl 250`, and `-pl 300` on cards carrying the OC VBIOS.

### Two ceilings, depending on VBIOS

| VBIOS | Max power limit | Extras |
|---|---|---|
| Stock CMP | **250 W** | none |
| NVIDIA 300 W "OC mining" | **300 W** | also raises the memory clock and permits a core-clock offset |

The 300 W ceiling is real on cards that carry that VBIOS: a 30-minute `gpu_burn` logged
`POW 278 / 300 W`. This resolves the apparent contradiction between the driver reporting a
250 W maximum and the many `-pl 300` reports in circulation.

> [!WARNING]
> **Experimental: the 300 W VBIOS on a 10 GB card**
>
> The 300 W OC VBIOS applies to the **8 GB** card. After the memory unlock, 10 GB cards
> were confirmed to still have both the core-clock-offset lock and the memory-clock lock
> in place, pinned at 1215 MHz. A separate 300 W VBIOS recommendation for 10 GB cards
> circulates, and one owner acquired cards on an unverified compatibility claim, but
> **nobody in this corpus has verified a 300 W VBIOS combined with the
> unlock on a 10 GB card.** Note that the unlocker itself contains no power-management
> code at all, so the only risk surface is the flash. See [VBIOS](../hardware/vbios.md).

---

## Power limit and stability

This is the section people come for, and the answer is counter-intuitive: **on this card
the power limit is almost never the binding constraint, and lowering it almost never fixes
anything.**

### Raising the limit buys almost nothing

Measured against the same tester's own 250 W baseline, on a card with the faster-memory
VBIOS and a large blower:

| Power limit | BF16 throughput | Temperature |
|---|---|---|
| 250 W | ~180 TFLOPS | core and memory below 65 C |
| 300 W | **185 TFLOPS (+2.8%)** | core and memory below 65 C |

Thermals were not the limiter in either case. The conclusion drawn was that the core simply
does not want to clock higher.

The power/performance curve is steeply diminishing at the other end too. In Hashcat DES
cracking, an OC-VBIOS card gave 1800 MHash at 190 W while a stock card gave 1700 MHash at
150 W: **+26.7% power for +5.9% performance**, i.e. power grows roughly 4.5 times faster
than performance. The tester disclosed the confound openly (two physically different cards,
so silicon variance is uncontrolled, and the workload is mostly compute-bound).

### Lowering the limit costs surprisingly little

One tester found **no measured throughput loss at `-pl 150`** in raw throughput stress
tests, with the hypothesis that so much of the die is disabled that the stock limit never
binds. Single source, and specific to throughput stress tests, so treat it as indicative.

The systematic clock-ceiling by clock-offset sweep is the better guide. Its efficiency peak
is far below the stock envelope:

| Configuration | BF16 | Power | Efficiency |
|---|---|---|---|
| ceiling 1650, offset +350 | 214.7 TFLOPS | 187 W | about 1149 GFLOP/W (1067 at +250) |
| ceiling 1740, offset +350 | 213.8 TFLOPS | 188 W | not reported separately |
| ceiling 1470, offset +350 | 196.1 TFLOPS | 149 W | not reported separately |
| **ceiling 1400, offset +350** | 186.7 TFLOPS | **134 W** | **1390 GFLOP/W (peak)** |
| ceiling 1400, offset +0 | 186.7 TFLOPS | 198 W | not reported separately |
| ceiling 1350, offset +300 | 180.7 TFLOPS | 131.3 W | 1376 GFLOP/W |

Note the two 1400-ceiling rows: **identical throughput, 64 W apart.** The offset, not the
power limit, is where the efficiency lives. Efficiency at a 1650 ceiling runs 1067 GFLOP/W at
+250 to about 1149 GFLOP/W at +350; higher figures at that ceiling come only from offsets that
faulted (1650/+375 reads 1205 GFLOP/W but took a device fault). See [Tuning](tuning.md) for the
full sweep.

> [!CAUTION]
> **The 1390 GFLOP/W peak is not an operating point**
>
> The 1400/+350 row above is a single efficiency reading that was never gated on a full-VRAM
> pattern sweep, and it sits between two recorded failures at the same ceiling: **1400/+325
> silently corrupted memory** (6 errors, then 3, then 0 across three sweeps) and **1400/+375
> took a CUDA device fault**. This card has no ECC and no error telemetry, so a run that
> completes is not evidence the setting was safe. The highest validated offset at a 1400 MHz
> ceiling is **+300** (138.5 W, 4 sweeps, 0 errors).

### What actually breaks: clock offset, not power

Faults and data corruption begin above the highest validated offset **for the ceiling in use**:
above +300 at a 1400 MHz ceiling, above +350 at a 1650 MHz ceiling, independently of the power
limit:

| Configuration | Failure |
|---|---|
| 1350 / +400 | corrupt |
| 1400 / +325 | CORRUPT |
| 1400 / +375 | fault |
| 1590 / +400 | HANG |
| 1650 / +355, +360, +375 | fault |
| 1700 / +375 | HANG |

### Power limiting does not fix the 80 GB configuration

The same evidence retired the theory that the depopulated VRM causes 80 GB instability: the
8 GB card has identical power delivery and is entirely stable at 64 GB. See
[Power delivery](../hardware/power-delivery.md).

---

## Recommended operating points

| Goal | Setting | Why |
|---|---|---|
| Best efficiency | 1400 MHz ceiling, +250 to +300 MHz offset (138.5 W at +300) | sweep-clean at 3-4 sweeps, 0 errors. The 1390 GFLOP/W peak sits at +350, an untested cell bracketed by 1400/+325 CORRUPT and 1400/+375 fault. Do not run it. |
| Safe default for a mixed rig | `-pl 200` | comfortably cooled by an 80 mm server fan at 3500 RPM. Note that one tester measured llama.cpp at 230-240 W steady while another saw only 206-225 W peaks, so this limit will bind on dense inference on some cards |
| Dense multi-card | `-pl 160` | 4 cards held under 65 C on two 120 mm fans |
| Maximum throughput | stock 250 W, or 300 W on the OC VBIOS | +2.8% for +20% power; rarely worth it |
| Never | offsets above the validated maximum **for your ceiling**: +300 at a 1400 MHz ceiling, +350 at a 1650 MHz ceiling | corruption and hangs, documented per cell above. There is no ECC and no error telemetry, so a completed run is not evidence of safety |

---

## See also

- [Power delivery](../hardware/power-delivery.md): the rails, the VRM, and why repopulating
  phases does not raise the ceiling.
- [Thermals](../hardware/thermals.md): limits, sensors, leakage runaway.
- [Cooling](cooling.md): what removes how many watts, measured.
- [Tuning](tuning.md): the clock ceiling and offset sweep in full.
- [Performance](performance.md): throughput figures in context.
- [VBIOS](../hardware/vbios.md): the stock and 300 W OC firmware images.
