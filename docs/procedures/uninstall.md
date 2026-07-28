# Uninstalling and reverting

**What this page covers.** How to remove the cmpunlocker driver patch cleanly, exactly what
`remove.sh` touches, what it deliberately leaves behind, why reverting is safe at the hardware
level, and the widely copied instruction that will simply fail because the file it names does not
exist.

The short version:

```bash
sudo ./remove.sh --yes
```

That is the whole supported uninstall. It deletes
`/lib/modules/*/updates/cmpunlocker/` on every installed kernel, re-runs `depmod`, rebuilds the
initramfs, cleans up residue from two abandoned generation-1 designs, and reloads the stock
NVIDIA modules. The card returns to its factory-reported 8192 MiB or 10240 MiB after the next
cold boot; a warm reboot is not a reset and is not established to clear the geometry.

!!! danger "`uninstall.sh` does not exist"
    `docs/INSTALLATION.md` on the `docs` branch, line 40, instructs `sudo ./uninstall.sh --yes`.
    **There is no `uninstall.sh` anywhere in the repository**, on `master` or on the `docs` branch
    itself. Running it produces a shell error and does nothing, which some people have read as
    "the uninstaller silently failed". The correct command is `remove.sh --yes`. The `docs` branch
    also carries three other known defects and is not authoritative: see
    [Verify](verify.md#the-sec2_debug-dmesg-trail).

---

## Why reverting is safe

Nothing about this unlock is persistent in hardware. There is no VBIOS flash, no fuse burn, no
EEPROM write, and since the shipping design no firmware file on disk is modified either. The
unlock is a sequence of volatile register writes performed by the patched kernel module every
time it boots the GSP:

| State | Survives a function-level reset? | Survives a power cycle? |
|---|---|---|
| SS0 `0x0082381c`, SS1 `0x00823820`, FEAT_OVR_PLM `0x00823804` | yes (always-on island) | no |
| CFG1 `0x009a0204`, per-FBPA CFG1, CSTATUS, LMR `0x00100ce0`, FB-geometry PLMs, AON LMR shadow `0x001180f0` | no | no |

Remove the patched modules and the writes stop happening. That is the entire mechanism of
reverting. One tester running HiveOS reported both cards back to normal mining after
`remove.sh`, which is the basis for calling the software side of the mod non-destructive (single
first-hand report).

Physical modifications are a different matter entirely and are **not** undone by anything on this
page. If the card has had its PCIe AC-coupling capacitors populated, that is soldered hardware.
See [Physical mods](../operations/physical-mods.md).

---

## What `remove.sh` does, step by step

The script refuses to run without `--yes` or `-y`. Invoked bare, it prints a summary of what it
would do and exits 1.

### Guard and step 1: root

`[[ "${EUID}" -eq 0 ]]` or die with `Run as root: sudo ./remove.sh --yes`. Output is tee'd to
`logs/remove_<YYYYmmdd_HHMMSS>.log` in the checkout, falling back to `/tmp` if the checkout is not
writable.

### Step 2/5: stop the legacy systemd unit

Stops and disables a `cmpunlocker` service, removes `/etc/systemd/system/cmpunlocker.service`,
runs `systemctl daemon-reload` and `reset-failed`, then
`pkill -f /opt/cmpunlocker/daemon/watchdog.py`.

!!! note "Superseded: the watchdog era"
    The current installer never creates that service or that daemon. They are residue from
    generation 1, when persistence was a userspace design: a systemd unit polled
    `/proc/driver/nvidia/gpus/<BDF>/clients` and re-applied the unlock within 250 ms whenever a
    new CUDA process opened the GPU. That was replaced on 2026-07-18 by patch 0006, which sets
    `NV_FLAG_PERSISTENT_SW_STATE` so RM never tears down software state when the last client
    closes. No daemon, no polling, no re-apply race. The cleanup code remains for people
    upgrading from the old design.

### Step 3/5: remove patched modules and legacy files

- For every `/lib/modules/*/updates/cmpunlocker` directory found (so **all** installed kernels,
  not just the running one): `rm -rf`, then `depmod -a "${kernel}"`.
- If nothing matched, it warns `No patched kernel modules found`.
- For each touched kernel it rebuilds the initramfs so stock modules are packed again, using the
  first available of `update-initramfs -u -k`, `dracut --force --kver`, or `mkinitcpio -P`. This
  matters as much on the way out as on the way in: an initramfs still holding patched modules
  would keep loading them.
- Deletes five firmware-era leftovers next to every `gsp_tu10x.bin`:
  `.cmpunlocker.bak`, `.cmpunlocker.patched`, `.cmpunlocker.tmp`, `.cmpunlocker.cleanup`,
  `.cmpunlocker.pat`.
- Removes `/opt/cmpunlocker` if present, warning
  `/opt/cmpunlocker not found (ok for module-only installs)` otherwise.

!!! danger "This deletes your only backup of a patched-era `gsp_tu10x.bin`"
    If you are mid-migration from the firmware-patching predecessor and have **not** yet restored
    the stock GSP firmware, restore it *before* running `remove.sh`. Step 3 deletes
    `gsp_tu10x.bin.cmpunlocker.bak`, which is the copy of the original blob. Restoring first:
    `sudo cp /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin.cmpunlocker.bak /lib/firmware/nvidia/610.43.03/gsp_tu10x.bin`.

### Step 4/5: reload the stock driver

Only if `lsmod` shows an `nvidia` module. In order:

1. Stop `gdm3`, `sddm`, `lightdm`, `display-manager`, then `nvidia-persistenced`.
2. `killall -9 Xorg Xwayland nvidia-persistenced`, sleep 1.
3. `modprobe -r nvidia_drm nvidia_uvm nvidia_modeset nvidia` (each ignoring failure), sleep 1.
4. If anything is still loaded, `rmmod -f` the four modules.
5. `modprobe nvidia`, then `nvidia-modeset`, `nvidia-uvm`, `nvidia-drm`. On failure it warns
   `Could not reload NVIDIA driver, reboot to finish cleanup`.
6. Restart the first display manager that was enabled.

!!! danger "Step 4 will kill your graphical session"
    `remove.sh` stops display managers and force-unloads modules with `rmmod -f`. Run it from a
    text console or over SSH, not from a terminal inside the desktop session you are about to
    terminate. On a headless compute box this is harmless; on a workstation, expect the display
    to go away and possibly not come back until you reboot.

### Step 5: summary

Prints the log path and, if the GPU or display is not working, tells you to `sudo reboot`.

---

## What `remove.sh` does **not** undo

| Not touched | Why it matters | Manual action |
|---|---|---|
| The kernel command line | Master's `remove.sh` contains no `iommu` or `cmdline` handling at all. IOMMU configuration exists on the `Gen2`, `far` and `deced` branches | If you installed from `Gen2`, `far` or `deced`, use **that same branch's** `remove.sh`, which restores from `<file>.cmpunlocker.bak` and prints `Reverted IOMMU kernel parameters (effective after reboot)`. Running master's `remove.sh` instead leaves the kernel command line permanently modified and an orphaned `/etc/default/grub.cmpunlocker.bak` behind |
| `/etc/modprobe.d/cmp-pcie-gen2.conf` | Written by the Gen2-lineage installers with `options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"` (or `0x2` on `far`/`deced`). Master never creates it and never deletes it | `sudo rm /etc/modprobe.d/cmp-pcie-gen2.conf` and rebuild the initramfs |
| `/usr/local/sbin/retrain.sh`, `cmpretrain.service` | Installed only by the `debug-gen2` branch. The `Gen2` installer removes them; master does not know about them | `sudo systemctl disable --now cmpretrain.service; sudo rm -f /usr/local/sbin/retrain.sh` |
| `/lib/firmware/nvidia/ga100/gsp/dmem.bin` | If you placed a custom payload override there, it stays. A future patched install reads it into the payload buffer instead of running the built-in fill, but the first `kgspSec2PostblTimingRefillPayload()` rewrites that buffer before any Booter Load consumes it, so on the released path the file has no effect | Delete it if you did not put it there deliberately |
| `driver/.build/` cache | The downloaded NVIDIA source tarball and extracted tree, potentially hundreds of MB inside the checkout | `rm -rf driver/.build` or just delete the clone |
| `logs/` | Install and remove transcripts | Keep them; they are useful for troubleshooting |
| The NVIDIA driver itself | `remove.sh` reverts the *patch*, not the driver package. nvidia-open 610.43.0x stays installed | Use your distribution's package manager |
| Anything physical | Capacitor mods, cooling shrouds, power adapters | Out of scope |
| The card's VBIOS | Never written by any part of cmpunlocker | Nothing to do; see [VBIOS](../hardware/vbios.md) |

There is also nothing to undo in the card's non-volatile state. The master kill fuse at
`0x008203f0` reads `0x00000000` (unblown) on every card examined, and nothing in the unlock path
blows fuses or writes OTP. See [Fuses and OTP](../hardware/fuses-and-otp.md).

---

## Verifying the revert

```bash
# Modules gone from every kernel
ls /lib/modules/*/updates/cmpunlocker 2>/dev/null   # expect: no output at all

# The stock module is what resolves and what is loaded
modprobe -n -v nvidia
cat /proc/driver/nvidia/version                      # should now say dvs-builder again

# Capacity back to stock (only after a cold boot)
nvidia-smi --query-gpu=memory.total --format=csv,noheader
#   8 GB card:  8192 MiB
#   10 GB card: 10240 MiB

# No unlock activity this boot
sudo dmesg | grep -c SEC2_DEBUG                      # expect 0 after a reboot
```

After `remove.sh` the card keeps reporting the unlocked size until a cold boot. This
is the normal result, not evidence that the patched module is still resident, because the geometry
registers survive a driver unload and reload. Judge the revert by `modprobe -n -v nvidia`,
`/sys/module/nvidia/srcversion` and the absence of `SEC2_DEBUG` lines in `dmesg`, not by
`memory.total`. If the unlocked size persists after a warm reboot, power the machine off fully and
try again before concluding anything: a warm reboot is not a reset. If it persists after a genuine
cold boot, check that the initramfs was actually rebuilt: a stale initramfs holding the patched
`nvidia.ko` is the usual cause, mirroring the same failure on the install side.

---

## Uninstall before switching branches

The maintainer's rule is to remove the old install before adding a new one: "In fact, I would
always recommend to remove the old one before adding the new one." One tester who cloned the
`Gen2` branch and installed on top of an existing install reported it did not work, and
uninstalling first fixed it.

This is guidance rather than a hard law. At least two other testers installed on top with no
problem, and the informal consensus was that most people are "just sending it on top". The
failure is real but not universal and nobody identified the differentiating factor. Removal-first
is the supported path:

```bash
cd /path/to/old-checkout && sudo ./remove.sh --yes
cd /path/to/new-checkout && sudo ./install.sh
sudo shutdown -h now      # cold boot
```

---

## If the card is wedged rather than merely patched

`remove.sh` is for a healthy system. If the card is in a bad state (a failed boot leaving WPR2
up, a Booter left mid-flight, `RmInitAdapter` failures, or a card that has stopped enumerating),
uninstalling the modules is not the right first move. Go to [Recovery](recovery.md), which covers
function-level reset via `/sys/bus/pci/devices/<BDF>/reset`, the
`modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia` teardown order, and the cases where only
a cold boot clears the state.

A practical multi-tenant example of the difference: one operator's renter killed an
underperforming `llama.cpp` run and left ghost processes behind that wrecked the driver state.
Recovery required a host reboot performed by the operator, because the cards could not be
restarted from inside the container. No amount of uninstalling would have helped.

---

## Related pages

- [Install](install.md) for the forward procedure
- [Verify](verify.md) for what a healthy install looks like, so you know what you are removing
- [Troubleshooting](troubleshooting.md) and [Recovery](recovery.md)
- [Multi-GPU](multi-gpu.md), whose branch installers add files master's `remove.sh` does not know
  about
