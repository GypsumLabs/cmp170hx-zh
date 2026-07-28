# Recovery

**What this page covers.** How to get a CMP 170HX back to a working state when it will not
initialise: the reset ladder from cheapest to most drastic, what a cold boot does that a warm
reboot does not, what FLR clears and what only a secondary bus reset (SBR) clears, exactly which
register state survives each kind of reset, how to remove the patched modules and restore a stock
system, and an honest assessment of how much real bricking risk exists.

**The short answer.** The unlock writes registers. It writes no fuses, no VBIOS, no EEPROM and (on
the shipping tool) no firmware file. Every geometry register it touches is volatile and reverts on
power loss, which means **a card that will not come up is almost always recoverable by removing
power**. No permanent brick has ever been confirmed in the entire corpus. One first-hand report
contradicts the no-persistent-state model and is documented honestly in
[Bricking risk](#bricking) below; it remains unexplained.

If you have one minute: shut the machine down, switch the PSU off or unplug it, wait 60 seconds,
power back on. That single action resolves the large majority of wedges.

---

## 1. The reset ladder { #reset-ladder }

Work down this list. Each rung is more disruptive than the last, and each is only worth trying if
the one above it failed.

| # | Rung | Command | Clears |
|---|---|---|---|
| 1 | Reload the driver | `modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia && modprobe nvidia` | Driver-side software state only |
| 2 | Function level reset (FLR) | `sudo rmmod nvidia_uvm nvidia`; `echo 1 \| sudo tee /sys/bus/pci/devices/$BDF/reset` | Engines, WPR2, PL0 scratch, SEC2 reset-PLM taint, Falcon IMEM contents; **resamples fuses** |
| 3 | PCI detach and rescan | see [3.4](#detach-rescan) | An off-bus card reading BAR0 `0xffffffff`; requires restoring bus mastering afterwards |
| 4 | Secondary bus reset (SBR) | issued on the upstream bridge | Everything FLR clears, **plus** the always-on (AON / PGC6 "GC6 island") power domain |
| 5 | Full power-off cold boot | PSU switch off or cable unplugged, 60 s wait | Everything, including capacitor-held state |
| 6 | Physically remove the card | leave it out for a period | Last resort; used once in an unexplained case |

Rung 2 in full:

```bash
sudo rmmod nvidia_uvm nvidia
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
```

Rung 5 is the primary recovery tool in practice. The recorded first-hand advice is blunt: "lots of
cold boots required from the way this gets wedged", with unplugging the PCIe power from the card
while shut down recommended alongside.

**Why the ladder has both FLR and SBR.** FLR resets the engines but **not** the AON island, so a
`0x65` wedge rooted in AON scratch survives FLR while SBR clears it. See
[FLR versus SBR](#flr-vs-sbr).

*(Confidence: high for the ladder itself; medium for the AON mechanism.)*

---

## 2. Cold boot versus warm reboot { #cold-boot }

**A warm reboot is not a reset.** It leaves WPR2 up and the board capacitors charged. Every
published procedure that calls for "a reboot" after a failed unlock means a **cold** one, and the
distinction is load-bearing: the same symptom that survives five `reboot` cycles frequently clears
on the first genuine power cycle.

### The procedure { #cold-boot-procedure }

```bash
sudo systemctl poweroff
```

1. Wait for a complete shutdown. SSH drops, fans stop.
2. Turn off the PSU switch, or unplug the power cable.
3. **Wait 60 seconds** for capacitor discharge and WPR2 reset.
4. Plug back in and power on.

The 60-second wait is prescribed as a hard requirement at every stage of the published guide, and
it is consistent with the WPR2 save-and-restore behaviour of the shipping patch. The same procedure
is prescribed for both the PLM-not-opened and the VRAM-still-8-GB symptoms.

Some cards have additionally needed their PCIe power cable physically unplugged and re-seated after
a cold boot before they behaved. That is reported friction, not an explained mechanism.

### When a cold boot is mandatory rather than advisory { #cold-boot-required }

* After a first boot that does not unlock. An OS reboot is explicitly not sufficient.
* After `[WARN] Modules installed but the running driver is still stock`.
* After a `GSP didn't boot` / status `0x65` failure. One tester confirmed that removing old kernel
  modules alone was not enough.
* After installing patched modules for the first time (the branch-only `verify.sh` says so in its
  own failure string: "Cold reboot if modules were just installed.").
* Between attempts on the over-provisioned 80 GB configuration, where one tester had to cold-cycle
  the entire system rather than just reload the driver.

---

## 3. Resets in detail { #resets }

### 3.1 Function level reset (FLR) { #flr }

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/reset
sleep 3
```

FLR wipes PL0 scratch writes and **resamples fuses**. A plain `modprobe` reload does not wipe
config-space writes; FLR does. This was tested using the PL0 scratchpad at `0x14A0` as a proxy and
corroborated by the exploit's original author.

**A successful FLR does clear WPR2.** The staged measurement of `WPR2_LO` / `WPR2_HI` / GSP
mailbox:

| Stage | WPR2_LO | WPR2_HI | GSP mailbox |
|---|---|---|---|
| Cold boot (WPR2 disabled) | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| After the ROP fire (Booter set it up) | `0x01F77000` | `0x01FFEE00` | `0x8FAE1000` |
| After FLR | `0x1FFFFE00` | `0x00000000` | `0x00000000` |
| Stock driver loaded afterwards | `nvidia-smi` worked, 8192 MiB | | |

!!! note "Superseded"
    "FLR doesn't clear WPR2" circulated as a general truth, sourced from an NVIDIA forum post and
    consistent with some observations. The four-stage measurement above disproved it. The claim
    applies only to the broken path where the ACR mutex was never released.
    *(Caveat: the same document's premise, that returning to `0x8103` works, was independently
    shown broken on hardware, so the mutex attribution is not airtight.)*

FLR also clears the SEC2 reset-PLM taint: `0x8f` becomes `0xff`.

**FLR removes the Booter from Falcon IMEM.** `EXCI 0x0a (MISS_INS)` after writing DMEM post-FLR
means exactly that: the Booter is no longer resident, because the FLR removed it.

### 3.2 Secondary bus reset (SBR) { #flr-vs-sbr }

SBR is issued on the upstream bridge rather than the device, and it drops and re-initialises the
always-on power domain that FLR leaves alone.

**Why FLR sometimes cannot recover a `0x65` wedge.** `SECURE_SCRATCH_14` (`0x001180f8`) lives in
the PGC6 "GC6 island" always-on power domain and is marked RW-4R (priv-masked). AON scratch
survives engine resets and FLR, so an un-DONE handoff plus the poisoned PLM and privilege state
that made the Booter's own DIO read of `0x1180f8` return `0xdead5ec1` persists straight through
FLR. SBR drops and re-inits the AON power domain, clearing the scratch so a fresh Booter can run
stage 3 and set DONE itself.

*(Confidence: medium. The empirical pattern "FLR doesn't clear it, SBR does" is repeatedly
observed; the AON / GC6 description attached to it is unverified.)*

### 3.3 What each reset leaves behind { #state-persistence }

This table is the core of the page. It explains both why the unlock is not persistent and why the
card is hard to permanently damage.

| State | Survives `modprobe` reload | Survives FLR | Survives SBR | Survives power cycle |
|---|---|---|---|---|
| SS0 `0x0082381c` = `0x88888888` | yes | **yes** (AON) | not established | no |
| SS1 `0x00823820` = `0x00000008` | yes | **yes** (AON) | not established | no |
| `FEAT_OVR_PLM` `0x00823804` | yes | **yes** (AON) | not established | no |
| CFG1 `0x009a0204` | yes | no | no | no |
| Per-FBPA CFG1 (`0x00900204 + n*0x4000`) | yes | no | no | no |
| CSTATUS_RAMAMOUNT | yes | no | no | no |
| MMU LMR `0x00100ce0` | yes | no | no | no |
| FB-geometry PLMs | yes | no | no | no |
| AON LMR shadow `0x001180f0` | yes | no | no | no |
| WPR2 bounds `0x001fa824` / `0x001fa828` | yes | **no**, reset to `0x1FFFFE00` / `0x0` | no | no |
| SEC2 reset-PLM taint (`0x8f`) | yes | **no**, returns to `0xff` | no | no |
| `SECURE_SCRATCH_14` `0x001180f8` (AON) | yes | **yes** | **no** | no |
| Falcon IMEM contents (Booter resident) | yes | no (`EXCI 0x0a`) | no | no |
| PL0 scratch (proxy `0x14A0`) | yes | no | no | no |
| PCI `COMMAND.BusMaster` | cleared by `rmmod nvidia` | reset to defaults | reset | reset |
| Fuses | yes | **resampled**, values unchanged | resampled | resampled |
| VBIOS, EEPROM, on-disk firmware | yes | yes | yes | **yes** |

**Two consequences follow directly.**

*Compute shipped before memory because of the FLR asymmetry.* SS0, SS1 and the feature-override PLM
sit in the always-on island and survive FLR; the entire memory geometry does not. That is why the
old FLR-based pipelines could unlock compute across a reset but lost the geometry every time. It is
also why the shipping patch opens the PLMs and writes the geometry inside **one** GSP boot, with no
reset in between. See [Memory geometry](../unlock/memory-geometry.md) and
[Compute throttle](../unlock/compute-throttle.md).

*Nothing the unlock writes survives a power cycle.* A card left unpowered comes back stock. That is
the single most important fact behind the bricking assessment below.

### 3.4 The card has fallen off the bus { #detach-rescan }

If BAR0 reads `0xffffffff`, the card is off-bus. Detach and rescan, then restore bus mastering:

```bash
echo 1 | sudo tee /sys/bus/pci/devices/$BDF/remove
echo 1 | sudo tee /sys/bus/pci/rescan
sudo setpci -s ${BDF#0000:} COMMAND=0x0546
```

The `setpci` step matters. `0x0546` has bit 2 (Bus Master) set; `0x0102` does not, and a card with
bus mastering off will silently do nothing when the standalone tooling fires at it, with no DMA
error anywhere in the log. See
[Bus mastering cleared](troubleshooting.md#bus-master) for the full failure mode.

If the card never reappears at all, and never did after a cold boot, the cause may be hardware
rather than state. See [The card dropped off the PCIe bus](troubleshooting.md#off-bus) for a fully
diagnosed board-level failure (a dead GS7155NVTD LDO shorting `PS_5V_PGOOD`) and its repair.

### 3.5 Tearing the driver down before a reset { #teardown }

FLR is unreliable while the driver is holding the device. The working teardown order is:

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

The nvidia module frequently refuses to unload regardless, leaving `nvidia 15835136 2` with `drm`
held by seven users including `i915`. That dependency chain is a practical reason to do unlock work
on a headless or non-NVIDIA-display host.

### 3.6 A card that boots pre-wedged { #boot-pre-wedged }

If the machine will not shut down, or the card wedges again before you can intervene, the driver
is autoloading and re-wedging it. Boot with the card disconnected, or blacklist the module from the
bootloader command line, then clean up:

```text
# GRUB kernel command line, one boot
modprobe.blacklist=nvidia,nvidia_uvm,nvidia_drm,nvidia_modeset
```

One 10 GB card was stuck in an uninterruptible-sleep state that survived about five cold reboots
and prevented Ubuntu from shutting down. **The cause was the autoloading patched kernel driver, not
the card.** Booting with the card disconnected and cleaning up resolved it.
*(Confidence: medium; root cause identified by the affected tester after recovery.)*

---

## 4. Removing the patched modules { #remove }

### 4.1 The supported path { #remove-sh }

```bash
sudo ./remove.sh --yes
```

`remove.sh` refuses to run without `--yes` or `-y`. It runs five steps and writes
`logs/remove_YYYYMMDD_HHMMSS.log`, falling back to `/tmp` if the repository directory is not
writable. What it does:

* Stops display managers and force-`rmmod`s if `modprobe -r` fails.
* Stops, disables and deletes the legacy `/etc/systemd/system/cmpunlocker.service`, and kills any
  leftover `/opt/cmpunlocker/daemon/watchdog.py` process. Both are vestiges of an abandoned
  watchdog design that the current installer never creates.
* Removes `/lib/modules/*/updates/cmpunlocker/` **on every kernel**, running `depmod -a` per kernel.
* Deletes the legacy `/opt/cmpunlocker` install directory.
* Deletes firmware-patching-era leftovers: for every `/lib/firmware/nvidia/*/gsp_tu10x.bin` it
  removes `.cmpunlocker.bak`, `.cmpunlocker.patched`, `.cmpunlocker.tmp`, `.cmpunlocker.cleanup`
  and `.cmpunlocker.pat`.
* Rebuilds the initramfs and reloads stock modules.

!!! danger "There is no `uninstall.sh`"
    Documentation on the `docs` branch references `sudo ./uninstall.sh --yes`. **No such script
    exists**, on master or on the docs branch itself. The correct command is
    `sudo ./remove.sh --yes`, and that branch's own `ARCHITECTURE.md` says so.

Master's `remove.sh` does **not** touch the kernel command line. IOMMU configuration and its
reversal exist on the `Gen2`, `far` and `deced` branches, where `remove.sh` restores
`*.cmpunlocker.bak` and prints either `Reverted IOMMU kernel parameters (effective after reboot)`
or `No IOMMU config backup found, kernel command line left as-is`.

Finish with a cold reboot. Then confirm the stock module is back:

```bash
cat /proc/driver/nvidia/version          # should show a dvs-builder release build
sudo dmesg | grep SEC2_DEBUG             # should print nothing
nvidia-smi                               # 8192 MiB or 10240 MiB
```

See [Uninstall](uninstall.md).

### 4.2 Three-tier manual rollback { #rollback-tiers }

Each tier ends in a cold reboot. Escalate only if the previous tier did not restore a working
stock stack.

**Tier 1: undo the module install by hand.**

```bash
sudo systemctl stop nvidia-persistenced
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo rm -rf /lib/modules/$(uname -r)/updates/cmpunlocker/
sudo depmod -a
# restore the backed-up stock nvidia.ko, then:
sudo apt install --reinstall nvidia-driver-610-open
```

**Tier 2:** `sudo ./remove.sh --yes`.

**Tier 3:** remove the 610 stack entirely and install 580.

### 4.3 Undoing prior experiments { #undo-experiments }

A machine that has been used for unlock development accumulates state that will silently break a
clean install. Before reinstalling, undo all of it:

* Delete `/etc/modprobe.d/blacklist-nvidia-manual.conf`.
* Remove any dpkg diverts.
* Restore `nvidia-lib-bak`.
* Restore stock `gsp_tu10x.bin` from `.stock` / `.backup` / `.bak` copies under
  `/lib/firmware/nvidia/610.43.03/` and `/lib/firmware/nvidia/580.173.02/`.

!!! danger "A stale patched `gsp_tu10x.bin` poisons the in-driver unlock"
    If the firmware-patching predecessor was ever used on this machine, restore the stock blob
    before running the in-driver patch:

    ```bash
    GSP_DIR=/lib/firmware/nvidia/610.43.03
    sudo cp $GSP_DIR/gsp_tu10x.bin.cmpunlocker.bak $GSP_DIR/gsp_tu10x.bin
    ```

    The driver saves the firmware's signature as "stock" during boot. If the firmware is still
    patched, it saves the **exploit payload** instead, and the clean GSP-RM boot then DMAs the
    wrong ROP chain. The success line to look for afterwards is
    `SEC2_DEBUG: saved stock signature (4096 bytes)`.

### 4.4 Restoring a version-matched firmware directory { #restore-firmware }

A deleted or mismatched `/lib/firmware/nvidia/<version>/` directory produces a failure that looks
like gradual hardware degradation. One multi-day "model degradation" that could not be reproduced
turned out to be a deleted
`/lib/firmware/nvidia/580.159.03/{gsp_tu10x.bin, booter_*.bin}` combined with a `.04` userspace
`nvidia-smi` that would not trigger GPU init on a `.03` module. `SEC2 MBOX0 = 0x0` in that state
means the Booter never loaded at all. Restoring the version-matched firmware directory immediately
reproduced the previous working state.

Keep a diff or changelog of any driver modification. Reinstalling a fresh driver silently discards
every needed injection.

### 4.5 Going back to a stock, never-touched card { #restore-stock }

There is nothing to undo in hardware. The unlock is a patch on top of the mainline NVIDIA driver,
not a firmware replacement, so once the patched modules are gone and the machine has been power
cycled, the card is bit-for-bit the card you started with: CFG1 `0x02449000`, LMR `0x00000208` or
`0x00000288`, `CSTATUS_RAMAMOUNT` `0x200` per FBPA, SS0 back to its locked value.

The card also runs on **stock** Linux NVIDIA drivers with no patch at all (`nvidia-driver-570` plus
CUDA 12.8 on Ubuntu 24.04 works out of the box, and `nvidia-driver-535-server` on Ubuntu 22.04 was
also reported), reporting as `NVIDIA Graphics Device`, compute capability 8.0. Being driveable and
being unlocked are separate things, and confirming the first is a good way to prove the card
survived whatever you did to it.

---

## 5. How much bricking risk is there really? { #bricking }

### 5.1 The evidence { #bricking-evidence }

**No permanent brick was ever confirmed anywhere in the corpus.** The specific claims and their
dispositions:

| Claim | Disposition |
|---|---|
| A card was bricked during the cleanroom work | An LLM agent's mistaken conclusion after it lost track of the fact that the cards could be reset |
| "CMP 170HX cards get bricked by the unlock or by NVIDIA-poisoned drivers" | No first-hand report exists. The specific public case cited was assessed as a 10 GB card being pushed to 80 GB |
| A motherboard PCH failure was caused by 170HX testing | The original post used the word "coincidentally"; no causal mechanism was established. Recorded as a risk anecdote only |
| Sellers describing a "defective batch" during the late-July 2026 price spike | Used as a cancellation excuse against listings that had shown working cards. No defective card was shipped or diagnosed in the documented cases |

The structural argument is stronger than the absence of reports. The shipping unlock:

* writes only volatile registers, all of which revert on power loss;
* blows no fuses (the master kill fuse `0x008203f0` reads `0x00000000` and is never written);
* does not flash the VBIOS or any EEPROM;
* on the shipping tool, does not modify any file under `/lib/firmware` (the earlier
  firmware-patching generation did, which is why `remove.sh` still cleans up after it);
* is fully reverted by `remove.sh` plus a power cycle.

### 5.2 The one report that does not fit { #bricking-contradiction }

!!! question "Open problem"
    One first-hand account describes a 10 GB card wedged with three stuck D-state threads that
    would not clear with FLR, SBR, PCI detach and reattach, **or a full PSU power-off cold boot**:
    "when I rebooted, the registers were still written, and the D-threads were still there... card
    booted pre-wedged". Recovery eventually required holding the power switch with the strip off
    and physically removing the card for a few hours.

    The observation was doubted in-channel and remains unexplained. It **contradicts** the
    otherwise well-supported model that the mod changes no persistent state, which is exactly why
    it is worth resolving rather than dismissing. The cause offered at the time was "booting a
    patched proprietary blob for cpu rm after a driverless payload delivery". Two other wedges in
    the same account: one caused by an agent writing `FUSE_SS_PLM`-style registers (needed a full
    power cycle), and one from "enter `0x10aa` at `0x10b9`" that hard-bricked a test bench.

    What would settle it: a fresh capture of the register values immediately after such a cold
    boot, with a photograph of the power state.

Until that is resolved, the honest statement is: **the model says a power cycle always wins, and
in every reproducible case it did, but one credible operator reports a state that survived one.**

### 5.3 What the real risks actually are { #real-risks }

The residual risks named by the people closest to the work are not exotic:

1. **Ordinary used-hardware failure.** These are ex-mining cards. The one fully diagnosed
   permanent-looking failure in the corpus was a dead 3.3 V LDO on the board, entirely unrelated to
   the unlock, and it was repairable at component level. See
   [Card off the bus](troubleshooting.md#off-bus).
2. **The patch set is actively changing.** Branch churn, not silicon, is what breaks installs.
3. **Thermal damage to HBM.** Chronic under-cooling degrades HBM. The failing burn-in card in the
   record ran at 85 °C with a memory overclock; error-free cards stayed below 73 °C.
   *(Confidence: medium; no failure-rate data exists.)* See [Thermals](../hardware/thermals.md).
4. **Running the card outside its stable geometry.** The 8 GB card at 64 GB is stable and in
   production; the 10 GB card at 40 GB is stable; the 10 GB card at 80 GB reports the capacity but
   is unusable above roughly 40 GB: kernels touching more than that cause fatal GPU loss,
   independent of power limit. Reported Xid codes include Xid 31 (described as harmless) and
   Xid 154 after CUDA memory tests; the dominant reported symptom is hangs, alongside burn-in
   errors. Xid 31 alone was suggested by a bystander and was not corroborated as *the* signature
   by the operator with the failing card. This destroys workloads, not cards. See
   [80 GB](../frontier/80gb.md).
5. **Operator error with live jobs.** `kill -9` on live multi-GPU jobs wedges the host CUDA runtime
   (roughly 32 zombie processes, `cuInit` returning 999) and needs a host reboot. SIGKILL on a
   verification kernel can wedge the card with Xid 45. Across a full 8-card session with hundreds
   of 60-second health samples there were **0** hard faults when the workload was driven properly.

!!! danger "Where real hardware risk does live"
    The one place in this project with genuine, irreversible hardware risk is the **capacitor mod**:
    24 × 0402 220 nF X7R parts hand-soldered in the C1100 to C1350 range on an 8 to 12 layer board
    that needs 420 °C hot air for 2 minutes before a chip will lift. That is a soldering risk, not
    a firmware risk, and it is covered separately in
    [Physical mods](../operations/physical-mods.md). Note also that the capacitor mod changes lane
    **count** only. It never changes PCIe generation.

### 5.4 A practical safety posture { #posture }

* Keep the card's stock behaviour verifiable: know that it enumerates and runs on an unpatched
  stock driver before you start.
* Prefer a headless or non-NVIDIA-display host, so the module can actually be unloaded.
* Do unlock development in a VM or container where practical. One developer reported needing to
  reinstall the OS after every botched `nvidia.ko` deploy on bare metal.
* Pin the driver at 610 as a long-term precaution against a future NVIDIA release closing the hole,
  the same way P100 and V100 users pin around 580. *(Confidence: medium; reasoned advice, not yet
  needed, because no blocking driver exists.)*
* Do not `kill -9` live jobs. Do not run the over-provisioned geometry on hardware you care about.
* Before asking for help, capture `sudo dmesg | grep SEC2_DEBUG` and the newest install log. See
  [Escalation](troubleshooting.md#escalation).

---

## Related pages

* [Troubleshooting](troubleshooting.md): symptom to cause to fix, indexed
* [Uninstall](uninstall.md): `remove.sh` in full
* [Install](install.md): the supported install procedure
* [Verify](verify.md): confirming a good state
* [Risks](../start/risks.md): the orientation-level version of this assessment
* [Privilege level masks](../unlock/privilege-level-masks.md): which PLMs are AON and which are not
* [Memory geometry](../unlock/memory-geometry.md): why geometry does not survive a reset
* [Register reference](../unlock/register-reference.md): every register named on this page
