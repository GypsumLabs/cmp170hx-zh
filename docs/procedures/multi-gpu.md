# Running several cards

**What this page covers.** What happens when a host has more than one CMP 170HX: why shipping
`master` works on multi-card rigs despite being a single-card installer, what the unreleased
`multiple-cards` branch adds (per-BDF classification, the `gpu_inventory` file, the `mixed`
profile and `SKIP_GEOMETRY_REWRITE`), and the failure modes that only appear once there are two or
more GPUs in the box.

The key result up front: **the unlock itself is already per-GPU.** Since commit `7fe49b6` the
patched `nvidia.ko` carries both geometries and selects one at GSP boot from
`pGpu->idInfo.PCIDeviceID >> 16`, so every card in the machine is unlocked independently with the
right size, whatever the installer thought. What is single-card on `master` is only the
*installer's* bookkeeping: it takes the first matching `lspci` line, guesses one profile from one
`nvidia-smi` reading, and writes one set of metadata files. The `multiple-cards` and `Gen2`
branches replace that bookkeeping with a real per-device inventory.

Multi-GPU operation is confirmed working in practice: one operator passed through eight 8 GB
CMP 170 cards under Proxmox and all of them unlocked. Earlier advice for a six-card rig was to try
`master` first, and a multi-GPU user later confirmed master worked well.

---

## What `master` does on a multi-card host

```bash
lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082' | head -1
```

That `head -1` is the whole story. `install.sh` records one BDF and one device ID, then calls
`detect_card_profile()`, which reads
`nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1`, again taking the
first entry, this time in *nvidia-smi* order rather than *lspci* order. The two orderings are not
guaranteed to agree.

The consequences on current `master`:

| Scenario | Outcome |
|---|---|
| 4x 8 GB cards | Works. All four unlock to 65536 MiB. Profile metadata says `8gb`, which happens to be right |
| 4x 10 GB cards | Works. All four unlock to 40960 MiB |
| Mixed 8 GB + 10 GB | **The geometry is still correct per card**, because it is chosen by device ID at GSP boot. Only `card_profile` / `unlock_geometry` are wrong for whichever type lost the coin toss |
| CMP cards plus an unrelated NVIDIA GPU | The profile may be detected from the *other* card. Still only a metadata error, unless the other card's size falls outside all four detection windows, in which case the install **dies** |
| A `10de:20b0` card is present | Warned about only if it is the *first* matching `lspci` line; sitting behind a `20c2` or `2082` card the `head -1` hides it entirely and no warning is printed. Either way it is never unlocked, because the in-driver gate accepts only `0x20C2` and `0x2082` |

!!! warning "Always pass `--profile` on a mixed-GPU host"
    A host with an RTX 3080 10 GB alongside an 8 GB CMP 170HX was reproduced by at least two
    people detecting "10GB" from the 3080 and selecting the 10 GB profile. A separate report has
    another CMP SKU (a 50HX) misdetected as a 10 GB 170HX. On current `master` this only
    mislabels the metadata files, but the habit of passing `--profile=8gb` or `--profile=10gb`
    explicitly costs nothing and removes a whole class of confusing output.

---

## The `multiple-cards` branch

!!! warning "Experimental: unreleased branch"
    `multiple-cards` (tip `b1cb6d8` "Added support for multiple cards", committed 2026-07-18,
    announced 2026-07-19) has **not** merged into `master` as of tip `cc872cb` (2026-07-23). The
    same installer also exists folded into the `Gen2` lineage via commit `2f27474`
    "Gen2 + multiple-card support". Everything in this section is branch code.

### Per-BDF classification

`detect_card_profile()` is replaced by `profile_from_devid()`:

```bash
profile_from_devid() {
    case "$1" in
        20c2) echo "8gb" ;;
        2082) echo "10gb" ;;
        *) echo "unsupported" ;;
    esac
}

expected_mib_for_profile() {
    case "$1" in
        8gb) echo "65536" ;;
        10gb) echo "40960" ;;
        *) echo "" ;;
    esac
}
```

The installer then walks **every** line of
`lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'` (via `mapfile`, not `head -1`) and builds
five parallel arrays: BDF, device ID, profile, expected MiB, current MiB. Current MiB comes from a
single cached `nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv,noheader,nounits`
lookup, matched by bus ID rather than by index.

Bus IDs are compared through a shared `normalize_bus_id()` that lowercases and expands a short
`BB:DD.F` into `0000:BB:DD.F`, so the `lspci` and `nvidia-smi` spellings compare equal. The same
function exists verbatim in `verify.sh`.

A `20b0` card is classified `unsupported` and **skipped** here, with
`GPU <bdf> (10de:20b0), unlock path not gated for this ID; skipping`, which is a behavioural
difference from master (which warns and continues with that card selected). If every detected card
is unsupported, the branch installer dies with
`No unlockable CMP 170HX GPUs found (need 10de:20c2 and/or 10de:2082)`.

Typical step 2 output:

```text
✓ GPU 0000:0b:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0c:00.0 (10de:20c2) → 8gb (current 8192 MiB, expect ~65536 MiB unlocked)
✓ GPU 0000:0d:00.0 (10de:2082) → 10gb (current 10240 MiB, expect ~40960 MiB unlocked)
==> Inventory: 3 unlockable (2× 8gb, 1× 10gb)
```

### The `mixed` profile

When both `COUNT_8GB > 0` and `COUNT_10GB > 0`, `CARD_PROFILE` becomes a third value, `mixed`:

```text
✓ Mixed variants detected → profile mixed (runtime geometry by PCI ID)
==> Unlock geometry: 64GB for 20c2 / 40GB for 2082 (chosen at GSP boot per GPU)
```

A `--profile=` override is **explicitly discarded** on a mixed inventory, with
`--profile=8gb ignored for mixed inventory; card_profile stays mixed (each card unlocks by PCI
ID)`. On a homogeneous inventory the override is honoured but warns that it is metadata only.
The branch's help text makes the demotion explicit:
`Force 8GB metadata label (geometry is still chosen per PCI ID)`.

### `SKIP_GEOMETRY_REWRITE`

`driver/build.sh` on the branch gains a third case and a guard flag:

```bash
SKIP_GEOMETRY_REWRITE=0
case "${PROFILE}" in
    8gb|8GB)   CFG1="0x02779000"; LMR="0x0000020B"; FB_BYTES="0x0000001000000000"; UNLOCK_LABEL="64GB" ;;
    10gb|10GB) CFG1="0x02669000"; LMR="0x0000028A"; FB_BYTES="0x0000000A00000000"; UNLOCK_LABEL="40GB" ;;
    mixed|MIXED)
        PROFILE="mixed"
        CFG1="0x02779000"; LMR="0x0000020B"; FB_BYTES="0x0000001000000000"
        UNLOCK_LABEL="mixed"
        SKIP_GEOMETRY_REWRITE=1
        ;;
esac

if [[ "${SKIP_GEOMETRY_REWRITE}" -eq 1 ]]; then
    info "mixed profile: runtime device-id geometry (no build-time CFG1/LMR rewrite)"
else
    python3 - ... <<'PY'
    ...
fi
```

Two things are worth noticing in that snippet:

1. In `mixed` mode the `CFG1` / `LMR` / `FB_BYTES` variables are still assigned the **8 GB**
   values, and are simply never used. They are the values a mixed host would try to bake for
   every card if the flag were dropped *and* the rewrite were reachable; point 2 explains why it
   is not.
2. `SKIP_GEOMETRY_REWRITE` is belt-and-braces on top of an existing safety net. The inline Python
   step it skips already begins with a six-marker check for both baked geometries and exits with
   `runtime device-id geometry (profile metadata=<label>)` without editing anything. On any tree
   descended from `7fe49b6` the rewrite is a no-op regardless. The flag matters only if someone
   re-introduces a single-SKU patch.

`unlock_geometry` is written as the literal string `mixed` in that mode, and `card_profile` as
`mixed`.

### The `gpu_inventory` file

`install.sh` exports `CMPUNLOCKER_GPU_INVENTORY` and `build.sh` persists it to
`/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`, one whitespace-separated line per
unlockable GPU:

```text
BDF              devid  profile  expected_mib
0000:0b:00.0     20c2   8gb      65536
0000:0c:00.0     20c2   8gb      65536
0000:0d:00.0     2082   10gb     40960
```

The real file has no header row; the columns above are labelled for readability. If the variable
is empty, `build.sh` truncates the file to zero bytes rather than leaving a stale one.

Like the other three metadata files, **nothing in the kernel modules reads it.** Its only consumer
is `verify.sh`, which prefers it over live `lspci` enumeration so that a card which has fallen off
the bus is reported as `MISSING` rather than silently vanishing from the check.

### `verify.sh` on a multi-card rig

```bash
sudo ./verify.sh
```

Enumerates from `gpu_inventory` if it is readable and non-empty, otherwise falls back to
`lspci -nn | grep -iE '10de:20c2|10de:2082'`. Per GPU it prints `OK`, `STOCK`, `MISSING` or
`UNEXPECTED` against the windows `>= 60000` MiB (8gb) and `35000`-`59999` MiB (10gb), then
summarises:

```text
✓ All 3 unlockable GPU(s) report unlocked memory
```

or fails with `<n> GPU(s) failed unlock verification. Cold reboot if modules were just installed.`
Full details, including the two things it does not check, are in [Verify](verify.md#verifysh).

---

## Known multi-card failure modes

### 1. depmod silently picks one `nvidia.ko`

The highest-value item on this page. A patched and a stock `nvidia.ko` can both end up under the
single `updates` depmod search entry, in which case **depmod picks one arbitrarily and silently
drops the other**. One tester root-caused a multi-GPU failure to exactly this, kept only the
cmpunlocker variant in the updates search path, rebooted, and then confirmed multi-GPU operation
working.

This is the same failure class as the `srcversion` mismatch that `build.sh` warns about: the
running module is not the patched one, so no card unlocks. Diagnose it with:

```bash
modprobe -n -v nvidia | awk '/insmod/ {print $2; exit}'
find /lib/modules/$(uname -r)/updates -name 'nvidia.ko'
cat /sys/module/nvidia/srcversion
modinfo -F srcversion /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko
```

Anything not under `updates/cmpunlocker/` in the first command, or more than one `nvidia.ko` in
the second, is the bug.

### 2. A stale initramfs beats depmod entirely

Unchanged from the single-card case but worse in a rig, because a partial result looks like a
per-card problem rather than a module-loading problem. `build.sh` rebuilds the initramfs itself
and warns `No initramfs tool found, rebuild manually before rebooting` when it cannot. If some
cards unlock and others do not on the *same* boot, this is not the cause; if *none* do, it very
likely is.

### 3. Profile misdetection from the wrong GPU

Covered above. On `master` it is a metadata-only error, except when it makes the install die.

### 4. `verify.sh`'s lspci fallback drops `0x20B0`

`install.sh` greps `10de:20b0|10de:20c2|10de:2082` and then warns or skips `20b0`, but
`verify.sh`'s fallback path greps only `10de:20c2|10de:2082`. A rig containing a `20b0` card will
show a different device count in the installer and in the verifier. Harmless, but confusing.

### 5. Virtualisation constraints

- **Proxmox passthrough works** for memory and compute: eight 8 GB cards passed through and all
  unlocked.
- **Use SeaBIOS, not UEFI/OVMF.** UEFI produces RM init and adapter failures that mimic the
  exploit simply not working. This was root-caused first-hand and immediately corroborated by a
  second person whose non-reproductions turned out to have the same cause.
- **PCIe Gen2 link training does not work in a VM** as of 2026-07-24, acknowledged by the
  maintainer as an open debugging item.

### 6. Host-level wedges in multi-tenant use

One operator's renter killed an underperforming `llama.cpp` run (about 121 t/s) and left ghost
processes that wrecked the driver state. Recovery required a host reboot by the operator, because
the cards could not be restarted from inside the Docker container. Plan for out-of-band reboot
access on any rented rig. See [Recovery](recovery.md).

### 7. Interconnect, not installer

Several "multi-card is slow" reports are link-bandwidth problems, not unlock problems:

- Every card is Gen1 x4 by default. Going to Gen2 is a software change on unreleased branches;
  going beyond x4 width requires soldering AC-coupling capacitors. These are two entirely separate
  achievements. See [PCIe subsystem](../hardware/pcie-subsystem.md) and
  [PCIe Gen2](../unlock/pcie-gen2.md).
- **NVLink is fused off** and P2P is absent on this card. `llama-server --split-mode row` was
  circulated alongside the layer-split command but annotated "benchmark-only on these links",
  consistent with tensor-parallel-style splits not being viable at Gen1 x4.
- A frequently quoted rule of thumb ("x4 gives 10-30% speedup, x8 or better is ideal" for
  multi-GPU LLM serving) was offered as a rule of thumb and **was not measured on a 170HX**. Treat
  it as low confidence. See [LLM inference](../operations/llm-inference.md).

### 8. P2P layering

The `aikitoria` P2P patch can be layered on top of cmpunlocker by dropping its diff into
`driver/patches/` as `0007-unlock-p2p.patch`, because `build.sh` applies every `*.patch` in glob
order. Whether it does anything useful on a 170HX-only system is unresolved: one tester reported
"It doesn't seem to take effect on the 170HX... It only has an effect on them if there are other
models of GPUs on the same machine", while another reported P2P plus cmpunlocker working on the
same day in a rig that also contained two RTX 3090s, which is precisely the mixed-model case the
first report says is the only one that works. Both sides agree P2P is bandwidth-bound and of
little benefit at Gen1 x4. See [P2P](../frontier/p2p.md).

---

## Recommended procedure for a multi-card rig today

1. Inventory the hardware before installing anything:

   ```bash
   lspci -nn | grep -iE '10de:20b0|10de:20c2|10de:2082'
   nvidia-smi --query-gpu=pci.bus_id,name,memory.total --format=csv
   ```

   Confirm the device ID of every card. See [Identify your card](../start/identify-your-card.md).

2. Install from `master` with an explicit profile if all cards are the same type:

   ```bash
   sudo ./install.sh --profile=8gb     # or --profile=10gb
   ```

   For a genuinely mixed 8 GB + 10 GB rig, `master` still produces correct geometry per card; the
   only thing you give up is accurate metadata and `verify.sh`. If you want those, use the
   `multiple-cards` branch and accept that it is unreleased.

3. Cold boot. `sudo shutdown -h now`, then power on.

4. Verify **every** card individually, not just the first:

   ```bash
   nvidia-smi --query-gpu=pci.bus_id,memory.total --format=csv
   sudo dmesg | grep 'POST-WRITE'      # one line per unlocked GPU, with its devId
   ```

   The `POST-WRITE` line carries `(devId=0x...)`, so a rig with mixed SKUs should show both
   `CFG1=0x02779000 LMR=0x0000020b` and `CFG1=0x02669000 LMR=0x0000028a` lines.

5. If exactly one card is wrong, suspect that card (seating, power, riser). If all are wrong,
   suspect module loading (failure modes 1 and 2).

---

## Merge status

!!! question "Open problem: should multi-card, IOMMU and Gen2 merge to master, and in what order?"
    Neither `multiple-cards` (`b1cb6d8`, standalone) nor the `Gen2` lineage (which folds it in)
    has merged as of `cc872cb`. The obstacle is bundling: merging `Gen2` wholesale would drag the
    experimental PCIe link retraining patches (`0007-pcie-gen2.patch`,
    `0008-pcie-gen2-probe-retrain.patch`) and their unverified register writes into the stable
    path. The multi-card installer changes are self-contained and could be cherry-picked alone,
    and the `mixed` profile already works because master's patch 0001 bakes in both geometries.
    Separately, `clanker/driver-port` (580/590/595/610 support) and the Gen2 lineage were
    developed independently and never merged, so choosing one today means giving up the other.
    See [Status board](../frontier/status-board.md) and
    [Driver versions](driver-versions.md).

---

## Related pages

- [Install](install.md), [Verify](verify.md), [Uninstall](uninstall.md)
- [Troubleshooting](troubleshooting.md) for symptom-first diagnosis
- [Driver patches](../unlock/driver-patches.md) for the device-ID gate that makes per-card
  geometry work
- [PCIe subsystem](../hardware/pcie-subsystem.md) for what the links can actually carry
