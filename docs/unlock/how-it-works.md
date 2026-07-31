# How the unlock works

**What this page covers.** The complete mechanism, end to end, in the order it happens at boot,
with the reason each step exists. A competent engineer should be able to read this page and
understand the whole design without opening the source. Register-by-register detail lives in
[Register reference](register-reference.md); the Falcon internals live in
[Falcon and Booter](falcon-and-booter.md); the payload construction lives in
[The ROP chain](rop-chain.md).

The one-sentence version: the driver enlarges the GSP signature buffer to `0x0000f800`, fills it
with a crafted Falcon ROP payload, re-runs NVIDIA's own signed SEC2 Booter Load once per privilege
level mask to gain an arbitrary BAR0 write at Heavy-Secure privilege, opens four PLMs, writes four
plain host registers, restores the real signature, and then lets GSP boot normally with the new
geometry patched into the static info it reports.

---

## Why it has to work this way

Three measured constraints force the whole design. Every one of them was discovered the hard way.

**1. The memory geometry does not survive a reset, but the compute unlock does.** Measured across a
function-level reset:

| Register | Survives FLR? |
|---|---|
| `SS0 0x0082381c` | **Yes** |
| `SS1 0x00823820` | **Yes** |
| `FEAT_OVR_PLM 0x00823804` | **Yes** (always-on island) |
| `CFG1 0x009a0204` | No, reverts to `0x02449000` |
| Per-FBPA CFG1, CSTATUS | No |
| `LMR 0x00100ce0` | No, reverts to the stock value |
| FB-geometry PLMs | No, they re-lock |
| AON LMR shadow `0x001180f0` | No, reverts |
| SEC2 reset-PLM taint | **Cleared** by FLR (`0x8f` becomes `0xff`) |

`FEAT_OVR_PLM` is the only PLM in a 26-register survey marked always-on. This asymmetry is the
single reason the compute unlock shipped weeks before the memory unlock, and the reason the memory
unlock cannot use the old compute recipe of "fire, FLR, then write from the host".

**2. There is no always-on shadow for framebuffer geometry.** Hours were spent sweeping for one,
because SS0 had a findable AON shadow and a published paper described the concept. With all six
FB-geometry PLMs plus `FUSE_SS_PLM` open, CFG1, CSTATUS and LMR still revert on FLR and are never
cold-boot persistent. A dedicated FLR-survival mapping run concluded that no PLM moves FBPA
configuration into the always-on domain. The geometry therefore has to be re-applied on **every**
module load.

**3. A stock driver re-locks what a driverless tool opens.** Writing `0x009A0204`, `0x0082381C` and
`0x00823804` from the host with no driver loaded works, the writes visibly land, and then loading
the stock driver reads `0x00823804` back as `0xffffff8f` with the throttle dividers restored to 5.
That failure is exactly what the in-driver approach exists to solve.

Add one more ordering constraint: **GSP-RM treats the LMR as the master during its own boot**. With
CFG1 set to the 40 GB tier but LMR left at the stock `0x288`, GSP-RM reverted per-FBPA
`CSTATUS_RAMAMOUNT` from `0x800` back to `0x200` during `kgspBootstrap`. So the geometry has to be
in place *before* the real Booter Load launches GSP-RM, not after.

The conclusion the maintainers arrived at: do all of it inside `_kgspBootGspRm`, between the point
where the driver has a signature buffer it controls and the point where the genuine Booter Load
runs.

---

## Step 0: where the unlock sits in the GA100 boot chain

```text
Power on
  └─ GFW / DEVINIT        signed firmware from flash; reads the RAMCFG strap,
                          latches the L2 address map. No RM yet. Always locked.
  └─ CPU-side RM (nvidia.ko)
       ├─ kgspPopulateWprMeta      reads hardware geometry / LMR into WprMeta.fbSize,
       │                           decides WPR2 placement
       ├─ kgspPrepareForBootstrap  runs FWSEC / FRTS (the VBIOS devinit)
       └─ kgspBootstrap            ◀── THE UNLOCK RUNS HERE, inside _kgspBootGspRm
            └─ SEC2 Booter Load    signed Falcon ucode; carves WPR2, launches GSP-RM
  └─ GSP-RM                        closed RISC-V firmware, runs on the GPU
```

Because a cold boot always runs the signed DevInit with the locked CMP strap table, first
enumeration always shows stock capacity, stock Gen1 link and the throttle in place. A plain
`rmmod` / `modprobe` does **not** re-run DevInit (no PERST asserted), which is why the geometry
written by a previous load survives a driver reload but not a reset.

---

## Step 1: the driver loads and detects the device ID

Patch 0001 adds a gate helper to `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`:

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

**Why the shift.** `pGpu->idInfo.PCIDeviceID` packs vendor and device; the device half is the upper
16 bits. Every unlock site in patches 0001 through 0005 tests it the same way. Patch 0006 is the
one exception, comparing the raw `nv->pci_info.device_id` because it runs at PCI probe in
`kernel-open/nvidia/nv.c`, before `OBJGPU` exists.

**Why a runtime gate rather than a build-time one.** Both geometry profiles are compiled into the
same module:

```c
if (devId == 0x20C2) { cfg1Value = 0x02779000U; lmrValue = 0x0000020BU; }
else                 { cfg1Value = 0x02669000U; lmrValue = 0x0000028AU; }
```

`driver/build.sh` still contains an inline Python step that used to rewrite these constants, but on
`master` it detects that both geometries are already present and exits with
`runtime device-id geometry (profile metadata=<label>)` without editing anything. A mis-detected
`--profile` therefore writes wrong metadata but cannot produce wrong geometry.

Any other GA100 SKU, including `10de:20b0`, boots the completely stock path even with the patched
modules installed.

---

## Step 2: the signature buffer is enlarged to `0xf800`

`_kgspCreateSignatureMemdesc` normally allocates `NV_ALIGN_UP(pGspFw->signatureSize, 256)` bytes,
which on this platform is 4096. When the device gate is true it instead allocates
`SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL` (63,488 bytes) in `ADDR_SYSMEM`, 256-byte
aligned. Before overwriting anything the real signature bytes are copied aside into two new
`KernelGsp` fields:

```c
NvU8 *pStockSignatureData;
NvU64 stockSignatureSize;
```

logged as `SEC2_DEBUG: saved stock signature (4096 bytes)`.

**Why 0xf800 exactly.** This is the whole exploit. The bug is an **unbounded DMA in the Booter's
LS-signature verification**: `booterVerifyLsSignatures_TU10X` at IMEM `0x29C4` calls
`booterIssueDma_HAL` with the DMEM destination fixed and the transfer length taken straight from
`sizeOfSignature` in `WprMeta`, with no bounds check. The DMA destination is **DMEM `0x0800`**, and
Falcon DMEM is 64 KB. So:

```text
0x0800 (DMA base) + 0xF800 (length) = 0x10000 (end of DMEM)
```

The payload maps 1:1 onto DMEM `0x0800`..`0xFFFF`, which is everything the Booter uses at runtime,
including its stack, its saved return addresses, and the stack-canary global. Choosing exactly
`0xf800` makes the last payload byte land on the last DMEM byte. (The arithmetic is
self-confirming: the payload writes its fake canary at offset `0x5b40`, and `0x5b40 + 0x800 =
0x6340`, the independently disassembled canary global address.)

**Why this is ROP and not code execution.** Falcon keeps instructions in IMEM and data in DMEM. The
overflow reaches DMEM only. It gives control of the return addresses on the Falcon call stack, so
the attack must be built from gadgets already present in the signed booter image.

**What the buffer does not contain.** An early belief, from the firmware-splice era, was that the
buffer had to begin with the real, valid signature, because zero-padding the whole `0xF800` region
made the stock booter bail with mailbox `0x31`. The shipping payload does not preserve it:
`_kgspSec2PostblTimingFillPayload()` writes `0x000004a7` over every dword from offset 0 upward and
never copies signature bytes back in. The saved stock bytes live only in `pStockSignatureData`
until step 7 puts them back. Mailbox `0x31` is also what a successful payload pass reports, so on
its own it is not a signature-validity verdict.

`_kgspCreateSignatureMemdesc` also tries `os_open_and_read_file()` on
`/lib/firmware/nvidia/ga100/gsp/dmem.bin` and, on failure, logs
`SEC2_DEBUG: <path> not found (0x59), using built-in payload`. Status `0x59` is benign and expected.

---

## Step 3: the payload is written

`_kgspSec2PostblTimingFillPayload(buffer, writeAddr, writeValue)` first fills every dword of the
buffer with `SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7`, then overwrites these slots. The DMEM
column is simply payload offset plus `0x800`:

| Payload offset | DMEM | Value | Role |
|---|---|---|---|
| all | `0x0800`-`0xFFFF` | `0x000004a7` | fill dword |
| `0x1100` | `0x1900` | `0x00000007` | `f100_field_save_restore` gate; leaves the SEC2 reset PLM at `0xff` |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **fake canary written into the guard global** |
| `0xf754` | `0xFF54` | *writeValue* | value argument |
| `0xf758` | `0xFF58` | `0xc0deca7e` | saved-canary slot |
| `0xf75c` | `0xFF5C` | `0x00000cbd` | |
| `0xf76c` | `0xFF6C` | *writeAddr* | address argument |
| `0xf774` | `0xFF74` | `0x00001fbd` | |
| `0xf780` | `0xFF80` | `0x00000000` | |
| `0xf788` | `0xFF88` | `0x000010aa` | **BAR0-master write gadget** |
| `0xf78c` | `0xFF8C` | `0x0000815a` | |
| `0xf790` | `0xFF90` | `0x00008e18` | |
| `0xf794` | `0xFF94` | `0xc0deca7e` | saved-canary slot |
| `0xf798` | `0xFF98` | `0x0000815a` | |
| `0xf79c` | `0xFF9C` | `0x00000000` | |
| `0xf7a0` | `0xFFA0` | `0xc0deca7e` | saved-canary slot |
| `0xf7a4` | `0xFFA4` | `0x00001fbd` | |
| `0xf7b0` | `0xFFB0` | `0x0000ffbc` | |
| `0xf7b8` | `0xFFB8` | `0x0000582d` | |
| `0xf7c4` | `0xFFC4` | `0xc0deca7e` | saved-canary slot |
| `0xf7c8` | `0xFFC8` | `0x00000cbd` | |
| `0xf7d8` | `0xFFD8` | `0x00000003` | |
| `0xf7e0` | `0xFFE0` | `0x00001fbd` | |
| `0xf7f4` | `0xFFF4` | `0x00000ccb` | see the open problem below |
| `0xf7f8` | `0xFFF8` | `0x00007f2f` | outermost slot |

This block is byte-identical in `master` and in all twelve archived branches. The magic
`0xc0deca7e` occurs exactly five times in every copy.

**Why the fake canary.** The booter generates a fresh random stack canary every boot and holds it
in a global at DMEM `0x6340`. Every protected function copies it to the boundary of its stack frame
and re-compares on exit; a mismatch calls `panic()`. Because the value is regenerated per boot it
cannot be guessed offline. The payload does not need to guess it: it overwrites the *global* with
`0xc0deca7e` and writes the same constant into every reconstructed canary slot, so every epilogue
compare passes and the unwind proceeds silently.

**Why `0x000010aa`.** That is `reg_write_indirect`, the booter's own arbitrary BAR0 write routine.
It is byte-for-byte the same code as NVIDIA's `_acrlibBar0RegWrite_TU10X`, and it drives an
indirect, mutex-gated mailbox in Falcon CSB space:

```text
I[0x1c100] = target PRI address
I[0x1c200] = data
I[0x1c000] = 0x800000f2   (write; 0x800000f1 is read)
```

The booter uses this same path for its own work, which is how the primitive was identified. That
one gadget is the entire privilege escalation: it executes at LEVEL2 inside a genuine, signed,
already-verified HS image.

**Why only one register write per fire.** The chain has to reconstruct the booter's stack frames on
its way out, and each write costs a `0x18`-byte frame. Independent implementations put the hard
ceiling between two and six writes per firing, and the driverless engine refuses to build a payload
outside one to two writes. The shipping driver does **one** write per fire and simply re-fires,
which is simpler and has no budget risk.

---

## Step 4: Booter Load is executed to gain the write primitive

For each pass the driver calls:

```c
kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
    memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
```

`kgspExecuteBooterLoad_TU102` performs a `kflcnReset(SEC2)` before every run, so SEC2 accumulates
no state across passes. The Booter loads, passes the RSA-3072 boot ROM check on its own image
(which is untouched and genuine), decrypts itself into HS mode, begins verifying the LS signature,
DMAs `0xf800` bytes into DMEM, and unwinds through the injected return addresses instead of its own.

> [!WARNING]
> **The reported status is always a failure and that is expected**
>
> Every payload pass logs
> `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` and
> `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`, and the register writes
> still land. The seccode leaves an error code in mailbox0 after every run, and `mailbox0 != 0`
> makes the HAL return `NV_ERR_GENERIC` (`0xffff`). **Register readback is the only valid success
> criterion**, and it is exactly the criterion the shipping loop uses. Do not read
> `status=0xffff` as a problem.

A Booter pass costs about **180 ms**.

---

## Step 5: the four PLMs are opened in sequence

A privilege level mask is a per-register-block gate: it decides which privilege levels may read or
write the registers it covers. At PL0 (an ordinary host BAR0 write from the kernel driver) the
target registers are simply not writable, and, importantly, **the failure is silent**. An early
pipeline logged `Write failed - wrote 0x2779000, read 0x2449000` three times with no error
signalled anywhere.

The shipping `plmTable[]` has exactly four entries, opened in this order:

| Index | Name | Address | Value written | Why it is needed |
|---|---|---|---|---|
| 0 | WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | Gates the WPR configuration block the booter validates and the driver manipulates |
| 1 | FBPA | `0x009a0148` | `0xffffffff` | Gates the FBPA aperture, including `CFG1 0x009a0204`. Also the built-in fallback payload target |
| 2 | WPR | `0x001fa7c4` | `0xffffffff` | Gates the WPR region registers |
| 3 | FEAT | `0x00823804` | `0xffffffff` | `FEAT_OVR_PLM`. Gates the feature-override block, i.e. SS0 and SS1 |

> [!WARNING]
> **WPR_CFG opens to `0xfffff0ff`, not `0xffffffff`**
>
> Both the distribution README and `docs/ARCHITECTURE.md` say every PLM should read `0xffffffff`.
> The code writes and verifies `0xfffff0ff` for entry 0. Treat `0xfffff0ff` as canonical: it is
> what the shipping loop both writes and checks against.

Each entry gets **up to two attempts**. The attempt loop is:

```text
for each plmTable entry:
    for attempt in 1..2:
        GPU_REG_WR32(0x001fa824, wpr2Lo)      # re-arm WPR2 low
        GPU_REG_WR32(0x001fa828, wpr2Hi)      # re-arm WPR2 high
        kgspSec2PostblTimingRefillPayload(addr, value)
        kgspExecuteBooterLoad_HAL(...)         # returns 0xffff; ignored
        if GPU_REG_RD32(addr) == value: break  # readback is the verdict
restore wpr2Lo / wpr2Hi one final time
```

**Why WPR2 has to be re-armed before every single attempt.** WPR2 is controlled by ADDR_LO
`0x001fa824` and ADDR_HI `0x001fa828`. `kgspIsWpr2Up()` returns false when HI is zero. Each Booter
Load pass carves WPR2 and leaves it up; a second Booter Load would then abort with "WPR2 already
up". Saving the pre-loop values and rewriting them before each attempt puts the registers back into
the state the driver and the booter both expect. The same problem is why patch 0001 downgrades the
fatal path in `_kgspBootGspRm`:

```c
/* stock */
NV_PRINTF(LEVEL_ERROR, "unexpected WPR2 already up, cannot proceed with booting GSP\n");
return NV_ERR_INVALID_STATE;

/* patched */
NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n");
```

Execution then falls straight through to `kgspPopulateWprMeta_HAL`.

**Why `FEAT_OVR_PLM` can be opened at all.** The gate chain is
`FUSE_QUADRO_WR_SEC` (`0x0082038c`) = 1 permits `0x00823804` to be opened; opening `0x00823804`
permits PL0 host writes to SS0/SS1; the feature-override registers outrank the fuses. And the whole
chain exists only because the master kill fuse `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` at `0x008203f0`
reads `0x00000000` on the 170HX. Had it been blown, no software path would exist at any privilege
level. The PLM itself is not PL0-writable: it must be opened from a Falcon in HS mode, "if this was
not so, any Nvidia card could be unlocked without any exploit".

The shipping tree writes **nothing** to `0x008200fc` (`FUSE_SS_PLM`, called `OPT_PLM` in the branch
source). An earlier consolidated recipe called for opening it; it was already observed reading
`0xffffffff` on stock cards, so opening it was unnecessary. The Gen2-family branches do add it, as
one of five extra entries taking the table from four to nine.

---

## Step 6: the compute and geometry registers are written

With the PLMs open, the escalation is over. Four plain host writes land the entire unlock, with no
exploit involved:

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* FBPA CFG1 broadcast */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* MMU local memory range */
```

followed by a readback logged as
`SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)`.

### SS0 and SS1: the compute unthrottle

`0x0082381c` is `NV_FUSE_FEATURE_OVERRIDE_SM_SPEED_SELECT`, holding eight 4-bit fields for
IMLA0-3, FMLA16, FMLA32, FFMA and DP. `0x00823820` is `..._SM_SPEED_SELECT_1`, holding the ninth
field for IMLA4. Each nibble reads as `[enable | 3-bit speed]`: `0x8` sets bit 3 (override enable)
with the speed field at 0 (full rate). So `0x88888888` means "override enabled, full rate" on all
eight SS0 units and `0x00000008` does the same for IMLA4 alone.

**Why both.** Writing only one is not enough; this was emphasised independently in-channel and is
reflected in every shipping write pair.

**Why this works while the fuses stay blown.** The throttle is OTP-fused per arithmetic unit:
`FUSE_SS_FFMA`, `FUSE_SS_FMLA16/32` and `FUSE_SS_IMLA0-4` all read `0x5` (divide-by-32) on the
170HX and `0x0` on every A100, A10, A5000, A6000 and Drive A100 probed. After a successful unlock
those fuse shadows **still read `0x5`**. The effective rate is arbitrated from a writable override
that supersedes the fuse, not from the fuse directly. The confirmation is `FEAT_READOUT_1` at
`0x00823818`, the read-only effective speed select for all nine units, dropping from `0x016db6ed`
to `0x00000000`.

### CFG1 and LMR: the geometry

`0x009a0204` is the FBPA CFG1 broadcast register. Its tier byte at bits [23:16] encodes addressing
depth per memory partition: `0x44` stock (12 row bits, 512 MiB per FBPA), `0x66` (14 row bits,
2048 MiB), `0x77` (15 row bits, 4096 MiB). Total capacity is addressing depth times the
fuse-determined active-FBPA count, which CFG1 does not touch. Both shipping values are literally the
stock CFG1 words of real A100 parts: `0x02779000` is what an A100 PCIe 80 GB reads, `0x02669000` is
what an A100 PCIe 40 GB and SXM4 40 GB read. The unlock restores genuine A100 geometry rather than
inventing constants.

`0x00100ce0` is the MMU local memory range. It encodes total framebuffer size as:

```text
size_MiB = MAG[9:4] << SCALE[3:0]
```

| Value | Decode | Meaning |
|---|---|---|
| `0x00000208` | 32 << 8 | 8192 MiB (stock, 8 GB card) |
| `0x00000288` | 40 << 8 | 10240 MiB (stock, 10 GB card) |
| `0x0000020B` | 32 << 11 | 65536 MiB (8 GB card unlocked) |
| `0x0000028A` | 40 << 10 | 40960 MiB (10 GB card unlocked) |
| `0x0000028B` | 40 << 11 | 81920 MiB (the 80 GB attempt) |

MAG is constant per SKU and equals twice the active-FBPA count. SCALE is what the unlock changes.

> [!WARNING]
> **`0x40A` and `0x50A` are refuted, not observed**
>
> Both circulated as candidate encodings. `(0x40A >> 4) & 0x3F = 0` and
> `(0x50A >> 4) & 0x3F = 0x10`, so neither decodes under a 6-bit MAG field, and a 2026-07-11
> attempt at `0x40A` on a 10 GB card moved neither register. The exact width of the `LOWER_MAG`
> field (6 bits at [9:4] versus 7 at [10:4]) has never been read out of `dev_fb.h` and remains
> the last open detail here.

**Why the LMR is a hard prerequisite, not an optimisation.** A controlled three-way comparison on
hardware: no memory writes gives CPU-RM failure `0x24` at `kbusVerifyBar2`; a 40 GB CFG1 strap with
the stock 10 GB LMR still gives `0x24`; strap plus matched LMR reaches `0x25` (StateLoad). There is
no configuration that reaches StateLoad without the LMR. And per the GSP-RM behaviour noted above,
an incoherent CFG1/LMR pair gets reverted during `kgspBootstrap`.

**Why one broadcast write is enough.** `0x009A0000`-`0x009A3FFF` is the broadcast FBPA aperture;
the 24 per-instance mirrors sit at `0x00900204 + n*0x4000`. The shipping driver writes **no**
per-FBPA register and produces a working card, because devinit runs afterwards and propagates the
value. In a driverless runtime context with no devinit, the broadcast alone does not move CSTATUS
and all per-FBPA instances must be written by hand. Whether the propagation is a PRI priv-ring
hardware mechanism has never been directly instrumented.

---

## Step 7: the stock signature is rebuilt

`kgspSec2PostblTimingRebuildStockSignature()` frees and destroys the `0xf800` payload memdesc,
allocates a new one of `NV_ALIGN_UP(stockSignatureSize, 256)` with
`MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`, copies `pStockSignatureData` back into it, and
re-points `pWprMeta->sysmemAddrOfSignature` and `pWprMeta->sizeOfSignature` at the new descriptor.
If it fails, `_kgspBootGspRm` returns that status and the boot aborts.

**Why.** The next Booter Load is the real one: the one that must carve WPR2 correctly, pass its own
signature verification, and launch GSP-RM. If the oversized payload buffer were still attached, that
run would overflow DMEM again and GSP would never start. Restoring the genuine 4096-byte signature
and its true length hands the Booter exactly what a stock driver would.

**Why the geometry change does not invalidate the signature.** The stock AES-MAC covers the static
GSP firmware image at rest, not runtime WPR metadata and not hardware geometry. WPR metadata is
computed by the driver at runtime. An earlier claim to the contrary was explicitly retracted, and
the shipping save / inject / restore flow is the empirical proof.

This step also explains a real-world trap: if the machine previously ran the firmware-patching
predecessor, `gsp_tu10x.bin` on disk must be restored to stock first. Otherwise the driver saves the
*exploit payload* as the "stock" signature at step 2, and the clean GSP-RM boot then DMAs the wrong
ROP chain. The success line to look for is `SEC2_DEBUG: saved stock signature (4096 bytes)`.

---

## Step 8: WPR metadata is recomputed

`kgspPopulateWprMeta_HAL()` is called a **second** time, after the geometry writes and the signature
rebuild. The first call ran in the stock position and computed WPR2 placement from the old, small
framebuffer. The second call recomputes it against the geometry that is now live, logging:

```text
SEC2_DEBUG: WPR meta updated fbSize=0x0000001000000000 wprStart=... wprEnd=... heapOffset=... heapSize=...
```

Without it, the driver's WPR2 placement and the booter's carve would disagree, which is exactly the
class of failure (`0x55`, `0x65`) that consumed days of debugging before the design settled.

---

## Step 9: GSP boots normally

The genuine Booter Load now runs unmodified. Patch 0002 adds the confirming readback:

```text
SEC2_DEBUG: normal BooterLoad status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=0xffffffff SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

That second line, printed only when the status is `NV_OK`, is the definitive proof the unlock
survived the real GSP boot. It is also the single line to ask for when triaging a report. Patch 0002
additionally converts four fatal assertions in `kgspBootstrap_TU102` into logged status checks, so a
transient failure produces diagnostics rather than a dead adapter.

---

## Step 10: GSP static info is patched so the new capacity is advertised

Opening the geometry registers changes what the hardware decodes. It does not change what GSP-RM
*reports* back to the driver. Patch 0001 therefore rewrites the static config info after
`kgspInitRm` receives it, gated on the same two device IDs:

- `pGSCI->fb_length` is set to `targetFbBytes`: `0x0000001000000000` (64 GiB) for `0x20C2`,
  `0x0000000A00000000` (40 GiB) for `0x2082`.
- If the last FB region's `limit` is below `targetFbBytes - 1`, that region is widened:
  `limit = targetFbBytes - 1`, `reserved = limit - base + 1`, `supportCompressed = NV_TRUE`,
  `supportISO = NV_TRUE`, `performance = 20`.

Logged as `SEC2_DEBUG: static-info BEFORE` / `AFTER`. Without this the driver would not report the
widened size at all.

---

## Step 11: making the extra capacity actually allocatable

Four more patches close the gap between "the region exists" and "CUDA can use it".

**Patch 0003, late PMA extension.** `memmgrSec2DebugLateExtendHighPmaRegion()` runs from a hook in
`osinit.c` after heap creation. It picks the highest FB region that is `bRsvdRegion &&
!bInternalHeap && limit >= 8 GiB`, registers `[max(base, 8 GiB), limit]` with `pmaRegisterRegion`,
and then either splits the candidate into a new public `FB_REGION_DESCRIPTOR` from 8 GiB upward or
un-reserves it in place, followed by `memmgrRegenerateFbRegionPriority`. It returns
`NV_ERR_INSUFFICIENT_RESOURCES` if a split is needed and `numFBRegions >= MAX_FB_REGIONS`. Logged as
`SEC2_DEBUG: late PMA extension status=0x0`.

Note that `stockFbBytes = 0x200000000ULL` (8 GiB) is hardcoded as the split point **for both
profiles**, including the 10 GB card whose true stock size is `0x280000000`. The same constant is
declared and never used in patch 0001.

**Patch 0004, PRAMIN clamp.** A single ten-line hunk in `kern_bus_gm107.c`. After the stock
`offsetBar0 = (Ram.fbAddrSpaceSizeMb << 20) - DRF_SIZE(NV_PRAMIN);` it adds: if the device ID
matches and `Ram.fbAddrSpaceSizeMb > 0x2000`, recompute as
`(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)`. **Why:** the PRAMIN window offset is derived from the
framebuffer size. Computed from 65536 MB it lands outside reachable BAR0 space. Clamping it back to
the stock 8 GiB address space keeps the aperture usable.

**Patch 0005, copy-engine scrub workarounds.** Two hunks. In `mem_mgr_tu102.c` the scrubber PTE-kind
helper returns `NV_MMU_PTE_KIND_GENERIC_MEMORY` early for the two device IDs instead of
`NV_MMU_PTE_KIND_GENERIC_MEMORY_COMPRESSIBLE_DISABLE_PLC`. In `mem_scrub.c` the
`memmgrUseVasForCeMemoryOps()` guard gains a device-ID exclusion so
`DRF_DEF(0050, _CEUTILS_FLAGS, _VIRTUAL_MODE, _TRUE)` is never set and the scrubber runs in physical
mode.

**Patch 0006, persistent software state.** Nine lines in `kernel-open/nvidia/nv.c` at PCI probe
setting `nv->flags |= NV_FLAG_PERSISTENT_SW_STATE` for either device ID. The flag already exists for
SR-IOV virtual functions and is repurposed so RM does not tear down software state when the last
client closes. This is effectively built-in persistence mode, and it is why the shipping design
needs no systemd daemon. (`remove.sh` still cleans up a legacy `cmpunlocker.service` and a
`watchdog.py` that the current installer never creates: vestiges of the abandoned watchdog design.)

---

## The whole sequence on a clock

Timeline from a complete 8 GB dmesg capture, driver load to usable card:

| Time | Event |
|---|---|
| 11.13 s | Stock signature saved |
| 11.32 s | PLM[0] WPR_CFG opened |
| 11.50 s | PLM[1] FBPA opened |
| 11.68 s | PLM[2] WPR opened |
| 11.86 s | PLM[3] FEAT opened |
| 11.86 s | POST-WRITE (SS0, SS1, CFG1, LMR) and WPR-meta update |
| 12.07 s | Normal BooterLoad `status=0x0` |
| 12.07 s | POST-BooterLoad verify: `PLM=0xffffffff SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b` |
| 12.64 s | Heap creation |
| 12.72 s | Late PMA extension `status=0x0` |

About one second of wall clock, four Booter passes at roughly 180 ms each.

Everything the unlock does is visible with:

```bash
sudo dmesg | grep SEC2_DEBUG
```

The `SEC2_DEBUG_PRI_*` register names, the `kgspSec2PostblTiming*` function names and the
`SEC2_DEBUG:` prefix appear nowhere in the stock 610.43.03 source. "PostBL Timing" is an invented
feature name, read by two independent reviews as deliberate camouflage of exploit code as a
manufacturing or debug feature.

---

## What survives afterwards

| Event | Compute unlock | Memory geometry |
|---|---|---|
| Driver unload / reload, no reset | Survives | **Survives** (registers still read the unlocked values) |
| FLR (`echo 1 > /sys/bus/pci/devices/<bdf>/reset`) | Survives | **Lost** |
| Power cycle / cold boot | Lost | Lost |

Because nothing is persistent across a cold boot, the whole sequence re-runs on every module load.
That is not a limitation of the implementation; it is the direct consequence of there being no
always-on shadow for framebuffer geometry.

---

## Where PCIe Gen2 slots into this narrative

> [!WARNING]
> **Experimental, branch only**
>
> `0007-pcie-gen2.patch` injects its entire register block into `kernel_gsp.c` at
> `@@ -4942,6 +4942,260 @@`, immediately after the `devId` print and immediately **before** the
> call to `kgspSec2PostblTimingRebuildStockSignature()`. It therefore runs inside exactly the
> window described in steps 5 and 6, while the PLMs are still open and the crafted signature
> payload still provides the arbitrary BAR0 write primitive. It pushes a 23-entry `xp3gTable`
> plus two further registers through the Booter (25 Booter-routed writes), then does plain host
> BAR0 writes, then leaves the actual link retrain to patch 0008 or to userspace. Full detail on
> [PCIe Gen2](pcie-gen2.md).

---

## Open problems in the mechanism itself

> [!NOTE]
> **Open problem**
>
> **Does the chain actually execute `0x0ccb`?** A hard constraint was recorded that no ROP exit
> path may route through `regtable_rw_indexed (0x0ccb)`, because the `0xF800` payload linearly
> smashes the descriptor tables it indexes at DMEM `0x2383` and `0x8e08`, and a 2026-07-06
> isolation matrix showed every write-carrying rejoin chain dying there. Yet the shipping payload
> places `0x00000ccb` at DMEM `0xFFF4` and works. The next step is to single-step or emulate the
> unwind from `0xFF54` and record whether `0xFFF4` is ever popped into PC or is only a
> live-through saved slot in the outermost frame.

> [!NOTE]
> **Open problem**
>
> **Does `0x00000007` at payload offset `0x1100` do anything beyond the reset PLM?** Its main
> role is settled: DMEM `0x1900` is the `f100_field_save_restore` slot reached from IMEM
> `0x1d3b`, and the `0x7` is what makes the exit through `secure_teardown` leave the SEC2 reset
> PLM at `0xff` instead of the usual `0x8f` taint. Whether it has any further effect has never
> been established.

> [!NOTE]
> **Open problem**
>
> **Is `0x008200FC` writable, and what does it read on a cold card?** One sweep reported
> `0xffffffff`, another `0x000003FF`. The nine-PLM Gen2 branch attempt returned `status=0xffff`
> with no readback recorded.

More at [Open questions](../frontier/open-questions.md) and the
[Status board](../frontier/status-board.md). For what was tried and failed on the way here, see
[Dead ends](../history/dead-ends.md).
