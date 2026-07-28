# NVLink: fused off, no lever found

**What this page covers.** The complete state of NVLink on the CMP 170HX: the fuse readings that
prove it is disabled in one-time-programmable silicon rather than in software, everything that
has been probed, every override path that was proposed and why each one is closed, the physical
connector and bridge situation, and the short list of experiments that would actually advance
the question.

**The headline: NVLink on the CMP 170HX does not work, has never worked for anyone in the
corpus, and no unlock has been attempted at register level.** It is disabled by OTP fuse, not by
software. Not one line of code in cmpunlocker (shipping `master` or any of the 12 unreleased
branch snapshots) touches NVLink. The entire presence of NVLink in the branch set is a single
word, `Planned`, in two README feature tables.

!!! question "Open problem"
    This is the highest-value unknown in the domain and there is nothing tractable on the table.
    Both override paths are closed: `CTRL_OPT` by `FUSE_EN_SW_OVERRIDE` = `0x0`, and the
    `FEAT_OVR` route by the absence of any NVLink register in that block. As one summary from
    2026-07-20 put it: "Still unsolved rn, a bit harder as there's no fuse mask."

**What the capability would be.** NVLink behaves like MMIO: remote memory at the far end of a link
can be mapped into the local GPU's address space and driven by CUDA kernels or the copy engine.
From the exploit's original author, confidence medium. Never demonstrated on a 170HX, because no
link has ever come up. This direct addressability is the reason pooled memory across bridged cards
would be worth anything at all.

---

## What the silicon says

Three readings define the situation, and they are mutually consistent across at least five
independent readbacks on both SKUs, plus a 15-card Ampere reference cohort.

| Register | Address | 170HX value | Meaning |
|---|---|---|---|
| `FUSE_NVLINK_DIS` (`OPT_NVLINK_DISABLE`) | `0x00820684` | `0x00000007` | All three bits of the `[2:0]` disable field are set |
| `STATUS_OPT_NVLINK` (read-only mirror) | `0x00820DB8` | `0x00000007` | The effective state the rest of the chip sees |
| `PTOP_SCAL_NUM_NVLINK` | `0x0002246C` | `0x0000000c` | The die scales to 12 links, exactly like every A100 |

Then the three that say the silicon is healthy:

| Register | Address | 170HX value | Meaning |
|---|---|---|---|
| `FUSE_NVLINK_DEFECTIVE` | `0x0082068C` | `0x00000000` | Not a yield repair. One survey reports `0` on every card in its 15-card cohort that returned a value; the A16 column reads the `BAR0` placeholder and the ES column is blank |
| `FUSE_NVLINK_DIS_CP` (disable critical path) | `0x00820688` | `0x00000000` | Not disabled at the critical-path level |
| `FUSE_NVLIPT_RST_DIS` | `0x00821100` | `0x00000000` | The NVLink IP reset condition is not disabled |

And the four that cover the override machinery, the last two of which show it is shut:

| Register | Address | 170HX value | Meaning |
|---|---|---|---|
| `CTRL_OPT_NVLINK` (effective, bits 15:0 per link) | `0x008209B8` | `0x00000000` | No CTRL override is set; the disable arrives through the STATUS path |
| `CTRL_OPT_PERLINK` (bits 11:0) | `0x00820820` | `0x00000000` | Same |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | `0x00000000` | The whole `CTRL_OPT` override mechanism is fuse-disabled |
| `FUSE_DIS_SW_OVR` | `0x00820084` | `0x00000001` | Confirms the above from the other direction |

The conclusion the corpus reaches: **this is deliberate product segmentation, not salvage
binning.** The links are physically built, the die reports 12 of them, none is marked defective,
and the disable is a fuse.

### It is not a mining-SKU restriction

The Drive A100 32 GB (PG199, `GA100-550F-A1`, `FUSE_PCIE_DEVIDA` = `0x000020bb`,
`FUSE_PCIE_DEVIDB` = `0x000020fb`) reads exactly the same `FUSE_NVLINK_DIS` = `0x00000007` and
`STATUS_OPT_NVLINK` = `0x00000007`, measured on two physical PG199 boards. All three regular
A100 SKUs read `0x00000000`. Any theory that treats the NVLink fuse as a crypto-mining-specific
punishment has to explain the Drive part.

### Write security splits by architecture, not by SKU

`OPT_SECURE_NVLINK_MASK_WR_SECURE` at `0x00820704` reads `0x00000005` on **every** GA100 part
(both 170HX units, all three A100 SKUs, the Drive A100) and `0x00000085` on every GA10x part.
The 170HX is not specially locked relative to a normal A100.

!!! note "Superseded: `FUSE_NVLINK_PHYS_DMG = 0x1` means nothing here"
    `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE` at `0x00820BD4` reads `0x00000001` uniformly
    on all fourteen probed Ampere cards, including healthy A100s with fully working NVLink.
    Several write-ups flagged it as "notable because it may make the disable non-recoverable";
    that inference does not survive the cross-card comparison. It is a **write-security bit on
    the physical-damage flag register**, set architecture-wide. The register that would actually
    record damage is `FUSE_NVLINK_DEFECTIVE`, and it reads zero.

!!! note "Superseded: 'the 3090 reads 0 for `PTOP_SCAL_NUM_NVLINK`'"
    This string propagated into at least four write-ups from an inline comment in the project's
    own `probe.sh` line 171: `("PTOP_SCAL_NUM_NVLINK", 0x0002246C, "max NVLink count; A100=12,
    3090=0")`. The project's own measured table contradicts it: RTX 3090, 3090 Ti, 3080, 3080
    Ti, A10, A5000 and A6000 all read `0x00000004`. Only the A16 reads `0x00000000`. The
    measured `0x4` matches NVIDIA's documented "four x4 links" for third-generation NVLink on
    GA102 exactly, which confirms the measurement over the comment.

---

## What the code says

A grep for `nvlink` and for every NVLink register address across the shipping `master` tree
returns nothing. Not in `common/constants.yaml`, `driver/build.sh`, `driver/VERSION`,
`install.sh`, `remove.sh`, `README.md`, nor in any of the six patches
(`0001-sec2-postbl-plm-ss-cfg.patch` through `0006-persistent-sw-state.patch`).
`constants.yaml` declares only the two driver versions, the device IDs `20c2`/`2082`, the
compute values `ss0: 0x88888888` / `ss1: 0x00000008`, and the two memory profiles.

The unreleased branches are the same. Across all twelve (`80`, `Gen2`, `PG199`,
`clanker/driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`, `far`, `housekeeping`, `memory`,
`multiple-cards`), NVLink appears exactly once, as a table row:

```markdown
| PCIe Gen2 x4 | Platform-dependent (no separate Root-port patch) |
| ECC | Planned |
| NVLink | Planned |
```

That row set is in the `housekeeping` and `memory` branch READMEs only. There is no NVLink
logic anywhere.

---

## The two override routes, and why both are closed

### Route A: `CTRL_OPT_NVLINK`

This is the single most-cited "next step" in the whole corpus, and **nobody ever tried the
write**. It reads `0x00000000`, it is documented as the *effective* per-link enable/disable
field, and it is described as writable. It looks like the lever.

It is closed by a strong prior rather than by a performed experiment:

- `FUSE_EN_SW_OVERRIDE` at `0x00820040` = `0x00000000` on the 170HX and on all datacenter GA100
  parts, versus `0x00000001` on all consumer and engineering-sample parts. The `CTRL_OPT`
  override mechanism is itself disabled at the fuse level.
- `FUSE_DIS_SW_OVR` at `0x00820084` = `0x00000001` on all cards.
- The 25-entry `NV_FUSE_CTRL_OPT_*` table found at offset `0x47341` inside the unsigned FwSec
  VBIOS tail (`0x43A00`-`0x47700`, 15,616 bytes outside the MAC-verified range) reads all zero
  across 13 probed GA100 cards and is inert here.

Any plan that routes through `CTRL_OPT_NVLINK` has to defeat `FUSE_EN_SW_OVERRIDE` first, and no
mechanism for that exists.

### Route B: a `FEAT_OVR`-style attack

Attractive because the shipping compute unlock lives in exactly this register block, and because
the master override kill `FUSE_FEAT_OVR_DIS` at `0x008203F0` reads `0x00000000` on all cards
(that is, it is **not** blown). The reasoning ran: if the compute throttle can be overridden
here, maybe NVLink can too.

It is precluded outright, because there is no NVLink register in the block. The complete
inventory of `0x00823800`-`0x0082382C`:

| Address | Name |
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

Twelve entries covering ECC, Quadro classification, SM speed, row remapping and readouts. There
is nothing to write. The PCIe attempt on this same block is a useful comparison, and it is a
probe result rather than a second register: a high-secure write to `0x00823800` read back
`0xfffffe8e`, so the write took, yet `OPT_GEN23` (`0x82057C`) stayed `0x1` and the link stayed
Gen1. That outcome was read at the time as a PCIe override-enable fused **off**, although no PCIe
entry appears in the inventory above. `SM_SPD` at `0x0082381C` is a real entry and is fused
**on**, which is why the [compute unlock](../unlock/compute-throttle.md) works by that route and
the [PCIe speed unlock](pcie-gen3-gen4.md) does not.

### The DevInit angle

DevInit does read the fuse. The complete inventory of `0x1482xxxx` (MMIO `0x82xxxx`) accesses in
the CMP DevInit disassembly includes `0x820684` alongside `0x820C14`/`0x820D38` (FBIO/FBP
floorsweep), `0x82380C`/`0x823814`, `0x820520` (`MAGIC_D`) and `0x820148`. Nothing in any source
writes it, no effective override was named, and **nobody traced what happens to the value after
it is read** (confidence: medium; basis: the access inventory, not a full trace).

---

## Dead ends

Every one of these was a real, reasonable idea that someone pursued.

| # | Idea | Why it was plausible | How it died |
|---|---|---|---|
| 1 | "NVLink already shows in the boot logs, so we just need a bridge" | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` genuinely appears on every boot | The line is emitted at `nvlink_linux.c:344` by the `nvidia-nvlink.ko` software core library announcing it loaded. Logged at `DBG_INFO`, on essentially every driver load for any GPU, during early module load before GPU/GSP bring-up. The `236` is a dynamically allocated char-device major from `alloc_chrdev_region` and can differ per boot. The one recorded run of `nvidia-smi nvlink` returned "Device does not have or support Nvlink." |
| 2 | The "HULK" encryption blocker | It was the only published explanation, on a project-adjacent gitbook with an authoritative tone | The site maintainer disowned it on 2026-07-20 ("This hasn't been updated in some time, don't rely on that") and the page's own author called it outdated. Nothing in any fuse readout, VBIOS dump or DevInit disassembly corroborates an encryption scheme gating NVLink |
| 3 | "`FUSE_NVLINK_PHYS_DMG = 0x1` means the links are marked damaged" | The register name is `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE`; a set damage flag would be a one-way door | Reads `0x1` on all fourteen probed Ampere cards including healthy A100s |
| 4 | "NVLink is software locked" | Several other 170HX restrictions genuinely are firmware-side | The disable comes out of OTP fuse `0x00820684` and is mirrored into a read-only status register. Recorded because it was still circulating on 2026-07-27, the last day of the corpus |
| 5 | Titan V analogy: NVLink was disabled by VBIOS there | A genuine earlier precedent | On the 170HX the value comes out of an OTP fuse, not a VBIOS setting. The mechanism does not transfer |
| 6 | "Some dies have working VRAM but failing NVLink blocks, hence the binning" | Exactly how salvage binning usually works | `FUSE_NVLINK_DEFECTIVE` = `0x00000000` on every 170HX probed. That fuse is precisely the field that would record a bad link group |
| 7 | Soldering the missing NVLink parts on from A100 schematics | The boards match and the candidate parts were identified by designator | Blocked in order by: clean-room policy (schematics offered and refused); three GPU-to-ground termination resistors with no visible tracks, needing a boardview or GPU removal with professional infrared rework; `R976` landing on ball `F51` **under the chip** on a package with at least 82 ball rows; and, decisively, a perfect rework still leaves `FUSE_NVLINK_DIS` at `0x00000007` |
| 8 | Characterising NVLink signal integrity first | Correct engineering order for a multi-tens-of-GHz differential interface | The one available 60 GHz oscilloscope was judged insufficient; renting adequate equipment was estimated at a few thousand for a month. Conclusion adopted: "Not like we need traceability on DIY nvlink boards. They either work or they don't." |
| 9 | Microchip SM806022 clock generator on the A100 bridge | A real, correctly specified part (52.08333 MHz crystal in, two 156.25 MHz differential HCSL out) genuinely found on consumer Ampere bridges | Direct inspection of an official A100 bridge: bare PCB, no clock generator. The teardown summary that named it was machine-generated from consumer-bridge material |
| 10 | A100 bridges contain an EEPROM holding a device ID | Consumer bridges do carry one | "a100 nvlink has neither eeprom or sig gen", from direct inspection. The consumer EEPROM is believed to hold per-board end-of-line impedance characterisation, not an ID. Also confirmed for SXM2 baseboards: "No, only traces" |
| 11 | A cheap 4-card active NVLink backplane for A100 | Reported to exist; would solve the topology problem outright | NVIDIA documents only the pairwise all-three-bridges Ampere topology, and NVSwitch exists only inside SXM platforms. The one real product identified is a Chinese 4x SXM V100 backplane with no switch, a different generation with unknown wiring |
| 12 | A single-slot 8-way NVLink backplane | Real PCB CAD work existed: repeated `NVLink_MiniCoolEdge_124pin` footprints in a grid with differential-pair routing, `SlimSAS_MCIO_8x` connectors, "A100" in the copper pour | No board fabricated, no link brought up, no bandwidth measured. 8-way needs an NVSwitch that exists only in SXM. And the fuse is still `0x7`. The only signal-integrity input was a machine-written EM simulator predicting the traces "do a lot of antenna at 37ghz but the simulator says it will just barely work" |
| 13 | Buy one bridge, reverse-engineer it, manufacture copies | The bridges are assessed as fully passive by two people with datacenter hardware experience, and the economics are brutal at roughly 200 EUR each | Nobody bought one, nobody built one, nobody in the corpus ever had a bridge in hand: "I don't have a bridge to test". Also pointless while the fuse stands |
| 14 | Fabricate an A100 interposer from scratch | "the a100 interposer is pretty simple, just needs the connector", with a concrete signal-integrity strategy (Megtron laminate, non-standard inter-card orientation to shorten paths) | The connector needs a bulk order, with an open worry that the 90-degree panel-mount version may be export-restricted (edge-mount proposed as the workaround). No connector ordered, no board fabricated. And the interposer would plug into dead silicon |
| 15 | Mount two PLX backplanes face to face so the edge connectors align | Sidesteps slot spacing entirely | Pure speculation, never drawn, never costed, blocked by the same fuse |
| 16 | Treat NVLink as the fix for the multi-card bandwidth problem | The baseline is PCIe Gen1 x4 at roughly 1 GB/s, and tensor parallelism was repeatedly called "a waste of time without nvlink" | Tempered by a first-hand measurement on 2x RTX 3090 with NVLink showing only about a 10 % throughput bump on a 27B model under vLLM tensor parallel. The counterpoint that the relative gain on a Gen1 x4 baseline would be far larger is reasoning only, and untestable while the fuse stands |
| 17 | "The CMP PCB has no NVLink connector at all" | Someone genuinely observed a shroud with an NVLink opening over a PCB without the connector | That observation belongs to the CMP **90HX**, a GA102 RTX 3080-class board whose sibling "RTX 3080 20GB" from the same unbranded maker does use a PCB with NVLink connectors. Applied to the 170HX it contradicts the teardown evidence (confidence: medium; this is an internal reconciliation, not a fresh observation) |

---

## The physical situation

Independent of the fuse, there is a mechanical and a population question.

- **The gold fingers exist.** The 170HX reuses the A100 board layout; the NVLink edge fingers
  are physically present and three bridge connector positions exist. Established by an external
  teardown on 2023-10-25 and agreed by card owners.
- **The shroud blocks them.** The aluminium cover must be machined or removed before any bridge
  can be seated, the same situation as the Tesla P100. NVIDIA covers the connector with rubber
  on the A100 and the bridge clips onto the A100 housing, so fitting a bridge to a 170HX also
  requires sourcing an A100 case with the clips or fabricating equivalents. One photograph
  exists of a P100 with dremeled cut-outs; its electrical outcome is unknown. One Bykski
  waterblock is reported to leave the NVLink area exposed.
- **The bridge is dumb.** The official A100 NVLink bridge is a bare passive PCB: no clock
  generator, no EEPROM, no retimer, no packet-processing ASIC. Consumer 3090 SLI bridges *do*
  carry a clock generator, believed to be because NVIDIA could not assume consumer motherboards
  supply the same PCIe reference clock. All bridges from Ampere through H200-NVL are assessed as
  "dumb bridges"; a switch appears only in later generations.
- **You cannot buy a third-party one.** The only third-party Ampere bridge ever produced is the
  discontinued ElmorLabs NVB-3S, a 3-slot part for the RTX 3090, RTX A5000 and RTX A6000, not an
  A100 part. A market survey across two Chinese marketplaces found only official 2-slot and
  3-slot bridges at uniform prices, implying very low trading volume.

!!! question "Open problem: is the NVLink area of the PCB populated?"
    This is the most consequential open question in the domain, because it decides whether a fuse
    bypass would even be useful. The evidence leans **depopulated**: the only direct A100-versus-CMP
    board comparison in the corpus reports parts missing, and the counter-claim is a schematic
    inference rather than an observation.

    **Depopulated:** the 2023 teardown states "the gold fingers of the NV-Link interface exist,
    but the feature is unsupported with all components unpopulated on the PCB" and, separately,
    "ICs related to the NV-Link interface are also missing". A researcher working from A100
    schematics identified five specific depopulated resistors above the GPU (`R234` 000, `R237`
    NP, `R236` 1k, `R1024` 000, `R238` 000, all page 17) plus `R976`, `R1029`, `R1030` and three
    GPU-to-ground termination resistors. Another participant recalled "absent parts of power
    supply to nvlink".

    That resistor list came from comparing the two boards directly: "they are populated on a
    genuine A100, but missing on CMP". It is the only such side-by-side in the corpus.

    **Populated:** the project's own VBIOS comparison table states "NVLink bridge, external
    bridge absent (PCB fully populated)", which is a project document row rather than an
    inspection. Two hours *before* the resistor list was posted, another researcher said "I do
    not believe there are any missing NVlink components. According to the schematics, the GPU die
    is connected directly to the edge connectors", attributing the confusion to the bridge
    containing active components "including a ROM chip". That last premise is itself refuted:
    dead end #10 below records direct inspection finding no EEPROM on an A100 bridge.

    **The complicating detail:** `R237` is marked **NP** (not populated) in the A100 schematic
    itself, so at least one of the five is expected absent on a genuine A100 too. This shows how
    easily a by-eye comparison misleads, and it is why the conclusion is "leans depopulated, one
    direct comparison, unrebutted" rather than settled. Nobody has photographed the area on both
    boards for the record.

---

## Topology and bandwidth, for when it matters

Recorded so that nobody re-derives it, and because several circulating figures are wrong.

| Quantity | Value | Confidence |
|---|---|---|
| A100 PCIe supported topology | 2 GPUs, all three bridges required | high |
| A100 per-bridge bandwidth | 200 GB/s | high |
| A100 pairwise total | 600 GB/s | high |
| Ampere port structure | 4 sub-ports x 4 lanes at 50 Gbps per lane, stated as 200 Gbps per port; 4 x 4 x 50 is 800 Gbps, so the decomposition and the figure cannot both be right | medium |
| GA102 (RTX 3090) third-gen per-link | 14.0625 GB/s bidirectional, four x4 links | high |
| GA102 totals | 56.25 GB/s bidirectional, 112.5 GB/s total aggregate between two GPUs | high |
| NVSwitch | SXM platforms only (for example DGX); 8-way | high |

Three ratio claims are in play and none is cleanly settled. The channel settled on **3x** for
A100 versus 3090 (600 versus 200 GB/s), but NVIDIA's documented GA102 figure is 112.5 GB/s total
aggregate, giving **5.33x**. The 200 GB/s figure quoted for a 3090 is described in the same
discussion as "200 GB/s-class bridges downclocked", which argues the 3x comparison uses the
wrong convention. Both readings agree that the earlier "A100 has 6x the NVLink bandwidth of a
3090" claim is wrong. What would settle it: an explicit statement of whether the A100 600 GB/s
number is unidirectional-summed or total-aggregate.

!!! question "Open problem: 2-way or 4-way passive?"
    Three connectors is exactly the node degree needed for a fully connected four-node mesh, and
    200 GB/s per edge across 3 edges is 600 GB/s aggregate per card, arithmetically identical to
    the pairwise figure. So 4-way is geometrically coherent. What is **not** established is that
    NVIDIA's driver or firmware will train links to three different peers on a PCIe GA100. No
    documentation says so and nobody demonstrated it. The two claims are about different things
    (geometry versus supported configuration) and both may be true.

!!! warning "Do not size a build on the 320 GB figure"
    A 4-card NVLink discussion quoted 320 GB of pooled memory for four 10 GB cards. That assumes
    80 GB per card. The shipping unlock gives the 10 GB card **40 GB**, so four of them pool
    **160 GB**. Four unlocked 8 GB cards pool **256 GB**. The 80 GB configuration was attempted
    and found unstable: see [the 80 GB attempt](80gb.md).

---

## The PCIe peer-to-peer fallback

Because NVLink is unreachable, PCIe P2P is the only cross-GPU acceleration path with any chance
of working today. It is not in cmpunlocker: a grep for `p2p` and `peer` across `master` and every
branch returns only the stock `nvidia-peermem.ko` in `build.sh` install lists and one line of
unmodified context (`nv_uvm_resume_P2P(pUuid)`) inside the `0008` diff. No branch contains any
P2P enablement.

The candidate is a community fork of `tinygrad/open-gpu-kernel-modules`, default branch
`610.43.03-p2p`, on **the same driver version cmpunlocker targets**. `HEAD~3` is commit
`452cec62d827` "610.43.03" (2026-07-07), a plain NVIDIA release import. Three commits sit on top:

| Commit | Content | Size |
|---|---|---|
| `9fb650447c7b` | The combined P2P mod | 8 files, +83/-28 |
| `52670f7fd6a7` | Experimental hugepage `cudaHostRegister` acceleration | 7 files, +383/-97 |
| `2849449f8cd6` | README | +245 |

The P2P commit touches `install.sh` (+7), `kernel-open/nvidia-uvm/uvm_gpu.h` (+7),
`kernel-open/nvidia/nv-reg.h` (+1/-1), `src/nvidia/generated/g_kern_bus_nvoc.c` (+5/-5),
`src/nvidia/src/kernel/gpu/bif/kernel_bif.c` (+3/-3),
`src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c` (+10),
`src/nvidia/src/kernel/mem_mgr/io_vaspace.c` (+11/-10) and
`src/nvidia/src/kernel/rmapi/nv_gpu_ops.c` (+39/-9). It enables BAR1 P2P where NVLink is absent
and falls back to NVLink where present; for PCIe pairs, transfers write directly to the other
GPU's physical address over DMA.

!!! warning "Experimental: GA100 is not on the supported list"
    The branch lists RTX 3090 (pairwise NVLink where available, PCIe BAR1 otherwise), RTX 4090
    and RTX 5090. **GA100 is not on that list and the patch has never been tested on a 170HX.**
    The P2P path touches `kern_bus_gp100.c`, `io_vaspace.c` and `nv_gpu_ops.c`, so a GA100 code
    path may simply not exist.

!!! danger "Take only the P2P commit, not the hugepage commit"
    `52670f7fd6a7` accelerates `cudaHostRegister` by a claimed ~5000x for 1G-hugepage-backed
    buffers and shrinks device page tables for such mappings. Its author states it is enabled
    automatically and that "this path skips some of the per-4K-page bookkeeping the stock driver
    performs, so it may misbehave in edge cases the stock driver handles correctly". Treat it as
    an instability source independent of the unlock patches.

Setup requirements as documented by that branch: `amd_iommu=on iommu=pt` or
`intel_iommu=on iommu=pt` in `GRUB_CMDLINE_LINUX_DEFAULT`, `update-grub`, install the 610.43.03
driver, run `./install.sh`, reboot. IOMMU must be in **passthrough** mode and not translating,
or DMA goes through IOMMU page tables and transfers fail. The README explicitly warns this is
"very dangerous if you run untrusted software or devices". If P2P is slow, ACS on the root ports
forces all GPU-to-GPU traffic through the CPU root complex; disable it in BIOS, with
`pcie_acs_override=downstream,multifunction`, or with an ACS override kernel patch.

See [P2P](p2p.md) for the full treatment.

---

## What would actually advance this

Ranked most tractable first. Only the first two are cheap.

### 1. Do the write nobody has done

Across all 31 archived unlocker attachments and every clean-room artifact, NVLink appears only
as fuse read-outs. There is no probe script, no override attempt, and no recorded write. A
read-write-read probe of `CTRL_OPT_NVLINK` (`0x008209B8`) and `CTRL_OPT_PERLINK` (`0x00820820`)
on an expendable card, followed by re-reading `STATUS_OPT_NVLINK` (`0x00820DB8`), costs one
session.

!!! danger "Write only to an expendable card"
    These are secure fuse-shadow registers. General caution about writing them is the stated
    reason nobody has. Expected result: the write is dropped and status stays `0x00000007`.
    That negative is still worth having on record, because right now the corpus cannot even say
    it was tried.

### 2. Photograph the NVLink component area

High-resolution photographs of a de-shrouded 170HX around designators `R234`, `R236`, `R237`,
`R238`, `R976`, `R1024`, `R1029`, `R1030`, side by side with a genuine A100, plus a continuity
check from the NVLink edge fingers to BGA balls `F1` and `G1` (`R1029`/`R1030` tie to those
balls at the chip edge and could be reached with thin wire). Cheap, decisive, requires one card
and a shroud removal. The maintainers named this as the practical first step on 2026-07-19 and
it has never been done.

### 3. Trace the DevInit read of `0x820684`

`0x820684` is on the DevInit access inventory. Nobody followed the read through the disassembly
to see whether the result is ever written anywhere or merely consumed. If there is a spoofable
consumer between OTP and the status register, this is where it is. Blocked only by effort, and
by the same wall that blocked the PCIe fuse layer.

### 4. Decode the 3-bit disable field against 12 physical links

`FUSE_NVLINK_DIS[2:0]` = `0x7` against `PTOP_SCAL_NUM_NVLINK` = 12, while `STATUS_OPT_NVLINK` is
annotated as a 16-bit field yet also reads `0x00000007`. **Working hypothesis, unconfirmed:**
three link *groups* of four links each (12 = 3 x 4), which would explain the recurring "all
groups" phrasing and the RTX 3080's `0x1` against its `PTOP_SCAL_NUM_NVLINK` of `0x4`. Nothing
in the corpus confirms this. What would settle it: probing an A100 with a known partial NVLink
floorsweep, or finding NVIDIA documentation for the `NV_FUSE_OPT_NVLINK_DISABLE` field width on
GA100.

### 5. Seat a bridge and see what happens

The one empirical test nobody has ever run. Nobody in the corpus has ever had a 170HX and an
A100 NVLink bridge at the same time. One bridge, one shroud modification (or a waterblock that
leaves the area exposed), then `nvidia-smi nvlink` and dmesg. Expected negative given the fuse,
but the corpus currently cannot even confirm the connectors are correctly aligned.

### 6. Interposer fabrication

Pointless before item 5 returns a positive. Deprioritise.

### 7. An actual fuse bypass

Nothing tractable on the table. Progress is additionally blocked by would-be contributors not
having cards: "I wanted to work on it but I cant get any cards. So you have to wait until
someone else figures it out."

---

## How the position moved

| Period | Believed | Replaced by |
|---|---|---|
| 2023-10-25 to 2026-05-07 | NVLink is unsupported because the hardware is missing (teardown: gold fingers present, components unpopulated) | A measured fuse story: the die scales to 12 links, none marked defective, disable is an OTP fuse reading `0x7`. Direct BAR0 readback beats a photographic teardown for what the silicon believes. Note the two are **not** mutually exclusive; the population question remains open |
| 2026-05-31 | The fuse might be a mining-SKU restriction worth attacking as such | The Drive A100 32 GB reads the identical `0x7`/`0x7`. Generic GA100 segmentation |
| 2026-05-31 onward | "NVLink killed, CTRL_OPT override path under investigation" (still printed in the VBIOS comparison table) | Superseded within the same document by `FUSE_EN_SW_OVERRIDE` = `0x0`: "CTRL_OPT fuse override disabled, cannot be changed, inert on 170HX". The reference table is internally inconsistent; the fuse measurement wins |
| 2026-07-07 to 2026-07-10 | A cheap 4-card active NVLink backplane exists for A100 | Pairwise topology only; NVSwitch is SXM-only |
| 2026-07-18 to 2026-07-21 | A100 bridges contain active circuitry (clock generator, EEPROM) | Direct inspection: bare PCB |
| 2026-07-19 | "it has triple (200GB/s?) NVLink, so PCIe is a non-issue" | Self-retracted the same day on being asked "doesn't work though, right?" |
| 2026-07-20 | The blocker is "cracking some kind of security-by-design architecture using encryption named HULK" | Disavowed by the site maintainer and by the page's own author. No replacement explanation was ever published |
| 2026-07-19 to 2026-07-27 | "worth trying, probably just a bridge" | "Might need to consider the state of NVLink, it's a lot harder than I thought to get working". First practical step redefined as redesigning the case for physical access, then photographing the component area. Asked to choose between one month and one year, the answer was that nothing conclusive can be said until the research is done |

---

## Measured values

| Quantity | Value | Conditions | Confidence |
|---|---|---|---|
| `FUSE_NVLINK_DIS` `0x00820684` | `0x00000007` | both 170HX units; Drive A100 32GB (PG199) | high |
| same | `0x00000000` | A100 SXM4 40G, A100 PCIe 40G, A100 PCIe 80G, A10, A5000, A6000, RTX 3090, RTX 3090 Ti | high |
| same | `0x00000001` | RTX 3080, RTX 3080 Ti | high |
| `STATUS_OPT_NVLINK` `0x00820DB8` (RO) | `0x00000007` | both 170HX units; Drive A100 | high |
| `FUSE_NVLINK_DEFECTIVE` `0x0082068C` | `0x00000000` | every card probed; `0` on every card in the 15-card survey that returned a value, the A16 and ES columns excepted | high |
| `FUSE_NVLINK_DIS_CP` `0x00820688` | `0x00000000` | every card probed | high |
| `OPT_SECURE_NVLINK_MASK_WR_SECURE` `0x00820704` | `0x00000005` GA100 / `0x00000085` GA10x | clean architecture split | high |
| `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE` `0x00820BD4` | `0x00000001` | uniform on all 14 probed Ampere cards | high |
| `FUSE_NVLIPT_RST_DIS` `0x00821100` | `0x00000000` | every card probed | high |
| `CTRL_OPT_NVLINK` `0x008209B8` | `0x00000000` | every card probed including 170HX | high |
| `CTRL_OPT_PERLINK` `0x00820820` | `0x00000000` | 170HX | high |
| `PTOP_SCAL_NUM_NVLINK` `0x0002246C` | `0x0000000c` (12) | both 170HX, all A100 SKUs, Drive A100 | high |
| same | `0x00000004` (4) | A10, A5000, A6000, RTX 3080/3080 Ti/3090/3090 Ti | high |
| same | `0x00000000` | A16 only | medium |
| `FUSE_EN_SW_OVERRIDE` `0x00820040` | `0x00000000` 170HX and datacenter GA100 / `0x00000001` consumer and ES | high |
| `FUSE_DIS_SW_OVR` `0x00820084` | `0x00000001` | all cards | high |
| `FUSE_FEAT_OVR_DIS` `0x008203F0` | `0x00000000` | all cards; master override kill **not** blown | high |
| Unsigned FwSec VBIOS tail | `0x43A00`-`0x47700`, 15,616 bytes outside the MAC range | holds a 25-entry `NV_FUSE_CTRL_OPT_*` table at `0x47341`, all zero on 13 GA100 cards | high |
| DevInit read of the NVLink fuse | `0x820684` present in the `0x1482xxxx` access inventory | read only, never written | medium |
| `nvidia-smi nvlink` output | "Device does not have or support Nvlink." | one rented 8-card 64 GiB host, 2026-07-24, GPU names masked; the only capture in the corpus | medium |
| dmesg NVLink line | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` | benign, software core load | high |
| NVLink references in shipping `master` | 0 | whole-tree grep | high |
| NVLink references across all 12 branches | 1 word, `Planned`, in two README tables | no code anywhere | high |
| 4x unlocked 10 GB card pool | 160 GB (4 x 40960 MiB) | shipping `constants.yaml` | high |
| 4x unlocked 8 GB card pool | 256 GB (4 x 65536 MiB) | shipping `constants.yaml` | high |
| A100 bridge street price | roughly 200 EUR each, and a supported A100 pair needs all three | 2026-07-26 market check | medium |
| Estimated NVLink trace frequency | 37 GHz (machine-written EM simulator) versus roughly 60 GHz (second-hand) | conflicting; neither derived from the 50 Gbps lane rate | low |
| 2x RTX 3090 vLLM TP, 27B model | roughly 10 % throughput improvement with NVLink | first-hand, single tester | medium |
| 2x RTX 3090 vLLM, published third-party | 715 versus 483 t/s output; 6,790 versus 4,583 t/s throughput | model, quantisation and batch settings unstated, so not comparable with the above | medium |

!!! note "Cohort caveat"
    In the reference table the A16 column reads the placeholder `BAR0` for every NVLink fuse row.
    Statements of the form "on all cards" above should be read as excluding the A16 for the fuse
    rows. The A16 is the only Ampere part reporting zero NVLink scalability, but its actual
    disable-fuse state was never captured.

---

## See also

- [NVLink hardware](../hardware/nvlink-hardware.md) for the connector and board detail
- [Fuses and OTP](../hardware/fuses-and-otp.md) for the full fuse cohort and methodology
- [Compute throttle](../unlock/compute-throttle.md) for the `FEAT_OVR` route that does work
- [PCIe Gen3 and Gen4](pcie-gen3-gen4.md) for the other fuse-gated frontier
- [P2P](p2p.md), [Status board](status-board.md), [Open questions](open-questions.md)
