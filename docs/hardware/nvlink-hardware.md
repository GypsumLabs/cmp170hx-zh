# NVLink hardware

## What this page covers

The state of NVLink on the CMP 170HX: what is physically on the board, what the fuses say, what
you see in the boot log and why it is misleading, and precisely which doors are closed. The
unlock attempts, proposals and open research live on [NVLink frontier](../frontier/nvlink.md);
this page is the hardware description.

**Bottom line: NVLink on the CMP 170HX does not work, has never worked for anyone, and is
disabled by an OTP fuse rather than by software.** The links are not damaged, the connectors are
physically present on the PCB, the die scales to the full twelve-link GA100 complement, and none
of that helps, because `FUSE_NVLINK_DIS` at `0x00820684` reads `0x00000007` and no override
register exists that could countermand it. No code in the unlocker touches NVLink, on master or
on any of the twelve unreleased branches.

---

## The fuse evidence

Measured on both physical 170HX units in the May 2026 cross-card survey and re-read independently
off BAR0 on live cards of both the `0x20C2` (8 GB) and `0x2082` (10 GB) SKUs, on at least five
occasions between 2026-05-07 and 2026-07-27.

| Register | Address | 170HX | A100 ×3 | A10 / A5000 / A6000 | RTX 3080 / 3080 Ti | RTX 3090 / 3090 Ti | Drive A100 32 GB | Meaning |
|---|---|---|---|---|---|---|---|---|
| `FUSE_NVLINK_DIS` (`OPT_NVLINK_DISABLE`) | `0x00820684` | `0x00000007` | `0x00000000` | `0x00000000` | `0x00000001` | `0x00000000` | `0x00000007` | Disable mask, field `[2:0]`. All three bits set |
| `STATUS_OPT_NVLINK` | `0x00820DB8` | `0x00000007` | `0x00000000` | `0x00000000` | `0x00000001` | `0x00000000` | `0x00000007` | Read-only effective state, annotated 16-bit |
| `FUSE_NVLINK_DEFECTIVE` | `0x0082068C` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | Defective-link mask. **Zero: the silicon is intact** |
| `FUSE_NVLINK_DIS_CP` (`..._DISABLE_CP`) | `0x00820688` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | Critical-path disable, unused |
| `FUSE_NVLINK_MASK_SEC` | `0x00820704` | `0x00000005` | `0x00000005` | `0x00000085` | `0x00000085` | `0x00000085` | `0x00000005` | Mask write-security, 8-bit. Splits by architecture, not by tier |
| `FUSE_NVLINK_PHYS_DMG` | `0x00820BD4` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | `0x00000001` | Write-security bit on the damage flag. Uniform everywhere |
| `FUSE_NVLIPT_RST_DIS` | `0x00821100` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | NVLink IP reset-condition disable |
| `CTRL_OPT_NVLINK` | `0x008209B8` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | Effective per-link control, bits `[15:0]` |
| `CTRL_OPT_PERLINK` | `0x00820820` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | `0x00000000` | Per-link control, bits `[11:0]` |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246C` | `0x0000000c` | `0x0000000c` | `0x00000004` | `0x00000004` | `0x00000004` | `0x0000000c` | Links built into the die: **12** |

Three readings follow directly:

1. **The disable is deliberate segmentation, not salvage binning.** `FUSE_NVLINK_DEFECTIVE`, the
   field that would record a bad link group, reads `0x00000000` on the 170HX and on every card in
   the 15-card survey that returned a value; the A16 column reads the `BAR0` placeholder because
   its BAR0 is too small to reach most fuse registers, and the ES column is blank. If NVIDIA had
   fused these links off because they failed test, this register is where that would be written,
   and it is empty.
2. **The die carries the full GA100 NVLink complement.** `PTOP_SCAL_NUM_NVLINK = 0x0000000c`
   describes twelve links built into the silicon and is unaffected by the disable fuse. It is
   byte-identical to all three A100 SKUs and to the Drive A100.
3. **The disable arrives through the STATUS path, not through a control override.** Both
   `CTRL_OPT` registers read zero, so nothing set them; the raw fuse propagates straight into the
   read-only status register. This is the same pattern as every other floorsweep on the card, and
   it is documented on [Fuses and OTP](fuses-and-otp.md).

### It is not a mining-SKU restriction

The DRIVE A100 32 GB (PG199, `GA100-550F-A1`, `FUSE_PCIE_DEVIDA` = `0x000020bb`,
`FUSE_PCIE_DEVIDB` = `0x000020fb`), measured on two physical boards, reads exactly the same
`FUSE_NVLINK_DIS` = `0x00000007` and `STATUS_OPT_NVLINK` = `0x00000007`. All three regular A100
SKUs read `0x00000000`. An NVLink-fused-off GA100 is therefore a normal thing for NVIDIA to ship,
which weakens any theory that this particular disable is a crypto-mining countermeasure that
might have a corresponding escape hatch.

Note also that the `0x20bb` "A100-class comparison card" referred to in some writeups as also
reading `7` **is** this Drive A100, not a fourth A100 SKU. The device IDs match.

### Two corrections worth carrying

!!! note "Superseded: `FUSE_NVLINK_PHYS_DMG = 0x1` means nothing about this card"
    The register's full name is `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE`, and several
    writeups flagged the set bit as ominous, possibly making the disable non-recoverable. It
    reads `0x00000001` on all fourteen probed Ampere cards, including healthy A100s with fully
    working NVLink. It is a **write-security bit on the damage-flag register**, set
    architecture-wide. The register that would actually record damage is
    `FUSE_NVLINK_DEFECTIVE` at `0x0082068C`, and it reads zero.

!!! note "Superseded: GA102 does not read zero for `PTOP_SCAL_NUM_NVLINK`"
    The claim "A100 = 12, 3090 = 0" appears in at least four writeups. It originates as an inline
    comment in the project's own probe script:
    `("PTOP_SCAL_NUM_NVLINK", 0x0002246C, "max NVLink count; A100=12, 3090=0")`. The same
    project's measured table contradicts it: RTX 3090, RTX 3090 Ti, RTX 3080, RTX 3080 Ti, A10,
    A5000 and A6000 all read `0x00000004`. Only the A16 reads `0x00000000`. The measured `0x4`
    matches NVIDIA's documented "four x4 links" for third-generation NVLink on GA102 exactly,
    which independently confirms the measurement over the comment.

!!! question "Open problem: a 3-bit disable field against 12 physical links"
    `FUSE_NVLINK_DIS[2:0]` = `0x7` with `PTOP_SCAL_NUM_NVLINK` = 12, and `STATUS_OPT_NVLINK` is
    annotated as a 16-bit field yet also reads `0x00000007`. The working hypothesis, unconfirmed
    by anything in the corpus, is **three link groups of four links each** (12 = 3 × 4), which
    would explain both the recurring "all groups" phrasing and the RTX 3080's `0x1` against its
    `PTOP_SCAL_NUM_NVLINK` of `0x4`. What would settle it: an A100 with a known *partial* NVLink
    floorsweep to compare against, or vendor documentation of the
    `NV_FUSE_OPT_NVLINK_DISABLE` field width on GA100. Neither exists in the corpus.

---

## The physical board

The CMP 170HX reuses the A100 board layout. **The gold fingers of the NVLink edge interface are
physically present, and three bridge connector positions exist.** This was established by an
external teardown in October 2023 and agreed by card owners in 2026.

!!! note "Correction: 'the CMP PCB lacks the NVLink connector entirely' is about the 90HX"
    The observation "the case has an opening for the NVLink connector, but the PCB lacks it"
    appears twice in the archive: once attributed to the 170HX, and once, with the fuller context
    that "the same unknown brand also makes an RTX 3080 20 GB [which] uses a PCB with the NVLink
    connectors", attributed to the **CMP 90HX**. The 90HX is a GA102 RTX 3080-class mining board,
    which is exactly what that RTX 3080 20 GB sibling remark describes. Applied to the 170HX the
    claim contradicts the teardown evidence. Treat the 170HX-attributed instance, and the
    parenthetical "CMP boards have no NVLink connector" in one writeup, as mis-attributions.

### The shroud is in the way

The aluminium shroud covers the connector area. Nothing can be seated until it is machined,
removed or replaced. This is the same situation as the Tesla P100: NVIDIA covers the connector
with a rubber cap on the A100 and the official bridge clips onto the A100 housing, which the
170HX does not have. One photograph exists of a P100 with dremeled cut-outs and its electrical
outcome is unknown. One water block is reported to leave the NVLink area exposed. Redesigning the
cooler for physical access was named as the practical first step in this domain, ahead of any
electrical work. See [Cooling](../operations/cooling.md).

### Populated or depopulated: leans depopulated, not settled

This is the most consequential open question about the board, because it decides whether a fuse
bypass would even be useful. The weight of evidence is on the depopulated side: the only direct
A100-versus-CMP board comparison in the record reports parts missing, and the counter-claim is
read off schematics rather than off a board.

**Evidence for depopulated.** The 2023 teardown states that "because the CMP 170HX uses the same
NVIDIA A100 circuit board, the gold fingers of the NVLink interface exist, but the feature is
unsupported with all components unpopulated on the PCB", and separately that "ICs related to the
NVLink interface are also missing". Working from A100 schematics, a researcher identified five
specific depopulated resistors above the GPU: `R234` (000), `R237` (NP), `R236` (1k), `R1024`
(000) and `R238` (000), all from page 17, plus `R976`, `R1029` and `R1030`, and three
GPU-to-ground termination resistors with no visible tracks. A second participant recalled absent
parts of the NVLink power supply.

That list was produced with both boards in view: the resistors "are populated on a genuine A100,
but missing on CMP".

**Evidence for populated.** The project's own VBIOS comparison table records "NVLink bridge:
external bridge absent (PCB fully populated)", which is a project document row rather than an
inspection. Two hours before the resistor list was posted, another researcher said "I do not
believe there are any missing NVLink components. According to the schematics, the GPU die is
connected directly to the edge connectors", blaming the confusion on the bridge carrying active
components "including a ROM chip". Direct inspection of an official A100 bridge later found no
EEPROM and no clock generator, so that stated basis does not hold.

**The complicating detail:** `R237` is marked **NP** (not populated) in the A100 schematic
itself, so at least one of those five is expected absent on a genuine A100 too. That is a clean
illustration of how easily a by-eye comparison misleads.

**What would settle it:** side-by-side high-resolution photographs of a de-shrouded 170HX and a
genuine A100 at those designators, or a continuity check from the NVLink edge fingers to BGA
balls `F1` and `G1`. Neither exists. Note that `R976` lands on ball `F51`, under the chip, on a
package with a minimum of 82 ball rows, so it cannot be reached without professional infrared SMD
rework or die removal; `R1029` and `R1030` tie to `F1` and `G1` at the chip edge and could be
reached with thin wire.

Even a perfect rework leaves `FUSE_NVLINK_DIS` at `0x00000007`.

---

## What appears in the boot log

Every 170HX boot with the NVIDIA driver loaded produces this line:

```text
nvidia-nvlink: Nvlink Core is being initialized, major device number 236
```

**It is benign and it is not evidence of link training.** It originates at `nvlink_linux.c:344`
in the `nvidia-nvlink.ko` software core library, announcing that the module loaded. It is logged
at `DBG_INFO`, it fires during early module load before GPU and GSP bring-up, and it appears on
essentially every driver load on any NVIDIA GPU. The "236" is a dynamically allocated Linux
character-device major from `alloc_chrdev_region` and can differ from boot to boot, so a
different number in your log means nothing either.

The authoritative check takes one command:

```console
$ nvidia-smi nvlink -s
Device does not have or support Nvlink.
```

That output is recorded once in the corpus, from a rented 8-card host of unlocked 64 GiB cards on
2026-07-24, so treat it as consistent with the fuse rather than as a broad survey. Corroborate it
against the fuse if you want certainty:

```bash
# STATUS_OPT_NVLINK, the read-only effective state
sudo python3 - <<'EOF'
import mmap, struct
BDF = '0000:81:00.0'
with open(f'/sys/bus/pci/devices/{BDF}/resource0','rb') as f:
    bar = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for name, off in (('FUSE_NVLINK_DIS', 0x00820684),
                      ('STATUS_OPT_NVLINK', 0x00820DB8),
                      ('FUSE_NVLINK_DEFECTIVE', 0x0082068C),
                      ('PTOP_SCAL_NUM_NVLINK', 0x0002246C)):
        print(f'{name:22s} 0x{off:08x} = 0x{struct.unpack_from("<I", bar, off)[0]:08x}')
EOF
```

Expected on any CMP 170HX: `0x00000007`, `0x00000007`, `0x00000000`, `0x0000000c`.

!!! note "Superseded: 'NVLink already shows in the boot logs, so we just need a bridge'"
    Raised on 2026-07-16 and again on 2026-07-20, refuted by the analysis above. It is the single
    most common wrong conclusion about this card and it is entirely understandable, because the
    dmesg line does read like the subsystem coming up.

---

## Why it stays locked

Four independent doors, each closed for a different reason. All four have to open. A fifth
section records that the unlocker never tries any of them.

### 1. The value comes out of OTP, not software

The disable is read out of an OTP fuse at `0x00820684` and mirrored into a read-only status
register. There is no software setting in the driver, in the VBIOS signed region, or in the
unsigned FwSec tail that produces it. The claim "NVLink is software locked as well", still
circulating on 2026-07-27, is simply wrong.

### 2. There is no FEAT_OVR register to write

The compute unlock works by opening `FEAT_OVR_PLM` at `0x00823804` and writing the feature
override registers in the same block. The obvious question is whether the same trick reaches
NVLink. It does not, because the block contains no NVLink entry. The complete inventory of
`0x00823800` to `0x0082382C`:

| Address | Register |
|---|---|
| `0x00823800` | `FEAT_OVR_ECC_PLM` |
| `0x00823804` | `FEAT_OVR_PLM` |
| `0x00823808` | `FEAT_OVR_QUADRO` |
| `0x0082380C` | `FEAT_OVR_ECC` |
| `0x00823810` | `FEAT_OVR_ECC_1` |
| `0x00823814` | `FEAT_READOUT_0` |
| `0x00823818` | `FEAT_READOUT_1` |
| `0x0082381C` | `FEAT_OVR_SM_SPD` |
| `0x00823820` | `FEAT_OVR_SM_SPD_1` |
| `0x00823824` | `FEAT_OVR_ROW_REMAP` |
| `0x00823828` | `FEAT_READOUT_2` |
| `0x0082382C` | `FEAT_OVR_ECC_2` |

Twelve registers, covering ECC, the Quadro classification word, SM speed select, the row
remapper and three readouts. Nothing for NVLink. The argument that "`FUSE_FEAT_OVR_DIS` reads
zero on all cards, so a FEAT_OVR-style attack on the NVLink mask is at least not obviously
precluded" is therefore wrong in its conclusion though right about the fuse: it **is** precluded,
because there is no such register to write.

### 3. The CTRL_OPT override path is fuse-disabled

`CTRL_OPT_NVLINK` at `0x008209B8` is documented as the effective per-link enable, it reads zero,
and it is described as writable. It is the most-cited candidate lever in the entire corpus. It is
also almost certainly inert here, because `FUSE_EN_SW_OVERRIDE` at `0x00820040` reads
`0x00000000` on both 170HX units, on all three A100 SKUs and on the Drive A100, against
`0x00000001` on every consumer and engineering-sample part. `FUSE_DIS_SW_OVR` at `0x00820084`
reads `0x00000001` on every card. The 25-entry `NV_FUSE_CTRL_OPT_*` table found at offset
`0x47341` inside the unsigned FwSec VBIOS tail (`0x43A00` to `0x47700`) reads all zero across 13
probed GA100 cards and is inert on this hardware.

!!! question "Open problem: nobody has ever performed the write"
    Across all 31 archived unlocker attachments and every clean-room artifact, NVLink appears
    only as fuse read-outs. There is no probe script, no override attempt and no recorded write.
    The strong prior is that a write to `0x008209B8` is dropped and `STATUS_OPT_NVLINK` stays
    `0x00000007`. That negative is still worth having on record, because right now the corpus
    cannot say whether it was tried. The experiment is a read-write-read on an expendable card
    followed by a re-read of `0x00820DB8`.

### 4. No spoofable consumer of the fuse has been found

The CMP DevInit firmware **reads** `0x820684`. The complete inventory of `0x1482xxxx` accesses
(MMIO `0x82xxxx`) in the DevInit disassembly is `0x820C14` and `0x820D38` (FBIO and FBP
floorsweep), `0x820684` (`FUSE_NVLINK_DIS`), `0x82380C` and `0x823814`, `0x820520` (`MAGIC_D`)
and `0x820148`. Nothing in any source writes it, and no effective override consumer was ever
named. Nobody has traced what DevInit does with the value after reading it, which is the one
remaining tractable software question in this area.

### 5. The unlocker contains no NVLink code at all

A grep for `nvlink` and for every NVLink register address across the entire shipping `master`
tree returns nothing: not in `common/constants.yaml`, `driver/build.sh`, `driver/VERSION`,
`install.sh`, `remove.sh`, `README.md`, nor in any of the six patches. `constants.yaml` declares
only the two driver versions, the two device IDs, the compute values and the two memory profiles.

Across all twelve unreleased branches (`80`, `Gen2`, `PG199`, `clanker/driver-port`,
`debug-gen2`, `deced`, `docs`, `ecc`, `far`, `housekeeping`, `memory`, `multiple-cards`) the
entire NVLink presence is one word. The `housekeeping` and `memory` branches add a feature-status
table whose relevant rows read:

```markdown
| ECC          | Planned |
| NVLink       | Planned |
```

---

## What NVLink would have been worth

Included because the cost of the missing feature keeps getting mis-stated in both directions.

| Quantity | Value | Confidence |
|---|---|---|
| A100 PCIe NVLink per bridge | 200 GB/s | high |
| A100 PCIe pairwise total, all three bridges | 600 GB/s | high |
| Documented Ampere PCIe topology | 2 GPUs, all three bridges required | high |
| Ampere port structure | 4 sub-ports × 4 lanes at 50 Gbps per lane = 800 Gbps raw per port (the source states 200 Gbps; the decomposition and the figure cannot both be right) | medium |
| GA102 third-gen per link | 14.0625 GB/s bidirectional, four x4 links | high |
| GA102 third-gen totals | 56.25 GB/s bidirectional, 112.5 GB/s total aggregate between two GPUs | high |
| 170HX interconnect baseline today | PCIe Gen 1 x4, roughly 1 GB/s | high |

NVSwitch, and therefore anything wider than a pair, exists only inside SXM platforms such as DGX.
The official A100 bridge is a **bare passive PCB**: no clock generator, no EEPROM, no retimer, no
packet-processing ASIC, established by direct inspection and independently corroborated for SXM2
baseboards. Consumer RTX 3090 bridges do carry a clock generator, believed to be because NVIDIA
could not assume consumer motherboards supply the same PCIe reference clock. All bridges from
Ampere through the H200 NVL generation are assessed as passive.

How much this actually buys for inference is itself unsettled: one first-hand measurement on a
pair of RTX 3090s under vLLM tensor parallel showed only about a 10 percent throughput
improvement, while third-party published figures for the same class of setup show roughly 48
percent. Model, quantisation, batch size and concurrency differ or are unstated. The argument
that a 170HX would gain far more because its baseline is Gen 1 x4 rather than Gen 4 x16 is
reasoning only, and cannot be tested while the fuse stands. See
[LLM inference](../operations/llm-inference.md).

For pooling arithmetic, note that four unlocked 8 GB cards give 256 GB (4 × 65536 MiB) and four
unlocked 10 GB cards give 160 GB (4 × 40960 MiB). A widely quoted 320 GB figure for four 10 GB
cards assumes the 80 GB configuration, which was attempted and found unstable. See
[80 GB](../frontier/80gb.md).

**The working alternative today is PCIe peer-to-peer, not NVLink.** See
[Peer-to-peer](../frontier/p2p.md).

---

## Common wrong answers

| Claim | Why it looked right | What kills it |
|---|---|---|
| "NVLink is in the boot logs, just add a bridge" | The dmesg line genuinely appears on every boot | It is the software core library announcing it loaded, at `DBG_INFO`, before GPU bring-up |
| "NVLink is software locked" | Several other 170HX restrictions genuinely are | The value comes out of OTP and is mirrored into a read-only register |
| "Encryption named HULK is the blocker" | It was the only published explanation, on an authoritative-looking page | Disowned by that site's maintainer on 2026-07-20 and called outdated by the page's own author; nothing in any fuse readout, VBIOS dump or DevInit disassembly corroborates it |
| "`PHYS_DMG = 1` means the links are marked damaged" | The register name says physical damage | It reads `1` on all fourteen probed cards including healthy A100s. It is a write-security bit |
| "3090 reads `0` links, so the 170HX gives up 12 versus 0" | It is a comment in the project's own probe script | Measured `0x4` on every GA10x part except the A16 |
| "The dies failed NVLink test, hence the binning" | It is how salvage binning usually works | `FUSE_NVLINK_DEFECTIVE` = `0x00000000` on every card probed |
| "Titan V had NVLink disabled in VBIOS, so this is firmware-gated" | A real precedent on an earlier NVIDIA part | On the 170HX the value comes out of an OTP fuse, not a VBIOS setting. The mechanism does not transfer |
| "Write `CTRL_OPT_NVLINK` and it opens" | Documented as the effective per-link enable, reads zero, described as writable | `FUSE_EN_SW_OVERRIDE` = `0`. Strong prior, never actually tested |

More, with dates and sources, on [Dead ends](../history/dead-ends.md).

---

## Status

| Question | State |
|---|---|
| Is NVLink usable on a 170HX? | No, and no path is known |
| Is the silicon damaged? | No. `DEFECTIVE` = `0x00000000` |
| Are the connectors on the board? | Yes, gold fingers and three positions. Blocked by the shroud |
| Is the connector area populated? | **Unresolved.** Direct evidence on both sides |
| Has anyone attempted a register-level unlock? | No. Not once, on any card |
| Has anyone seated a bridge on a 170HX? | No. Nobody in the corpus has ever had a card and a bridge at the same time |
| Is there any NVLink code in the unlocker? | No. One word, "Planned", in two branch README tables |

## See also

- [Fuses and OTP](fuses-and-otp.md) for the full fuse survey this page draws on
- [NVLink frontier](../frontier/nvlink.md) for every attempt, proposal and open question
- [Peer-to-peer](../frontier/p2p.md) for the working cross-GPU alternative
- [PCIe subsystem](pcie-subsystem.md) for the interconnect you do have
- [Board and variants](board-and-variants.md) for the PCB itself
- [Multi-GPU](../procedures/multi-gpu.md) for running several cards without NVLink
- [Open questions](../frontier/open-questions.md)
