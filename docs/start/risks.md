# Risks

**What this page covers.** An honest assessment of what can go wrong if you unlock a CMP 170HX,
ranked by how permanent the damage is. What is recoverable and what is not, whether the card can
actually be bricked and by which specific actions, the thermal and power hazards that are far more
likely to destroy a card than any software step, the irreversible risk in the capacitor mod, what
this does to host stability and Secure Boot, and where the legal and warranty questions sit.

**The short version.** The unlock itself is close to risk-free for the card. It writes only volatile
registers, it blows no fuses, it never touches the VBIOS or any EEPROM, and it lives entirely inside
a patched kernel module in `/lib/modules/$(uname -r)/updates/cmpunlocker/`. Delete that directory,
power cycle, and the card is bit-for-bit the card you started with. **No permanent brick caused by
the unlock has ever been confirmed.** The genuine, irreversible risks in this project are all
physical: inadequate airflow on a 250 W passively cooled card, the wrong power cable in the EPS
socket, a soldering iron near the PCIe fingers, and a VBIOS flash without a hardware programmer to
recover from.

Read [Recovery](../procedures/recovery.md) for the full reset ladder and register-persistence table.
This page is the decision-time summary.

---

## 1. What is recoverable and what is not

| Failure | Permanence | Cost to recover |
|---|---|---|
| Unlock does not take; card still reports 8192 / 10240 MiB | None | Cold reboot, or `sudo ./remove.sh --yes` |
| GSP will not boot; `nvidia-smi` says "No devices were found" | None | Cold power cycle (60 s with the PSU off) |
| Card wedged, `nvidia-smi` hangs, Xid 119 / 154 / 31 | None | Reset ladder: FLR, then SBR, then cold boot |
| Host CUDA runtime wedged, `cuInit` returns 999 | None | Host reboot |
| Machine will not shut down, card boots pre-wedged | None | Boot with the module blacklisted, then clean up |
| System left at a text console after a failed retrain | None | Blacklist `nvidia` from the bootloader, reinstall |
| Workload data in VRAM at the moment of an Xid | **Lost** | Nothing; the job dies |
| HBM degraded by chronic over-temperature operation | **Permanent** | None |
| Board damaged by a PCIe 8-pin cable in the EPS socket | **Permanent** | Component-level repair, if at all |
| PCB warped, traces broken or ICs cooked during rework | **Permanent** | Usually none; these defects are very hard to diagnose |
| Bad VBIOS flash | **Permanent without a programmer** | External SPI programmer with a 1.8 V adapter |

Everything in the first six rows is inconvenience. That is most of what actually happens to people.

---

## 2. Can the card be bricked?

### 2.1 By the unlock: no confirmed case

The structural argument is stronger than the (also complete) absence of reports. The shipping
unlock:

* writes only volatile registers, all of which revert on power loss;
* never writes the master kill fuse `0x008203f0`, which reads `0x00000000` on shipping cards and
  would, if blown, lock out every feature override permanently;
* does not flash the VBIOS or any EEPROM;
* modifies no file under `/lib/firmware` (the abandoned firmware-patching predecessor did, which is
  why `remove.sh` still cleans up `gsp_tu10x.bin.cmpunlocker.*` leftovers);
* is fully reverted by `remove.sh` plus a power cycle.

Memory geometry (CFG1, LMR, per-FBPA CSTATUS, the FB-geometry PLMs) does not survive a
function-level reset, let alone a power cycle. Only SS0, SS1 and the feature-override PLM at
`0x00823804` sit in the always-on island, and even those are gone after the power goes off.

The three public brick claims all dissolve on inspection. The one "bricked" report inside the
clean-room work was an LLM agent's mistaken conclusion after it lost track of the fact that the
cards could be reset. The public "NVIDIA-poisoned drivers brick cards" claim has no first-hand
report behind it; the specific case cited was assessed as a 10 GB card being pushed to the unstable
80 GB geometry. Seller talk of a "defective batch" during the late-July 2026 price spike was a
cancellation excuse used against listings that had already shown working cards.

!!! question "Open problem: one report that does not fit"
    One first-hand account describes a 10 GB card wedged with three stuck D-state threads that would
    not clear with FLR, SBR, PCI detach and reattach, **or a full PSU power-off cold boot**: "when I
    rebooted, the registers were still written, and the D-threads were still there... card booted
    pre-wedged". Recovery eventually required holding the power switch with the power strip off and
    physically removing the card for a few hours. The observation was doubted in-channel and remains
    unexplained. It contradicts the otherwise well-supported no-persistent-state model, which is
    exactly why it is recorded rather than dismissed. The honest statement is: the model says a power
    cycle always wins, and in every reproducible case it did, but one credible operator reports a
    state that survived one.

### 2.2 By specific physical actions: yes, permanently

!!! danger "Actions that will destroy hardware"
    **Forcing a PCIe 8-pin cable into the card's EPS socket.** The two are keyed differently and
    only go together if forced. The 12 V and ground lines are swapped on some pins between the two
    connector types, so forcing it **will damage the card**. The socket is a single 8-pin
    CPU-style (EPS) connector carrying two logical 12 V rails (12V_EXT1 and 12V_EXT2); cards ship
    with a dual 8-pin-PCIe to 8-pin-EPS Y adapter for exactly this reason.

    **Reusing a modular PSU cable across PSU brands.** Modular-side pinouts are vendor-specific with
    no standard. This destroys hardware in the general case, not just on this card.

    **Running the card with no airflow.** See section 3. This is the single most likely way to kill
    a 170HX.

    **Preheating the whole board in an oven, or over-preheating with an IR stove plus hot air,
    during the capacitor mod.** The dominant beginner failure mode: it bends the PCB, breaks internal
    traces and cooks ICs, and those defects are extremely hard to diagnose afterwards. The oven idea
    was proposed in-channel and immediately rejected.

    **Flashing a VBIOS that is not for this device.** TechPowerUp entry 283106 is an
    A100 / DRIVE-PG199-PROD image (device `0x20BB`, subsystem `10DE 14A1`) that has circulated as a
    170HX reference and must never be flashed to a 170HX. Recovery from a bad flash needs an external
    programmer; GPU EEPROMs are 1.8 V, so a CH341A needs a 1.8 V adapter. Note that the unlocker
    itself never touches the VBIOS, so flashing is an entirely separate decision with its own risk.

    **Writing the VRM duty-cycle registers `0x20340` / `0x20344`.** Re-executing devinit through the
    PMU at runtime with a wrong value could push the VRM past **1.3 V**, because the devinit region
    containing memory timing also covers clocks, PLLs and VID-PWM. This has never been tested, these
    addresses appear nowhere in the unlocker or any of its twelve branches, and there is no reason to
    go near them.

---

## 3. Thermal risk: the most likely way to destroy a card

This is a **250 W card with a fully passive heatsink and no fan of its own**. `nvidia-smi` reports
`Fan Speed : N/A` on every capture ever taken. It was designed for the forced air of a high-RPM
server chassis. In a desktop case with ambient airflow it will cook.

!!! danger "Never power the card without arranged airflow"
    The GA100 die exhibits genuine leakage-driven thermal runaway. Higher junction temperature raises
    CMOS leakage current, which produces more heat, which raises leakage further. Observed first-hand
    while dry-running a card with a waterblock fitted but no coolant: idle draw started around
    **40 W**, climbed to **60 W at 80 °C**, and was still rising when the card was powered off.

    **If you dry-run the card without coolant, power off within 5 minutes.**

    If cooling fails outright under load, the card does not settle at its throttle point: it climbs.
    The hands-on description is "it'll thermally throttle, but to a temperature above 100 degrees,
    that then consumes more power, thus increased temperature... and you end up with a volcano."

The driver-reported limits, read from an unlocked 10 GB card on driver 610.43.02:

| Limit | Value |
|---|---|
| GPU Shutdown Temp | 98 °C |
| GPU Slowdown Temp | 95 °C |
| GPU Max Operating Temp | 85 °C |
| Memory Max Operating Temp | 95 °C |

Practical throttle onset is reported as around **80 °C**. That figure came from a participant who
asked whether 90 °C was acceptable, then said they had found throttling starting at 80 °C, and
was told it was not acceptable; no telemetry was posted, so treat it as a reading rather than a
measurement. Community design targets converged on **70 °C core and 75 to 76 °C memory hotspot**
under load. Ninety degrees hotspot is treated as
unacceptable. GA100 memory is unusually conservative compared with GDDR6X parts that run to ~105 °C.

*(Confidence: medium on the exact throttle layering. Nobody has captured a log correlating clock
reduction against temperature through 75 to 95 °C, so the "soft VBIOS reduction at 80, driver
ceiling at 85, hardware slowdown at 95" picture is inferred.)*

Two traps specific to this card:

1. **A single 40 mm fan is not enough, whatever its RPM.** One Arctic S4028-15K gives a 90 °C
   hotspot; two on the same bracket never exceed 70 °C GPU and 76 °C hotspot. The commonly sold
   3.24 W snail-fan "A100 cooling" printed adapter advertises 300 W and removes **150 to 180 W
   maximum** at full duty from a direct PSU feed.
2. **Do not validate cooling with a conventional FP32 burn-in.** The card is hard to load: `gpu_burn`
   FP32 and FP64 draw only about **60 W**, tensor-core `gpu_burn` about **75 W**. Hashcat (pure
   integer) and a STREAM-like memory benchmark both pull **160+ W**; real llama.cpp inference holds
   **230 to 240 W**. A cooler that passes an FP32 burn-in has proved almost nothing.

Chronic under-cooling is the one thermal failure that is permanent: HBM degrades fast past its safe
temperature. In the burn-in record, the card accumulating memory errors ran at 85 °C with a memory
overclock, while error-free cards stayed below 73 °C. *(Confidence: medium; no failure-rate data
exists.)*

See [Cooling](../operations/cooling.md) for the full measured comparison of blowers, axial fans,
shrouds and waterblocks, and [Thermals](../hardware/thermals.md) for the limits in detail.

---

## 4. Power and PSU risk

The card takes a **single 8-pin EPS (CPU-style) connector**, not PCIe 8-pin. `lspci` reports
`SlotPowerLimit 75 W` in DevCap, so everything above 75 W arrives through that connector.

* An **8-pin EPS connector is rated 300 W; an 8-pin PCIe connector is rated 150 W**, and the 12 V and
  ground lines are swapped on some pins. Use the supplied Y adapter: one leg at 150 W, both legs at
  300 W, or source proper cables.
* Check what your PSU actually has. One real build failed on an EVGA unit with **1× PCIe 6+2 and
  1× 6-pin** rather than two 6+2 connectors, which breaks the two-PCIe feed the adapter expects.
* PSU sizing: roughly **600 W on the 12 V rail** is the stated minimum for a two-card build. Five
  cards at 250 W each (about 1250 W of GPU load) wants a 1600 to 2000 W supply. Twenty cards idling
  at ~30 W each is 600 to 700 W just to sit there.
* The card exposes only performance state **P0** and has no idle P-state. Idle draw is 27 to 46 W
  and cannot be reduced by `nvidia-pstated`, which returns `NVAPI_ERROR` on single-P0 cards. Budget
  for it.

The stock power envelope is 250 W default, 250 W maximum, 100 W floor. `nvidia-smi -pl` works fine
and can only *lower* the card unless it carries the 300 W OC mining VBIOS. Raising the limit to
300 W buys about **+2.8 %** on BF16 in a direct A/B, so there is little reason to.

See [Power and PSU](../operations/power-and-psu.md) and
[Power delivery](../hardware/power-delivery.md).

---

## 5. The capacitor mod: the one genuinely irreversible step

The x4-to-x16 link-width mod means hand-soldering **24 × 0402 capacitors** (220 nF, X7R, ≥ 16 V,
designators roughly C1100 to C1350) onto pads immediately adjacent to the PCIe gold fingers of an
8 to 12 layer board. There is no software involved and no undo.

!!! danger "Soldering risk, not firmware risk"
    Rework datum for this board: **hot air at 420 °C for two minutes** before any chip can be
    removed. That is the thermal mass you are working against, a few millimetres from the edge
    connector.

    The dominant beginner failure is over-preheating with an IR stove plus hot air, which bends the
    PCB, breaks internal traces and cooks ICs. Those defects are extremely hard to diagnose
    afterwards, and a warning raised in-channel is blunt: inexperienced buyers attempting this
    themselves are likely to brick cards by improperly soldering the decoupling caps.

Honest counterweight: several experienced modders rate the job beginner-to-hobbyist level, called it
"probably the easiest card to do PCIE mod", and one completed a card by hand in about 20 minutes.
The area is not cramped. The adjudicated technique is leaded 60/40 solder and gel flux, wick away
all the factory lead-free solder first, a fine-point iron at about 380 °C with no preheating,
Kapton tape around the area, and practise on a scrap board.

Partial or bridged work negotiates down to the next legal width rather than failing outright, so
reported lane count is a direct diagnostic of solder quality: 12 of 24 populated gives x8, and one
modder's progression across three cards was x4 → x8 → x16 as technique improved.

**The capacitor mod changes lane count only. It never changes PCIe generation.** Gen1 to Gen2 is a
separate, software-only achievement that lives on unreleased branches. Do not conflate them. See
[Physical mods](../operations/physical-mods.md) and [PCIe Gen2](../unlock/pcie-gen2.md).

---

## 6. Data loss and system stability

The unlock does not corrupt data at rest. What it does is change the size of the window CUDA is
allowed to allocate in, and workloads that run past the genuinely usable edge die.

* **Xid 31, MMU fault, region violation.** Allocating past the usable top of the unlocked window
  faults the card and makes it unusable in CUDA until a full reboot. One capture shows the faulting
  physical address at `0xf_f7400000`, which is 63.86 GiB, right at the top of the 64 GB window. Fix:
  offload one fewer layer to that GPU.
* **Keep vLLM at `gpu-memory-utilization` 0.90 or below.** The unlocked geometry exposes 65052 MB
  with only 64733 MB actually available, so 0.95 is thin enough to crash a card.
* **Do not `kill -9` live multi-GPU jobs.** Repeatedly doing so leaves roughly 32 zombie CUDA
  processes and wedges the host CUDA runtime, so `cuInit` returns 999 for every framework while
  `nvidia-smi` still reports healthy. This is not fixable inside a container; it needs a host reboot.
  SIGKILL on a live verification kernel can wedge the card with Xid 45. In one full 8-card session
  with hundreds of 60-second health samples there were **zero** hard faults when the workload was
  driven properly, so this is an operator-induced class of failure, not a hardware one.

!!! danger "The over-provisioned 80 GB geometry destroys workloads"
    The 8 GB card at 64 GB is stable and in production. The 10 GB card at 40 GB is stable. The 10 GB
    card pushed to **80 GB reports the capacity but is unusable above roughly 40 GB**: hangs,
    Xid 154, and memory errors under stress (one gpu-burn run at 80 GB logged **2,796 errors**
    while the same card ran cleanly at 40 GB). It is power-limit independent. This wrecks jobs
    rather than cards, but it wrecks them reliably. See [80 GB](../frontier/80gb.md).

Host-level risk is real but ordinary. Driver-patch iteration on bare metal is destructive enough
that one developer reported reinstalling the OS after each botched `nvidia.ko` deploy. Prefer a
headless or non-NVIDIA-display host: the `nvidia` module frequently refuses to unload because `drm`
is held by seven users including `i915`, and unlock work needs the module out of the way.

---

## 7. Secure Boot and unsigned modules

`install.sh` **hard-fails if Secure Boot is enabled**, because the patched modules are unsigned:

```text
Secure Boot is enabled. Disable it before installing unsigned patched modules.
```

Three consequences worth weighing before you start:

1. **Disabling Secure Boot is a host-wide security posture change**, not a per-card one. It affects
   everything the machine boots, forever, until you turn it back on.
2. **The check is conditional.** It only runs if `/sys/firmware/efi` exists **and** `mokutil` is on
   `PATH`. On a non-EFI machine, or one without `mokutil` installed, the check is silently skipped
   and you can still end up with modules the kernel refuses to load. The symptom in `dmesg` is
   `nvidia: module verification failed: signature and/or required key missing - tainting kernel`.
3. **Kernel modules cannot be sandboxed.** They run in ring 0 with full access to the machine. This
   was noted explicitly in-channel when someone proposed having an LLM scan a circulated binary blob
   for safety: that is not a safety guarantee. The mitigation is to build from source. `build.sh`
   fetches NVIDIA's own tag tarball and applies six patches you can read; nothing prebuilt is
   redistributed. Note, though, that `build.sh` performs **no checksum or signature verification** on
   the downloaded tarball, so on an untrusted network verify the cached file yourself.

Signing the modules yourself with your own Machine Owner Key is the standard way to keep Secure Boot
on. Nobody in the record has documented doing it for this patch set.

---

## 8. This is unsupported experimental software

There is no vendor, no warranty on the software, and no service-level commitment of any kind.

* **Exactly two driver versions are supported:** nvidia-open `610.43.03` (default) and `610.43.02`,
  matched as exact strings. The build hard-fails on anything else. Ports to 595, 590 and 580 exist
  only on an unreleased branch, are source-verified, and **have never been boot-tested by anyone**.
* **Branch churn, not silicon, is what breaks installs.** Twelve unreleased branches exist alongside
  shipping `master`, several of them carrying documentation that disagrees with their own code. The
  `docs` branch alone references an `uninstall.sh` that does not exist, states SS0 and SS1 values
  that the code does not write, and over-generalises the PLM readback rule.
* **PCIe Gen2 does not ship on `master`.** Patches `0007` and `0008` exist only on experimental
  branches, and one of the two competing `RMPcieLinkSpeed` values is wrong with no A/B test to say
  which.
* **Support is one person.** The first documented Gen2 ticket waited about **10.5 hours** for a
  first reply. Attach `sudo dmesg | grep SEC2_DEBUG` and your newest install log or expect to wait
  longer.

Which of these matter depends on you. If your response to "my card came back reporting 8192 MiB
after a cold boot" is to read `dmesg` and work the triage list, this is a comfortable project. If
you need the card working on Tuesday, it is not.

---

## 9. Legal and warranty considerations

Stated neutrally, and briefly. **None of this is legal advice, and the applicable law varies by
jurisdiction.**

* **NVIDIA issued a DMCA takedown against at least one `cmpunlocker` fork on 2026-07-17**, taking
  that repository offline. The recipient stated the notice came from NVIDIA directly and stopped
  public work. Whether that was human or automated filter-triggered enforcement was never
  established, and no takedown document exists in the source set. *(Confidence: medium; first-hand
  report from the repository owner, with the repository observably down.)*
* The unlock is a patch against **NVIDIA's own open-source kernel modules**, published by NVIDIA and
  fetched from NVIDIA at build time. No NVIDIA code is redistributed by the tool. The decryption keys
  involved are ones already published on NVIDIA's public website. The provenance question of whether
  the work derives from the 2022 LAPSUS$ breach has been examined at length and answered in the
  negative; see [Clean room and provenance](../history/clean-room-and-provenance.md).
* The driver's end-user licence terms, and any local rules on circumventing technological protection
  measures, are yours to read and evaluate.
* On warranty: these are ex-mining cards bought second-hand, so in practice there is rarely a
  manufacturer warranty to void. Where a seller warranty exists, modifying the card physically, and
  quite possibly running unsigned patched drivers on it, would be expected to end it. Whether a
  seller honours anything after an unlock attempt is a matter between you and the seller.

---

## 10. A practical safety posture

* **Arrange cooling before you power the card once.** This is the only item on this list that can
  destroy a card in minutes.
* Confirm the card enumerates and runs on an **unpatched stock driver** first. It does: stock
  `nvidia-driver-570` plus CUDA 12.8 on Ubuntu 24.04 works out of the box. Knowing that gives you a
  baseline to return to.
* Use the supplied EPS adapter. Never put a PCIe 8-pin cable into the EPS socket.
* Prefer a headless or non-NVIDIA-display host so the module can actually unload.
* Do the unlock on a machine you can afford to reinstall.
* Do not `kill -9` live jobs, and keep vLLM at 0.90 or below.
* Do not run the over-provisioned 80 GB geometry on hardware or workloads you care about.
* Pin the driver at 610 as a long-term precaution against a future NVIDIA release closing the hole,
  the same way P100 and V100 users pin around 580. *(Confidence: medium; reasoned advice, not yet
  needed, since no blocking driver exists.)*
* Before asking for help, capture `sudo dmesg | grep SEC2_DEBUG` and the newest
  `logs/install_*.log`.

---

## Related pages

* [Identify your card](identify-your-card.md): which SKU you have and which profile applies
* [Quick start](quick-start.md) and [What is this card](what-is-this-card.md)
* [Recovery](../procedures/recovery.md): the reset ladder and the full state-persistence table
* [Troubleshooting](../procedures/troubleshooting.md): symptom to cause to fix
* [Install](../procedures/install.md): prerequisites and the supported procedure
* [Cooling](../operations/cooling.md) and [Thermals](../hardware/thermals.md)
* [Power and PSU](../operations/power-and-psu.md) and
  [Power delivery](../hardware/power-delivery.md)
* [Physical mods](../operations/physical-mods.md): the capacitor mod in full
* [80 GB](../frontier/80gb.md): why the over-provisioned geometry is not usable
* [Glossary](glossary.md) for any term above that is unfamiliar
