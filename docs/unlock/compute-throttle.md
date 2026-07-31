# The compute throttle and how it is removed

**What this page covers.** The mechanism NVIDIA used to cripple arithmetic throughput on the
CMP 170HX, the exact registers and values that defeat it, why the fuses themselves are never
touched, what the measured improvement is, why the register with the most promising name
(`SM_ISSUE_RATE_MODIFIER`) is a dead end, and why the compute unlock survives a Function Level
Reset when the [memory unlock](memory-geometry.md) does not.

**The short version.** The restriction is an **instruction issue-rate divider**, implemented as
nine one-time-programmable fuses in the `OPT_SM_SPEED_SELECT` block, all set to their maximum
divisor (divide by 32) on this SKU and to zero on every A100. The fuses cannot be changed, and the
unlock does not try. Instead it opens one privilege level mask, `FEAT_OVR_PLM` at `0x00823804`,
from L3-only (`0xffffff8f`) to fully open (`0xffffffff`), using the SEC2 Booter as a
privileged write primitive, and then performs **two plain host register writes**:

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0: FEATURE_OVERRIDE_SM_SPEED_SELECT   */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1: FEATURE_OVERRIDE_SM_SPEED_SELECT_1 */
```

Those two dwords are the entire compute unlock. FP32 goes from 0.395 TFLOPS to roughly
12.7 to 12.9 TFLOPS (about **32x**), FP64 and every tensor path come back with it, and the
override survives FLR because `0x00823804` lives in the always-on island. Nothing here is written
to the card's BIOS; the patched driver reapplies the sequence on every GSP boot.

---

## Layer 1: the fuses

The throttle is per arithmetic unit. Nine fuses, one shared privilege level mask. A fuse value of
`0` is full rate; `5` is the maximum divisor, divide by 32. `FUSE_SS_DP` is a one-bit fuse where
`0` is full and `1` is reduced, so `1` is *its* maximum.

| Fuse | Address | Governs | 170HX | A100 / A10 / A5000 / A6000 / DRIVE A100 | RTX 3080-3090 Ti |
|---|---|---|---|---|---|
| `FUSE_SS_DP` | `0x00820224` | FP64 (1 bit) | `0x00000001` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FFMA` | `0x0082059c` | FP32 fused multiply-add | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FMLA16` | `0x008207d4` | FP16 MLA | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_FMLA32` | `0x008207d8` | FP32 MLA | `0x00000005` | `0x00000000` | `0x00000001` |
| `FUSE_SS_IMLA0` | `0x008207dc` | integer MLA 0, also DP4A | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA1` | `0x008207e0` | integer MLA 1 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA2` | `0x008207e4` | integer MLA 2 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA3` | `0x008207e8` | integer MLA 3 | `0x00000005` | `0x00000000` | `0x00000000` |
| `FUSE_SS_IMLA4` | `0x008207ec` | integer MLA 4 | `0x00000005` | `0x00000000` | `0x00000001` |
| `FUSE_SS_PLM` | `0x008200fc` | shared PLM over the block | `0xffffffff` | `0xffffffff` | `0xffffffff` |

These readings come from at least five independent 170HX probes across both SKUs between
2026-05-07 and 2026-07-27, plus an 11-card rented comparison cohort and two physical DRIVE A100
(PG199) boards. The values are a **product-line constant**: identical on every 170HX, which is why
a fixed unlock recipe is safe. Contrast this with the override registers below, which are per-die.

> [!NOTE]
> **A frequently repeated imprecision**
>
> Summaries that say "all 9 speed select fuses at `0x5`" are loose. Eight fuses read `0x5`; the
> ninth, `FUSE_SS_DP`, reads `0x1`, which is its own maximum because it is a one-bit field.

### The product-tier signature

`FUSE_SS_FMLA32` and `FUSE_SS_IMLA4` split the probed Ampere cohort into exactly three tiers:

| Value | Parts |
|---|---|
| `0x00000000` | A100 SXM4 40G, A100 PCIe 40G, A100 PCIe 80G, A10, A5000, A6000, DRIVE A100 |
| `0x00000001` | RTX 3080, RTX 3080 Ti, RTX 3090, RTX 3090 Ti |
| `0x00000005` | **CMP 170HX, both units** |

The `0x1` tier is the well-known consumer halving of FP16-with-FP32-accumulate tensor throughput.
The CMP throttle is not a special mechanism: it is the same mechanism turned to its maximum
divisor.

### Why you cannot just change the fuses

Four separate routes were tried and closed:

- **Writing the `OPT_SM_SPEED_SELECT` registers.** They are OTP fuse *shadows* and are read-only
  regardless of privilege. `FUSE_SS_PLM` (`0x008200fc`) being wide open on every card looks like
  an oversight but yields nothing.
- **The FUSECTRL software fuse-override path.** Closed on this part:
  `NV_FUSE_FUSECTRL 0x00820000 = 0xe0040000`, `FUSE_EN_SW_OVERRIDE 0x00820040 = 0x00000000`,
  `ENABLE_FUSE_PROGRAM_STATUS 0x00820078 = 0x00000001`,
  `DISABLE_FUSE_PROGRAM_STATUS 0x0082007c = 0x00000000`,
  `BYPASS_FUSES_STATUS 0x00820080 = 0x00000000`,
  `DISABLE_SW_OVERRIDE_STATUS 0x00820084 = 0x00000001`. A GA10x control card shares the FUSECTRL
  value but has `EN_SW_OVERRIDE = 0x00000001`, which proves the register works and that it was
  deliberately closed here.
- **The FECS mirror.** `FECS_FEAT_OVERRIDE 0x00409664` and `FECS_FEAT_READOUT_1 0x00409668` return
  the PRI privilege-violation sentinel `0xbadf5040` on all fifteen probed Ampere cards, including
  unthrottled ones, so the value is a read-block indication and not data.
- **Physically re-fusing the silicon.** Named as an attack path in 2024, never attempted, made
  moot by the override register.

---

## Layer 2: the FEATURE_OVERRIDE block

The `0x00823800` block is a set of registers that **outrank the fuses**. A full range scan of
`0x00823800` to `0x00823ffc` on a locked card returned only thirteen live dwords; every other
offset returned `0xbadf5040`.

| Register | Address | Stock 170HX | Role |
|---|---|---|---|
| `FEATURE_OVERRIDE_ECC PLM` | `0x00823800` | `0xffffff8f` | PLM over the ECC override group (distinct register from `0x00823804`) |
| **`FEATURE_OVERRIDE PLM` (FEAT_OVR_PLM)** | **`0x00823804`** | **`0xffffff8f`** | **the gate. L3-only at stock. Always-on island** |
| `FEATURE_OVERRIDE_QUADRO` | `0x00823808` | `0x00000181` / `0x00000182` on the two physical 170HX units; other dumps read `0x00100183` (stock PLM range scan) and `0x00000081` (post-unlock probe); A100 80 GB reads `0x01000282` | Per-die, one of the 13 binning differences, and unexplained. Read only. Why the value differs across dumps is an open question; see the [register reference](register-reference.md) |
| `FEATURE_OVERRIDE_ECC` | `0x0082380c` | `0x00888888` | SM_LRF / L1 / LTC / DRAM / CBU ECC control |
| `FEATURE_OVERRIDE_ECC_1` | `0x00823810` | `0x002aaaaa` | icache / FECS / GPCCS / PMU / HUBMMU ECC |
| `FEATURE_READOUT` (READOUT_0) | `0x00823814` | `0x00000233` | Quadro bits [5:0] + ECC status [31:12], read-only |
| **`FEATURE_READOUT_1`** | **`0x00823818`** | **`0x016db6ed`** | **read-only effective SM speed select, all nine units** |
| **`FEATURE_OVERRIDE_SM_SPEED_SELECT` (SS0)** | **`0x0082381c`** | per-die | **IMLA0-3, FMLA16, FMLA32, FFMA, DP: eight 4-bit fields** |
| **`FEATURE_OVERRIDE_SM_SPEED_SELECT_1` (SS1)** | **`0x00823820`** | per-die | **the ninth field, IMLA4** |
| `FEATURE_OVERRIDE_ROW_REMAPPER` | `0x00823824` | `0x00000000` / `0x00000001` | has its own PLM at `0x00823b00` |
| `FEATURE_READOUT_2` | `0x00823828` | `0x00000000` | |
| `FEATURE_OVERRIDE_ECC_2` | `0x0082382c` | `0x0000000a` | LTC_CBC and SM_URF ECC |
| `FEAT2 PLM` (ROW_REMAPPER PLM) | `0x00823b00` | `0xffffff8f` | opened only by the Gen2-family branches |

> [!CAUTION]
> **SS0 and SS1 are per-die binning values. Never treat one card's reading as canonical.**
>
> Measured stock SS0 across the cohort: 170HX `0x51261070`, another 170HX `0x10206152`, a third
> `0x71066125`, a fourth `0x12103060`; a `0x20bb` GA100 reference board (unthrottled, `FEAT_READOUT_1` = 0)
> `0x53540175`; A100 SXM4 40G `0x10413004`;
> A100 PCIe 40G `0x14604062`; A100 PCIe 80G `0x72020072`; A10 `0x11303071`; A5000 `0x63573073`;
> A6000 `0x14170072`; RTX 3080 `0x03676064`; RTX 3080 Ti `0x10551033`; RTX 3090 `0x06740057`;
> RTX 3090 Ti `0x30403100`; DRIVE A100 `0x25045144`. Two archived dumps of the *same* A100 80 GB
> device ID disagree with each other (`0x00112011`/`0x00000002` versus
> `0x00343015`/`0x00000004`), so these are runtime state, not stable fuse state. Use
> `FEATURE_READOUT_1` (`0x00823818`), not SS0/SS1, as a reference target.

`FEATURE_READOUT_1` is the one value that is stable and meaningful: it reads `0x016db6ed`
identically on both physical 170HX cards despite their SS0/SS1 differing, `0x00000000` on every
A100 and the DRIVE A100, and `0x00400080` on all four RTX 30-series parts. **`0x00823818 == 0` is
the cleanest available "is this card unlocked" test.**

### The nibble encoding

Each SS0 nibble is best read as `[enable | 3-bit speed]`. `0x8` sets bit 3 (override enable) with
bits [2:0] = 0 (speed 0, full rate). So `0x88888888` means "override enabled, full rate" on all
eight SS0 units, and `0x00000008` does the same for IMLA4 alone in SS1.

> [!WARNING]
> **Encoding is inferred, not documented**
>
> No NVIDIA documentation for this field layout exists in the corpus. The reading is supported
> by three observations: no stock dump anywhere in the archive has any nibble greater than or
> equal to 8, i.e. on stock silicon the override-enable bits are clear and the field contents are
> don't-care; the effective readout at `0x00823818` goes to zero after the write; and the
> performance result matches. It has never been confirmed field by field. A single-nibble sweep
> of SS0 on an unlocked card, watching which bits of `0x00823818` move, would settle both this
> and the readout decode.

### The gate chain

```text
FUSE_QUADRO_WR_SEC (0x0082038c) = 1
        permits
FEAT_OVR_PLM (0x00823804) to be opened from 0xffffff8f to 0xffffffff
        permits
PL0 host writes to SS0 (0x0082381c) and SS1 (0x00823820)
        which
outrank the OPT_SM_SPEED_SELECT fuses
```

Two gating fuses were measured on the same card: `OPT_SECURE_FEATURE_OVERRIDE_QUADRO_WR_SECURE`
(`0x0082038c`) = `0x00000001` and `OPT_SECURE_GSP` (`0x0082074c`) = `0x00000001`.

And above all of it:

> [!NOTE]
> **The one fuse that makes this possible**
>
> `OPT_FEATURE_FUSES_OVERRIDE_DISABLE` (`FUSE_FEAT_OVR_DIS`) at `0x008203f0` reads
> `0x00000000` on the CMP 170HX. The probe annotates it "MASTER KILL: if YES all overrides
> permanently locked". Had NVIDIA blown that one fuse, every route on this page would be closed
> permanently. It reads zero on every card probed, including the GA10x control.

Note that `FEAT_OVR_PLM 0x00823804` reads `0xffffff8f` (L3-only) on **all fifteen** probed Ampere
parts, including every A100. The 170HX is not special here. The unlock's entire difficulty is
reaching L3 to change it, which is what the [SEC2 Booter path](falcon-and-booter.md) does. Only
SS0 and SS1 are host-writable at PL0; the PLM itself must be written by a Falcon in
high-security mode. As one analysis put it, if that were not so, any NVIDIA card could be unlocked
without an exploit.

---

## What the shipping code actually does

From `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` on branch `master`, inside the GSP
bootstrap path, gated on PCI device ID by `_kgspSec2PostblTimingEnabled()` which accepts
`0x20C2` (8 GB) **and** `0x2082` (10 GB):

```c
static const struct { NvU32 addr; NvU32 value; const char *name; } plmTable[] = {
    { 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
    { 0x009a0148U, 0xffffffffU, "FBPA" },
    { 0x001fa7c4U, 0xffffffffU, "WPR" },
    { 0x00823804U, 0xffffffffU, "FEAT" },
};

NvU32 wpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824U);
NvU32 wpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828U);

for (plmIdx = 0; plmIdx < 4; plmIdx++)
{
    NvBool opened = NV_FALSE;
    for (attempt = 0; attempt < 2 && !opened; attempt++)
    {
        GPU_REG_WR32(pGpu, 0x001fa824U, wpr2Lo);        /* re-arm WPR2 before every attempt */
        GPU_REG_WR32(pGpu, 0x001fa828U, wpr2Hi);

        plmStatus = kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
            plmTable[plmIdx].addr, plmTable[plmIdx].value);
        if (plmStatus != NV_OK)
            continue;

        plmStatus = kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
            memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));

        NvU32 regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
        if (regVal == plmTable[plmIdx].value)
            opened = NV_TRUE;
    }
}
```

then, after the PLMs are open:

```c
GPU_REG_WR32(pGpu, 0x0082381cU, 0x88888888U);   /* SS0  */
GPU_REG_WR32(pGpu, 0x00823820U, 0x00000008U);   /* SS1  */
GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);     /* CFG1 (memory geometry) */
GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);      /* LMR  (memory geometry) */
```

Points worth noting:

- The payload carries **one** (address, value) pair, and Booter Load is re-fired **once per PLM**,
  up to **2 attempts each**, with the WPR2 bounds at `0x001fa824` / `0x001fa828` saved and restored
  around every attempt. Success is judged by **readback**, not by the Booter status, which returns
  `0xffff` on every run whether it worked or not.
- Only **three** of the four PLMs go to `0xffffffff`. `WPR_CFG 0x001fa7cc` is written
  `0xfffff0ff`. Any documentation saying "all PLMs must show `0xffffffff`" is loose wording.
- **SS0 and SS1 are identical for both SKUs.** Only `cfg1Value` and `lmrValue` are selected by
  device ID. See [memory geometry](memory-geometry.md) for those.
- Shipping order is SS0, SS1, CFG1, LMR, followed by a single readback log line.
- Both SS0 **and** SS1 must be written. Writing only one is not enough.
- `common/constants.yaml` records `compute: ss0: "0x88888888"` / `ss1: "0x00000008"`, but neither
  `install.sh` nor `driver/build.sh` reads that file. The values are hard-coded in the patch.
  Treat the YAML as documentation that happens to agree with the code.
- SS0/SS1 are byte-identical in all twelve unreleased branches. No branch ever experimented with
  different compute values; all compute experimentation predates the values being settled.

---

## Verifying the unlock

A second shipping patch, `0002-booter-verify.patch`, defines the canonical five-register set the
project itself considers definitive and logs them after every Booter Load:

| Symbol | Address |
|---|---|
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM` | `0x00823804` |
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED` | `0x0082381c` |
| `SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1` | `0x00823820` |
| `SEC2_DEBUG_PRI_FBPA_CFG1` | `0x009a0204` |
| `SEC2_DEBUG_PRI_MMU_LMR` | `0x00100ce0` |

```bash
sudo dmesg | grep SEC2_DEBUG
```

A successful 8 GB card prints:

```text
SEC2_DEBUG: POST-WRITE SS0=0x88888888 SS1=0x00000008 CFG1=0x02779000 LMR=0x0000020b (devId=0x20c2)
```

Post-unlock register state on an 8 GB card, versus a locked comparison card:

| Register | Address | Locked | Unlocked |
|---|---|---|---|
| `FEAT_OVR_PLM` | `0x00823804` | `0xffffff8f` | `0xffffffff` |
| SS0 | `0x0082381c` | per-die, e.g. `0x12103060` | `0x88888888` |
| SS1 | `0x00823820` | per-die, e.g. `0x00000003` | `0x00000008` |
| `FEAT_READOUT_1` | `0x00823818` | `0x016db6ed` | `0x00000000` |
| `FUSE_SS_FFMA` and friends | `0x0082059c` etc. | `0x00000005` | **`0x00000005`, unchanged** |

That last row is the hard confirmation that this is an override and not a fuse edit: after a
successful unlock the fuse shadows still read `5` (and DP still reads `1`), while the effective
readout is zero.

> [!WARNING]
> **`clocks.max.sm` is not a good verification signal**
>
> `install.sh` prints `nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader` as its
> compute verification step, and one post-unlock report read `1935 MHz` from it. Every sustained
> measurement contradicts reading that as an operating clock: the VBIOS table maximum graphics
> clock is 1695 MHz and the practical silicon ceiling is about 1604 to 1614 MHz at a +350 offset.
> Sustained SM clock is **1410 MHz** (1470 MHz at `-pl 300`). Treat 1935 MHz as a reported field,
> single report, low confidence. A better functional check is that the NVML GPC clock VF offset
> range comes back as `[-1000 .. +1000]` rather than `[0 .. 0]`; see
> [tuning](../operations/tuning.md).

---

## The measured improvement

Locked FP32 fused multiply-add throughput measures **394.77 GFLOPS**, and it is *identical* across
float, float2, float4, float8 and float16. That perfect flatness across vector widths is
the signature of a fixed instruction-issue restriction rather than a bandwidth or occupancy limit.
The arithmetic closes exactly: theoretical FP32 for 4480 lanes at 1410 MHz is 12.634 TFLOPS, and
12.634 / 32 = 394.8 GFLOPS.

That five-digit figure is **not** a community measurement. It comes from a public 2023 clpeak
review of a stock, never-unlocked card, which is also the source of the matching no-FMA control
(float 6285.48 GFLOPS, about 16x faster) and of locked FP64 at 182.72 GFLOPS. The community record
carries only rounded restatements of the same quantity: 0.39 TFLOPS in an 8-card benchmark
write-up, and 0.38 TFLOPS *back-computed* as 12.28 / 32 rather than measured. Quote it as
**roughly 0.39 TFLOPS** unless the external clpeak run is being cited directly.

### First full before/after table (2026-07-06, one card)

Posted as a rendered image, not as tool output, alongside the first "I have compute unlock working"
report in the private verified channel. Source attachment:
`archive/cleanroom/1523499947490541640_PNG_image.png`.

| Datatype | Throttled | Unlocked | Ratio |
|---|---|---|---|
| FP64 | 0.20 TF/s | 12.91 TF/s | 63.0x |
| FP32 IEEE | 0.41 TF/s | 12.69 TF/s | 31.0x |
| INT8 | 1.63 TOP/s | 50.50 TOP/s | 30.9x |
| BF16 | 6.40 TF/s | 184.86 TF/s | 28.9x |
| FP16 | 6.52 TF/s | 153.92 TF/s | 23.6x |
| INT4 | 11.55 TOP/s | 259.34 TOP/s | 22.5x |
| INT1 | 46.16 TOP/s | 1038.89 TOP/s | 22.5x |
| TF32 | 90.72 TF/s | 90.09 TF/s | 1.0x, marked "untouched" (disputed) |

> [!NOTE]
> **Why this date is six days before the timeline's unlock milestone**
>
> [timeline.md](../history/timeline.md) dates "compute unlock works on hardware" to **2026-07-12**.
> That is the first *community-reproduced* unlock. This table predates it because the private
> verified channel had compute working on **2026-07-06 01:24**, in the same message that reported
> INT4 and INT8 hitting 300 and 600 with CUTLASS TN shape tuning. The two dates are not in
> conflict; they mark private first light and public reproduction.
>
> Treat the numbers themselves with the caution an image deserves: no tool is named, no clock or
> flop-counting convention is stated, and none of the eight rows was ever reproduced digit for
> digit. The throttled column is corroborated in kind by the external clpeak review (locked FP64
> 182.72 GFLOPS against 0.20 TF/s here; locked FP32 394.77 GFLOPS against 0.41 TF/s), and the
> unlocked FP16 and BF16 rows sit inside the later 8-card spread. The TF32 row is disputed
> outright.

### Independent confirmations

| Measurement | Value | Conditions |
|---|---|---|
| SGEMM FP32 | 12.28 TFLOPS | 2026-07-12, first reported full SM unlock outside the verified channel, cc 8.0; corroborated about one minute later by an independent gpu-burn run at 12229 Gflop/s, 0 errors, 62 C |
| DGEMM FP64 | 11.48 TFLOPS | same run (tensor DMMA path, see below) |
| FP32, OpenCL-Benchmark | 12.890 TFLOPs/s | 64 GB unlocked card, driver 610.43.03 |
| FP64, OpenCL-Benchmark | 6.421 TFLOPs/s (1/2 of FP32) | same run |
| FP16, OpenCL-Benchmark | 48.740 TFLOPs/s (4x FP32) | same run |
| INT8, OpenCL-Benchmark | 49.362 TIOPs/s | same run |
| FP32 non-tensor | 12.6 to 12.76 TFLOPS | 2026-07-27, one tuned card plus an 8-card rental |
| FP16 tensor | 158.7 to 162.7 TFLOPS | same campaign |
| BF16 tensor | 171.4 to 192.7 TFLOPS | same campaign |
| TF32 tensor | 79.0 to 91.9 TFLOPS | same campaign |
| INT8 | 44.1 TOPS | same campaign, still gated |

### The FP64 spread is two paths, not a dispute

The apparent conflict between roughly 6.3 and roughly 12 TFLOPS FP64 is **settled**, and it was
settled by a single clpeak dump on 2026-07-15 that printed both numbers in one run, on one card
(sm_80, 70 SMs, 7890 MB, driver 13.0):

| Path | Instruction | Measured |
|---|---|---|
| FP64 non-tensor | plain `double` FMA | **6.31 TFLOPS** (`double : 6308.65` GFLOPS) |
| FP64 tensor | `wmma`/`mma` `fp64xfp64+fp64` 8x8x4 (DMMA) | **11.96 TFLOPS** (`wmma_fp64 : 11.96`) |

The non-tensor figure is the architectural 1:2 rate: half of the same run's FP32 (`float :
12565.14` GFLOPS). The tensor figure is the second FP64 datapath GA100 exposes, and it is where
the 11.48 to 12.91 TFLOPS cluster comes from. So the OpenCL-Benchmark 6.421 TFLOPs/s and the DGEMM
11.48 TFLOPS were never measuring the same thing, and no flop-counting error is involved.

State it as: **FP64 non-tensor about 6.3 TFLOPS, FP64 tensor about 12 TFLOPS.** Both are fully
restored by the unlock. The same dump is the cleanest single-run source for the tensor rows
generally: `wmma_fp16` 179.19, `fp16_f16acc` 189.66, `wmma_bf16` 179.19, `wmma_tf32` 89.69 TFLOPS.

### Tensor-core collapse before the unlock

Cycle-level measurement against an A800 control shows what the throttle did to `mma.sync`:

| Warps | 170HX (throttled) | A800 control |
|---|---|---|
| 1 | 256.40 cycles | 24.64 cycles |
| 4 | 256.34 cycles | 24.55 cycles |
| 5 | 374.65 cycles | |
| 8 | 513.83 cycles | |
| 16 | 1026.20 cycles | |
| 32 | 2039.46 cycles | 71.45 cycles |

Wall throughput never exceeded about 0.082 TFLOPs at any occupancy, versus 1.807910 TFLOPs on the
A800. Roughly a 10x per-instruction penalty compounded by a hard limit of 4 warps of `mma.sync` in
parallel per SM.

---

## What the unlock does not change

- **It does not add SMs.** 70 SM before and after, `smid` 0..69 with no gaps. The card is already
  at its silicon fuse floor. See [GA100 silicon](../hardware/ga100-silicon.md).
- **It does not raise clock speeds.** The canonical in-channel formulation was "compute limit yes,
  bus speed no". Overclocking is a separate NVML lever; see [tuning](../operations/tuning.md).
- **It does not change PCIe link speed or width.** Gen2 lives on unreleased branches
  ([PCIe Gen2](pcie-gen2.md)) and width is a soldering job
  ([physical mods](../operations/physical-mods.md)).
- **It does not restore INT8 / IMMA.** Unlocked INT8 measures 44.1 TOPS, roughly 3.7x *slower*
  than FP16 on the same card, whereas on an A100 INT8 is about 2x *faster* than FP16. The IMLA
  fuses read the same `0x5` and the SS0 override nibbles are set identically, yet the measured
  IMMA rate does not follow. Practical consequence for inference: use W4A16 (AWQ or GPTQ, INT4
  weights with BF16 activations) and avoid W8A8 entirely; KV cache must be BF16. See
  [LLM inference](../operations/llm-inference.md).
- **Scalar FP16 was never throttled**, even on a locked card: GA100 runs 16-bit hfma at 4x its
  FP32 fma rate, and locked cards measure roughly 42 to 50 TFLOPS scalar FP16 (mixbench 41869
  GFLOPS; OpenCL half2-fma about 48 to 50 TFLOPS). This is why locked cards were already usable
  for LLM token generation, and it is a standing puzzle given `FUSE_SS_FMLA16` reads `0x5`.
- **HBM bandwidth and L2 are untouched.** A same-card A/B measured 1592 GB/s stock versus
  1599 GB/s modded, a ratio of 1.0x, in the same table where FP32 moved 30.7x. The full 32 MB L2
  and roughly 12.5 TIOPS of INT32 are likewise unrestricted at stock. Together these bound what
  the throttle touches: FP32 FFMA, DP, DP4A and the tensor MMA paths.

---

## Why `SM_ISSUE_RATE_MODIFIER` (`0x00504204`) is NOT the throttle

This is the most seductive false lead in the whole domain, and it is worth stating flatly:
**`0x00504204` is not the CMP throttle register, and the shipping unlock never touches it.** A
repository-wide grep of the shipping tree for `0x504204` returns zero hits.

The evidence:

| Observation | Detail |
|---|---|
| It reads `0x00000005` on the 170HX | which is exactly the throttle fuse value, hence the appeal |
| It also reads `0x00000005` on A100 SXM4 40G, A100 PCIe 40G and 80G, A10, A5000, A6000, RTX 3080 / 3080 Ti / 3090 / 3090 Ti and DRIVE A100 | full-speed parts, same value |
| It reads `0x00000005` on a 96-SM `0x20bb` GA100 whose every `FUSE_SS_*` reads `0` | the decisive counter-measurement, 2026-07-27 |
| It is host-writable, and zeroing it produces no performance change | null result recorded in the fuse reference table |
| A GA10x control (`0x2484`) reads `0x00000007` there | the value does not track the throttle on any part |
| Pre-driver, the 170HX returns `0xbadf1201` at that offset | as do all five neighbouring SKED registers |

The register does have a real NVIDIA-side consumer. Reverse engineering of GSP firmware found an
init function at VA `0x01607b78` reading the registry key `RMOverrideSmSpeedSelect` and storing a
present flag plus an override dword into the GPU config struct, consumed at VA `0x01155dcc` and by
four helpers at VA `0x01175a48` to `0x01175b2c`, with present-flag checks at `0x014853e4` and
`0x01491f34`. That override flows into the PROD_DIFF list and ends up aimed at
`SM_ISSUE_RATE_MODIFIER`, reached through HAL abstraction (`0x504204` does not even appear as a
literal in the firmware). **The name was right; the target register was wrong.**

A related and instructive dead end: spoofing the `speed_select` fuse value inside GSP firmware so
PROD_DIFF would program `SM_ISSUE_RATE_MODIFIER = 0`. Fourteen firmware patches to
`gsp_ga10x.bin` plus twelve `nvidia.ko` edits moved FFMA from 0.3159 TFLOPS to 0.3146 TFLOPS, a
0.4% delta called measurement noise. It failed for two independent reasons: FECS reaches GPU
registers through a priv window spanning `0x20000000` to `0x23050000`, and the SM register space
where `SM_ISSUE_RATE_MODIFIER` lives (`0x20504xxx`) is completely absent from it, so FECS is
physically unable to write it even with a perfect PROD_DIFF list; and GSP-RM is NVIDIA-signed
anyway.

> [!NOTE]
> **Open problem: does `0x00504204` impose any residual limit on an already-unlocked card?**
>
> Nobody has run the obvious A/B: write `0x00504204` to zero **on a card whose SS0/SS1 are
> already set** and re-run the benchmark suite. The register is host-writable, the write
> primitive exists in the ROP toolchain, and the answer is a yes or no. This is the most
> tractable open question in the compute domain. A second, related unknown is whether
> `0xbadf1201` at that offset means "privilege-blocked" or "not decoded" on GA100: the whole
> `0x00504xxx` and `0x00407xxx` aperture returns the same sentinel on a 170HX while a GA10x
> control returns real values everywhere, which points at an address-decode difference rather
> than a per-register block. A `0x20bb` GA100 reading a real `0x00000005` complicates that.

---

## Why compute survives FLR

`FEAT_OVR_PLM` at `0x00823804` sits in the **always-on (AON) island**. It is the only PLM in the
26-register PLM survey marked AON, and none of the framebuffer-geometry PLMs are. Once opened it
stays open across a Function Level Reset, and the SS0/SS1 values written through it stay written.

| Behaviour under FLR | Registers |
|---|---|
| **Survive** | SS0 `0x0082381c`, SS1 `0x00823820`, `FEAT_OVR_PLM` `0x00823804` |
| **Do not survive** | CFG1 `0x009a0204`, per-FBPA CFG1, CSTATUS, LMR `0x00100ce0`, the FB-geometry PLMs (which re-lock), and the AON LMR shadow `0x001180f0` (which reverts) |
| **Cleared by FLR** | the SEC2 reset-PLM taint (`0x8f` back to `0xff`) |

This was established by a dedicated FLR survival sweep (`plm_flr_survival_20260716.sh` plus
`fire_vram_featovr_sweep.sh`) and independently corroborated by a second tester two days earlier.

```bash
# Function Level Reset, as used by every unlock harness
echo 1 | sudo tee /sys/bus/pci/devices/0000:${PCI}/reset
```

**This asymmetry is the single reason the compute unlock shipped before the memory unlock.** The
compute writes are sticky in the always-on domain; the memory-geometry writes are lost on the
first reset, which is why the memory path needed a two-load, no-FLR workflow.

Two clarifications that are often conflated:

- **The registers themselves are volatile.** Removing power loses them. What changed with the
  shipping driver patch is not the hardware behaviour but that the patched modules reapply the
  whole PLM-open plus SS0/SS1 sequence on **every GSP bootstrap** for device `0x20C2` or `0x2082`.
  So the user-facing statement is "persists across reboot", while the hardware statement
  "nothing survives a power cycle" is still true underneath.
- **Writing SS0/SS1 with no driver loaded and then loading the stock driver does not work.** The
  writes visibly land, but the stock driver re-locks the PLM: `0x00823804` reads back `0xffffff8f`
  and the throttle dividers return to `5`. That failure mode is precisely why the in-driver
  GSP-boot-path approach exists.

---

## Remaining open questions

> [!NOTE]
> **Open problems in this domain**
>
> 1. **Does `0x00504204` matter on an unlocked card?** See above. One A/B settles it.
> 2. **Why is INT8 / IMMA still gated?** The IMLA fuses read `0x5` and the override nibbles are
>    set identically to the FMA ones, yet measured IMMA does not follow. Next step: dump
>    `0x00823818` alongside a per-datatype microbenchmark to see whether the effective IMLA
>    fields really are zero, and look for a separate DP4A/IMMA gate outside the
>    `SM_SPEED_SELECT` block.
> 3. **Isolate SS1's effect on FP64.** The claim "SS1 nerfs 64-bit compute" is, strictly, an
>    untested 2026-07-14 prediction that happens to sit next to a correct FP64 measurement. A
>    one-line build with the `0x00823820` write removed, then the OpenCL FP64 test, would give
>    the answer (expect 6.421 versus something near 0.19 TFLOPs/s if the belief is right).
> 4. **Decode `FEATURE_READOUT_1` (`0x00823818`).** A naive nine-by-three-bit LSB-first unpack of
>    the stock `0x016db6ed` yields `[5,5,3,3,3,3,3,3,1]`, which does not match the fuses
>    (uniformly 5 with DP at 1, predicting `0x01b6db6d`). Either the field order or width
>    assumption is wrong, or the readout is a post-arbitration effective rate. Regardless of
>    decode, `== 0` remains the practical success test.
> 5. **Why does `FUSE_SS_FMLA16 = 0x5` not appear to throttle FP16?** Likely because FMLA16
>    governs a tensor/MLA path distinct from the packed-half CUDA-core path, but nobody has
>    measured FP16 scalar and FP16 tensor separately on the same card in both states.
> 6. **Is TF32 throttled at stock?** One table says `90.72 → 90.09 TF/s` (untouched); another,
>    on a different card, says `2.96 → 51.53`, `3.01 → 84.75` and `3.21 → 80.59 TFLOPS` at
>    1024³, 4096³ and 8192³. Both cannot be true. One TF32 GEMM on a card confirmed locked by
>    `0x00823818 != 0x00000000` would settle it.
> 7. **Is `0x008200fc` writable, and what does it read cold?** `0xffffffff` in one sweep,
>    `0x000003ff` in another, and `status=0xffff` from the nine-PLM branch attempt with no
>    readback recorded. The register is called `FUSE_SS_PLM` in clean-room tooling and
>    `OPT_PLM` in branch source; they are the same register.

---

## Related pages

- [How the unlock works, end to end](how-it-works.md)
- [The SEC2 Falcon and Booter primitive](falcon-and-booter.md)
- [Privilege level masks](privilege-level-masks.md)
- [Memory geometry unlock](memory-geometry.md)
- [Driver patches](driver-patches.md)
- [Full register reference](register-reference.md)
- [GA100 silicon and floorsweeping](../hardware/ga100-silicon.md)
- [Fuses and OTP](../hardware/fuses-and-otp.md)
- [Verification procedure](../procedures/verify.md)
- [Performance](../operations/performance.md) and [tuning](../operations/tuning.md)
- [Glossary](../start/glossary.md)
