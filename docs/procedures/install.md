# Installing the unlock

**What this page covers.** The complete, supported installation procedure for the shipping
`cmpunlocker` driver patch on a CMP 170HX: what must be true before you start, the exact
commands, what `install.sh` and `driver/build.sh` do at every step, how the card profile is
chosen (and when to force it), why a cold reboot matters, and what a correct run looks like on
screen and in `dmesg`.

The short version: install nvidia-open **610.43.03** or **610.43.02**, disable Secure Boot,
install kernel headers, then run `sudo ./install.sh` from a clone of the repository and cold
boot. The script downloads NVIDIA's stock `open-gpu-kernel-modules` tarball for your driver
version, applies six patches, builds five kernel modules, and installs them into
`/lib/modules/$(uname -r)/updates/cmpunlocker/`. Nothing is written to the card's VBIOS and no
firmware file on disk is modified. An 8 GB card (`10de:20c2`) comes back reporting **65536 MiB**
and a 10 GB card (`10de:2082`) comes back reporting **40960 MiB**.

The unlock itself is described in [How the unlock works](../unlock/how-it-works.md) and the
patch series in [Driver patches](../unlock/driver-patches.md). This page is only the operating
procedure.

---

## Prerequisites

| Requirement | Detail | Enforced by |
|---|---|---|
| Operating system | Linux, x86-64. There is **no Windows path** for this unlock. | Not checked; the patch only exists for the Linux GSP boot path |
| Privilege | root (`sudo ./install.sh`) | `install.sh` step 1, `build.sh` |
| Card | `10de:20c2` (8 GB) or `10de:2082` (10 GB). `10de:20b0` is detected but is **not** unlocked. | `install.sh` step 2 (`lspci` grep), and the in-driver device gate |
| Driver | nvidia-**open** `610.43.03` (default) or `610.43.02`, exact string match | `install.sh` step 4 and `driver/build.sh`, both against `driver/VERSION` |
| Kernel headers | `/lib/modules/$(uname -r)/build` must exist | `install.sh` step 4 and `build.sh` |
| Secure Boot | disabled; the patched modules are unsigned | `install.sh` step 4, via `mokutil --sb-state` |
| Network | reachable `github.com` on first install for the source tarball | `curl -L --fail` in `build.sh` |
| Toolchain | `python3`, `patch`, `make`, `curl`, a working kernel build environment | `build.sh` checks `python3` only |

Notes that matter in practice:

- **nvidia-open, not the proprietary driver.** The closed driver has different boot paths and
  cannot be patched the same way. The card *drives* fine on stock drivers (a tester ran
  `nvidia-driver-570` plus CUDA 12.8 on Ubuntu 24.04 out of the box, and
  `nvidia-driver-535-server` on Ubuntu 22.04 was also reported), but being driveable and being
  unlocked are separate things. See [Driver versions](driver-versions.md).
- **The Secure Boot check is conditional.** It only runs if `/sys/firmware/efi` exists **and**
  `mokutil` is on `PATH`. On a non-EFI machine, or a machine without `mokutil` installed, the
  check is silently skipped and you can still end up with modules the kernel refuses to load.
  The symptom in `dmesg` is
  `nvidia: module verification failed: signature and/or required key missing - tainting kernel`.
- **No PyYAML, no GCC version check.** `build.sh` uses plain `python3` with the standard library
  and performs no compiler version test. The "python3 with PyYAML / gcc 13+" prerequisite that
  circulates online comes from the third-party `unlock-cmp-170hx` guide repository, not from these
  scripts; a vestigial `requirements.txt` pinning `pyyaml>=5.1` also sits on six cmpunlocker
  branches, though no branch script ever imports `yaml`. The leaked prebuilt package's README
  asks only for root access and kernel headers. A working build was reported on Ubuntu 26.04 LTS
  with kernel 7.0.0-27-generic (`Gen2` branch, survived multiple reboots).
- **Do this on a machine you can afford to break.** Driver-patch iteration on bare metal is
  destructive enough that one developer reported reinstalling the OS after each botched
  `nvidia.ko` deploy. See [Risks](../start/risks.md).

> [!CAUTION]
> **Leftover state from the firmware-patching era**
>
> If this machine ever ran `cmpunlocker`'s **firmware-patching predecessor**, restore
> `gsp_tu10x.bin` to stock *before* installing the driver patch:
>
> ```bash
> GSP_DIR=/lib/firmware/nvidia/610.43.03
> sudo cp "$GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak" "$GSP_DIR/gsp_tu10x.bin"
> ```
>
> The patched driver saves the firmware's signature as "stock" during boot. If the firmware on
> disk is still patched, the driver saves the exploit payload instead and the clean GSP-RM boot
> then DMAs the wrong ROP chain. The success line to look for afterwards is
> `SEC2_DEBUG: saved stock signature (4096 bytes)`.

---

## The commands

```bash
git clone https://github.com/amoghmunikote/cmpunlocker
cd cmpunlocker
sudo ./install.sh
```

Force a profile when auto-detection is wrong or `nvidia-smi` is unavailable:

```bash
sudo ./install.sh --profile=8gb     # 8 GB physical card  -> 64 GB geometry
sudo ./install.sh --profile=10gb    # 10 GB physical card -> 40 GB geometry
sudo ./install.sh --help
```

Only those three flag forms are accepted (`--profile=8gb|8GB|10gb|10GB`, `-h`, `--help`). Any
other argument exits 1 with `Unknown argument: <arg>`.

Everything is tee'd to `logs/install_<YYYYmmdd_HHMMSS>.log` inside the checkout, so run from a
writable directory.

---

## What `install.sh` does, step by step

The script is six numbered steps under `set -euo pipefail`.

### Step 1/6: root

`[[ "${EUID}" -eq 0 ]]` or die with `Run as root: sudo ./install.sh`.

### Step 2/6: GPU detection

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

No match is fatal: `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)`. Note the
`head -1`: **master is a single-card installer**. It records only the first matching BDF (bus,
device, function address) and the device ID from that one line. For rigs with more than one card
see [Multi-GPU](multi-gpu.md).

If the detected device ID is neither `20c2` nor `2082`, the script warns and **continues**:

```text
! In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.
! This card reports 0x20b0; install will continue, but unlock may not activate.
```

That is accurate. The in-driver gate `_kgspSec2PostblTimingEnabled()` accepts only `0x20C2` and
`0x2082`, so a `20b0` card gets fully patched modules that never fire for it. The README's older
"unlock is `0x20C2`-gated" phrasing is stale; `0x2082` has been a first-class target since commit
`0f9aca5` "Unlock isn't gated anymore".

### Step 3/6: card profile

Either the `--profile` override, or `detect_card_profile()`, which reads
`nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1` and maps four
windows:

| Reported `memory.total` | Selected profile | Why the window exists |
|---|---|---|
| `>= 60000` MiB | `8gb` | re-install on an **already unlocked** 64 GB card |
| `35000`-`59999` MiB | `10gb` | re-install on an already unlocked 40 GB card |
| `7680`-`8704` MiB | `8gb` | stock 8 GB card (8192 MiB) |
| `9728`-`10752` MiB | `10gb` | stock 10 GB card (10240 MiB) |
| anything else | fatal | prints `unknown:<mib>`, then `Could not detect 8GB vs 10GB card. Re-run with --profile=8gb or --profile=10gb` |

The banner then prints one of:

```text
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)
==> Unlock geometry: 40GB (CFG1=0x02669000 LMR=0x0000028A)
```

> [!WARNING]
> **Auto-detection is unsafe on mixed-GPU hosts**
>
> `detect_card_profile()` takes the **first GPU in `nvidia-smi` order**, which is not
> necessarily the CMP that `lspci` found. A host with an RTX 3080 10 GB alongside an 8 GB
> CMP 170HX was reproduced by at least two people detecting "10GB" from the 3080. A separate
> report has other CMP SKUs (a 50HX) misdetected as a 10 GB 170HX. On current `master` the
> consequence is only wrong metadata, but on a host with any other NVIDIA card the safe habit
> is to **always pass `--profile` explicitly**. If the first GPU reports a size outside all
> four windows (a 24 GB card, say), the install dies outright.

### Step 4/6: Secure Boot, driver version, headers

- Secure Boot: if `/sys/firmware/efi` exists and `mokutil` is present and
  `mokutil --sb-state` matches `SecureBoot enabled`, die with
  `Secure Boot is enabled. Disable it before installing unsigned patched modules.`
- Driver version detection order:
  1. `/proc/driver/nvidia/version`
  2. `nvidia-smi --query-gpu=driver_version`
  3. a directory probe for `/lib/firmware/nvidia/<supported-version>/`
  4. the highest-sorting directory under `/lib/firmware/nvidia/`
- The detected string must match a line in `driver/VERSION` exactly, otherwise:
  `Installed driver is <detected>, but cmpunlocker requires one of: 610.43.03,610.43.02.`
- `/lib/modules/$(uname -r)/build` must exist, otherwise
  `Kernel headers missing for <kver>. Install linux-headers-<kver> or kernel-devel.`

### Step 5/6: build and install

`install.sh` chmods and execs `driver/build.sh` with `CMPUNLOCKER_DRIVER_VERSION` and
`CMPUNLOCKER_CARD_PROFILE` in the environment. See the next section.

### Step 6/6: next steps banner

Prints the expected post-unlock size, then four numbered next steps: a cold-reboot reminder
(`sudo shutdown -h now`) and three verification commands (`nvidia-smi`,
`sudo dmesg | grep SEC2_DEBUG`, and
`nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader`), followed by the path to the
install log.

---

## What `driver/build.sh` does

1. **Re-validates** root, the version against `driver/VERSION`, the patches directory, kernel
   headers, and the presence of `python3`.
2. **Downloads** `https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz`
   with `curl -L --fail` into `driver/.build/` (override the cache location with
   `CMPUNLOCKER_BUILD_DIR`). A cached tarball is reused. No NVIDIA code ships in the repository.
3. **Extracts clean** every run: `rm -rf "${SRC_DIR}"` then untar, so a failed previous build
   cannot contaminate the next.
4. **Applies every `driver/patches/*.patch`** in glob (lexicographic) order with `patch -p1`.
   The shipping series is six files totalling 37,415 bytes:

   | Patch | Bytes | What it does |
   |---|---|---|
   | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 | the entire unlock: payload, [PLM](../unlock/privilege-level-masks.md) loop, SS0/SS1/CFG1/LMR writes, `fb_length` rewrite |
   | `0002-booter-verify.patch` | 3,988 | soft-fails four boot asserts, prints the post-BooterLoad readback |
   | `0003-late-pma.patch` | 10,580 | registers the new memory above 8 GiB with the physical memory allocator |
   | `0004-bar0-pramin-clamp.patch` | 861 | clamps the BAR0/PRAMIN window to the stock 8192 MB offset |
   | `0005-ce-scrub-workarounds.patch` | 1,642 | forces the copy-engine scrubber into physical mode |
   | `0006-persistent-sw-state.patch` | 603 | sets `NV_FLAG_PERSISTENT_SW_STATE`, replacing the old watchdog daemon |

   Because the loop is a plain glob under `set -euo pipefail`, dropping a third-party diff named
   `0007-*.patch` into that directory composes cleanly and any failing hunk aborts the build.
   That is how the P2P patch is layered (see [P2P](../frontier/p2p.md)).
5. **Runs the profile step.** An inline Python script checks whether the patched `kernel_gsp.c`
   already contains all six markers (`SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID`,
   `..._10GB_PCI_DEVICE_ID`, `0x02779000U`, `0x02669000U`, `0x0000001000000000ULL`,
   `0x0000000A00000000ULL`). On `master` all six are present, so it prints
   `runtime device-id geometry (profile metadata=64GB)` and exits without editing anything. The
   regex-substitution branch below it is a dead legacy fallback for single-SKU patches.
6. **Writes three metadata files** into `/lib/modules/$(uname -r)/updates/cmpunlocker/`:
   `driver_version`, `card_profile` (`8gb` / `10gb`), `unlock_geometry` (`64GB` / `40GB`).
   **Nothing in the kernel modules reads any of them.** They exist for humans and for
   `verify.sh`. The only file the patched kernel reads at boot is the optional
   `/lib/firmware/nvidia/ga100/gsp/dmem.bin`.
7. **Builds**: `rm -rf src/nvidia/_out src/nvidia-modeset/_out kernel-open/conftest`, `make clean`,
   then `make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build`. Reported build time is
   **2 to 5 minutes on a modern CPU**. That range comes from two written distributions (the leaked
   prebuilt package's README says "~2-5 min", a circulated 40 GB unlock guide says "~5 minutes on a
   modern CPU"); nobody posted a timed measurement.
8. **Installs five modules** at mode `0644` into
   `/lib/modules/$(uname -r)/updates/cmpunlocker/`: `nvidia.ko`, `nvidia-modeset.ko`,
   `nvidia-uvm.ko`, `nvidia-drm.ko`, `nvidia-peermem.ko` (found by `find`, excluding
   `*/conftest/*`). Only `nvidia.ko` carries unlock code; the other four are stock rebuilds
   shipped so the module set stays version-consistent.
9. **`depmod -a "${KVER}"`**. Module precedence is plain depmod ordering:
   `updates/cmpunlocker/` > `updates/dkms/` > `kernel/drivers/`, which is why no `dpkg-divert`
   is needed.
10. **Rebuilds the initramfs** with the first available of `update-initramfs -u -k`,
    `dracut --force --kver`, `mkinitcpio -P`, else warns
    `No initramfs tool found, rebuild manually before rebooting`. Master's `build.sh` carries no
    comment here, but the branch copies (`memory`, `ecc`, `housekeeping`, `PG199`) explain the
    reasoning verbatim: NVIDIA often loads from initramfs, and if only `updates/dkms` is packed
    there, stock modules win at boot even when depmod prefers `updates/cmpunlocker`. That is a
    plausible route to "installed but memory still shows stock size", but it is the scripts'
    reasoning rather than a diagnosed field failure: the words *initramfs*, *initrd*, *dracut* and
    *mkinitcpio* appear nowhere in the chat corpus. Only after the initramfs step does
    `build.sh` run its empirical check that the patched module actually wins:
    `modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'`, warning
    `Resolved nvidia.ko is not under updates/cmpunlocker/, stock may still win`.
11. **Attempts a hot reload**: stops `nvidia-persistenced` and `nvidia-fabricmanager`,
    `modprobe -r` on `nvidia_drm`, `nvidia_uvm`, `nvidia_modeset`, `nvidia`, then reloads. It
    then compares `/sys/module/nvidia/srcversion` against
    `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko` and, on mismatch, warns
    `Loaded nvidia srcversion (X) != patched (Y)` and clears its own success flag.

> [!WARNING]
> **No integrity check on the downloaded tarball**
>
> `build.sh` fetches the NVIDIA tag tarball with `curl -L --fail` and caches it with no
> checksum or signature verification anywhere in the tree. On an untrusted network, verify the
> cached tarball yourself before the first build.

---

## The cold reboot

A warm reboot is not enough and neither is the hot reload in the general case. The instruction
throughout the project, including in the leaked prebuilt distribution's own README, is a **cold**
reboot: full power off, then power on.

```bash
sudo shutdown -h now
# then power on
```

Reasons, in order of how often they bite:

1. The unlock runs inside the patched module's GSP bootstrap. If the running `nvidia.ko` is still
   the stock one because the hot reload failed or the initramfs still holds stock modules, the
   unlock never executes.
2. Modules in use (X11, a display manager, a persistenced daemon, a CUDA process) block
   `modprobe -r`, and `build.sh` prints `Could not unload nvidia modules (in use), cold reboot
   required`.
3. Memory geometry does **not** survive a function-level reset or a power cycle, so a clean cold
   start is the well-defined state in which the patched driver re-applies everything from
   scratch. Only SS0, SS1 and the FEAT PLM at `0x00823804` live in the always-on island.

If the hot reload did succeed, `build.sh` says so and you can verify immediately. If it did not,
the script prints the recovery instructions itself.

---

## What a correct run looks like

The following is composed from the scripts' own literal output strings (not a single captured
transcript), so treat the variable parts as placeholders.

```text
╔════════════════════════════════════════╗
║               cmpunlocker              ║
╚════════════════════════════════════════╝

━━━ Step 1/6: Verifying root privileges ━━━
✓ Running as root

━━━ Step 2/6: Detecting CMP 170HX GPU ━━━
✓ GPU detected: 0000:0b:00.0 (10de:20c2)

━━━ Step 3/6: Selecting card memory profile ━━━
✓ Detected stock/reported memory 8192 MiB → profile 8gb
==> Unlock geometry: 64GB (CFG1=0x02779000 LMR=0x0000020B)

━━━ Step 4/6: Verifying nvidia-open (610.43.03,610.43.02) ━━━
✓ NVIDIA driver 610.43.03 is supported
✓ Kernel headers present for 6.8.0-136-generic

━━━ Step 5/6: Building and installing patched modules ━━━
[INFO]  Building against open-gpu-kernel-modules 610.43.03
[ OK ]  Using cached tarball .../driver/.build/open-gpu-kernel-modules-610.43.03.tar.gz
[INFO]  Applying unlock patches...
[INFO]    0001-sec2-postbl-plm-ss-cfg.patch
...
[ OK ]  All patches applied
runtime device-id geometry (profile metadata=64GB)
[ OK ]  Memory profile 8gb: CFG1=0x02779000 LMR=0x0000020B fb=0x0000001000000000 (64GB)
[ OK ]  Modules built
[ OK ]  Installed nvidia.ko
[ OK ]  depmod complete
[ OK ]  initramfs rebuilt
[INFO]  modprobe will load: /lib/modules/6.8.0-136-generic/updates/cmpunlocker/nvidia.ko
[ OK ]  Patched NVIDIA modules loaded
[ OK ]  Build and install finished. Verify with: nvidia-smi

━━━ Step 6/6: Done ━━━
Profile: 8gb → expect ~65536 MiB after unlock
```

Immediately after boot, the definitive evidence is in the kernel log:

```bash
sudo dmesg | grep SEC2_DEBUG
```

A healthy 8 GB unlock produces these lines. For scale, the archived single-card 8 GB capture
contains **29** `SEC2_DEBUG` lines in total, and the archived two-card Gen2-branch boot log
contains **134**:

```text
SEC2_DEBUG: saved stock signature (4096 bytes)
SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
SEC2_DEBUG: PLMs: FEAT=0xffffffff FBPA=0xffffffff WPR=0xffffffff WPR_CFG=0xfffff0ff
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
SEC2_DEBUG: late PMA extension status=0x0
SEC2_DEBUG: POST-BooterLoad verify PLM=... SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b
```

> [!NOTE]
> **Do not use the line count as a pass/fail test**
>
> Line counts are not a reliable cross-build fingerprint. Recorded values: **29** on the archived
> single-card 8 GB capture, **134** on the archived two-card Gen2-branch `610.43.03` log, 34
> (Gen1 build) and 80 (Gen2 build) from the reporting tools, and `SEC2_DEBUG lines=152` printed
> by `pcielink.sh` on two separate two-card Gen2 rigs. Do not read a mismatch as a failed
> install. The register readback lines above are the criterion.

Three things routinely alarm first-time installers and are all normal:

- `WPR_CFG=0xfffff0ff` is a **pass**. Only three of the four PLMs target `0xffffffff`.
- Per-attempt Booter status `0xffff` is expected on every payload pass, success or not. The
  register readback is the only valid success criterion.
- `not found (0x59)` for `dmem.bin` is benign; the built-in payload is used.

Read [Verifying the unlock](verify.md) next for the full log decode and the memory-versus-compute
distinction. If something is wrong, go to [Troubleshooting](troubleshooting.md).

---

## Reinstalling, upgrading and switching branches

The maintainer's stated rule is **remove first, then install** when switching between branches:
"In fact, I would always recommend to remove the old one before adding the new one." One tester
who cloned the `Gen2` branch and installed on top of an existing install reported it did not
work, and uninstalling first fixed it. At least two other testers installed on top with no
problem, and the informal consensus was that most people are "just sending it on top". The
failure is real but not universal, and nobody identified the differentiating factor.
Removal-first is the *supported* path:

```bash
sudo ./remove.sh --yes     # in the OLD checkout
sudo ./install.sh          # in the NEW checkout
```

See [Uninstalling](uninstall.md).

---

## Environment-specific notes

> [!WARNING]
> **Experimental: virtualisation**
>
> Memory and compute unlock work under **Proxmox GPU passthrough**: one operator passed
> through eight 8 GB CMP 170 cards and all unlocked. Two constraints are recorded:
>
> - Use **SeaBIOS, not UEFI/OVMF**. UEFI produces RM init and adapter failures that look
>   exactly like the exploit simply not working. This was root-caused first-hand and
>   immediately corroborated by a second person who had been unable to reproduce results.
> - The PCIe Gen2 link-speed change did **not** work in a VM as of 2026-07-24, acknowledged by
>   the maintainer as an open debugging item. See [PCIe Gen2](../unlock/pcie-gen2.md).

> [!NOTE]
> **Open problem: does a missing display device upset the GSP?**
>
> One operator observed that GSP seemed less happy on systems with no iGPU and no BMC display
> device, compared with systems that have one. Nobody responded with a confirmation, a
> contradiction, or an error string. An A/B on one machine with the BMC display device disabled
> in BIOS, capturing `dmesg`, would settle it.

Windows is a dead end for this patch: the unlock is implemented against the Linux open kernel
modules and the GSP boot path is Linux-specific. A Windows machine can *drive* a 170HX with a
GRID or datacenter driver and an injected hardware ID, but that gets you a working card, not an
unlocked one.

---

## Related pages

- [Quick start](../start/quick-start.md) for the condensed version
- [Identify your card](../start/identify-your-card.md) to confirm which SKU you have first
- [Verify](verify.md), [Troubleshooting](troubleshooting.md), [Recovery](recovery.md)
- [Multi-GPU](multi-gpu.md) if the rig has more than one card
- [Driver versions](driver-versions.md) for the 610-only constraint and the unreleased ports
- [Driver patches](../unlock/driver-patches.md) for what each patch actually changes
