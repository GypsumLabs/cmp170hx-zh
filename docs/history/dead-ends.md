# Dead ends: what did not work, and why

## What this page covers

Roughly **507 dead ends** were recorded across the CMP 170HX project between March 2026 and July
2026. This page documents the significant ones by domain: the hypothesis as it was actually held,
why it was reasonable at the time, the specific evidence that killed it, and the date it was
abandoned.

Read this before starting new work. Several of these consumed weeks. A few were disproved by the
same people who proposed them, sometimes within minutes, and that is the healthiest pattern in the
whole archive. Nothing here is mockery: every entry was a defensible reading of the evidence
available when it was made, and the entries that were wrong were wrong for interesting reasons.

Three headline results that this page exists to protect:

- The FP32 throttle **is** hardware-enforced, and it **was** defeated anyway. Both halves are true.
  The published conclusion that it could not be overridden was correct about every path it tested
  and wrong about the one it never tried.
- The L2/LTC address-map register `0x17E22C` was the team's root-cause model for the memory
  capacity wall for more than a week. It is not the wall. The shipping driver never touches any
  `0x17Exxxx` register.
- The project's own `docs` branch is **not** authoritative. It invents acronym expansions, prints
  register values the code does not write, and documents a script that does not exist. Anyone
  validating an unlock against it will wrongly conclude the unlock failed.

## How to read an entry

Each entry carries four things: the **hypothesis**, why it was **plausible**, what **disproved** it
with the concrete evidence, and the **date** it was abandoned. Where a claim was retracted by its
own author, that is stated, because self-retraction is a much stronger signal than third-party
dispute.

A dead end is not the same as an open question. Things that are unresolved rather than refuted live
on [open questions](../frontier/open-questions.md) and the
[status board](../frontier/status-board.md). Things that were replaced by something better are
recorded here as superseded, with a pointer to the replacement.

---

## Contents

1. [Compute and the FP throttle](#compute-and-the-fp-throttle)
2. [Memory geometry and capacity](#memory-geometry-and-capacity)
3. [Firmware, the Falcon and the Booter ROP](#firmware-the-falcon-and-the-booter-rop)
4. [PCIe: speed, width, Gen3 and Gen4](#pcie-speed-width-gen3-and-gen4)
5. [NVLink](#nvlink)
6. [ECC](#ecc)
7. [VBIOS and flashing](#vbios-and-flashing)
8. [Drivers and the kernel patch set](#drivers-and-the-kernel-patch-set)
9. [Tooling, measurement and AI-assisted work](#tooling-measurement-and-ai-assisted-work)
10. [Thermal, power and cooling](#thermal-power-and-cooling)
11. [Documentation defects in the project's own docs branch](#documentation-defects-in-the-projects-own-docs-branch)
12. [Values that propagated through chat but are absent from shipping code](#values-that-propagated-through-chat-but-are-absent-from-shipping-code)
13. [Recurring failure patterns](#recurring-failure-patterns)

---

## Compute and the FP throttle

### `SM_ISSUE_RATE_MODIFIER` at `0x00504204` is the throttle register

**Hypothesis.** The register literally named "SM issue rate modifier" controls the 1/32 FP32 issue
rate. Zero it and the throttle lifts.

**Plausible because** the name is exactly what anyone would want, the register is host-writable at
PL0, and it reads `0x00000005` on the 170HX, which is the same value as the speed-select fuses. Two
independent facts appeared to line up.

**Disproved by** a 13-card cross-probe: `0x00000005` is also what A100 SXM4 40G, A100 PCIe 40G,
A100 PCIe 80G, A10, A5000, A6000, RTX 3080, RTX 3080 Ti, RTX 3090, RTX 3090 Ti and Drive A100 all
read. Full-speed datacentre parts carry the identical value, so it cannot encode a throttle.
Writing zero produced no performance change. Re-confirmed on 2026-07-27 against a 96-SM `0x20bb`
GA100 (`NVIDIA DRIVE-PG199-PROD CC 8.0 SMs=96`), which reads `0x00000005` while every `FUSE_SS_*`
on that card reads 0. The shipping tree contains **zero** references to `0x504204`.

**Abandoned** 2026-05-31, re-confirmed dead 2026-07-27.

### The `RMOverrideSmSpeedSelect` registry key

**Hypothesis.** A genuine NVIDIA registry key inside the GSP firmware sets the SM speed select
override. Set it and the throttle lifts.

**Plausible because** the key is real and the entire consumer chain was traced by reverse
engineering: an init function at VA `0x01607B78` reads the key and stores a present flag plus an
override dword into the GPU config struct; VA `0x01155DCC` reads the override as a halfword; four
helper functions at VA `0x01175A48` to `0x01175B2C` test bits 0 to 3; present-flag checks sit at
`0x014853E4` and `0x01491F34`.

**Disproved by** following the chain to its destination. The override flows into the PROD_DIFF list
and the HAL registry table and ends up aimed at `SM_ISSUE_RATE_MODIFIER` at `0x504204`, whose writes
are silently dropped on production silicon. The address does not even appear as a literal in the
firmware; it is reached through HAL abstraction. The mechanism name was right and the target
register was wrong.

**Abandoned** 2026-04-04.

### Spoofing the `speed_select` fuse value inside GSP firmware

**Hypothesis.** Patch the fuse read inside GSP firmware so the Production Differential register list
that GSP-RM builds and hands to FECS programs `SM_ISSUE_RATE_MODIFIER = 0`.

**Plausible because** it attacked what genuinely is the source of truth (the fuse read) at what
genuinely is the configuration layer (PROD_DIFF). This was not a shot in the dark.

**Disproved by** two independent facts. FECS reaches GPU registers through a priv window spanning
`0x20000000` to `0x23050000`, and the SM register space where `SM_ISSUE_RATE_MODIFIER` lives
(`0x20504xxx`) is completely absent from that window, so FECS physically cannot write the register
even given a perfect PROD_DIFF list. Separately, GSP-RM is NVIDIA-signed. Fourteen firmware patches
to `gsp_ga10x.bin` (VAs `0x1629618`, `0x1629694`, `0x16297f8`, `0x15d70bc`, `0x15d70f8`, `0x14b1480`,
`0x14b1478`, `0x1607e20`, `0x1629680`, `0x1592b38`, `0x1592c50`, `0x1592d7c`, `0x1593620`,
`0x15939a0`) plus 12 `nvidia.ko` edits moved FFMA from 0.3159 TFLOPS to 0.3146 TFLOPS, a 0.4% delta
that was correctly called measurement noise.

**Abandoned** April 2026, published 2026-07-23.

### "The FP throttle is hardware enforced and cannot be overridden"

This is the single most consequential dead end in the project.

**Hypothesis.** An externally published, AI-generated write-up (roughly 18 hours of agent time,
about USD 110 of API spend) concluded verbatim: "The FFMA throttle is not a software restriction. It
is not a firmware configuration. It is not a driver policy. It is a physical property of the chip,
programmed at the factory and enforced by hardware logic that runs before any software has a chance
to intervene."

**Plausible because** every path it tried genuinely failed and its measurements were correct. It was
not sloppy work. Its own footer records the environment: Ubuntu 22.04, kernel 5.15.0-174-generic,
NVIDIA driver 535.288.01, CMP 170HX (`0x2082`), April 2026.

**Disproved by** a register dump of an unlocked card on 2026-07-25 showing `0x00823800` and
`0x00823804` reading `0xffffffff`, `0x0082381c` = `0x88888888`, `0x00823820` = `0x00000008` and
`0x00823818` = `0x00000000`. The search space never included the `FEATURE_OVERRIDE` register block:
it never opened the privilege level mask at `0x00823804` and never wrote `0x0082381c`.

**The nuance worth preserving.** The fuse itself really is unchangeable, and the throttle really is
hardware-enforced. What the write-up missed is that the enforcement is *configurable at privilege
level 3* through a documented override that supersedes the fuse, and that this override is available
only because the master kill fuse `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` at `0x008203f0` reads
`0x00000000` on this part. NVIDIA left the override enable unblown. Had it been blown, the write-up
would have been right.

**Abandoned** 2026-07-25. Driver 535.288.01 also predates the GSP layout the shipping unlocker
targets (610.43.02 and 610.43.03), which is a further reason its firmware analysis does not transfer.

### Host-only register writes with no driver loaded

**Hypothesis.** Write the unlock registers from the host with no driver loaded, then load the stock
driver and keep the result.

**Plausible because** the writes visibly land. On 2026-06-30 a researcher wrote
`0x009A0204 = 0x02779000`, `0x0082381C = 0x88888888` and `0x00823804 = 0xFFFFFFFF` with no drivers
loaded and read all three back correctly.

**Disproved by** loading the stock driver afterwards: `0x00823804` read back `0xffffff8f`
(re-locked) and the throttle dividers were back at 5. The stock driver re-locks the privilege level
mask as part of normal bring-up. This is the exact failure mode that the in-driver GSP-boot-path
design exists to solve.

**Abandoned** 2026-06-30. Superseded by opening the mask from inside the SEC2 Booter window and
writing the registers in the same driver load. See
[how the unlock works](../unlock/how-it-works.md).

### Opening `FUSE_SS_PLM` at `0x008200FC`

**Hypothesis.** The speed-select fuse mask is wide open (`0xffffffff`) on every card, which reads
like an oversight. Go through it.

**Plausible because** an unguarded privilege level mask on exactly the registers of interest is
precisely the kind of mistake that makes an unlock possible, and an early consolidated recipe
(2026-07-07) listed writing it as one of three high-secure steps.

**Disproved by** what sits behind it: the `OPT_SM_SPEED_SELECT` registers are OTP fuse **shadows**
and are read-only regardless of privilege. Separately, writing the mask itself fails: it appears
physically read-only, capped at `0x000003FF`, from both the ROP and a direct host `writel`. The
correct diagnosis was recorded at the time: "the PLM is not needed, if we modify the SM_SPD
registers directly." The shipping unlock does not touch this address at all.

**Abandoned** 2026-07-09. It reappears in the nine-entry mask table on the Gen2-family branches
under the code name `OPT_PLM`.

### Recovering extra SMs

**Hypothesis.** The card is floorswept to 70 SMs out of 108, and the floorsweep control registers
are writable, so the missing SMs can be turned back on.

**Plausible because** `FUSE_STATUS_OPT_TPC_GPC(i)` at `0x820c38 + i*4` clearly shows the disable
pattern (GPC0, GPC3 and GPC5 read `0xff`, the others read `0x01`), and the control register sits
right next to it at `0x820838 + i*4`. Envytools additionally describes the floorsweep registers as
read/write at privilege level r4.

**Disproved by** the cleanest negative-result experiment in the archive, which carried two controls.
The **positive control**: a high-secure write to FBPA CFG1 `0x9a0204` changed `0x02449000` to
`0x02779000` and stuck, with `resetPLM = 0xff` throughout, proving the Booter write primitive was
live. The **reachability control**: a high-secure write to `CTRL_OPT 0x82083c` changed `0` to `0x80`
and `STATUS 0x820c3c` responded `0x1` to `0x81`, proving the floorsweep block itself accepts
high-secure writes. The real targets all bounced: `OPT_GPC_DISABLE 0x820350` stayed `0x45`,
`STATUS_OPT_GPC 0x820c1c` stayed `0x45`, `OPT_TPC_GPC2 0x820768` stayed `0xff`,
`DIS_SW_OVR 0x820084` stayed `1`, and `RING_ENUM_GPC` never moved off 5. The GPC-disable registers
are latched. Privilege level was never the blocker.

**Abandoned** 2026-07-27, on an 8 GB card (`0x20c2`).

A parallel attack on `gpcMask` (forcing `0xdc` to `0xff`) was tried three independent ways by
someone who already had the 64 GB memory unlock working: through the RM floorsweep struct, through a
host MMIO write `GPU_REG_WR32(0x408970, 0xFF)`, and by patching the GSP firmware's `andi`
instruction to `li a4,255`. In all three cases the software stack reported 8 GPC and 112 SM,
`0x408970` read back `0xdc` every time, and `cuInit` segfaulted. The mask is not the lever; the GPCs
are genuinely fused or power-gated off.

### Other compute dead ends

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| The FECS mirror `FECS_FEAT_OVERRIDE 0x00409664` / `FECS_FEAT_READOUT_1 0x00409668` is a second, less-guarded door | Two registers naming the same state | Both return `0xbadf5040` on **all fifteen** probed cards. No read path, let alone a write path | 2026-05-07 |
| The FUSECTRL software fuse-override path | The override mechanism exists and is documented | `FUSE_EN_SW_OVERRIDE 0x00820040` = `0x00000000` and `DISABLE_SW_OVERRIDE_STATUS 0x00820084` = `0x00000001`. A GA10x control card has `EN_SW_OVERRIDE = 1`, proving the register works and that it was deliberately closed here | 2026-07-19 / 25 |
| The 25-entry `CTRL_OPT` table in the unsigned FwSec tail is free real estate | It is unsigned and editable and it controls floorsweep | Inert on the 170HX and on the Drive A100 because `FUSE_EN_SW_OVERRIDE = 0`, and every `CTRL_OPT_*` register reads `0x00000000` anyway | 2026-05-31 |
| `PBUS_SW_SCRATCH(1)` bit 14 skips the FWSEC loop that zeroes `CTRL_OPT` | `0x001404` reads `0x20042000` with bit 14 clear on both SKUs | Never write-tested, and moot: `CTRL_OPT` is already all-zero and the card is at its fuse floor, so flipping the bit cannot add SMs even if the belief is right. Auxiliary lead `0x00118f78` reads 0 on both the CMP and the A100 reference | 2026-07-24 |
| MODS `IssueRateOverride` | A first-party NVIDIA tool with exactly the right function name | Useless on production hardware: debug features are disabled and privilege level masks are set strict | 2026-04-21 |
| Patching the PTX just-in-time compiler | The target function carries the string "Enables (disables) the contraction of floating-point multiplies..." and its ninth argument is true | Recovered only a portion of the expected FLOPS | April 2026 |
| `jonpry/sass_fma`, a SASS-level rewriter | Published, real, Linux-native | Uses an unsupported CUDA binary loading API and was never validated, because its author only had a Volta card ("this should work to at least get 50% performance") | April 2026 |
| Physically re-fusing the silicon | Named as an attack path in 2024 | Never attempted, and made moot by the override register | 2024 |
| Extracting NVIDIA's private key, or using leaked Booter keys | Would collapse the whole problem | Retail GA100 and GA10x Booters use different AES keys and, by assumption, different RSA keys. No encryption keys were ever leaked, "or the whole exploit would be unnecessary in the first place" | 2026-07-19 |
| Reusing the exploit on Turing CMP cards (50HX, Turing 90HX) | Same vendor, same throttling story | Turing uses a different throttling register and a different mask that none of the exploits touch. On the 50HX, `FEATURE_OVERRIDE_PRIV_LEVEL_MASK` at `0x00019400` returns `0xdead____` on every read regardless of method; both mask and throttle registers were touched, neither responded, and writing `0xFFFFFFFF` failed. Two days of attempts, all identical | 2026-07-15 / 19 |
| Reusing the 170HX mask value on GA102 | Same architecture family | `0xFFFFFFFF` is wrong for GA102 and must be `0xFFFFF3FF` because other bits are fused; a second mask (`0x00823B04`) and a third data register (`0x00823830`) are also needed. Whether even that works is unknown, and no success report exists | 2026-07-17 |
| Applying NVIDIA-patcher to a 170HX for compute | It is the known tool for unlocking NVIDIA sandbagging | Produces a GeForce GPU with **error 43**. The sandbagging it removes affects only DirectX, OpenGL and Vulkan, never CUDA or OpenCL | (recorded 2026-07) |
| `--fmad=false` as a route to gaming on these cards | The flag recovers large factors in compute kernels | Game engines cannot practically be recompiled with it, and even where the graphics-API sandbag is removed (recovering 4 fps to 50 fps) the fuse-based FP32 issue-rate throttle is untouched. Confirmed by BeamNG: 15 fps at Gen1 x16 with the capacitor mod, 5 fps at x4, "still awful" | 2026-03-25 / 2026-07-21 |
| The FMA-shadow trick generalises across the CMP line | It works on the 170HX | On the CMP 90HX it made FP32 **worse**, dropping 0.710 to 0.355 TFLOPS, from 1/32 rate to 1/64 | 2025-04-08 |
| Gaming FPS is a valid way to verify a compute unlock | The unlock is described as restoring "full SM throughput" | One tester measured identical FPS with and without the compute unlock while LLM and CUTLASS throughput clearly changed | 2026-07-14 |
| Partitioning the unlocked card with MIG | MIG is a standard A100 feature on the same die | Only `1g.64gb` exists; standard A100 profiles return `Invalid Argument`. Adding profiles was identified as the prerequisite and was never done | 2026-07-22 |
| "1 petaTOPS of INT1" as a usable headline | It appears in specification material | GA100's INT1 path is XNOR-popcount binary GEMM sharing the INT8 tensor path with no dedicated INT1 unit, and real 1-bit and ternary models multiply 1-bit weights against higher-precision activations, so INT8 math is what actually runs. Marked **disputed, never resolved with a measurement** | 2026-07-15 |
| "Unlocked 8 GB 170HX becomes 70/108 of A100 compute with 32 GB VRAM" | The compute ratio is a defensible estimate | The 32 GB figure is simply wrong: the 8 GB card unlocks to **64 GB**. Also, the unlock is an SM *speed-select* override, not an SM-count change, so "70/108 of A100 compute" describes the harvest, not the unlock | 2026-06-29 |
| "Every Turing GPU can do 8:1 non-tensor FP16" | Derived from a published 8:1 FP16 rate for the Tesla T4 (64.8 to 65 TFLOPS), implying a CMP 50HX could reach ~90 TFLOPS | Refuted the same day: that figure is a tensor-core number and the T4 datasheet quotes it in mixed-precision mode. The useful comparison that survived: unlocked 170HX is roughly 50 TFLOPS scalar and roughly 200 TFLOPS tensor | 2026-07-16 |
| "My 8 GB card only has 56 SM" | An early first-hand report, and a smaller SM count is a natural way to bin a smaller SKU | Fuse reads showed all SMs undamaged with the standard 4480 CUDA cores in 70 SMs enabled. A PTX special-register dump on a live `0x20C2` card reports `SMs=70` with smid values 0 to 69. The 56 SM figure appears in a community wiki and in third-party spec databases and is inherited error | 2026-07-13, restated 2026-07-19 |

### Tuning dead ends

Every entry here was measured on hardware in a single 2026-07-27 session and is directly useful to
anyone tuning a card. See [tuning](../operations/tuning.md).

| Hypothesis | What disproved it |
|---|---|
| Clock ceilings above 1650 MHz buy performance | 1700 MHz and 1740 MHz ceilings both deliver roughly 1600 MHz effective and 213 to 214 TFLOPS, no better than 1650 MHz at 214.7 TFLOPS. The silicon caps at about 1604 to 1614 MHz at +350 |
| Raising the power limit unlocks performance | The card never reaches its 250 W cap on the tested workload; it is voltage-frequency limited near 190 to 200 W. Raising the cap to 300 W alone changed nothing measurable |
| `nvidia-smi -pl` is the right tuning knob | Under a power cap the clock oscillates around the cap and efficiency is worse everywhere than a pinned clock ceiling: 1240 GFLOPS/W versus 1286 GFLOPS/W in a same-card head-to-head |
| Lock the clock as `<max>,<max>` | Works, but blocks idle downclocking; the card no longer drops to 210 MHz and roughly 40 to 54 W. The shipped form is `210,<max>` |
| Efficiency can be interpolated between measured clock and offset pairs | Response is non-monotonic once the clock stretcher engages. 1590/+400 hangs while 1650/+400 runs, and the arbiter silently fails to reach requested clocks at low offsets (1650/+250 gives 1067 GFLOPS/W against 1149 GFLOPS/W at +350). Every pair must be measured |
| Two clean sweeps qualify an overclock profile | The `eff` profile shipped at +400/1350 on two clean sweeps; a later sweep returned `mem_errors=1`. Backed down to +250/1350 for the same roughly 132 W with about 150 MHz more margin, which then passed a four-sweep gate |

> [!WARNING]
> **Experimental**
>
> `nvidia-smi` reports `clocks.max.sm = 1935 MHz` on an unlocked card. This is a **reported field,
> not an achievable clock**, and it rests on a single unre-checked report. The VBIOS table maximum
> graphics clock is 1695 MHz and the practical silicon ceiling is about 1604 to 1614 MHz at +350
> offset. Sustained SM clock is **1410 MHz**, or 1470 MHz at `-pl 300`. Do not plan around 1935 MHz.

---

## Memory geometry and capacity

### The L2/LTC address-map wall at `0x17E22C`

This was the team's working root-cause model for the capacity limit for over a week, and it was
wrong.

**Hypothesis.** GSP-RM derives usable framebuffer size from the L2/LTC address map at `0x17E22C`,
whose value is `fbSize >> 28` and is latched by DEVINIT at 10 GB. Therefore real capacity above
10 GB requires the address map to be programmed, and opening the LTC privilege level masks at
`0x17E0xx` requires an in-driver `kgspExecuteBooterLoad`.

**Plausible because** it was recorded as ROOT-CAUSE on 2026-07-14 with supporting detail: the value
is a read-only mirror from the host, bits [24:22] are unwritable even from high-secure mode, and the
target value `0x00a00404` for 40 GB would not latch at runtime. The native value `0x28` matches
10 GiB exactly. The model correctly predicted several intermediate observations, which is precisely
what made it durable.

**Disproved by** a single run on 2026-07-22 that reached real 40 GB with `0x17E22C` sitting at its
native `0x00280404` the entire time, never programmed. The chain header records the correction
verbatim: `CORRECTED 2026-07-22: usable fbSize tracks LMR(0x100CE0)+CFG1+CSTATUS (all
fire-writable), NOT the amap 0x17E22C.` The standing confirmation is that the shipping driver
contains no `0x17Exxxx` address anywhere, in master or in any of the twelve branch snapshots.

**Abandoned** 2026-07-22. One real register fact survived the retraction: **bit 23 of `0x17E22C` is
fuse-locked**.

The honest self-assessment recorded alongside it is worth quoting in substance: the open-source
CPU-side RM in `kern_mem_sys_gp102.c` computes framebuffer size from LMR `0x100CE0`, not from
`0x17E22C`; and with GSP firmware enabled, CPU-RM does not read that register at all, receiving
framebuffer size from GSP-RM over RPC in `GspStaticConfigInfo`. The label "`0x17E22C` = fbSize>>28"
came from prior notes inferred from the native value matching 10 GiB, not from reading firmware,
which the team had never disassembled.

A related claim, that the shipping driver's mask table writes the LTC-decode cluster
(`0x17E2B4` / `0x17E2A0` / `0x17E2E4` / `0x17E2FC`), is **false**. The shipping table has four
entries: `0x001fa7cc` to `0xfffff0ff`, `0x009a0148` to `0xffffffff`, `0x001fa7c4` to `0xffffffff`,
and `0x00823804` to `0xffffffff`.

### The 80 GB geometry for the 10 GB card

**Hypothesis.** The 10 GB card can take the 8 GB card's CFG1 value `0x02779000` with an 80 GiB
`fb_bytes` of `0x0000001400000000` and reach 81920 MiB, the same way the 8 GB card reaches 65536 MiB.

**Plausible because** it is a small delta from a working path, the commit history shows it was taken
seriously ("Trying an 80GB unlock instead of 40GB", then "Correct LMR for 80GB"), the geometry
registers accept it, the card boots, and `nvidia-smi` reports roughly 81920 MiB. PRAMIN separately
proved 80 distinct GiB of physical DRAM are present. The published paper also repeatedly states
10 GB to 80 GB (abstract "10 GB instead of 80 GB", Table 1 "Memory capacity (10 to 80 GB)").

**Disproved by** three independent testers within one to two days of the branch appearing:
`cuda_memtest` hangs above 39 GiB, model loads failing above roughly 20 GB, and a second tester
seeing failures in the 40 to 60 GB range. Reverting to the 40 GB geometry restored working loads.
The paper's own stability data agrees with the refutation: 2,796 errors in one gpu-burn run at 80 GB
while the same card ran cleanly at 40 GB.

**Abandoned** 2026-07-19 to 2026-07-20. Master ships 40 GB for the 10 GB card:
CFG1 `0x02669000`, LMR `0x0000028A`, `fb_bytes 0x0000000A00000000`.

> [!CAUTION]
> **The `80` branch is internally incoherent as built**
>
> The branch's `common/constants.yaml` says `lmr: "0x0000028B"`, and `0x28B` is arithmetically the
> correct LMR for 81920 MiB. But `build.sh` never reads `constants.yaml`. On that branch,
> `driver/build.sh` line 93 sets `LMR="0x0000028A"`, `install.sh` line 138 prints
> `Unlock geometry: 80GB (CFG1=0x02779000 LMR=0x0000028A)`, and
> `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` line 144 bakes `lmrValue = 0x0000028AU`. The
> build-time Python rewrite is short-circuited because the dual-device guard finds all seven
> markers it looks for and exits early. **Commit `3c53aca` "Correct LMR for 80GB" changed only
> inert metadata.** Every tester who ran the `80` branch programmed CFG1 `0x02779000` (4096 MiB
> per FBPA, 81920 MiB of FBPA geometry) alongside an LMR declaring 40960 MiB to the MMU and a
> `targetFbBytes` of 80 GiB to GSP: a three-way disagreement that exactly predicts the reported
> behaviour, namely that `nvidia-smi` reports 80 GB, the hardware decodes 40 GiB, and the alias
> test folds at precisely 40 GiB. No *build* of the branch has ever carried a coherent `0x28B`
> triple. The coherent register set was reached separately, by a clean-room refire script, and
> the fold did not appear there: see [The 80 GB problem](../frontier/80gb.md).

Two further corrections to the record around this branch:

- **"No patch file differs from master" is wrong.** Byte comparison shows `0002` through `0006` are
  identical, but `0001-sec2-postbl-plm-ss-cfg.patch` differs in exactly two lines:
  `cfg1Value = 0x02669000U` becomes `0x02779000U`, and `targetFbBytes ... 0x0000000A00000000ULL`
  becomes `0x0000001400000000ULL`. The branch also changes `build.sh`, `install.sh` and
  `constants.yaml`.
- **"80 GB requires some SMD components to be soldered on" is wrong.** No hardware modification is
  needed to reach 80 GB, and none is known to stabilise it. This was corroborated empirically on
  2026-07-25 when an unmodified 10 GB card reached the same 80 GB state with the refire script.

See [the 80 GB frontier page](../frontier/80gb.md) for what remains open.

### Attempts to stabilise the 80 GB configuration

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| Doubling the HBM refresh rate (`CONFIG4 = 0xc403001a`, refresh = 26) fixes retention | Physically motivated: the 80 GB fire doubles reachable rows (CSTATUS `0x800` to `0x1000`) while refresh stays at the 2 GB per channel rate, so roughly half the rows miss retention. It explained both the paper's 2,796 errors and the community's Xid 154. It even landed cleanly on all 20 live FBPAs | Refuted the same day by two testers. Instability persisted, and bandwidth collapsed from 1416 to 1422 GiB/s (98% of peak) down to 848 to 888 GiB/s (59 to 61%) at low offsets, and from 1147 to 1151 GiB/s down to roughly 782 to 823 GiB/s at high offsets. The profile did flatten but at a large absolute cost. Verdict recorded in-channel: "refresh timing is like using a strait-jacket as a bandage" | 2026-07-25 |
| Power-limiting to 100 W fixes it | The 80 GB configuration was the only one failing and the board is VRM-depopulated | Self-retracted by the reporter within two minutes ("hmm nevermind. it's hanging again"), reproduced as still-failing by a second tester the same hour, and decisively killed by the observation that the cards **never drew above roughly 80 W during the failing load**, so a 100 W ceiling was never binding | 2026-07-20 |
| The trimmed VRM is the cause | The board really is missing 3 MOSFETs and coils per side versus an A100 80 GB | Argued against three ways: it fails regardless of power limit; the roughly 80 W draw during failures; and the 8 GB card has **identical** power delivery and is entirely stable at 64 GB. Electrically, the GPU does not sense VRM phase count, a VRM runs fine under load with half its MOSFETs populated, and the PWM controller would have to be reconfigured for added phases to do anything. Nobody ever repopulated a VRM to test it directly, so this is argued rather than formally refuted | 2026-06-26 proposed, 2026-07-20 to 26 argued down |
| Underclocking the memory | Reduced memory clock is the classic stability lever | The tester could not adjust clocks at all; on the 10 GB card the memory clock is locked at 1215 MHz. Follow-on suggestions (TechPowerUp VBIOSes, HiveOS, enumerating in Windows for an Afterburner-style tool) were never reported as tried | 2026-07-19 / 20 |
| A waterblock fixes it, because the retail A100 80 GB has no integrated heat spreader while the 170HX does | It correctly identifies a real physical difference | Never tested, and undercut by the roughly 80 W draw measurement: the failing cards are not thermally limited | 2026-07-20 |
| Holding HBM hotspot under 60 C cures it via reduced charge leakage | Published work shows leakage current roughly doubling per 10 C | Countered immediately: sub-60 C would be far below the 80 C-plus at which the rest of the HBM2e on these cards is demonstrably stable. Never tested; no refresh-rate register was identified at the time | 2026-07-20 |
| Modding the HBM voltage rail upward | A standard memory-stability lever | Nobody executed it, no controller was identified, no rail voltage was ever measured. Additional deterrent recorded later: Samsung HBM2 "does not like having its voltages messed with", and faulty HBM can be permanently fused out inside the stack | 2026-07-20 onward |
| "The instability is a driver bug, not the memory", because a genuine VRAM failure would crash the system and de-enumerate the card whereas only the CUDA application dies | The observation is accurate and the reasoning is superficially sound | Rebutted the same day: VRAM bit errors normally do **not** crash a driver. They silently return wrong values and kill the consumer, which is exactly the observed symptom | 2026-07-26 |
| Xid 31 is the 80 GB failure signature | Xid codes are the natural fingerprint to look for | At 80 GB, kernels touching more than roughly 40 GB cause fatal GPU loss, independent of power limit. Reported Xid codes include Xid 31 (described as harmless) and Xid 154 after CUDA memory tests; the dominant reported symptom is hangs. Xid 31 alone was suggested by a bystander and was not corroborated as *the* signature by the operator with the failing card. Treat the code as unestablished; the threshold itself is not in doubt | 2026-07-20 |
| "1 memory error in 20 to 30 minutes of `cuda_memtest` on 80 GB", i.e. nearly viable | It was a first-hand measurement from an active tester and the only positive 80 GB data point anyone had | Self-retracted hours later: the run had accidentally targeted a second GPU in the machine. The tester confirmed "I have yet to run anything successfully on 80GB yet". This is the origin of the short-lived belief that 80 GB was "mostly working" | 2026-07-20 |

### Capacity above 64 GB

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| 96 GB on the 8 GB card by raising LMR further | LMR had already proved to be the size selector, and an A100 96 GB exists as an OEM-exclusive part | The tool author tried it and got a rejected boot with no POST. Reinforced by fuse readout: the disabled FBPs read `FBP_DEFECTIVE = 0x840` with `STATUS_HALF_FBPA = 0` and `DISABLE == DEFECTIVE`, i.e. genuinely dead silicon. 96 GB needs 24 live FBPAs; the 8 GB card has 16. In-channel verdict: "96GB is almost definitely impossible on either 170HX" | 2026-07-19 |
| A per-stack half-capacity fuse bit in `FUSE_HALF_FBPA_EN` (`0x82049C`) plus `STATUS_HALF_FBPA` (`0x820C00`) yields "96 to 128 GB" | The registers exist, the probe catalog flags them CRITICAL, and a half-capacity fuse is exactly the kind of lever NVIDIA uses | Probes of an 8 GB card, a 10 GB card and an `0x20bb` A100-class card **all read `0x00000000` in both registers**. Nothing was running at half capacity, so there was nothing to clear | 2026-07-12 |
| Software re-enable of floorswept FBPAs via `EN_SW_OVERRIDE` plus "unmask all" to `CTRL_OPT_FBPA` | The override register exists and is writable | On hardware: `EN_SW_OVERRIDE` moved `0x0` to `0x1` (the write took), but `DISABLE_SW_OVERRIDE_STATUS` stayed `0x1`, `CTRL_OPT_FBPA` stayed `0x0`, and the effective mask `STATUS_FBPA` did not move from `0x00c0330c` | 2026-07-14 |
| `CTRL_OPT_FBPA` (`0x820818`) = `0xFFFFFFFF` as a fuse-merge override | Part of a coherent speculative target list | Never demonstrated to do anything; the register reads `0x00000000`, and the same dump corrected two of the three addresses in the list | 2026-07-12, superseded 2026-07-19 |
| Set the `*_DISABLE` bitmasks equal to the `*_DEFECTIVE` bitmasks so only genuinely bad partitions stay off | A real and general technique, with candidate registers identified (`0x00820364`, `0x00820368`, `0x0082036C`, `0x008202C4` against `0x008205CC`, `0x008205D0`, `0x008205D4`, `0x008205E8`) | On the tested 10 GB card the delta is empty: `FBP_DEFECTIVE` = `FBP_DISABLE` = `0x840`, and `STATUS_HALF_FBPA` = 0 means no half-capacity fuses to recover. **Not closed in general**: a community dump shows `FBP_DISABLE = 0x852` against `FBP_DEFECTIVE = 0x840`, a non-empty delta. The intended 8 GB-card test was never reported | 2026-07-12 to 14 |
| The 8 GB cards were cut down from 96 GB parts, so 32 GB is still hidden | Reasonable given the 64 GB result | Nobody defended it after the 64 GB result landed. Current reading: cut down from 80 GB with one stack disabled and four partially enabled, and only the partially disabled portions are recoverable | 2026-07-20 to 25 |
| Post-boot LTC companion write `0x1402b4 = 0x00a00030` holds the fold in place | Every other visible register had been made to match a real A100 80 GB | Writing it post-boot did not move the fold, which still landed at exactly 40 GiB with PMA = 79 GB and `fb_length` = 80 GB both confirmed. Not fully closed | 2026-07-19 |

### Wrong registers, wrong addresses, wrong decodes

| Claim | What it actually is | Date |
|---|---|---|
| Per-stack VRAM straps at `0x82381C + N*4` with strides `0x00, 0x04, 0x08, 0x0C, 0x10, 0x14`, each written `0x02779000`, to reach 96 GB | That is the compute-throttle block. `0x0082381c` is `FEATURE_OVERRIDE_SM_SPEED_SELECT`, `0x00823820` is `..._SM_SPEED_SELECT_1`, `0x00823824` is `FEATURE_OVERRIDE_ROW_REMAPPER`, `0x00823828` is `FEATURE_READOUT_2`, `0x0082382c` is `FEATURE_OVERRIDE_ECC_2`. The real per-partition path is per-FBPA CFG1 at `0x00900204 + n*0x4000`, and the working unlock reaches 64 GB with a **single broadcast write** | 2026-07-12 |
| Per-FBPA unicast CFG1 near the broadcast register with stride `0x1000` (`0x009a1204`, `0x009a2204`, ...) | Garbage and decode-error sentinels: `0x0007fff0`, `0x00000000`, `0xbadf1002`, `0xbadf4000`. The correct aperture is `0x00900204 + n*0x4000` for n = 0 to 23, with the broadcast window at `0x009A0000` to `0x009A3FFF` | 2026-07-20 |
| LMR lives at `0x1183A4` | That is the local-memory-range location for **GP102**. The verified GA100 MMU LMR is `0x00100ce0` | 2026-07-05 |
| The LMR mask is `0x1FA7C0`, and opening the `0x1FA7C0` to `0x1FA7CC` cluster lets host PL0 write the LMR | Retracted 2026-07-12: the effect was host-write-only and the high-secure LMR write sticks with the cluster closed because the LMR is post-latched. The real register is `0x1FA7C4`, the `dev_fb.h`-named `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE__PRIV_LEVEL_MASK`. `0x001fa7c0` appears nowhere in the shipping tree. A practical hazard survives: writing `0x1FA7C0` first in a multiwrite chain faults the chain | 2026-07-08 to 12 |
| The MMU memory-lock range (`0x1FA82C` / `0x1FA830`, mask `0x1FA7C8`) caps usable VRAM | The mask reads `0x4cb8f` with write nibble `0x8` (level 3 or high-secure only) and the host cannot write it, which looks exactly like a capacity guard. But the range it protects is empty: LO = `0x1ffffff0`, HI = 0. AHESASC disables the range before the host ever sees it. Recorded verbatim as "dead thread, does not cap our memory" | 2026-07-16 |
| `CONFIG4` is at `0x9A0210` | Repeated on-card reads showed `0x9A0210` wandering `0x7575` to `0x5252` to `0x3535` to `0x1a1a` to `0x0101` within one loop, the signature of PUT/GET queue pointers, while `0x9A02A0` read a rock-stable `0xc4030033` | 2026-07-25 |
| CFG1 should be `0x22779000` with bit 29 as DUAL_RANK | The analysis got `0x02779000` exactly right, which lent credibility to the rest, but the DUAL_RANK reading of bit 29 is unsupported and the shipping driver writes `0x02779000` with no bit 29. The value `0x22779000` is not fictional: the 2026-07-27 PMU-devinit run landed CFG1 = `0x22779000` on a live 170HX and still resolved to 40960 MiB because tier `0x77` was halved (see the memory-timing table below), and a PG199 A100 reads `0x22779000` as its **stock** CFG1. What is refuted is that setting bit 29 buys capacity | 2026-07-18 |
| `FBPA_CFG0` is `CMP170HX=0x24490000, A100=0x26690000` | A live 170HX reads `0x07981800` at `0x009a0200`, identically on all 20 live per-FBPA instances and on three A100 SKUs; the GA100 reference card reads `0x06981800` and an RTX 3070 reads `0x069f9803`. The quoted pair are the known **CFG1** values `0x02449000` and `0x02669000` shifted one nibble left and attached to the wrong register | 2026-07-25 |
| CFG1 values `0x26690000`, `0x27790000`, `0x24490000` | Nibble-shifted transcription slips. The verified forms are `0x02669000`, `0x02779000` and `0x02449000` | ongoing |
| `0x009a0148` is the LMR register | It is the FBPA privilege level mask, opened to `0xffffffff`. The LMR value goes to `0x00100ce0` | ongoing |
| LMR `0x40A` gives 64 GB on a 10 GB card | Two problems at once. `0x40A` is the wrong target for that SKU, and it does not decode: under `size_MiB = MAG[9:4] << SCALE[3:0]`, `(0x40A >> 4) & 0x3F = 0`, so magnitude is zero with a stray bit 10 set. In the posted 2026-07-11 run neither register moved at all (`LMR=0x288[want 0x40A] CFG1=0x2449000[want 0x2779000]`), so it was a mask failure layered on a wrong target | 2026-07-11 |
| LMR `0x050A` gives 80 GB | `(0x50A >> 4) & 0x3F = 0x10 = 16`, so it decodes to 16384 MiB, not 81920 MiB. The rule is exact for all five values in real use (`0x208`, `0x288`, `0x20B`, `0x28A`, `0x28B`); `0x40A` and `0x50A` are refuted candidates, not observed encodings | adjudicated 2026-07-28 |
| "The 40 GB guide's FBPA 4, 5, 10 and 11 are physically disabled" | The silicon probe of a 10 GB card shows `FUSE_FBPA_DISABLE = 0x000000c3`, i.e. FBPAs **0, 1, 6 and 7**, and `FUSE_FBP_DISABLE = 0x9`, i.e. FBPs 0 and 3. The five-of-six-stacks conclusion is right; the specific indices are wrong | flagged 2026-07-22 |
| The VBIOS strap-table byte at entry+3 encodes HBM stack height | The leaked GA100 sim and emu ROMs kill it: sim 4-Hi and sim HBM2e have identical entry+3 patterns despite different tier bytes (`66` versus `77`), and the sim baseline is uniformly `02` | 2026-05-31 |
| The strap-table offset is `0x41F52` | Corrected to `0x41D53`. The earlier offset sat 529 bytes past the actual table on 250 W ROMs and landed near where the 300 W ROM's table would be. Consequence: the whole earlier "memory unlock via VBIOS edit does not work" result is **invalid as evidence** | 2026-05-05 |

### Measurement traps

**The 4 GiB `cuMemGetInfo` result.** On 2026-07-22, after a no-FLR GSP-RM boot, `cuMemGetInfo`
reported `total = 4.00 GiB`. It was plausible because it arrived with a self-consistent allocation
pattern: 36, 20 and 12 GiB allocations failing with `r=1` while 10 GiB succeeded. It was disproved
the following morning by non-replication and by identifying a **ctypes bug in the test harness that
truncated a 64-bit `size_t` to 32 bits**. The same session then measured 39.67 GiB total and
39.39 GiB free. This is the archetype of the class: the number was wrong, the tool was wrong, and
the corroborating pattern was coincidence.

**Naive memory-fold tests without L2 eviction.** Early fold checks reported an apparent fold at 37
to 38 GiB. The corrected methodology floods 1 GB to evict L2 before re-reading tags, after which no
fold appears. **Any fold result taken before 2026-07-22 that did not evict L2 should be discarded.**

**The fold harness itself was unreliable.** A control run after a secondary bus reset back to
consistent native state (10240 MiB, driver 610.43.03, CFG1 `0x02449000`, address map `0x00280404`)
allocated 9 GiB of genuinely native memory and reported "4608 chunks, 4608 corrupt/aliased" across
five passes, i.e. native memory folding, which is impossible. Earlier the same harness reported
10 GiB as "5120 chunks verified, 5120 aliased/corrupt" at roughly 26.6 GB/s on pass 1 then roughly
197 to 198 GB/s on passes 2 to 5. This retroactively invalidated a body of earlier fold-at-40 GB
conclusions.

**The sparse memory probe.** Superficially a reasonable optimisation over a dense scan, and it was
actually used. It gives false negatives on a folded card because the fold aliases at a
channel-interleave offset (`LOW[0]` maps to `40GiB[+576]`), so it writes one partner and checks a
different address. The source instruction is explicit: do not optimise the dense scan into a sparse
scan.

**"`nvidia-smi` shows it, therefore it exists."** An early manual flow forced `fb_size` to roughly
80 GB from `nv-linux.c` and set the `uvm_gpu` heap to 81920 MB while `STRAP` and `LMR` carried the
64 GB values (`0x9A0204 = 0x02779000`, `0x100CE0 = 0x0000020B`). The reported 80 GB was a
driver-side display override sitting on top of a 64 GB geometry. Every later log from that lineage
reports `fbTotal=65536MB`. This explains a whole class of misleading early screenshots and is the
origin of the dense-tag validation standard. See [verification](../procedures/verify.md).

**"PRAMIN shows REAL memory up to 159 GiB with LMR `0x28c`."** The log flagged readbacks as REAL at
64, 72, 76, 78, 79, 80, 81, 82, 84, 88, 96, 112, 128 and 159 GiB, with interference tests reported
as independent. The arithmetic is genuinely consistent, since `0x28c` decodes to 163840 MiB. But the
same run ended `recovered cap=10240 MiB`, the author treated it as a joke, and on 2026-07-12
disowned the whole memory analysis. Date: 2026-07-07.

**"Bandwidth above 10 GB collapses to 32 GiB/s because the HBM is untrained."** The first sweep
literally showed 1 GB memset at 1449 GiB/s (100%), 4 GB at 1446 (100%), 8 GB at 1251 (86%), 16 GB at
1242 (86%), and 32 GB and above dropping to 32 GiB/s, and "untrained" was the reigning explanation
for every 80 GB symptom. An offset sweep the same day showed a uniform **79% of peak from 8 GB all
the way to 76 GB with no dead zones**. The 32 GiB/s reading was an artefact of the sweep test
exhausting the single CUDA context. Date: 2026-07-25.

### Memory clock and timing

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| HBM memory overclocking through the FBPA PLL coefficients | Properly tested with a kernel-module patch, and the registers accept the value with the PLL lock bit setting | A clean measurement with a causal control: underclocking works (NDIV 65, roughly -6.25% clock giving -6.8% bandwidth) but up-clocking does nothing (NDIV 70, coefficient `0x00014601`, +4.9% requested, **identical bandwidth, zero errors, no roll-off**). Zero gain with no errors and no roll-off is the signature of a hard clamp at the trained rate. Two supporting facts explain it: no Memory Clock Table exists in any of 8 ROMs, so the rate comes from FWSEC devinit at POST, and the part already runs 3.456 Gbps per pin against an HBM2e nominal of about 3.2. The source carries an explicit instruction not to re-run the sweep | 2026-07-27 |
| Writing the HBM `TIMING0` to `TIMING20` registers (`0x9A0220` to `0x9A028C`) | They are writable and they are the timing registers | Disproved by reading one bit rather than by a failed experiment: `CONFIG0.USE_TIMING_REGS` (bit 31 of `0x9A0290`) is **0** on this card, so the hardware uses the read-only `TIMING*_GEN` shadows and the writable copies are ignored. Read that bit first | 2026-07-25 |
| The PTRIM registers are the memory clock path | An 8-ROM hunt for the PLL coefficient encoding turned up 864 MHz PLLs, including an FBPA block at `0x903C7C` | A controlled boot-and-diff: boot at NDIV 60, a demonstrably lower delivered rate with read bandwidth 1574.7 GB/s, then diff the register dump. Only the FBPA PLL pair changed. The clamp is not in any reachable PTRIM register | 2026-07-27 |
| Re-running devinit at runtime applies better timings for the unlocked region | Devinit programs exactly the registers in question | FBFLCN's HBM training pass is skipped on a runtime re-execute (`TRAINING_STATUS 0x9a0974` reads 0 before and after, every time), so the controller's timing shadow moves while the DRAM stays calibrated for the boot strap, and `RmInitAdapter` rejects the mismatch with `0x62:0x40:2862`. Silver lining: this established that **capacity** is unaffected, because row, bank and column addressing is combinational | 2026-07-27 |
| PMU devinit re-execution reaches a larger geometry | It genuinely moved the hardware: CFG1 to `0x22779000` and 6 of 7 HBM timing registers to strap-5 values | The geometry still resolved to 40960 MiB because tier `0x77` was halved, and strap 5 timings would not load at all | 2026-07-27 |
| Clocking the Samsung memory **up** to 1512 MHz will stabilise it | The observation is real: an A100 80 GB delivers 1.94 TB/s at 1512 MHz while the 170HX delivers 1.59 TB/s at 1215 MHz | Countered immediately with the vendor explanation (Hynix versus Samsung silicon, different capability) and disclaimed by the poster. **Never tested** | 2026-07-20 |
| HBM refresh-rate tuning per the published paper stabilises over-provisioned capacity | The paper reports stabilising a card at the cost of bandwidth | Applied successfully but never stable enough to be usable; the paper's result "was stabilized at the cost of reducing bandwidth, but it was not reproduced". The blocker was later re-described as memory training rather than refresh interval. Unsettled, but it has consumed effort without producing a usable configuration | as of 2026-07-27 |
| `FBPA_MRS_8` / MR8 Density is the capacity mechanism, telling the stacks they are smaller than they are | It is exactly the right kind of register | Disproved by uniformity: `0x009A0320` reads `0x00200000` on **all 15 cards**, including a 10 GB CMP, a 40 GB A100 and an 80 GB A100 | 2026-05-31 |
| `FBPA_VEND_ID_C0` / `C1` identify the HBM stacks | FBIO vendor and device ID registers should carry identity | Both `0x009A0838` and `0x009A083C` read `0x00000000` on all 15 cards. Identity has to come from the IEEE 1500 bridge instead | 2026-05-31 |

### Beliefs about the silicon itself

| Belief | What replaced it | Date |
|---|---|---|
| "The cards really do have 2 GB HBM2 stacks and nothing is locked", concluding "this card is worthless" | Arithmetically consistent (HBM2 stacks have a fixed 1024-bit bus regardless of capacity, so 8 GB = 4 stacks and 10 GB = 5 stacks) but refuted on industry grounds: the minimum HBM2 stack is 4 Gb with 8 Gb most common, so 2 Gb stacks do not exist. Definitively refuted by the July 2026 unlock addressing 64 GB on an 8 GB card | 2026-05-01, refuted 2026-05-20 |
| "The 8 GB cap is unbreakable because of firmware signing" | The pessimism about VBIOS modding turned out correct; the conclusion did not. The unlock bypasses the VBIOS entirely by opening masks through repeated Booter Load passes with a crafted signature buffer | 2023-10-25 |
| "The 8 GB card can only reach 32 GB", on the reasoning that it is A100-40GB-class silicon with an integrated heat spreader | Recognising it as A100-80GB-class with 16 GB Hynix stacks moved the ceiling to 64 GB. This belief had real cost: one researcher bought four 10 GB cards on the strength of it, then ordered seven 8 GB cards after the reversal | retracted 2026-07-19 / 20 |
| "The 64 GB card's memory is unevenly striped, 48 GB fast then 16 GB slow" | A GTX 970-style partition fear, plausible because 8 of 12 half-stacks enabled across 6 stacks would make two stacks twice the size of the other four. Corrected: each half-stack is its own independent 512-bit channel, the card reads the full 4096-bit width at once, and a full stack does not share bandwidth. The originator accepted the correction | 2026-07-20 |
| "One whole HBM stack is reserved for ECC on an 80 GB A100, so all six give 96 GB" | Proposed and retracted within hours once per-FBPA `CSTATUS_RAMAMOUNT` numbers were posted: `0x07ff` against `0x0800` shows ECC costs about 1/2048 of a stack's addressable range, not a whole stack | 2026-07-07 |
| "CMP 100HX cards hide HBM capacity the same way" | Countered on mechanism: on 100HX parts full stack height is already available and only whole stacks are disabled, whereas the 170HX hides upper layers on already-accessible stacks. No 100HX was ever probed, so this is a soft dead end | 2026-06-25 |
| "Stock RM rewrites the geometry back on every boot" | An AI-generated hypothesis, plausible because reversions were being observed. Refuted by measurement: after a full clean-driver boot and after a driver unload and reload with no secondary bus reset, `0x009a0204` still read `0x02669000` and `0x00100ce0` still read `0x0000028a`. The observed reversions were traced to **operator-induced FLRs** | 2026-07-22 |
| Late-production 170HX cards were fully functional dies binned purely to create the SKU | Explicitly flagged as unsubstantiated by the person repeating it, and countered by a corporate-statement position that CMP is made from yields unusable for datacenter or consumer parts. No per-card defect distribution was ever produced and no community benchmark database was built | 2026-07-16 |
| "Multi-card unlock failure is caused by defective HBM stacks on 8 GB cards" | Rejected the same day: the reporter reproduced the identical failure on a different rig holding a single 170HX, ruling out a per-card memory defect | 2026-07-19 |
| A retail listing's "Unlockable between 12GB to 64GB VRAM (Silicon Lottery)" | Recorded as **disputed rather than refuted**: no in-channel case of a failed 64 GB unlock on an 8 GB card was ever reported, but nobody ran a large enough sample to close it, and a fair counter-caution was raised that these are ex-mining cards | 2026-07-23 |

---

## Firmware, the Falcon and the Booter ROP

This is the densest domain in the archive. Almost every entry here is a case where a
plausible-looking constant, gadget address or exit strategy was carried forward for days before
disassembly or a hardware A/B settled it. See [Falcon and the Booter](../unlock/falcon-and-booter.md)
and [the ROP chain](../unlock/rop-chain.md) for what is true.

### "Software delivery of the memory unlock is architecturally impossible"

**Hypothesis.** A five-link catch-22, stated as proven and structural on 2026-07-12: the memory
strap requires heavy-secure mode to write; the Booter's single high-secure exit inherently stamps
the SEC2 reset mask at `0x8403C4` to `0x8f`; `0x8f` blocks the second load's Booter; only an FLR
clears `0x8f`; and an FLR reverts the framebuffer configuration to the read-only strap default.
Both candidate delivery architectures were declared walled, single-load by SEC2's double role at
CORE_RESUME and two-load by the `0x8f` taint. The stated "usable path" was a physical re-strap of
resistors R1004 and R1005.

**Plausible because** every link was independently observed and each one was true in isolation.

**Disproved twice within days.** On 2026-07-13 a Hello-World ucode proved SEC2 still runs code at
`0x8f`. On 2026-07-15 a `mutexfree` terminator exited with `resetPLM = 0xff` and no FLR at all. The
author wrote: "it overturns the documented 0x8f is unavoidable verdict."

**Abandoned** 2026-07-15. A related absolute, "`0x8f` is hardware-latched at the high-secure to
non-secure exit, therefore no exit can leave `0xff`", followed the same arc: the mechanism held, the
conclusion did not. Premature and spin-park exits that never run teardown, with an explicit
`0x8403C4 = 0xff` written last, do leave `0xff`.

The physical re-strap of R1004 and R1005 remains a real hardware option and was the honest
conclusion at the time. It is not what shipped.

### The "structural wall" for GSP boot

**Hypothesis (2026-07-10, 22:40).** GA100 GSP boot is architecturally incompatible with the
Booter-overflow exploit: boot requires a mid-boot GSP reset plus SEC2-driven reload, the single-shot
overflow hijacks the first SEC2 load, and the exploited SEC2 cannot service CORE_RESUME because it
is mask-locked, has its SCP keys wiped and has no bit-26 code path. "The exploit breaks exactly what
the boot needs."

**Plausible because** every attempt was failing with `0x62:0x55`.

**Disproved 2026-07-12, 15:20** by a control run: with a clean, non-tainting first load, the second
load booted all the way to `nvidia-smi` reporting 10240 MiB. The `0x55` was self-inflicted by the
ROP's own `WPR2_HI = 0` write clearing WPR2 (`0x55` is literally "can't load GSP-RM into WPR2"), and
the residual SEC2 taint came from the first load's own driver retry loop.

### Gadget, offset and constant errors

| Belief | Correction | Date |
|---|---|---|
| The signature buffer is at DMEM `0x200`, then IMEM, then DMEM `0x1800` (from immediates at `0x39cc`), then `0x0900` | DMEM **`0x800`**, established by binary search on payload size: the panic boundary sits at `0x5B40`, and `0x6340 - 0x5B40 = 0x800`. The guard address was known, so the boundary directly yields the buffer base | 2026-07-05 |
| The payload is `0xf700` bytes | `0xF800` (63,488). `0x800 + 0xF800 = 0x10000` exactly fills DMEM; `0xf700` stops `0x100` bytes (64 dwords) short of the top at base `0x800`, and only reached the top when paired with the superseded `0x0900` base. The shipping patch hardcodes `SEC2_POSTBL_TIMING_SIGNATURE_SIZE 0x0000f800ULL` | 2026-06-30 |
| The overflow smashes IMEM | DMEM only. The Falcon is Harvard-architecture with separate 16-bit address spaces. Consequence: the exploit is pure ROP, never code injection | 2026-06-30 |
| The BAR0 write routine is `0x0F40` | `0x10aa`. Self-corrected in the same message and settled by disassembly the same day | 2026-07-02 |
| `0x8137` is `main` and `0x27fa` is `booter_load_wpr_main` | `0x8137` is `booter_load_wrap`, `main` is at `0x7f82`, and `booter_load_wpr_main` is `0x22ba` | 2026-07-09 |
| `mpopaddret` stores registers in reverse order | `r0` sits at the **highest** address of the popped block. This also corrected an emulator bug that had `r10` two words too low; the silicon sweep put its real slot at +8. Getting it backwards puts the canary address in the wrong register and kills the chain in `__stack_chk_fail` at `0x7dd9` | 2026-07-05 / 07 |
| The return-address slot is `0xFFE4` | `0xFF5C`. `0xFFE4` is the far end of the useful payload for a rejoin chain, not the entry point | 2026-07-05 |
| The ROP entry point is DMEM `0xFF48`, "`0xFFFC - 0xFF48 + 4 = 0xB4 = 180 bytes = 45 words`" | The arithmetic is wrong on its own terms (`0xB4` is 180, plus 4 is 184 bytes or 46 words) and the entry point is `0xFF5C`. `0xFF48` is the `r3` slot in the `0x4d4` pop block, carrying the guard address `0x6340`. The usable region from `0xFF5C` to `0xFFFC` inclusive is `0xA4` = 164 bytes = 41 words. The surrounding claims (each `0x10b9` stanza consumes 6 words, payload is exactly 63,488 bytes) are correct | 2026-07-10 |
| CSB `0x9100` bit 31 is a busy or completion poll | It is a fault flag, `FALCON_CSBERRSTAT.VALID`. The code branches to a self-loop when the bit is set rather than looping while it is set. The same overview's constant table still carries the older wrong gloss | 2026-07-03 |
| The SEC2 mailboxes are at BAR0 `0x1000` (read) and `0x2000` (write) | Falcon I/O `0x1000` is MAILBOX0, host-visible at BAR0 `0x840040`, with MAILBOX1 at `0x840044`. Reading BAR0 `0x1000` from the host at PL0 returns `0xbadf5040`. GSP's own MAILBOX0 is a different register at `0x110040` | 2026-07-08 / 11 |
| `0xFFD4 = 0x8119` is the `0x22ba` frame return address | `0x814e`, which returns into `booter_load_wrap` at `0x8137`. Annotated by its own author: "NOT 0x8119 (that was my bug)". `0x8119` is the `secure_teardown` branch target reached from `main`'s epilogue when `$r0 == 0` | 2026-07-07 |
| The canary global is at `0x6440` | `0x6340`, seen throughout the disassembly and confirmed by the shipping payload. Treat `0x6440` as a one-off slip; a tidy but unreliable explanation is `0x5b40 + 0x900 = 0x6440`, which is what you get assuming the older documented DMA base of `0x0900` | 2026-07 |
| The pre-580 constant set: `PAYLOAD_SIZE = 0xF700`, `DMA_TARGET = 0x0900`, `CANARY_ADDR = 0x2C20`, `GADGET_BAR0_WRITE = 0x0F40`, `CANARY = 0x000700A6` | Refuted by direct byte-level search: `0x0F40`, `0x5889`, `0x2C20`, `0xFF40` and `0x000700A6` **do not appear in 580.159.03 at all**. The file was based on an unknown older driver version by someone who had abandoned the project. It was real independent work, aimed at a different binary | 2026-07-05 |
| Production-image gadget offsets (`0x0F40`, `0x0F20` x4, `0x19E7`, `0x5960`, `0x58E9`, `0x04D0`, `WPRMETA_ADDR 0x0600`, canary `0xDEAD2C20` at `0x2C20`), derived from `g_booteruc_load_ga100_prod` | Everything that actually worked targets the **debug-fused** image: `0x10b9`, `0x8119`, `0x810d`, `0x04d0`, `0x8262`, canary at `0x6340`. No later artifact reuses any of the `0x0F40` family | 2026-07-02 |
| `SP_DMA_INNER = 0xFF40` versus `0xFF48` (the builder flagged its own discrepancy) | Disproved by the annotated disassembly (`mov $r3 0x6340`) and by every working payload from 2026-07-05 onward | 2026-07-01 |
| Two mechanical payload bugs that silently ate writes | Slot `0xFF45` was a typo for `0xFF54` (offset 63316), write #1's `$r0` slot. And leaving `0x00008262` at slot `0xFFBC` made it act as a plain `ret`, so write #5's operands (SS1 `0x823820 = 0x00000008`) loaded at `0xFFB0` and `0xFFB4` but were never issued. Changing it to `0x000010b9` executes the write. Worth remembering as the class of bug where a chain "works" but silently drops its last write | 2026-07-08 |

### `0x10aa` and the write primitive

**Hypothesis (2026-07-02 to 03).** "`0x10aa` writes to predefined registers in BAR0. These addresses
cannot be changed... The `0x10aa` function is of no use, not even as parts for gadgets." Restated
more strongly the next day: "The `0x10aa` function is disinformation. Totally useless for us."

**Plausible because** the function does reference fixed-looking addresses, and `0x8224` looked like
a more direct write.

**Disproved by** counter-analysis showing that `0x1c100` and `0x1c200` are the BAR0 master's address
and data ports rather than final targets, and that the Booter itself routes `0x29b8` to `0x10aa` to
write its own WPR2 registers, proving `r0` and `r1` survive the intermediate `0x1064` and `0x8264`
calls. By 2026-07-06 the `full_0x10aa` chain was hardware-confirmed as the arbitrary high-secure
BAR0-master write. `0x10aa` is the write gadget planted in the shipping payload at offset `0xf788`.
The proposer conceded having got "a lot of useful information and hints from it".

**Abandoned** 2026-07-06.

Two related dead ends resolved alongside it:

- **"A BAR0-master ownership mutex at `0x1c300` is silently dropping our writes."** Plausible
  because `0x1c300` is referenced at `0x1042` and the hijacked flow skips whatever acquire the
  Booter performs during boot. Killed by two facts: the Falcon is single-core and single-threaded
  and needs no mutex for its own operation (any mutex only coordinates between different GPU
  processors), and the reconciliation analysis showed the chain's writes are byte-perfect and "the
  bug is entirely in the exit tail... The writes DO issue; the tail throws them away". Proposed
  2026-07-02, refuted 2026-07-11.
- **The "direct write" theory**, claiming gadget `0x8224` writes `BAR0[r10 & 0xFFFF] = r11`, works
  only for BAR0 offsets below `0xA800`, and that hardware applies a read-modify-write mask. It was
  plausible because four write and read-back pairs measured on a live card formed a tidy pattern:
  mask `0xFFFFFFFF` reading back `0xFFFFFF8F`, strap `0x02779000` reading back `0x02449000`, LMR
  `0x0000020B` reading back `0x00000208`, WPR2 `0x1FFFFE00` reading back `0x01F77000`. Disproved:
  `0x8224` is `csb_write`, which writes Falcon CSB space `I[r10]`, not external BAR0, so the
  "read-backs" were simply the **untouched stock values** of registers that were never written.
  `0xffffff8f`, `0x02449000` and `0x208` are precisely the documented stock values. Date 2026-07-15.

### The 16-bit address-truncation model

**Hypothesis.** The high-secure Falcon indirect write engine truncates 32-bit addresses to 16 bits,
so `0x009A0204` lands at `BAR0[0x0204]`, with a per-register PRI write mask filtering the value. A
variant claimed writes to `0x9A0204`, `0x100CE0`, `0x823804` and `0x1FA824` were actually landing at
`0x0204`, `0x0CE0`, `0x3804` and `0xA824`.

**Plausible because** those truncated offsets do read `0xbadf`, which looks like corroboration.

**Disproved by** every tool that actually landed writes: the 2026-07-08 poke generator, the
2026-07-22 refire chain and the shipping unlocker all pass **full 32-bit addresses** and read them
back at the full address. The model also cannot explain per-FBPA writes at `0x00900204 + n*0x4000`,
which share their low 16 bits. A related truncated write list (`0x00000204`, `0x00000CE0`,
`0x0000A7CC`) presented as BAR0-relative is internally inconsistent, since the same list keeps the
mask write at its full `0x00823804`, and no readback confirming a truncated write exists anywhere.

**Abandoned** 2026-07-13 to 2026-07-16. Treat it as a transcription error, not a distinct addressing
mode.

### Mailbox `0x31`

**Hypothesis, in four successive readings.** (a) An `IMEM_MISS_INS` Falcon fault with
`excause = 0xa`, from recovery jumping into unloaded IMEM, possibly a sign the ROP had taken
control. (b) A driver-planted value. (c) "Canary passed, PC hijacked (exploit successful!)", which
a loader script printed verbatim. (d) An early "HS-entered" marker meaning a phase-3 quiesce stall.

**Plausible because** `0x31` genuinely does appear at points where each of those stories fits.

**Resolved 2026-07-17 / 18** by locating the value in the disassembly: the Booter itself stamps
`0x31` at ucode offset `0x7a` as its first liveness marker, overwriting the driver's planted WprMeta
physical-address argument, and `report_status` at `0x1d0f` later rewrites it. So `0x31` means only
"`report_status` never ran", which is compatible with both an early stall **and** a successful
hijack. It is not an error code, and it is not proof of anything.

A parallel confusion, "`0x65 == 0x31`", was killed within an hour on 2026-07-10: the WPR2 error
comes from register writes alone, while a two-load run with no writes still produces `0x65`.

### The `0x1180f8` top nibble

**Hypothesis, revised three times in a single day (2026-07-15).** First: the mutexfree terminator
left `0xf0000000` and `booter_unload` rejected it with `0x29`, so nibble 0 was declared correct.
Then, because `whole_stack_rejoin` (which got furthest, with the RISC-V core active) writes nibble
`0x1` and a stock post-Booter state reads `0x11000000`, the target was revised to `0x1` and three
prior tests were declared mistakes.

**Disproved by** disassembly: `check_1180f8_nibbles` at `0x80a5` requires the **incoming** top
nibble to be 0. **The nibble was never the blocker.** The Booter dies deeper inside
`booter_load_wpr_main` at `0x22ba`, hanging at a target-engine handshake with `MB0 = 0x31` and no
halt, producing the driver's `0x65` timeout.

**Abandoned** 2026-07-15, having consumed several test iterations.

Two adjacent theories died with it:

- **"`0x1180f8` IS the ACR mutex or WprMeta ownership token", with a non-zero top nibble meaning
  "WPR2 is owned".** Plausible because the nibble does change across boot stages and the mutex is
  released nearby. Refuted twice: the mutex is released by the `0xccb` call **inside** `0x1c0e`, not
  by the nibble store; and the register was later identified as a boot-stage scratch with fields
  `[27:24]`, `[31:28]`, `[23:20]` and bit 26.
- **"The mutex-acquire at `0xd66` clobbers `r10` to the owner-id `0xf` before the nibble store."**
  Refuted by disassembly: `r10` is copied to `r0` at `0x1c1f` **before** the `0xd66` call, and the
  `0xf` comes from `main`'s explicit `-1` store at `0x80f1`
  (`mov $r15 -0x1; mov $r9 $sp; add b32 $r9 $r9 0x8; st b32 D[$r9] $r15`), which puts `0xffffffff`
  into `D[sp+8]`; `0x1c0e` then writes `(0xffffffff << 28) = 0xf0000000`.

The handoff value for `0x1180f8` also moved twice: `0x11000000` to `0x13100000` to `0x17100000`.
`0x11000000` was wrong because bit 26 = 0 would pass the Booter's `0x29` check at `0x1c9a` but fail
the host `_kgspIsReloadCompleted` poll; `0x17100000` was measured to pass both. The `0x17100000`
write also produced new FBPA mask-open failures, and the shipping chain does not depend on it at
all.

### Exit strategies

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| `secure_teardown` is the clean exit | It is the *designed* exit and does perform the SCP scrub and set `$cauth \|= 0x80000` | On a failed or overflow boot it does not yield a clean `resetPLM`: the value is hardware-arbitrated and comes out `0x8f`. The working exit at the time skipped teardown and wrote `0x8403C4 = 0xff` as the final action, reported with the caveat "I'm not 100% that this is correct" | 2026-07-17 |
| `0x810D` is a safe exit | A third-party repository settled on it and the clean room used it too | Then disputed on the grounds that performing `secure_teardown()` "locks the Falcon". **Both positions were partly wrong**: the exit is safe if and only if `D[0x1900]` carries `0x7`, which `f100_field_save_restore()` restores. The shipping tail returns to `0x7f2f` inside `secure_teardown` and the shipping payload does write `0x1100` (payload offset) to `0x00000007` | resolved 2026-07-25 |
| Terminating at `0x814e` boots GSP-RM | It looks like a clean rejoin into the normal flow | It skips the `0x37b7` image validation that both authenticates the image and zeroes `$r10`, so `r10` keeps `0x800`, the check at `0x8150` fails, and the GSP RISC-V core rejects the unauthenticated image | 2026-07-08 |
| Returning into `main` at `0x8103` releases the mutex | The call site is real | Faulted on hardware with `EXCI cause=0x9 INV_INS` at `PC 0x100`: the ROP arrived at `main`'s `lcall 0x1c0e` site with the ROP-landing stack pointer, about `0xc` **below** `main`'s real `0x8103` SP of `0xFFDC`, so the `lcall` push corrupted control. Fix: land at `0x1c0e`'s own entry with `r10 = nibble` and plant `0x1c0e`'s own epilogue return address | 2026-07-14 |
| Rejoining at `0x27fa` inside `booter_load_wpr_main` frees WPR2 | ROP v3 was built entirely on this | Disassembly against `booter_load_580_DEBUG` the same day showed `0x27fa` is mid-image-load WprMeta scratch that writes `D[0x600+0xf8]`, `D[0x600+0xfc]` and `D[0x600+0x48]` and touches **no** WPR2 register. `booter_load_wpr_main` is `0x22ba`. **There is no WPR2 teardown in `booter_load` at all.** A later analysis additionally called `0x27fa` "a poison write that produces a hang" | 2026-07-09 |
| Returning the chain to `0x2740` clears WPR2 | `0x2740` sits on the success path right after `image_copy_verify` at `0x3747` | The code just past it (`0x274b` to `0x29b8 region_subwrite`, and `0x291e wpr_region_program`) is exactly what **writes** `0x1fa824` and `0x1fa828`, so returning there **carves** WPR2 rather than clearing it. And `wpr_region_program` rejects an empty region (end < start yields error `0x5`), so the Booter cannot be coaxed into programming an empty WPR2. The direct high-secure write `0x1FA824 = 0x1FFFFE00` was used instead | 2026-07-16 |
| `booter_unload` is the load-1 to load-2 WPR2-release handoff | The disassembly facts are right: `booter_unload` writes `0x1fa824` and `0x1fa828` plus WPR1 and the FBIF `0x800` bits at many sites, and `MAILBOX0 = 0xFF` is a genuine no-FB-DMA shortcut | It failed as a plan: it only loads if `resetPLM` is already `0xff`, it re-stamps `resetPLM` to `0x8f` on exit (net zero), and it returned error `0x29` even with `resetPLM = 0xff` and `1180f8 = 0`, apparently because the fire-carved WPR2 had no matching `booter_load` lifecycle to unload | 2026-07-15 to 18 |
| Re-entering the Booter by returning to `_start()` at `0x100` with two signatures in a row, a fake one then a real one | Straightforward if the entry point is reusable | Tested on hardware: "replacing return address with 0x00 and hanging the unmodified signature on the second time did not work, with the same 0x31 in mailbox." The low-secure bootstrap at `0x00` is **wiped when the Falcon enters HS mode**, so there is nothing to return to. The shipping implementation instead re-runs the Booter repeatedly from the host | 2026-07-10 |
| Clearing only bit 24 of `0x1180f8` via `0x1b44 set_1180f8_bit24()` frees the ACR mutex | The gadget semantics are correct: it pops four words, lining up the following return address at `0xFFFC` | The conclusion after failures was that the whole register needs clearing. That requirement was then itself sidelined: the shipping refire chain **never frees the ACR mutex at all** and still works | 2026-07-21 |
| `0x8307 fbif_set_bit800` is the re-entrant mutex-free gadget | Used in re-entrant ROP v1's `FFEC` slot | It pops five words where four are needed, so it would wrap the stack to `0000`. Replaced by `0x1b44` | 2026-07-22 |
| The `_TAIL = {0x00: 0x1b44, 0x10: 0x7f2f}` minimal tail | A reviewer found the shipping tail uses ten gadgets where three should suffice, and that the `0x1fbd` elevator gadgets are pure stack-eaters that check a canary and do nothing. The minimal edit would leave five useful writes per fire instead of one | **Never tested.** The implementer declined to change a working chain because re-firing removed the pressure on per-fire write count. Verified still absent from master | 2026-07-25 |

### Overflow mechanics that were blamed and cleared

- **"Every write-carrying rejoin chain fails at `0xccb`."** Systematic isolation with an FLR between
  each fire showed every write variant failing at `0xccb` with `finalize = 0x01000000`, while the
  no-write `whole_stack` chain passed with `0x11000000`. Ruled out along the way: BCR-specific
  behaviour (a plain scratch write fails identically), shared BAR0-master state, main-SP frame
  collision at `0x10`, and overflow size (`0xF810` fails identically). The offered root cause is
  that the write costs `+0x18` of main-SP shift, putting `main` at `0xFFFC` so `0xccb`'s SP-relative
  accesses wrap past `0x10000`; the constraint is that `main` must stay below `0xFFF0` while the
  minimum BAR0-master write costs `+0x10` or `+0x18`. **No SP-lowering gadget exists in the Booter**:
  `mov $sp $r9` appears only at `_start`, which re-runs boot, and all `mpush` and `add $sp -N` forms
  live inside function prologues. Caveat recorded at the time: this conclusion was AI-generated
  analysis and was never independently reproduced. Date 2026-07-06.
- **"Writes and the clean `0xff` exit are structurally incompatible."** Declared "proven and
  structural" at 13:58 on 2026-07-12 with a tested elimination matrix. Superseded hours later the
  same day by the `0x8117` bare-exit route, which skips `main`'s finalize entirely. The parallel
  "7 free stack words" lead was called a red herring.
- **The "enlarge-overflow trick"**, raising the payload to `0xF810` so the DMA wraps into DMEM `0x0`
  to `0xF`, making the finalize locals payload-controllable. Initially promising and described as
  reaching finalize with the write issued. Ruled out the same day by the isolation sweep: `0xF810`
  fails identically to every other write variant. It did establish one useful fact, that the Falcon
  stack wraps from `0xFFFF` around to `0x0000`. Date 2026-07-06.
- **"The sig-DMA overflow smashes the stack" as the explanation of the driverless failure.**
  Eliminated by four independent controls: a fake address gave identical results; size `0x200`
  versus `0xF800` gave identical results; a spin-sled that would catch any frame smash still halted;
  and forcing the coherent aperture still halted. No IOMMU or DMAR fault appeared in the kernel log,
  so it is a Falcon-internal exception (`EXCI cause 0x9`) at a fixed point independent of the
  signature. The real cause was localised to a SEC2 context gap that `nvidia.ko`'s FWSEC and ACR
  path establishes and the driverless path does not. **The overflow mechanism itself is sound**, and
  the same overflow works under `nvidia.ko`. Date 2026-07-07.
- **Zero-padding the signature.** The hypothesis was that the whole `0xF800` buffer could be
  arbitrary payload. The payload must **begin with the real, valid signature**: zero padding makes
  the stock Booter bail with mailbox `0x31` before the ROP ever gains control. Consistent with the
  control experiment where a signature plus 256 correct bytes booted while any signature corruption
  gave `0x31`.
- **"The driver ignores the inflated `.fwsignature` section size."** The reading was that the stock
  driver sizes the signature memory descriptor from `pGspFw->signatureSize` and copies exactly that
  many bytes rather than the section's `sh_size`, so the splice would never overflow. It is exactly
  what the stock code path looks like on a quick read. Disproved the same day by a one-line
  diagnostic print inside `_kgspCreateSignatureMemdesc`:
  `NVRM: _kgspCreateSignatureMemdesc: V3DIAG signatureSize=0xf800 memdescSize=0xf800`. The container
  reader `_kgspFwContainerGetSection` validates `sh_size` and `sh_offset`, so the splice does reach
  it. Date 2026-07-11.
- **Baked-in `REJOIN_WPRMETA`.** The rejoin payload hard-coded `{r2: 0xf7700000, r4: 0xffeff000,
  ...}` commented "captured live, attempt-1". A live WprMeta dump from actual fires showed the
  framebuffer addresses are randomised per boot, so a static capture cannot be reused. Reviewers
  also flagged that the reconstructed stack placed two canaries adjacent, which should not happen.
  Date 2026-07-06.
- **"Booter behaviour is geometry-invariant."** Refuted 2026-07-14 by a side-by-side at the identical
  post-Booter checkpoint: SEC2 MB0 `0x0` (Booter reported success) against `0x31` (exploit leftover,
  Booter never reported); RV_STATUS `0x35` (RISC-V active) against `0x0` (never started);
  finalize `0x11000000` against `0x0`; WPR2 `0x02777000` carved in both. At 40 GB the Booter halts
  after carving WPR2 and before finalize **without calling `report_status`**, which is a trap or
  exception rather than a data-verify mismatch.
- **The `RA_SKIP` core-start theory.** Proposed 2026-07-13: GSP-RM's RISC-V never starts because
  `RA_SKIP = 0x38a7` jumps past the Booter's core-start block in `hw_init_block 0x692f`. Superseded
  within days: cold-boot and `whole_stack_rejoin` runs both showed the RISC-V core starting
  (RV_STATUS `0x33` or `0x35`), and the real blockers were the held ACR mutex and the RmInitDone
  stage.
- **Non-deterministic payload landing blamed on buffer physical-address layout.** Fire #1 landed all
  5 writes; the next roughly 12 identical fires landed only 3 of 5, dropping the strap and reset-mask
  writes. The signature payload physical address swapped between `0x104800000` and `0x104a00000`
  across runs, giving `MAILBOX0 = 0x31` against `0x6e`, which made buffer ordering look causal.
  Disproved by 39 further fires that all returned `0x6e` with 3 to 5 writes, plus a padding sweep and
  pool resets that failed to reproduce the good landing. `iommu=pt` and hugepages were explicitly
  ruled out. The real difference was GSP boot state: fire #1 was the only one run immediately after
  the `.04` driver had booted GSP-RM, leaving a valid WprMeta carved in WPR2. Date 2026-07-12.

### Cryptography and signing

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| Brute-force the NVIDIA firmware signing keys by renting B200s | A "throw compute at it" reflex, half-joking | An estimate that 10,000 B200s would take the age of the universe against RSA-3072. Never revisited | 2026-07-15 |
| The 384-byte NVGI blocks are RSA-3072 signatures (3072/8 = 384) | The arithmetic is exact and the assumption is natural | Disassembly showed the path is `_acrVerifySignature_TU10X` to `_acrCalculateDmhash_TU10X` to `_acrDeriveLsVerifKeyAndEncryptDmHash_TU10X` to `_acrMemcmp`, with **zero RSA functions in the binary**: Davies-Meyer hash plus AES key derivation keyed from a csecret. This changes the attack model completely, because a symmetric MAC can be forged if the key is recovered whereas RSA-3072 would have required factoring. Recovery target: `csecret(2)` | 2026-05-15 |
| Reversing the Booter to obtain high-secure signing privileges by re-compressing an almost-signed image | It would collapse the problem | Dropped by its own proposer ("Guess not, it's aes"). Even extracting the AES key from silicon leaves the RSA private key missing, since the die holds only the public key. The remaining theoretical route is enabling debug mode and using the debug RSA private key, but a **physical fuse disables debug mode on production cards** and only engineering samples have it enabled | 2026-07-14 |
| Harvesting live SCP crypto secrets from non-secure code after skipping `secure_teardown` | If true this would have been an independent serious vulnerability: skip the teardown, leave secret data in `$c0` to `$c7`, then read it from non-secure code DMA'd into SEC2 IMEM | Refuted the same day by two adversarial byte-for-byte static traces of the crypt-register lifecycle. The prologue at `0x107` to `0x147` loads each `csecret $cN, N` then immediately `cxor $cN, $cN` (self-XOR to zero); the real key use is the AES signature verify at `0x1e20` to `0x1e70` (`ckeyreg $c4, cenc`); scrub sweeps at `0x1e74` to `0x206e` run three back-to-back self-zero passes; the bound key register is XOR-zeroed at `0x1e94`; the last crypt op is `0x206e cxor $c0, $c0`. From `0x2070` to `0x7eef` there are **zero crypt ops**, and the hijack point (`lcall 0x4d4` at `0x37b3`) sits squarely inside that gap. The skip saves nothing because the bank is already empty roughly 0x1500 bytes of code earlier | 2026-07-17 |
| `csecret(2)` in high-secure mode for HULK signing | High-secure mode does expose `csecret` | Killed by two objections, the second confirmed by the proposer: the secrets are already cleared elsewhere in `booter_load`, and in non-secure mode the CS registers read back 0 for non-authenticated code | 2026-07-22 |
| The HULK licence and InfoROM as a source of unlock clues | Vendor-sanctioned mechanisms are cleaner than exploits | Closed by the project maintainer: anything gated behind the HULK licence requires `csecret(2)`, a Falcon secret-index crypto operation keyed to fuses the project cannot read. Prior work also established that HULK certificates must be generated internally at NVIDIA, no leaked generator exists, and each certificate is bound to the specific card it was issued for | 2026-06-27, 2026-07-20 |
| RAM-patch TOCTOU: patch signed firmware in system RAM between load and verify | It is the classic attack on this kind of boot chain | Closed on Ampere: signature validation happens **during** the DMA into IMEM, so there is no load-versus-verify window; modified bytes are rejected before execution. This generalises beyond PCIe to any firmware-level attack on this part | 2026-07-24 |
| `csigenc` ACL-`0x13` spill: invoke the crypto instruction that on Turing-class Falcons sets ACL to Insecure-Readable on its output, leaking a high-secure secret | A real primitive on a related architecture | Dead offline: `envydis` shows the SEC2 Booter secure body is ciphertext from `0x101` to `0x86FB` under `csecret(6)` AES, with **zero SCP or crypto opcodes in the plaintext stub**. The gadget, if present at all, is inside the encrypted body with no pinnable ROP address | 2026-07-24 |
| A master-key signature bypass or arbitrary high-secure Falcon code execution | It would generalise the primitive enormously | No flaw exists. The known load-before-verify timing hole yields **data-only register pokes** (`mpopaddret` plus a write gadget), not arbitrary Falcon code, because the body is AES-encrypted and unsignable. Plaintext ends at `0x101`, so there is no plaintext `iowr` or CSB gadget with a controllable target. No high-secure-reachable Ampere CVE exists | 2026-07-24 |
| `csecret(6)` or `csecret(2)` fault injection by electromagnetic or voltage glitching | Technically real, and the tooling was validated offline. The known-plaintext verifier is `AES_ECB(key, 0xFF x16) = 717d1494eaca317ff106195258b38377` | Roughly USD 400 to 2,000 of equipment, weeks of work, no guarantee, and the part would **still** be fuse-bound for PCIe afterwards. Equipment never acquired; the three DFA paths surveyed on 2026-05-31 were never attempted | 2026-07-24 |
| Non-secure Hello-World ucode can run the LMR and CFG1 writes over the priv bus | Non-secure Falcon code is trivially loadable and the targets are just BAR0 writes | Tried; did not work, exactly as NVIDIA's own Falcon-Security documentation predicts. Non-secure mode restricts register and physical-memory access, and the masks on these registers demand the highest level | 2026-07 |
| "Non-secure ucode cannot reach external BAR0" (the negative result) | A clean-looking driverless test | **Withdrawn by its own author** on 2026-07-16: the failing test used a `D[0x14000000]` window that actually aliased the Falcon's local DMEM, so it never probed BAR0 at all. No replacement measurement was reported, and the question reverted to open. The stake is large: if non-secure code, or host PL0 after a one-time mask open, can reach CFG1, LMR and SS0/SS1, then because the SS0/SS1 mask at `0x823804` is always-on, a single high-secure open would give a permanent path | 2026-07-16 |
| Host-PL0 SFTRESET (`0x0084007c = 1`) clears HSMODE | Worth one command | Did nothing; only the engine reset cleared HSMODE. Left as a **partial** dead end because the in-ucode variant, which would run at the Falcon's own privilege, was never tried | 2026-07-16 |
| Driver-side GSP falcon launch (PATH A) | If the driver could launch the GSP falcon itself, it would not need to ride the signed Booter | Recorded categorically in the driverless loader comments: "PATH A (driver-side launch) is DEAD IN ALL FORMS - PL0 cannot write any launch reg." PL0 cannot write any register in the `0x110280` to `0x110298` launch block, nor `0x1103d0`, because the Booter raises those masks to `0x8f` or `0xff` in heavy-secure mode at code range roughly `0x6933` to `0x699b`. Readbacks show the `0xbadf` priv-blocked pattern | 2026-07-16 |
| Host-side PCI device-ID spoofing to an A100 ID (`0x20b0`) | The A100 and the 170HX are the same die | It cannot work: VBIOS and devinit key off the *card-level* device ID before the driver or GSP get a chance to, and it is the same Booter for all GA100 cards and even Turing cards, so nothing downstream branches on the host ID. A researcher reported having already attempted it with the 450 driver and Booter | 2026-07-08, refuted same day |
| Patching `nvidia.ko` structs | Twelve patch sites were found in a roughly 76 MB module: nine single-byte stores and one four-byte store in a loop initialising per-SM tracking structures, plus a CMP-detection branch that was inverted. The fields looked like capability gates | Patching all of them changed nothing. Benchmark numbers were unchanged, because those fields are host-side bookkeeping used for reporting | 2026-07-23 |

### Analysis-target and tooling errors

- **Decrypting `gsp_tu10x.bin` as if it were the Booter.** Several people spent days on it. It is
  not the SEC2 Falcon Booter; it is the GSP RISC-V ELF payload that the Booter validates.
  `file gsp_tu10x.bin` returns "ELF 64-bit LSB relocatable, UCB RISC-V, soft-float ABI, version 1
  (SYSV), BuildID[sha1]=9ea6f739bfdf716c0d1211471c68a083e376fe4c, not stripped" for the 580.65.06
  build. Ghidra emitted roughly **100 MB of C** and `riscv64-unknown-elf-objdump` roughly **1.5 GB
  of assembly** from it. The actual target is only about `0x6000` bytes, roughly 25 kB, and
  disassembles to about 390 kB: `booter_load_ga100_*.bin`. Plausible because it is the GSP firmware
  file the driver loads, it sits in `/lib/firmware/nvidia/*/`, and it looks encrypted. **Important
  nuance:** the file was not useless. The clean-room Python unlock injects its ROP payload into the
  `.fwsignature_ga100` section of exactly this file. It was the wrong disassembly target but the
  right delivery vehicle. Date 2026-06-30.
- **Fear that a `-debug` compile flag would shift every gadget address.** Plausible because that is
  what debug builds normally do, and had it been true the entire clean-room approach would have been
  dead. Disproved two ways: the debug and production binaries are exactly the same size, and a ROP
  chain built purely from the debug disassembly executed correctly on production silicon. Date
  2026-07-02.
- **The `faucon` disassembler and emulator against the encrypted Booter.** Reported as
  "encrypted/obfuscated" and abandoned. The analysis that actually produced results was done by
  hand. Date 2026-07-21.
- **`envytools` as a source for Falcon secure boot.** Recorded as a negative result: the crypto page
  is entirely "Todo: write me". Do not re-search it.
- **Trusting community Falcon emulators as ground truth.** A canary-echo ROP intended to leave the
  original canary in `$r15` and echo it to the mailbox printed the canary in the simulator but
  produced a random per-boot number on real silicon in one variant and nothing in another.
  Separately, both the emulator and the verified `mpopaddret` semantics predicted the next
  return-address slot for one chain at byte 63364, but on silicon the chain wandered and returned
  `0x31`. Never resolved.
- **Manual reconstruction of the call chain into the overflow.** Abandoned because `0x4d4` is called
  from at least 20 places, so static reasoning could not identify which frames were on the stack.
  Replaced by word-by-word exfiltration of the real stack from an 8 GB card over **35 boots**.
- **The LLM-generated DMEM map placing a 32-byte signature buffer at `0x5c00` to `0x5c1f`.**
  Circulated 2026-07-13 and reviewed as a "good summary" with "some minor technical errors". It is
  worse than that. It lists both a "signature verification buffer" at `0x0800` and a "SIGNATURE
  BUFFER (32 bytes)" at `0x5c00`, which is self-contradictory. It lists "IMEM code" ranges *inside a
  DMEM map*, a category error given the Harvard architecture. And it lists `0x9100` as "CSB",
  `0xd000` to `0xd500` as "mailbox registers", `0x10100` and `0x14000` to `0x14b00` as "IO windows"
  and `0x30000+` as a payload region, all of which are CSB or IO addresses or beyond the `0x10000`
  end of DMEM. The entries that **are** confirmed by working exploits are `0x0600` (WPR descriptor),
  `0x0700` (image descriptor), `0x0800` (signature buffer), `0x6330` to `0x633f` (scratch) and
  `0x6340` (stack canary guard). One further mislabel to watch for: the same family of documents
  writes "Signature buffer: BAR0[0x0800]". It is **DMEM** `0x0800`, not BAR0.
- **The 208-writable-BAR0-registers scan.** Reported as finding 208 fully writable registers with
  PRI mask `0x00000000`, clustered in the signature-buffer, configuration and mailbox regions.
  Plausible as scan output, but sourced from the same document as the DMEM map above, never
  independently reproduced, and it lists "0x0800 (signature buffer)" as a BAR0 register, repeating
  the DMEM/BAR0 confusion. Treat as unverified.
- **The bot claim that "direct write works for BAR0 offsets < `0xA800`, fails above".** Challenged as
  internally inconsistent, and the accompanying ROP chain was shown to be structurally broken: it
  used `0x30bb` and `0x30be` as elevators, which sit at the start of the long function `0x2e80`
  `image_auth_decrypt()` where `$r10` and `$r11` are overwritten many times. The correct elevators
  for calling `0x8224` are `0x1fb9` and `0x1fbd`. Date 2026-07-15.
- **Calling `0x8224 csb_write` directly instead of `0x10aa` or `0x10b9`.** It works, but requires
  hand-rolling the address, data, command and poll sequence per register in the ROP, costing more
  frames for no benefit. `0x10b9` is the clean chainable encapsulation because it ends in
  `mpopaddret $r3 0x4` and walks straight to the next write frame.
- **A "mega-ROP" staged in low DMEM.** Ruled out by the observation that nothing at all is allocated
  below DMEM `0x100`.
- **The region-splice idea**, putting a `0x1000` write at DMEM `0x650` into an `nvidia.ko` rejoin
  ROP, was found to require a post-overflow DMA-to-WPR2 write and was not pursued.
- **The register sweep verdict that `0x9a0148` and friends are non-functional.** The sweep found
  `0x100b10`, `0x100b38`, `0x9A0148`, `0x9A014C`, `0x9A0108`, `0x9A0008`, `0x9A010C` and `0x9A000C`
  all non-always-on (reverting `0xffffffff` to `0xffffff8f` on FLR) and marked them non-functional
  for geometry. The shipping patch opens `0x009a0148` to `0xffffffff` on every boot and logs the
  readback. The sweep's own author immediately flagged the methodology hole that explains it: the
  sweep opened the mask in high-secure mode then did the geometry write from the host **after** the
  FLR, so if the geometry shadow only latches an in-high-secure write, the sweep would report
  geometry as failing for every mask regardless. Date 2026-07-16 to 18.
- **"Open the four FBPA masks first" as a premise for the high-secure path.** Refuted by
  measurement: one high-secure broadcast CFG1 write took all 20 live FBPAs from `CSTATUS 0x200` to
  `0x800`. High-secure mode bypasses the FBPA masks entirely; opening them was only ever needed for
  host-PL0 per-FBPA writes. Date 2026-07-15.
- **Persistence on the CMP 90HX.** A tester reported the exploit "landed on 90hx and it... persists",
  then retracted within minutes: "wait, i didnt test ss0/ss1 writement after flr" and "false
  positive". What survived as significant is only that the Turing-generation `booter_load` can be
  **loaded** onto a GA102 Ampere card at all. Date 2026-07-14.
- **`/lib/firmware/nvidia/ga100/gsp/dmem.bin` as a payload override.** The hook exists in shipping
  code and logs on success, but in the released boot flow the first
  `kgspSec2PostblTimingRefillPayload()` rewrites the entire buffer with the built-in template before
  any Booter Load consumes it. Anyone hoping to swap payloads by dropping a file there should know
  it has **no effect on the released path**. Its absence is reported as `0x59` and is benign.
- **IOMMU debugging before the DMEM-write breakthrough.** Roughly a day was spent on IOMMU dead ends
  before SEC2 DMEM writes were made to work on 2026-06-28. During vfio-based development the Falcon
  DMA engine ran (`wcount_delta=2`) yet zero bytes landed in SEC2 DMEM (`dmem_after=0`), leaving the
  Booter waiting with `sig0=0`, `mb0=0x31`, `TRACEPC=0x16b`. Encoding, bus mastering, hugetlb
  allocation and stale SEC2 state were all ruled out. The working hypothesis was that with
  `intel_iommu=on` the driver's INSTBLK page tables did not map the exploit buffer's physical
  address. Refuted by test: IOMMU off, `iommu=pt`, VFIO IOVA and the paper's FBIF constants all
  failed to fix it.
- **Skipping 100 decimal bytes instead of `0x100` hex.** One tester decrypted from byte 100 and got
  gibberish. The distributed instruction was explicit: the first **`0x100`** bytes are cleartext and
  must not be decrypted, the zero padding at the boundary must not be disassembled, and disassembly
  must restart at `0x100`.
- **"The encrypted region starts at byte 760 where entropy rises."** Refuted the same day: the 760
  figure was an artefact of the extractor's synthesised headers and signature block still being
  prepended. Once everything but the raw firmware was removed, the file showed exactly `0x100`
  unencrypted bytes and clean 16-byte AES alignment. A related early observation, that the pad
  pattern sat on an 8-byte rather than 16-byte boundary, was the same artefact.
- **A 4,196-byte blob that turned out to be mostly empty.** A `0x1064`-byte binary posted to the
  channel is a Falcon Booter descriptor image whose entire tail from `0x0500` to `0x1064` is zero.
  Recorded so nobody analyses it again.
- **Die-level and HBM-controller attacks on memory geometry.** Not pursued. The stated reason: the
  HBM controller only accepts commands from the Falcon core at boot, and interrupting or injecting
  into memory training is not easy. This is documented reading rather than measurement, so it is a
  **deprioritisation rather than a proof of impossibility**.
- **"GSP-RM is encrypted and cannot be disassembled."** Plausible because GSP-RM is a signed radix3
  blob and nobody had opened it. Retracted by its own author on 2026-07-23 and contradicted by an
  external write-up that disassembled the 13.25 MB RISC-V ELF. The correct blocker is the
  **signature, not encryption**: a modified GSP-RM will not authenticate.
- **The "persistent across FLR resets" claim for the FLR-based unlock.** Self-contradictory inside a
  single document: it asserts the chain survives two consecutive FLRs, then admits that because
  stage 1 restores the original GSP at the end, the mask re-injects from the patched GSP only "until
  the stock GSP is swapped back in and you do another FLR cycle". Never independently reproduced.
  Date 2026-07-12.
- **The perma-lock fear.** Raised 2026-07-21 ("wait can new nvidia drivers perma lock them?").
  Rejected on the grounds that the unlock does not use a stock signed driver, the open-source tree is
  already widely forked, and no runtime OTP-fuse mechanism was ever demonstrated on the 170HX. The
  speculative counter-mechanism produced no supporting evidence.

---

## PCIe: speed, width, Gen3 and Gen4

> [!CAUTION]
> **Keep speed and width separate**
>
> PCIe link **speed** (Gen1 to Gen2) is a software and firmware unlock, shipped only on unreleased
> branches. PCIe link **width** (x4 to x16) is caused by 12 of 16 lanes shipping with their AC
> coupling capacitors depopulated, and is fixable only by hand-soldering 24 0402 parts. Several
> dead ends below exist purely because someone conflated the two. See
> [the PCIe subsystem](../hardware/pcie-subsystem.md) and
> [physical mods](../operations/physical-mods.md).

### The four-layer wall

**Hypothesis (2026-07-24).** A PCIe field manual concluded that all four layers were empirically
closed: runtime register writes, register semantics, durable firmware, and the silicon fuse. It was
verified on two independent surfaces, an offline firmware fuzz sweep of 4,032 runs (66 functions x
126 function-register pairs x 32 single-bit values) and on-silicon direct-write probing.

**Plausible because** every individual component genuinely was inert.

**Disproved by** its own section 6, which stated the exception: *"The full community Gen2
sequence ... as a single combined write was not run: every component is individually proven inert,
so it is a low-odds combination."* The low-odds combination worked. Nobody had previously issued the
**combined** sequence (CYA_0 bit 2 clear, LINK_CONFIG_0 MAX_RATE = 2, XP3G override and value,
PRIV_MISC_1, VSEC) from inside the Booter privilege window, and nobody had driven a root-port
retrain while those writes were in effect.

**Abandoned for Gen2** 2026-07-24 to 26. **The Gen3 half of the conclusion still stands.**

### Register and configuration-space attacks on the speed cap

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| `setpci` write to LnkCap2 (config `0x2C`) with all speeds set | It is the register that literally lists supported speeds | The write is **silently dropped**. The register is hardware read-only, marked `R-EVF` in NVIDIA's own `dev_nv_xve3g_fn0` header, meaning no write port at any privilege level. Opening a mask cannot help; you cannot write a portless register | 2026-07-24 |
| Raise TARGET_LINK_SPEED (`0x880A8`) and retrain, with nothing else | TARGET is genuinely writable | The link re-trains at **Gen1** because the endpoint re-advertises Gen1 in its TS1/TS2 ordered sets, bounded by the read-only SUPPORTED field | 2026-07-24 |
| Host BAR0 writes to `0x88070`, `0x8808C`, `0x88090` | Ordinary-looking XVE registers | PROT-walled from the host: reads return 0, writes are ignored | 2026-07-24 |
| High-secure XP3G PHY-rate override **in isolation** | The most promising-looking of all: the mask opened (`XP3G_PLM(0x8e1b0) reg=0xffffffff`), the override registers proved writable, and the rate field read back Gen3-capable (`XP3G rate=0x00340036 ovr0=0x4`) | The link nevertheless stayed at Gen1 (`lnksta=0x10410040 speed=1`). Read at the time as proof that the fuse gates the SerDes downstream of every override. It incidentally proved a positive: the `0x10B9` SEC2 CSB mailbox gadget does reach the XP3G and PCIe priv block. **Note it is one of the components of the combination that later worked** | 2026-07-24 |
| High-secure FEAT_OVR write plus retrain | It is the mechanism that unlocked compute | `0x823800` read back `0xfffffe8e`, so the write took, but `OPT_GEN23` stayed `0x1` and the link stayed Gen1 with AER = 0. Read at the time as a PCIe override-enable fused **off**, unlike SM speed select which is fused **on**. The block's own inventory lists no PCIe register, so the durable result is the probe outcome: nothing in `FEAT_OVR` moves the link | 2026-07-24 |
| Direct write of `OPT_GEN23` (`0x82057C` to 0) | The obvious lever | Attempted from every available privilege: host, high-secure driver write, and the Booter payload. Always fails, logging `PLM[4] OPT_GEN23(0x82057c) status=0xffff reg=0x1 (write FAILED)` and `PCIe xp3g booter FAILED to set OPT_GEN23` with `rd=0x00000001` after two attempts. It is a pure OTP fuse-sense reflection, hard read-only. **Notably the shipped Gen2 patch still attempts this write and still fails, and Gen2 works anyway** | 2026-07-23 |
| Setting VSEC_DEVICE bit 0 through the Booter | Part of the working sequence, so it looked required | `pre=0x00000800 want=0x00000801`; failed twice with `rd=0x00000800`. This is awkward for the transient-window model, which attributes the window's closure to RM clearing a bit that the patch apparently never managed to set | 2026-07-23 |
| Writing the derived allowed-Gen mask `0x85084` at postbl | "GSP writes `0x85084`" is true | Both `0x85080` and `0x85084` read **`0xBADF1100`** from the injection point and writes are dropped: GSP writes it at a privilege the injection point never reaches. RM re-derives the mask on every retrain anyway, bounded by the supported cap | 2026-07-24 |
| `0x88084` MAX_LINK_SPEED is a writable cap | It is the advertised cap | An analysis concluded no host-writable register backs it: a high-secure write to a scratch register succeeded while the same write to the entire XP-PL LINK_CONFIG cluster (`0x8C044`, `0x8C048`, `0x8C04C`) was rejected, and unlike compute and ECC there is no `FEAT_OVR_*` shadow for link speed. The person relaying it flagged it as "90% sure the AI analysis is wrong", and it was never resolved. The checkable parts hold up: `0x8C044/48/4C` really are a different cluster from `0x8C040`, `0x8C2C0` and `0x8C1C0`, which are the ones the working patch uses | 2026-07-12 |
| `0x8c044` (XP_PL) is the link-rate register | A named candidate | A probe reads `0xbadf5040`, the priv-masked sentinel, and the write-test tool skips it with `XP_PL_0x8C044 @0x08c044: read=SENTINEL (masked) -> skip`. The real candidates are XVE_LINK_CAP `0x88084` and XVE_LINK_CONTROL_2 `0x880a8` | 2026-07-20 |
| `pl_link_rate_addr: 0x0008c1c0` = `0x00240036` is a validated Gen2 requirement | It is in the working patch | The A100 forced-generation sweep showed XP_PL `0x8C044`, `0x8C048` and `0x8C04C` all reading `0xbadf5040` at *every* generation on the reference card, so the PL family was never validated against a working link. Independently, the write exists only in the in-GSP path of patch 0007: neither `tools/retrain.sh` nor patch 0008 touches `0x0008c1c0`, and both produce Gen2, so it is **not required** for a post-boot retrain. What the individual bits of `0x00240036` encode is documented nowhere | verified against all three code paths |
| BAR0 `0x8872c` value sweep is the retrain lever | A tester on Proxmox found `0x8872c = 0x6` leaves the LTSSM at Gen1 x4 and is the *stable* value, while `0x2` and `0xA` expose additional Gen2 behaviour | `0x2` and `0xA` eventually **wedge the VFIO/QEMU function**. The shipping patch 0007 writes exactly `0x6` here and its own log calls it "skip mid-boot retrain", so this register is not the retrain lever anyone hoped | 2026-07-12 |
| PTOP_FS4 `0x0002241c` is the Gen2 gate | The documented bit names are literally `GEN2_PCIE` (bit 0) and `GEN2_PCIE_SPEED` (bit 7), and the 8 GB 170HX reads `0x00000000` while an A100 80GB and an RTX 3070 read `0x00000081` | A GA10x control card that trains Gen4 reads the same `0x00000081`, **and the 10 GB 170HX also reads `0x00000081` while still being capped at Gen1**. If those bits gated speed, neither observation could hold. No write was ever attempted against it | 2026-07-25 |
| `0x118F78`, `0x132B70`, `0x132B30`, `0x132B6C` carry the lock | `0x118F78` was an externally suggested lead | Measured byte-identical on CMP and A100: `0x118F78` = 0 / 0, `0x132B70` = 0 / 0, `0x132B30` = `0x00000400` / `0x00000400`, `0x132B6C` = `0x08000020` / `0x08000020`. Identical values cannot encode a SKU restriction, at least in the idle no-driver state. The whole `0x132xxx` block was dropped and patch 0007 was recalibrated from 8 writes to 5 | 2026-07-22 |
| Overriding the PCIe fuses from software: clear MAGIC_D bit 25 at `0x00820520` and set the DevInit gate bit 0 at `0x00820148` | The Booter payload demonstrably writes other privileged registers | **The cleanest A/B in the whole project**: in a single boot, with the identical payload mechanism, the XVE targets landed and persisted while `0x820520` stayed `0x16680000` and `0x820148` stayed `0`. Cause: `FUSE_EN_SW_OVERRIDE 0x820040` = 0 and `FUSE_DIS_SW_OVR 0x820084` = 1, and `0x820148` is an OTP spare bit that can never be set from software. The code was left in place behind `CMP_PCIE_FUSE_WRITES=0` with the comment "PROVEN hw-locked" | 2026-07-22 |
| Naive one-shot pokes at the CTRL_OPT window | It is the visible fuse-override surface | Recorded experiment table: `0x820838` stock 0, wrote 1, now reads 0 (did not persist); `0x820840` stock 0, wrote 1, now reads 3 (changed); `0x820850` and `0x820854` stock 0, **not written**, now read 7; `0x82057c` and `0x820580` stock 1, wrote 0 (dropped), still read 1. Conclusion: the window is actively managed by GPU firmware every boot, one-shot writes are absorbed or mangled, and the firmware writes override bits on its own | 2026-07-22 |
| The VBIOS CTRL_OPT and HULK option regions are a PCIe lever | They are the editable regions | "Everything imo", with the structural reason "CTRL_OPT is remove only, not add". A link-speed unlock cannot come from a VBIOS option-region edit | 2026-07 |
| Device-ID spoofing to present as an A100 | Two variants, both natural | Writing the XVE config shadow dword0 `0x88000 = 0x208210de` only changes the host-visible ID while the locks (MAGIC_D bit 25, PPCI_2 SPEED, the DevInit-suppressed `0x88CE4`) remain. And the underlying IDs come from read-only fuses `0x8204D8` and `0x82056C` with `FUSE_DEVID_SW_OVR_DIS 0x00820584` = 1 blocking any software override | abandoned, never pursued |
| `RmForceEnableGen2=1` alone does something | The branch installer ships it | The independent Gen2 setup script lists it among things "tested and confirmed unnecessary". Nobody has shown it doing anything on its own | ongoing |

### Firmware and strap attacks on the generation cap

**The devinit Gen-strap bytes.** The 170HX PCIe speed restriction is **5 bytes across 3 devinit
sites**, located by searching for references to Falcon register `0x14118F78` (little-endian byte
pattern `78 8f 11 14`). The differing bytes versus A100 SXM4 are hit #8 `0xBB` to `0xE2`, hit #10
`72 DE` to `52 DD`, and hit #11 `97/59` to `95/39`. All five bytes fall **100% inside** the
Davies-Meyer `csecret(2)` MAC range `0x2200` to `0x43C00`, so a keyless forge is a 2^128
second-preimage. Status: closed, 2026-05-31.

> [!WARNING]
> **The intuitive direction is exactly wrong**
>
> The community `pcie_set_speed` direction is backwards. The strap field is
> **monotonic-restrictive**: 0 means all generations enabled, 3 is the 170HX setting (clearing
> Gen2, Gen3 and Gen4), and `0xF` is out of range with all disabled. **Raising the ceiling
> requires a lower strap value, not a higher one**, and no write port exists. The devinit
> read-modify-write in the signed FWSEC is `mov r9 0x14118f78; ld; and 0x3ff / or 0x400; st` at
> VBIOS offset `0xE88C`, with 26 references in every ROM; the 170HX-versus-A100 delta is the
> **value written**, not the code. Refuted 2026-07-24. This is one of the most valuable
> corrections in the corpus.

A related address-space error was retracted late: a 2026-07-24 field manual described the devinit
Gen strap as living on a "Falcon PRIV bus, >16MB, not host BAR0" at roughly 321 MB and built a "no
host aperture exists" argument on it. The 2026-07-27 correction retracts this: every `0x14xx....`
constant in FWSEC falcon code is a BAR0 offset OR'd with aperture base `0x14000000`, so
`0x14118F78` is BAR0 offset `0x118F78`, inside the ordinary 16 MB window. Standing caveat: a host
read of `0x118F78` returns `0xbadf1100`, so host reachability outside FWSEC context is still
unproven.

Other firmware routes:

- **Reflashing an edited VBIOS** (`nvflash` or a CH341A programmer). The Ampere RSA signature check
  rejects it and the card will not boot. Gen-cap bytes at `0x40B4B`, `0x40F05-3D` and `0x40FC5-CB`
  are all inside the MAC. Refuted 2026-07-24.
- **A leaked production HULK certificate**, in-ROM at `0xFE504` with `csecret(40)` and
  `STRICT_ID_MATCH=NO`, would be a *signed* override of `FUSE_FEATURE_OVERRIDE` `0x823800` that
  sidesteps the 2^128 forge. Gated by the `RmActivateHulk` fmodel flag, which is false on production
  silicon; requires the certificate files; and on-card FEAT_OVR writes do not move `OPT_GEN23`
  anyway. Largely mooted.
- **Flashing a genuine A100 80GB VBIOS to restore PCIe 4.0.** Highly plausible given the
  byte-identical BIT tables and the near-identical PCB. Tested and failed: "Theyve tested that and
  it doesnt work. the pcie 4.0 bit at least." Reported 2026-07-19.

### Hardware and platform attacks

| Hypothesis | What disproved it | Date |
|---|---|---|
| Copy the A100's strap configuration onto a 170HX | Tried by a tester who already had Gen2 x16 working. Result: **card not detected at boot**. Follow-up answers were blunt: "the straps don't do anything", "it's not a hardware problem", "falcon is driving the rewrites", "there's no gen3 override register". The generation limit is enforced by Falcon firmware rewriting the PCIe configuration at boot, not by board straps. A separate researcher independently reported that comparing strap profiles against a live A100 dump was also a dead end after two days of work, and the comparison artifact `reg-ref-a100-vs-170hx.csv` (1,857 bytes) produced nothing | 2026-07-26 / 27 |
| A plain PCIe redriver | A redriver only re-amplifies, so the endpoint still sources its own fuse-capped TX rate. Only a **retimer**, which terminates the link and can advertise a different rate to each side, could forge TS1/TS2 Rate-ID on the physical lanes. Named candidates: Astera Aries, TI DS160PR810-class interposers. Never attempted, and applies to Gen3 and above only since Gen2 turned out to be reachable in software | 2026-07-24 |
| Full remove-and-rescan from inside the driver ("Option A"): `pci_stop_and_remove_bus_device(pdev)` then `pci_rescan_bus()` | Three caveats killed it. It can never run from probe context, and the GSP boot hook runs inside `probe()`, so removing the device there is a use-after-free of its own context and would need deferring with `schedule_work()`. After rescan the driver is re-probed, GSP boots, the writes run, and it rescans again, requiring a module-global once-flag that survives device remove but not `rmmod`. And active CUDA and `nvidia-smi` clients are dropped on remove. Option B, retrain via the upstream bridge, shipped instead, because config-space reads are live so a fixed XVE shadow shows up in `lspci` immediately with no rescan | analysed and rejected 2026-07-22 |
| Call the kernel's own `pcie_set_target_speed()` | Present in the bandwidth-control service in kernel 6.x and later, but **not exported**, so the LNKCTL2 and LNKCTL writes have to be done by hand | recorded |
| Fault injection or glitching of the Falcon boot sequence (a ChipSHOUTER-class EM injector) | Proposed as "the only feasible path" after the register route stalled. **Never attempted by anyone** | 2026-07-24 |
| Changing PCIe mode by hot PCIe reset on a running system | Suggested with the caveat that motherboard hotplug settings may govern it. **Never tested** | 2026-07 |
| The Gen4 shadow experiment (`0007-pcie-gen4-shadow.patch`) | Abandoned to a boot loop. Upstream patches 0001 to 0006 use 4 Booter payload runs per boot and boot fine; this patch raised that to 7 to 11 runs and the *real* Booter Load then failed with `mailbox0 != 0` (status `0xffff`), after which RM retried `_kgspBootGspRm` endlessly with `wprStart` sliding down the framebuffer on each retry and then wrapping. One cause was eliminated: the loop persisted with `CMP_PCIE_RETRAIN=0`, ruling out the in-driver retrain. Two hypotheses survived and were **never decided**: too many Booter or priv-sequencer executions immediately before the real boot exhausting sequencer state (note `kgspExecuteBooterLoad_TU102` resets SEC2 before every run so SEC2 accumulates no state, but the priv sequencer is separate hardware that is not reset), and a specific write (prime suspects `0x8C2C0` LTSSM config then `0x8C040` SPEED) disturbing the PCIe block over exactly the link the Booter uses to DMA its signature from system memory. Outcome never recorded | ongoing |
| PCIe switch fan-out as a bandwidth fix | Correctly caveated in-channel: a switch does not create bandwidth, so the uplink remains the aggregate ceiling; passive dividers need motherboard bifurcation while a real switch does not; chaining switches costs signal integrity and latency; and **because the 170HX has no P2P, cards on the same switch cannot bypass the uplink**, which removes the main reason to buy one. Nobody in the window had actually deployed 170HX cards behind such a board | 2026-07 |
| The community patch enabled P2P DMA between GPUs | **Refuted against source**: no branch of `cmpunlocker` contains any P2P enablement. The supporting switch-latency reasoning (8 to 15 ns through a PEX switch) is sound generic PCIe behaviour but does not apply to 170HX-to-170HX traffic today, and nobody measured 170HX P2P throughput. See [P2P](../frontier/p2p.md) | 2026-07-27 |

### False claims, misdiagnoses and measurement traps

| Claim | What killed it | Date |
|---|---|---|
| A fork advertised as reaching PCIe Gen 4 | A maintainer said "Apparently, this version of cmpunlocker can get to PCIe Gen 4, but I'm about to debunk that." Roughly an hour later: "This is BS - didn't work for me at all." Two days later the origin was clarified as a mis-filed issue. Both testers' hosts were limited to PCIe Gen3 anyway, so a Gen4 result could not have been observed | refuted 2026-07-20 |
| "PCIe Gen 3 is actually working" via AI-driven experimentation | No measurement, no register write and no link-status output was ever posted; the claim came in a joking register and was immediately followed by community discussion still treating Gen3 and Gen4 as unsolved | no evidence, 2026-07-24 |
| A rental listing advertising a 170HX at "PCIe 3.0" | Judged incorrect reporting by the platform: the deployer does no firmware work, Gen3 was known to be unsolved that day, and the `OPT_GEN23` write failure was logged the same day | 2026-07-23 |
| "This patch is for Turing so it won't work on the Ampere 170HX" | Seeing `kernel_gsp_tu102.c` in a patch-apply error led to the inference. Partially retracted within two minutes, and the real cause was malformed hunk headers. The `_TU102`-suffixed GSP functions are exactly the ones the 170HX executes; they appear in Booter failure messages on working Ampere cards | 2026-07-24 |
| "Only kernel 5.15 unlocks Gen2" | One tester found Ubuntu 26.06 with kernel 7.0.0 failing and a fresh 22.04 with 5.15.0-186-generic working. Refuted by successes on 5.15, 6.12, 6.18.38 and 7.1.3, and superseded by the hardcoded PCI address discovery. A secondary real problem persisted: kernel-swapping on Ubuntu broke the NVIDIA 610 open driver build | 2026-07-26, root-caused 2026-07-27 |
| The early hard-fuse theory for link training generally | "The card can advertise it, but if there are fuses interacting with link training it doesn't matter what the card advertises." The suggested diagnostic came back "dmesg is clean, doesn't show anything." Software-only Gen2 landed the next day, undermining the theory **for Gen2**. It may still hold for Gen3 and Gen4 | refuted for Gen2, 2026-07-24 |
| "Gen 3.0 and 4.0 is a dead end due to fused blockers in the die" | Rebutted in-channel: "it's not guaranteed dead", "the fuses are signals used by the firmware to control function", "they're not hard efuses that actually destroy functionality". The rebuttal is better supported, since the Gen2 unlock proves at least one fused generation limit is firmware-mediated and defeatable. Unsettled but leaning rebuttal | 2026-07-26 |
| Trusting sysfs `max_link_speed` | On three cards across two rigs sysfs reported `cur 5.0 GT/s / max 2.5 GT/s`, a maximum **lower** than the current speed, while config-space LnkCap on the same devices correctly advertised Gen2 `0x00456102` and LnkCap2 `0x00000006`. Diagnose a 170HX link from LnkCap and LnkSta, not from the sysfs attribute | recorded |
| Reading `nvidia-smi`'s `PCIe Generation Max` as evidence of anything | The stock card reports `Max : 2` while `Device Current : 1` and `Device Max : 1`, and `lspci` LnkCap2 lists only 2.5 GT/s as supported. An internal inconsistency present since 2023, useful only as a fingerprint | ongoing |
| Assuming the x4 width is a fuse, a strap, or something the driver can change | No lane fuse is set, no Gen2 code touches width, and one host port that was itself x16-capable still trained the card at x4. The cause is the missing AC coupling capacitors, and the answer comes from PCB analysis, not from software | recorded |
| A `0.71 GB/s` bidirectional result on a card advertised as Gen1 x16 | Flagged as "way too low" for Gen1 x16 (nominal roughly 4 GB/s), implying the link was still effectively x4. Nobody could establish what lane mod the test card had, so it was never settled, but the number should not be quoted as a Gen1 x16 measurement | 2026-07 |
| The "0.80 GB/s PCIe (Gen1 x16)" annotation | Gen1 x16 has a roughly 4 GB/s ceiling, so 0.80 GB/s would be 20% of line rate, whereas Gen1 x4 has a roughly 1 GB/s ceiling making it an 80% result, which is normal. Almost certainly a Gen1 x4 link | flagged 2026-07-28 |
| Patch 0008 reporting failure | Structurally correct root-port retrain, but it runs at driver probe roughly 3 seconds after the capability window closes, and its success predicate requires `PCI_EXP_LNKSTA_DLLLA`, a bit the 170HX port is not even capable of reporting (LnkCap bit 20 = 0). **Every Gen2-trained card gets told it failed** | proven from source |
| Patch 0007 alone as a retrain | It runs in RM context and cannot reach the upstream PCIe bridge; it can only poke the endpoint's LTSSM register at BAR0 `0x8872c`, which is not a real retrain. The patch's own log admits it: "skip mid-boot retrain" | recorded |
| Counting errors in secondary documentation | Three, all checkable against `0007-pcie-gen2.patch`. "Eleven consecutive option and fuse-block privilege masks from `0x008200d0` through `0x008200f4`" is wrong: the table has **ten** (`D0, D4, D8, DC, E0, E4, E8, EC, F0, F4`), and a third-party guide's "9 regs" is also wrong. "Opens 22 PLM-protected registers" is wrong: the table has **18** mask opens inside a 23-entry table. And "late retrain ... after GSP-RM boot completes" is wrong: the late hunk sits in `kernel_gsp_tu102.c` immediately after Booter Load returns, i.e. **before** GSP-RM is running | adjudicated |

Two implementation regressions are worth recording as dead ends in their own right, because both
blocked testers for days:

- **The hardcoded `0a:00.0` BDF in `tools/retrain.sh`.** The `Gen2` and `far` branches hardcode
  `SYS=/sys/bus/pci/devices/0000:0a:00.0` with `GPU, UP = "0a:00.0", "09:01.0"`, so the script
  silently targets the wrong device on any other machine. Fixed on `deced` (commit `2326599`,
  "Stupid mistake - it appears to be hardcoded") with a `find_gpu_bdf()` helper. Note that
  `debug-gen2`'s earlier `retrain.sh` already did full sysfs discovery, so this was a **regression
  introduced and then reverted**. It is also dead code on the current lineage, since from `Gen2`
  onward `install.sh` deletes it and patch 0008 does the retrain in-kernel.
- **`RMPcieLinkSpeed=0x1` on the `Gen2` branch.** Installing that branch writes a modprobe option
  pinning the link to Gen1 while simultaneously trying to enable Gen2. Corrected on `far` to `0x2`
  under the commit message "Remove clamp link to Gen1".

> [!NOTE]
> **Open problem**
>
> Whether `RMPcieLinkSpeed` should be `0x1` or `0x2` is **genuinely unresolved**. Both spellings
> ship, on branches whose authors each believed theirs was right: `Gen2` and `debug-gen2` write
> `0x1`, `far` and `deced` write `0x2`. The `Gen2` branch, the one whose README claims Gen2
> working, ships `0x1`. No A/B boot test exists. One three-way boot comparison on one card would
> settle it.

---

## NVLink

NVLink is fused off. `FUSE_NVLINK_DIS` reads `0x00000007`, the die scales to 12 links
(`PTOP_SCAL_NUM_NVLINK` = `0x0000000c`), and the links are **not** marked defective. Every route
below runs into the same fuse. See [NVLink hardware](../hardware/nvlink-hardware.md) and
[the NVLink frontier](../frontier/nvlink.md).

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| "NVLink already shows in the boot logs, so we just need a bridge" | `nvidia-nvlink: Nvlink Core is being initialized, major device number 236` genuinely appears on every 170HX boot and reads like the subsystem coming up | The message is emitted at `nvlink_linux.c:344` by the `nvidia-nvlink.ko` software core library announcing that it loaded. It is logged at `DBG_INFO` on essentially every driver load for any GPU, during early module load before GPU and GSP bring-up, and the "236" is a dynamically allocated char-device major that can change per boot. Reinforced by the one recorded run of `nvidia-smi nvlink`, on an 8-card rented host, returning "Device does not have or support Nvlink." | raised 2026-07-16 and 20, refuted by 2026-07-10 analysis |
| The "HULK" encryption blocker, per a project-adjacent public wiki page | It was the only published explanation and it had an authoritative tone | The site maintainer disowned it: "This hasn't been updated in some time, don't rely on that." The page's own author called it outdated. **Nothing** in any fuse readout, VBIOS dump or DevInit disassembly corroborates an encryption scheme gating NVLink | 2026-07-20 |
| "3090 reads `0x0` for `PTOP_SCAL_NUM_NVLINK`, so 12-versus-0 shows how much the 170HX gives up" | It is an inline comment in the project's own `probe.sh` and was copied into at least four write-ups | The project's own measured cross-card table says RTX 3090 = `0x00000004`, and every GA10x part except the A16 reads `0x00000004`, matching NVIDIA's documented four x4 links on GA102 exactly. Only the A16 reads `0x00000000` | comment propagated 2026-07-07 to 27, adjudicated 2026-07-28 |
| `FUSE_NVLINK_PHYS_DMG = 0x1` means the links are marked physically damaged | The register name is `OPT_SECURE_NVLINKS_PHYSICAL_DAMAGE_WR_SECURE`, and a set damage flag would be a one-way door | It reads `0x00000001` on **all fourteen probed Ampere cards**, including healthy A100s with fully working NVLink. It is a write-security bit, uniform architecture-wide. The register that would record damage, `FUSE_NVLINK_DEFECTIVE` at `0x0082068C`, reads `0x00000000` on the 170HX | flagged 2026-07-12 to 27, refuted by 2026-05-31 table |
| Writing `CTRL_OPT_NVLINK` at `0x008209B8` re-opens the links | It reads `0x00000000`, is documented as the *effective* per-link enable in bits [15:0], and is described as writable. This is the single most-cited "next step" in the corpus | Disproved by strong prior rather than by experiment: `FUSE_EN_SW_OVERRIDE` at `0x00820040` = `0x00000000` on the 170HX and all datacenter GA100 parts against `0x00000001` on all consumer parts, so the CTRL_OPT override mechanism is disabled at the fuse level, and `FUSE_DIS_SW_OVR` = `0x00000001`. The 25-entry `NV_FUSE_CTRL_OPT_*` table in the unsigned FwSec tail reads all zero on 13 probed GA100 cards. **Nobody ever tried the write** | proposed 2026-05-31 to 2026-07-25 |
| A FEAT_OVR-style attack on the NVLink mask | `FUSE_FEAT_OVR_DIS` at `0x008203F0` reads `0x00000000` on all cards, so the master override kill is not blown, and the compute unlock works by exactly this route in the same register block | The FEAT_OVR block `0x00823800` to `0x0082382C` has **no NVLink register**. Its twelve entries cover ECC, QUADRO, SM speed, row remap and readouts. There is nothing to write | suggested 2026-07-19 |
| "NVLink is software locked" | Several other 170HX restrictions genuinely are firmware or driver side | The disable is read out of OTP fuse `0x00820684` and mirrored into the read-only `STATUS_OPT_NVLINK`. Recorded because it was still circulating on 2026-07-27 | 2026-07-27 |
| The Titan V analogy: NVLink was disabled by VBIOS there | A genuine precedent on an earlier NVIDIA part | On the 170HX the value comes out of an OTP fuse, not a VBIOS setting. The mechanism does not transfer | 2026-07-24 |
| "Some dies have working VRAM but failing NVLink blocks, which explains the binning" | Exactly how salvage binning usually works | `FUSE_NVLINK_DEFECTIVE` at `0x0082068C` = `0x00000000` on every 170HX probed and on every card in one 15-card survey that returned a value, the unreadable A16 and the blank ES column excepted. That fuse is precisely the field that would record a bad link group. The disable is **segmentation, not salvage** | speculated 2026-07-06 |
| The NVLink fuse is a mining-SKU restriction worth attacking as such | Natural framing | The Drive A100 32 GB reads the identical `0x7`, so this is generic GA100 product segmentation | 2026-05-31 |
| A100 NVLink bridges contain active circuitry: a Microchip SM806022 clock generator and an EEPROM | The clock generator is a real, correctly specified part (52.08333 MHz crystal input, two 156.25 MHz differential HCSL outputs) genuinely found on consumer Ampere bridges, and consumer bridges do carry an EEPROM | Direct inspection of an official A100 bridge: bare PCB, neither part present. "a100 nvlink has neither eeprom or sig gen". The teardown summary was AI-generated from consumer-bridge material and corrected by someone holding the hardware. The consumer EEPROM is believed to hold per-board end-of-line impedance characterisation, not an ID | posted and refuted 2026-07-21 |
| A cheap 4-card active NVLink backplane for A100 exists | It would solve the topology problem outright | NVIDIA documents only the pairwise all-three-bridges Ampere topology, and NVSwitch exists only inside SXM platforms. The one real product identified is a Chinese 4x SXM V100 backplane with no switch, a different generation with unknown wiring | 2026-07-07 |
| Soldering the missing NVLink parts on from A100 schematics | The boards match, the schematics exist, and candidate parts were identified by designator (`R234`, `R237`, `R236`, `R1024`, `R238` from page 17, plus `R976`, `R1030` and `R1029`) | Blocked in order by: clean-room policy, since schematics were offered and refused; the three GPU-to-ground termination resistors having no visible tracks, so locating them requires a boardview or GPU removal with professional infrared rework; `R976` landing on ball `F51`, **under the chip**, on a package with a minimum of 82 ball rows; and the fact that even a perfect rework leaves `FUSE_NVLINK_DIS` at `0x00000007`. Caveat: `R237` is marked not-populated in the A100 schematic itself | 2026-07-06 / 07 |
| Characterise NVLink signal integrity before building anything | The correct engineering order of operations for a differential interface at these rates | The one available 60 GHz oscilloscope was judged insufficient, and renting adequate equipment was estimated at a few thousand for a month. Conclusion adopted: "Not like we need traceability on DIY nvlink boards. They either work or they don't." The cited "traces were around 60GHz" figure is second-hand and probably confuses signalling rate with bandwidth | 2026-07-22 |
| A single-slot 8-way NVLink backplane | Real PCB CAD work was done: repeated 124-pin NVLink footprints in a grid with differential-pair routing, multiple 8x SlimSAS connector footprints, "A100" in the copper pour, alongside single-slot cooling development | No board was fabricated, no link was ever brought up, no bandwidth was measured. 8-way requires an NVSwitch, which exists only in SXM platforms. And the fuse is still `0x7`. The only signal-integrity input was an LLM-written EM simulator predicting that without back-drilled vias the traces "do a lot of antenna at 37ghz but the simulator says it will just barely work" | 2026-07-08 to 12 |
| Buy one A100 bridge, reverse-engineer it, manufacture cheap copies | The bridges are assessed as fully passive by two people with datacenter hardware experience, and the economics are brutal at roughly 200 EUR each | Nobody bought one, nobody built one, and nobody in the corpus ever had a bridge in hand to test. Also pointless while the fuse stands | 2026-07-20 to 26 |
| Fabricate an A100 interposer from scratch | "the a100 interposer is pretty simple, just needs the connector", with a concrete signal-integrity strategy (Megtron laminate, or a non-standard inter-card orientation to minimise path lengths, plus a thick pour) | The connector "will likely need to be ordered in bulk", with an open worry that the 90-degree panel-mount version may be export-restricted. No connector was ordered, no board fabricated. And there is no fuse mask to attack, so the interposer would plug into dead silicon | 2026-07-20 |
| Mount two PLX backplanes face to face so NVLink edge connectors align | It sidesteps the slot-spacing problem entirely | Pure speculation, never drawn, never costed, blocked by the same fuse | 2026-07-19 |
| NVLink is the fix for the multi-card bandwidth problem | The baseline is PCIe Gen1 x4 at roughly 1 GB/s, and tensor parallelism was repeatedly described as "a waste of time without nvlink" | Tempered by a first-hand measurement on 2x RTX 3090 with NVLink showing only about a **10%** throughput bump on a 27B model under vLLM tensor parallel, with the observation that NVLink matters little with default llama.cpp settings. The counterpoint that the relative gain on a Gen1 x4 baseline would be far larger is reasoning only, and untestable while the fuse stands | 2026-07-27 |
| The P2P driver patch as a drop-in NVLink substitute | Real, shipping, well-documented code on the exact driver version `cmpunlocker` targets | **Not yet a dead end, but unvalidated**: GA100 is not in that branch's supported-configuration list (RTX 3090, 4090 and 5090 only), and no benchmark of P2P over the stock Gen1 x4 link was ever posted. Listed here because it was proposed and then dropped without anyone trying it | 2026-07-20 |
| "The CMP PCB has no NVLink connector at all" | Someone genuinely observed a shroud with an NVLink opening over a PCB without the connector | That observation belongs to the **CMP 90HX**, a GA102 board. The 170HX has the gold fingers and three connector positions | 2026-07-08 / 25, adjudicated 2026-07-28 |
| "It has triple (200GB/s?) NVLink, so PCIe is a non-issue" | Optimism | Retracted immediately on being asked "doesn't work though, right?" | 2026-07-19 |
| The A100 has 6x the NVLink bandwidth of a 3090 | Casual arithmetic | Corrected to roughly 3x. The correction is real but the replacement figure is not clean either | 2026-07-24 |

---

## ECC

ECC is fused off, no lever has been found, and there is no telemetry. See
[the ECC frontier](../frontier/ecc.md).

**Hypothesis.** Opening the ECC feature-override mask `0x00823800` (which gates `FEAT_OVR_ECC`
`0x82380c`, `ECC_1` `0x823810` and `ECC_2` `0x82382c`) and writing the shadows turns ECC on, giving
error visibility on the unlocked region.

**Plausible because** the shadow registers exist, are populated, the mask reads `0xffffff8f` cold on
the 170HX, and the high-secure ROP demonstrably can open it. This is the same shape as the compute
unlock that worked.

**Disproved by** two independent failure layers. The ECC-enable readout at `0x00823814` is
POR/fuse-latched and does not respond to live override writes. And `FEAT_OVR_ECC` is not in the
always-on domain, so the overrides revert on FLR anyway. `FBPA_ECC_CTRL` MASTER_EN bit 0 is
read-only. Multiple dedicated attempts (`fire_ecc_driverless_test.sh`, `fire_ecc_unlock.sh`) failed
and the result was written up as `ecc-unlock-dead.md`.

**Abandoned** 2026-07-16. Confirmed 2026-07-28 that **no `cmpunlocker` branch contains any ECC
write**.

Two further ECC dead ends:

- **The branch named `ecc` is not ECC work.** Its `driver/patches/` directory is byte-identical to
  master's and its only commit is `bb4d669 Fixed dual geometry support`. Its remaining differences
  from master are `README.md`, `constants.yaml` comments, `build.sh`, `install.sh`, `remove.sh` and
  a `requirements.txt` that master later deleted. Nobody should read it as ECC work. A related
  claim, that `| ECC | Planned |` and `| NVLink | Planned |` sit in the `ecc` branch README, is also
  false: those rows appear only in the `memory` and `housekeeping` branch READMEs.
- **The Maxwell-era ECC unlock ported to Ampere**, flashing a device-ID-edited Quadro VBIOS and
  force-installing the Quadro driver via INF, was demonstrated with photographic evidence on
  Maxwell and immediately caveated by the same poster: "As for how you would do that for Ampere? I
  have no idea... this is not trivial for Ampere". Never demonstrated on GA100. Date 2026-07-19.
- **Enabling ECC or PCIe Gen3 through the feature-override route.** Both are believed to be
  established by DEVINIT before the driver runs, which the ROP and feature-override approach cannot
  alter. PCIe is additionally double-locked at the fuse level (`FUSE_PCIE_GEN23_DIS = 0x1`,
  `FUSE_PCIE_GEN3_DIS = 0x1`) plus a five-byte devinit change, so a firmware-only patch is
  insufficient. Date 2026-07-24.

> [!NOTE]
> **Open problem**
>
> Whether the HBM stacks carry ECC provisioning at all is only partly answered. The A100
> per-FBPA `CSTATUS_RAMAMOUNT` differential (`0x07ff` / `0x0fff` against a consumer `0x0800` /
> `0x1000`) reads as ECC being reserved capacity inside the same stacks, but that is an
> inference from register values, not a datasheet. See [ECC](../frontier/ecc.md).

---

## VBIOS and flashing

Every entry here was a real attempt with a real result. This is the most directly reusable part of
the archive: none of these should be retried without new information. See
[the VBIOS](../hardware/vbios.md).

| Attempt | Why plausible | Result | Date |
|---|---|---|---|
| Full A100 VBIOS cross-flash onto a 170HX | Same PCB, same silicon, and it works on AMD Vega and MI50 parts | The card does not boot in secured mode and is unusable. Memory size, SM count and shader count do not change; only the subsystem ID changes. The boot ROM verifies the VBIOS against the device ID fused into the die, plus additional fuse-based ROM checks | 2024-07-17, reconfirmed 2026-07-19 and 2026-07-25 |
| A100 VBIOS onto a strap-modified 10 GB card | If you first get the 40 GB strap configuration, the A100 VBIOS might become acceptable | **Bricks the card.** Recovery required re-flashing the saved original ROM with an SPI programmer | 2026-06-23 |
| A locally patched 170HX VBIOS on Windows | The obvious next step after a strap-table analysis | Every patched image gave Device Manager **Code 10**, forcing all subsequent strap testing back onto the stock VBIOS | 2026-06-23 |
| DRIVE A100 (PG199, `10DE:20BB`) VBIOS via SPI programmer | Motivated by a screenshot appearing to show a 170HX reporting DevID `20BB`; a matching image was located | Flashing produced `NVRM: GPU 0000:0d:00.0: RmInitAdapter failed! (0x62:0x55:2674)` and the reported DevID **remained `10DE:20C2`**. The flash changed nothing functionally. A follow-up with a Windows flashing tool caused a BSOD | 2026-07-15 |
| Editing the memory strap byte `44` to `66` and fixing the checksum | The obvious fix suggested by the strap table analysis | The driver fails to load, consistent with the Falcon validating at power-up and dropping the chip into non-secure mode. Superseded by the runtime CFG1 write at `0x009a0204` after the FBPA mask is opened, which is what the shipping code does | 2026-06-26 |
| Simple ROM splicing, swapping A100 sections into a 170HX image | Sections look interchangeable | Fails on two counts: the strap-table offsets differ per ROM (`0x4285A` against `0x41D41`) and each section is independently MAC'd | 2026-05-08 |
| A single byte flip inside the signed range, at `0x41D53` (the CFG1 tier byte) | The minimal test of whether the MAC is enforced | The Booter stalled with `GFW_BOOT=0x001`. This is the empirical proof that in-MAC edits are closed without `csecret(2)` | 2026-05-08 |
| FwSec / VN image swap between SKUs | The VN preambles are identical across 170HX SKUs | Ruled out structurally by the body-size mismatch: every product line has a different FwSec body size, so nothing lines up | 2026-05-31 |
| A30 FWSEC module transplant | The boot ROM might not re-verify the whole VBIOS on a runtime FWSEC restart | Dead on arrival: the signed code modules are already **identical** between the 10 GB 170HX and the A30, so offering the A30 module gains nothing. The differentiating data is non-code configuration inside the verified section | 2026-07-27 |
| `nvflash` with patched image validation plus `--protectoff` | It gets further than stock | Then throws **`falcon halted`** when nvflash tries to run its ucode, and that ucode is the SPI writer itself. Other flashing tools likewise refuse an edited BIOS. The stated fallback is direct SPI, which requires removing the cooler and repasting | 2026-07-25 |
| Writing the SPI controller registers from software | The refire chain **did** successfully open the SPI mask at `0xD7D8` from high-secure mode, confirmed open with read and write protect both 0 | Despite the mask reading fully open: `SPI_DATA 0xE4A0` written `0xDEADBEEF` from PL0 read back `0x00000000`; `SPI_CTRL 0xE5A0` the same; `ROM_SERIAL_BYPASS 0xE204` the same; and direct high-secure writes to `0xE4A0` and `0xE5A0` did not land, with the registers staying `0x0`. Conclusion: a hardware write filter enforced by the secure boot state machine drops all writes to the SPI controller from any agent except the GFW boot firmware. **The CFG1 flash byte cannot be written by any software path on this card** | 2026-07-25 |
| NVGI as an attack surface | Inputs to devinit can be written into NVGI records | Anything NVGI writes into MR1, MR2 or MR3 is overwritten by devinit moments later using the table values for the boot strap, and writing masks from NVGI is futile because FWSEC re-raises them afterwards. Closed off by boot ordering | 2026-07-27 |
| TOCTOU on the VBIOS | The classic attack | The attempt wiped the VBIOS state-register data. With the clean stock driver the card then fails at `kgspExtractVbiosFromRom_TU102: did not find valid ROM signature` followed by `RmInitAdapter failed! (0x62:0x25:2028)`. PROM reads back all `0xFF` because `GFW_BOOT` is stamped **`0x8F`** rather than `0xFF`, so FWSEC ran but GFW never proceeded past it. **Reflashing a stock VBIOS did not help, because the state-register data was gone** | 2026-07-17 |
| 8 GB VBIOS onto a 10 GB card | Same product family | Performed with a patched flasher and reverted successfully, but the 8 GB image **does not boot on the 10 GB card**, and strap edits fail an image check during flashing. Suspected cause: the device ID. Caveat: no reboot was performed between flashes, so the result is suggestive rather than definitive | 2026-07-25 |
| VBIOS as host-CPU UEFI code, shadowed with an A100 ROM in a VM | Pursued for weeks from 2026-03-05. Opening an A100 firmware image showed no UEFI volume at all, read as evidence the ROM is not what it appears; and libvirt's `<rom file='...'/>` element inside `<hostdev>` genuinely does substitute an option ROM | Refuted by the boot-order correction: the device reads its VBIOS from SPI at power-up and the on-die Falcon validates it before any host software runs, so the `<rom>` element only replaces the option ROM the **host** sees. The theory's own author conceded. Never demonstrated to work by anyone with a card | 2026-03-29 |
| Flashing the "16 GB" TechPowerUp image to get 16 GB | The image was widely believed to be a leaked NVIDIA VBIOS built for a large mining customer | Flashed on an engineering-sample GA100 that accepts unsigned and mismatched VBIOS: the board still reported 8 GB. The same tester also flashed the 10 GB image and the board stayed at 8 GB. **Capacity is not a function of which ROM is loaded**; it follows the strap-selected CFG1 word | 2026-03-30 |
| Believing the TechPowerUp "Memory Size" column | It is the obvious place to look | It cannot be traced to any field in the `.rom` files. The "16 GB" image is the 8 GB image and the "0 GB" image is the 300 W overclock ROM | 2026-03-24 |
| `DEVID_REBRAND` as a VBIOS setting that changes how the card presents | The name is suggestive | Dismissed immediately as doing nothing, and corroborated later when a foreign VBIOS flash left the reported Device ID at `10DE:20C2` regardless. Root cause now known: `OPT_DEVID_SW_OVERRIDE_DIS` = 1 | 2026-06-23 |
| DEVID_SEL strap swap between `0x2082` and `0x20C2` | A reading of an NVIDIA patent plus `FUSE_PCIE_DEVIDA` and `DEVIDB` suggested the die is fused for both IDs and a strap could select between them | Contradicted by the observation that the alternate ID **reads as zero in firmware `92.00.67.00.01`**, making strap-resistor play pointless | 2026-03-25 |
| Resistor-strap modification to unlock memory capacity | The leading opinion in mid-2026 was that the "fuses" are really VBIOS values, and it works on RTX 3080 and 3090 for memory amount | **No correct resistor position was ever identified**, and no resistor mod was ever attempted on that basis | 2026-07-02 |
| CMP 100-210 to 32 GB V100 via a Titan V VBIOS | The Titan V VBIOS **is** accepted by the CMP 100-210 without modification | Titan V lacks NVLink and has only 3 of 4 HBM2 stacks enabled (12 GB against the CMP's 16 GB). **HBM stacks are disabled by physical fuses on the die, not by the VBIOS**, so no VBIOS can re-enable a fused-off stack | 2026-07-21 |
| VBIOS-only flashing of a CMP 100-210 to V100, skipping the strap mod | It avoids the soldering | Refuted by direct experiment the same day: the card enumerates but the device ID is unchanged, so the Linux driver binds it as a CMP 100 and loads the wrong binary blobs. "The resistors are required to change the device id." | 2026-07-23 |
| Modifying an already-decrypted VBIOS | With the ROM decrypted and disassembled, locations were identified for undervolting and for changing memory timings | **Every modification attempted resulted in a failed driver load.** Patching the driver to accept the modified state had not been tried | 2026-07-27 |
| Self-signing a custom VBIOS | Reported to have been briefly possible during a leak window | No usable signing capability exists now, consistent with the Booter and VBIOS debug keys being the named blockers. Treat the leak-window detail as anecdote | 2026-07-25 |
| VBIOS modification as a route around the GSP-RM problem | The natural first instinct | "Checksum failed", and the conclusion that the unlock lives in driver and firmware territory rather than flashable VBIOS regions. A test of defeating the Booter chip-ID gate via a VBIOS flash "didn't work at all". Observed failure: `kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x65 VBIOS version 92.00.66.00.02` | 2026-07-07 |
| The sim/emu HBM2e ROM as a template | It carries raised tier bytes | In the leaked sim build, straps 0 to 7 tier bytes were raised `66` to `77` for larger-die addressing, but **only the primary table was updated**: the second copy at `0x1AD72` still reads all `00 90 66 02`. Sim ROMs are roughly 230 KB with both copies inside the same image, a completely different layout from the 1,044,480-byte production ROMs, so nothing transplants | 2026-05-31 |
| Locating the Drive A100 license region from an MMIO dump | A reasonable survey method | The `NV_PROM` readback at BAR0 + `0x300000` shows all `0xFF` at both `0xFE000` and `0xFF000`. Whether that is a genuinely empty region or an artefact of the `NV_PROM` path is unresolved, since the readback shows the VBIOS as the GPU sees it and the table-of-contents structure may not survive that path. An SPI dump is required | 2026-05-31 |
| Predicting that flashing an 80 GB VBIOS would fail an internal check and refuse to boot | A reasonable prediction from the signature-check model | Refuted the same day by two people with hands-on results: it **boots fully and reports 80 GB**. The predictor conceded. The real limitation is stability of the untrained upper HBM region, not a boot-time signature or capacity check | 2026-07-27 |
| The license region is at `0xFF000` on the 170HX, by analogy with the A100 | The A100 layout is the obvious model | Corrected to `0xFE000` to `0xFEFFF` after verification across five dumps by three methods. This matters because `nvflash` on the 170HX dumps only 1020 KB, so the region **is** inside the nvflash window whereas on the A100 it is not | 2026-05-16 |
| `0x2000` (RFRD) is a power table with `0x200D` and `0x2025` as power-limit bytes | It reads like one | Superseded by the image-layout-descriptor reading, in which `0x200C` is `pci_option_rom_size`, the MAC-verified range size, and `0x200D` is merely its high byte. **Both parser scripts in the same analysis still carry the stale naming**, printing "RFRD power:", so tooling output remains misleading | 2026-05-31 |
| "If I corrupt NVGI there is no recovery path at all" | A reasonable fear | Self-corrected within one minute: a hardware SPI programmer makes it recoverable. Practical rule: have an external flasher on hand **before** touching NVGI | recorded |
| "Timing data is shared across all strap indexes" | An LLM analysis of the dump | Corrected the next day by the same person after re-reading: the data is shared across the 8 GB and 10 GB SKUs, but individual straps carry different timings | 2026-07-24 / 25 |

Two VBIOS-adjacent corrections worth stating plainly:

- **"The RSA-signed region ends at about `0x45000`" is imprecise on two counts.** The boundary is
  `0x43A00` on 250 W 170HX ROMs and `0x43C00` on the 300 W ROM, declared by the RFRD `field_0C`, and
  it is a **symmetric MAC keyed on `csecret(2)`**, not an RSA signature over the image. RSA is used
  by the boot ROM to authenticate Booter code, a separate mechanism.
- **The 432 / 729 / 1458 MHz memory-clock "three-way conflict" is not a conflict.** It is one clock
  at three multiples; the VBIOS field is quarter-rate.
- **"The 8 GB SKU carries `92.00.6D.00.0A`" is wrong as a blanket statement.** Two physical 8 GB
  cards dumped 2026-07-26 reported `92.00.67.00.01`, and four cards across two hosts showed both
  versions in the field. `92.00.67.00.01` is the production 8 GB image; `92.00.6D.00.0A` is the
  later 300 W overclock image.

---

## Drivers and the kernel patch set

See [driver patches](../unlock/driver-patches.md) and
[driver versions](../procedures/driver-versions.md).

### The two-load architecture

**Hypothesis (2026-07-05 to 07).** Unlock in load 1, then reload a clean driver in load 2 and keep
the result.

**Plausible because** the geometry write demonstrably lands and survives `rmmod`.

**Disproved by** a circular dependency that was real, not imagined. Load 1's failed-GSP driver
re-locks SEC2's reset mask at `0x008403c4` on unload, which is a driver-side action the ROP cannot
prevent, and the FLR needed to clear it reverts the non-always-on geometry. Separately, WPR2 must be
cleared for the second load, but clearing it re-raises the reset mask to `0x8f`, blocking the stock
`kflcnReset` and yielding `0x65`. WPR2 state also could not be cleared by PL0 host writes between
the two boots.

**Abandoned** 2026-07-07. The stated conclusion at the time is exactly what shipped: "the exploit
must set geometry and finish the boot in one pass, leaving a live GSP-RM that the clean patched
driver inits against the unlocked size." A second escape route was found in between: the driverless
work of 2026-07-22 clears WPR1 and WPR2_HI so a stock driver boots with **no FLR at all**.

### The 3 MB WPR2 placement mismatch

**Hypothesis (2026-07-13).** The Booter carves WPR2 at a fixed native-10 GB top,
`[0x277700000, 0x27fee0000]`, about 136 MB, strap-derived because FWSEC ignores the 40 GB override.
The driver's first-attempt layout `[0x277400000, 0x27ff00000]` (about 139 MB) starts exactly
`0x300000` (3 MB) below the Booter's base and is about 3 MB too large. On retry the driver moves
progressively further away (`0x277400000`, then `0x26e800000`, then `0x265c00000`), never
converging. "That 3 MB, a suspiciously round number, is the whole defect."

**Plausible because** the numbers were exact, decoded from registers, and the divergence pattern
looked like a classic off-by-a-region bug.

**Disproved the same day** by building a byte-exact WPR2 layout: "a byte-exact WPR2 layout does NOT
resolve 0x55. So 0x55 was not (only) a placement problem." The real fit-check lives inside the
closed Booter ucode.

**Abandoned** 2026-07-13.

### Fighting the project's own leftover patch

**Belief.** A class of `0x55` failures was hardware or geometry behaviour.

**Reality (2026-07-13).** A leftover CMP 170HX driver patch from an earlier `0x55`-fix attempt had
hard-set `placeFbSize = 8 GB`, putting the driver's layout below where the Booter carves WPR2 at the
native-10 GB top. "So we're partly fighting our own patch." This retroactively explained days of
"geometry reverts" observations: "who knows how many days that was there... I've been working with a
10 GB card for over a week now."

**Lesson recorded at the time:** always re-baseline against a pristine tree. The clean test proposed
was a stock unmodified driver with no `fb_size` override.

### Other driver dead ends

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| The `kflcnIsRiscvActive` false-negative theory: the PL0 read of the HS-locked RISC-V CPUCTL returns `0xbadf...` and false-negatives, so deleting the `return NV_ERR_NOT_READY;` in the else branch would let boot proceed | HS-locked registers really do read back poison at PL0 | Disproved hours later the same day: `kflcnIsRiscvActive = NOT_ACTIVE` was a **true** negative. `msgqRxLink -7` means GSP-RM never wrote its queue header, and the queue lives in system memory so geometry could not have moved it. The bypass only relocated the failure from `0x62:0x55` to `0x62:0x65`. **No `kflcnIsRiscvActive` bypass exists anywhere in the six shipping patches** | 2026-07-11 |
| Binary-patching `nvidia.ko` to bypass the WPR2 check: find the byte pattern `0f 84 40 08 00 00`, then `74 11` at offset -13, and change `74` to `eb`, turning `je` into `jmp` | It avoids a roughly three-minute driver rebuild | "Unfortunately. No luck." The author agreed it was not the best solution. A source-level downgrade is what shipped | 2026-07-06 |
| Clamping `pWprMeta->fbSize` to `CMP170HX_WPR2_SAFE_LIMIT 0x0A00000000ULL` (40 GB) | A way to keep WPR2 inside a size the firmware would accept | Never shipped. The released design widens `fb_length` and the last FB region and clamps only the BAR0/PRAMIN window instead. Verified absent from the shipping repository | proposed 2026-07-12, dropped by 2026-07-18 |
| Mailbox-value-based tolerance of GSP-RM init timeouts: replace the assert around `kgspWaitForRmInitDone` with a read of `NV_PFALCON_FALCON_MAILBOX0`, treating anything other than `0x00000000` and `0x00000031` as "alive, proceeding" | `0x31` genuinely does appear during the early mask Booter passes and is usually harmless | Never shipped. The literal `0x00000031` appears nowhere in the shipping code. The README instead documents that Booter status codes such as `0x31` and `0xffff` during the early passes can appear and are often harmless if the final boot succeeds | proposed 2026-07-12, dropped by 2026-07-18 |
| The unconditional `gpuValidateRegOps` bypass | A debugging convenience while poking registers from user space | Present in the pre-release leaked diff, **dropped before release**. This is a meaningful safety improvement, not just cleanup: the shipping driver does not silently disable register-operation permission checks for every consumer of that path. Verified absent from the shipping repository and from all twelve unreleased branches | gone in 0001 to 0006 |
| Nouveau plus Vulkan as an escape from NVIDIA's user-space restrictions | A fully open path from kernel to userspace would in principle bypass any driver-level throttling | Refuted end to end. Nouveau does not load as a module for non-VGA devices, so the 170HX is never picked up at all. On a CMP 90HX where nouveau *does* bind, it reports `fb: 10240 MiB of unknown memory type`, `BIT table A not found`, `Pointer to TMDS table not found` and `Cannot find any crtc or sizes`, and a Vulkan `llama-bench` run there gave llama 8B Q4_K_M `tg512` at **5.07 ± 0.13 t/s**, roughly 20x slower than the CUDA path. Two independent conclusions kill it: the throttle is not in the proprietary user-space stack, and nouveau's GA100 and GA102 support is far too immature to be usable even if it were | 2025-03-18 |
| "535 is the newest driver supporting CPU-RM on GA100" | Relayed second-hand | Refuted the same week by direct testing on 580. The split is by **mode** (GSP versus `NVreg_EnableGpuFirmware=0`), not by driver package | 2026-07 |
| "A modified NVML could raise clocks beyond boost" | GSP-RM and CPU-RM showed different clock behaviour | **Self-retracted in an edit to the same message the same day**: "edit: looks like NO". The real explanation was NVML version matching between driver and tool | 2026-07-24 |
| "CPU-RM serves only one CUDA context per module load" | An observed lazy 4 GB per channel behaviour reverting to 2 GB when no context was active | **Self-flagged as probably bogus within 90 minutes** because the sizing only worked for a single kernel. The underlying behaviour was later re-explained as the UVM atomic-fault decode flip | 2026-07-23 |
| "GSP LibOS logs are empty, the 170HX produces no GSP-RM log at all" | Nothing renderable ever appeared | The logs were never empty, merely **undecodable**: release firmware strips the format-string database (`pLogElf = 0`) so `kgspDumpGspLogs` cannot render packed records. Measured `GSP-LOG[INIT] put=0x44` (68 bytes) and `GSP-LOG[INTR] put=0x94` (148 bytes), proving GSP-RM booted and ran its interrupt task. The buffers live in **unprotected system RAM**, not in the framebuffer and not in WPR, so the `0xbadf5040` poison-lock does not hide them. In the `0xFFFF` failure case the `GSP-LOG[RM]` task buffer is NULL, so RM task logging never got set up and RM init fails very early | refuted 2026-07-07 and 2026-07-14 |
| The floorswept-partition WPR2 theory for `msgqRxLink -7`: the driver places GSP-RM's boot region at the top of `fbSize`, so with a 40, 64 or 80 GB LMR that region lands in floorswept or untrained partitions | It reads like "the same floorsweep wall, one stage earlier" | **Never directly tested**, and partially undermined the next day when a clean first load let the second load boot to 10240 MiB with geometry writes landing, suggesting SEC2 taint was the real cause | 2026-07-11 |
| The BAR2 self-test bypass (`PDB_PROP_GPU_BROKEN_FB`, `gpuIsCacheOnlyModeEnabled`, `kbusIsBar2TestSkipped`) | Identified in source as ways to skip the BAR2 virtual self-test while `0x24:0x72` was blocking boot | **Never exercised**: the WPR2 teardown fixed the underlying cause instead. It remains a documented, untried escape hatch | recorded |
| `RmDefaultTimeout=15000` | A cheap thing to try | Reported to have **zero effect** on the CPU-RM Booter path, with identical results from both CPU-RM and GSP-RM. Put out for independent confirmation; none arrived | recorded |
| The `0x24:0x72` "cryptographic dead end" | Plausible framing at first | Reversed the same day: `0x72` decodes to `kbusVerifyBar2`, a BAR2 and MMU test, not SCP crypto, proven by the code path and by the error appearing even post-FLR | 2026-07-16 |
| Writing 0 to SEC2 MAILBOX0 (`0x00840040`) as a sixth ROP write | It looked like tidy state hygiene | Present in one revision of a test script, removed in the next with the comment `NOTE: SEC2 clear (0x840040) is INTENTIONALLY REMOVED.` Clearing the mailbox destroys the only status oracle the operator has. No later payload writes the mailbox | 2026-07-11 |
| Fear that NVIDIA would pull the vulnerable driver versions | 580-branch download URLs were 404ing while 610.43.02 downloaded fine, and members archived every 580.167 file pre-emptively | The 404s were at least partly **mistyped version strings**: 580.189.04 and 580.183.02 do not exist, and 580.159.04 is the correct pack version. No confirmed removal of a working version occurred, and the open modules on a public host cannot be recalled | 2026-06-30 |
| "The exploitable driver version is 580, so a 610 driver claiming 64 GB is suspicious" | A reasonable provenance objection | The objection was itself wrong: the shipping unlock targets nvidia-open 610.43.02 and 610.43.03. Separately, the practical point stands, since kernel modules cannot be sandboxed and an LLM scan of a binary blob is not a safety guarantee | 2026-07-18 |
| AI-generated CMP 90HX unlock guides on public repositories | They look like the real thing | Refuted concretely: the patch sets PCI device ID `0x2684` while the real card reports `0x260d`. Two people who had done GA102 work dismissed the repository outright | 2026-07-27 |
| A Reddit-sourced unlock method | It circulated | Dismissed by two participants as "cope" with no technical rebuttal and no test. Recorded so it is not rediscovered; the method's content survives only as a screenshot | 2026-07-21 |
| "CMP 170HX cards get bricked by the unlock or by NVIDIA-poisoned drivers" | Fear travels fast | **No first-hand report exists.** The modification edits registers and is reversible. The specific public case cited was assessed as a 10 GB card being pushed to 80 GB | 2026-07-24 |
| The `housekeeping` branch's patches would apply cleanly | They look complete | Adding the `0x2082` arms increased the number of inserted lines but the hunk counts were not updated: patch 0001 had `@@ -102,6 +102,21 @@` where it should be 23, `@@ -4821,6 +4844,104 @@` where it should be 117, and `@@ -5164,6 +5285,50 @@` where it should be 53; patch 0006 had `@@ -1521,6 +1521,11 @@` where it should be 15. This is exactly what the single `ecc` commit fixed | 2026-07-18 |
| The `PG199` branch implements DRIVE A100 support | The name says so, and the arithmetic works (4096-bit bus, "8x4 = 32 or 16x4 = 64 possible") | Nothing was ever committed. Its diff against master touches only `README.md`, `constants.yaml` comments, `build.sh`, `install.sh`, `remove.sh`, `requirements.txt` and a deleted PR template. Its profiles are byte-identical to master's. **`0x20BB` appears nowhere in the repository.** Supply of PG199 boards was described as nearly nonexistent | branch dated 2026-07-18, assessed 2026-07-26 / 27 |
| "10 GB-card register state `CFG1=0x22779000 LMR=0x0000028a` is apparently the PG199 config" | It reads like a real capture | The capture is genuine, the label is not. That state is the **after** side of the 2026-07-27 PMU-devinit run on a live 10 GB 170HX, and it produced no extra usable memory. It is not a PG199 configuration: the PG199 dump reads CFG1 `0x22779000` with LMR `0x0000020a`, not `0x0000028a`. `0x22779000` is also not a value any shipping or branch code writes, so **do not use it as a target** | adjudicated |
| Editing `common/constants.yaml` changes the built geometry | It is named like a configuration file and reads like the source of truth | **No script, patch or Makefile reads it.** The values that actually reach hardware are the bash `case` in `driver/build.sh` and the constants baked into `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`. `constants.yaml` is documentation. Its content happens to be correct on master, so no wrong value shipped, but the file has no authority | adjudicated 2026-07-28 |
| `--profile` selects geometry on master | It did on the `memory` branch, whose patch 0001 defines a single device ID with one baked geometry | On current master, patch 0001 contains all six markers the `build.sh` guard looks for, so the Python rewrite prints `runtime device-id geometry` and exits without editing anything. `--profile` now affects only the printed banner, the expected-MiB figure, and the metadata files. The `multiple-cards` branch made the demotion explicit in its help text. **Users following pre-2026-07-18 instructions will find the flag no longer changes the unlock size** | adjudicated |
| `install.sh` auto-detection is safe on mixed-GPU hosts | It looks like it detects the CMP | `detect_card_profile()` reads `nvidia-smi --query-gpu=memory.total` piped through `head -1`, which is the **first GPU in nvidia-smi order**, not the CMP found by `lspci`. A system with an RTX 3080 10 GB alongside an 8 GB CMP 170HX detected "10GB" from the 3080 and selected the wrong profile. Reproduced by at least two users; both worked around it by always passing `--profile` explicitly. A separate report has other CMP SKUs misdetected as 10 GB 170HX cards | 2026-07-25 |
| `multiple-cards`' `verify.sh` handles every detected ID | `install.sh` greps for all three of `10de:20b0`, `10de:20c2` and `10de:2082` | `verify.sh`'s `lspci` fallback greps only `10de:20c2` and `10de:2082`, silently dropping `0x20B0` | 2026-07-19 |
| The shipping README is accurate about device gating | It is the primary document | It says the unlock "runs automatically every time the patched modules boot GSP for PCI ID `0x20C2`". The code gates on `0x20C2` **or** `0x2082` in `_kgspSec2PostblTimingEnabled()`, in every one of the six patches and in `install.sh`. The commit that widened it is titled "Unlock isn't gated anymore". Only `0x20b0` is detected but not unlocked. The `ecc` and `PG199` branch READMEs carry the same stale "`0x20C2`-gated" phrasing | adjudicated |
| "All PLMs must show `0xffffffff`" | It is in the project's own debugging documentation and in a milder form in the shipping README | Over-general and wrong for one of the four. `WPR_CFG` at `0x001fa7cc` is deliberately opened to **`0xfffff0ff`**, and the loop's own success test `if (regVal == plmTable[plmIdx].value)` treats that as open. Users should not read `WPR_CFG=0xfffff0ff` as a failure | refuted 2026-07-27 |

Three further facts about the shipping patches that no mined claim recorded, and that anyone
auditing the tree should know:

- **Patch 0001 removes the "WPR2 already up" bail for all GPUs, not just the CMP.** This could mask
  a genuinely bad GPU state on unrelated hardware if the patched modules are ever loaded on a mixed
  system.
- **`stockFbBytes` is hardcoded to 8 GiB for the 10 GB card too**, in `0003-late-pma.patch`
  (`stockFbBytes = 0x200000000ULL; /* 8GB */`, used for both device IDs), where the true stock
  framebuffer on `0x2082` is `0x280000000`. No failure has been attributed to this.
- **A GA102 adaptation comments the whole WPR2-already-up block out entirely** with
  `// Bypass WPR2 check (for CMP 90HX compute unlock)`. The GA100 shipping patch only weakens it to
  a warning. The GA100 behaviour is the canonical one for the 170HX.

> [!NOTE]
> **Open problem**
>
> Whether the 595, 590 and 580 ports in `clanker/driver-port` actually boot is unknown. The
> patches apply cleanly and the sizes are plausible, but no boot has been reported on any of them,
> and the branch's `VERSION` and `constants.yaml` disagree about which versions are even claimed
> (12 against 5). Boot-tested versions remain exactly `610.43.02` and `610.43.03`. Note also that
> the `610` port directory is a **byte-for-byte copy of master** at 37,415 bytes across six
> patches (19741 / 3988 / 10580 / 861 / 1642 / 603).

---

## Tooling, measurement and AI-assisted work

| Dead end | Detail | Date |
|---|---|---|
| `deploy.py --path vbios-memory` | Never worked. Produced `[vbios-memory] ERROR: Not a PCI Option ROM (bad magic at 0x00)` and aborted. The tool expected the inner image extracted from the full ROM dump rather than the raw dump, and a reviewer noted the code path "seems to have been written by [an LLM] based on unconfirmed assumptions" and that the only thing a modified VBIOS gets you at that point is a non-working device. The whole VBIOS-memory approach was dropped | 2026-06-23 |
| `deploy.py --path sec2-rop` tool-integration break | `deploy.py` invoked `load_custom_bin.py --verify`, but the loader's argument parser did not accept `--verify`, so it exited with code 2 and the whole path aborted with `unrecognized arguments: --verify`. **Not a hardware failure.** Recorded because it cost time and looked like an exploit failure | 2026-06-22 |
| `stack_gen.py`'s first release zeroed all canary slots | It could not have worked: the canary at `D[0x6340]` must be replicated into every frame or `__stack_chk_fail` at `0x7dd9` fires. The author flagged it at post time ("accidently zeroed all canaries") | 2026-07-04 |
| `load_gsp_sec2_falcon.py` could not load an exploit-patched GSP image | `parse_gsp_firmware()` used a blind 3/4 IMEM, 1/8 SEC, remainder DMEM size estimate and dumped the whole blob sequentially into `IMEM[0]` starting at `BOOTVEC=0`. The patched firmware requires exact placement: `booter_load_wpr_main` at `0x22ba`, a 63,488-byte uniform-fill DMEM payload, the signature buffer target at DMEM `0x0800`, the canary at `DMEM[0x6340]`, and the ELF sections `.bootstrap`, `.ga100_text` and `.tu10x_text` at specific IMEM offsets. Replaced the same day by a two-level ELF parser; the working path used in-driver delivery instead | 2026-07-16 |
| `probe.sh`'s advertised `/dev/mem` fallback does not exist | The header comment reads "Falls back to /dev/mem path if resource0 fails", but the resolution block ends with a hard `exit 2`. Anyone relying on the documented fallback on a host without sysfs `resource0` gets a hard failure | 2026-05-31 |
| `z2_parse_vbios_table.py` carries stale artefacts that contradict its own output | The strap-table docstring says "~0x3FB18 in A100 PCIe" while the comparison table places it at `0x4285A`; `extract_rfrd` still says "power table"; `extract_fbpa_tier_table` searches a window that will match the CFG1 table itself if nothing else qualifies, so its "FBPA tiers" output may be a duplicate; and `find_subsystem_id` is a stub. Anyone using the output labels verbatim propagates all of these | 2026-05-31 |
| Days of unattended LLM agent work failed to produce an 80 GB unlock | One user ran a coding agent for over three days on one model plus a couple of days on another, keeping a progress file, using retrieval, indexing several ROMs, and feeding the leaked source and the open driver source as context, with no result. Plausible because the same class of agent had reproduced the VRAM unlock before it was public | 2026-07-25 |
| An LLM agent falsely declared cards bricked | An agent fed all the raw logs did reproduce the compute unlock, but then "completely lost how it did it and spent 2hours figuring out what it did", and context bloat caused it to forget the cards could be reset and to claim they were bricked. **They were recoverable by reset.** Related warning: "It's really tough keeping the [agent] from going off the rails when hardware mods are on the table, basically everything gets blamed as a hardware wall" | 2026-07-15 |
| Frontier assistants produced plausible-looking hallucinations throughout | Documented concrete failures: an assistant asserted the `0x10aa` write path with knowledge not derivable from the Booter code alone; an assistant used the GP102 local memory range address instead of the GA102 one; an assistant refused to disclose the reconstructed stack contents it was using. Retractions traceable within a single chat chunk include `CONFIG4 = 0x9A0210` (wrong register), "timing data is shared across all strap indexes" (wrong scope), "no recovery path at all" for NVGI (wrong), and "secure_teardown yields a clean resetPLM" (wrong) | 2026-07-06 and 2026-07-26 |
| Asking a commercial assistant where board components are | The assistant confidently placed two specific resistors "adjacent to the other high-value 100k strap resistors", described them as 100 kΩ 0402 parts tied to specific nets, and named two crystals with exact frequencies on a named schematic page. When challenged on reference-designator logic it reversed itself completely: "No, it is not likely that they sit next to each other... Components with vastly different component numbers... are almost always placed in completely different sections of a PCB." Recorded verbatim as a cautionary data point: **fabricated board topology reads exactly like real board topology** | 2026-07 |
| Uncensored or abliterated models | "Don't bother with uncensored models, they often get dumber as a result of uncensoring." Guardrail refusals were instead worked around with a framing prompt asserting owned-hardware research and citing prior public disclosure | 2026-07-06 |
| A shared MCP server and retrieval corpus for participants' agents | Abandoned the same day for time reasons, with an archive posted for anyone to pick up. Nobody did | 2026-07-16 |
| Double-counting the mask range scan | Two archived copies of the same scan exist: a 13,544-byte raw typescript (28 seconds of wall time, complete with the operator fumbling a command line) and a 12,265-byte cleaned copy posted two days later in a different channel. A programmatic diff of all 510 address and value pairs found **zero differences**. Treating these as two independent observations is a mistake | 2026-07-18 |
| `gsp_tu10x.bin` needed extracting | It is openly distributed by NVIDIA with the driver. The decompressed, decoded and annotated blob at issue is the **debug Booter**, not the GSP binary | 2026-07-21 |
| GeekBench misidentifies the CMP 170HX as an engineering sample | Single unchallenged first-hand report; relevant to anyone submitting or comparing results | 2026-07-21 |
| Killing a stuck `llama.cpp` process | Left ghost processes that wrecked driver state; recovery required a host reboot by the operator, since the cards could not be restarted from inside the container. A practical operational failure mode for multi-tenant hosting | 2026-07-27 |
| The PoCL runtime-level FMA workaround | Three files patched, but the reviewer flags it incomplete (`mad24()`, `mad_hi()` and `mad_sat()` are not covered) and publishes no benchmark number proving it reaches the source-level route's result | 2023-10-25 |
| The compiler-level FMA workaround generalises | A transparent compiler or runtime patch does not affect built-in function behaviour; GPU kernels are often shipped precompiled as machine code, and most HPC libraries contain hand-tuned assembly that relies on FMA. The technique is only tractable for self-contained codebases. **This is the practical ceiling on the FMA bypass** | 2023-10-25 |
| The 1-second register re-apply loop | A third-party commit rewrote the geometry registers every second. Dismissed by two experienced reviewers and by a tester who never needed it: "you do not need the 1sec refresh/reapply. it is excessive", diagnosed as "they're doing it because they're fighting against the driver for the compute retiming. has nothing to do with the mem unlock... sledge hammer instead of spoon". The same review found the commit "surprisingly not bullshit but incomplete, would work for 40 but anything above nada" | 2026-07-16 |
| The stale TechPowerUp URL `gpu-specs/cmp-170hx.c3824` | Returns HTTP 200 and was in circulation, including in an agent brief, but redirects to an unrelated AMD product page. The correct entry is `c3830` | 2026-07-27 |
| TechPowerUp as a spec source for CMP parts | Wrong twice in this domain: it lists 8 MB of L2 for the 170HX where the part actually has 32 MB (corroborated by latency-spike measurement), and it implies 80 of 84 SMs for the CMP 100-210 where the real figure is 68 of 84 | 2026-04-22 and 2026-06-19 |
| A GPU-Z screenshot showing an A100 40 GB BIOS on a "170HX" with 64 GB VRAM and 6144 SM units | Identified within a minute as a PG199 board, not a 170HX. The original poster accepted the correction | 2026-07-19 |
| "Too few SMs after the flash" | The tool was reading a display GPU in the same machine, not the CMP under test. Self-corrected within minutes. **Lesson: when the CMP has no display output, always verify which device a GUI tool is reading** | 2026-06-23 |
| The mmapeak screenshot used as proof of card ownership | Disproved by side-by-side comparison of the original, a blog repost and a forum comment: byte-identical figures with **zero run-to-run variance**, which does not happen across real repeated runs. The original author confirmed the attributed name was not theirs | 2026-07-24 |
| The 96 GB CMP 170HX screenshot, and the "re-fuse the device ID from `0x2082` to `0x20BB`" theory built on similar images | The bit-superset observation (`BB` is a superset of `82`) is arithmetically true and 96 GB A100 variants do exist. The author posted a self-correction within the hour: `10DE 20BB` is the device ID of a DRIVE product, and the likelier explanation is cheap A100 Drive modules reballed onto 170HX e-waste PCBs. Others noted the PCI ID and GPU name in the screenshots were mutually inconsistent, the VBIOS versions did not match, and 80 GB is electrically impossible with only four HBM stacks on a 4096-bit bus. Independently confirmed by `OPT_DEVID_SW_OVERRIDE_DIS` = 1 | 2026-07-15 |
| Telegram and marketplace sellers claiming a working memory and SM unlock | Someone who read the source channel reported that participants there were merely debating whether such an unlock exists: "They don't have any unlock at all" | 2026-07-17 |
| `clpeak` as the tool for measuring the FMA and DP4A patches | Rejected in-channel: "Clpeak isn't the right way to test them". mixbench CUDA and cuBLAS-based tensor tests were recommended instead. clpeak remains useful as a full-device dump | 2026-06-26 |
| `OpenCL-Benchmark` as a complete performance picture | It is the accepted proof-of-unlock artefact, but it **does not measure tensor cores at all**. Anyone reading only its output will conclude the card does about 12.5 TFLOPS and miss the roughly 190 TFLOPS tensor path entirely | 2026-07-12 |
| `CUBLAS_COMPUTE_16F` reporting 10,748 TFLOPS | Disproved by the probe author noticing the call returns instantly: passing a `float` alpha and beta pointer to a 16F compute type makes the GEMM a **no-op** | 2026-07-27 |
| `1769.47 GB/sec` as a measured bandwidth figure | Disproved arithmetically: 864 MHz x 4 x 4096 bits / 8 = 1769.472 GB/s exactly. It is a computed peak from the clock and bus-width fields printed two lines above it, as is the accompanying `12633.60 GFlops` | established 2026-07-28 |
| The AI-generated 4-card and 8-card throughput table | Disproved by the author's own admission ("Naw just estimate values based on other ppls results") and rejected in-channel within the hour. **Worth keeping: the pessimistic counter-estimate that replaced it, "more like 100 t/s prefill, 2 t/s decode", was also wrong**, being beaten by a real multi-card pipeline-parallel run at 2600 t/s prefill and 30 t/s decode. The correction to a bad number was itself a bad number, in the opposite direction | 2026-07-27 |
| Locked-mode numbers mistaken for a successful unlock | mixbench 12 BF16 TFLOPS, clpeak 367 GFLOPS and a custom GEMM at 6.25 TFLOPS were briefly taken as post-unlock results, because the tools ran cleanly and returned self-consistent numbers. Disproved by comparison against the roughly 202 TFLOPS BF16 ceiling, an order of magnitude short; identified as "the performance of tf32 in locked mode" and the user concluded the payload had false-landed | 2026-07-12 |
| A 2026-07-13 write-up's compute table read as measured data | 12,500 GFLOPS FP32 SGEMM and 6,200 GFLOPS FP64 DGEMM were presented as results while the document's own Next Steps still said "Benchmark: Run clpeak to verify full compute performance". **The dispute was about provenance, and the provenance criticism was correct; the numbers happened to be right anyway**, because a theoretical 70-SM GA100 at 1410 MHz is 12,633.6 GFLOPS and the card achieves about 99% of that. "An LLM computed the theoretical peak and formatted it as a result" is a failure mode that recurred at least three times | 2026-07-13 |
| "35B in NVFP4 at 154 tok/s on a 170HX" | Disproved by the per-instruction MMA sweep, which enumerates every FP4, FP6 and FP8 MMA variant as "not supported" on this sm_80 device. Either the number is for a different device, the quantisation format is misreported, or it is marketing. Recorded because it was used commercially to justify pricing | 2026-07-21 |
| "llama.cpp disables FMA when it detects a 170HX during build" | Never tested and never substantiated. The observed vLLM advantage has simpler explanations. Recorded as a hypothesis, not a finding | 2026-07-20 |

### Inference-stack dead ends

These belong to [LLM inference](../operations/llm-inference.md) but are recorded here because they
are expensive to rediscover.

| Dead end | What disproved it | Date |
|---|---|---|
| Tensor parallelism at PCIe Gen1 x4 | Direct A/B: TP2 on a 72B AWQ model was 2.3 to 2.8x **worse** at prefill for only +23% decode; TP8 on a large MoE was roughly 4x worse than PP8 at prefill and gave 3.4 t/s decode, or crashed outright. Multiple operators converged: "TP would choke to death on gen1x4" | 2026-07-20 to 27 |
| Vulkan for multi-card work | Without good `VK_KHR_device_group` driver support all card-to-card transfers go through host RAM, and the ggml/llama.cpp Vulkan backend does not support device groups at all. A direct hardware test with 2x V100 plus an NVLink board "did not work whatsoever. It only worked for CUDA." | 2026-07-20 |
| MTP on vLLM for a 35B MoE | MTP gave a clean +21% on llama.cpp on the same model with 75% acceptance, so it looked safe. Measured: 113 tok/s with MTP against 147 tok/s without. A backend-specific dead end, not a model-specific one | 2026-07-21 |
| MTP combined with pipeline parallelism | Currently incompatible in vLLM; on the TP8 path it went straight to out-of-memory | 2026-07-27 |
| SGLang for MTP workloads | "sglang doesnt like mtp". The tester also expected SGLang to beat vLLM on concurrency and was surprised it did not | 2026-07-27 |
| A widely cited AWQ INT4 quant on vLLM | Actively harmful as a dead end because it is the quant most published guides cite. The MoE kernels reject asymmetric quantisation. Use symmetric quants instead | 2026-07-27 |
| llama.cpp for any DSA-attention model | Head-to-head: 124 to 162 t/s prefill and 17.2 t/s decode against vLLM's 2,675 t/s, caused by a dense-attention fallback. It also degrades with context, the opposite of vLLM | 2026-07-27 |
| Loading a 467 GB model on an 88 GiB-RAM host | The load-time compute-graph pass pinned resident memory at 87.6 GB with roughly 820 MB/s of continuous disk re-reads until out-of-memory, even though the weights genuinely reached a roughly 431 GiB VRAM plateau. Reproduced across two loaders and multiple flag sets; `swapon` was blocked in the container | 2026-07-24 |
| `VLLM_USE_PRECOMPILED` editable install for a patched vLLM | It ships no `vllm._C` and will fail. The working approach is the release wheel with the patch's Python files applied as a diff onto site-packages | 2026-07-27 |
| A prebuilt CUDA backend library on a mismatched CUDA host | Silently degrades to a CPU-only weight load followed by out-of-memory rather than erroring cleanly, which made it hard to diagnose | 2026-07-24 |
| GPU offload as a way to speed up prefill | Normally true, but backwards on this card at Gen1 x4: pp2048 33.44 t/s with three 40 GB cards holding one layer plus buffers for a roughly 460 GB MoE, which the tester put at "~30% down" against CPU plus DDR4 alone. Decode went the other way, "~60% up", so offload is worth it only if decode dominates. Relative deltas only; the CPU-only rates were never posted | 2026-07-20 |
| Expecting the extra unlocked VRAM to unlock qualitatively better models | Going 40 GB to 84 GB let one user run the same 27B model with a longer context, and "even with an 8x64 and 512GB, LLMs like [the largest models] still cant run". A statement about the model landscape at these sizes, not about the hardware | 2026-07-23 |
| The DP2A substitution on other CMP parts | On a Volta CMP: no difference at default micro-batch (353.59 to 354.14 pp512) and a severe drop at micro-batch 56 (977.20 to 757.22). That card uses a different throttling mechanism and is far less nerfed. On P100 it is structurally impossible, since dp2a and dp4a were both introduced in sm61 and the P100 is sm60 | 2026-06-14 |
| 3D Gaussian splat training on this card | **Predicted** poor rather than measured poor: splats have few dense matrix multiplies and generally do not use lower-precision formats, so they run on standard CUDA cores where the card is weak. Nobody ran an actual splat benchmark, so this is not empirically closed | 2026-07-21 |
| "PCIe bandwidth is a nothing burger" | Correct for single-card workloads and contested as soon as it was generalised to multi-GPU. It conflates pipeline with tensor parallelism, and the measured TP prefill collapse settles it for TP. It was **not** the consensus | 2026-07-22 |
| Row-split tensor parallelism on 170HX links | Circulated alongside the layer-split command but annotated "benchmark-only on these links" | 2026-07-22 |
| "Tensor cores don't work on the unlocked card" | Three days before the claim was repeated, a tester had measured 165 TFLOPS FP16 on a cuBLAS tensor-core benchmark on an unlocked card. The consistent reading is that tensor cores were **throttled, not absent** | claim repeated 2026-07-19 |
| "It's only relevant for mining. These things will be ass for LLM inference" | The same archive contains a working 8-card, 512 GiB deployment running a 239 GB quant at 17.3 tok/s single-user, and post-unlock figures of roughly 12,500 GFLOPS FP32 and 6,200 GFLOPS FP64. The genuine limitations that surfaced are interconnect-side, not compute or capacity | 2026-07-16 |

---

## Thermal, power and cooling

See [cooling](../operations/cooling.md), [thermals](../hardware/thermals.md) and
[power and PSU](../operations/power-and-psu.md).

### The 3.24 W snail fan sold as a 300 W A100 cooler

**Hypothesis.** The commonly sold printed "A100 cooling" adapter with a 3.24 W blower handles a
300 W card, because that is what the vendor advertises.

**Plausible because** it is the default purchase, it physically fits, and the listing says so.

**Disproved by** first-hand measurement: **150 to 180 W maximum at full duty from a direct PSU
feed**. On a 250 W card that is not enough, and it is nowhere near 300 W.

**Abandoned** 2026-07-20. This is the single most directly actionable cooling correction in the
archive: anyone buying the standard adapter is buying roughly half the cooling capacity the listing
claims.

### Other cooling and power dead ends

| Hypothesis | Why plausible | What disproved it | Date |
|---|---|---|---|
| A VBIOS power-limit modification to 300 W plus better cooling unlocks significant performance | 250 W is well above measured draw and the card looked thermally constrained | Direct A/B against the same tester's 250 W baseline: roughly **180 to 185 TFLOPS BF16, +2.8%**, with core and memory both below 65 C. Thermals were not the limiter; the core does not want to clock higher | 2026-07-24 |
| Repopulating the roughly 6 missing VRM phases raises the ceiling | An A100 restoration guide exists and reads as a parts list | The added parts stabilise voltage rather than add headroom; you would also have to reconfigure the PWM controllers to activate the phases; an overloaded PWM either trips protection or burns out; and "seems a huge amount of handwork, maybe better to keep TDP below original 250 Watts" | 2026-07-07 / 18 |
| Delidding to replace the die-to-IHS thermal interface material | Factory TIM quality on server parts is unknown and thermals looked like the constraint | Closed by argument, not experiment: "We struggle to hit 250 W with GPCs disabled. That would have to be fixed first." **Nobody delidded a card.** A secondary motive was floated and left open: if an HBM stack is physically too short to contact the IHS properly, that could be why it is disabled, particularly on the 8 GB card | 2026-07-27 |
| Low FP32 power draw indicates thermal or power throttling from a hardware fault | Under 75 W on a 250 W part with slow FP32 looks exactly like throttling | Disproved by the reviewer's own follow-up and by an independent benchmark result from a separate tester on Windows showing the same low draw: **the FP32 lockdown is the cause and the low power is the effect**, not the reverse. A healthy 170HX legitimately reports under 75 W in a conventional FP32 stress test. A genuine unrelated hardware failure did occur on that card later, which is why the two must be distinguished | 2023-10-25 |
| `nvidia-pstated` will cut 170HX idle power | It took a CMP 90HX from 75 W to 5 W | On the 170HX `NvAPI_GPU_SetForcePstate` returns `NVAPI_ERROR` because the card exposes only P0, and the two-P-state fork that works on P100 and V100 produced "no change for 170". The remaining live lead is flashing a PCIe A100 VBIOS, which does contain several P-states. **Never attempted** | 2025-01-16 / 2026-07-20 / 26 |
| VRM duty-cycle registers `0x20340` and `0x20344` are a route to higher clocks | A shot in the dark, posted as such | **The reasoning is self-contradictory as written**: if there is no PLL controlling clocks, a duty-cycle change alone should not set clock. Never tested. These addresses appear nowhere in the shipping unlocker or in any of the thirteen trees. Separately flagged as an **overvolt hazard**: re-executing devinit via the PMU at runtime could push the VRM past **1.3 V** with a wrong value, because the devinit region containing timing and MRS programming is part of the training section that also covers clocks, PLLs and voltage-ID PWM | 2026-07-24 / 27 |
| Flashing a different VBIOS widens the memory bus or re-enables stacks | VBIOS flashing changes so much else | "No! The memory interface and the active FBPs and stacks is set in fuses. The VBIOS has no effect on them." This also explains why the strap-resistor experiment produced no CFG1 change | 2026-07-25 |
| The GA100 die shot proves the bus cannot be widened, because 2 of 6 HBM sites are dummies | The die shot is real, and dummies visibly exist for mechanical reasons: uneven pressure distribution when mounting coolers leads to worse cooling and a higher chance of cracking the die | Contradicted the same day on three grounds: bonding yield is genuinely bad; each 1024-bit interface is really 4 x 256-bit channels so partial enablement is a real state; and **you cannot tell a dummy from a real die non-destructively** | 2026-07-18 |
| A5000 and A6000 blower shrouds are a drop-in | "the PCB is the same shape and size as those used by Ampere and later workstation GPUs" | Contradicted on different screw holes and no fan connector. **Neither side posted a photo**, so this remains disputed rather than closed | 2026-07-26 |
| Friction-fit printed fan ducts are adequate | They were the default community answer | Repeated mechanical failure: both the single-GPU and dual-GPU versions "simply fall off". Multiple owners independently converged on "the card has screw holes so might as well use them" | 2026-07-20, re-confirmed 2026-07-21 |
| Sleeve-style shrouds, and pushing air through the card | Symmetrical intuition | Consistent first-hand accounts of considerable blowback; pulling works much better than pushing; sleeve types do not work in two-slot spacing. Not quantified | 2026-07-27 |
| Boring out the stock two-slot shroud for an integral fan | It reuses what is already there | Works for a single card or spaced-out cards, but fails for adjacent installs because two-slot cards leave no intake gap between them. The counter-proposal of one external 120 mm fan with a duct across both fin stacks was argued to be simpler and quieter. Neither side produced a measurement. The pro-blower case was explicitly conditional on the GPU PCB fan-header pads being active, which was never established | 2026-07 |
| Mounting an AIO cold plate to the IHS via a copper adapter plate | Several people had reportedly done it and it avoids sourcing a rare full-cover block | Disproved on this attempt by a photographed pump-out failure: cracked paste and bare copper across much of the die contact area, with the AIO failing before a game finished loading. Attributed to poor mounting pressure or an incompatible adapter | 2026-07-19 |
| SXM waterblocks fit, possibly with straps and a thick thermal pad | A cheap route | SXM blocks are physically incompatible with PCIe cards, and a block designed for the non-IHS A100 80 GB will not seat properly on an IHS variant regardless | 2026-07-20 |
| 90 C is a fine operating temperature for this chip | Consumer GPUs tolerate it | Corrected emphatically in-channel, then confirmed by the same person finding their own throttle onset at **80 C** | 2026-07-27 |
| An 8000 RPM 40 mm fan will be enough | It is a high-RPM part | Abandoned by its own proposer once the 80 C throttle onset was discovered: "guess 8k rpm won't do." By 2026-07-27 the 40 mm class had been empirically split: one 15,000 RPM 40 mm fan gives 90 C hotspot, two give 70 C and 76 C | 2026-07-27 |
| "Any fan will do" | Early generic guidance | Superseded by a working rule: the 170HX heatsink is not large, so it needs above-average airflow, with a minimum of 4 W or 0.35 A at 12 V, radial or 38 mm thick axial | 2026-07-20 to 27 |
| A PCIe 8-pin cable can be used in the card's EPS socket | The two look interchangeable | The connectors are keyed differently and can only be forced together; the 12 V and ground lines are swapped on some pins between the two types, so forcing it **damages the card** | 2026-07-22 |
| "2x 8-pin power connectors" (as listed in a third-party spec database) | It is in the database and was never corrected there | The teardown resolves it: **two logical rails, one physical connector**, a single EPS 8-pin | 2023-10-25 |
| "There is no working power-limit control on the CMP 170HX" | Frustration with the lack of headroom | Refuted by the corpus itself: `nvidia-smi -pl` at 100, 150, 160, 175, 200 and 300 W all appear in posted telemetry from multiple testers, and `nvidia-smi -q` reports Min Power Limit 100.00 W and Max Power Limit 250.00 W. What is genuinely absent is **headroom above stock** and **an idle P-state**, not the mechanism | mistaken claim 2026-07-25 |
| Optane persistent memory on a dual-socket host as an expert-offload feed | Per-module idle is about 3.5 W since it does not need active power to maintain state, and the modules could feed experts to GPUs over PCIe | Disproved by measurement: the dual-socket 1.2 TB system idled at **400 to 600 W** even with low P-states, against a single-socket EPYC whole system at 80 W | 2026-07-26 |
| Reflowing a failed HBM2 stack with a heat gun | Reflow does fix BGA solder-joint failures on other hardware | The stacks are bonded to the **silicon interposer**, not to the PCB. One member tried it on several HBM2 GPUs at a range of temperatures over several hours with no success | recorded |
| A BGA reball on a CMP-class card | A standard repair | Attempted first-hand and failed: `nvidia-smi` hangs on access despite the test harness reporting no errors afterwards. Worth recording as a failure **mode**: a clean test result can still coexist with a card that hangs the driver | 2026-07 |
| Preheating the whole board in an oven before capacitor rework | It is standard advice for some rework | Immediately rejected as a beginner trap ("that is terrible advice lol"). The described real-world consequence of over-preheating is a bent PCB, broken internal traces and cooked ICs, producing subtle defects that are extremely difficult to diagnose afterwards | 2026-07 |
| An iron is not enough for the 0402 capacitors, you need hot air | A reasonable default for 0402 work | Explicitly retracted by the person who held it: an iron works, with the qualification that all the lead-free solder must be wicked away first and leaded solder used | 2026-07-26 |
| Applying 3.3 V to a "manufacturing_mode" pin found on some cards | Observed on real hardware by a tester who had cross-flashed several GA100 VBIOS images, with real-world precedent from bypassing a similar mechanism on industrial equipment | Neither this nor the companion proposal (diff PCB schematics between A100 engineering samples and production A100s to find a weirdly enabled pin) was ever pursued to a result. **Nobody characterised what the pin does** | recorded |
| Soldering chips into the CMP 90HX's two unpopulated memory slots | The pads are there | Purely theoretical; nobody attempted it. Objections: the channels are disabled during devinit; in stock form the card does not accept double-density chips; and double-density G6X chips are unsupported by the VBIOS on every Ampere card except one, which is why no 48 GB variant exists. Two incompatible mechanisms, fuses versus straps, were proposed for how density is selected and **neither was tested** | recorded |
| A "$1000 CMP 170HX waterblock" style listing | The listing photo shows the card | What ships is worthless. The pattern is a cooler or accessory listing baiting buyers who think they are buying the GPU. Independently corroborated | 2026-07-25 |
| The 10 GB card is the better buy | It has more stock memory and a wider bus | Superseded: the 10 GB card likely inherits the weaker Samsung HBM2 memory system of the A100 40GB and A30 lineage, it unlocks to only 40 GB against 64 GB, its memory is locked at 1215 MHz with no core-clock offset, and no 300 W overclock VBIOS applies to it. Community verdict by 2026-07-18: "As of current it looks as if those with the 8gb cards are the winners". Inference from public specifications, **not directly measured** | 2026-07-18 |

### Strap resistors

Strap resistors deserve their own note, because the idea recurred at least six times in different
forms and is refuted every time for capacity.

**Hypothesis.** The stock 10 GB configuration `LLLLH` can be switched to `LLLHL` for 40 GB or
`LLLHH` for 80 GB, and more generally the memory strap resistors select capacity.

**Plausible because** the straps demonstrably select memory configuration in the VBIOS strap tables,
and the A100 schematic's GPU strap configuration table really does map STRAP2, STRAP1 and STRAP0 to
vendor-specific RAMCFG values. The idea originated from an LLM suggestion and was labelled a
hallucination by the maintainer after the fact.

**Disproved by** exhaustive permutation on 2026-06-23: all 8 combinations of the last three straps
on a 10 GB card with stock VBIOS produced **no capacity change on any of them**. `LLHHH` bricked the
system entirely with no POST. Physically removing three straps also changed nothing, so they default
to something. A second tester independently confirmed no effect, and the maintainer accepted the
debunk the same day. Re-confirmed on 2026-07-25, when a physical re-strap of a 10 GB card left CFG1
unchanged at `0x02449000` while an unmodded card reached the same capacity by software alone.

**Abandoned** 2026-06-23, re-confirmed 2026-07-25.

Follow-on strap dead ends:

- **"The resistor mod enabled the 80 GB decode change."** On 2026-07-24 a physical re-strap of a
  10 GB card was credited with enabling the L2 decode change to `0x10000300` and
  with the 80 GB result. The "before" value is context-dependent: `0x70000300` (dirty),
  `0x60000300` (clean 40 GB fire), `0x10000300` (post resistor mod or live UVM atomics).
  On 2026-07-25 the probe showed `FBPA_CFG1_BROADCAST = 0x02449000`, i.e.
  unchanged from stock, and an **unmodified** 10 GB card reproduced the same 80 GB state with the
  refire script. The dependency was retired within a day.
- **Re-strapping RAMCFG to the 8 GB pattern to make the 64 GB path apply to a 10 GB card.**
  Disproved by source code: the shipping driver selects CFG1 and LMR from
  `pGpu->idInfo.PCIDeviceID >> 16`, not from any strap or RAMCFG value. A tester performed this
  exact modification on 2026-07-24 and no boot or train result was ever reported.
- **A `strap5` resistor switching between the two fused device IDs.** Plausible: the die genuinely
  carries two device-ID fuses (`OPT_PCIE_DEVIDA 0x008204d8` and `OPT_PCIE_DEVIDB 0x0082056c`), the
  proposer had located five other strap resistors, and the mechanism is described in an NVIDIA
  patent. Dead for two reasons: the strap was never located, and the five-strap map published a week
  later enumerates exactly five straps with no `strap5` among them.
- **Re-fusing the device ID** (10 GB `2082` to `20B2`, or `20C2` to `20F2`) to allow flashing a
  genuine A100 VBIOS. Never attempted. Weaknesses stated in the proposal itself: blowing more fuses
  generally further degrades the card, and the message contains an internal inconsistency. `20B2` is
  a known typo for `2082`, corrected in-channel on 2026-06-29. The two 170HX IDs are `0x20C2` (8 GB)
  and `0x2082` (10 GB).
- **"Strap2 gives 40 GB and Strap1 gives 80 GB via a read-only RAMCFG strap into the L2 decode
  latch."** The person relaying it flagged the resistor designators and positions as completely
  unverified and did not know which physical strap was which. Undercut by its own author, who noted
  the 40 GB unlock already works with no hardware modification at all. A measurement script
  involving repeated soldering and desoldering was drafted and never executed.
- **Identifying the VRAM strap resistors by reading `0x101000` bits [23:20], moving one resistor,
  cold booting and re-reading.** LLM-generated and judged sane apart from a criticism that it
  recommended shorting rather than moving the resistors. Never attempted. Contradicted by a same-day
  statement that there is no known way to read back which strap value is selected, the only
  indication being the value at `0x009A0204`. Made moot by the register-write path.
- **"Hardware unlock is impossible."** Stated flatly on 2026-06-29. **Partially wrong.** It is true
  for VRAM capacity via straps, but false for PCIe lane width, where the capacitor modification is
  the only route and works reliably. The accurate statement is that hardware modification cannot
  move fused boundaries but **can restore depopulated PCB features**.

Two further capacitor-modification notes. The dielectric is **X7R**, not "XR7", a transposition that
propagated widely: the canonical part is 24 x 0402, 220 nF (0.22 uF), X7R, rated 6.3 V or higher, in
the C1100 to C1350 designator range, with Taiyo Yuden `MAASJ105SB7224KFCA01` as the confirmed
manufacturer part. And the claim that the shipped unlock README documents the x4 limitation is
**false**: a grep across the entire working tree, the full history and all twelve branch checkouts
finds zero occurrences of "capacitor", "AC coupling", "solder" or any lane-width register or
wording. The technical claim about the capacitors is true and well evidenced; only the
attribution to the shipped README is wrong.

---

## Documentation defects in the project's own docs branch

The `docs` branch (`cmpunlocker-branches/docs/`) is the most dangerous artefact in the project,
because it looks authoritative, it is inside the project's own repository, and it is wrong in ways
that would cause a working unlock to be reported as a failure. **Do not treat it as a reference.**
Everything below was verified against the shipping source.

### Invented acronym expansions

| Term | What the docs branch says | What it actually is |
|---|---|---|
| **PLM** | "Program Logic Modules", as in "The SEC2 Booter executes firmware sequences (PLMs)" | **Privilege Level Mask.** It is a property of a register, not a module that gets executed. The shipping code writes privilege-level-mask registers: `0x001fa7cc` WPR_CFG, `0x009a0148` FBPA, `0x001fa7c4` WPR and `0x00823804` FEAT |
| **PMM** | "the PMM (Permute Mask Model)", and a "SEC2 Booter PMM" | **Appears nowhere in the code.** The term is an invention |
| **LMR** | "LM Request" and "LM (Local Memory) Request register" | The register is `NV_PFB_PRI_MMU_LOCAL_MEMORY_RANGE`: Local Memory **Range**, not Request |
| **SS0 / SS1** | "Suspension State" registers that "artificially disable clusters of SMs" | `FEATURE_OVERRIDE_SM_SPEED_SELECT` (`0x0082381c`) and `FEATURE_OVERRIDE_SM_SPEED_SELECT_1` (`0x00823820`). They control per-instruction-unit **issue rate**, not which SMs are active |
| **PMA** | "Power Management Array", with "PMA is reconfigured for the enabled SM clusters" | The RM **Physical Memory Allocator**. `0003-late-pma.patch` is pure memory-manager code: it declares `PMA_REGION_DESCRIPTOR`, walks `pHeap->pPmaObject`, calls `memmgrIsPmaInitialized`, and logs `pmaFreeBefore`, `pmaTotalBefore`, `pmaFreeAfter`, `pmaTotalAfter`, `heapFree` and `heapTotal`. The "late PMA" step extends the high PMA region to cover the newly exposed framebuffer. It has **nothing to do with power management** |

### Wrong values and wrong log lines

- **"cmpunlocker writes `0xffffffff` to both SS0 and SS1, enabling all clusters."** The shipping
  code writes `GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U)` and
  `GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U)`, and `common/constants.yaml` agrees
  (`ss0: "0x88888888"`, `ss1: "0x00000008"`). Verified identical in all 15 copies of
  `0001-sec2-postbl-plm-ss-cfg.patch` across master and every branch.
- **The expected dmesg lines `SEC2_DEBUG: SS0 = 0xffffffff` and `SEC2_DEBUG: SS1 = 0xffffffff`**
  (`docs/ARCHITECTURE.md` lines 81 and 82) will never appear. **Anyone validating an unlock against
  those strings will wrongly conclude it failed.**
- **The log line `SEC2_DEBUG: Executing unlock sequence...`** is printed in the documentation as
  expected output. **It does not exist anywhere in the code.** Do not grep for it.
- **"Sets PLM permissions to `0xffffffff` (all PLMs enabled)."** Three of the four are opened to
  `0xffffffff`, but **`WPR_CFG` at `0x001fa7cc` is written `0xfffff0ff`**. The loop's own success
  test treats `0xfffff0ff` as open. Master's README carries a milder version of the same imprecision
  ("Expected: PLMs opening to 0xffffffff").
- **"Injects custom PLM sequences."** The code opens four specific privilege-level-mask registers by
  re-running Booter Load with a doctored signature buffer. There are no injected sequences.
- **"Stock firmware sets these to disable ~50% of the SMs."** Both SKUs enumerate all 70 SMs at
  stock, and SM count is unchanged at 70 before and after the unlock.
- **`sudo ./uninstall.sh --yes`** (docs branch `README.md` line 68 and `docs/INSTALLATION.md`
  line 40). **No `uninstall.sh` exists** in any snapshot, including on the `docs` branch itself. The
  correct command is `sudo ./remove.sh --yes`, and the same branch's `ARCHITECTURE.md` line 118 says
  so, so the branch contradicts itself. See [uninstall](../procedures/uninstall.md).

### Other documentation defects, outside the docs branch

- **The `80` branch README's "Working ✓" row for 80 GB.** "Working" in that README means "reports
  the size and boots", not "passes memory validation". The author's own assessment on 2026-07-19 was
  far more modest: "I'd say even having 80GB show up in nvidia-smi without rejected boot is a
  success (for now)."
- **`DEBUGGING.md`'s remedy "All the PLMs must show `0xffffffff`."** See above.
- **The shipping README's `0x20C2`-only background sentence.** The code gates on `0x20C2` **or**
  `0x2082`. The README's own table two paragraphs later lists both cards.
- **The 170th-Street specification page contradicts itself on SM count**, giving 70 SMs in its
  compute table and "8GB variant: 56 SMs, 4,096-bit memory bus" in its closing note. The register
  accounting settles it at 70.
- **The 170th-Street timeline page still says the PCIe capacitor mod is "documented but unconfirmed
  on the 170HX specifically".** Superseded by the same wiki's own modification page, which records a
  confirmed 170HX success in April 2026 with before-and-after `lspci` output.
- **The 170th-Street specification page still says "PCIe Gen 1 x4 (firmware locked), ~1 GB/s"** while
  the same wiki's unlock page lists Gen2 speeds as a feature.
- **The NVLink comparison table in the reference material is internally inconsistent**, printing
  "NVLink killed, CTRL_OPT override path under investigation" while the same document establishes
  `FUSE_EN_SW_OVERRIDE = 0x0` and therefore "CTRL_OPT fuse override disabled, cannot be changed,
  inert on 170HX". The fuse measurement wins.

---

## Values that propagated through chat but are absent from shipping code

These are not wrong so much as **superseded and still circulating**. Each is a real value from a
real working artefact at some point in the project's history. None of them is what the shipping
driver does.

### The guard value `0xFACEB13D`

**Where it came from.** The proof of concept used `0x4a7` filler. On 2026-07-04 the community
adopted `0xFACEB13D` by convention, explicitly rejecting `0xDEADC0DE` and `0xCAFEBABE` as overused
and possibly present in NVIDIA's own code, which would make attribution ambiguous when reading a
DMEM dump. ROP v1 planted `0xFACEB13D` both at `D[0x6340]` and in every stack canary slot.

**What ships.** `0xc0deca7e`, written to payload offset `0x5b40`, which is DMEM `0x6340`. The fill
dword for the rest of the buffer remains `0x000004a7`.

**Why it does not matter functionally.** The mechanism is value-independent: the guard word only has
to match. Three values are valid for the same reason. The `0x4a7` filler was separately believed to
be a functional requirement and was explained on 2026-07-04 as merely a self-loop detector that lets
the host see the Falcon parked in the panic loop rather than wandering. It is not needed for the
exploit to work, though the shipping driver still uses it for exactly that diagnostic reason.

**Why it matters documentarily.** Anyone grepping a shipping payload dump for `0xFACEB13D` will find
nothing and may conclude the payload is malformed.

An intermediate design also existed: the `0x10b9` multiwrite chain replaced the plant-a-matching-word
approach with a **pointer trick**, passing `GUARD_ADDR 0x6340` as the operand in both canary slots so
the compare is self-referential, with a guard value of 0 acceptable. The shipping driver reverted to
plant-a-matching-word but with a different constant.

### The gadget `0x10b9`

**Where it came from.** Research chains standardised on the `0x10b9` mid-entry with `r0` and `r1`.
It is the clean chainable encapsulation, because it ends in `mpopaddret $r3 0x4` and walks straight
to the next write frame. Every community multiwrite chain uses it, and a long-standing belief that
`0x10b9` "drops additional writes" past the first was diagnosed on 2026-07-15 as a reverse-order
slot bug in the generator, not a mechanism fault. It chains natively.

**What ships.** The shipping driver uses the **`0x10aa` full entry** with `r10` and `r11`,
marshalled by the elevators `0xcbd` and `0x1fbd`. `0x10aa` is the gadget planted in the shipping
payload at offset `0xf788`. In the shipping payload the address literal is `0x000010aa`.

**Both work.** The wiki must not conflate them: a chain written for `0x10b9` semantics will not read
correctly against a shipping payload dump, and vice versa. The shipping payload is a separate,
single-write lineage.

### The `0xFFxx` versus `0xF7xx` "divergence"

**The claim.** A provenance review noted that the community's DMEM offsets cluster in the `0xFFxx`
range while the shipping patch's payload offsets are `0xF7xx`, and concluded that the community was
either working against a different Booter build or had not yet converged on the correct layout. It
was written up as a high-concern item in a leak-derivation assessment.

**Why it looked real.** The two documents genuinely print different numbers, and different numbers
usually mean different things.

**What it actually is: a units artefact, not a divergence.** The payload is DMA'd to DMEM `0x800`.
Therefore **payload offset plus `0x800` equals the DMEM address**, and the two sets of numbers are
the same addresses in different frames of reference:

```text
payload 0xf754 + 0x800 = DMEM 0xFF54
payload 0xf7c4 + 0x800 = DMEM 0xFFC4
payload 0x5b40 + 0x800 = DMEM 0x6340   (the canary guard)
payload 0x1100 + 0x800 = DMEM 0x1900   (the 0x7 that secure_teardown restores)
```

The assessment cited the patch offset as suspect and the DMEM address as clean **on the same slot**.
The rest of that review holds up: its inventory of the three exit strategies (`secure_teardown`, the
premature exit `0x8117`, and `multiwrite_then_mutexfree_cleanexit`) and its identification of
`0x8403C4` as the reset mask are both correct.

**Date settled:** 2026-07-18.

Two adjacent provenance concerns from the same assessment were also disproved:

- **"Deriving the offsets requires an emulator, NVIDIA-internal stack-frame documentation, or the
  leaked Booter source."** Every code address in the chain is an instruction boundary in a
  disassembly published 2026-07-01; the gadget semantics and `mpopaddret` epilogues were tabulated in
  a public atlas on 2026-07-10; and the six-field `0xFF48` / `0x18` frame grid was in a public git
  commit on 2026-07-15 and in a prose write-up the same day. All of that predates the leaked diff.
- **"Offset `0x5b40` receiving `0xc0deca7e` is present in no public source."** The published paper
  gives `buffer=0x800` and `guard@0x6340` in its emulator trace, and publishes
  `guard: 0x00000000 -> 0xc0deca7e` as the stub value. `0x6340 - 0x800 = 0x5b40`. Both the offset
  and the value are reconstructible with one subtraction.

### Other values worth checking before you quote them

| Circulating value | Shipping reality |
|---|---|
| FEAT mask opened to `0x000000FF` | `0xFFFFFFFF`. `0xFF` sets only the read and write nibbles and leaves `SOURCE_ENABLE` at 0. A researcher separately reported writing `0xFFFFFFFF` into the 50HX feature-override mask, matching the flag description, with no success, so the correct encoding is **necessary but not sufficient** on every part |
| CFG1 `0x27790000` for "64GB of usable VRAM" | `0x02779000`, the same digits shifted one nibble right |
| The five-value recipe of 2026-07-07 (`0x009A0204 = 0x02779000`, `0x008200FC = 0xFFFFFFFF`, `0x00823804 = 0x000000ff`, then host SS0 and SS1) | Two of its three high-secure values did not survive: the shipping patch opens `0x00823804` to `0xffffffff`, not `0x000000ff`, and **never writes `0x008200fc` at all**. The host-side SS0 and SS1 pair survived verbatim |
| A three-write ROP payload carrying SS0, SS1 and the FEAT mask in one fire | The shipping design is structurally different: the payload carries **one** address-value pair, and Booter Load is re-fired four times, once per mask, with WPR2 lo and hi (`0x001fa824` and `0x001fa828`) restored before each attempt. SS0 and SS1 are then written by the host, not by the payload |
| The five-word live-WprMeta injection into `kgspExecuteBooterLoad_TU102` | A real and correct description of the clean-room driver patch of 2026-07-10. It is **not** in `cmpunlocker` master or in any of the twelve archived branches |
| The five-entry `FB_GEO_PLMS` list and the `0x00900204 + n*0x4000` per-FBPA loop, described as part of the shipping tool | Those addresses appear **nowhere** in `sources/cmpunlocker`. They belong to the clean-room driverless refire chain, a separate unreleased toolchain. Keep the two paths distinct |
| Six FB-geometry masks must be opened | Five suffice; `0x100b38` was dropped on 2026-07-16. And the **shipping** tool uses four masks and one broadcast CFG1 write |
| A RISC-V trampoline patched into `gsp_tu10x.bin` at file offset `0x1C485D0` with a 128-byte trampoline at `0x1CF6110` | Nothing resembling it survives. Every offset was pinned to driver 580.159.03 and the integrity guard was never even populated. The shipping patch does all register writes from the host kernel module after the masks are open |
| A userspace persistence daemon polling `/proc/driver/nvidia/gpus/<BDF>/clients` to re-apply within 250 ms | Replaced by in-driver application at every GSP boot. Residue survives: `remove.sh` still stops a unit and kills a watchdog that the current installer never creates, and still deletes five `gsp_tu10x.bin.cmpunlocker.*` suffixes |
| `Booter run status` as a success signal | The Booter run status reads `0xffff` on **every** run, success or not. **Readback is the only verdict** |
| "Thirteen unreleased branches" | **Twelve** unreleased branch snapshots (`80`, `Gen2`, `PG199`, `clanker/driver-port`, `debug-gen2`, `deced`, `docs`, `ecc`, `far`, `housekeeping`, `memory`, `multiple-cards`), or thirteen trees counting shipping `master`. One document says fourteen while enumerating twelve |
| "The Gen2-family branches add a fifth mask entry" | They add **five** new entries for a total of **nine**: XVE `0x00088ff4`, XVE_B `0x00088ab4`, XVE_C `0x00088ff8`, FEAT2 `0x00823b00` and OPT_PLM `0x008200fc`, all `0xffffffff` |
| Per-FBPA aperture stride `0x400` | `0x4000`. The broadcast aperture is `0x009A0000` to `0x009A3FFF`, i.e. `0x4000` wide, which is the per-instance window size |
| `0x008200FC` is `FUSE_SS_PLM`, or `0x008200FC` is `OPT_PLM` | Same register, two names. The branch code literally writes `{0x008200fcU, 0xffffffffU, "OPT_PLM"}`, so `OPT_PLM` is the code name and `FUSE_SS_PLM` the clean-room tooling name. Carry both aliases on one entry |

---

## Recurring failure patterns

Six patterns account for most of the 507 entries. Recognising them early is worth more than
memorising any individual dead end.

**1. A theoretical peak computed and then formatted as a measurement.** This happened at least three
times: the `1769.47 GB/sec` bandwidth figure (864 MHz x 4 x 4096 bits / 8 exactly), the
`12633.60 GFlops` beside it, and the 2026-07-13 compute table. In the last case the numbers happened
to be right, which made the provenance criticism look pedantic. It was not pedantic; the same
process produced wrong numbers elsewhere. **Ask where a number was measured before asking whether it
is plausible.**

**2. A register whose name is exactly what you want.** `SM_ISSUE_RATE_MODIFIER`,
`RMOverrideSmSpeedSelect`, `CTRL_OPT_NVLINK`, `FUSE_HALF_FBPA_EN`, `PTOP_FS4` bits literally named
`GEN2_PCIE`. In every case the name was accurate and the register was still not the lever. **The
cross-card probe is the cheapest disproof available**: if a full-speed A100 reads the same value, the
register does not encode the restriction.

**3. Reading back a register that was never written.** The "direct write" theory measured four
write-and-readback pairs that formed a tidy pattern, and every one of the "read-backs" was the
untouched stock value. `0xffffff8f`, `0x02449000` and `0x208` are the documented stock values.
**Always confirm the write landed somewhere, with a positive control on a register you know you can
move.**

**4. Units confusion presented as a substantive divergence.** Payload offset versus DMEM address
(`+0x800`), BAR0 offset versus Falcon aperture (`| 0x14000000`), quarter-rate versus effective memory
clock (432 / 729 / 1458 MHz), per-user versus aggregate token rate (2.4 against 38.9 at 16 users),
nibble-shifted CFG1 transcriptions. **When two credible sources print different numbers for the same
thing, check for a constant factor or offset before concluding they disagree.**

**5. A tool or harness that is itself broken.** The 4 GiB `cuMemGetInfo` truncation, the fold harness
reporting native memory as folded, the sparse probe aliasing past its own partner address,
`CUBLAS_COMPUTE_16F` returning instantly because of a pointer type mismatch, the argparse mismatch
that aborted an exploit path, the canary-zeroing stack generator. **A surprising result from a new
tool is a tool bug until a control run says otherwise.**

**6. Confident, well-formatted, wrong AI output.** This one is worth stating plainly because it
recurs across every domain: an invented DMEM map, an invented board topology with correct-looking
designators and crystal frequencies, a GP102 register address used on GA100, a 16-bit truncation
model, a "structural wall" argument, and the FP-throttle write-up that cost roughly USD 110 and
concluded the opposite of the truth. The corpus also contains AI-assisted work that was **correct
and decisive**, including the reproduction of the compute unlock itself. The distinguishing feature
is not the tool; it is whether a claim came with a readback, a control, or a cross-card comparison.

A seventh pattern is worth ending on, because it is the healthy one. A large share of the entries
above were **retracted by the people who proposed them**, often within minutes: the FSP theory, the
NVML clock theory, the CPU-RM context theory, the 90HX persistence claim, the memory-error count on
80 GB, the PG199 capacity estimate, the non-secure BAR0 negative result, the mutex `r10` clobber
theory, the "no recovery path for NVGI" claim, the `0xf700` payload size, and the `0x0F40` write
gadget (self-corrected in the same message it was proposed). Rapid self-correction is why a project
with 507 dead ends still shipped a working 64 GB unlock in about five weeks.

---

## See also

- [Project timeline](timeline.md) for when each of these happened relative to the results.
- [Tool lineage](tool-lineage.md) for which tools are dead and which were never obsoleted.
- [Clean room and provenance](clean-room-and-provenance.md) for the leak-derivation questions
  touched on above.
- [Open questions](../frontier/open-questions.md) for what is unresolved rather than refuted.
- [Troubleshooting](../procedures/troubleshooting.md) for the error codes referenced throughout.
- [Register reference](../unlock/register-reference.md) for the canonical value of every address on
  this page.


