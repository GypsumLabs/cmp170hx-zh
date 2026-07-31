# Thermal design

## What this page covers

The CMP 170HX's cooler, the temperatures the silicon will tolerate, the sensors the driver
exposes, and every measured temperature in the corpus. This is the reference page: for
choosing an actual fan or waterblock, see [Cooling](../operations/cooling.md). For the
power side of the same problem, see [Power and PSU](../operations/power-and-psu.md) and
[Power delivery](power-delivery.md).

Two facts frame everything else. First, **the cooler is fully passive**: a bare heatsink
with no fan and no fan header the driver can see, designed for the forced air of a 1U/2U
server chassis. `nvidia-smi` reports `Fan Speed : N/A` in every capture ever posted, so the
card will never spin anything up on its own and will happily cook itself in a quiet desktop
case. Second, **the card is hard to load**: a conventional FP32 burn-in draws only about
60 W on a 250 W part, so a cooler validated that way is not validated at all.

The unlock is irrelevant here. A keyword sweep of the shipping unlocker and all 12
unreleased branches for `thermal`, `pstate`, `power_limit`, `vid_pwm`, `clkdomain`,
`freqDelta`, `0x20340`, `MHz` and `watt` returns nothing in any patch, script or config.
Every thermal characteristic below is a property of the stock board and stock VBIOS.

---

## The physical cooler

| Property | Value | Basis |
|---|---|---|
| Cooler type | Fully passive bare heatsink, no fan, no shroud fan | direct observation |
| Slot width | Dual-slot, approximately 40 mm / 1.57 in thick | measured by owners fitting brackets, medium confidence |
| PCB length | 27 cm bare; 29 cm including I/O shield and a plugged-in EPS connector | direct measurement |
| Clearance above the PCIe edge connector | roughly 5-6 mm (1/4 in) | measured, medium confidence |
| Heatsink bolt pattern around the die | 57 x 68 mm centre-to-centre (68 mm vertical, 57 mm horizontal) | direct measurement |
| Die package | approximately 55 x 55 mm; die itself 826 mm² | measurement plus die database |
| Fasteners | Torx T10 and T15 | teardown |
| Thermal interface, main areas | 1.5 mm soft pad | one owner with the card open and a photo; a second guessed 2 mm without confidence |
| Thermal interface, inductors | 3 mm soft pad | same source |
| Thermal interface, die | liquid thermal compound / liquid thermal pad | same source |
| Published CFM, static pressure, dBA, fin pitch | **none exist** | no vendor or teardown figure in any source |

The 40 mm slot width matters for bracket shopping: A100/H100-style 40 mm blower brackets
advertised for A100, H100, A20, A30, A40 and CMP 170HX measure 1.57 in wide and therefore
fit standard 2-slot spacing.

> [!NOTE]
> **Open problem: nobody has measured this heatsink**
>
> No CFM, static-pressure, dBA or fin-pitch figure for the stock 170HX heatsink is
> published anywhere in this corpus. Every airflow number in this wiki is a community
> measurement of a fan-plus-card system, not a heatsink specification. The closest thing
> to an anchor is the two-120 mm-fans-for-four-cards result at `-pl 160`. Closing this
> needs one person with a known fan curve correlating fan operating point against
> steady-state die temperature at a fixed power limit.

---

## Thermal limits

The first four come straight out of the driver on an unlocked 10 GB card (driver
`610.43.02`, captured 2026-07-25 at 18:32, P0, 18% utilisation). The last two rows are
community observations, not driver-reported.

| Limit | Value | Layer |
|---|---|---|
| GPU Shutdown Temp | **98 C** | hardware, driver-reported |
| GPU Slowdown Temp | **95 C** | hardware slowdown, driver-reported |
| GPU Max Operating Temp | **85 C** | driver-reported operating ceiling |
| Memory Max Operating Temp | **95 C** | driver-reported, HBM |
| Reported throttle onset | **~80 C** | a single unsourced reading, no telemetry posted, low confidence |
| GA100 memory throttle (recalled) | ~85 C, "not on all bios" | two hedged recollections, low confidence |

At that capture the card read GPU 34 C, memory 48 C, `Fan Speed : N/A`, and every clocks
event reason `Not Active`, including HW Thermal Slowdown and HW Power Brake Slowdown, with
every event counter at `0 us`.

> [!NOTE]
> **Open problem: the throttle layering is inferred, not established**
>
> Four numbers are on the record for "when does it throttle": 80 C (one tester's own
> telemetry), 85 C (two GA100 recollections and the driver's Max Operating Temp), 95 C
> (driver Slowdown Temp) and "above 100 C" (described for a card whose cooling failed
> entirely). These may all be true at different layers: a soft VBIOS-level clock
> reduction at 80 C, a driver operating ceiling at 85 C, a hardware slowdown at 95 C,
> and runaway when there is no cooling loop at all. **No one has posted a throttle log
> correlating clock reduction against temperature.** What would settle it is a logged
> sweep through 75-95 C of `nvidia-smi
> --query-gpu=temperature.gpu,clocks.sm,clocks_throttle_reasons.active --format=csv -l 1`.

### The community design target

Independently of the driver limits, testers converged on **70 C core and 75-76 C memory
hotspot under load** as the design target for a cooling solution. 90 C hotspot is treated as
unacceptable and was the basis for rejecting a single 40 mm fan. In the exchange that settled
this, a participant shopping for fans asked whether 90 C was acceptable for the chip, then
reported reading that throttling starts at 80 C, and was answered "Absolutely not!". No
telemetry was posted alongside the 80 C figure, so treat it as a reading rather than a
measurement.

---

## Sensors and telemetry

The card exposes GPU temperature and memory temperature, and nothing else thermal. There is
no fan tachometer, no per-stack HBM sensor, no exposed VRM or hotspot-delta sensor, and no
`nvidia-settings` fan control path because there is no fan.

```bash
# Static limits and the current reading
nvidia-smi -q -d TEMPERATURE

# Continuous log, one row per second, suitable for finding the real throttle point
nvidia-smi --query-gpu=timestamp,temperature.gpu,temperature.memory,clocks.sm,\
clocks.mem,power.draw,clocks_throttle_reasons.active --format=csv -l 1
```

Fields confirmed present on the 170HX:

| Field | Confirmed value in a real capture |
|---|---|
| `GPU Current Temp` | `34 C` (idle, unlocked 10 GB) |
| `GPU Shutdown Temp` | `98 C` |
| `GPU Slowdown Temp` | `95 C` |
| `GPU Max Operating Temp` | `85 C` |
| `Memory Current Temp` | `48 C` (idle) |
| `Memory Max Operating Temp` | `95 C` |
| `Fan Speed` | `N/A` on every capture ever posted |
| Clocks Event Reasons | all `Not Active` at idle; all counters `0 us` |

`nvtop` reports the same sensors in one line, and is what most testers pasted:

```text
GPU 1440MHz MEM 1890MHz TEMP 76C FAN N/A POW 278 / 300 W
PCIe GEN 1@ 4x
GPU 100%  MEM 57.534Gi/64.000Gi
```

A practical note from a tester building a fan curve: driving the curve from the reported
**hotspot** sensor makes the controller hunt, and **die temperature is the better control
input**.

---

## Leakage feedback and thermal runaway

GA100 exhibits a genuine leakage-driven positive feedback loop. Higher junction temperature
means higher CMOS leakage current, which means more heat, which means more leakage.

The cleanest measurement of it was taken by accident. One researcher dry-ran a card with a
waterblock fitted but no coolant in it: idle draw started at about **40 W**, climbed to
**60 W at 80 C**, and was still rising when the card was powered off.

> [!CAUTION]
> **Never power a card with a mounted-but-dry waterblock for more than 5 minutes**
>
> A dry block is worse than no block: it insulates. The measured 40 W to 60 W climb had
> not stabilised at 80 C. If you must dry-fit to check clearances, power off within
> 5 minutes.

Two consequences follow, one benign and one not:

- **Benign:** cooling the card better lowers its idle power, because it suppresses the
  leakage term as well as removing heat. This is the most likely explanation for the 30 W
  versus 44 W idle spread between testers.
- **Not benign:** if cooling fails outright, GA100 does not settle at its throttle point.
  One account from hands-on A100-class experience: "The thermal throttling runs at such a
  high power that if the cooling fails, it'll thermally throttle, but to a temperature above
  100 degrees, that then consumes more power, thus increased temperature... and you end up
  with a volcano." The exact temperature is BIOS-dependent and was disputed in the same
  exchange, so treat the shape of the curve as established and the number as not.

---

## Measured temperatures

Every temperature in the corpus, on a 170HX unless the row says otherwise. "Proxy card"
rows are A100 or MI100 results included because the A100 40 GB shares the PCB and cooler.

### Idle

| Cooling | Temperature | Conditions | Confidence |
|---|---|---|---|
| 360 mm radiator, fan and pump at minimum | **30 C** @ 30 W | Bykski N-TESLA-A100-X-V2 | high |
| 1 x Arctic P12 Pro PST 120 mm @ 1000 RPM, feeding 2 cards | **32 C** @ ~34 W each | printed shroud, taped for static pressure | high |
| Unstated (driver capture) | **34 C** GPU / **48 C** memory | unlocked 10 GB, P0, 18% util | high |
| 1 x 140 mm Noctua NF-A14 industrialPPC, 3 cards | **~38 C** | repurposed P100 shroud, wattage-driven curve | high |
| Unstated, cold room | **29 C** @ 37 W | locked 8 GB, driver `580.159.04` | high |
| Unstated, 3 unlocked 40 GB cards | **44 / 45 / 41 C** | `nvtop`, 210 MHz core / 1215 MHz memory | high |
| Unstated, during MIG testing | **61-62 C** @ 44 W in P0 | 250 W cap | high |
| A100 proxy, 2 x 120 mm case fans at maximum | 64 C | before shroud fitted | medium |
| A100 proxy, 9733S blower + printed shroud | 36 C | after shroud fitted | medium |

### Under load

| Cooling | Temperature | Load | Confidence |
|---|---|---|---|
| 360 mm radiator, fan and pump at minimum | **45 C** after 30 min | 180 W, FluidX3D FP32/FP16S, FMA disabled | high |
| Budget generic full-cover waterblock | **48 C core / 58 C memory** | 1 h stress test, 8 GB card, in service about a year | medium |
| A100 proxy, 9733S blower + printed shroud | 40-50 C | LLM load, down from 80+ C on 2 x 120 mm case fans | medium |
| Stock passive heatsink, datacenter chassis (80 mm fans) | **60 C** peak | 254 W, 8-card rental | medium |
| Two-fan printed shroud shipped with a card | never above 60 C | under half fan speed, card not yet unlocked, workload never stated | medium |
| Unstated | **61 C** @ 208 W | sustained 100% load at the stock 250 W cap | high |
| San Ace B97 1.85 A + USB controller, curve capped at 66% | **below 65 C** | 250 W sustained | medium |
| 2 x Arctic P12 Pro PST CO 120 mm in ducts, feeding 4 cards | **under 65 C** | `-pl 160` per card | medium |
| Large blower, 300 W A/B test | core and memory **both below 65 C** | BF16 at 300 W | high |
| 80 mm 10k-RPM server fan @ 3500 RPM | **under 70 C core / 75 C memory** | `-pl 200` | medium |
| 80 mm server fan @ 7500 RPM | **70 C core / 75 C memory** | full 300 W with an overclock | high |
| Cooling unstated | **~70 C ±2** | default clocks; same owner and same card as the 300 W row below | high |
| 2 x Arctic S4028-15K 40 mm @ 15000 RPM, custom 2-slot bracket | **never above 70 C GPU / 76 C hotspot** | heavy load, curve 100% at 70 C | high |
| 1 x 120 mm @ 3000 RPM, ducted | **73 C** peak | stock clocks | high |
| EFB0251S3 blower (3.24 W) | **saturates at 73 C** | `-pl 200`, sustained 100% | medium |
| Cooling unstated, 30 min `gpu_burn` | **75 C rising to 77 C** | unlocked 64 GB at a 300 W limit, 278/300 W drawn. One report, not reproduced | high |
| 1 x 140 mm Noctua industrialPPC, 3 cards | **under 80 C** | LLM inference | high |
| 2 x stacked Noctua 140 mm | **~80 C down to ~70 C** when the second fan was added | unstated load | high |
| Arctic 12038-4K 120 mm | **~85 C** | memory-overclock `gpu_burn`; owner reported no further headroom on air, HBM errors within the first couple of minutes | medium |
| **1 x Arctic S4028-15K 40 mm** | **90 C hotspot, rejected** | same bracket as the 2-fan row above | high |
| Unstated, SM-unlock GEMM ramp | 62 C to 73 C in about 25-30 s | 8 GB card, shows the ramp rate | high |

The ramp figure is worth internalising: a 170HX goes from 62 C to 73 C in roughly 25 to 30
seconds once a real kernel starts. Idle temperature tells you almost nothing about whether
your cooling is adequate.

### The HBM floor on air

After a multi-configuration power and clock sweep on a card under a 140 mm shroud with a
120 mm fan at 3000 RPM, one tester concluded: "with the right tuning.. the temp baseline is
right here.. you can save watts, but you wont be able to drop temps on air" and "getting
lower hbm temps on air seems impossible". A 30-minute `gpu_burn` at those settings
(`EFF / Balanced +300MHz / 1400`) completed with no errors.

> [!NOTE]
> **Open problem: is the HBM temperature floor a cooling limit or intrinsic?**
>
> A direct request for waterblock HBM temperature data went unanswered, so the floor is
> unbounded from below: nobody knows whether water gets HBM materially cooler than air.
> The single cheapest high-value experiment in this domain is for the owner of the
> budget waterblock (48 C core / 58 C memory over one hour) to re-run the same
> `EFF / Balanced +300MHz / 1400` sweep with the memory sensor logged.

---

## Thermals are usually not the limiter

This surprises people, and it changes how you should spend money on cooling.

- Raising the power limit from 250 W to 300 W on a well-cooled card gained **+2.8%** BF16
  throughput (about 180 to 185 TFLOPS) with **core and memory both below 65 C**. The core
  simply does not want to clock higher.
- `mmapeak` on an 8 GB card with the OC VBIOS sat at **1470 MHz drawing only ~150 W** with
  GPU-T reporting `PerfCap: None`, even with the power limit at 300 W. Neither power nor an
  exposed cap explains that ceiling, and it remains unexplained.
- The 80 GB configuration's instability is not thermal and not power-related: the failing
  cards **never drew above about 80 W** during the crashing workload.

One genuine thermal fault mode does exist. Cards that have never been re-pasted or
re-padded can throttle heavily: one owner with two 8 GB cards could only bench one, because
the second "throttles a lot" and needed re-padding and re-pasting. If a card throttles far
earlier than its neighbours under identical airflow, suspect the factory thermal interface
before you suspect the silicon.

---

## Airflow guidance

There is no measured requirement, only a set of rules that emerged from the measurements
above. They are collected and compared against real coolers on
[Cooling](../operations/cooling.md).

| Quantity | Value | Status |
|---|---|---|
| Target static pressure for full-power operation | 20 mm | spec-derived recommendation, **not measured** |
| Arctic P12 Pro CO published spec | ~7 mm static pressure, 130 m³/h | vendor spec; this fan nonetheless held 4 cards under 65 C at `-pl 160` |
| Minimum practical fan power | above 4 W, i.e. 0.35 A at 12 V | practical guidance, unchallenged, unmeasured |
| Preferred fan classes | radial high-static-pressure blowers, or 38 mm thick axial fans | thin 120 mm fans were doubted for 300 W and for two cards |
| Airflow direction | **pull, do not push** | consistent first-hand reports of blowback from push-through sleeve shrouds |
| Single 40 mm fan | insufficient at any RPM | 1 x S4028-15K gives 90 C hotspot; 2 x gives 70 C / 76 C |

Whatever cooler is used **must also cool the VRM**, not just the die. A deshroud plus a
pressure-mounted tower cooler on the die still needs a separate 80-120 mm fan over the power
delivery area. See [Power delivery](power-delivery.md) for where those parts sit.

---

## See also

- [Cooling](../operations/cooling.md): real coolers, measured, with a recommendation table
  by target wattage.
- [Power and PSU](../operations/power-and-psu.md): power limiting, idle draw, PSU sizing.
- [Power delivery](power-delivery.md): the on-board VRM and rail topology.
- [Physical mods](../operations/physical-mods.md): teardown, waterblock installation, and
  the capacitor mod.
- [Tuning](../operations/tuning.md): the clock-ceiling and offset sweep behind the
  efficiency figures.
- [Board and variants](board-and-variants.md): SKU identification and board part numbers.
