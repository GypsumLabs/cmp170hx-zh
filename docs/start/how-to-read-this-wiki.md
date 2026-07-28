# How to read this wiki

**What this page covers.** The conventions this wiki uses to separate settled fact from
active speculation, what each admonition box means, how claims were gathered and
adjudicated, why no individual is ever named, and what the phrase "as of 2026-07-28" is
doing at the bottom of pages.

Read this once. Everything else on the site assumes you have.

The headline: **plain prose means the claim is confirmed.** If a statement is not wrapped in
a coloured box and does not carry an inline hedge, it has been checked against source code
or against multiple independent measurements. Anything less certain than that is marked, and
the marking tells you exactly how much less certain.

---

## The confidence system

### Level 1: plain prose

Unmarked prose is a confirmed fact. In practice that means one of the following was true
during adjudication:

- The claim was **settled from source code**. The shipping `cmpunlocker` tree and 12
  unreleased branch snapshots were read directly. Where documentation and code disagreed,
  the code won, every time, and the correction is stated in the text.
- The claim was **measured on hardware by two or more independent parties**, with the
  measurements agreeing.
- The claim is **arithmetic** derived from values in the first two categories, with the
  derivation shown.

### Level 2: inline hedges

Some facts rest on a single report from a single machine. Those are never presented as
settled, but they are also not hidden, because a single good measurement is far more useful
than silence. They are hedged in the sentence itself:

> "one tester reported ...", "observed once, on 2026-07-26, on one rig", "a single
> capture exists", "medium confidence".

When you see that phrasing, treat the number as a data point, not a specification. It has
not been reproduced.

### Level 3: admonitions

Four box types carry specific meanings. They are used sparingly and consistently.

!!! warning "Experimental"

    The material inside is on an unreleased branch, or rests on a single report, or both.
    It is not part of the shipping unlocker. PCIe Gen2, the 80 GB memory profile, the MIG
    enable and the multi-card handling all lived here at various times. Expect it to work
    on some hosts and not others, and expect the details to change.

!!! danger

    Following the instructions inside can destroy hardware or lose data. This box is
    reserved for physical and irreversible risk: connector mis-mating, VBIOS flashing,
    thermal runaway, soldering, and allocations that fault the card. It is not used for
    "this might not work".

!!! question "Open problem"

    Nobody knows. The box states what is known, what has been tried, why the investigation
    stalled, and what one experiment would settle it. Every open item is collected and ranked
    by tractability on [Open questions](../frontier/open-questions.md) and tracked on the
    [Status board](../frontier/status-board.md). Thirteen of them can be settled by neither
    the documents nor the source trees.

!!! note "Superseded"

    The approach described was real, worked (or nearly worked), and has since been replaced.
    Every superseded box points at what replaced it. These are kept because the reasoning is
    reusable and because abandoned approaches get rediscovered otherwise. The on-disk GSP
    firmware patching route, the two-load clear-WPR2 architecture, the standalone
    `cmpretrain.service` and FLR-based recovery are all here.

### What "unknown" means

If a number is not known, this wiki says it is not known. It never fills the gap with a
plausible figure. A page that says "no CFM, static-pressure or fin-pitch figure for the stock
heatsink exists in any source" is more useful than one that quotes an invented number, and
the distinction matters more on this hardware than most, because several of the numbers in
public circulation are wrong.

---

## Where the facts came from

### The corpus

The underlying material is a mined archive of the community effort that produced the unlock:
project chat channels (clean-room and post-release), long-form write-ups, raw `dmesg`
captures, register dumps, screenshots, published tooling source, external references such as
teardowns and fuse tables, and the shipping and branch source trees themselves. Individual
claims in the working documents carry citation tags of the form
`[artifacts__cleanroom_writeups#082]` or `[chat__unlocker__testing_general__01#039]`, plus a
confidence rating and the date the claim was established.

### The domain documents

Raw claims were adjudicated into **24 domain documents**, one per subject area (memory in
four parts, firmware in four, compute in two, driver in two, PCIe in two, plus performance,
thermal and power, VBIOS, tooling, provenance, troubleshooting, mods, NVLink, LLM inference
and a miscellany). Each document separates canonical facts from dead ends, open questions,
unresolved contradictions, corrections to the record, and a table of measured values.

Two of those sections deserve special mention because they are unusual and useful:

- **Dead ends.** Every failed hypothesis, with why it was plausible and what disproved it.
  Twenty-five in troubleshooting alone. These exist so the same wrong idea is not
  re-litigated. They surface on [Dead ends](../history/dead-ends.md).
- **Corrections to the record.** Places where project documentation, a public guide or a
  widely repeated claim is provably wrong against the source. Several of these are still
  circulating in third-party forks and AI-generated guides.

### The authority ranking

When sources conflict, this order decides:

| Rank | Source | Example |
|---|---|---|
| 1 | Shipping source code, read directly | `plmTable[]` in `0001-sec2-postbl-plm-ss-cfg.patch` |
| 2 | Branch source snapshots | `0007-pcie-gen2.patch` on `Gen2` |
| 3 | Direct measurement with a posted capture | a verbatim `dmesg` block, a register readback |
| 4 | First-hand report without a capture | "one tester reported" |
| 5 | Project documentation | `README.md`, `docs/ARCHITECTURE.md` |
| 6 | Reasoned inference | explicitly labelled as such |

Project documentation ranks **below** measurement deliberately. The `docs` branch diverged
from the code: it invents acronym expansions, quotes the wrong SS0/SS1 values, references a
script that does not exist, and over-generalises the PLM readback rule. See the
[Glossary](glossary.md#corrected-expansions-do-not-repeat-these).

### The cross-check

A final pass compared every number that appears in more than one domain document against
every other occurrence, re-deriving code-settleable disputes from the source trees rather
than quoting the documents. It found **14 conflicts: 8 settled from code, 6 weighed on
evidence.** The result is a canonical value table that this wiki treats as authoritative.
Where a page quotes a number that was disputed, it quotes the canonical value and, where the
dispute is instructive, says what the disagreement was.

A worked example of why this matters: the archived `80` branch carries `lmr: "0x0000028B"` in
`common/constants.yaml`, and several documents repeat that as the value the branch programs.
It is not. `build.sh` never reads `constants.yaml`; the build sets `0x0000028A`, the installer
prints `0x0000028A`, and patch `0001` bakes `0x0000028A`. Every tester who ran that branch
programmed a three-way-inconsistent geometry, which is itself the leading suspect for the
instability. Only reading the code exposes that.

---

## Why nobody is named

No Discord handle, display name, real name or user ID appears anywhere on this site. Where
attribution is load-bearing to the claim, this wiki writes "a researcher", "one tester",
"two independent testers", "the maintainers", or "the tool author". Gendered pronouns are not
used for anyone; they/them is used throughout.

There are three reasons, and only the first is about politeness:

1. **The work was done under clean-room rules.** The governing standard was that no vendor
   secrets be discussed, that knowledge be admissible only where the same information is
   demonstrably derivable from public sources, and that posting leaked material was a
   bannable offence. An earlier server was destroyed because it may have contained leaked
   vendor material. Attribution invites exactly the kind of provenance argument those rules
   were designed to avoid.
2. **There is live legal exposure.** A takedown notice was reported against at least one
   public fork on 2026-07-17, and the repository was observably offline. The report is
   first-hand but no takedown document is in the source set, so this one is medium
   confidence. Naming contributors adds risk to individuals without adding a single fact to
   the record.
3. **Attribution is not evidence.** What matters for a technical claim is the capture, the
   register readback or the line of code, not who posted it. Removing names forces every
   claim to stand on its own basis, which is the correct outcome.

Community history is documented in [Clean room and provenance](../history/clean-room-and-provenance.md)
without personalities. Prices, sellers, procurement and community disputes are out of scope
entirely.

---

## What "as of 2026-07-28" means

That is the **adjudication date**: the day the corpus was frozen, the source trees were read,
and the cross-check was run. It is not the date the hardware was released, nor the date any
individual claim was established.

Read it as "through the end of 2026-07-27". The capture happened just after midnight UTC, so
2026-07-28 itself contributes only three off-topic messages and no code. See
[methodology](../appendix/methodology.md).

Three separate timelines run underneath it:

| Timeline | Range | What it covers |
|---|---|---|
| Hardware and board-repair record | from 2023-10-25 | Teardowns, die markings, power-rail repair, the A100 board comparison |
| VBIOS and fuse characterisation | from 2024-07, concentrated 2026-03 to 2026-05 | ROM diffs, fuse tables, cross-flash attempts |
| The unlock effort | 2026-06-27 to 2026-07-28 | Clean-room exploit work, then the shipping in-driver patch set |

Individual facts in the domain documents carry their own "established" date, and several
carry a second date where they were corrected or code-confirmed during the 2026-07-28 pass.
Where a date is significant to interpreting a claim, this wiki states it inline.

**What the date implies for you, practically:**

- The shipping unlocker as described here accepts exactly nvidia-open `610.43.03` and
  `610.43.02`. If you are reading this after a newer driver has shipped, that whitelist has
  either been extended or the approach has moved. Check
  [Driver versions](../procedures/driver-versions.md).
- Anything marked Experimental was still moving on the freeze date. The PCIe Gen2 hardcoded
  BDF bug, for instance, was root-caused on 2026-07-27 and fixed on one branch the same day,
  with several open reports never re-tested against the fix.
- The open-question list is a snapshot. Some of those items need one boot test to close.
- Nothing here has been re-verified against hardware after the freeze date.

---

## Reading a typical page

Every substantive page follows the same shape:

1. **What this page covers**, one short paragraph, plus the key result stated in the first
   two paragraphs. Nothing important is buried.
2. Substance, densest first. Register maps and measured values are in tables. Commands, code
   and log output are in fenced blocks with a language tag, and are reproduced verbatim
   including addresses and error codes.
3. Cross-links to the pages that go deeper. Links are relative and always end in `.md`.
4. Open problems and superseded material, boxed.

Two structural conventions worth knowing:

- **Speed and width are never conflated.** PCIe generation (Gen1 to Gen2) is a
  driver-side software change that modifies no firmware image. Link width (x4 to x16)
  requires hand-soldering 24 missing 0402 capacitors. They are separate achievements with
  separate evidence, and no page mixes them. See [PCIe Gen2](../unlock/pcie-gen2.md) and
  [Physical mods](../operations/physical-mods.md).
- **The two SKUs are never mixed.** The 8 GB card (`10de:20c2`) unlocks to **64 GB**. The
  10 GB card (`10de:2082`) unlocks to **40 GB**. The 80 GB configuration for 10 GB cards was
  attempted and found unusable above roughly 40 GB. If a page seems to be talking about your
  card and quotes the other capacity, you are reading about the other SKU. Start at
  [Identify your card](identify-your-card.md).

---

## If you find an error

Every claim on this site is traceable to a domain document, a citation tag and a date. The
most valuable corrections are the ones that come with a capture: a `dmesg` block, a register
readback with `lspci -nn` in the same paste, or a byte comparison. Several of the open
questions listed on [Open questions](../frontier/open-questions.md) would close with a
single such capture from a single card.

---

## See also

- [Glossary](glossary.md) for every acronym and term, including the ones commonly expanded
  wrongly.
- [Risks](risks.md) for what can go wrong before you start.
- [Methodology](../appendix/methodology.md) for the full adjudication procedure.
