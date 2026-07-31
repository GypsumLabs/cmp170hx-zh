# Troubleshooting

**What this page covers.** Every documented failure mode of the CMP 170HX unlock, indexed by the
symptom you actually see: dmesg strings, Xid numbers, Booter status codes, `RmInitAdapter`
triplets, `nvidia-smi` readings, build errors and host-level weirdness. Each entry gives the
symptom, the established cause, and the fix, with the confidence marked where the record is thin.

**Start here.** Two commands answer most questions:

```bash
sudo dmesg | grep SEC2_DEBUG      # did the unlock path run, and what did it read back?
nvidia-smi                        # 8 GB card -> ~65536 MiB, 10 GB card -> ~40960 MiB
```

If `dmesg | grep SEC2_DEBUG` prints nothing at all, the patched module never ran: go to
[Installed but still stock](#stock-memory). If it prints and the PLM lines reached their targets
but memory is still stock, go to [Memory still shows stock size](#stock-memory) and check the
initramfs. If the boot never got that far, go to [GSP boot failures](#gsp-boot).

Two rules that prevent most false alarms:

1. **`WPR_CFG` reading `0xfffff0ff` is correct.** Only three of the four privilege level masks
   (PLMs) target `0xffffffff`. See [PLM readback values](#benign-wprcfg).
2. **Booter status `0x31` and `0xffff` during the PLM passes are expected.** The unlock
   deliberately makes those runs fail. Only `SEC2_DEBUG: normal BooterLoad status=0x0` matters.
   See [Booter errors during the PLM passes](#benign-booter-31).

---

## Symptom index { #index }

| What you see | Where to go |
|---|---|
| No `SEC2_DEBUG` lines in dmesg at all | [Installed but still stock](#stock-memory) |
| `nvidia-smi` shows 8192 MiB or 10240 MiB after install | [Memory still shows stock size](#stock-memory) |
| `[WARN] Loaded nvidia srcversion (…) != patched (…)` | [srcversion mismatch](#srcversion-mismatch) |
| `Resolved nvidia.ko is not under updates/cmpunlocker/` | [Module resolution](#module-resolution) |
| `nvidia-smi`: driver/library version mismatch | [Version mismatch](#version-mismatch) |
| Unlock worked, then did not survive a shutdown | [Unlock does not persist](#not-persistent) |
| Installer exits doing nothing | [Installer refuses to run](#install-refuses) |
| `Could not detect 8GB vs 10GB card` | [Profile detection](#profile-detect) |
| `This card reports 0x…; install will continue` | [Third device ID `20b0`](#device-id-20b0) |
| `WPR_CFG=0xfffff0ff` looks wrong | [PLM readback values](#benign-wprcfg) |
| `Booter failed with non-zero error code: 0x31` | [Benign Booter errors](#benign-booter-31) |
| `dmem.bin not found (0x59)` | [Missing `dmem.bin`](#benign-0x59) |
| `Skipping BTF generation … vmlinux` | [Benign build noise](#benign-btf) |
| `[drm] No compatible format found` | [Benign DRM messages](#benign-drm) |
| `cudaHostRegister of 439781.26 MiB failed` | [Benign llama.cpp warning](#benign-cudahostregister) |
| Card shows as a generic "NVIDIA display device" | [Generic enumeration](#benign-generic-device) |
| `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042)` | [Gen2 retrain false negative](#benign-retrain-false-negative) |
| `unexpected WPR2 already up, cannot proceed with booting GSP` | [WPR2 already up](#wpr2-already-up) |
| `RmInitAdapter failed! (0x62:0x40:2028)` | [WPR2 already up](#wpr2-already-up) |
| `RmInitAdapter failed! (0x62:0x55:2028)` | [Status code catalogue](#codes-rminit) |
| `RmInitAdapter failed! (0x62:0x65:2028)` | [Status code catalogue](#codes-rminit) |
| `RmInitAdapter failed! (0x62:0x40:2674)` | [Second-GPU init failure](#rminit-2674) |
| `RmInitAdapter failed! (0x62:0xffff:2119)` with Booter `0x29` | [Dirty SEC2 exit](#rminit-2119) |
| `RmInitAdapter failed!` `0x24:0x72`, `BAR 0/BAR 2 failed.` | [BAR2 self-test failure](#bar2-0x72) |
| `GSP didn't boot`, status `0x65` | [GSP timeout `0x65`](#gsp-0x65) |
| Xid 119, 60 s, function 4097 `GSP_INIT_DONE` | [Xid 119, 60 s](#xid119-60s) |
| Xid 119, 6 s, function 103 `GSP_RM_ALLOC` | [Xid 119, 6 s](#xid119-6s) |
| Booter error `0x35` | [Booter `0x35`](#booter-0x35) |
| Booter error `0x54` on a PG199 / A100D | [Booter `0x54`](#booter-0x54) |
| `rpc_result = 0xFFFF`, NULL `GSP-LOG[RM]` | [RM init stalls early](#rpc-ffff) |
| `falconMailbox 0:00000031`, `riscvPc 00000000` | [Falcon core dump](#falcon-coredump) |
| `0xbadfXXXX` register reads | [`0xbadf` taxonomy](#codes-badf) |
| Fire runs, nothing changes, `resetPLM 0xff -> 0x8f` | [Bus mastering cleared](#bus-master) |
| `PLMs: 1/9 open (fired 8 closed)`, `resetPLM=0x00cf` | [Driver still loaded](#driver-loaded) |
| `modprobe -r nvidia` refuses, `nvidia 15835136 2` | [Module will not unload](#module-stuck) |
| DMEM writes silently dropped | [DMEM locked in HS](#dmem-locked) |
| CFG1 write bounces back to `0x02449000` | [FLR between PLM open and write](#flr-between) |
| Card "degraded" over days, `SEC2 MBOX0 = 0x0` | [Deleted firmware directory](#firmware-deleted) |
| Build fails after a kernel swap | [Build failures](#build) |
| PCIe still Gen1 after installing the unlocker | [Gen2 stays at Gen1](#gen2-still-gen1) |
| Black screen, text console, `cmpretrain.service` failed | [Black screens](#black-screen) |
| Xid 31, `FAULT_INFO_TYPE_REGION_VIOLATION` | [Xid 31](#xid31) |
| Xid 45 after killing a CUDA job | [Xid 45](#xid45) |
| Xid 154 on an over-provisioned card | [Xid 154](#xid154) |
| vLLM crashes at `gpu-memory-utilization 0.95` | [vLLM headroom](#vllm) |
| `cuInit` returns 999 everywhere | [`cuInit` 999](#cuinit999) |
| gpu-burn reports thousands of memory errors | [Burn-in errors](#burn-errors) |
| `nvidia-smi --gpu-reset`: "GPU is being used by another process" | [Reset refuses](#gpu-reset-busy) |
| Unlock works but CUDA does not | [CUDA broken on one host](#cuda-clean-host) |
| Multi-GPU rig: every card stays stock | [Silent multi-card failure](#multicard) |
| Server will not POST with the cards fitted | [Host will not boot](#no-post) |
| Card ran for an hour, then vanished from the bus | [Card off the bus](#off-bus) |

---

## 1. What a healthy boot looks like { #healthy-boot }

A successful unlock boot prints these `SEC2_DEBUG` lines, in this order:

1. `SEC2_DEBUG: saved stock signature (4096 bytes)`, immediately followed by
   `SEC2_DEBUG: <path> not found (0x59), using built-in payload`
2. The WPR meta dump: `SEC2_DEBUG: WPR meta fbSize=… wprEnd=… heapSize=…`
3. `SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x`
4. Four `SEC2_DEBUG: PLM[%u] %s(0x%x) attempt=%u status=0x%x reg=0x%08x` lines
5. `SEC2_DEBUG: PLMs: FEAT=… FBPA=… WPR=… WPR_CFG=…`
6. `SEC2_DEBUG: POST-WRITE SS0=… SS1=… CFG1=… LMR=… (devId=0x%x)`, followed on failure only by
   `SEC2_DEBUG: rebuild stock signature failed: 0x%x`
7. `SEC2_DEBUG: WPR meta updated fbSize=… wprStart=… wprEnd=… heapOffset=… heapSize=…`
8. `SEC2_DEBUG: normal BooterLoad status=0x0`
9. `SEC2_DEBUG: POST-BooterLoad verify PLM=… SS0=… SS1=… CFG1=… LMR=…`
10. The GSP static-info BEFORE/AFTER pair

Both signature prints come from `_kgspCreateSignatureMemdesc`, which runs before `_kgspBootGspRm`,
so they open the trail rather than sitting mid-sequence. The `POST-BooterLoad verify` line is the
definitive proof: it is read back **after** the real GSP boot, so it shows the unlock survived.

**Expected values.**

| Log field | Expected | Notes |
|---|---|---|
| `PLM[0] WPR_CFG(0x1fa7cc)` | `reg=0xfffff0ff` | not `0xffffffff` |
| `PLM[1] FBPA(0x9a0148)` | `reg=0xffffffff` | |
| `PLM[2] WPR(0x1fa7c4)` | `reg=0xffffffff` | |
| `PLM[3] FEAT(0x823804)` | `reg=0xffffffff` | always-on island, survives FLR |
| `status=` on any PLM line | `0xffff` | expected; the readback is the verdict |
| `SS0 (0x0082381c)` | `0x88888888` | locked card reads e.g. `0x53540175` |
| `SS1 (0x00823820)` | `0x00000008` | |
| `CFG1 (0x009a0204)` | `0x02779000` (8 GB card) / `0x02669000` (10 GB card) | stock is `0x02449000` on both |
| `LMR (0x00100ce0)` | `0x0000020B` (8 GB card) / `0x0000028A` (10 GB card) | stock `0x00000208` / `0x00000288` |
| `normal BooterLoad status` | `0x0` | the one status that must be zero |

Any other CFG1/LMR pairing in `POST-WRITE` means the wrong profile is in play. See
[Memory geometry](../unlock/memory-geometry.md) for what the values mean.

Three log tags exist, all emitted at `LEVEL_ERROR` so they appear with no extra debug flags:

| Tag | Emitted by | Content |
|---|---|---|
| `SEC2_DEBUG` | patches 0001, 0002, 0003 | PLM, register and Booter stages: 14 log strings in 0001, 7 in 0002, plus `late PMA extension status=0x%x` in 0003 |
| `SEC2_DEBUG_HEAP` | patch 0003 | `fbAddrSpace=%lluMB mapRam=%lluMB fbTotal=%lluMB fbUsable=0x%llx heapTotal=0x%llx regionBytes=0x%llx publicBytes=0x%llx numRegions=%u` (one string) |
| `SEC2_DEBUG_LATE_PMA` | patch 0003 | per-FB-region descriptors plus `pma_total 0x%llx->0x%llx pma_free 0x%llx->0x%llx` (10 strings) |

**Full verification block:**

```bash
nvidia-smi                                                     # ~65536 MiB or ~40960 MiB
nvidia-smi --query-gpu=memory.total,clocks.max.sm --format=csv
sudo dmesg | grep SEC2_DEBUG
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile  # 8gb or 10gb
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry
```

One archived good result reads literally `65536 MiB, 1935 MHz`. Note that
`clocks.max.sm = 1935 MHz` is a **reported field only** and not an achievable clock: sustained SM
clock is 1410 MHz, or 1470 MHz at `-pl 300`. See [Performance](../operations/performance.md).

See [Verify](verify.md) for the full post-install checklist.

---

## 2. Messages that look like failures but are not { #benign }

### 2.1 Booter errors during the PLM passes { #benign-booter-31 }

**Symptom.**

```text
s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31
kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff
```

immediately followed by a PLM line showing the target value in `reg=`.

**Why it is fine.** Patch 0001 deliberately overwrites the GSP signature buffer with an exploit
payload for each PLM pass, so Booter Load is *supposed* to reject those runs: the injected chain
has already executed by the time the signature complaint is raised. Success is judged only by
reading the PLM register back, never by the Booter status. Worst case there are eight of these
(four PLMs, up to two attempts each) before the real bootstrap Booter Load.

**The line that must succeed** is `SEC2_DEBUG: normal BooterLoad status=0x0`.

### 2.2 `dmem.bin not found (0x59)` { #benign-0x59 }

```text
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
```

This is the normal path. The external `dmem.bin` is a development override hook read with
`os_open_and_read_file`; `0x59` is that function's file-not-found status. Every archived
successful unlock boot shows this line. The built-in fallback payload targets the FBPA PLM
(`writeAddr = 0x009a0148`, `writeValue = 0xffffffff`), which the PLM loop then rewrites per
iteration.

The preceding line, `SEC2_DEBUG: saved stock signature (4096 bytes)`, confirms the stock GSP
signature on this driver is 4096 bytes.

### 2.3 `Skipping BTF generation` during the build { #benign-btf }

```text
Skipping BTF generation for .../nvidia.ko due to unavailability of vmlinux
```

Benign. BTF is kernel debug metadata unrelated to the unlock; the modules still build and load.
It appears for `nvidia-peermem.ko`, `nvidia-modeset.ko`, `nvidia-drm.ko`, `nvidia.ko` and
`nvidia-uvm.ko`. The line that matters afterwards is `[ OK ] Patched NVIDIA modules loaded`.

### 2.4 DRM "no compatible format" messages { #benign-drm }

```text
[drm] Initialized nvidia-drm 0.0.0 20160202 ... on minor 1
[drm] No compatible format found
[drm] Cannot find any crtc or sizes
```

Benign. The CMP 170HX has no display outputs.

### 2.5 llama.cpp `cudaHostRegister` warning { #benign-cudahostregister }

```text
ggml_cuda_host_malloc: cudaHostRegister of 439781.26 MiB failed: unknown error
```

Not fatal: loading continues and benchmarks complete. Distinguish it from a genuine allocation
crash, which kills the process outright.

### 2.6 Generic device enumeration { #benign-generic-device }

The card enumerating as a generic "NVIDIA display device" in Linux monitoring tools (for example
Mission Center) is normal. On a stock driver `nvidia-smi` also reports it as
`NVIDIA Graphics Device` with compute capability 8.0, because the driver's PCI ID table carries no
marketing name for `0x20C2`. That is a fast way to confirm you are looking at a CMP part.

### 2.7 Gen2 retrain "completed without Gen2 link" { #benign-retrain-false-negative }

```text
CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)
```

This is a **false negative**: `0x1042` *is* a trained Gen2 x4 link. Decode: speed field `[3:0] = 2`
(5.0 GT/s), width field `[9:4] = 4` (x4). The driver's success test additionally requires
`PCI_EXP_LNKSTA_DLLLA` (Data Link Layer Link Active, bit 13, `0x2000`), and `0x1042` has bit 13
clear, so the check fails while the link is genuinely at Gen2. Hosts reporting `0x7042` (bit 13
set) print the success message from the same code. Four cards across two hosts show the
contradictory pairing.

Trust one of these instead:

```bash
nvidia-smi --query-gpu=pcie.link.gen.current --format=csv
cat /sys/bus/pci/devices/0000:$BDF/current_link_speed
```

> [!NOTE]
> **Open problem**
>
> Whether the DLLLA bit reading zero indicates a real, if benign, link-layer difference between
> those hosts, rather than only a reporting artifact, was never investigated.

### 2.8 "All PLMs must show `0xffffffff`" { #benign-wprcfg }

Third-party documentation (`docs/DEBUGGING.md`, `docs/ARCHITECTURE.md`, and a milder phrasing in
the shipping README) says every PLM should read `0xffffffff`. That is over-general. The shipping
`plmTable[]` is:

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

and the loop's success predicate is `if (regVal == plmTable[plmIdx].value)`. A healthy boot prints
`SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff`.

---

## 3. Installed, but the card is still stock { #stock-memory }

This is the most common class of report. The unlock code is fine; the patched module is not the
one running, or it did not get a clean boot in which to run.

### 3.1 `nvidia-smi` shows 8192 MiB or 10240 MiB { #stock-size }

**Cause.** Either the PLM unlock did not take, or the stock module is still loaded.

**Fix.** Check `sudo dmesg | grep SEC2_DEBUG`.

* **No output at all** means the patched module never ran. Work through 3.2 to 3.5.
* **Output present, PLMs did not reach their targets** means the unlock chain ran and failed:
  do a full power-off shutdown (an OS reboot is *not* sufficient) and retry. See
  [Cold boot](recovery.md#cold-boot).
* **Output present, `POST-WRITE` correct, memory still stock** points at the second-stage memory
  plumbing rather than the register writes. Capture the `SEC2_DEBUG_HEAP` and
  `SEC2_DEBUG_LATE_PMA` lines and the `late PMA extension status=0x%x` value.

The leaked distribution README uses the same triage: `nvidia-smi` showing 65536 MiB is the success
criterion, and 8192 MiB means the PLM unlock failed. It also instructs a **cold** reboot rather
than a warm one.

### 3.2 srcversion mismatch { #srcversion-mismatch }

**Symptom.**

```text
[WARN] Loaded nvidia srcversion (…) != patched (…)
[WARN] Modules installed but the running driver is still stock (or unload failed).
```

**Cause.** The stock `nvidia.ko` is still resident and could not be unloaded. `build.sh` attempts a
hot reload (stop `nvidia-persistenced` and `nvidia-fabricmanager`, `modprobe -r` the four modules,
reload) and cross-checks `/sys/module/nvidia/srcversion` against `modinfo -F srcversion` of the
installed module.

**Fix.** Cold reboot (`shutdown -h now`, then power on), then confirm:

```bash
cat /proc/driver/nvidia/version      # must NOT say dvs-builder
sudo dmesg | grep SEC2_DEBUG         # must have output
```

One tester confirmed the cold reboot cleared it.

### 3.3 Module resolution: stock still wins { #module-resolution }

**Symptom.** `build.sh` prints
`Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`.

This is the earliest signal of a module-resolution problem. Module precedence is
`updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`, which is plain depmod ordering (this
is why no `dpkg-divert` is needed). `build.sh` runs `depmod -a "${KVER}"` and then empirically
verifies the result with `modprobe -n -v nvidia`.

> [!CAUTION]
> **Multi-GPU hazard**
>
> On multi-GPU systems a patched and a stock `nvidia.ko` can both end up under the single
> `updates` depmod search entry, in which case **depmod picks one arbitrarily and silently drops
> the other**. One tester root-caused a multi-GPU failure to exactly this, kept only the
> cmpunlocker variant in the updates search path, rebooted, and then confirmed multi-GPU
> operation working.

### 3.4 The initramfs still carries stock modules { #initramfs }

Branch copies of `build.sh` (`memory`, `ecc`, `housekeeping`, `PG199`) carry the explanation
verbatim: "NVIDIA often loads from initramfs. If only updates/dkms is packed there, stock modules
win at boot even when updates/cmpunlocker is preferred by depmod." Master drops the comment but
keeps the behaviour: `build.sh` calls, in order of availability, `update-initramfs -u -k "${KVER}"`,
`dracut --force --kver "${KVER}"`, or `mkinitcpio -P`; if none is present it warns
`No initramfs tool found, rebuild manually before rebooting`.

This is a plausible route to "installed but memory still shows stock size", and it is worth ruling
out first because it is cheap, but it is the scripts' own reasoning rather than a diagnosed field
failure: no chat report anywhere in the corpus mentions initramfs, initrd, dracut or mkinitcpio.
If you saw that warning, rebuild the initramfs by hand and cold boot.

### 3.5 Maintainer triage: three steps { #triage-three-step }

The standard triage for "install completes but the card is still stock":

```bash
# Step 1 - did the build target the kernel you actually booted?
uname -r
ls -la /lib/modules/$(uname -r)/updates/cmpunlocker/
cat /lib/modules/$(uname -r)/updates/cmpunlocker/driver_version
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile
cat /lib/modules/$(uname -r)/updates/cmpunlocker/unlock_geometry

# Step 2 - is the running module the patched one?
modprobe -n -v nvidia
modinfo -F filename,srcversion,version nvidia
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko

# Step 3 - what does the card and the log say?
nvidia-smi --query-gpu=name,memory.total,driver_version,pci.bus_id --format=csv
sudo dmesg | grep -E "SEC2_DEBUG|NVRM|nvidia"
cat /proc/driver/nvidia/version
```

A missing directory in step 1 means the build targeted a different kernel than the one booted. In
step 2 the resolved path must contain `/updates/cmpunlocker/` and the running srcversion must equal
the cmpunlocker `.ko` srcversion; a mismatch means stock is still running.

Note that the three metadata files are **metadata only**. Nothing in the kernel modules reads
them: geometry is chosen at runtime from the PCI device ID. A mis-detected `--profile` writes
wrong metadata but does **not** produce wrong geometry.

### 3.6 `nvidia-smi`: driver/library version mismatch { #version-mismatch }

**Cause.** The previous kernel module is still resident.

**Fix, in order of safety:** reboot; or reload the kernel module; or install a matching
`nvidia-smi` build. Disabling the version-mismatch check masks the problem rather than fixing it.

> [!CAUTION]
> **A mismatched `nvidia-smi` silently invalidates every measurement**
>
> NVML refuses to talk across versions, so unlock verification through a mismatched binary is
> meaningless. One multi-day measurement series was invalidated this way (a 580.159.03 userspace
> against a different kernel module build). If your userspace and module versions differ,
> every `memory.total` reading you have taken is void.

### 3.7 The unlock did not survive a shutdown { #not-persistent }

**Cause.** Remnants of an older NVIDIA driver and/or an older `cmpunlocker` systemd service.

**Fix.** Remove all old kernel modules **and** the old `cmpunlocker` service, then reinstall.
Shipping `remove.sh` now does both: it stops, disables and deletes
`/etc/systemd/system/cmpunlocker.service`, kills `/opt/cmpunlocker/daemon/watchdog.py`, removes
`/lib/modules/*/updates/cmpunlocker/`, runs `depmod -a` per kernel, rebuilds the initramfs, and
reloads stock modules. See [Uninstall](uninstall.md) and [Recovery](recovery.md).

No systemd daemon is needed on the shipping tool: patch 0006 sets `NV_FLAG_PERSISTENT_SW_STATE`
for both device IDs, which is effectively built-in persistence mode.

### 3.8 The installer refuses to run { #install-refuses }

`install.sh` hard-fails, doing nothing, in these cases:

| Condition | Message / behaviour |
|---|---|
| Not root | dies immediately |
| No `10de:20b0`, `10de:20c2` or `10de:2082` in `lspci -nn` | dies |
| Secure Boot enabled | `Secure Boot is enabled. Disable it before installing unsigned patched modules.` |
| Kernel headers missing at `/lib/modules/$(uname -r)/build` | dies |
| Detected driver not in `driver/VERSION` | `Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.` |
| Memory total outside every profile bucket | `Could not detect 8GB vs 10GB card` |

The Secure Boot gate only runs if `/sys/firmware/efi` exists **and** `mokutil` is on PATH; on a
non-EFI system, or one without `mokutil`, the check is silently skipped, and the unsigned modules
will then fail to load with
`nvidia: module verification failed: signature and/or required key missing - tainting kernel`.

Driver-version detection order: `/proc/driver/nvidia/version`, then
`nvidia-smi --query-gpu=driver_version`, then a scan for `/lib/firmware/nvidia/<supported>/`, then
the highest-sorting directory under `/lib/firmware/nvidia/`. See
[Driver versions](driver-versions.md).

### 3.9 Wrong card profile detected { #profile-detect }

`detect_card_profile()` reads stock `nvidia-smi memory.total` and buckets it:

| Reported `memory.total` | Profile |
|---|---|
| ≥ 60000 MiB | `8gb` (already-unlocked 64 GB card) |
| 35000 to 59999 MiB | `10gb` (already-unlocked 40 GB card) |
| 7680 to 8704 MiB | `8gb` |
| 9728 to 10752 MiB | `10gb` |
| anything else | fatal `Could not detect 8GB vs 10GB card` |

The first two ranges exist so that re-installing on an already-unlocked card still detects the
right profile. If detection is wrong or `nvidia-smi` is unavailable, force it:

```bash
sudo ./install.sh --profile=8gb    # or --profile=10gb
```

### 3.10 Third device ID `10de:20b0` { #device-id-20b0 }

`install.sh` detects `10de:20b0` but warns and continues:

```text
In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
This card reports 0x20b0; install will continue, but unlock may not activate.
```

Every unlock action **and every `SEC2_DEBUG` print** in patches 0001 and 0002 is gated on
`0x20C2` / `0x2082` only, via `_kgspSec2PostblTimingEnabled()`, which tests
`pGpu->idInfo.PCIDeviceID >> 16`. A `20b0` card therefore installs cleanly, boots the completely
stock path, and should print **nothing** in `dmesg | grep SEC2_DEBUG`.

> [!NOTE]
> **Open problem**
>
> One tester with A100 Engineering Sample silicon (`20B0`, 8192 MB, 2048-bit, 4096 CUDA cores,
> Samsung 8Hi HBM2) reported an `NVRM initialization error` *and* that `SEC2_DEBUG` confirmed the
> registers were written. A stock build cannot print those lines on a `20B0` card. Either a
> modified build with the ES ID added was running, or the lines came from a different card in
> the same host. Not resolvable from the record.

---

## 4. GSP boot failures { #gsp-boot }

### 4.1 WPR2 already up { #wpr2-already-up }

**Symptom.**

```text
NVRM: _kgspBootGspRm: unexpected WPR2 already up, cannot proceed with booting GSP
NVRM: (the GPU is likely in a bad state and may need to be reset)
NVRM: RmInitAdapter: Cannot initialize GSP firmware RM
NVRM: RmInitAdapter failed! (0x62:0x40:2028)
NVRM: rm_init_adapter failed, device minor number 0
```

ending in `No devices were found` from `nvidia-smi`. This was the dominant post-exploit failure,
reported identically by at least three testers.

**Cause.** A previous Booter run programmed the WPR2 MMU registers and then derailed, so on the
next modprobe the driver sees WPR2 already up and refuses.

**Fix (cleanroom era).** Full driver teardown, then FLR via
`echo 1 > /sys/bus/pci/devices/0000:BDF/reset`, or a cold power cycle.

The shipping patch also saves WPR2 lo/hi from `0x001fa824` / `0x001fa828` once before the PLM loop,
rewrites both registers before **every** Booter Load attempt, and rewrites them again after the
loop. It never clears them.

### 4.2 Xid 119, 60 second timeout, function 4097 { #xid119-60s }

**Symptom.**

```text
Xid 119: Timeout after 60s of waiting for RPC response from GPU0 GSP!
  Expected function 4097 (GSP_INIT_DONE)
GSP RPC buffer contains function 4098 (GSP_RUN_CPU_SEQUENCER)
kflcnWaitForHalt_TU102: Timeout waiting for Falcon to halt
NV_ERR_TIMEOUT (0x00000065)  from kflcnWaitForHalt_HAL at kernel_gsp.c:5386 (or :5449)
falconMailbox 0:00000031
... then: WPR2 already up
```

**Cause.** The GSP RISC-V core never reached RM init: the boot **hung** rather than being rejected.

**Fix.** Reset so WPR2 is cleared, then retry: FLR first, then SBR or a cold power cycle if FLR
does not clear it. See [Recovery](recovery.md).

**Supporting detail.** The preceding `_threadNodeCheckTimeout` shows the 4000 ms Falcon-halt
timeout; the GSP event itself took 59 s. On one capture the CPU-to-GSP RPC history contained only
entry 0 `SET_REGISTRY` and entry -1 `GSP_SET_SYSTEM_INFO`, meaning the GPU never got past early
bootstrap. Captured on two hosts, two kernels and two driver builds (580.159.03 and 580.167.08).

### 4.3 Xid 119, 6 second timeout, function 103 { #xid119-6s }

**This is a different failure** from 4.2. Distinguish them by function number and timeout length.

**Symptom.** Xid 119 with a 6-second timeout and function 103 (`GSP_RM_ALLOC`), after a partially
successful boot: the GPU reaches a running state (nvidia-drm loaded, `GSP_RM_CONTROL` and `FREE`
RPCs completing in 224 to 5222 µs), and then every `nvidia-smi` hangs, repeating the Xid roughly
every 6 s for successive sequence numbers (184, 185, 186).

**Fix.** Reset the card; the state is not recoverable in place.

### 4.4 `GSP didn't boot`, status `0x65` { #gsp-0x65 }

**Symptom.** `GSP didn't boot` in dmesg with status `0x65`.

**Cause.** The crafted signature buffer / Booter sequence left GSP unable to start. `0x65` is
driver-side `NV_ERR_TIMEOUT`.

**Fix.** Full power cycle and retry. Removing old kernel modules alone was **not** sufficient for
the tester who reported it.

> [!CAUTION]
> **`0x65` is not `0x31`**
>
> `0x65` is the driver-side `NV_ERR_TIMEOUT`; `0x31` is a mailbox value. They occur at different
> stages. The decisive test: the WPR2 error comes from the register writes alone, while a
> two-load process with no writes at all still hits `0x65`. An early claim that the two codes
> were the same thing was contradicted within the hour by a controlled no-writes run.

Why FLR sometimes cannot recover a `0x65` wedge is covered in [Recovery](recovery.md#flr-vs-sbr).

### 4.5 Booter error `0x35` { #booter-0x35 }

**Symptom (standalone / driverless tooling only).** Booter returns `0x35`.

**Cause.** `regtable_rw_indexed` reads the DMEM register descriptor tables at DMEM `0x2383` and
`0x8e08` and finds zeros. The stock signature is only `0x1000` bytes, so its DMA reaches only DMEM
`0x17FF` and leaves those tables intact. The exploit payload must be `0xF800` bytes so its frames
reach the stack at `0xF748`, which makes the DMA overwrite DMEM `0x0800` to `0xFFFF` and zero the
tables. Stage MAIN.6 reads the table before the DMA (intact) and MAIN.7 verifies after (zeroed),
triggering `0x35`.

**Fix (driverless path).** Include the original stock table contents at payload offsets `0x1B83`
(DMEM `0x2383`) and `0x8608` (DMEM `0x8E08`). Those contents exist in no flat file: they are
generated at runtime by the bootloader from constants in bootloader code and/or the boot
descriptor, so reconstructing them was itself a substantial sub-problem. Immediately after applying
the fix the researcher reported getting GSP-RM started.

> [!NOTE]
> **Not reachable on the shipping path**
>
> The shipping in-driver patch never hits `0x35`. `kgspSec2PostblTimingRebuildStockSignature()`
> restores the real 4096-byte signature before the genuine GSP-RM boot, so that boot's DMA
> reaches only DMEM `0x17FF` and the descriptor tables stay intact. The `0x1B83`/`0x8608`
> restoration is absent from the shipping payload and is not needed there.
> *(Confidence: medium; reasoned from the shipping code plus the 2026-07-20 root-cause analysis,
> not independently instrumented.)*

### 4.6 Booter error `0x54` { #booter-0x54 }

> [!NOTE]
> **Open problem**
>
> **Symptom (PG199 / A100D, `10DE:20BB`, 32768 MiB stock):**
>
> ```text
> kgspBootstrap_TU102: kflcnResetIntoRiscv 0x0
> s_executeBooterUcode_TU102: Booter failed 0x54
> ```
>
> State reached before the failure: `MMU_LMR 0x0000020a -> 0x0000020b`; `FBPA_CFG1` stock
> `0x22779000`, with one variant clearing bit 29 to give `0x02779000` and another leaving
> `0x22779000`; `SS0 0x53540175` and `SS1 0x00000000` deliberately unchanged; WPR2
> `07f68000/07fefe00 -> 1ffffe00/0`; PLMs `ffffff8f/0004cb8f -> opened`. WPR2 is left in the
> failed-init state because GSP never finishes initialising.
>
> **Nobody could say what `0x54` means.** It has been observed only on A100D / PG199 hardware,
> never on a 170HX. The register writes demonstrably land, so the question is narrow: find the
> Booter status enum. Note that the branch named `PG199` contains no A100D support, so this work
> lives outside the repository.

### 4.7 `RmInitAdapter failed! (0x62:0x40:2674)` { #rminit-2674 }

**Symptom.** No successful init at all on one GPU of a multi-GPU box, while another GPU in the same
box reaches Xid 119.

**Cause.** Not established. It is a real, reproducible signature. Observed on an OEM BTC B250
mining board, kernel 6.8.0-134-generic, driver 580.159.03, Intel SPT PCH root ports with the ACS
workaround enabled.

### 4.8 `RmInitAdapter failed! (0x62:0xffff:2119)`, dirty SEC2 exit { #rminit-2119 }

**Symptom.**

```text
s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x29
_kgspBootGspRm: SEC2_DEBUG: FAILED to open FBPA_008 (0x9a0008) after 2 attempts reg=0xffffff8f
kgspInitRm_IMPL: Max GSP-RM boot attempts exceeded: 4/4
NVRM: RmInitAdapter failed! (0x62:0xffff:2119)
```

**Cause.** The PLM was left partly locked by a dirty SEC2 exit. `reg=0xffffff8f` is the tell:
`0x8f` is the "secure_teardown ran" marker value. Booter `0x29` comes from `check_1180f8_nibbles`,
which requires the incoming top nibble of `0x001180f8` to be `0`.

**Reproducible A/B.** Firing with no geometry or compute writes and no `0x1180f8` write got further
and only failed at `FBPA_00C (0x9a000c)`; adding just the `0x1180f8 = 0x17100000` write made both
`FBPA_008` and `FBPA_00C` fail.

**Fix.** Get a clean SEC2 exit: cold boot, then re-fire without the extra writes.

### 4.9 `0x24:0x72`, `BAR 0/BAR 2 failed.` { #bar2-0x72 }

**Symptom.** `RmInitAdapter failed!` with `0x24:0x72` or `0x72`, journal string
`"BAR 0/BAR 2 failed."` at `journal.c:4081`, i.e. `NV_ERR_MEMORY_ERROR`.

**Cause.** Not memory damage, and not an SCP crypto failure. A before/after probe showed the
BAR0-to-vidmem path still returned the written pattern `0xabcdabcd`. What fails is the second,
BAR2-virtual (MMU-translated) test in `kbusVerifyBar2`, because the genuine Booter carved WPR2 at
`0x2777000` to `0x27fee00` and set the FBIF `0x800` bit during its normal ACR job, and the driver's
BAR2 test buffer / instance block lands in that write-protected region.

**Fix.** Tear WPR2 back down on the way out of heavy-secure mode:

```text
0x1FA824 = 0x1FFFFE00
0x1FA828 = 0x00000000
```

**Escape hatch, never exercised.** The BAR2 self-test is skippable via `PDB_PROP_GPU_BROKEN_FB`,
`gpuIsCacheOnlyModeEnabled` or `kbusIsBar2TestSkipped`. These were identified in source while
`0x24:0x72` was still blocking boot, but the WPR2 teardown fixed the underlying cause first, so
they remain documented and untried.

A driverless exploit run produces the same `0x72` mapping: it leaves the GPU's BAR2/L2/MMU
(POST/DEVINIT) state ACR-configured, so CPU-RM's memory self-test fails.

### 4.10 RM init stalls with `rpc_result = 0xFFFF` { #rpc-ffff }

> [!WARNING]
> **Experimental**
>
> Historical, cleanroom-era, single-load rejoin path. A partially successful rejoin can reach
> GSP-RM init and still stall with `RPC_HDR->rpc_result = 0xFFFF` (`NV_ERR_GENERIC`) and a NULL
> `GSP-LOG[RM]` buffer, meaning RM init fails very early. In that state the Booter had completed
> (WPR2 set up, `BOOTVEC = 0xfd00`, `finalize_1180f8` observed `0x17100000` against a known-good
> `0x11000000`), the driver re-asserted GSP boot-args because MBOX0 was clobbered to `0x31`,
> restored `WprMeta.sizeOfSignature = 0x1000`, and bypassed `kflcnIsRiscvActive` because the
> HS-locked register gives a false negative. Documented as "the current wall" on 2026-07-07; the
> RM-side root cause was never identified, and the whole approach was superseded by the
> in-driver patch. *(Confidence: medium.)*

A related state: a failed GSP handoff presenting as Xid 119 / `GSP_INIT_DONE` timeout with
mailbox0 = `0x31`, `finalize_1180f8 = 0x11000000` and `BOOTVEC = 0xfd00`. There the Booter
completed its authentication path but the RISC-V GSP never launched, because no BCR write was
issued. Returning at `0x37b7` and at `0x37cc` gave identical outcomes.

**Reference "good landing" state** after a successful whole-stack rejoin, for comparison:

| Observable | Good value | Meaning |
|---|---|---|
| `finalize 0x1180f8` | `0x11000000` | nibble 1 in `[31:28]` plus authenticate's bit 24; bit 26 (`BOOT_STAGE_3_HANDOFF`) is **not** set |
| `GSP_FALCON_MAILBOX0` | `0x31` | GSP-RM alive |
| `GSP BOOTVEC` | `0xfd00` | |
| SEC2 resetPLM | `0x8f` | `secure_teardown` ran |
| SEC2 MBOX0 | `0x0` | `report_status` wrote r0 = 0 |
| `RV_STATUS 0x111240` | `0x33` or `0x35` | RISC-V core running (`0x0` when it never started) |

### 4.11 Falcon core dump from a hung boot { #falcon-coredump }

A non-destructive Falcon core dump from a hung boot reads:

```text
falconMailbox 0:00000031        # PC hijack succeeded
riscvPc       00000000          # RISC-V core idle
riscvCpuctl   00000010
riscv mailboxes 0,1,2,3 = 0
riscvIrqmask / riscvIrqdest / riscvPrivErrStat / riscvPrivErrInfo
  / riscvPrivErrAddr / riscvHubErrStat = 0
falconIrqstat 00000000
falconIrqmode 0000fc24
fbifInstblk   00000000
fbifCtl       00000190
fbifThrottle  80000064
fbifAchkBlk   0:a2286560 1:370b1788
fbifAchkCtl   0/0
fbifCg1       0000000f
```

**Read:** the overflow took control of the Booter, but the GSP core was never started. The exploit
hung the boot rather than being rejected by the signature check.

### 4.12 Diagnosability: what patch 0002 adds { #patch-0002 }

Patch 0002 exists specifically to make GSP bootstrap failures diagnosable. It converts fatal
`NV_ASSERT_OK_OR_RETURN` macros into logged status checks, producing:

```text
SEC2_DEBUG: FWSEC cmd is NULL, aborting
SEC2_DEBUG: kflcnReset for FWSEC: 0x%x
SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x
SEC2_DEBUG: FWSEC: pPreparedFwsecCmd=%p frtsSize=0x%x
SEC2_DEBUG: FWSEC status=0x%x
```

Most of the `SEC2_DEBUG` lines users are asked to paste into tickets originate here.

### 4.13 Signature-size positive control { #sigtest }

If you see this, it is a **positive control**, not a failure:

```text
_kgspCreateSignatureMemdesc: kgsp: TEST sig override active:
  orig first 4096 B + /tmp/sig tail, total 23360 B, orig size: 4096
kgspBootstrap_TU102: [sigtest] DEVICE IS UP: GSP booted and RISCV is active
  (Booter accepted the signature)
```

This run on 580.167.08 demonstrated the vulnerability. It still hit the usual Xid 119 /
WPR2-already-up path 60 s later.

The shipping signature buffer is `0xf800` bytes (`SEC2_POSTBL_TIMING_SIGNATURE_SIZE
0x0000f800ULL`, 63,488 bytes), **not** `0xf700`. A community reproduction blocked on the
`fwsignature_ga100` section in the GSP binary being only `0x1000` bytes versus a hardcoded `0xf700`
payload; the resolution was to stop patching firmware and enlarge `pSignatureMemdesc` from the
driver instead.

---

## 5. Status code catalogue { #codes }

### 5.1 Booter and GSP status codes { #codes-booter }

| Code | Meaning | Notes |
|---|---|---|
| `0x00` | SEC2 MAILBOX0 clean exit / GSP-RM booted cleanly | |
| `0x2` | Invalid signature | |
| `0x29` | Bad finalize nibbles, from `check_1180f8_nibbles` | requires incoming top nibble of `0x1180f8` to be `0` |
| `0x31` | Booter refused / default status in SEC2 MAILBOX0 | **context-dependent**, see below |
| `0x35` | DMEM register descriptor tables read zero | driverless path only, see [4.5](#booter-0x35) |
| `0x47` | Canary mismatch panic | |
| `0x54` | Observed only on A100D / PG199 | meaning **unknown**, see [4.6](#booter-0x54) |
| `0x59` | File-not-found for the optional `dmem.bin` | benign, see [2.2](#benign-0x59) |
| `0x60` | Seen transitioning to `0xffff` | |
| `0x62` | Driver-side `NV_ERR_RESET_REQUIRED`; also a firmware-init failure status | leading field of the RmInitAdapter triplets |
| `0x65` | Driver-side `NV_ERR_TIMEOUT` | see [4.4](#gsp-0x65) |
| `0x72` | `NV_ERR_MEMORY_ERROR`, BAR2 self-test | see [4.9](#bar2-0x72) |
| `0xfe` | CPU-RM ACR detects post-fire SEC2 state | only an FLR clears it *(confidence: medium)* |
| `0xffff` | Booter Load failure / GSP-RM init failed | expected on every payload pass |
| `0xFFFFFFFF` | GSP mailbox unread | |
| `0x15` | The Booter's `csb_write` error path, reported into SEC2 MAILBOX0 | |

Confidence is high for codes read from live dmesg, and low for the `0x54` and `0xffff` mechanism
attributions. One reading attributes `0xffff` to the Booter carving WPR2 at the top of FB into an
unbacked region after a geometry change; that is not settled.

**Mailbox addresses.** SEC2 MAILBOX0 is BAR0 `0x00840040`; the GSP mailbox is `0x00110040`.

> [!NOTE]
> **Open problem**
>
> **What mailbox `0x31` means was never settled.** Three incompatible readings exist:
> (a) "initial value / no writes yet", **explicitly withdrawn**, because `0x31` turned out to be
> a written value (the driver's boot-args physical address, clobbered) and because a healthy GSP
> boot resets `0x110040` to 0; (b) "the ACR mutex is held", the reading that stuck early;
> (c) "the SEC2 Booter's own success signature", with the driver's `0x65` then being only a 60 s
> completion-wait timeout caused by SEC2 sitting in the `0x8f` torn-down state. A fourth usage
> reads `GSP_FALCON_MAILBOX0 = 0x31` as "GSP-RM alive" in the good-landing state.
> **Treat `0x31` as an observation, not a diagnosis.** What would settle it: the SEC2 Booter's
> own status enum, or a controlled experiment producing `0x31` with the ACR mutex provably free.

### 5.2 `RmInitAdapter` triplets { #codes-rminit }

The leading `0x62` is `NV_ERR_RESET_REQUIRED`.

| Triplet | Meaning |
|---|---|
| `(0x62:0x40:2028)` | WPR2 already up, see [4.1](#wpr2-already-up) |
| `(0x62:0x55:2028)` | `DEVICE FAILED TO COME UP: RISCV not active after Booter Load` |
| `(0x62:0x65:2028)` | RmInitDone timeout |
| `(0x62:0x40:2674)` | Init failure on a second GPU, root cause unknown, see [4.7](#rminit-2674) |
| `(0x62:0xffff:2119)` | The `0x29` / FBPA-open path, see [4.8](#rminit-2119) |
| `0x24:0x72:1220` | Cold-boot downstream stage at 10 GB, in `RmInitNvDevice`; a separate stage from the BAR2 case |

### 5.3 SEC2 reset PLM observable values { #codes-resetplm }

Reported at address `0x8403C4`. The GSP analog is `0x001103d0`.

| Value | Meaning |
|---|---|
| `0xff` | Clean; bus mastering healthy |
| `0x8f` | `secure_teardown` ran (bits `[6:4]` went `0x7 -> 0x0`) |
| `0x00cf` | The driver-still-loaded partial-fire state |

*(Confidence: medium. This is consistently used as the observable marker across many runs, but the
register's identity at `0x8403C4` was challenged in-channel on the grounds that the address does
not appear on the fuse list, and it was never independently documented. See
[Register reference](../unlock/register-reference.md).)*

FLR clears the SEC2 reset-PLM taint: `0x8f` becomes `0xff`.

### 5.4 `0xbadfXXXX` reads { #codes-badf }

`0xbadfXXXX` reads are **privilege or existence failures, not stored data**.

| Pattern | Meaning | Examples |
|---|---|---|
| `0xbadf5040` | Read blocked by a privilege level mask | `FECS_FEAT_OVERRIDE 0x00409664`, `FECS_FEAT_READOUT_1 0x00409668`, the second feature-override group `0x00823830`-`0x0082383c` |
| `0xbadf1100` | PRI target does not exist | `PMC_BOOT_42 0x0000a800`, `FUSE_OPT_FBIO_OLD 0x00021c14` on GA100 |
| `0xbadf20NN` (`0xbadf2010`-`0xbadf201b`) | Target exists but the FBPA partition is floorswept | low byte encodes the instance |
| `0xbadf1002` | GA10x variant of the not-present sentinel | at `0x00021C14` |
| `0xbadf5108` | AON secure scratch read from PL0 | `0x001180f8`, `0x001182d0` |
| `0xbadf` prefix generally | Priv-blocked readback | e.g. the GSP falcon launch block `0x110280`-`0x110298` |

*(Confidence: high for the three main families, medium for the exact taxonomy wording.)*

### 5.5 Other driver error codes { #codes-other }

**`NV_ERR_INSUFFICIENT_RESOURCES (0x1A)`** on a CUDA failure points at the WPR meta second pass not
picking up the unlocked capacity. Check with `dmesg | grep -E 'Xid|NVRM.*rror'`.
*(Confidence: medium; from the shipped guide, with no independent reproduction plus fix.)*

**`NV_ERR_RESET_REQUIRED (0x62)` from `NVA06F_CTRL_CMD_STOP_CHANNEL`** at `nv_gpu_ops.c:11190`
appears when allocations cross the device's real decode boundary (observed at 40 GB on an
over-provisioned card):

```text
nvAssertOkFailedNoLog: Assertion failed: Reset required [NV_ERR_RESET_REQUIRED] (0x00000062)
  returned from pRmApi->Control(...)
```

The card is fine below the boundary and fails on channel stop once allocations cross it.

**`EXCI 0x0a (MISS_INS)`** after writing DMEM post-FLR means the Booter is no longer resident in
IMEM: the FLR removed it.

---

## 6. Silent failures and operational gotchas { #silent }

### 6.1 Bus mastering cleared by `rmmod nvidia` { #bus-master }

> [!CAUTION]
> **The single most operationally important gotcha in the corpus**
>
> **`rmmod nvidia` clears PCI `COMMAND.BusMaster`.** The SEC2 Booter fetches the ROP payload from
> system memory by DMA, so with bus mastering off it fetches nothing, runs with an empty payload,
> executes no ROP and faults out. **Nothing in the log mentions DMA.** Every write simply
> bounces, and the only visible artifact is `resetPLM` going `0xff -> 0x8f`.

**Diagnostic:**

```bash
setpci -s <bdf> COMMAND
# 0x0102 = broken (bus master bit clear)
# 0x0546 = good   (bit 2, Bus Master, set)
```

**Fix.** Re-enable bus mastering before firing:

```bash
sudo setpci -s <bdf> COMMAND=0x0546
```

An `ensure_bus_master()` call was added to `prepare()` in the refire tool so it self-heals. After
the fix, `resetPLM` stayed `0xff` on every single fire.

This gotcha applies to the standalone / driverless tooling. The shipping in-driver patch runs
inside a live driver, where bus mastering is on by definition.

### 6.2 Firing with the driver still loaded { #driver-loaded }

**Symptom.**

```text
PLMs: 1/9 open (fired 8 closed)
resetPLM=0x00cf
PRE  CFG1=0x02449000 LMR=0x00000288
POST CFG1=0x02449000 LMR=0x00000288
decode=0x70000300
CSTATUS=0/24
WPR2=['0x2779000','0x27fee00']
STATE NOT CLEAN, FLR + re-fire
EXIT_CODE=1
```

**Fix.** Unload the driver. With the driver unloaded, the identical command gave
`PLMs: 9/9 open (fired 0 closed)`, `resetPLM=0x00ff`, `CSTATUS=20/24` and `READY`. Failure and fix
were observed back to back on the same hardware within minutes.

### 6.3 Tearing the driver down properly { #teardown }

`modprobe -r` alone is not enough. The working order:

```bash
systemctl stop nvidia-persistenced      2>/dev/null || true
systemctl disable nvidia-persistenced   2>/dev/null || true
systemctl stop gdm3 sddm lightdm display-manager 2>/dev/null || true
killall -9 Xorg Xwayland nvidia-persistenced     2>/dev/null || true
sleep 2
modprobe -r nvidia-uvm      2>/dev/null || true
modprobe -r nvidia_drm      2>/dev/null || true
modprobe -r nvidia_modeset  2>/dev/null || true
modprobe -r nvidia          2>/dev/null || true
sleep 2
lsmod | grep -q nvidia && rmmod -f nvidia_uvm nvidia_drm nvidia_modeset nvidia
```

Every step is guarded so a missing service does not abort the script under `set -e`. The FLR that
follows is:

```bash
echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset
sleep 3
```

This harness ran nine unlock cycles.

### 6.4 The module will not unload { #module-stuck }

The nvidia module frequently refuses to unload anyway, leaving:

```text
nvidia 15835136 2
drm    753664 7 drm_kms_helper,drm_display_helper,nvidia,drm_buddy,i915,ttm
```

The dependency on `i915` through `drm` is a practical reason to run unlock work on a headless or
non-NVIDIA-display host. Module sizes on that system: `nvidia_modeset` 2248704,
`nvidia_uvm` 2039808. *(Confidence: medium; repeatedly observed within one run log.)*

### 6.5 DMEM writes silently dropped { #dmem-locked }

**Cause.** Once `nvidia.ko` has booted the SEC Falcon into heavy-secure (HS) mode,
`DMEM_PRIV_LEVEL_MASK` (`0x00840284`) write protection reads 0 and all DMEM writes are dropped.
DMEM can be neither read nor written while the Falcon is in HS.

**Detection.**

```text
mask    = read32(0x00840284)
rd_prot = mask & 0x7
wr_prot = (mask >> 4) & 0x7      # 0 means LOCKED
```

Functional test: write `0xDEADBEEF` to DMEM`[0x000]` via DMEMC0/DMEMD0 and read it back.

**Fix.** An ENGINE reset:

```text
wr32(PSEC_ENGINE, 0x1); sleep 10 ms; wr32(PSEC_ENGINE, 0x0)
poll DMATRFCMD for IDLE && !FULL
poll DMACTL & 0x6 == 0                 # scrub complete
check SCP_CTL_P2PRX bit 3 (SFK_LOADED)
check KFUSE_LOAD_CTL bit 0 set, bit 1 clear
```

Or power-cycle and run before loading `nvidia.ko`.

### 6.6 Firing alongside a live CUDA context { #live-cuda-context }

Firing the unlock alongside a live CUDA context **does** open the FB-geometry PLMs (`0x00100b10`:
`0xffffff8f -> 0xffffffff`), but then hangs `nvidia-smi`, because leaving SEC2 halted in HS
(spin-park) destabilises the driver's health path. Recovery is a `FALCON_ENGINE` reset, which
clears the HS state without touching FB contents. *(Confidence: medium.)*

### 6.7 Writing secure registers outside the `0x82xxxx` block { #resetplm-8f }

Writing any secure register outside `0x82xxxx` re-raises the SEC2 reset PLM to `0x8f`, which blocks
the stock `kflcnReset` and makes the second Booter Load fail with `0x65`. Named offenders:
`0x1183A4` (capacity scratch), `0x9A0204` (FBPA strap), `0x1FA8xx` (WPR). Only `0x82xxxx` writes
are exempt. **This is why compute unlocked easily and memory did not.**
*(Confidence: medium; reproducible symptom with a consistent `resetPLM=0x8f` marker, but the
register identity was challenged.)*

### 6.8 Separating the PLM open from the geometry write with a reset { #flr-between }

**Symptom.** The same pipeline succeeds on the compute PLM, but the CFG1 write at `0x009A0204`
bounces, reading back the stock `0x2449000` instead of `0x2779000` on all three attempts, ending
`Pipeline complete: 0/1 GPU(s) unlocked`.

**Cause.** The FB-geometry PLMs are **not** in the always-on (AON) island, while the
feature-override PLM `0x00823804` **is**. A staged pipeline that opens PLMs, does an FLR, then
writes geometry loses the FB-geometry PLM state across the FLR.

**Fix.** Never separate the PLM open from the geometry write with a reset. The shipping patch does
both inside one GSP boot. See [Recovery: what survives a reset](recovery.md#state-persistence).

### 6.9 Deleted or mismatched firmware { #firmware-deleted }

**Symptom.** A multi-day "model degradation" that could not be reproduced, with
`SEC2 MBOX0 = 0x0` (the Booter never loaded at all).

**Cause.** `/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` had been deleted, and a
`.04` userspace `nvidia-smi` would not trigger GPU init on a `.03` module.

**Fix.** Restore the version-matched firmware directory and use a version-matched `nvidia-smi`.
Restoring firmware immediately reproduced the previous working state.

**Practical lesson recorded at the time:** when an agent modifies the driver, keep a diff or
changelog, because reinstalling a fresh driver silently discards every needed injection.

### 6.10 A stale patched `gsp_tu10x.bin` on disk { #stale-firmware }

If cmpunlocker's **firmware-patching predecessor** was ever used on the machine, `gsp_tu10x.bin`
must be restored to stock before running the in-driver patch:

```bash
GSP_DIR=/lib/firmware/nvidia/610.43.03
sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
```

**Why.** The driver saves the firmware's signature as "stock" during boot. If the firmware is still
patched, it saves the **exploit payload** instead, and the clean GSP-RM boot then DMAs the wrong
ROP chain. The success line is `SEC2_DEBUG: saved stock signature (4096 bytes)`.

### 6.11 Repeated driver loads walk the error code forward { #nondeterminism }

Repeated CPU-RM driver loads progressively clean a dirty device and walk the error code forward.
A single-variable control showed that a single MMU-invalidate run stayed at `0x24`, so the earlier
`0x24 -> 0x25` advance came from the **double load** (CPU-RM's own partial init cleaning up state),
not from the MMU write. This also explains observed nondeterminism: the dirty-device cleanup is
non-deterministic and results are noisy per fire. *(Confidence: medium; the underlying cleanup
mechanism was never confirmed.)*

---

## 7. Build failures { #build }

`build.sh` runs under `set -euo pipefail`, so any failing hunk aborts the build. It downloads
`https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz` into
`driver/.build/` (cached, overridable via `CMPUNLOCKER_BUILD_DIR`), deletes and re-extracts a clean
tree every run, applies `patches/*.patch` in lexicographic order with `patch -p1`, then runs
`make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`. Build time is around 5 minutes
*(single report, hardware-dependent)*.

| Failure | Cause | Fix |
|---|---|---|
| `Installed driver is X, but cmpunlocker requires one of: 610.43.03,610.43.02.` | Exact-string version whitelist | Install 610.43.03 or 610.43.02 nvidia-open |
| Kernel header error, `/lib/modules/$(uname -r)/build` missing | Headers not installed for the **running** kernel | Install matching headers, or boot the kernel you built for |
| Patch hunk rejected | Wrong upstream tarball, or a stale `.build/` tree | The script re-extracts every run; check you are on the branch you think you are |
| `python3: command not found` | `build.sh` needs `python3` | Install it. **No PyYAML is used on master**, and there is **no explicit GCC version check** in the shipping scripts |
| No network on first install | Tarball download | Pre-seed `driver/.build/` |
| `No initramfs tool found, rebuild manually before rebooting` | Neither `update-initramfs`, `dracut` nor `mkinitcpio` present | Rebuild the initramfs by hand, see [3.4](#initramfs) |
| Build breaks after swapping kernels on Ubuntu via mainline | Kernel-swapping broke the NVIDIA 610 open driver build | Use a distribution kernel |

Prerequisites worth stating explicitly: Secure Boot off (the modules are unsigned), nvidia-open
610.43.0x (the proprietary driver "has different boot paths and cannot be patched the same way"),
**Linux only** (the GSP boot path is Linux-specific), root, and modules compiled for the running
kernel. The build installs **five** modules (`nvidia.ko`, `nvidia-modeset.ko`, `nvidia-uvm.ko`,
`nvidia-drm.ko`, `nvidia-peermem.ko`), mode `0644`, into
`/lib/modules/$(uname -r)/updates/cmpunlocker/`. Only `nvidia.ko` carries unlock code; the other
four are stock rebuilds.

Because patches are applied by glob, dropping a third-party diff named `0007-*.patch` into
`driver/patches/` composes cleanly with the unlock series. That is the documented mechanism for
layering a P2P patch. See [Driver patches](../unlock/driver-patches.md).

**Removing before installing.** The maintainer's rule when switching branches is "always remove
the old one before adding the new one." One tester who cloned the Gen2 branch and installed on top
of an existing install reported it did not work, and uninstalling first fixed it. This is guidance,
not a hard law: at least two other testers installed on top successfully. Removal-first is the
*supported* path. *(Confidence: medium; no one identified the differentiating factor.)*

---

## 8. PCIe Gen2 problems { #gen2 }

> [!WARNING]
> **Experimental**
>
> **No PCIe Gen2 patch ships on `master`.** Patches `0007-pcie-gen2.patch` and
> `0008-pcie-gen2-probe-retrain.patch`, plus `tools/retrain.sh`, exist only on branches `Gen2`,
> `far`, `debug-gen2` (0007 and `tools/retrain.sh` only) and `deced`. `verify.sh` is a separate
> tool and ships on `Gen2`, `far`, `deced` and `multiple-cards`, see [11.2](#verify-sh).
> Everything in this section applies to experimental branches.

Remember that **speed and width are separate achievements**. Gen1 to Gen2 is a driver and firmware
unlock. Going beyond x4 width requires physically soldering 24 0402 X7R capacitors onto lanes 4 to
15. Neither one changes the other. See [PCIe Gen2](../unlock/pcie-gen2.md) and
[Physical mods](../operations/physical-mods.md).

### 8.1 Gen2 works on some machines and not others { #gen2-hardcoded-bdf }

**Root cause: a hardcoded PCI address `0a:00.0`.** The hardcode is in the *userspace helper*
`tools/retrain.sh`, in three places (`SYS=/sys/bus/pci/devices/0000:0a:00.0`,
`GPU, UP = "0a:00.0", "09:01.0"`, and the `resource0` path), **not** in the kernel patches:
`0008-pcie-gen2-probe-retrain.patch` is byte-identical between `Gen2` and `deced`.

Branch `deced` (commit message: "Stupid mistake - it appears to be hardcoded") replaces it with
`find_gpu_bdf()`, which discovers the card via `lspci -d 10de:20c2` / `lspci -d 10de:2082`, waits
up to 120 s for `resource0` and `nvidia-smi -L`, and derives the upstream bridge with
`readlink -f`. **Branches `Gen2` and `far` still contain the hardcode.**

### 8.2 PCIe still at Gen1 after install { #gen2-still-gen1 }

**First check: IOMMU passthrough.** The `Gen2`, `far` and `deced` installers all append
`intel_iommu=on iommu=pt` (Intel) or `amd_iommu=on iommu=pt` (AMD) to the kernel command line via
`/etc/default/grub` or `/etc/kernel/cmdline`, replace conflicting entries, back the file up to
`*.cmpunlocker.bak`, regenerate the boot config, and each branch's own `remove.sh` restores it.
`--no-iommu` opts out. Master touches none of this, so uninstall with the same branch you installed
from. IOMMU must also be enabled in BIOS/UEFI (VT-d / AMD-Vi / SVM).

**Second check: is your checkout current?** Before 2026-07-29 the Gen2 patches were branch-only,
and users repeatedly failed because they were on `master`. Gen2 is in `master` now, so a checkout
predating that merge is the thing to rule out.

**Third: the retrain may have bailed out.** The standalone `retrain.sh` bails early with a printed
reason in four cases:

| Message | Condition |
|---|---|
| `retrain: BAR0 dead; skip` | BAR0 or CYA reads `0xFFFFFFFF` |
| `retrain: DIS_G2 still set; skip` | `DIS_G2` (BAR0 `0x8c2c0` bit 2) still set |
| `retrain: Cap Gen1; skip` | Link capability below Gen2 |
| `retrain: preconditions failed; skip` | Post-write preconditions failing |

It also exits **silently** with status 0 if `nvidia-smi` is unavailable, memory reads `[N/A]`, the
link is already Gen2, or max link gen is not 2, 3 or 4.

The in-driver retrain runs at probe time and polls for up to 2 seconds (20 attempts × 100 ms) after
`msleep(50)`. It clears BAR0 `0x8c2c0` bit 2 (DIS_G2), forces `0x8c040` bits `[19:18]` to 2, writes
`0x00000006` to `0x8872c`, sets `PCI_EXP_LNKCTL2_TLS_5_0GT` on both the GPU and the upstream
bridge, then sets `PCI_EXP_LNKCTL_RL` (retrain link) on the upstream bridge. Its failure prints:

```text
CMP Gen2: no upstream PCIe bridge; skipping link retrain
CMP Gen2: cannot map BAR0; skipping link retrain
CMP Gen2: PCIe capability access failed (%d); skipping link retrain
```

plus the false negative described in [2.7](#benign-retrain-false-negative).

### 8.3 Root port will not change speed { #gen2-root-port }

> [!WARNING]
> **Experimental**
>
> Documented but not independently confirmed. If `sudo dmesg | grep "SEC2_DEBUG.*Root port"`
> says "upstream port not valid", the chipset driver did not enumerate the upstream port;
> the suggested workaround is `setpci -s <root_port> <offset>.w=0002` followed by a link
> retrain. If "Root port LnkCtl2" shows the write but speed stays 1, the root port may not
> support directed speed change; the suggested fix is a root-port-initiated retrain via
> `setpci -s <root_port> <link_ctrl>.w` with bit 5 set. **No measurement of either workaround
> succeeding appears anywhere in the corpus.**

### 8.4 Gen2 in a virtual machine { #gen2-vm }

Memory and compute unlock work under Proxmox passthrough (one operator passed through eight 8 GB
cards and all unlocked). **The PCIe Gen2 link-speed change does not work in a VM** as of
2026-07-24, acknowledged by the maintainer. Whether the retrain sequence needs config-space or
link-layer access that the hypervisor intercepts is not established.

> [!NOTE]
> **Open problem**
>
> One host (ASUS X99-A, LGA2011) reported Gen2 x1 in one slot only and Gen1 x4 in the others,
> after trying IOMMU/virtualization settings and all four slots. It was reported on 2026-07-27,
> the same day the hardcoded-BDF discovery landed. Slot dependence is exactly what a hardcoded
> BDF produces, so this is likely already fixed on branch `deced`, but it was never confirmed.

### 8.5 The `RMPcieLinkSpeed` split { #gen2-linkspeed }

> [!NOTE]
> **Open problem**
>
> Two branch families ship different registry values and each author believed theirs was right:
> `debug-gen2` and `Gen2` write
> `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`, while `far` and `deced` write
> `…=0x2` (introduced by a commit titled "Remove clamp link to Gen1"). The `Gen2` branch, whose
> README claims Gen2 works, ships `0x1`. **No A/B boot test exists.** Neither value should be
> presented as canonical. One three-way boot comparison on one card would settle it.

---

## 9. Black screens { #black-screen }

### 9.1 Black screen when running the unlock script { #black-screen-script }

> [!NOTE]
> **Open problem**
>
> A tester reported a black screen when running the unlock script on 2026-07-20. Their own
> unverified hypothesis was a wrong-driver installation, and they declined to debug further.
> Both testers in that thread were on hosts limited to PCIe Gen3. Nothing was established.

### 9.2 Headless boot in general { #headless }

The CMP 170HX has no video output, so some boards will not POST with it as the only card (an
ASRock X370-I was reported to refuse). Plan for a third display-capable card, or confirm the board
boots headless. See also [Host will not boot](#no-post).

---

## 10. Runtime, CUDA and workload failures { #runtime }

### 10.1 Xid 31, MMU fault, region violation { #xid31 }

**Symptom.** `Xid 31` MMU fault with `FAULT_INFO_TYPE_REGION_VIOLATION`; the card is unusable in
CUDA until reboot. A capture shows:

```text
ENGINE GRAPHICS HUBCLIENT_FE  faulted @ 0x7fad_3a200000 ... ACCESS_TYPE_VIRT_WRITE
ENGINE CE2      HUBCLIENT_HSCE2 faulted @ 0xf_f7400000 ... ACCESS_TYPE_PHYS_WRITE
```

**Cause.** Allocation past the usable top of the unlocked window. The physical address
`0xf_f7400000` is 63.86 GiB, right at the top of the 64 GB window.

**Fix.** Offload one fewer LLM layer to that GPU. Recovery requires a full reboot. *(The suggested
fix was not confirmed applied.)*

> [!NOTE]
> **Xid 31 is not, on its own, the 80 GB signature**
>
> At 80 GB, kernels touching more than roughly 40 GB cause fatal GPU loss, independent of power
> limit. Reported Xid codes include Xid 31 (described as harmless) and Xid 154 after CUDA memory
> tests; the dominant reported symptom is hangs. Xid 31 alone was suggested by a bystander and
> was not corroborated as *the* signature by the operator with the failing card. The rest of the
> adjudicated 80 GB picture: reports ~81920 MiB / 85,545,582,592 bytes, and `cudaMalloc` of
> 77 GiB succeeds. See [80 GB](../frontier/80gb.md).

### 10.2 Xid 45 after killing a CUDA job { #xid45 }

Killing a live CUDA verification kernel with SIGKILL can wedge the card with Xid 45 and force a
reset cycle. The published tooling carries the caution: run in the **foreground**, never SIGKILL
mid-run; Ctrl-C between kernel launches is fine. Dense fill/check kernels run for a long time on a
64 GB card (over a million 64 KB pages), so the temptation to background and kill them is real.
*(Confidence: medium; stated as a hard-won operational warning, no dmesg capture attached.)*

### 10.3 Xid 154 on the over-provisioned configuration { #xid154 }

Xid 154 is the dominant failure after CUDA memory tests on the over-provisioned 80 GB
configuration, limiting the card to one CUDA context per fire. One tester could only get GSP-RM
working, not CPU-RM; another had to cold-cycle the entire system between attempts rather than just
reload the driver. Both agreed the memory is physically reachable by CUDA: the open problem is
retention and stability, not addressability. Independently reproduced by two testers on different
hardware.

> [!NOTE]
> **Open problem**
>
> The 4 GB/channel decode re-enable and the CUDA `719` → Xid 45 → Xid 154 chain are two outcomes
> of the same atomic fault and could not be separated. An atomic to a page above 40 GB (held on
> the host by UVM, since the device only decodes 40 GB) faults; CPU-RM migrates the page up and
> re-enables 4 GB/channel, but the same fault poisons the CUDA context, surfacing as
> `719 unspecified launch failure`, then Xid 45, then Xid 154. Attempts at a clean handoff (flip
> the decode with a small managed "keeper", free it, then allocate non-managed 77 GiB) kept
> erroring. A related knob noted but untested: `PDB_PROP_GPU_RECOVERY_SQUASH_XID154`.

### 10.4 vLLM crashes at high memory utilization { #vllm }

**Symptom.** A vLLM card crash at `gpu-memory-utilization 0.95`.

**Cause.** The unlocked geometry exposes 65052 MB with only 64733 MB actually available, so
headroom at 0.95 is thin.

**Fix.** Drop to 0.9, which recovered the card. A separate long multi-card session saw a transient
"GPU requires reset" only at 0.95 with a huge context, self-recovering. **Guidance: keep
utilization at or below 0.90.** *(Confidence: medium-high.)* See
[LLM inference](../operations/llm-inference.md).

### 10.5 `cuInit` returns 999 everywhere { #cuinit999 }

**Symptom.** `cuInit` returns 999 for every framework while `nvidia-smi` still reports healthy.

**Cause.** Repeatedly `kill -9`ing live multi-GPU jobs leaves roughly 32 zombie CUDA processes and
wedges the host CUDA runtime.

**Fix.** Host reboot. **This is not fixable inside a container.** Do not `kill -9` live multi-GPU
jobs.

Across the same full 8-card session, with hundreds of 60-second health samples, there were **0**
hard faults. This is an operator-induced failure, not a hardware one.

### 10.6 Allocating past the genuinely usable capacity { #alloc-crash }

Allocating past the genuinely usable capacity crashes benchmarks even when `nvidia-smi` reports the
larger number. `llama-server` holding 37798 / 47400 / 53960 MiB on three cards each reporting
81920 MiB crashed the run. After a reboot the same rig loaded roughly 32 GB per card
(27734 / 31758 / 32754 MiB) and the benchmark completed, with results about the same as the
10 GB → 40 GB configuration.

### 10.7 Memory errors under burn-in { #burn-errors }

**Symptom.** A card unlocked beyond its stable geometry accumulates memory errors within minutes of
a compute burn:

```text
2.1%  proc'd: 777 (12153 Gflop/s)   errors: 24433  (WARNING!)  temps: 85 C
```

Errors appear in the first couple of minutes. The 12153 Gflop/s figure shows the compute unlock was
active. **The stable 10 GB → 40 GB configuration passes a 5-minute gpu-burn cleanly**, and the
8 GB → 64 GB configuration is stable and in production.

> [!NOTE]
> **Open problem**
>
> Whether those 85 °C gpu-burn errors were thermal or a memory overclock was never settled. One
> position: "too hot, dial it back". The other: "85 °C is within spec", with core and memory
> temperatures within a few degrees of each other; a third observer called it an HBM hardware
> error. Others reported zero errors on two cards staying below 73 °C. The branch author's actual
> resolution was to lower the memory multiplier, not to demand better cooling. The failing card
> was a Samsung-memory part. What would settle it: the same card at the same multiplier with
> forced cooling holding below 70 °C. See [Thermals](../hardware/thermals.md).

> [!WARNING]
> **Experimental**
>
> A related claim, advanced with low confidence and hedged by its own author, is that "normal
> stress tests don't load an unlocked card because the fuses rely on the math being thrown at
> them." Never tested against a known-good workload. It matters because it determines whether
> gpu-burn is an adequate stability test. Context: one tester could not push a card above 68 W
> with a standard stress test before patching.

### 10.8 `nvidia-smi --gpu-reset` refuses { #gpu-reset-busy }

> [!NOTE]
> **Open problem**
>
> `nvidia-smi --gpu-reset` fails with "GPU is being used by another process" when no process
> holds it. **Unresolved.** Next step: enumerate holders with `fuser -v /dev/nvidia*` and
> `lsof /dev/nvidia*`, and check for a leaked `nvidia-persistenced` or a zombie CUDA process of
> the kind that produces `cuInit=999`.
>
> Related recovery friction reported in the same window: after a cold boot the card sometimes
> needed its PCIe power cable physically unplugged and re-seated, and a CUDA alias test leaks its
> allocation, so an SBR-recover plus driver reload is required between runs.

### 10.9 Unlock works but CUDA does not { #cuda-clean-host }

**Triage step that resolved one case: move the card to a clean host.** The original host's software
stack was the suspected culprit; the root cause was never confirmed. Before blaming the unlock,
test the card in a clean host. *(Confidence: medium.)*

Note that the card runs on **stock** Linux NVIDIA drivers with no patch at all
(`nvidia-driver-570` plus CUDA 12.8 on Ubuntu 24.04 works out of the box), so "is the card
driveable" and "is the card unlocked" are separate questions that can be tested separately.

### 10.10 Patches that exist purely as runtime workarounds { #runtime-patches }

Three shipping patches exist only to fix post-unlock runtime faults. If you are debugging a
runtime fault, know that these are already applied:

| Patch | What it does |
|---|---|
| 0004 `bar0-pramin-clamp` | Clamps the BAR0 PRAMIN window back to the stock 8 GB-based offset `(0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN)` whenever `fbAddrSpaceSizeMb > 0x2000` on `0x20C2`/`0x2082`, so the window does not fall outside the real aperture after the geometry change. Note a 10 GB card at 10240 MB already exceeds `0x2000`, so the clamp engages there too |
| 0005 `ce-scrub-workarounds` | Forces `*pteKind = NV_MMU_PTE_KIND_GENERIC_MEMORY` (instead of `..._COMPRESSIBLE_DISABLE_PLC`) and disables the VAS-based CE scrubber path for these cards |
| 0006 `persistent-sw-state` | Sets `NV_FLAG_PERSISTENT_SW_STATE` for both device IDs, so RM does not tear down software state when the last client closes |

---

## 11. Multi-card rigs { #multicard }

### 11.1 The unlock silently does nothing on a multi-GPU rig { #multicard-silent }

**Symptom.** All five 8 GB cards stayed stock after warm and cold reboot; the verifier reported
`MISSING` and `✗ 0000:01:00.0: not found in nvidia-smi` for every BDF (01:00.0, 05:00.0, 06:00.0,
07:00.0, 12:00.0), each `20c2 / 8gb` expecting ~65536 MiB, plus `! No SEC2_DEBUG lines in dmesg`.

**Cause.** The early tooling had no multi-card handling. The same person's single-card rig worked
with the same drivers.

**Fix.** For the two-card HiveOS case: `remove.sh`, reboot, reinstall. Both cards then came up at
40 GB. A `multiple-cards` branch and a `verify.sh` were subsequently added, but **have not merged
into master**: master's `install.sh` still takes only the first matching `lspci` line via `head -1`.

See also [depmod picking one module arbitrarily](#module-resolution), which is a separate
multi-GPU failure with the same outward appearance.

### 11.2 Reading `verify.sh` output { #verify-sh }

> [!WARNING]
> **Experimental**
>
> `verify.sh` exists only on branches `deced`, `multiple-cards`, `Gen2` and `far`. Three
> diagnostic strings are worth recognising:
>
> * `<bdf>: not found in nvidia-smi` with status `MISSING`
> * `No SEC2_DEBUG lines in dmesg (logs may have rotated; unlock can still be OK if memory is unlocked)`
> * the fatal `<N> GPU(s) failed unlock verification. Cold reboot if modules were just installed.`
>
> It maps device IDs to profiles (`20c2 -> 8gb -> 65536 MiB`, `2082 -> 10gb -> 40960 MiB`) and
> reads an inventory from `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`.

### 11.3 The HiveOS ten-card case { #hiveos }

> [!NOTE]
> **Open problem**
>
> HiveOS beta 24.04 with ten CMP 170HX and nvidia 610.43.03: `install.sh` finishes cleanly but
> the patched module is not loaded after a cold reboot. Nothing beyond re-running the install was
> tried, and no fix was posted. Most promising next step: run the three-step triage
> ([3.5](#triage-three-step)), specifically comparing `/sys/module/nvidia/srcversion` with the
> cmpunlocker `.ko`, and check whether HiveOS's own driver package reinstalls over the patched
> module, or whether the initramfs / DKMS ordering puts stock first. Both candidates are named
> but unconfirmed.

See [Multi-GPU](multi-gpu.md).

---

## 12. Host and hardware-level failures { #host }

### 12.1 The server will not boot with the cards fitted { #no-post }

**Symptom.** No beep codes, no motherboard diagnostic LEDs, "No display adapter, press F1" already
disabled.

**Cause in the documented case: nothing to do with the GPUs.** Changing PCI slots renamed the
network interface (from an `XXX5XX` to an `XXX6XX` predictable name), so the box booted headless
but had no IP.

**Fix.** Fix the network configuration.

**General advice given while diagnosing:** use the correct power cables (the ATX/EPS-style
connector without adapter, the PCIe connector with adapter), try one GPU at a time, and expect two
to three restarts after a hardware change. The card takes one EPS 8-pin (300 W rated) and needs a
2 × PCIe-to-EPS adapter. See [Power and PSU](../operations/power-and-psu.md).

### 12.2 Virtual machines { #vm }

**Proxmox passthrough requires SeaBIOS, not UEFI/OVMF.** UEFI produces RM init / adapter failures
that mimic the exploit simply not working. One person spent significant time on "rm init adapt
failures" before realising their old working VM was SeaBIOS; a second member immediately recognised
it as the cause of their own non-reproductions.

At least some exploit development was done against a GPU passed through to a QEMU Q35 VM rather
than bare metal (`QEMU Standard PC (Q35 + ICH9, 2009)`, BIOS
`rel-1.17.0-0-gb52ca86e094d-prebuilt.qemu.org 04/01/2014`, GPU at `0000:01:00`, Ubuntu kernel
6.8.0-136-generic, nvidia-modeset 580.159.03). The crash there emitted a bad-frame-pointer stack
unwind warning, and the fault path ran through `nvidia_drm`/`nvidia_modeset`
(`EnumerateGpus -> AllocateDevice -> nvkms_open_gpu`).

Memory and compute unlock work in a VM; PCIe Gen2 does not, see [8.4](#gen2-vm).

### 12.3 The card dropped off the PCIe bus { #off-bus }

**Symptom.** A card that ran for an hour, then dropped off the PCIe bus permanently and is no
longer detected. If BAR0 reads `0xffffffff`, the card is off-bus. Try the recovery ladder in
[Recovery](recovery.md#reset-ladder) first, including
`echo 1 > /sys/bus/pci/devices/$BDF/remove` followed by `echo 1 > /sys/bus/pci/rescan`.

If it never comes back, the cause may be hardware. One fully diagnosed instance on
A100/170HX-class hardware:

**Cause.** A dead GS7155NVTD 3.3 V LDO shorting the `PS_5V_PGOOD` net to 5 ohms, which prevented
the MP1475DJ 5 V converter from starting. Visible as hiccup-mode protection: a momentary SW-node
pulse of dozens of nanoseconds retrying after dozens of microseconds.

**Diagnostic path.** The 12 V input inductors to ground read high impedance and the slot 12 V
showed no short (ruling out a gross core short); the core-side output inductors showed no voltage
and no switching; after desoldering the MP1475DJ, its empty-footprint Pin 1 (Power Good) to ground
measured 5 ohms.

**Fix.** Replace MP1475DJ and GS7155NVTD, then jumper `PS_5V_PGOOD` over from U816. Result: 3V3_SEQ
returned, switching resumed, NVVDD 1.0 V and PEXVDD returned, and the GA100 was redetected on
PCIe. `PS_5V_PGOOD` feeds the SN74LV1T08 AND gates that sequence PEXVDD, NVVDD, 1V35 and 1V8, and
enables the LDO producing 3V3_SEQ.

> [!CAUTION]
> **Bench-test a freshly soldered GS7155NVTD before trusting it**
>
> Swap the 7.68 kilohm feedback resistor for 20 kilohm to reprogram the output from 3.3 V to
> 1.8 V, inject 3.3 V on the 5 V rail, confirm a regulated 1.8 V, then restore the 7.68 kilohm
> part. The hazard defended against is an **open feedback pin** (a likely cold-joint failure on
> QFN), which makes the LDO see permanent undervoltage and drive its output to maximum, putting
> the full 5 V onto the 3.3 V rail and destroying almost all 3.3 V logic. Rework datum for this
> 8 to 12 layer board: hot air at 420 °C for 2 minutes before any chip can be removed. The
> GS7155NVTD is a GSTEK QFN part whose full datasheet is under NDA.

### 12.4 Card condition on arrival { #dirty-cards }

Ex-mining cards arrive filthy: heavy dust, rusted PCIe brackets, salt crust inside heatsinks,
exposed gold fingers with no connector cover. They need cleaning, repaste and new thermal pads
before use. **Cosmetic condition is not a predictor of unlock failure:** one visibly filthy card
unlocked to 64 GB cleanly on the first try. *(Confidence: high for the condition reports across
multiple independent unboxings; medium for the "not a predictor" conclusion, which rests on one
sample. No batch-level unlock yield was ever published.)*

> [!WARNING]
> **Experimental**
>
> An unchallenged but undata-backed position holds that chronically under-cooled HBM "should be
> dead by now unless it's had a very low operating time", and that HBM degrades fast once past
> the safe temperature. Many cards may be near-zero-hours because the CMP 170HX launched in
> September and the market was unprofitable by November. No failure-rate or temperature data
> supports or refutes this.

"Defective batch" language from sellers during the late-July 2026 price spike is **not** evidence
of a real hardware defect population: it was used as a cancellation excuse against listings that
had shown working cards. No defective card was actually shipped or diagnosed in the documented
cases.

### 12.5 Uninterruptible-sleep wedge that survived cold boots { #d-state }

**Symptom.** A 10 GB card stuck in an "uninterruptible sleep" state that survived about five cold
reboots and prevented Ubuntu from shutting down.

**Cause.** An autoloading patched kernel driver, not the card.

**Fix.** Boot with the card disconnected (or `blacklist nvidia`), then clean up.
*(Confidence: medium; root cause identified by the affected tester after recovery.)*

A harder variant of this is discussed honestly in [Recovery](recovery.md#bricking).

---

## 13. Escalation and reporting { #escalation }

`install.sh` writes a timestamped log to `logs/install_YYYYMMDD_HHMMSS.log`; `remove.sh` writes
`logs/remove_YYYYMMDD_HHMMSS.log`. `remove.sh` falls back to `/tmp` if the repository directory is
not writable; `install.sh` does not, and aborts at startup instead. **Attach the newest install log to any support request.**

A useful report contains:

1. OS and version, kernel (`uname -r`)
2. GPU model and driver version
3. `lspci -nn` for the whole host
4. `sudo dmesg | grep SEC2_DEBUG` in full
5. The latest install log
6. `cat /lib/modules/$(uname -r)/updates/cmpunlocker/{driver_version,card_profile,unlock_geometry}`

Response is single-operator and slow: the first documented Gen2 ticket waited about 10.5 hours for
a first reply (opened 06:21, replied 16:59).

---

## 14. Symptoms with no known fix { #unsolved }

> [!NOTE]
> **Open problem**
>
> These are recorded so they are not rediscovered as new. None has a published resolution.
>
> * **`NVRM initialization error` after cold reboot** on Ubuntu 24.04, kernel 6.8.0-111-generic,
>   driver 610.43.03. Cold reboots (which had previously cleared a srcversion mismatch for the
>   same tester) did not help. `SEC2_DEBUG` lines were present and registers were being written,
>   which points at a post-register-write initialization failure rather than a failed unlock
>   chain, but nobody pursued it. Next step: capture the full dmesg **after** the `SEC2_DEBUG`
>   block, including the `normal BooterLoad status` line and any `RmInitAdapter` triplet, to
>   place the failure in the sequence.
> * **Kernel panic plus reboot on the first `insmod` of a normal driver immediately after running
>   the exploit.** Asked once on 2026-07-01, never answered. Next step: capture the panic (serial
>   console or `pstore`); the fault path in the comparable QEMU capture ran through
>   `nvidia_drm`/`nvidia_modeset`, so unloading those before the fire is a cheap first test.
> * **Does the absence of an iGPU or BMC display device upset the GSP?** One observation, no
>   confirmation, no contradiction, no error string. An A/B on one machine with the BMC display
>   device disabled in BIOS would answer it.
> * **80 GB instability: `cuda_memtest` passes over all 80 GB once immediately after a reboot and
>   fails on every subsequent retry.** Power limiting to 100 W and the power-delivery hypothesis
>   have both been eliminated. The reboot dependence points at memory training or refresh state.
>   This is the most concrete remaining lead on the 80 GB profile. See
>   [80 GB](../frontier/80gb.md).
> * **The Ubuntu-versus-Arch memory unlock failure.** One reading: a memory-address conflict
>   between two PCIe devices, where a non-170HX, non-2080 device (presumably an M.2 SSD) tried to
>   read at an address the IOMMU rejected. The affected tester's own reading: the Ubuntu install
>   was simply misconfigured. Only the workaround (a different OS install on a different M.2 SSD)
>   is verified. Recommended first diagnostic at the time: `lspci -s 06:00.0`.
> * **The expected number of PLMs.** Standalone tooling reports "9/9 open" and a reviewer expected
>   "0 or 26, not 1". The shipping in-driver path opens exactly 4. These are different PLM
>   inventories, but nothing in the record maps the 9-entry or 26-entry lists onto the shipping
>   4-entry `plmTable`.

For the full list of unresolved items across the whole project, see
[Open questions](../frontier/open-questions.md) and the [status board](../frontier/status-board.md).

---

## Related pages

* [Recovery](recovery.md): cold boot, FLR, SBR, and what actually persists
* [Verify](verify.md): the post-install checklist in full
* [Install](install.md): the supported procedure
* [Uninstall](uninstall.md): `remove.sh` and manual rollback
* [Driver versions](driver-versions.md): which versions are supported and boot-tested
* [Multi-GPU](multi-gpu.md): multi-card installs
* [Privilege level masks](../unlock/privilege-level-masks.md): what the PLM table does
* [Register reference](../unlock/register-reference.md): every register named on this page
* [Dead ends](../history/dead-ends.md): hypotheses that were tried and refuted
