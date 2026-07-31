# External sources

**What this page covers.** An annotated bibliography of every external reference this wiki leans
on: the `cmpunlocker` repository and its unreleased branches, the upstream NVIDIA open kernel
modules, the 170th Street community wiki, the independent teardown review, the TechPowerUp VBIOS
and specification database, the academic papers, envytools and the Falcon tooling family, and the
community forks, gists and issue threads. Each entry says what the source is and **how far to trust
it**, because several widely-cited sources here are wrong in specific, identifiable ways.

Commercial listings, marketplaces, vendor product pages and anything procurement-related are out of
scope and deliberately absent.

## How to read the trust column

| Rating | Meaning |
|---|---|
| **Primary** | You can re-derive the claim yourself from the artifact. Source code, a signed measurement, or a file you can hash. |
| **Reliable** | Independent, first-hand, and corroborated at least once. Cite freely, but say what it is. |
| **Use with care** | Genuinely useful, with known specific defects. Never cite without checking the defect list below. |
| **Do not cite** | Known to contain confidently wrong technical content. Useful only as a historical record. |

---

## 1. The unlock implementation

### `github.com/amoghmunikote/cmpunlocker` (branch `master`)

**Trust: Primary.** This is the shipping tool and the authority for anything expressible in code.
Tagline: "A tool to unlobotomize your NVIDIA card!". Made public on 2026-07-14; first commit
`9b9fb2f Initial commit`; the archived `master` tip is `cc872cb Moved PR template location`
(2026-07-23).

`master` contains exactly eight top-level items: `.github/pull_request_template.md`, `.gitignore`,
`LICENSE`, `README.md`, `common/constants.yaml`, `driver/`, `install.sh`, `remove.sh`. There is
**no** `verify.sh`, **no** `tools/` directory, **no** `probe.sh`, **no** `requirements.txt` (deleted
2026-07-19) and no test suite. The uninstaller is `remove.sh --yes`; **`uninstall.sh` does not
exist** anywhere in the tree.

`common/constants.yaml` is the machine-readable ground truth and matches patch `0001` exactly. Note
one important behaviour that reading the README will not tell you: on current `master`, `--profile`
no longer selects geometry. Patch `0001` branches on `pGpu->idInfo.PCIDeviceID >> 16` at GSP boot,
`build.sh`'s inline rewrite finds all six markers and exits without editing, and `--profile` affects
only the banner, `EXPECTED_MIB` and the metadata files. Pre-2026-07-18 instructions are stale on
this point. See [driver patches](../unlock/driver-patches.md) and
[install](../procedures/install.md).

> [!WARNING]
> **The README is loose on the device gate**
>
> It says the unlock is `0x20C2`-gated, when the in-driver gate `_kgspSec2PostblTimingEnabled()`
> accepts `0x20C2` **and** `0x2082`. Master ships no `DEBUGGING.md` at all: the "all PLMs must
> show `0xffffffff`" line lives on the `docs` branch, and it is wrong because the shipping table
> opens WPR_CFG `0x001fa7cc` to `0xfffff0ff`.

### The twelve unreleased branches

**Trust: Primary as code, Experimental as advice.** Real code, unmerged, and in several cases
internally inconsistent. There are exactly **12** unreleased branch snapshots (13 trees counting
`master`): `80`, `Gen2`, `PG199`, `clanker/driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`,
`far`, `housekeeping`, `memory`, `multiple-cards`. Any source claiming thirteen or fourteen
*snapshots* is counting wrong. Note that the repository carried **17 branch refs** at fetch time,
so four unreleased refs were never snapshotted and are not analysed anywhere on this site:
`code-simplification`, `dual-geometry-fix`, `fix` and `v0.1`.

| Branch | Tip | What it is | Trust note |
|---|---|---|---|
| `multiple-cards` | `b1cb6d8`, 2026-07-18 | Per-device-ID profiles, a `mixed` profile, `gpu_inventory`, and the branch-only `verify.sh` | Self-contained and the most likely to merge. Its `verify.sh` lspci fallback silently drops `10de:20b0`. |
| `debug-gen2` -> `Gen2` -> `far` -> `deced` | `746d9f7` -> `a4de322` -> `8854d3e` -> `2326599` | The PCIe Gen2 lineage. `0007-pcie-gen2.patch` on all four; `0008-pcie-gen2-probe-retrain.patch` from `Gen2` on. `deced` (2026-07-27) is the most current. | See the danger note below. |
| `clanker/driver-port` | `153cd6d`, 2026-07-21 | Per-branch patch directories `{580,590,595,610}/`. Lists **twelve** versions in `driver/VERSION` but **five** in `constants.yaml`: an acknowledged internal inconsistency. Its `install.sh` is byte-identical to master's. | The `610` directory is a byte-for-byte copy of master. **No boot has ever been reported on 595, 590 or 580.** |
| `80` | `3c53aca`, 2026-07-19 | The 80 GB attempt for 10 GB cards | See the danger note below. |
| `ecc` | `bb4d669`, 2026-07-18 | Single commit, "Fixed dual geometry support" | **Contains no ECC code.** The name misleads. |
| `housekeeping`, `memory` | 2026-07-18 | Intermediate development states | `housekeeping`'s patches would not have applied: the `@@` hunk counts were not updated when the `0x2082` arms were added. |
| `PG199` | | Drive A100 snapshot | Reference only. |
| `docs` | `651b6d5`, 2026-07-27 | Prose documentation | **Do not cite.** See below. |

> [!CAUTION]
> **Two branch defects that will cost you**
>
> **`Gen2` installs a Gen1 clamp.** `debug-gen2` and `Gen2` write
> `NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"` into
> `/etc/modprobe.d/cmp-pcie-gen2.conf`, pinning the link to Gen1 while trying to enable Gen2.
> `far` commit `8854d3e "Remove clamp link to Gen1"` changed it to `0x2`. Which value is correct
> is genuinely unresolved: both ship, and no A/B boot test exists.
>
> **The `80` branch does not program what its metadata says.** `80/common/constants.yaml` carries
> `lmr: "0x0000028B"` and `81920`, but `build.sh` never reads that file. `80/driver/build.sh`
> line 93 sets `LMR="0x0000028A"`, `install.sh` line 138 prints `CFG1=0x02779000 LMR=0x0000028A`,
> and patch `0001` line 144 bakes `lmrValue = 0x0000028AU`. Commit `3c53aca "Correct LMR for 80GB"`
> changed only inert metadata. Every tester who ran that branch programmed CFG1 `0x02779000`,
> LMR `0x0000028A` and `fb_length 0x0000001400000000`, a three-way disagreement that is the best
> explanation for the branch's fold at exactly 40 GiB. No build of the branch has ever carried
> the coherent value, though a clean-room script has fired it.
> See [the 80 GB question](../frontier/80gb.md).

### `github.com/amoghmunikote/cmpunlocker` branch `docs`

**Trust: Do not cite.** Seven commits. It is the project's own documentation branch and it is a
documented source of errors: `docs/ARCHITECTURE.md` claims `SS0 = 0xffffffff` and
`SS1 = 0xffffffff` when the shipping patch writes `0x88888888` and `0x00000008`; `DEBUGGING.md`
says all PLMs must read `0xffffffff`; both `docs/INSTALLATION.md` and the branch README instruct
`sudo ./uninstall.sh --yes`, a file that does not exist; and it invents acronym expansions found
nowhere in code or chat (SS as "Suspension State", PLM as "Program Logic Modules", PMM as "Permute
Mask Model", LMR as "LM (Local Memory) Request register", PMA as "Power Management Array"). It also
asserts a `SEC2_DEBUG: Executing unlock sequence...` log line that the driver never emits.

### `github.com/NVIDIA/open-gpu-kernel-modules`

**Trust: Primary.** The upstream driver source that `build.sh` fetches at install time
(`archive/refs/tags/${VERSION}.tar.gz`), and the source of the signed booter blob. Three files
matter repeatedly: `src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`
(holding `IMAGE_{DBG,PROD}`, `HEADER_{DBG,PROD}`, `SIG_{DBG,PROD}` and `PATCH_LOC = 0x8900`),
`kernel_gsp_booter_tu102.c`, and `nouveau/extract-firmware-nouveau.txt`. Supported versions on
shipping `master` are exactly `610.43.03` (default) and `610.43.02`; the build hard-fails on
anything else. See [driver versions](../procedures/driver-versions.md).

> [!NOTE]
> **No integrity check on the download**
>
> `build.sh` fetches the tarball with `curl -L --fail` and caches it, with no checksum or
> signature verification anywhere in the tree. Recording an expected SHA-256 per version would be
> a one-line improvement and has not been done.

---

## 2. Community documentation

### 170th Street (`170th-street.gitbook.io/hx`)

**Trust: Use with care.** The largest community wiki for this card and the project's own nominated
documentation site as of 2026-07-27. Its structure covers hardware (full specifications, teardown
guide, a leaked NVIDIA A100 schematic page), modifications (PCIe capacitor mod, watercooling),
unlock, AI and ML workloads, benchmarks, and an NVLink population research page. It runs an
issue-based contribution process, and its issue tracker thread #1 holds a substantial early-research
discussion.

The capacitor-mod page is the reference community writeup for that procedure and is corroborated by
independent measurement, so it is safe. The problems are elsewhere:

- **It contradicts itself on SM count.** `hardware/full-specifications.md` gives one Compute table
  with 70 SMs, 4,480 CUDA cores and 280 tensor cores, while its own "Notes on Specification
  Discrepancies" section says "8 GB variant: 56 SMs, 4,096-bit memory bus" and "10 GB variant:
  70 SMs, 5,120-bit memory bus", and `introduction/what-is-the-cmp-170hx.md` repeats the split.
  The measured value on a live 8 GB card, taken by PTX special-register dump, is **70 SMs**.
- **Its PCIe page is outdated.** `hardware/full-specifications.md` still states "PCIe Gen 1 x4
  (firmware locked), ~1 GB/s", and its own timeline page still describes the capacitor mod as
  unconfirmed. Both have been overtaken.
- **Its FP16 comparison mixes scalar and tensor rates**, comparing the 170HX's scalar performance
  against other cards' tensor-core performance, which was pointed out in-channel.
- The `cmpunlocker` maintainer explicitly declared it outdated and untrustworthy when asked whether
  the LnkCap and LnkCap2 values were proven to be fuse-derived.

Treat it as a well-organised secondary summary. Re-verify any register, fuse or specification claim
against [the register reference](../unlock/register-reference.md) or a measurement.

### The independent teardown review (`niconiconi.neocities.org/tech-notes/nvidia-cmp-170hx-review/`)

**Trust: Reliable, and the best physical-observation source in the bibliography.** Published
2023-10-25, two and a half years before the unlock work, so it is entirely uncontaminated by it.
Its key finding, quoted often and never contradicted: the CMP 170HX uses a circuit board nearly if
not completely identical to the A100 40 GiB, the only difference being the ASIC model number
`GA100-105F-A1`, and the board has many unpopulated components including omitted VRM phases
(depopulated DrMOS transistors and their output inductors) and **missing NVLink-related ICs**.

That last point matters more than any register value: the missing NVLink interface ICs are a
*physical* obstacle to an NVLink unlock, independent of anything in firmware. See
[NVLink](../frontier/nvlink.md). The review is also the source of the same author's FMA-disabling
work, which is where the whole software-side story of this card starts.

The review's accompanying teardown photographs are hosted at the same domain and are the
highest-quality PCB images in the corpus.

---

## 3. Specification and VBIOS databases

### TechPowerUp VBIOS collection

**Trust: Primary for the ROM files, Do not trust the metadata columns.** The `.rom` images are real
and hashable; TechPowerUp's own "Memory Size" column for these entries could not be traced to any
field inside the files and is unreliable.

Four CMP 170HX images exist in the collection:

| Entry | Version | Build | Device / subsystem | Labelled | Actually |
|---|---|---|---|---|---|
| 257744 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | 8 GB | The stock production 8 GB image, 364 MHz memory field, 250 W |
| 239457 | `92.00.67.00.01` | 2021-05-14 | `10DE 20C2` / `10DE 1585` | "16 GB" | **Bit-for-bit identical to the 8 GB image** apart from the `flash_status_ledger`, which changes on every flash including at the factory. The 16 GB label is wrong. |
| 268495 | `92.00.6D.00.0A` | 2022-04-07 | `10DE 20C2` / `10DE 1585` | "0 GB" | The **300 W** ROM: 432 MHz memory field, board power target 250.0 W, limit 300.0 W, adjustment range -60% / +20%, MD5 `a58aae86e72b13d50603c15653350664`. The 0 GB label is wrong. |
| 268984 | `92.00.66.00.02` | 2021-04-23 | `10DE 2082` / `10DE 1557` | 10 GB | The 10 GB image |

> [!CAUTION]
> **Neither the '16 GB' nor the '0 GB' image unlocks memory**
>
> They differ only in power and clock fields. Flashing 239457 onto a 10 GB card produced a yellow
> bang and no driver acceptance because the device ID does not match. Flashing the 8 GB VBIOS onto
> a 10 GB card leaves the card unable to boot. A third revision, `92.00.6D.00.09` dated
> 2021-11-01, exists in the field but is not in the TechPowerUp collection: it already carries the
> 300 W limit but has no memory overclock. **VBIOS version makes no difference to whether the
> unlock works**, confirmed across four cards on two hosts running both `92.00.67` and
> `92.00.6D.00.0A`. See [VBIOS](../hardware/vbios.md).

Useful comparison entries from the same collection: A100 PCIe 40 GB (277449), A100 (283106), A30
(262595, whose `92.00.66.00.0x` is almost identical to the 10 GB 170HX image), and Tesla V100 16 GB
(199146).

### TechPowerUp GPU specification database

**Trust: Use with care.** The correct entry for this card is `gpu-specs/cmp-170hx-8-gb.c3830`.

> [!CAUTION]
> **The `c3824` URL is a trap**
>
> `gpu-specs/cmp-170hx.c3824` returns HTTP 200 and redirects to
> `/gpu-specs/radeon-pro-w6800x-duo.c3824`, an AMD product page. It has circulated widely,
> including inside an agent brief. Adjacent IDs for orientation: `c3821` is the A100 PCIe 80 GB,
> `c3822` the CMP 70HX, `c3823` PG506-242.

TechPowerUp is reliable for die size (826 mm²), shading units (4,480 = 70 x 64), TMUs/ROPs/tensor
cores (280/128/280) and L1 (192 KB per SM). It is **wrong twice** in ways that matter: it lists
**8 MB of L2** where deviceQuery and an independent latency-spike microbenchmark both measure
**32 MB**, and it describes the power connector as "2x 8-pin" where the board has **one EPS 8-pin**
carrying two logical 12 V rails. Its PG199 6144-bit bus listing was also called wrong by a
first-hand owner. Its bandwidth figures for CMP parts were flagged in-channel as occasionally wrong.

---

## 4. Academic and formal publications

### "A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"

**Trust: Primary, and the single designated clean input for the whole clean-room effort.** June
2026, 16 pages, Zenodo record **20916112**, mirrored as ResearchGate publication **408132536**.
Circulated in the unlocker server on 2026-06-26 and posted into the clean-room server on
2026-07-16T06:07:12Z.

Its abstract states that the CMP 170HX is "the same die as a flagship A100 but is fuse-crippled on
three commercial axes: SM math rate (throttled to 1/32), memory capacity (10 GB instead of 80 GB),
and PCIe link (Gen1 instead of Gen4)", that "all three caps are soft", and reports headline gains of
roughly 31 to 62x compute, 8x capacity and 2x link.

Why it is load-bearing: the clean-room rules designated it the one admissible input document, on the
grounds that it was published on a scientific-publication site and had been sent to the vendor. Its
section 5.5 emulator trace publishes `buffer = 0x800`, `SIGSZ = 0xf800`, uniform fill `V = 0x4a7`,
`guard@0x6340` and the guard stub value `0xc0deca7e`, which is where a large fraction of the
shipping payload's constants come from. Its section 8.5, "Persistence across FLR", is the argument
that override values in an always-on island turn a one-shot exploit into a durable state.

Two cautions. Its "3-4 BAR0 value changes" framing misled every independent implementer: the
difficulty is entirely in opening the four PLMs first, and the BAR0 writes afterwards are trivial.
And its Falcon emulator **was never released**, which closes the most direct route to reproducing
its analysis. A second-hand report that the paper describes stabilising a card at roughly a 35%
throughput penalty is recorded here at low confidence and is not verified.

The paper's authors declined a pre-publication embargo, arguing in section 10 that coordinated
disclosure assumes the vendor's remedy protects the user, which does not hold when the defender is
the device and the adversary is its owner.

### arXiv:2505.03782

**Trust: Reliable, and frequently confused with the above.** "Exploration of Cryptocurrency
Mining-Specific GPUs in AI Applications: A Case Study of CMP 170HX", submitted 30 April 2025,
categories cs.AR and cs.DC. It reports FP32 exceeding **15x** the original capability and LLM
inference at certain precisions surpassing **3x**, achieved by disabling FMA contraction in CUDA
source, on stock firmware, measured with an OpenCL benchmark, mixbench and a LLAMA benchmark. It is
reference [13] of the Canary paper. **It is not the exploit paper**, and for a period the community
conflated the two.

Other Zenodo records that accumulated around this card: 18994970, 19002983, and 18995979 (a 170HX
Tensor Core analysis, reportedly rejected by arXiv over classification, risk and terminology).

---

## 5. Falcon reverse-engineering tooling

### envytools / envydis (`envytools.readthedocs.io`, `github.com/envytools/envytools`)

**Trust: Reliable for what it covers, silent on what it does not.** `envydis` with the **`fuc5`**
target successfully disassembles the GA100 booter, and the resulting listing was independently
reviewed and executed correctly on silicon. This works even though the envytools table nominally
assigns `fuc6` to GP102-and-later parts (`fuc0 [G98, MCP77, MCP79]`, `fuc3 [GT215+]`,
`fuc4 [GF119+]`, `fuc5 [GK208+]`, `fuc6 [GP102+, selected engines only]`). Whether the 170HX SEC2 is
formally fuc5 or fuc6 remains open; the practical answer recorded in-channel was "I picked whatever
worked".

> [!NOTE]
> **Open problem**
>
> envytools has not been updated in roughly eight years, and it **cannot corroborate the secure
> boot material at all**: its Falcon crypto page has section headings with no content, it
> documents Falcon hardware versions only up to v5, and it has no entry for several registers this
> work depends on. `envyhooks` on `gitlab.freedesktop.org/nouveau/envyhooks` was suggested as a
> successor and was found to lack equivalent functionality. Settling fuc5 versus fuc6 needs a diff
> of both decodes of the same image, looking for instructions only one target resolves coherently.

Also in this family:

- **`github.com/vbe0201/faucon`**: a Falcon emulator, explicitly fuc5-only. Its
  `faucon-emu/src/cpu/instructions/data.rs` was used as an instruction-semantics reference.
- **`github.com/CAmadeus/falcon-tools`** (the `requiem` subtree): Falcon secure-boot tooling,
  keygen, payloads and reverse-engineering material. Requires Python 3.6+, PyCryptodome, envytools,
  make and m4, and targets no NVIDIA GPU at the relevant generation directly.
- **`github.com/karolherbst/nouveau_tools`** (`dbg_falcon.sh`): a Falcon debug helper.
- **`hexkyz.blogspot.com`** ("Je ne sais quoi: Falcons over the Horizon", November 2021) and the
  **switchbrew TSEC page**: the standard external references for Falcon secure-mode behaviour,
  including `$sr10` semantics and the bit that suppresses interrupts and exceptions before halting.
- **`github.com/ttabi/extract-firmware-nova`** and **`github.com/NVIDIA/nova`**
  (`drivers/gpu/nova-core/devinit.rs`, `vbios.rs`): the Rust rewrite of the NVIDIA kernel driver,
  useful because it names registers in plain source where the C driver hides them behind macros.

---

## 6. Community gists and reference tables

**Trust: Primary as measurement records.** Both of the important gists were deleted after release
and re-forked by others, so cite the content, not a specific fork.

| Gist ID | Content | Why it matters |
|---|---|---|
| `0480d2b2b35ad594e57b6543952be307` | **GA100 Fuse and Register Reference Table** (about 50 kB) plus `probe.sh` (about 19 kB) | The clean room's differential corpus: 120 registers read across 15 Ampere cards (2 physical 170HX 10 GB, 11 rented via cloud, 2 physical Drive A100 32 GB). Establishes that exactly **five** register groups distinguish a 170HX from an A100 of the same silicon: SM speed select, PCIe boot generation, NVLink disable, ECC enable, and FBPA CFG1 geometry. Also establishes that two physical 170HX units agree on **107 of 120** registers, with all 13 differences being per-die binning artefacts, which is what makes an unlock recipe transferable between cards. |
| `84cd3921788d2ffbc1e9bf8b6f2c9396` | **GA100 VBIOS Comparison Table** (about 27 kB) plus `z1_dump_and_parse_vbios.sh` and `z2_parse_vbios_table.py` | Seven ROMs parsed statically, with the CFG1 strap table located by heuristic and memory-training entries decoded. The dump script is read-only with respect to flash: no write path exists. |
| `da...` (A100 comparison), `dafea7b6663c13edc28b33872f6e51be` | Supplementary VBIOS comparison material | Secondary. |

> [!WARNING]
> **The VBIOS parser carries stale labels**
>
> `z2_parse_vbios_table.py`'s docstrings contradict its own output. It claims the A100 PCIe strap
> table sits at about `0x3FB18` while the comparison table places it at `0x4285A`. It labels RFRD
> an "power table" when RFRD is an image layout descriptor and its `field_0C` is a MAC-verified
> range size, not a power limit. Its FBPA tier extractor searches a window around the CFG1 table
> and will match the CFG1 table itself if nothing else qualifies. Anyone using its output labels
> verbatim propagates all of this.

---

## 7. Forks, reimplementations and adjacent tools

At least six public repositories forked or reimplemented the unlock within days of release. None is
authoritative over `master`.

| Repository | What it is | Trust |
|---|---|---|
| `arabel1a/cmpunlocker` (2026-07-15) | Early fork | Historical |
| Six further personal forks and repackagings | Forks and repackagings | Historical. One of them carries a `combined-multiple-cards-gen2` branch, a notable community merge of the Gen2 work with multi-card support. Owner names are omitted under this wiki's anonymisation policy. |
| `asm64-hooligan/cmpunlocker` branch `mem_overclock` | Memory overclock experiment, multiplier lowered 72 to 70 | Experimental, single author, test requested in-channel |
| `theneocorp/cmppatcher` | A **different approach**: patches the NVIDIA driver **binary** directly so the change survives driver updates. Reported 3D acceleration and FP32 FMA bypass. | Independent, unverified here |
| `abobasixseven/unlock-cmp-170hx` | **Not a writeup.** Contains only `README.md` and `cmp90_compute_unlock_prompt.md`, both ending in AI-agent execution instructions such as "EXECUTE STEP BY STEP: 5 -> 6 -> 6.5 -> 7", and hardcoding one user's home directory throughout its backup and clone commands. | Use with care. Its register tables match the shipping patches; its prose and PCIe chapter are secondary summaries, not measurement. |
| `eastmoe/CMPGPU-patch-script` (`optimize-cmp-cuda.py`) | Interactive llama.cpp source patcher with five independent optimisation groups, each defaulting to no: `fp32_fma_flag` (adds `-fmad=false`), `fp32_fma_split` (rewrites `fmaf(...)` to `__fadd_rn(__fmul_rn(...))` in `quantize.cu`), `math_intrinsics`, `dp2a`, `fp16_bf16_cuda_core`. Eleven PatchSpec entries across seven files, `.cmp-bak` backups, `--dry-run`/`--no-backup`/`--restore`. | Reliable, and its own README warns performance may **decrease** on non-170HX CC 8.x devices. |
| `cachenetics/170tune` | Tuning and qualification harness installing as `/usr/local/bin/170hx-oc`; measures, gates and recovers clock and voltage settings, and treats "a completed benchmark as evidence of nothing" | Reliable in approach. Whether it persists settings across reboot is an open question its own author flagged. See [tuning](../operations/tuning.md). |
| `Kepling5001/Miners` (`CMP170HX_Compute_Unlock_v8_3.sh`) | A compute-unlock shell script leaked publicly and quickly deleted. Its author described it as "just the compute only logic ... with some minor modifications to attempt to run on multiple GPU's vs 1. Nothing new" | Historical only. Contains nothing about the memory unlock. |
| `arabel1a/ml-on-cmp`, `arabel1a/gpu-micro-bench` | Microbenchmark repositories | Reliable for the measurements they publish |
| `Highwayaiexpose/CMP-170hx-64gb-LLM-benchmarks` | Community LLM benchmark collection on unlocked 64 GB cards | Use with care: rig-specific, single-source |
| `InnovativeOSS117/Gaming-on-A100` | Graphics-on-GA100 work | Adjacent; relevant to the display-output and 3D questions |

### Third-party validation and measurement tools

Used repeatedly and worth knowing about: `ComputationalRadiationPhysics/cuda_memtest` (v1.2.3, the
maintainer-recommended VRAM validator, exits on first error, **hangs indefinitely on the 80 GB
profile unless capped at 39 GB**), `GpuZelenograd/memtest_vulkan`, `wilicc/gpu-burn`,
`ProjectPhysX/OpenCL-Benchmark`, `ReinForce-II/mmapeak` (tensor throughput),
`zzc0721/torch-performance-test-data` (GEMM), `sasha0552/nvidia-pstated` (idle power management;
see its issue #6), and `xCuri0/ReBarUEFI` for hosts without resizable BAR firmware support.

---

## 8. Issue threads and discussion trails

**`github.com/dartraiden/NVIDIA-patcher` issue #73.** *Trust: Reliable as a record, unreliable as
analysis.* This is where the whole effort began, in March 2026, before moving to Discord in April.
It also carries the memory-strap explanation ("the amount of addressable RAM on each of the HBM2
stacks is defined by a 32-bit word at a specific location in one DMEM region"), the strap-resistor
discussion (Strap4 at R999/R1000, PCIE_CFG), and the first public "40 GB confirmed working" report.
Note that the NVIDIA-patcher project **itself cannot drive the 170HX**: it is graphics-oriented, and
what it yields is a GeForce-classified GPU rather than a compute unlock. Applying it to a 170HX does
not affect the FP32 throttle.

An April 2026 write-up linked from that thread concluded, after roughly 18 hours of automated
analysis, that "the FP throttle is hardware enforced and can't be overridden". Its own footer states
it was performed on driver **535.288.01**, which predates the GSP layout the shipping unlocker
targets, and its conclusion is refuted by the shipping compute unlock. It is a good example of a
carefully documented wrong answer.

**`github.com/ggml-org/llama.cpp`**: issue #24616 (the CMP-specific patch set that reached 240 t/s
pp512 on a 90HX at PCIe 1.1 x4), issue #24730 (no DSA attention support, which is why GLM-class
models fall back to dense attention and become unusable here), PR #19378 (backend-agnostic tensor
parallelism via `--split-mode tensor`), and discussion #15013. See
[LLM inference](../operations/llm-inference.md).

**`github.com/JustVugg/colibri`**, **`github.com/LaurieWired/tailslayer`** (refresh-timing tuning),
**`github.com/microsoft/Tutel`**, **`github.com/sgl-project/sglang`**, **`ikawrakow/ik_llama.cpp`**:
adjacent tools circulated for workload work, none validated on this card in the source material.

**FluidX3D issue #8 (2023-10-27).** Credit for the original FMA-disable discovery, two months before
it reached NVIDIA-patcher issue #73 on 2023-12-06. The two-line patch to `LBM_Domain::device_defines()` in
`src/lbm.cpp` (index `d99202f..28aeb25`, around line 286) applies `#pragma OPENCL FP_CONTRACT OFF`
plus macro-shadowing to every generated OpenCL program without touching kernel source, and measured
**7,681 MLUPs/s** with FMA removed, at 1175 GB/s: a **3.4x** improvement over 2,276 MLUPs/s stock.
Separately, the same technique reported on the NVIDIA-patcher thread took 170HX FP32 from
**0.395 → 6.285 TFLOPS, a factor of 15.9**. Both
are 2023 locked-card results. (6.25 TFLOPS is a different, locked-mode custom-GEMM reading, recorded
in the corpus as a failed-unlock signature: do not attach it to this result.)

---

## 9. Sources deliberately excluded

- **Commercial and marketplace links of every kind.** Procurement is out of scope for this wiki.
- **Distributor part numbers.** Two different distributor SKUs circulated for the capacitor-mod
  part, and no source settles which is correct. This wiki quotes only the manufacturer part,
  Taiyo Yuden `MAASJ105SB7224KFCA01` (220 nF, 6.3 V, X7R, 0402). See
  [physical mods](../operations/physical-mods.md).
- **Leaked material.** The February to March 2022 NVIDIA breach cache is referenced in the record
  only as a provenance question. Its contents are not used, quoted or linked here. See
  [clean room and provenance](../history/clean-room-and-provenance.md).
- **AI chat transcripts shared as evidence.** Several dozen shared assistant conversations appear in
  the corpus. They are recorded as leads and as documented hallucinations, never as sources.
- **Video walkthroughs.** Several exist, in several languages. None was verifiable against a
  register or a log, so none is cited.

---

## Related pages

- [Preserved artifacts](artifacts.md)
- [Methodology](methodology.md)
- [Clean room and provenance](../history/clean-room-and-provenance.md)
- [Tool lineage](../history/tool-lineage.md)
- [Dead ends](../history/dead-ends.md)
