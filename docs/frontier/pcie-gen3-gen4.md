# PCIe Gen3 and Gen4: why they are still locked

**What this page covers.** Everything known about the PCIe generation wall above 5 GT/s on the
CMP 170HX: the two independent lock layers (a pair of OTP fuses plus a five-byte edit in the
signed DevInit image), why the Gen2 breakthrough of 2026-07-24 did not carry Gen3 with it, the
exact registers the working Gen2 patch reads but never writes, a full catalogue of refuted
approaches, and the remaining avenues ranked by cost.

**The headline: no Gen3 or Gen4 link has ever trained on a CMP 170HX.** As of 2026-07-28 no
source in the corpus reports `LnkSta: Speed 8GT/s` or `16GT/s` on this card. Gen3
*advertisement* was made to work on 2026-07-24 (`LnkCap: Port #1, Speed 8GT/s, Width x4` and
`LnkCtl2: Target Link Speed: 8GT/s`) while `LnkSta` stayed pinned at `Speed 2.5GT/s, Width x4`.
The closing position on the record, stated by the maintainer on 2026-07-27, is that Gen3 needs a
GSP-RM firmware patch: "Gen 3 doesn't work whatsoever, it's going to require a GSP patch" and
"I haven't seen anybody at all get a working GSP patch."

> [!NOTE]
> **Open problem**
>
> This page describes unsolved work. Nothing here ships. Gen2 (5 GT/s) *is* solved in software
> and shipped in `master` on 2026-07-29: see [PCIe Gen2](../unlock/pcie-gen2.md).

> [!WARNING]
> **Speed is not width**
>
> PCIe link **speed** (Gen1 to Gen2) and PCIe link **width** (x4 to x16) are two entirely
> separate problems on this card with two entirely separate fixes. Speed is firmware and fuses,
> the subject of this page. Width is a PCB depopulation fixed only by hand-soldering 24
> AC-coupling capacitors, covered in [physical mods](../operations/physical-mods.md). A Gen3
> software unlock at the native x4 width is the community's stated next target precisely
> because it would need no soldering.

---

## Status at a glance

| Generation | Rate | Status on the 170HX | Mechanism |
|---|---|---|---|
| Gen1 | 2.5 GT/s | Stock, always trains at cold boot | Signed DevInit programs the CMP PCIe table |
| Gen2 | 5.0 GT/s | **Solved in software**, shipped in `master` since 2026-07-29 | Combined register sequence through the SEC2 Booter plus a root-port retrain |
| Gen3 | 8.0 GT/s | **Unsolved.** Capability can be advertised; the link never trains | Stated on 2026-07-27 by the maintainer to need a GSP-RM patch, and no working GSP patch has been produced |
| Gen4 | 16.0 GT/s | **Unsolved and untestable.** No contributor has a Gen4 host | Fuse bit 25 `GEN4_SPEED_DISABLED` plus the suppressed DevInit block |

Link-state fingerprints for reference:

| State | LnkCap | LnkCap2 | LnkCtl2 | LnkSta |
|---|---|---|---|---|
| Stock (locked) | `0x00456101` | `0x00000002` | `0x0000` | `0x1041` |
| Unlocker installed, trained | `0x00456102` | `0x00000006` | `0x0002` | `0x1042` |
| Round-3 vector spoof | wrote `0x00457104` (width x16) | wrote `0x0180001E`; clipped back to `0x00456102` / `0x00000006` | not recorded | not recorded |
| Gen3 advertisement, 2026-07-24 | `Port #1, Speed 8GT/s, Width x4` | not recorded | target 8GT/s accepted | stayed 2.5GT/s x4 |

These last two rows are **two different experiments**, never observed together, and their `LnkCap`
values encode different widths (x16 versus x4). Do not read them as one run.

---

## Why Gen2 fell and Gen3 did not

Before 2026-07-24 the prevailing model treated the supported-speeds vector as contiguous by
specification (Gen4 requires Gen2 and Gen3), so Gen2, Gen3 and Gen4 were treated as one problem:
"either the vector opens or nothing does". The vector then opened, and only to Gen2.

The Gen2 result works by opening a set of privilege-level masks through the SEC2 Booter payload
write primitive, clearing the `DIS_G2` chicken bit in `CYA_0`, forcing `LINK_CONFIG_0` MAX_RATE
to 2, driving the XP3G override slots and `PRIV_MISC_1`, and then having the **upstream root
port** retrain the link. The endpoint's `LnkCap`/`LnkCap2` are PHY reflections: once the Gen2
gates are open, they regenerate to `0x00456102` / `0x00000006` without anything writing them
directly. They regenerate to Gen2 **and no further**, even when a spoof explicitly writes the
Gen1-4 values:

```text
round-3 spoof: 0x88084 <- 0x00457104   (A100 Max Link Speed = 4)
               0x880A4 <- 0x0180001E   (A100 supported vector, Gen1-4)
observed post: CAP=0x00456102 CAP2=0x00000006
```

The hardware clipped the write to Gen2. A researcher who then proved out the Gen2 half two days
later summarised it as: "Lnkctrl2 is capped at gen2 with a direct hardware mask (which is why
gen 3/4 is such a pain). But you can achieve gen2 with the correct register writes."

Two possibilities remain live and nothing in the corpus separates them:

1. the contiguity argument was simply wrong about this silicon, or
2. the Gen3 fuse is enforced independently, downstream of the supported-speeds vector.

The strongest on-silicon evidence favours (2). With the XP3G privilege-level mask opened
(`PLM[4] XP3G_PLM(0x8e1b0) reg=0xffffffff`) the PHY rate register was forced to a Gen3-capable
value and read back correctly, and the link still trained at Gen1:

```text
XP3G rate=0x00340036 ovr0=0x4
lnksta=0x10410040 speed=1        # lspci: Speed 2.5GT/s
```

A second, weaker line of evidence: on Gen2-trained cards `LnkSta2` reports
`EqualizationComplete-` and `EqualizationPhase1-`, that is, the PHY equalization pass that Gen3
mandates has never run. The write-up phrasing that captures the community view is *"Gen2 is a
software lockout, Gen3 is a hardware fuse"* (confidence: medium; no Gen3 force attempt with
measured PHY behaviour was ever reported).

---

## Lock layer 1: the OTP fuses

Three fuse-option registers form the fingerprint of the generation lock. All were read on both
physical 170HX SKUs and compared against a 15-card Ampere cohort.

| Register | Address | 170HX | Comparison cohort | Notes |
|---|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS` (`OPT_PCIE_BOOT_GEN23_DISABLE`) | `0x0082057c` | `0x00000001` | `0x00000000` on all three A100 SKUs, A10, A5000, A6000, RTX 3080/3080 Ti/3090/3090 Ti, an ES part, a Drive A100 and a GA10x control | The only one the Gen2 patch attempts to write |
| `FUSE_PCIE_GEN3_DIS` (`OPT_PCIE_BOOT_GEN3_DISABLE`) | `0x00820580` | `0x00000001` | `0x00000000` everywhere else | **Never written by anyone** |
| `FUSE_PCIE_MAGIC_D` | `0x00820520` | `0x16680000` (bit 25 set) | `0x00200000` on A100 SXM4 40G / PCIe 40G / PCIe 80G / Drive A100; `0x01a00000` on A10/A5000/A6000; `0x10a80000` on RTX 30-series | Bit 25 is documented `GEN4_SPEED_DISABLED`, referenced to NVIDIA bug 2220334 |

The three-register fingerprint of the lock is therefore **`1` / `1` / `0x16680000`**.

Two supporting fuse facts matter for anyone planning an attack:

- **The lanes are clean.** `OPT_PCIE_LANE_DISABLE` `0x00820394`, `CTRL_OPT_PCIE_LANE`
  `0x0082082C` and `STATUS_OPT_PCIE_LANE` `0x00820C2C` all read `0x00000000`. Only speed is
  fused. This is independent confirmation that the x4 width is a board issue.
- **The software-override path is fused shut.** `FUSE_EN_SW_OVERRIDE` `0x00820040` = `0` and
  `FUSE_DIS_SW_OVR` `0x00820084` = `1`. `0x00820148`, the DevInit gate bit that would make
  DevInit write the A100 `MAGIC_D` value, is an OTP spare bit that reads `0` and can never be
  set from software. This is why the cleanest A/B in the whole project (2026-07-22) saw the XVE
  targets land and persist in the same boot in which `0x820520` stayed `0x16680000` and
  `0x820148` stayed `0`.

### `OPT_GEN3` and `OPT_MAGIC`: read, logged, never written

This is the single most important code-level fact on this page. The working Gen2 patch
`0007-pcie-gen2.patch` `#define`s all three fuse-option registers and prints all three, but its
23-entry Booter-routed write table contains exactly one of them:

```c
/* from 0007-pcie-gen2.patch */
#define PCIE_GEN2_OPT_GEN23_ADDR   0x0082057cU   /* write attempted -> fails on silicon */
#define PCIE_GEN2_OPT_GEN3_ADDR    0x00820580U   /* read only */
#define PCIE_GEN2_OPT_MAGIC_ADDR   0x00820520U   /* read only */
```

The three values appear together in the `NV_PRINTF` argument lists with format
`OPT=%08x/%08x/%08x` (GEN23 / GEN3 / MAGIC). On a Gen2-branch boot that print reads:

```text
OPT=00000001/00000001/16680000
```

That line is a useful dmesg fingerprint on its own: a Gen1 build emits 34 `SEC2_DEBUG` lines, a
Gen2 build emits 80.

> [!NOTE]
> **Line counts are not a reliable cross-build fingerprint**
>
> 34 (Gen1 build) / 80 (Gen2 build) is recorded at high confidence, while a separate Gen2-branch
> 610.43.03 boot counted 152 at medium confidence. Do not read a mismatch as a failed install.

No code path in any branch, and none in the independent clean-room tool
set, ever requests a target link speed above 2: `constants.yaml` in the Gen2 code pins
`target_gen: 2`, `TARGET_LINK_SPEED` is written as `2`, the LTSSM speed field is set to `2`, and
the success test is `LnkCap2 & 0x4`.

### The `OPT_GEN23` write fails, and Gen2 works anyway

The one fuse write that *is* attempted does not land. Verbatim from an instrumented build, on
both GPUs in the same boot:

```text
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter OPT_GEN23(0x82057c)=0x00000000 \
  attempt=1 status=0xffff rd=0x00000001 OVR0=0x00000000 VAL0=0x00000000 \
  OVR3=0x00000000 VAL3=0x00000000
NVRM: GPU0 _kgspBootGspRm: SEC2_DEBUG: PCIe xp3g booter FAILED to set OPT_GEN23
```

A direct high-secure write logged `PLM[4] OPT_GEN23(0x82057c) status=0xffff reg=0x1
(write FAILED)`. The register is a pure OTP fuse-sense reflection with no write port at any
privilege level. **Gen2 therefore works despite `OPT_GEN23` never being cleared.** The fuse
shadow is not the lever; `CYA_0`, `LINK_CONFIG_0`, the XP3G overrides and `PRIV_MISC_1` are.

This matters for planning, because the most frequently cited "cheap next step" for Gen3 is to
write `0x00820580 = 0` through the same table that "already succeeds on `0x0082057c`". That
premise is wrong: the table's write to `0x0082057c` is observed to fail on silicon. The
experiment is still worth running (it costs one boot) but its prior should be low.

---

## Lock layer 2: the DevInit config table

The PCIe speed restriction also lives in a PCIe configuration table inside the **unencrypted**
DevInit falcon image in SPI flash, not in the legacy x86 VBIOS portion.

| Item | CMP 170HX | A100 |
|---|---|---|
| Table location, flash | `0x420ED` (mirror `0xA20ED`) | `0x408A0` (mirror `0xA08A0`) |
| Runtime DMEM base | `0xF1D` | `0xE50` |
| Five bytes at table `+0xC7..+0xCB` | `00 00 08 00 06` at flash `0x421B4-0x421B8` | `00 00 14 00 06` at flash `0x40967-0x4096B` |
| Suppress flag at table `+0x0F` | `0x01` | `0x00` |
| DevInit image | flash `0xDE00` (disasm base `0x8000`), duplicated in bank 2 at `+0x60000` | same layout |
| BIT tables (I, i, C, D, x, p, u, B, M) | byte-identical to A100 | byte-identical to CMP |

The suppress flag is the decisive byte. In the disassembly at `0x31B3F-0x31B92` the code reads
it and branches away from the entire Gen4 programming block:

```text
ld b8 r9, D[tab+0x0F]
bra ne -> skip whole block
```

When the block does run it computes two write-only registers:

```text
0x88CE4 = (old & ((b1<<8) | b0)) | ((b3<<8) | b2)   ; reduces to byte [+0xC9] since b0=b1=b3=0
0x88CE0 = (old & ~0x3F) | (b4 & 0x3F)               ; b4 = 0x06 on both parts
```

Both `0x88CE0` and `0x88CE4` are write-only across the whole DevInit disassembly (one-shot Gen4
init config) and sit inside the XVE shadow of the Physical Layer 16.0 GT/s Extended Capability
(PCIe capability ID `0x0026` at shadow `0x88C1C`). The surrounding Gen4 sequence also writes
LTSSM timeouts `0x8D1A0 = 0x1B1F2327` and `0x8D1A4 = 0x0B0F1317` (identical to live A100 values)
and `0x88610 = 0x1001`.

A symbolic mini-interpreter over the CMP DevInit disassembly later established that **thirteen**
DevInit bytes differ in total, not five; eleven of the differing bytes were attributed to
non-PCIe SKU features (HBM, NVLink, ECC). The PCIe-relevant consumers are `[0xC9]` to `0x88CE4`
and `0x132B70`, `[0x1C-0x1F]` to `0x8C2C0` plus the `0x918050`/`0x91C050`/`0x920050` series, and
`[0x3F]` (`0x00` on A100, `0x0C` on CMP) to `0x8C040`.

> [!CAUTION]
> **Reflashing is not a path**
>
> All five PCIe bytes fall **100 % inside** the Davies-Meyer `csecret(2)` MAC range
> `0x2200-0x43C00`. A keyless forge is a 2^128 second-preimage problem. The Ampere RSA
> signature check rejects an edited image and the card will not boot. Gen-cap bytes at
> `0x40B4B`, `0x40F05-3D` and `0x40FC5-CB` are also inside the MAC. Do not attempt to flash a
> modified DevInit: see [VBIOS](../hardware/vbios.md) and
> [recovery](../procedures/recovery.md).

### The refuted intuition: the strap field is monotonic-restrictive

One of the most valuable corrections in the corpus. The intuitive direction of the community
`pcie_set_speed` patch is exactly backwards. The devinit read-modify-write in the signed FWSEC
is `mov r9 0x14118f78; ld; and 0x3ff / or 0x400; st` at VBIOS offset `0xE88C`, with 26
references in every ROM; the 170HX-versus-A100 delta is the **value written**, not the code. The
strap field is restrictive: `0` = all generations enabled, `3` = the 170HX setting (clears
Gen2/3/4), `0xF` = out of range / all disabled. Raising the ceiling requires a **lower** strap
value, and no write port exists.

A related address-space claim was retracted on 2026-07-27: every `0x14xx....` constant in FWSEC
falcon code is a BAR0 offset OR'd with aperture base `0x14000000`, so `0x14118F78` is BAR0
offset `0x118F78`, inside the ordinary 16 MB window, not on a separate ">16 MB Falcon PRIV bus".
A host read of `0x118F78` **with the driver loaded** returns `0xbadf1100`, NVIDIA's priv-poison
pattern, so host reachability outside FWSEC context is still unproven.

---

## Where the fuses are actually consumed

DevInit does not read the two Gen fuses at all. The complete list of `0x82xxxx` accesses in the
CMP DevInit disassembly is `0x820C14`/`0x820D38` (FBIO/FBP floorsweep), `0x820684`
(`FUSE_NVLINK_DIS`), `0x82380C`/`0x823814`, `0x820520`, `0x820148`, `0x8243xx`, `0x8202xx`,
`0x8201xx`, `0x82033C`/`0x82030C`. Neither `0x82057C` nor `0x820580` appears.

GSP-RM does read them, and those read sites are located:

| Firmware | Address | Instruction evidence |
|---|---|---|
| `470.42.01 gsp.bin` | fuse-read jump table at `0x5D55834` | `li a2, 0x580` and `li a2, 0x57c` |
| `580.105.08 gsp_tu10x.bin` | `0x4DD9B00` (`jalr fuse_read`) | `li a2, 0x57c` |

That pairing is why the current statement of requirement is "it needs a GSP patch". A full
disassembly scan of `gsp_tu10x.bin` also established what GSP does **not** do: no writes were
found anywhere to `0x88CE4`, `0x88CE0`, `0x88084`, `0x880A4`, `0x880A8`, `0x820520` or
`0x82057C`. GSP touches PCIe only for link management (`0x88088` read-modify-write of bits 0-1,
speed reads with Gen1/2/3 branching where Gen4 falls into the default path, `0x8A088`, internal
reads `0x88A48`/`0x88A4C`/`0x88A64`, and dynamic fuse-block access as `0x82000 | offset`).

> [!NOTE]
> **Method note worth preserving**
>
> An early naive 4-byte constant search falsely reported "no XVE references" in the GSP image,
> because RISC-V builds these addresses dynamically via `lui`/`addi`. A full pattern scan was
> required. Encrypted GSP regions remain unreadable, so even the corrected scan is not
> exhaustive.

---

## The register-level map of the speed capability

From RM disassembly, with the caveat that the working Gen2 result shows the practical picture is
more permissive than this map implies (confidence: medium).

| Register | Role | Access | Observed on 170HX |
|---|---|---|---|
| `0x85080` | Supported-speed source [23:20], jump-table index | RO, zero writers in 4.1 M lines of RM disassembly | `0xBADF1100` (poison) from the injection point |
| `0x85084` | Allowed-Gen mask [3:0], re-derived by GSP-RM every retrain | RO from reachable contexts | `0xBADF1100` |
| `0x88084` | `MAX_LINK_SPEED` [3:0] | PHY reflection, marked R-XVF | `0x00456101` stock |
| `0x8808C` | `SUPPORTED_LINK_SPEED` [7:1] | PHY reflection, marked R-EVF (no write port) | PROT-walled from host |
| `0x880A8` | `TARGET_LINK_SPEED` | RW but capped by SUPPORTED | `0x00000001` stock |
| `0x8841C` | `PRIV_MISC_1` CYA Gen2/3 override bits 11-16, 30, 31 | RW under PLM | `0x20340500` to `0x20342d00` |
| `0x88610` | `VSEC_HIERARCHY`, bit 12 gates PRIV_MISC_1 reprogram | RW under PLM | live `0x00001001` |
| `0x8872C` | LTSSM trigger (write `6`) | RW under PLM | not a real retrain |
| `0x8C1C0` | `PL_LINK_RATE`, gen field [19:16] | RW under PLM | written `0x00240036` by 0007 |
| `0x881C0` | `PPCI.UNK1C0`, [17:16] `LNK_CAP_SPEED`, [21:20] `SYSTEM_MAX_SPEED` | host reads blocked | `0xbadf5040`; A100 twin `0x8C1C0` reads `0x00040036` |

Speed-vector encodings: Gen1 = `0x1`, Gen1_2 = `0x3`, Gen1_2_3 = `0x7`, Gen1_2_3_4 = `0xF`.

A forced-generation sweep on a reference A100 80GB pins where link rate actually lives, and is
the cleanest control measurement available:

| Forced gen | `0x88088` (speed at [19:16]) | `0x880a8` (target at [3:0]) | `0x88084` |
|---|---|---|---|
| Gen1 | `0x11010140` | `0x001e0001` | `0x00456104` or `0x00457104` |
| Gen2 | `0x11020140` | `0x001f0002` | unchanged, nibble always 4 |
| Gen3 | `0x11030140` | `0x001f0003` | unchanged |
| Native | `0x11040140` | `0x001f0004` | unchanged |

---

## What has been tried and failed

### Register and configuration-space attacks

| # | Approach | Why it was plausible | How it died | Date |
|---|---|---|---|---|
| 1 | `setpci` write to LnkCap2 (config `0x2C`) with all speeds set | It is literally the register that lists supported speeds | Silently dropped. Hardware read-only, marked `R-EVF` in NVIDIA's `dev_nv_xve3g_fn0` header: no write port at any privilege level, so opening a PLM cannot help | 2026-07-24 |
| 2 | Raise `TARGET_LINK_SPEED` (`0x880A8`) and retrain, alone | TARGET is genuinely writable | Link re-trains at Gen1; the endpoint re-advertises Gen1 in its TS1/TS2 ordered sets, bounded by the read-only SUPPORTED field | 2026-07-24 |
| 3 | Host BAR0 writes to `0x88070` / `0x8808C` / `0x88090` | Adjacent to the capability block | PROT-walled from the host: reads return 0, writes ignored | 2026-07-24 |
| 4 | High-secure XP3G PHY-rate override in isolation | PLM opened, override registers writable, rate read back Gen3-capable `0x00340036` | Link stayed Gen1. It did prove a positive: the `0x10B9` SEC2 CSB mailbox gadget reaches the XP3G/PCIe privilege block. Later became a *component* of the working Gen2 combination | 2026-07-24 |
| 5 | High-secure `FEAT_OVR` write plus retrain | The compute unlock works by exactly this route | `0x823800` read back `0xfffffe8e` (the write took), `OPT_GEN23` stayed `0x1`, link stayed Gen1, AER = 0. Conclusion drawn at the time: a PCIe override-enable fused **off** in FEAT_OVR, unlike `SM_SPD` which is fused **on**. Note the [FEAT_OVR inventory](nvlink.md#route-b-a-feat_ovr-style-attack) lists no PCIe register in that block, so treat this as the probe outcome rather than a located register | 2026-07-24 |
| 6 | Direct write of `OPT_GEN23` (`0x82057C` <- 0) | Obvious lever | Fails from host, from HS-ROP, and through the Booter payload. Still attempted by the shipped Gen2 patch, still fails, Gen2 works anyway | 2026-07-23 |
| 7 | Set `VSEC_DEVICE` bit 0 through the Booter | Part of the published sequence | `pre=0x00000800 want=0x00000801`, failed twice with `rd=0x00000800`. Awkward for the "transient window" model, which blames window closure on RM clearing a bit the patch never set | 2026-07-23 |
| 8 | Write the derived allowed-Gen mask `0x85084` at postbl | "GSP writes `0x85084`" is true | Both `0x85080` and `0x85084` read `0xBADF1100` from the injection point and writes are dropped. GSP writes it at a privilege the injection point never reaches, and re-derives it every retrain anyway | 2026-07-24 |
| 9 | BAR0 `0x8872c` value sweep under VFIO/QEMU | LTSSM-adjacent | `0x6` is stable and leaves the LTSSM at Gen1 x4; `0x2` and `0xA` expose extra Gen2 behaviour but eventually wedge the VFIO/QEMU function. Shipping 0007 writes exactly `0x6` and its own log says "skip mid-boot retrain" | 2026-07-12 |
| 10 | `0x88084` `MAX_LINK_SPEED` as a writable cap | An analysis concluded there is no host-writable backing register | An HS write to a scratch register succeeded while the same write to the whole XP-PL `LINK_CONFIG` cluster (`0x8C044` / `0x8C048` / `0x8C04C`) was rejected. The relayer flagged the analysis as probably wrong, but the checked parts hold up: that cluster is genuinely distinct from `0x8C040`/`0x8C2C0`/`0x8C1C0`, which are the ones the working patch uses | 2026-07-12 |
| 11 | `0x8c044` (XP_PL) as the link-rate register | Named candidate `0x8c044/0x2` | Reads `0xbadf5040`, the priv-masked sentinel; the probe write-test skips it. Notably the same three registers read `0xbadf5040` at *every* generation on a reference A100 | 2026-07-20 |

### Firmware and signing attacks

| # | Approach | How it died |
|---|---|---|
| 12 | Edit the VBIOS devinit Gen-strap bytes | 5 bytes across 3 devinit sites (found by searching for references to Falcon register `0x14118F78`, byte pattern `78 8f 11 14`). Differing bytes versus A100 SXM4: hit #8 `0xBB` to `0xE2`, hit #10 `72 DE` to `52 DD`, hit #11 `97/59` to `95/39`. All five are inside the `csecret(2)` MAC range. **CLOSED** |
| 13 | Reflash an edited VBIOS (`nvflash` / CH341A) | Ampere RSA signature check rejects it; card will not boot |
| 14 | RAM-patch TOCTOU (patch signed firmware between load and verify) | Closed on Ampere: signature validation happens **during** the DMA into IMEM, so there is no load-versus-verify window. Generalises to any firmware-level attack on this part |
| 15 | `csigenc` ACL-`0x13` spill (leak an HS secret past the 1-bit boot oracle) | Dead offline. `envydis` shows the SEC2 booter secure body is ciphertext from `0x101` to `0x86FB` under `csecret(6)` AES, with zero SCP/crypto opcodes in the plaintext stub. No pinnable ROP address |
| 16 | Master-key signature bypass / arbitrary HS Falcon code | No flaw exists. The known timing hole yields **data-only register pokes**, not arbitrary Falcon code, because the body is AES-encrypted and unsignable. Plaintext ends at `0x101`. No HS-reachable Ampere CVE exists |
| 17 | Leaked production HULK certificate | In-ROM at `0xFE504`, `csecret(40)`, `STRICT_ID_MATCH=NO`. Gated by the `RmActivateHulk` fmodel flag, false on production silicon; requires the cert files; and on-card FEAT_OVR writes do not move `OPT_GEN23` anyway (see #5). Largely mooted |
| 18 | `csecret(6)`/`csecret(2)` fault injection (EM or voltage glitching) | Roughly $400-2k of equipment, weeks of work, no guarantee, and the part would **still** be fuse-bound for PCIe afterwards. Tooling validated offline, equipment never acquired. A ChipSHOUTER CW520 was proposed and never attempted |

### Hardware and platform attacks

| # | Approach | How it died |
|---|---|---|
| 19 | Copy the A100's strap configuration onto a 170HX | Tried by a tester who already had Gen2 x16 working: **card not detected at boot**. Follow-up answers were blunt: "the straps don't do anything", "falcon is driving the rewrites", "there's no gen3 override register". Strap4 (`R999`/`R1000`, near `U808`) was mapped as `PCIE_CFG`. A second researcher independently found comparing strap profiles against a live A100 dump to be a dead end after two days |
| 20 | A plain PCIe redriver | A redriver only re-amplifies; the endpoint still sources its own fuse-capped TX rate. Only a **retimer**, which terminates the link and can advertise a different rate to each side, could forge TS1/TS2 Rate-ID. Named candidates: Astera Aries, TI DS160PR810-class. Never attempted |
| 21 | Full remove-and-rescan from inside the driver ("Option A") | Three caveats: the GSP boot hook runs inside `probe()`, so `pci_stop_and_remove_bus_device()` there is a use-after-free of its own context; after rescan the driver re-probes, GSP boots, the writes run and it rescans again (needs a module-global once-flag); and active CUDA clients are dropped. Option B (upstream-bridge retrain) shipped instead |
| 22 | Device-ID spoofing to present as an A100 | `FUSE_DEVID_SW_OVR_DIS` `0x00820584` = `0x00000001` on every Ampere part probed. Writing the XVE config shadow dword0 `0x88000 = 0x208210de` changes only the host-visible ID while `MAGIC_D` bit 25, PPCI_2 SPEED and the suppressed `0x88CE4` all remain |
| 23 | Flash a genuine A100 80GB VBIOS to restore PCIe 4.0 | Tested and failed, reported 2026-07-19: "Theyve tested that and it doesnt work. the pcie 4.0 bit at least." |
| 24 | VBIOS `CTRL_OPT` / HULK option regions as a PCIe lever | Structurally impossible: "CTRL_OPT is remove only, not add" |

### False claims worth recording

- A fork advertised as reaching **PCIe Gen 4** was debunked within an hour on 2026-07-19 ("This
  is BS, didn't work for me at all"). Both testers' hosts were limited to Gen3 anyway, so a Gen4
  result could not have been observed. Retracted 2026-07-21.
- **"PCIe Gen 3 is actually working" via AI-driven experimentation** (2026-07-24). No
  measurement, no register write and no link-status output was ever posted. The claim came in a
  joking register and was immediately followed by discussion still treating Gen3 and Gen4 as
  unsolved.
- A public rental listing advertising a 170HX at "PCIe 3.0" was judged incorrect reporting by
  the platform; the `OPT_GEN23` write failure was logged the same day.
- **"Gen 3.0 and 4.0 is a dead end due to fused blockers in the die"** was rebutted in-channel:
  "the fuses are signals used by the firmware to control function", "they're not hard efuses
  that actually destroy functionality". The rebuttal is better supported, because the Gen2
  unlock proves at least one fused gen limit is firmware-mediated and defeatable. Unsettled,
  leaning rebuttal.

---

## The Gen4 shadow experiment and its boot loop

A separate clean-room patch, `0007-pcie-gen4-shadow.patch` (not to be confused with the
cmpunlocker `0007-pcie-gen2.patch`, which is a different patch with the same number), was
abandoned to a boot loop and remains the most interesting unfinished Gen4 artefact.

> [!CAUTION]
> **This experiment bricks the boot cycle until the module is removed**
>
> Upstream patches `0001`-`0006` use 4 Booter payload runs per boot and boot fine. The Gen4
> shadow patch raised that to 7-11 runs including fuse and retrain attempts. The **real**
> BooterLoad then failed with `mailbox0 != 0` (status `0xffff`), after which RM retried
> `_kgspBootGspRm` endlessly, with `wprStart` sliding down the frame buffer on each retry
> (per-retry WPR allocation) and eventually wrapping.

One cause was eliminated: the loop persisted with `CMP_PCIE_RETRAIN=0`, ruling out the in-driver
retrain. Two hypotheses survived and were never decided:

- **H-COUNT.** Too many Booter / priv-sequencer executions immediately before the real boot
  exhaust sequencer state. Note `kgspExecuteBooterLoad_TU102` does `kflcnReset(SEC2)` before
  every run, so SEC2 accumulates no state, but the priv sequencer is separate hardware that is
  not reset, and the WPR2/PLM registers and XVE writes also survive.
- **H-WRITE.** A specific write disturbs the PCIe block over exactly the link the Booter uses to
  DMA its signature from sysmem. Prime suspects: `0x8C2C0` (LTSSM config) then `0x8C040`
  (SPEED).

The bisection harness already exists as compile-time switches: `CMP_PCIE_ONCE=1` (apply once per
module lifetime, since the writes persist, so a failed first cycle is followed by a clean second
cycle with values already applied), `CMP_PCIE_ATTEMPTS=1`, and the groups
`CMP_PCIE_XVE_LTSSM_WRITES`, `CMP_PCIE_VECTOR_SPOOF`, `CMP_PCIE_UNK1C0_WRITE`,
`CMP_PCIE_XVE_PHY_WRITES`. The prescribed bisection order is LTSSM first, then vector spoof,
then UNK1C0, then PHY last. The outcome was never recorded.

---

## The most promising remaining avenues

Ranked by cost, cheapest first. None of these has been done.

### 1. Write `0x00820580 = 0` through the xp3g table, then request TLS = 3

Cost: one boot. `FUSE_PCIE_GEN3_DIS` has never been written by anyone. The table mechanism
already exists in `0007-pcie-gen2.patch`; adding one entry and raising `target_gen` is a
few-line change. Expected result, given #6 above, is a `booter FAILED to set` line and
`rd=0x00000001`, but the negative is worth having on record. The decisive observation is
whether `LnkCap2` ever reaches `0x0000000E`.

### 2. Is `FUSE_PCIE_MAGIC_D` writable? Read, write `0x00200000`, read back

Cost: five minutes, never published. The evidence is genuinely contradictory. One analysis
annotates bit 25 `GEN4_SPEED_DISABLED` and marks the register explicitly **"(writable)"**,
contrasting it with `GEN23_DIS` which "needs no write". An independent clean-room chain script
records writing `0x00820520 = 0x00200000` (the A100 / Drive reference value) as part of a
*working* Gen2 chain. But the PCIe field manual lists `0x820580` / `0x820520` as read-only fuse-
option shadows, and `0007` only ever reads `0x00820520`. Since Gen4 is untestable, this has
never been exercised.

### 3. Read `0x85080` / `0x85084` / `0x881C0` from inside the SEC2 high-secure context

Cost: one instrumented build. All three read poison from the host and from the injection point.
`0x8e1b0` and `0x823800` have already been shown reachable from HS, so the read is feasible.
This is the only route to locating the strap layer that actually sources the supported-speeds
vector.

### 4. Test the second feature-override group at `0x823830`-`0x82383C`

Cost: one HS write-then-readback. Reads from PL0 return `0xbadf5040`; HS reads return real
values. No manual PLM covers the group and an HS write-then-readback has never been performed.
Explicitly listed under "writability still unknown / worth testing".

### 5. Dump `LnkSta2` equalization fields during a forced Gen3 attempt

Cost: one boot with instrumentation. The counter-hypothesis is that `GEN3_DIS` might be latched
at boot into a re-writable PHY/strap config register rather than consumed directly by the analog
PHY, in which case a post-boot register to overwrite would exist. The proposer bet against their
own idea. The measurement that would decide it is whether equalization Phase 1 is ever entered.

### 6. The GSP-RM patch

The stated requirement as of 2026-07-27, and the reason nobody has delivered: "I haven't seen
anybody at all get a working GSP patch." The concrete starting point is the pair of fuse-read
sites above (`0x5D55834` in `470.42.01 gsp.bin`, `0x4DD9B00` in `580.105.08 gsp_tu10x.bin`).
The question is whether that consumption can be diverted the way the Gen2 overrides divert the
Gen2 path. Encrypted GSP regions remain unreadable, which is the standing obstacle.

### 7. A signed or otherwise accepted flash with `[+0x0F] = 0x00` and `[+0xC9] = 0x14`

This is the only experiment that would settle whether the DevInit five-byte edit **alone** would
restore Gen4. The fuse reference gist asserts "PCIe double-locked: `FUSE_PCIE_GEN23_DIS` = `0x1`
(fuse) + devinit (5 bytes). Firmware-only patch insufficient", but that conclusion is an
inference from the fuse values, not the outcome of an attempted firmware patch. Nobody has ever
flashed a modified DevInit table, and nobody can without a signing key.

### 8. A wire-level retimer

Equipment-and-board-work gated. Someone with the parts and board-fab capability would need to
build an interposer that forges TS1/TS2 Rate-ID. Named candidates: Astera Aries, TI
DS160PR810-class. Nothing attempted.

### 9. Find a Gen4 host

Blocked on hardware before it is blocked on technique. The researcher working on Gen4 stated
plainly: "I can't do PCIe Gen 4 because I don't have a computer that supports it", and
separately that "devinit routes are genuinely horrible to try to work on".

### Low-priority leads

A researcher flagged `Mellanox-ConnectX-5-PCIe-Gen-4-Enablement` as an analogous
"shipped-downgraded part" case, explicitly "not expecting much". Nothing was attempted.

---

## The moving-target problem in the record

The Gen3 route changed direction four times inside a span of about 40 hours, which is worth knowing
before reading any single quote as the project's position:

| Timestamp | Position |
|---|---|
| 2026-07-26 06:38 | "a devinit route might be the only way" |
| 2026-07-26 14:25 | "My current fix doesn't use devinit, and it's a dead end" |
| 2026-07-26 14:42 | "We need to use devinit" |
| 2026-07-27 22:57 | "Gen 3 doesn't work whatsoever, it's going to require a GSP patch" / "I haven't seen anybody at all get a working GSP patch" |

The last of these is the state as of 2026-07-28.

The earlier "four-layer wall" field manual (dated 2026-07-24) concluded that all four layers
(runtime register writes, register semantics, durable firmware, silicon fuse) were empirically
closed, verified on two surfaces: a 4032-run offline firmware fuzz sweep (126 function-register
pairs drawn from 66 functions, each swept over 32 single-bit values) and on-silicon direct-write
probing. Its own
section 6 contains the reason it was wrong for Gen2: *"The full community Gen2 sequence ... as a
single combined write was not run: every component is individually proven inert, so it is a
low-odds combination."* The low-odds combination worked. **The Gen3 half of that conclusion
still stands.**

---

## If you are testing a Gen3 claim

> [!WARNING]
> **Verify with LnkSta, never LnkCap**
>
> `LnkCap` is the advertised capability and can read a higher generation while the link is
> still training at Gen1. That trap is the stated source of most "it works" claims that do not
> hold up. The Gen3 advertisement result of 2026-07-24 is exactly this case.

```bash
# the three honest fields
sudo lspci -vvs <bdf> | grep -E 'LnkCap:|LnkCap2:|LnkSta:'
cat /sys/bus/pci/devices/<bdf>/current_link_speed
nvidia-smi --query-gpu=pcie.link.gen.gpucurrent --format=csv
```

Two known false signals on this card:

- On a Gen2-trained 170HX, `/sys/.../max_link_speed` still reads `2.5 GT/s` while
  `current_link_speed` reads `5.0 GT/s`. Diagnose from config space, not from the sysfs
  attribute.
- `nvidia-smi` has reported `PCIe Generation Max : 2` on a stock card since 2023 while
  `Device Current` and `Device Max` both read `1` and `LnkCap2` lists only 2.5 GT/s. Useful only
  as a fingerprint.

ASPM is a genuine false-negative trap on other platforms (many idle the link down to Gen1), but
the 170HX itself advertises `ASPM not supported` in its own `LnkCap`, so it is a first
diagnostic rather than a likely cause here.

---

## Measured values

| Quantity | Value | Conditions | Confidence |
|---|---|---|---|
| `FUSE_PCIE_GEN23_DIS` `0x0082057c` | `0x00000001` | both 170HX SKUs, two physical units, read twice each; `0x00000000` on 13 comparison parts | high |
| `FUSE_PCIE_GEN3_DIS` `0x00820580` | `0x00000001` | same | high |
| `FUSE_PCIE_MAGIC_D` `0x00820520` | `0x16680000` (bit 25 set) | 170HX; A100 family `0x00200000` | high |
| `OPT_PCIE_LANE_DISABLE` `0x00820394` | `0x00000000` | 170HX | high |
| `CTRL_OPT_PCIE_LANE` `0x0082082c` | `0x00000000` | 170HX | high |
| `STATUS_OPT_PCIE_LANE` `0x00820c2c` | `0x00000000` | 170HX | high |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000` | 170HX and all datacenter GA100; `0x00000001` on consumer parts | high |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | all cards | high |
| `0x00820148` (DevInit MAGIC_D gate) | `0x00000000` | OTP spare bit, never settable from software | high |
| `OPT=` triple in Gen2 dmesg | `00000001/00000001/16680000` | GEN23 / GEN3 / MAGIC after a full Gen2 run | high |
| XP3G rate after PLM open | `0x00340036`, `ovr0 = 0x4` | writes take, link stays Gen1 (`lnksta=0x10410040`, speed 1) | high |
| `0x85080` / `0x85084` | `0xBADF1100` (poison) | read from the injection point | high |
| `0x881C0` host read | `0xbadf5040` | priv-blocked pattern | high |
| `0x8C1C0` on A100 | `0x00040036` | PPCI_2 UNK1C0 reference | high |
| `A100 0x8C044` / `0x8C048` / `0x8C04C` | `0xbadf5040` at every generation | masked even on the reference card | high |
| CMP `0x88CE4` | `0x0000003F` | versus A100 `0x00000014` | high |
| CMP `0x88CE0` low 6 bits | `0x02` | versus A100 `0x06` | high |
| CMP `0x8C040` `PPCI_2.CONFIG_LINK` | `0x800C4C00` (SPEED = 3) | BAR0 mmap, no driver; A100 `0x80004C00` (SPEED = 0) | high |
| CMP `0x8C2C0` | `0x068731B7` | versus A100 `0x060711B2` | high |
| CMP `0x880A8` | `0x00000001` | versus A100 `0x001F0004` | high |
| CMP `0x88084` / `0x880A4` | `0x00456101` / `0x00000002` | versus A100 `0x00457104` / `0x0180001E` | high |
| `0x118F78` / `0x132B70` | `0` / `0` on both CMP and A100 | **BAR0 mmap, no driver loaded** (the same address returns `0xbadf1100` on a host read with the driver up); identical values cannot encode a SKU restriction | high |
| `0x132B30` / `0x132B6C` / `0x132B50` | `0x00000400` / `0x08000020` / `0x03780000` on both | idle, no driver | high |
| LTSSM timeouts `0x8D1A0` / `0x8D1A4` | `0x1B1F2327` / `0x0B0F1317` | identical CMP and A100 | high |
| Booter payload runs per boot | 4 (patches 0001-0006, boots fine) vs 7-11 (Gen4 experiment, boot loop) | GSP boot | high |
| Booter payload run status | `0xffff` on every run, even when the write lands | register readback is the only valid verdict | high |
| SEC2_DEBUG dmesg line count | 29 (archived single-card capture), 34 (Gen1 build), 80 (Gen2 build), 134 (archived two-card Gen2-branch 610.43.03 log), 152 (`pcielink.sh` on two two-card Gen2 rigs) | **not a reliable cross-build fingerprint**; do not read a mismatch as a failed install | high |
| Gen3 advertisement result | `LnkCap Speed 8GT/s`, `LnkCtl2 Target 8GT/s`, `LnkSta Speed 2.5GT/s` | 2026-07-24 | high |

---

## See also

- [PCIe Gen2](../unlock/pcie-gen2.md) for the mechanism that does work
- [PCIe subsystem](../hardware/pcie-subsystem.md) for the register block map
- [Fuses and OTP](../hardware/fuses-and-otp.md) for the full fuse cohort
- [VBIOS](../hardware/vbios.md) for the DevInit image layout and signing
- [Physical mods](../operations/physical-mods.md) for the capacitor mod that changes width only
- [Dead ends](../history/dead-ends.md) and [Open questions](open-questions.md)
- [Status board](status-board.md)
