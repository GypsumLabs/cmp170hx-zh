# The unlock at a glance

**What this page covers.** What the CMP 170HX unlock actually does, what it does not do, which
parts shipped and which live only on unreleased branches, the two per-SKU geometry profiles, and
where to go next for detail. This is the entry point to the whole unlock section. Every number
here is the canonical value; the deeper pages carry the evidence.

## The headline result

The shipping `cmpunlocker` patch set removes **two** factory restrictions on the CMP 170HX and
adds one convenience flag. It removes the SM speed-select throttle, restoring roughly 30x FP32 FMA
and full tensor throughput on GA100 silicon, and it rewrites the framebuffer geometry so an 8 GB
card enumerates **65536 MiB (64 GB)** and a 10 GB card enumerates **40960 MiB (40 GB)**. Both
happen automatically inside the GSP boot path on every driver load, in about one second, with no
soldering, no VBIOS flash, and no signature forgery.

The mechanism is a data-only attack on NVIDIA's own signed SEC2 Booter Load ucode: the driver
enlarges the GSP signature buffer from ~4 KB to `0x0000f800`, fills it with a crafted Falcon ROP
payload, and lets an unbounded DMA inside the Booter's signature-verification path overwrite the
Falcon's stack. That yields one arbitrary BAR0 write per Booter run at Heavy-Secure privilege,
which is spent opening four privilege level masks. After that, plain host register writes do the
actual unlocking. Nothing is decapped, no key is extracted, and the RSA boot ROM check is never
broken. See [How it works](how-it-works.md) for the full narrative.

!!! danger "This voids everything and can lose data"
    Patched kernel modules are unsigned, so Secure Boot must be off and the kernel is tainted.
    Overclocking an unlocked card can corrupt memory silently without crashing. The 80 GB
    configuration on a 10 GB card reports capacity it cannot reliably deliver. Read
    [Risks](../start/risks.md) and [Tuning](../operations/tuning.md) before running anything
    beyond the stock profiles.

## Status table

| Capability | Status | Where it lives | Mechanism |
|---|---|---|---|
| SM speed-select throttle removed | **Shipped, stable** | `master`, patch 0001 | `SS0 0x0082381c = 0x88888888`, `SS1 0x00823820 = 0x00000008` after opening `FEAT_OVR_PLM 0x00823804` |
| Memory geometry 8 GB to 64 GB | **Shipped, stable, in production** | `master`, patch 0001 | `CFG1 0x009a0204 = 0x02779000`, `LMR 0x00100ce0 = 0x0000020B` |
| Memory geometry 10 GB to 40 GB | **Shipped, stable** | `master`, patch 0001 | `CFG1 = 0x02669000`, `LMR = 0x0000028A` |
| Capacity advertised to CUDA | **Shipped** | `master`, patches 0001 + 0003 | GSP static-info `fb_length` rewrite plus a late PMA region extension |
| Built-in persistence mode | **Shipped** | `master`, patch 0006 | `NV_FLAG_PERSISTENT_SW_STATE` set at PCI probe; no daemon needed |
| PCIe Gen1 to Gen2 (5 GT/s) | **Experimental, branch only** | `debug-gen2`, `Gen2`, `far`, `deced`; patches 0007 / 0008 | 25 Booter-routed register writes plus plain BAR0 writes, then an upstream-bridge retrain |
| PCIe width beyond x4 | **Hardware only** | Not software at all | 24 hand-soldered 0402 AC-coupling capacitors |
| MIG (Multi-Instance GPU) | **Community finding, not merged** | Nowhere in the tree | Bit 0 of `0x820840`; one researcher, three corroborating `nvidia-smi` outputs |
| 10 GB card to 80 GB | **Attempted and abandoned** | `80` branch | Unstable above roughly 40 GB of real use |
| PCIe Gen3 / Gen4 | **Not achieved** | Nowhere | `FUSE_PCIE_GEN23_DIS` and `FUSE_PCIE_GEN3_DIS` both read `0x00000001` |
| ECC | **Not achieved** | Nowhere | Fused off, no lever found; the branch named `ecc` contains no ECC code |
| NVLink | **Not achieved** | Nowhere | Fuse-disabled (`FUSE_NVLINK_DIS`); no FEAT_OVR entry exists |
| More than 70 SMs | **Not achieved** | Nowhere | Every GPC-disable write path is latched, including HS-privileged writes |
| Peer-to-peer (P2P) | **Absent** | Nowhere | Not present on this card |
| Higher clocks | **Not part of the unlock** | NVML, out of tree | GPC clock VF offset via `nvmlDeviceSetGpcClkVfOffset`; see [Tuning](../operations/tuning.md) |

Two things the unlock deliberately does not touch: **clock speeds** and **PCIe bus speed**. The
canonical in-channel formulation was "compute limit yes, bus speed no", and it matches the shipping
mechanism, which writes nothing in the clock tables or the PCIe config block.

!!! note "Superseded"
    `SM_ISSUE_RATE_MODIFIER` at `0x00504204`, the `RMOverrideSmSpeedSelect` registry key, GSP
    firmware patching and VBIOS flashing were all pursued at length and all failed. The shipping
    tree contains zero references to `0x00504204`. See [Dead ends](../history/dead-ends.md).

## The two SKU profiles

Geometry is selected at **runtime by PCI device ID**, not at build time. Both profiles are compiled
into the same module, and `driver/build.sh` on `master` performs no source rewrite at all.

| Quantity | 8 GB card | 10 GB card |
|---|---|---|
| PCI ID | `10de:20c2` (`0x20C2`) | `10de:2082` (`0x2082`) |
| Stock capacity | 8192 MiB | 10240 MiB |
| Unlocked capacity | **65536 MiB (64 GB)** | **40960 MiB (40 GB)** |
| Stock `CFG1 0x009a0204` | `0x02449000` | `0x02449000` |
| Unlocked `CFG1` | `0x02779000` | `0x02669000` |
| Stock `LMR 0x00100ce0` | `0x00000208` | `0x00000288` |
| Unlocked `LMR` | `0x0000020B` | `0x0000028A` |
| `targetFbBytes` / `fb_length` | `0x0000001000000000` (64 GiB) | `0x0000000A00000000` (40 GiB) |
| Active FBPAs / FBPs | 16 FBPAs, 8 FBPs | 20 FBPAs, 10 FBPs |
| Memory bus | 4096-bit | 5120-bit |
| `SS0` / `SS1` | `0x88888888` / `0x00000008` | identical |
| SM count | 70 (CC 8.0, 4480 CUDA cores) | 70 (identical) |
| GPC clock offset headroom | VBIOS `0x47177` / `0x47179` hold `freqDelta = ±1000` | both read 0 |

!!! warning "Never mix the profiles up"
    8 GB goes to 64 GB. 10 GB goes to 40 GB. Applying the 8 GB geometry to a 10 GB card is a
    documented failure mode, and the 80 GB configuration for 10 GB cards was tried and found
    unstable. See [Memory geometry](memory-geometry.md).

A **third** device ID, `10de:20b0`, is matched by `install.sh`'s `lspci` scan but is **not**
unlocked: the in-driver gate `_kgspSec2PostblTimingEnabled()` accepts only `0x20C2` and `0x2082`.
Such a card installs cleanly, boots the stock path, and never fires. Any README wording implying
the unlock is `0x20C2`-gated alone is stale.

## What shipped versus what is experimental

**Shipping `master`** is six numbered patches applied to an unmodified
`open-gpu-kernel-modules` tarball, totalling 37,415 bytes:

| Patch | Size | What it does |
|---|---|---|
| `0001-sec2-postbl-plm-ss-cfg.patch` | 19,741 B | The whole unlock: signature enlargement, payload, PLM loop, register writes, signature rebuild, static-info rewrite |
| `0002-booter-verify.patch` | 3,988 B | Downgrades four fatal assertions and adds the `POST-BooterLoad verify` readback |
| `0003-late-pma.patch` | 10,580 B | Registers the framebuffer above 8 GiB with PMA so it is allocatable |
| `0004-bar0-pramin-clamp.patch` | 861 B | Keeps the PRAMIN window inside reachable BAR0 space |
| `0005-ce-scrub-workarounds.patch` | 1,642 B | Forces the copy-engine scrubber into physical mode |
| `0006-persistent-sw-state.patch` | 603 B | Sets the persistent-software-state flag |

Supported driver versions on `master` are exactly **`610.43.03` (default) and `610.43.02`**, matched
as exact strings; the build hard-fails on anything else. Linux only, nvidia-open only, Secure Boot
off. See [Driver versions](../procedures/driver-versions.md) and [Install](../procedures/install.md).

**Twelve unreleased branch snapshots** exist (thirteen trees counting `master`): `80`, `Gen2`,
`PG199`, `clanker_driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`, `far`, `housekeeping`,
`memory`, `multiple-cards`.

!!! warning "Experimental"
    **PCIe Gen2** ships only on the `Gen2` family. Patch `0007-pcie-gen2.patch` exists on
    `debug-gen2`, `Gen2`, `far` and `deced`; `0008-pcie-gen2-probe-retrain.patch` on `Gen2`, `far`
    and `deced`. The Gen2-family PLM table grows from four entries to nine. Gen2 is not
    deterministic, does not work under VM passthrough, and two of the four branches (`Gen2`
    and `debug-gen2`) set `RMPcieLinkSpeed` to the Gen1 enum `0x1`, while `far` and `deced`
    set `0x2`; no A/B boot test has ever settled which value is right. See [PCIe Gen2](pcie-gen2.md).

!!! warning "Experimental"
    The **`clanker_driver-port`** branch adds `580/`, `590/`, `595/` and `610/` patch directories.
    Every register value and payload offset is character-for-character identical to `master`, and
    the `610` directory is a byte-for-byte copy of it. The 595 / 590 / 580 ports are
    **source-verified only**: the patches apply cleanly and nobody has reported a boot.

!!! note "Superseded"
    The `80` branch changes exactly one patch file (two lines) plus `build.sh`, `install.sh` and
    `constants.yaml`. Its `constants.yaml` declares `lmr: "0x0000028B"` and `unlocked_mib: 81920`,
    but that file is never read by the build. What an 80-branch build actually programs is
    `CFG1 0x02779000` + `LMR 0x0000028A` + `fb_length 0x0000001400000000`, a three-way
    disagreement that is the best explanation for the branch's fold at exactly 40 GiB. Firing the
    coherent `LMR 0x0000028B` from a clean-room script does remove the fold, but not the crashes.
    See [The 80 GB question](../frontier/80gb.md).

!!! warning "The `memory` branch is single-device and hard-codes the 8 GB profile"
    `memory` predates dual-geometry support. Its patch `0001` hard-codes
    `SEC2_POSTBL_TIMING_CMP_170HX_PCI_DEVICE_ID 0x20C2`, `cfg1Value = 0x02779000U` and
    `lmrValue = 0x0000020BU` with no device-ID branch and no 10 GB path: a `0x2082` card is not
    unlocked at all on that branch. Do not build from it expecting runtime profile selection.

The `ecc` branch contains no ECC implementation whatsoever: all six driver patches are byte-identical
to `master`. The `docs` branch's `ARCHITECTURE.md` is a documentation defect and should not be
cited: it calls SS0/SS1 "Suspension State" registers, claims both are written to `0xffffffff`,
expands PLM as "Program Logic Modules", and prints log lines that exist nowhere in the code.

## What the unlock buys, measured

Rows dated 2026-07-06 come from a single rendered image posted with the first private
"compute unlock working" report, not from named tool output. See
[compute-throttle.md](compute-throttle.md) for the provenance caveat.

| Metric | Locked | Unlocked | Notes |
|---|---|---|---|
| FP32 IEEE (2026-07-06, one card) | 0.41 TF/s | 12.69 TF/s | 31.0x; theoretical ceiling 12.63 TFLOPS (4480 x 2 x 1410 MHz) |
| FP64 non-tensor | 0.20 TF/s | 6.2-6.31 TF/s | 1/2 of FP32, the full GA100 rate |
| FP64 tensor (DMMA) | n/a | 11.5-12.9 TF/s | Roughly 2x the non-tensor rate. The two FP64 figures are not in conflict: one clpeak run printed `double : 6308.65` GFLOPS and `wmma_fp64 : 11.96` TFLOPS side by side |
| BF16 tensor (2026-07-27, 8 rented cards) | 6.40 TF/s | 164.4-192.7 TF/s | across eight rented cards plus a tuned reference |
| FP16 tensor (2026-07-27, 8 rented cards) | 6.52 TF/s | 158.7-190 TF/s | |
| INT8 (2026-07-06, one card) | 1.63 TOP/s | 50.50 TOP/s | 30.9x. A later 8-rented-card campaign (2026-07-27) measured 44.1 TOPS on the library path with no matching locked baseline; the INT8 *tensor* path measures 335 TOPS |
| FP16 scalar (non-tensor) | ~42-50 TFLOPS | unchanged | never throttled, which is why locked cards were already usable for token generation |
| INT32 | ~12.5 TIOPS | unchanged | never throttled |
| HBM bandwidth | 1305.86-1600 GB/s | unchanged | a range across tools and access patterns, not one figure |
| Sustained SM clock | 1410 MHz | unchanged | 1470 MHz at `-pl 300`; `clocks.max.sm = 1935 MHz` is a reported field only, low confidence |

The success signal is `FEAT_READOUT_1` at `0x00823818` reading `0x00000000`. A stock 170HX reads
`0x016db6ed`. That single register is the cleanest available "is this card unlocked" test.

!!! question "Open problem"
    INT8 / IMMA remains gated after the unlock even though the IMLA override nibbles are set
    identically to the FMLA and FFMA ones. On an A100, INT8 runs roughly 2x faster than FP16; on an
    unlocked 170HX it runs 3.7x slower. Practical consequence for inference: use W4A16 (AWQ, GPTQ)
    and avoid W8A8 entirely. See [LLM inference](../operations/llm-inference.md).

## Why it works at all

Three facts underpin everything:

1. **The master kill fuse is unblown.** `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` at `0x008203f0` reads
   `0x00000000` on the CMP 170HX. Had it been blown, all feature overrides would be permanently
   locked and no software path would exist.
2. **GA100 loads Turing-generation firmware.** The GSP image is `gsp_tu10x.bin` and the SEC2 booter
   is Turing-lineage `booter_load`, which carries the unbounded-DMA bug. The GA100 `booter_load`
   binary is bit-identical across driver branches 580 through 610.
3. **The debug and production booter images contain the same cleartext code.** Only the AES key
   differs, and the debug key is a non-secret numbered test key, so the production HS code could be
   read without any leaked source.

The exploit is a data-only attack on a vendor-signed blob whose validating keys are fused into
immutable silicon, so the vulnerable booter cannot be revoked by a driver update. That is an
inference about the trust model, not a demonstrated result.

## Map of the deeper pages

| Page | Covers |
|---|---|
| [How it works](how-it-works.md) | The complete end-to-end mechanism in boot order, and why each step is necessary |
| [Falcon and Booter](falcon-and-booter.md) | SEC2 hardware interface, booter extraction and decryption, internal structure, the vulnerability |
| [The ROP chain](rop-chain.md) | Payload layout, gadgets, stack canary defeat, terminators, the write budget |
| [Privilege level masks](privilege-level-masks.md) | What a PLM is, the four-entry shipping table, the nine-entry Gen2 table, FLR survival |
| [Memory geometry](memory-geometry.md) | CFG1 and LMR encodings, per-FBPA propagation, why LMR is mandatory, the 80 GB wall |
| [Compute throttle](compute-throttle.md) | SS0/SS1 semantics, the speed-select fuses, the gate chain, measured throughput |
| [Driver patches](driver-patches.md) | All six patches hunk by hunk, `install.sh`, `build.sh`, `remove.sh`, the version ports |
| [PCIe Gen2](pcie-gen2.md) | Patches 0007 and 0008, the `xp3gTable`, retrain, the branch history |
| [Register reference](register-reference.md) | Every address, every measured value, per SKU and per comparison part |

Adjacent material: [PCIe subsystem](../hardware/pcie-subsystem.md) for the width cap and the
capacitor mod, [Physical mods](../operations/physical-mods.md) for the soldering itself,
[Verify](../procedures/verify.md) for confirming a successful unlock,
[Troubleshooting](../procedures/troubleshooting.md) when it does not fire, and the
[Status board](../frontier/status-board.md) for what is still open.
