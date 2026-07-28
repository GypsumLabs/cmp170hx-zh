# The clean room and the provenance question

## What this page covers

The CMP 170HX unlock was developed under an explicit clean-room protocol, and the single question
that protocol existed to answer is whether the resulting code could have been produced without
material from the February 2022 LAPSUS$ breach of NVIDIA. This page records how the clean room was
organised, what its rules were, what its permitted inputs were, what the contemporaneous provenance
assessment concluded and on what reasoning, what later byte-level comparison established, and how a
leaked private proof-of-concept entered the picture on 2026-07-18.

Two results dominate everything below.

1. **Every constant in the shipping ROP payload but one has been traced to a dated public or
   clean-room-derived artifact that predates the shipping patch.** Gadget addresses come from a
   decrypted debug-booter disassembly published 2026-07-01, gadget semantics from an auto-generated
   atlas published 2026-07-10, the DMEM stack frame grid from a public git commit on
   2026-07-15T04:47Z, and the buffer, guard, fill and size constants from the June 2026 academic
   preprint. The exception is the `0x00000007` planted at payload offset `0x1100` (`D[0x1900]`),
   which no dated artifact predating the patch accounts for. Nothing else in the payload requires
   leaked material to derive.
2. **The shipping `cmpunlocker` driver patch set is, line for line, the leaked `patch.diff`,** with
   10 GB dual-geometry support added and one hostile change removed, adopted 70 minutes after
   `patch.diff` was posted. Derivability in principle and derivation in fact are not the same thing,
   and the source material does not settle which happened.

This page reports both, states the arguments made on each side, and stops there. It does not offer a
legal conclusion, and no individual is named anywhere on it. For the code itself see
[the six driver patches](../unlock/driver-patches.md) and [the ROP chain](../unlock/rop-chain.md);
for dates see [the project timeline](timeline.md).

---

## Why a clean room existed at all

The unlock did not begin in a clean room. It began on a public GitHub issue tracker in March 2026,
moved to a Discord server in April 2026, and by May 2026 had produced the decisive cryptography
result that allowed the AES-encrypted, RSA-signed `booter_load` code to be read. In June 2026 a ROP
chain able to jump to an arbitrary address inside that code was demonstrated and announced publicly.
Development then moved into a private group of **seven people**, which produced the proof-of-concept,
the academic preprint dated June 2026, and two internal **Driver Modification Guides** (one for
compute, one for memory).

That private group made two decisions that shaped everything afterwards:

- **Publish the paper, withhold the exploit code**, and wait for independent reproduction.
- **Delete the original Discord server**, on the stated grounds that it may have contained material
  leaked from NVIDIA.

The clean room was created to reproduce the withheld result from scratch, using only inputs whose
provenance could be shown. The threat it was managing was the LAPSUS$ breach: as characterised by
the later provenance assessment, a February to March 2022 incident that leaked approximately **1 TB**
of NVIDIA data including GPU driver source code, internal hardware documentation and firmware signing
keys. The leaked cache remains publicly locatable (the Internet Archive was named in-channel), which
is exactly why a rule was needed rather than an assumption.

---

## The rule set

The governing standard, stated as channel policy from 2026-06-27 and enforced by deletions and ban
threats for the whole period:

1. **No NVIDIA secrets may be discussed.**
2. **Secret knowledge is admissible only if the same information can be shown to be derivable from
   public sources.**
3. **Posting leaked or illegal material is a ban.** This explicitly covered leaked source, leaked
   schematics, and any file carried over from the deleted earlier Discord.

The June 2026 preprint was designated **the single clean input document**, on two grounds: it was
published on a scientific-publication site, and it had been sent to NVIDIA.

Rule 2 is the load-bearing one, and it is also the rule the 2026-07-18 events put under the most
strain. See [Two readings, unresolved](#two-readings-unresolved) below.

---

## Clean room and dirty room: intended versus actual

A two-team split was proposed on day one. The stated organising principle was conventional: a
**dirty-room** team performs the reverse engineering and emits documentation containing nothing
illegal, and a **clean team** that has seen nothing else reimplements the result from those documents
alone.

That split was largely dropped. What actually materialised was a **channel split, not a team split**:

| Intended | What happened |
|---|---|
| Dirty-room team, isolated, does RE and writes specifications | No document in the source set uses "dirty room" as an operating team |
| Clean team, exposure-free, implements from those specifications only | Same people worked across channels |
| Separation enforced by team membership | Separation enforced by channel topic and by the admissibility rule |

The channels that did exist were a `#general-how-to-cleanroom` how-to channel carrying only working
values, and deeper technical channels carrying register sweeps, Falcon exit-path analysis and DMEM
stack exploration. Confidence in this characterisation is **medium**: the intent is quoted verbatim
in the archive and the channel structure is directly observable, but the two-team protocol is not
evidenced as ever having been staffed.

!!! note "Superseded"
    Any description of the project as having run a staffed dirty-room team is not supported. The
    admissibility rule, not team isolation, was the actual mechanism.

---

## The clean input corpus

Everything the clean room permitted itself to build on, with the argument for each:

| Input | Why it was held clean |
|---|---|
| **"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"**, June 2026, Zenodo record `20916112`, ResearchGate publication `408132536`, 16 pages | Published on a scientific-publication site and disclosed to the vendor. Designated the single clean input document. Circulated 2026-06-26; posted into the clean-room server 2026-07-16T06:07:12Z as `main.pdf` |
| `NVIDIA/open-gpu-kernel-modules` (tags `610.43.02`, `610.43.03`, and earlier `580.x`) | NVIDIA's own published source |
| The **debug** `booter_load` binary | Compiled as a C array inside NVIDIA's `.ko` and published in the open-gpu-kernel-modules tree as `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`. Extracted with the Nouveau firmware-extraction tool (patched for GA100). Working the path out took the group two days |
| NVIDIA's **public AES-128-ECB test keys** | Sourced from NVIDIA's public Jetson Secure Boot documentation. The key construction is the MD5 initialization vector `...0123456789abcdef...` with the key number as the last byte. A self-contained public-domain Rijndael decrypter and key validator (`rijndael-tool.zip`) containing no NVIDIA material was published in-channel |
| The **GA100 Fuse and Register Reference Table**: 120 registers across 15 Ampere cards | Produced entirely from read-only MMIO probing of hardware the participants owned or rented. See [fuses and OTP](../hardware/fuses-and-otp.md) |
| BAR0 register reads from the card itself, and from A100 comparison parts | Owner-side measurement of owned hardware |

The framing agreed in-channel about the encryption was pointed: NVIDIA's mistake was **not** the use
of trivial test keys, but **shipping exactly the same binary in the debug and production branches**,
and signing a binary containing a serious vulnerability.

### The 15-card differential corpus

The register-level provenance argument rests on this table. It compares 120 registers read by
`tools/mmio-probe/probe.sh` across:

- **2 × CMP 170HX 10 GB**, physical, probed 2026-05-05 and 2026-05-07
- **11 cards rented via a GPU-rental provider**: A100 SXM4 40G, A100 PCIe 40G, A100 PCIe 80G, A10,
  A16, A5000, A6000, RTX 3080, RTX 3080 Ti, RTX 3090, RTX 3090 Ti. (An engineering-sample part
  appears as a column in the fuse table but carries no values in any row.)
- **2 × Drive A100 32 GB** (`GA100-550F-A1`, PG199), physical, probed 2026-05-31

Exactly five register groups distinguish a 170HX from an A100 of the same silicon: SM speed select,
PCIe boot generation, NVLink disable, ECC enable, and FBPA CFG1 geometry.

Two physical 170HX units were also shown to be register-identical where it matters: **107 of 120
registers byte-identical**, with all 13 differences being per-die binning artefacts (floorsweep masks
and their FBIO/STATUS mirrors, the per-unit `FEAT_OVR_SM_SPD` encoding, `FEAT_OVR_QUADRO`, the HBM
silicon identity registers, and the per-FBPA readbacks that follow the floorsweep). Every restriction
fuse matched exactly. That result is what licenses generalising a recipe derived from one card to
another.

---

## The provenance standard for the register values

Accepted in-channel on 2026-07-02 as the justification for publishing the target register set:

> The memory geometry comes from the VBIOS and from reading the BAR0 address space, and everything
> else can be deduced by diffing an A100's BAR0 output against a 170HX's, changing everything to the
> A100 values.

Only NVIDIA open-source driver data and NVIDIA's public test keys were used to produce the clean
`booter_load` assembly. The 120-register cross-variant fuse table is the independent backing for the
claim: it shows the A100-versus-170HX delta directly, without reference to any internal document.

---

## The load-bearing technical fact: debug equals production where it matters

The entire clean-room approach depends on one empirical result. If the `-debug` compile of
`booter_load` carried extra bytes, every gadget address derived from the readable debug disassembly
would be shifted and useless on production silicon, and the only route to correct offsets would be
the production binary (which cannot be decrypted) or leaked source.

The concern was raised on 2026-07-02 and disproved two ways in the same period:

- The debug and production binaries are **exactly the same size**.
- A ROP chain built purely from the debug disassembly **executed correctly on production silicon**.

!!! question "Open problem"
    "Same size plus one successful chain" is a proof by instance, not by construction. No document in
    the source set records an actual byte-level comparison of the `IMAGE_DBG` and `IMAGE_PROD` blobs,
    which the bindata archive makes trivially possible. Settled by: hashing the two entries in
    `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`. Nobody has published that hash.

A related debate was whether touching the GSP signature at all breaks cleanliness. One camp held that
tampering with a signature makes the result unclean by definition. The counter-position went
unrebutted: return-oriented programming reuses code already present in the signed binary and needs no
access to NVIDIA source, so a chain built from a legitimately decrypted binary is clean, and the only
conceivably unclean element would be the payload itself if it had been copied rather than derived.
The production booter is never modified: every working tool loads an unmodified signed image and only
splices the detached 384-byte signature back at `PATCH_LOC 0x8900`.

---

## The 2026-07-18 provenance assessment

A document titled **"Assessment: Is patch.diff Derived from LAPSUS$-Leaked Information?"** was posted
at **2026-07-18T18:40:16Z**, exactly **39 minutes** after `patch.diff` itself was posted at
**2026-07-18T18:01:15Z**. Both timestamps are decoded from Discord message snowflakes to the
millisecond.

**Scope.** A patch against `NVIDIA/open-gpu-kernel-modules` tag `610.43.03`.

**Clean-source corpus, exactly three items and no more:**

1. `paper.md` (the Canary preprint)
2. `how_to.discord.html` and `discussion.discord.html`, exported transcripts of two channels of the
   clean-room server
3. `NVIDIA/open-gpu-kernel-modules` tag `610.43.03`

No leaked-cache comparison was available to the assessor, which the assessment itself records as a
limit on its conclusion.

**Method.** Compare the patch against those three sources, then apply the patch cleanly to a cloned
repository and inspect it in context.

**Verdict, verbatim:** "The available evidence does not support a conclusion that this patch is
derived from LAPSUS$-leaked information."

### What the assessment classified as clean

| Class | Contents | Recorded verdict |
|---|---|---|
| **Clean from the paper** (nine concepts) | Stack-canary reference-word vulnerability (§5.1-5.3, Thesis 1); DMA overflow via unbounded signature-length copy (§3.2, §5.5); SEC2 Falcon HS-mode entry via signed booter (§2.2, §5.4); uniform-fill value **V = `0x4a7`** (§5.5, emulator trace); overflow signature size **SIGSZ = `0xf800`** (§5.5); PLM unlocking as the pivot after HS code execution (§6.1); the feature-override shadow register concept (§2.1); WPR2 teardown from HS (§8.5); the inverted threat model of a rooted host with the GPU as defender (§2.3) | "Clean. These concepts are fully documented in the paper and require no special access." |
| **Clean from the open driver tree** (kernel-internal APIs) | `memdescCreate`, `memdescMapInternal`, `memdescFlushCpuCaches`, `memdescGetSize`, `memdescGetPhysAddr`; `pmaRegisterRegion`, `pmaGetRegionInfo`, `pmaGetFreeMemory`, `pmaGetTotalMemory`; `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`; `os_open_and_read_file`; `kgspExecuteBooterLoad_HAL`, `kgspPopulateWprMeta_HAL`; `FB_REGION_DESCRIPTOR`, `PMA_REGION_DESCRIPTOR`; `NV_FLAG_PERSISTENT_SW_STATE`; `GPU_REG_RD32`/`GPU_REG_WR32`; `NV2080_CTRL_CMD_FB_GET_FB_REGION_INFO_PARAMS` | "Clean. Any competent kernel module developer can discover these by reading the source." Every named symbol is present in the shipping patch set |
| **Clean but early** (eight elements, present in the public transcripts dated 2026-07-09 to 2026-07-17) | Feature-override addresses `0x823804`, `0x82381c`, `0x823820`, `0x9a0204`, `0x100ce0`; WPR2 registers `0x1fa824`/`0x1fa828` and WPR2 carving as a blocker; FB-geometry PLM addresses `0x100b10`/`0x100b38` and `0x9a0148`/`0x9a014C`/`0x9a0108`/`0x9a010C`; `0x8403C4` as `resetPLM`; three named exit strategies (`secure_teardown`, premature exit `0x8117`, `multiwrite_then_mutexfree_cleanexit`); FLR persistence of certain registers; a non-secure ucode loader for direct SEC2 control; DMEM stack exploration from `D[0xFFC4]` through `D[0xFFF0]` | "Clean, but overlapping." |

One citation in that table is wrong. "WPR2 teardown from HS" is mapped to paper §8.5; §8.5 is titled
"Persistence across FLR" and argues that override values held in an always-on island turn a transient
exploit into a durable state. It contains no WPR2 teardown and no ROP discussion. The paper's only
ROP reference is a single citation in §5.5. The practical consequence is that the shipping patch's
explicit WPR2 save and restore around each Booter pass is not covered by the paper as the table
implies. The assessment separately and correctly attributes WPR2 handling to the public transcripts,
so this is a citation error rather than a substantive one.

### The assessment's three arguments for external origin

These are recorded as arguments, not as facts.

1. **Negative evidence.** The patch contains no NVIDIA-internal code comments, no revealing variable
   names from leaked builds, no use of the leaked signing keys (the exploit forges no signature), and
   no internal-only register names that are not also discoverable through BAR0 probing. The paper's
   ethics statement corroborates the key point directly: "We extracted no signing keys and forged no
   signature."
2. **The sledgehammer argument.** `patch.diff` inserts `return NV_OK;` as the first statement of
   `gpuValidateRegOps` in `subdevice_ctrl_gpu_regops.c`, leaving the original body dead. It is
   unconditional, affects all GPUs rather than only the CMP 170HX, and disables control-panel
   register read/write validation entirely. The inference drawn: "The sledgehammer approach suggests
   an external developer who needed a quick bypass and didn't care about collateral damage to other
   GPUs or security... An internal NVIDIA engineer or someone with leaked docs would likely make a
   surgical change."
3. **The masquerade naming.** `SEC2_DEBUG_PRI_*`, `kgspSec2PostblTiming*` and the `SEC2_DEBUG` log
   prefix exist nowhere in NVIDIA's codebase, and "PostBL Timing" is a plausible-sounding but
   fictional feature name. The scheme reads as an attempt to disguise exploit code as a legitimate
   manufacturing or debug feature, which "would be unnecessary for someone with legitimate access."
   The naming is verbatim in the shipping code, which defines
   `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM 0x00823804`,
   `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED 0x0082381c`,
   `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820`,
   `SEC2_DEBUG_PRI_FBPA_CFG1 0x009a0204` and `SEC2_DEBUG_PRI_MMU_LMR 0x00100ce0` in
   `0002-booter-verify.patch`.

!!! danger "The `gpuValidateRegOps` bypass is not in the shipping tool"
    The unconditional bypass is real and serious: any process with `NV_GPU_REG_OP` access could read
    or write arbitrary GPU registers on any NVIDIA GPU in the machine. It exists **only in the leaked
    `patch.diff`**. The shipping `cmpunlocker` patch set does not touch
    `subdevice_ctrl_gpu_regops.c` at all, and the string `gpuValidateRegOps` appears nowhere in
    `master` or in any of the twelve unreleased branches. Any text attributing this hole to
    `cmpunlocker` is wrong.

### The single residual concern

Two items were rated HIGH and left uncleared: the complete ROP chain DMEM byte offsets (`0x1100`,
`0x5b40`, `0xf754` through `0xf7f8`) and the gadget chain mapping `writeAddr`/`writeValue` through
DMEM stack slots, described as `_kgspSec2PostblTimingFillPayload` writing **24 specific 32-bit
values** at precise byte offsets inside the `0xf800`-byte signature buffer.

The reasoning was fourfold:

| # | Argument |
|---|---|
| (a) | The paper describes the concept of a uniform-fill ROP chain but does not publish the version-specific DMEM layout |
| (b) | The offsets are booter-version-specific, and getting them wrong yields a crash (`MB0=0x31`, `IMEM_MISS_INS`, or canary failure) rather than a working exploit |
| (c) | The community was exploring what it believed to be a different offset range |
| (d) | Deriving them requires a cycle-faithful Falcon emulator plus the specific booter binary, NVIDIA-internal documentation of the stack frame layout, or the leaked booter source |

Its own stated mitigation was that the paper's emulator methodology is sufficient to reproduce the
analysis. Bottom line, verbatim: "The ROP chain offsets are the only element that would require
significant independent work to produce without leaked documentation, and the paper explicitly
describes how to do that work."

The count is correct: the shipping payload contains exactly **24** `_kgspSec2PostblTimingPutU32`
calls, at payload offsets `0x1100`, `0x5b40`, `0xf754`, `0xf758`, `0xf75c`, `0xf76c`, `0xf774`,
`0xf780`, `0xf788`, `0xf78c`, `0xf790`, `0xf794`, `0xf798`, `0xf79c`, `0xf7a0`, `0xf7a4`, `0xf7b0`,
`0xf7b8`, `0xf7c4`, `0xf7c8`, `0xf7d8`, `0xf7e0`, `0xf7f4`, `0xf7f8`.

---

## What later analysis established about that residual concern

Concerns (c) and (d) do not survive. The corrections below were derived by re-reading the archived
artifacts and the shipping source, not quoted from the assessment.

### (c) is a base-offset framing artifact

The payload is DMA'd to DMEM `0x800`, so **payload offset + `0x800` = DMEM address**. The two
"different" ranges are the same range:

| Patch offset | DMEM address | Status in the assessment's own tables |
|---|---|---|
| `0xf754` | `D[0xFF54]` | flagged HIGH |
| `0xf76c` | `D[0xFF6C]` | flagged HIGH |
| `0xf7c4` | `D[0xFFC4]` | listed as **clean but early** |
| `0xf7f8` | `D[0xFFF8]` | flagged HIGH |

The clean-but-early list already contained `D[0xFFC4]` through `D[0xFFF0]`, which covers four of the
22 stack slots the assessment flagged as HIGH. By the assessment's own accounting, part of the range
it flagged as HIGH was already flagged as clean. The assessment cited the patch offset as suspect and
the DMEM address as clean, on the same slot.

### (d) is refuted by dated public artifacts

Every code address in the shipping ROP chain is an instruction boundary in the clean room's own
decrypted debug-booter disassembly, published **seventeen days before** the patch.

| Artifact | Posted | What it supplies |
|---|---|---|
| `booter_load_ga100_dbg_seccode.fuc5.asm` (545,149 B) | 2026-07-01T12:40:37Z | Raw envydis output; every chain address `0x0cbd`, `0x0ccb`, `0x10aa`, `0x10b9`, `0x1fbd`, `0x582d`, `0x7f2f`, `0x815a`, `0x0d66`, `0x04d4` matches exactly one instruction line |
| `...annotated.fuc5.asm` | 2026-07-03T17:12:52Z | Per-function banners |
| `...annotated.fuc5_v2.asm` (607,702 B, 11,875 lines) | 2026-07-09T03:03:21Z | Every `lcall` carries an inline comment naming the callee |
| **Register Gadget Atlas** | 2026-07-10T13:40:14Z | Machine-generated from that disassembly. Lists `0x0cbd` as "`$r10 <- $r0`, canary(r15==r9), via-call, `mpopaddret $r3 0x4`" and `0x1fbd` as "`$r11 <- $r10`, canary(r15==r9), via-call, `mpopaddret $r2 0x4`", precisely the roles they play in the shipping chain, including the `mpopaddret` epilogues that produce the frame stride |
| `cmpunlocker` initial commit `9b9fb2f`, `common/constants.yaml` | 2026-07-14T21:47:02-07:00 = 2026-07-15T04:47:02Z | `dmem_layout: dma_target 0x0800, payload_size 0xF800, guard_addr 0x6340, canary 0xFACEB13D`; `booter_addrs: bar0_write_gadget 0x10B9`; `payload_frames: frame_start_addr 0xFF48, frame_stride 0x18, frame_field_offsets {r0 0x00, r1 0x04, r2 0x08, r3 0x0C, saved_reg 0x10, return_addr 0x14}` |
| `ROP_CHAINS_1180f8_nibble_writeup_20260715.md` | 2026-07-15T18:48:10Z | The same grid in prose: "N BAR0-master writes via the light `0x10b9` self-chain, **+0x18 DMEM per write**", tabulating `D[0xFF50]`, `D[0xFF54]`, `D[0xFF5C]`, `D[0xFF68]`, `D[0xFF6C]`, `D[0xFF74]`, `D[0xFF80]`, `D[0xFF84]` |

**All 22 stack-slot offsets in the shipping patch fall exactly on a named field of that six-field,
`0x18`-stride grid, with zero unaligned hits.** The remaining two of the 24 values are the guard word
(`0x5b40` maps to `D[0x6340]`) and `0x1100` (maps to `D[0x1900]`).

The remaining non-gadget constants are accounted for as well: `0xf800`, `0x800`, `0x6340` and `0x4a7`
come from the paper's emulator trace and are on the assessment's own clean-from-paper list;
`0xc0deca7e` is the paper's published guard stub value; `0x5b40 = 0x6340 - 0x800` is arithmetic on two
numbers the paper prints; `0x0000ffbc` at `D[0xFFB0]` is a self-referential DMEM stack pointer into
the frame grid; and `0x00008e18` at `D[0xFF90]` lies beyond the booter's code image (the disassembly
ends at `0x86ff`) and points into the register-descriptor table region `0x8e04`/`0x8e08` documented
in the annotated listing at instruction lines `0x0d39`, `0x0da1` and `0x0e1b`.

!!! note "Superseded"
    The assessment's own gap-closing suggestion, reproducing the analysis with the paper's Falcon
    emulator, turned out to be unnecessary. It is also unavailable: a request for the emulator on
    2026-07-25 was answered with a flat "No, they did not [release it]".

### The clean room's own chain was related but not a copy

The clean-room Python unlocker and the shipping C chain share the buffer base `0x800`, the size
`0xF800`, the guard address `0x6340` and the `0xFF48`/`0x18` six-field frame grid. They differ
visibly in two ways:

| | Clean-room Python (`payload/build.py`, commit `9b9fb2f`) | Shipping C (`0001-sec2-postbl-plm-ss-cfg.patch`) |
|---|---|---|
| Canary literal | `0xFACEB13D` (the project codename) | `0xc0deca7e` (the paper's published stub) |
| Chain shape | One self-chaining gadget `0x10B9`, one frame per write | Longer chain through `0x0cbd`, `0x1fbd`, `0x815a`, `0x582d` |
| Terminator | `0x0000810D` | `0x00000ccb` (ACR mutex release) then `0x00007f2f`, exactly the `multiwrite_then_mutexfree_cleanexit` strategy named in the public transcripts |

The exploit's codename, **FACEB13D**, pronounced "fake bird", refers to the stack guard canary that
had to be defeated, not to the Falcon. The enumerated hurdles were security by obscurity, stack
canaries, security levels L0 to L3, an immutable boot ROM, a secure co-processor, AES encryption of
code, and RSA signing of code.

---

## The leaked proof-of-concept

### The redistributed package

Roughly three days after the clean-room compute unlocker was released and cloned to GitHub, a
"Chinese unlock" surfaced on Russian Telegram. It was the leaked private proof-of-concept, not
independent work, according to the assessment made at the time.

Package structure, as inspected by multiple independent reviewers:

```text
cmp170hx-unlock-610.43.03.zip
├── install.sh                              # assessed safe on inspection
├── NVIDIA-Linux-x86_64-610.43.03.run       # byte-identical to the official installer
├── open-gpu-kernel-modules-610.43.03/      # patched source + precompiled binaries
└── README.txt                              # irrelevant
```

Diffing the shipped source against `NVIDIA/open-gpu-kernel-modules` tag `610.43.03` produced
`patch.diff` at **35,867 bytes, 887 lines, 11 files**. Every modification was isolated to the open
kernel-module component; no closed binaries were altered. The recommended safe handling was to delete
the shipped open-modules folder, `git clone` upstream, apply `patch.diff`, recompile, and only then
run `install.sh`.

Archive size is reported inconsistently (537.2 MB in the account that also gives the inner `.run` at
461.5 MB, roughly 520 MB in another), and a second filename `cmp170hx-unlock-610.43.03.tar.zst`
appears in one source. Both filenames may be real, the same payload redistributed twice.

A holder of both artifacts reported the diff to be **word-for-word identical** to the code in the
private Driver Modification Guides. Confidence: **high** for the archive structure and the diff size
(multiple reviewers, the diff file itself archived); **medium** for the "leaked rather than
rediscovered" attribution, which rests on a single byte comparison from one side of a contested
attribution.

Two further points about the redistributed unlocker, from independent inspection: it writes exactly
the same privilege-level-mask table as the public repository, unlocks no extra feature, does **not**
enable PCIe Gen2, and recognises only the 8 GB card ("currently this unlocker only supports 8G cards
and can't recognize the 10G card").

### The leaked shell script

Separately, a compute-unlock shell script leaked publicly as `CMP170HX_Compute_Unlock_v8_3.sh`,
posted to a public GitHub repository on 2026-07-14 and quickly deleted. Its author described it as
"just the compute only logic that was posted here, with some minor modifications to attempt to run on
multiple GPU's vs 1. Nothing new sadly", implemented by duplicating the injection block per card with
hardcoded PCIe IDs. It contained nothing about the memory unlock.

### The blog claim

A Chinese blog covering the event claimed two hackers had independently unlocked the memory, and
showed a screenshot of the team's `booter_load` code with entirely different function names and
comments. Different names are consistent with either an independent disassembly-plus-annotation pass
(exactly how the clean room's own names were produced) or with re-annotation of copied material.

!!! question "Open problem"
    Whether that screenshot was independently decrypted using the public hints was never settled.
    Next step: compare the screenshot's instruction addresses against
    `booter_load_ga100_dbg_seccode.fuc5.asm`. If they match a debug build, the author would have had
    to decrypt it with the public Jetson test key, which is the clean path.

---

## The 70-minute adoption window

This is the part of the record that the contemporaneous assessment could not have known, and it is
established by git author timestamps, `diff -Naur` header mtimes, and decoded message snowflakes.

| Time (UTC) | Event |
|---|---|
| 2026-07-18T18:01:15Z | `patch.diff` posted to `#general-how-to-cleanroom` |
| 2026-07-18T18:26:26Z | Every file in the shipping `cmpunlocker` patch set carries this `diff -Naur` header mtime (`2026-07-18 11:26:26 -0700`). One tree, written at one instant, 25 minutes after the posting |
| 2026-07-18T18:40:16Z | The provenance assessment is posted, in the middle of the window |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` authored on the `memory` branch, **70 minutes** after the posting |
| 2026-07-18T20:51:36Z | `6b7d9ee "FULL WORKING THING"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` merged to `master` |

Direction of derivation is not ambiguous: the shipping repository contained **no driver patch of any
kind** before `06fabf2`, and `patch.diff` supports only the 8 GB `0x20C2` card.

### What actually differs between the two

Comparing every added line of the archived `patch.diff` against the concatenation of
`driver/patches/0001` through `0006`:

| Measure | Value |
|---|---|
| `patch.diff` | 35,867 B, 887 lines, 11 files |
| `cmpunlocker` patch set | 890 lines, 6 patch files, 10 target files |
| Added lines byte-identical between them | **638** |
| Lines unique to `patch.diff` | **19** |
| Lines unique to `cmpunlocker` | **43** |

Every one of the 19 `patch.diff`-only lines is either the 8 GB-only hardcoded form of something
`cmpunlocker` made per-profile, a log line `cmpunlocker` extended with the device ID, or the single
line `+    return NV_OK;` in `gpuValidateRegOps`:

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_PCI_DEVICE_ID 0x20C2
NvU32 cfg1Value    = 0x02779000U;
NvU32 lmrValue     = 0x0000020BU;
NvU64 targetFbBytes = 0x0000001000000000ULL;  /* 64GB */
/* plus the devId == 0x20C2 guards */
```

Every one of the 43 `cmpunlocker`-only lines is the 10 GB (`0x2082`) counterpart: the split into
`SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID 0x20C2` and
`SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID 0x2082`, the `cfg1Value = 0x02669000U` /
`lmrValue = 0x0000028AU` branch, `targetFbBytes ... : 0x0000000A00000000ULL`, and the dual device-ID
guards. Nothing else differs. Those geometry values are the canonical ones documented on
[memory geometry](../unlock/memory-geometry.md).

---

## Two readings, unresolved

The evidence is in genuine tension with itself, and the source set cannot resolve it. Both readings
are stated here in full because a reader is entitled to weigh them.

=== "Side A: clean by the room's own rule"

    Every constant in the shipping ROP payload is independently derivable from dated public or
    clean-room-derived material that predates `patch.diff`: gadget addresses from a disassembly
    published 2026-07-01, gadget semantics from an atlas published 2026-07-10, the frame grid from a
    public git commit at 2026-07-15T04:47Z, and the buffer, guard, fill and size constants from the
    June 2026 paper. The clean room had independently built a working ROP chain on the same grid,
    with the same buffer, the same guard address and the same `reg_write_indirect` BAR0 write
    primitive (entered at `0x10b9`, where the shipping chain enters at `0x10aa`), and had shipped it
    publicly four days earlier. On this reading the clean room satisfied its own rule ("secret
    knowledge is admissible only if the same information can be shown to be derivable from public
    sources"), and the assessment's negative verdict is correct and in fact understated.

=== "Side B: not clean"

    The shipping code is not a clean-room reimplementation of `patch.diff`. It **is** `patch.diff`,
    adopted verbatim 70 minutes after it appeared, with one hostile change removed and one device-ID
    branch added. Derivability in principle is not derivation in fact, and the clean-room rule as
    several participants read it ("it is dirty, 100%") barred use of the artifact regardless of
    whether the information in it was independently obtainable. The material was purged rather than
    adjudicated, and the tool adopted the code anyway.

**What would settle it.** Nothing in the available material. The two private Driver Modification
Guides would establish whether `patch.diff` is genuinely the private group's code, and a statement
from the adopting maintainer would establish whether the code was copied or convergently written.
Neither exists in the source set.

!!! question "Open problem"
    A narrower, tractable version of the same question: are patches `0004` (BAR0 PRAMIN clamp) and
    `0005` (CE scrub workarounds) original to `cmpunlocker`, or were they in the private Guides too?
    Their content is byte-identical between `patch.diff` and `cmpunlocker`, so they came in together,
    but the community summaries of `patch.diff` describe only the signature hijack, PLM opens,
    register pokes, signature rebuild, `fb_length` spoof and the late-PMA extension. They do not
    mention the PRAMIN clamp or the CE scrub workarounds. Only the Guides would settle it.

---

## The academic paper and its disclosure stance

The preprint is the effort's single designated clean input and its methodological foundation. Its
abstract states that the CMP 170HX is "the same die as a flagship A100 but is fuse-crippled on three
commercial axes: SM math rate (throttled to 1/32), memory capacity (10 GB instead of 80 GB), and PCIe
link (Gen1 instead of Gen4)", that "all three caps are soft", and gives headline gains of "roughly
31-62x compute, 8x capacity, 2x link". It is a different paper from `arXiv:2505.03782`, which it
cites as reference [13].

The authors deliberately declined a pre-publication embargo. Section 10 records that the work was
lab-only on a single card, with no resale, no persistent silicon change, no extracted signing key and
no forged signature, and that the card was restored to native configuration after measurement. The
vendor's product-security team was notified **concurrently with publication** rather than in advance.
The stated reasoning, recorded here as what the authors argued and not as an endorsement:

> Coordinated disclosure assumes the vendor's remedy protects the user, which does not hold in an
> inverted threat model where the defender is the device and the adversary is its owner. A private
> embargo window would let the vendor burn the relevant anti-rollback fuses on already-shipped
> hardware, permanently removing that capability from the very users this work concerns, before those
> users could learn of it or act.

The paper also describes a static checker built by its authors over the booter instruction stream: it
lifts DMA-as-copy summaries into an IR, treats DMA as a taint source, applies a bounded-write check
at DMA sinks (`L <= S - o`), and escalates on link-map-aware layout adjacency. Run as a differential
gate it flags the open-kernel-era booter's signature-read transfer as its single unbounded sink and
passes the older booter family with no false positives. Confidence: **medium**. The checker is not
published in the archived material and no independent party has reproduced it.

Practical footnote for implementers: the paper's "3-4 BAR0 value changes" framing misled every
independent reproducer. The three or four writes are trivial; the whole difficulty is opening the
four PLMs first. See [privilege level masks](../unlock/privilege-level-masks.md).

---

## A downstream legal event

**NVIDIA issued a DMCA takedown against at least one `cmpunlocker` fork on 2026-07-17**, taking that
repository offline. The recipient stated the notice came from NVIDIA directly and stopped public work
on the project. Others speculated it was automated filter-triggered enforcement and noted that many
forks already existed; advice circulated to rename and rewrite forks. Confidence: **medium**. The
report is first-hand and the repository was observably down, but no takedown document is in the source
set. Nothing here is legal advice, and this wiki takes no position on the merits.

---

## Provenance hygiene for readers of this wiki

Three cautions that follow directly from the record above.

!!! danger "Do not cite the project's `docs` branch"
    `docs/ARCHITECTURE.md` states that `cmpunlocker` writes `0xffffffff` to both SS0 and SS1. The
    shipping patch writes `0x0082381c = 0x88888888` and `0x00823820 = 0x00000008`. The same branch
    invents acronym expansions found nowhere in the code or the transcripts (SS as "Suspension
    State", PLM as "Program Logic Modules", PMM as "Permute Mask Model", LMR as "LM (Local Memory)
    Request register", PMA as "Power Management Array"), asserts a nonexistent
    `SEC2_DEBUG: Executing unlock sequence...` log line, and instructs users to run
    `sudo ./uninstall.sh --yes` when the shipping script is `remove.sh`. It is seven commits and it
    is not authoritative.

!!! warning "The most-circulated architecture notes are self-rated at about 10 percent proven"
    Their author posted them with the caveat: "I do hold some notes. I try to double-check each
    statement, but this work can not be given to LLMs, so it is goes REALLY slow. This is what I have
    now. I do not state that this information is accurate, I would say, just ~10% has reliable
    proofs/sources." A parallel warning was given to anyone attempting a consolidated writeup: "most
    of things known about throttling mechanism are based on hypotheses and some experiments that do
    not contradict them... if you simply collect all points mentioned in chat you will likely get
    many wrong conclusions and it will get your llm insane." The three sources named as reliable
    priming material were the Zenodo paper, the public GA100 fuse reference table, and the annotated
    `booter_load` assembly. Attach this caveat to the architecture notes specifically, not to the
    register dumps or the disassembly, which are demonstrably better supported.

!!! note "Superseded"
    The widely circulated Booter Load overview document was LLM-generated from the disassembly, and
    the poster said so at the time: "I fed asm to claude and asked to describe/comment what is
    happening. Here is output, I have no idea what part of it is hallucinated." It was superseded by
    hand verification: an annotated `.fuc5` listing with per-function banners, then a v2 with every
    `lcall` carrying an inline comment naming the callee, then an immutable backup copy re-posted on
    2026-07-18 so that search sessions could not accidentally edit it. Verify anything from the
    overview against the annotated listing, which preserves the original instruction lines
    byte-for-byte.

Function names used across the project are inferred from behaviour, not read from a symbol table: the
binary has no symbols. One pair is named inconsistently between documents. `0xd66` and `0xccb` are
`regtable_reverse_lookup` and `regtable_rw_indexed` in the LLM overview, but ACR mutex acquire and
release in the ROP writeup. The code supports the mutex reading, and the shipping chain places
`0x00000ccb` at `D[0xFFF4]` immediately before its clean-exit `0x00007f2f`, so the mutex reading is
the one the shipping code relies on.

---

## Dated artifact index

Everything on this page that carries a decoded timestamp, in order.

| Date and time (UTC) | Artifact or event |
|---|---|
| 2026-05-05 / 2026-05-07 | Two physical CMP 170HX 10 GB cards probed (120 registers each) |
| 2026-05-31 | Drive A100 32 GB (PG199) probed; the 15-card fuse reference table is complete |
| 2026-06-26 | The Canary preprint circulated in the unlocker server |
| 2026-06-27 | Clean-room rule set stated as channel policy |
| 2026-06-30 | Public AES-128-ECB test key and `rijndael-tool.zip` published in-channel |
| 2026-07-01T12:40:37Z | Raw debug booter disassembly posted (545,149 B) |
| 2026-07-02 | Debug-versus-production equivalence settled; register provenance standard accepted |
| 2026-07-03T17:12:52Z | Annotated disassembly posted |
| 2026-07-09T03:03:21Z | Annotated disassembly v2 posted (607,702 B, 11,875 lines) |
| 2026-07-10T13:40:14Z | Register Gadget Atlas posted |
| 2026-07-14T21:47:02-07:00 | `cmpunlocker` initial commit `9b9fb2f`, carrying the frame-grid constants |
| 2026-07-15T18:48:10Z | `ROP_CHAINS_1180f8` writeup, documenting `+0x18 DMEM per write` |
| 2026-07-16T06:07:12Z | The paper posted into the clean-room server as `main.pdf` |
| 2026-07-17 | DMCA takedown against at least one fork |
| 2026-07-18T18:01:15Z | `patch.diff` posted |
| 2026-07-18T18:26:26Z | Shipping patch-set file mtimes |
| 2026-07-18T18:40:16Z | LAPSUS$ provenance assessment posted |
| 2026-07-18T19:11:01Z | `06fabf2 "WORKING MEMORY UNLOCK"` |
| 2026-07-18T21:46:49Z | `e4026e5 "Memory working!"` merged to `master` |

---

## See also

- [Project timeline](timeline.md), the full dated sequence including the technical milestones
- [Tool lineage](tool-lineage.md), which tools superseded which, and which are dead
- [Dead ends](dead-ends.md), approaches that were tried and refuted
- [The ROP chain](../unlock/rop-chain.md), the payload whose provenance is the subject of this page
- [The six driver patches](../unlock/driver-patches.md)
- [Falcon and the Booter](../unlock/falcon-and-booter.md)
- [Fuses and OTP](../hardware/fuses-and-otp.md), the 120-register differential corpus
- [Methodology](../appendix/methodology.md) and [external sources](../appendix/external-sources.md)
