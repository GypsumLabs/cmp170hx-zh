# PCIe subsystem

**What this page covers**: the physical and firmware state of the CMP 170HX's PCIe interface as
it ships. The two restrictions the card leaves the factory with, the fuse and DevInit evidence
behind the speed cap, the depopulated AC-coupling capacitors behind the width cap, the exact
register and `lspci` state of a stock card, and the platform-level confounds that get mistaken
for either. The software defeat of the speed cap lives on [Gen2 unlock](../unlock/pcie-gen2.md);
the soldering work that defeats the width cap lives on
[physical mods](../operations/physical-mods.md).

## The headline: two caps, two mechanisms, two fixes

A stock CMP 170HX trains at **PCIe Gen1 (2.5 GT/s) by x4**. Those are two entirely separate
restrictions that happen to coexist on the same board, and defeating either one does nothing
whatsoever for the other.

| | Speed cap | Width cap |
|---|---|---|
| Observed state | 2.5 GT/s (Gen1) | x4 trained, x16 advertised |
| Mechanism | OTP fuses plus a signed DevInit table, enforced in firmware | 12 of 16 lanes ship with their AC-coupling capacitors depopulated |
| Where it lives | Silicon and SPI flash | The PCB |
| Defeated by | A driver patch on unreleased branches (Gen2 only) | Hand-soldering 24 × 0402 capacitors |
| Status | Gen2 reached in software 2026-07-24, **not shipped**; Gen3 and Gen4 unreached | Reproduced by multiple independent modders since April 2026 |
| Does it change the other? | No. A Gen2-patched unmodded card is Gen2 x4. | No. A fully modded unpatched card is Gen1 x16. |

The clearest single proof that the two are independent: a stock, never-soldered 8 GB card running
the Gen2 branch reports `LnkCap: Port #0, Speed 5GT/s, Width x16` while `LnkSta` reads
`Speed 5GT/s, Width x4 (downgraded)`. The capability register says x16; the trained link says x4.
Nothing in software can close that gap, because there is no electrical path on 12 of the lanes.

!!! warning "Experimental"
    Everything on this page about Gen2 describes unreleased branch code. Shipping `master`
    contains no PCIe patch of any kind. See [Gen2 unlock](../unlock/pcie-gen2.md).

## Stock link state

### What `lspci` prints

```console
$ sudo lspci -s 0a:00.0 -vvv | grep -E 'LnkCap|LnkSta|LnkCtl'
LnkCap: Port #0, Speed 2.5GT/s, Width x16, ASPM not supported
        ClockPM+ Surprise- LLActRep- BwNot- ASPMOptComp+
LnkCtl: ASPM Disabled; RCB 64 bytes, Disabled- CommClk+
LnkSta: Speed 2.5GT/s, Width x4 (downgraded)
LnkCap2: Supported Link Speeds: 2.5GT/s, Crosslink- Retimer- 2Retimers- DRS-
LnkCtl2: Target Link Speed: 2.5GT/s, EnterCompliance- SpeedDis-
LnkSta2: Current De-emphasis Level: -6dB, EqualizationComplete-, EqualizationPhase1-
```

Two details are worth internalising. `LnkCap` advertises **Width x16**, so the card knows it has
sixteen lanes; the `(downgraded)` marker on `LnkSta` means the link *negotiated* down, which is
what happens when the receiver sees no signal on lanes 4 through 15. And `LnkCap2` lists only
2.5 GT/s as supported, which per the PCIe specification clamps any target link speed you write to
`LnkCtl2`: writing `0x2` there on a stock card reads back `0x1`.

The kernel says the same thing in its own words on every boot:

```text
pci 0000:0a:00.0: 8.000 Gb/s available PCIe bandwidth, limited by 2.5 GT/s PCIe x4 link at
  0000:09:01.0 (capable of 32.000 Gb/s with 2.5 GT/s PCIe x16 link)
```

Note what the kernel is comparing against: 32 Gb/s at **2.5 GT/s x16**. It is complaining about
width, not speed.

### Raw register values

All addresses below are BAR0 mirrors of XVE config space. The PCIe Express capability sits at
config offset `0x78` (not `0x60`), and the XVE shadow base is `0x88000`, so config `cap+0x0C`
maps to BAR0 `0x00088084`, and so on.

| Field | Config offset | BAR0 mirror | Stock (locked) | After the Gen2 branch |
|---|---|---|---|---|
| LnkCap | `CAP_EXP+0x0C` | `0x00088084` | `0x00456101` | `0x00456102` |
| LnkCtl / LnkSta | `CAP_EXP+0x10` | `0x00088088` | LnkCtl `0x0140`, LnkSta `0x1041` | LnkCtl `0x0140`, LnkSta `0x1042` |
| LnkCap2 | `CAP_EXP+0x2C` | `0x000880a4` | `0x00000002` | `0x00000006` |
| LnkCtl2 / LnkSta2 | `CAP_EXP+0x30` | `0x000880a8` | `0x0000` / `0x0000` | `0x0002` / `0x0001` or `0x0000` |
| DevCap2 | | | `0x00070803` | `0x00070813` |
| DevCtl2 | | | `0x1400` | `0x0400` (one rig `0x7410`) |

`nvidia-smi` reports `pcie.link.gen.current, pcie.link.gen.max, pcie.link.width.current` as
**1, 1, 4** on a stock card and **2, 2, 4** after the Gen2 branch. Width never moves in either
case.

!!! note "Do not repeat one published address"
    A widely circulated field manual lists the LnkCap2 BAR0 mirror as `0x8808C`. That is
    internally inconsistent: with the XVE mirror based at `0x88000`, config `0xA4` maps to
    `0x880A4`, and `0x8808C` maps to config `0x8C`. Both the branch patch
    (`#define PCIE_GEN2_LINK_CAP2_ADDR 0x000880a4U`) and the community `pcielink.sh` diagnostic
    use `0x880A4`. Use `0x880A4`.

### Other stock config-space facts

| Item | Value |
|---|---|
| Slot power limit (DevCap) | 75 W |
| MaxPayload / MaxReadReq | 256 bytes / 512 bytes |
| ASPM | Not supported (advertised in LnkCap) |
| FLReset | Supported |
| BAR0 | 16 MB at a 32-bit non-prefetchable region, aperture `0x1000000` |
| BAR1 | 64 MB, 64-bit prefetchable |
| BAR3 | 32 MB, 64-bit prefetchable |
| Resizable BAR capability | Present at `[bb0 v1]`, but each BAR advertises exactly one supported size |

BAR1 stays at 64 MiB no matter what framebuffer size the card reports, so full-VRAM host mapping
is unavailable even on a card reporting 81920 MiB. Resizable BAR is therefore advertised but
functionally inert. The old objection that ReBAR "requires PCIe 3.0" is wrong (ReBAR is a
config-space capability, in the specification since 2007, and independent of link generation),
but nobody has demonstrated a working ReBAR on a Gen2-trained 170HX either.

## The speed cap

### Fuse evidence

Three OTP fuse shadows form the fingerprint of the lock. The 170HX reads **1 / 1 / `0x16680000`**
where every comparison Ampere part reads **0 / 0 / something without bit 25**.

| Register | Address | 170HX (both SKUs) | A100 (all three SKUs) and Drive A100 | Notes |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS` (`OPT_PCIE_BOOT_GEN23_DISABLE`) | `0x0082057c` | `0x00000001` | `0x00000000` | Also 0 on A10, A5000, A6000, RTX 3080 / 3080 Ti / 3090 / 3090 Ti and a GA10x control card |
| `FUSE_PCIE_GEN3_DIS` (`OPT_PCIE_BOOT_GEN3_DISABLE`) | `0x00820580` | `0x00000001` | `0x00000000` | Same cohort |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000` (bit 25 set) | `0x00200000` | Bit 25 is documented `GEN4_SPEED_DISABLED`, referenced to NVIDIA bug 2220334. A10/A5000/A6000 read `0x01a00000`; RTX 30-series read `0x10a80000` |

Both 170HX values were measured on two physical units, read twice per part, across a 15-card
comparison cohort. The `0x20c2` reading came from a driver-side dump printing
`OPT=00000001/00000001/16680000`; the `0x2082` reading came from an independent probe's
`registers.json`.

Two related fuses close off the obvious workarounds. `FUSE_EN_SW_OVERRIDE` at `0x820040` reads 0
and `FUSE_DIS_SW_OVR` at `0x820084` reads 1, so the software-override path is disabled in
silicon. `0x820148` is an OTP spare bit that reads 0 and can never be set from software; DevInit
writes the A100 value `0x00200000` to `MAGIC_D` only when `0x820148 & 1`, which is exactly why
DevInit never writes it on the CMP.

`OPT_GEN23` at `0x0082057c` has been attacked from every available privilege: plain host write,
HS-privilege driver write, and the SEC2 Booter payload. Every attempt fails with the readback
still `0x00000001`. It is a pure fuse-sense reflection with no write port. More on that in
[fuses and OTP](fuses-and-otp.md) and [dead ends](../history/dead-ends.md).

!!! info "The fuse is not the lever"
    The Gen2 unlock works **while `OPT_GEN23` still reads `0x00000001`**. The shipped branch patch
    still attempts the write, still fails, and Gen2 still trains. The working levers are the
    CYA_0, LINK_CONFIG_0, XP3G and PRIV_MISC_1 overrides, not the fuse shadow.

### The DevInit layer

The fuse is only one of three layers. The second is a PCIe configuration table inside the
**unencrypted** DevInit Falcon image in SPI flash, which is separate from the legacy x86 VBIOS.

| Item | CMP 170HX | A100 |
|---|---|---|
| PCIe config table, flash offset | `0x420ED` (mirror `0xA20ED`) | `0x408A0` (mirror `0xA08A0`) |
| Runtime DMEM base | `0xF1D` | `0xE50` |
| The five bytes, table offsets `+0xC7` to `+0xCB` | `00 00 08 00 06` at flash `0x421B4`-`0x421B8` | `00 00 14 00 06` at flash `0x40967`-`0x4096B` |
| Suppress flag at table offset `+0x0F` | `0x01` | `0x00` |
| DevInit image location | flash `0xDE00` (disassembly base `0x8000`), duplicated in bank 2 at `+0x60000` | |

The suppress flag is the decisive one: on the CMP, `ld b8 r9, D[tab+0x0F]; bra ne` skips the
entire Gen4 programming block (disassembly `0x31B3F`-`0x31B92`). When that block does run it
computes `0x88CE4 = (old & ((b1<<8)|b0)) | ((b3<<8)|b2)`, which reduces to byte `[+0xC9]` because
`b0 = b1 = b3 = 0`, and `0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)` with `b4 = 0x06` on both parts.
A wider symbolic analysis found **thirteen** DevInit bytes differing in total, of which eleven are
attributable to non-PCIe SKU features (HBM, NVLink, ECC); the PCIe-relevant ones are `[0xC9]`
(feeds `0x88CE4`), `[0x1C-0x1F]` (feeds `0x8C2C0`), and `[0x3F]` (feeds `0x8C040`). The CMP and
A100 BIT tables are byte-identical.

Editing those bytes is a closed route. All five sit **100% inside** the Davies-Meyer `csecret(2)`
MAC range `0x2200`-`0x43C00`, so a keyless forge is a 2^128 second-preimage, and reflashing an
edited image fails the Ampere RSA signature check outright. See [VBIOS](vbios.md).

!!! danger "Do not attempt a modified reflash"
    An edited DevInit or VBIOS image is rejected by the signature check and the card will not
    boot. Recovery requires an external programmer. Read [recovery](../procedures/recovery.md)
    before touching flash.

The third layer is runtime: DevInit itself never reads `0x82057C` or `0x820580`. An exhaustive
search of the CMP DevInit disassembly finds only `0x820C14`/`0x820D38` (FBIO/FBP floorsweep),
`0x820684` (`FUSE_NVLINK_DIS`), `0x82380C`/`0x823814`, `0x820520`, `0x820148`, `0x8243xx`,
`0x8202xx`, `0x8201xx`, `0x82033C`/`0x82030C`. GSP-RM is the consumer: a fuse-read jump table at
`0x5D55834` in `470.42.01 gsp.bin` uses `li a2, 0x580` and `li a2, 0x57c`, and
`580.105.08 gsp_tu10x.bin` does `jalr fuse_read` at `0x4DD9B00` with `li a2, 0x57c`. That is why
the Gen3 route is currently described as needing a GSP patch.

### Boot ordering

FWSEC-DevInit programs and **latches** `SUPPORTED_LINK_SPEED` before the SEC2 Booter runs, and the
SEC2 Booter is where the unlock's timing-hole gadget lives. The latched capability is therefore
already fixed by the time any exploit window opens. The memory and compute unlocks land because
`FEAT_OVR` (`0x82381C` / `0x823804`) and FBPA (`0x9A0204`) are ordinary registers inside the 16 MB
BAR0 that become writable once their PLM is opened. A latched PHY capability is not. What the
Gen2 result actually does is make the PHY reflections regenerate to Gen2 and then train the link
before anything re-clamps it.

### Where the speed capability lives, register by register

| Register | Address | Access | Notes |
|---|---|---|---|
| Supported-speed source | `0x00085080` | Read-only, `[23:20]` | Reads `0xBADF1100` (poison) from the host; zero writers found in 4.1 M lines of RM disassembly |
| Allowed-Gen mask | `0x00085084` | Re-derived by GSP-RM on every retrain | Also reads poison |
| `MAX_LINK_SPEED` | `0x00088084` `[3:0]` | PHY reflection, marked `R-XVF` | No write port |
| `SUPPORTED_LINK_SPEED` | `0x0008808C` `[7:1]` | PHY reflection, marked `R-EVF` | No write port at any privilege |
| `TARGET_LINK_SPEED` | `0x000880A8` `[3:0]` | RW, but clamped by SUPPORTED | |
| `LINK_CONTROL_STATUS` | `0x00088088` | Live negotiated speed at `[19:16]` | |
| `PRIV_MISC_1` | `0x0008841C` | RW under PLM | CYA Gen2/3 override bits 11-16, 30, 31 |
| `VSEC_HIERARCHY` | `0x00088610` | RW under PLM | Bit 12 gates PRIV_MISC_1 reprogram; live value `0x00001001` |
| LTSSM retrain trigger | `0x0008872C` | RW under PLM | Write `6` |
| `PPCI_2.CONFIG_LINK` (`LINK_CONFIG_0`) | `0x0008C040` | RW under PLM | `[3:0]` LTSSM_DIRECTIVE, `[4]` LTSSM_STATUS, `[19:18]` SPEED (0 = max, 2 = 5.0 GT/s, 3 = 2.5 GT/s). CMP reads `0x800C4C00` (SPEED = 3); A100 reads `0x80004C00` (SPEED = 0) |
| `CYA_0` | `0x0008C2C0` | RW under PLM | Bit 2 is the `DIS_G2` chicken bit. CMP `0x068731B7` vs A100 `0x060711B2` |
| `PL_LINK_RATE` | `0x0008C1C0` | | A100 reads `0x00040036` |
| `PPCI.UNK1C0` | `0x000881C0` | Host reads return `0xbadf5040` | rnndb: `[17:16]` LNK_CAP_SPEED, `[21:20]` SYSTEM_MAX_SPEED |

Speed-vector encodings used throughout: Gen1 = `0x1`, Gen1_2 = `0x3`, Gen1_2_3 = `0x7`,
Gen1_2_3_4 = `0xF`.

Block layout follows envytools rnndb naming for GK104 and later: **PPCI** at `0x88000` (config
shadow plus priv), **PPCI_HDA** at `0x8A000`, **PPCI_2** at `0x8C000` (the LTSSM and speed block,
containing `CONFIG_LINK` at `0x8C040` and `WIDTH` at `0x8C080`, the latter reading `0x00001010` on
an A100). The full list is in the [register index](../appendix/register-index.md).

## The width cap

### It is missing parts, not fuses and not firmware

Twelve of the sixteen PCIe data lanes on the 170HX ship with their AC-coupling capacitors
physically omitted from the PCB. There are two capacitors per differential pair, so twelve lanes
means **24 missing parts**. NVIDIA populated only the four lanes it intended the card to use.
Lanes 0 through 3 are populated; lanes 4 through 15 are not.

Three independent lines of evidence rule out every software explanation:

1. **No lane fuse is set.** `OPT_PCIE_LANE_DISABLE` at `0x00820394`, `CTRL_OPT_PCIE_LANE` at
   `0x0082082C` and `STATUS_OPT_PCIE_LANE` at `0x00820C2C` all read `0x00000000` on every card in
   the cohort, both 170HX units included. The x16 electrical width is intact in silicon.
2. **No code touches width.** An exhaustive audit of every PCIe-related write in the Gen2 branches
   found writes only to `LINK_CTRL_2 [3:0]`, `LINK_CONFIG_0 [19:18]`, `CYA_0` bit 2, `PRIV_MISC_1`
   bits 11-14, `PL_LINK_RATE`, `OPT_GEN23`, XP3G slots 0 and 3, VSEC device and hierarchy bits,
   and `LNKCTL2` TLS in config space. `LINK_CAP` is read but only its low speed nibble is tested;
   the Max Link Width field at `LINK_CAP[9:4]` is never read or written, and `LNKSTA` is masked
   with `PCI_EXP_LNKSTA_CLS` and `PCI_EXP_LNKSTA_DLLLA` but never `PCI_EXP_LNKSTA_NLW`. A grep of
   shipping master and all twelve unreleased branches for "capacitor", "AC coupling", "solder" or
   any lane-width register returns nothing.
3. **A known-good x16 host port still trains x4.** Measured on 2026-07-26 on two cards in one
   host: sysfs reported the GPU at width `cur 4 / max 16` on both, and the second GPU's upstream
   port was itself x16-capable (`cur 4 / max 16`) while the link still trained x4. The riser and
   slot-bifurcation hypotheses are answered by the PCB analysis, not by anything in software.

### The parts

| Property | Canonical value |
|---|---|
| Count | 24 (2 per differential pair × 12 depopulated lanes) |
| Package | 0402 |
| Capacitance | 220 nF (0.22 µF) |
| Dielectric | **X7R** (frequently mistyped "XR7") |
| Voltage rating | 16 V or higher: the canonical guide and the confirmed Samsung part are both 16 V. One card owner gave 10 V as the floor |
| Reference designators | C1100 to C1350 range, for example C1120 / C1125 / C1130 / C1135 per pair |
| Confirmed manufacturer part | Samsung `CL05B224KO5NNNC` |
| Distributor numbers seen | DigiKey `1276-1176-1-ND` and Digi-Key `3886834`. Both are plausibly the same manufacturer part in different packaging; treat them as unverified aliases and buy to the manufacturer part |

The value is not guesswork: it is read off the NVIDIA A100 GA100-883 reference schematic
**P1001-B02 page 3, "IO: PCIe CONNECTOR"**, which the 170HX board closely follows. One tester
reported 100 nF substitutes working.

### Measured result

```text
before:  LnkSta: Speed 2.5GT/s, Width x4 (downgraded)
after:   LnkSta: Speed 2.5GT/s, Width x16
```

Verify with `sudo lspci -s <bdf> -vvv | grep LnkSta`. The speed field does not move, and that is
the expected outcome.

Partial work negotiates down rather than failing. PCIe width negotiation falls back through the
legal widths 16, 8, 4, 1, so a card with between 12 and 23 of the 24 capacitors correctly
populated trains at **x8**. One modder's progression across three cards was x4, then x8, then x16
as technique improved; another card went x4, x8, x16 "after smaller readjustments". An x8 result
after a mod means incomplete or bridged solder joints, not a distinct hardware limit. Reflow and
inspect all 24 joints.

!!! danger "This is fine-pitch rework on a card you cannot replace"
    0402 parts on a dense high-speed differential region. A bridged pair does not merely fail to
    widen the link, it can corrupt signalling on a lane that previously worked. Leaded solder was
    reported to make the job "extremely easy"; solder paste applied with a needle plus a heat gun
    lets the parts self-align. Full procedure and photographs on
    [physical mods](../operations/physical-mods.md).

## Bandwidth by configuration

| Configuration | Measured | Method and conditions | Confidence |
|---|---|---|---|
| Gen1 x4 | 0.85 GB/s write, 0.84 GB/s read | clpeak `enqueueWriteBuffer` / `enqueueReadBuffer`, published 2023 table | high |
| Gen1 x4 | 0.80 GB/s send, 0.84 GB/s receive, 0.81 bidirectional | One OpenCL-Benchmark screenshot relayed from an outside hardware group, 10 GB-to-40 GB card; the tool labelled the link "Gen1 x16" | medium |
| Gen1 x16 (cap mod, no Gen2) | 2.88 GB/s flat, error-free | Modded card; nominal ~4 GB/s, shortfall attributed to PCIe 1.1 signalling overhead | medium |
| Gen2 x4 | 1.68 GB/s send, 1.71 GB/s receive | OpenCL-Benchmark, one archived screenshot, unmodded card; the setup script independently predicts "~0.85 to ~1.7 GB/s, exactly 2x" | medium |
| Gen1 x8 → Gen2 x8 (A/B on one card) | 1.67 GB/s to 3.24 GB/s | OpenCL, on a cap-modded card that negotiated x8. This is a **width** result as much as a speed result; do not quote it as a Gen2 x4 figure | medium |
| Gen2 x16 | 6.63 to 6.67 GB/s (`ocl_pcie_bw`); the same run's nvtop screenshot shows `PCIe GEN 2@16x` with TX 7.061 GiB/s | fully modded card also running the Gen2 branch; one rig, one capture, 2026-07-26 | medium |

!!! warning "Gen2 x16 rests on a single observation"
    Gen2 x16 has been observed **once**, on 2026-07-26, on one rig, in one screenshot, on a card
    whose 24-capacitor mod was complete. There is no `lspci` capture bridging it to the earlier
    survey in which every Gen2 result was x4, no burn-in, no AER counters over time, and no second
    rig. Treat the 6.63-6.67 GB/s figure as medium confidence and treat Gen2 x16 **stability** as
    unestablished.

A `0.71 GB/s` bidirectional figure circulated for a card described as Gen1 x16. It is far too low
for that configuration (nominal ~4 GB/s) and the card's actual lane state was never established.
Do not quote it as a Gen1 x16 measurement.

For what these numbers mean in practice, see [performance](../operations/performance.md) and
[LLM inference](../operations/llm-inference.md). The short version: at Gen1 x4 the link is the
binding constraint for graphics (Unigine Superposition capped at 5 fps, 15-20 fps in 1080p games,
a single 1080p60 remote-gaming stream saturating the link), while for pipeline-parallel LLM decode
the link is nearly irrelevant (a 5120-hidden-dimension model moves 10,240 bytes per token per hop,
so saturating a single PCIe 1.0 lane would need roughly 25,000 tokens per second). Tensor and
expert parallelism are judged unworkable even at Gen2 x16.

## Things that look like the cause but are not

| Suspect | Why it looks plausible | Why it is not the cause |
|---|---|---|
| `NV_PTOP_FS4` `0x0002241c` | Documented bit names are literally `GEN2_PCIE` (bit 0) and `GEN2_PCIE_SPEED` (bit 7) | Reads `0x00000000` on the 8 GB (`0x20c2`) card and `0x00000081` on the 10 GB (`0x2082`) card. A GA10x control card that trains Gen4 reads the same `0x00000081`, and the 10 GB 170HX reads `0x00000081` while still capped at Gen1. Both observations cannot hold if these bits gate speed. `PTOP_FS_STATUS` at `0x00022470` reads `0x0000003f` |
| Board straps | There are visible strap resistor pads near U808; Strap4 (R999/R1000) maps as `PCIE_CFG` | Copying the A100 strap configuration onto a 170HX resulted in the **card not being detected at boot**. The verdict from the researcher who tried it: "the straps don't do anything", "falcon is driving the rewrites" |
| Device-ID spoofing | Present the card as an A100 and inherit its settings | `FUSE_DEVID_SW_OVR_DIS` at `0x00820584` reads `0x00000001` on every Ampere part probed; the IDs come from read-only fuses `0x008204D8` and `0x0082056C`. Writing the XVE config shadow dword0 changes only the host-visible ID while every lock stays in place |
| Flashing a genuine A100 80GB VBIOS | Byte-identical BIT tables, near-identical PCB | Tested and failed; the Gen4 bit at minimum does not carry over |
| A PCIe redriver | Cheap and available | A redriver only re-amplifies, so the endpoint still sources its own fuse-capped TX rate. Only a **retimer** (which terminates the link and can advertise a different rate to each side) could forge TS1/TS2 Rate-ID. Never attempted |
| ASPM | Many platforms idle a link down to Gen1 | Genuine false-negative trap when testing, so run tests under load, but the 170HX advertises `ASPM not supported` in its own `LnkCap`, so it was not the cause in the case where it was raised |

A curiosity worth recording: on **both** physical 10 GB cards, `FUSE_PCIE_DEVIDA` at `0x008204D8`
reads `0x00002082` while `FUSE_PCIE_DEVIDB` at `0x0082056C` reads `0x000020c2`. A 10 GB card
carries the 8 GB variant's device ID as its secondary fuse. Across 13 comparison cards, fuse B
equals fuse A with bit 6 set (`+0x40`), for example A100 PCIe 80G `0x20b5`/`0x20f5`. Also measured:
**`OPT_SKU_ID` at `0x00821060` = `0x00000068`** on these 10 GB units (`0x00000080` is the 8 GB /
`0x20C2` value), `OPT_INTERNAL_SKU` at `0x008203f4` = 0.

## Platform and interconnect

| Topology | Verdict |
|---|---|
| Bare metal PCIe slot | Supported and the reference configuration |
| Oculink | Works. Essentially a direct PCIe riser, sometimes with a redriver for timing |
| Thunderbolt 3 eGPU enclosure | **Breaks the unlock entirely**, not just PCIe. `nvidia-smi` returns "No devices were found" and dmesg shows the full GSP boot failure chain (`Booter failed with non-zero error code: 0x15`, `failed to execute Booter Load: 0xffff`, `Max GSP-RM boot attempts exceeded: 4/4`, `RmInitAdapter failed! (0x62:0xffff:2119)`) |
| GPU passthrough into a VM | Gen2 capability is advertised but training does not happen. Acknowledged by the maintainers 2026-07-24, unfixed |
| Passive SlimSAS / MCIO, 70 cm | Unreliable at Gen4 x8 (many errors), stable at Gen3 x8. Cable marking `HNW-SS-8654-AA75`. Most adapter boards carry an `ICS 9ZXL1950DKIL`, which is a **clock buffer, not a redriver**; the `NFHK N-W54B-P` variant was identified as carrying actual redrivers |
| PCIe switch fan-out (for example PEX88096) | A switch does not create bandwidth, and because the 170HX has **no P2P**, cards behind one switch cannot bypass the uplink. Nobody in the observed window deployed 170HX cards behind one |
| InfiniBand or fast fabric in a cluster | Zero benefit at Gen1 or Gen2. One multi-node operator could not even saturate 10 GbE |

Peer-to-peer is absent on this card and no branch contains any P2P enablement. See
[P2P](../frontier/p2p.md).

## Diagnostic rules

1. **Read `LnkSta`, never `LnkCap`.** `LnkCap` is the advertised capability and can read Gen2
   while the link is still training at Gen1. That trap is the stated source of most "it works"
   claims that do not survive scrutiny.
2. **Do not trust sysfs `max_link_speed`.** On three cards across two rigs it reported
   `cur 5.0 GT/s / max 2.5 GT/s`, a maximum lower than the current speed, while config-space
   `LnkCap` correctly read `0x00456102`. Expect the mismatch; it is not a fault.
3. **Do not read `nvidia-smi`'s `PCIe Generation Max` as evidence of anything.** A stock card has
   reported `Max: 2` alongside `Device Current: 1` and `Device Max: 1` since 2023, while `LnkCap2`
   lists only 2.5 GT/s. It is useful only as a fingerprint.
4. The three honest fields are `lspci -vvs <bdf> | grep LnkSta`,
   `/sys/bus/pci/devices/<bdf>/current_link_speed`, and
   `nvidia-smi --query-gpu=pcie.link.gen.gpucurrent`.

The community's standard link report is a published `pcielink.sh` diagnostic that captures kernel,
driver, SEC2_DEBUG line count, BDF, board and GPU part numbers, VBIOS, the full
LnkCap/LnkCap2/LnkCtl2/LnkSta/LnkSta2/DevCap2/DevCtl2/LnkCtl set for **both** the GPU and the host
bridge, sysfs speed and width, `nvidia-smi` figures and AER counters. Observed identities on
confirmed cards: VBIOS `92.00.6D.00.0A` and `92.00.67.00.01`, BoardPN `900-11001-0108-000`,
GPUPN `20C2-105-A1`, subsystem `0x158510DE`.

## Open problems

!!! question "Open problem: Gen3 and Gen4"
    `FUSE_PCIE_GEN23_DIS` and `FUSE_PCIE_GEN3_DIS` both read `0x00000001`, and the supported-speeds
    vector clips at `0x00000006` even after the PHY rate is forced to a Gen3-capable
    `0x00340036`. Whether the "vector is contiguous so Gen2/3/4 are one problem" argument simply
    failed on this silicon, or the Gen3 fuse is enforced independently downstream, is unresolved.
    The cheapest untried experiment: write `0x00820580 = 0` through the same `xp3g` table that
    already *attempts* `0x0082057c`, noting that that write fails, so expect
    `booter FAILED to set` and `rd=0x00000001`. Then request TLS = 3. Cheap, but low prior. See
    [Gen3 and Gen4](../frontier/pcie-gen3-gen4.md).

!!! question "Open problem: is `FUSE_PCIE_MAGIC_D` writable?"
    One analysis annotates `0x00820520` "(writable)"; one clean-room chain writes `0x00200000` to
    it; the field manual lists it read-only; and the branch patch only ever reads it. Since Gen4 is
    untestable without a Gen4 host, this has never been exercised. Read, write `0x00200000`, read
    back, publish both values. Five minutes of work nobody has done.

!!! question "Open problem: is x16 stable?"
    One 2026-07-26 capture is the entire evidence base for Gen2 x16. No burn-in, no AER counters
    over time, no second rig.

!!! question "Open problem: Resizable BAR on a Gen2 card"
    The capability structure exists and has been captured (`Capabilities: [bb0 v1] Physical
    Resizable BAR`, BAR0 16 MB, BAR1 64 MB, BAR3 32 MB, one supported size each). What is open is
    whether ReBAR can be made *usable*: BAR1 stays pinned at 64 MiB even when the card reports
    81920 MiB, and nobody has retested it on a Gen2-trained card.

## See also

- [Gen2 software unlock](../unlock/pcie-gen2.md) for the register mechanism and the branch code
- [Physical mods](../operations/physical-mods.md) for the capacitor rework procedure
- [Fuses and OTP](fuses-and-otp.md) for the full fuse map
- [Gen3 and Gen4](../frontier/pcie-gen3-gen4.md) for the unsolved half
- [Register index](../appendix/register-index.md)
- [Glossary](../start/glossary.md)
