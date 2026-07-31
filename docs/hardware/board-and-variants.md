# The board and its variants

**What this page covers.** The physical CMP 170HX PCB: what it is derived from, which components
NVIDIA deliberately deleted from it, the two shipping variants and every reliable way to tell
them apart, board and part-number codes, connector layout, the VRM, the strap resistor array,
the per-SKU floorsweep, and what the bare footprints on the board do and do not tell you.

**Two facts to fix before anything else.**

1. **The CMP 170HX PCB is the NVIDIA A100 40 GB PCIe reference design with components
   deliberately deleted.** Every component reference designator on the board matches the leaked
   NVIDIA Tesla A100 electrical schematic `NVIDIA-A100-GA100-883-P1001-B02-Rev-A.pdf` of the
   PG100/PG101 family. The match is to the **40 GB PCIe** board specifically, not the 80 GB and
   not SXM.
2. **There are exactly two shipping variants, and they unlock to different capacities.** The
   **8 GB** card (`10de:20c2`) unlocks to **64 GB**. The **10 GB** card (`10de:2082`) unlocks to
   **40 GB**. Never mix these up. The 80 GB configuration was tried on 10 GB cards and found
   unstable; see [the 80 GB question](../frontier/80gb.md).

---

## The two variants at a glance

| Property | 8 GB variant | 10 GB variant |
|---|---|---|
| PCI ID | `10de:20c2` (`0x20C2`) | `10de:2082` (`0x2082`) |
| Subsystem | `0x158510DE` | `0x155710DE` |
| Board part number | `900-11001-0108-000` | `900-11001-0105-000` |
| GPU part number | `20C2-105-A1` | `2082-105-A1` |
| Board ID | not recorded | `0x8100` |
| Production VBIOS | `92.00.67.00.01` (2021-05-14) | `92.00.66.00.02` (2021-04-23) |
| HBM vendor | SK Hynix **HBM2e** | Samsung **HBM2** |
| Active FBPAs / FBPs | 16 of 24 / 8 of 12 | 20 of 24 / 10 of 12 |
| Active stacks / bus width | 4 stacks, 4096-bit | 5 stacks, 5120-bit |
| Stock capacity | 8192 MiB | 10240 MiB |
| **Unlocks to** | **65536 MiB (64 GB)** | **40960 MiB (40 GB)** |
| Unlocked CFG1 `0x009a0204` | `0x02779000` | `0x02669000` |
| Unlocked LMR `0x00100ce0` | `0x0000020B` | `0x0000028A` |
| `FUSE_SKU_ID` `0x00821060` | `0x80` | `0x68` |
| `OPT_GPC_DISABLE` `0x00820350` | `0x13`, `0x25`, `0x45` observed | `0x15`, `0x85`, `0xa8` observed: **per-die, not per-SKU; all leave 5 GPCs / 70 SM** |
| `NV_PTOP_FS4` `0x0002241c` | `0x00000000` | `0x00000081` |

Both report identically in the obvious places, which is exactly why the table above matters:
`lspci` names both `GA100 [CMP 170HX] (rev a1)`, and `nvidia-smi` reports the product name only
as "NVIDIA Graphics Device". Neither string distinguishes the SKUs.

A third device ID, `10de:20b0`, is detected by the installer but is **not** unlocked: the
in-driver gate accepts `0x20C2` and `0x2082` only, so a `20b0` card installs the tool without
unlocking anything. `10de:20b0` is the A100 SXM4 40 GB ID.

> [!CAUTION]
> **Getting the variant wrong is the single most consequential identification error**
>
> The shipping driver picks geometry from the PCI device ID at runtime, so it will do the right
> thing on its own. But a human who assumes "8 GB means 40 GB" or "10 GB means 64 GB" will
> misread every register capture, every capacity report and every troubleshooting thread. Read
> the device ID first, every time.

---

## Telling them apart

### From software

```bash
# 1. Device ID and subsystem. This is the authoritative answer.
lspci -nn -d 10de: | grep -i GA100
# 0d:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)

lspci -d 10de:20c2 -vnn | grep -i "Subsystem"
# Subsystem: NVIDIA Corporation Device [10de:1585]

# 2. Cross-check with nvidia-smi.
nvidia-smi --query-gpu=pci.device_id,pci.sub_device_id,vbios_version,memory.total \
           --format=csv

# 3. Board and GPU part numbers, and the serial/board ID, from the InfoROM.
nvidia-smi -q | grep -Ei "board part number|gpu part number|inforom|serial"
```

Mapping:

| `pci.device_id` | `pci.sub_device_id` | Variant |
|---|---|---|
| `0x20C210DE` | `0x158510DE` | 8 GB, unlocks to 64 GB |
| `0x208210DE` | `0x155710DE` | 10 GB, unlocks to 40 GB |

### From registers, if the PCI IDs are in doubt

These are read-only probes over BAR0. See [fuses and OTP](fuses-and-otp.md) for the full map and
[verify](../procedures/verify.md) for the tooling.

| Register | 8 GB | 10 GB |
|---|---|---|
| `FUSE_FBP_DISABLE` `0x00820364` | `0x00000852` | `0x00000009` (also `0x840`; varies per die) |
| `FUSE_FBPA_DISABLE` `0x00820368` | `0x00c0330c` | `0x000000c3` (also `0xc03000`) |
| `FBHUB_NUM_ACTIVE_LTCS` `0x00100800` | `0x10` (16) | `0x14` (20) |
| `FBPA_NUM_ACTIVE` `0x009a0164` | `8` | `0xa` |
| `FUSE_SKU_ID` `0x00821060` | `0x80` | `0x68` |
| `NV_PTOP_FS4` `0x0002241c` | `0x00000000` | `0x00000081` |
| VBIOS IFR fingerprint | `2ff19960f9175320` | `3ca3d24230d6800f` |
| VBIOS FIRMWARE fingerprint | `e2c91c1808ae2759` | `8c4e1344c51b0940` |

`NV_PTOP_FS4` bit 0 is `GEN2_PCIE` and bit 7 is `GEN2_PCIE_SPEED`, so the 8 GB card reading
`0x00000000` is the interesting half. The 10 GB reading of `0x00000081` matches what an A100
80 GB, an RTX 3070, GA10x parts and the Drive `0x20bb` all return.

### From the board and the package

| Signal | 8 GB | 10 GB |
|---|---|---|
| PCB silkscreen above the gold fingers | `180-11001-DAAA-B15` (also seen `180-11001-DAAA-B35`, `180-11001-DAAA-045`) | same board family |
| ASIC marking | `GA100-105F-A1` | `GA100-105A-A1` |
| HBM vendor (GPU-Z, or stack markings) | SK Hynix HBM2e | Samsung HBM2 |
| Board PN sticker / InfoROM `BRD` | `900-11001-0108-000` | `900-11001-0105-000` |

The `-0108-` versus `-0105-` field in the board part number is the most reliable purely physical
discriminator short of reading the HBM stack markings.

---

## Board codes and lineage

| Code | What it is | Relationship to the 170HX |
|---|---|---|
| `PG100` / `PG101` | NVIDIA A100 PCIe board family, the schematic family the 170HX designators match | The 170HX **is** this board, depopulated |
| `P1001-B02` | The specific leaked schematic revision (`NVIDIA-A100-GA100-883-P1001-B02-Rev-A.pdf`); page 3 is "IO: PCIe CONNECTOR" | Source of the capacitor designators and values used for the lane-width mod |
| `180-11001-DAAA-*` | PCB silkscreen part number on the 170HX | The `11001` field is shared with the board PN `900-11001-*` |
| `900-11001-0108-000` / `900-11001-0105-000` | Assembled board part numbers | 8 GB / 10 GB |
| `GA100-883AA-A1` | ASIC marking on a retail Tesla A100 40 GB | The full-fat bin, photographed alongside a 170HX for comparison |
| `GA100-105F-A1` | ASIC marking on the 170HX | The cut-down bin. The `105` matches the GPU PN suffix `-105-A1` on both SKUs |
| `PG199` | The NVIDIA DRIVE A100 (A100D) **SXM2** module, PCI `10DE:20BB` | **Not a 170HX board.** A different part entirely |

> [!WARNING]
> **PG199 is a recurring source of confusion, in three different ways**
>
> 1. **PG199 is not the 170HX board code.** It is the DRIVE A100 SXM2 module. It was repeatedly
>    floated as an unlock candidate because it shares the 170HX's memory topology (4-stack
>    Hynix HBM2e, 4096-bit, sold as 32 GB, some sources listing a 40 GB SKU) and would need no
>    PCIe soldering. A first-hand owner reported 96 SMs rather than 108, supported core clocks
>    of only 1140-1260 MHz, PCIe 3.0 x16, brutal to cool, and difficult to run training loads on
>    under water. TechPowerUp's 6144-bit listing for it was called wrong. No PG199 unlock exists.
>    One attempt is on record: a modified cmpunlocker was applied to a PG199 board on
>    2026-07-26, the intended CFG1 and LMR writes landed and the PLMs opened, but boot failed
>    with `Booter failed 0x54` and GSP never finished init.
> 2. **The unlocker branch named `PG199` does not implement PG199 support.** Its diff against
>    master touches only `README.md`, `common/constants.yaml` (comments only), `driver/build.sh`,
>    `install.sh`, `remove.sh` and `requirements.txt`, and deletes the PR template. Its profiles
>    are byte-identical to master's 8 GB and 10 GB profiles, no driver patch is changed, and
>    `0x20BB` appears nowhere in the repository. It makes no device-detection change at all:
>    master's own `install.sh` already greps for `10de:20b0` alongside `10de:20c2` and
>    `10de:2082`, and the branch only rewords the README requirement line to say so.
> 3. **TechPowerUp entry 283106 is a DRIVE-PG199-PROD image and must never be flashed to a
>    170HX.** See [VBIOS](vbios.md).

---

## Physical dimensions and mounting

| Measurement | Value |
|---|---|
| PCB length | 27 cm |
| All-in length | 29 cm, including the I/O shield and a plugged-in EPS connector |
| Heatsink bolt pattern around the die | 57 × 68 mm centre-to-centre (68 mm vertical, 57 mm horizontal) |
| Die package | about 55 × 55 mm, BGA-2743 |
| Die area | 826 mm², TSMC 7 nm, 54,200 million transistors, 65.6 M/mm² |
| Fasteners | Torx T10 and T15 |
| Thermal pads | 1.5 mm soft on the main areas, 3 mm soft on the inductors, plus liquid thermal compound on the die |

The package legend on the 170HX also reads `NVIDIA / B KR 2120A1 / TBSG42.M0W e1`.

> [!NOTE]
> **Open problem**
>
> Whether the main-area thermal pad is 1.5 mm or 2 mm. The 1.5 mm and 3 mm figures came from an
> owner with the card open and a photograph; a "2 mm" figure came from a different participant
> prefaced with "I think". The T10/T15 bits are corroborated by both. A caliper measurement of a
> stock pad would settle it.

Cooling, teardown order and waterblock fitment are covered on [cooling](../operations/cooling.md).
The one board-specific hazard worth repeating here, because it is a property of the *depopulated
PCB* rather than of any particular cooler:

> [!CAUTION]
> **Cover every unpopulated IC footprint before lowering a waterblock**
>
> All unpopulated IC footprints within reach of the block's contact pillars must be covered with
> thermal pad, or the block's metal pillars can short across the exposed copper pads and
> permanently kill the card. **Because the 170HX is a depopulated A100 board it has far more
> bare footprints than a real A100 and is correspondingly more dangerous to waterblock.** Pad
> placement: the DrMOS positions left and right of the ASIC; bottom-left and bottom-right of the
> ASIC; the PMIC to the right of the die between an inductor and a capacitor; and the two PMICs
> to the left of the die below the 3.3 µH inductor. Confidence is high for the instruction and
> the mechanism; the causal attribution rests on one card that died about an hour after a
> waterblock install, competing with a pre-existing mining-wear fault, and was never definitively
> isolated.

---

## Connector layout

| Connector | Detail |
|---|---|
| PCIe edge | Full x16 mechanical, **x16 electrically routed**, trains at x4 stock because 12 lanes' AC-coupling capacitors are depopulated |
| NVLink edge fingers | **Physically present** on the PCB, visible in teardown photographs and exposed by A100 waterblocks. Whether the supporting NVLink ICs are populated is **open and leans depopulated**: one direct A100-versus-CMP comparison says missing, against a schematic-based reading; see [NVLink hardware](nvlink-hardware.md) |
| Power | **1 × EPS 8-pin**, not a PCIe 8-pin, at the top right, with a stiff cable routed through the backplane |
| Display outputs | None. No display hardware. Display output is recorded as permanently absent |
| Unpopulated 4-pin pad | Measured carrying 12 V, suspected to be a fan header |

### The EPS connector

Power input is a single EPS 8-pin. Most PSU-integrated EPS cables have oversized retention clips
that physically will not fit, so a 2× PCIe-8-pin-to-EPS adapter is the usual solution. Related
cable-safety rules stated alongside: a modular EPS12V cable must carry 4× 12 V and 4× GND on
**both** ends, and one good-quality pin carries only about 70 to 80 W. The slot power limit in the
device capability structure is 75 W and the connector is rated 300 W. The software ceiling is set
by the VBIOS, not by the connector: 250 W maximum on stock firmware, and 300 W only on cards
carrying the NVIDIA 300 W OC image. See [power and PSU](../operations/power-and-psu.md).

During teardown the power cable must be pried free of the backplane with a plastic spudger before
the board can move at all, and the PCB cannot be lifted vertically because the PCIe connector
slides into a slot in the backplane. That step is documented as having confused a well-known
hardware channel on its first attempt.

> [!NOTE]
> **Open problem**
>
> Are the 4-pin fan-header pads live and PWM-controllable? One pin was measured at 12 V. The
> mating receptacle part number is unknown and nobody has established whether a tachometer or
> PWM signal is present. Scoping the remaining two pins at idle and under load, and tracing them
> on the leaked schematic, would answer it. It matters because it would enable standalone
> per-card fan control with no external controller.

### Memory apertures

Relevant to any BAR-level work:

| BAR | Size | Notes |
|---|---|---|
| BAR0 | 16 MB, non-prefetchable (`0xfa000000` on one test host, `resource0` size `0x1000000`) | Register aperture; NV_PROM lives at +`0x300000` |
| BAR1 | 64 MB, prefetchable | **Not resizable.** This is why PRAMIN-window work matters for large-memory patches |
| BAR3 | 32 MB | |

---

## What was depopulated, and what it means

This is the heart of the page. Four classes of deletion, with very different consequences. One of
the four, the NVLink interface ICs, is a reported deletion rather than a confirmed one: the
population question is unresolved, with direct evidence both ways.

| Deleted | Consequence | Restorable? |
|---|---|---|
| PCIe AC-coupling capacitors, lanes 4-15 (24 × 0402) | Link trains at x4 instead of x16 | **Yes.** Hand-soldering, reliably reproduced |
| VRM phases: DrMOS transistors plus their output inductors | None that anyone has measured | Physically yes, functionally pointless |
| NVLink interface ICs (population **unresolved**, see below) | No NVLink either way; the fuse closes it | No known path |
| Security-module region (Microchip CEC1712) | The 170HX has the pads but no chip | Not wanted; its absence is a *reduction* in verification hardware |

### PCIe AC-coupling capacitors: the flagship mod

The card trains at x4 because the AC-coupling capacitors for the upper twelve lanes (lanes 4-15)
are **routed on the PCB but depopulated from the factory**. Two capacitors per differential pair
× 12 lanes = 24 missing 0402 parts. Hand-soldering all 24 restores a full x16 link. Populating
only 12 of the 24 yields x8. The mod is purely physical: it works with no software patch at all.

| Specification | Value |
|---|---|
| Package | 0402 |
| Value | 220 nF (0.22 µF) |
| Dielectric | **X7R** (frequently miswritten as "XR7") |
| Voltage rating | ≥ 6.3 V. The x16 mod that is known to have worked used 6.3 V parts |
| Manufacturer part | Taiyo Yuden `MAASJ105SB7224KFCA01` (220 nF, 6.3 V, X7R, 0402). Samsung `CL05B224KO5NNNC` (16 V) also reported working |
| Designators | roughly C1100-C1350, from schematic page 3 "IO: PCIe CONNECTOR" |
| Distributor numbers | Digi-Key `3886834` and Digi-Key `1276-1176-1-ND` are both cited; neither is verified against the other. Quote the manufacturer part |
| Reported substitute | 100 nF 16 V X7R worked for one tester; another desoldered equivalents from a dead motherboard |

> [!CAUTION]
> **The capacitor mod changes lane WIDTH only. It never changes PCIe GENERATION.**
>
> A cap-modded card with no unlocker reports **x16 at PCIe 1.0**. Conversely, Gen2 (5 GT/s) has
> been reached in software on completely unmodded **x4** cards. The two axes are independent.
> This is settled from source code: no file in the shipping repository or in any of the twelve
> unreleased branches contains the strings "capacitor", "AC coupling", "solder" or any
> lane-width register, and a grep over the full history returns nothing. The experimental `Gen2`
> branch manipulates link **speed** only. See [PCIe subsystem](pcie-subsystem.md) and
> [PCIe Gen2](../unlock/pcie-gen2.md).

Partial or bridged solder work negotiates down to the next legal width (16 to 8 to 4 to 1) rather
than failing outright, which makes the reported lane count a direct diagnostic of solder quality.
One modder's progression across three cards was x4, then x8, then x16 as technique improved. An
x8 result after a cap mod means incomplete or bridged work, not a distinct hardware limit.

Rework technique, procedure, difficulty and the measured bandwidth results are on
[physical mods](../operations/physical-mods.md). The short version: leaded 60/40 solder and gel
flux, wick away all the factory lead-free solder first, a fine-point iron at about 380 °C is
sufficient and needs no preheating. The area is not cramped and one modder completed a card by
hand in about 20 minutes. Preheating the whole board in an oven was proposed and immediately
rejected; the dominant beginner failure mode is over-preheating with an IR stove plus hot air,
which bends the PCB, breaks internal traces and cooks ICs, producing defects that are extremely
hard to diagnose afterwards.

### VRM phases

The card uses **MP86957 smart power stages, rated 70 A output each**. Several DrMOS positions and
their output inductors are unpopulated. The in-channel conclusion is that the stock VRM can handle
about 500 W and that the unpopulated phases are redundancy rather than necessity. Measured
full-load draw is about 250 W, the stock limit.

> [!NOTE]
> **Populating the missing VRM phases does not help anything**
>
> Refuted from three directions. (a) The 8 GB card has *identical* power delivery and is
> entirely stable at 64 GB, while the 10 GB card at 80 GB is not. (b) The failing 80 GB cards
> never drew above about 80 W during the crashing workload, against a 250 W stock limit. (c)
> Electrically, the GPU does not sense VRM phase count, a VRM runs correctly under full load with
> half its MOSFETs fitted (the rest simply run hotter), and the PWM controller would additionally
> have to be reconfigured to drive any added phases, so soldering parts alone would not even
> raise the effective phase count. The 500 W figure is datasheet reasoning and has never been
> validated by an actual 500 W run.

Restoring full A100 TDP is expected to be a simple shunt mod rather than a firmware change, but
nobody has performed or measured one. A software or VBIOS route to a 400-500 W limit was proposed
as the alternative and also never achieved.

> [!NOTE]
> **Open problem**
>
> Does the 170HX need the medium SMD capacitors on the rear of the PCB near the core, roughly two
> per MOSFET on the left and right cap rows? Raised from a photograph by someone who had
> previously seen an RTX 2070 with two of them broken off, which wrecked its voltages; the dual
> placement is redundant but at least one must be present and working. This concerns local
> decoupling rather than VRM phases, so it is in tension with, not refuted by, the phase-count
> result above. Never checked on a 170HX. Next step: photograph the rear of a working 8 GB and a
> working 10 GB card and compare against the schematic's C-designator list.

### NVLink

The edge fingers are present. Whether the supporting ICs are populated is **open, and leans
depopulated**: a teardown and the one direct A100-versus-CMP board comparison both report parts
missing, against a schematic-based reading and a project VBIOS comparison table row saying the
PCB is fully populated; see [NVLink hardware](nvlink-hardware.md).
Independently of that, NVLink is fused off in silicon
(`FUSE_NVLINK_DIS`), there is no NVLink register in the `0x00823800`-`0x0082382C` feature-override
block, and no NVLink code exists in any branch. `PTOP_SCAL_NUM_NVLINK` `0x0002246c` still reads
`0xc`, because the die is a complete GA100. P2P is absent on this card.

By contrast the CMP 90HX shroud has an opening for an NVLink connector but the PCB lacks the
connector entirely, so the 170HX is comparatively generous here: the traces exist.

> [!NOTE]
> **Open problem**
>
> Can NVLink be brought up? The expectation in-channel was "will require PCB mods most likely,
> add missing components". It is complicated by the hypothesis that the GA100 interposer can
> itself carry eFuses, meaning the NVLink disconnect may be physical and unreachable by any laser
> or any solder. Nobody has imaged or probed an interposer. This is the least tractable hardware
> question on the card: it plausibly requires BGA-class rework on top of an unknown. See
> [NVLink](../frontier/nvlink.md) and [NVLink hardware](nvlink-hardware.md).

### The missing security module

A populated region on some A100 boards that is absent on the 170HX was identified as a **Microchip
CEC1712 security chip**, initially described as a "mystery FPGA that verifies the VBIOS" and
corrected the same day with a citation to NVIDIA's "Data Center CEC Defeaturing" end-customer
communication. The 170HX PCB has the pads but no chip. Not all A100s carry it either: an Ampere
revision shipped without it because of component shortages, and there is no way to tell from a
listing. The AMD MI50 has a comparable guard chip that only accepts official VBIOS images.
Confidence medium: no part marking was ever read off a board and no datasheet was produced.

### The Winbond chip in the circulating hardware-restore PDF

The Winbond BIOS chip that appears in the bill of materials of the circulating `a100-unlock.pdf` /
`cmp-170hx_a100_hardware-restore.pdf` is a **backup VBIOS chip** for recovering from a bad flash.
It is not part of the PCIe or memory unlock. The PDF's author stated that only the small components
on the PCIe lanes are needed for x16, and that everything else in that build was an attempt to
replicate an A100 under the hood. An experienced modder reading the same guide judged it to imply a
full BGA job requiring a stencil, which is why the guide over-scares people out of a mod that is
actually beginner-to-hobbyist level. Confidence medium: this rests on second-hand recollection of
the author's explanation, consistent with the author's own "only the lane parts are needed"
statement.

---

## Strap resistors

The board carries five strap resistor pairs in the top-left area near the decoupling capacitors:
ten pads for five straps, unmarked parts, typically 100 kΩ 0402, pulled to 0 V or 1.8 V. Each strap
is a resistor plus an empty pad, so moving the part between the two positions flips that strap bit.
Reading left to right on the PCB:

| Strap | Designators | Function |
|---|---|---|
| Strap1 | R986, R987 | `RAMCFG[1]` |
| Strap0 | R989, R990 | `RAMCFG[0]` |
| Strap3 | R993, R994 | `VGA_DEVICE` |
| Strap4 | R999, R1000 | `PCIE_CFG` |
| Strap2 | R1004, R1005 | `RAMCFG[2]` |

R1004 and R1005 are the two alternative footprints of the *same* strap position, not two separate
resistors. A sixth strap, `DEVID_SEL` at R240/R241, is named in the same source but has never been
physically located.

Stock patterns: the A100 40 GB and the 170HX 10 GB share `LLLLH`; the 170HX 8 GB is `HHLLH`. Strap
resistor 2 (`RAMCFG[2]`, rightmost) is H on both variants. The A100 schematic's GPU STRAP
CONFIGURATION table gives STRAP2/STRAP1/STRAP0 to `RAMCFG[4:0]` as `H, L, L` = `00100` = Samsung
HBM2 8 Gb 8Hi; `H, H, H` = `00111` = Hynix HBM2E 16 Gb 8Hi; `L, M, H` = `01010` = Micron HBM2E
16 Gb 8Hi, where M is a mid-level tri-state. Confidence medium: this is derived from VBIOS strap
tables and the A100 schematic rather than measured on a CMP.

> [!CAUTION]
> **Moving the memory strap resistors does not unlock VRAM, and one pattern bricks the card**
>
> Settled from four independent directions. (a) One tester permuted all 8 combinations of the last
> three straps on a 10 GB card with stock VBIOS and saw no change in reported VRAM; the pattern
> `LLHHH` bricked the system with no POST; physically removing three straps also changed nothing.
> (b) A second tester independently reported a strap flip "did not change a thing". (c) A 10 GB
> card re-strapped to `HHLLH`, the 8 GB stock pattern, still read
> `FBPA_CFG1_BROADCAST @ 0x009a0204 = 0x02449000`, the unmodified 10 GB value. (d) An unmodified
> 10 GB card reached the same 80 GB state as a re-strapped one, so no resistor change was ever a
> prerequisite. The maintainers accepted the debunk the same day it was demonstrated.

The reason it cannot work is in the source code: the shipping unlock selects memory geometry from
the **PCI device ID at driver runtime**, not from any strap. The patch computes
`devId = pGpu->idInfo.PCIDeviceID >> 16`; if `devId == 0x20C2` it writes `cfg1Value = 0x02779000`
and `lmrValue = 0x0000020B`, otherwise `0x02669000` and `0x0000028A`, via
`GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value)` and `GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue)`.
Re-strapping `RAMCFG` to the 8 GB pattern therefore cannot make the 64 GB path apply to a 10 GB
card. Only a device-ID change could, and the device ID is not on the `RAMCFG` straps.

One recorded oddity worth knowing when reading old captures: a mismatched strap change on a 10 GB
card produced `CFG1 = 0x4266a000` where `0x02669000` was expected, with only the first four FBPAs
active and one stack.

> [!NOTE]
> **Open problem**
>
> What do Strap3 (`VGA_DEVICE`, R993/R994) and Strap4 (`PCIE_CFG`, R999/R1000) actually do? The
> question was posed on 2026-07-26 after the strap map had been posted twice and went unanswered.
> A `VGA_DEVICE` strap could bear on display-output enablement and a `PCIE_CFG` strap on link
> configuration, both open problems. One accidental data point exists: a tester who intended to
> move R1004 in fact moved Strap4, taking the pattern from `LLLLH` to `LLLHH`, and reported no
> memory effect. Whether PCIe capability negotiation changed was never measured. Next step:
> repeat that experiment deliberately and capture `lspci -vv` LnkCap and LnkSta before and after.

> [!NOTE]
> **Open problem**
>
> Locate R240/R241 (`DEVID_SEL`) on the physical board. It matters because the device ID is what
> the shipping driver keys geometry off, and because `OPT_DEVID_SW_OVERRIDE_DIS` `0x00820584` = 1
> closes every software route. Tried and rejected: visual search near the R986-R1005 group,
> photographic search of the front side, and asking a commercial AI assistant, which fabricated a
> confident answer and then reversed itself when challenged. One researcher argues from designator
> numbering that R240/R241 cannot be near R986-R1005 and may be on the opposite PCB side, noting
> that A100 and 170HX front-side designators run below 500 while a Tesla V100 rear side runs above
> 500. Another insists the M-marked resistors they photographed are the right ones. Never settled.
> Best next step: a systematic high-resolution scan of the sub-500-designator side, cross-referenced
> against the leaked schematic's `DEVID_SEL` net rather than against designator adjacency.

---

## Memory package

| | 8 GB variant | 10 GB variant |
|---|---|---|
| Vendor and type | SK Hynix HBM2e | Samsung HBM2 |
| GA100 package option | 96 GB of faster Hynix HBM2e (as on the A100 80 GB) | 48 GB of Samsung HBM2 (as on the A100 40 GB) |
| Active stacks | 4 | 5 |
| Bus width | 4096-bit | 5120-bit |
| Unlock target | 4 × 16 GB = 64 GB, **stable** | 5 × 8 GB = 40 GB, **stable**; 80 GB unstable |

**This vendor split is the leading explanation for why 8 GB to 64 GB is stable while 10 GB to
80 GB is not.** The 8 GB card sits on the denser, faster Hynix package. Confidence high: asserted
independently by at least three participants over a month, never contradicted, backed by a GPU-Z
screenshot, and consistent with the observed stability split.

The full die would be 6144-bit across 24 FBPAs. That configuration has never been available on a
170HX.

> [!NOTE]
> **Open problem**
>
> Does the 8 GB card carry five stacks of 16 GB, or six stacks with four of twelve FBPs disabled?
> The circulating unlock guide states "HBM2e: 5 stacks × 16 GB = 64 GB physically (Hynix),
> software-locked to 8 GB". The proof-of-concept team states every GA100 package carries six
> physical stacks, 96 GB of Hynix HBM2e on the 8 GB variant, with two of the twelve FBPs fused off
> as defective and four total marked disabled, spread so that two stacks run a full 1024-bit
> interface and four run only 512 bits. Both agree the addressable target is 64 GB and both agree
> the memory is Hynix HBM2e. **Leaning to the six-stack account:** the measured 8 GB fuse mask
> leaves 16 of 24 FBPAs across 8 of 12 FBPs, and the 5 × 16 = 64 arithmetic conveniently matches
> the unlock target in a way that looks back-derived. But the "two stacks at 1024-bit, four at
> 512-bit" split does not obviously reconcile with the measured contiguous per-FBPA dead indices
> (2, 3, 8, 9, 12, 13, 22, 23), which read as four *whole* stacks lost. Decapping, an X-ray, or a
> per-stack bandwidth measurement would settle it.

HBM stacks are bonded to the **silicon interposer**, not to the PCB. A failed stack therefore
cannot be reflowed back into service. One member spent several hours at a range of temperatures
with a heat gun on several HBM2 GPUs with no success. HBM stacks also contain internal fuses, so
faulty dies can be permanently fused out inside the stack. Samsung HBM2 in particular is reported
not to tolerate voltage adjustment well, and nobody has identified the rail's controller or
measured its voltage.

---

## Floorsweep: what is fused off on each variant

The capacity and SM caps are burned into fuses and cannot be re-enabled in software. Full detail is
on [fuses and OTP](fuses-and-otp.md); the board-relevant summary:

| Register | 8 GB (`0x20C2`) | 10 GB (`0x2082`) |
|---|---|---|
| `FUSE_FBP_DISABLE` `0x00820364` | `0x00000852` (8 of 12 FBPs active) | `0x00000009` or `0x840` (10 of 12 active) |
| `FUSE_FBPA_DISABLE` `0x00820368` | `0x00c0330c` (16 of 24 active) | `0x000000c3` or `0xc03000` (20 of 24) |
| `FUSE_FBIO_DISABLE` `0x0082036c` | `0x00c0330c` | `0xc03000` |
| `ROP_L2_DISABLE` `0x008202C4` | | `0xc03000` |
| `FBHUB_NUM_ACTIVE_LTCS` `0x00100800` | `0x10` (16) | `0x14` (20) |
| `FBPA_NUM_ACTIVE` `0x009a0164` | `8` | `0xa` |
| Dead per-FBPA indices | 2, 3, 8, 9, 12, 13, 22, 23 | 0, 1, 6, 7 |

Floorswept partitions read back `0xbadf20xx` (for example fbpa02 `0xbadf2011`, fbpa08 `0xbadf2014`,
fbpa12 `0xbadf2016`, fbpa22 `0xbadf201b`) while live ones read `0x00001000`.

Two points that matter when comparing dumps across cards:

- **There are no real silicon defects, only an active disable mask.** The corresponding DEFECTIVE
  registers all read zero: `FBP 0x8205CC`, `FBPA 0x8205D0`, `FBIO 0x8205D4`, `ROP/L2 0x8205E8`.
  Writing 0 to the DISABLE registers does not move them.
- **The specific mask varies per die; the totals do not.** Observed FBP masks on 10 GB cards
  include `0x840` (FBP6, FBP11) and `0x00000009` (FBP0, FBP3): different indices, both leaving 10
  of 12. GPC masks observed include `0x13`, `0x15`, `0x25`, `0x45`, `0x85` and `0xa8`, all leaving 5 GPCs
  and all enumerating 70 SM. Expect these to differ between cards without it indicating a different SKU or different
  unlock potential.

The compute side is at its fuse floor on both variants: 5 active GPCs, 35 active TPCs, 70 SM at
compute capability 8.0, which is 4480 CUDA cores. Every per-GPC `CTRL_OPT` register
(`0x00820838 + i*4`) and every `RECONF_OVR` (`0x00820A40 + i*4`) reads `0x00000000`,
`OPT_GPC_DEFECTIVE 0x008205C4` = 0, and the fuse floor computed from `OPT|RECONFIG` equals the
enumerated count exactly. Against a full GA100 (8 GPC × 8 TPC = 64 TPC = 128 SM) the part ships
54.7 % of the die's SMs, and none of the missing SMs are recoverable.

The die itself is a complete GA100 by every scaling register:

| Register | Value | GA10x control card |
|---|---|---|
| `PTOP_SCAL_NUM_GPCS` `0x00022430` | `8` | `6` |
| `PTOP_SCAL_NUM_TPC_GPC` `0x00022434` | `8` | `4` |
| `PTOP_SCAL_NUM_FBPS` `0x00022438` | `0xc` (12) | `4` |
| `PTOP_SCAL_NUM_FBPAS` `0x0002243c` | `0x18` (24) | `4` |
| `PTOP_SCAL_NUM_LTCS` `0x00022454` | `0x18` (24) | `8` |
| `PTOP_SCAL_FBPA_PER_FBP` `0x00022458` | `2` | `1` |
| `PTOP_SCAL_NUM_NVLINK` `0x0002246c` | `0xc` (12) | `0` |
| `PTOP_FS_STATUS` `0x00022470` | `0x3f` | |
| `PMC_BOOT_0` `0x00000000` | `0x170000a1` (`0x170` = GA100, rev a1) | `0xb74000a1` |

> [!NOTE]
> **Register-address correction of record**
>
> `0x00820C14` is `STATUS_OPT_FBIO`, **not** `STATUS_OPT_FBPA`. The FBPA floorsweep status is at
> `0x00820C18`. The Pascal-era FBPA fuse address `0x00021C14` returns BADF on GA100. The
> clean-room `probe.sh` carries both entries with the correction annotated inline, so the tooling
> itself preserves the history.

---

## Device-ID fuses

Both 170HX PCI IDs are burned on the same die.

| Fuse | Address | 10 GB reading | 8 GB reading |
|---|---|---|---|
| `OPT_PCIE_DEVIDA` | `0x008204d8` | `0x00002082` | `0x000020c2` (disputed, see below) |
| `OPT_PCIE_DEVIDB` | `0x0082056c` | `0x000020c2` | `0x000020c2` |
| `OPT_DEVID_SW_OVERRIDE_DIS` | `0x00820584` | `0x00000001` | `0x00000001` |
| `OPT_INTERNAL_SKU` | `0x008203f4` | `0x00000000` | `0x00000000` |
| `OPT_SKU_ID` | `0x00821060` | `0x00000068` | `0x00000080` |
| `OPT_SLT_REV` | `0x008204bc` | `0x00000001` | |
| `FUSE_FB_FALCON_PRI_DIS` | `0x00820670` | `0x00000000` | |
| `FUSE_OPT_SECURE_GSP` | `0x0082074c` | `0x00000001` | |
| `FUSECTRL` | `0x00820000` | `0xe0040000` | |

`FUSE_FB_FALCON_PRI_DIS` = 0 means the Falcon can still reach FB PRI registers, which is a
precondition for the memory unlock. `FUSE_OPT_SECURE_GSP` = 1 means GSP debug is disabled.

**The primary PCIe device ID is fused into the die and cannot be changed by VBIOS or by strap
resistors; only the subsystem ID is VBIOS-settable.** Selection between DEVIDA and DEVIDB is
strap-latched (`DEVID_SEL`), and as of 2026-07-27 no software-only way to change it had been found.
A VBIOS declaring an alternate device ID only means that VBIOS is *permitted to run* on a card with
that ID; it cannot rebrand the card.

> [!NOTE]
> **Open problem**
>
> Device-ID fuse values on an 8 GB card. A 2026-07-19 BAR0 probe of a `0x20c2` card reports
> DEVIDA **and** DEVIDB both `0x000020c2`. A 2026-07-22 PCIe firmware analysis states DEVIDA
> `0x2082`, DEVIDB `0x20C2`, and 2026-07-24/25 dumps on 10 GB cards agree with the latter. Neither
> has been retracted, and the SKU behind the second figure is not stated. Either the 8 GB card
> genuinely has both fuses at `0x20c2`, which is what a separate source independently claims, or
> one dump is mislabelled. Note that the first reading breaks the working `DEVIDB = DEVIDA | 0x40`
> hypothesis, which otherwise holds on the 170HX (`0x2082`/`0x20c2`) and on a GA10x control card
> (`0x2484`/`0x24c4`). A single dump of both fuses from one confirmed 8 GB card, with `lspci -nn`
> in the same paste, would settle it.

> [!NOTE]
> **`20B2` is not a CMP 170HX device ID**
>
> It appeared in an early message and was corrected in-channel on 2026-06-29 as a typo for
> `2082`. It also appears inside a speculative re-fusing proposal as a *target* A100 ID, which is
> a different usage. The two 170HX IDs are `0x20C2` (8 GB) and `0x2082` (10 GB).

---

## Revision differences

There is no single "revision" axis on this card. Four independent things vary.

| Axis | Values seen | Does it matter? |
|---|---|---|
| Silicon revision | `rev a1` on every card (`PMC_BOOT_0` = `0x170000a1`) | No variation observed |
| PCB silkscreen trailing field | `180-11001-DAAA-B15`, `180-11001-DAAA-B35`, `180-11001-DAAA-045` | Same board family; no functional difference established. B15 and B35 both took the x16 capacitor mod with identical results |
| VBIOS revision | `92.00.67.00.01` (8 GB production), `92.00.6D.00.09` (2021-11-01, 300 W, no memory OC), `92.00.6D.00.0A` (2022-04-07, 300 W, 432 MHz memory field), `92.00.66.00.02` (10 GB production) | **Not for the unlock.** Yes for power limit and memory clock |
| Per-die floorsweep mask | FBP and GPC disable masks differ between dies of the same SKU | No: totals are constant |

**VBIOS version makes no difference to whether the unlock works.** Four cards across two hosts, two
on each of `92.00.67.00.01` and `92.00.6D.00.0A`, showed identical unlock and Gen2 results, with
identical Board PN `900-11001-0108-000`, GPU PN `20C2-105-A1` and subsystem `0x158510DE`. Writing
"8 GB cards carry `92.00.6D.00.0A`" as a blanket statement is wrong: both versions are in the field.
Full version detail is on [VBIOS](vbios.md).

One supplier-side wrinkle, recorded because it would show up as an apparent hardware difference: a
single commercially interested source claimed to hold "two kinds of VBIOS for 170hx, one has higher
bandwidth", with no version strings and no figures given. It is at least consistent with both the
364 MHz and 432 MHz memory-field images being in circulation. Unresolvable from the record.

> [!NOTE]
> **Open problem**
>
> Do power-raised "unlock BIOS" cards blow a rear-board capacitor after prolonged mining? One
> owner relayed that the seller who supplied their cards had this happen repeatedly and showed a
> blown board, with the suspected parts narrowed to two components on the rear of an 8 GB board
> believed to be capacitors. The same seller ran cards at around 56 °C, raising the suspicion of
> monitoring the wrong sensor and overheating the VRM while mining bandwidth-bound coins. An
> experienced long-time owner said they had never seen this failure and doubted it. No photograph
> of the failed component and no measurement were produced. A photograph of a failed board with
> the designator readable, plus a thermocouple reading on the VRM under a bandwidth-bound load,
> would settle it.

---

## What the PCB does and does not tell you

**It tells you** exactly which features were removed and, thanks to the matching A100 schematic,
exactly which parts would restore them. That is how the lane-width mod was derived: designator
range, package, value and dielectric all came off page 3 of the schematic rather than from guesswork.

**It does not tell you** anything about the capacity or compute limits. Those live in three layers,
and only one of them is on the board:

| Layer | Where | Movable? |
|---|---|---|
| PCB-level physical omissions | The board | Yes, by soldering, but only for PCIe lane width |
| VBIOS firmware | The SPI ROM, inside the MAC range | No, without csecret(2) |
| OTP fuses | The die | No |

The unlock that actually shipped moves none of them. It overrides register state at runtime, from
the driver, with no hardware change at all. Across all six shipping patches the only registers
written in the `0x0082xxxx` fuse space are `0x00823804` (FEAT PLM), `0x0082381C` (SS0 =
`0x88888888`) and `0x00823820` (SS1 = `0x00000008`). No floorsweep register (`0x00820350`,
`0x00820364`, `0x00820368`, `0x0082036C`, `0x008202C4`, `0x00820C1C`) is written anywhere. **The
unlock reprograms memory geometry; it does not and cannot revive fused-off units.**

### Board-level dead ends

Do not retry these without new information. The full list is on
[dead ends](../history/dead-ends.md).

| Attempt | Why it is dead |
|---|---|
| Memory strap resistors unlock VRAM | Exhaustive permutation of all 8 combinations produced no capacity change; `LLHHH` bricked the system; removing three straps changed nothing |
| Re-strapping `RAMCFG` to the 8 GB pattern makes the 64 GB path apply to a 10 GB card | The driver selects geometry from the PCI device ID, not from any strap |
| Adding the missing VRM FETs, capacitors, coils and inductors stabilises 80 GB | Refuted three ways (see VRM section above) |
| A waterblock stabilises 80 GB, because the retail A100 80 GB has no IHS while the 170HX does | Never tested, superseded by the memory-refresh explanation, and undercut by the measurement that failing cards draw only about 80 W: they are not thermally limited |
| Hardware-modding the HBM voltage rail as a stability fix | Nobody executed it, no controller identified, no rail voltage measured. Samsung HBM2 reportedly does not tolerate it, and faulty HBM can be permanently fused out inside the stack |
| Reflowing a failed HBM2 stack with a heat gun | Stacks are bonded to the interposer, not the PCB. Tried on several HBM2 GPUs over several hours with no success |
| A `strap5` resistor switches between the two fused device IDs | The strap was never located, and the five-strap map published a week later enumerates exactly five straps with no strap5 |
| Clearing `CTRL_OPT` to recover extra SMs | All eight per-GPC `CTRL_OPT` registers already read `0x00000000` and the enumerated 35 TPC already equals the fuse floor. The GPC disable is in OTP at `0x00820350`, not in `CTRL_OPT` |
| A BGA reball on a CMP-class card | Attempted first-hand and failed: `nvidia-smi` hangs on access despite MODS reporting no errors afterwards. Worth knowing as a failure *mode*: a MODS-clean card can still hang the driver |
| Preheating the whole board in an oven before the capacitor rework | Rejected as a beginner trap; over-preheating bends the PCB, breaks internal traces and cooks ICs |
| Applying 3.3 V to a "manufacturing_mode" pin found on some cards | Observed on real hardware but never characterised, never pursued to a result |

> [!WARNING]
> **Fabricated board topology reads exactly like real board topology**
>
> Recorded verbatim as a cautionary data point. A commercial AI assistant, asked where R240/R241
> and the board crystals are, confidently placed R240/R241 "adjacent to the other high-value 100k
> strap resistors (such as R985-R1016)", described them as 100 kΩ 0402 parts tied to `FS_OVERT`
> and `PCIE_CFG`, and named Y200 (27.000 MHz) and Y201 (100.000 MHz low-jitter differential) on
> "Page 5: CLOCK GENERATION / CRYSTALS" of a PG100/PG101 schematic. When challenged on
> reference-designator logic it reversed itself completely. None of it was verifiable. Treat any
> designator, page reference or net name that is not read off a photograph or the schematic itself
> as unverified.

---

## Related pages

- [Identify your card](../start/identify-your-card.md): the short version of the table above
- [VBIOS](vbios.md): ROM structure, per-batch versions, and the seven-byte restriction
- [Fuses and OTP](fuses-and-otp.md): the floorsweep and device-ID fuses in full
- [Memory subsystem](memory-subsystem.md): FBPAs, stacks, CFG1 and LMR
- [PCIe subsystem](pcie-subsystem.md) and [physical mods](../operations/physical-mods.md): the
  lane-width capacitor mod end to end
- [Power delivery](power-delivery.md) and [power and PSU](../operations/power-and-psu.md)
- [Cooling](../operations/cooling.md): teardown order, waterblocks, air retrofits
- [NVLink hardware](nvlink-hardware.md)
- [GA100 silicon](ga100-silicon.md)
