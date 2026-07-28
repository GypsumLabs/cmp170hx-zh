# Tool lineage: what to use, and what is dead

## What this page covers

Four generations of CMP 170HX tooling exist, and they overlap in time, so "newer" does not always
mean "replaces". This page traces every tool from the first manual BAR0 pokes in June 2026 to the
shipping in-driver patch set and the branch structure on top of it, and states plainly which paths
are dead so nobody follows one.

**If you only want the short answer:**

- To **unlock a card**, use `cmpunlocker` `master`: `install.sh` plus `driver/build.sh` plus the six
  patches. Everything else is history or experiment.
- To **measure a card**, use the generation-0 read-only instruments (`probe.sh`, `pcielink.sh`,
  `check_fold.py`, the VBIOS dumper). These were never obsoleted.
- **Do not** use any Python ROP unlocker, any GSP ELF patcher, or any systemd persistence daemon from
  generation 1. Every persistence mechanism in that generation was replaced.
- **Do not** expect to find the measurement tools in the repository. `master` has no `tools/`
  directory. `probe.sh`, `pcielink.sh`, `check_fold.py`, `cuda_dbg.py`, the A100 probe kit and the
  `refire_chain*.py` scripts were all distributed out of band as gists and channel attachments.

---

## Lineage at a glance

| Gen | Period | Tools | Status |
|---|---|---|---|
| **0: read-only characterisation** | 2026-05-31 to present | `probe.sh` (mmio-probe), `z1_dump_and_parse_vbios.sh` + `z2_parse_vbios_table.py`, `pcielink.sh`, A100 `probe.py`/`sweep.sh`, `cuda_dbg.py`, `check_fold.py`, `cuda_memtest` | **CURRENT.** Never obsoleted. These are measurement instruments, not unlockers |
| **1: manual BAR0 poking and Python ROP unlockers** | 2026-06-22 to 2026-07-17 | `deploy.py --path sec2-rop`, `deploy.py --path vbios-memory`, `load_custom_bin.py`, `unlc.py`, `stack_gen.py`, `patch_gsp.py`, `payload-lnject.py`, `scan_dmem.py`, `nuke.sh`, `b.sh`, `falcon_emulator.py`, systemd `cmp170hx-unlock.service` | **OBSOLETE.** Every persistence mechanism here was replaced |
| **2: shipping driver patch (`cmpunlocker`)** | 2026-07-14 to present | `install.sh`, `driver/build.sh`, `driver/patches/0001`-`0006`, `remove.sh`, `common/constants.yaml`, `driver/VERSION` | **CURRENT and canonical.** This is what ships on `master` |
| **3: driverless SEC2 refire chain** | 2026-07-22 to present | `refire_chain.py` (v1), `refire_chain_v2.py`, `refire_chain_v6.py` | **CURRENT but experimental.** A parallel, non-shipping path; not part of `cmpunlocker` |
| **4: unmerged feature branches** | 2026-07-18 to present | `multiple-cards`, `clanker/driver-port`, `80`, `debug-gen2` to `Gen2` to `far` to `deced`, plus `docs`, `ecc`, `housekeeping`, `memory`, `PG199` | **EXPERIMENTAL.** Sits on top of generation 2 |

---

## Generation 0: the measurement instruments

These predate the unlock, were built for fuse characterisation, and remain the correct tools. The
governing discipline of the whole project came from here: **after any write, read the register back
with `probe.sh` rather than trusting a tool's claim of success.**

### `probe.sh` (tools/mmio-probe)

A self-contained bash-plus-inline-Python tool that read-only-mmaps
`/sys/bus/pci/devices/<BDF>/resource0` and dumps roughly 120 to 130 named registers plus 24 per-FBPA
reads. It **never writes to BAR0**.

```bash
./probe.sh [pci_id]      # default filter 10de:
# output to ${OUTDIR:-/tmp/mmio-probe-$(date +%s)}
```

| Property | Value |
|---|---|
| Access mode | `os.open(..., os.O_RDONLY)`, `mmap.mmap(fd, 0, access=mmap.ACCESS_READ)`, `struct.unpack_from('<I', bar, off)` |
| Outputs | `registers.json`, `lspci.txt`, `nvidia-smi.txt`, `gpu-summary.csv`, `probe.log`, tarred to `/tmp/mmio-probe-$(hostname)-YYYYmmdd-HHMMSS.tar.gz` |
| `registers.json` keys | `targets` (name to offset/value/why), `fbpa_capacity`, `fbpa_cfg0` |
| Per-FBPA constants | `FBPA_BASE = 0x900000`, `FBPA_STRIDE = 0x4000`, `CSTATUS_RAM = 0x20C`, `FBPA_COUNT_TO_PROBE = 24` |
| Derived addresses | fbpa00 CSTATUS_RAMAMOUNT `0x0090020C`, fbpa01 `0x0090420C`, fbpa23 `0x0095C20C`; CFG0 at offset `0x200`; broadcast CFG0 `0x009A0200`, CFG1 `0x009A0204` |
| Optional CUDA step | Compiles and runs `sr_dump.cu` with `nvcc -arch=sm_70 -O2`, launched as `dump_sr<<<p.multiProcessorCount, 32>>>()`, reporting `%smid`, `%warpid`, `%nsmid`, `%nwarpid`, `%lanemask_eq` per SM, so **SM count is measured, not reported** (70 on a 170HX). Skipped with a log line if `nvcc` is absent |

`gpu-summary.csv` captures `driver_version` and `vbios_version`, which is what lets a probe result be
tied to a specific VBIOS. The tool was built off MODS/MATS and is expected to port to other cards
with the caveat that "registers may be in diff ranges etc though".

Reading BAR0 needs root **plus** `CAP_SYS_RAWIO`, which containerised GPU hosts drop; the probe then
raises `cannot open .../resource0 (EPERM) even as root`. If `mmap` fails with EBUSY or EACCES the
NVIDIA driver holds the BAR:

```bash
sudo systemctl stop nvidia-persistenced; sudo nvidia-smi -pm 0
# or, more forcefully
echo <BDF> | sudo tee /sys/bus/pci/drivers/nvidia/unbind
```

GA100 BAR0 is a 16 MiB PRI aperture (`0x1000000`); `PMC_BOOT_0` at offset 0 identifies the chip:
`0x170000a1` GA100, `0xb72000a1` GA102, `0xb74000a1` GA104.

!!! warning "The advertised `/dev/mem` fallback does not exist"
    Line 9 of the header comment reads `# Falls back to /dev/mem path if resource0 fails.` The
    resource0 resolution block actually ends with
    `log "ERROR: cannot find resource0 for $PCI_BDF"; ... exit 2`. The code path was never written.

### VBIOS tooling

`z1_dump_and_parse_vbios.sh` dumps a VBIOS non-destructively through three sysfs commands
(`echo 1 > .../rom`, `cat`, `echo 0 >`), with fallbacks to the unprefixed sysfs path and then
`nvflash --save`. It is **read-only with respect to flash**: no write path exists. Exit 2 if no dump
method exists, exit 3 if the dump is empty.

`z2_parse_vbios_table.py` locates ROM structures by four magics: `NVGI` at offset 0, `PCIR` via the
ROM header pointer at `+0x18`, the BIT pattern `ff b8 42 49 54 00`, and `RFRD` at absolute `0x2000`.
The CFG1 strap table is auto-located by a stride-1 scan of `0x30000` to `0xB0000` for 16 consecutive
4-byte entries whose byte+2 is in `{0x44,0x55,0x66,0x77}` and byte+3 in `{0x02,0x22}`.

!!! warning "The parser's labels are stale in four places"
    Its `extract_cfg1_strap_table` docstring cites "~0x3FB18 in A100 PCIe" while the comparison table
    places it at `0x4285A`; `extract_rfrd` calls RFRD a "power table" when it is an image layout
    descriptor and `field_0C` is the MAC-verified range size, not a power limit;
    `extract_fbpa_tier_table` can match the CFG1 table itself and report a duplicate; and
    `find_subsystem_id` is a stub. Anyone quoting the tool's output labels verbatim propagates all
    four. See [VBIOS](../hardware/vbios.md).

### `pcielink.sh`

The standard PCIe field-report collector, and the right thing to attach to any link-related bug
report. It auto-discovers `10de:20c2` / `10de:2082` (falling back to any NVIDIA 3D controller) and
decodes, on both the endpoint and its parent bridge:

| Capability offset | Field |
|---|---|
| `CAP_EXP+0c.l` | LnkCap |
| `CAP_EXP+2c.l` | LnkCap2 |
| `CAP_EXP+10.w` | LnkCtl |
| `CAP_EXP+12.w` | LnkSta |
| `CAP_EXP+24.l` | DevCap2 |
| `CAP_EXP+28.w` | DevCtl2 |
| `CAP_EXP+30.w` | LnkCtl2 |
| `CAP_EXP+32.w` | LnkSta2 |

plus sysfs link speed and width, `nvidia-smi pcie.link.gen`, AER counters, and the count of
`SEC2_DEBUG` dmesg lines with the OPT fuse triple. The tool printed
`SEC2_DEBUG lines=152` alongside `OPT=00000001/00000001/16680000` on two separate unlocked two-card
Gen2 rigs, one HiveOS and one Unraid.

!!! note "Line counts are not a reliable cross-build fingerprint"
    Every recorded value differs: 29 on the archived single-card 8 GB capture, 134 on the archived
    two-card Gen2-branch `610.43.03` log, 34 (Gen1 build) and 80 (Gen2 build) from the reporting
    tools, and 152 from `pcielink.sh` on two two-card Gen2 rigs. Do not read a mismatch as a failed
    install.

### The A100 probe kit

A three-step, opt-in-write workflow used to build the Gen2 differential:

```bash
python3 probe.py which
sudo python3 probe.py inventory --out a100_native.json   # read-only
sudo ./sweep.sh                                          # forces Gen1/2/3, auto-restores via EXIT trap
sudo python3 probe.py write-test --confirm               # writes then immediately restores
```

`write-test` touches `0x880a8` (target speed to 2), `0x8c044` (to `0x00000002`) and `0x88088`
(retrain bit 5), classifying each as `WROTE-OK` or `REJECTED(PLM?)`. Masked-read sentinel is
`0xBADF5040`. Nothing in the kit writes fuses or persists across reboot. Run with the GPU idle: the
sweep retrains the live link.

### VRAM validators

| Tool | What it proves | Mechanism |
|---|---|---|
| **`check_fold.py`** | **Authoritative.** Whether unlocked VRAM is real, not aliased | Allocates all free VRAM minus 2 GiB, writes each 64 KB page's own index with a PTX `sm_80` `fill` kernel, reads every page back with a `chk` kernel. Must be dense: the fold aliases at a channel-**interleave** offset, so `LOW[0]` maps to `(40 GiB + interleave)`, not `(40 GiB + 0)`, and a sparse probe gives false negatives. Uses `libcuda` via ctypes with `st.global.wt.u32` and `ld.global.cv.u32` to defeat caching. Output `REAL, NO FOLD` or `FOLD/mismatch @<pageindex>`; exit 0 real, 1 fold, 2 error |
| `cuda_dbg.py` | Lighter alias test | `cuMemGetInfo_v2`, then `cuMemAlloc_v2` at 64, 60, 56, 52, 48, 44, 42 GiB until one succeeds; writes `0xAAAA0000` at offset 0 and `0xBBBB0000` at 40 GiB, reads offset 0. Reading back `0xBBBB0000` means the space aliases. It leaks its allocation, so run it once per driver load |
| `cuda_memtest` 1.2.3 | Community VRAM validator | Exits on the first error. On an unlocked card reports `global memory size=85545582592`. On the 80 GB profile prints `Attached to device 0 successfully.` then hangs indefinitely unless capped at 39 GB |

!!! danger "An earlier fold harness was itself broken"
    A control run after an SBR back to consistent native state (10240 MiB, driver 610.43.03, CFG1
    `0x02449000`) allocated 9 GiB of genuinely native memory and reported "4608 chunks, 4608
    corrupt/aliased" across five passes, that is, native memory "folding", which is impossible. The
    same harness had earlier reported 10 GiB as fully aliased at roughly 26.6 GB/s on pass 1 then
    197 to 198 GB/s on passes 2 to 5. This retroactively invalidated a body of fold-at-40 GB
    conclusions. Use `check_fold.py`, not any earlier harness output.

The standard driver-teardown sequence used throughout testing, still correct:

```bash
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
echo 1 | sudo tee /sys/bus/pci/devices/<BDF>/reset
```

---

## Generation 1: manual BAR0 poking and Python ROP unlockers

!!! note "Superseded"
    Everything in this section is obsolete. It is documented because the constants and failure modes
    recur in older guides that are still circulating, and a reader needs to recognise a dead path on
    sight. Replaced by [generation 2](#generation-2-cmpunlocker-the-shipping-driver-patch).

### What the era looked like

The working manual procedure on 2026-07-12, before any in-driver patch existed:

```text
run the ROP script -> FLR -> kill the NVIDIA driver -> FLR again -> run the SM unlock script
```

run from a TTY, on open kernel modules 580.159.04, with the ROP payload spliced into
`gsp_tu10x.bin` by `patch_gsp.py`. `unlc.py` demonstrated the two-step model the shipping patch
still uses: the exploit only has to open the FEAT PLM, after which SS0 and SS1 are ordinary host
writes.

### The tools and how each died

| Tool | Role | Fate |
|---|---|---|
| `deploy.py --path sec2-rop` | Orchestrator, wrote a 63,232 B payload to `/var/lib/cmp170hx/payload.bin`, installed a systemd unit | Superseded by in-driver delivery. Its first release also aborted because it passed `--verify` to `load_custom_bin.py`, whose argparse did not accept it (exit code 2, not a hardware failure). Fixed 2026-06-24 |
| `deploy.py --path vbios-memory` | Rewrite CFG1 strap tiers in the VBIOS | **Never worked.** Produced `[vbios-memory] ERROR: Not a PCI Option ROM (bad magic at 0x00)`: it expected the inner image, not the raw ROM dump. The whole VBIOS-memory approach was dropped 2026-06-23 |
| `load_custom_bin.py` | Load a Falcon binary and dump DMEM | Absorbed into the refire chain's delivery primitives |
| `unlc.py` | Host-side SS0/SS1 writer after the PLM was open | Its model survives inside patch 0001; the script does not |
| `stack_gen.py` | ROP stack builder | First release **zeroed all canary slots** and could not have worked: the canary at `D[0x6340]` must be replicated into every frame or `__stack_chk_fail` (`0x7dd9`) fires. Constants were `exit_addr 0x79e7`, `payload_size 0xF700`, `dma_target 0x0900`, `stack_start 0xf75c` |
| `patch_gsp.py`, `payload-lnject.py` | ELF surgery on `gsp_tu10x.bin`: parse ELF64 header at `e_shoff 0x28`, `e_shentsize 0x3A`, `e_shnum 0x3C`, `e_shstrndx 0x3E`, find `.fwsignature_ga100`, overwrite in place, patch `sh_size` to `0xF800`, append `.shstrtab` to EOF, rewrite `e_shoff` | Superseded. `.fwsignature_ga100` sits at file offset `0x1D09F0F` in the 580.159.04 blob |
| `scan_dmem.py` | Safer ELF patcher variant using pyelftools, appending the replacement section at EOF honouring `sh_addralign`, plus DMEM scanning | Superseded |
| `nuke.sh`, `b.sh` | PLM persistence sweeps (27 candidate addresses in 9 cycles of 3, two FLRs per cycle, no driver loaded) | Their canary literal was `0xFACEB13D` at `CANARY_ADDR = 0x6340` with `DMA_TARGET = 0x0800` |
| `falcon_emulator.py` | Local Falcon emulation | Not load-bearing; the paper's own emulator was never released |
| `cmp170hx-unlock.service` | systemd persistence, polled `/proc/driver/nvidia/gpus/<BDF>/clients` and re-applied within 250 ms whenever a new CUDA process opened the GPU | Superseded. The daemon raced process-open against re-apply and could not survive a driver reload |
| `/opt/cmpunlocker/daemon/watchdog.py` | Alternative daemon design | Superseded |

### Two supersessions worth understanding

**On-disk GSP firmware patching became an in-driver signature memdesc.** Until 2026-07-17 it was
believed the payload had to be spliced into the shipped GSP ELF. Three independent ELF patchers
existed. The pipeline copied the patched blob over
`/lib/firmware/nvidia/580.159.04/gsp_tu10x.bin`, loaded the driver, verified the PLM read
`0xFFFFFFFF`, then restored the original. Patch `0001` replaced all of it by allocating
`pSignatureMemdesc` at `0xf800` and filling it in memory. No ELF surgery, no firmware file to back up
or restore, no risk of leaving a patched blob on disk, and the payload can be rebuilt between Booter
firings. **Residue:** `remove.sh` still deletes five `gsp_tu10x.bin.cmpunlocker.*` suffixes.

**Userspace daemon persistence became patched kernel modules.** The unlock now runs inside
`kgspBootstrap` every time the patched modules boot GSP: no daemon, no polling, no re-apply window.
**Residue:** `remove.sh` still stops a `cmpunlocker` systemd unit and `pkill`s the watchdog.

### The exfiltration ROP and the recipe catalog

Two generation-1 artifacts are worth remembering as technique rather than tooling.

The original booter stack was recovered from silicon one word at a time using an exfiltration ROP
built from gadget `0x7de9`: the gadget writes a chosen DMEM word into the SEC2 mailbox, so each boot
leaks one dword. Roughly **35 boots at about 90 s each** under DKMS, about an hour per pass. The
region below `D[0xFF74]` could not be leaked because the ROP itself sits there. Because the canary is
re-randomised every boot, running the dump twice and diffing reveals exactly which slots are
canaries: a limitation turned into a technique.

Eight named ROP recipes were maintained as a parameterised catalog, differing in rejoin point
(`0x37b7` versus `0x37cc`), hijack gadget, stack style and smash size (`0xF800`, `0xF810`, `0xF820`):
`rejoin_short_37cc`, `whole_stack_37b7` (guard `0xFACEB13D`), `dummy_shift_37cc`, `srw_v1_37b7`,
`srw_v2_37cc`, `waa_37cc`, `waa_37b7`, `waa_3747`. The multi-write pattern the research chains
standardised on is `0x4d4(r0=addr,r1=val,RA=0x10b9) -> [0x10b9 write -> 0x10aa-epi] xN -> TERM`.
That `0x10b9` mid-entry form belongs to the clean-room and driverless tooling: the shipping payload
plants `0x000010aa` instead, and the string `10b9` appears nowhere in the shipping tree. See
[the ROP chain](../unlock/rop-chain.md).

---

## The interlude: the first `cmpunlocker` was driverless Python

Between **2026-07-14T21:47:02-07:00** and **2026-07-18T19:11Z**, the public `cmpunlocker` repository
contained no driver patch of any kind. It shipped `payload/build.py`, `payload/gsp_patch.py`,
`payload/pipeline.py`, `payload/bar0.py`, `payload/driver.py`, `unlock/compute.py` and a `daemon/`
watchdog.

Its pipeline: locate `/lib/firmware/nvidia/*/gsp_tu10x.bin`, back it up, build a `0xF800`-byte ROP
payload, splice it into the `.fwsignature_ga100` ELF section, load the stock module, FLR reset, unload
aggressively, FLR reset again, write SS0 `0x0082381C = 0x88888888` and SS1 `0x00823820 = 0x00000008`
from the host over BAR0, then restore the original firmware.

Its ROP builder emitted one frame per write, on the grid that is still in use:

```yaml
dmem_layout:   { dma_target: 0x0800, payload_size: 0xF800, guard_addr: 0x6340, canary: 0xFACEB13D }
booter_addrs:  { bar0_write_gadget: 0x10B9 }
payload_frames:
  frame_start_addr: 0xFF48
  frame_stride:     0x18
  frame_field_offsets: { r0: 0x00, r1: 0x04, r2: 0x08, r3: 0x0C, saved_reg: 0x10, return_addr: 0x14 }
```

with a zeroed terminator frame returning to `0x0000810D`. Its three writes were
`0x009A0204 = 0x02779000`, `0x00100CE0 = 0x0000020B` and `0x00823804 = 0xFFFFFFFF`.

!!! note "Superseded"
    Commit `06fabf2 "WORKING MEMORY UNLOCK"` deleted the entire Python pipeline, the daemon and
    `.pylintrc`, replacing all of it with six driver patches. The pylint and tests GitHub workflows
    survived that commit and went about two hours later in `99338ef "Goodbye lint"`, with the last
    remaining test file removed in `8206c16 "Goodbye tests"`. The
    stated reason: the Python path did compute only; the driver path did compute **and** memory in
    one shot. The trade also abandoned the effort's founding goal, an unlock that does not modify the
    driver so that Secure Boot can stay enabled. `install.sh` now hard-fails with "Secure Boot is
    enabled. Disable it before installing unsigned patched modules."

---

## Generation 2: `cmpunlocker`, the shipping driver patch

This is the canonical tool. Repository tagline: "A tool to unlobotomize your NVIDIA card!".

### What `master` actually contains

Exactly eight top-level items:

```text
.github/pull_request_template.md
.gitignore
LICENSE
README.md
common/constants.yaml
driver/
install.sh
remove.sh
```

There is **no** `verify.sh`, **no** `tools/` directory, **no** `probe.sh`, **no** `requirements.txt`
(deleted 2026-07-19 in `7019bc2`) and **no** test suite on `master`.

### `install.sh`

Six steps: root check, GPU detect, profile select, driver / Secure Boot / headers check, build and
install, done. Everything is tee'd to `logs/install_$(date +%Y%m%d_%H%M%S).log`.

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

Dies with `No CMP 170HX GPU found (10de:20b0 / 10de:20c2 / 10de:2082)` if nothing matches, and warns
`In-driver unlock path is gated on PCI ID 0x20C2 / 0x2082.` for any other device ID. A `10de:20b0`
card therefore installs without unlocking.

`detect_card_profile()` reads `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits |
head -1` and maps four windows: `>= 60000 MiB` to `8gb` (already unlocked), `35000-59999` to `10gb`,
`7680-8704` to `8gb`, `9728-10752` to `10gb`. Anything else prints `unknown:<mib>` and the installer
dies telling you to pass `--profile=8gb|10gb`.

!!! danger "Auto-detection is unsafe on mixed-GPU hosts"
    `detect_card_profile()` reads the **first GPU in `nvidia-smi` order**, not the CMP that `lspci`
    found. A system with an RTX 3080 10 GB alongside an 8 GB CMP 170HX detects "10GB" from the 3080
    and selects the wrong profile. Reproduced by at least two users; other CMP SKUs have also been
    misdetected as 10 GB 170HX cards. **Always pass `--profile` explicitly on a multi-GPU host.**

Secure Boot is a hard gate: if `/sys/firmware/efi` exists, `mokutil` is present and `mokutil
--sb-state` reports it enabled, the installer refuses. Driver version must exactly match a line in
`driver/VERSION` (`610.43.03`, `610.43.02`), detected in order from `/proc/driver/nvidia/version`,
then `nvidia-smi --query-gpu=driver_version`, then a directory probe of
`/lib/firmware/nvidia/<version>/`, then the highest-sorted `/lib/firmware/nvidia/*/`. Kernel headers
must exist at `/lib/modules/$(uname -r)/build`.

### `driver/build.sh`

It never ships NVIDIA code. It downloads
`https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/${VERSION}.tar.gz` with
`curl -L --fail`, caches it under `driver/.build/`, extracts clean, applies every
`driver/patches/*.patch` with `patch -p1`, builds with
`make -j$(nproc) modules SYSSRC=/lib/modules/$(uname -r)/build` after clearing `_out` and `conftest`,
and installs `nvidia.ko`, `nvidia-modeset.ko`, `nvidia-uvm.ko`, `nvidia-drm.ko` and
`nvidia-peermem.ko` at mode 0644 into `/lib/modules/$(uname -r)/updates/cmpunlocker/`.

It writes three single-line metadata files there: `driver_version`, `card_profile` (`8gb` or `10gb`)
and `unlock_geometry` (`64GB` or `40GB`), then runs `depmod -a "${KVER}"` and rebuilds initramfs via
the first available of `update-initramfs -u -k`, `dracut --force --kver` or `mkinitcpio -P`.

It also cross-checks that the patched module won. Before reload it runs
`modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'` and warns
`Resolved nvidia.ko is not under updates/cmpunlocker/ - stock may still win`. After reload it compares
`/sys/module/nvidia/srcversion` against `modinfo -F srcversion .../updates/cmpunlocker/nvidia.ko` and
on mismatch warns `Loaded nvidia srcversion (X) != patched (Y)`, clears `reload_ok`, and advises a
cold reboot plus `cat /proc/driver/nvidia/version  (should NOT say dvs-builder)`.

!!! warning "`--profile` no longer selects geometry"
    On the `memory` branch snapshot, `--profile` genuinely chose CFG1 and LMR through a build-time
    Python regex rewrite. On current `master` it does not. Patch `0001` contains all six markers the
    `build.sh` guard looks for, so the rewrite prints `runtime device-id geometry (profile
    metadata=<label>)` and exits without editing anything. Geometry is chosen at GSP boot from
    `pGpu->idInfo.PCIDeviceID >> 16`. `--profile` now affects only the printed banner, `EXPECTED_MIB`
    and the metadata files. Instructions written before 2026-07-18 are wrong about this.

### The six patches

| # | File | Bytes |
|---|---|---|
| 0001 | `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 |
| 0002 | `0002-booter-verify.patch` | 3,988 |
| 0003 | `0003-late-pma.patch` | 10,580 |
| 0004 | `0004-bar0-pramin-clamp.patch` | 861 |
| 0005 | `0005-ce-scrub-workarounds.patch` | 1,642 |
| 0006 | `0006-persistent-sw-state.patch` | 603 |
| | **Total** | **37,415** |

Patch `0001` carries the whole unlock: it enlarges `pSignatureMemdesc` to
`SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL` (63,488 bytes), fills it with
`SEC2_POSTBL_TIMING_FILL_DWORD 0x000004a7U`, lays a ROP stack into it, and re-runs
`kgspExecuteBooterLoad_HAL` once per PLM attempt. **No ELF surgery on `gsp_tu10x.bin` occurs.**

The PLM table is four entries, up to two attempts each, WPR2 lo/hi (`0x001fa824`/`0x001fa828`) saved
before the loop and rewritten before every attempt and once after:

```c
{ 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },   /* note: NOT 0xffffffff */
{ 0x009a0148U, 0xffffffffU, "FBPA"    },
{ 0x001fa7c4U, 0xffffffffU, "WPR"     },
{ 0x00823804U, 0xffffffffU, "FEAT"    },
```

Then four plain host register writes:

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0 */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1 */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* 0x02779000 (20C2) / 0x02669000 (2082) */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* 0x0000020B (20C2) / 0x0000028A (2082) */
```

Patch `0001` also relaxes the stock `WPR2 already up` hard error into
`NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n")`, and rewrites
`pGSCI->fb_length` to `0x0000001000000000ULL` (64 GB) or `0x0000000A00000000ULL` (40 GB) plus the last
FB region's `limit`, `reserved`, `supportCompressed`, `supportISO` and `performance = 20`.

The built-in payload can be overridden at runtime from
`/lib/firmware/nvidia/ga100/gsp/dmem.bin` (`SEC2_POSTBL_TIMING_DMEM_PATH`), `0xf800` bytes loaded via
`os_open_and_read_file`. If absent the driver logs
`SEC2_DEBUG: <path> not found (0x%x), using built-in payload` (the reported code is `0x59`, benign)
and falls back to the compiled-in fill, whose default single write is `0x009a0148U = 0xffffffffU`.

!!! warning "The shipping payload's marker word is `0xc0deca7e`, not `0xFACEB13D`"
    `0xc0deca7e` appears at payload offsets `0x5b40`, `0xf758`, `0xf794`, `0xf7a0` and `0xf7c4`. The
    earlier standalone harnesses used `0xFACEB13D` at `CANARY_ADDR = 0x6340` with
    `DMA_TARGET = 0x0800`. `0x5b40 + 0x0800 = 0x6340`, so it is the same slot with a different
    literal. Do not assume `0xFACEB13D` when reading shipping code.

The shipping in-driver stack and the standalone driverless chain share the **same tail recipe**: at
payload offsets `0xf78c` to `0xf7f8`, patch 0001 writes the non-zero gadget sequence
`0x815a, 0x8e18, 0x815a, 0x1fbd, 0xffbc, 0x582d, 0xcbd, 0x3, 0x1fbd, 0xccb, 0x7f2f`, and sets payload
word `0x1100 = 0x00000007`.

### `common/constants.yaml`

The machine-readable ground truth in the repository, matching the C in patch 0001 exactly:

```yaml
driver_versions: [610.43.03, 610.43.02]
gpu: { vendor_id: 10de, device_ids: [20c2, 2082] }
compute: { ss0: "0x88888888", ss1: "0x00000008" }
profiles:
  8gb:  { stock_mib: 8192,  unlocked_mib: 65536, cfg1: "0x02779000", lmr: "0x0000020B", fb_bytes: "0x0000001000000000" }
  10gb: { stock_mib: 10240, unlocked_mib: 40960, cfg1: "0x02669000", lmr: "0x0000028A", fb_bytes: "0x0000000A00000000" }
```

### `remove.sh`

The uninstaller is `remove.sh` and it requires `--yes` or `-y`. **There is no `uninstall.sh` anywhere
in the tree**, despite what the `docs` branch says. Five steps: stop and disable a legacy
`cmpunlocker` systemd unit and `pkill -f /opt/cmpunlocker/daemon/watchdog.py`;
`rm -rf /lib/modules/*/updates/cmpunlocker` with `depmod -a` per kernel; rebuild initramfs; delete
`/lib/firmware/nvidia/*/gsp_tu10x.bin.cmpunlocker.{bak,patched,tmp,cleanup,pat}`; remove
`/opt/cmpunlocker`; then stop the display manager and `nvidia-persistenced`, force-unload the four
modules and `modprobe nvidia` again. One tester on HiveOS reported both cards back to mining after
running it, which is the basis for the claim that the mod is non-destructive (single report, medium
confidence).

See [install](../procedures/install.md), [verify](../procedures/verify.md) and
[uninstall](../procedures/uninstall.md) for the operational procedures.

---

## Generation 3: the driverless SEC2 refire chain

!!! warning "Experimental"
    This is a parallel path, not part of `cmpunlocker`, and it is not what anyone should run to
    unlock a card for production use. It matters because it is the only line of work that still
    pursues the founding goal of an unlock that does not modify the driver.

`refire_chain_v6.py` (27,769 bytes, released 2026-07-24) performs the whole unlock from userspace
with **no NVIDIA driver loaded**, using only stdlib (`os`, `sys`, `mmap`, `ctypes`, `struct`, `time`,
`subprocess`). It maps BAR0 as 16 MiB, treats SEC2 as base `0x00840000`, resets the Falcon, loads NS
code to IMEM 0 unsecure and HS code to `IMEM[ns]` secure with the tag register, loads DMEM, sets
MAILBOX0/1 to the WprMeta physical address, starts the CPU, and then overflows the signed Booter's
signature-read DMA repeatedly.

Operating procedure:

```bash
echo 16 | sudo tee /proc/sys/vm/nr_hugepages
sudo rmmod nvidia_uvm nvidia
BDF=$(python3 -c 'import refire_chain_v6 as V; print(V.resolve_bdf())')
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sudo python3 refire_chain_v6.py --all
```

Modes: `--compute` (SM and tensor throttle off only, always-on, FLR-sticky), `--memory 40` (the
real and stable tier), `--memory 80` (the 80 GB tier), `--pcie-gen2` (LnkCap2 cap only),
`--pcie-retrain`. Environment overrides: `CMP_BDF`, `CMP_BOOTER_IMG`, `CMP_BOOTER_SIG`. `--all`
leaves the card READY for a no-FLR driver load. Every mode needs the GPU unbound and hugepages set
except `--pcie-retrain`, which is pure host writes.

Prerequisites are strict: root; the GPU **unbound** from any NVIDIA driver; a signed GA100
`booter_load` HS ucode image (about 60,160 bytes with the 384-byte RSA-3072-PSS signature baked at
`0x8900`); 16 hugepages; and kernel cmdline `intel_iommu=off` or `iommu=pt` so DMA physical addresses
are host-physical. It allocates one physically contiguous 2 MiB hugepage, `mlock`s it, resolves the
physical address via `/proc/self/pagemap` (bit 63 must be set, else `page not present (need
hugepages)`), and calls a hand-assembled clflush plus mfence stub
(`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`) because "sig-DMA is NONCOHERENT, must hit RAM
not CPU cache".

Internal detail worth knowing: `stage_radix3()` must run or the Booter's pre-signature DMAs fail with
cause `0x9`. It allocates `0x6000` bytes and writes a three-level chain
(`[0x0000] = phys+0x1000`, `[0x1000] = phys+0x2000`, `[0x2000] = phys+0x3000`), then flushes. The
WprMeta template is a 256-byte struct captured from a real 10 GB boot, with only the signature
pointer (`0x48`), signature size (`0x50` = `0xF800`), radix3 pointer (`0x10`), radix3 size (`0x18`),
bootloader pointer (`0x20`) and bootloader size (`0x28`) overridden. Its first two words are the WPR
descriptor magics `0x371a60b3` and `0xdc3aae21`.

### Version lineage

| Version | Change |
|---|---|
| v1 (`refire_chain.py`) | Hardcoded a compact two-write payload per PLM |
| v2 | Payload becomes a generic write engine taking a flat `[(addr, value), ...]` list with zero WprMeta or geometry knowledge. WprMeta is built once in the delivery layer purely as the signature-DMA overflow trigger. Delivery primitives `Bar0, alloc, flush, reset_sec2, load_booter, wpr_meta, start_wait, stage_radix3, geometry, fire, PATCHLOC` reused verbatim from the hardware-proven v1. Payload size `0xF800`, entry tail constant `TAIL0 = 0x815a` |
| v6 | Adds the mode flags, BDF resolution and environment overrides above |

!!! danger "Portability limit: 10 GB cards only"
    The released chain carries a WprMeta template captured from a **10 GB** boot. It cannot be
    applied unmodified to a `0x20C2` 8 GB card. Producing an 8 GB template is a recorded open task:
    capture `pWprMeta` from an 8 GB card during a normal driver GSP boot and substitute it. Only six
    fields are overridden anyway, so the risk is low, but nobody has done it.

---

## Generation 4: the unmerged branches

Twelve unreleased branch snapshots were captured (**thirteen trees counting shipping `master`**):
`80`, `Gen2`, `PG199`, `clanker/driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`, `far`,
`housekeeping`, `memory`, `multiple-cards`. Sixteen unreleased branch refs exist on the remote;
`code-simplification`, `dual-geometry-fix`, `fix` and `v0.1` were not snapshotted and are not
analysed anywhere in this wiki. See [methodology](../appendix/methodology.md).

| Branch | Tip | What it adds | Verdict |
|---|---|---|---|
| `memory` | 2026-07-18 | The original in-driver memory unlock, single baked geometry | Merged to `master` |
| `housekeeping` | 2026-07-18 | `43c762d "Add 2082 (10GB) device support to all patches"`; also removed the `.ai/CONTEXT.md` agent-instruction file | Merged, after a fix |
| `ecc` | `bb4d669`, 2026-07-18 | One commit, "Fixed dual geometry support". **Contains no ECC code** | Merged. ECC is fused off with no known lever |
| `multiple-cards` | `b1cb6d8`, 2026-07-18 (announced 07-19) | Replaces `detect_card_profile()` with `profile_from_devid()` (`20c2` to `8gb`, `2082` to `10gb`, else unsupported), walks **every** matching `lspci` line, builds five parallel arrays, adds a third `mixed` profile that sets `SKIP_GEOMETRY_REWRITE=1`. Exports `CMPUNLOCKER_GPU_INVENTORY`, persisted as `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`, one line per GPU in the form `0000:0b:00.0 20c2 8gb 65536`. Adds `verify.sh` | Unmerged. See [multi-GPU](../procedures/multi-gpu.md) |
| `80` | `3c53aca`, 2026-07-19 | Rewrites the 10 GB arm of patch 0001 to `cfg1Value = 0x02779000U` (the **8 GB** card's CFG1) with `lmrValue = 0x0000028AU` and `targetFbBytes = 0x0000001400000000ULL` | **Do not use.** Unstable |
| `clanker/driver-port` | `153cd6d`, 2026-07-21 | Per-branch patch directories `driver/patches/{580,590,595,610}/` selected by `BRANCH="${VERSION%%.*}"`. Lists twelve versions in `driver/VERSION` but five in `constants.yaml`, an acknowledged internal inconsistency. Its `install.sh` is **byte-identical to master's** | Unmerged, never boot-tested below 610 |
| `debug-gen2` | `746d9f7 "PCIe Gen 2 works!"`, 2026-07-23 | Patches 0001-0007, plus `tools/retrain.sh` and `tools/cmpretrain.service` installed as a systemd oneshot | Superseded by `Gen2` |
| `Gen2` | `2f27474`, 2026-07-24; tip `a4de322`, 2026-07-26 | `2f27474 "Gen2 + multiple-card support"` adds `0008-pcie-gen2-probe-retrain.patch`, multi-card support and `verify.sh`, and **deletes** `tools/cmpretrain.service` (`tools/retrain.sh` stays). The tip `a4de322` is a pure merge of `master` and touches only `.github/pull_request_template.md` | Current Gen2 base |
| `far` | `8854d3e "Remove clamp link to Gen1"`, 2026-07-26 | Exactly one changed line versus `Gen2`: `RMPcieLinkSpeed` `0x1` to `0x2` | |
| `deced` | `2326599`, 2026-07-27 | Replaces the hardcoded BDF in `tools/retrain.sh` with `find_gpu_bdf()`. **Most current Gen2 tree in the archive** | |
| `docs` | `651b6d5`, 2026-07-27 | Seven commits of documentation | **Not authoritative.** See below |
| `PG199` | | Drive A100 comparison snapshot | Reference only |

### Branch-only tooling

`verify.sh` is a **branch-only** multi-GPU post-install checker and does not exist on `master`. It
prefers the installed `gpu_inventory` and otherwise enumerates via
`lspci -nn | grep -iE '10de:20c2|10de:2082'`. `is_unlocked_memory` accepts `>= 60000 MiB` for `8gb`
and `35000..59999 MiB` for `10gb`; `is_stock_memory` accepts `7680..8704` and `9728..10752`. Per-GPU
status is `OK`, `STOCK`, `MISSING` or `UNEXPECTED`. A missing `SEC2_DEBUG` dmesg trail is a warning,
not a failure, because ring buffers rotate.

!!! question "Open problem"
    **`verify.sh` never checks PCIe Gen2, not even on the Gen2 branch lineage.** Grepping
    `Gen2/verify.sh`, `far/verify.sh` and `deced/verify.sh` for "pcie" returns zero hits. Gen2
    verification is left entirely to the user running `nvidia-smi` by hand. The fix is small: query
    `nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max`, or reuse `pcielink.sh`'s
    `CAP_EXP+12.w` LnkSta decode.

### Gen2 lineage supersessions

**Userspace retrain script became an in-driver probe-time retrain.** `debug-gen2` installed
`/usr/local/sbin/retrain.sh` and `cmpretrain.service` (`Type=oneshot`, `ExecStartPre=/bin/sleep 15`,
`WantedBy=multi-user.target`). From `Gen2` onward, `0008-pcie-gen2-probe-retrain.patch` adds
`nv_cmp170hx_retrain_gen2()` to `kernel-open/nvidia/nv.c`, gated on
`gpu->device == 0x20c2 || gpu->device == 0x2082`, which walks `pci_upstream_bridge(gpu)` and retrains
at probe time. The installer actively disables `cmpretrain.service` and `cmp-gen2-retrain.service`
and `rm -f`s the helper scripts, printing `Removed legacy PCIe retrain helpers`. A 15-second-sleep
oneshot after `multi-user.target` is fragile and cannot run before the driver claims the device.

!!! note "Superseded"
    `tools/retrain.sh` is **dead code** on the `Gen2`, `far` and `deced` trees. It is still present in
    the source, but from `Gen2` onward the installer deletes the installed copy and patch 0008 does
    the retrain in-kernel. Only `debug-gen2` actually installs it. Fixing its hardcoded `0a:00.0` BDF
    (done on `deced`) changes nothing about what runs.

The Gen2-lineage installers also write `/etc/modprobe.d/cmp-pcie-gen2.conf` and configure the IOMMU,
appending `intel_iommu=on iommu=pt` or `amd_iommu=on iommu=pt` to the kernel command line unless
`--no-iommu` is passed.

!!! danger "`Gen2` installs a Gen1 clamp"
    `debug-gen2` and `Gen2` write
    `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"`, pinning the link
    to Gen1 while simultaneously trying to enable Gen2. `far` and `deced` write `0x2`. Which value is
    correct is **genuinely unresolved**: both spellings ship, on branches whose authors each believed
    theirs was right, and no A/B boot test exists. One three-way boot comparison on one card would
    settle it.

!!! danger "Do not follow the `docs` branch"
    `docs/INSTALLATION.md` line 40 says `sudo ./uninstall.sh --yes` (no such file);
    `docs/ARCHITECTURE.md` lines 81-82 claim `SEC2_DEBUG: SS0 = 0xffffffff` / `SS1 = 0xffffffff` when
    the shipping code writes `0x88888888` and `0x00000008`; `docs/DEBUGGING.md` line 15 says "All the
    PLMs must show `0xffffffff`" when WPR_CFG at `0x001fa7cc` is opened to `0xfffff0ff`. The branch
    also invents acronym expansions found nowhere in the code.

---

## Community forks and adjacent tools

At least six public repositories forked or reimplemented the unlock within days of release.

| Repository | Nature |
|---|---|
| `amoghmunikote/cmpunlocker` | The reference implementation described above |
| Several personal forks, one carrying a `combined-multiple-cards-gen2` branch | Forks; one combines the Gen2 work with multi-card support. Owner names omitted under this wiki's anonymisation policy |
| `abobasixseven/unlock-cmp-170hx` | **Not a writeup.** An AI-agent execution prompt: only `README.md` and `cmp90_compute_unlock_prompt.md`, both ending with lines such as `EXECUTE STEP BY STEP: 5 (preparation) -> 6 (installation) -> 6.5 (cold reboot) -> 7 (verification)`, hardcoding a specific home directory throughout. Its register tables match the shipping patches, but its prose and PCIe Gen2 chapter are secondary summaries, not first-hand measurement |
| `theneocorp/cmppatcher` | A genuinely different approach: patches the NVIDIA driver **binary** directly so the patch persists across driver updates. Reported 3D acceleration and FP32 FMA bypass |

Adjacent, non-unlock tooling:

| Tool | Purpose |
|---|---|
| `CMPGPU-patch-script` (`optimize-cmp-cuda.py`) | Interactive llama.cpp source patcher with five independent optimisation groups, each defaulting to `n`: `fp32_fma_flag` (adds `-fmad=false` to CUDA_FLAGS), `fp32_fma_split` (rewrites `fmaf(...)` to `__fadd_rn(__fmul_rn(...), ...)`), `math_intrinsics`, `dp2a`, `fp16_bf16_cuda_core`. Eleven PatchSpec entries across seven files; `.cmp-bak` backups; `--dry-run`, `--no-backup`, `--restore`. Its README warns performance may **decrease** on non-170HX CC 8.x devices |
| `170tune` (`/usr/local/bin/170hx-oc`) | Tuning and qualification harness that measures, gates and recovers clock and voltage settings, treating "a completed benchmark as evidence of nothing". Ships a 26,987-byte tuning guide. Whether its settings persist across a reboot is an open question. See [tuning](../operations/tuning.md) |
| `cmp170hx-gen2-setup.sh` (12,389 B, 2026-07-26) | Standalone Gen2 setup artifact, distinct from the `Gen2` branch's in-driver approach, released with a `PCIE_GEN1_LOCK.md` analysis |
| `unlock_host_610.sh` | Host-side script for nvidia-open 610.43.03: unbind from `vfio-pci`, clear `driver_override`, kill `nvidia-persistenced`, unload the four modules, `modprobe ecdh_generic ecc ecdsa_generic` (the module has crypto dependencies), `insmod kernel-open/nvidia.ko`, assert `/sys/module/nvidia/version == 610.43.03`, `insmod nvidia-uvm.ko`, echo the BDF into `/sys/bus/pci/drivers/nvidia/bind`, then `mknod` the device nodes. Binding triggers `RmInit` and hence the in-driver unlock |

### The FMA workaround family

The FP32 FMA lockdown is worked around at compile time, not by any unlock: OpenCL via
`#pragma OPENCL FP_CONTRACT OFF` plus macro-shadowing of `fma()` and `mad()`, CUDA via
`nvcc -fmad=false`, SYCL via clang `-ffp-contract=off`. Both explicit calls and implicit contraction
of `a * b + c` must be suppressed, and the numerical consequence is two roundings instead of one.

!!! note "Superseded"
    On an unlocked card the FMA workaround is no longer the point: the compute unlock removes the
    throttle in hardware. Two limits made it a ceiling anyway. A transparent compiler or runtime
    patch does not affect built-in function behaviour, GPU kernels are often shipped precompiled, and
    most HPC libraries contain hand-tuned assembly that relies on FMA. A PoCL 4.0 runtime-level
    variant patching `pocl_llvm_build.cc`, `lib/kernel/fma.cl` and `lib/kernel/mad.cl` was never
    benchmarked to completion and does not cover `mad24()`, `mad_hi()` or `mad_sat()`.

---

## Booter extraction toolchain

Needed only if you are working on the exploit itself, not to unlock a card.

The documented recipe for a readable Booter disassembly:

```text
extract the debug binary from the NVIDIA .ko with the Nouveau extraction tool
  -> decrypt with rijndael-tool using NVIDIA's public test key
  -> check it is not compressed (NVIDIA uses a compressor called binHex)
  -> disassemble with envytools (envydis, target fuc5)
  -> annotate
```

`nouveau/extract-firmware-nouveau.py` had to be patched for GA100 because the generated C array names
changed to the form
`kgspBinArchiveBooter{LOAD}Ucode_{GPU}_BINDATA_LABEL_IMAGE_{fuse.upper()}_data`. The stock script
selects prod or debug ucode via a `--debug-fused` key and defaults to prod, and it needs firmware
`.bin` files from the matching **closed-source** driver pack, whose version is listed in `version.mk`
and is *not* the open-branch version number.

In the open driver the signed HS ucode lives in
`src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c` with three archive entries:
`..._IMAGE_PROD` (compressed with NVIDIA's own bindata compressor, not plain zlib), `..._SIG_PROD`
(uncompressed, a 384-byte array) and `..._PATCH_LOC` (4 bytes = `0x8900`). The image is about 60,160
bytes.

An alternative extraction dumps the booter live from a loaded stock driver through the SEC2 Falcon
windows at base `0x840000`: write `IMEMC (0x840180) = off | (1 << 25)` for auto-increment reads and
loop-read `IMEMD (0x840184)` for `off = 0 ... 0x8700`; same for DMEM via `DMEMC (0x8401c0)` /
`DMEMD (0x8401c4)`. Confidence **medium**: the procedure is concrete and the register addresses look
right, but no captured dump was ever posted, and the read must happen right after the driver
PIO-loads the booter and before it reuses SEC2.

The production booter cannot be modified or even read: it is encrypted with a strong key. The exploit
therefore changes the *flow of execution* via the stack, not the code, and no re-signing is required.

!!! question "Open problem"
    `envydis` with the `fuc5` target successfully disassembles the GA100 booter even though the
    envytools table nominally assigns `fuc6` to GP102-and-later parts. envytools has not been updated
    in roughly 8 years; `envyhooks` was suggested as a successor but lacks equivalent functionality;
    `faucon` targets fuc5 only. Whether the 170HX SEC2 is formally fuc5 or fuc6 is unsettled. Next
    step: diff a fuc5 and a fuc6 decode of the same image and look for instructions only one target
    decodes coherently.

---

## Obsolete paths, at a glance

Do not follow any of these.

| Dead path | Why | Use instead |
|---|---|---|
| Patching `gsp_tu10x.bin` on disk (`patch_gsp.py`, `payload-lnject.py`, `scan_dmem.py`) | Replaced by the in-driver signature memdesc; leaves a patched blob on disk | `cmpunlocker` patch `0001` |
| systemd persistence (`cmp170hx-unlock.service`, `watchdog.py`) | Raced process-open against re-apply; could not survive a driver reload | Patched modules in `/lib/modules/.../updates/cmpunlocker/` |
| `deploy.py --path vbios-memory` | Never worked; a modified VBIOS at that point yields a non-working device | Register-level unlock |
| `stack_gen.py` v1 | Zeroed all canary slots; `__stack_chk_fail` at `0x7dd9` fires | Any later payload builder |
| Manual five-step TTY procedure | Superseded 2026-07-18 | `sudo ./install.sh` |
| `--profile` as a geometry selector | Demoted to a metadata label on `master` | Geometry is chosen per PCI ID at GSP boot |
| `sudo ./uninstall.sh --yes` | No such file | `sudo ./remove.sh --yes` |
| `tools/retrain.sh` on `Gen2`/`far`/`deced` | Dead code; installer deletes it, patch 0008 retrains in-kernel | Patch `0008` |
| The `80` branch | Unstable above roughly 40 GB | 40 GB on 10 GB cards |
| The `docs` branch | Documented factual errors | This wiki, and the source |
| Any fold harness other than `check_fold.py` | An earlier harness reported native memory as folding | `check_fold.py` |
| Decrypting `gsp_tu10x.bin` as if it were the booter | It is the GSP RISC-V ELF payload, not the SEC2 Falcon booter. Ghidra emits roughly 100 MB of C and objdump roughly 1.5 GB of assembly from it | Disassemble `booter_load_ga100_*.bin`, about 25 kB, roughly 390 kB of assembly |

---

## See also

- [Project timeline](timeline.md), the dates behind every supersession above
- [The clean room and the provenance question](clean-room-and-provenance.md)
- [Dead ends](dead-ends.md)
- [The six driver patches](../unlock/driver-patches.md) and [the ROP chain](../unlock/rop-chain.md)
- [Install](../procedures/install.md), [verify](../procedures/verify.md),
  [troubleshooting](../procedures/troubleshooting.md)
- [Register reference](../unlock/register-reference.md) and
  [register index](../appendix/register-index.md)
