# Memory geometry: how the capacity unlock works

**What this page covers.** The exact mechanism by which a CMP 170HX is made to report and use more
framebuffer than it ships with: the two registers that carry the geometry, the per-SKU values, why
those two registers must agree, the driver-side plumbing that turns reported memory into allocatable
memory, and the persistence rules. For the physical substrate (HBM stacks, partitions, floorsweep,
bandwidth) see [The memory subsystem](../hardware/memory-subsystem.md).

The headline, stated once here and repeated throughout because mixing it up is the single most
common error in this subject:

> **An 8 GB CMP 170HX (`10de:20c2`) unlocks to 64 GB. A 10 GB CMP 170HX (`10de:2082`) unlocks to
> 40 GB.** Never the other way round. The 80 GB configuration for 10 GB cards was tried and found
> unusable above roughly 40 GB.

The entire memory-geometry mechanism in the shipping unlocker is **two host register writes**:

| Register | Address | Role |
|---|---|---|
| `NV_PFB_FBPA_CFG1`, broadcast | `0x009a0204` | per-partition addressing depth (the capacity *tier*) |
| `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE` (LMR) | `0x00100ce0` | the MMU's declaration of total framebuffer size |

Everything else in the unlock exists to make those two writes land, to make GSP-RM and CPU-RM
believe them, and to make the resulting space allocatable.

---

## The per-SKU value table

This is the authoritative table. Every number in it agrees across the shipping
`common/constants.yaml`, `driver/build.sh`, `install.sh` and the hard-coded branch inside
`driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`.

| Quantity | 8 GB card `10de:20c2` | 10 GB card `10de:2082` |
|---|---|---|
| Stock capacity | 8192 MiB | 10240 MiB |
| **Unlocked capacity** | **65536 MiB (64 GB)** | **40960 MiB (40 GB)** |
| Stock CFG1 `0x009a0204` | `0x02449000` | `0x02449000` (identical) |
| **Unlocked CFG1** | **`0x02779000`** | **`0x02669000`** |
| Stock LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| **Unlocked LMR** | **`0x0000020B`** | **`0x0000028A`** |
| `targetFbBytes` / GSP `fb_length` | `0x0000001000000000` (64 GiB) | `0x0000000A00000000` (40 GiB) |
| `unlocked_mib` in metadata | 65536 | 40960 |
| Stock per-FBPA `CSTATUS_RAMAMOUNT` | `0x200` (512 MiB) | `0x200` (512 MiB) |
| Unlocked per-FBPA `CSTATUS_RAMAMOUNT` | `0x1000` (4096 MiB) | `0x800` (2048 MiB) |
| Live FBPAs | 16 | 20 |
| CFG1 tier byte `[23:16]` | `0x77` | `0x66` |
| `install.sh` banner | `Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)` | `Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)` |

A third device ID, `10de:20b0`, is detected by the installer's `lspci` scan but is **not** unlocked:
the in-driver gate accepts only `0x20C2` and `0x2082`, so a `20b0` card builds and installs a driver
whose unlock never fires. The master `README.md` still says the unlock is `0x20C2`-gated; that
phrasing is stale, and the code gates on both IDs in all six patches.

Geometry is selected **at runtime by PCI device ID**, not at build time. Both profiles are compiled
into the same module:

```c
NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;

if (devId == 0x20C2) { cfg1Value = 0x02779000U; lmrValue = 0x0000020BU; }  /* 8 GB  -> 64 GB */
else                 { cfg1Value = 0x02669000U; lmrValue = 0x0000028AU; }  /* 10 GB -> 40 GB */
```

---

## What CFG1 encodes

CFG1 encodes **addressing depth per memory partition**. It does not encode capacity, and it does not
encode stack count.

The tier byte sits at bits `[23:16]`. Each nibble is a row-address count offset by 8:

| Tier byte | Row bits | Capacity per FBPA | Full CFG1 word |
|---|---|---|---|
| `0x44` | 12 | 512 MiB | `0x02449000` (stock, both SKUs) |
| `0x66` | 14 | 2048 MiB | `0x02669000` (10 GB card to 40 GB) |
| `0x77` | 15 | 4096 MiB | `0x02779000` (8 GB card to 64 GB) |

Total capacity is therefore `tier × live FBPA count`, and the FBPA count is fuse-determined and
untouched by CFG1. **The same word `0x02779000` yields 64 GB on the 16-partition 8 GB CMP and 80 GB
on a 20-partition A100.** It is a per-partition strap, not a per-card one.

The probe-catalogue field decode for the register is `SUBP[1:0]`, `COL[15:12]`, `ROWA[19:16]`,
`BANK[25:24]`. Across every HBM part observed, `COL` stays `0x9` and `BANK` stays `0b10`; only the
row-address nibbles move. GDDR6 parts read different `COL` values (`0x4266b000` on A10/A5000/RTX
3090/3090 Ti, `0x4277b000` on A6000, `0x4266a000` on RTX 3080/3080 Ti), which is why the `0x9`
nibble is a memory-type constant and not a "5 stacks" flag.

!!! note "Superseded"
    One widely circulated analysis read CFG1 as `0x02 [strap] [feature] 0x00` with bits `[15:8]` as
    a stack-count field (`0x00` = 4 stacks, `0x90` = 5 stacks). The shipping code refutes it: it
    writes `0x02779000` (feature byte `0x90`) to the 4096-bit, 4-stack-equivalent 8 GB card and
    obtains 64 GB, and GDDR6 parts show `0xa`/`0xb` in that nibble, which a stack count cannot
    explain. The derived 40 GB figure from that table happened to be right for the wrong reason.

**These are not magic constants.** `0x02779000` is literally the stock CFG1 value measured on real
A100 PCIe 80 GB silicon (PCI `0x20b5`), together with LMR `0x0000028b`. `0x02669000` is likewise the
stock value on A100 PCIe 40 GB and A100 SXM4 40 GB. The unlock restores genuine A100 geometry.
A reference GA100 reads `0x22779000`, differing only in bit 29. That bit **halves per-FBPA
addressing depth**: on 2026-07-27 a 170HX driven to `CFG1 = 0x22779000` held per-FBPA
`CSTATUS_RAMAMOUNT` at `0x800` (2048 MiB) rather than `0x1000`, logged as
`tier=0x77 HALVED -> 2048 MiB/FBPA x20 = 40960 MiB (40 GB)`, against the unlocked 8 GB card whose
live FBPAs each read `0x00001000` after the tier `0x77` unlock. Whether bit 29 does anything else
was not established.

The same word also lives in the VBIOS. From at least Pascal, memory type/size/vendor is chosen by
one of 16 memory-configuration straps selected by hardware pins STRAP0 to STRAP2. The CFG1 strap
table is 16 entries of 4 bytes, laid out `00 90 TT 02` little-endian, that is `u32 = 0x02TT9000`,
which is bit-for-bit the register value. Only strap 4 is populated on shipping CMP hardware. See
[VBIOS](../hardware/vbios.md).

---

## What LMR encodes

The MMU Local Memory Range register at `0x00100ce0` declares total framebuffer size as a
magnitude/scale pair:

```text
size_MiB = LOWER_MAG[9:4] << LOWER_SCALE[3:0]
```

equivalently `bytes = MAG << (SCALE + 20)`. `MAG` is constant per SKU and equals **twice the active
FBPA count**; `SCALE` is what the unlock changes.

| LMR value | MAG | SCALE | Decodes to | Status |
|---|---|---|---|---|
| `0x00000208` | 32 | 8 | 8192 MiB | stock, 8 GB card |
| `0x00000288` | 40 | 8 | 10240 MiB | stock, 10 GB card |
| `0x0000020B` | 32 | 11 | 65536 MiB | **shipping, 8 GB card to 64 GB** |
| `0x0000028A` | 40 | 10 | 40960 MiB | **shipping, 10 GB card to 40 GB** |
| `0x0000028B` | 40 | 11 | 81920 MiB | correct for 80 GB; fired experimentally from a script, never shipped |
| `0x0000028C` | 40 | 12 | 163840 MiB | a joke value that a PRAMIN run genuinely accepted |

The unlock adds **+3 to the scale nibble on the 8 GB card** and **+2 on the 10 GB card**. In CFG1
terms the delta is `+0x00330000` (bits 16, 17, 20, 21) for the 8 GB card and `+0x00220000`
(bits 17, 21) for the 10 GB card.

!!! note "Superseded"
    `0x0000040A` and `0x0000050A` circulated as 64 GB and 80 GB encodings and both are **refuted**.
    Under a 6-bit magnitude field, `(0x40A >> 4) & 0x3F = 0` and `(0x50A >> 4) & 0x3F = 0x10 = 16`,
    so `0x40A` programs a geometry of zero with a stray bit 10 set, and `0x50A` decodes to 16 GB.
    `payload_v3.py` used `0x40A` with the comment "LMR (0x40A, not 0x20B)"; it lost. A 2026-07-11
    hardware run targeting `0x40A` on a 10 GB card moved neither register
    (`LMR=0x288[want 0x40A] CFG1=0x2449000[want 0x2779000]`). The shipping value for 64 GB is
    `0x0000020B`.

!!! question "Open problem: is `LOWER_MAG` 6 bits at [9:4] or 7 bits at [10:4]?"
    Everything in real use works under 6 bits. The width has never been read from `dev_fb.h`. This
    is a header lookup, not an experiment, and it is the last thing standing between the
    `0x28B`-versus-`0x50A` argument and a clean answer.

---

## Why CFG1 and LMR must match

They are two independent declarations of the same fact, and the GPU checks them against each other.

A controlled three-way comparison on hardware:

| Configuration | Result |
|---|---|
| No memory writes at all | CPU-RM fails at `0x24` (`kbusVerifyBar2`) |
| 40 GB CFG1 strap with stock 10 GB LMR (`0x288`) | still `0x24` |
| 40 GB CFG1 **plus matched LMR** (`0x28A`) | reaches `0x25` (StateLoad) |

There is no configuration that reaches StateLoad without the LMR. **CFG1 alone is insufficient; the
LMR is a hard prerequisite.**

**GSP-RM treats the LMR as the master during its own boot.** With CFG1 set to the 40 GB tier but LMR
left at `0x288`, GSP-RM reverted `CSTATUS` from `0x800` back to `0x200` during `kgspBootstrap`. With
LMR set coherently to `0x28A`, instrumented dumps read
`CSTATUS=0x800 LMR=0x28a CFG1=0x2669000 WprMeta.fbSize=0xa00000000` at all four checkpoints
including post-Bootstrap. FWSEC itself does not revert the geometry.

This is exactly the failure the unmerged `80` branch walked into: see
[The 80 GB attempt](#the-80-gb-attempt-and-why-it-is-incoherent) below.

---

## The shipping write sequence

The unlock is gated by `_kgspSec2PostblTimingEnabled()`, which reads
`NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;` and returns true for `0x20C2` **or** `0x2082`.

### Step 1: open four PLMs

Host (PL0) writes to CFG1 are **silently dropped** until the FB-geometry privilege-level masks are
open. An early pipeline logged `Write failed - wrote 0x2779000, read 0x2449000` three times with no
error signalled at all. The reason is fuse `OPT_SECURE_FBPA_MEM_WR_SECURE` (`0x00820618`) = `1`,
which restricts FBPA memory-config writes to privileged code.

The shipping `plmTable[]` has **exactly four entries**, opened in this order, each retried up to
twice through a Booter Load pass, with the saved WPR2 LO/HI pair rewritten before every attempt and
once more after the loop:

| Order | Address | Written value | Label |
|---|---|---|---|
| 0 | `0x001fa7cc` | **`0xfffff0ff`** | `WPR_CFG` |
| 1 | `0x009a0148` | `0xffffffff` | `FBPA` |
| 2 | `0x001fa7c4` | `0xffffffff` | `WPR` |
| 3 | `0x00823804` | `0xffffffff` | `FEAT` |

Note the WPR_CFG target is `0xfffff0ff`, **not** `0xffffffff`. README and `DEBUGGING.md` text saying
"all PLMs must show `0xffffffff`" is loose wording. Stock values are `0xffffff8f` for FEAT and FBPA
and `0x0004cb8f` for the WPR pair.

If a PLM fails both attempts the driver logs `SEC2_DEBUG: FAILED to open <name> after 2 attempts`
and **continues anyway** to the geometry writes. WPR2 LO/HI (`0x001fa824` / `0x001fa828`) are saved
and restored only; they are never set to a new value by the shipping driver. See
[Privilege level masks](privilege-level-masks.md) and [The ROP chain](rop-chain.md).

!!! note "Naming is disputed, addresses are not"
    Register-catalogue work names `0x001fa7c4` `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`,
    that is the LMR PLM, while the shipping `plmTable` labels it "WPR" and `0x001fa7cc` "WPR_CFG".
    The addresses and values are not in dispute and the functional outcome is identical. Rely on the
    addresses. `0x001fa7c0` is **not** the LMR PLM and appears nowhere in the shipping tree; placing
    it first in a multiwrite chain faults the ROP chain.

### Step 2: four host register writes

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);  /* SS0: compute throttle off      */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);  /* SS1: compute throttle off      */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);    /* FBPA CFG1, BROADCAST alias     */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);     /* MMU local memory range         */
```

CFG1 is written **before** LMR. All four are then read back and printed:

```text
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
```

The first two writes are the [compute unlock](compute-throttle.md) and are issued unconditionally
for both SKUs. They are included here only because they share the same window.

### Step 3: broadcast only

**The shipping driver writes CFG1 only to the broadcast alias `0x009a0204`.** It does not loop over
the 24 per-FBPA instances at `0x00900204 + n*0x4000`, and a repository-wide grep for those addresses
across every patch, script and YAML file returns zero hits. Anyone reading dmesg from the shipping
installer will therefore see exactly one CFG1 value, not twenty.

This is context-dependent and the distinction matters:

| Context | What is sufficient |
|---|---|
| In the driver / devinit path (the shipping tool) | one broadcast write to `0x009a0204` |
| Driverless runtime with no devinit (the clean-room refire chain) | the broadcast alone does not move CSTATUS; **all 24 per-FBPA CFG1 instances must be written by hand** at `0x00900204 + n*0x4000`, verified by reading `CSTATUS_RAMAMOUNT` at `0x0090020C + n*0x4000` |

The five-PLM `FB_GEO_PLMS = [0x00100b10, 0x009a0148, 0x009a014c, 0x009a0008, 0x009a000c]` list and
the 24-instance loop belong to the **separate, unreleased driverless toolchain**, not to the
shipping installer. Keep the two paths distinct when reading any write-up. See
[Tool lineage](../history/tool-lineage.md).

!!! question "Open problem: is the broadcast a PRI priv-ring hardware mechanism?"
    A researcher who originally believed the broadcast was a software step in GSP-RM struck that
    belief through and proposed the priv ring instead, but it was never directly instrumented. It
    matters because it decides whether one write is guaranteed sufficient in every context or only
    when devinit follows. The experiment: with the FB-geo PLMs open and no devinit, write only the
    broadcast, then read all 24 per-FBPA CFG1 mirrors to see whether the value propagates even
    though CSTATUS does not move.

### Step 4: rebuild the stock signature and boot GSP

The postbl path replaces the GSP signature buffer with a ROP payload of
`SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800` bytes (63,488), filled with dword `0x000004a7` and
overwritten at fixed offsets (`0x1100`, `0x5b40`, and `0xf754` to `0xf7f8`, ending `0x00007f2f`).
If `/lib/firmware/nvidia/ga100/gsp/dmem.bin` exists it is loaded instead; if it is absent the
built-in fallback payload is used with a single default write of `0x009a0148 = 0xffffffff`, and the
absence is reported as `0x59`, which is benign.

Before GSP boots, `kgspSec2PostblTimingRebuildStockSignature()` frees the oversized payload memdesc,
allocates `NV_ALIGN_UP(stockSignatureSize, 256)`, copies the saved stock signature back, and updates
`pWprMeta->sysmemAddrOfSignature` and `sizeOfSignature`. If the rebuild fails, GSP boot is aborted.
This is the step that lets an otherwise-normal GSP-RM boot on top of the changed geometry.

`kgspPopulateWprMeta_HAL` is then re-run so the WPR metadata matches the new framebuffer:

| Field | Before (8 GB card) | After (64 GB) |
|---|---|---|
| `fbSize` | `0x0000000200000000` | `0x0000001000000000` |
| `wprEnd` | `0x00000001fff00000` | `0x0000000ffff00000` |
| `wprStart` | (n/a) | `0x0000000ff7400000` |
| `heapOffset` | (n/a) | `0x0000000ff7500000` |
| `heapSize` | `0x0000000006900000` | `0x0000000006e00000` |
| Saved WPR2 | `lo=0x1ffffe00 hi=0x00000000` | unchanged |

On a 10 GB card the corresponding `fbSize` transition is `0x0000000280000000` to
`0x0000000a00000000`.

Patch `0001` also **unconditionally** downgrades the upstream "unexpected WPR2 already up, cannot
proceed with booting GSP" hard failure (`return NV_ERR_INVALID_STATE`) to a warning
(`WPR2 already up before GSP boot; continuing for recovery`), so a card left dirty can still boot.

!!! danger "That WPR2 downgrade is not gated on the CMP device IDs"
    It applies to **every GPU the patched module drives**. On a mixed system the patched modules
    will silently continue past a genuinely bad WPR2 state on unrelated hardware. Do not install
    these modules on a machine whose other GPUs you care about.

---

## Making the space real, not just reported

Register geometry alone gets you a number in `nvidia-smi`. Four more patches turn it into memory
CUDA can allocate.

### GSP static info and the FB region (patch `0001`)

After `kgspInitRm`, for devId `0x20C2` or `0x2082`:

- `pGSCI->fb_length` is overwritten with `targetFbBytes`
  (`0x0000001000000000` on the 8 GB card, `0x0000000A00000000` on the 10 GB card).
- If `0 < numRegions <= NV2080_CTRL_CMD_FB_GET_FB_REGION_INFO_MAX_ENTRIES`, the driver takes
  `fbRegion[numRegions-1]` and, when `limit < targetFbBytes - 1`, sets
  `limit = targetFbBytes - 1`, `reserved = limit - base + 1`, `supportCompressed = NV_TRUE`,
  `supportISO = NV_TRUE`, `performance = 20`.

Logged as `SEC2_DEBUG: static-info BEFORE/AFTER: fb_length=... numRegions=...`. **Without this the
driver would not report the widened size**, because with GSP firmware enabled CPU-RM does not size
the framebuffer itself: it receives `fbSize` from GSP-RM over RPC in `GspStaticConfigInfo`.

Observed on a 64 GB boot: `static-info BEFORE: fb_length=0x1000000000 numRegions=5`, last
`region[4] base=0xff7300000 limit=0xfffffffff reserved=0x8d00000`.

### Late PMA extension (patch `0003`)

`memmgrSec2DebugLateExtendHighPmaRegion()` is called from `osinit.c` after GPU init, gated on the two
device IDs. It is the step that turns reported memory into **allocatable** memory. It scans
`Ram.fbRegion[]` for the highest-limit region satisfying
`bRsvdRegion && !bInternalHeap && limit >= stockFbBytes && base <= limit`, builds a
`PMA_REGION_DESCRIPTOR` with `base = NV_MAX(candidate->base, 0x200000000)` and
`bSupportCompressed = NV_TRUE`, and calls
`pmaRegisterRegion(pPma, numPmaRegions, NV_FALSE, &pmaRegion, 0, NULL)`.

On success it either splits or unreserves the candidate:

- If `candidate->base < 0x200000000`, append a new public FB region (`base = 0x200000000`,
  `limit` = old limit, `rsvdSize = 0`, `bRsvdRegion = NV_FALSE`, `bInternalHeap = NV_FALSE`,
  `bSupportCompressed = NV_FALSE`), truncate the original to `limit = 0x1ffffffff`, clamp its
  `rsvdSize`, increment `numFBRegions`, then call `memmgrRegenerateFbRegionPriority()`.
- Otherwise clear `bRsvdRegion`, `rsvdSize`, `bInternalHeap` and `bSupportCompressed` in place.

Early-outs: `NV_OK` if PMA is uninitialised (`SEC2_DEBUG_LATE_PMA: no PMA, skipped`), if the range
is empty, or if `pmaIsPmaManaged()` already covers it; `NV_ERR_INSUFFICIENT_RESOURCES` if a split is
needed but `numFBRegions >= MAX_FB_REGIONS`.

Measured effect on a 64 GB card:

```text
SEC2_DEBUG_LATE_PMA: registering candidate=6 base=0xff7300000 limit=0xfffffffff ... pma_region_id=1
SEC2_DEBUG_LATE_PMA: status=0x0 pma_total 0xfd8f50000->0xfe1c50000 pma_free 0xfd8f50000->0xfe1c50000
```

That delta is `0x8d00000` bytes = 147,849,216 bytes = **141.0 MiB** exactly. Both "about +136 MiB"
and "about 141 MiB" circulate; 141.0 MiB is this delta, and the ~136 MiB figure elsewhere refers to
the WPR carve, which is a different thing.

Full FB region layout on an unlocked 64 GB card, seven regions:

| Region | Base | Limit | Flags |
|---|---|---|---|
| 0 | `0x0` | `0x1007ffff` | rsvd=1, rsvdSize `0x10080000` |
| 1 | `0x10080000` | `0xfe8fcffff` | rsvd=0 |
| 2 | `0xfe8fd0000` | `0xff42dffff` | rsvd=0, rsvdSize `0xb310000`, intHeap=1 |
| 3 | `0xff42e0000` | `0xff430ffff` | rsvd=1, intHeap=1 |
| 4 | `0xff4310000` | `0xff720ffff` | rsvd=1, rsvdSize `0x2f00000` |
| 5 | `0xff7210000` | `0xff72fffff` | rsvd=1 |
| 6 | `0xff7300000` | `0xfffffffff` | rsvd=1, rsvdSize `0x8d00000`, **the extension candidate** |

Heap summary on the same boot:

```text
SEC2_DEBUG_HEAP: fbAddrSpace=65536MB mapRam=0MB fbTotal=65536MB fbUsable=0xfe4260000
                 heapTotal=0x1000000000 regionBytes=0x1000000000 publicBytes=0xfd8f50000 numRegions=7
```

### The BAR0/PRAMIN clamp (patch `0004`)

In `kern_bus_gm107.c`, for devId `0x20C2` or `0x2082` with `Ram.fbAddrSpaceSizeMb > 0x2000`
(8192 MB), `offsetBar0` is forced to:

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

that is, the PRAMIN window is pinned back to the **stock 8 GiB** address space instead of tracking
the enlarged one. This matters for anyone using PRAMIN to probe high physical memory: after the
unlock, PRAMIN does not reach the top of the new space by default. The patch file is byte-identical
(md5 `8e6a2b1c03df6d3388243db82ebbb9b4`) across master and all four driver-series port directories.

### CE scrub workarounds (patch `0005`, plus one hunk in `0003`)

Compression is deliberately disabled on unlocked cards in three places, all gated on the two device
IDs:

1. In `mem_mgr_tu102.c`, the scrubber's PTE-kind selector returns `NV_MMU_PTE_KIND_GENERIC_MEMORY`
   instead of the default `NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`.
2. In `mem_scrub.c`, the CeUtils guard becomes
   `if (memmgrUseVasForCeMemoryOps(pMemoryManager) && ((pGpu->idInfo.PCIDeviceID >> 16) != 0x20C2 && (pGpu->idInfo.PCIDeviceID >> 16) != 0x2082))`,
   keeping CeUtils in physical rather than virtual mode.
3. In `mem_mgr.c` (third hunk of patch `0003`), the same device-ID exclusion is added to the
   `ceUtilsParams.flags |= DRF_DEF(0050_CEUTILS, _FLAGS, _VIRTUAL_MODE, _TRUE)` path guarded by
   `bUseRawModeComptaglineAllocation` / `bOneToOneComptagLineAllocation`.

Without these the copy-engine scrubber trips over compressed allocations in the widened space.

### Persistent software state (patch `0006`)

`NV_FLAG_PERSISTENT_SW_STATE` is set in `nv.c` for both device IDs, in two separate `if`/`else if`
arms with identical bodies.

### A real asymmetry in the shipping code

`stockFbBytes = 0x200000000ULL /* 8GB */` is hard-coded in both patch `0001` and patch `0003` and is
used for **both** device IDs, including the 10 GB card whose true stock size is `0x280000000`. The
PRAMIN clamp likewise compares against `0x2000` MB. In patch `0001` the variable is declared and
never referenced (dead code); in patch `0003` it is the split point between the stock region and the
late-PMA extension region.

!!! question "Open problem: does the 8 GiB `stockFbBytes` matter on a 10 GB card?"
    The unlock demonstrably works on `0x2082`, so any effect is subtle. The check is a pure
    log-reading exercise: read the `SEC2_DEBUG_LATE_PMA: region[...]` and `SEC2_DEBUG_HEAP:` dmesg
    lines on a 40 GB-unlocked 10 GB card and confirm `publicBytes` accounts for the full 40 GiB
    rather than losing the 8 to 10 GiB slice. Nobody has posted it.

---

## Timing: the whole thing takes about one second

From a complete dmesg capture on an 8 GB card going to 64 GB:

```text
11.13 s  stock signature saved
11.32 s  PLM[0] WPR_CFG
11.50 s  PLM[1] FBPA
11.68 s  PLM[2] WPR
11.86 s  PLM[3] FEAT              (about 180 ms per Booter pass)
11.86 s  POST-WRITE and WPR-meta update
12.07 s  normal BooterLoad status=0x0
         POST-BooterLoad verify PLM=0xffffffff SS0=0x88888888 SS1=0x00000008
                                CFG1=0x02779000 LMR=0x0000020b
12.64 s  heap creation
12.72 s  late PMA extension status=0x0
```

Note that `BooterLoad` reports `status=0xffff` on every re-fire run whether it succeeded or not;
readback is the only verdict.

---

## Persistence: geometry versus compute

This is the most important operational property of the memory unlock, and it is the reason the
compute unlock shipped before the memory unlock.

| Event | Compute (SS0 `0x0082381c`, SS1 `0x00823820`, FEAT PLM `0x00823804`) | Memory geometry (CFG1, per-FBPA CFG1, CSTATUS, LMR, FB-geo PLMs, AON LMR shadow `0x001180f0`) |
|---|---|---|
| Driver unload and reload, no SBR | survives | **survives** |
| Function-level reset (FLR) | **survives** (always-on island) | **reverts** |
| Reboot / power cycle | reverts | reverts |
| DEVINIT | reverts | reverts |

Measured across an FLR on a 10 GB card: CFG1 `0x9A0204` written `0x2779000` reverted to `0x2449000`;
LMR `0x100CE0` written `0x20b` reverted to `0x288`; while SS0 `0x82381C` = `0x88888888` and SS1
`0x823820` = `0x8` both survived. The SEC2 reset-PLM taint is also cleared by FLR (`0x8f` to `0xff`).

Geometry **does** survive a driver unload and reload with no SBR: after unloading, the registers
still read `0x009a0204` = `0x02669000` and `0x00100ce0` = `0x0000028a`, and a fresh load again
enumerated 40960 MiB on 610.43.03.

### No PLM moves geometry into the always-on domain

An **11-PLM in-HS geometry survival sweep** settled this exhaustively. For all eleven candidates the
in-HS pre-FLR state was identical
(`CFG1=0x2669000 CSTATUS0=0x800 LMR=0x28a amap=0x200404 resetPLM=0x8f`) and every post-FLR read
reverted to `CFG1=0x2449000 CSTATUS0=0x200 LMR=0x288 amap=0x280404`. Only `0x008200fc`,
`0x00823800`, `0x00823804` and `0x00823b00` stayed open (`PLM=0xffffffff`, AON = yes);
`0x00100b10`, `0x00100b38`, `0x009a0148`, `0x009a014c`, `0x009a0008`, `0x009a000c` and `0x00118128`
all re-locked to `0xffffff8f`. The card recovered to `boot0=0x170000a1 resetPLM=0xff`. The sweep was
captioned "welp, no dice".

**This is the structural reason the shipping design re-applies the geometry inside the GSP boot path
on every module load** rather than flashing or latching a permanent state. Of the four PLMs the
shipping tool opens, only FEAT (`0x00823804`) survives an FLR, so host-side CFG1/LMR writes issued
after an FLR are blocked. The geometry writes must happen inside the same no-FLR window as the PLM
opens.

!!! note "Superseded"
    The published `unlock-cmp-170hx` recipe was: write `FEAT_OVR_PLM 0x00823804` from ROP in HS mode,
    do an FLR, then write the memory geometry from the host. FEAT genuinely does survive FLR, so the
    approach looked sound. It fails on two independent grounds: CFG1 and LMR do not survive FLR, so
    the geometry write lands after the window has closed, and a tester who ran it reported
    "Already did, it's useless." The compute-style write-then-FLR flow does not transfer to memory.

!!! note "Superseded"
    Hunting for an always-on shadow register for memory geometry consumed hours, because the compute
    unlock's SS0 shadow was found by exactly that method. There is no equivalent for FB geometry.
    `0x001180f0` holding `0x050A` snapped back to `0x288` after FLR. `SECURE_SCRATCH_14` at
    `0x001180f8` is a booter stage-3 handoff register, not an LMR shadow, and
    `NV_PGC6_BSI_SECURE_SCRATCH_MMU_LOCAL_MEMORY_RANGE` (the register Blackwell resets LMR from)
    does not exist on GA100 at all.

### Corollary: the driver cannot silently undo it

`kmemsysReadUsableFbSize_GP102` on GA100 is read-only, and the open-source CPU-side RM computes
`fbSize` from LMR `0x00100ce0` rather than from the L2 amap. A hypothesis that stock RM reads the
`0x44` tier at boot, rewrites CFG1/CSTATUS back to the stock tier and re-locks the FB-geo PLMs was
**refuted by measurement**: after a full clean-driver boot and after a driver unload/reload with no
SBR, `0x009a0204` still read `0x02669000` and `0x00100ce0` still read `0x0000028a`. The observed
reversions were traced to operator-induced FLRs.

---

## Verifying that it landed

In order of trustworthiness, most trustworthy last:

1. **`nvidia-smi --query-gpu=memory.total`** proves nothing. A driver can be patched to print any
   number while memory silently folds. Multiple people were misled by exactly this, including an
   early flow that forced `fb_size` to about 80 GB from `nv-linux.c` on top of a 64 GB geometry.
2. **Register readback.** `CSTATUS_RAMAMOUNT` at `0x0090020C + n*0x4000` is the cheapest reliable
   check: `0x800` for the 40 GB tier, `0x1000` for the 64 GB tier. Expect the floorswept partitions
   to return `0xbadf20NN`, so 20 of 24 on a 10 GB card and 16 of 24 on an 8 GB card is the correct
   full-pass result, not 24 of 24. The driverless chain uses `CSTATUS == 0x800` as its verification
   predicate.
3. **A dense fold test.** Write every page's own index, read every page back. If an address line is
   missing, memory folds and two addresses hold the same data, which a conventional memtest that
   writes and reads the same region will not catch.

!!! danger "Do not sparse-sample the fold test"
    A sparse probe (one word per N MB) gives **false negatives** on a folded card, because the fold
    aliases at a channel-interleave offset rather than the identical byte offset: `LOW[0]` maps to
    `40GiB + interleave`, not `40GiB + 0`, so a sparse test writes one partner and checks a
    different address. The reference checker allocates all free VRAM minus 2 GiB, writes each 64 KiB
    page's own index via a PTX kernel, reads every page back, and exits 0 for real, 1 for fold. Also
    write all data first and then read all data back: interleaved read/write causes contention that
    gets very slow from around 48 GB. And evict L2 as you go, or reads are served from cache. Any
    fold result taken before the eviction methodology was adopted should be discarded.
    `SIGKILL`ing a live CUDA kernel during this test can wedge the card with **Xid 45** and force a
    reset cycle.

A successful 8 GB to 64 GB unlock presents as:

```text
NVIDIA-SMI 610.43.03   Driver Version: 610.43.03   CUDA Version: 13.0
NVIDIA CMP 170HX        0MiB / 65536MiB      34W / 250W     42C     P0
```

with CUDA via ctypes returning `cuInit` 0, `cuDeviceGetCount` 1, `cuDeviceGetName`
`NVIDIA CMP 170HX`, `cuDeviceTotalMem` 64.0 GB, attributes 75/76 giving compute capability 8.0. The
card name may also show as `Unknown`, which is normal.

!!! warning "`clocks.max.sm = 1935 MHz` is a reported field, not an achievable clock"
    It appears in the same `nvidia-smi` query as the capacity and is often quoted as part of the
    64 GB signature. The VBIOS table maximum graphics clock is 1695 MHz and the practical silicon
    ceiling is roughly 1604 to 1614 MHz at a +350 offset. Sustained SM clock is 1410 MHz nominal
    (1470 MHz at `-pl 300`). Treat 1935 MHz as low confidence and see
    [Compute throttle](compute-throttle.md).

Stability verdict as of the end of the archive window: **8 GB to 64 GB is stable and in production
use; 10 GB to 40 GB is stable; 10 GB to 80 GB reports the size but is not usable above roughly
40 GB.** A 64 GB card passed `gpu_burn` with zero errors after about an hour, and multiple
independent owners reproduced it with no in-channel case of a failed 64 GB unlock on an 8 GB card. A
10 GB card at 40 GB passed a 5-minute `gpu-burn`, a 30 GiB CUDA write/readback burn with zero
mismatches, and a 37 GiB tagged self-evicting fold test with no fold.

---

## Packaging: how the build picks a profile

`install.sh detect_card_profile()` is a four-rung ladder on
`nvidia-smi --query-gpu=memory.total`, not on the PCI ID:

| Reported MiB | Profile | Why |
|---|---|---|
| `>= 60000` | `8gb` | an already-unlocked 64 GB card, so a reinstall picks the same profile |
| `>= 35000` and `< 60000` | `10gb` | an already-unlocked 40 GB card |
| `7680` to `8704` | `8gb` | stock window, ±512 MiB tolerance for reserved FB |
| `9728` to `10752` | `10gb` | stock window |
| anything else | fail | prints `unknown:<mib>` and dies telling you to pass `--profile=8gb` or `--profile=10gb` |

If `nvidia-smi` is missing or returns something non-numeric the function returns 1 immediately.

**`driver/build.sh` does not read `common/constants.yaml`.** No script, patch or Makefile reads that
file anywhere in the tree. The build script hard-codes its own CFG1/LMR/fb_bytes per profile in a
bash `case`, then runs a Python rewriter over `kernel_gsp.c`. Because master's patch `0001` already
contains all six markers the rewriter checks for (`..._8GB_PCI_DEVICE_ID`, `..._10GB_PCI_DEVICE_ID`,
`0x02779000U`, `0x02669000U`, `0x0000001000000000ULL`, `0x0000000A00000000ULL`), the rewriter always
exits early printing `runtime device-id geometry (profile metadata=<label>)`. **On master the
build-time geometry rewrite never fires.** The bash profile only affects labels, expected-size
messages and the `card_profile` marker file.

`constants.yaml` is documentation. Its content happens to be correct on master, so no wrong value
ever shipped, but the file has no authority and editing it alone changes nothing that gets compiled.
Anyone reading a branch must check `build.sh` and the patch, not the YAML.

Install output paths:
`/lib/modules/$(uname -r)/updates/cmpunlocker/{driver_version,card_profile,unlock_geometry}`.
Uninstall is `sudo ./remove.sh --yes`; there is no `uninstall.sh` in the shipping repository.

---

## The 80 GB attempt, and why it is incoherent

!!! danger "The `80` branch is unmerged, unstable, and internally self-contradictory"
    It is documented here so that anyone who finds it understands what it actually programs. Do not
    run it on a card you need.

The unmerged `80` branch aims a 10 GB card at 81920 MiB. Two commits: `02ce75c` "Trying an 80GB
unlock instead of 40GB" and `3c53aca` "Correct LMR for 80GB". Its README claims
"Memory geometry (64GB on 8GB cards, 80GB on 10GB cards) | Working ✓". That claim is false and was
disproved within one to two days by the branch's own testers. Record it as a documentation defect,
not a result.

**What it actually differs by:** exactly one patch file, two lines. Patches `0002` through `0006`
are byte-identical to master. `0001-sec2-postbl-plm-ss-cfg.patch` differs only in
`cfg1Value = 0x02669000U` becoming `0x02779000U` and
`targetFbBytes ... 0x0000000A00000000ULL` becoming `0x0000001400000000ULL`. Plus `build.sh`,
`install.sh` and `constants.yaml`. (A claim that "no patch file differs from master" is wrong.)

**What it actually programs**, code-verified line by line:

| Layer | Value | Decodes to |
|---|---|---|
| CFG1 `0x009a0204` | `0x02779000` (tier `0x77`) | 4096 MiB per FBPA × 20 live = **81920 MiB** |
| LMR `0x00100ce0` | `0x0000028A` | 40 << 10 = **40960 MiB** |
| `targetFbBytes` / GSP `fb_length` | `0x0000001400000000` | **80 GiB** |

That is a **three-way disagreement**, and per the CFG1/LMR coherence rule above it is the same
class of CFG1/LMR mismatch that made GSP-RM revert the geometry in the 2026-07-13 experiment.
That experiment used a different pair, CFG1 `0x02669000` against a stock `0x288` LMR, so the
mechanism is analogous rather than identical.

`80/common/constants.yaml` does carry `lmr: "0x0000028B"` and `unlocked_mib: 81920`, but `build.sh`
never reads that file. `80/driver/build.sh` line 93 sets `LMR="0x0000028A"`, `80/install.sh` line
138 prints `Unlock geometry: 80GB (CFG1=0x02779000 LMR=0x0000028A)`, and the branch's patch `0001`
bakes `lmrValue = 0x0000028AU`. The build-time rewrite is short-circuited as well: the dual-device
guard tests for `0x02779000U`, `0x0000020BU`, `0x0000028AU`, `0x0000001000000000ULL` and
`0x0000001400000000ULL`, all of which are present, so the Python rewriter exits before substituting
anything. **Commit `3c53aca` "Correct LMR for 80GB" changed only inert metadata.** Every tester who
ran the `80` branch, before or after that commit, programmed CFG1 `0x02779000` + LMR `0x0000028A` +
`fb_length` 80 GiB.

The branch also adds an installer rung master does not have,
`if (( mem_mib >= 75000 )); then echo "10gb"`, placed ahead of the `>= 60000` test, because without
it an 81920 MiB card would re-detect as an 8 GB card. Master has no such rung because master never
produces an 81920 MiB card.

**The failure signature is precise, but each component of it comes from a single reporter and none
has been independently reproduced.** `nvidia-smi` shows about 81920 MiB and CUDA
reports `global memory size=85545582592` bytes (79.67 GiB). `cudaMalloc` and `cudaMemset` for 77 GiB
both succeed. One tester reports `cuda_memtest` completing once immediately after reboot and failing
every subsequent run, hanging after `Attached to device 0 successfully.` unless the allocation is
capped at 39 GB; a second operator saw Xid 154 after the same tests but said explicitly of the first
operator's errors, "I don't know what errors [they] are getting." Kernels
touching more than roughly 40 GB cause fatal GPU loss and normally require a full reboot. Reported
Xid codes include Xid 31 (described as harmless) and Xid 154 after CUDA memory tests; the dominant
reported symptom is hangs. Xid 31 alone was suggested by a bystander and was not corroborated as
*the* signature by the operator with the failing card. One tester's model loads failed above
20 GB, another's in the 40 to 60 GB band. The failures are **independent of the power limit**. One
group reported 2,796 errors in a `gpu-burn` run at 80 GB on a card that ran cleanly at 40 GB. The
configuration also works only once per driver load, and on at least one system needs a cold power
cycle rather than a driver reload before it can be fired again.

Note the fold boundary lands at **exactly 40 GiB**, which matches the LMR the branch actually
programs. The driverless result below makes the match look causal rather than coincidental.

!!! warning "Experimental: the coherent triple was fired, and the fold went away"
    The coherent set was **not** reached by rebuilding the branch. It was reached by a clean-room
    refire script between 2026-07-23 and 2026-07-27, logging
    `CFG1=0x02779000 LMR=0x0000028b CST=20/24 resetPLM=0x00ff` with L2 decode `0x10000300` and
    81920 MiB reported under both GSP-RM and CPU-RM. A dense tagged write/readback then returned
    310 of 310 blocks correct across 77.5 GiB, **no fold**, and a later run reached 72 GiB at stock
    boot timings. The limits are real: roughly one CUDA context per fire before Xid 154, about
    79 % of peak bandwidth above the boundary, the top roughly 2 GiB untested, and only two
    operators. It is not shipped and it is not an install path.

    **Shipping master gives a 10 GB card 40 GB, and 40 GB is the supported configuration.**
    Rebuilding the branch with `lmrValue = 0x0000028BU` in
    `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` **and** `LMR="0x0000028B"` in
    `driver/build.sh` (not just in `constants.yaml`, which is not read) remains untried, and is
    what would tell you whether a driver can carry the geometry the fire script can.
    See [The 80 GB question](../frontier/80gb.md).

An intermediate rung has never been tried either. The per-channel tier is coarse (512 / 2048 / 4096
MiB), so 48, 56 or 64 GB on a 10 GB card is not reachable by tier alone; it would need CFG1 pinned
at tier `0x77` with the driver-visible size clamped through `targetFbBytes` and the late-PMA region
limit. Asked directly in-channel whether a 10 GB card could unlock to a stable 60 GB, the answer was
"I don't believe its been tried."

---

## Dead ends worth knowing about

- **Flashing a different VBIOS.** The "16 GB" 170HX image (TechPowerUp 239457) and the 10 GB image
  (268984) were both flashed onto an engineering-sample GA100 that accepts unsigned and mismatched
  ROMs. The board still reported 8 GB in both cases. Capacity is not a function of which ROM is
  loaded; it follows the strap-selected CFG1 word. Separately, flashing the 8 GB VBIOS onto a 10 GB
  card leaves the card unable to boot, attributed to device-ID mismatch.
- **A MAC-forged VBIOS memory unlock.** It would need one byte flipped at `0x41D53` (250 W 170HX) or
  `0x41F53` (300 W). Flipping `44` to `66` reaches only the 40 GB geometry; reaching 64 GB would
  require `44` to `77`. No MAC forgery has been achieved, and the byte-level mapping is medium
  confidence and never empirically tested.
- **The L2/LTC amap `0x0017e22c` as the greater-than-10 GB gate.** This was the team's working
  root-cause model for over a week. Disproved the same day it was written down: a run reached real
  40 GB with `0x17e22c` sitting at its native `0x00280404` the whole time, never programmed. The
  shipping driver contains **no** `0x17Exxxx` address at all, in any patch, on master or on any of
  the 12 unreleased branch snapshots. A claim that the shipping `plmTable` writes the LTC-decode
  cluster (`0x17E2B4`/`A0`/`E4`/`FC`) is simply false.
- **The "mystery PLM" `SEC2_DEBUG_PRI_FBPA_CFG1 0x009a0204`.** `0x009a0204` is the CFG1 data
  register itself, not a PLM. The FBPA PLM is `0x009a0148`.
- **The one-second register re-apply loop.** A third-party commit rewrote the geometry registers
  every second. Two experienced reviewers and a tester who never needed it dismissed it: the loop
  fights the driver over compute retiming and has nothing to do with the memory unlock.
- **The `ecc` branch.** Contains no ECC code. Single commit, "Fixed dual geometry support", patch
  directory byte-identical to master.
- **"LMR is at `0x1183A4`."** That is the correct local-memory-range location for GP102. The
  verified GA100 address is `0x00100ce0`.
- **Nibble-shifted transcriptions.** `0x26690000`, `0x27790000` and `0x24490000` all circulated in
  chat. The verified forms are `0x02669000`, `0x02779000` and `0x02449000`.
- **The `docs` branch.** It gets the CFG1/LMR table right but invents an acronym, expanding LMR as
  "LM Request". The register is `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`, Local Memory **Range**. The
  same branch also misstates SS0/SS1 as `0xffffffff`/`0xffffffff`; the correct values are
  `0x88888888` and `0x00000008`.

See [Dead ends](../history/dead-ends.md) for the full catalogue.

---

## Alternative routes to the same registers

The shipping installer is a patched kernel module, but it is not the only demonstrated path.

!!! warning "Experimental: the driverless re-fireable ROP chain"
    A re-entrant SEC2 ROP chain was hardware-proven to leave CFG1 = `0x02669000` surviving into a
    clean, unmodified GSP-RM driver boot with no FLR and no SBR (`BooterLoad 0x0`). Two enabling
    tricks: every fire pairs its useful write with a WPR2_LO teardown (`0x1fa824` set to
    `0x1ffffe00`, `0x1fa828` to `0x00000000`, that is start greater than end, an empty region),
    because each booter run re-carves WPR2 and leaving it up taints the next overflow; and the ACR
    mutex is released via the clean `0x7f2f` tail leaving `resetPLM = 0xff`. Readiness predicate:
    broadcast CFG1 equals the target **and** the SEC2 reset PLM (BAR0 `0x8403c4`, falcon offset
    `0x3c4`) reads `0xff`. In this chain, WPR2_HI must be cleared as the **final** fire, after the
    host CFG1 writes, because `kgspIsWpr2Up_HAL` reads the WPR2_HI VAL field and a stock driver
    would otherwise bail with `NV_ERR_INVALID_STATE`. This toolchain is not in the shipping
    repository.

!!! warning "Experimental: an unmodified-driver Python unlocker"
    A script that runs before the driver loads was demonstrated the day after the opposite was
    concluded impossible: no patched `.ko`, no installer. It is the cleanest known route in
    principle. It is not present in the shipping tree or in any archived branch, so the shipping
    product remains the patched-module path.

!!! note "How the leaked proof-of-concept differed"
    The leaked package patches the `WprMeta` structure in host memory immediately before GSP-RM
    loads, which is why it necessarily ships modified open kernel modules. The clean-room approach
    instead opens the relevant PLM and writes the geometry registers directly. Medium confidence:
    this is stated by someone holding both artefacts and was not independently re-derived.

The historical community stage-1 poke set that preceded the driver patch was five writes:
`0x009A0204` = `0x02669000`, `0x00100CE0` = `0x0000028A`, `0x00823804` = `0xFFFFFFFF`,
`0x0082381C` = `0x88888888`, `0x00823820` = `0x00000008`. The generator delivers up to five writes
in a single overflow and pads any shorter list with harmless `(0x000014A0, 0)` entries up to exactly
five, so the exit-frame offsets stay put. The shipping driver differs in one respect:
it opens `0x00823804` through a Booter pass rather than writing it directly from the host.

---

## See also

- [The memory subsystem](../hardware/memory-subsystem.md), the physical partitions and tiers
- [Privilege level masks](privilege-level-masks.md)
- [The ROP chain](rop-chain.md) and [Falcon and Booter](falcon-and-booter.md)
- [Driver patches](driver-patches.md), all six patches in order
- [Compute throttle](compute-throttle.md), the SS0/SS1 half of the same window
- [Register reference](register-reference.md)
- [Verification](../procedures/verify.md) and [Troubleshooting](../procedures/troubleshooting.md)
- [The 80 GB question](../frontier/80gb.md)
- [Glossary](../start/glossary.md)
