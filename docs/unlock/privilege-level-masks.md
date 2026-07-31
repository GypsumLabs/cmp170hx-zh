# Privilege Level Masks

**What this page covers.** What a PLM is on GA100, how the mask bits are encoded, the exact four
masks the shipping unlock opens and the exact value each is opened to, why one of the four is
deliberately opened only partially, which masks survive a function-level reset and which do not,
and the nine-mask table the unreleased PCIe branches use instead. The mechanism that performs the
opens is on [The ROP chain](rop-chain.md); the microcode it runs on is on
[The SEC2 Falcon and the Booter Load microcode](falcon-and-booter.md).

**The key result up front.** The unlock opens exactly four masks, in a fixed order, and only three
of them are opened to all ones:

| Order | Name | BAR0 address | Value written |
|:---:|---|---|---|
| 0 | `WPR_CFG` | `0x001fa7cc` | **`0xfffff0ff`** |
| 1 | `FBPA` | `0x009a0148` | `0xffffffff` |
| 2 | `WPR` | `0x001fa7c4` | `0xffffffff` |
| 3 | `FEAT` | `0x00823804` | `0xffffffff` |

> [!CAUTION]
> **`WPR_CFG` opens to `0xfffff0ff`, not `0xffffffff`**
>
> Bits [11:8] of `0x001fa7cc` are deliberately left clear. Both the project README and the
> `docs` branch describe the unlock as "opening the PLMs to `0xffffffff`", or state that all PLMs
> must read `0xffffffff` after a successful unlock. That phrasing is imprecise for the first entry
> and will make a correct unlock look like a failure to anyone verifying by eye. A card that shows
> `0x001fa7cc = 0xfffff0ff` and the other three at `0xffffffff` is **correct**.

---

## 1. What a PLM is

The host, the SEC2 Falcon and the GSP NVRISC-V core all talk to the GPU's internal registers over
**PRI**, a shared privileged register interface. The host's window onto PRI is BAR0. PRI is not flat
and open: regions of it are gated by **Privilege Level Masks**, one small register per protected
region, that declare which privilege levels may read the region, which may write it, and which
on-die sources are allowed to issue those accesses at all.

Falcon-family privilege levels run L0 to L3, mapping onto the Falcon execution modes described on
[falcon-and-booter.md](falcon-and-booter.md#2-the-falcon-security-model):

| Level | Who | Typical reach |
|---|---|---|
| L0 | The host over BAR0, and non-secure Falcon code | Ordinary registers |
| L1 / L2 | Light-Secure Falcon contexts | Intermediate |
| L3 | Heavy-Secure Falcon code | Everything, including the PLMs themselves |

The whole unlock exists because the registers that change the card's memory geometry and compute
throttle are gated by masks that permit L3 writes only, and the only way to reach L3 on this die is
to be running inside a signed heavy-secure microcode. Once a PLM has been rewritten from inside HS
to allow L0 writes, ordinary host BAR0 writes work with no further exploit. This pivot is the entire
architecture of the shipping unlock.

> [!WARNING]
> **PLM means Privilege Level Mask**
>
> The project's own `docs` branch (`cmpunlocker-branches/docs/docs/ARCHITECTURE.md`) expands PLM
> as "Program Logic Modules", and also invents "PMM (Permute Mask Model)", "LMR (LM Request)",
> "SS0/SS1 (Suspension State)" and "PMA (Power Management Array)". All of these are inventions.
> The underlying register name in NVIDIA's headers is `PRIV_LEVEL_MASK`. Nothing from that
> document should be carried into a description of this hardware. See
> [dead ends](../history/dead-ends.md).

---

## 2. Bit encoding

The encoding used throughout this project, consistent with every observed value on the die:

| Field | Bits | Meaning |
|---|---|---|
| `READ_PROTECTION` | [3:0] | Which levels may read |
| `WRITE_PROTECTION` | [7:4] | Which levels may write |
| `SOURCE_ENABLE` | [23:8] | Which on-die sources may issue the access |

Common values:

| Value | Reading |
|---|---|
| `0xFFFFFF8F` | Read at all levels, write L3-only, all sources enabled. **The locked baseline on this die.** |
| `0xFFFFFFFF` | Fully open: read and write at all levels, all sources. |
| `0xFFFFFFCF` | Another observed write-locked pattern. |
| `0x0004CB8F` | What `WPR` and `WPR_CFG` are re-locked to after a stock driver load post-unlock. |
| `0xFFFFFE8E` | Observed on `0x009A0008`, `0x00100B10` and `0x00100B38` after a stock driver load. |
| `0x0000008F` / `0x000000DF` | Low-byte-only patterns seen on the SEC2 reset PLM. |

Confidence in the exact three-field decomposition is high as a working model: it matches every
observed baseline, every observed post-unlock value and the shipping unlocker's choice of
`0xFFFFFFFF`. It is inferred from behaviour rather than read from a published header.

Two practical consequences of the encoding:

- **`0x000000FF` is not "open".** It sets only the READ and WRITE nibbles and leaves
  `SOURCE_ENABLE = 0`, which blocks everything. ROP v2 wrote `0x000000FF` to `0x00823804` for
  exactly this reason and it did nothing useful; every later payload and the shipping patch write
  `0xFFFFFFFF`.
- **PLMs reject out-of-range values.** Writing an arbitrary value such as `0xff` to a PLM bounces
  even when other masks are open. Brute-forcing PLM values is therefore bounded by the hardware's
  accepted encodings, not by the full 32-bit space. Observed directly by at least two people on two
  different cards.

---

## 3. The four masks the unlock opens

### 3.1 The table, exactly as it appears in the source

```c
static const struct {
    NvU32 addr;
    NvU32 value;
    const char *name;
} plmTable[] = {
    { 0x001fa7ccU, 0xfffff0ffU, "WPR_CFG" },
    { 0x009a0148U, 0xffffffffU, "FBPA"    },
    { 0x001fa7c4U, 0xffffffffU, "WPR"     },
    { 0x00823804U, 0xffffffffU, "FEAT"    },
};
```

This table is byte-identical in shipping `master` and in every archived branch except the four
Gen2-family branches, which extend it (section 6).

### 3.2 What each one gates

| Name | Address | Gates | Why the unlock needs it |
|---|---|---|---|
| `WPR_CFG` | `0x001fa7cc` | The WPR mask/configuration registers `0x001fa814` / `0x001fa818`, and the WPR region block generally | The write-protected-region machinery has to be re-armable across the repeated Booter fires |
| `FBPA` | `0x009a0148` | The FBPA (frame-buffer partition) register aperture, including broadcast CFG1 at `0x009a0204` | Host PL0 must be able to write CFG1 after the fires. See [memory geometry](memory-geometry.md). |
| `WPR` | `0x001fa7c4` | The WPR1/WPR2 address registers `0x001fa81c`-`0x001fa828` | WPR2 lo/hi must be re-armed by the host before every fire |
| `FEAT` | `0x00823804` | The feature-override block `0x00823800`-`0x00823FFC`, including SS0 `0x0082381c` and SS1 `0x00823820` | Host PL0 must be able to write the compute-throttle overrides. See [compute throttle](compute-throttle.md). |

`FEAT` is the interesting one for persistence, because it lives in an always-on island. See
section 5.

### 3.3 The stock values

| Register | Stock reading | Notes |
|---|---|---|
| `0x00823804` `FEAT_OVR_PLM` | `0xffffff8f` | Reads identically on **every** Ampere card probed: both 170HX units, A100 SXM4 40G, A100 PCIe 40G, A100 PCIe 80G, A10, A5000, A6000, RTX 3080 / 3080 Ti / 3090 / 3090 Ti, and Drive A100 |
| `0x00823800` `FEAT_OVR_ECC_PLM` | `0xffffff8f` | A100 SXM4 40G alone reads `0x0000abcf`, unexplained |
| `0x00823B00` (row-remapper PLM) | `0xFFFFFF8F` | |
| `0x009a0148` `FBPA` | `0xFFFFFF8F` | |
| `0x001fa7c4` / `0x001fa7cc` | locked | Re-lock to `0x0004CB8F` after a stock driver load |

Only three registers in the whole `0x823800`-`0x823FFC` window read `0xFFFFFF8F` on a locked card:
`0x823800`, `0x823804` and `0x823B00`. That shared value is what identifies them as the PLMs
guarding the block. They are not the only readable dwords, though: a 2026-07-16 range scan of the
whole window on a locked card returned twelve live dwords at PL0, the contiguous run
`0x823800`-`0x82382C` plus `0x823B00`, and `0xBADF5040` for every other dword up to `0x823FFC`.

---

## 4. How the opens are performed

The mechanics are the same for all four entries, and they are worth reading closely because the
success criterion is not what the log lines suggest.

```c
savedWpr2Lo = GPU_REG_RD32(pGpu, 0x001fa824);
savedWpr2Hi = GPU_REG_RD32(pGpu, 0x001fa828);
/* SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x */

for (plmIdx = 0; plmIdx < 4; plmIdx++) {
    opened = NV_FALSE;
    for (attempt = 0; attempt < 2 && !opened; attempt++) {
        GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
        GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
        kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
                                          plmTable[plmIdx].addr,
                                          plmTable[plmIdx].value);
        kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
            memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
        regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
        opened = (regVal == plmTable[plmIdx].value);   /* exact equality */
    }
    /* SEC2_DEBUG: FAILED to open <name> after 2 attempts */
}
GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
```

Points that matter:

- **One Booter Load fire per attempt, one arbitrary BAR0 write per fire.** The payload carries a
  single `(writeAddr, writeValue)` pair, so opening four masks costs four to eight fires.
- **WPR2 lo/hi are re-armed before every single attempt**, up to eight times, and once more after
  the loop, because every fire re-carves WPR2 and a subsequent Booter Load would otherwise abort
  with "WPR2 already up". The shipping driver restores the *saved* pair; it does not write the
  constant `0x1FFFFE00` / `0` that the driverless tools write.
- **Success is exact read-back equality**, not the Booter status. Every fire reports
  `status=0xffff` and logs `Booter failed with non-zero error code: 0x31` regardless of outcome. The
  register read-back is the only valid verdict.
- **Failure of one entry does not abort the loop.** It logs and moves on.

Shipping `master` logs one line per attempt, then a summary line after the loop:

```text
SEC2_DEBUG: PLM[%u] %s(0x%x) attempt=%u status=0x%x reg=0x%08x
SEC2_DEBUG: PLMs: FEAT=0x%08x FBPA=0x%08x WPR=0x%08x WPR_CFG=0x%08x
```

A real line reads `SEC2_DEBUG: PLM[3] FEAT(0x823804) attempt=0 status=0xffff reg=0xffffffff`, with
the index-to-name mapping `PLM[0]=WPR_CFG, PLM[1]=FBPA, PLM[2]=WPR, PLM[3]=FEAT`. The unreleased
branches use the same per-entry format.

The shorter `SEC2_DEBUG: PLM FEAT before:` / `PLM FEAT after:` pair that circulates in fork threads
is **not** a shipping string: a grep of the shipping repository finds no such text. The values it
quotes (`0xFFFFFF8F` locked, `0xFFFFFFFF` opened) are right for `FEAT`, but do not use the line
itself as the thing to look for in `dmesg`.

If a mask still reads its locked value afterwards, the open did not happen, and the documented
remedy is another cold boot. See [troubleshooting](../procedures/troubleshooting.md).

### 4.1 What happens after the loop

Once the four masks are open the driver performs four plain host `GPU_REG_WR32()` calls at PL0, with
no further exploit:

| Register | Value | Purpose |
|---|---|---|
| `0x0082381c` (SS0) | `0x88888888` | Compute throttle |
| `0x00823820` (SS1) | `0x00000008` | Compute throttle |
| `0x009a0204` (CFG1) | `0x02779000` (8 GB card) / `0x02669000` (10 GB card) | Memory geometry |
| `0x00100ce0` (LMR) | `0x0000020B` (8 GB card) / `0x0000028A` (10 GB card) | Memory geometry |

> [!WARNING]
> **The `docs` branch is wrong about SS0 and SS1**
>
> `ARCHITECTURE.md` states `SEC2_DEBUG: SS0 = 0xffffffff` and `SS1 = 0xffffffff`, and prints an
> expected log line `SEC2_DEBUG: Executing unlock sequence...` that does not exist anywhere in the
> code. The shipping code writes SS0 = `0x88888888` and SS1 = `0x00000008`. The geometry table in
> the same document (8 GB to 64 GB with `0x02779000`/`0x0000020B`, 10 GB to 40 GB with
> `0x02669000`/`0x0000028A`) is, however, correct.

---

## 5. Persistence: which masks survive a reset

This asymmetry is the single most consequential property of the PLM set, and it is why the compute
unlock shipped before the memory unlock.

| Register | Survives FLR? | Notes |
|---|---|---|
| `FEAT` `0x00823804` | **Yes** | Always-on (AON) power island |
| SS0 `0x0082381c`, SS1 `0x00823820` | **Yes** | AON |
| `WPR` `0x001fa7c4`, `WPR_CFG` `0x001fa7cc` | No | Re-lock to `0x0004CB8F` after a stock driver load |
| `FBPA` `0x009a0148` | No | Reads `0xFFFFFF8F` again |
| CFG1 `0x009a0204`, per-FBPA CFG1, `CSTATUS`, LMR `0x00100ce0` | No | Geometry does **not** survive |
| AON LMR shadow `0x001180f0` | No | |
| SEC2 reset PLM `0x008403C4` | Taint cleared: `0x8f` back to `0xff` | FLR is the only thing that clears it |

After a stock driver load following an unlock, only `FEAT` at `0x00823804` stays unlocked. A larger
sweep on 580.159.04 after two FLRs with no driver loaded reported UNLOCKED for `0x8200D4`,
`0x8200D8`, `0x8200E0`, `0x8200E4`, `0x8200E8`, `0x8200EC`, `0x8200F0`, `0x8200F4`, `0x8200FC`,
`0x823800`, `0x823804` and `0x823B00`, while `0x8200D0` and `0x8200DC` read `0xFFFFFF8F`,
`0x9A0008` / `0x9A000C` / `0x9A0148` / `0x9A014C` / `0x9A03F0` read `0xFFFFFF8F`, `0x9A0168` /
`0x9A0554` / `0x100B9C` read `0xFFFFFFCF`, `0x9A0BFC` read `0x00000000`, `0x100B10` / `0x100B38`
read `0xFFFFFF8F` and `0x100B84` read `0xFFFFFF88`.

The distinction drawn from that sweep: persistent PLMs sit on an always-on power island; reset PLMs
need re-unlocking every boot.

> [!NOTE]
> **Open problem: a systematic AON classification**
>
> An experiment named `nuke.sh` fully specifies the work: build a three-write ROP payload per
> cycle, patch the GSP, load the driver, FLR, kill the driver, FLR again, and read 26 candidate
> PLMs with no driver loaded, over nine cycles with a cold-boot baseline first. Candidate set:
> `0x008200D0, D4, D8, DC, E0, E4, E8, EC, F0, F4, FC`; `0x00823800`, `0x00823804`, `0x00823B00`;
> `0x009A0008, 000C, 0148, 014C, 0168, 03F0, 0554, 0BFC`; `0x00100B10, B38, B84, B9C`. The
> methodology and the candidate list are on record; the resulting classification table is not.

Because geometry does not survive an FLR, the "attack, FLR, reload a clean driver" trick that works
for the compute unlock cannot carry the memory unlock: the FLR that clears the GSP-RM damage also
clears the LMR write. That constraint is what forced the in-driver, same-load design.

---

## 6. The nine-mask table on the unreleased branches

> [!WARNING]
> **Experimental**
>
> Four unreleased branches, `Gen2`, `debug-gen2`, `far` and `deced`, extend the table from four
> entries to **nine** and loop `plmIdx < 9`. This code is not on `master`, has no shipping
> consumer, and its read-back results are not recorded in the sources for the entries that matter
> most. See [PCIe Gen2](pcie-gen2.md).

| Order | Name | Address | Value | Status |
|:---:|---|---|---|---|
| 0 | `WPR_CFG` | `0x001fa7cc` | `0xfffff0ff` | as shipping |
| 1 | `FBPA` | `0x009a0148` | `0xffffffff` | as shipping |
| 2 | `WPR` | `0x001fa7c4` | `0xffffffff` | as shipping |
| 3 | `FEAT` | `0x00823804` | `0xffffffff` | as shipping |
| 4 | `XVE` | `0x00088ff4` | `0xffffffff` | added |
| 5 | `XVE_B` | `0x00088ab4` | `0xffffffff` | added |
| 6 | `XVE_C` | `0x00088ff8` | `0xffffffff` | added |
| 7 | `FEAT2` | `0x00823b00` | `0xffffffff` | added; also the row-remapper PLM |
| 8 | `OPT_PLM` | `0x008200fc` | `0xffffffff` | added |

The three XVE masks are needed because the PCIe shadow registers are PLM-protected against host
reads: a host read returns `0xbadf5040`.

The final driverless tool used the same nine-entry list and reported all nine succeeding on the
first attempt on both GPUs in one boot, logged as
`PLM[n] NAME(addr) attempt=0 status=0xffff reg=0xffffffff`, with the first four cross-verified
byte for byte against the shipping table including the partial `0xfffff0ff`.

That result sits in tension with a separate, concrete observation:

> [!NOTE]
> **Open problem: does `FEAT2` `0x00823b00` actually open?**
>
> One researcher reported on 2026-07-22 that `0x00823b00` **rejects** the SEC2 chain, because its
> `SOURCE_ENABLE` field does not whitelist sec2-HS, and that the SEC2 ROP can only open masks
> whose `SOURCE_ENABLE` permits it. Another statement from the same period: "There are other
> primitives that allow PLM opening. Not all L3 access is equal. Regops via bar0 or via sec2
> `iowrs`." The branch code logs a per-entry read-back, so a single boot on a card would settle
> it.

### 6.1 `0x008200FC`: two names, three readings, no resolution

> [!NOTE]
> **Open problem**
>
> The register at `0x008200FC` is called `OPT_PLM` in the branch source and `FUSE_SS_PLM` in the
> clean-room tooling. **They are the same register**, and the wiki carries both aliases on one
> entry. What it reads and whether it is writable is not settled:
>
> | Date | Report |
> |---|---|
> | 2026-07-09 | "PLM = `0x000003FF` (target `0xFFFFFFFF`) ... the FUSE write fails, register appears physically read-only. Direct `writel` from host also capped at `0x3FF`." |
> | 2026-07-16 | "reads `0xffffffff` (open to all levels) across the whole Ampere lineup" |
> | 2026-07-23/24 | The nine-PLM tool includes it and reports `PLM[8] OPT_PLM(0x8200fc) attempt=0 status=0xffff reg=0xffffffff`, i.e. success |
>
> Possible resolutions: a card-state difference, the naming mix-up, or the register only being
> writable once other masks are open. Settled by reading `0x008200FC` on a cold-booted card before
> any unlock, then after each of the nine opens, on the same unit.
>
> Early ROP chains (v2 and v3) wrote `0x008200FC = 0xFFFFFFFF` and the write failed. It was
> correctly diagnosed as unnecessary: the working compute unlock uses only `FEAT_OVR_PLM`
> `0x00823804` plus SS0/SS1. **Shipping `master` does not write it.**

---

## 7. How many PLMs exist

Far more than the original estimates. The count went 1, then 3, then "5 important, probably 10 to
15", and fire logs eventually enumerated 9, 10 and 27 distinct masks in different sets. The earliest
estimate came from a public GA100 fuse and register gist written "before we knew what a PLM even
was".

A read-only survey catalogued **26 distinct PLM registers** on the 170HX and established the bit
encoding in section 2. A separate enumeration counted **27 masks** opened on one card by a community
driver's boot-time chain: `FEAT`, `FBPA`, `WPR`, `WPR_CFG`, six `XVE` masks, `FUSE_FAM_A`, ten
`FUSE_PLM` masks and six `XP_PL` masks. Confidence: medium, first-hand register-level report
corroborated by a second researcher.

Each PLM sits near the registers it protects. Opening one allows writes from all privilege levels
L0 to L3.

> [!NOTE]
> **Open problem: is a register's PLM address derivable from the register's own address?**
>
> Asked directly and never answered. The shipping set (`FEAT 0x00823804`, `FBPA 0x009a0148`,
> `WPR 0x001fa7c4`, `WPR_CFG 0x001fa7cc`) follows no obvious offset rule relative to the registers
> it guards, though the observation that they are all placed near their registers holds. Next
> step: a full PLM sweep across one aperture, to see whether masks occupy a fixed sub-range of
> each block.

> [!NOTE]
> **Open problem: where is the LMR PLM?**
>
> Nobody located the mask that gates LMR `0x00100CE0`. A candidate FBHUB table was posted
> (`0x100B10 = 0xFFFFFF8F`, `0x100B38 = 0xFFFFFF8F`, `0x100B84 = 0xFFFFFF88`,
> `0x100B9C = 0xFFFFFFCF`) but the poster disclaimed it and later reported being unable to find
> it. The shipping driver nevertheless writes LMR from the host successfully after opening
> `WPR_CFG`, `FBPA`, `WPR` and `FEAT`, so **one of those four already gates it**. A four-way
> ablation of the shipping table would identify which.

> [!NOTE]
> **Open problem: how many FBPA-side masks the memory unlock actually needs**
>
> One position held that four FBPA masks (`0x9A0148`, `0x9A014C`, `0x9A0008`, `0x9A000C`) plus LMR
> plus the reset PLM are required, with `0x100b10` proven unnecessary. A second position, argued
> forcefully, held that CFG1 and LMR alone suffice and the FBPA masks are set automatically by the
> CFG1 broadcast. The shipping code partially settles it by opening exactly **one** FBPA mask,
> `0x009a0148`, and then writing CFG1 and LMR from the host, so neither "four" nor "none" is the
> shipping answer. It cuts against a third data point: the driverless `geometry_chain()` opens
> **five** FB-geometry masks including `0x100b10`. Settled by ablating both lists one entry at a
> time on the same card.
>
> A relevant measurement narrows the question: **a single heavy-secure broadcast write to CFG1 at
> `0x009A0204` propagated to all 20 per-FBPA `CSTATUS` registers** (`0x200` to `0x800` on every
> live FBPA), so HS bypasses the FBPA masks entirely. Opening them was only ever needed for
> host-PL0 per-FBPA writes at `0x00900204 + n*0x4000`.

---

## 8. The SEC2 reset PLM, `0x008403C4`

This is a PLM in the same sense as the four above, but it is not one the unlock opens. It guards the
SEC2 Falcon's own reset control (`FALCON_ENGINE` at SEC2 + `0x3c0`), and it is the reason the
driverless tooling has a whole "clean SEC2" discipline.

| Value | State |
|---|---|
| `0xff` | Fully open. Clean idle, post-SBR. A host PL0 reset will take. |
| `0xdf` | Normal working state after a stock driver's GSP-boot teardown. Reset still permitted. |
| `0xcf` | After the driver's GSP-prime re-locks the PLMs (bit 4 clear). |
| `0x8f` | The heavy-secure exit taint. Write locked to the secure source; a PL0 reset write bounces. |

`reset_allowed = resetPLM in {0xff, 0xdf}`, and `0xdf = 0x8f | 0x50`. `0x8f` is hardware-latched at
the HS-to-NS exit transition, not written by any booter instruction. Host PL0 cannot write `0xff`,
`0xdf` or `0xffffffff` to it once it reads `0x8f`; only an HS write can lower it, and only FLR or
SBR clears it back to `0xff`. In that state `0x8f` blocks GSP-RM boot with the error pair
`0x62:0x55` and blocks a PL0-issued SEC2 `SFTRESET`.

The engine-reset gate the host-side procedure checks is `(value & 0x77) == 0x77`.

> [!NOTE]
> **The shipping driver never touches it**
>
> A grep of the shipping repository finds zero references to `0x008403c4`. The whole clean-SEC2
> discipline belongs to the driverless tooling. The in-driver path re-fires Booter Load through
> the driver's own `kflcnReset`/FWSEC sequence instead, so it never needs a host-issued SFTRESET.
> Confidence in that explanation: medium, it is inference, since nobody stated it. Settled by
> reading `0x008403C4` before and after each of the 4 to 8 PLM passes under the shipping driver.

Full detail, including the `D[0x1900] = 7` mechanism by which the shipping payload leaves it at
`0xff` anyway, is on [falcon-and-booter.md](falcon-and-booter.md#10-leaving-heavy-secure-mode-and-the-reset-plm)
and [rop-chain.md](rop-chain.md#73-why-the-exit-is-clean).

---

## 9. Why the masks are the only lever

It is worth stating what the PLM approach replaced, because the fuse evidence closes off the
alternatives cleanly. Measured across 15 Ampere cards:

| Fuse | Address | Reading | Consequence |
|---|---|---|---|
| `FUSE_QUADRO_WR_SEC` | `0x0082038C` | `0x00000001` on all 15 | The self-sealing fuse that gates the feature-override PLM at `0x823804` is **blown everywhere** |
| `FUSE_FEAT_OVR_DIS` | `0x008203F0` | `0x00000000` on all 15 | The master kill switch that would permanently lock all feature overrides is **not blown**. This is why any of this works. |
| `FUSE_EN_SW_OVERRIDE` | `0x00820040` | `0x00000000` on 170HX, all three A100 SKUs and Drive A100; `0x00000001` on every consumer and ES part | The CTRL_OPT software fuse-override path is disabled at the fuse level, so the 25-entry CTRL_OPT table in the unsigned FwSec tail is inert on these cards |
| `FUSE_OPT_SECURE_GSP` | `0x0082074C` | `0x00000001` on all 15 | GSP debug is disabled and GSP accepts only signed production firmware, which is why the unlock must go through the signature-buffer route |
| `FUSE_DIS_SW_OVR` | `0x00820084` | `0x00000001` on all 15 | Not HS-writable: probed 2026-07-27 on an 8 GB card with two live controls and the value bounced. What is still open is narrower: whether `DIS_SW_OVR = 1` actually *locks* `FUSE_EN_SW_OVERRIDE`, given it also reads `1` on consumer cards where overrides work |
| `FUSECTRL` | `0x00820000` | `0xe0040000` on all 15 | |
| `FEATURE_OVERRIDE_QUADRO` | `0x00823808` | per-die and unexplained: `0x00100183` (stock PLM range scan), `0x00000081` (**post-unlock** probe, not a stock reading), `0x00000181` / `0x00000182` (two physical 170HX units), `0x01000282` (A100 80 GB) | Read only. Why the value differs across dumps is an open question; see the [register reference](register-reference.md) |

The 2026-05-31 verdict that host-only register writes are "CONFIRMED DEAD" remains entirely valid as
a diagnosis: `FEAT_OVR_PLM` and `FEAT_OVR_ECC_PLM` both at `0xffffff8f` (level 3 only),
`FUSE_QUADRO_WR_SEC = 1` sealing that mask, `FUSE_EN_SW_OVERRIDE = 0` disabling the CTRL_OPT
override table, and `FECS_FEAT_OVERRIDE` reads returning `0xbadf5040`. What that document lacked was
a way to reach level 3, and it predicted correctly that the answer would be "needs Falcon HS".

See [fuses and OTP](../hardware/fuses-and-otp.md) for the full fuse picture.

> [!NOTE]
> **A negative result worth keeping**
>
> Running the LMR and CFG1 writes from a non-secure Hello-World ucode over the priv bus was tried
> and did not work, exactly as NVIDIA's own Falcon-Security documentation predicts: NS restricts
> register and physical-memory access, and the masks on these registers demand the highest level.
> A later driverless probe that appeared to confirm NS cannot reach external BAR0 at all was
> **withdrawn by its own author**, because the failing test used a `D[0x14000000]` window that
> aliased the Falcon's local DMEM and therefore never probed BAR0. No replacement measurement was
> reported.

> [!NOTE]
> **Open problem: can PL0 reach the geometry registers once the mask is open?**
>
> The stake is large. Because the SS0/SS1 mask at `0x00823804` is always-on and stays open through
> FLR, if host PL0 can reach CFG1 at `0x00900204 + n*0x4000`, LMR `0x00100CE0` and SS0/SS1 after a
> single one-time HS open, then a permanent path exists with no further heavy-secure work. Next
> step: re-run the withdrawn probe with a correctly mapped external aperture window and check each
> register individually.

---

## 10. Verifying a card by hand

The four values to read back after an unlock, and what a correct card shows:

```text
0x001fa7cc  ->  0xfffff0ff     WPR_CFG   (NOT 0xffffffff)
0x009a0148  ->  0xffffffff     FBPA
0x001fa7c4  ->  0xffffffff     WPR
0x00823804  ->  0xffffffff     FEAT
```

And the four unlock writes those masks enable:

```text
0x0082381c  ->  0x88888888     SS0
0x00823820  ->  0x00000008     SS1
0x009a0204  ->  0x02779000  (8 GB card)  /  0x02669000  (10 GB card)
0x00100ce0  ->  0x0000020b  (8 GB card)  /  0x0000028a  (10 GB card)
```

Note that the last two do not survive an FLR or a power cycle, and that only `0x00823804`,
`0x0082381c` and `0x00823820` do. See [verify](../procedures/verify.md).

---

## Related pages

- [The SEC2 Falcon and the Booter Load microcode](falcon-and-booter.md)
- [The ROP chain](rop-chain.md)
- [Memory geometry](memory-geometry.md) and [compute throttle](compute-throttle.md)
- [Driver patches](driver-patches.md)
- [PCIe Gen2](pcie-gen2.md)
- [Fuses and OTP](../hardware/fuses-and-otp.md)
- [Register reference](register-reference.md) and the [register index](../appendix/register-index.md)
- [Glossary](../start/glossary.md)
