# Verifying the unlock

**What this page covers.** How to prove, with evidence rather than hope, that an unlock actually
landed: what `nvidia-smi` should say for each SKU, how to read the `SEC2_DEBUG` kernel log lines
one by one, what the installed metadata files do and do not mean, how the branch-only `verify.sh`
works, how to confirm the extra memory is *real* rather than aliased, and how to confirm the
**compute** unlock, which is a completely separate result from the memory capacity and needs its
own measurement.

The headline: `nvidia-smi` reporting **65536 MiB** on an 8 GB card or **40960 MiB** on a 10 GB
card proves the memory geometry write landed. It proves nothing about compute. Compute is
unlocked by two register writes (SS0 `0x0082381c` = `0x88888888`, SS1 `0x00823820` = `0x00000008`)
that are invisible to `nvidia-smi`, and the only way to confirm them is to read them back from the
`SEC2_DEBUG` log or to benchmark throughput.

---

## The three layers, and the evidence for each

| Layer | What it is | Primary evidence | Secondary evidence |
|---|---|---|---|
| Memory **capacity** | CFG1 + LMR geometry, plus the GSP `fb_length` and PMA rewrite | `nvidia-smi` total memory | `SEC2_DEBUG: POST-WRITE ... CFG1=... LMR=...` |
| Memory **reality** | that the reported capacity is backed by distinct physical DRAM, not an alias | `check_fold.py` reporting `REAL, NO FOLD` | a large `gpu_burn` or `cuda_memtest` run with zero errors |
| Compute **throughput** | SS0/SS1 written after the FEAT PLM is opened | `SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008` | an FP32/OpenCL benchmark compared against the locked baseline |

A card can pass one and fail another. The compute unlock survives a function-level reset while
the memory geometry does not, which is exactly why compute shipped before memory.

---

## `nvidia-smi` expectations per SKU

| Quantity | 8 GB card (`10de:20c2`) | 10 GB card (`10de:2082`) |
|---|---|---|
| Stock `memory.total` | 8192 MiB | 10240 MiB |
| Unlocked `memory.total` | **65536 MiB** | **40960 MiB** |
| CFG1 `0x009a0204` written | `0x02779000` | `0x02669000` |
| LMR `0x00100ce0` written | `0x0000020B` | `0x0000028A` |
| GSP `fb_length` written | `0x0000001000000000` (64 GiB) | `0x0000000A00000000` (40 GiB) |
| Reported product name | `NVIDIA Graphics Device` on stock drivers, because the PCI ID table carries no marketing name | same |
| Compute capability | 8.0 | 8.0 |
| SM count | 70 (4480 CUDA cores) | 70 |
| PCIe link (stock) | gen 1, max 1, width 4 | gen 1, max 1, width 4 |

```bash
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,clocks.max.sm,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current --format=csv
```

Reading the result:

- **8192 MiB on an 8 GB card means the unlock did not fire.** That is the failure triage line
  from the leaked distribution's own README and it is correct: the PLM open, and therefore
  everything downstream of it, did not happen.
- **Anything between the stock size and the target size is not a partial unlock.** The geometry
  is a fixed CFG1 + LMR pair chosen from the PCI device ID; it either landed or it did not.

!!! danger "81920 MiB is not a success"
    A 10 GB card reporting ~81920 MiB, with CUDA seeing 85,545,582,592 bytes (79.67 GiB), is
    running the experimental 80 GB
    tier, not the shipping 40 GB profile. `cudaMalloc` of 77 GiB succeeds, but kernels touching
    more than roughly 40 GB cause fatal GPU loss, independent of power limit. Reported Xid codes
    include Xid 31 (described as harmless) and Xid 154 after CUDA memory tests; the dominant
    reported symptom is hangs. Xid 31 alone was suggested by a bystander and was not corroborated
    as *the* signature by the operator with the failing card. The
    80 GB configuration was attempted and abandoned. See [80 GB](../frontier/80gb.md). Every
    document that mentions it records it as unstable; the `80` branch README's "Working" row is a
    documentation defect.

!!! note "`clocks.max.sm = 1935 MHz` is a reported field, not an achievable clock"
    `install.sh` suggests checking `clocks.max.sm` as step 4 of verification, and unlocked cards
    do report 1935 MHz. Treat that number as **low confidence** and not as an operating clock:
    the VBIOS table maximum graphics clock is 1695 MHz and the practical silicon ceiling is around
    1604-1614 MHz at a +350 offset. Every sustained measurement sits at **1410 MHz** nominal, or
    **1470 MHz** at `-pl 300`. See [Tuning](../operations/tuning.md).

---

## The `SEC2_DEBUG` dmesg trail

Every unlock action logs with a `SEC2_DEBUG:` prefix. That prefix, along with the
`SEC2_DEBUG_PRI_*` register names and the `kgspSec2PostblTiming*` function names, appears nowhere
in the stock 610.43.03 source; "PostBL Timing" is an invented, NVIDIA-plausible feature name. The
practical consequence is a single grep:

```bash
sudo dmesg | grep SEC2_DEBUG
sudo dmesg | grep -c SEC2_DEBUG      # the count varies by build and card count, see below
```

!!! note "The line count is not a pass/fail test"
    Every archived count is different, and none of them is a fingerprint. The single archived
    single-card 8 GB capture contains **29** lines. The single archived two-card Gen2-branch
    `610.43.03` boot log contains **134**. The `pcielink.sh` reporting tool printed
    `SEC2_DEBUG lines=152` on two separate two-card Gen2 rigs (a HiveOS host and an Unraid host),
    and 34 (Gen1 build) / 80 (Gen2 build) are also on record. Do not read a mismatch as a failed
    install. The register readback lines below are the criterion.

Lines are emitted roughly in this order on a healthy boot.

| Log line (format) | Stage | How to read it |
|---|---|---|
| `SEC2_DEBUG: saved stock signature (4096 bytes)` | before the payload overwrites the signature buffer | If this is missing or the size is wrong, the GSP firmware on disk may still be patched from the firmware-era predecessor |
| `SEC2_DEBUG: loaded 63488 bytes from /lib/firmware/nvidia/ga100/gsp/dmem.bin` | payload source | Only if you deliberately placed an override payload |
| `SEC2_DEBUG: <path> not found (0x59), using built-in payload` | payload source | **Normal.** `0x59` is benign; the built-in payload targeting `0x009a0148 = 0xffffffff` is used |
| `SEC2_DEBUG: WPR meta fbSize=... wprEnd=... heapSize=...` | first `kgspPopulateWprMeta_HAL` | Pre-unlock geometry, so `fbSize` here still reflects the stock size |
| per-PLM attempt lines carrying `status=0xffff` | the four-entry PLM loop | **Expected on every payload pass.** The Booter always leaves an error in mailbox0 after a payload run |
| `SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff` | PLM loop result | The definitive PLM verdict. See the table below |
| `FAILED to open %s after 2 attempts` | PLM loop failure | Each PLM gets at most two attempts; this names the one that did not open |
| `SEC2_DEBUG: POST-WRITE SS0=... SS1=... CFG1=... LMR=... (devId=0x%x)` | host register writes | **The single most useful line on this page.** Compare all four values against the SKU table above |
| `SEC2_DEBUG: WPR meta updated fbSize=... wprStart=... wprEnd=... heapOffset=... heapSize=...` | second `kgspPopulateWprMeta_HAL` | Now agrees with the enlarged geometry |
| `SEC2_DEBUG: normal BooterLoad status=0x%x` | the real bootstrap Booter run | This one should be `NV_OK`, unlike the payload passes |
| `SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=... SS1=... CFG1=... LMR=...` | post-bootstrap readback | Printed only when the normal BooterLoad returned `NV_OK`. **This is the proof the unlock survived the real GSP boot** |
| `SEC2_DEBUG: static-info BEFORE` / `AFTER` | GSP static config rewrite | `fb_length` and the last FB region widened |
| `SEC2_DEBUG_HEAP: fbAddrSpace=... mapRam=... fbTotal=... fbUsable=... heapTotal=... regionBytes=... publicBytes=... numRegions=...` | after heap creation | Diagnostic for the PMA work |
| `SEC2_DEBUG: late PMA extension status=0x%x` | stage two of the memory spoof | `0x0` is success. A non-zero status here means the extra memory was never registered with the allocator even though the geometry write landed |
| `SEC2_DEBUG: rebuild stock signature failed: 0x%x` | failure only | The whole init aborts if the stock signature cannot be restored |

### Reading the PLM line correctly

| PLM | Address | Expected value | Note |
|---|---|---|---|
| WPR_CFG | `0x001fa7cc` | `0xfffff0ff` | **Not** `0xffffffff`. This is the value the code writes *and* the value it checks |
| FBPA | `0x009a0148` | `0xffffffff` | Also the built-in payload's default target |
| WPR | `0x001fa7c4` | `0xffffffff` | |
| FEAT | `0x00823804` | `0xffffffff` | Stock is `0xffffff8f`; always-on, survives a function-level reset |

!!! note "Superseded: two documentation defects to ignore"
    The `docs` branch is not authoritative and will make you misdiagnose a healthy card:

    - `docs/DEBUGGING.md` line 15 says "All the PLMs must show `0xffffffff`." Wrong for WPR_CFG.
      Master's `README.md` carries a milder version of the same imprecision
      ("Expected: PLMs opening to 0xffffffff").
    - `docs/ARCHITECTURE.md` prints expected `SEC2_DEBUG: SS0 = 0xffffffff` /
      `SS1 = 0xffffffff`. The code writes `0x88888888` and `0x00000008`, and
      `common/constants.yaml` agrees. Anyone validating an unlock against those strings will
      wrongly conclude it failed.

    The same document also invents acronym expansions ("Program Logic Modules", "Suspension
    State", "Power Management Array") that appear nowhere in the code. Do not propagate them; see
    the [glossary](../start/glossary.md).

### When the log is missing

Ring buffers rotate. A missing `SEC2_DEBUG` trail on a card whose memory is correct is a warning,
not a failure, and `verify.sh` treats it that way. To force a fresh trail, cold boot and grep
immediately, or raise the kernel log buffer size.

---

## The installed metadata files

```bash
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile      # 8gb | 10gb | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry   # 64GB | 40GB | mixed
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version    # e.g. 610.43.03
cat /lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory     # branch-only, see multi-gpu.md
```

These are single-line files written by `build.sh`. **Nothing in the kernel modules reads any of
them.** They record what the installer *believed*, not what the driver *did*. A `card_profile` of
`10gb` on a machine whose 8 GB card came up at 65536 MiB is a metadata bug, not an unlock bug,
because geometry is chosen at GSP boot from the PCI device ID. The only file the patched kernel
reads at boot is the optional `/lib/firmware/nvidia/ga100/gsp/dmem.bin`.

Two further useful checks:

```bash
cat /proc/driver/nvidia/version        # should NOT say dvs-builder if the patched module is live
cat /sys/module/nvidia/srcversion      # compare with:
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

A `srcversion` mismatch means the running module is the stock one. That is the same failure class
as the multi-GPU depmod ambiguity described in [Multi-GPU](multi-gpu.md).

---

## `verify.sh`

!!! warning "Experimental: branch-only script"
    `verify.sh` does **not** exist on `master`. It ships on the `multiple-cards`, `Gen2`, `far`
    and `deced` branches only. There is no `tools/` directory and no test suite on `master`
    either.

`verify.sh` is a multi-GPU post-install checker. It requires `nvidia-smi`, caches
`nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits`, then enumerates
GPUs by preferring the installed `gpu_inventory` file and otherwise falling back to
`lspci -nn | grep -iE '10de:20c2|10de:2082'`.

Per GPU it classifies the reported size:

| Profile | `is_unlocked_memory` | `is_stock_memory` |
|---|---|---|
| `8gb` | `>= 60000` MiB | `7680`-`8704` MiB |
| `10gb` | `35000`-`59999` MiB | `9728`-`10752` MiB |

and prints one of four statuses:

| Status | Meaning |
|---|---|
| `OK` | in the unlocked window |
| `STOCK` | still at the locked size |
| `MISSING` | the BDF is not present in `nvidia-smi` output at all |
| `UNEXPECTED` | a size that is neither stock nor unlocked for that profile |

It then greps `dmesg` for `SEC2_DEBUG`, prints the last eight matching lines as a sample, prints
the installed `card_profile` and `unlock_geometry`, and finishes with either

```text
✓ All 4 unlockable GPU(s) report unlocked memory
```

exiting 0, or

```text
✗ 1 GPU(s) failed unlock verification. Cold reboot if modules were just installed.
```

exiting non-zero.

Two known gaps:

- **`verify.sh` never checks PCIe Gen2**, not even on the Gen2 branch lineage. Grepping
  `Gen2/verify.sh`, `far/verify.sh` and `deced/verify.sh` for "pcie" returns zero hits. Link
  verification is entirely manual; see [PCIe Gen2](../unlock/pcie-gen2.md).
- **`verify.sh` never checks compute.** Memory size is the only pass criterion.

---

## Confirming the memory is real, not aliased

Reported capacity and usable capacity are different claims. The failure mode to rule out is a
**fold**: the address space wrapping so that high addresses alias low ones.

`check_fold.py` is the authoritative test. It is not in the repository: like `cuda_dbg.py` it was
distributed out-of-band as a gist or channel attachment, so obtain it separately rather than
expecting a clone to provide it. It allocates all free VRAM minus 2 GiB, writes each
64 KB page's own index with a PTX `sm_80` `fill` kernel, then reads every page back with a `chk`
kernel, using `st.global.wt.u32` stores and `ld.global.cv.u32` loads to defeat caching. It must
be dense, because the fold aliases at a channel-**interleave** offset: `LOW[0]` maps to
`(40 GiB + interleave)`, not `(40 GiB + 0)`, so a sparse probe gives false negatives.

| Output | Exit code | Meaning |
|---|---|---|
| `REAL, NO FOLD` | 0 | the capacity is backed by distinct physical DRAM |
| `FOLD/mismatch @<pageindex>` | 1 | aliasing detected at that page |
| error | 2 | harness problem |

Lighter and heavier alternatives:

- `cuda_dbg.py` is a quick alias test: `cuMemGetInfo_v2`, then `cuMemAlloc_v2` tried at 64, 60,
  56, 52, 48, 44, 42 GiB until one succeeds, then `cuMemsetD32_v2` writes `0xAAAA0000` at offset 0
  and `0xBBBB0000` at 40 GiB and reads offset 0 back. Reading `0xBBBB0000` at offset 0 means the
  space aliases. It leaks its allocation, so run it once per driver load.
- `cuda_memtest` 1.2.3 is the community validator the maintainer recommends; it exits on the
  first error. On the 80 GB profile it prints `Attached to device 0 successfully.` and then hangs
  indefinitely unless the allocation is capped at 39 GB. That hang is the primary disproof of
  the `80` branch README's "Working" claim, not a weak signal.
- The leaked distribution's README suggests `./gpu_burn -m 63500 -d 30` on a 64 GB card,
  expecting zero memory errors.

!!! warning "Fold harnesses have produced false positives"
    An early fold/alias harness reported *native, un-unlocked* memory as folding: a control run
    after a reset to a consistent native state (10240 MiB, driver 610.43.03, CFG1 `0x02449000`)
    allocated 9 GiB of genuinely native memory and reported "4608 chunks, 4608 corrupt/aliased"
    across five passes, which is impossible. That retroactively invalidated a body of earlier
    fold-at-40 GB conclusions. Trust `check_fold.py`'s dense method, and treat any fold result
    from an ad-hoc script as unproven until a native control run comes back clean.

---

## Confirming compute throughput, as distinct from capacity

The compute unlock is the pair of writes to SS0 and SS1 that follow the FEAT PLM open. They are
`GPU_REG_WR32` calls from the host CPU, with no exploit involved once the PLM is open, and they
are **unconditional for both SKUs**.

| Register | Address | Locked | Unlocked |
|---|---|---|---|
| SS0 (`SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED`) | `0x0082381c` | e.g. `0x53540175` | `0x88888888` |
| SS1 (`..._SM_SPEED_1`) | `0x00823820` | | `0x00000008` |
| FEAT_OVR_PLM | `0x00823804` | `0xffffff8f` | `0xffffffff` |

### Step 1: read them back

The `POST-WRITE` and `POST-BooterLoad verify` lines both carry SS0 and SS1. If they read
`0x88888888` and `0x00000008` after the normal BooterLoad, compute is unlocked for this boot.
This is the cheapest and most direct confirmation, and it works even on a card whose memory
unlock failed.

### Step 2: measure throughput

Register readback proves the write landed; it does not prove the silicon behaves differently.
Reference figures for a healthy unlocked card:

| Quantity | Value | Notes |
|---|---|---|
| SM count | 70 | measured with a PTX `%smid` dumper, not merely reported |
| Theoretical FP32 | 12.63 TFLOPS | 4480 cores x 2 x 1410 MHz |
| Sustained SM clock | 1410 MHz, 1470 MHz at `-pl 300` | base 1140 MHz |
| TDP / max software power limit | 250 W / 300 W | 300 W only on cards carrying the NVIDIA OC mining VBIOS; on the stock CMP VBIOS `nvidia-smi -pl` ranges 100-250 W |
| HBM bandwidth, measured | a **range**, 1305.86-1600 GB/s | depends on tool and access pattern; no single canonical figure |
| HBM theoretical peak | 1555.2 GB/s (1448.4 GiB/s) | 1215 MHz DDR x 5120-bit |

Use a compute benchmark, not a memory one: the project's own proof-of-concept screenshots use
[OpenCL-Benchmark](https://github.com/ProjectPhysX/OpenCL-Benchmark), and `clpeak` and `mixbench`
are also in use. Compare against the same benchmark on the same card before the unlock, on the
same driver, at the same power limit. See [Performance](../operations/performance.md).

!!! note "Superseded: the stock restriction is issue-rate throttling, not SM disablement"
    The `docs` branch asserts "Stock firmware sets these to disable ~50% of the SMs". That claim
    is false, and the matter is settled rather than open. Both SKUs already enumerate all 70 SMs
    at stock and sit at their silicon fuse floor: a PTX `%smid` dumper returns 0..69 with no
    gaps, `OPT_GPC_DISABLE` accounts for exactly 35 active TPC, and every `CTRL_OPT` floorsweep
    register reads `0x00000000`. The code's own register names are `FEATURE_OVERRIDE_SM_SPEED`
    and `_SM_SPEED_1`, and the written values `0x88888888` / `0x00000008` are nibble-patterned
    issue-rate overrides rather than a bitmask of enabled clusters. The instruction-class evidence
    comes from an April-2026 firmware-patching investigation on driver 535.288.01, before any
    working unlock existed: non-FMA FP32 throughput was bit-identical at **4.3077 TFLOPS** across
    the unpatched card and every failed firmware and module patch, while FFMA stayed pinned near
    **0.316 TFLOPS**. A per-instruction-class throttle explains that; missing SMs would have moved
    both numbers together. To confirm it on a card, compare a CUDA
    `multiProcessorCount` query before and after the unlock: the SM count does not move, only
    throughput does. See [Compute throttle](../unlock/compute-throttle.md).

### A note on the FMA lockdown

Separately from SS0/SS1, FP32 fused-multiply-add throughput on this part is restricted in a way
that a compiler flag can work around: `nvcc -fmad=false`, `#pragma OPENCL FP_CONTRACT OFF` plus
macro-shadowing of `fma()`/`mad()` for OpenCL, or clang `-ffp-contract=off` for SYCL. A 2023
**locked-card** FluidX3D case reached 7,681 MLUPs/s with FMA removed, a 3.4x improvement; a
separate 2023 report took locked-card FP32 from 0.395 → 6.285 TFLOPS by the same route. These are pre-unlock figures. After the
SS0/SS1 writes, FP32 FFMA is unthrottled (12.2-12.8 TFLOPS with ordinary builds) and the
no-FMA/no-DP4A patches are unnecessary. **A card benchmarking near 6.25 TFLOPS is a failed-unlock
signature, not an FMA-contraction artefact**. See [Performance](../operations/performance.md).

---

## A complete verification checklist

!!! warning "`check_fold.py` and `cuda_dbg.py` are not in the repository"
    Both were published out-of-band as gists and channel attachments, not through the repository,
    and must be obtained separately. Cloning will not get you either one.

```bash
# 1. Right module is live
cat /proc/driver/nvidia/version                       # not dvs-builder
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko

# 2. Unlock executed this boot
sudo dmesg | grep SEC2_DEBUG | grep -E 'PLMs|POST-WRITE|POST-BooterLoad|late PMA'

# 3. Capacity
nvidia-smi --query-gpu=memory.total --format=csv,noheader

# 4. Capacity is real
python3 -u check_fold.py <BDF>                         # expect: REAL, NO FOLD   (out-of-band script, not in the repo)

# 5. Compute
#    read SS0/SS1 from the POST-WRITE line, then benchmark FP32 against the locked baseline

# 6. Multi-card rigs (branch script)
sudo ./verify.sh
```

If any step fails, [Troubleshooting](troubleshooting.md) is organised by symptom, and
[Recovery](recovery.md) covers wedged cards.
