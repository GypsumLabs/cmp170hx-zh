# Quick start

**What this page covers:** the shortest correct path from a stock CMP 170HX to an unlocked one,
using the shipping `cmpunlocker` `master` branch. Exact commands, expected output at every step,
and a failure-to-page routing table. Nothing here is experimental: everything below is in the
shipping tree.

The whole procedure is: install nvidia-open `610.43.03` (or `610.43.02`), run `sudo ./install.sh`,
cold boot, check `nvidia-smi`. On an 8 GB card you end at **65536 MiB**; on a 10 GB card you end at
**40960 MiB**. Full SM compute throughput is unlocked at the same time. The change is
register-only: no flash is written, and `sudo ./remove.sh --yes` puts the card back to stock.

> [!WARNING]
> **What quick start does NOT get you**
>
> - **No PCIe Gen2.** Shipping `master` contains patches `0001` through `0006` only. The Gen2
>   patches (`0007-pcie-gen2.patch`, `0008-pcie-gen2-probe-retrain.patch`) live on unreleased
>   branches. You will stay at Gen1, 2.5 GT/s. See [PCIe Gen2](../unlock/pcie-gen2.md).
> - **No x16 link width.** The card ships with the AC-coupling capacitors for lanes 4-15
>   depopulated, so it trains at x4. Restoring x16 needs 24 hand-soldered 0402 220 nF X7R
>   capacitors. That is a physically separate achievement from link speed and it never changes
>   the PCIe generation. See [physical mods](../operations/physical-mods.md).
> - **No 80 GB on a 10 GB card.** That configuration was built, tested and abandoned as
>   unstable. See [the 80 GB tier](../frontier/80gb.md).
> - **No ECC, no NVLink, no peer-to-peer.** ECC and NVLink are OTP-fuse disabled with no known
>   lever. Peer-to-peer is absent as well, but whether that is a fuse or a driver gate has never
>   been determined. See [peer-to-peer](../frontier/p2p.md).
> - **Linux only.** The unlock rides the Linux GSP boot path. Windows has a completely different
>   driver model.
>
> Expect roughly **0.85 GB/s** of host-to-device bandwidth at Gen1 x4 (measured, clpeak). That is
> the main practical cost of skipping the two hardware/branch projects above.

---

## Prerequisites checklist

| Requirement | Check | Notes |
|---|---|---|
| x86-64 Linux, root | `id -u` returns `0` under `sudo` | `install.sh` dies with `Run as root: sudo ./install.sh` |
| A CMP 170HX | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082'` | `20c2` = 8 GB SKU, `2082` = 10 GB SKU |
| **nvidia-open 610.43.03 or 610.43.02** | `cat /proc/driver/nvidia/version` | Exact string match. Anything else aborts the install |
| Kernel headers | `ls -d /lib/modules/$(uname -r)/build` | Package `linux-headers-$(uname -r)` or `kernel-devel` |
| Secure Boot **disabled** | `mokutil --sb-state` | Patched modules are unsigned |
| Network access | first install only | `build.sh` downloads the matching stock `open-gpu-kernel-modules` tarball |
| `python3`, `curl`, `patch`, `make`, a C toolchain | `command -v python3 curl patch make gcc` | No PyYAML is used on `master`, and there is no explicit GCC version check in the shipping scripts |
| An initramfs tool | `update-initramfs`, `dracut` or `mkinitcpio` | Without one the build warns and stock modules can win at boot |
| Power: 1 x EPS 8-pin | 300 W rated connector | Needs 2 x PCIe-to-EPS adapter. See [power and PSU](../operations/power-and-psu.md) |
| Cooling: forced air | passive heatsink, no fan on the card | See [cooling](../operations/cooling.md) |
| A display-capable GPU, or a board that POSTs headless | the 170HX has no video output | At least one board was reported refusing to POST with only a 170HX fitted |

> [!NOTE]
> **The card works without any unlock**
>
> A stock 170HX drives fine on ordinary distro drivers (`nvidia-driver-570` plus CUDA 12.8 on
> Ubuntu 24.04 was confirmed). `nvidia-smi` names it `NVIDIA Graphics Device`, compute capability
> 8.0, because the driver PCI ID table has no marketing name for `0x20C2`. Use that as a
> pre-flight sanity check before you touch anything. Being driveable and being unlocked are
> separate matters.

---

## Step 0: confirm which card you have

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'
nvidia-smi --query-gpu=memory.total,driver_version --format=csv
```

| PCI ID | Physical | Unlocks to | CFG1 `0x009a0204` | LMR `0x00100ce0` |
|---|---|---|---|---|
| `10de:20c2` | 8 GB | **64 GB** (65536 MiB) | `0x02779000` | `0x0000020B` |
| `10de:2082` | 10 GB | **40 GB** (40960 MiB) | `0x02669000` | `0x0000028A` |
| `10de:20b0` | varies | **nothing** | n/a | n/a |

`install.sh` detects all three IDs, but the in-driver gate `_kgspSec2PostblTimingEnabled()` accepts
only `0x20C2` and `0x2082`. A `20b0` card installs cleanly and then never unlocks; the installer
warns `This card reports 0x20b0; install will continue, but unlock may not activate.`
More detail: [identify your card](identify-your-card.md).

---

## Step 1: install nvidia-open 610.43.0x

Use whatever your distribution provides, or the NVIDIA `.run` installer, as long as the result is
the open kernel modules at exactly `610.43.03` or `610.43.02`. Verify before continuing:

```bash
cat /proc/driver/nvidia/version
# NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  610.43.03  Release Build ...
nvidia-smi
```

`610.43.03` is the default build target (first line of `driver/VERSION`).

> [!NOTE]
> **Open problem**
>
> Whether `610.43.02` or `610.43.03` is more reliable was asked repeatedly and never answered.
> Successful unlocks exist on both. `610.43.03` is merely first in the list.

Consider pinning the driver package at 610 so a distribution upgrade cannot silently move you off a
supported version. See [driver versions](../procedures/driver-versions.md).

## Step 2: get the tool and run it

```bash
git clone https://github.com/amoghmunikote/cmpunlocker
cd cmpunlocker
sudo ./install.sh
```

Force the profile only if auto-detection is wrong or `nvidia-smi` is unavailable:

```bash
sudo ./install.sh --profile=8gb     # 8 GB card  -> 64 GB geometry
sudo ./install.sh --profile=10gb    # 10 GB card -> 40 GB geometry
```

Auto-detection reads `nvidia-smi --query-gpu=memory.total` and buckets it:
`>= 60000 MiB -> 8gb` (already-unlocked card), `35000-59999 -> 10gb`, `7680-8704 -> 8gb`,
`9728-10752 -> 10gb`. Anything else aborts with `Could not detect 8GB vs 10GB card`.

**Expected output**, six numbered steps, everything tee'd to `logs/install_YYYYmmdd_HHMMSS.log`:

```text
Step 1/6: Verifying root privileges
✓ Running as root
Step 2/6: Detecting CMP 170HX GPU
✓ GPU detected: 0000:0b:00.0 (10de:20c2)
Step 3/6: Selecting card memory profile
✓ Detected stock/reported memory 8192 MiB → profile 8gb
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
Step 4/6: Verifying nvidia-open (610.43.03,610.43.02)
✓ NVIDIA driver 610.43.03 is supported
✓ Kernel headers present for 6.8.0-136-generic
Step 5/6: Building and installing patched modules
...
Step 6/6: Done
Profile: 8gb → expect ~65536 MiB after unlock
```

The profile you pass is metadata only. On shipping `master` both geometries are baked into the
patched `kernel_gsp.c` and selected at GSP boot from the live PCI device ID, so a mis-detected
profile writes a wrong label but cannot produce the wrong geometry.

Two build-log lines that look alarming and are not:
`Skipping BTF generation for .../nvidia*.ko due to unavailability of vmlinux` (kernel debug
metadata, irrelevant), and `[drm] No compatible format found` (the card has no display outputs).

## Step 3: cold boot

`build.sh` attempts a hot module reload. If it succeeds you may skip this, but a cold boot is the
reliable path and is what the installer recommends.

```bash
sudo shutdown -h now
```

Then power off at the PSU or unplug the cable, wait **60 seconds** for capacitor discharge and WPR2
to clear, and power on. A warm reboot leaves WPR2 up and is not equivalent.

## Step 4: verify

```bash
nvidia-smi
# 8 GB card:  ~65536 MiB
# 10 GB card: ~40960 MiB

sudo dmesg | grep SEC2_DEBUG
cat /lib/modules/$(uname -r)/updates/cmpunlocker/card_profile   # 8gb or 10gb
```

A healthy `SEC2_DEBUG` trail prints, in order: the WPR meta dump, `saved WPR2 lo=... hi=...`, four
`PLM[n] ...` lines, a `PLMs:` summary, the `POST-WRITE` line, the `WPR meta updated`
line, `normal BooterLoad status=0x0`, a final `POST-BooterLoad verify` and then the static-info
before/after pair.
The PLM lines have this shape (one archived line verbatim, the rest follow the same format):

```text
SEC2_DEBUG: PLM[3] FEAT(0x823804) attempt=0 status=0xffff reg=0xffffffff
```

Expected readbacks:

| Line | Register | Expected value |
|---|---|---|
| `PLM[0] WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` (**not** `0xffffffff`) |
| `PLM[1] FBPA` | `0x009a0148` | `0xffffffff` |
| `PLM[2] WPR` | `0x001fa7c4` | `0xffffffff` |
| `PLM[3] FEAT` | `0x00823804` | `0xffffffff` |
| `POST-WRITE SS0` | `0x0082381c` | `0x88888888` |
| `POST-WRITE SS1` | `0x00823820` | `0x00000008` |
| `POST-WRITE CFG1` | `0x009a0204` | `0x02779000` (8 GB) / `0x02669000` (10 GB) |
| `POST-WRITE LMR` | `0x00100ce0` | `0x0000020B` (8 GB) / `0x0000028A` (10 GB) |

> [!NOTE]
> **Ignore three scary-looking lines**
>
> - `status=0xffff` on every PLM line is **normal**. The payload Booter run is supposed to be
>   rejected; success is judged by the register readback, never by the status. `0x31` from
>   `s_executeBooterUcode_TU102` is the same story.
> - `SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload`
>   is the normal path. That file is a development override hook.
> - Third-party docs claiming "all PLMs must show `0xffffffff`" are wrong. `WPR_CFG` is
>   `0xfffff0ff` by design.
>
> The one line that **must** read zero is `SEC2_DEBUG: normal BooterLoad status=0x0`.

Compute unlock is confirmed by throughput, not by a clock field. Sustained SM clock on an unlocked
card is 1410 MHz (1470 MHz at `nvidia-smi -pl 300`). `nvidia-smi --query-gpu=clocks.max.sm` reports
1935 MHz, but that is a reported maximum field of low confidence, not an achievable clock: the
VBIOS table maximum is 1695 MHz. Use a real benchmark instead. See
[performance](../operations/performance.md).

---

## If this fails, go here

| Symptom or exact message | Likely cause | Go to |
|---|---|---|
| `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)` | card not enumerating, board did not POST headless, seating or power | [identify your card](identify-your-card.md), [troubleshooting](../procedures/troubleshooting.md) |
| `Installed driver is X, but cmpunlocker requires one of: 610.43.03,610.43.02.` | unsupported driver version | [driver versions](../procedures/driver-versions.md) |
| `Secure Boot is enabled. Disable it before installing unsigned patched modules.` | Secure Boot on | [install](../procedures/install.md) |
| `Kernel headers missing for <kver>` | no `linux-headers-$(uname -r)` | [install](../procedures/install.md) |
| `Could not detect 8GB vs 10GB card` | `nvidia-smi` absent or an out-of-range `memory.total` | re-run with `--profile=8gb` or `--profile=10gb` |
| Build stops during download | no network, or the tarball tag is unreachable | [install](../procedures/install.md) |
| `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win` | depmod resolution or initramfs still holds stock modules | [troubleshooting](../procedures/troubleshooting.md) |
| `Loaded nvidia srcversion (X) != patched (Y)` | stock module still resident after the hot reload | cold boot, then [troubleshooting](../procedures/troubleshooting.md) |
| `nvidia-smi` still shows 8192 / 10240 MiB after a reboot | PLM open did not take, or stock module is running | full power-off cold cycle, then [troubleshooting](../procedures/troubleshooting.md) |
| **No** `SEC2_DEBUG` lines at all | the patched module never ran | [troubleshooting](../procedures/troubleshooting.md), [verify](../procedures/verify.md) |
| `WPR2 already up` / `RmInitAdapter failed! (0x62:0x40:2028)` / `No devices were found` | GSP boot left WPR2 programmed | [recovery](../procedures/recovery.md) |
| Xid 119, `Timeout after 60s ... Expected function 4097 (GSP_INIT_DONE)` | GSP never reached RM init | [recovery](../procedures/recovery.md) |
| `nvidia-smi` reports "driver/library version mismatch" | userspace does not match the loaded module | [troubleshooting](../procedures/troubleshooting.md) |
| No card in a multi-GPU box unlocks | a stock and a patched `nvidia.ko` both under the single `updates` search path, so depmod loads one of them arbitrarily | [multi-GPU](../procedures/multi-gpu.md) |
| Xid 31, `FAULT_INFO_TYPE_REGION_VIOLATION`, card unusable until reboot | allocation ran past the usable top of the window | [LLM inference](../operations/llm-inference.md), [troubleshooting](../procedures/troubleshooting.md) |
| Link still reports Gen1 x4 | expected on `master`: no Gen2 patch ships there | [PCIe Gen2](../unlock/pcie-gen2.md) |

Before opening a support ticket, collect `sudo dmesg | grep SEC2_DEBUG` and the newest
`logs/install_*.log`. Expect a slow, single-operator response.

---

## Rolling back

```bash
sudo ./remove.sh --yes
```

The uninstaller is `remove.sh` and it requires `--yes` or `-y`. **There is no `uninstall.sh`**,
despite what one branch's `INSTALLATION.md` says. It deletes
`/lib/modules/*/updates/cmpunlocker/` on every kernel, re-runs `depmod`, rebuilds the initramfs,
clears legacy systemd and `/opt/cmpunlocker` leftovers, and reloads stock modules. Reboot if the
GPU does not come back cleanly. One tester reported both cards returning to normal mining
afterwards, which is the basis for calling the change non-destructive. No permanent brick has ever
been confirmed. Full detail: [uninstall](../procedures/uninstall.md).

When switching between branches, the maintainer's advice is remove first, then install. That is
guidance rather than a hard rule: one tester hit a failure that uninstalling first fixed, and at
least two others installed on top successfully.

---

## Where to go next

- [Verify properly](../procedures/verify.md), including whether the unlocked VRAM is real and not
  an aliased fold.
- [Risks](risks.md) before you run this on a card you cannot replace.
- [Memory geometry](../unlock/memory-geometry.md) and
  [compute throttle](../unlock/compute-throttle.md) for what the four register writes actually do.
- [Driver patches](../unlock/driver-patches.md) for a hunk-by-hunk read of all six patches.
- [Glossary](glossary.md) for PLM, WPR2, SEC2, GSP-RM, FBPA, LMR and CFG1.
