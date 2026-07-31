# Identify your card

**What this page covers.** How to determine exactly which CMP 170HX you have, and therefore which
unlock profile applies. The `lspci` device IDs, the subsystem IDs, board and GPU part numbers,
what `nvidia-smi` reports before and after the unlock, the die markings under the heatsink, the
register-level fingerprints that separate the two SKUs, and the exact profile-detection ladder
`install.sh` runs at install time. Ends with a decision table from what you observe to what you get.

**The key result, in one line.** There are two 170HX SKUs and they unlock to different capacities:
the **8 GB card, PCI ID `10de:20c2`, unlocks to 64 GB**, and the **10 GB card, PCI ID `10de:2082`,
unlocks to 40 GB**. Never mix these up. A third ID, `10de:20b0`, is detected by the installer but is
**not** a 170HX and does not unlock. Everything else on this page is corroboration for that single
distinction.

The fastest possible answer:

```bash
lspci -nn | grep -i nvidia
```

If the bracketed pair reads `[10de:20c2]` you have an 8 GB card and you are going to 64 GB. If it
reads `[10de:2082]` you have a 10 GB card and you are going to 40 GB.

---

## 1. `lspci`: the authoritative identification

Both SKUs enumerate under the same human-readable name, so the name alone tells you nothing. The
bracketed vendor:device pair is what matters.

```bash
lspci -nn | grep -i '10de:20c2\|10de:2082\|10de:20b0'
```

Expected output on an 8 GB card:

```text
0a:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
```

Expected output on a 10 GB card:

```text
81:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:2082] (rev a1)
```

Note the class: it is a `3D controller`, not a `VGA compatible controller`, because the card has no
display outputs. `rev a1` is the GA100 silicon revision and is the same on both.

For the subsystem ID, which is the second independent confirmation, ask for verbose output:

```bash
sudo lspci -nn -vv -s 0a:00.0 | head -8
```

```text
0a:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
        Subsystem: NVIDIA Corporation GA100 [CMP 170HX] [10de:1585]
        Control: I/O- Mem+ BusMaster+ SpecCyc- MemWINV- VGAMon- FastB2B- DisINTx+
        Capabilities: [60] Power Management version 3
```

Subsystem `10de:1585` is the 8 GB card. Subsystem `10de:1557` is the 10 GB card. The subsystem ID is
the one identifier on this card that **is** VBIOS-settable, so treat it as corroboration rather than
proof. The primary device ID is fused into the die: `FUSE_DEVID_SW_OVR_DIS` (`0x00820584`) reads 1
on every card probed, so software cannot override it, and strap resistors do not change it either.

Sysfs gives the same two values without root:

```bash
BDF=0000:0a:00.0
cat /sys/bus/pci/devices/$BDF/device            # 0x20c2
cat /sys/bus/pci/devices/$BDF/subsystem_device  # 0x1585
```

---

## 2. `nvidia-smi`: reported memory and part numbers

`nvidia-smi` does not report a useful product name. Both SKUs come up as
**`NVIDIA Graphics Device`**, and Linux monitoring tools showing a generic "NVIDIA display device"
entry are behaving normally. The size field and the part numbers are the useful ones.

```bash
nvidia-smi --query-gpu=name,memory.total,pci.device_id,pci.sub_device_id,vbios_version \
           --format=csv
```

Stock 8 GB card:

```text
name, memory.total [MiB], pci.device_id, pci.sub_device_id, vbios_version
NVIDIA Graphics Device, 8192 MiB, 0x20C210DE, 0x158510DE, 92.00.67.00.01
```

Stock 10 GB card:

```text
NVIDIA Graphics Device, 10240 MiB, 0x208210DE, 0x155710DE, 92.00.66.00.02
```

After a successful unlock the same command reports **65536 MiB** on the 8 GB card and
**40960 MiB** on the 10 GB card. Nothing else in the output changes.

Board and GPU part numbers are in the full query:

```bash
nvidia-smi -q | grep -E 'Board Part Number|GPU Part Number|VBIOS Version|Bus Id'
```

```text
    VBIOS Version                         : 92.00.6D.00.0A
    Board Part Number                     : 900-11001-0108-000
    GPU Part Number                       : 20C2-105-A1
```

> [!CAUTION]
> **A mismatched `nvidia-smi` invalidates every reading on this page**
>
> NVML refuses to talk across driver versions, so a `memory.total` read through a mismatched
> `nvidia-smi` binary is meaningless. One multi-day measurement series was invalidated exactly this
> way, running a 580.159.03 userspace against a different kernel module build. If `nvidia-smi`
> prints "driver/library version mismatch", fix that before trusting anything it says. See
> [Troubleshooting](../procedures/troubleshooting.md#version-mismatch).

---

## 3. Physical markings

If the card is out of the machine, or the cooler is off, three markings are readable.

| Marking | 8 GB card | 10 GB card |
|---|---|---|
| ASIC (die) marking | `GA100-105F-A1` | `GA100-105A-A1` |
| Board part number | `900-11001-0108-000` | `900-11001-0105-000` |
| GPU part number | `20C2-105-A1` | `2082-105-A1` |
| PCB silkscreen, above the gold fingers | `180-11001-DAAA-B15` (also seen: `180-11001-DAAA-B35`, `180-11001-DAAA-045`) | same board family |
| Board ID | not recorded | `0x8100` |

The two silkscreen strings are the same board family; the trailing field is a revision or variant
code, and both have been photographed under a USB microscope. The 170HX package legend also reads
`NVIDIA / B KR 2120A1 / TBSG42.M0W e1`. For contrast, a retail Tesla A100 40 GB die photographed
alongside a 170HX is marked `GA100-883AA-A1`, so the `-105x-` middle field is what says "CMP".

> [!WARNING]
> **Experimental: the 10 GB die marking is not photographed here**
>
> `GA100-105F-A1` on the 8 GB card is confirmed by a teardown photograph and by the TechPowerUp
> database, two independent sources agreeing on the variant string. `GA100-105A-A1` for the 10 GB
> card comes from the documented specification table and is not independently photographed anywhere
> in this corpus. Reading the die also means removing the cooler, so this is the least practical
> identification route on the page: use `lspci`.

The board and GPU part numbers are the more useful physical identifiers because `nvidia-smi` reports
them without disassembly, and they were identical across all four 8 GB cards examined on two hosts.

---

## 4. VBIOS versions, and why they do not decide anything

```bash
nvidia-smi --query-gpu=vbios_version --format=csv,noheader
```

| VBIOS | SKU | Build date | Notes |
|---|---|---|---|
| `92.00.67.00.01` | 8 GB (`0x20C2`, subsys `0x1585`) | 2021-05-14 | Stock production image, 364 MHz memory field, 250 W |
| `92.00.6D.00.0A` | 8 GB | 2022-04-07 | The 300 W "OC mining" image, 432 MHz memory field, permits a core-clock offset |
| `92.00.6D.00.09` | 8 GB | 2021-11-01 | Carries the 300 W limit but no memory overclock. Not in the TechPowerUp collection. *(Confidence: medium-high; one researcher holding the file.)* |
| `92.00.66.00.02` | 10 GB (`0x2082`, subsys `0x1557`) | 2021-04-23 | The only 10 GB image |

**VBIOS version makes no difference to whether the unlock works.** This was asserted directly by a
core researcher and independently corroborated by a four-card, two-host comparison in which two
cards on `92.00.67.00.01` and two on `92.00.6D.00.0A` produced identical unlock and Gen2 results.
See [VBIOS](../hardware/vbios.md) for the full image inventory, including which circulating images
are mislabelled and which must never be flashed.

---

## 5. Register-level fingerprints

These require BAR0 access and are for confirming an ambiguous case or cross-checking a probe dump,
not for routine identification.

| Register | 8 GB (`0x20C2`) | 10 GB (`0x2082`) |
|---|---|---|
| `PMC_BOOT_0` | `0x170000a1` | `0x170000a1` (every GA100) |
| `FUSE_PCIE_DEVIDA` `0x008204d8` | `0x000020c2` | `0x00002082` |
| `FUSE_PCIE_DEVIDB` `0x0082056c` | **disputed**: one 2026-07-19 probe of a `0x20c2` card reads `0x000020c2`; the `DEVIDB = DEVIDA + 0x40` rule predicts `0x00002102` (see [board and variants](../hardware/board-and-variants.md)) | `0x000020c2` |
| `FUSE_SKU_ID` `0x00821060` | `0x80` | `0x68` |
| `OPT_GPC_DISABLE` `0x00820350` | **per-die, not per-SKU: do not use for identification** | **per-die, not per-SKU: do not use for identification** |
| `NV_PTOP_FS4` `0x0002241c` | `0x00000000` | `0x00000081` |
| Stock CFG1 `0x009a0204` | `0x02449000` | `0x02449000` (identical on both) |
| Stock LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| Stock per-FBPA `CSTATUS_RAMAMOUNT` | `0x200` (512 MiB) | `0x200` (512 MiB) |
| HBM `MRS_2` `0x009a0334` | `0x00200019` | `0x002000cf` |
| HBM `MRS_WL_RL` `0x009a0338` | `0x003000eb` | `0x003000ea` |
| `FBPA_HBM_CFG0` `0x009a038c` | `0x000000a7` | `0x000000a7` |

Note that **stock CFG1 is `0x02449000` on both SKUs**, so CFG1 alone cannot tell you which card you
have; the LMR can. `NV_PTOP_FS4` is the cleanest single-register split, and bit 0 is `GEN2_PCIE` with
bit 7 `GEN2_PCIE_SPEED`, which makes the 8 GB card's `0x00000000` reading the more interesting half.

> [!WARNING]
> **`OPT_GPC_DISABLE` is not a SKU fingerprint**
>
> The GPC floorsweep mask varies per die, not per SKU. Values observed across 170HX cards of both
> SKUs include `0x13`, `0x15`, `0x23`, `0x25`, `0x45`, `0x85`, `0xa8` and `0xd0`, and all of them
> still enumerate 70 SMs. Never hard-code a floorsweep value or infer a SKU from one. Use
> `FUSE_SKU_ID` `0x00821060` (`0x80` on the 8 GB card, `0x68` on the 10 GB card) instead.

Structural differences that follow from the SKU:

| Property | 8 GB card | 10 GB card |
|---|---|---|
| Bus width | 4096-bit | 5120-bit |
| HBM stacks | **Unresolved.** A delidded 8 GB card visibly showed six stacks; a die-shot source claims two of the six are dummies. Both readings are compatible with the measured bus width, so bus width cannot settle it | 5 reported |
| Active FBPAs | 16 of 24 (8 FBPs) | 20 of 24 (10 FBPs) |
| Per-FBPA capacity, stock | 512 MiB (`_CSTATUS_RAMAMOUNT` = `0x200`, CFG1 tier `0x44`) | 512 MiB (identical) |
| Per-FBPA capacity, unlocked | 4096 MiB (`0x1000`, tier `0x77`) | 2048 MiB (`0x800`, tier `0x66`) |
| Memory clock | **unresolved**, see the box below | 1215 MHz, current equals max, no headroom |
| Unlocks to | **64 GB** | **40 GB** |

> [!NOTE]
> **Open problem: the stock 8 GB memory clock**
>
> The stock 8 GB memory clock is unresolved: 1458 MHz (one sweep and TechPowerUp), 1728 MHz
> (`nvidia-smi -q` Supported Clocks, noted as "432 MHz × 4"), 1890 MHz (`nvtop` during an
> unlocked 64 GB `gpu_burn` at 300 W). 1215 MHz is the 10 GB card and is solid. The plausible
> reconciliation, 1458 stock / 1728 OC VBIOS / 1890 overclocked OC VBIOS, is unproven, and the
> 1728 MHz figure is separately attributed to FWSEC devinit at POST rather than to the OC VBIOS,
> since no Memory Clock Table appears in any of the eight dumped ROMs. A raw FBPA PLL read would
> settle it.

Which specific FBPs are floorswept varies per card. One 10 GB dump reads `FBP_DEFECTIVE` = `0x840`
(FBP6, FBP11), the same pattern as the A100 PCIe 40/80 GB parts, but the card identity behind that
reading is disputed (one source attributes it to an 8 GB card), and a separate 10 GB probe reads
`OPT_FBP_DISABLE` = `0x00000009` (FBPs 0 and 3). Medium confidence, single dump. Every clean unlock
fire on a 10 GB card reports `CSTATUS=20/24`.
See [Memory subsystem](../hardware/memory-subsystem.md) and
[Fuses and OTP](../hardware/fuses-and-otp.md).

---

## 6. The third device ID: `10de:20b0`

`install.sh` greps for three IDs:

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

but the in-driver gate `_kgspSec2PostblTimingEnabled()` accepts **only** `0x20C2` and `0x2082`. A
`20b0` card therefore installs cleanly and never unlocks. The installer says so and continues:

```text
! In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
! This card reports 0x20b0; install will continue, but unlock may not activate.
```

`0x20b0` is the A100 SXM4 40 GB device ID and is also carried by an A100 engineering sample
(8192 MB, 2048-bit, 4096 CUDA cores, Samsung 8Hi HBM2). The README's older
"unlock is `0x20C2`-gated" phrasing is stale: `0x2082` has been a first-class target since the
"Unlock isn't gated anymore" commit.

Two related notes:

* Every `SEC2_DEBUG` print in patches 0001 and 0002 is gated on the same two device IDs, so a stock
  build on a `20b0` card should print **nothing at all** in `dmesg`. One report of SEC2_DEBUG lines
  on a `20b0` engineering sample is unresolved and is most likely a modified build or a second card
  in the same host.
* `0x20BB` is the Drive A100 / PG199 part (32768 MiB stock). The branch named `PG199` adds nothing at
  all: its tree is byte-identical to the `ecc` branch, its commit list is empty, and nothing anywhere
  in it mentions PG199, `0x20BB` or A100D. It adds no detection, contains no A100D support, and does
  not change the `lspci` grep or the in-driver gate. There is no PG199 unlock.

See [Troubleshooting](../procedures/troubleshooting.md#device-id-20b0).

---

## 7. The install-time profile detection ladder

`install.sh` picks a profile in step 3 of 6. Either you pass `--profile`, or `detect_card_profile()`
reads reported memory and buckets it:

```bash
nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1
```

| Reported `memory.total` | Selected profile | Why the window exists |
|---|---|---|
| `>= 60000` MiB | `8gb` | reinstall on an **already unlocked** 64 GB card |
| `35000`-`59999` MiB | `10gb` | reinstall on an already unlocked 40 GB card |
| `7680`-`8704` MiB | `8gb` | stock 8 GB card (8192 MiB) |
| `9728`-`10752` MiB | `10gb` | stock 10 GB card (10240 MiB) |
| anything else | **fatal** | prints `unknown:<mib>`, then `Could not detect 8GB vs 10GB card. Re-run with --profile=8gb or --profile=10gb` |

The banner then prints one of:

```text
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
==> Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)
```

> [!WARNING]
> **Auto-detection is unsafe on mixed-GPU hosts**
>
> `detect_card_profile()` takes the **first GPU in `nvidia-smi` order**, which is not necessarily
> the CMP that `lspci` found. A host with an RTX 3080 10 GB alongside an 8 GB CMP 170HX was
> reproduced by at least two people detecting "10GB" from the 3080, and a separate report has a
> CMP 50HX misdetected as a 10 GB 170HX. If the first GPU reports a size outside all four windows,
> a 24 GB card for example, the install dies outright.
>
> Always pass `--profile` explicitly on any host with more than one NVIDIA card:
>
> ```bash
> sudo ./install.sh --profile=8gb     # 8 GB physical card  -> 64 GB
> sudo ./install.sh --profile=10gb    # 10 GB physical card -> 40 GB
> ```

After installing, the recorded profile is readable at:

```bash
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile      # 8gb or 10gb
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry   # 64GB or 40GB
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
```

Nothing in the kernel modules reads any of these three files. They exist for humans and for
`verify.sh`, which maps `20c2 -> 8gb -> 65536 MiB` and `2082 -> 10gb -> 40960 MiB`. Note that
`verify.sh` does **not** ship on `master`: it exists only on the `multiple-cards`, `Gen2`, `far` and
`deced` branches, and it derives that mapping from `lspci`, reading `card_profile` and
`unlock_geometry` only to print them.

---

## 8. Decision table

| What you observe | Card | Profile | Post-unlock `nvidia-smi` | CFG1 / LMR written |
|---|---|---|---|---|
| `[10de:20c2]`, subsystem `10de:1585`, 8192 MiB | 8 GB CMP 170HX | `8gb` | **65536 MiB** | `0x02779000` / `0x0000020B` |
| `[10de:2082]`, subsystem `10de:1557`, 10240 MiB | 10 GB CMP 170HX | `10gb` | **40960 MiB** | `0x02669000` / `0x0000028A` |
| `[10de:20c2]`, already reporting 65536 MiB | 8 GB, already unlocked | `8gb` | unchanged | reapplied each boot |
| `[10de:2082]`, already reporting 40960 MiB | 10 GB, already unlocked | `10gb` | unchanged | reapplied each boot |
| `[10de:20b0]` | A100 SXM4 40 GB or an A100 engineering sample | installs, warns | **no change** | none; the in-driver gate rejects it |
| `[10de:20bb]`, 32768 MiB | Drive A100 / PG199 | not detected at all | **no change** | none; no PG199 unlock exists |
| Any other `10de:` ID | Not a 170HX | installer exits | n/a | n/a |
| `[10de:2082]` forced to the 80 GB geometry | 10 GB, over-provisioned | archived `80` branch | reports 81920 MiB | `0x02779000` / `0x0000028A` |

> [!CAUTION]
> **The 80 GB row is not a supported option**
>
> The archived `80` branch programs the 10 GB card to report 81920 MiB, but the card is unusable
> above roughly 40 GB: hangs, Xid 154, and burn-in errors within minutes. It is presented as
> unstable or rejected in every source that mentions it, and it is power-limit independent. What it
> actually programs is a three-way-inconsistent combination (CFG1 `0x02779000` with LMR
> `0x0000028A` and an 80 GiB `fb_length`), which is itself the likely cause. See
> [80 GB](../frontier/80gb.md).

---

## 9. If you still are not sure

Run all three checks and compare. They should agree; if they do not, the `lspci` device ID wins,
because it is fused into the die and cannot be changed by VBIOS or straps.

```bash
# 1. Fused device ID: authoritative
lspci -nn | grep -iE '10de:(20b0|20c2|2082)'

# 2. Subsystem ID and part numbers: corroboration (subsystem is VBIOS-settable)
nvidia-smi --query-gpu=pci.sub_device_id,vbios_version --format=csv,noheader
nvidia-smi -q | grep -E 'Board Part Number|GPU Part Number'

# 3. Reported size: what the installer's auto-detection will see
nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits
```

A card that enumerates and runs on an unpatched stock driver, reporting `NVIDIA Graphics Device` and
compute capability 8.0, is a healthy 170HX regardless of how filthy it looks. Ex-mining cards arrive
with heavy dust, rusted brackets and salt crust inside the heatsinks, and cosmetic condition has not
predicted unlock failure: one visibly filthy card unlocked to 64 GB cleanly on the first try.

---

## Related pages

* [What is this card](what-is-this-card.md): the orientation-level overview
* [Risks](risks.md): read before you start
* [Quick start](quick-start.md) and [Install](../procedures/install.md)
* [Verify](../procedures/verify.md): confirming the unlock actually landed
* [Multi-GPU](../procedures/multi-gpu.md): why `head -1` in the installer matters on rigs
* [Board and variants](../hardware/board-and-variants.md): the physical board in detail
* [VBIOS](../hardware/vbios.md): every known image and what each one changes
* [Memory geometry](../unlock/memory-geometry.md): what CFG1 and LMR actually do
* [Fuses and OTP](../hardware/fuses-and-otp.md): the cross-variant fuse table
* [Glossary](glossary.md)
