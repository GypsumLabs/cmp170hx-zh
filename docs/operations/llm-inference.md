# 在 CMP 170HX 上运行 LLM

**本页涵盖的内容。** 哪些推理栈能在解锁后的显卡上运行；在明确给出模型、量化方式和上下文长度的情况下，提示处理和 token 生成速率分别是多少；哪些情况会出问题以及原因；如何扩展到多张卡；以及决定几乎所有多卡方案的那个问题：PCIe 带宽是否构成瓶颈。原始算力和带宽数据见[性能](performance.md)，时钟和功耗数据见[调优](tuning.md)。

**三个结果几乎决定了你会做出的每个选择。**

1. **在一张卡和同一个模型家族上，vLLM 大约比 llama.cpp 快 1.8 倍**，同时也快于 SGLang。这个比值来自一位测试者，而且两边使用的量化方式并不匹配，所以应把它视为趋势，而不是固定常数。
2. **跨卡时必须使用流水线并行；在 PCIe Gen1 x4 下，张量并行是一条失败路线。** 对 Qwen2.5-72B AWQ 的直接 A/B 测试显示：TP2 的 prefill 慢了 **2.3-2.8 倍**，只换来 23% 的 decode 提升。
3. **目前记录中最好的多卡结果**，是一个 744B 参数的 MoE（GLM-5.2，40B active），在 8 张解锁后的 64 GB 卡上使用 vLLM 流水线并行运行：上下文长度为 131k 时 **prefill 达到 2,675 t/s，decode 达到 30.2 t/s**，整个会话没有发生硬故障。

除非另有说明，下面所有数据都在 **PCIe Gen1 x4** 下测得。发布版解锁器完全不包含 PCIe 代码：`master` 中的 `common/constants.yaml` 只有 `driver_versions`、`gpu`、`compute` 和 `profiles` 这几个键，整个代码树中也没有 `pcie` 节。凡是描述为使用发布版解锁器运行的基准测试，使用的都是显卡出厂时的链路。

> [!WARNING]
> **如何理解本页中的数字**
>
> 这里几乎每个数字都来自**一位测试者、一张卡、一个会话**。独立复现的情况很少；一些曾经被当作不同确认的行，后来证明其实是同一张表中的两行，或者只是报告附上十分钟后在聊天中的总结。如果一个数字有多个来源，正文会明确说明；如果没有特别说明，就应假定它来自单一报告。模型、量化方式、上下文长度和测试条件也会逐个数字注明，原因同样在此。

---

## 解锁能为推理工作负载带来什么

算力解锁（将 FEAT PLM `0x00823804` 打开到 `0xffffffff`，然后将 SS0 `0x0082381C` 写为 `0x88888888`、SS1 `0x00823820` 写为 `0x00000008`）让张量核吞吐能力真正可用。参见[算力节流](../unlock/compute-throttle.md)。

- **使用出厂 SM80 构建的 `llama.cpp` 会自动使用 GA100 张量核。** 不需要补丁，也不需要额外标志。这正是多位测试者在未修改的最新构建中，将 SM80（以及 SM86）加入 CUDA 架构列表后，得到每秒数千 token 的提示处理速率的原因。
- **解锁后的显存确实可用。** 一位在 64 GB 卡上运行 LLM 的测试者报告称 "havent had a single crash"（一次崩溃都没有）。六张解锁到 40 GB 的 10 GB 卡以 4-bit 运行 Qwen 27B 和 Qwen 35B，既没有崩溃，也没有卡变砖；唯一的限制是散热，在没有足够散热方案时只能运行约 10 分钟。参见[散热](cooling.md)。
- **解锁后的快速健全性检查：** 使用 LM Studio 运行一个小模型；对于名为 "E2B" 的小模型，预期速率约为 **85 tokens/s**。这是某位测试者给出的数据，而且模型大小没有完全说明，因此只能把它当作数量级检查，不能当作目标值。严格的检查方法是将 BF16 吞吐量与 202 TFLOPS 上限进行比较；参见[验证](../procedures/verify.md)。

---

## 后端选择

| 后端 | 在这款硬件上的结论 | 证据 |
|---|---|---|
| **vLLM** | 在几乎所有测过的配置中都是最好的默认选择。 | 一位测试者在单卡上对 Qwen3.6 27B 同时运行两者后称其“快约 1.8 倍”。量化对等关系尚未确认：llama.cpp 一侧使用 Q4_K_M，vLLM 一侧的量化方式从未说明，频道内推测为 q6。归档的 vLLM 表显示，Qwen3.6-27B 单流为 62.4 t/s；与 36.87 t/s 相比是 1.69 倍。它也是唯一能以可用速度运行 GLM-5.2 的栈。 |
| **llama.cpp** | 适合单卡，也适合跨卡运行非 DSA 模型；无法使用 DSA 注意力模型。 | 单卡 pp512 为 888.09 t/s；8 卡运行 GLM-5.2 时 prefill 为 141 t/s，而 vLLM 为 2,675 t/s。 |
| **ik_llama** | 在唯一一次受控对比中慢于主线 llama.cpp。 | pp512 为 296.36，对比 360.65；tg128 为 33.20，对比 33.10。 |
| **SGLang** | 在单卡运行 Qwen3.6 27B int8 时输给 vLLM，与预期相反；而且完全无法运行 MTP。 | 带截图的头对头测试。 |
| **LM Studio / llama-swap** | 可以正常工作，适合冒烟测试和提供服务。 | 小模型约 85 t/s；125 W 功耗上限下运行 35B A3B Q8 为 60 t/s。 |
| **Vulkan** | 多卡是一条失败路线。 | ggml Vulkan 后端不支持 `VK_KHR_device_group`，因此所有卡间传输都要经过主机 RAM。 |

### 为这张卡构建 llama.cpp

有人发布了一个可复现的容器构建脚本 `build-llama-170hx.sh`：

```bash
# 基础镜像：nvidia/cuda:13.3.0-devel-ubuntu26.04
# 在已解析的 master 提交上克隆 ggml-org/llama.cpp
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
# 确认 libggml-cuda.so 没有缺失的 ldd 条目，使用 llama.cpp 构建编号标记镜像，然后通过 --runtime=nvidia --gpus all 进行冒烟测试：
nvidia-smi --query-gpu=name,memory.total,pcie.link.gen.current,pcie.link.gen.max --format=csv
llama-bench --list-devices
```

`-DCMAKE_CUDA_ARCHITECTURES=80` 是决定成败的关键标志：CUDA capability 8.0 对应 GA100。

> [!CAUTION]
> **预构建的 `libggml-cuda.so` 需要 CUDA 13，没有它会静默失败**
>
> 预构建二进制链接了 `libcudart.so.13` 和 `libcublas.so.13`。如果主机只有 CUDA 12.4，权重会**以 CPU-only 方式加载，随后发生 OOM**，而不是干净地报告错误，因此很难诊断。可行的修复方法是将 PyTorch 捆绑的 cu13 库放到 `LD_LIBRARY_PATH` 的最前面。

`llama.cpp` 还通过 `--split-mode tensor`（上游 PR `ggml-org/llama.cpp#19378`）获得了与后端无关的张量并行，从而移除了 GPU 数量必须为偶数或 2 的幂的限制。该 PR 自己也将此功能描述为 "experimental ... not yet production ready"（实验性功能，尚未达到生产就绪状态）。vLLM 的张量并行仍然要求 GPU 数量为偶数；而且在这张卡上，张量并行本来就是错误的策略（见下文）。

---

## 单卡实测吞吐

### vLLM：一张解锁后的 64 GB 卡

测试形状大致为 1,500 个 token 的提示和 200 个 token 的输出。

| 模型 | Decode | 4 路并行时的聚合速率 | Prefill |
|---|---|---|---|
| `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`（MoE） | **113 tok/s** | **452 tok/s** | **1,700 tok/s** |
| `Qwen3-32B-AWQ`（dense） | 52.9 tok/s | 205 tok/s | 1,755 tok/s |
| Qwen3.6-27B BF16 | 19.2 tok/s | 71.1 tok/s | 2,231 tok/s |
| Qwen3.6-27B-AWQ-INT4 | 58.5 tok/s | 214.8 tok/s | 2,044 tok/s |

### llama.cpp：一张解锁后的卡

| 基准测试 | 模型 / 条件 | 结果 |
|---|---|---|
| `llama-bench` pp512 | qwen35 27B Q4_K_M，15.65 GiB，26.90 B 参数，CUDA，`ngl 99`，一张卡 | **888.09 ± 24.69 t/s** |
| `llama-bench` tg128 | 同一张表的第二行，同一次运行，同一张截图 | **36.87 ± 0.04 t/s** |
| 社区参考基准 | Llama-2 7B Q4_0，在频道内被建议作为标准量化方式 | **pp 3106 t/s，tg 158 t/s**，一份数字报告。第二位测试者发布了截图但没有引用具体数字，并同意这些数字“fine”；第三位测试者称 "I get 3333 on 7b"，但没有说明量化方式。 |
| dense 与 sparse 对比 | Gemma4 26B A4B Q8（sparse）pp2048 为 3894.29，而 Gemma4 31B Q8（dense）pp2048 为 830.33，硬件和构建相同 | 差异来自模型密度，而不是配置错误。 |
| 按模型划分的 Decode | Qwen3.5 9B q4_k_xl 约 105 tok/s；Qwen3.6 27B q8，使用 q8 KV 和 MTP depth 2，50 tok/s；Gemma4 26B A4B Q8 的 tg128 / tg512 / tg1024 为 90.65 / 90.10 / 89.85；Gemma4 31B Q8 的 tg128 / tg512 / tg1024 为 27.07 / 26.74 / 26.33 | 单卡。 |

888.09 / 36.87 这一对数字来自**同一次运行**：一张截图中单个 `llama-bench` 表的两行。后来，另一位参与者重新发布了同一段对话的截图，称这次运行与自己的数字一致，但从未公布被对照的数字，因此没有第二张表可供比较。

Dense 27B 级模型的提示处理速度比 7B 慢一个数量级；这源于模型密度，而不是调优失败。在未打补丁的 SM80/SM86 构建上，dense Qwen3.6 27B q4_k_p 的 pp 约 500 t/s 和约 900 t/s 都有人报告过。

### 最严格的受控单卡基准测试

测试对象是一张解锁到 40 GB 的 10 GB 卡，链路为 Gen1 x4，功耗上限为 250 W。主机配置：2x EPYC 7713、DDR4、Supermicro H12DSi-N6、kernel 6.18.38。模型为 `unsloth/Qwen3.6-27B-MTP-GGUF`（`UD-Q4_K_XL` 和 `UD-Q8_K_XL`）；Q4 使用了 40960 MiB 中的 17464 MiB，Q8 使用 35718 MiB，空闲功耗约 42 W。一位测试者在一张卡、一个会话中完整发布了带误差棒的数据；没有人重新运行过这项测试。

| 构建 / 配置 | pp512 | pp2048 | pp8192 | tg128 | tg512 | tg2048 |
|---|---|---|---|---|---|---|
| llama.cpp b10095（e8e6c7af2），Q4，无 MTP | 360.65 | 564.30 | 722.49 | 33.10 | 32.67 | 30.50 |
| 相同配置，启用 MTP（`--spec-type draft-mtp --spec-draft-n-max 2`） | 323.63 | 496.85 | 639.53 | 46.24（峰值 56.67） | 43.02（峰值 55.33） | 44.47（峰值 59.00） |
| ik_llama b4735（9d07d868），Q4，无 MTP | 296.36 | 544.72 | 649.61 | 33.20 | 34.23 | 31.93 |
| ik_llama，Q4，MTP（`--spec-type mtp:n_max=2,p_min=0.0`） | 203.38 | 315.87 | 336.61 | 41.11（峰值 47.00） | 38.26（峰值 47.67） | 35.82（峰值 46.67） |
| ik_llama，Q8，无 MTP | 271.49 | 584.31 | 697.18 | 26.36 | 27.27 | 25.79 |
| ik_llama，Q8，MTP | 203.84 | 328.81 | 363.25 | 38.15 | 37.69 | 36.78 |

### 单卡级别的功耗和效率

| 条件 | 结果 |
|---|---|
| Qwen3.6 27B `q6_k_xl`（驻留 41 GB），故意受限的主机（无 AVX2 CPU，显卡限制在 250 W，PCIe x4） | 约 26 tok/s，启用 MTP 后升至**先 50、再 55 tok/s**。 |
| `Qwen-AgentWorld-35B-A3B-Q8_0.gguf`，通过 llama-swap 使用 llama.cpp，**125 W 功耗上限** | 约 60 tok/s。 |
| Qwen3.6-35B-A3B Q8，启用 MTP，**170 W** | 约 130 tok/s。 |
| vLLM，Qwen3.6 27B int8 | **每瓦 2.16 tok/s**；频道内将其描述为 "actually decent efficiency"（效率确实不错）。 |

功耗上限和 MTP 都会显著改变结果。参见[调优](tuning.md)。

> [!NOTE]
> **未解问题：27B 单卡 decode 数字尚未统一**
>
> 已发布数据和频道内关于“Qwen 27B 级模型、单张解锁后的 64 GB 卡、vLLM”的结果横跨 **97 / 90 / 75 / 58.5 t/s**，另有 llama.cpp Q4_K_M 的 36.87 t/s。不同报告使用的量化方式、MTP 状态、上下文长度和 vLLM 版本各不相同，也从未保持一致。只要在一张卡上原样运行已发布的仓库配置并公布命令行标志，这个问题就能得到解决。

---

## 多 token 预测（MTP）

对于同一个 35B MoE，MTP 在两个后端上的表现**正好相反**。

| 后端 | 不启用 MTP | 启用 MTP | 变化 |
|---|---|---|---|
| llama.cpp（`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`） | 108.4 tok/s | **131.3 tok/s** | **+21%** |
| vLLM（同一模型类别） | 147 tok/s | **113 tok/s** | **-23%**，尽管接受率为 75% / 1.75 tokens |

在受控的 40 GB 主机上，MTP 带来了约 **40% 的 decode 提升，同时提示处理下降约 10%**（tg128 从 33.10 升到 46.24，而 pp8192 从 722.49 降到 639.53）。这项收益**只适用于单流**；另有一条单独的警告称 MTP 随 batch size 扩展得不好，但那是推断而非测量结果。

研究者围绕三个假设追踪了 vLLM 的性能回退。首先排除了 MTP 头量化问题（`mtp` 位于 `modules_to_not_convert` 中，fc、attention 和 shared expert 全部为 BF16）；其次怀疑是错误的 FlashInfer cubin。当前最可信的解释是 CPU 侧瓶颈："it utilizes the CPU and as we are on PCIe Gen1 4x this becomes the bottleneck. GPU-Compute Utilization goes down by 7% and Mem Usage as well."（它会使用 CPU，而当前处于 PCIe Gen1 4x，因此这里成了瓶颈。GPU-Compute 利用率下降了 7%，Mem Usage 也一样。）建议的监控命令如下：

```bash
nvidia-smi dmon -s put      # 观察 sm、mem、rx/txpci
```

这个解释从未通过修复问题得到验证。

---

## 多卡：头条结果及其配置

一个 744B 参数的 MoE（GLM-5.2，40B active）采用 W4A16 对称量化，在 **8 张解锁后的 64 GB 卡**上使用 vLLM 流水线并行运行；驱动版本为 610.43.02，链路为 PCIe Gen1 x4（没有电容改装，并且早于 Gen2 合并），硬件为租用设备。

| 指标 | 数值 |
|---|---|
| 上下文长度为 4k / 32k / 65k / 131k 时的 Prefill | 665 / 1,497 / 2,342 / **2,675 t/s** |
| Decode（无 MTP） | **30.2 t/s** |
| KV 容量 | 在 0.92 的显存利用率下为 438,107 个 token（BF16 KV；MLA 下约为 88-100 KB/token） |
| 模型加载时间 | 约 440-620 s |
| 故障 | 整个会话零硬故障 |

由于采用了分块 prefill 和稀疏注意力，Prefill 会随上下文长度**增加**。这与 llama.cpp 在同一模型上的行为相反，也是最清晰的单一信号，表明在这里推理栈的选择比硬件更能决定结果。

这**不是两份报告，而是一份报告**。一位测试者租用了九张卡，在其中八张上进行基准测试，附上 `170HX-benchmark-results.md`（131k 上下文下 prefill 为 2,675 t/s、decode 为 30.2 t/s），并在十分钟后于聊天中将同一次运行总结为 "2600 t/s prefill, 30 t/s decode"。取整后的数字和精确数字来自同一个会话。没有人在其他卡上复现过这项结果。

### 精确配置

```text
vllm==0.20.2  release wheel
  + 将 PR #38476 的 python 文件作为 diff 应用到 site-packages
transformers 5.x                       （4.57 不认识 glm_moe_dsa）
VLLM_ATTENTION_BACKEND=TRITON_MLA_SPARSE
VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0
--pipeline-parallel-size 8 --gpu-memory-utilization 0.90
block-size 64                          （由 DEEPSEEK_V32_INDEXER 自动设置）
quantisation: W4A16 symmetric
```

GLM-5.2 使用 DeepSeek 稀疏注意力（DSA），原生需要 Hopper 或 Blackwell。要在 Ampere 上运行它，必须使用来自 vLLM PR #38476 的 `TRITON_MLA_SPARSE` 后端。

> [!CAUTION]
> **量化选择：大多数已发布的指南都不适用于这条路径**
>
> 对于 vLLM 上的 GLM-5.2，MoE 内核会**拒绝非对称量化**。
> 可用：`lowbitcoffee/GLM-5.2-W4A16`（对称、g128、388 GB）和 `QuantTrio/GLM-5.2-Int4-Int8Mix`。
> **失败：`cyankiwi/GLM-5.2-AWQ-INT4`**（非对称、g32），大多数指南引用的正是这种量化。

> [!WARNING]
> **实验性：`VLLM_USE_PRECOMPILED` 在这里无法工作**
>
> 应用 vLLM 补丁的通常方式，是使用 `VLLM_USE_PRECOMPILED` 进行可编辑安装。但这种方式不会提供 `vllm._C`，因此会失败。应使用 0.20.2 release wheel，并将 PR 中的 python 文件作为 diff 应用到 site-packages。

### 其它多卡结果

| 配置 | 模型 / 栈 | 结果 |
|---|---|---|
| 8x 64 GB（512 GiB），llama.cpp b10079，`-ngl 999 -c 4096 -np 1 --flash-attn on --no-context-shift --fit off --no-warmup --spec-type none`；虚拟化主机，GPU 名称被屏蔽，链路为 active Gen1 x4，但设备最大为 Gen2 x16 | GLM-5.2 UD-IQ2_M，239 GB、2-bit，约 224 GiB 驻留，加载约 6 分钟 | TG **17.33 tok/s**（17.31-17.37，SD 0.02）；PP **113.0 tok/s**（111.8-115.5，SD 1.01），连续运行十次。 |
| 8x 64 GB，llama.cpp `-sm layer` | GLM-5.2 Q4_K_S GGUF | 在 512 / 4k / 16k 下 prefill 为 **141 / 162 / 124 t/s**（随上下文长度增加而下降），decode 为 **17.2 t/s**。 |
| 8x 64 GB，llama.cpp layer split，Gigabyte G292-Z20，Proxmox passthrough | GLM-5.2-Q4_K_XL 完全驻留 VRAM（报告称驻留 320 GB） | 单流 **13-14 tok/s**；20 个并发会话时降至 **3 tok/s**。 |
| 4x 64 GB（256 GB），通过 AliExpress x4x4x4x4 bifurcation board 连接，每张卡 Gen1 x4，llama.cpp layer/row split，无 MTP | unsloth `GLM-5.2-UD-IQ2_XXS` | **约 15 tok/s decode**、**24.07 t/s prefill**；详见下方日志。 |
| 3x 40 GB（120 GB），llama.cpp，模型几乎全部在 CPU 上：GPU 上只有**一层**以及上下文和算力缓冲区（每张卡 40 GB 中自身占用 18 GB） | unsloth `GLM-5.2-GGUF`，约 460 GB 的 MoE | **pp2048 33.44 ± 0.37 t/s，tg512 5.90 ± 0.03 t/s**。与仅使用 CPU 加 DDR4 的结果相比，测试者只报告了相对变化：“TG went ~60% up”（TG 上升约 60%）和 “PP went ~30% down”（PP 下降约 30%）；从未公布 CPU-only 的绝对数字。 |
| 7 卡租用主机，llama.cpp | GLM-5.2 | **121 t/s prefill**，被判定为不可用（提示处理约需 25 分钟）；在 decode 前被终止。 |

4 卡服务器日志值得完整引用，因为它是档案中配置说明最完整的多卡捕获记录：

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

### 并发扩展性很差

目前只有一份并发扫描：8 卡 GLM-5.2 UD-IQ2_M 报告，配置为 `-np 16 -c 16384`，使用 continuous batching，每位用户生成 128 个 token。下面的每一列都来自那份报告中的表格。

| 用户数 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| 聚合速率 | 17.3 | 21.6 | 25.7 | 28.1 | **38.9 tok/s** |
| 每用户速率 | 17.3 | 10.8 | 6.4 | 3.5 | **2.4 tok/s** |
| 批处理墙钟时间 | n/a | 11.9 s | 20.0 s | 36.5 s | 52.6 s |
| 相对于 1 个用户的扩展 | 1.00x | 1.25x | 1.49x | 1.62x | **2.25x** |

从 1 个用户增加到 16 个用户，聚合速率只有 **2.25 倍**。报告认为原因是三个因素共同作用：没有 PCIe 或 NVLink P2P，因此每个 token 都要经过主机内存中继七次；第 49 层到第 50 层的过渡存在一次跨 NUMA 的流水线跳转；以及链路本身的限制。需要注意的是，主机处于虚拟化或 passthrough 环境，GPU 名称被屏蔽；它报告的链路为**当前 active Gen1 x4，但设备最大为 Gen2 x16**，所以这次扫描并不是一次干净的出厂卡测量。

---

## PCIe 为什么有时是瓶颈，有时又不是

这是档案中争议最大的问题，争议之所以持续，主要是因为双方描述的是不同配置。只要按配置分别陈述结论，问题其实很清楚。

### 物理情况

- 出厂链路为 **Gen1 x4，约 1.0 GB/s**，并且**不会在推理负载下提速**。
- 没有 **P2P，也没有 NVLink**。在一台 8 卡主机上，`torch.cuda.can_device_access_peer(i,j)` 对全部 **56 个 GPU 对**都返回了 `False`，即使它们位于同一个 PIX 组内也一样；一份 ggml `-lv 5` 日志中完全没有出现 peer/p2p/rpc；`nvidia-smi nvlink` 报告 "Device does not have or support Nvlink"。参见[P2P](../frontier/p2p.md)和[NVLink](../frontier/nvlink.md)。
- 因此，在一台 8 卡、80 层的模型上进行 layer split 时（每张 GPU 分 10 层），每个生成的 token 都要经历 **7 次 GPU 到 CPU RAM 再到 GPU 的跳转**，其中一次会在第 49 层到第 50 层之间跨越 NUMA/socket 边界。

### 它不会造成明显影响的地方

**单卡。** 权重加载完成后会驻留在 VRAM 中。PCIe 的代价只是一次性约 30 s 的模型加载时间，之后 prefill 和 decode 都以正常速度运行。将单卡的链路从 x4 换为 x16，只让 llama.cpp 的 pp 从 439 变为 448、tg 从 81.91 变为 85.75。“PCIe bandwidth is a nothing burger”（PCIe 带宽根本不重要）这一观点**对这种情况是正确的**，但只适用于这种情况。

**扩散、图像和视频生成。** 这些工作负载受算力限制，并且驻留在 VRAM 中，所以链路不会成为影响因素。

### 它会造成严重影响的地方

**Prefill，而不是 decode。** 两种不同卡家族上都有相关报告：一位 170HX offload 用户发现，提示处理在 CPU 上实际上比 GPU offload 更快（在一次三卡、只向 GPU offload 一层、测得 pp2048 为 33.44 t/s 的运行中，报告称 “PP went ~30% down because of gen1 x4 link limit”）；一位使用大型 MoE 模型的 CMP 100-210 多卡用户则称 “the pipeline parallelization for decode is fine, its the prefill that kills you”（decode 的流水线并行没问题，真正拖垮性能的是 prefill）。同一次运行中的 decode 变化方向相反：相对于 CPU 加 DDR4，报告称 “TG went ~60% up”。因此，只有当工作负载以 decode 为主时，GPU offload 才值得采用。这组对比的两边都是测试者给出的百分比；CPU-only 的绝对速率从未公布，所以不要把任何推导出的 CPU 数字当成测量结果。

**张量并行。** 决定性的 A/B 测试是在 Gen1 x4 下，使用 vLLM 运行 Qwen2.5-72B dense AWQ：

| 配置 | 1k / 4k / 16k 下的 Prefill | Decode |
|---|---|---|
| 1 卡 | 839 / 1,092 / 960 t/s | 27.3 t/s |
| **PP2**（流水线并行） | 829 / 1,084 / **1,167** t/s | 29.1 t/s |
| **TP2**（张量并行） | **316 / 420 / 416** t/s | 33.7 t/s |

TP 的 prefill **慢了 2.3-2.8 倍，只换来 23% 的 decode 提升**。在 8 卡运行 GLM-5.2 时，情况更加严重：启用 `enforce_eager` 的 TP8 在 4k / 16k / 32k 下为 382 / 435 / 629 t/s（比 PP8 慢约 4 倍），decode 只有 **3.4 t/s**；不启用 `enforce_eager` 时，CUDA-graph 捕获会崩溃（vLLM issue #48285）。多位操作者独立得出了相同结论：“With PCIe 1.0 x4 link Tensor parallel is a no go.”（在 PCIe 1.0 x4 链路上，张量并行不可行。）

**并发。** 上文从 1 个用户到 16 个用户时只有 2.25 倍的上限。

### 为什么流水线并行能在窄链路上工作

流水线并行只在阶段之间传输 token，或者传输其 activation/embedding 向量，并且每个阶段每个 token 只传输一次。张量并行会拆分每一次矩阵乘法，因此每一层内部都需要在卡之间执行 all-reduce，同时对带宽和**延迟**提出要求（而延迟是单纯加宽链路无法解决的部分）。测量结果支持以下互连需求排序：

**Tensor >> Expert > Pipeline > Data。**

只有数据并行能在 170HX 的出厂链路上不受影响地运行。早期曾流传一个说法：在 PCIe 1.0 x4 链路下，流水线并行使用两张卡时，提示处理速度比单卡提升 **1.56 倍**；但这是二手信息，来自一个无法分享来源的私人群组，也没有给出模型、量化方式或配置。应把它视为轶闻，而不是测量结果。流水线并行不会明显提升 token 生成速度；它带来的是容量和 prefill，而不是 decode。实测 PP2 相对于单卡的 decode 只从 27.3 升到 29.1 t/s，16k 下的 prefill 则从 960 升到 1,167 t/s。

### 张量并行的阈值，以及 Gen2 x4 为何仍不够

有人提出的阈值是 **PCIe Gen2 x16 或 Gen3 x4**：“Unless we can unlock at least PCIE 2 16x or PCIE 3 4x, Tensor Parallel is out of the question.”（除非至少能解锁到 PCIE 2 16x 或 PCIE 3 4x，否则张量并行无从谈起。）解锁器提供的是 **Gen2 x4**（约 2 GB/s），低于这个阈值。聊天中提到的 “Gen 2 x4 lane unlock” 是一种误称：`Gen2/_DIFF_vs_master.patch` 中完全没有 lane、width 或 x16 处理。恢复 x16 需要进行**物理改装**，即手工焊接 24 颗 0402 电容。参见[物理改装](physical-mods.md)和[PCIe Gen2](../unlock/pcie-gen2.md)。

Gen2 x4 能带来什么，来自**同一位测试者的两次运行**；两次都不是有明确方法论的受控 A/B。应结合各自条件阅读。

**更干净的一次：单卡，模型完全驻留 VRAM。** 一张解锁到 40 GB 的 10 GB 卡，在 ik_llama 上运行 `unsloth/Qwen3.6-27B-MTP-UD-Q8_K_XL` 并启用 MTP；测试者称“all other factors unchanged”（其它因素全部不变）：

| 测试 | Gen1 x4（2026-07-22） | Gen2 x4（2026-07-27） |
|---|---|---|
| pp512 | 203.84 ± 12.10 | **277.84 ± 19.81** |
| pp2048 | 328.81 ± 8.27 | **449.41 ± 13.44** |
| pp8192 | 363.25 ± 14.93 | **493.86 ± 16.92** |
| tg128 | 38.15 ± 0.20 | **41.52 ± 1.89** |
| tg512 | 37.69 ± 1.59 | **40.12 ± 1.52** |
| tg2048 | 36.78 ± 1.43 | **37.90 ± 0.80** |

测试者将结果总结为 “big PP gains”（PP 大幅提升）和 “TG also got a nice bump”（TG 也有不错的提升），但无法解释一个完全驻留 VRAM 的模型为什么会受到影响，只能猜测与 MTP 的 CPU 侧调度有关。需要注意两点：两次运行相隔五天，并非背靠背进行；第二次运行的明确目的，是测量 SlimSAS 转接卡路径，而不是测量链路速度。

**多卡的一次：两次运行并非同类对比。** 一次三 GPU 运行几乎把整个模型放在 CPU 上（卡上只有一层以及上下文和算力缓冲区）：2026-07-20 在 Gen1 x4 下 pp2048 为 33.44 ± 0.37 t/s；2026-07-24 在测试者标记为 “gen2 x4 attempt” 的运行中为 48.22 ± 1.36 t/s；tg512 从 5.90 变为 6.39；time-to-first-response 从 61,253 ms 变为 42,510 ms。经常从这组数据引用的百分比变化（prefill +44.2%、延迟 -30.6%）是本文计算得出的，并非测试者直接陈述；而且两次运行的量化方式也不匹配：较晚的一次标记为 `GLM-5.2-GGUF-Q4`，较早的一次只标记为 `GLM-5.2-GGUF`。同一主机上 Gen2 x4 的 `GLM-5.2-UD-Q2_K_XL` 运行结果为 pp2048 49.00 ± 1.08、tg512 6.81 ± 0.06。测试者自己的结论很谨慎：“with gen2 x4 PP is at least not worse, but I feel like I'm still getting pegged by bandwidth”（使用 gen2 x4 后，PP 至少没有变差，但我感觉仍然被带宽卡住）。

两组数据的共同趋势是：prefill 和延迟得到改善，decode 的变化小得多。这符合流水线并行模型的预期，但两次运行都没有干净地隔离链路速度这个变量。

> [!NOTE]
> **未解问题：没有人在 Gen2 x4 下重新进行并行方式 A/B 测试**
>
> 这个领域中的所有并行方式对比都在 Gen1 x4 下运行。上面的两组 Gen2 x4 推理数据来自同一位测试者，而且都不是流水线并行与张量并行的对比。其他人曾多次表示“didn't try the pcie 2.0 yet”（还没有试过 pcie 2.0）。目前最干净的单变量实验，是在上文那台配置完整记录的 4 卡 bifurcation 主机上，安装 Gen2 代码并运行完全相同的 GLM-5.2 UD-IQ2_XXS 工作负载。

> [!NOTE]
> **未解问题：权重驻留后，通道数量是否仍然重要？**
>
> 有人直接提出过这个问题，但得到的只有观点性回答：“any additional bandwidth is more than welcome”（额外带宽越多越好）、“use MoE models”（使用 MoE 模型）、“PCI-e 3.0 x16 would be more than enough for multi-GPU”（PCI-e 3.0 x16 对多 GPU 来说绰绰有余）。这个问题受硬件限制：提问者没有可用的 x16 卡。资料中唯一一组长上下文 prefill 与链路宽度的对比数字，是在一张不同的、非 170HX 卡上测得的：64k 上下文下从 x16 换到 x8，速率大约从 6,000 降到 3,000 t/s，不能直接迁移到这里。前文引用的 CMP x4 与 x16 的 llama.cpp 对比属于短上下文、单卡测试，因此同样无法解决长上下文场景。

### 确实有依据的缓解措施

- **优先选择 MoE 模型。** 它们能减少每个 token 的跨设备 activation 流量，这是针对缺少 NVLink 的推荐缓解措施。这个结论是推理得出的，并未通过单独基准测试隔离验证，但与所有测量结果一致。
- **始终使用流水线并行。**
- **只要模型放得下，就在一张卡上进行 batch，而不是跨卡分片。**

---

## 哪些情况会出问题

| 症状 | 原因 | 修复方法 |
|---|---|---|
| 权重以 CPU-only 方式加载，随后 OOM | 预构建的 `libggml-cuda.so` 需要 `libcudart.so.13` / `libcublas.so.13`，而主机使用 CUDA 12.4 | 将 PyTorch 捆绑的 cu13 库放到 `LD_LIBRARY_PATH` 的最前面 |
| vLLM 导入失败，没有 `vllm._C` | 使用 `VLLM_USE_PRECOMPILED` 的可编辑安装 | 使用 0.20.2 release wheel，并将 PR #38476 的 python diff 应用到 site-packages |
| vLLM 不认识 `glm_moe_dsa` | `transformers` 4.57 | 使用 `transformers` 5.x |
| GLM-5.2 MoE 内核拒绝量化方式 | 非对称量化（`cyankiwi/GLM-5.2-AWQ-INT4`、asym g32） | 使用对称量化：`lowbitcoffee/GLM-5.2-W4A16`、`QuantTrio/GLM-5.2-Int4-Int8Mix` |
| GLM-5.2 的 prefill 降至约 120-160 t/s | llama.cpp 不支持 DSA，回退到 dense attention（llama.cpp issue #24730） | 使用带 `TRITON_MLA_SPARSE` 的 vLLM |
| vLLM TP8 在 CUDA-graph 捕获期间崩溃 | vLLM issue #48285 | 使用 `enforce_eager` 可避免崩溃，但 prefill 代价约为 4 倍；改用 PP |
| MTP + 流水线并行拒绝运行 | 当前 vLLM 不兼容 | 暂无已知修复；MTP + TP8 会直接 OOM |
| SGLang 无法运行 MTP | "sglang doesnt like mtp" | 使用 vLLM 或 llama.cpp 运行 MTP |
| 加载器占满 RSS，并持续抖动磁盘直到 OOM | llama.cpp 加载时的 compute-graph pass 抖动系统 RAM | 增加主机 RAM（见下文）；容器内的 `swapon` 被阻止 |
| 模型加载在约 20 GB 后挂起 | 80 GB 几何布局 | 回退到发布版的 40 GB profile |

> [!CAUTION]
> **80 GB profile 提供的可用显存更少，而不是更多**
>
> 在实验性的 `80` 分支中，模型加载到约 20 GB 后会挂起；即使之前能装入 40 GB 解锁配置的模型，也会停止加载。第二位测试者在 40-60 GB 范围内看到了失败。回退到 40 GB 几何布局后，模型即可正常加载。还要注意，该分支的 `constants.yaml` 宣称 `lmr: 0x0000028B`，但构建过程从不读取这个文件：`80/driver/build.sh` 第 93 行设置的是 `LMR="0x0000028A"`。因此，运行过该分支的每位测试者实际写入的都是 CFG1 `0x02779000` + LMR `0x0000028A` + `fb_length 0x0000001400000000`；这三者不一致本身很可能就是不稳定的原因。参见[80 GB 问题](../frontier/80gb.md)。

---

## 模型尺寸和主机要求

| 问题 | 答案 |
|---|---|
| Qwen3.6 27B bf16 能装进一张 64 GB 卡吗？ | 可以，约占 **54-56 GB**，几乎没有 KV 余量。同一模型的 Q4_K_M 量化占 **18-24 GB**。 |
| 从 q4 往上提升量化精度值得吗？ | 频道内的判断认为并不明确，但所依据的基准测试没有说明。在 64 GB 卡上，KV 余量更重要。 |
| 需要多少主机 RAM？ | 对非常大的模型，**至少约 256 GB**。一个 4-bit、467 GB 的 GLM-5.2 模型，即使主机有 512 GiB VRAM 可用，在一台只有 88 GiB RAM 的主机上也无法加载：权重达到约 431 GiB 的 VRAM 平台（405 GiB 模型加 KV/开销），但加载器将 RSS 固定在 **87.6 GB**，并持续以**约 820 MB/s 的速度重新读取磁盘**直到 OOM。这个现象在原始 `llama-server` 和 Unsloth studio 运行中都复现过，也在 `-c 1024` / `-c 8192`、no-warmup 和 batch 调优配置之间复现过。 |
| 模型加载需要多长时间？ | 单卡 Gen1 约 30 s；8 卡加载 239 GB 模型约 6 分钟；vLLM 加载 GLM-5.2 约 440-620 s。通过 RPC，在 Q4-6 下加载 >=500B 模型需要 20-60 分钟；在 170HX 卡之间运行 Kimi K3 级模型需要 4-6 小时。 |
| Kimi K3 需要多少张卡？ | 约 1.4T 权重使用 MXFP4（e2m1），激活使用 MXFP8，即**每个权重 4.25 bit**（权重本身 4 bit，每 32 个权重使用一个 8-bit scale，摊销 0.25 bit），因此约需要 **744 GB 权重，也就是十二张 64 GB 卡的容量**。频道内的估算比较随意，而且更高：“so... 25 cards XD”指仅使用流水线并行，“more like 32 to account for inefficiencies, kv cache, and a reasonable parallelism setup”（考虑低效、kv cache 和合理的并行配置后，更接近 32 张）。没有人核对过这组算术，而且这个估算中的 tp8 部分在 Gen1 x4 下无法成立。GA100 通过 Marlin kernel 处理 group scales。 |

> [!NOTE]
> **在这个范围内，VRAM 本身不是选择模型时的决定性约束**
>
> 将可用显存从 40 GB 增加到 84 GB，只让一位用户能够用更长的上下文运行同一个 27B 模型。另有两人提供了佐证：“even with an 8x64 and 512GB, LLMs like deepseek pro still cant run”（即使有 8x64 和 512GB，deepseek pro 这类 LLM 仍然无法运行）以及“I think 27b unmatched up to like 200gb”（我认为 27B 模型在大约 200 GB 以内都没有合适的匹配）。这些说法讨论的是这一尺寸范围内的模型格局，而不是硬件能力。相反的观点是使用更高比特量化，以及未量化的上下文。

---

## 这张卡与其它硬件的对比位置

| 参考对象 | 数据 | 备注 |
|---|---|---|
| RTX 3090、Qwen 27B q4_k_m | 启用 MTP 时 60 tok/s，未启用时 40 tok/s，prefill 约 1,200 t/s | 频道内使用的对比基线。 |
| 170HX 对比 3090 | 对 **dense** 模型的单流 decode 大致处于 3090 级别，但 VRAM 多得多；MoE prefill **高于** 3090；MoE decode **低于** 3090，因为它受带宽限制。 | “3090 级别”这一描述存在争议，但双方的说法可能分别适用于不同模型类别。 |
| 两张 170HX 对比一张 RTX 5090，图像和视频 | “A little bit slower, but same power draw and would let you run concurrent tasks in 2 separate comfyui containers”（稍微慢一点，但功耗相同，还能让你在两个独立的 comfyui 容器中运行并发任务）。 | 一位测试者在租用硬件上进行测试，只有截图且从未复现，置信度低。 |
| A100、GLM-5.2 | 55 tok/s | 二手数据，没有配置，置信度低。 |

---

## 非 LLM 的 CUDA 工作负载

扩散和图像生成非常适合这张卡：INT8 convolution “is fast and works well on the cmp170 in ComfyUI”（在 cmp170 上的 ComfyUI 中速度快且运行良好），一位从 Pascal 升级而来的拥有者称其为 “a speed demon”（速度恶魔）。原因在于，这类工作负载受算力限制，并且完全装入 VRAM，因此 Gen1 x4 链路不会造成影响；此外，相比语言模型，扩散过程对低精度噪声的容忍度更高，因为错误不会以同样的方式累积。需要注意的是，有人指出 diffusion-transformer 权重的离群值比 LLM 权重更严重，因此 W8A8 形式的量化并非天然安全。实测扩散数据见[性能](performance.md)。

视频生成也能正常工作：单张解锁后的卡运行 LTX 2.3，在“zero optimization going”（完全没有进行优化）的情况下，约 2 分钟生成了一个**约 30 秒的片段**；显卡在 USB 控制的鼓风机下持续运行 250 W，温度保持在 65 C 以下。该报告没有提供分辨率、帧数或步数，因此置信度为低到中等。

一台由六张 10 GB 到 40 GB 显卡组成的主机已经验证可以同时提供 **五个 vLLM OpenAI 兼容端点**（GPU 0-4，每张卡一个模型：`Qwen/Qwen2.5-7B-Instruct-AWQ`、`cyankiwi/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit`、`Qwen/Qwen2.5-32B-Instruct-AWQ`、`Qwen/Qwen2.5-VL-32B-Instruct-AWQ`、`Qwen/Qwen2.5-Omni-7B-AWQ`），同时在 GPU 5 上运行 ComfyUI。这明确是一次并发冒烟测试，而不是基准测试。

> [!NOTE]
> **未解问题：3D Gaussian splat 训练**
>
> 目前只是预测其表现会很差，并非测得很差。Splat 使用的 dense matrix multiply 很少，而且通常不使用低精度格式，因此会在标准 CUDA 核心上运行；在这类核心上，这张卡的 FP32 性能约为 12 TFLOPS，大致相当于一张 3060。没有人运行过实际的 splat 基准测试。

---

## 未解问题

1. **让 vLLM 中的 MTP 与流水线并行协同工作。** 如果 RFC #44697 中尚未合并的修复落地，基准测试报告预计 PP8 上会有“约 1.7 倍 decode（30 升至约 50 t/s）”；同一作者后来又在聊天中说，MTP “should push GLM 5.2 closer to 45 t/s”（应该能把 GLM 5.2 推近 45 t/s）。这两者都是从已测得的 30.2 t/s 推导出的预测，不是测量结果。
2. **在有完整文档记录的 4 卡 bifurcation 主机上，重新进行 PCIe Gen2 x4 下的并行方式 A/B 测试。**
3. **用数字回答 Gen2 下 x4 与 x16 的差异。** 当前受硬件条件限制。
4. **通过原样运行一个已发布配置，统一约 27B 模型的单卡 decode 数据。**
5. **解释 vLLM 的长上下文性能回退：** 一位测试者看到 vLLM 在约 130k 上下文时降至 22 tok/s，而同一张卡上的 llama.cpp 在两边都启用 MTP 时仍保持 48 tok/s；在正常上下文下，vLLM 原本以 90 对 60 领先。8 卡结果显示 vLLM 的 prefill 会随上下文长度*提升*，因此很可能存在配置方面的原因。没有人复现过这个现象。
6. **确定是否有可能启用 P2P。** 解锁器已经能够触及 SEC2/PLM 寄存器；`0x00823804` 处 FEAT PLM 所控制的同一地址空间中是否存在 P2P capability 位，至今从未检查。
7. **采用 Colibri 风格的 expert placement，**直接让非驻留的 MoE expert 从 RAM 在 CPU 上执行，而不是通过慢速链路上传。此前已有提示性证据：在这条链路上，prefill 在 CPU 上已经比 GPU offload 更快。
8. **确定显存解锁是否会通过 refresh collision，轻微拖慢原本就没有节流的算力。** 没有人做过解锁前后的对比，因为安装器会同时应用这两种解锁。

参见[未解问题](../frontier/open-questions.md)、[多卡](../procedures/multi-gpu.md)和[失败路线](../history/dead-ends.md)。
