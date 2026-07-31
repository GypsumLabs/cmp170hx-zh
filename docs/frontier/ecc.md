# ECC: fused off, and the `ecc` branch is empty

**What this page covers.** The state of error-correcting memory on the CMP 170HX: what is
actually known (very little, and almost all of it negative), the one register-level attack that
was attempted and why it failed on two independent layers, why the branch named `ecc` contains
no ECC code at all, what has never been measured, and what would have to happen for the question
to become answerable.

**The headline: ECC is off, there is no known lever, and there is no telemetry.** The card
reports no ECC state, no correctable-error counters and no volatile/aggregate ECC page. Every
capacity and stability claim about this hardware, including the
[64 GB and 40 GB unlocks](../unlock/memory-geometry.md), is made on non-ECC memory.

> [!NOTE]
> **Open problem**
>
> ECC was named as the candidate target immediately after PCIe Gen 2, and then nothing
> happened. Beyond reading `OPT_ECC_EN` across the comparison cohort and dumping the four
> `FEATURE_OVERRIDE` ECC words, **nothing has been tried.** The prior question, whether the HBM
> stacks carry ECC provisioning at all, has one partial answer rather than none: the A100
> capacity differential below reads as ECC being a slice of the same stacks, not separate
> storage. That was stated in-channel and never checked against a datasheet.

---

## Status at a glance

| Claim | Status | Basis |
|---|---|---|
| ECC is disabled on the CMP 170HX | Confirmed | Every published spec table and every card report |
| The disable is fuse/POR-latched, not a runtime setting | Confirmed | `0x00823814` readout is POR/fuse-latched; runtime overrides do not move it |
| A `FEAT_OVR`-style ECC unlock works | **Refuted** | Two dedicated attempt scripts, two independent failure layers |
| The `ecc` branch implements ECC | **False** | Single commit, "Fixed dual geometry support", no ECC code |
| ECC is implemented in the HBM stacks | **Partly answered** | One first-hand reading of the fuse table: on A100s each stack's per-FBPA `CSTATUS_RAMAMOUNT` reads `0x7ff` / `0xfff` against the consumer `0x800` / `0x1000`, that is, ECC as in-band capacity reservation inside the same HBM2 stacks. Never confirmed against a datasheet |
| `OPT_ECC_EN` (`0x00820228`) reads `0x00000000` on a 170HX | Confirmed | Two physical 170HX units; `0x00000001` on every A100-class comparison part |

---

## The register block

ECC on GA100 is described by five registers inside the feature-override block at
`0x00823800`-`0x0082382C`, the same block that carries the working
[compute unlock](../unlock/compute-throttle.md). That adjacency is exactly why an ECC unlock
looked reachable.

| Register | Address | 170HX | A100 80 GB | Notes |
|---|---|---|---|---|
| `FEAT_OVR_ECC_PLM` | `0x00823800` | `0xffffff8f` cold | not captured | The privilege-level mask gating the three override words. Openable by the HS-ROP, and inert once opened |
| `FEAT_OVR_ECC` | `0x0082380C` | `0x00888888` | `0x00000101` | Per-unit ECC: SM_LRF / L1 / LTC / DRAM / CBU |
| `FEAT_OVR_ECC_1` | `0x00823810` | `0x002AAAAA` | `0x00100105` | icache / FECS / GPCCS / PMU / HUBMMU |
| `FEAT_OVR_ECC_2` | `0x0082382C` | `0x0000000A` | not captured | Reads the same stock and unlocked |
| `FEAT_READOUT_0` | `0x00823814` | `0x00000233` | `0xef8ff100` | **The ECC-enable readout. POR/fuse-latched.** Reads the same stock and unlocked |

Confidence on those values: medium. They come from PLM range scans and post-unlock probes rather
than from a repeated multi-card sweep, and the A100 comparison column is a single card.

> [!WARNING]
> **Do not confuse `0x00823800` with `0x00823804`**
>
> `FEAT_OVR_ECC_PLM` at `0x00823800` and `FEAT_OVR_PLM` at `0x00823804` are distinct
> registers. The shipping unlock opens `0x00823804` (stock `0xffffff8f`, opened to
> `0xffffffff`) to reach SS0 and SS1. `0x00823800` also reads `0xffffff8f` stock, which makes
> the two easy to mix up in a dump. The Gen2-family branches open `0x00823800` too, but only
> as one of eighteen PLM opens in the PCIe sequence, not for any ECC purpose.

---

## The one attempt, and its two failure layers

**Hypothesis.** Opening `FEAT_OVR_ECC_PLM` (`0x823800`), which gates `FEAT_OVR_ECC`
(`0x82380C`), `FEAT_OVR_ECC_1` (`0x823810`) and `FEAT_OVR_ECC_2` (`0x82382C`), would let ECC be
enabled at runtime, exactly the way `FEAT_OVR_PLM` plus SS0/SS1 defeats the compute throttle.

**Why it was plausible.** The PLM reads `0xffffff8f` cold on the 170HX, meaning it is a normal
L3-gated mask rather than something exotic; the HS-ROP genuinely can open it; and the master
override kill fuse `FUSE_FEAT_OVR_DIS` at `0x008203F0` reads `0x00000000` on every card probed,
so overrides as a class are not permanently locked out. That last fact is the reason the entire
compute and memory unlock works at all.

**What happened.** Multiple dedicated attempts, `fire_ecc_driverless_test.sh` and
`fire_ecc_unlock.sh`, all failed. Two independent layers were identified and written up in
`ecc-unlock-dead.md` on 2026-07-16:

1. **The overrides are not always-on.** `FEAT_OVR_ECC` is not in the always-on (AON) island, so
   any override written to it reverts on function-level reset. This is the same asymmetry that
   makes the memory geometry non-persistent: SS0, SS1 and `0x00823804` survive FLR, while
   everything else in the geometry and ECC path does not. See
   [privilege-level masks](../unlock/privilege-level-masks.md).
2. **The readout is POR-latched, which is fatal.** `0x00823814` is latched at power-on from the
   fuse, so **no runtime override changes the effective ECC state**. Even a persistent override
   would be writing to something the rest of the chip has already stopped consulting.

Layer 2 is the one that closes the route. It is not a "we could not make the write stick"
failure; it is a "the write is not the thing that decides" failure.

---

## The `ecc` branch contains no ECC code

The branch is named `ecc`. It has a single commit, `bb4d669 Fixed dual geometry support`. Its
complete diff against `master`:

- the deleted pull-request template,
- comment blocks in `build.sh`, `install.sh` and `remove.sh`,
- `# 64 GiB` and `# 40 GiB` annotations in `constants.yaml`,
- one README requirements line,
- a new `requirements.txt` containing `pyyaml>=5.1` and `pytest>=7.0`.

**No ECC register, no ECC enable path, no ECC test exists in the tree.** The name records an
intention, not work.

Two related corrections to the record:

For completeness: the `PG199` branch snapshot is byte-identical to the `ecc` snapshot except for
`_COMMITS.txt` (`ecc` lists `bb4d669`; `PG199`'s is zero bytes). Their `_DIFF_vs_master.patch`
files are identical byte for byte. Both are placeholders. See
[driver patches](../unlock/driver-patches.md) for the branch inventory.

---

## What has never been measured

This is the honest part of the page, and it is longer than the part with results.

- **A decode of the A100 differential.** The single-card A100 dump behind the table above covers
  three of the five ECC-related words (`0x0082380C`, `0x00823810` and `0x00823814`) and does not
  carry `0x00823800` or `0x0082382C`. A wider side-by-side does exist: the 15-card fuse reference
  table gives the whole `0x00823800`-`0x0082382C` block for both 170HX units against A100 SXM4
  40G, A100 PCIe 40G, A100 PCIe 80G and Drive A100, all of which read `FUSE_ECC_EN` = `1`. What
  has never been produced is a field-level decode of that differential, and the two independent
  A100 80 GB dumps do not agree with each other (`0x0082380C` `0x00000101` versus `0x00110111`;
  `0x00823810` `0x00100105` versus `0x00104104`), so the A100 side is not settled either.
- **Whether ECC is implemented in the HBM stacks themselves.** If it is a memory-vendor QA and
  binning property rather than a firmware toggle, there is nothing to unlock. The corpus does not
  settle this, but it does contain one substantive reading: "On GA100 cards, ECC is a feature of
  the HBM2 stack. On the 170HX, ECC is fused off can likely not be enabled", supported by the
  per-FBPA `CSTATUS_RAMAMOUNT` differential in the 15-card fuse table, where A100 parts read
  `0x07ff` and `0x0fff` for 8 GB and 16 GB stacks against `0x0800` and `0x1000` on consumer
  cards. That pattern reads as ECC reserving part of the same stack's addressable range rather
  than living in extra dedicated storage, which is also what killed the "a whole stack is
  reserved for ECC" theory. It is one participant's inference from register values, with no
  datasheet behind it, and the exact fraction reserved was never agreed. Note the HBM density
  mode register `FBPA_MRS_8`
  (`0x009A0320`) reads the identical `0x00200000` on all 15 cards including a 10 GB CMP, a 40 GB
  A100 and an 80 GB A100, so the stacks are not being told they are smaller than they are, but
  that says nothing about ECC provisioning.
- **Whether ECC would even be desirable at the unlocked geometry.** No before/after error-rate
  data exists on an unlocked card.

---

## The origin story that is not evidence

The fuse evidence leans toward the defect reading rather than deliberate segmentation, at
least on the memory side: on one 10 GB card, `FBP_DEFECTIVE` (`0x8205CC`) and `FBP_DISABLE` (`0x820364`)
both read `0x840`, that is, the disabled-but-not-defective set is empty, and the card is
genuinely dead on those partitions. One community dump shows a non-empty delta
(`FBP_DISABLE` = `0x852` against `FBP_DEFECTIVE` = `0x840`), so per-card variation is real.

---

## Practical consequences of running without ECC

No ECC means no correctable-error counters, no uncorrectable-error reporting, no row-remapping
telemetry and no `nvidia-smi` ECC page to consult when a workload misbehaves. The practical
effects recorded in the corpus:

- **Diagnosis is harder.** Without ECC counters, the only way to establish that a memory
  configuration is sound is a write/read-back alias ("fold") test rather than a reported size.
  This rule was adopted after a reported 79.4 GiB folded above 40 GiB and a reported 4 GiB
  turned out to be a tooling bug. It applies directly to
  [the 80 GB attempt](80gb.md).
- **Row remapping.** `FEAT_OVR_ROW_REMAP` at `0x00823824` reads `0x00000000` on both 170HX units
  (confidence: high; also `0` on A100 SXM4 40G, A100 PCIe 80G, A10 and Drive A100, versus
  `0x00000001` on A100 PCIe 40G, A5000, A6000 and RTX 30). The row remapper is inactive. One
  medium-confidence source reports `0x00000001` stock; it is outweighed. Its candidate PLM
  `0x00823b00` was write-tested and recorded `PLM=0xffffffff(AON=YES)` post-FLR, placing it in
  the durable class alongside `0x823804` and `0x823800`. Nobody chased what the row remapper
  does on a card with no ECC.
- **Marketplace listing.** Whether the absence of ECC blocks rental-marketplace listing is
  unresolved. Reasons given for cards not being listable include no ECC, wrong PCI IDs and poor
  bandwidth. The counter-argument is that 2080 Ti 22 GB mods and consumer 30/40/50-series cards
  have no ECC and are already listed. On the technical merits, the position offered was that
  "neural nets are largely very robust against bit flips and it's still going to be a rare
  occurrence"; one owner reported an A100 with a full row of faulty memory that processed LLM
  inference fine while glitching badly in graphics. One marketplace stated it had no timeline
  for enabling CMP cards; other platforms did list them. What would settle it: a marketplace
  stating its actual blocking criterion.

---

## What would advance this

Ranked most tractable first. All are unstarted.

1. **Decode the `0x00823800`-`0x0082382C` differential that already exists.**
   The 15-card fuse reference table already holds the whole block for both 170HX units and for
   A100 SXM4 40G, A100 PCIe 40G, A100 PCIe 80G and Drive A100; what is missing is a mapping of
   those dwords to fields. Doing that would also bear on the open question about why
   `FEATURE_OVERRIDE_QUADRO`
   (`0x00823808`) differs across all three known dumps (stock 170HX `0x00100183`, unlocked 170HX
   `0x00000081`, A100 80 GB `0x01000282`).
2. **Establish whether the HBM stacks carry ECC provisioning at all.** The IEEE 1500 HBM debug
   bridge is live on this card (`I1500_INSTR` `0x009a3cb4`, `MODE` `0x009a3cb8`, `DATA`
   `0x009a3cbc`, `SHADOW_WIR` `0x009a3cc0`, `SHADOW_WDR` `0x009a3cc4`, `STATUS` `0x009a3cc8`)
   and is the only working route to HBM stack identity, because `FBPA_VEND_ID_C0`/`C1`
   (`0x009A0838`/`0x009A083C`) read `0x00000000` on all 15 cards. Nobody has decoded the
   `SHADOW_WDR` contents into a vendor and density, let alone an ECC capability. The suggested
   next step is to shift in the standard IEEE 1500 `DEVICE_ID` WIR opcode rather than reading
   whatever instruction was left latched.
3. **Find a consumer of `0x00823814` that is not POR-latched.** This is the only route that
   could revive the register attack, and no candidate has been named.

> [!CAUTION]
> **Do not treat an unlocked card as ECC-protected**
>
> Nothing on this page describes a working ECC path. An unlocked 170HX running 40 GB or 64 GB
> is running unprotected HBM at a geometry the factory never validated. For workloads where a
> silent bit flip is unacceptable, this is not the right hardware.

---

## Measured values

| Quantity | Value | Conditions | Confidence |
|---|---|---|---|
| `FEAT_OVR_ECC_PLM` `0x00823800` | `0xffffff8f` cold | 170HX; openable by HS-ROP but inert | high |
| `FEATURE_OVERRIDE_ECC` `0x0082380C` | `0x00888888` (170HX) / `0x00000101` (A100 80 GB) | per-unit ECC: SM_LRF, L1, LTC, DRAM, CBU | medium |
| `FEATURE_OVERRIDE_ECC_1` `0x00823810` | `0x002AAAAA` (170HX) / `0x00100105` (A100 80 GB) | icache, FECS, GPCCS, PMU, HUBMMU | medium |
| `FEATURE_OVERRIDE_ECC_2` `0x0082382C` | `0x0000000A` | 170HX, stock and unlocked | medium |
| `FEAT_READOUT_0` `0x00823814` | `0x00000233` (170HX) / `0xef8ff100` (A100 80 GB) | stock and unlocked identical; POR/fuse-latched | medium |
| `FUSE_FEAT_OVR_DIS` `0x008203F0` | `0x00000000` | all cards; master override kill **not** blown | high |
| `OPT_ECC_EN` `0x00820228` | `0x00000000` on both 170HX units; `0x00000001` on A100 SXM4 40G, A100 PCIe 40G/80G, A10, A5000, A6000 and Drive A100 | two physical 170HX units, six independent probe reports | high |
| `FEAT_OVR_ROW_REMAP` `0x00823824` | `0x00000000` on both 170HX units | also `0` on A100 SXM4 40G, A100 PCIe 80G, A10 and Drive A100; `0x00000001` on A100 PCIe 40G, A5000, A6000 and RTX 30 | high |
| `0x00823b00` (row-remapper PLM candidate) post-FLR | `0xffffffff`, AON = YES | in-HS geometry sweep; did not make geometry persist | high |
| `FBPA_MRS_8` `0x009A0320` (MR8 Density) | `0x00200000` | all 15 cards including 10 GB CMP, A100 40 GB, A100 80 GB | high |
| `FBPA_VEND_ID_C0` / `C1` `0x009A0838` / `0x083C` | `0x00000000` | all 15 cards; identity must come from IEEE 1500 instead | high |
| ECC code in shipping `master` | none | whole-tree read | high |
| ECC code in the `ecc` branch | none | single commit, "Fixed dual geometry support" | high |

---

## See also

- [Memory subsystem](../hardware/memory-subsystem.md) for HBM organisation and floorsweep
- [Memory geometry unlock](../unlock/memory-geometry.md) for what does work
- [Compute throttle](../unlock/compute-throttle.md) for the `FEAT_OVR` route that succeeds
- [Privilege-level masks](../unlock/privilege-level-masks.md) for the AON versus non-AON split
- [The 80 GB attempt](80gb.md) for the memory-stress data closest to an ECC question
- [Fuses and OTP](../hardware/fuses-and-otp.md), [Status board](status-board.md),
  [Open questions](open-questions.md)
