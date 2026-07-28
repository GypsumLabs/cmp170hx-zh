# The memory subsystem

**What this page covers.** The physical framebuffer of the CMP 170HX: the GA100 HBM stacks, the
FBP/FBPA partition hierarchy, how many partitions exist and how many each SKU actually keeps, the
per-partition capacity descriptors, bus width, bandwidth, floorsweeping, the difference between a
*defective* and a *disabled* partition, and the stock locked register values. It explains in
hardware terms **why the 8 GB card unlocks to 64 GB and the 10 GB card unlocks to 40 GB**. The
register writes that perform that unlock live on
[Memory geometry unlock](../unlock/memory-geometry.md).

Two facts carry this entire page:

1. **Reported framebuffer capacity on this die equals (live FBPA count) × (per-FBPA capacity
   tier).** Both terms are readable from BAR0. The FBPA count is fuse-determined and cannot be
   changed. The tier is set by one register and *can* be changed.
2. **The two 170HX SKUs differ only in how many partitions survive floorsweeping.** The 8 GB card
   keeps 16 of 24 memory partitions; the 10 GB card keeps 20 of 24. Both ship with the same
   512 MiB-per-partition tier, which is what produces 8192 MiB and 10240 MiB respectively.

The unlock raises the tier, not the partition count. Because the 8 GB card is given the top tier
(4096 MiB per partition) and the 10 GB card is given the middle tier (2048 MiB per partition), the
physically *smaller* card ends up with the *larger* framebuffer: **8 GB to 64 GB, 10 GB to 40 GB.**

---

## Die topology

GA100 carries six HBM2/HBM2e stacks. Each stack is served by two Frame Buffer Partitions (FBPs),
each FBP by two Frame Buffer Partition Accelerators (FBPAs), and each FBPA by one L2 slice (LTC).
At full die that is 12 FBPs, 24 FBPAs and 24 LTCs. Each FBP presents a 512-bit channel, so a full
die would be 6144-bit.

These scalars are read directly from the PTOP block and are identical on every 170HX:

| Register | Address | Value | Meaning |
|---|---|---|---|
| `PTOP_SCAL_NUM_FBPAS` | `0x0002243c` | 24 | FBPAs at full die |
| `NUM_FBPS` | `0x00022438` | 12 | FBPs at full die |
| `FBPA_PER_FBP` | `0x00022458` | 2 | FBPAs per FBP (mask `0x1f`) |
| `NUM_LTCS` | `0x00022454` | 24 | L2 slices at full die |
| `NUM_GPCS` | `0x00022430` | 8 | see [GA100 silicon](ga100-silicon.md) |
| `TPC_PER_GPC` | `0x00022434` | 8 | |
| `NUM_NVLINK` | `0x0002246c` | 12 | fused off, see [NVLink](nvlink-hardware.md) |

!!! question "Open problem: how many HBM stacks are actually bonded?"
    A delidded 8 GB card visibly showed six stack sites; a separate die-shot source claims two of
    the six are dummies. Both readings are compatible with the measured 4096-bit bus, so bus width
    cannot discriminate. Only a package X-ray or a per-FBPA-to-stack channel-targeted access
    pattern would settle it. The geometry arithmetic below does not depend on the answer.

---

## Per-SKU floorsweep

Floorsweeping is done in fuses. Two independent bitmasks exist: **DEFECTIVE** marks partitions that
failed at test, and **DISABLE** marks partitions that are switched off. DISABLE is a superset of
DEFECTIVE: real failures are marked defective, and additional *good* partitions are then disabled
on top to hit the product spec.

### 8 GB SKU (`10de:20c2`)

| Register | Address | Value | Decode |
|---|---|---|---|
| `OPT_FBPA_DISABLE` | `0x00820368` | `0x00c0330c` | FBPAs 2, 3, 8, 9, 12, 13, 22, 23 off (8 dead, **16 live**) |
| `OPT_FBIO_DISABLE` | `0x0082036c` | `0x00c0330c` | matches FBPA |
| `STATUS_OPT_FBPA` | `0x00820c18` | `0x00c0330c` | effective mask |
| `STATUS_OPT_FBIO` | `0x00820c14` | `0x00c0330c` | effective mask |
| `OPT_FBP_DISABLE` | `0x00820364` | `0x00000852` | FBPs 1, 4, 6, 11 off (**8 of 12 live**) |
| `FBP_DEFECTIVE` | `0x008205cc` | `0x00000840` | FBPs 6 and 11 only: *medium confidence, single community dump, card identity disputed* |
| `FBPA_NUM_ACTIVE` | `0x009a0164` | `0x00000008` | counts **FBPs**, not FBPAs, despite the name |
| `FBHUB_NUM_ACTIVE_LTCS` | `0x00100800` | `0x00000010` | 16 LTCs |
| `MMU_NUM_ACTIVE_LTCS` | `0x00100ec0` | `0x04001410` | LTC count field `[4:0]` = 16 |

*If* the `0x840` pairing holds, the DISABLE/DEFECTIVE delta on this card is non-empty: `0x852`
against `0x840` leaves FBPs 1 and 4 marked *disabled but not defective*. That is the whole basis of the "could we get to 80 GB on an
8 GB card" hope, and no mechanism to act on it has ever been found.

### 10 GB SKU (`10de:2082`)

| Register | Address | Value | Decode |
|---|---|---|---|
| `OPT_FBPA_DISABLE` | `0x00820368` | `0x000000c3` | FBPAs 0, 1, 6, 7 off (4 dead, **20 live**) |
| `OPT_FBIO_DISABLE` | `0x0082036c` | `0x000000c3` | matches FBPA |
| `STATUS_OPT_FBPA` | `0x00820c18` | `0x000000c3` | effective mask |
| `OPT_FBP_DISABLE` | `0x00820364` | `0x00000009` | FBPs 0 and 3 off (**10 of 12 live**) |
| `FBP_DEFECTIVE` | `0x008205cc` | `0x00000840` on one card, `0x840` = `DISABLE` on another | see note |
| `FBPA_NUM_ACTIVE` | `0x009a0164` | `0x0000000a` | 10 FBPs |
| `FBHUB_NUM_ACTIVE_LTCS` | `0x00100800` | `0x00000014` | 20 LTCs |
| `MMU_NUM_ACTIVE_LTCS` | `0x00100ec0` | `0x05001414` | LTC count field `[4:0]` = 20, byte-identical to all three A100 SKUs |

The swept set is per-die binning, not a per-SKU constant, so the table above is one card rather
than the SKU. The two physically probed 10 GB units disagree: one reads `OPT_FBP_DISABLE` =
`STATUS_FBP` = `0x00000009` (FBPs 0 and 3) with `OPT_FBPA_DISABLE` = `STATUS_OPT_FBPA` =
`0x000000c3` (FBPAs 00/01 and 06/07), the other reads `0x00000180` (FBPs 7 and 8) with
`0x0003c000` (FBPAs 14 to 17). A third 10 GB card reads `0x840` (FBPs 6 and 11) with `0x00c03000`
(FBPAs 12/13 and 22/23), which is also the A100 PCIe 40G/80G value. All three keep 20 FBPAs live,
so the capacity arithmetic is unaffected.

!!! note "A reconciliation, not a confirmed fact"
    `MMU_NUM_ACTIVE_LTCS` was recorded once as `0x05001414` and once as `0x04001410` on parts both
    described as 170HX, and one adjudicated document lists that as an unresolved contradiction. The
    per-SKU split above resolves it arithmetically: the LTC-count field reads 16 on a 16-FBPA card
    and 20 on a 20-FBPA card, exactly as it should. No paired same-boot capture stating the PCI
    device ID alongside the register has been posted, so treat the split as strongly indicated
    rather than proven.

!!! note "Superseded: the FBP index to FBPA index mapping is linear"
    An earlier note read `FBP_DEFECTIVE = 0x840` (FBPs 6 and 11) against measured dead FBPAs 00/01
    and 06/07 as evidence that the mapping might not be linear, and asked for one report giving the
    PCI device ID, the full 24-instance CSTATUS sweep, the FBPA mask from `0x00820c18` and the FBP
    mask from `0x00820d38` all from the same boot. The 15-card fuse reference table is that report,
    for five GA100 parts at once. Every one obeys FBP *n* to FBPAs *2n* and *2n+1*: FBP mask
    `0x00000009` pairs with FBPA mask `0x000000c3`, `0x00000180` with `0x0003c000`, `0x00000012`
    with `0x0000030c`, `0x00000840` with `0x00c03000` and `0x00000852` with `0x00c0330c`, and in
    each case the poisoned CSTATUS instances are exactly those FBPAs. The mapping is linear; the
    puzzle was two different physical cards being conflated in the reports.

### Poison sentinels

Floorswept partitions are trivially identifiable in MMIO because their registers return PRI error
sentinels rather than data. Two patterns must be told apart:

| Sentinel | Meaning |
|---|---|
| `0xbadf1100` | the target does not physically exist on this die (GA10x parts return this for FBPA indices 6 to 23, matching `PTOP_SCAL_NUM_FBPAS` = 6) |
| `0xbadf20NN` | the target exists but is floorswept; the low byte encodes the disabled FBP index |

Observed values: `0xbadf2011` (FBPAs 02/03), `0xbadf2014` (08/09), `0xbadf2016` (12/13) and
`0xbadf201b` (22/23) on an 8 GB card; `0xbadf2010` (00/01) and `0xbadf2013` (06/07) on a 10 GB card.
A full 24-of-24 confirmation of anything is therefore never expected on a floorswept card. The
index-encoding rule holds on all six probed cards with floorswept FBPAs but is a derivation, not a
documented field.

---

## The per-FBPA register aperture

Each FBPA has a 16 KiB register window. The layout is:

```text
per-instance:   0x00900000 + n * 0x4000        for n = 0 .. 23
  + 0x200       FBPA CFG0
  + 0x204       FBPA CFG1
  + 0x20C       FBPA CSTATUS_RAMAMOUNT

broadcast:      0x009A0000 .. 0x009A3FFF        (one 0x4000-wide window)
  0x009A0200    CFG0   broadcast
  0x009A0204    CFG1   broadcast
  0x009A020C    CSTATUS_RAMAMOUNT broadcast
```

The stride is `0x4000`, matching the width of the broadcast window exactly. One adjudicated
document records `0x400` in a single sentence; that is a dropped-zero typo contradicted by two
other entries in the same document, by the probe tooling's own constants
(`FBPA_BASE = 0x900000`, `FBPA_STRIDE = 0x4000`) and by the broadcast window size.

!!! note "Superseded"
    An early hypothesis put the per-instance CFG1 at `0x009a<N>204` with a `0x1000` stride. It was
    tested in the same dump that proposed it and produced garbage: `0x009a1204` = `0x0007fff0`,
    `0x009a2204` = `0x00000000`, `0x009a3204` = `0xbadf1002`, `0x009a4204` = `0xbadf4000`. Use
    `0x00900204 + n*0x4000`.

**CFG0** reads `0x07981800` on the broadcast register and on every live per-instance copy, on both
170HX SKUs and on A100 SXM4 40 GB, A100 PCIe 40 GB and A100 PCIe 80 GB alike. A Drive A100 reads
`0x06981800` and a GA10x control card `0x069f9803`. The memory-controller base configuration is
therefore **not** restricted on the 170HX. Only CFG1 differs. Uniformity across instances is also
what makes a single broadcast write safe.

!!! note "Superseded"
    A probe catalogue annotates `NV_PFB_FBPA_CFG0` with `CMP170HX=0x24490000, A100=0x26690000`.
    That is wrong: the register measures `0x07981800`. The quoted pair are the CFG1 values
    `0x02449000` and `0x02669000` shifted one nibble left and attached to the wrong register. Do
    not use it.

---

## CSTATUS_RAMAMOUNT: the per-partition capacity descriptor

`CSTATUS_RAMAMOUNT` at `0x0090020C + n*0x4000` reads the partition's capacity **directly in MiB**.
It is derived hardware state that follows CFG1; no tool writes it. It is the cheapest and most
trustworthy readback for confirming that a geometry change actually landed, far better than
`nvidia-smi`.

| Value | Capacity per FBPA | Where seen |
|---|---|---|
| `0x200` | 512 MiB | stock, **both** 170HX SKUs |
| `0x800` | 2048 MiB | 40 GB tier (10 GB card unlocked) |
| `0x1000` | 4096 MiB | 64 GB tier (8 GB card unlocked) and the attempted 80 GB tier |
| `0x7ff` | 2047 MiB | stock A100 SXM4 40 GB, A100 PCIe 40 GB, Drive A100 32 GB (PG199) |
| `0xfff` | 4095 MiB | stock A100 PCIe 80 GB |

The 170HX values are round where the A100 values are one less. The explanation on record is ECC:
on GA100, ECC is a within-stack reservation costing roughly 1/2048 of each partition's addressable
range, and the 170HX has ECC fused off, so nothing is carved out. That reading is consistent but
has never been proven from a field definition.

### The arithmetic closes exactly

| Card | Live FBPAs | Tier | Product | Reported |
|---|---|---|---|---|
| 8 GB, stock | 16 | 512 MiB | 8192 MiB | 8192 MiB |
| 8 GB, **unlocked to 64 GB** | 16 | 4096 MiB | 65536 MiB | 65536 MiB |
| 10 GB, stock | 20 | 512 MiB | 10240 MiB | 10240 MiB |
| 10 GB, **unlocked to 40 GB** | 20 | 2048 MiB | 40960 MiB | 40960 MiB |
| 10 GB, attempted 80 GB | 20 | 4096 MiB | 81920 MiB | 81920 MiB reported, unusable above ~40 GB |
| A100 PCIe 40 GB | 20 | 2047 MiB | 40 GB | 40 GB |
| A100 PCIe 80 GB | 20 | 4095 MiB | 80 GB | 80 GB |
| Drive A100 32 GB | 16 | 2047 MiB | 32 GB | 32 GB |

**The per-card theoretical ceiling is (live FBPAs) × 4096 MiB**, because tier `0x77` (4 GiB per
partition) is the largest tier in use. For the 8 GB card that is 16 × 4096 = 64 GB, exactly what
ships. For the 10 GB card it is 20 × 4096 = 80 GB, exactly the number the unmerged `80` branch
chased. 96 GB would need 24 live FBPAs, which neither SKU has. This single line retires the whole
96 GB family of proposals.

### CSTATUS reports measured capacity, not usable capacity

A partition can report 4096 MiB without the upper half of that range being usable under load. Every
capacity claim must be backed by a write-everything-then-read-everything alias ("fold") test, not by
a reported size. See [Verification](../procedures/verify.md).

---

## Bus width and bandwidth

Bus width follows directly from live partition count: each FBP is a 512-bit channel, each FBPA
256 bits.

| Part | Live FBPAs / FBPs | Bus width |
|---|---|---|
| CMP 170HX 8 GB | 16 / 8 | **4096-bit** |
| CMP 170HX 10 GB | 20 / 10 | **5120-bit** |
| A100 40 GB | 20 / 10 | 5120-bit |
| A100 96 GB class | 24 / 12 | 6144-bit |
| Drive A100 32 GB | 16 / 8 | 4096-bit |

**The memory bus was never cut down by the unlock and is not cut down by it.** The unlock makes more
of the already-attached HBM addressable. It adds no channels and connects no chips. This is
completely separate from the PCIe link, which is limited by different means (see
[PCIe subsystem](pcie-subsystem.md)) and must never be conflated with memory geometry.

Note the counter-intuitive consequence: the 8 GB card has the *narrower* bus but usually the
*higher* delivered bandwidth, because its HBM runs faster.

### Theoretical peaks

| Card | Clock | Width | Theoretical peak |
|---|---|---|---|
| 10 GB SKU | 1215 MHz DDR | 5120-bit | **1555.2 GB/s = 1448.4 GiB/s** |
| 8 GB SKU | 1728 MHz DDR | 4096-bit | 1769 GB/s (3.456 Gbps/pin) |
| 8 GB SKU, published spec database | 1458 MHz | 4096-bit | 1492.99 GB/s |

### Measured bandwidth

!!! warning "There is no single canonical measured bandwidth figure for this card"
    Across tools and access patterns the reported values span **1305.86 to 1600 GB/s**. Use the
    range. Two directional read-stream measurements sit above it and are listed with their
    conditions below; a point estimate quoted without a tool and an access pattern is not
    meaningful on this hardware.

!!! info "The memory geometry does not survive FLR or a power cycle; the compute unlock does"
    SS0, SS1 and `0x00823804` survive FLR; the CFG1/LMR geometry rewrite does not. This asymmetry
    is why compute shipped before memory, and it is why "no FLR" appears as a stated condition on
    the DtoD bandwidth row below.

| Measurement | Value | Conditions |
|---|---|---|
| Device-to-device, 10 GB card at 40 GB | 1390 GB/s | clean 610.43.03, no FLR |
| Read stream, 8 GB card unlocked | 1679.1 to 1699.3 GB/s | 24 GiB stream |
| Read bandwidth at the perf profile | 1695 GB/s | 1728 MHz memory, patched module |
| Read bandwidth at NDIV 60 | 1582 GB/s | 1620 MHz memory |
| Read bandwidth at NDIV 52 | 1279 GB/s | 1404 MHz memory |
| Read bandwidth at NDIV 60 (PLL diff run) | 1574.7 GB/s | controlled lower-rate boot |
| `mem_burn` write, 80 GB-fired 10 GB card | 1354.6 GiB/s | 30 GiB, 0 mismatches |
| clpeak, stock 8 GB card, 2023 | 1165.79 / 1269.69 / 1343.50 / 1355.40 / 1350.14 GB/s | float / float2 / float4 / float8 / float16 |

Within an over-provisioned 80 GB configuration, an offset sweep found the originally trained
0 to 4 GB region running at ~1416 GiB/s (98 % of peak) and the whole 8 to 76 GB span running at
~1149 GiB/s (79 % of peak) **uniformly, with no dead zones**. At 32 GB chunk sizes both offsets
reach 100 %. An earlier reading that showed a collapse to 32 GiB/s above 32 GB was an artefact of
the sweep exhausting its single CUDA context and is retracted.

!!! question "Open problem: the stock HBM clock on the 8 GB card"
    Three figures circulate: 1458 MHz (specification database and a 2023 `deviceQuery` reporting
    729 MHz, doubled by convention), 1592 MHz, and 1728 MHz (direct 2026 measurement). The
    1679 to 1699 GB/s delivered read bandwidth is decisive *against* 1458 MHz for that run because
    it exceeds the ceiling that clock implies, but it does not choose between 1592 and 1728. What
    would settle it: a raw FBPA PLL register read published with the divider chain. 1728 MHz is the
    best-supported figure and is the one used above.

### Memory clocking is closed by measurement

A non-production kernel-module patch (`driver/0009-hbm-mclk-overclock.patch`) that writes FBPA PLL
coefficients established the following with a causal control:

- **Underclocking is causal.** NDIV 65 (a 6.25 % clock reduction) delivered 6.8 % less bandwidth
  with higher latency.
- **Up-clocking delivers nothing.** NDIV 70 (coefficient `0x00014601`, a 4.9 % request) measured
  bandwidth identical to stock, with zero memory errors and no soft roll-off, even though the
  register accepted the coefficient and the PLL lock bit set. Zero gain with no errors and no
  roll-off is the signature of a hard clamp at the trained rate.

Two supporting facts explain it: **no Memory Clock Table exists in any of eight ROM dumps** (the
1728 MHz rate comes from FWSEC devinit at POST), and the part already runs 3.456 Gbps/pin against
an HBM2e nominal of about 3.2, so there was never factory headroom. The source carries an explicit
instruction not to re-run the PLL sweep.

Memory *underclocking* is a real efficiency lever on compute-bound work and is covered in
[Tuning](../operations/tuning.md).

!!! warning "Experimental"
    An unreleased third-party fork carries a memory overclock with a stock multiplier of 64 and a
    shipped default of 70 (lowered from 72 after one tester's 8 GB-to-64 GB card produced
    `gpu_burn` errors within about two minutes at roughly 1944 MHz effective and 85 C). One author
    reports all of their own cards stable at 73. This is not the shipping tool and the values are
    per-card.

---

## HBM identity and mode registers

The HBM stacks are **not** being told they are smaller than they are. `FBPA_MRS_8` (MR8 Density) at
`0x009A0320` reads `0x00200000` on all 15 cards in the probe cohort, including a 10 GB CMP, a 40 GB
A100 and an 80 GB A100. Density is not the capacity restriction.

| Register | Address | 8 GB 170HX | 10 GB 170HX | Reference |
|---|---|---|---|---|
| `FBPA_MRS_0` | `0x009a0300` | `0x00000003` | `0x00000003` | `0x00000003` on A100/Drive; `0x00000025` on A10/A5000/A6000 |
| `FBPA_MRS_1` | `0x009a0304` | `0x00100000` | `0x00100000` | `0x00100000` everywhere |
| `FBPA_MRS_2` | `0x009a0334` | `0x00200019` | `0x002000cf` | `0x00200029` A100 80G; `0x00200031` Drive |
| `FBPA_MRS_WL_RL` | `0x009a0338` | `0x003000eb` | `0x003000ea` | `0x003000ef` A100 80G / Drive |
| `FBPA_MRS_8` (density) | `0x009a0320` | `0x00200000` | `0x00200000` | `0x00200000` on all 15 cards |
| `FBPA_HBM_CFG0` | `0x009a038c` | `0x000000a7` | `0x000000a7` | `0x000000a7` on all three A100 SKUs; `0x000000a6` on Drive A100; `0x000003fe` on GDDR6 parts |
| `FBPA_TRAINING_STATUS` | `0x009a0974` | `0x00000000` | `0x00000000` | FINISHED on both sub-partitions on all 15 cards, **including an unlocked 64 GB card** |
| `FBPA_VEND_ID_C0` / `_C1` | `0x009a0838` / `0x009a083c` | `0x00000000` | `0x00000000` | zero on all 15 cards: no vendor info available this way |

`FBPA_HBM_CFG0` decodes as `dual_rank[0]`, `dual_rank_bank[1]`, `SID_VAL[11]`. The 170HX matching
the A100 exactly means the memory controller sees the same stack organisation.

The **IEEE 1500 HBM debug bridge** is live on the 170HX at `0x009a3cb4` to `0x009a3cc8` and is the
only working route to real stack identity. Values differ per die: `I1500_DATA` reads `0xde79ffc1`
on one 170HX and `0xc631ffc1` on another, `I1500_SHADOW_WDR` reads `0xbcf3ff83` and `0x8c63ff83`
respectively, sharing low 16 bits (`0xffc1` / `0xff83`) with per-unit upper halves. A100 parts read
a much tidier `0xNN000000` / `0xNN00f000` family. GA10x parts return `0xbadf5040` for the whole
block, so the aperture is GA100-specific.

!!! question "Open problem: nobody has decoded `I1500_SHADOW_WDR`"
    The next step is to shift in the standard IEEE 1500 `DEVICE_ID` WIR opcode rather than reading
    whatever instruction was left latched (`I1500_INSTR` = `0x0000000f`, `I1500_MODE` = `0x00000008`
    at the time of the reads). That would give HBM vendor and per-stack density from the DRAM
    itself and would settle several long-running arguments at once.

### Which vendor, and HBM2 or HBM2e?

The strong working assumption is **SK hynix HBM2e on the 8 GB SKU (~1590 MHz) and Samsung HBM2 on
the 10 GB SKU (~1200 MHz)**, which is consistent with the measured clock and stability gap and with
the community verdict that 8 GB owners got the better part. It has never been verified by package
markings, X-ray or a vendor-ID readout. It also matters less than it appears: one participant
established that Samsung HBM2's row/column/bank structure is the same as the HBM2e structure the
CFG1 profiles encode, so the same CFG1 values apply either way.

---

## HBM timing

`CONFIG0.USE_TIMING_REGS` (bit 31 of `0x9A0290`) is **0** on this part (CONFIG0 reads `0x1255B93C`).
The controller therefore runs on internally generated timings held in the read-only `TIMING*_GEN`
shadow registers, and **writing the raw `TIMING0` to `TIMING20` registers has no effect at all.**
This is the single most important constraint on any HBM tuning attempt on this card. Read that bit
before doing anything else.

Live timings decoded from register reads: CL 27, CWL/WL 8, tRCD(read) 18, tRCD(write) 13, tRC 60,
tRFC 441, tRAS 42, tRP 18, tWR 19, tRRD 6, tFAW 21, tCCD_L 4, tCCD_S 2, tCKE 10. The generated
shadows agree with the CONFIG copies except on bus turnaround, where `TIMING1_GEN` (`0x9A02B4`)
gives R2W 29, W2R 20 and W2P 28 against 18, 13 and 18 in the writable copies. The `_GEN` values are
the ones in force.

Register map highlights (reconstructed against NVIDIA's own `dev_fbpa.h` from the driver pack):

| Register | Address | Value | Notes |
|---|---|---|---|
| `CONFIG0` | `0x9A0290` | `0x1255B93C` | bit 31 `USE_TIMING_REGS` = 0 |
| `CONFIG1` | `0x9A0294` | `0x38D4841B` | CL[6:0] 27, WL[13:7] 8, RD_RCD[19:14] 18, WR_RCD[25:20] 13 |
| `CONFIG2` | `0x9A0298` | `0x88130B11` | tWR 19, W2R_BUS 8, R2W_BUS 8, CDLR 11 |
| `CONFIG3` | `0x9A029C` | `0x24002B4A` | FAW 21, CCDL 4, CCDS 2 |
| `CONFIG4` | `0x9A02A0` | `0xC4030033` | tREFI in bits [14:0], field value 51 |
| `CONFIG7` | `0x9A02AC` | `0x00C35000` | ZQCS_INTERVAL 12,800,000 |
| `TIMING12` | `0x9A0250` | `0x0BB800A1` | CKE 10, LOCKPLL 3000 |
| `TIMING*` writable | `0x9A0220`-`0x9A028C` | inert | ignored while `USE_TIMING_REGS` = 0 |
| `TIMING*_GEN` shadows | `0x9A02B0`-`0x9A02F0`, plus `0x9A0288` | live | read-only |

!!! note "Superseded"
    `CONFIG4` is at `0x9A02A0`, **not** `0x9A0210`. `0x9A0210` is the REFCTRL PUT/GET queue-pointer
    pair and wanders (`0x7575` to `0x5252` to `0x3535` to `0x1a1a` to `0x0101`) within a single read
    loop. `0x9A02A0` reads a rock-stable `0xc4030033`.

### The refresh experiment

`CONFIG4` does not scale with capacity: `0xc4030033` is identical on the 10 GB CMP, the 8 GB CMP and
an A100, at both 40 GB and 80 GB. An 80 GB fire doubles the reachable row count while leaving the
refresh interval at the 2 GiB-per-channel rate, so the physically motivated fix was to double
refresh with `CONFIG4 = 0xC403001A` (field 26). It landed cleanly on all 20 live FBPAs through the
HS ROP `run()` path.

**It did not work.** Instability persisted, and bandwidth collapsed from 1416 to 1422 GiB/s (98 %)
down to 848 to 888 GiB/s (59 to 61 %) at low offsets, and from 1147 to 1151 GiB/s down to roughly
782 to 823 GiB/s at high offsets. A separate completed tREFI sweep found stock (51) both stable and
fastest. Refresh tuning is recorded in-channel as "using a strait-jacket as a bandage".

An override of the visible CONFIG/TIMING registers was mapped out (set `USE_TIMING_REGS`, then
write CONFIG0-CONFIG4 and TIMING0-TIMING20 through the HS ROP because they are PLM-gated) but
failed because the CONFIG registers carry no per-channel DQ/VREF offsets. Where those offsets
actually live is unknown; the `_GEN` shadow family is the obvious next place to look.

---

## Fuses: what does and does not cap capacity

### Does not

Every plausible topology or half-capacity fuse reads zero on both 170HX SKUs and on an A100-class
reference, so nothing was ever running at half capacity and there is nothing to clear:

| Fuse | Address | Value |
|---|---|---|
| `OPT_HALF_FBPA_ENABLE` | `0x0082049c` | `0x00000000` |
| `CTRL_OPT_HALF_FBPA` | `0x00820800` | `0x00000000` |
| `STATUS_HALF_FBPA` | `0x00820c00` | `0x00000000` |
| `OPT_FB_CONFIG` (4-bit topology selector, PLM `0x008200fc`) | `0x00820328` | `0x00000000` |
| `CTRL_OPT_FB_CONFIG` | `0x00820834` | `0x00000000` |
| `STATUS_OPT_FB_CONFIG` | `0x00820c34` | `0x00000000` |
| `OPT_SPARE_FS` / status | `0x00820398` / `0x00820c30` | `0x00000000` |
| `CTRL_OPT_FBPA` | `0x00820818` | `0x00000000` |

### Does gate the write path

| Fuse | Address | Value | Consequence |
|---|---|---|---|
| `OPT_MEMORY_LOCKED_ENABLED` | `0x00820340` | `0x00000001` | "memory config cannot be changed at runtime". It gates the *privilege level* of the write, not the hardware's willingness to accept a new geometry: with the FBPA PLM open, CFG1 writes land and CSTATUS moves. |
| `OPT_SECURE_FBPA_MEM_WR_SECURE` | `0x00820618` | `0x00000001` | FBPA memory-config writes are restricted to privileged code, on all 15 Ampere parts measured. This is exactly why PLM `0x009a0148` must be opened first. |
| `OPT_FB_FALCON_PRI_ACCESS_DISABLE` | `0x00820670` | `0x00000000` | a Falcon retains PRI access to FB registers. The whole SEC2 ROP route depends on this. |
| `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` | `0x008203f0` | `0x00000000` | the master kill fuse is **unblown**. |
| `EN_SW_OVERRIDE` | `0x00820040` | `0x00000000` | writable and persistent, but see below. |
| `DISABLE_SW_OVERRIDE_STATUS` | `0x00820084` | `0x00000001` | software fuse override is permanently blocked. |

Together those force the PLM-plus-MMIO route and rule out the fuse-override route entirely.

!!! note "Superseded"
    Software re-enable of floorswept FBPAs was tested on hardware and failed. `EN_SW_OVERRIDE`
    moved `0x0` to `0x1` (the write took), but `DISABLE_SW_OVERRIDE_STATUS` stayed at `0x1`,
    `CTRL_OPT_FBPA` stayed at `0x0`, and the effective mask `STATUS_FBPA` did not move from
    `0x00c0330c`. Fused-off partitions cannot be recovered by this exploit. Only the VBIOS-imposed
    per-partition capacity cap is reversible.

Also relevant: on both physical 10 GB units, `DEVIDA` (`0x008204d8`) = `0x00002082` and `DEVIDB`
(`0x0082056c`) = `0x000020c2`, consistent with the `DEVIDB = DEVIDA + 0x40` rule that holds on all
11 parts with data (A100 SXM4 40G and A100 PCIe 40G read `0x20b1`/`0x20f1`; A100 PCIe 80G reads
`0x20b5`/`0x20f5`). A 2026-07-19 probe of a `0x20c2` card reported **both** fuses at `0x20c2`; that
reading is disputed; see the open problem in [board and variants](board-and-variants.md). The rule
predicts an 8 GB card should read `DEVIDA` = `0x20c2`, `DEVIDB` = `0x2102`.
See [Fuses and OTP](fuses-and-otp.md).

---

## ECC

**ECC is fused off on the CMP 170HX and no lever has been found.**

| Register | Address | 170HX | Reference |
|---|---|---|---|
| `FUSE_ECC_EN` / `OPT_ECC_EN` | `0x00820228` | `0x00000000` | `0x00000001` on A100 SXM4 40G, A100 PCIe 40G/80G, A10, A5000, A6000, Drive A100 |
| `FBPA_ECC_CTRL` | `0x009a0470` | `0x00000000`, `MASTER_EN` bit 0 read-only | `0x00000041` on A100/Drive; `0x20000020` on GA10x |
| `FEAT_OVR_ECC` | `0x0082380c` | `0x00888888` | SM_LRF/L1/LTC/DRAM/CBU |
| `FEAT_OVR_ECC_1` | `0x00823810` | `0x002aaaaa` | icache/FECS/GPCCS/PMU/HUBMMU |
| `FEAT_OVR_ECC_2` | `0x0082382c` | `0x0000000a` | LTC_CBC, SM_URF |
| `FEAT_OVR_ECC_PLM` | `0x00823800` | `0xffffff8f` | distinct register from `0x00823804` |
| `FEAT_READOUT_0` | `0x00823814` | `0x00000233` | POR/fuse-latched |
| `FEAT_OVR_ROW_REMAP` | `0x00823824` | `0x00000000` | row remapper inactive |
| `FEAT_READOUT_2` | `0x00823828` | `0x00000000` | row remapper inactive |

The feature-override shadows exist and are populated, and the HS ROP genuinely can open their PLM,
but the ECC-enable readout at `0x00823814` is POR/fuse-latched and does not respond to live
override writes, and `FEAT_OVR_ECC` is not always-on so it reverts on FLR anyway. `nvidia-smi -q`
reports every ECC field as `N/A`, `Remapped Rows: N/A`.

**Practical consequence: an unlocked 170HX has no ECC telemetry, so silent corruption above the real
capacity ceiling never surfaces as a counter.** This is why the fold test exists.

!!! note "Superseded"
    The branch named `ecc` contains no ECC code. Its patch directory is byte-identical to master and
    its single commit is "Fixed dual geometry support". A grep across master and all 12 unreleased
    branch snapshots finds zero references to `0x00820228` or `0x009a0470`. See
    [ECC frontier](../frontier/ecc.md).

---

## The stock, locked state

This is what an untouched CMP 170HX reads. These are the values the unlock overwrites.

| Quantity | 8 GB SKU (`10de:20c2`) | 10 GB SKU (`10de:2082`) |
|---|---|---|
| Reported capacity | 8192 MiB | 10240 MiB |
| FBPA CFG1 `0x009a0204` | `0x02449000` | `0x02449000` (**identical**) |
| MMU LMR `0x00100ce0` | `0x00000208` | `0x00000288` |
| Per-FBPA `CSTATUS_RAMAMOUNT` | `0x200` (512 MiB) | `0x200` (512 MiB) |
| Per-FBPA CFG0 | `0x07981800` | `0x07981800` |
| Live FBPAs / FBPs / LTCs | 16 / 8 / 16 | 20 / 10 / 20 |
| Bus width | 4096-bit | 5120-bit |
| FB-geometry PLMs (`0x00100b10`, `0x00100b38`, `0x009a0148`, `0x009a014c`, `0x009a0008`, `0x009a000c`) | `0xffffff8f` (read all levels, write L3 only) | same |
| WPR PLMs `0x001fa7c4` / `0x001fa7cc` | `0x0004cb8f` | same |

Both SKUs share the same stock CFG1 word `0x02449000`. Only the LMR differs, and it differs only in
the magnitude field, which encodes the partition count.

Baseline runtime numbers from an independent 2023 review of a stock, locked 8 GB card: CUDA
`Total global mem: 7961 MB`, `Memory bus width: 4096 bits`, `ECC enabled: No`,
`Memory bandwidth: 1492.99 GB/sec`, `deviceQuery` memory clock 729 MHz; `gpu_burn` saw
`7961 MB of memory (7660 MB available, using 6894 MB of it)`.

!!! note "No uncontaminated stock CFG1 exists in any capture taken through the patched driver"
    Patch `0001` writes CFG1 before anything can read it, so every "stock" value above comes from
    pre-write pipeline logs or driverless reads. There is also **no known way to read back which
    VBIOS strap is currently selected**; the only indirect indication is the value at `0x009a0204`,
    which the unlock overwrites. That blocks distinguishing "the card was strapped down" from "the
    card was fused down".

---

## Why the two SKUs differ, in one paragraph

Both cards are the same GA100 die with the same six HBM sites, the same 24-partition register map,
the same CFG0, the same mode registers and the same stock CFG1 word. The 8 GB part had four more
FBPs swept off (8 of 12 live rather than 10 of 12), which is why it reports 8192 MiB against
10240 MiB and 4096-bit against 5120-bit. That is the whole physical difference. The unlock then
assigns each SKU a different per-partition tier: the 8 GB card gets tier `0x77` (4096 MiB per
partition, 16 × 4096 = **65536 MiB**) and the 10 GB card gets tier `0x66` (2048 MiB per partition,
20 × 2048 = **40960 MiB**). The 8 GB card can carry the top tier because its stacks are the better
part; the 10 GB card at the top tier reaches 81920 MiB of *geometry* but is not usable above roughly
40 GB. **8 GB to 64 GB, 10 GB to 40 GB.**

The physical explanation offered by a member of the original proof-of-concept team, medium
confidence and not independently verified: NVIDIA never produced A100s with 80 GB of Samsung memory,
and Samsung most likely sold NVIDIA partly-defective 16 GB HBM2e stacks binned as 8 GB stacks. The
exploit lets the 10 GB card address all 80 GB, but the upper 40 GB does not perform to standard.

!!! danger "Do not target 80 GB on a 10 GB card"
    The 80 GB configuration reports ~81920 MiB (85,545,582,592 bytes to CUDA) and `cudaMalloc` of
    77 GiB succeeds, but kernels touching more than roughly 40 GB cause fatal GPU loss, independent
    of power limit. Reported Xid codes include Xid 31 (described as harmless) and Xid 154 after
    CUDA memory tests; the dominant reported symptom is hangs. Xid 31 alone was suggested by a
    bystander and was not corroborated as *the* signature by the operator with the failing card.
    See [The 80 GB question](../frontier/80gb.md).

---

## Open problems on the physical side

!!! question "Open problem: can disabled-but-not-defective FBPs be re-enabled?"
    `OPT_FBP_DISABLE` = `0x00000852` on the 8 GB SKU is high confidence, but the paired
    `FBP_DEFECTIVE` = `0x840` comes from a single medium-confidence community reference dump whose
    card identity is disputed: `0x840` is also the A100 PCIe 40G/80G `FUSE_FBP_DISABLE` value. If
    the pairing holds, two FBPs are disabled purely for binning and re-enabling both would move the
    card from 64 GB to 80 GB, but the inference is unproven. The
    software-override path is closed (see above), and re-enabling fuse-disabled partitions at
    register level was reported to produce `0xbadf` poison on read. Devinit is the only untested
    escape hatch, and nobody has made devinit run at runtime.

!!! question "Open problem: does the physical DRAM above the shipping tier work, or only exist?"
    PRAMIN sweeps on a 10 GB card proved 80 of 80 distinct GiB are physically present, a dense
    77 GiB fill and verify at 64 KiB granularity returned zero errors twice, and the largest
    verified no-fold run was 72 GiB at stock boot timings. Against that: crashes above roughly
    40 GB, one CUDA context per fire before Xid 154, and 79 % of peak bandwidth in the extended
    region. The current synthesis, not a resolution: the cells are addressable and hold data briefly
    under a single context, and addressable is different from working.

!!! question "Open problem: retention failure or address-decode failure?"
    A retention failure should scatter errors by time and address across the whole upper region. A
    decode fold should produce exact aliasing at a power-of-two boundary, and the observed fold sits
    at exactly 40 GiB, which is suspiciously exact for a retention problem. That fold was seen under
    the `80` branch's incoherent LMR `0x0000028A`, and it disappears when the coherent `0x0000028B`
    is fired instead, which reads as a decode story. But the crashes do not disappear with it.
    Doubling refresh (`FBPA_CONFIG4 = 0xc403001a`) landed
    on all 20 live FBPAs and did **not** fix the instability while costing about 40 % of bandwidth,
    which is evidence against the retention story too. Neither mechanism is established.

!!! question "Open problem: is the upper region 'untrained'?"
    `FBPA_TRAINING_STATUS` (`0x009a0974`) reads FINISHED on every card probed, including an unlocked
    card already carrying the 64 GB CFG1 value, and a controlled A/B established that row/bank/column
    addressing is combinational and needs no training, so capacity is not gated on retraining. Yet
    "untrained" remains the most-repeated explanation for the instability. The reconciliation on
    offer is that the status bit reflects only the stock-geometry pass, or that the internally
    generated timings are simply wrong for the widened geometry (a timings problem, not a training
    problem). Nobody has correlated `TRAINING_STATUS` with an actual crash trace.

!!! question "Open problem: is MIG usable on an unlocked card?"
    The MIG-relevant descriptors are populated and readable (`FBHUB_MEM_PART_BOT` `0x00100b88`,
    `MID` `0x00100b8c`, `BOUNDARY_CFG0` `0x00100b90` = `0x00000603`,
    `SYSMEM_HSHUB_CONNECTION_CFG` `0x00100b98` = `0x00000003`), and the fuse survey shows MIG is not
    fused off, merely unprogrammed. MIG does enable, but it cannot partition: `-lgip` exposes only
    one profile (`1g.64gb`, 63.00 GiB, 70 SMs, P2P No), `-cgi 0` was run and produced a single
    instance at `1 MiB / 65053 MiB`, and a standard A100 profile (`-cgi 9,3g.20gb -C`) is rejected
    with `Invalid Argument`. What is open is whether the boundary descriptors can be reprogrammed to
    expose more than one profile.

---

## See also

- [Memory geometry unlock](../unlock/memory-geometry.md), the CFG1 and LMR mechanism
- [Register reference](../unlock/register-reference.md) and the [register index](../appendix/register-index.md)
- [Fuses and OTP](fuses-and-otp.md)
- [VBIOS and the strap table](vbios.md)
- [The 80 GB question](../frontier/80gb.md)
- [Verification methodology](../procedures/verify.md)
- [Glossary](../start/glossary.md) for FBP, FBPA, LTC, PLM, floorsweep
