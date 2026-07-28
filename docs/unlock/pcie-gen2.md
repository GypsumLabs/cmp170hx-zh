# PCIe Gen2 software unlock

**What this page covers**: the complete register mechanism that takes a CMP 170HX from PCIe Gen1
(2.5 GT/s) to Gen2 (5.0 GT/s) with no hardware modification, how it is split between patches
`0007` and `0008`, the retrain procedure, the IOMMU dependency, the modprobe registry keys, and
the four-branch lineage the work lives on. For the hardware it is defeating, see
[PCIe subsystem](../hardware/pcie-subsystem.md).

!!! warning "Experimental: this is not in the shipping release"
    Shipping `master` contains patches `0001` through `0006` only, has no `pcie:` block in
    `common/constants.yaml`, and its "What Gets Unlocked" table has exactly three rows (compute,
    memory geometry, persistence) with no PCIe row. A case-insensitive grep of master's
    `install.sh`, `remove.sh`, `README.md` and `driver/build.sh` for
    `gen2|gen 2|pcie|iommu|retrain|RMPcieLinkSpeed` returns **zero hits**. All Gen2 code lives on
    four of the twelve unreleased branches. Nothing on this page has been merged, and one
    contributor described the result as "like a script spamming stuff and hoping it sticks". A
    dedicated issue channel was opened five hours after the announcement.

## The result, up front

Gen2 doubles link **speed**. It does not touch link **width**, and no code in any branch reads or
writes a width field. A Gen2-patched card that has not been soldered runs at Gen2 x4.

| | Stock | After the Gen2 branch |
|---|---|---|
| `LnkCap` | `0x00456101` (Gen1 max, x16) | `0x00456102` (Gen2 max, x16) |
| `LnkCap2` supported speeds | `0x00000002` (2.5 GT/s only) | `0x00000006` (2.5 and 5.0 GT/s) |
| `LnkCtl2` target | `0x0000` | `0x0002` |
| `LnkSta` | `0x1041` (Gen1, x4) | `0x1042` (Gen2, x4) |
| `LnkSta2` | `0x0000` | `0x0001` or `0x0000`, rig dependent |
| `DevCap2` / `DevCtl2` | `0x00070803` / `0x1400` | `0x00070813` / `0x0400` (one rig `0x7410`) |
| `nvidia-smi` cur / max / width | 1, 1, 4 | 2, 2, 4 |
| Host bandwidth | ~0.85 GB/s | ~1.71 GB/s |
| AER correctable / nonfatal / fatal | 0 / 0 / 0 | 0 / 0 / 0 |

Three independent rigs posted full machine-generated dumps of the Gen2 state: driver 610.43.02 on
kernel 5.15.0-186-generic, driver 610.43.03 on kernel 6.12.54-Unraid with two cards, and driver
610.43.03 on kernel 6.12.0-hiveos with two cards.

## Where the code lives

| Branch | `0007-pcie-gen2.patch` | `0008-pcie-gen2-probe-retrain.patch` | `tools/retrain.sh` | IOMMU handling | `RMPcieLinkSpeed` |
|---|---|---|---|---|---|
| `master` (shipping) | absent | absent | absent | absent | absent |
| `debug-gen2` | yes (malformed hunk headers) | absent | installed, auto-discovering BDFs, plus `cmpretrain.service` | none | `0x1` |
| `Gen2` | yes (headers fixed) | yes | present but never installed, BDFs hard-coded | automatic | `0x1` |
| `far` | yes | yes | present but never installed, BDFs hard-coded | automatic | `0x2` |
| `deced` | yes | yes | present but never installed, BDFs auto-discovered again | automatic | `0x2` |

### Branch lineage

```text
# dates in committer-local time (-0700)
6621ffc  Effort on PCIe Gen 2                               2026-07-22
4bd6d4d  Fixed malformed patch                              2026-07-22
a9b2470  Delete requirements.txt
746d9f7  PCIe Gen 2 works!                                  2026-07-23   <- tip of debug-gen2
0901346  Fix malformed 0007-pcie-gen2 hunk line counts      2026-07-24
d88af88  Potential fix                                      2026-07-24
146da6f  Correct retraining                                 2026-07-24
2f27474  Gen2 + multiple-card support                       2026-07-24
7ea2c4f / 1605219 / bed923f / a14176b / e95784c
6a85e6c  IOMMU enablement as part of install script         2026-07-24
a4de322  (merge)                                            2026-07-26   <- tip of Gen2
8854d3e  Remove clamp link to Gen1                          2026-07-26   <- tip of far
2326599  Stupid mistake - it appears to be hardcoded        2026-07-27   <- tip of deced
```

Roughly twenty hours separated "advertises Gen2 but will not retrain" (`Effort on PCIe Gen 2`,
2026-07-22 22:02:43 -0700, that is 2026-07-23 05:02 UTC) from "trains" (`PCIe Gen 2 works!`,
2026-07-23 18:21:35 -0700, that is 2026-07-24 01:21 UTC). The result was
announced publicly on 2026-07-24 at 00:59 and reproduced within hours by several independent
testers on distinct hardware.

`far` is `Gen2` plus exactly one commit whose only content change in the entire tree is a single
character in one line. `deced` is `far` plus one commit that re-adds BDF auto-discovery to a
script the installer deletes.

!!! note "Superseded: the Gen1 hardware-wall conclusion"
    Through 2026-07-19 the maintainers stated flatly that "Gen 2 hasn't worked for anybody". A
    field manual dated 2026-07-24 concluded that all four layers of the lock (runtime register
    writes, register semantics, durable firmware, silicon fuse) were empirically closed, verified
    across a 4032-run offline firmware fuzz sweep (126 function-register pairs drawn from 66
    functions, each swept over 32 single-bit values) and on-silicon direct-write probing. Its own section 6 names the gap: "The
    full community Gen2 sequence ... as a single combined write was not run: every component is
    individually proven inert, so it is a low-odds combination." The low-odds combination worked.
    The Gen3 half of that conclusion still stands. See
    [Gen3 and Gen4](../frontier/pcie-gen3-gen4.md).

## Mechanism

The unlock has three phases. Phase A needs SEC2 Booter privilege; phase B needs only an open PLM;
phase C needs the upstream bridge and cannot be done from inside the driver's GSP hook at all.

```text
Phase A  25 Booter-routed writes   (0007, kernel_gsp.c)      opens PLMs, sets XP3G overrides
Phase B   6 plain BAR0 writes      (0007, in-GSP hunk)       clears DIS_G2, sets MAX_RATE
Phase C   root-port retrain        (0008 / retrain.sh / hammer)  actually changes the link speed
```

### Injection point

Patch `0007` injects its entire register block into
`src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c` at `@@ -4942,6 +4942,260 @@`, immediately after the
existing `devId` print and immediately **before**
`plmStatus = kgspSec2PostblTimingRebuildStockSignature(pGpu, pKernelGsp);`. It therefore runs
inside the SEC2 post-bootloader unlock window, while the PLMs are still open and the crafted
Falcon signature payload still provides an arbitrary BAR0 write primitive through Booter Load.
That is the same privilege escalation the memory and compute unlocks use; see
[Falcon and Booter](falcon-and-booter.md) and [how it works](how-it-works.md).

### Phase A: the 23-entry `xp3gTable`

Each entry is an `{address, value}` pair pushed through the Booter payload primitive. Per entry
the code restores WPR2 lo and hi (`GPU_REG_WR32(pGpu, 0x001fa824U, wpr2Lo)` and
`0x001fa828U, wpr2Hi`), calls `kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp, addr, value)`,
calls `kgspExecuteBooterLoad_HAL(...)`, reads the target back, and retries once (`xattempt < 2`),
printing `SEC2_DEBUG: PCIe xp3g booter FAILED to set <name>` on failure.

| # | Address | Name | Value | Purpose |
|---|---|---|---|---|
| 1 | `0x0008e1b0` | `XP3G_PLM` | `0xffffffff` | PLM open |
| 2 | `0x0008e1b4` | `XP3G_PLM4` | `0xffffffff` | PLM open |
| 3 | `0x0008e1b8` | `XP3G_PLM8` | `0xffffffff` | PLM open |
| 4 | `0x0008e1bc` | `XP3G_PLMC` | `0xffffffff` | PLM open |
| 5 | `0x00088fe8` | `XVE_D0` | `0xffffffff` | PLM open |
| 6 | `0x00088fec` | `XVE_D4` | `0xffffffff` | PLM open |
| 7 | `0x00088ff0` | `XVE_D8` | `0xffffffff` | PLM open |
| 8-17 | `0x008200d0`, `d4`, `d8`, `dc`, `e0`, `e4`, `e8`, `ec`, `f0`, `f4` | `OPTB_D0` .. `OPTB_F4` (**10** registers) | `0xffffffff` | PLM open |
| 18 | `0x00823800` | `FEAT_OVR_ECC_PLM` | `0xffffffff` | PLM open |
| 19 | `0x0082057c` | `OPT_GEN23` | `0x00000000` | Value write, **always fails** |
| 20 | `0x0008e120` | `XP3G_VAL0` | `0x00000000` | Value write |
| 21 | `0x0008e110` | `XP3G_OVR0` | `0x00000001` | Enable, slot 0 |
| 22 | `0x0008e12c` | `XP3G_VAL3` | `0x00200000` | Value write, exported as `opt_magic_a100` |
| 23 | `0x0008e11c` | `XP3G_OVR3` | `0x00000004` | Enable, slot 3 |

Eighteen PLM opens plus five value writes. Two more registers get the identical two-attempt Booter
treatment **outside** the table, giving **25 Booter-routed writes** in total:

| Address | Name | Operation | On-silicon result |
|---|---|---|---|
| `0x0008860c` | `VSEC_DEVICE` | set bit 0 (`|= 1 << 0`) | **Fails**: `pre=0x00000800 want=0x00000801`, readback `0x00000800` twice, then `PCIe VSEC_DEVICE booter FAILED` |
| `0x0008841c` | `PRIV_MISC_1` | set bits 11 and 13, clear bits 12 and 14 | **Succeeds** on the first attempt: `0x20340500` becomes `0x20342d00`, and still reads `0x20342d00` after the real BooterLoad |

The XP3G override block is three parallel four-dword arrays: status base `0x0008e100`,
override-enable base `0x0008e110`, value base `0x0008e120`, with slot *n* at base + 4*n*, so slot 3
is base + `0xC`. The value is always written before the enable so the override never latches stale
data, and the enable encodings are one-hot per slot (`0x1` for slot 0, `0x4` for slot 3).

!!! info "Two entries fail and Gen2 works anyway"
    `OPT_GEN23` is a pure OTP fuse-sense reflection with no write port; every attempt from every
    privilege level returns `status=0xffff rd=0x00000001`. `VSEC_DEVICE` also fails. The shipped
    patch still attempts both, still fails at both, and the link still trains at Gen2. The working
    levers are `CYA_0`, `LINK_CONFIG_0`, the XP3G overrides and `PRIV_MISC_1`.

!!! note "Counting errors in secondary documentation"
    Three published counts are wrong and are checkable directly against the patch: the OPTB run is
    **ten** registers (`D0, D4, D8, DC, E0, E4, E8, EC, F0, F4`), not eleven and not nine; the
    table opens **18** PLMs inside a **23**-entry table, not 22; and the late hunk sits in
    `kernel_gsp_tu102.c` immediately after Booter Load returns, which is *before* GSP-RM is
    running, not after.

### Phase B: plain BAR0 writes

Once the XVE PLMs `0x00088fe8` / `fec` / `ff0` are open, ordinary `GPU_REG_WR32` writes land. Before
that, the priv ring drops them; a probe of `0x08c044` returned the priv-masked sentinel
`0xbadf5040` and was skipped, while `0x0880a8` wrote and read back cleanly.

| Register | Address | Operation | Notes |
|---|---|---|---|
| `VSEC_HIERARCHY` | `0x00088610` | `hier = (hier & ~(1U << 12)) | (1U << 0)` | Bit 12 gates `PRIV_MISC_1` reprogram; live value before modification `0x00001001` |
| `LINK_CTRL_2` | `0x000880a8` | `lc2 = (lc2 & ~0xFU) | 0x2`, then `lc2 = (lc2 & ~0x000F0000U) | 0x000F0000U` | Target Link Speed = 2 in `[3:0]`, `0xF` in `[19:16]` |
| `CYA_0` | `0x0008c2c0` | `cya0 = cya0 & ~(1U << 2)` | Clears the `DIS_G2` chicken bit |
| `LINK_CONFIG_0` | `0x0008c040` | `linkCfg = (linkCfg & ~0x000C0000U) | (0x2U << 18)` | `MAX_RATE` field `[19:18]` set to 2 (5.0 GT/s). CMP stock reads `0x800C4C00`, SPEED = 3 |
| `PL_LINK_RATE` | `0x0008c1c0` | `= 0x00240036` | See caveat below |
| LTSSM / `XVE_OVR` | `0x0008872c` | `= 0x00000006` | Log line: `SEC2_DEBUG: PCIe XVE_OVR@8872c=0x%08x; skip mid-boot retrain` |

`CYA_0` bit 2 is cleared in **four** independent places: the in-GSP site in `kernel_gsp.c`, the
late site in `kernel_gsp_tu102.c`, `tools/retrain.sh`, and `nv_cmp170hx_retrain_gen2()` in patch
`0008`. `retrain.sh` treats a still-set bit 2 as a hard abort (`retrain: DIS_G2 still set; skip`).

`PRIV_MISC_1` is a paired enable and value CYA override. The patch macros are
`PCIE_GEN2_PRIV_MISC_1_GEN2_EN = ((1U << 11) | (1U << 13))` and
`PCIE_GEN2_PRIV_MISC_1_GEN2_VAL = ((1U << 12) | (1U << 14))`, with the requested value
`(misc1 | GEN2_EN) & ~GEN2_VAL`: assert both override enables, drive both value bits to zero.

!!! note "`PL_LINK_RATE 0x00240036` is not required"
    The write exists only in `0007`'s in-GSP path. Neither `tools/retrain.sh` nor patch `0008`
    touches `0x0008c1c0`, and both of those produce Gen2. The A100 forced-generation sweep also
    showed the whole XP_PL family (`0x8C044`, `0x8C048`, `0x8C04C`) reading `0xbadf5040` at every
    generation on the reference card, so the family was never validated against a working link.
    What the individual bits of `0x00240036` encode is documented nowhere. Naming caution: the
    address is `#define`d `PCIE_GEN2_LTSSM_ADDR` for `0x0008872c` while the log string calls it
    `XVE_OVR`; that ambiguity is in the source itself.

### The late hunk

Patch `0007` has a second hunk in
`src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c` at `@@ -611,6 +611,44 @@`. It
re-applies four writes as plain BAR0 accesses with **no** Booter: `PRIV_MISC_1`, `CYA_0` bit 2
clear, `LINK_CONFIG_0` `MAX_RATE = 2`, and `0x0008872c = 6`. Its log lines are suffixed `late`.
It is gated on:

```c
NvU32 lateDevId = pGpu->idInfo.PCIDeviceID >> 16;
if ((lateDevId == 0x20C2 || lateDevId == 0x2082) && status == NV_OK)
```

A `10de:20b0` card therefore receives no Gen2 treatment at all, matching the device-ID handling in
the rest of the project. See [identify your card](../start/identify-your-card.md).

### Named addresses defined by `0007`

```c
#define PCIE_GEN2_LINK_CAP_ADDR        0x00088084U
#define PCIE_GEN2_LINK_CAP2_ADDR       0x000880a4U
#define PCIE_GEN2_LINK_CTRL_2_ADDR     0x000880a8U
#define PCIE_GEN2_LINK_CTRL_STATUS_ADDR 0x00088088U
#define PCIE_GEN2_PL_LINK_RATE_ADDR    0x0008c1c0U
#define PCIE_GEN2_LTSSM_ADDR           0x0008872cU
#define PCIE_GEN2_VSEC_DEVICE_ADDR     0x0008860cU
#define PCIE_GEN2_VSEC_HIERARCHY_ADDR  0x00088610U
#define PCIE_GEN2_XP3G_OVR_BASE        0x0008e110U
#define PCIE_GEN2_XP3G_VAL_BASE        0x0008e120U
#define PCIE_GEN2_XP3G_STATUS_BASE     0x0008e100U
#define PCIE_GEN2_OPT_GEN23_ADDR       0x0082057cU
#define PCIE_GEN2_OPT_GEN3_ADDR        0x00820580U
#define PCIE_GEN2_OPT_MAGIC_ADDR       0x00820520U
#define PCIE_GEN2_PRIV_MISC_1_ADDR     0x0008841cU
#define PCIE_LINK_SPEED_OF(stat)       (((stat) >> 16) & 0xFU)
```

Two of the values are `const NvU32` declarations rather than `#define`s:

```c
const NvU32 PCIE_GEN2_LINK_SPEED = 0x00000002U;
const NvU32 PCIE_GEN2_PL_LINK_RATE_VALUE = 0x00240036U;
```

`OPT_GEN3` and `OPT_MAGIC` are read and logged (inside `NV_PRINTF` argument lists with format
`OPT=%08x/%08x/%08x` for GEN23 / GEN3 / MAGIC) but **never written**. The only fuse-option
register the code attempts to write is `OPT_GEN23`, and that write fails. No code path anywhere
requests a target link speed above 2.

### The PLM table grows from four to nine

Shipping master arms four PLM entries. The Gen2-family branches (`Gen2`, `debug-gen2`, `far`,
`deced`, all four byte-identical in this respect) add five more to
`0001-sec2-postbl-plm-ss-cfg.patch`, giving nine:

| Index | Address | Name | Target value | On shipping master? |
|---|---|---|---|---|
| 0 | `0x001fa7cc` | `WPR_CFG` | `0xfffff0ff` | yes |
| 1 | `0x009a0148` | `FBPA` | `0xffffffff` | yes |
| 2 | `0x001fa7c4` | `WPR` | `0xffffffff` | yes |
| 3 | `0x00823804` | `FEAT` | `0xffffffff` | yes |
| 4 | `0x00088ff4` | `XVE` | `0xffffffff` | Gen2 family only |
| 5 | `0x00088ab4` | `XVE_B` | `0xffffffff` | Gen2 family only |
| 6 | `0x00088ff8` | `XVE_C` | `0xffffffff` | Gen2 family only |
| 7 | `0x00823b00` | `FEAT2` | `0xffffffff` | Gen2 family only |
| 8 | `0x008200fc` | `OPT_PLM` (also called `FUSE_SS_PLM` in clean-room tooling) | `0xffffffff` | Gen2 family only |

Each entry gets at most two attempts, with WPR2 lo and hi re-armed before every attempt. All nine
read back `0xffffffff` except `WPR_CFG` at `0xfffff0ff`, which is the correct exception. Full
detail on [privilege level masks](privilege-level-masks.md).

### `constants.yaml`

The Gen2 branches add a `pcie:` block with exactly these keys:

```yaml
pcie:
  target_gen: 2
  link_speed_gen2: "0x2"
  xve_link_control_status: "0x00088088"
  xve_link_control_2: "0x000880a8"
  pl_link_rate_addr: "0x0008c1c0"
  pl_link_rate_value: "0x00240036"
  vsec_hierarchy_addr: "0x00088610"
  vsec_device_addr: "0x0008860c"
  xp_fuse_override_base: "0x0008e110"
  xp_fuse_override_val_base: "0x0008e120"
  opt_gen23_addr: "0x0082057c"
  opt_magic_a100: "0x00200000"
```

Five registers central to the mechanism are **absent** from the yaml: `CYA_0` `0x0008c2c0`,
`LINK_CONFIG_0` `0x0008c040`, `PRIV_MISC_1` `0x0008841c`, `LINK_CAP` `0x00088084` and
`0x0008872c`. The same commit also dropped the `comment:` lines from the 8gb and 10gb profile
blocks. Shipping master has no `pcie:` block at all.

## Patch 0007 versus patch 0008

They are **complementary, not alternatives**.

| | `0007-pcie-gen2.patch` | `0008-pcie-gen2-probe-retrain.patch` |
|---|---|---|
| Files touched | `kernel_gsp.c`, `kernel_gsp_tu102.c` | `kernel-open/nvidia/nv.c` |
| Privilege needed | SEC2 Booter (to write PLM-protected registers) | None beyond three already-unlocked BAR0 registers and standard PCIe capability access |
| What it achieves | Raises `LINK_CAP` / `LinkCap2` to Gen2 | Triggers the actual link retrain from the upstream bridge |
| What it cannot do | Retrain (explicitly declines: "skip mid-boot retrain") | Raise `LINK_CAP` by itself |
| Branches | `debug-gen2`, `Gen2`, `far`, `deced` | `Gen2`, `far`, `deced` |
| Hunk sizes | 260 lines (254 added) and 44 lines (38 added) | adds includes plus one function and one call site |

`driver/build.sh` applies them in filename order:

```bash
patches=("${PATCH_DIR}"/*.patch)
for p in "${patches[@]}"; do patch -p1 < "${p}"; done
```

### Patch 0008 in detail

`nv_cmp170hx_retrain_gen2()` is added to `kernel-open/nvidia/nv.c` along with includes
`<linux/delay.h>`, `<linux/io.h>`, `<linux/pci.h>` and `<uapi/linux/pci_regs.h>`. The call is
inserted immediately after `nv->flags |= NV_FLAG_PERSISTENT_SW_STATE;` and before
`(void)rm_get_gpu_uuid_raw(sp, nv);`.

```text
return unless gpu->device is 0x20c2 or 0x2082
pci_upstream_bridge(gpu)                 -> bail if NULL
ioremap(pci_resource_start(gpu, 0), 0x90000)   /* 576 KiB, just enough to reach 0x8c2c0 */
clear CYA_0 bit 2            at BAR0 0x8c2c0
set MAX_RATE = 2             at BAR0 0x8c040   ((v & ~0x000c0000) | (2 << 18))
write 0x00000006             to  BAR0 0x8872c, read back to flush posted writes
iounmap
msleep(50)
set PCI_EXP_LNKCTL2_TLS_5_0GT on BOTH the GPU and the upstream bridge
set PCI_EXP_LNKCTL_RL         on the UPSTREAM BRIDGE
poll LnkSta 20 times at msleep(100)      /* 2.05 s worst case */
```

!!! danger "0008's success test can never pass on this card"
    The predicate is:

    ```c
    if (!ret && (link_status & PCI_EXP_LNKSTA_DLLLA) &&
        ((link_status & PCI_EXP_LNKSTA_CLS) >= PCI_EXP_LNKSTA_CLS_5_0GB))
    ```

    `PCI_EXP_LNKSTA_DLLLA` is bit 13 (`0x2000`). A Gen2-trained 170HX reads `LnkSta = 0x1042`, and
    `0x1042 & 0x2000 = 0`, so the predicate fails even though `0x1042 & 0xF = 2` means 5.0 GT/s.
    The bit can **never** be set on this port: DLL Link Active Reporting Capable is `LnkCap` bit
    20, and the GPU's `LnkCap = 0x00456102` has bit 20 clear. The upstream root port does report it
    (`LnkCap 0x007b7905`, `LnkSta 0x7042`), but `0008` reads `LnkSta` from the **GPU**.

    Consequence: on every working Gen2 170HX, patch `0008` burns the full 20 × 100 ms and then
    prints `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)` at
    `NV_DBG_ERRORS`. The message is a false negative. It has already misled at least one downstream
    analysis into concluding `0008` "runs too late".

The log-level convention compounds it. In `0008`, success prints at `NV_DBG_INFO` while all four
failure paths print at `NV_DBG_ERRORS`; `0007` by contrast emits even routine pre and post dumps at
`LEVEL_ERROR` so they survive default dmesg filtering. **Do not read dmesg to decide whether Gen2
worked.** Read `nvidia-smi --query-gpu=pcie.link.gen.current` or `lspci` `LnkSta`.

## The retrain

The retrain is the step that actually changes the link speed, and it must be driven from the
**upstream bridge's** Retrain Link bit, never from the GPU. Bit 5 (`0x20`) of Link Control is only
meaningful on a downstream port. Every implementation in the corpus does it this way:

| Implementation | Retrain call |
|---|---|
| `debug-gen2` `retrain.sh` | `pci_write(up, cap + 0x10, 2, ctl | 0x20)` |
| `Gen2` / `far` / `deced` `retrain.sh` | `setpci -s <UP> CAP_EXP+10.w=<cur|0x20>` |
| Patch `0008` | `pcie_capability_write_word(upstream, PCI_EXP_LNKCTL, upstream_ctl | PCI_EXP_LNKCTL_RL)` |
| Independent hammer script | `setpci -s "${rp}" "CAP_EXP+0x10.w=...|0x20"` |

`0008` bails with `CMP Gen2: no upstream PCIe bridge; skipping link retrain` when
`pci_upstream_bridge()` returns NULL, and the `debug-gen2` systemd unit is literally named
`Description=CMP 170HX PCIe Gen2 upstream soft retrain`.

### Manual host-side procedure

```bash
# 1. find the upstream root port for your GPU
lspci -tv

# 2. set Target Link Speed = 2 (Gen2) in LNKCTL2 at CAP_EXP+0x30
sudo setpci -s 64:00.0 CAP_EXP+0x30.L=2

# 3. set the Retrain Link bit (0x20) in LNKCTL at CAP_EXP+0x10, preserving current bits
sudo setpci -s 64:00.0 CAP_EXP+0x10.w=$(( LnkCtl | 0x20 ))

# 4. verify from the GPU
sudo lspci -vv -s <gpu_bdf> | grep -E "LnkCap:|LnkSta:"
```

The `CAP_EXP+0x30.L=0x4` form targets Gen4 and has never succeeded on this card. Kernel 6.x and
later contains `pcie_set_target_speed()` in the bwctrl service, but it is **not exported**, so the
LNKCTL2 and LNKCTL writes must be issued by hand.

### The `retrain.sh` sequence

`Correct retraining` (`146da6f`) reordered the script relative to `debug-gen2`, which did the BAR0
writes first:

```text
pre-state dump
  -> setpci -s <UP> CAP_EXP+30.w=<(cur & ~0xF) | 0x2>   (LNKCTL2 TLS = 2, on UP and GPU)
  -> sleep 0.2
  -> reopen BAR0, clear DIS_G2 at 0x8C2C0, set MAX_RATE = 2 at 0x8C040
  -> sleep 0.05
  -> verify
  -> setpci -s <UP> CAP_EXP+10.w=<cur | 0x20>            (Retrain Link)
  -> sleep 2.0                                            (up from 1.5 in debug-gen2)
  -> read CAP_EXP+12.w, print "retrain: speed_after=<sta & 0xF>"
```

Early-exit preconditions: `nvidia-smi` `memory.total` empty or `[N/A]`;
`pcie.link.gen.current` already 2; `pcie.link.gen.max` not in {2, 3, 4}; BAR0 or CYA reading
`0xFFFFFFFF`; `DIS_G2` still set; `LINK_CAP` speed nibble below 2; and, after the BAR0 writes,
"not alive or DIS_G2 set or mx != 2". Only the checks inside the Python block print a skip line.
The first three run in the shell wrapper and are bare `exit 0` with no output, so a completely
silent run is normal and is not evidence that the script failed to start.

Every implementation waits for the driver to come up first. `debug-gen2` used systemd
`ExecStartPre=/bin/sleep 15` plus `for _ in $(seq 1 60); do nvidia-smi -L && break; sleep 1; done`.
`Gen2`, `far` and `deced` poll `for i in $(seq 1 120)` on both `resource0` existing and
`nvidia-smi -L`. `0008` runs inside probe so it needs only `msleep(50)` plus 20 × `msleep(100)`.

!!! note "Superseded: the userspace systemd retrain"
    `debug-gen2` shipped `/usr/local/sbin/retrain.sh` plus `cmpretrain.service`
    (`After=multi-user.target`, `Type=oneshot`, `ExecStartPre=/bin/sleep 15`,
    `RemainAfterExit=yes`, `WantedBy=multi-user.target`). On 2026-07-24 it was root-caused as
    retraining only the first GPU **and** as a source of random card crashes, because it operates
    while the driver is actively accessing the card. Symptom before the fix: "Gen2 just apply the
    first card....2nd card still running at Gen1". Patch `0008` replaced it. From the `Gen2` branch
    onward `install.sh` step 5b actively **uninstalls** it:

    ```bash
    for legacy_unit in cmpretrain.service cmp-gen2-retrain.service; do
        systemctl disable --now "$legacy_unit"; systemctl reset-failed "$legacy_unit"
    done
    rm -f /etc/systemd/system/cmpretrain.service /etc/systemd/system/cmp-gen2-retrain.service \
          /usr/local/sbin/retrain.sh /usr/local/sbin/cmp-gen2-retrain.sh
    systemctl daemon-reload
    ```

    Three independent testers reported `0008` fixing multi-card Gen2 and eliminating the crashes,
    on 2× 10 GB, 3× 10 GB and mixed 8 GB plus 10 GB systems. See [multi-GPU](../procedures/multi-gpu.md).

!!! warning "Experimental: `tools/retrain.sh` is dead code on Gen2, far and deced"
    Those branches ship a script their own installer deletes from `/usr/local/sbin`. Grepping their
    installers for `retrain` returns only the removal block. There is no
    `install -m 0755 tools/retrain.sh` anywhere. To use it you must run it by hand as root. Worse,
    on `Gen2` and `far` the script hard-codes one developer's PCI addresses
    (`SYS=/sys/bus/pci/devices/0000:0a:00.0`, `GPU, UP = "0a:00.0", "09:01.0"`,
    `PATH = "/sys/bus/pci/devices/0000:0a:00.0/resource0"`) and silently targets the wrong device
    on any other machine. This was a regression: `debug-gen2` auto-discovered both. `deced`
    (`2326599`) restored discovery with

    ```bash
    find_gpu_bdf() {
      for id in 10de:20c2 10de:2082; do
        lspci -d "$id" -D 2>/dev/null | head -1 | cut -d' ' -f1
      done | head -1
    }
    UP_BDF="$(basename "$(dirname "$(readlink -f "/sys/bus/pci/devices/$GPU_BDF")")")"
    ```

    and re-polls `find_gpu_bdf` on each of the 120 wait iterations. Script line counts:
    `debug-gen2` 138, `Gen2` 106, `far` 106, `deced` 115.

### The independent early-boot hammer

A separate community setup script takes the opposite approach and runs as early as possible,
because "late is the same as never". Its model: while `0007`'s `CYA_0`, `LINK_CONFIG_0` and
`VSEC_DEVICE` writes hold, the endpoint **transiently** advertises `LnkCap2 = 0x06`; the window
opens roughly 8 to 14 s after boot during GSP bootstrap and closes when RM clears `VSEC_DEVICE`
bit 0. The stated key insight is that the capability does not need to persist, because a link that
trains at Gen2 while the window is open stays trained after it closes.

Implementation: `/usr/local/sbin/cmp170hx-gen2-hammer` loops `MAX_ITER=600` at `SLEEP_S=0.05`
(30 s of coverage), setting the LnkCtl2 target to Gen2 on both ends and toggling the **root port's**
Retrain bit each pass. It typically succeeds around iteration 30, about 1.5 s in. Its unit uses
`DefaultDependencies=no`, `After=sysinit.target`, `Before=multi-user.target`, `Type=oneshot`,
`TimeoutStartSec=120`, `WantedBy=sysinit.target`, and it sanity-checks the installed driver with
`strings /lib/modules/$(uname -r)/updates/cmpunlocker/nvidia.ko | grep -q 'SEC2_DEBUG: PCIe'`,
logging to `/var/log/cmp170hx-gen2.log`.

!!! question "Open problem: is the Gen2 window transient?"
    The hammer's transient-window model is contradicted by an archived steady-state dump (kernel
    6.12.0-hiveos, driver 610.43.03, two `10de:20c2` cards) which reads `LnkCap2 = 0x00000006` and
    `LnkCap = 0x00456102` **after boot has completed**. `0007`'s own dmesg also shows the
    `VSEC_DEVICE` write failing, so the bit RM is supposed to clear may never have been set. Both
    sides are first-hand. What would settle it: a timestamped poll of
    `setpci -s <bdf> CAP_EXP+0x2c.l` every 100 ms from early boot through 60 s, on both an AMD
    CachyOS host and a HiveOS host. Until then, treat the transient window as one host's
    observation, not a property of the card.

## Modprobe registry keys

`install.sh` step 5b writes `/etc/modprobe.d/cmp-pcie-gen2.conf`:

```text
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x1"
```

The clean-room tooling documents the key as load-bearing, in a docstring dated and marked
confirmed on-card 2026-07-24: `"REQUIRES: driver loaded with
NVreg_RegistryDwords=\"RmForceEnableGen2=1;RMPcieLinkSpeed=0x1\" (else the RM re-clamps Gen1 every
retrain)."` Separately, the same setup script lists `RmForceEnableGen2` among things "tested and
confirmed unnecessary", and nobody has shown that key doing anything on its own.

!!! question "Open problem: `RMPcieLinkSpeed=0x1` or `0x2`?"
    Both spellings ship. `debug-gen2` (`install.sh:191`) and `Gen2` (`install.sh:280`) write `0x1`;
    `far` (`install.sh:280`) and `deced` (`install.sh:280`) write `0x2`, introduced by commit
    `8854d3e` "Remove clamp link to Gen1". Note that the `Gen2` branch, the one whose README claims
    Gen2 "Working ✓", ships `0x1`, and the on-card confirmation was made with `0x1`. Both readings
    are internally coherent depending on whether the key means "clamp to gen N" or "enable up to
    gen N". No A/B boot test exists. Neither value should be presented as canonical. What would
    settle it: boot the same card and kernel three times, with no key, with `0x1`, and with `0x2`,
    and post `LnkSta` each time. Cheap and decisive.

## IOMMU enablement

From commit `6a85e6c` (2026-07-24) onward the installer configures IOMMU passthrough
automatically. Forgetting it was the single most common cause of a failed Gen2 result before that.

`install.sh` reads `/proc/cpuinfo` and picks `intel_iommu=on iommu=pt` for `GenuineIntel` or
`amd_iommu=on iommu=pt` for `AuthenticAMD`, strips any existing `intel_iommu=*`, `amd_iommu=*` or
`iommu=*` tokens, and rewrites `/etc/default/grub` (`GRUB_CMDLINE_LINUX_DEFAULT`, falling back to
`GRUB_CMDLINE_LINUX`) or `/etc/kernel/cmdline`, taking a `*.cmpunlocker.bak` backup. `--no-iommu`
opts out. It warns that IOMMU must also be enabled in BIOS or UEFI (VT-d, AMD-Vi or SVM).
`remove.sh` restores the backup, printing
`Reverted IOMMU kernel parameters (effective after reboot)` or warning
`No IOMMU config backup found - kernel command line left as-is`.

`debug-gen2` has no IOMMU handling at all, and neither does shipping master. The manual recipe
before `6a85e6c`:

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt"/' /etc/default/grub
sudo update-grub
sudo reboot
dmesg | grep -i iommu
```

!!! question "Open problem: is IOMMU passthrough actually required?"
    For: multiple testers went from "got 64GB memory, BUT still PCIe 1" to success after a single
    grub change; the maintainers' `DEBUGGING.md` gives it as the *only* remedy for "PCIe still at
    Gen1 after install"; the installer now does it automatically. Against: the independent setup
    script lists `iommu=pt` and VT-d among things "tested and confirmed unnecessary", and its
    confirmed hosts plus the AMD HiveOS success case made **no grub changes at all**. Directly
    contradictory single-tester reports also exist for `iomem=relaxed`: one tester was stuck at
    2.5 GT/s "until i messed with iommu configuration in grub / because mmap was failing", while
    another ran `intel_iommu=on iommu=pt iomem=relaxed` and got nothing. A plausible but
    undemonstrated reconciliation is that `iomem=relaxed` matters only for the userspace
    `mmap`-based retrain and IOMMU mode matters only on some chipsets. What would settle it: a
    matrix of {IOMMU off, on, pt} × {Intel, AMD} × {userspace hammer, in-driver 0008} on identical
    software.

## Verification

```bash
# expect "2, 2"
nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max --format=csv

# expect "LnkSta: Speed 5GT/s"
sudo lspci -d 10de:20c2 -vv | grep -E 'LnkCap:|LnkSta:'
```

Three rules, in order of importance:

1. **Verify with `LnkSta`, never `LnkCap`.** `LnkCap` can read Gen2 while the link is still
   training at Gen1. That trap is the stated source of most "it works" claims that do not hold up.
2. **Expect sysfs to lie.** On a Gen2-trained card `/sys/bus/pci/devices/<bdf>/max_link_speed` may
   still read `2.5 GT/s` while `current_link_speed` reads `5.0 GT/s`. One rig reported a coherent
   `max 5.0 GT/s`; three cards across two rigs reported the mismatch. It is expected, not a fault.
3. **Host bandwidth roughly doubling, from ~0.85 GB/s to ~1.7 GB/s, is the real proof.**

`Gen2/verify.sh` checks **only memory geometry** and contains no PCIe check whatsoever, despite the
branch README listing `| PCIe Gen2 link (5GT/s, Device Max >= 2) | Working ✓ |`. See
[verify](../procedures/verify.md).

## Diagnostic strings

| Source | String | Meaning |
|---|---|---|
| `0007` | `SEC2_DEBUG: PCIe xp3g booter FAILED to set <name>` | A PLM or fuse write did not take through the Booter |
| `0007` | `SEC2_DEBUG: PCIe VSEC_DEVICE booter FAILED` | Expected on this silicon; Gen2 still works |
| `0007` | `SEC2_DEBUG: PCIe PRIV_MISC_1 booter FAILED` | Not expected; this write normally succeeds first try |
| `0007` | `SEC2_DEBUG: PCIe CYA_0 after clear DIS_G2: 0x%08x (bit2=%u)` | Informational; `bit2` should read 0 |
| `0007` | `SEC2_DEBUG: PCIe XVE_OVR@8872c=0x%08x; skip mid-boot retrain` | Informational and deliberate |
| `0008` | `CMP Gen2: no upstream PCIe bridge; skipping link retrain` | Card is not behind a bridge that can retrain it |
| `0008` | `CMP Gen2: cannot map BAR0; skipping link retrain` | `ioremap` failed |
| `0008` | `CMP Gen2: PCIe capability access failed (<ret>); skipping link retrain` | Config access error |
| `0008` | `CMP Gen2: PCIe retrain completed without Gen2 link (status=0x1042, ret=0)` | **False negative.** `0x1042` *is* Gen2 |
| `0008` | `CMP Gen2: PCIe link trained to Gen<n>` | Success, but emitted at `NV_DBG_INFO` so it is usually filtered out |
| `retrain.sh` | `BAR0 dead; skip` / `DIS_G2 still set; skip` / `Cap Gen<n>; skip` / `BAR0 dead after TLS; skip` / `preconditions failed; skip` | Early exits |

Read the lot with `sudo dmesg | grep SEC2_DEBUG`. Recorded counts: 34 lines on a Gen1 build with
no PCIe patch, 80 lines on a Gen2 build, and `SEC2_DEBUG lines=152` from `pcielink.sh` on two
separate two-card Gen2 rigs on 610.43.03, each carrying `OPT=00000001/00000001/16680000` in the
same output. The one archived raw two-card Gen2-branch `610.43.03` dmesg contains 134 lines, and
the one archived single-card capture contains 29.

!!! note "Line counts are not a reliable cross-build fingerprint"
    The recorded values are 29, 34, 80, 134 and 152, depending on build, branch and card count. Do
    not read a mismatch as a failed install.

!!! info "Booter run status is always `0xffff`"
    `kgspExecuteBooterLoad_HAL` returns `0xffff` for every payload run, whether or not the write
    landed. After each run the seccode error code sits in mailbox0, and `mailbox0 != 0` yields
    `NV_ERR_GENERIC` from `s_executeBooterUcode_TU102`. For payload runs this is the expected
    "invalid signature" complaint raised *after* the priv-sequencer script has already run.
    **Register readback is the only valid success criterion.** For the real BooterLoad,
    `mailbox0 != 0` is a genuine failure.

## Requirements and constraints

- **Driver**: nvidia-open `610.43.03` (default) or `610.43.02`, exact match. `driver/VERSION` on
  `debug-gen2` and `Gen2` is identical to shipping master, and the build hard-fails on anything
  else. Because `0007` patches `kernel_gsp.c` and `kernel_gsp_tu102.c` and `0008` patches
  `kernel-open/nvidia/nv.c`, the Gen2 work is tightly bound to those two releases. See
  [driver versions](../procedures/driver-versions.md).
- **Secure Boot must be off.** `install.sh` dies if `mokutil --sb-state` reports
  `SecureBoot enabled`.
- **Device ID** must be `10de:20c2` or `10de:2082`. A `10de:20b0` card installs but gets
  `unlock path not gated for this ID; skipping`.
- **Bare metal or Oculink.** Passthrough VMs advertise Gen2 but do not train; Thunderbolt 3
  enclosures break the entire unlock, not just PCIe.

### Persistence

A cold boot always runs the signed DevInit from flash with the locked CMP table, so first
enumeration always shows Gen1. A plain `rmmod` and `modprobe` does **not** re-run DevInit (no
PERST), so the patch re-fires on every GSP boot and restores the register values, but the retrain
must be re-triggered after every reload. Full reset paths (PERST, `nvidia-smi --gpu-reset`,
`echo 1 > /sys/bus/pci/devices/<bdf>/reset`) re-run signed DevInit and discard the fixes. This
model is consistent with every observation but has not been confirmed by a direct before-and-after
PERST measurement.

`remove.sh` on the Gen2 family cleans the whole footprint: disables and reset-fails
`cmpretrain.service` and `cmp-gen2-retrain.service`, removes both unit files,
`/usr/local/sbin/retrain.sh`, `/usr/local/sbin/cmp-gen2-retrain.sh` and
`/etc/modprobe.d/cmp-pcie-gen2.conf` (`Removed PCIe Gen2 helpers`), then restores the
`*.cmpunlocker.bak` kernel-command-line backup.

## Known failure modes

| Symptom | Status |
|---|---|
| `nvidia-smi` reports `2, 2` right after `install.sh` but `1, 1` after reboot, reproducibly | Unexplained. Re-running `install.sh` restores it every time. One NixOS user sidestepped it by applying the patch at kernel level so it re-applies at every boot. Working hypothesis: the *patched* module is not actually the one loaded at boot. Check `modinfo` and look for `SEC2_DEBUG: PCIe` lines after reboot before blaming the retrain |
| One Intel platform never reaches Gen2 | An ASUS W890 SAGE with four PCIe 5.0 x16 slots, Ubuntu 24.04, kernel 7.0.0-28-generic, two cards. Tried: the `Gen2` branch, `debug-gen2`, an external fork, grub lines including `intel_iommu=on iommu=pt iomem=relaxed`, a soldered card and an unmodded card, slots 1 and 4. Every time: `LnkSta: Speed 2.5GT/s (downgraded), Width x4 (downgraded)` while `LnkCap` correctly advertised 5 GT/s. Kernel version was ruled out by a separate tester who rolled CachyOS back to 6.12-LTS with no change. Contrast working case: AMD, HiveOS Ubuntu 22.04, kernel 6.12.0, no grub changes at all |
| Guest VM under Proxmox or VFIO | Capability advertised, training does not happen. The retrain would need to be driven from the **host** on the physical root port, because the guest has no access to the real upstream bridge |
| Thunderbolt 3 | Booter Load fails outright (`0x15` / `0xffff`), so this is a compute and memory failure, not a PCIe one. Use Oculink |
| First public patch would not apply | `patch: **** malformed patch at line 264` on `kernel_gsp_tu102.c`. Two hunk headers overstated their line counts: `@@ -4942,6 +4942,323 @@` should be `260`, and `@@ -611,6 +611,50 @@` should be `44`. Fixed the same day by `0901346`. A full diff of `debug-gen2`'s `0007` against `Gen2`'s shows exactly two differing lines, both hunk headers; the patch bodies are byte-identical across all four branches. It was survivable only because `build.sh` uses lenient `patch -p1` rather than `git apply` |

Note also that seeing `kernel_gsp_tu102.c` in a patch-apply error does **not** mean the patch is
for Turing. The `_TU102`-suffixed GSP functions are exactly the ones the 170HX executes; they
appear in the Booter failure messages on working Ampere cards
(`s_executeBooterUcode_TU102`, `kgspExecuteBooterLoad_TU102`, `kgspBootstrap_TU102`).

Do not confuse this `0007` with the clean-room line's `0007-pcie-gen4-shadow.patch`, which was
abandoned to a boot loop. Same number, different patch.

## Measured Gen2 results

| Quantity | Value | Conditions | Confidence |
|---|---|---|---|
| Host bandwidth, Gen2 x4 | 1.68 GB/s send, 1.71 GB/s receive | OpenCL-Benchmark, one archived screenshot, one unmodded card | medium |
| Host bandwidth, Gen2 x4 | ~1.71 GB/s | The setup script's own prediction, "~0.85 to ~1.71 GB/s, exactly 2x", verified on one AMD B650M / CachyOS host. Not a separate measurement | low |
| Gen1 x4 to Gen2 x4, one A/B | 1.67 to 3.24 GB/s | OpenCL, on a modded card that negotiated only x8 | medium |
| Gen2 x16 | 6.63 to 6.67 GB/s | `ocl_pcie_bw`, one rig, 2026-07-26, full 24-capacitor mod | medium |
| pp512 | 203.84 to 277.84 t/s | Q8 ik_llama with MTP, 10 GB card unlocked to 40 GB, `--spec-type mtp:n_max=2,p_min=0.0`, all else unchanged | high |
| pp2048 | 328.81 to 449.41 t/s | Same A/B | high |
| pp8192 | 363.25 to 493.86 ± 16.92 t/s | Same A/B | high |
| tg128 | 38.15 to 41.52 ± 1.89 t/s | Same A/B | high |
| tg512 | 37.69 to 40.12 t/s | Same A/B | high |
| tg2048 | 36.78 to 37.90 t/s | Same A/B | high |
| AER counters at Gen2 | 0 / 0 / 0 | Two `0x20c2` cards, kernel 6.12.0-hiveos | high |
| Gen2 de-emphasis | -3.5 dB | `LnkSta2`, first confirmed Gen2 capture | medium |

Prefill benefits meaningfully; token generation barely moves. That matches the arithmetic: at
5120 hidden dimensions, fp16 activations are 10,240 bytes per token per hop, so decode traffic is
nowhere near the link ceiling. See [LLM inference](../operations/llm-inference.md).

## Open problems

!!! question "Open problem: fix the 0008 success predicate"
    The most tractable item in the whole PCIe area, and a one-line change. Drop the
    `PCI_EXP_LNKSTA_DLLLA` term, or make it conditional on `PCI_EXP_LNKCAP_DLLLARC`, or read
    `LnkSta` from the upstream bridge instead of the endpoint. Also raise the success print to
    `NV_DBG_ERRORS` to match `0007`'s convention.

!!! question "Open problem: is 0008 sufficient, unnecessary, or actively misleading?"
    Three independent testers reported `0008` fixing multi-card Gen2 and eliminating crashes. The
    independent setup script asserts `0008` runs at driver probe roughly three seconds after the
    capability window has closed, and lists it among things "tested and confirmed unnecessary".
    The DLLLA defect complicates **both** positions: `0008`'s failure message is emitted
    unconditionally on this card, so it is not evidence the retrain failed, and equally the three
    testers may have been reading `nvidia-smi` on cards that reached Gen2 by another route. What
    would settle it: install the Gen2 branch with `0008` present and the hammer service absent, and
    check `pcie.link.gen.current` after a cold boot on a host where the hammer is known to succeed.

!!! question "Open problem: why do some users get Gen2 and some do not?"
    The `pcielink.sh` report was circulated specifically so kernel, driver, serial, board part
    number and VBIOS could be correlated against success and failure. Two VBIOS versions are
    already in evidence on otherwise identical `900-11001-0108-000` boards: `92.00.6D.00.0A` and
    `92.00.67.00.01`. Next step: tabulate by VBIOS and root-port model, and test the documented
    cold-boot dependency (one clean-room run needed 18 of 27 PCIe PLMs re-opened after a cold boot).

!!! question "Open problem: merging Gen2 to master"
    Blockers visible in the tree: `0007` is a large debug-instrumented hunk logging at
    `LEVEL_ERROR` throughout; `tools/retrain.sh` is dead code on `Gen2` and `far`;
    `constants.yaml` omits five of the registers the mechanism depends on; and `verify.sh` does not
    check PCIe at all. Whether multi-card, IOMMU and Gen2 work merges, and in what order, is
    undecided. The multi-card installer changes are self-contained and could land alone.

!!! question "Open problem: an unexplained early Gen2 claim"
    A verified clean-room exchange dated 2026-07-05 corrects a Gen3 claim with "only 2.0 was",
    treating Gen2 as already accomplished, three weeks before the reproduced result and directly
    contradicting a 2026-07-07 message that still says "We still need something for PCIe 2.0".
    Either an earlier independent result never propagated, or the timestamp is mis-attributed. Only
    the original message metadata can settle it. The technical content of that message (Gen3 is
    fuse-gated) is consistent with everything else and can be relied on; the date cannot.

## See also

- [PCIe subsystem](../hardware/pcie-subsystem.md) for the fuses, the DevInit table and the width cap
- [Gen3 and Gen4](../frontier/pcie-gen3-gen4.md) for the unsolved half
- [Privilege level masks](privilege-level-masks.md) for the nine-entry PLM table
- [Falcon and Booter](falcon-and-booter.md) for the write primitive `0007` rides on
- [Driver patches](driver-patches.md) for the full `0001` through `0008` inventory
- [Register reference](register-reference.md) and [register index](../appendix/register-index.md)
- [Troubleshooting](../procedures/troubleshooting.md)
- [Status board](../frontier/status-board.md)
