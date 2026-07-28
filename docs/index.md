# The CMP 170HX Wiki

**What this page covers:** what the NVIDIA CMP 170HX is, what the community took back from
it, exactly what works today, and where to go next depending on why you are here.

The CMP 170HX is a cryptocurrency mining accelerator built on **GA100**, the same 826 mm²
7 nm die as the NVIDIA A100. It shipped in two SKUs, PCI ID `10de:20c2` reporting 8192 MiB
and `10de:2082` reporting 10240 MiB, and both expose 70 streaming multiprocessors, 4480 CUDA
cores and 280 third-generation tensor cores at compute capability 8.0. NVIDIA sold it
deliberately crippled in four separate ways: the SM issue rate was fused down to roughly 1/32
for FP32 FMA and for every tensor-core path, HBM capacity was strapped to a fraction of what
the stacks physically hold, the PCIe link was capped at Gen1 speed and negotiates only x4 of
its 16 wired lanes, and NVLink and ECC were fused off. A careful 2023 teardown concluded that
the combination "guaranteed the uselessness of the GPU" and judged the caps unbreakable
because of firmware signing.

Between 2023 and July 2026 a distributed community took most of it back, in software, with no
VBIOS flashing and no signature forgery. The shipping unlocker is a six-patch set against
NVIDIA's open kernel modules. It re-fires the SEC2 Booter Load with a crafted signature
payload to open four privilege level masks, then performs four register writes inside the GSP
boot window: `0x0082381c` = `0x88888888` and `0x00823820` = `0x00000008` restore the full SM
issue rate, and FBPA CFG1 `0x009a0204` plus MMU LMR `0x00100ce0` restore genuine A100 memory
geometry. Measured result: FP32 non-tensor goes from about 0.39 to about 12.6 TFLOPS (a 26x to
32x gain), BF16 tensor from 6.4 to 171-193 TFLOPS, FP64 to 11.6 TFLOPS on a torch GEMM (the
tensor path: one clpeak dump prints 6.31 TFLOPS scalar against 11.96 for `wmma_fp64` in the same
run), and an 8 GB card reports and uses **65536 MiB**. The whole sequence costs about one second
of driver load, re-runs on every module load, and writes nothing to flash. Eight rented cards
benchmarked in one session measured under 2.5% spread and passed 8/8 full-VRAM byte-compare
integrity tests.

!!! warning "Two things to get right before you read anything else"
    **Capacity is per SKU and is not interchangeable.** The 8 GB card unlocks to **64 GB**.
    The 10 GB card unlocks to **40 GB**, and 40 GB is the supported configuration. The 80 GB
    driver branch for 10 GB cards was built, tested and abandoned: it reports 81920 MiB but fails
    above roughly 40 GB of real use. A separate script-driven coherent register set does reach
    real memory past 40 GiB, but it is unshipped, experimental and gives roughly one CUDA context
    per fire.

    **PCIe speed and PCIe width are two different problems with two different fixes.**
    Gen1 to Gen2 is a *software* unlock that exists only on unreleased branches. Going beyond
    x4 *width* requires hand-soldering 24 AC-coupling capacitors onto the board. Neither one
    does anything for the other.

## Status today

| Capability | Status | Detail |
|---|---|---|
| SM throttle removal (compute) | **Shipped, stable** | Two register writes; survives FLR. [How it works](unlock/compute-throttle.md) |
| 8 GB card to 64 GB | **Shipped, stable, in production** | CFG1 `0x02779000`, LMR `0x0000020B`. [Memory geometry](unlock/memory-geometry.md) |
| 10 GB card to 40 GB | **Shipped, stable** | CFG1 `0x02669000`, LMR `0x0000028A` |
| Persistence across reboot | **Automatic** | Re-applied on every GSP boot; nothing is flashed. [Install](procedures/install.md) |
| Multi-card rigs | **Works** | 8-card rigs measured; see [Multi-GPU](procedures/multi-gpu.md) |
| GPC clock offset / undervolt | **Works via NVML** | `[-1000..+1000]` MHz on the 8 GB SKU. [Tuning](operations/tuning.md) |
| Power limiting (`nvidia-smi -pl`) | **Works** | 100-250 W stock, 300 W on the OC VBIOS. [Power](operations/power-and-psu.md) |
| PCIe Gen2 (link **speed**) | **Works, unreleased branches only** | Not in shipping `master`; non-deterministic in the field. [Gen2](unlock/pcie-gen2.md) |
| PCIe x16 (link **width**) | **Hardware mod only** | 24 × 0402 220 nF X7R capacitors. [Physical mods](operations/physical-mods.md) |
| Gen2 at x16 together | **Observed once** | 6.63-6.67 GB/s, one rig, 2026-07-26, medium confidence |
| 10 GB card to 80 GB | **Branch rejected; coherent set experimental** | The `80` branch reports 81920 MiB and fails above ~40 GB. A driverless coherent fire passed a 77.5 GiB no-fold test but gives one CUDA context per fire. [80 GB](frontier/80gb.md) |
| PCIe Gen3 / Gen4 | **Unsolved** | Both gen fuses read `0x00000001`. [Gen3/Gen4](frontier/pcie-gen3-gen4.md) |
| More than 70 SMs | **Unsolved** | Every write path to the GPC-disable fuses is latched |
| ECC | **No lever found** | Fused off, no telemetry, `MASTER_EN` read-only. [ECC](frontier/ecc.md) |
| NVLink | **Not possible on this board** | Fused off. Whether the board-side interface ICs are populated is open and leans depopulated. [NVLink](frontier/nvlink.md) |
| Peer-to-peer (P2P) | **Absent** | [P2P](frontier/p2p.md) |
| MIG | **Single report, not shipped** | Bit 0 of `0x820840`; awaiting a second card and a pull request |
| Idle power reduction | **No lever** | Only performance state P0 exists; `nvidia-pstated` returns `NVAPI_ERROR` |
| Memory clock control | **Refused through NVML**, but reachable with a patched module | NVML MEM VF offset range is `[0..0]` and `-lmc` is unsupported, yet a patched module plus a reboot has downclocked HBM in practice: 1728 MHz → 212.2 TF / 181.2 W; 1620 MHz (NDIV 60) → 211.6 TF / 172.9 W; 1404 MHz (NDIV 52) → 210.5 TF / 169.3 W |
| VBIOS modification | **Closed for the unlock levers** | The capacity straps and the PCIe Gen straps sit inside the Davies-Meyer MAC range. The unsigned FwSec tail is outside it and does hold editable fields, including the board power limit at `0x45E45` and `freqDelta`, but writing them needs a CH341A clip. [VBIOS](hardware/vbios.md) |

Supported drivers on shipping `master` are exactly **`610.43.03`** (default) and
**`610.43.02`**; the build hard-fails on anything else. Ports to 595 / 590 / 580 exist on one
branch, are source-verified, and have never been reported to boot.

## Start here

**"I just bought one and I want it working."**
Read [What is this card](start/what-is-this-card.md) for the background, then
[Identify your card](start/identify-your-card.md) to establish which SKU you hold (this
decides everything downstream), then [Risks](start/risks.md), then
[Quick start](start/quick-start.md) and [Install](procedures/install.md). Before you power it
on at all, read [Cooling](operations/cooling.md) and
[Power and PSUs](operations/power-and-psu.md): the card is passively cooled with no fan, and
its single 8-pin socket is an **EPS** socket, not a PCIe one. Forcing a PCIe cable into it
will damage the card. When the install finishes, confirm it with
[Verify](procedures/verify.md) rather than by reading dmesg.

**"I want to unlock it, and I want to know what I am typing."**
[The unlock, in overview](unlock/overview.md) then [How it works](unlock/how-it-works.md).
The mechanism splits into [Falcon and the Booter](unlock/falcon-and-booter.md),
[privilege level masks](unlock/privilege-level-masks.md),
[the compute throttle](unlock/compute-throttle.md) and
[memory geometry](unlock/memory-geometry.md). If something goes wrong,
[Troubleshooting](procedures/troubleshooting.md) is organised by the exact string you saw.
[Driver versions](procedures/driver-versions.md) explains why the version pin is not
negotiable.

**"I want to understand how it works at the register level."**
[Hardware overview](hardware/overview.md) for the complete specification, then
[GA100 silicon](hardware/ga100-silicon.md), [fuses and OTP](hardware/fuses-and-otp.md),
[the memory subsystem](hardware/memory-subsystem.md) and
[the PCIe subsystem](hardware/pcie-subsystem.md). Every address, value and readback in the
project is collected in the [register reference](unlock/register-reference.md) and indexed in
the [register index](appendix/register-index.md). The
[VBIOS page](hardware/vbios.md) explains why firmware attacks are closed.

**"I want to help solve what is left."**
Start at the [status board](frontier/status-board.md) and the
[open questions](frontier/open-questions.md), which are ranked by tractability and each carry
a concrete next experiment. Several are cheap: one three-way boot comparison settles the
`RMPcieLinkSpeed` `0x1`-versus-`0x2` dispute, one header lookup settles the LMR magnitude
field width, one constant change and one reboot would test whether a *coherent* 80 GB triple
behaves differently from the incoherent one the `80` branch actually shipped. Read
[dead ends](history/dead-ends.md) first: a large amount of effort has already been spent on
paths that are now closed, and the page records exactly why each one closed.

## How this wiki marks confidence

Readers must be able to tell settled fact from active speculation at a glance.

- **Plain prose is confirmed.** It carries no marker because none is needed. Where a figure is
  code-derived, the source file is named; where it is measured, the conditions are given.
- `!!! warning "Experimental"` marks unreleased-branch material and anything resting on a
  single report. Everything about PCIe Gen2 is in this category, because the Gen2 patches have
  never been merged to `master`.
- `!!! danger` marks anything that can destroy hardware or silently corrupt data. The most
  important instance in this wiki is not an obvious one: at a 1400 MHz ceiling, a +325 MHz
  clock offset **corrupts memory without crashing**, so a run that completes is not evidence
  that a setting is safe.
- `!!! question "Open problem"` marks things nobody has solved, and always states what was
  tried and what the next step would be.
- `!!! note "Superseded"` marks an approach that has been replaced, with a pointer to what
  replaced it. These are kept rather than deleted, because a great deal of published material
  about this card is superseded and readers arrive carrying it.

Claims resting on one observation say so in the sentence itself: "one tester reported", "a
single rig on one day". Numbers that appear in more than one place have been reconciled
against a single canonical value, and where two sources genuinely disagree and no evidence
settles it, this wiki says the value is unknown rather than picking one quietly. See
[How to read this wiki](start/how-to-read-this-wiki.md) for the full convention and
[methodology](appendix/methodology.md) for how the underlying claims were adjudicated.
