# Project timeline

## What this page covers

A dated record of how the CMP 170HX went from a fuse-crippled mining card to a 64 GB, full-rate
GA100, covering the active period **2026-06-22 to 2026-07-28** with the earlier context that made it
possible. Chat timestamps are UTC unless a local offset is shown, and where a time is given to the
second it was decoded from a message snowflake or read from a git author timestamp. Git rows are
dated by the **author's local offset** (mostly `-07:00`), which is how the commits present
themselves; three branch tips therefore sit one calendar day earlier here than their UTC instant.

The five milestones a reader should anchor on:

| Date | Milestone |
|---|---|
| **2026-07-12** | Compute unlock works on hardware. A manual five-step TTY procedure lifts the 1/32 FP32 throttle; 12.28 TFLOPS SGEMM measured |
| **2026-07-14 / 15** | `cmpunlocker` goes public. The first release is a **driverless Python** compute unlocker, no driver patching at all |
| **2026-07-18** | Memory geometry ships. 8 GB to **64 GB**, 10 GB to **40 GB**, in-driver, in one day |
| **2026-07-23 / 24** | The driverless path returns as a standalone Python refire chain, and **PCIe Gen2** is announced |
| **2026-07-26 / 27** | Gen2 branch lineage stabilises; a single Gen2 x16 observation is captured on a capacitor-modded card |

Two things this timeline keeps rigorously separate, per the rule that governs the whole wiki: PCIe
link **speed** (Gen1 to Gen2, a software and firmware unlock) and PCIe link **width** (x4 to x16,
achievable only by hand-soldering 24 depopulated capacitors). They are different achievements on
different dates. See [the PCIe subsystem](../hardware/pcie-subsystem.md) and
[physical mods](../operations/physical-mods.md).

---

## Prehistory: 2021 to 2023

| Date | Event |
|---|---|
| **2021-04-23** | VBIOS build date of the earliest shipping 10 GB card (`92.00.66.00.02`, device `0x2082`) |
| **2021-05-14** | VBIOS build date of the 8 GB card (`92.00.67.00.01`, device `0x20C2`) |
| **2021-09-01** | **CMP 170HX released.** GA100, 826 mm², 54.2 billion transistors, TSMC 7 nm N7, 8 GB or 10 GB HBM2e, 250 W, no display outputs, no DirectX/Vulkan/OpenGL/NVENC/NVDEC exposure, sold for Ethash mining |
| **2021-11-01** | A third VBIOS revision, `92.00.6D.00.09`, exists but is not in the archived comparison set |
| **2023-07-05** | A community blower-adapter STL is published, the first widely reused 170HX cooling artifact |
| **2023-10-25** | **The public teardown and review.** The single most important pre-unlock document: it publishes the verbatim `lspci` output (Gen1 x4 trained on a x16-wired slot, `SlotPowerLimit 75W`, `FLReset+`), the depopulated AC-coupling capacitors on lanes 4 to 15, stock clpeak and mixbench numbers, and the conclusion that the Tensor Cores "probably aren't working" |
| **2023-10-27** | **The FMA-disable discovery.** Posted to the FluidX3D issue tracker, issue #8 (comments 1779728815, 1782734954, 1782763214) and implemented immediately: compiling with FMA contraction off recovers roughly 16x FP32, reaching about 6.25 TFLOPS |
| **2023-12-06** | The FMA result is brought to the NVIDIA-patcher issue tracker, issue #73, two months later. That issue is what ultimately led to the register-level crack |

!!! note "Superseded"
    The 2023 review's conclusion that the Tensor Cores were not working was drawn from `gpu_burn -d
    -tc` returning 6236 GFLOP/s, identical to the plain non-FMA FP32 rate. The cores were present and
    functional but throttled; `CUBLAS_TENSOR_OP_MATH` was routing around the FP32 FMA lockdown rather
    than engaging tensor hardware. Unlock-era measurements put FP16/BF16 tensor at 150 to 195 TFLOPS.

---

## Origins of the modern effort: 2026-03 to 2026-06-21

| Date | Event |
|---|---|
| **2026-03** | Work restarts on the NVIDIA-patcher issue tracker, issue #73 |
| **2026-04** | Development moves to a Discord server |
| **2026-04-04** | An AI-generated write-up concluding "the FP throttle is hardware enforced and can't be overridden" is linked from issue #73. Its own footer records the test environment: Ubuntu 22.04, kernel 5.15.0-174-generic, driver 535.288.01, CMP 170HX (`0x2082`), April 2026. Later refuted outright by the shipping compute unlock |
| **2026-05** | **The decisive cryptography discovery**: a route to reading the AES-encrypted, RSA-signed `booter_load` code |
| **2026-05-05, 2026-05-07** | **The fuse survey begins.** Two physical CMP 170HX 10 GB cards fully probed with `tools/mmio-probe/probe.sh`, 120 registers each. 107 of 120 registers are byte-identical between the two units; all 13 differences are per-die binning artefacts. This is the result that licenses transferring a recipe from one card to another |
| **2026-05-31** | **The fuse survey completes.** Two physical Drive A100 32 GB (`GA100-550F-A1`, PG199) probed, joining 11 rented Ampere cards, for a **15-card, 120-register** cross-variant table. Exactly five register groups distinguish a 170HX from an A100 of the same silicon: SM speed select, PCIe boot generation, NVLink disable, ECC enable, FBPA CFG1 geometry. `z1_dump_and_parse_vbios.sh` and `z2_parse_vbios_table.py` land the same day, along with a survey of six firmware-side attack paths (three DFA glitching routes, a CH341A flash path, the capacitor mod, and the software FMA workaround) |
| **2026-06** | The first ROP chain able to jump to an arbitrary address in the booter is demonstrated and announced on the open server. Development moves into a private group of **seven people**, producing the proof-of-concept, the paper, and two internal Driver Modification Guides |
| **2026-06 (paper date)** | **"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"**, 16 pages, Zenodo record `20916112`, ResearchGate `408132536`. Headline claims: all three caps are soft; roughly 31-62x compute, 8x capacity, 2x link |

The exploit's codename is **FACEB13D**, "fake bird", after the stack guard canary that had to be
defeated. The enumerated obstacles were security by obscurity, stack canaries, security levels L0 to
L3, an immutable boot ROM, a secure co-processor, AES encryption of code, and RSA signing of code.

---

## 2026-06-22 to 2026-06-30: first public tooling and the clean-room charter

| Date | Event |
|---|---|
| **2026-06-22** | First dated tooling failure in the archive: `deploy.py --path sec2-rop` aborts because it invokes `firmware/load_custom_bin.py --verify`, an argument the loader's argparse does not accept. Exit code 2, not a hardware failure. Fixed by 2026-06-24 |
| **2026-06-23** | `deploy.py --path vbios-memory` is tried and never works: `ERROR: Not a PCI Option ROM (bad magic at 0x00)`. The whole VBIOS-memory approach is dropped. Separately, `CMPGPU-patch-script` (`optimize-cmp-cuda.py`), an interactive llama.cpp source patcher with five FMA and intrinsic optimisation groups, is published |
| **2026-06-26** | The Canary preprint is circulated in the unlocker server |
| **2026-06-27** | **The clean-room rule set is stated as channel policy**: no NVIDIA secrets; secret knowledge admissible only if derivable from public sources; posting leaked material is a ban. The paper is designated the single clean input document. A dirty-room/clean-room two-team split is proposed and then largely dropped in favour of a channel split |
| **2026-06-30** | The debug branch is shown to be obfuscated only with a **public AES-128-ECB test key**, constructed as the MD5 initialization vector with the key number as the last byte, sourced from NVIDIA's public Jetson Secure Boot documentation. A self-contained public-domain decrypter (`rijndael-tool.zip`) is published in-channel |

See [the clean room and the provenance question](clean-room-and-provenance.md) for the full charter
and its consequences.

---

## 2026-07-01 to 2026-07-11: the booter becomes readable

This is the fortnight in which the Falcon secure co-processor stopped being a black box.

| Date and time | Event |
|---|---|
| **2026-07-01T12:40:37Z** | **The raw debug booter disassembly is posted**: `booter_load_ga100_dbg_seccode.fuc5.asm`, 545,149 bytes, produced with `envytools/envydis` targeting `fuc5`. Every gadget address later used by the shipping exploit is an instruction boundary in this file |
| **2026-07-01** | The clean extraction path is accepted in-channel: the debug `booter_load` is a C array inside NVIDIA's own `.ko`, published as `g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c`. Working it out took two days. A 4,196-byte descriptor blob posted the same day turns out to be mostly zeros |
| **2026-07-02** | **Debug equals production where it matters.** The two binaries are exactly the same size, and a chain built purely from the debug disassembly runs on production silicon. Without this the clean-room approach would have been dead. The register provenance standard is accepted the same day: diff an A100's BAR0 against a 170HX's and change everything to the A100 values |
| **2026-07-03T17:12:52Z** | The annotated disassembly is posted, superseding an LLM-generated overview whose author flagged it as unverified |
| **2026-07-04** | **The booter stack is exfiltrated from silicon**, one dword per boot, via gadget `0x7de9` writing a chosen DMEM word to the SEC2 mailbox. About 35 boots at roughly 90 s each under DKMS. The region below `D[0xFF74]` cannot be leaked because the ROP itself sits there. Because the canary is re-randomised every boot, running the dump twice and diffing reveals which slots are canaries |
| **2026-07-05T20:42:54Z** | `170HX_ROP_payload_v1.txt` posted. The Nouveau firmware-extraction script, patched for GA100 array naming, is confirmed working by multiple users |
| **2026-07-06** | A parameterised catalog of **eight named ROP recipes** is maintained, differing in rejoin point (`0x37b7` versus `0x37cc`), hijack gadget, stack style and smash size (`0xF800`, `0xF810`, `0xF820`) |
| **2026-07-09T03:03:21Z** | Annotated disassembly **v2**, 607,702 bytes, 11,875 lines, with every `lcall` carrying an inline comment naming the callee |
| **2026-07-09T10:17:09Z** | `170HX_ROP_payload_v3.txt` posted |
| **2026-07-10T13:40:14Z** | **The Register Gadget Atlas**, auto-generated from the disassembly, tabulating each gadget's register effect, canary condition and `mpopaddret` epilogue |
| **2026-07-11** | An LMR encoding attempt of `0x40A` on a 10 GB card fails. Separately, the claim that the CMP 100 series is Pascal is walked back to Volta by its own author |

!!! question "Open problem"
    A clean-room message dated **2026-07-05** treats PCIe Gen2 as already unlocked, three weeks
    before the reproduced result. Either an earlier independent result that never propagated, or a
    mis-attributed timestamp. Only the original message metadata can settle it.

---

## 2026-07-12 to 2026-07-17: compute lands, and the repository goes public

### The compute unlock

**2026-07-12** is the date the throttle came off. The working manual procedure, before any in-driver
patch existed:

```text
run the ROP script  ->  FLR  ->  kill the NVIDIA driver  ->  FLR again  ->  run the SM unlock script
```

FLR means `echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset`. It had to be run from a TTY.
The driver was the open kernel modules at 580.159.04, with the payload spliced into
`gsp_tu10x.bin` by `patch_gsp.py`. `Guide_SM.sh` implemented it as a three-write ROP stage
(CFG1 `0x02779000`, LMR `0x0000020B`, PLM `0xFFFFFFFF`), an FLR, an aggressive driver unload, a
second FLR, then host writes of `0x0082381C = 0x88888888` and `0x00823820 = 0x00000008` through
`resource0` with readback verification.

Measured the same day: **12.28 TFLOPS SGEMM FP32** on a first full SM unlock, reported by two
independent testers. No locked baseline was taken on that card in that session. The "32x" announced
alongside it is the architectural divisor implied by the fuse value `0x5`, and the quoted stock rate
of roughly 0.38 TFLOPS is 12.28 divided by 32, not a separate measurement. An independently measured
locked rate of about 0.39 TFLOPS corroborates the divisor; see
[performance](../operations/performance.md). The stock
`FEATURE_OVERRIDE` block was dumped in full (`regs_01.txt`), and the master kill fuse `0x008203f0` was
confirmed unblown at `0x00000000`, which is the reason any of this is possible.

Getting there cost **over 1100 fires**, of which only about 50 were genuinely distinct attempts, as
the person who did the work later put it: "I just couldn't have known that in advance."

### The rest of the week

| Date | Event |
|---|---|
| **2026-07-12** | In a driverless context with no devinit, a broadcast write to `0x009A0204` alone does not move CSTATUS; every per-FBPA instance must be written at `0x00900204 + n*0x4000`, n = 0..23. In the driver path the single broadcast write suffices |
| **2026-07-13** | **LMR coherence.** With CFG1 written but LMR left at `0x288`, GSP-RM reverts CSTATUS from `0x800` back to `0x200` during `kgspBootstrap`. With LMR set coherently to `0x28A`, instrumented dumps hold `CSTATUS=0x800 LMR=0x28a CFG1=0x2669000 WprMeta.fbSize=0xa00000000` at all four checkpoints. A parallel clean-room server's compute unlock is public on or before this date, which is the stated argument for open-sourcing |
| **2026-07-14T21:47:02-07:00** | **`cmpunlocker` initial commit `9b9fb2f`.** Announced in-channel the same day (the announcement window and the commit's UTC time, 2026-07-15T04:47:02Z, do not order cleanly; announcement times are approximate). The release is **driverless Python**: `payload/build.py`, `gsp_patch.py`, `pipeline.py`, `bar0.py`, `driver.py`, `unlock/compute.py` and a `daemon/` watchdog, with no driver patching whatsoever |
| **2026-07-14** | Geometry is measured **not** to survive an FLR: CFG1 reverts `0x2779000` to `0x2449000`, LMR reverts `0x20b` to `0x288`, while SS0 and SS1 both survive. That asymmetry is why compute shipped before memory. A compute-unlock shell script leaks as `CMP170HX_Compute_Unlock_v8_3.sh` and is quickly deleted |
| **2026-07-15** | Within an hour of a `cmpunlocker` repository being shared, testers report bricked machines and non-booting 10 GB cards. No root cause is established in that window, but 10 GB (`0x2082`) support did not yet exist in any driver path, so the suspicion was directionally right. Forks appear the same day. Per-FBPA CFG0 is measured identical at `0x07981800` on every live partition |
| **2026-07-15T18:48:10Z** | The `ROP_CHAINS_1180f8` writeup documents the `+0x18` DMEM frame stride in prose |
| **2026-07-16T06:07:12Z** | The paper is posted into the clean-room server as `main.pdf` |
| **2026-07-16** | **No PLM confers always-on status on FB geometry.** With all six FB-geometry PLMs plus `FUSE_SS_PLM` open, CFG1, CSTATUS and LMR still revert on FLR and are never cold-boot persistent (`geo_flr_survival_map_20260716.sh`). This is the structural reason the shipping design re-applies geometry inside the GSP boot path on every module load. A catalog of **26 distinct PLM registers** is completed the same day |
| **2026-07-17** | **NVIDIA issues a DMCA takedown against at least one fork**, taking that repository offline. Host PL0 writes to CFG1 are reproduced as silently dropped until the FB-geometry PLMs are opened (`Write failed - wrote 0x2779000, read 0x2449000`, three times, no error signalled). The most-circulated architecture notes are published with a self-rating of about 10 percent proven |

!!! warning "Which repository was first is unresolved"
    Three independent first-hand retellings on 2026-07-22 place the clean-room compute unlocker's
    release at "about 10 days ago", pointing to roughly 2026-07-12, and a 2026-07-13 statement says a
    compute unlock "was released and it's basically available to the public at this point in time".
    But the repository whose source is archived has its initial commit on 2026-07-14, and a
    **differently-owned** repository of the same name was being shared and bricking testers on
    2026-07-15. The most likely reconciliation is at least two same-named repositories under
    different accounts, with "about 10 days ago" a rounded recollection. The archived tree cannot be
    assumed to be the earliest clean-room release.

---

## 2026-07-18: memory, in one day

The single densest day in the project. Times are UTC.

| Time | Event |
|---|---|
| **18:01:15** | `patch.diff` is posted to `#general-how-to-cleanroom`, extracted from a leaked redistribution package |
| **18:26:26** | Every file in what becomes the shipping patch set carries this `diff -Naur` header mtime. One tree, written at one instant |
| **18:40:16** | The LAPSUS$ provenance assessment is posted, 39 minutes after `patch.diff` |
| **19:11:01** | `06fabf2 "WORKING MEMORY UNLOCK"` on the `memory` branch, **70 minutes** after the posting. The commit deletes the entire driverless Python pipeline (`payload/*.py`, the `daemon/` watchdog, `.pylintrc`) and replaces it with six driver patches |
| **20:51:36** | `6b7d9ee "FULL WORKING THING"` |
| **21:37:17** | `99338ef "Goodbye lint"` deletes `.github/workflows/pylint.yml` and `tests.yml`; `8206c16 "Goodbye tests"` follows 16 seconds later and removes the last test file |
| **21:46:49** | `e4026e5 "Memory working!"` merged to `master` |

What shipped that evening, and still ships:

| Card | PCI ID | Stock | Unlocked | CFG1 `0x009a0204` | LMR `0x00100ce0` | `targetFbBytes` |
|---|---|---|---|---|---|---|
| 8 GB | `10de:20c2` | 8192 MiB | **65536 MiB (64 GB)** | `0x02779000` | `0x0000020B` | `0x0000001000000000` |
| 10 GB | `10de:2082` | 10240 MiB | **40960 MiB (40 GB)** | `0x02669000` | `0x0000028A` | `0x0000000A00000000` |

Stock CFG1 is `0x02449000` on **both** SKUs; stock LMR is `0x00000208` (8 GB) or `0x00000288`
(10 GB). Also on 2026-07-18: the `multiple-cards` branch is committed, the `housekeeping` branch adds
`0x2082` support to all patches, and master commit `0f9aca5 "Unlock isn't gated anymore"` widens the
install gate from `0x20C2`-only to `0x20C2`/`0x2082`.

Full detail: [memory geometry](../unlock/memory-geometry.md) and
[the six driver patches](../unlock/driver-patches.md).

---

## 2026-07-19 to 2026-07-24: consolidation, the driverless return, and Gen2

| Date | Event |
|---|---|
| **2026-07-19** | The `multiple-cards` branch is announced. The `80` branch (`3c53aca "Correct LMR for 80GB"`) attempts 80 GB on the 10 GB card. `requirements.txt` is deleted (`7019bc2`). `remove.sh` is confirmed to restore a card well enough to resume mining. `cuda_dbg.py` and `cuda_memtest` 1.2.3 enter use as VRAM validators. `unlock_host_610.sh` is published. The project lead asks role-holders to validate the 10 GB path |
| **2026-07-20 02:25** | A100 owners are asked to run `sudo python3 probe.py --check` and `--out a100.json` (`probe.py`, 11,472 B) |
| **2026-07-20 16:40** | A Gen2-specific probe kit is distributed (`probe.py` 9,132 B, `README.md` 3,022 B, `sweep.sh` 3,007 B) "to probe and sweep registers on the A100 specifically for PCIe Gen 2". A contributor with real A100 access supplies six JSON dumps. Write tests on the donor A100 do not work, so only read data is available, which the maintainer says is sufficient |
| **2026-07-21** | `clanker/driver-port` (`153cd6d`) adds per-branch patch directories for 580/590/595/610. It is established that `gsp_tu10x.bin` never needed extracting: the annotated blob is the debug Booter |
| **2026-07-22** | **First-hand accounts of the whole development history are posted**, independently in three channels, establishing the March-to-June sequence. The "Chinese unlock" is assessed as the leaked private proof-of-concept. Geometry is measured to survive a driver unload and reload with no SBR. The first `refire_chain.py` and its v2 generic write-engine rewrite land. The fold-detection harness is shown to be unreliable, retroactively invalidating a body of earlier fold-at-40 GB conclusions. A near-driverless 40 GB path is demonstrated with a single driver line still removed |
| **2026-07-23** | **The driverless Python unlocker returns.** A standalone memory unlocker script, run **before** driver load, needing no FLR, is documented: run the original compute-only unlock (which does perform an FLR), then run the memory script, then load a clean unmodified driver. Its authors state plainly that it is machine-generated and not fully understood: "It is so cryptic, it is almost like a black box." The `debug-gen2` branch tip is `746d9f7 "PCIe Gen 2 works!"`. `master` reaches its archived tip `cc872cb`, whose last two commits add `pull_request_template.md` and move it under `.github/`. The `docs/CONTRIBUTING.md` guide and the hard-gated template wording ("I WILL REJECT ANY PR THAT DOES NOT FOLLOW THIS TEMPLATE!") land four days later, on the `docs` branch on 2026-07-27 |
| **2026-07-24** | **PCIe Gen2 is announced.** `refire_chain_v6.py` (27,769 B) is released with mode flags `--compute`, `--memory 40|80`, `--pcie-gen2`, `--pcie-retrain`, `--all`. `pcielink.sh` becomes the standard PCIe field-report collector. `check_fold.py`, the authoritative test for whether unlocked VRAM is real, is published. The unlock is restated as non-persistent software state, not a firmware modification: it must be re-applied on every GSP boot. The maintainer declines to support other Ampere CMP cards as a scoping decision |

!!! warning "Experimental"
    Gen2 is real, reproduced, and **not shipped**. `master` carries patches `0001` to `0006` only and
    has no `pcie:` block in `constants.yaml`. `0007-pcie-gen2.patch` exists on `debug-gen2`, `Gen2`,
    `far` and `deced`; `0008-pcie-gen2-probe-retrain.patch` on `Gen2`, `far` and `deced`. Installing
    Gen2 means running an unreleased branch. See [PCIe Gen2](../unlock/pcie-gen2.md).

---

## 2026-07-25 to 2026-07-28: the last week in the archive

| Date | Event |
|---|---|
| **2026-07-25** | Days of unattended LLM agent work fail to produce an 80 GB unlock. `install.sh` auto-detection is found unsafe on mixed-GPU hosts: `detect_card_profile()` reads the first GPU in `nvidia-smi` order, not the CMP found by `lspci`, so an RTX 3080 10 GB next to an 8 GB 170HX selects the wrong profile. Always pass `--profile` explicitly. A request for the paper's Falcon emulator is answered "No, they did not" |
| **2026-07-26** | The `Gen2` branch reaches its tip `a4de322`, which only merges `master` into `Gen2`. The branch's multi-card support, `verify.sh`, the move of the retrain into the driver via patch `0008` and the deletion of `tools/cmpretrain.service` all landed two days earlier, in `2f27474 "Gen2 + multiple-card support"` on 2026-07-24; `tools/retrain.sh` remains in the tree. `far` (`8854d3e "Remove clamp link to Gen1"`) changes `RMPcieLinkSpeed` from `0x1` to `0x2`. A standalone `cmp170hx-gen2-setup.sh` (12,389 B) is released alongside a `PCIE_GEN1_LOCK.md` analysis |
| **2026-07-26** | **Gen2 x16 is observed once.** A capacitor-modded card running the `Gen2` branch reports `PCIe GEN 2@16x` with `ocl_pcie_bw` at 6.63 to 6.67 GB/s and nvtop TX at 7.061 GiB/s. One rig, one day, one screenshot. Confidence **medium**; stability at Gen2 x16 is unestablished |
| **2026-07-27** | `deced` (`2326599 "Stupid mistake - it appears to be hardcoded"`) replaces the hardcoded `0a:00.0` BDF in `tools/retrain.sh` with a `find_gpu_bdf()` lookup, though that file is dead code on the lineage. The `docs` branch reaches `651b6d5` and is documented as non-authoritative. A two-day A100-versus-170HX register diff hunting a PCIe Gen3 strap is declared a dead end; the negative result is the finding. `170tune` is published. The canonical documentation site is updated at 23:59. A multi-tenant rig loses its driver state to ghost processes after a killed `llama.cpp` run |
| **2026-07-28** | End of the archived period. Twelve unreleased branches were snapshotted (thirteen trees counting `master`). Sixteen unreleased branch refs exist on the remote; `code-simplification`, `dual-geometry-fix`, `fix` and `v0.1` were not captured and were not analysed |

---

## Milestone summary

| Achievement | Date | Persistence | Ships on `master`? |
|---|---|---|---|
| FP32 FMA compile-time workaround (roughly 16x, 6.25 TFLOPS) | 2023-10-27 | Source-level, per application | Not a driver feature |
| Compute throttle removed (SS0/SS1, full rate) | 2026-07-12 | Survives FLR (always-on island) | **Yes** |
| `cmpunlocker` public, driverless Python | 2026-07-14 / 15 | Re-applied per boot | Removed 2026-07-18 |
| Memory geometry, 8 GB to 64 GB and 10 GB to 40 GB | 2026-07-18 | Does **not** survive FLR or power cycle | **Yes** |
| Multi-card support | 2026-07-18 / 19 | Per boot | No, branch only |
| 80 GB on the 10 GB card | 2026-07-19 | Attempted, unstable above roughly 40 GB | No, and it should not |
| Driverless SEC2 refire chain (v1 to v6) | 2026-07-22 to 24 | Per boot, GPU must be unbound | No, parallel path |
| PCIe Gen2 (speed, x4) | 2026-07-24 | Per boot, in-driver on branch | No, branch only |
| PCIe x16 (width, by soldering) | Hardware mod, any date | Permanent, physical | Not software |
| Gen2 x16 combined | 2026-07-26, one observation | Unestablished | No |

!!! danger "The 80 GB tier is not a milestone"
    The `80` branch reports roughly 81920 MiB and 85,545,582,592 bytes, and `cudaMalloc` of 77 GiB
    succeeds, but at 80 GB kernels touching more than roughly 40 GB cause fatal GPU loss,
    independent of power limit. Reported Xid codes include Xid 31 (described as harmless) and
    Xid 154 after CUDA memory tests; the dominant reported symptom is hangs. Xid 31 alone was
    suggested by a bystander and was not corroborated as *the* signature by the operator with the
    failing card. `cuda_memtest` hangs unless capped at 39 GB. 40 GB ships instead. See
    [the 80 GB question](../frontier/80gb.md).

---

## See also

- [The clean room and the provenance question](clean-room-and-provenance.md)
- [Tool lineage](tool-lineage.md), and which tools are dead
- [Dead ends](dead-ends.md)
- [How the unlock works](../unlock/how-it-works.md) and
  [the compute throttle](../unlock/compute-throttle.md)
- [Open questions](../frontier/open-questions.md), what is still unsolved as of 2026-07-28
