# The six driver patches, one by one

## What this page covers

The shipping CMP 170HX unlock is not a firmware flash, not a userspace daemon and not a binary
edit. It is **six numbered patch files** applied to an unmodified checkout of NVIDIA's
`open-gpu-kernel-modules` at version 610.43.03 or 610.43.02, compiled locally, and installed as
five kernel modules. This page walks through each patch: what it changes, in which source file,
why it is needed, and what fails if you drop it.

The whole unlock (privilege-level mask opening, the compute-throttle writes, the memory-geometry
writes) lives in **patch 0001**, inside `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`. The other
five patches exist because a GA100 that suddenly claims 64 GiB of framebuffer breaks several
downstream assumptions in the driver: fatal assertions fire, the PRAMIN window lands out of
range, the physical memory allocator never learns about the new memory, the copy-engine scrubber
picks the wrong PTE kind, and RM tears down software state between clients. Each of 0002 to 0006
repairs exactly one of those.

If you only remember one command from this page:

```bash
sudo dmesg | grep SEC2_DEBUG
```

Almost every line the patch set emits carries that prefix. The one exception is the downgraded
WPR2 warning from patch 0001, `WPR2 already up before GSP boot; continuing for recovery`, which
is printed at `LEVEL_WARNING` with no `SEC2_DEBUG:` tag.

---

## The series at a glance

Applied in filename order, with `patch -p1`, against a freshly extracted stock tree.

| # | File | Bytes | Lines | Primary source file | Role |
|---|---|---|---|---|---|
| 0001 | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,278 | 463 | `gpu/gsp/kernel_gsp.c` | The exploit: opens PLMs, writes SS0/SS1/CFG1/LMR, widens `fb_length` |
| 0002 | `0002-booter-verify.patch` | 3,901 | 87 | `gpu/gsp/arch/turing/kernel_gsp_tu102.c` | Softens four fatal asserts, prints the post-boot readback proof |
| 0003 | `0003-late-pma.patch` | 10,317 | 263 | `gpu/mem_mgr/mem_mgr.c`, `nvalloc/unix/src/osinit.c` | Registers the new memory with the physical memory allocator |
| 0004 | `0004-bar0-pramin-clamp.patch` | 841 | 20 | `gpu/bus/arch/maxwell/kern_bus_gm107.c` | Keeps the PRAMIN window inside reachable BAR0 space |
| 0005 | `0005-ce-scrub-workarounds.patch` | 1,604 | 38 | `mem_mgr/arch/turing/mem_mgr_tu102.c`, `mem_mgr/mem_scrub.c` | Forces the scrubber into physical mode with a plain PTE kind |
| 0006 | `0006-persistent-sw-state.patch` | 584 | 19 | `kernel-open/nvidia/nv.c` | Sets the persistent-software-state flag at PCI probe |

Total: **36,525 bytes across six patches**, touching **ten distinct source files**. Line counts
include diff headers. Byte counts are the repository blob sizes with LF line endings. A checkout
made on Windows with `core.autocrlf=true` inflates every file by one byte per line, which is
where the frequently quoted 37,415 byte total comes from.

The full list of files the series touches:

```text
src/nvidia/generated/g_kernel_gsp_nvoc.h
src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c
src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c
src/nvidia/arch/nvalloc/unix/src/osinit.c
src/nvidia/inc/kernel/gpu/mem_mgr/mem_mgr.h
src/nvidia/src/kernel/gpu/mem_mgr/mem_mgr.c
src/nvidia/src/kernel/gpu/bus/arch/maxwell/kern_bus_gm107.c
src/nvidia/src/kernel/gpu/mem_mgr/arch/turing/mem_mgr_tu102.c
src/nvidia/src/kernel/gpu/mem_mgr/mem_scrub.c
kernel-open/nvidia/nv.c
```

`driver/build.sh` downloads
`https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`, caches
it under `driver/.build/`, deletes and re-extracts a clean tree on every run, then loops:

```bash
for p in "${patches[@]}"; do patch -p1 < "${p}"; done
```

The script runs under `set -euo pipefail`, so a single rejected hunk aborts the build. Because
the loop is a plain glob over `driver/patches/*.patch`, a third-party diff dropped in as
`0007-*.patch` composes cleanly with the series. See [P2P](../frontier/p2p.md) for the one
recorded case of that.

Five modules are built and installed to `/lib/modules/$(uname -r)/updates/cmpunlocker/`:
`nvidia.ko`, `nvidia-modeset.ko`, `nvidia-uvm.ko`, `nvidia-drm.ko`, `nvidia-peermem.ko`. Only
`nvidia.ko` carries unlock code; the other four are stock rebuilds that exist so the whole set
has a matching `srcversion`.

---

## The device gate that all six share

Every unlock site tests the **upper 16 bits** of the PCI device ID against the two known 170HX
SKUs. Patch 0001 adds the shared helper to `kernel_gsp.c`:

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID  0x2082

static NvBool _kgspSec2PostblTimingEnabled(OBJGPU *pGpu)
{
    NvU32 devId = pGpu->idInfo.PCIDeviceID >> 16;
    return (devId == SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID ||
            devId == SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID);
}
```

Consequences worth internalising:

- Any other GA100 SKU, including an A100 in the same chassis, boots the completely stock path
  with the patched modules installed. The patch is inert on it.
- `install.sh` greps `lspci` for `10de:20b0|10de:20c2|10de:2082`, so a `20b0` card installs
  successfully and then never unlocks, because the in-driver gate does not list `0x20B0`. The
  installer says so: `This card reports 0x${DEVID}; install will continue, but unlock may not
  activate.`
- Patch 0006 is the one exception to the `>> 16` form. It runs in `kernel-open/nvidia/nv.c` at
  PCI probe, before an `OBJGPU` exists, so it compares the raw `nv->pci_info.device_id`.

Geometry is selected at **runtime from the device ID**, not at install time. Both profiles are
baked into patch 0001, so `--profile=` on the installer only changes the printed banner and the
metadata files. See [Memory geometry](memory-geometry.md).

---

## 0001 `sec2-postbl-plm-ss-cfg`: the exploit

This is the patch. Everything else is support. It is 19,278 bytes, roughly 460 diff lines, and
it makes seven distinct changes.

### 1. Two new fields on the GSP object

Inserted into `src/nvidia/generated/g_kernel_gsp_nvoc.h` immediately after
`MEMORY_DESCRIPTOR *pSignatureMemdesc;`, at hunk anchor `@@ -544,6 +544,8 @@`:

```c
NvU8 *pStockSignatureData;
NvU64 stockSignatureSize;
```

The real GSP firmware signature is copied aside into these before the payload overwrites the
buffer, and logged as `SEC2_DEBUG: saved stock signature (4096 bytes)`.

!!! danger "Restore stock GSP firmware first"
    If the machine ever ran cmpunlocker's firmware-patching predecessor, restore
    `gsp_tu10x.bin` to stock before installing the driver patch. The driver saves whatever
    signature the firmware carries as "stock". If the firmware on disk is still patched, it
    saves the **exploit payload** as stock, and the subsequent clean GSP-RM boot DMAs the wrong
    ROP chain.

    ```bash
    GSP_DIR=/lib/firmware/nvidia/610.43.03
    sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
    ```

### 2. An oversized signature buffer

`_kgspCreateSignatureMemdesc` normally allocates `NV_ALIGN_UP(pGspFw->signatureSize, 256)` bytes,
which is 4096 in practice. When the device gate is true it instead allocates
`SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL` (63,488 bytes) in `ADDR_SYSMEM`, 256-byte
aligned because the SEC2 Booter's DMA engine requires it.

That oversize buffer is the whole exploit vehicle: the signed Booter reads it with an unbounded
DMA and smashes its own stack. The mechanism is covered in
[The ROP chain](rop-chain.md) and [Falcon and Booter](falcon-and-booter.md).

### 3. The payload

`_kgspSec2PostblTimingFillPayload` fills the entire buffer with the dword
`SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7`, then overwrites exactly **24 dwords**, all written
little-endian by a byte-wise helper `_kgspSec2PostblTimingPutU32`:

| Offset | Value | Role |
|---|---|---|
| `0x1100` | `0x00000007` | stack/control word |
| `0x5b40` | `0xc0deca7e` | fake stack canary |
| `0xf754` | `writeValue` | **patched per PLM pass** |
| `0xf758` | `0xc0deca7e` | canary |
| `0xf75c` | `0x00000cbd` | gadget |
| `0xf76c` | `writeAddr` | **patched per PLM pass** |
| `0xf774` | `0x00001fbd` | gadget |
| `0xf780` | `0x00000000` | |
| `0xf788` | `0x000010aa` | **the BAR0 write gadget** |
| `0xf78c` | `0x0000815a` | tail |
| `0xf790` | `0x00008e18` | tail |
| `0xf794` | `0xc0deca7e` | canary |
| `0xf798` | `0x0000815a` | tail |
| `0xf79c` | `0x00000000` | |
| `0xf7a0` | `0xc0deca7e` | canary |
| `0xf7a4` | `0x00001fbd` | gadget |
| `0xf7b0` | `0x0000ffbc` | tail |
| `0xf7b8` | `0x0000582d` | tail |
| `0xf7c4` | `0xc0deca7e` | canary |
| `0xf7c8` | `0x00000cbd` | gadget |
| `0xf7d8` | `0x00000003` | |
| `0xf7e0` | `0x00001fbd` | gadget |
| `0xf7f4` | `0x00000ccb` | tail |
| `0xf7f8` | `0x00007f2f` | tail |

Only two of the 24 change between passes: `writeAddr` at `0xf76c` and `writeValue` at `0xf754`.
The chain is a generic single-register write primitive, refired once per target.

The payload can be overridden from disk. `_kgspCreateSignatureMemdesc` first tries
`os_open_and_read_file("/lib/firmware/nvidia/ga100/gsp/dmem.bin", pSignatureVa, 0xf800)`. On
success it logs `SEC2_DEBUG: loaded 63488 bytes from ...`. On the normal path that file does not
exist, and the driver logs a benign status `0x59` and falls back to the built-in fill:

```text
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
```

The built-in default arms `writeAddr = 0x009a0148`, `writeValue = 0xffffffff`, which the PLM loop
immediately overwrites per iteration.

!!! note "`0xFACEB13D` is not the shipping canary"
    Earlier standalone harnesses used `0xFACEB13D` at `CANARY_ADDR = 0x6340` with
    `DMA_TARGET = 0x0800`. That is the same slot as the shipping `0x5b40` canary
    (`0x5b40 + 0x0800 = 0x6340`) with a different literal. Reading shipping code, expect
    `0xc0deca7e`.

### 4. The PLM loop

The inserted block sits in the `kgspInitRm` path in `kernel_gsp.c`, immediately **after**
`kgspPrepareForBootstrap_HAL(...)` returns, not inside it. Hunk anchor `@@ -4821,6 +4844,117 @@`.

Four privilege-level masks, up to two attempts each. A PLM is a per-register access-control
register: it decides which privilege level may read or write the register it guards. See
[Privilege level masks](privilege-level-masks.md).

```c
/* plmTable[] entries, verbatim from patch 0001 */
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

!!! warning "Three of four target `0xffffffff`, WPR_CFG does not"
    `WPR_CFG` at `0x001fa7cc` is deliberately opened to **`0xfffff0ff`**. The loop's success
    predicate is `if (regVal == plmTable[plmIdx].value)`, so `0xfffff0ff` is a **pass**. The
    project's own `docs/DEBUGGING.md` says "All the PLMs must show `0xffffffff`" and the
    `README.md` says "Expected: PLMs opening to 0xffffffff". Both are loose wording. Do not read
    `WPR_CFG=0xfffff0ff` as a failure.

Around each attempt the driver saves and restores the write-protected-region-2 bounds. Before the
loop it reads `wpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824U)` and
`wpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828U)`; on every attempt it writes both back, refills the
payload for that `{address, value}` pair, then calls:

```c
kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
    memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
```

and reads the target register back. After the loop it restores `wpr2Lo`/`wpr2Hi` one final time.
Worst case that is **eight Booter Load executions before the normal bootstrap Booter Load**.

!!! note "`status=0xffff` on every payload pass is expected"
    `s_executeBooterUcode_TU102` finds an error code left in mailbox0 by the seccode after every
    run, so `kgspExecuteBooterLoad_HAL` returns `NV_ERR_GENERIC` (`0xffff`) unconditionally on
    payload passes. That is the invalid-signature complaint raised *after* the injected chain has
    already executed. **The register readback is the only valid success criterion.**
    `kgspExecuteBooterLoad_TU102` also performs `kflcnReset(SEC2)` before every run, so SEC2
    accumulates no state across passes. Booter status `0x31` during these early passes is also
    tolerated.

Failure prints `FAILED to open %s after 2 attempts`. Success prints:

```text
SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff
```

### 5. The four host register writes

Once the PLMs are open, the host CPU writes the unlock registers **directly**. No exploit is
involved in this step, which is the key architectural insight: the ROP chain only has to buy
write access, after which everything is an ordinary MMIO store.

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* FBPA CFG1 */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* MMU LMR   */
```

| Device ID | Card | `cfg1Value` | `lmrValue` | `targetFbBytes` | Result |
|---|---|---|---|---|---|
| `0x20C2` | 8 GB | `0x02779000` | `0x0000020B` | `0x0000001000000000` | 65536 MiB |
| `0x2082` | 10 GB | `0x02669000` | `0x0000028A` | `0x0000000A00000000` | 40960 MiB |

SS0 and SS1 are written **unconditionally for both SKUs**. `common/constants.yaml` agrees with
the code (`ss0: "0x88888888"`, `ss1: "0x00000008"`).

!!! danger "The documentation branch is wrong about SS0 and SS1"
    `docs/ARCHITECTURE.md` claims cmpunlocker writes `0xffffffff` to both SS0 and SS1 and shows
    expected dmesg lines to match. It does not. Validating an unlock against those strings will
    make a working card look broken. The code has written `0x88888888` / `0x00000008` since
    2026-07-18. See [Compute throttle](compute-throttle.md).

A readback line follows:

```text
SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)
```

### 6. Stock signature rebuild, and the second WPR meta pass

`kgspSec2PostblTimingRebuildStockSignature()` frees and re-creates `pSignatureMemdesc` at
`NV_ALIGN_UP(stockSignatureSize, 256)` with `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`, copies
the saved stock signature back, and resets `pWprMeta->sysmemAddrOfSignature` and
`pWprMeta->sizeOfSignature` to the new descriptor. If it returns anything other than `NV_OK`,
`_kgspBootGspRm` propagates that status and the boot aborts with
`SEC2_DEBUG: rebuild stock signature failed: 0x%x`.

`kgspPopulateWprMeta_HAL()` is then called a **second** time (it was already called in the stock
position before the PLM work). The first call logs `SEC2_DEBUG: WPR meta fbSize=... wprEnd=...
heapSize=...`; the second logs `SEC2_DEBUG: WPR meta updated fbSize=... wprStart=... wprEnd=...
heapOffset=... heapSize=...`. The second call is what makes the driver's WPR2 placement agree
with the now-enlarged geometry.

### 7. The WPR2 downgrade and the GSP static-info rewrite

Two more edits complete the patch.

The "WPR2 already up" fatal error is **downgraded, not deleted**. Inside the existing
`if (kgspIsWpr2Up_HAL(...) && !pGpu->getProperty(pGpu, PDB_PROP_GPU_PREINITIALIZED_WPR_REGION))`
guard, at anchor `@@ -4805,14 +4820,22 @@`, two `NV_PRINTF(LEVEL_ERROR, ...)` lines and
`return NV_ERR_INVALID_STATE;` become one line:

```c
NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n");
```

Execution falls straight through to `kgspPopulateWprMeta_HAL`. This is mandatory: the unlock runs
Booter Load up to eight times, and Booter Load leaves WPR2 up.

Then, at `@@ -5164,6 +5285,53 @@`, after `kgspInitRm` receives GSP static config info, the patch
rewrites it: `pGSCI->fb_length = targetFbBytes`, and if the last FB region's `limit` is below
`targetFbBytes - 1` it sets `limit = targetFbBytes - 1`, `reserved = limit - base + 1`,
`supportCompressed = NV_TRUE`, `supportISO = NV_TRUE`, `performance = 20`. Logged as
`SEC2_DEBUG: static-info BEFORE/AFTER`.

### What breaks without 0001

Everything. There is no unlock. The card boots stock at 8192 or 10240 MiB with the compute
throttle in place.

---

## 0002 `booter-verify`: asserts and proof

Touches only `src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c`. Three jobs.

**It names five registers.** These defines are purely for the logging in this file:

```c
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM        0x00823804
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED   0x0082381c
#define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820
#define SEC2_DEBUG_PRI_FBPA_CFG1                   0x009a0204
#define SEC2_DEBUG_PRI_MMU_LMR                     0x00100ce0
```

Note the names: `FEATURE_OVERRIDE_SM_SPEED` and `_SM_SPEED_1` for SS0 and SS1. Those are the
code's own names for the compute-throttle registers, and they read as clock or throughput
controls rather than a cluster enable bitmask.

**It converts four fatal assertions into logged status checks** in `kgspBootstrap_TU102`: the
`NV_ASSERT_OR_RETURN` on `pPreparedFwsecCmd != NULL`, `NV_ASSERT_OK_OR_RETURN(kflcnReset_HAL)`,
the FWSEC status assert, and `NV_ASSERT_OK_OR_RETURN(kflcnResetIntoRiscv_HAL)`.

**It prints the definitive proof line.** After the real `kgspExecuteBooterLoad_HAL`, for the two
device IDs only, it prints `SEC2_DEBUG: normal BooterLoad status=0x%x`, and then, only when that
status is `NV_OK`:

```text
SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...
```

That is the readback showing the unlock survived the genuine GSP boot, not just the payload
passes.

### What breaks without 0002

Control flow does not actually change: the replacements still `return status` on any non-`NV_OK`
result from FWSEC or either Falcon reset, exactly as the assertions did. What 0002 buys is
diagnosis. Without it nothing names which of the four steps failed or with what status, and the
only post-boot verification line disappears, which is the line every troubleshooting flow asks
for. See [Verify](../procedures/verify.md).

---

## 0003 `late-pma`: making the memory allocatable

Patch 0001 tells GSP-RM that the framebuffer is bigger. That is not the same as making the extra
memory allocatable. The physical memory allocator (PMA) still has to be told about it. Patch
0003 has **four hunks** plus a hook.

1. A forward declaration of `memmgrSec2DebugLateExtendHighPmaRegion` in
   `src/nvidia/inc/kernel/gpu/mem_mgr/mem_mgr.h`.
2. A diagnostic after `kmemsysPostHeapCreate_HAL`:
   `SEC2_DEBUG_HEAP: fbAddrSpace=... mapRam=... fbTotal=... fbUsable=... heapTotal=...
   regionBytes=... publicBytes=... numRegions=...`
3. The roughly 180-line `memmgrSec2DebugLateExtendHighPmaRegion()` itself.
4. The other CeUtils virtual-mode exclusion, appended to the compbit-backing condition in
   `mem_mgr.c`. The first is in patch 0005 (`mem_scrub.c`); there are two in the whole series.
   Patch 0005's second hunk is the PTE-kind override (`NV_MMU_PTE_KIND_GENERIC_MEMORY`), not a
   virtual-mode guard.

Plus the hook in `src/nvidia/arch/nvalloc/unix/src/osinit.c` that calls it late in
`RmInitAdapter` and logs `SEC2_DEBUG: late PMA extension status=0x%x`.

The function itself:

```text
stockFbBytes = 0x200000000ULL           /* 8 GiB, hard-coded for BOTH SKUs */
candidate    = highest-limit Ram.fbRegion[] entry with
               bRsvdRegion && !bInternalHeap && limit >= stockFbBytes
pmaRegion    = [ NV_MAX(base, stockFbBytes), limit ], bSupportCompressed = NV_TRUE
early-out    if pmaIsPmaManaged already covers the range
pmaRegisterRegion(pPma, numPmaRegions, NV_FALSE, &pmaRegion, 0, NULL)
then, only on NV_OK:
  split   -> append public FB_REGION_DESCRIPTOR [8 GiB, limit] with
             bRsvdRegion = NV_FALSE, bInternalHeap = NV_FALSE,
             bSupportCompressed = NV_FALSE; clamp the reserved region to stockFbBytes - 1
  or
  in-place-> clear bRsvdRegion
finally  memmgrRegenerateFbRegionPriority()
```

If a split is needed and `numFBRegions >= MAX_FB_REGIONS`, it returns
`NV_ERR_INSUFFICIENT_RESOURCES` rather than splitting.

!!! note "`stockFbBytes` is 8 GiB even on a 10 GB card"
    `0x200000000ULL` is hard-coded for both profiles. On a `0x2082` card the boundary is
    therefore 8 GiB, not the card's native 10 GiB. This is in the shipping code and is not a
    typo in this wiki.

### What breaks without 0003

The extra framebuffer is reported but never handed to PMA, so the region stays reserved and
allocations above the stock size fail. This is the difference between "nvidia-smi shows 65536
MiB" and "you can actually allocate 63 GB".

---

## 0004 `bar0-pramin-clamp`: keeping PRAMIN reachable

The smallest interesting patch: a single ten-line hunk in
`src/nvidia/src/kernel/gpu/bus/arch/maxwell/kern_bus_gm107.c`. PRAMIN is a sliding window in
BAR0 through which the CPU reaches framebuffer memory. Stock code places it at the top of the
framebuffer:

```c
offsetBar0 = (pMemoryManager->Ram.fbAddrSpaceSizeMb << 20) - DRF_SIZE(NV_PRAMIN);
```

The patch adds, for `0x20C2` or `0x2082` when `Ram.fbAddrSpaceSizeMb > 0x2000` (8192 MB):

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

Note the threshold is 8192 MB, so the clamp engages on a stock 10 GB card too, not only on an
unlocked one.

### What breaks without 0004

The PRAMIN aperture is computed from 65536 MB and lands outside reachable BAR0 space. GA100 BAR0
is a 16 MiB PRI aperture; a window placed at the top of a 64 GiB address space is simply not
addressable through it.

---

## 0005 `ce-scrub-workarounds`: physical-mode scrubbing

Two hunks on `master`.

In `mem_mgr_tu102.c`, the scrubber's PTE-kind helper obtains the GPU with
`ENG_GET_GPU(pMemoryManager)` and returns early for the two device IDs:

```c
*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY;   /* instead of */
/*         NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC */
```

In `mem_scrub.c`, the `if (memmgrUseVasForCeMemoryOps(pMemoryManager))` guard gains:

```c
&& ((pGpu->idInfo.PCIDeviceID >> 16) != 0x20C2
 && (pGpu->idInfo.PCIDeviceID >> 16) != 0x2082)
```

so `DRF_DEF(0050, _CEUTILS_FLAGS, _VIRTUAL_MODE, _TRUE)` is never set and the copy-engine
scrubber runs in **physical** mode. The other virtual-mode exclusion is in patch 0003.

### What breaks without 0005

The scrubber attempts virtual-mode copy-engine operations with a compression-capable PTE kind
across a framebuffer whose geometry the MMU tables were not built for. This is the patch you are
most likely to be tempted to skip and should not.

---

## 0006 `persistent-sw-state`: no daemon required

Nineteen lines total, nine of them added code, in `kernel-open/nvidia/nv.c` at
`@@ -1521,6 +1521,15 @@`, inserted after the IRQ-setup error path and before
`(void)rm_get_gpu_uuid_raw(sp, nv);`:

```c
if (nv->pci_info.device_id == 0x20C2)
{
    nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;
}
else if (nv->pci_info.device_id == 0x2082)
{
    nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;
}
```

The two arms are identical and could be one condition. Cosmetic, not a bug.

`NV_FLAG_PERSISTENT_SW_STATE` is an existing `nv.h` flag intended for SR-IOV virtual functions.
Repurposed here, it stops RM tearing down software state when the last client closes. It is
effectively built-in persistence mode, and it is why the current design needs no systemd
watchdog. Earlier generations of the tooling did need one; `remove.sh` still cleans up a legacy
`cmpunlocker.service` and `/opt/cmpunlocker/daemon/watchdog.py` that the current installer never
creates. See [Tool lineage](../history/tool-lineage.md).

### What breaks without 0006

RM tears down GPU software state whenever the last client exits. On a card whose geometry was
established during driver load, that teardown-and-rebuild cycle is exactly what you do not want
between CUDA processes.

---

## Reading a successful boot

```bash
sudo dmesg | grep SEC2_DEBUG
```

Expected sequence, in order:

| Line | From | Meaning |
|---|---|---|
| `saved stock signature (4096 bytes)` | 0001 | Real signature copied aside |
| `<dmem.bin path> not found (0x59), using built-in payload` | 0001 | Normal, no override file |
| `WPR meta fbSize=... wprEnd=... heapSize=...` | 0001 | First WPR meta pass |
| per-PLM lines, `status=0xffff` | 0001 | Expected on every payload pass |
| `PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff` | 0001 | All four open |
| `POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x...)` | 0001 | Unlock registers written |
| `WPR meta updated fbSize=...` | 0001 | Second WPR meta pass |
| `normal BooterLoad status=0x0` | 0002 | The genuine boot succeeded |
| `POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...` | 0002 | Survived the real boot |
| `static-info BEFORE/AFTER` | 0001 | `fb_length` widened, once GSP has returned its static config |
| `late PMA extension status=0x0` | 0003 | New memory is allocatable |

One reference capture from a working two-card 8 GB boot on 610.43.03 contained **152**
`SEC2_DEBUG` lines (medium confidence, single capture). Absence of the trail is not proof of
failure on its own, because kernel ring buffers rotate.

!!! note "Line counts are not a reliable cross-build fingerprint"
    34 (Gen1 build) / 80 (Gen2 build) is recorded at high confidence, while a separate
    Gen2-branch 610.43.03 boot counted 152 at medium confidence. Do not read a mismatch as a
    failed install.

---

## Naming, and why it looks like an NVIDIA feature

The patch camouflages itself with fictional NVIDIA-style names. `SEC2_DEBUG_PRI_*`,
`kgspSec2PostblTiming*` and the `SEC2_DEBUG:` log prefix appear **nowhere** in the stock 610.43.03
source. "PostBL Timing" is a plausible-sounding but invented feature name. Two independent
reviews read this as deliberate disguise of exploit code as a manufacturing or debug feature,
and as evidence against NVIDIA-internal authorship, since a person with legitimate internal
access would not need the disguise. The practical consequence is the useful one: a single grep
finds every unlock line in a boot log.

!!! note "Invented acronym expansions to ignore"
    The `docs` branch expands PLM as "Program Logic Modules", SS0/SS1 as "Suspension State"
    registers, PMA as "Power Management Array", and introduces a "SEC2 Booter PMM" that appears
    nowhere in the code. All four are wrong. PLM is the privilege level mask; PMA is the
    physical memory allocator (`pmaRegisterRegion`, `pmaGetFreeMemory`, `PMA_REGION_DESCRIPTOR`,
    `pmaIsPmaManaged`); the code's own names for SS0/SS1 are
    `FEATURE_OVERRIDE_SM_SPEED` and `_SM_SPEED_1`. Do not propagate the expansions.

---

## What the shipping series does **not** contain

Several widely repeated claims describe artefacts other than cmpunlocker `master`. Verified
absent from all six patches:

| Claim | Reality |
|---|---|
| `gpuValidateRegOps` stubbed to `return NV_OK` | Not present. No change to `subdevice_ctrl_gpu_regops.c` at all. The pre-release `patch.diff` and, apparently, the leaked package did carry this unconditional bypass of register-operation permission validation; it was dropped before release. That is a real safety improvement, not cleanup. |
| `CMP170HX_WPR2_SAFE_LIMIT 0x0A00000000ULL` clamp on `pWprMeta->fbSize` | Proposed, never shipped. The released design widens `fb_length` and the last FB region and clamps only the BAR0/PRAMIN window. |
| Mailbox-value tolerance treating anything but `0x00000000`/`0x00000031` as alive | Proposed, never shipped. The literal `0x00000031` appears nowhere in the repository. |
| The `0x00100ce4` LMR-lock clear/re-lock workaround | Appears nowhere in shipping code. Documented as an untested contingency in a 40 GB guide, whose snippet also targets the wrong file (`kernel_gsp_tu102.c`; the LMR write is in `kernel_gsp.c`). |
| Any ELF surgery on `gsp_tu10x.bin` | None. That was the generation-1 approach, replaced on 2026-07-18. |
| PCIe Gen2 patches `0007`/`0008` | Not on `master`. Branch-only. See [PCIe Gen2](pcie-gen2.md). |
| A `kflcnIsRiscvActive` bypass | Not present in any of the six patches. |

Master's patch set is `0001` through `0006` and nothing else.

---

## Related pages

- [How the unlock works](how-it-works.md) for the end-to-end boot story
- [Privilege level masks](privilege-level-masks.md) for the four PLM targets in detail
- [Memory geometry](memory-geometry.md) for CFG1, LMR and the capacity arithmetic
- [Compute throttle](compute-throttle.md) for SS0 and SS1
- [Driver versions](../procedures/driver-versions.md) for why 610.43.0x and what the backports do
- [Register reference](register-reference.md) and the [register index](../appendix/register-index.md)
- [Troubleshooting](../procedures/troubleshooting.md) when the `SEC2_DEBUG` trail stops early
