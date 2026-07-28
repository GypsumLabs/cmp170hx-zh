# What is this card?

**What this page covers:** what a CMP card is, why NVIDIA built one out of A100 silicon, what
was taken away and why, and what the community has put back. Written for someone meeting the
CMP 170HX for the first time. Terms defined here are collected in the
[glossary](glossary.md).

The short version: the CMP 170HX is a datacenter-class GPU that NVIDIA deliberately broke
before selling it, built on the same physical chip as the A100. In July 2026 a community
effort restored the two most valuable pieces, full compute throughput and full memory
capacity, entirely in software, on a stock unmodified card, with nothing written to the card's
flash. An 8 GB card becomes a 64 GB card and its FP32 throughput rises by roughly 32 times.

## What a CMP card is

CMP stands for **Cryptocurrency Mining Processor**. Around 2021, NVIDIA created a product line
aimed at industrial-scale Ethereum miners. The idea was straightforward: miners were buying
gaming and datacenter GPUs in enormous volume and driving prices up for everyone else, so
NVIDIA offered them purpose-built parts instead. A CMP card has no display outputs, is not
supported for graphics or gaming, is sold without a consumer warranty, and, critically, has
capabilities removed that mining does not need.

Ethereum mining at the time was almost entirely a **memory bandwidth** problem. The Ethash
algorithm walks a large dataset in a mostly random pattern, so what a miner needs is fast
memory and enough integer throughput to run the hashing. Floating-point maths, tensor cores,
fast interconnects and large VRAM capacity contribute nothing. So NVIDIA removed exactly
those. The CMP 170HX was the top of that line.

## Why the silicon is so interesting

Most CMP parts were built from consumer chips. The CMP 170HX was not. It uses **GA100**, the
826 mm² 7 nm die that powers the A100, NVIDIA's flagship datacenter accelerator of the Ampere
generation. It is the largest chip NVIDIA made on that node, sitting at the reticle limit,
carrying HBM2e stacked memory bonded directly to the package.

The CMP 170HX board is nearly identical to the A100 40 GiB PCIe board. A100 waterblocks fit.
A100 shrouds fit. The ASIC is marked `GA100-105F-A1`, a harvested GA100 with 5 of 8 graphics
processing clusters enabled, giving 70 streaming multiprocessors and 4480 CUDA cores against a
full A100's 108 SMs and 6912 cores. That harvest is normal industry practice: chips this large
always have some defective regions, and parts are binned accordingly. What is *not* normal is
everything else that was done to it.

There is a detail here that matters a great deal later. On several examined cards, the
disabled graphics clusters were marked **not defective**. The silicon is good; it was switched
off to hit a product specification. The same is true of the memory: the HBM stacks physically
hold far more than the card reports.

## What was restricted, and why

Four independent restrictions, four separate mechanisms.

**1. The SM maths rate was throttled to roughly 1/32.** This is the big one. Inside each SM,
NVIDIA burned one-time-programmable fuses that set the *issue rate* for specific arithmetic
units. On a 170HX, the fuses for FFMA (fused multiply-add), FMLA16, FMLA32 and the integer
multiply units IMLA0 through IMLA4 all read `0x5`, which means divide-by-32. On every A100,
A10, A5000, A6000 and Drive A100 probed, those same fuses read `0`. The throttle is per
instruction class rather than a blanket ban, which is why a locked card still does scalar FP16
at 42-50 TFLOPS and INT32 at 12.5 TIOPS while FP32 fused multiply-add collapses to about
0.39 TFLOPS. The purpose was to make the card useless for AI training and high-performance
computing, both of which live on exactly the instructions that were cut.

**2. Memory capacity was strapped down.** The card reports 8 GB or 10 GB depending on the SKU.
The memory controllers are physically capable of addressing far more, and the stacks contain
far more. The cap is a single 32-bit configuration word selected by a hardware strap at boot,
which programs the *addressing depth* of each memory partition. Set it lower and each
partition addresses 512 MiB; set it to the value a real A100 uses and the same partition
addresses 4096 MiB. Nothing physical changes.

**3. The PCIe link was capped twice over.** The card negotiates PCIe **Gen1** (2.5 GT/s) rather
than the Gen4 the silicon supports, giving about 0.85 GB/s to the host. Separately, although
all 16 lanes are wired into the edge connector, only **4** of them train, because NVIDIA left
the AC-coupling capacitors off the other 12 lanes at manufacture. These are genuinely two
different problems: the speed cap is enforced by fuses and firmware, the width cap is a
missing component on the board.

**4. NVLink and ECC were fused off.** NVLink is NVIDIA's high-speed GPU-to-GPU interconnect. On
this board it is disabled in fuses *and* the interface chips are simply not fitted, so no
software change can bring it back. ECC (error-correcting memory) is fused off with no
telemetry and no known lever.

A careful independent review in 2023 added these up and concluded that the combination
"guaranteed the uselessness of the GPU", judging that firmware signing made a bypass unlikely.
The pessimism about firmware was correct. The conclusion was not.

## What the community restored

The story runs in three acts.

**Act one, December 2023: the workaround.** Someone benchmarking a fluid-dynamics simulator
noticed that if the OpenCL kernel was recompiled with floating-point contraction disabled, so
that the compiler emitted separate multiply and add instructions instead of a single fused
multiply-add, throughput jumped from 0.395 to 6.285 TFLOPS. A factor of 15.9. That was the
first hard evidence that the restriction was per-instruction rather than physical, and it
turned into a family of practical patches: builds of llama.cpp with `--fmad=false` and DP4A
disabled roughly doubled token generation on a completely locked card, with no register writes
at all. Those patches are still useful for anyone who cannot or will not patch a driver.

**Act two, June and July 2026: the register unlock.** The real mechanism turned out to be a
pair of override registers that sit above the fuses. GA100 has a `FEATURE_OVERRIDE` block, and
within it two registers, `0x0082381c` and `0x00823820`, hold the effective speed-select fields
for the nine arithmetic units. Writing `0x88888888` and `0x00000008` sets every unit to
"override enabled, full rate". The fuses are unchanged and still read `0x5` afterwards; the
override simply outranks them.

The catch is that those registers are protected by a **privilege level mask**, a hardware gate
that decides which agents may write a given register. Opening it requires the SEC2 security
processor running in high-security mode, which requires code NVIDIA signed. The solution was
to re-fire the signed **Booter Load** routine repeatedly with a crafted payload buffer, using
it as a narrow arbitrary-write primitive to open four masks, one per pass, then perform the
real writes from the host. The whole sequence was folded into NVIDIA's own open-source kernel
modules as a patch set, so it runs automatically inside the GSP boot path every time the
driver loads.

The same primitive unlocked memory: with the framebuffer masks open, writing the A100
addressing word to FBPA CFG1 (`0x009a0204`) and the matching size to the MMU local memory
range register (`0x00100ce0`) makes the card enumerate its real capacity. Compute shipped
first because of a hardware asymmetry: the compute registers live in the always-on power
island and survive a function-level reset, while the memory geometry registers do not and must
be re-applied on every driver load.

**Act three, July 2026: PCIe Gen2.** On 24 July 2026, a combined sequence of register writes
issued from inside the same Booter privilege window, followed by a link retrain driven from
the *upstream* bridge, trained a 170HX at 5 GT/s for the first time. It doubles host bandwidth
to about 1.7 GB/s. It is real, it has been reproduced on multiple machines, and it is also
fragile, not deterministic, absent from the shipping release, broken under virtual-machine
passthrough, and completely useless over Thunderbolt. Treat it as experimental.

## What you actually get, and what you do not

| You get | You do not get |
|---|---|
| 64 GB (8 GB SKU) or 40 GB (10 GB SKU) of stacked HBM | More than 70 SMs. Every path into the cluster-disable fuses is latched |
| ~12.6 TFLOPS FP32, ~11.6 TFLOPS FP64 tensor, 170-190 TFLOPS BF16 | Even INT8. It is uneven, and why is unexplained: the library path measures 43-48 TOPS (slower than FP16), while the INT8 *tensor* MMA path measures 335.0-335.6 TOPS on the same cards. The 7.6x gap is an open question, not a demonstrated hardware restriction |
| ~1.6 TB/s of memory bandwidth, never restricted in the first place | ECC. Fused off, with no lever and no telemetry |
| A GPC clock offset on 8 GB cards carrying the 300 W OC VBIOS, usable as an undervolt | NVLink, fuse-closed with the interface parts unfitted and no lever found. PCIe peer-to-peer is absent too, but it is a separate mechanism that the NVLink fuse does not gate, and nobody has determined whether it is fused or driver-gated; the public `610.43.03-p2p` driver branch has never been tried on a 170HX |
| Automatic re-application on every driver load | PCIe Gen3 or Gen4. Both remain unsolved |
| Nothing written to flash, and a clean uninstall | A gaming card. Graphics remain poor even at x16 |

## Before you go further

The card is **passively cooled with no fan at all**, and it is designed to sit in a server
chassis with screaming 80 mm fans behind it. On a desk with no airflow it will overheat, and
GA100 has a genuine leakage-driven runaway characteristic where getting hotter makes it draw
more power. Its single 8-pin socket is an **EPS** (CPU-style) connector, not a PCIe one, and
plugging a PCIe cable into it will damage the card.

Read [Risks](risks.md) next, then [Identify your card](identify-your-card.md), because whether
you hold the 8 GB or the 10 GB SKU determines the capacity you can reach, the memory clock you
are stuck with and whether the overclock VBIOS applies to you. From there,
[Quick start](quick-start.md) and [Install](../procedures/install.md).

For the full specification, see [the hardware overview](../hardware/overview.md). For the
mechanism in depth, start at [the unlock overview](../unlock/overview.md). For how this wiki
signals what is proven and what is not, see
[how to read this wiki](how-to-read-this-wiki.md).
