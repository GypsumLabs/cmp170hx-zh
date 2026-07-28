# Glossary

**What this page covers.** Every acronym, register nickname, tool name and piece of jargon
used anywhere in this wiki, with an accurate expansion and a short explanation. It also
flags the acronym expansions that the project's own documentation branch invented, which
are wrong and are still being copied into third-party guides.

Two conventions apply throughout. Where NVIDIA has never published an expansion for an
internal block name, this page says so rather than guessing. Where two names exist for the
same register, both are listed on one entry rather than as two entries.

---

## Corrected expansions: do not repeat these

The `docs` branch of `cmpunlocker` (`docs/docs/ARCHITECTURE.md`) contains five acronym
expansions that appear nowhere in the shipping source, in any branch snapshot, or in any
NVIDIA-published header. They are inventions. They have propagated into downstream guides.

!!! warning "Wrong expansions in circulation"

    | Term | Wrong expansion (and where) | Correct |
    |---|---|---|
    | PLM | "Program Logic Modules" (`ARCHITECTURE.md` line 38) | **Privilege Level Mask**, a per-register access-control mask |
    | PMA | "Power Management Array" (line 30) | **Physical Memory Allocator**, an RM memory-manager object |
    | SS0 / SS1 | "Suspension State" registers (line 29) | `FEATURE_OVERRIDE_SM_SPEED_SELECT` (`0x0082381c`) and `..._SM_SPEED_SELECT_1` (`0x00823820`) |
    | LMR | "LM Request" / "LM (Local Memory) Request register" (line 28) | `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`, Local Memory **Range** |
    | PMM | "the PMM (Permute Mask Model)" (line 41) | No such block exists in the code. The term is fabricated. |

    Two related factual errors travel with them: the same file states that SS0 and SS1 are
    both written to `0xffffffff` (the shipping patch writes `0x88888888` and `0x00000008`),
    and that the unlock works by "injecting custom PLM sequences" (it opens four named
    privilege-level-mask registers by re-running Booter Load with an oversized signature
    buffer). See [Compute throttle](../unlock/compute-throttle.md) and
    [Privilege level masks](../unlock/privilege-level-masks.md).

Two further terminology traps, unrelated to that branch:

- **ROP.** In ordinary GPU vocabulary ROP means *Raster Operations Pipeline*. Everywhere in
  this wiki it means **Return-Oriented Programming**, the exploitation technique used to
  drive the SEC2 Booter. See [ROP chain](../unlock/rop-chain.md).
- **XR7.** Several mod write-ups (and an earlier draft of this project's own brief) say the
  PCIe coupling capacitors are "XR7". The dielectric code is **X7R**. See
  [Physical mods](../operations/physical-mods.md).

---

## A

**A100D**
:   Informal name for the NVIDIA DRIVE A100 (`10DE:20BB`, board code PG199), a 32 GB GA100
    part that appears in this corpus only as a comparison device. Booter status `0x54` was
    observed on it and has never been decoded. The `cmpunlocker` branch named `PG199`
    contains no A100D support.

**ACR**
:   Access Control Region. NVIDIA's signed secure-boot framework for GPU microcontrollers,
    responsible for carving the write-protected regions in framebuffer and for the mutex
    that serialises secure engine access. A held ACR mutex is one of the recurring
    explanations offered for a stuck SEC2 mailbox.

**AER**
:   Advanced Error Reporting, the standard PCIe error-logging capability. On a healthy
    170HX `lspci -vvv` shows AER at capability offset `[420]` with all UESta/CESta bits
    clear. AER counters are the correct instrument for judging whether a Gen2 or
    capacitor-modded link is actually clean.

**AON island** (also **always-on island**, **GC6 island**, **PGC6**)
:   The always-powered domain of the GPU that stays alive across engine resets. Registers
    inside it survive [FLR](#f); registers outside it do not. This asymmetry is the single
    most important structural fact about the unlock: `FEAT_OVR_PLM` (`0x00823804`), SS0 and
    SS1 are AON and survive FLR, while CFG1, per-FBPA CFG1, CSTATUS, LMR, the FB-geometry
    PLMs and the AON LMR shadow `0x001180f0` do not. It is why the compute unlock shipped
    before the memory unlock. The mechanism description itself (that `SECURE_SCRATCH_14`
    lives in a PGC6 domain marked RW-4R) is medium confidence.

---

## B

**BAR0**
:   Base Address Register 0. The 16 MB memory-mapped register aperture through which almost
    every register in this wiki is read and written. Tools reach it by mmap-ing
    `/sys/bus/pci/devices/<BDF>/resource0`. A BAR0 that reads all `0xffffffff` means the
    card has fallen off the bus.

**BAR1 / Resizable BAR**
:   BAR1 is the framebuffer aperture exposed to the host. The 170HX advertises a Physical
    Resizable BAR capability at `[bb0]` but the window is limited to 64 MiB, so large-BAR
    tricks are not available.

**BAR2**
:   The MMU-translated aperture used by the driver's own `kbusVerifyBar2` self-test.
    Failures decoding to `NV_ERR_MEMORY_ERROR` (`0x72`) with the journal string
    `"BAR 0/BAR 2 failed."` come from this test hitting a booter-carved WPR2 region, not
    from damaged memory.

**BDF**
:   Bus:Device.Function, the PCI address of the card, for example `0000:0a:00.0`. A
    hardcoded BDF of `0a:00.0` in the userspace helper `tools/retrain.sh` was the root
    cause of the machine-dependent PCIe Gen2 failures.

**Booter / Booter Load**
:   The NVIDIA-signed ACR bootloader ucode that the driver runs on the [SEC2](#s) Falcon to
    authenticate and launch [GSP-RM](#g). The unlock works by handing Booter Load a
    deliberately oversized signature buffer so that a controlled overflow executes a
    [ROP chain](../unlock/rop-chain.md) inside the Booter's own privilege context. Booter
    reports `0xffff` on every run in the shipping flow, success or not, so a register
    readback is the only real verdict.

**BSI scratch**
:   The `0x001180xx` secure-scratch block (for example `SECURE_SCRATCH_14` at `0x001180f8`,
    and the AON LMR shadow at `0x001180f0`). Read from PL0 these return `0xbadf5108`. The
    expansion of "BSI" is not established in this corpus.

---

## C

**Canary**
:   A stack canary: a random per-boot value the Booter stores below its saved return
    address and re-checks before returning, so that a naive buffer overflow is detected.
    The 170HX Booter loads its canary from DMEM `0x6340`. A mismatch panics with SEC2
    mailbox `0x47`. The shipping payload writes a **fake canary** value of `0xc0deca7e` at
    several offsets in the crafted signature buffer.

**CE**
:   Copy Engine. The GPU's DMA engines. Relevant twice: shipping patch 0005 disables the
    VAS-based CE scrubber path on these cards, and an Xid 31 capture names
    `ENGINE CE2 HUBCLIENT_HSCE2` as the faulting client at the top of the 64 GB window.

**CFG0 / CFG1**
:   `NV_PFB_FBPA_CFG0` and `NV_PFB_FBPA_CFG1`, the memory-controller configuration
    registers. CFG1 is the register that defines addressing depth per partition and is the
    primary memory-unlock target. Broadcast CFG1 is `0x009a0204`; the per-FBPA unicast copy
    is `0x00900204 + n*0x4000` for n = 0..23. Stock CFG1 is `0x02449000` on **both** SKUs;
    unlocked it is `0x02779000` (8 GB card) or `0x02669000` (10 GB card). Byte [23:16] is
    the tier: `0x44` stock, `0x66` = 2048 MiB per FBPA, `0x77` = 4096 MiB per FBPA. Live
    per-FBPA CFG0 reads `0x07981800` on every active partition of both cards.

**CMP**
:   Cryptocurrency Mining Processor, NVIDIA's product line for compute-restricted mining
    parts. The CMP 170HX is the GA100-based member of that line, released 1 September 2021.

**CSTATUS_RAMAMOUNT**
:   The per-partition capacity readback register, at `0x0090020C + n*0x4000`. Stock it
    reads `0x200` (512 MiB per FBPA) on both SKUs. A `0xbadf20NN` value here means that
    partition is floorswept, with the low byte encoding the instance.

**CPU-RM**
:   The monolithic driver mode in which the resource manager runs on the host CPU rather
    than on the GSP, selected with `NVreg_EnableGpuFirmware=0`. It clocks the SM at the
    1140 MHz base rather than the 1410 MHz GSP-RM locks in.

**CYA_0**
:   BAR0 `0x0008c2c0`. Bit 2 is `DIS_G2`, the Gen2 disable. The Gen2 branches clear it.

---

## D

**DEVINIT**
:   The device-initialisation script embedded in the VBIOS and executed before any firmware
    runs. Several unresolved limits (ECC, NVLink, possibly PCIe Gen3) are believed to be
    established at DEVINIT time, which is why register-level overrides after boot do not
    reach them.

**DKMS / srcversion**
:   DKMS rebuilds out-of-tree kernel modules per kernel. `srcversion` is the module's
    source hash; comparing `/sys/module/nvidia/srcversion` against the srcversion of
    `/lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko` is the definitive test for
    whether the patched module or the stock one is actually running.

**DIO**
:   The Falcon's secondary data-I/O sideband interface, used by the Booter to reach the
    always-on scratch registers. The letters are not expanded in any public NVIDIA
    document. A poisoned DIO read of `0x1180f8` returns `0xdead5ec1`.

**DLLLA**
:   Data Link Layer Link Active, bit 13 (`0x2000`) of the PCIe Link Status register. The
    GPU always reports LnkSta `0x1042` with DLLLA clear, even on a trained Gen2 x4 link, so
    patch `0008`'s success predicate never fires and the "retrain completed without Gen2 link"
    line is a **false negative on every host**. `0x7042` is the *upstream root port's* LnkSta in
    the same capture, not a different class of host; `0008` reads the GPU's.

**DMEM / IMEM**
:   Falcon data memory and instruction memory. The standalone tooling loaded 63,232 bytes at
    DMEM `0x0900` and 45,824 bytes at IMEM `0x0000`. IMEM is 256-byte block aligned. Once
    the Falcon is in [HS mode](#h), DMEM can be neither read nor written: writes are
    silently dropped and `DMEM_PRIV_LEVEL_MASK` (`0x00840284`) shows `wr_prot == 0`.

**`dmem.bin`**
:   The optional external payload override at
    `/lib/firmware/nvidia/ga100/gsp/dmem.bin`. It is a development hook. Its absence is
    reported as status `0x59` and is the normal, healthy path.

---

## E

**ECC**
:   Error-Correcting Code memory. Fused off on the 170HX (`FUSE_ECC_EN = 0x0`), with no
    known lever and no telemetry: `nvidia-smi -q` reports every ECC field as `N/A`. The
    branch named `ecc` contains no ECC code at all. See [ECC](../frontier/ecc.md).

**EPS 8-pin**
:   The CPU-style 8-pin power connector the card actually uses, rated 300 W and internally
    carrying two separate 12 V rails. It is **not** a PCIe 8-pin (rated 150 W), and the
    12 V and ground pin assignments differ between the two. See [Risks](risks.md).

---

## F

**Falcon**
:   NVIDIA's family of small embedded microcontrollers, commonly expanded as *FAst Logic
    CONtroller*, present as SEC2, GSP's boot core, FECS and others. Falcons have their own
    IMEM/DMEM, a crypto co-processor, and hardware-enforced security modes.

**FBHUB**
:   The framebuffer hub, the crossbar between engine clients and the framebuffer
    partitions. `FBHUB_NUM_ACTIVE_LTCS` at `0x00100800` reads `0x10` (16) on the 8 GB card
    and `0x14` (20) on the 10 GB card.

**FBP / FBPA**
:   FBP is a framebuffer partition, the memory-subsystem slice that contains the L2 slices
    and two FBPAs. FBPA (commonly expanded *frame buffer partition adapter*) is the DRAM
    controller itself. The 8 GB card has 16 active FBPAs across 8 FBPs, a 4096-bit bus; the
    10 GB card has 20 FBPAs across 10 FBPs, a 5120-bit bus. Probe tooling walks 24 FBPA
    slots because the full GA100 has 24.

**FECS**
:   The FrontEnd Context Switch microcontroller in the graphics pipeline.
    `FECS_FEAT_OVERRIDE` (`0x00409664`) and `FECS_FEAT_READOUT_1` (`0x00409668`) mirror the
    PRI feature-override state and read `0xbadf5040` from an unprivileged context.

**Floorsweeping**
:   Permanently disabling defective or surplus units (GPCs, TPCs, FBPAs, NVLinks) via fuses
    at manufacture, to salvage partially defective die. Floorsweep masks are **per die**,
    not per SKU: four 170HX cards read `OPT_GPC_DISABLE` values of `0x85`, `0x45`, `0x13`
    and `0xa8` while all four still enumerated 70 SMs. Never hard-code a floorsweep value.

**FLR**
:   Function Level Reset, the PCIe per-function reset triggered by
    `echo 1 > /sys/bus/pci/devices/<BDF>/reset`. The 170HX advertises `FLReset+` in DevCap,
    which is what makes the unlock harnesses possible. A successful FLR **does** clear WPR2
    and does clear the SEC2 reset-PLM taint (`0x8f` back to `0xff`), but it does not reset
    the [AON island](#a).

**FRTS**
:   The FWSEC command that establishes the firmware-resident region in framebuffer before
    GSP boot, invoked from `kgspPrepareForBootstrap`. No expansion of the acronym is
    established anywhere in this corpus.

**FWSEC / FWSECLIC**
:   The VBIOS-resident firmware-security ucode that runs on a Falcon early in boot and
    performs, among other things, the FRTS carve. Shipping patch 0002 exists largely to
    make FWSEC failures diagnosable, converting fatal asserts into
    `SEC2_DEBUG: FWSEC status=0x%x` style log lines. FWSECLIC is the licence-checking
    companion.

---

## G

**GA100**
:   The Ampere datacentre die used by both the A100 and the CMP 170HX: TSMC 7 nm N7,
    54.2 billion transistors, 826 mm², BGA-2743 package, CUDA compute capability 8.0.
    `PMC_BOOT_0` reads `0x170000a1` on every GA100 probed.

**GPC / TPC / SM**
:   Graphics Processing Cluster, Texture Processing Cluster, Streaming Multiprocessor. The
    170HX enumerates 5 active GPCs, 35 active TPCs and **70 SMs** (4480 CUDA cores) on both
    SKUs, already at its fuse floor. A full GA100 would be 8 GPCs and 64 TPCs.

**GSP**
:   GPU System Processor, the RISC-V microcontroller on Ampere and later that runs most of
    the resource manager on-die.

**GSP-RM**
:   The resource-manager firmware image that runs on the GSP. Its counterpart on the host
    is Kernel-RM / CPU-RM. Boot failures in this wiki are almost always GSP-RM bootstrap
    failures.

---

## H

**HBM2 / HBM2e**
:   High Bandwidth Memory, the stacked DRAM used by GA100. Theoretical peak on the 170HX is
    1555.2 GB/s (1215 MHz DDR across 5120 bits). Measured figures span 1305.86 to
    1600 GB/s depending on tool and access pattern; there is no single canonical number.

**HS mode** (Heavy Secure)
:   The Falcon's highest privilege mode. Code enters HS only after signature verification;
    once in HS the low-secure bootstrap at IMEM `0x00` is wiped, DMEM becomes inaccessible
    from the host, and the Falcon can write registers that are otherwise PL0-blocked. The
    entire memory unlock exists because a specific register write set is only reachable
    from HS.

**HULK**
:   NVIDIA's internal licence/certificate mechanism for enabling debug and vendor features.
    The 170HX carries a pre-built but empty HULK table of contents in its licence region at
    `0xFE000`-`0xFEFFF`. Investigated and closed as a route.

---

## I

**InfoROM**
:   The per-board persistent data region in the VBIOS image, holding serials and
    calibration. On the DRIVE A100 it accounts for 99.5 % of the byte difference between
    two physically distinct GPUs carrying the same firmware.

**IOMMU**
:   The host input/output memory management unit. Passthrough mode (`iommu=pt`) is the
    first thing to check when PCIe stays at Gen1 after installing a Gen2 branch; the
    `Gen2`, `far` and `deced` branch installers set `intel_iommu=on iommu=pt` or the AMD
    equivalent automatically.

---

## L

**LMR**
:   `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE` at `0x00100ce0`: the MMU's view of how much local
    memory exists. Encoding is `size_MiB = MAG[9:4] << SCALE[3:0]`. Stock values are
    `0x00000208` (8 GB card) and `0x00000288` (10 GB card); unlocked values are
    `0x0000020B` (64 GB) and `0x0000028A` (40 GB). Its PLM is `0x001fa7c4`
    (`..._LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`), and there is an AON shadow at `0x001180f0`.
    Do **not** expand LMR as "LM Request".

**LnkCap / LnkCap2 / LnkCtl2 / LnkSta**
:   PCIe Express Capability registers for link capability, supported speeds, target speed
    and trained status. Stock 170HX: `LnkCap 0x00456101`, `LnkCap2 0x00000002`,
    `LnkSta 0x1041`. After the Gen2 branch: `LnkCap 0x00456102`, `LnkCap2 0x00000006`,
    `LnkCtl2 0x0002`, `LnkSta 0x1042`. Advertised capability is not the trained link.

**LTC**
:   Level-two cache slice. The 170HX has 32 MB of L2 against the A100's 40 MB.

**LTSSM**
:   Link Training and Status State Machine, the PCIe state machine that negotiates speed
    and width. On this card the register nicknamed LTSSM in the Gen2 patch is BAR0
    `0x0008872c`, written with `0x00000006`. Fields at play elsewhere in that block include
    LTSSM_DIRECTIVE (0 = NORMAL, 1 = CHANGE_SPEED) and a SPEED field at [19:18].

---

## M

**MIG**
:   Multi-Instance GPU, Ampere's hardware partitioning feature. It can be enabled on an
    unlocked 170HX by setting bit 0 of `0x820840`, after which `nvidia-smi` reports
    `MIG M. Enabled` with 65536 MiB visible.

    !!! warning "Experimental"
        The MIG enable is a community write and is **not** in the shipping unlocker.

**MOK / Secure Boot**
:   Machine Owner Key enrolment, the mechanism that lets a signed out-of-tree module load
    under UEFI Secure Boot. The patched modules are unsigned, so `install.sh` hard-fails if
    `mokutil --sb-state` reports `SecureBoot enabled`.

---

## N

**NVGI / PciAt / FwSec body**
:   The three main regions of a GA100 VBIOS image. NVGI is the earliest, executed by the
    PBUS/XVE init-from-ROM sequencer before any firmware runs; PciAt holds the PCI-visible
    identity; the FwSec body holds the signed firmware. The whole functional difference
    between the 8 GB and 10 GB VBIOS images comes down to 2 bytes in the NVGI bootstrap.

**NVLink**
:   Fused off on the 170HX (`FUSE_NVLINK_DIS`). No firmware or driver change can restore it.
    Whether the board-side NVLink interface ICs are populated is unresolved. See
    [NVLink](../frontier/nvlink.md).

**nvidia-open**
:   NVIDIA's open GPU kernel modules. `cmpunlocker` patches this tree, not the proprietary
    one, and accepts exactly versions `610.43.03` (default) and `610.43.02`.

---

## O

**OTP**
:   One-Time Programmable. The fuses that carry the compute throttle
    (`OPT_SM_SPEED_SELECT`, nine separate fuses), the device ID, the PCIe generation
    disables and the floorsweep masks. The registers exposing them are read-only fuse
    shadows. The master kill fuse at `0x008203f0` reads `0x00000000` (unblown), which is
    why any of this is possible.

---

## P

**P2P**
:   Peer-to-peer GPU-to-GPU transfer. Absent on this card.

**PLM** (Privilege Level Mask)
:   A per-register access-control mask that decides which privilege levels (PL0 host, up to
    PL3 heavy-secure) may read and write the register it guards. Opening a PLM is the whole
    game: the shipping in-driver path opens exactly four, in order, with at most two
    attempts each:

    | Index | Name | Address | Target value |
    |---|---|---|---|
    | 0 | `WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` |
    | 1 | `FBPA` | `0x009a0148` | `0xffffffff` |
    | 2 | `WPR` | `0x001fa7c4` | `0xffffffff` |
    | 3 | `FEAT` | `0x00823804` | `0xffffffff` |

    A `WPR_CFG` readback of `0xfffff0ff` is **correct** and is not a failure. Guides that
    say "all PLMs must show `0xffffffff`" are over-strict.

**PMA**
:   Physical Memory Allocator, the RM object that owns framebuffer pages
    (`pmaRegisterRegion`, `pmaGetFreeMemory`, `PMA_REGION_DESCRIPTOR`). Shipping patch 0003
    performs a "late PMA extension" that grows the high PMA region to cover the newly
    exposed framebuffer, logging `SEC2_DEBUG: late PMA extension status=0x%x`. It has
    nothing to do with power management.

**PMC_BOOT_0**
:   BAR0 `0x00000000`, the chip identity register. Reads `0x170000a1` on every GA100. A
    GA10x control part reads `0xb74000a1`.

**PRAMIN**
:   The privileged BAR0 window that gives the CPU direct access to a movable region of
    video memory. Shipping patch 0004 clamps the PRAMIN base back to a stock 8 GB-derived
    offset (`(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`) whenever `fbAddrSpaceSizeMb > 0x2000`,
    because otherwise the window would be computed from 65536 MB and land outside reachable
    BAR0 space. PRAMIN was also the instrument that proved 80 distinct GiB of physical DRAM
    are present on a 10 GB card.

**PRI**
:   The GPU's internal privileged register bus. A read that is blocked or targets nothing
    returns a `0xbadfXXXX` poison value rather than data: `0xbadf5040` = blocked by a
    privilege level mask, `0xbadf1100` = target does not exist, `0xbadf20NN` = target exists
    but that FBPA is floorswept, `0xbadf5108` = AON secure scratch read from PL0.

**`probe.sh`**
:   The read-only characterisation tool (`tools/mmio-probe`). It mmaps `resource0`
    read-only, dumps roughly 120 to 130 named registers plus 24 per-FBPA reads, and
    **never writes to BAR0**. Constants: `FBPA_BASE = 0x900000`, `FBPA_STRIDE = 0x4000`,
    `CSTATUS_RAM = 0x20C`. It emits `registers.json`, `lspci.txt`, `nvidia-smi.txt`,
    `gpu-summary.csv` and `probe.log`. It is the standard verification instrument: after
    any write, read the register back with `probe.sh` rather than trusting a tool's claim
    of success.

**PTE kind**
:   The "kind" field of a GPU page table entry, describing compression and tiling format.
    Shipping patch 0005 forces `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY` in place of
    `..._COMPRESSIBLE_DISABLE_PLC` for these device IDs.

---

## R

**RFRD**
:   An image-layout descriptor record in the VBIOS SPI ROM, found at absolute `0x2000`.
    One community parser mislabels it as a "power table", which it is not.

**ROP chain**
:   Return-Oriented Programming chain. A payload built entirely from short instruction
    sequences ("gadgets") already present in signed code, chained by overwriting return
    addresses, so that no new code has to be signed. On this card the chain is placed in
    the oversized GSP signature buffer and executed by the SEC2 Booter. The Booter takes its
    hijacked return address from DMEM `0xFF5C`; `0xFF48` is the saved-r3 slot in the `0x4d4`
    pop block and the base of the `0x18`-byte frame grid, so in the superseded standalone
    chains an N-write tail began at `0xFF48 + N*0x18`. See [ROP chain](../unlock/rop-chain.md).

---

## S

**SBR**
:   Secondary Bus Reset, a stronger reset than FLR issued by the upstream bridge. SBR drops
    and re-initialises the always-on power domain, so it clears wedges rooted in AON scratch
    that survive FLR.

**SCP**
:   The Falcon's Secure Co-Processor, the crypto block used for signature verification and
    key handling. `SCP_CTL_P2PRX` bit 3 (SFK_LOADED) is polled during Falcon engine-reset
    recovery.

**SEC2**
:   The GPU's security-engine Falcon, at BAR0 base `0x00840000` (mailbox 0 at `0x00840040`).
    It runs the Booter ucode, and it is the engine that the unlock exploits. Its
    reset-PLM observable (address reported as `0x008403C4`, identity disputed) reads `0xff`
    clean, `0x8f` after `secure_teardown` has run, `0x00cf` in the driver-still-loaded
    partial-fire state.

**Signature buffer**
:   The memory descriptor holding the GSP firmware signature. Stock size is 4096 bytes; the
    shipping patch enlarges it to `0x0000f800` (63,488 bytes) and fills it with the payload,
    dword `0x000004a7`. The earlier, abandoned approach patched `gsp_tu10x.bin` on disk and
    was blocked by the `fwsignature_ga100` section being only `0x1000` bytes.

**SS0 / SS1**
:   `FEATURE_OVERRIDE_SM_SPEED_SELECT` (`0x0082381c`) and `..._SM_SPEED_SELECT_1`
    (`0x00823820`). These control per-instruction-unit **issue rate**, not which SMs are
    active. The unlock writes `0x88888888` and `0x00000008`. A locked card reads, for
    example, `0x53540175` at SS0. They are AON and survive FLR. They are not "Suspension
    State" registers.

**Strap / strap resistor**
:   A 0402 resistor plus an empty adjacent pad, where moving the part between positions
    flips a hardware-sampled configuration bit. The 170HX carries five strap pairs
    (ten pads, designators R986 to R1005) plus a DEVID_SEL pair elsewhere. The primary PCIe
    device ID is fused into the die and is **not** strap-settable
    (`FUSE_DEVID_SW_OVR_DIS 0x00820584` = 1 on every card probed).

---

## V

**VBIOS**
:   The card's firmware ROM. Four 170HX images exist publicly; the TechPowerUp "16 GB" and
    "0 GB" size labels on two of them are wrong and neither unlocks memory. VBIOS version
    makes no difference to whether the unlock works. See [VBIOS](../hardware/vbios.md).

**VSEC**
:   Vendor-Specific Extended Capability, the PCIe config-space extended capability block.
    Two registers matter for Gen2: `VSEC_DEVICE` at `0x0008860c` (bit 0 set through the
    Booter payload) and `VSEC_HIERARCHY` at `0x00088610` (a plain host BAR0 write after the
    Booter phase).

---

## W

**WPR / WPR1 / WPR2**
:   Write Protected Region. Framebuffer ranges the MMU refuses to let unprivileged agents
    write, used to hold ACR and GSP firmware state. WPR2 lo/hi live at `0x001fa824` and
    `0x001fa828`. Disabled they read `0x1FFFFE00 / 0x00000000`; after a Booter run they read
    `0x01F77000 / 0x01FFEE00`. The shipping patch saves both once and rewrites them before
    **every** Booter Load attempt, rather than clearing them. "WPR2 already up" was the
    dominant early failure and is now downgraded to a warning that continues.

**WprMeta**
:   The metadata structure describing the WPR layout, including `fbSize` and
    `sizeOfSignature`, that the driver populates and the Booter validates.

---

## X

**Xid**
:   NVIDIA's driver-emitted error identifier. The ones that matter here:

    | Xid | Meaning in this corpus |
    |---|---|
    | 31 | MMU fault, `FAULT_INFO_TYPE_REGION_VIOLATION`. Allocation past the usable top of the unlocked window. Card unusable in CUDA until reboot. At 80 GB, kernels touching more than roughly 40 GB cause fatal GPU loss independent of power limit; reported Xid codes include Xid 31 (described as harmless) and Xid 154 after CUDA memory tests, and the dominant reported symptom is hangs. Xid 31 alone was suggested by a bystander and was not corroborated as *the* signature by the operator with the failing card. |
    | 45 | Provoked by SIGKILLing a live CUDA verification kernel; forces a reset cycle. |
    | 119 | GSP RPC timeout. Two distinct variants: 60 s waiting on function 4097 `GSP_INIT_DONE` (boot never completed) and 6 s on function 103 `GSP_RM_ALLOC` (post-boot hang, repeats per `nvidia-smi`). |
    | 154 | Dominant failure after CUDA memory tests on the over-provisioned 80 GB configuration; limits the card to one CUDA context per fire. |

**XP3G**
:   The PCIe link-layer override block at `0x0008e1xx`, including `XP3G_OVR0` `0x0008e110`,
    `XP3G_VAL0` `0x0008e120`, `XP3G_OVR3` `0x0008e11c`, `XP3G_VAL3` `0x0008e12c` and the PLM
    quartet `0x0008e1b0` / `0x0008e1b4` / `0x0008e1b8` / `0x0008e1bc`. The Gen2 patch pushes a
    23-entry `xp3gTable` through the Booter payload primitive (18 PLM opens plus 5 value
    writes). NVIDIA has not published an expansion of the name.

**XVE**
:   NVIDIA's internal name for the PCI Express endpoint and config-space block, base
    `0x00088xxx`. The Gen2-family branches add three XVE capability PLMs to the table:
    `0x00088ff4` (XVE), `0x00088ab4` (XVE_B), `0x00088ff8` (XVE_C). The letters are not
    expanded in any public NVIDIA document.

---

## Numbers, codes and file paths

**`0x008200FC`**
:   One register, two names. The branch source writes
    `{0x008200fcU, 0xffffffffU, "OPT_PLM"}`, so `OPT_PLM` is the code name; `FUSE_SS_PLM` is
    the clean-room tooling name for the same register. It is **not** written by shipping
    master. Whether it is writable, and what it reads on a cold card, is open.

**`0xbadfXXXX`**
:   See [PRI](#p). These are never stored data.

**`0xc0deca7e`**
:   The fake canary sentinel placed in the crafted signature buffer.

**Branch names**
:   There are **12** unreleased branch snapshots (`80`, `Gen2`, `PG199`,
    `clanker_driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`, `far`, `housekeeping`,
    `memory`, `multiple-cards`) and 13 trees counting shipping `master`. Documents that say
    "thirteen unreleased branches" are off by one.

**`/lib/modules/$(uname -r)/updates/cmpunlocker/`**
:   Where the install writes the patched modules plus three marker files:
    `driver_version`, `card_profile` (`8gb` or `10gb`) and `unlock_geometry`. Multi-card
    branches add `gpu_inventory`.

**`SEC2_DEBUG`**
:   The log tag for the unlock path. `sudo dmesg | grep SEC2_DEBUG` is the single primary
    diagnostic. Two sibling tags exist: `SEC2_DEBUG_HEAP` and `SEC2_DEBUG_LATE_PMA`. All are
    emitted at `LEVEL_ERROR`, so no extra debug flags are needed. Total absence of
    SEC2_DEBUG lines means the patched module never ran.

---

## Tools referenced in this wiki

| Tool | What it is used for here |
|---|---|
| `clpeak` | OpenCL bandwidth and compute microbenchmark; source of the Gen1 x4 ~0.85 GB/s figure |
| `cuda_memtest` | GPU memory verification; the 80 GB profile passes once after reboot then fails |
| `gpu-burn` | Sustained compute stress with an error counter; a stable 40 GB card passes 5 minutes cleanly |
| `mixbench` | Mixed-precision throughput; its `1769.47 GB/sec` figure is theoretical, not measured |
| `nvtop` | Live per-GPU telemetry including PCIe generation and width |
| `ocl_pcie_bw` | OpenCL host-to-device bandwidth; source of the 6.63 to 6.67 GB/s Gen2 x16 figure |
| `pcielink.sh` | Community data-collection script for link-training reports; prints identity plus the full LnkCap/LnkSta/AER set for GPU and bridge |
| `probe.sh` | Read-only register survey; see [PRI](#p) above |
| `verify.sh` | Per-BDF unlock verification on the multi-card branches |
| `CH341A` | SPI flash programmer. GPU EEPROMs are 1.8 V, so a 1.8 V adapter is required |

---

## See also

- [How to read this wiki](how-to-read-this-wiki.md) for the confidence conventions.
- [Register reference](../unlock/register-reference.md) for every address in one table.
- [Identify your card](identify-your-card.md) to work out which SKU you hold.
