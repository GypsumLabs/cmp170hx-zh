# Peer-to-peer and multi-GPU

## What this page covers

Whether two CMP 170HX cards can talk to each other directly, what the third-party
`aikitoria/open-gpu-kernel-modules` P2P patch does, how it is layered on top of
[cmpunlocker](../unlock/driver-patches.md) with a documented three-commit diff, what IOMMU and
BAR sizing have to do with it, and what is still unknown.

**The short answer: peer-to-peer is absent on this card by default.** No shipping code enables
it and every measurement in the corpus reports it unavailable. The one third-party patch that
could plausibly change that does build and load on top of the unlock, which is itself a useful
result, because it proves the cmpunlocker build system composes with unrelated driver diffs.
One builder has since reported that the patch half-works on GA100: peer *data movement* runs at
6.25 GB/s while peer *synchronisation* does not work at all, which would leave NCCL and every
other collective library hanging. That report is **unverified**, from one rig with no
independent reproduction. See
[Unverified report](#unverified-report-peer-dma-works-peer-synchronisation-does-not).

**The second short answer: even if P2P worked, the link would still be the bottleneck.** At
PCIe Gen1 x4 (about 1.0 GB/s) the position broadly agreed across the project is that P2P is
bandwidth-bound and buys little before Gen3. The furthest the project has reached in software is Gen2 x4, which
shipped in `master` on 2026-07-29; Gen2 x16 has been reproduced on two rigs, and only on cards
carrying the 24-capacitor solder mod. See [PCIe Gen2](../unlock/pcie-gen2.md) and
[Gen3/Gen4](pcie-gen3-gen4.md).

---

## The measured baseline: what "no P2P" looks like

| Observation | Result | Conditions |
|---|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | `False` for **all 56** pairs (P2P-capable pairs: 0 of 56) | 8 unlocked cards, all pairs, including within a `PIX` group |
| ggml `-lv 5` log | zero `peer` / `p2p` / `rpc` occurrences | same rig |
| `nvidia-smi nvlink` | `Device does not have or support Nvlink.` | same rig, 8 unlocked 64 GiB cards, 2026-07-24; the only capture in the corpus |
| MIG profile listing | `1g.64gb`, ID 0, 63.00 GiB, 70 SMs, 5 CEs, **P2P No** | only profile offered by `nvidia-smi mig -lgip` on an unlocked card |
| Active link during the sweep | Gen1 x4, ~1.0 GB/s, did not ramp under inference load | device maximum reported as Gen2 x16 |

The absence is also visible in the source tree rather than only in telemetry. A grep for `p2p`
and `peer` across shipping `master` and all twelve unreleased branches returns exactly two kinds
of hit: the stock `nvidia-peermem.ko` filename in the `build.sh` module install list, and one
line of unmodified context (`nv_uvm_resume_P2P(pUuid)`) inside the Gen2 branch's
`0008-pcie-gen2-probe-retrain.patch`. **No branch contains any P2P enablement.**

> [!NOTE]
> **`nvidia-peermem` is not the same thing**
>
> `build.sh` collects and installs five modules: `nvidia.ko`, `nvidia-modeset.ko`,
> `nvidia-uvm.ko`, `nvidia-drm.ko` and `nvidia-peermem.ko`. `nvidia-peermem` is the stock
> peer-memory client that lets third-party RDMA hardware reach GPU memory. Seeing it built and
> loaded (including the harmless `Skipping BTF generation for ... nvidia-peermem.ko` line) is
> **not** evidence that GPU-to-GPU peer access is available.

### Why it matters: the measured cost

With `-sm layer` split on an 8-card, 80-layer model (10 layers per GPU), every generated token
makes **7 GPU to CPU RAM to GPU hops**, one of which crosses a NUMA/socket boundary at the layer
49 to 50 transition. The consequence shows up as a concurrency ceiling:

| Concurrent users | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| Aggregate tok/s | 17.3 | 21.6 | 25.7 | 28.1 | 38.9 |
| Per-user tok/s | 17.3 | 10.8 | 6.4 | 3.5 | 2.4 |
| Batch wall time (s) | n/a | 11.9 | 20.0 | 36.5 | 52.6 |
| Scaling versus 1 user | 1.00x | 1.25x | 1.49x | 1.62x | 2.25x |

That is **2.25x aggregate scaling from 1 to 16 users**, attributed in the source report to three
causes together: the absence of P2P/NVLink, a cross-NUMA pipeline hop, and the link. It is one
sweep on one virtualised host whose link read active Gen1 x4 with a device maximum of Gen2 x16. Tensor parallelism, the strategy that would benefit
most from peer access, is a measured dead end on these links:

| Configuration | Prefill 1k / 4k / 16k (t/s) | Decode (t/s) |
|---|---|---|
| 1 card | 839 / 1,092 / 960 | 27.3 |
| PP2 (pipeline) | 829 / 1,084 / 1,167 | 29.1 |
| TP2 (tensor) | 316 / 420 / 416 | 33.7 |

Qwen2.5-72B dense AWQ under vLLM at Gen1 x4. TP is 2.3-2.8x worse at prefill for +23% decode.
More in [LLM inference](../operations/llm-inference.md).

---

## The aikitoria fork

`github.com/aikitoria/open-gpu-kernel-modules` is a fork of
`tinygrad/open-gpu-kernel-modules`, created 2024-10-14. Its default branch is **`610.43.03-p2p`**,
which is the same driver version cmpunlocker targets, and branch names in the fork run from 515
through 610.43.03. That version alignment is what makes the layering workable at all: master's
`build.sh` hard-fails on any driver version not listed in `driver/VERSION`
(`610.43.03`, `610.43.02`).

The branch is three commits on top of a plain NVIDIA release import:

| Commit | Subject | Scope |
|---|---|---|
| `452cec62d827` | `610.43.03` (base import, 2026-07-07) | `README.md`, `kernel-open/Kbuild`, `dp_connectorimpl.cpp`, `nvBldVer.h`, `nvUnixVersion.h`, `version.mk` |
| `9fb650447c7b` | Combined P2P mod | 8 files, **+83 / -28** |
| `52670f7fd6a7` | Experimental hugepage `cudaHostRegister` | 7 files, **+383 / -97** |
| `2849449f8cd6` | README update | **+245** |

The P2P commit itself touches:

| File | Delta |
|---|---|
| `install.sh` | +7 |
| `kernel-open/nvidia-uvm/uvm_gpu.h` | +7 |
| `kernel-open/nvidia/nv-reg.h` | +1 / -1 |
| `src/nvidia/generated/g_kern_bus_nvoc.c` | +5 / -5 |
| `src/nvidia/src/kernel/gpu/bif/kernel_bif.c` | +3 / -3 |
| `src/nvidia/src/kernel/gpu/bus/arch/pascal/kern_bus_gp100.c` | +10 |
| `src/nvidia/src/kernel/mem_mgr/io_vaspace.c` | +11 / -10 |
| `src/nvidia/src/kernel/rmapi/nv_gpu_ops.c` | +39 / -9 |

**Mechanism:** it enables **BAR1 peer-to-peer** on GPUs where NVLink is absent and falls back to
NVLink where present. For a PCIe pair, transfers write directly into the other GPU's physical
address over DMA rather than bouncing through host RAM.

> [!WARNING]
> **Experimental: GA100 is not a supported configuration**
>
> The branch README lists RTX 3090 (pairwise NVLink where available, PCIe BAR1 otherwise),
> RTX 4090 (PCIe BAR1) and RTX 5090 (PCIe BAR1), and states that P2P also works between
> different devices of the same generation. **GA100 is not on that list, and the patch has
> never been validated on a 170HX.** The code path it modifies is
> `kern_bus_gp100.c` (Pascal-and-later bus code), `io_vaspace.c` and `nv_gpu_ops.c`, so a
> working GA100 branch inside it may simply not exist.

---

## The three-commit diff workflow

This is the exact recipe posted with a working build screenshot on 2026-07-23:

```bash
git clone https://github.com/aikitoria/open-gpu-kernel-modules open-gpu-kernel-modules-p2p
git -C open-gpu-kernel-modules-p2p diff --src-prefix=a/ HEAD~3 > ./cmpunlocker/driver/patches/0007-unlock-p2p.patch
cd ./cmpunlocker && sudo install.sh
```

### Why it composes

`driver/build.sh` deletes and re-extracts a clean stock tree, then applies **every** file matching
`driver/patches/*.patch` in glob (lexicographic) order with `patch -p1`:

```bash
rm -rf "${SRC_DIR}"
# ... re-extract open-gpu-kernel-modules-${VERSION}.tar.gz ...
for p in "${patches[@]}"; do
    patch -p1 < "${p}"
done
```

The script runs under `set -euo pipefail`, so a failing hunk aborts the build rather than
producing a half-patched module. Naming the third-party diff `0007-unlock-p2p.patch` sorts it
after the shipping series `0001`-`0006`, so the unlock lands first and the P2P changes apply on
top. `--src-prefix=a/` guarantees the `a/` and `b/` path prefixes that `patch -p1` expects.
`HEAD~3` with no second revision diffs the working tree against three commits back, producing one
squashed patch containing all three commits, not three separate ones.

The mechanism is code-confirmed. The specific diff's compatibility with 610.43.0x was reported by
one tester and not independently reproduced, so treat the recipe as medium confidence.

> [!CAUTION]
> **You are also installing the experimental hugepage commit**
>
> `HEAD~3..HEAD` includes `52670f7fd6a7`, which accelerates `cudaHostRegister` for
> 1G-hugepage-backed buffers and shrinks the device page tables for those mappings. Its own
> author records that it is enabled automatically and that "this path skips some of the
> per-4K-page bookkeeping the stock driver performs, so it may misbehave in edge cases the
> stock driver handles correctly". It has no GA100 validation of any kind. To take only the P2P
> change, cherry-pick or format-patch **`9fb650447c7b` alone** instead of the whole range.

### Practical notes on the recipe

- As transcribed, the final line reads `sudo install.sh`. Master's installer is invoked as
  `sudo ./install.sh`; `install.sh` without a path only works if `.` is on `PATH`.
- The fork's own `install.sh` change (+7 lines) is swept into the diff but has no effect: the
  file it patches is a stock NVIDIA installer script that cmpunlocker's `build.sh` never runs.
- **Filename collision hazard.** Gen2 is now in `master` and already uses `0007-pcie-gen2.patch`
  and `0008-pcie-gen2-probe-retrain.patch`, so the P2P diff has to be numbered `0009` or later
  against any current checkout. This was a branch-merge hazard before 2026-07-29; it is now
  simply the numbering every layered patch has to respect.
- `build.sh` fetches the upstream tarball with `curl -L --fail` and performs **no checksum or
  signature verification**. Layering a second unverified diff on top compounds that.
- After install, `build.sh` compares `/sys/module/nvidia/srcversion` against
  `modinfo -F srcversion` on the patched `nvidia.ko`. A mismatch means stock modules won the
  load race and neither the unlock nor the P2P patch is active. See
  [verification](../procedures/verify.md).

---

## Measured results

There are almost none, and the gap is the single most important thing on this page.

| Quantity | Value | Conditions | Confidence |
|---|---|---|---|
| `p2pBandwidthLatencyTest` on any 170HX | **not run** | nobody posted a matrix, with or without the patch | n/a |
| P2P pairs reported capable, unpatched | 0 of 56 | 8 unlocked cards, PyTorch | high |
| P2P patch builds and loads on cmpunlocker | yes | one tester, 2026-07-23, screenshot; rig also contained 2x RTX 3090 | medium |
| Effect on 170HX-only pairs | reported **none** | one tester, no test output posted | low |
| Reference P2P-disabled bandwidth | 42.69-43.91 GB/s | 9-GPU Blackwell system, Gen5 x16, **not a 170HX** | high (for that system) |
| Reference P2P-enabled bandwidth | 55.59-56.58 GB/s | same system | high (for that system) |
| Reference device-to-self | 1611.24-1665.83 GB/s | same system | high (for that system) |

The Blackwell reference numbers do **not** transfer. A 170HX at Gen1 x4, or even Gen2 x4, moves
roughly one thirtieth to one sixtieth of those figures, and that system's driver branch lists only
3090/4090/5090 as supported.

> [!NOTE]
> **Open problem: does the patch do anything on a 170HX-only host?**
>
> Two reports exist from the same day. One records getting "p2p + cmpunlock working" with a
> screenshot, in a rig that also contained two RTX 3090s. Another records that after a
> successful build "it doesn't seem to take effect on the 170HX ... it only has an effect on
> them if there are other models of GPUs on the same machine". Those two may not actually
> conflict: the successful rig is precisely the mixed-model case the negative report says is
> the only one that works. Nobody posted `simpleP2P` or `p2pBandwidthLatencyTest` output either
> way. **What would settle it:** the connectivity matrix from a 170HX-only two-card host, with
> and without the layered patch. The test is cheap and the result is unambiguous.

---

## Unverified report: peer DMA works, peer synchronisation does not

> [!CAUTION]
> **Unverified community claim**
>
> Everything in this section is from a single builder on a single four-card rig, posted with
> logs but never independently reproduced. It contradicts the "effect unproven" position above.
> Treat it as a lead worth checking, not as a result.

The claim is that the layered `aikitoria` P2P patch does take effect on GA100, but only halfway:
peer *data movement* works and peer *synchronisation* does not.

| Test | Reported result |
|---|---|
| `torch.cuda.can_device_access_peer(i,j)` | `True` for all 12 ordered pairs on a 4-card host |
| `cudaMemcpyPeer` across cards | **6.25 GB/s**, against 5.70 GB/s for the same copy staged through host memory |
| Cross-process CUDA IPC handle sharing | works |
| Any NCCL collective | **hangs** at transport connect: no error, no timeout, both GPUs pinned at 100 % |
| vLLM custom all-reduce | **hangs** the same way |

The offered explanation is that the two halves have different requirements. A peer copy is a DMA
engine walking a mapping. A collective additionally needs one GPU to write a flag into another
GPU's memory and have a kernel on that second GPU spin until it observes the write. It is that
second pattern that reportedly does not work, which would explain why a raw copy succeeds while
every collective library hangs rather than failing.

The mechanism offered for it, also unverified:

- `kbusIsPcieBar1P2PMappingSupported_GH100` requires **static BAR1** on both GPUs, and static
  BAR1 requires BAR1 to span the whole framebuffer at a 512 MB-aligned offset. On the 170HX BAR1
  is **64 MB**, so the check cannot pass. See
  [BAR sizing](#bar-sizing-and-resizable-bar-limits), which is the same 64 MB constraint that
  blocks other things on this page.
- The mailbox fallback then fails its own alignment assertion, `(base & RM_PAGE_MASK) == 0` in
  `kern_bus.c`, followed by `remoteWMBoxLocalAddr != ~0ULL` in `kern_bus_gm200.c`.
- Separately, the reporter claims cmpunlocker's own `P2P` branch gates `p2pOverride` and
  `pcieP2PType` behind `devId == 0x20C2` read from `pGpu->idInfo.PCIDeviceID` inside
  `_kbifInitRegistryOverrides`, but that field is not populated until later in `gpu.c`, so the
  gate never opens. Upstream `aikitoria` commit `9fb650447c7b` sets both unconditionally.

If this holds up, the practical consequence is narrow but real: hand-written multi-GPU code that
moves buffers between cards and leaves coordination to the **host** could use peer DMA, while
every collective library, and therefore tensor parallelism in every mainstream inference server,
could not. The reporter's working configuration for multi-card vLLM is `NCCL_P2P_DISABLE=1` plus
`--disable-custom-all-reduce`, which is exactly the configuration that works with no P2P patch at
all. On that rig the patch therefore bought nothing for inference.

**What would settle it.** A second rig running three tests: `can_device_access_peer`, a timed
`cudaMemcpyPeer`, and any NCCL collective. The third is the decisive one, and it is a two-minute
test for anyone who already has two cards and the patch built.

---

## IOMMU interaction

BAR1 peer DMA writes a raw physical address at the other device. That only works if the IOMMU is
not translating those addresses.

The P2P branch's documented setup is:

```bash
# /etc/default/grub, GRUB_CMDLINE_LINUX_DEFAULT
amd_iommu=on iommu=pt        # AMD
intel_iommu=on iommu=pt      # Intel
sudo update-grub
# install the 610.43.03 driver, run ./install.sh, reboot
```

The README states the requirement flatly: IOMMU must be in **passthrough** mode, not translating,
or DMA goes through IOMMU page tables and transfers fail.

> [!CAUTION]
> **Passthrough mode weakens DMA isolation**
>
> The same README warns that this configuration "is very dangerous if you run untrusted
> software or devices". `iommu=pt` means devices DMA with host-physical addresses and the IOMMU
> is not policing them. Do not apply this to a multi-tenant host.

**ACS is the second half of the problem.** If P2P is enabled but slow, Access Control Services on
the root ports forces all GPU-to-GPU traffic up through the CPU root complex, which destroys the
bandwidth the patch exists to provide. Remedies given, in order of preference: disable ACS in
BIOS; boot with `pcie_acs_override=downstream,multifunction`; or apply an ACS override kernel
patch. Note that ACS override is also what breaks IOMMU group isolation, so this compounds the
warning above.

For A/B testing, 3090 pairs can be forced onto the PCIe BAR1 path instead of NVLink with:

```conf
# /etc/modprobe.d/nvidia.conf
options nvidia NVreg_RegistryDwords="RMForceP2PType=1"
```

### What cmpunlocker itself does about IOMMU

| Tree | IOMMU handling |
|---|---|
| `master` (shipping) | **none**. `install.sh` and `remove.sh` contain no `iommu` or kernel-cmdline handling at all |
| Gen2 code (now in `master`) | appends `intel_iommu=on iommu=pt` (GenuineIntel) or `amd_iommu=on iommu=pt` (AuthenticAMD) to `/etc/default/grub` or `/etc/kernel/cmdline`, with a `--no-iommu` opt-out |

The Gen2 installer also verifies at runtime with
`grep -qw iommu=pt /proc/cmdline && [[ -d /sys/class/iommu ]] && [[ -n "$(ls -A /sys/class/iommu)" ]]`,
printing `IOMMU is already active in passthrough mode on the running kernel` or
`IOMMU passthrough takes effect after the next reboot` plus a reminder that VT-d / AMD-Vi / SVM
must also be on in BIOS. `remove.sh` on that branch restores from `*.cmpunlocker.bak` and prints
`Reverted IOMMU kernel parameters (effective after reboot)`, or reports that no IOMMU config
backup was found and the kernel command line was left as-is. That is commit `6a85e6c`
"IOMMU enablement as part of install script", branch code, not shipping.

The practical consequence: **the Gen2 code already configures exactly what the P2P patch
requires**, which makes Gen2-plus-P2P the closest thing to a pre-configured stack anyone could
assemble today. Nobody has assembled it.

A verified passthrough boot from a test rig, for comparison:

```text
Linux 7.1.3-arch2-2, cmdline: intel_iommu=on iommu=pt nowatchdog nvme_load=YES
DMAR: IOMMU enabled
(four DRHD units)
iommu: Default domain type: Passthrough (set via kernel command line)
GPU at 0000:65:00.0, alone in IOMMU group 3
```

A separate `lspci -vvv` capture shows a card at `0000:81:00.0` in IOMMU group 31. A card alone in
its own group is what passthrough setups want, but it says nothing about ACS behaviour between
root ports, which is the part that governs P2P throughput.

The driverless [refire chain](../history/tool-lineage.md) has the same class of requirement for a
different reason: it needs `intel_iommu=off` **or** `iommu=pt` so that DMA physical addresses
equal host-physical addresses when it hands the Booter a hugepage address.

---

## BAR sizing and Resizable BAR limits

The 170HX exposes three BARs and a Resizable BAR capability that cannot actually resize anything.

| BAR | Size | Type | Observed region base | ReBAR supported sizes |
|---|---|---|---|---|
| BAR0 | 16 MB (`0x1000000`) | 32-bit, non-prefetchable | `f0000000` (`0xfa000000` on another host) | 16MB only |
| BAR1 | **64 MB** | 64-bit, prefetchable | `20048000000` | 64MB only |
| BAR3 | 32 MB | 64-bit, prefetchable | `2004c000000` | 32MB only |

`lspci -vvv` reports `Capabilities: [bb0 v1] Physical Resizable BAR` with exactly one supported
size per BAR, and `nvidia-smi` agrees: `BAR1 Memory Usage Total: 64 MiB`. A MIG instance created
on an unlocked card reports `0MiB / 64MiB` shared BAR1 alongside `1MiB / 65053MiB` of memory.

**BAR1 stays at 64 MiB even when the card advertises 81920 MiB of framebuffer.** Large-BAR or
full-VRAM host mapping is therefore not available on this card, which is exactly why the
[PRAMIN window](../unlock/memory-geometry.md) matters for the memory unlock.

Since the aikitoria patch works by mapping peer memory through **BAR1**, this 64 MiB non-resizable
aperture is the structural question hanging over the whole approach on GA100. No source in the
corpus establishes whether the driver's BAR1 P2P path can operate inside a 64 MiB window, or
whether it assumes a large BAR the way consumer 4090/5090 setups have. Nobody has tested it.

### The shipping BAR0/PRAMIN clamp

`0004-bar0-pramin-clamp.patch` is 20 lines and applies to **both** device IDs. When
`devId == 0x20C2 || devId == 0x2082` and `Ram.fbAddrSpaceSizeMb > 0x2000` (8192 MB):

```c
offsetBar0 = (0x2000ULL << 20) - DRF_SIZE(NV_PRAMIN);
```

A 10 GB card at 10240 MB already exceeds `0x2000`, so the clamp engages there too, and a 10 GB
card unlocked to 40 GB gets the 8192 MiB-based PRAMIN window rather than a 10240 MiB-based one.
This is a deliberate two-line-scale constant that anyone experimenting with BAR behaviour can
change and rebuild against.

### Resizable BAR: what is settled and what is not

> [!NOTE]
> **Open problem: Large BAR / ReBAR / Above 4G Decoding**
>
> The question was posted on 2026-07-22 at 14:11 and never answered. It matters because the
> shipping unlock deliberately clamps the BAR0/PRAMIN window and the card advertises a ReBAR
> capability that appears to offer no alternative sizes. **Next step:** boot with Above 4G
> Decoding enabled and read back the ReBAR capability sizes on a Gen2-trained card. If the
> capability structure genuinely lists a single supported size per BAR, no host-side workaround
> helps, including `github.com/xCuri0/ReBarUEFI` for hosts whose UEFI lacks ReBAR support.

### BAR pressure with many cards

A second-hand report describes BAR address-space problems above eight high-VRAM GPUs in a single
server, with no error string or platform captured. The important qualification: the unlock does
**not** grow any BAR, so BAR pressure comes from the per-device resizable-BAR aperture, not from
the 64 GB framebuffer. Lane arithmetic for a 128-lane single-socket platform gives roughly seven
cards at x16 (eight with no NVMe) or far more at x4 for the same aggregate bandwidth. Operators
are running 8-card and 10-card servers in production.

---

## Multi-GPU install state

P2P is inherently a multi-card topic, and cmpunlocker's multi-card support is branch-only.

| Capability | `master` | `multiple-cards` / `Gen2` |
|---|---|---|
| Card enumeration | `lspci -nn \| grep -iE '10de:20b0\|10de:20c2\|10de:2082' \| head -1` (first match only) | `mapfile -t PCI_LINES`, every match, five parallel arrays (BDF, devid, profile, expected_mib, current_mib) |
| Profile | `8gb` / `10gb` from `nvidia-smi memory.total` thresholds | `profile_from_devid()`: `20c2 → 8gb`, `2082 → 10gb`, plus a third `mixed` profile |
| Inventory file | none | `/lib/modules/$(uname -r)/updates/cmpunlocker/gpu_inventory`, one line per GPU, e.g. `0000:0b:00.0 20c2 8gb 65536` |
| `verify.sh` | does not exist | per-GPU `OK` / `STOCK` / `MISSING` / `UNEXPECTED`, thresholds `>= 60000 MiB` (8gb) and `35000-59999 MiB` (10gb) |

The installer limitation is cosmetic for the unlock itself: patch `0001` reads
`pGpu->idInfo.PCIDeviceID` on **every** GSP boot and picks geometry per device, so a multi-card
host is fully unlocked even though master's installer inspects only one card. One build serves a
host containing both 8 GB and 10 GB cards.

> [!CAUTION]
> **Mixed-GPU hosts mis-detect the profile**
>
> `detect_card_profile()` reads `nvidia-smi --query-gpu=memory.total ... | head -1`, which is
> the **first GPU in nvidia-smi order**, not the CMP that `lspci` found. A host with an
> RTX 3080 10 GB alongside an 8 GB 170HX detected "10GB" from the 3080 and selected the wrong
> profile. Reproduced by at least two testers; other CMP SKUs have been misdetected as 10 GB
> 170HX cards too. **Always pass `--profile=8gb` or `--profile=10gb` explicitly on a mixed
> host.** This bites P2P work specifically, because a mixed-model host is the one configuration
> where the P2P patch is reported to have any effect at all.

Two further multi-GPU constraints worth carrying here:

- **Proxmox passthrough requires SeaBIOS, not UEFI/OVMF.** UEFI produces RM init / adapter
  failures that look exactly like the exploit not working. Two people independently traced
  non-reproductions to this.
- **`verify.sh` never checks PCIe generation**, not even on the Gen2 branch lineage. Grepping
  `Gen2/verify.sh`, `far/verify.sh` and `deced/verify.sh` for "pcie" returns zero hits. Link
  state must be checked by hand with `nvidia-smi` or `pcielink.sh`.

See [multi-GPU procedures](../procedures/multi-gpu.md) for the full install path.

---

## Where P2P sits against the alternatives

| Path | Status | Blocker |
|---|---|---|
| NVLink | Fuse-disabled (`FUSE_NVLINK_DIS` `0x00820684` = `0x00000007`), never brought up | OTP fuse plus depopulated board components; see [NVLink](nvlink.md) |
| PCIe P2P, shipping unlock | Absent | No code anywhere in the tree |
| PCIe P2P, layered patch | Builds and loads. One **unverified** report of peer DMA at 6.25 GB/s with peer synchronisation still broken | Unsupported configuration; collectives reported to hang |
| Faster link (Gen2 x4) | Shipped in `master` since 2026-07-29 | Below the stated tensor-parallel threshold |
| Faster link (Gen2 x16) | Reproduced on two rigs, 5.97 to 6.67 GB/s | Requires the 24-capacitor solder mod; burn-in beyond 90 minutes unmeasured |
| Gen3 / Gen4 | Not achieved | Assessed as needing a GSP patch nobody has produced |

The stated threshold for tensor parallelism to become worth attempting at all is **PCIe Gen2 x16
or Gen3 x4**. The unlocker delivers Gen2 **x4**, which is below it. Restoring x16 is a
[physical modification](../operations/physical-mods.md) (24 x 0402 220 nF X7R capacitors), not a
software change, and it changes lane count only, never link generation. The two mechanisms are
independent and must not be conflated.

Until then, the working guidance is unchanged: pipeline parallelism, not tensor parallelism, and
MoE models to reduce cross-device activation traffic per token.

---

## Open problems

> [!NOTE]
> **Open problem: the P2P question set**
>
> 1. **Does the layered patch enable P2P between two 170HX cards?** Run `simpleP2P` and
>    `p2pBandwidthLatencyTest` on a 170HX-only pair, with and without the patch, and post the
>    matrix. Nothing else in this domain is as cheap or as decisive.
> 2. **Does a GA100 code path exist in the patch at all?** The modified files are Pascal-era bus
>    code plus the VA-space and RM API layers. Reading `kern_bus_gp100.c` against the GA100 HAL
>    would answer this without hardware.
> 3. **Can BAR1 P2P work through a 64 MiB non-resizable aperture?** Unestablished. This may be
>    the reason the negative report exists.
> 4. **Is P2P worth anything at Gen1 x4 or Gen2 x4?** The lead position on record is "I would
>    only implement P2P when we get at least PCIe Gen 3, otherwise it seems kind of a waste on
>    these cards". That precondition is currently unmet and there is no evidence either way that
>    it is reachable.
> 5. **Does a P2P-capability bit exist in silicon?** One suggestion on record is to check
>    whether the register space governed by the FEAT PLM at `0x00823804` carries a P2P
>    capability bit, since the unlock already reaches that block. Nobody looked.
> 6. **Do the tinygrad-lineage device tables even match a 170HX?** The upstream P2P driver
>    enumerates the A100s and CMP 40HX through CMP 90HX but omits the 170HX, and a fork updated
>    for 610.x still omits it. It is unknown whether an unlocked card would be accepted or
>    whether the `Graphics Device` identification string breaks device matching. Adding the two
>    device IDs to the table and testing is a trivial change.
> 7. **Should multi-card, IOMMU and Gen2 merge to master, and in what order?** The
>    `multiple-cards` installer changes (`b1cb6d8`) are self-contained and could land alone; the
>    Gen2 branch bundles them with unverified PCIe register writes.

---

## Related pages

- [PCIe subsystem](../hardware/pcie-subsystem.md) for link, BAR and config-space detail
- [PCIe Gen2 unlock](../unlock/pcie-gen2.md) and [Gen3/Gen4](pcie-gen3-gen4.md)
- [NVLink](nvlink.md) and [NVLink hardware](../hardware/nvlink-hardware.md)
- [Driver patches](../unlock/driver-patches.md) for the `0001`-`0006` series and the build system
- [Multi-GPU install](../procedures/multi-gpu.md) and [verification](../procedures/verify.md)
- [Physical modifications](../operations/physical-mods.md) for the x16 capacitor mod
- [LLM inference](../operations/llm-inference.md) for the parallelism measurements
- [Status board](status-board.md) and [open questions](open-questions.md)
- [Glossary](../start/glossary.md)
