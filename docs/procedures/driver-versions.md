# Driver versions: what is supported, and why

## What this page covers

Which NVIDIA driver versions the CMP 170HX unlock builds against, why the list is that short,
what happens if you point the installer at anything else, and what the unreleased backport branch
actually offers for 595, 590 and 580.

The short answer: **shipping `master` supports exactly two versions, `610.43.03` (the default)
and `610.43.02`, matched as exact strings. The build hard-fails on anything else.** Both have
been boot-tested on real hardware. Everything below 610 exists only on an unreleased branch, is
source-verified, and has never been booted on a 170HX by anyone whose report survives in the
record.

Note the distinction that trips people up: the 170HX runs perfectly well on ordinary stock
NVIDIA drivers. It just does not **unlock** on them. Being driveable and being unlockable are
separate questions.

---

## The supported list on `master`

`driver/VERSION` contains two lines, in this order:

```text
610.43.03
610.43.02
```

The first line is the default build target. `common/constants.yaml` mirrors the same two under
`driver_versions`. Both `install.sh` and `driver/build.sh` read `driver/VERSION` into
`SUPPORTED_VERSIONS` and call an exact-string `version_supported()`. There is no range check, no
"610 or newer" comparison and no fuzzy match.

If your installed driver is not one of the two, the install dies with:

```text
Installed driver is ${detected}, but cmpunlocker requires one of: 610.43.03,610.43.02.
```

### How the installed version is detected

`install.sh` tries four sources, in order, and stops at the first that yields a version:

| Order | Source |
|---|---|
| 1 | `/proc/driver/nvidia/version` |
| 2 | `nvidia-smi --query-gpu=driver_version` |
| 3 | A directory probe for `/lib/firmware/nvidia/<supported>/` |
| 4 | The highest-sorting directory under `/lib/firmware/nvidia/` |

The build then downloads the matching upstream source tarball:

```text
https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz
```

It is cached under `driver/.build/` and re-extracted clean on every run. No NVIDIA code ships in
the cmpunlocker repository itself.

!!! note "No checksum on the download"
    `build.sh` fetches the tarball with `curl -L --fail` and verifies nothing. There is no
    recorded SHA-256 anywhere in the tree. Recording an expected hash per version in
    `driver/VERSION` or `common/constants.yaml` is an obvious, unimplemented improvement.

---

## Why 610.43.0x specifically

Four reasons, in decreasing order of hardness.

**The patch hunks are anchored to that source tree.** Six patch files apply with `patch -p1`
under `set -euo pipefail`. A single rejected hunk aborts the build. The line numbers, surrounding
context and struct layouts in `kernel_gsp.c`, `g_kernel_gsp_nvoc.h`, `osinit.c`,
`kernel_gsp_tu102.c` and `nv.c` all move between upstream releases. See
[the six driver patches](../unlock/driver-patches.md).

**The unlock must be a patch to the open kernel modules.** The proprietary NVIDIA driver "has
different boot paths and cannot be patched the same way". The open modules are also GSP-only on
GA100: loading with `NVreg_EnableGpuFirmware=0` fails outright with a `0x62` firmware-init error,
so there is no CPU-RM escape hatch on this silicon.

**610 is the stated floor.** The maintainer's own phrasing when asked about coexisting with a
third-party P2P driver was that "it needs to be **610 or above**". In practice `master` is
stricter than that statement: it refuses anything that is not exactly one of the two whitelisted
strings.

**Both versions are attested in the field.** Independent runtime captures from two machines:

```text
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64 610.43.02 Release Build
              (dvs-builder@U22-I3-H05-01-2) Tue May 19 11:24:27 UTC 2026
GCC version:  gcc version 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1)
kernel:       6.8.0-136-generic
```

!!! warning "That capture is from a rig where the unlock did not fire"
    Read it as evidence that `610.43.02` exists and installs, not that it unlocked. The
    `dvs-builder` build string is NVIDIA's own, so the module loaded there was the **stock** one,
    not the patched one; on the same rig `verify.sh` reported every GPU `MISSING` and no
    `SEC2_DEBUG` lines in `dmesg`. Do not read the gcc or kernel version in this block as a
    known-good build environment.

and, separately, `NVIDIA-SMI 610.43.03 / KMD Version: 610.43.03 / CUDA UMD Version: 13.3`. A
packaged NixOS module in circulation hard-asserts
`config.hardware.nvidia.package.version == "610.43.03"`.

Every experimental branch, including the whole PCIe Gen2 lineage and the 80 GB attempt, also
lists only `610.43.03` and `610.43.02`. The backport branch is the sole exception.

---

## `610.43.02` or `610.43.03`?

!!! question "Open problem"
    Nobody has answered this. The question "is 610.43.02 or 610.43.03 more reliable?" was asked
    directly in-channel on 2026-07-24 and never answered. Successful unlocks exist on both.
    `610.43.03` is the default only because it is the first line of `driver/VERSION`.

    The experiment is trivial and nobody has run it: collect the `driver_version` metadata file
    plus the `SEC2_DEBUG` PLM-open success rate from the existing installed base and compare.

Practical guidance: **take `610.43.03`, the default.** If a card refuses to unlock cleanly on one
of the two, trying the other is a cheap and legitimate diagnostic step, but there is no evidence
either way that it will help.

---

## Pinning

!!! warning "Reasoned advice, not a measured result"
    The recommended long-term mitigation against a future NVIDIA driver closing the hole is to
    **pin the driver at 610**, the same way P100 and V100 operators pin around 580. At least one
    operator had already pinned the package as a precaution. This is unchallenged reasoning
    rather than a demonstrated need: no blocking driver exists, and the open kernel modules
    already published on GitHub cannot be recalled.

---

## Stock drivers: driveable, not unlocked

The 170HX enumerates and runs CUDA on completely unpatched drivers. `nvidia-driver-570` with
CUDA 12.8 on Ubuntu 24.04 works out of the box, and `nvidia-driver-535-server` on Ubuntu 22.04
was also reported working. `nvidia-smi` calls the card `NVIDIA Graphics Device` at compute
capability 8.0, because the driver's PCI ID table carries no marketing name for `0x20C2`. That
naming quirk is a fast way to confirm you are looking at a CMP part.

Under a stock driver the card is locked: stock capacity, stock compute throttle, PCIe Gen1 x4.

---

## Hard requirements that travel with the version

| Requirement | Detail |
|---|---|
| Secure Boot | Must be **off**. Patched modules are unsigned; with it on, dmesg shows `nvidia: module verification failed: signature and/or required key missing - tainting kernel`. `install.sh` dies with `Secure Boot is enabled. Disable it before installing unsigned patched modules.` if `/sys/firmware/efi` exists, `mokutil` is present and `mokutil --sb-state` reports it enabled. On a non-EFI system, or one without `mokutil` installed, the check is silently skipped. |
| Driver family | nvidia-open only. The proprietary blob cannot be patched the same way. |
| OS | **Linux only.** The GSP boot path is Linux-specific; the Windows WDDM driver is fundamentally different. |
| Kernel headers | `/lib/modules/$(uname -r)/build` must exist. |
| Toolchain | `python3` required. **No PyYAML** is used on `master`, and there is **no explicit GCC version check** anywhere in the shipping scripts. "Requires gcc 13+ and PyYAML" comes from the third-party `unlock-cmp-170hx` guide repository (plus a vestigial `requirements.txt` on six branches), not from cmpunlocker. The leaked package's README asks only for root and kernel headers. |
| Network | Needed on first install, to fetch the upstream tarball. |

See [Install](install.md) for the full procedure and [Uninstall](uninstall.md) for reverting.

---

## The backport branch: `clanker/driver-port`

!!! warning "Experimental: source-verified, never boot-tested"
    The 595, 590 and 580 support is an unreleased branch. Its own README states verbatim:

    > `595.71.05, 590.48.01, and 580.105.08 are source-verified (patches apply cleanly and the
    > unlock logic matches the 610.43.0x path) but have not yet been boot-tested on physical CMP
    > 170HX hardware.`

    The branch was announced on 2026-07-21 with an explicit request for testers. **No
    confirmation of success appears anywhere in the record through 2026-07-28.** Treat a
    successful build as evidence of nothing until a card boots.

Branch tip `153cd6d`, 2026-07-21.

### What it changes

Almost nothing structural. `driver/patches/` becomes four per-major-version subdirectories, each
holding the same six patch filenames, and `build.sh` gains a two-line edit:

```diff
-PATCH_DIR="${SCRIPT_DIR}/patches"
+BRANCH="${VERSION%%.*}"
+PATCH_DIR="${SCRIPT_DIR}/patches/${BRANCH}"
```

`install.sh` on the branch is **byte-identical to master's**: single-GPU, `head -1`, no
`verify.sh`, no `gpu_inventory`. If you want multi-GPU or PCIe Gen2 as well, you cannot have
them from this branch. See [Multi-GPU](multi-gpu.md).

### It is a re-anchoring exercise, not a rewrite

Every register value, PLM entry, payload offset, static-info rewrite and PMA function is
character-for-character the same across all four directories. Specifically:

- Patches `0004` and `0005` are byte-identical (same md5) across all four version directories.
- Patches `0002` and `0006` are byte-identical between 590 and 610.
- The added `+` lines of `0003` are identical across all four.
- The added `+` lines of `0001` differ between 610 and 580/590/595 by **exactly one extra blank
  added line**, and nothing else.

### Patch sizes per directory

| Directory | 0001 | 0002 | 0003 | 0004 | 0005 | 0006 | Total |
|---|---|---|---|---|---|---|---|
| `580` | 19,700 | 3,957 | 10,377 | 861 | 1,642 | 497 | **37,034** |
| `590` | 19,647 | 3,988 | 10,377 | 861 | 1,642 | 603 | **37,118** |
| `595` | 19,638 | 3,957 | 10,364 | 861 | 1,642 | 531 | **36,993** |
| `610` | 19,741 | 3,988 | 10,580 | 861 | 1,642 | 603 | **37,415** |

The `610` directory is a **byte-for-byte copy of `master`'s patch set**. Nothing in the port
changes the shipping path.

### The upstream divergences the port had to absorb

Only one of these is semantic; the rest are context and anchor drift.

| Divergence | 610 | 595 | 590 | 580 |
|---|---|---|---|---|
| Memdesc flags in `_kgspCreateSignatureMemdesc` | gated on `if (confComputeForceUnprotAlloc(pGpu))` | `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY` unconditional | same as 595 | same as 595 |
| Late-PMA hook context in `osinit.c` | follows `goto shutdown;` | follows `goto shutdown;` | follows `consoleDisabled = NV_FALSE;` | follows `consoleDisabled = NV_FALSE;` |
| GSP static-info trailing context | `NV_ASSERT_OK_OR_GOTO(status, kgspInitGspTraceCrashBuffer(...), done);` | present | **absent** | present |
| Static-info hunk anchor | `@@ -5164` | `@@ -5070` | `@@ -4065` | `@@ -4198` |
| `KernelGsp` field-insert anchor | `@@ -544,6 +544,8 @@` | `@@ -541` | `@@ -525` | `@@ -524` |
| Fields following the insert point | `GspSystemInfo *pSystemInfo; NvU32 regTableSize; PACKED_REGISTRY_TABLE *pRegTable;` | same as 610 | `LIBOS_LOG_DECODE logDecode; LIBOS_LOG_DECODE logDecodeVgpuPartition[48]; RM_LIBOS_LOG_MEM rmLibosLogMem[7];` | same as 590 |
| Patch 0006 trailing context | `(void)rm_get_gpu_uuid_raw(sp, nv);` | same as 610 | same as 610 | `{ const NvU8 *uuid = rm_get_gpu_uuid_raw(sp, nv);` |
| Patch 0006 anchor | `@@ -1521` | `@@ -1531` | `@@ -1521` | `@@ -1481` |
| Patch 0002 neighbouring symbol | `void kgspConfigureFalcon_TU102(` | `static NvBool _kgspIsProcessorSuspended(OBJGPU *pGpu, void *pVoid);` | same as 610 | same as 595 |
| Patch 0002 anchors | `@@ -57` / `@@ -545` / `@@ -565` | `@@ -55` / `@@ -500` / `@@ -520` | same as 610 | `@@ -54` / `@@ -516` / `@@ -536` |

The unprotected-allocation difference is the only behavioural one, and it makes the pre-610
trees slightly more permissive rather than less.

### The version list is internally inconsistent

!!! danger "Seven of twelve whitelisted versions have no verified patch anchor"
    The branch's `driver/VERSION` lists **twelve** versions:

    ```text
    610.43.03  610.43.02
    595.71.05  595.58.03  595.45.04
    590.48.01
    580.105.08 580.95.05  580.82.09  580.82.07  580.76.05  580.65.06
    ```

    but only **four** patch directories exist, and `build.sh` selects one by
    `BRANCH="${VERSION%%.*}"`, that is, by **major version alone**. So `595.45.04` is patched
    with `595.71.05` hunks and `580.65.06` with `580.105.08` hunks. Five of the twelve carry
    some evidence: `610.43.03` and `610.43.02` are boot-tested, and `595.71.05`, `590.48.01`
    and `580.105.08` are the three the branch README calls source-verified. The remaining
    seven (`595.58.03`, `595.45.04`, `580.95.05`, `580.82.09`, `580.82.07`, `580.76.05`,
    `580.65.06`) rely entirely on `patch -p1` fuzz matching.

    Meanwhile `common/constants.yaml` on the same branch lists only **five** versions
    (`610.43.03`, `610.43.02`, `595.71.05`, `590.48.01`, `580.105.08`), disagreeing with
    `VERSION`. `install.sh` accepts any of the twelve, so a user can reach the unverified state
    without doing anything unusual.

    The failure risk here is reasoned inference from reading the code, not an observed patch
    reject. The test is purely offline and mechanical: download each of the seven extra tarballs
    and run `patch -p1 --dry-run` against the major-version patch directory. No hardware needed.

---

## Which should you run?

| Situation | Recommendation |
|---|---|
| Normal install, one card, want it to work | `master` on **610.43.03**. This is the only combination with broad first-hand confirmation. |
| One card, 610.43.03 misbehaves | Try **610.43.02**. Both are whitelisted and both have produced successful unlocks. |
| Multiple 170HX cards | `master` works and has been confirmed on multi-GPU hosts, including 8 cards under Proxmox passthrough. Note the `install.sh` auto-detect hazard and pass `--profile` explicitly. See [Multi-GPU](multi-gpu.md). |
| You need PCIe Gen2 | Branch only, and 610-only. See [PCIe Gen2](../unlock/pcie-gen2.md). |
| You are pinned to 595, 590 or 580 by another application | The backport is your only option, and you would be the first person to boot it. Do this on a machine you can afford to break, and report the `POST-BooterLoad verify` line either way. |
| You want to keep a 170HX alongside Volta or Maxwell cards | This is exactly the motivation for the 580 backport: 580 covers everything from a 980 Ti to an A100. The port answers it in source form and nowhere else. |

!!! danger "Driver-patch development on bare metal is destructive"
    One developer reported needing to reinstall the OS after every botched `nvidia.ko` deploy.
    The accepted remedy is to test modified drivers in a VM or container. For Proxmox
    passthrough specifically, use **SeaBIOS, not UEFI/OVMF**: UEFI produces RM init and adapter
    failures that look exactly like the exploit simply not working, and that misdiagnosis cost at
    least two people significant time.

---

## Switching versions or branches

The supported path is **remove first, then install**. The maintainer's phrasing: "In fact, I
would always recommend to remove the old one before adding the new one."

```bash
sudo ./remove.sh --yes
```

There is no `uninstall.sh`, on `master` or on the `docs` branch, despite what
`docs/INSTALLATION.md` says.

That said, this is guidance rather than a hard law. One tester who cloned a different branch and
installed on top of an existing install reported it did not work, and uninstalling first fixed
it; at least two other testers installed on top with no problem, and the informal consensus was
that most people just install over the top. Nobody identified the differentiating factor.

After any install, three metadata files are written next to the modules at
`/lib/modules/$(uname -r)/updates/cmpunlocker/`:

| File | Contents |
|---|---|
| `driver_version` | e.g. `610.43.03` |
| `card_profile` | `8gb` or `10gb` |
| `unlock_geometry` | `64GB` or `40GB` |

**Nothing in the kernel modules reads any of them.** They are install-time bookkeeping. The only
file the patched kernel reads at boot is the optional
`/lib/firmware/nvidia/ga100/gsp/dmem.bin`. If you need to know which version is actually loaded,
read `cat /proc/driver/nvidia/version` (it should **not** say `dvs-builder`) and confirm with
`sudo dmesg | grep SEC2_DEBUG`.

---

## Open questions on this page

!!! question "Open problem"
    1. **Is 610.43.02 or 610.43.03 more reliable?** Asked repeatedly, never answered.
    2. **Do the 595 / 590 / 580 ports boot at all?** One tester per branch reporting
       `dmesg | grep SEC2_DEBUG` and the `POST-BooterLoad verify` line settles it.
    3. **Do the seven non-verified point releases in the port branch's `VERSION` even apply?**
       Answerable offline with `patch -p1 --dry-run`.
    4. **Whether the port branch and the Gen2 or multi-card lineages will ever merge.** They were
       developed independently. Choosing one currently means giving up the other. The merge is
       structurally simple, since the port only changes `PATCH_DIR` computation, but it requires
       regenerating the Gen2 patches `0007` and `0008` against 580, 590 and 595 sources.
    5. **WSL and HiveOS support.** Both asked about, both unanswered, no evidence either way.

---

## Related pages

- [The six driver patches](../unlock/driver-patches.md)
- [Install](install.md) and [Verify](verify.md)
- [Troubleshooting](troubleshooting.md)
- [Multi-GPU](multi-gpu.md)
- [PCIe Gen2](../unlock/pcie-gen2.md)
- [Open questions](../frontier/open-questions.md)
