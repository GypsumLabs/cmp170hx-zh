# On-board power delivery

## What this page covers

The CMP 170HX's own power path: the four board-level inputs, the rails they derive, the
controllers and power stages that derive them, the power-on sequence, and the depopulated
VRM phases that generate so much speculation. For PSU sizing, connectors, adapters, measured
draw and `nvidia-smi -pl`, see [Power and PSU](../operations/power-and-psu.md).

The board is the **NVIDIA A100 40 GB PCIe reference design with components deliberately
deleted**. Every component reference designator matches the leaked NVIDIA Tesla A100
electrical schematic (`NVIDIA-A100-GA100-883-P1001-B02-Rev-A.pdf`, PG100/PG101 family), so
that document is the authoritative map of this power tree. The deletions relevant here are
unpopulated VRM phases (DrMOS transistors plus their output inductors) and some rear-side
filter capacitors.

The headline for anyone considering rework: **the stock VRM is not the limiting factor on
this card, and repopulating the missing phases does not raise the power ceiling.** Measured
full-load draw is about 250 W against an estimated ~500 W of installed power-stage
capability.

---

## The four inputs

| Input | Source | Feeds |
|---|---|---|
| `3V3_PEX` | PCIe slot | stepped to **1.8 V** by an LDO, for auxiliary control circuits |
| `12V_PEX` | PCIe slot | 5 V, 1.35 V, HBMVPP 2.5 V, PEXVDD |
| `12V_EXT1` | EPS 8-pin connector, rail 1 | NVVDD core (multiphase) and HBMVDD |
| `12V_EXT2` | EPS 8-pin connector, rail 2 | a second group of the same |

The single physical 8-pin EPS socket carries `12V_EXT1` and `12V_EXT2` as two separate 12 V
inputs internally. They remain distinguishable when an adapter cable is used. This is the
origin of the "2x 8-pin" figure in third-party spec databases: two logical rails, one
physical connector.

---

## Rail map

Read directly from page 1 of the A100 schematic and cross-checked by probing a physical
board during a repair.

| Rail | Voltage | Regulator | Phases | Derived from |
|---|---|---|---|---|
| **NVVDD** (GPU core) | 1.0 V | MP2988 PWM controller driving DrMOS stages | multiple | `12V_EXT1` / `12V_EXT2` |
| **HBMVDD** (HBM core) | not stated | MP2988 driving DrMOS stages | multiple | `12V_EXT1` / `12V_EXT2` |
| **HBMVPP** | 2.5 V | MP1475 buck | 1 | `12V_PEX` |
| **PEXVDD** (PCIe I/O signalling domain) | not stated | MP2988 | 1 DrMOS phase | `12V_PEX` |
| 5 V | 5 V | MP1475 buck (MP1475DJ) | 1 | `12V_PEX` |
| 1.35 V | 1.35 V | MP2988 | 1 DrMOS phase | `12V_PEX` |
| 1.8 V | 1.8 V | LDO | - | `3V3_PEX` |

The HBMVPP rail is suspected to power the memory controller itself, on the grounds that its
supply is far simpler than the multiphase HBMVDD rail. That inference is not confirmed.

Power stages are **MP86957 smart power stages, rated 70 A output each**.

---

## Power-on sequencing

Useful because it tells you where to probe when a card is dead on the bus.

1. 12 V is applied and the filtered net `12V_F` comes up.
2. `12V_F` feeds resistive divider **R391 / R392**, producing a **2.5 V** logic-level
   `5V_PS_EN` signal.
3. `5V_PS_EN` is de-glitched by a **10 nF** capacitor.
4. `5V_PS_EN` enables the **MP1475DJ** 5 V buck.

Documented on schematics page 48; the MP1475DJ itself is on page 18.

> [!TIP]
> **Diagnostic consequence**
>
> If the card is dead on the PCIe bus, **check the 12 V input filter inductors and the
> 5 V rail switching node first, not the core rail.** This sequence was used successfully
> to guide a real repair.

---

## The depopulated phases

The 170HX is VRM-depopulated relative to the A100, and this is the single most misunderstood
feature of the board.

| Board | Missing power MOSFETs and coils |
|---|---|
| CMP 170HX | **3 per side** (one direct comparison); **roughly 6 of about 20 phases** (a second independent comparison), plus some rear-side filter capacitors |
| A100 40 GB | 1 per side |
| A100 80 GB | none |

Both figures come from side-by-side photo and board comparisons by two independent people
holding the hardware. Nobody has repopulated phases or scoped the rails, so confidence is
medium. The phases are **not uniform**: some feed memory, some feed the GPU, so "6 of 20" is
not a uniform 30% capability reduction.

A circulating PDF (`a100-unlock.pdf`, also seen as
`cmp-170hx_a100_hardware-restore.pdf`) is essentially a list of which parts to add back.
Note that the Winbond BIOS chip in that document's bill of materials is a **backup VBIOS chip
for recovering from a bad flash**, not part of any unlock. The document's author stated that
only the small components on the PCIe lanes are needed for x16; everything else in that build
was an attempt to replicate an A100 under the hood.

### Repopulating them does not help

This has been refuted from several directions and should be treated as settled:

- **Capability is not the constraint.** MP86957 stages at 70 A each put the installed VRM at
  an estimated **~500 W** against a measured full-load draw of about **250 W**. (The 500 W
  figure is datasheet reasoning, never validated by an actual 500 W run.)
- **The GPU does not sense phase count.** A VRM runs correctly under full load with half its
  MOSFETs fitted; the fitted ones simply run hotter.
- **Soldering parts on would not even activate them.** The PWM controllers would have to be
  reconfigured to drive any added phases, which makes this a very large amount of handwork
  for no effect.
- **The added parts from the A100 restoration guide serve voltage stabilisation only.** They
  do not raise the power ceiling.
- **The 8 GB card has identical power delivery and is entirely stable at 64 GB**, with the
  VRM mod reported unnecessary and minimal error observed without it.
- **The 80 GB failures were never power-related:** the failing cards never drew above about
  80 W during the crashing workload, against a 250 W limit.

> [!CAUTION]
> **Missing capacitors are a different matter from missing phases**
>
> An LC filter on a MOSFET output with its capacitors missing turns a chopped switching
> waveform into unfiltered output. Best case the card does not boot; **overvolt is
> possible.** If you are adding parts back, do not add MOSFETs and inductors without their
> filter capacitors.

An overload counter-argument also stands on the record: the 8 GB card already has an
overclock VBIOS raising the limit to 300 W (the same as A100 PCIe), and an overloaded PWM
would either trip its protection and shut down, or overheat and burn out. Neither outcome
gives you more performance.

---

## Raising the ceiling: what has and has not been tried

| Route | Status |
|---|---|
| 300 W "OC mining" VBIOS | **Works**, on 8 GB cards. Real ceiling, `POW 278 / 300 W` logged over 30 minutes. Buys about +2.8% BF16. |
| Shunt mod to restore full A100 TDP | **Never performed.** Expected by an experienced hardware modder to be a simple shunt mod rather than a firmware change, but nobody has done or measured one. |
| Software or VBIOS route to a 400-500 W limit | **Never achieved.** Proposed as the alternative for people uncomfortable with shunt modding. |
| Repopulating VRM phases | **Does not raise the ceiling.** See above. |

Since raising the limit from 250 W to 300 W measurably gains only about 2.8% with core and
memory both below 65 C, none of these is likely to be worth the risk. The core does not want
to clock higher. See [Power and PSU](../operations/power-and-psu.md) and
[Tuning](../operations/tuning.md).

---

## VRM registers: a dead end with a hazard attached

> [!CAUTION]
> **`0x20340` / `0x20344` and runtime devinit can overvolt the card**
>
> A proposal to change VRM duty cycle directly through registers `0x20340` / `0x20344` was
> posted as a shot in the dark: "Not sure if 0x20340/0x20344 changing the duty cycle on
> VRMs directly would give the clock increase on its own. I don't think there's a PLL
> controlling clocks. If there is, then just changing the duty cycle should work on its
> own." The reasoning is self-contradictory as written: if there is no PLL, a duty-cycle
> change alone should not set a clock. **It was never tested.**
>
> The same registers were separately flagged as an **overvolt hazard**: re-executing
> devinit through the PMU at runtime could push the VRM **past 1.3 V** with a wrong value,
> because the devinit region containing timing and MRS programming is part of the training
> section that also covers clocks, PLLs and VID-PWM. Recorded here only because the
> addresses may be useful later, and because anyone poking at runtime devinit should know
> what is adjacent to it.

These addresses appear **nowhere** in the shipping unlocker or in any of the 12 unreleased
branches, verified by keyword sweep.

---

## The unlock does not touch power at all

A keyword sweep of the shipping tree and all 12 unreleased branch snapshots for `0x20340`,
`0x20344`, `freqDelta`, `power_limit`, `powerlimit`, `thermal`, `pstate`, `vid_pwm`,
`clkdomain`, `MHz` and `watt` returns nothing in any patch, script or config. The unlock
touches privilege-level masks, SS0/SS1, CFG1, LMR and the GSP framebuffer/PMA description
and nothing else.

Every power and thermal characteristic of an unlocked card is therefore a property of the
**stock VBIOS and stock board**, and cannot be fixed, or broken, by the unlocker.

---

## The unpopulated 4-pin pad

An unpopulated 4-pin pad on the PCB was measured carrying **12 V** and is suspected to be a
fan header.

> [!NOTE]
> **Open problem: is it a fan header, and is it PWM-controllable?**
>
> One participant reported "it has 12v and gnd", which is power only: no tachometer, no
> PWM, meaning any fan attached would run at fixed full speed with no RPM reporting. A
> skeptic in the same thread said the connector "doesn't look like a fan con". **No
> photo-confirmed pinout, no mating receptacle part number, and no working fan install
> has ever been posted.** Next step: scope the remaining two pins while the card idles and
> loads, and trace them on the leaked schematic. This matters because it would enable
> standalone per-card fan control with no external controller. See
> [Cooling](../operations/cooling.md).

---

## Open and unresolved

> [!NOTE]
> **Open problem: do power-raised cards blow a rear-board capacitor after prolonged mining?**
>
> One owner relayed that the supplier of their cards had this happen repeatedly and
> showed a blown board: "literally goes poof and lets out black smoke", described as
> cheap and repairable, with the suspected parts narrowed to two components on the rear of
> an 8 GB board believed to be capacitors. That same operator ran cards at around 56 C,
> raising the suspicion that the wrong sensor was being monitored and the VRM was
> overheating under bandwidth-bound mining loads. An experienced long-time owner said they
> had never seen this failure and doubted it, arguing the components can handle far more
> than the BIOS allows. No photograph of the failed component and no measurement were
> produced. **What would settle it:** a photograph of a failed board with the designator
> readable, plus a thermocouple reading on the VRM under a bandwidth-bound load.

> [!NOTE]
> **Open problem: are the medium rear-side SMD capacitors near the core needed?**
>
> Raised from a photo by someone who had previously seen an RTX 2070 with two of these
> broken off, which wrecked its voltages: roughly two per MOSFET on the left and right
> capacitor rows, dual-placed for redundancy, but at least one of each pair must be
> present and working. Flagged explicitly as a hypothesis, not a finding, and specifically
> as a possible 80 GB stability factor. This concerns local decoupling rather than VRM
> phases, so it is not covered by the phase-repopulation refutation above. **Next step:**
> photograph the rear of a working 8 GB and a working 10 GB card and compare against the
> schematic's C-designator list.

---

## Interface summary

| Quantity | Value |
|---|---|
| PCIe slot power limit (DevCap) | 75 W |
| External connector | 1 x EPS 8-pin, 300 W rated, carrying `12V_EXT1` and `12V_EXT2` |
| Stock power limit | 250 W default = 250 W maximum, 100 W minimum |
| OC mining VBIOS power limit | 300 W maximum |
| Measured full-load draw | ~250 W stock, 278 W at a 300 W limit |
| Power stages | MP86957, 70 A each |
| Estimated installed VRM capability | ~500 W (datasheet reasoning, never validated) |
| VRM overvolt hazard threshold | past 1.3 V, if a wrong value reaches `0x20340` / `0x20344` during runtime devinit |

---

## See also

- [Power and PSU](../operations/power-and-psu.md): connectors, adapters, PSU sizing,
  measured draw, `nvidia-smi -pl`.
- [Thermals](thermals.md): thermal limits, sensors, and the leakage feedback loop.
- [Cooling](../operations/cooling.md): the VRM needs its own airflow.
- [Physical mods](../operations/physical-mods.md): teardown and rework, including the
  capacitor mod (which is a PCIe signalling mod, not a power mod).
- [Board and variants](board-and-variants.md): the A100 lineage and what else was deleted.
