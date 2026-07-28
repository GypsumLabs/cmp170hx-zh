# Running LLMs on the CMP 170HX

**What this page covers.** Which inference stacks work on an unlocked card, the measured
prompt-processing and token-generation rates with model, quantisation and context stated, what
breaks and why, how to scale across cards, and the one question that governs every multi-card
decision: whether PCIe bandwidth is the bottleneck. Raw compute and bandwidth numbers live on
[performance.md](performance.md); clocks and power on [tuning.md](tuning.md).

**Three results decide almost every choice you will make.**

1. **vLLM beats llama.cpp by roughly 1.8x** on one card and one model family, and beats SGLang
   too. That ratio comes from a single tester and the two sides were not quant-matched, so treat
   it as a direction, not a constant.
2. **Pipeline parallelism is mandatory across cards; tensor parallelism is a dead end at
   PCIe Gen1 x4.** Direct A/B on Qwen2.5-72B AWQ: TP2 is 2.3-2.8x *worse* at prefill for +23%
   decode.
3. **The best multi-card result on record** is a 744B-parameter MoE (GLM-5.2, 40B active) on
   8 unlocked 64 GB cards under vLLM pipeline parallelism: **2,675 t/s prefill at 131k context
   and 30.2 t/s decode**, zero hard faults across the session.

Everything below is measured at **PCIe Gen1 x4** unless stated. The shipping unlocker contains
no PCIe code at all: `common/constants.yaml` on `master` has only `driver_versions`, `gpu`,
`compute` and `profiles` keys, with no `pcie` section anywhere in the tree. Any benchmark
described as running on the released unlock ran at the card's stock link.

!!! warning "How to read the numbers on this page"
    Almost every figure here comes from **one tester, one card, one session**. Very little has
    been independently reproduced, and several rows that once read as separate confirmations
    turned out to be two rows of one table, or a chat summary of a report attached ten minutes
    earlier. Where a figure has more than one source, the text says so explicitly; where it says
    nothing, assume a single report. Model, quantisation, context and conditions are stated per
    figure for the same reason.

---

## What the unlock buys an inference workload

The compute unlock (FEAT PLM `0x00823804` opened to `0xffffffff`, then SS0 `0x0082381C` =
`0x88888888` and SS1 `0x00823820` = `0x00000008`) is what makes tensor-core throughput
available. See [compute-throttle.md](../unlock/compute-throttle.md).

- **`llama.cpp` uses the GA100 tensor cores automatically** with a stock SM80 build. No patch,
  no flag. This is what produces the multi-thousand-token prompt-processing rates several
  testers reproduced on unmodified latest builds with SM80 (and SM86) in the CUDA arch list.
- **The unlocked VRAM is genuinely usable.** One tester running LLMs on 64 GB cards reported
  "havent had a single crash". Six 10 GB cards unlocked to 40 GB ran Qwen 27B and Qwen 35B at
  4-bit with no crashes and no bricked cards; the only limit was thermal, about 10 minutes of
  runtime without an adequate cooling solution. See [cooling.md](cooling.md).
- **Quick sanity check after an unlock:** LM Studio with a small model, where roughly
  **85 tokens/s** is expected on the "E2B" small model. That is one tester's figure with the
  model size not fully specified, so treat it as an order-of-magnitude check, not a target.
  The rigorous check is BF16 throughput against the 202 TFLOPS ceiling; see
  [verify.md](../procedures/verify.md).

!!! note "Superseded: the DP4A / no-FMA patches"
    Before the register unlock, the `no-fma` and `no-dp4a` / DP2A-substitution patches were the
    way to get usable token generation out of a crippled card, roughly doubling decode
    (Llama-2-7B-Q4_0: 61.7 to 143.6 tg with dp2a plus `--fmad=false`). After the compute unlock
    they are unnecessary on the 170HX. They remain the correct path for **non-unlocked** CMP
    cards and for the 90HX / 50HX. DP4A on CMP parts is throttled at roughly a **16x slower
    dispatch rate** than an RTX 2080, and the substitution is four instructions: `prmt.b32` with
    selector `0x9180`, `prmt.b32` with `0xB3A2`, then `dp2a.lo.s32.s32` and `dp2a.hi.s32.s32`
    accumulating into the same register, in `ggml/src/ggml-cuda/common.cuh`, gated by
    `-DDISABLE_DP4A`.

---

## Backend selection

| Backend | Verdict on this hardware | Evidence |
|---|---|---|
| **vLLM** | Best in essentially every measured configuration. The default choice. | "~1.8x faster" as stated by the one tester who ran both on Qwen3.6 27B, single card. Quant parity is not established: the llama.cpp side is Q4_K_M, the vLLM side's quant was never stated and was read in-channel as q6. The archived vLLM table gives Qwen3.6-27B at 62.4 t/s single-stream, which against 36.87 t/s is 1.69x. Also the only stack that runs GLM-5.2 usably |
| **llama.cpp** | Fine for single-card and for non-DSA models across cards. Unusable for DSA-attention models. | 888.09 t/s pp512 single card; 141 t/s prefill on 8 cards for GLM-5.2 versus vLLM's 2,675 |
| **ik_llama** | Slower than mainline llama.cpp on the one controlled comparison | pp512 296.36 versus 360.65; tg128 33.20 versus 33.10 |
| **SGLang** | Lost to vLLM on a single card for Qwen3.6 27B int8, contrary to expectation, and would not run MTP at all | head-to-head with screenshots |
| **LM Studio / llama-swap** | Work; useful as smoke tests and for serving | ~85 t/s on a small model; 60 t/s for a 35B A3B Q8 at a 125 W cap |
| **Vulkan** | Dead end for multi-card | no `VK_KHR_device_group` support in the ggml Vulkan backend, so all card-to-card transfers go through host RAM |

### Building llama.cpp for this card

A reproducible container build was published as `build-llama-170hx.sh`:

```bash
# base image: nvidia/cuda:13.3.0-devel-ubuntu26.04
# clones ggml-org/llama.cpp at a resolved master commit
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=80 \
  -DGGML_BACKEND_DL=ON \
  -DGGML_CPU_ALL_VARIANTS=ON \
  -DGGML_OPENMP=ON \
  -DGGML_CUDA_FA=ON \
  -DLLAMA_OPENSSL=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/app
cmake --build build -j12          # Ninja
# verifies libggml-cuda.so has no missing ldd entries, tags the image by
# llama.cpp build number, then smoke-tests with --runtime=nvidia --gpus all:
nvidia-smi --query-gpu=name,memory.total,pcie.link.gen.current,pcie.link.gen.max --format=csv
llama-bench --list-devices
```

`-DCMAKE_CUDA_ARCHITECTURES=80` is the load-bearing flag: CUDA capability 8.0 is GA100.

!!! danger "Prebuilt `libggml-cuda.so` needs CUDA 13, and fails silently without it"
    The prebuilt binaries link `libcudart.so.13` and `libcublas.so.13`. On a host with only
    CUDA 12.4 the weights **load CPU-only and then OOM** rather than erroring cleanly, which
    makes it hard to diagnose. The working fix is to prepend PyTorch's bundled cu13 libraries to
    `LD_LIBRARY_PATH`.

`llama.cpp` also gained backend-agnostic tensor parallelism via `--split-mode tensor`
(upstream PR `ggml-org/llama.cpp#19378`), removing the even / power-of-two GPU-count
constraint. The PR itself describes the feature as "experimental ... not yet production ready".
vLLM still requires an even GPU count for tensor parallelism, and on this card tensor
parallelism is the wrong strategy anyway (see below).

---

## Single-card measured throughput

### vLLM, one unlocked 64 GB card

Test shape roughly a 1,500-token prompt with 200 tokens of output.

| Model | Decode | Aggregate at 4 parallel | Prefill |
|---|---|---|---|
| `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` (MoE) | **113 tok/s** | **452 tok/s** | **1,700 tok/s** |
| `Qwen3-32B-AWQ` (dense) | 52.9 tok/s | 205 tok/s | 1,755 tok/s |
| Qwen3.6-27B BF16 | 19.2 tok/s | 71.1 tok/s | 2,231 tok/s |
| Qwen3.6-27B-AWQ-INT4 | 58.5 tok/s | 214.8 tok/s | 2,044 tok/s |

### llama.cpp, one unlocked card

| Benchmark | Model / conditions | Result |
|---|---|---|
| `llama-bench` pp512 | qwen35 27B Q4_K_M, 15.65 GiB, 26.90 B params, CUDA, `ngl 99`, one card | **888.09 ± 24.69 t/s** |
| `llama-bench` tg128 | the second row of that same table, same run, same screenshot | **36.87 ± 0.04 t/s** |
| Community reference bench | Llama-2 7B Q4_0, proposed in-channel as the standard quant | **3106 t/s pp, 158 t/s tg**, one numeric report. A second tester posted a screenshot without quoting figures and agreed the numbers were "fine"; a third said "I get 3333 on 7b" without stating the quant |
| Dense versus sparse contrast | Gemma4 26B A4B Q8 (sparse) pp2048 3894.29 versus Gemma4 31B Q8 (dense) pp2048 830.33, same rig and build | model density, not misconfiguration |
| Decode by model | Qwen3.5 9B q4_k_xl ~105 tok/s; Qwen3.6 27B q8 with q8 KV and MTP depth 2, 50 tok/s; Gemma4 26B A4B Q8 tg128 90.65 / tg512 90.10 / tg1024 89.85; Gemma4 31B Q8 tg128 27.07 / tg512 26.74 / tg1024 26.33 | single card |

The 888.09 / 36.87 pair is **one run**: two rows of a single `llama-bench` table in a single
screenshot. A second participant later reposted a screenshot of that same conversation, saying the
run had matched their own numbers, but never posted the numbers being matched, so there is no
second table to compare against.

Dense 27B-class models run an order of magnitude slower on prompt processing than 7B, and that
is model density, not a tuning failure: ~500 t/s and ~900 t/s pp were both reported for dense
Qwen3.6 27B q4_k_p on unpatched SM80/SM86 builds.

### The most rigorous controlled single-card benchmark

A 10 GB card unlocked to 40 GB, Gen1 x4, 250 W cap. Host: 2x EPYC 7713, DDR4, Supermicro
H12DSi-N6, kernel 6.18.38. Model `unsloth/Qwen3.6-27B-MTP-GGUF` (`UD-Q4_K_XL` and `UD-Q8_K_XL`),
17464 MiB of 40960 MiB used at Q4 and 35718 MiB at Q8, ~42 W idle. One tester, one card, one
session, posted in full with error bars; nobody has re-run it.

| Build / config | pp512 | pp2048 | pp8192 | tg128 | tg512 | tg2048 |
|---|---|---|---|---|---|---|
| llama.cpp b10095 (e8e6c7af2), Q4, no MTP | 360.65 | 564.30 | 722.49 | 33.10 | 32.67 | 30.50 |
| Same, MTP (`--spec-type draft-mtp --spec-draft-n-max 2`) | 323.63 | 496.85 | 639.53 | 46.24 (peak 56.67) | 43.02 (peak 55.33) | 44.47 (peak 59.00) |
| ik_llama b4735 (9d07d868), Q4, no MTP | 296.36 | 544.72 | 649.61 | 33.20 | 34.23 | 31.93 |
| ik_llama, Q4, MTP (`--spec-type mtp:n_max=2,p_min=0.0`) | 203.38 | 315.87 | 336.61 | 41.11 (peak 47.00) | 38.26 (peak 47.67) | 35.82 (peak 46.67) |
| ik_llama, Q8, no MTP | 271.49 | 584.31 | 697.18 | 26.36 | 27.27 | 25.79 |
| ik_llama, Q8, MTP | 203.84 | 328.81 | 363.25 | 38.15 | 37.69 | 36.78 |

### Power and efficiency at the single-card level

| Condition | Result |
|---|---|
| Qwen3.6 27B `q6_k_xl` (41 GB resident), deliberately handicapped host (no-AVX2 CPU, card throttling at 250 W, PCIe x4) | ~26 tok/s, rising to **50 then 55 tok/s** once MTP was enabled |
| `Qwen-AgentWorld-35B-A3B-Q8_0.gguf`, llama.cpp via llama-swap, **125 W power limit** | ~60 tok/s |
| Qwen3.6-35B-A3B Q8 with MTP, **170 W** | ~130 tok/s |
| vLLM, Qwen3.6 27B int8 | **2.16 tok/s per watt**, described in-channel as "actually decent efficiency" |

Power limit and MTP both move the number substantially. See [tuning.md](tuning.md).

!!! question "Open problem: the 27B single-card decode figure is not reconciled"
    Published and in-channel figures for "Qwen 27B-class, one unlocked 64 GB card, vLLM" span
    **97 / 90 / 75 / 58.5 t/s**, plus 36.87 t/s for llama.cpp Q4_K_M. Quantisation, MTP state,
    context length and vLLM version all differ between reports and were never held constant.
    Running the published repo configuration verbatim on one card and posting the flags would
    settle it.

---

## Multi-token prediction (MTP)

MTP behaves **oppositely on the two backends** for the same 35B MoE.

| Backend | Without MTP | With MTP | Delta |
|---|---|---|---|
| llama.cpp (`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`) | 108.4 tok/s | **131.3 tok/s** | **+21%** |
| vLLM (same model class) | 147 tok/s | **113 tok/s** | **-23%**, despite a 75% acceptance rate / 1.75 tokens |

On the controlled 40 GB rig, MTP buys roughly **+40% decode for about -10% prompt processing**
(tg128 33.10 to 46.24 while pp8192 722.49 to 639.53). It is a **single-stream benefit only**; a
caution was raised separately that MTP does not scale well with batch size, which is reasoned
rather than measured.

The vLLM regression was traced through three hypotheses. Quantisation of the MTP head was ruled
out (`mtp` is in `modules_to_not_convert`, and fc, attention and shared expert are all BF16). A
wrong FlashInfer cubin was suspected second. The standing explanation is a CPU-side bottleneck:
"it utilizes the CPU and as we are on PCIe Gen1 4x this becomes the bottleneck. GPU-Compute
Utilization goes down by 7% and Mem Usage as well." Suggested monitoring:

```bash
nvidia-smi dmon -s put      # watch sm, mem, rx/txpci
```

It was never proven with a fix.

---

## Multi-card: the headline result and its recipe

A 744B-parameter MoE (GLM-5.2, 40B active) at W4A16 symmetric quantisation on **8 unlocked 64 GB
cards** under vLLM pipeline parallelism, driver 610.43.02, PCIe Gen1 x4 stock (no capacitor mod,
no Gen2 branch), rented hardware.

| Metric | Value |
|---|---|
| Prefill at 4k / 32k / 65k / 131k context | 665 / 1,497 / 2,342 / **2,675 t/s** |
| Decode (no MTP) | **30.2 t/s** |
| KV capacity | 438,107 tokens at 0.92 memory utilisation (BF16 KV, ~88-100 KB/token under MLA) |
| Model load time | ~440-620 s |
| Faults | zero hard faults across the session |

Prefill **rises** with context, because of chunked prefill plus sparse attention. That is the
opposite of llama.cpp's behaviour on the same model and is the clearest single signal that stack
choice dominates hardware here.

This is **one report, not two.** A single tester rented nine cards, benchmarked on eight,
attached `170HX-benchmark-results.md` (2,675 t/s prefill at 131k, 30.2 t/s decode) and ten
minutes later summarised the same run in chat as "2600 t/s prefill, 30 t/s decode". The rounded
and the precise figures are the same session. Nobody has reproduced it on other cards.

### The exact recipe

```text
vllm==0.20.2  release wheel
  + PR #38476 python files applied as a diff onto site-packages
transformers 5.x                       (4.57 does not know glm_moe_dsa)
VLLM_ATTENTION_BACKEND=TRITON_MLA_SPARSE
VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0
--pipeline-parallel-size 8 --gpu-memory-utilization 0.90
block-size 64                          (auto-set by DEEPSEEK_V32_INDEXER)
quantisation: W4A16 symmetric
```

GLM-5.2 uses DeepSeek sparse attention (DSA), which natively needs Hopper or Blackwell. Running
it on Ampere requires the `TRITON_MLA_SPARSE` backend from vLLM PR #38476.

!!! danger "Quantisation selection: most published guides are wrong for this path"
    For GLM-5.2 on vLLM the MoE kernels **reject asymmetric quantisation**.
    Working: `lowbitcoffee/GLM-5.2-W4A16` (symmetric, g128, 388 GB) and
    `QuantTrio/GLM-5.2-Int4-Int8Mix`.
    **Fails: `cyankiwi/GLM-5.2-AWQ-INT4`** (asymmetric, g32), which is the quant most guides
    cite.

!!! warning "Experimental: `VLLM_USE_PRECOMPILED` will not work here"
    The normal way to apply a vLLM patch is an editable install with `VLLM_USE_PRECOMPILED`. It
    ships no `vllm._C` and will fail. Use the 0.20.2 release wheel with the PR's python files
    applied as a diff onto site-packages.

### Other multi-card results

| Configuration | Model / stack | Result |
|---|---|---|
| 8x 64 GB (512 GiB), llama.cpp b10079, `-ngl 999 -c 4096 -np 1 --flash-attn on --no-context-shift --fit off --no-warmup --spec-type none`; virtualised host, masked GPU names, link active Gen1 x4 but device max Gen2 x16 | GLM-5.2 UD-IQ2_M, 239 GB 2-bit, ~224 GiB resident, ~6 min load | TG **17.33 tok/s** (17.31-17.37, SD 0.02); PP **113.0 tok/s** (111.8-115.5, SD 1.01), ten consecutive runs |
| 8x 64 GB, llama.cpp `-sm layer` | GLM-5.2 Q4_K_S GGUF | prefill **141 / 162 / 124 t/s** at 512 / 4k / 16k (degrades with context), decode **17.2 t/s** |
| 8x 64 GB, llama.cpp layer split, Gigabyte G292-Z20, Proxmox passthrough | GLM-5.2-Q4_K_XL fully in VRAM (320 GB reported resident) | **13-14 tok/s** single stream, collapsing to **3 tok/s** across 20 concurrent sessions |
| 4x 64 GB (256 GB) through an AliExpress x4x4x4x4 bifurcation board, every card Gen1 x4, llama.cpp layer/row split, no MTP | unsloth `GLM-5.2-UD-IQ2_XXS` | **~15 tok/s decode**, **24.07 t/s prefill**; see the log detail below |
| 3x 40 GB (120 GB), llama.cpp, almost all of the model on CPU: **one layer** plus context and compute buffers on the GPUs (18 GB of 40 GB on their own) | unsloth `GLM-5.2-GGUF`, ~460 GB MoE | **pp2048 33.44 ± 0.37 t/s, tg512 5.90 ± 0.03 t/s**. Against CPU plus DDR4 alone the tester reported only relative deltas, "TG went ~60% up" and "PP went ~30% down"; no absolute CPU-only figures were ever posted |
| 7-card rented rig, llama.cpp | GLM-5.2 | **121 t/s prefill**, judged unusable (about a 25-minute prompt-processing time); killed before decode |

The 4-card server log is worth quoting in full because it is the most completely specified
multi-card capture in the archive:

```text
n_ctx_slot = 65536, n_keep = 0
prompt eval:  13210.35 ms /  318 tokens (41.54 ms per token,  24.07 tokens/s)
       eval:   5235.97 ms /   67 tokens (78.15 ms per token,  12.80 tokens/s)
      total:  18446.32 ms /  385 tokens ; graphs reused 66
slot timings at n_decoded 100/148/196/244/292:
  tg    = 13.62 / 14.25 / 14.59 / 14.79 / 14.93 t/s
  tg_3s = 13.62 / 15.79 / 15.72 / 15.68 / 15.68 t/s
VRAM: 53G/64G, 60G/64G, 60G/64G, 56G/64G
prompt cache: 8192.000 MiB, 65536 tokens, 8589934592 est
```

### Concurrency scales badly

One concurrency sweep exists: the 8-card GLM-5.2 UD-IQ2_M report, `-np 16 -c 16384`, continuous
batching, 128 tokens per user. Every column below is tabulated in that report.

| Users | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| Aggregate | 17.3 | 21.6 | 25.7 | 28.1 | **38.9 tok/s** |
| Per user | 17.3 | 10.8 | 6.4 | 3.5 | **2.4 tok/s** |
| Batch wall time | n/a | 11.9 s | 20.0 s | 36.5 s | 52.6 s |
| Scaling versus 1 user | 1.00x | 1.25x | 1.49x | 1.62x | **2.25x** |

That is only **2.25x from 1 to 16 users**. The report root-causes it to three things together:
no PCIe or NVLink peer-to-peer, so every token is relayed through host memory seven times; a
cross-NUMA pipeline hop at the layer 49 to 50 transition; and the link itself. Note the host is
a virtualised or passthrough environment with masked GPU names, and its link reads **active
Gen1 x4 but device-max Gen2 x16**, so this one sweep is not a clean stock-card measurement.

!!! note "Superseded: 'roughly 2.4 tok/s aggregate across 16 agents'"
    A chat report from the same day and channel stated 2.4 tok/s as an *aggregate* figure. The
    accompanying benchmark report gives 38.9 tok/s aggregate and 2.4 tok/s per user
    (38.9 / 16 = 2.43). The two sources agree; only the wording differed.

---

## Why PCIe is, and is not, the bottleneck

This is the most contested question in the archive, and the dispute persists mostly because the
two sides are describing different configurations. State the claim per configuration and it
resolves cleanly.

### The physical situation

- The stock link is **Gen1 x4, about 1.0 GB/s**, and it **does not ramp under inference load**.
- There is **no peer-to-peer and no NVLink**. `torch.cuda.can_device_access_peer(i,j)` returned
  `False` for all **56 GPU pairs** on an 8-card rig, even within a PIX group; a ggml `-lv 5` log
  contained zero peer/p2p/rpc occurrences; `nvidia-smi nvlink` reports "Device does not have or
  support Nvlink". See [p2p.md](../frontier/p2p.md) and [nvlink.md](../frontier/nvlink.md).
- Consequently, with layer split on an 8-card 80-layer model (10 layers per GPU), every
  generated token makes **7 GPU to CPU RAM to GPU hops**, one of which crosses a NUMA/socket
  boundary at the layer 49 to 50 transition.

### Where it does not bite

**Single card.** Weights are resident in VRAM after load. The PCIe cost is a one-time ~30 s
model load, after which prefill and decode run at normal speed. Moving a single card from x4 to
x16 moved llama.cpp pp only 439 to 448 and tg 81.91 to 85.75. The "PCIe bandwidth is a nothing
burger" position is **correct for this case** and only this case.

**Diffusion and image or video generation.** Compute-bound and VRAM-resident, so the link never
enters the picture.

### Where it bites hard

**Prefill, not decode.** Reported on two different card families: a 170HX offload user found
prompt processing literally *faster on CPU* than with GPU offload ("PP went ~30% down because of
gen1 x4 link limit" for the three-card, one-layer-offload run that measured pp2048 33.44 t/s),
and a CMP 100-210 multi-card user with large MoE models reported "the pipeline parallelization
for decode is fine, its the prefill that kills you". Decode moved the other way on the same run,
"TG went ~60% up" against CPU plus DDR4, so GPU offload is worth it only if decode dominates your
workload. Both sides of that comparison are percentages quoted by the tester; the CPU-only
absolute rates were never posted, so do not treat any derived CPU figure as measured.

**Tensor parallelism.** The decisive A/B, Qwen2.5-72B dense AWQ on vLLM at Gen1 x4:

| Configuration | Prefill at 1k / 4k / 16k | Decode |
|---|---|---|
| 1 card | 839 / 1,092 / 960 t/s | 27.3 t/s |
| **PP2** (pipeline) | 829 / 1,084 / **1,167** t/s | 29.1 t/s |
| **TP2** (tensor) | **316 / 420 / 416** t/s | 33.7 t/s |

TP is **2.3-2.8x worse at prefill for +23% decode**. On GLM-5.2 with 8 cards the same pattern is
worse: TP8 with `enforce_eager` gives 382 / 435 / 629 t/s at 4k / 16k / 32k (about 4x worse than
PP8) and **3.4 t/s decode**; without `enforce_eager`, CUDA-graph capture crashes (vLLM issue
#48285). Multiple operators converged independently: "With PCIe 1.0 x4 link Tensor parallel is a
no go."

**Concurrency.** The 2.25x ceiling from 1 to 16 users above.

### Why pipeline parallelism survives a narrow link

Pipeline parallelism sends only the token or its activation/embedding vector between stages,
once per stage per token. Tensor parallelism splits every matrix multiply and therefore needs an
all-reduce across cards inside every layer, which is demanding on both bandwidth **and** latency
(and latency is the part a wider link does not fix). The interconnect-demand ranking that the
measurements support is:

**Tensor >> Expert > Pipeline > Data.**

Only data parallelism runs unimpaired on stock 170HX links. A **1.56x** prompt-processing gain
for two cards in pipeline-parallel mode despite the PCIe 1.0 x4 link circulated early, but it is
second-hand: it was relayed from a private group the reporter could not share, with no model,
quant or configuration given. Treat it as an anecdote, not a measurement. Pipeline parallelism
does not meaningfully improve token-generation speed; it buys capacity and prefill, not decode.
The measured PP2 gain over one card was 27.3 to 29.1 t/s decode, with prefill at 16k rising
960 to 1,167 t/s.

### The threshold for tensor parallelism, and why the Gen2 branch does not meet it

The stated threshold is **PCIe Gen2 x16 or Gen3 x4**: "Unless we can unlock at least PCIE 2 16x
or PCIE 3 4x, Tensor Parallel is out of the question." The `Gen2` branch delivers **Gen2 x4**
(roughly 2 GB/s), which is below that. Chat references to a "Gen 2 x4 lane unlock" are a
misnomer: there is no lane, width or x16 handling anywhere in `Gen2/_DIFF_vs_master.patch`.
Restoring x16 is a **physical** modification, 24 hand-soldered 0402 capacitors. See
[physical-mods.md](physical-mods.md) and [pcie-gen2.md](../unlock/pcie-gen2.md).

What Gen2 x4 buys comes from **two runs by the same tester**, neither of them a controlled A/B
with a stated methodology. Both are worth reading with their conditions attached.

**The cleaner one: a single card, model fully resident in VRAM.** A 10 GB card unlocked to 40 GB,
`unsloth/Qwen3.6-27B-MTP-UD-Q8_K_XL` on ik_llama with MTP on, described by the tester as
"all other factors unchanged":

| Test | Gen1 x4 (2026-07-22) | Gen2 x4 (2026-07-27) |
|---|---|---|
| pp512 | 203.84 ± 12.10 | **277.84 ± 19.81** |
| pp2048 | 328.81 ± 8.27 | **449.41 ± 13.44** |
| pp8192 | 363.25 ± 14.93 | **493.86 ± 16.92** |
| tg128 | 38.15 ± 0.20 | **41.52 ± 1.89** |
| tg512 | 37.69 ± 1.59 | **40.12 ± 1.52** |
| tg2048 | 36.78 ± 1.43 | **37.90 ± 0.80** |

The tester summarised it as "big PP gains" with "TG also got a nice bump", and could not explain why a
fully VRAM-resident model should move at all, guessing at MTP's CPU-side scheduling. Two caveats:
the runs are five days apart rather than back to back, and the stated purpose of the second run
was measuring a SlimSAS adapter path, not link speed.

**The multi-card one, which is not a like-for-like pair.** A three-GPU run with almost the whole
model on CPU (one layer plus context and compute buffers on the cards): pp2048
33.44 ± 0.37 t/s at Gen1 x4 on 2026-07-20, and 48.22 ± 1.36 t/s in what the tester labelled a
"gen2 x4 attempt" on 2026-07-24; tg512 5.90 to 6.39; time-to-first-response 61,253 to 42,510 ms.
The percentage deltas often quoted from this pair (+44.2% prefill, -30.6% latency) are computed
here, not stated by the tester, and the two runs are not quant-matched: the later one is labelled
`GLM-5.2-GGUF-Q4` where the earlier is unlabelled `GLM-5.2-GGUF`. A `GLM-5.2-UD-Q2_K_XL` run on
the same rig at Gen2 x4 gave pp2048 49.00 ± 1.08 and tg512 6.81 ± 0.06. The tester's own verdict
was cautious: "with gen2 x4 PP is at least not worse, but I feel like I'm still getting pegged by
bandwidth".

Direction across both: prefill and latency improve, decode moves much less. That is the shape the
pipeline-parallel model predicts, but neither run isolates link speed cleanly.

!!! question "Open problem: nobody has re-run the parallelism A/B at Gen2 x4"
    Every parallelism comparison in this domain ran at Gen1 x4. The two Gen2 x4 inference
    datasets above come from one tester, and neither is a pipeline-versus-tensor comparison.
    Others repeatedly noted "didn't try the pcie 2.0 yet". The cleanest single-variable
    experiment available is the 4-card bifurcation rig above (fully documented configuration)
    running the identical GLM-5.2 UD-IQ2_XXS workload with the `Gen2` branch installed.

!!! question "Open problem: does lane count matter once weights are resident?"
    Asked directly and answered only with opinions ("any additional bandwidth is more than
    welcome", "use MoE models", "PCI-e 3.0 x16 would be more than enough for multi-GPU"). It is
    blocked on hardware: no x16 card was available to the people asking. The one long-context
    prefill-versus-width number in the corpus, roughly 6,000 down to 3,000 t/s moving x16 to x8
    at 64k context, was measured on a different, non-170HX card and does not transfer. The CMP
    x4-versus-x16 llama.cpp comparison quoted earlier is short-context and single-card, so it
    does not settle the long-context case either.

### Mitigations that are actually supported

- **Prefer MoE models.** They reduce cross-device activation traffic per token, which is the
  recommended mitigation for the lack of NVLink. Reasoned rather than isolated by benchmark, but
  consistent with everything measured.
- **Use pipeline parallelism, always.**
- **Batch on one card rather than sharding across cards** where the model fits.

---

## What breaks

| Symptom | Cause | Fix |
|---|---|---|
| Weights load CPU-only then OOM | prebuilt `libggml-cuda.so` needs `libcudart.so.13` / `libcublas.so.13`; host has CUDA 12.4 | prepend PyTorch's bundled cu13 libraries to `LD_LIBRARY_PATH` |
| vLLM import fails, no `vllm._C` | `VLLM_USE_PRECOMPILED` editable install | 0.20.2 release wheel + PR #38476 python diff onto site-packages |
| vLLM does not recognise `glm_moe_dsa` | `transformers` 4.57 | `transformers` 5.x |
| GLM-5.2 MoE kernels reject the quant | asymmetric quantisation (`cyankiwi/GLM-5.2-AWQ-INT4`, asym g32) | symmetric quants: `lowbitcoffee/GLM-5.2-W4A16`, `QuantTrio/GLM-5.2-Int4-Int8Mix` |
| GLM-5.2 prefill collapses to ~120-160 t/s | llama.cpp has no DSA support and falls back to dense attention (llama.cpp issue #24730) | use vLLM with `TRITON_MLA_SPARSE` |
| vLLM TP8 crashes during CUDA-graph capture | vLLM issue #48285 | `enforce_eager` avoids the crash but costs ~4x prefill; use PP instead |
| MTP + pipeline parallelism refuses to run | currently incompatible in vLLM | none known; MTP + TP8 goes straight to OOM |
| SGLang will not run MTP | "sglang doesnt like mtp" | use vLLM or llama.cpp for MTP |
| Loader pins RSS and thrashes disk until OOM | llama.cpp's load-time compute-graph pass thrashes system RAM | more host RAM (see below); `swapon` is blocked inside containers |
| Model loading hangs after ~20 GB | the 80 GB geometry | revert to the shipping 40 GB profile |

!!! danger "The 80 GB profile gives you less usable memory, not more"
    Under the experimental `80` branch, model loading hung after roughly 20 GB and even models
    that previously fit the 40 GB unlock stopped loading; a second tester saw failures in the
    40-60 GB range. Reverting to the 40 GB geometry restored working loads. Note also that the
    branch's `constants.yaml` advertises `lmr: 0x0000028B` but the build never reads that file:
    `80/driver/build.sh` line 93 sets `LMR="0x0000028A"`, so every tester who ran that branch
    actually programmed CFG1 `0x02779000` + LMR `0x0000028A` + `fb_length 0x0000001400000000`, a
    three-way inconsistency that is itself the likely cause of the instability. See
    [80gb.md](../frontier/80gb.md).

---

## Model sizing and host requirements

| Question | Answer |
|---|---|
| Does Qwen3.6 27B bf16 fit a 64 GB card? | Yes, at roughly **54-56 GB**, leaving almost no KV headroom. The Q4_K_M quant of the same model is **18-24 GB** |
| Is going above q4 worth it? | In-channel judgement backed by unspecified benchmarks: not clearly. On a 64 GB card the KV headroom matters more |
| How much host RAM? | **At least ~256 GB** for very large models. A GLM-5.2 4-bit 467 GB model could not load on an 88 GiB-RAM host **even with 512 GiB of VRAM available**: weights reached a ~431 GiB VRAM plateau (405 GiB model plus KV/overhead) but the loader pinned RSS at **87.6 GB** with continuous **~820 MB/s disk re-reads** until OOM. Reproduced across raw `llama-server` and an Unsloth studio run, and across `-c 1024` / `-c 8192`, no-warmup and batch tuning |
| Model load time? | ~30 s for a single card at Gen1; ~6 min for a 239 GB model across 8 cards; ~440-620 s for GLM-5.2 under vLLM. Over RPC, 20-60 min for a >=500B model at Q4-6, and 4-6 hours for a Kimi K3-class model across 170HX cards |
| How many cards for Kimi K3? | ~1.4T weights in MXFP4 (e2m1) with MXFP8 activations is **4.25 bits per weight** (4 for the weight, 0.25 for an 8-bit scale per 32 weights), so about **744 GB of weights, twelve 64 GB cards' worth**. The in-channel estimates were off-the-cuff and higher: "so... 25 cards XD" for pipeline-parallel only and "more like 32 to account for inefficiencies, kv cache, and a reasonable parallelism setup". Nobody reconciled the arithmetic, and the tp8 half of that estimate does not hold at Gen1 x4. GA100 handles the group scales via the Marlin kernel |

!!! note "VRAM alone is not the binding constraint on model choice in this range"
    Going from 40 GB to 84 GB let one user run the same 27B model with only a longer context.
    Two others corroborated: "even with an 8x64 and 512GB, LLMs like deepseek pro still cant
    run", and "I think 27b unmatched up to like 200gb". This is a statement about the model
    landscape at these sizes, not about the hardware. The counterpoint offered was bigger quants
    and unquantised context.

---

## Where the card sits against other hardware

| Reference | Figure | Notes |
|---|---|---|
| RTX 3090, Qwen 27B q4_k_m | 60 tok/s with MTP, 40 without, prefill ~1,200 t/s | the comparison baseline used in-channel |
| 170HX versus 3090 | roughly 3090-class for single-stream decode on **dense** models, with far more VRAM; **above** the 3090 on MoE prefill; **below** it on MoE decode, which is bandwidth-bound | the "3090-class" characterisation is disputed and both sides are probably right for different model classes |
| Two 170HX versus one RTX 5090, image and video | "A little bit slower, but same power draw and would let you run concurrent tasks in 2 separate comfyui containers" | one tester on rented hardware, screenshots only, never reproduced: low confidence |
| A100, GLM-5.2 | 55 tok/s | second-hand, no configuration, low confidence |

!!! note "Superseded: '13 tok/s on 8x 170HX versus 55 tok/s on a single A100'"
    Reported second-hand and explicitly labelled unoptimised. The estimate offered at the time
    was that an optimised setup "should hit 30 tok/s lower bound". The measured PP8 vLLM decode
    came in at **30.2 t/s** the next day. Cite 13 tok/s only as the llama.cpp / unoptimised
    baseline.

---

## Non-LLM CUDA workloads

Diffusion and image generation are a strong fit: INT8 convolution "is fast and works well on the
cmp170 in ComfyUI", and an owner coming from Pascal called it "a speed demon". The mechanism is
that the workload is compute-bound and fits entirely in VRAM, so the Gen1 x4 link does not bite,
and diffusion tolerates low-precision noise better than language models because errors do not
compound the same way. One caveat raised: diffusion-transformer weights have worse outliers than
LLM weights, so W8A8-style quantisation is not automatically safe. Measured diffusion numbers are
tabulated on [performance.md](performance.md).

Video generation works: LTX 2.3 on a single unlocked card produced roughly a **30-second clip in
about 2 minutes** with "zero optimization going", the card running 250 W sustained under a
USB-controlled blower and staying below 65 C. That report gives no resolution, frame count or
step count, so it is low-to-medium confidence.

A six-GPU 10 GB to 40 GB host was verified serving **five concurrent vLLM OpenAI-compatible
endpoints** (GPUs 0-4, one model each: `Qwen/Qwen2.5-7B-Instruct-AWQ`,
`cyankiwi/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit`, `Qwen/Qwen2.5-32B-Instruct-AWQ`,
`Qwen/Qwen2.5-VL-32B-Instruct-AWQ`, `Qwen/Qwen2.5-Omni-7B-AWQ`) plus ComfyUI on GPU 5. That was
explicitly a concurrency smoke test, not a benchmark.

!!! question "Open problem: 3D Gaussian splat training"
    Predicted poor rather than measured poor. Splats have few dense matrix multiplies and
    generally do not use lower-precision formats, so they run on standard CUDA cores where the
    card is ~12 TFLOPS FP32, roughly a 3060. Nobody has run an actual splat benchmark.

---

## Open questions

1. **Get MTP working with pipeline parallelism in vLLM.** The benchmark report projects
   "~1.7x decode (30 to ~50 t/s) on PP8" if the unmerged fix in RFC #44697 lands; the same
   author later said in chat that MTP "should push GLM 5.2 closer to 45 t/s". Both are
   projections from the measured 30.2 t/s, not measurements.
2. **Re-run the parallelism A/B at PCIe Gen2 x4** on the documented 4-card bifurcation rig.
3. **Answer x4 versus x16 at Gen2 with numbers.** Blocked on hardware.
4. **Reconcile the ~27B single-card decode figures** by running one published configuration
   verbatim.
5. **Explain the vLLM long-context regression:** one tester saw vLLM fall to 22 tok/s at ~130k
   context while llama.cpp held 48 tok/s on the same card, with MTP on both, after vLLM led
   90 versus 60 at normal context. The 8-card result shows vLLM prefill *improving* with
   context, so a configuration cause is likely. Nobody reproduced it.
6. **Determine whether P2P can be enabled at all.** The unlocker already reaches SEC2/PLM
   registers; whether a P2P-capability bit lives in the same space the FEAT PLM at `0x00823804`
   governs has never been checked.
7. **Colibri-style expert placement**, executing non-resident MoE experts on the CPU directly
   from RAM instead of uploading them over the slow link. Suggestive prior evidence: prefill is
   already faster on CPU than with GPU offload on this link.
8. **Whether the memory unlock slightly slows already-unthrottled compute** through refresh
   collisions. Nobody has run the before/after because the installer applies both unlocks
   together.

See [open-questions.md](../frontier/open-questions.md),
[multi-gpu.md](../procedures/multi-gpu.md) and [dead-ends.md](../history/dead-ends.md).
