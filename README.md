# The CMP 170HX Wiki

A comprehensive technical reference for the NVIDIA CMP 170HX (GA100): silicon, firmware, the
community unlock, operating procedures, and the open frontier.

55 pages, roughly 278,000 words. Current as of **2026-07-31**.

## Two ways to read this

- **[Wiki tab](https://github.com/Consensus-Protocol/cmp170hx/wiki)** for browsing, with a sidebar.
  Pages there are generated from `docs/` and are identical apart from link style.
- **`docs/` in this repository** is the source of truth. It is reviewable, takes pull
  requests, and builds the full themed site with search via MkDocs.

Keep the two in step. `to_github_wiki.py` publishes `docs/` to the wiki; if edits are made on
the wiki instead, sync them back before continuing so the trees never diverge.

## Reading it

The pages are plain Markdown and read fine directly on GitHub or in any editor. Callouts are
written as GitHub alert blockquotes (`> [!NOTE]`), which GitHub styles natively; MkDocs renders
them as plain blockquotes unless a callout extension is enabled. To get search and navigation:

```bash
pip install mkdocs mkdocs-material
mkdocs serve          # http://127.0.0.1:8000
mkdocs build          # static site into ../site
```

## What is covered

| Section | Contents |
|---|---|
| `start/` | Orientation, card identification, quick start, risks, glossary |
| `hardware/` | GA100 silicon, board variants, memory subsystem, fuses and OTP, PCIe, NVLink, power, thermals, VBIOS |
| `unlock/` | The mechanism end to end: Falcon and Booter, the ROP chain, privilege level masks, memory geometry, compute throttle, driver patches, PCIe Gen2, full register reference |
| `procedures/` | Install, verify, troubleshoot, recover, multi-GPU, driver versions, uninstall |
| `operations/` | Cooling, power and PSUs, physical mods, performance, LLM inference, tuning |
| `frontier/` | Status board and the unsolved problems: PCIe Gen3/Gen4, NVLink, ECC, 80 GB, P2P |
| `history/` | Timeline, the clean-room and provenance question, dead ends, tool lineage |
| `appendix/` | Register index, preserved artifacts, external sources, methodology |

## Two things this wiki insists on

**Capacity is per SKU and is not interchangeable.** The 8 GB card (`10de:20c2`) unlocks to
**64 GB**. The 10 GB card (`10de:2082`) unlocks to **40 GB**. The 80 GB configuration for
10 GB cards was built, tested, and rejected as unstable.

**PCIe link speed and link width are separate problems.** Gen1 to Gen2 is a software unlock,
shipped in cmpunlocker `master` since 2026-07-29, so any card with the unlock installed runs
Gen2. Going beyond x4 width requires hand soldering 24 AC coupling capacitors. Neither one
achieves the other.

## Conventions

Plain prose is confirmed fact. Experimental, dangerous and unsolved material is marked with
alerts. Claims resting on a single observation say so in the sentence.
Where evidence genuinely conflicts and nothing settles it, the wiki says so rather than
choosing quietly.

No individual is named anywhere. Findings are attributed to dates and channels rather than to
people. See `docs/appendix/methodology.md` for how the underlying claims were gathered,
adjudicated and verified, and for an honest account of the limitations.
