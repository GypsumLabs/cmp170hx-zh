# Methodology

**What this page covers.** How this wiki was actually built: what the source material is, how
roughly 2,400 raw claims were reduced to a canonical fact set, which source beats which when they
disagree, what the confidence markers on every other page really mean, why nobody is named, and,
at the end and in detail, what this method cannot guarantee. Read it if you are about to act on
something you found here.

The short version: **this wiki is a synthesis of a five-week technical conversation, adjudicated
against the source code that conversation produced.** Where a claim is expressible in code, the
code was read and the code decided, even when the chat consensus said otherwise, and it repeatedly
did. Where a claim is a hardware measurement, no such tiebreaker exists, and the wiki falls back on
counting independent reports. That asymmetry is the single most important thing to understand
about how much weight to put on any given sentence: **the firmware and driver material is close to
verifiable; the electrical, thermal and performance material is a small pile of field reports.**

---

## 1. The corpus

Everything here derives from a frozen snapshot of primary material, captured **just after midnight
UTC on 2026-07-28**. That granularity matters: substantive coverage ends **2026-07-27 at 23:59**,
and only three messages in the whole archive fall on 2026-07-28, at 00:00, 00:00 and 00:01, all of
them wiki-link and research-resource chatter. Read "2026-07-28" as "through the end of 2026-07-27",
not as a full day of coverage. Anything that happened later, including repository changes, is
outside the snapshot.

| Component | Extent | Notes |
|---|---|---|
| Chat archive | **26,123 messages**, **20 channels**, two public Discord servers, **2026-06-22 to 2026-07-28** | Split into 35 working chunks; 21 marked high priority (technical channels), 14 low (off-topic, welcome, procurement). The last substantive message is dated 2026-07-27 23:59 |
| File attachments | **1,121 files** archived | Fetched before their signed CDN URLs expired. 131 are text or code (disassembly listings, ROP payloads, probe scripts, register dumps, `dmesg` captures, long-form write-ups); the remainder are images, ROMs and binaries |
| Unlock tool source | **17 branch refs**, of which 13 full trees were read | Shipping `master` plus **12** unreleased branch snapshots. The refs `code-simplification`, `dual-geometry-fix`, `fix` and `v0.1` exist in the repository but were not snapshotted and were **not** analysed |
| Reference gists | 2 | The GA100 fuse and register reference table with `probe.sh`, and the GA100 VBIOS comparison table with its dump and parse scripts. Both were deleted after release; the archived copies are what this wiki used |
| External references | Teardown, papers, upstream driver, tooling | An independent 2023-10-25 teardown review predating all unlock work, the June 2026 Falcon stack-protection paper (Zenodo 20916112), arXiv:2505.03782, the NVIDIA open kernel modules, envytools and the Falcon tooling family |

The two servers play different roles and are weighted differently. The clean-room server (1,539 of
the extracted claims) is where the exploit was developed under rules that admitted exactly one
input document; it is dense with disassembly and register work. The post-release server (800
claims) is where the tool met other people's hardware; it is where nearly all the failure modes,
thermals and benchmarks come from, and it is much noisier. A further 59 claims come from external
documents.

Deliberately out of scope and stripped at ingest: prices, sellers, shipping, procurement, and
community disputes. See [external sources](external-sources.md) for the annotated bibliography
and [preserved artifacts](artifacts.md) for the file-level inventory.

---

## 2. The pipeline

Four passes, each one narrowing and each one leaving an audit trail.

**Pass 1: extraction.** Every chunk was read under a fixed brief and reduced to structured claim
records: a one-sentence falsifiable assertion, a dense technical detail field, a verbatim evidence
quote with attribution stripped, a date, a channel, a status and a confidence rating. This produced
**2,398 claims**. The brief supplied a small ground-truth table (the two SKUs, their geometry
values, the compute registers) so that early wrong guesses would be recorded as refuted rather than
propagated.

| Status | Count | Meaning |
|---|---|---|
| `confirmed` | 1,426 | Someone ran it and reported a concrete result, or it matches code, or it was independently reproduced |
| `likely` | 331 | Well-reasoned and unchallenged, but never directly demonstrated |
| `open-question` | 232 | Still unsolved |
| `refuted` | 182 | Later shown false, with the disproof recorded |
| `disputed` | 126 | Knowledgeable people disagreed and it was never settled |
| `superseded` | 101 | True of an earlier approach that a better method replaced |

Confidence was tracked separately: 1,534 high, 708 medium, 156 low.

**Pass 2: adjudication.** The claims were partitioned into 24 domains (memory in four parts,
firmware in four, compute, driver and PCIe in two each, plus performance, thermal and power, VBIOS,
tooling, provenance, troubleshooting, mods, NVLink, LLM inference and a miscellany) and each domain
was resolved against the authority ranking below into canonical facts, an evolution and
supersession section, dead ends, open questions, unresolved contradictions, and a table of measured
values. Output: about **1,458 canonical facts**, **507 recorded dead ends** and **266 open
questions**.

**Pass 3: cross-check.** Every quantity appearing in more than one domain document was compared
against every other occurrence, and every code-settleable dispute was **re-derived from the source
trees rather than quoted from the documents**. This found **14 conflicts: 8 settled from code, 6
weighed on evidence**. The result is a canonical value table that overrides the domain documents
wherever they disagree with it.

**Pass 4: writing.** Pages were written under a style brief that forbids inventing values, forbids
naming anyone, and requires the canonical value for any cross-referenced number. A scripted gate
then checks every published page against a list of **1,036 handles** seen in the corpus, resolves
every relative link, verifies navigation integrity, spot-checks the geometry and compute constants
for transcription errors, and flags style violations.

> [!WARNING]
> **Experimental**
>
> Passes 1 and 2 were carried out by language-model agents working to a fixed brief, not by hand.
> That is precisely why pass 3 exists and why it re-derives from source rather than trusting the
> documents: agents summarising a conversation reproduce the conversation's confident errors.
> Pass 3 caught 14 of those. It is not safe to assume it caught all of them.

---

## 3. The authority ranking

When two sources conflict, this order decides, top wins:

| Rank | Source | Why it ranks there |
|---|---|---|
| 1 | Shipping source code (`master`) | This is what actually runs on people's cards |
| 2 | Unreleased branch snapshots | Real code, but unmerged and sometimes internally inconsistent. Always labelled Experimental |
| 3 | Independently reproduced empirical results | The same measurement from two or more testers, or a posted capture |
| 4 | Single-tester empirical results | Useful, never treated as settled |
| 5 | Reasoned analysis by someone who understood the system | Labelled as inference |
| 6 | Speculation | Recorded only when notable and later resolved |

Project documentation is not on this list as a rank of its own. It sits below measurement, because
the project's own documentation branch is a known source of errors.

### Why chat consensus kept losing

A group of skilled people working fast will converge on a confident shared belief that is wrong in
a way nobody re-checks, because re-checking means reading a diff instead of reading a sentence. Two
worked examples, both of which changed what this wiki says:

**Example 1: the compute unlock values.** The project's `docs` branch states that both SM
speed-select registers are written `0xffffffff`. That reading circulated and was repeated. The
shipping patch `0001-sec2-postbl-plm-ss-cfg.patch` writes `SS0 0x0082381c = 0x88888888` and
`SS1 0x00823820 = 0x00000008`, and all 16 copies of that patch across `master` and every branch are
identical on this point. The documentation is simply wrong, and this wiki says so on
[compute throttle](../unlock/compute-throttle.md).

**Example 2: what the `80` branch programs.** Four independent working documents, following the
branch's own `common/constants.yaml` and its commit titled "Correct LMR for 80GB", reported that
the 80 GB attempt sets `LMR = 0x0000028B`. It does not. `build.sh` never reads `constants.yaml`;
`80/driver/build.sh` line 93 sets `LMR="0x0000028A"`, `80/install.sh` line 138 prints
`CFG1=0x02779000 LMR=0x0000028A`, and patch `0001` line 144 bakes `lmrValue = 0x0000028AU`. The
commit changed inert metadata only. Every tester who ran that branch therefore programmed a
three-way-inconsistent geometry, which is the leading suspect for the instability, and that
conclusion only exists because somebody read the file instead of the changelog. See
[the 80 GB question](../frontier/80gb.md).

Other rulings of the same kind, all re-derived during pass 3: a claim that no patch file on the
`80` branch differs from `master` (two lines differ); 24 reported patch byte sizes, all wrong
against `wc -c`; the count of unreleased branch *snapshots*, reported variously as thirteen and
fourteen (**12** were snapshotted, out of **16** unreleased refs, the other four being
`code-simplification`, `dual-geometry-fix`, `fix` and `v0.1`); the size of the Gen2 PLM table,
reported as one added entry (it adds five, for a total
of nine); and the README's claim that the unlock is gated on device ID `0x20C2` alone, when the
in-driver gate accepts `0x20C2` and `0x2082`.

### What code cannot settle

Six of the 14 conflicts were not code-settleable, because the quantity in dispute does not exist in
any source file. PCIe link width, bandwidth, clocks and thermals are in this category. Those were
weighed on evidence, and the honest outcome was usually to **lower** a confidence rating rather
than pick a winner:

- **Gen2 at x16** was recorded in two documents as an established result. It rests on one rig, one
  day, one screenshot. It is now stated as observed once on 2026-07-26 at medium confidence, with
  stability explicitly unestablished.
- **A 1935 MHz maximum SM clock** was carried as high confidence. It is a reported field, not an
  achievable clock: the VBIOS ceiling is 1695 MHz and every sustained measurement sits at 1410 MHz
  nominal. It is now low confidence.

---

## 4. Confidence taxonomy and how it maps to the page markers

| Underlying basis | How it appears on a page |
|---|---|
| Settled from shipping code, or reproduced by two or more testers, or arithmetic from either | Plain prose, no marker |
| Unreleased-branch code, or a single report | a `> [!WARNING]` alert titled **Experimental**, or an inline hedge naming the limitation |
| One report, one machine, one capture | Hedged in the sentence itself: "one tester reported", "observed once, on 2026-07-26" |
| Can destroy hardware or lose data | a `> [!CAUTION]` alert, reserved for physical and irreversible risk, never for "this might not work" |
| Genuinely unsolved | a `> [!NOTE]` alert titled **Open problem**, stating what was tried and what one experiment would close it |
| Unknown | The word "unknown", never a plausible-looking number |

The reader-facing version of this table, with examples, is on
[how to read this wiki](../start/how-to-read-this-wiki.md). The items that survived every pass as
genuinely unknown are collected on [open questions](../frontier/open-questions.md), ranked by how
cheaply each one could be closed.

---

## 5. Anonymisation

This documents two public servers, and **no individual is named anywhere on this site**: no handle,
display name, real name or user ID. Claims are attributed to a **date and a channel**, or to a
file, a commit or a register readback. Where the number of people matters to the weight of a claim,
this wiki writes "one tester", "two independent testers", "a researcher", "the maintainers".
Gendered pronouns are not used for anyone.

Three reasons, and only the first is courtesy. The work was done under clean-room rules where
provenance arguments were a live hazard. There is live legal exposure: a takedown notice was issued
against at least one public fork on 2026-07-17. And attribution is not evidence: stripping names
forces every claim to stand on its capture, its code line or its measurement. The community history
is recorded without personalities on
[clean room and provenance](../history/clean-room-and-provenance.md).

---

## 6. Limitations

Stated plainly, because they bound everything else on this site.

1. **This is a synthesis of a conversation, not a controlled study.** Nothing here was designed as
   an experiment. Measurements arrived when someone happened to run something and happened to post
   the output, on their own hardware, with their own cooling, PSU, host platform and workload.
   There is no control group and no protocol.
2. **The physical sample is tiny.** The 120-register fuse and register survey that underpins much
   of the hardware chapter was run on **two** physical 170HX units, both 10 GB cards, against 11
   rented comparison cards and two Drive A100 boards. Most other results come from a handful of
   cards belonging to a handful of testers.
3. **No 8 GB card was ever put through the full fuse survey.** Every 8 GB fuse and topology value
   in this wiki is a single-point probe, not a differential reading. Where 8 GB and 10 GB values
   differ, as they do for `NV_PTOP_FS4 0x0002241c`, the difference is asserted on thinner evidence
   than the 10 GB side.
4. **Several measurements are single-report.** Gen2 at x16, the 80 GB failure signature, most
   thermal figures and several benchmark numbers each rest on one capture from one machine. They
   are marked, but marked is not the same as reproduced.
5. **Some register semantics are inferred, not read from a header.** No NVIDIA internal header was
   available. Field widths and bit meanings were reconstructed from observed values and arithmetic
   that fits them. The clearest live case: the LMR magnitude field is treated as 6 bits at [9:4]
   because that is exact for all five encodings in real use, but the width has never been read from
   `dev_fb.h`, and one open question hangs on it. Inferred semantics can be exactly right about
   every value anyone has tried and still wrong about the field.
6. **Register names are not always the vendor's names.** Some are the code's names, some are
   clean-room tooling names, and at least one register carries two names in the corpus. The
   [register reference](../unlock/register-reference.md) carries aliases rather than pretending to
   a single authority.
7. **Absence of a report is not absence of a problem.** Failure modes that nobody hit on the small
   set of hosts represented here are simply invisible to this method.
8. **The project was still moving when the corpus was frozen.** Gen2, multi-card and IOMMU work
   were unmerged and actively changing. Two separate Gen2 fixes landed in the last two days of the
   archive: commit `8854d3e` "Remove clamp link to Gen1" on branch `far`, authored
   2026-07-26 local time and 2026-07-27T06:46Z, and branch `deced` published 2026-07-27 evening to
   remove a hardcoded PCI address that the maintainer called "the big bug". Several open reports
   were never re-tested against either. **"As of 2026-07-28" is load-bearing in every status claim
   on this site**, and nothing here has been re-verified against hardware after that date.
   Repository drift began immediately: the remote `ecc` branch was force-updated roughly sixteen
   hours after the snapshot, so this wiki's description of it is a snapshot description. The driver
   whitelist in particular
   (`610.43.03` and `610.43.02` exactly) is the most perishable fact in the wiki. See
   [driver versions](../procedures/driver-versions.md).

### What this method can and cannot guarantee

**It can reasonably guarantee** that a register address, value, offset, patch line, file path,
version string, command or error code quoted in plain prose is what the shipping tool actually
contains, because those were re-derived from the source trees rather than from the conversation
about the source trees. It can guarantee that a documented dead end really was tried and really did
fail. It can guarantee that no claim was upgraded in confidence during writing.

**It cannot guarantee** that any performance, thermal, power or link-width number generalises
beyond the specific card and host that produced it. It cannot guarantee that an unmarked absence
means the thing does not exist, rather than that nobody looked. It cannot guarantee that an
inferred register field is inferred correctly. And it cannot guarantee that the extraction and
adjudication passes did not lose or distort claims that the cross-check had no reason to examine,
because the cross-check only sees quantities that appear in more than one place.

Treat plain prose about code as near-certain, treat every hedged sentence as a single data point,
and treat the [status board](../frontier/status-board.md) as the current, perishable state of
things rather than as a specification.

---

## Related pages

- [How to read this wiki](../start/how-to-read-this-wiki.md)
- [External sources](external-sources.md)
- [Preserved artifacts](artifacts.md)
- [Open questions](../frontier/open-questions.md)
- [Dead ends](../history/dead-ends.md)
- [Clean room and provenance](../history/clean-room-and-provenance.md)
- [Timeline](../history/timeline.md)
