# 在 CMP 170HX 上运行 LLM

**本页覆盖内容。** 哪些推理栈在一张解锁卡上工作、带模型/量化/上下文声明的实测提示处理和 token 生成速率、什么会坏以及为什么、如何跨卡扩展，以及支配每个多卡决定的那个问题：PCIe 带宽是不是瓶颈。原始算力和带宽数字在[性能](performance.md)；时钟和功耗在[调优](tuning.md)。

**三个结果将决定你做的几乎每个选择。**

1. **vLLM 比 llama.cpp 大约快 1.8x**，在一张卡和一个模型家族上，也比 SGLang 快。那个比值来自一个测试者，且两侧量化不匹配，所以把它当一个方向，而不是一个常量。
2. **跨卡流水线并行是必须的；张量并行在 PCIe Gen1 x4 下是一条死路。** Qwen2.5-72B AWQ 上的直接 A/B：TP2 在 prefill 时**差 2.3-2.8x**，换来 +23% 解码。
3. **记录上最佳的多卡结果**是一个 744B 参数 MoE（GLM-5.2、40B 活跃），在 vLLM 流水线并行下跑在 8 张解锁 64 GB 卡上：**131k 上下文下 prefill 2,675 t/s、decode 30.2 t/s**，整个会话零硬故障。

下面一切除非说明，都在 **PCIe Gen1 x4** 下测量。出货解锁器完全不含任何 PCIe 代码：`master` 上的 `common/constants.yaml` 只有 `driver_versions`、`gpu`、`compute` 和 `profiles` 键，树里任何地方都没有 `pcie` 节。任何被描述为跑在发布解锁上的基准测试，都以卡的出厂链路运行。

> [!WARNING]
> **如何读本页的数字**
>
> 这里几乎每个数字都来自 **一个测试者、一张卡、一个会话**。很少有独立复现；几行一度读作分开确认的，最终被证明是一张表的两行，或一条十分钟前附着报告的聊天总结。凡一个数字有多个来源，正文会显式说明；凡它什么都没说，就假设是单一报告。模型、量化、上下文和条件也为此逐数字说明。

---

## 解锁给推理工作负载买什么

算力解锁（FEAT PLM `0x00823804` 打开到 `0xffffffff`，然后 SS0 `0x0082381C` = `0x88888888` 和 SS1 `0x00823820` = `0x00000008`）就是让张量核吞吐可用的东西。见[算力节流](../unlock/compute-throttle.md)。

- **`llama.cpp` 带出厂 SM80 构建自动使用 GA100 张量核。** 无补丁、无标志。这正是几位测试者在 CUDA 架构列表里带 SM80（和 SM86）的未修改最新构建上，复现出数千 token 提示处理速率的原因。
- **解锁的 VRAM 真正可用。** 一位在 64 GB 卡上跑 LLM 的测试者报告 "havent had a single crash"（从没崩过一次）。六张解锁到 40 GB 的 10 GB 卡以 4 位跑 Qwen 27B 和 Qwen 35B，无崩溃、无变砖；唯一限制是散热：没有足够的散热方案时约 10 分钟运行时间。见[散热](cooling.md)。
- **解锁后的快速健全检查：** LM Studio 带一个小模型，"E2B" 小模型上预期约 **85 tokens/s**。那是模型大小未完全说明的一位测试者数字，所以把它当一个量级检查，而不是目标。严格检查是对照 202 TFLOPS 上限的 BF16 吞吐；见[验证](../procedures/verify.md)。

---

## 后端选择

| 后端 | 在这块硬件上的判决 | 证据 |
|---|---|---|
| **vLLM** | 在基本每个测量的配置里最好。默认选择。 | "约 1.8x faster"，由那个在 Qwen3.6 27B、单卡上跑过两者的唯一测试者陈述。量化对等未确立：llama.cpp 侧是 Q4_K_M，vLLM 侧的量化从未被说明，在频道内被读作 q6。归档的 vLLM 表给 Qwen3.6-27B 单流 62.4 t/s，对 36.87 t/s 是 1.69x。也是唯一能可用地跑 GLM-5.2 的栈 |
| **llama.cpp** | 单卡和跨卡的非 DSA 模型很好。DSA 注意力模型不可用。 | 单卡 pp512 888.09 t/s；8 卡上 GLM-5.2 prefill 141 t/s，对比 vLLM 的 2,675 |
| **ik_llama** | 在唯一受控对比里比主线的 llama.cpp 慢 | pp512 296.36 对比 360.65；tg128 33.20 对比 33.10 |
| **SGLang** | 在 Qwen3.6 27B int8、单卡上输给 vLLM，与预期相反，而且完全跑不了 MTP | 带截图的头对头 |
| **LM Studio / llama-swap** | 有效；作冒烟测试和服务有用 | 小模型约 85 t/s；125 W 上限下 35B A3B Q8 60 t/s |
| **Vulkan** | 多卡死路 | ggml Vulkan 后端没有 `VK_KHR_device_group` 支持，所以所有卡间传输都经主机 RAM |

### 为这张卡构建 llama.cpp

一个可复现的容器构建被发布为 `build-llama-170hx.sh`：

```bash
# 基础镜像：nvidia/cuda:13.3.0-devel-ubuntu26.04
# 在解析过的 master 提交克隆 ggml-org/llama.cpp
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
# 验证 libggml-cuda.so 没有缺失的 ldd 条目、按 llama.cpp 构建号标记镜像、然后冒烟测试：
nvidia-smi --query-gpu=name,memory.total,pcie.link.gen.current,pcie.link.gen.max --format=csv
llama-bench --list-devices
```

`-DCMAKE_CUDA_ARCHITECTURES=80` 是承重标志：CUDA 能力 8.0 是 GA100。

> [!CAUTION]
> **预构建的 `libggml-cuda.so` 需要 CUDA 13，没有它静默失败**
>
> 预构建二进制链接 `libcudart.so.13` 和 `libcublas.so.13`。在一台只有 CUDA 12.4 的主机上，权重**以 CPU-only 加载然后 OOM**，而非干净报错，这让诊断困难。有效修复是把 PyTorch 捆绑的 cu13 库前置到 `LD_LIBRARY_PATH`。

`llama.cpp` 也通过 `--split-mode tensor`（上游 PR `ggml-org/llama.cpp#19378`）获得了后端无关的张量并行，移除了偶数/2 的幂 GPU 计数约束。PR 本身把该功能描述为 "experimental ... not yet production ready"（实验性……还没到生产就绪）。vLLM 的张量并行仍要求偶数 GPU 数，而且在这张卡上张量并行反正是一个错误策略（见下）。

---

## 单卡实测吞吐

### vLLM、一张解锁 64 GB 卡

测试形状大致一个 1,500-token 提示带 200 个 token 输出。

| 模型 | 解码 | 4 并行下的聚合 | Prefill |
|---|---|---|---|
| `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`（MoE） | **113 tok/s** | **452 tok/s** | **1,700 tok/s** |
| `Qwen3-32B-AWQ`（dense） | 52.9 tok/s | 205 tok/s | 1,755 tok/s |
| Qwen3.6-27B BF16 | 19.2 tok/s | 71.1 tok/s | 2,231 tok/s |
| Qwen3.6-27B-AWQ-INT4 | 58.5 tok/s | 214.8 tok/s | 2,044 tok/s |

### llama.cpp、一张解锁卡

| 基准测试 | 模型 / 条件 | 结果 |
|---|---|---|
| `llama-bench` pp512 | qwen35 27B Q4_K_M、15.65 GiB、26.90 B 参数、CUDA、`ngl 99`、一张卡 | **888.09 ± 24.69 t/s** |
| `llama-bench` tg128 | 同一张表的第二行、同一次运行、同一个截图 | **36.87 ± 0.04 t/s** |
| 社区参考基准 | Llama-2 7B Q4_0、在频道内被提出作标准量化 | **pp 3106 t/s、tg 158 t/s**、一份数字报告。第二位测试者贴了一个截图没引数字、同意这些数字 "fine"；第三位说 "I get 3333 on 7b" 没说明量化 |
| dense 对比 sparse 对照 | Gemma4 26B A4B Q8（sparse）pp2048 3894.29 对比 Gemma4 31B Q8（dense）pp2048 830.33、同一机架同一构建 | 模型密度、不是配置错误 |
| 按模型的解码 | Qwen3.5 9B q4_k_xl 约 105 tok/s；Qwen3.6 27B q8 带 q8 KV 和 MTP depth 2、50 tok/s；Gemma4 26B A4B Q8 tg128 90.65 / tg512 90.10 / tg1024 89.85；Gemma4 31B Q8 tg128 27.07 / tg512 26.74 / tg1024 26.33 | 单卡 |

888.09 / 36.87 对是**一次运行**：单个 `llama-bench` 表在一个截图里的两行。第二位参与者后来重贴了同一段对话的截图，说该运行匹配了他们自己的数字，却从没贴出被匹配的数字，所以没有第二张表可对比。

Dense 27B 类模型在提示处理上比 7B 慢一个数量级，那是模型密度，不是调优失败：dense Qwen3.6 27B q4_k_p 在未打补丁的 SM80/SM86 构建上，pp 约 500 t/s 和约 900 t/s 都被报告。

### 最严格的控制单卡基准测试

一张解锁到 40 GB 的 10 GB 卡、Gen1 x4、250 W 上限。主机：2x EPYC 7713、DDR4、Supermicro H12DSi-N6、内核 6.18.38。模型 `unsloth/Qwen3.6-27B-MTP-GGUF`（`UD-Q4_K_XL` 和 `UD-Q8_K_XL`），Q4 用 40960 MiB 中的 17464 MiB、Q8 用 35718 MiB、空转约 42 W。一个测试者、一张卡、一个会话、带误差棒完整贴出；没人重跑过。

| 构建 / 配置 | pp512 | pp2048 | pp8192 | tg128 | tg512 | tg2048 |
|---|---|---|---|---|---|---|
| llama.cpp b10095（e8e6c7af2）、Q4、无 MTP | 360.65 | 564.30 | 722.49 | 33.10 | 32.67 | 30.50 |
| 相同、MTP（`--spec-type draft-mtp --spec-draft-n-max 2`） | 323.63 | 496.85 | 639.53 | 46.24（峰值 56.67） | 43.02（峰值 55.33） | 44.47（峰值 59.00） |
| ik_llama b4735（9d07d868）、Q4、无 MTP | 296.36 | 544.72 | 649.61 | 33.20 | 34.23 | 31.93 |
| ik_llama、Q4、MTP（`--spec-type mtp:n_max=2,p_min=0.0`） | 203.38 | 315.87 | 336.61 | 41.11（峰值 47.00） | 38.26（峰值 47.67） | 35.82（峰值 46.67） |
| ik_llama、Q8、无 MTP | 271.49 | 584.31 | 697.18 | 26.36 | 27.27 | 25.79 |
| ik_llama、Q8、MTP | 203.84 | 328.81 | 363.25 | 38.15 | 37.69 | 36.78 |

### 单卡级的功耗和效率

| 条件 | 结果 |
|---|---|
| Qwen3.6 27B `q6_k_xl`（41 GB 驻留）、故意拖累的主机（无-AVX2 CPU、卡在 250 W 节流、PCIe x4） | 约 26 tok/s、启用 MTP 后升到 **50 然后 55 tok/s** |
| `Qwen-AgentWorld-35B-A3B-Q8_0.gguf`、llama.cpp 经 llama-swap、**125 W 功耗限制** | 约 60 tok/s |
| Qwen3.6-35B-A3B Q8 带 MTP、**170 W** | 约 130 tok/s |
| vLLM、Qwen3.6 27B int8 | **每瓦 2.16 tok/s**、在频道内被描述为 "actually decent efficiency"（实际效率不错） |

功耗限制和 MTP 都大幅移动那个数字。见[调优](tuning.md)。

> [!NOTE]
> **未解问题：27B 单卡解码数字未调和**
>
> 已发布和频道内的 "Qwen 27B 类、一张解锁 64 GB 卡、vLLM" 数字跨越 **97 / 90 / 75 / 58.5 t/s**，加上 llama.cpp Q4_K_M 的 36.87 t/s。量化、MTP 状态、上下文长度和 vLLM 版本都在报告间不同，从未被保持恒定。在一张卡上逐字跑已发布的仓库配置并贴出标志，就能解决它。

---

## 多 token 预测（MTP）

MTP 在同一个 35B MoE 的两个后端上表现**相反**。

| 后端 | 无 MTP | 带 MTP | 增量 |
|---|---|---|---|
| llama.cpp（`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`） | 108.4 tok/s | **131.3 tok/s** | **+21%** |
| vLLM（同模型类） | 147 tok/s | **113 tok/s** | **-23%**，尽管 75% 接受率 / 1.75 tokens |

在受控 40 GB 机架上，MTP 买来约 **+40% 解码、约 -10% 提示处理**（tg128 33.10 到 46.24，而 pp8192 722.49 到 639.53）。它是一个**仅单流受益**的收益；另有一条警告说 MTP 不能随批大小很好扩展，那是推理，不是测量。

vLLM 回退被追踪穿过三个假设。MTP 头的量化被排除（`mtp` 在 `modules_to_not_convert` 里，fc、attention 和共享专家都是 BF16）。一个错误的 FlashInfer cubin 是第二个怀疑。站得住脚的解释是一个 CPU 侧瓶颈："it utilizes the CPU and as we are on PCIe Gen1 4x this becomes the bottleneck. GPU-Compute Utilization goes down by 7% and Mem Usage as well."（它利用 CPU，而我们在 PCIe Gen1 4x 上，这成为瓶颈。GPU-Compute 利用率掉 7%，Mem 使用也一样。）建议的监控：

```bash
nvidia-smi dmon -s put      # 观察 sm、mem、rx/txpci
```

它从未带修复被证明。

---

## 多卡：头条结果和它的配方

一个 744B 参数 MoE（GLM-5.2、40B 活跃）在 W4A16 对称量化、**8 张解锁 64 GB 卡**、vLLM 流水线并行、驱动 610.43.02、PCIe Gen1 x4（无电容改装，先于 Gen2 合并）、租用硬件上。

| 指标 | 值 |
|---|---|
| 4k / 32k / 65k / 131k 上下文下的 Prefill | 665 / 1,497 / 2,342 / **2,675 t/s** |
| 解码（无 MTP） | **30.2 t/s** |
| KV 容量 | 0.92 显存利用率下 438,107 个 token（BF16 KV、MLA 下约 88-100 KB/token） |
| 模型加载时间 | 约 440-620 s |
| 故障 | 整个会话零硬故障 |

Prefill **随上下文上升**，因为分块 prefill 加稀疏注意力。那是 llama.cpp 在同一个模型上行为的反面，也是栈选择在这里主导硬件的单一最清晰信号。

这是**一份报告、不是两份。** 一个测试者租了九张卡、在八张上基准测试，附着 `170HX-benchmark-results.md`（131k 下 prefill 2,675 t/s、decode 30.2 t/s），十分钟后在聊天里把同一次运行总结为 "2600 t/s prefill, 30 t/s decode"。取整的和精确的数字是同一个会话。没人用其它卡复现过它。

### 精确配方

```text
vllm==0.20.2  release wheel
  + PR #38476 python 文件作为 diff 应用到 site-packages
transformers 5.x                       （4.57 不认识 glm_moe_dsa）
VLLM_ATTENTION_BACKEND=TRITON_MLA_SPARSE
VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0
--pipeline-parallel-size 8 --gpu-memory-utilization 0.90
block-size 64                          （由 DEEPSEEK_V32_INDEXER 自动设置）
quantisation: W4A16 symmetric
```

GLM-5.2 用 DeepSeek 稀疏注意力（DSA），它原生需要 Hopper 或 Blackwell。在 Ampere 上跑它，需要来自 vLLM PR #38476 的 `TRITON_MLA_SPARSE` 后端。

> [!CAUTION]
> **量化选择：大多数已发布指南对这条路径是错的**
>
> 对 vLLM 上的 GLM-5.2、MoE 内核**拒绝非对称量化**。
> 有效：`lowbitcoffee/GLM-5.2-W4A16`（对称、g128、388 GB）和 `QuantTrio/GLM-5.2-Int4-Int8Mix`。
> **失败：`cyankiwi/GLM-5.2-AWQ-INT4`**（非对称、g32）、它是大多数指南引用的量化。

> [!WARNING]
> **实验性：`VLLM_USE_PRECOMPILED` 这里不会工作**
>
> 应用一个 vLLM 补丁的正常方式是带 `VLLM_USE_PRECOMPILED` 的可编辑安装。它不带 `vllm._C` 出货，会失败。用 0.20.2 release wheel，把 PR 的 python 文件作为 diff 应用到 site-packages。

### 其它多卡结果

| 配置 | 模型 / 栈 | 结果 |
|---|---|---|
| 8x 64 GB（512 GiB）、llama.cpp b10079、`-ngl 999 -c 4096 -np 1 --flash-attn on --no-context-shift --fit off --no-warmup --spec-type none`；虚拟化主机、掩码 GPU 名、链路活跃 Gen1 x4 但设备最大 Gen2 x16 | GLM-5.2 UD-IQ2_M、239 GB 2 位、约 224 GiB 驻留、约 6 分钟加载 | TG **17.33 tok/s**（17.31-17.37、SD 0.02）；PP **113.0 tok/s**（111.8-115.5、SD 1.01）、十次连续运行 |
| 8x 64 GB、llama.cpp `-sm layer` | GLM-5.2 Q4_K_S GGUF | prefill **141 / 162 / 124 t/s** at 512 / 4k / 16k（随上下文退化）、decode **17.2 t/s** |
| 8x 64 GB、llama.cpp 层拆分、Gigabyte G292-Z20、Proxmox 直通 | GLM-5.2-Q4_K_XL 完全在 VRAM（报告 320 GB 驻留） | **13-14 tok/s** 单流、20 个并发会话时崩到 **3 tok/s** |
| 4x 64 GB（256 GB）经一块 AliExpress x4x4x4x4 分叉板、每张卡 Gen1 x4、llama.cpp 层/行拆分、无 MTP | unsloth `GLM-5.2-UD-IQ2_XXS` | **约 15 tok/s 解码**、**24.07 t/s prefill**；见下面日志细节 |
| 3x 40 GB（120 GB）、llama.cpp、几乎整个模型在 CPU 上：**一层**加上下文和算力缓冲在 GPU 上（40 GB 中 18 GB 在它们自己身上） | unsloth `GLM-5.2-GGUF`、约 460 GB MoE | **pp2048 33.44 ± 0.37 t/s、tg512 5.90 ± 0.03 t/s**。对照单独的 CPU 加 DDR4、测试者只报相对增量、"TG went ~60% up"（TG 升约 60%）和 "PP went ~30% down"（PP 降约 30%）；绝对 CPU-only 数字从未贴出 |
| 7 卡租用机架、llama.cpp | GLM-5.2 | **121 t/s prefill**、被判不可用（约 25 分钟提示处理时间）；解码前被杀 |

4 卡服务器日志值得完整引用、因为它是档案里最完整指定的多卡捕获：

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

### 并发扩展很差

存在一个并发扫描：8 卡 GLM-5.2 UD-IQ2_M 报告、`-np 16 -c 16384`、连续批处理、每用户 128 个 token。下面每列都在那份报告里制成表。

| 用户 | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| 聚合 | 17.3 | 21.6 | 25.7 | 28.1 | **38.9 tok/s** |
| 每用户 | 17.3 | 10.8 | 6.4 | 3.5 | **2.4 tok/s** |
| 批墙钟时间 | n/a | 11.9 s | 20.0 s | 36.5 s | 52.6 s |
| 相对 1 用户的扩展 | 1.00x | 1.25x | 1.49x | 1.62x | **2.25x** |

那是从 1 到 16 个用户只有 **2.25x**。报告把它根因归到三个东西一起：没有 PCIe 或 NVLink 点对点，所以每个 token 经主机内存中继七次；层 49 到 50 过渡处一次跨-NUMA 流水线跳；以及链路本身。注意主机是一个带掩码 GPU 名的虚拟化或直通环境，它的链路读作**活跃 Gen1 x4 但设备最大 Gen2 x16**，所以这个单一扫描不是一次干净的出厂卡测量。

---

## 为什么 PCIe 是、又不是瓶颈

这是档案里最有争议的问题，争议持续主要是双方在描述不同的配置。按配置陈述声称，它就干净地解决。

### 物理情况

- 出厂链路是 **Gen1 x4、约 1.0 GB/s**，而且**在推理负载下不爬升**。
- 没有**点对点、也没有 NVLink**。`torch.cuda.can_device_access_peer(i,j)` 在一个 8 卡机架上对全部 **56 个 GPU 对**返回 `False`，即使在一个 PIX 组内；一个 ggml `-lv 5` 日志含零个 peer/p2p/rpc 出现；`nvidia-smi nvlink` 报告 "Device does not have or support Nvlink"。见[P2P](../frontier/p2p.md) 和[NVLink](../frontier/nvlink.md)。
- 因此，在 8 卡 80 层模型（每 GPU 10 层）上做层拆分时，每个生成的 token 做 **7 次 GPU 到 CPU RAM 到 GPU 跳**，其中一次在层 49 到 50 过渡处跨一个 NUMA/socket 边界。

### 它不咬人的地方

**单卡。** 权重在加载后驻留 VRAM。PCIe 代价是一次性约 30 s 的模型加载，之后 prefill 和 decode 以正常速度跑。把单卡从 x4 移到 x16，只移动 llama.cpp pp 439 到 448 和 tg 81.91 到 85.75。"PCIe bandwidth is a nothing burger"（PCIe 带宽无所谓）的立场**对这个情况正确**，而且只对这个情况。

**扩散和图像或视频生成。** 算力绑定且驻留 VRAM，所以链路从不进入画面。

### 它咬得很狠的地方

**Prefill、不是 decode。** 在两个不同的卡家族上报告：一个 170HX 卸载用户发现提示处理在 CPU 上*字面上更快*，比 GPU 卸载还快（"PP went ~30% down because of gen1 x4 link limit"、针对测出 pp2048 33.44 t/s 的三卡一层卸载运行）；一个带大 MoE 模型的多卡 CMP 100-210 用户报告 "the pipeline parallelization for decode is fine, its the prefill that kills you"（流水线并行化对解码没问题，是 prefill 干掉你）。同一运行里解码朝反方向移动，"TG went ~60% up" 对比 CPU 加 DDR4，所以只有 decode 支配你的工作负载时，GPU 卸载才值得。那个对比的两侧都是测试者引用的百分比；CPU-only 绝对速率从未贴出，所以不要把任何派生的 CPU 数字当测量过。

**张量并行。** 决定性的 A/B、Qwen2.5-72B dense AWQ 在 vLLM、Gen1 x4：

| 配置 | 1k / 4k / 16k 下的 Prefill | 解码 |
|---|---|---|
| 1 卡 | 839 / 1,092 / 960 t/s | 27.3 t/s |
| **PP2**（流水线） | 829 / 1,084 / **1,167** t/s | 29.1 t/s |
| **TP2**（张量） | **316 / 420 / 416** t/s | 33.7 t/s |

TP 在 prefill 时**差 2.3-2.8x**，换来 +23% 解码。在 8 卡的 GLM-5.2 上同一个模式更糟：带 `enforce_eager` 的 TP8 在 4k / 16k / 32k 给 382 / 435 / 629 t/s（比 PP8 差约 4x）和 **3.4 t/s 解码**；不带 `enforce_eager`、CUDA-graph 捕获崩溃（vLLM issue #48285）。多位操作者独立收敛到同一结论："With PCIe 1.0 x4 link Tensor parallel is a no go."（在 PCIe 1.0 x4 链路上张量并行不可行。）

**并发。** 上面 1 到 16 用户的 2.25x 上限。

### 为什么流水线并行能活过一条窄链路

流水线并行在阶段之间只发 token 或其激活/嵌入向量，每阶段每 token 一次。张量并行拆分每个矩阵乘，因此需要在每层内跨卡做 all-reduce，这同时苛求带宽**和**延迟（而延迟是更宽链路修不了的那部分）。测量支持这个互连需求排序：

**Tensor >> Expert > Pipeline > Data。**

只有数据并行在出厂 170HX 链路上不受损地运行。一个 **1.56x** 的、流水线并行模式里两张卡相对单卡的提示处理增益早期流传，但它是二手的：从一个报告者无法分享的私人组转述，没给模型、量化或配置。把它当一个轶事，而不是测量。流水线并行不显著改善 token 生成速度；它买容量和 prefill，不是解码。测得的 PP2 相对一卡的增益是 decode 27.3 到 29.1 t/s、prefill 在 16k 从 960 升到 1,167 t/s。

### 张量并行的阈值、以及为什么 Gen2 x4 达不到

陈述的阈值是 **PCIe Gen2 x16 或 Gen3 x4**："Unless we can unlock at least PCIE 2 16x or PCIE 3 4x, Tensor Parallel is out of the question."（除非我们能解锁至少 PCIE 2 16x 或 PCIE 3 4x、张量并行无从谈起。）解锁器交付 **Gen2 x4**（约 2 GB/s），低于那个。聊天里对 "Gen 2 x4 lane unlock"（Gen 2 x4 通道解锁）的引用是一个误称：`Gen2/_DIFF_vs_master.patch` 里任何地方都没有 lane、width 或 x16 处理。恢复 x16 是一个**物理**改装——24 颗手工焊接 0402 电容。见[物理改装](physical-mods.md) 和[PCIe Gen2](../unlock/pcie-gen2.md)。

Gen2 x4 买来什么，来自**同一个测试者的两次运行**，都不是带陈述方法论的受控 A/B。两者都值得带条件读。

**更干净的那次：一张卡、模型完全驻留 VRAM。** 一张解锁到 40 GB 的 10 GB 卡，`unsloth/Qwen3.6-27B-MTP-UD-Q8_K_XL` 在 ik_llama 上带 MTP 开，被测试者描述为 "all other factors unchanged"（其它一切不变）：

| 测试 | Gen1 x4（2026-07-22） | Gen2 x4（2026-07-27） |
|---|---|---|
| pp512 | 203.84 ± 12.10 | **277.84 ± 19.81** |
| pp2048 | 328.81 ± 8.27 | **449.41 ± 13.44** |
| pp8192 | 363.25 ± 14.93 | **493.86 ± 16.92** |
| tg128 | 38.15 ± 0.20 | **41.52 ± 1.89** |
| tg512 | 37.69 ± 1.59 | **40.12 ± 1.52** |
| tg2048 | 36.78 ± 1.43 | **37.90 ± 0.80** |

测试者把它总结为 "big PP gains"（大 PP 增益）、"TG also got a nice bump"（TG 也得到不错的提升），且无法解释为什么一个完全驻留 VRAM 的模型应该动，猜测是 MTP 的 CPU 侧调度。两个注意：运行相隔五天而非背靠背；第二个运行的陈述目的是测量一个 SlimSAS 转接卡路径，不是链路速度。

**多卡那次、不是一个同类对。** 一个三-GPU 运行，几乎整个模型在 CPU 上（一层加上下文和算力缓冲在卡上）：pp2048 33.44 ± 0.37 t/s，在 2026-07-20 的 Gen1 x4 上，和 48.22 ± 1.36 t/s 在测试者标注为 "gen2 x4 attempt" 的 2026-07-24 运行；tg512 5.90 到 6.39；到首响应时间 61,253 到 42,510 ms。常从这个对引用的百分比增量（+44.2% prefill、-30.6% 延迟）在这里计算，不是测试者陈述，而且两个运行量化不匹配：更晚的标注 `GLM-5.2-GGUF-Q4`、更早的未标注 `GLM-5.2-GGUF`。同一机架上 Gen2 x4 的 `GLM-5.2-UD-Q2_K_XL` 运行给 pp2048 49.00 ± 1.08 和 tg512 6.81 ± 0.06。测试者自己的判决谨慎："with gen2 x4 PP is at least not worse, but I feel like I'm still getting pegged by bandwidth"（带 gen2 x4 PP 至少不更糟，但我觉得还是被带宽钉住）。

两者跨向：prefill 和延迟改善，decode 动得少得多。那是流水线并行模型预测的形状，但两个运行都没有干净隔离链路速度。

> [!NOTE]
> **未解问题：没人重跑过 Gen2 x4 下的并行 A/B**
>
> 这个领域里每个并行对比都跑在 Gen1 x4。上面两个 Gen2 x4 推理数据集来自一个测试者，而且都不是流水线-对比-张量对比。其他人反复注明 "didn't try the pcie 2.0 yet"（还没试 pcie 2.0）。可用的最干净单变量实验是上面的 4 卡分叉机架（完整文档化配置），带安装的 Gen2 代码跑完全相同的 GLM-5.2 UD-IQ2_XXS 工作负载。

> [!NOTE]
> **未解问题：权重驻留后通道数要紧吗？**
>
> 被直接问，只被意见回答（"any additional bandwidth is more than welcome"（任何额外带宽都求之不得）、"use MoE models"（用 MoE 模型）、"PCI-e 3.0 x16 would be more than enough for multi-GPU"（PCI-e 3.0 x16 对多 GPU 绰绰有余））。它被硬件阻塞：问的人没有 x16 卡可用。语料库里唯一的长上下文 prefill-对比-位宽数字——64k 上下文时从 x16 到 x8 约 6,000 降到 3,000 t/s——是在一张不同的、非 170HX 卡上测量的，不可迁移。上面引用的 CMP x4-对比-x16 llama.cpp 对比是短上下文和单卡，所以也不解决长上下文情况。

### 真正受支持的缓解

- **偏好 MoE 模型。** 它们减少每 token 的跨设备激活流量，那是对缺 NVLink 的推荐缓解。是推理而非被基准测试隔离，但与一切测量一致。
- **总是用流水线并行。**
- **模型放得下时，在一张卡上批处理，而不是跨卡分片。**

---

## 什么会坏

| 症状 | 原因 | 修复 |
|---|---|---|
| 权重以 CPU-only 加载然后 OOM | 预构建 `libggml-cuda.so` 需要 `libcudart.so.13` / `libcublas.so.13`；主机有 CUDA 12.4 | 把 PyTorch 捆绑的 cu13 库前置到 `LD_LIBRARY_PATH` |
| vLLM import 失败、无 `vllm._C` | `VLLM_USE_PRECOMPILED` 可编辑安装 | 0.20.2 release wheel + PR #38476 python diff 应用到 site-packages |
| vLLM 不认识 `glm_moe_dsa` | `transformers` 4.57 | `transformers` 5.x |
| GLM-5.2 MoE 内核拒绝量化 | 非对称量化（`cyankiwi/GLM-5.2-AWQ-INT4`、asym g32） | 对称量化：`lowbitcoffee/GLM-5.2-W4A16`、`QuantTrio/GLM-5.2-Int4-Int8Mix` |
| GLM-5.2 prefill 崩到约 120-160 t/s | llama.cpp 没有 DSA 支持、回退到 dense 注意力（llama.cpp issue #24730） | 用带 `TRITON_MLA_SPARSE` 的 vLLM |
| vLLM TP8 在 CUDA-graph 捕获期间崩溃 | vLLM issue #48285 | `enforce_eager` 避免崩溃但花约 4x prefill；改用 PP |
| MTP + 流水线并行拒绝运行 | 在 vLLM 中当前不兼容 | 未知；MTP + TP8 直接 OOM |
| SGLang 不跑 MTP | "sglang doesnt like mtp" | 用 vLLM 或 llama.cpp 跑 MTP |
| 加载器钉死 RSS 和磁盘抖动直到 OOM | llama.cpp 的加载时计算图 pass 抖动系统 RAM | 更多主机 RAM（见下）；容器内 `swapon` 被阻止 |
| 约 20 GB 后模型加载挂起 | 80 GB 几何布局 | 回退到出货 40 GB 档位 |

> [!CAUTION]
> **80 GB 档位给你更少的可用显存、不是更多**
>
> 实验性 `80` 分支下，模型加载在约 20 GB 后挂起，甚至之前装进 40 GB 解锁的模型也停止加载；第二位测试者在 40-60 GB 范围看到失败。回退到 40 GB 几何布局恢复了工作加载。也要注意分支的 `constants.yaml` 宣告 `lmr: 0x0000028B`，但构建从不读那个文件：`80/driver/build.sh` 第 93 行设 `LMR="0x0000028A"`，所以每个跑过那个分支的测试者实际编程了 CFG1 `0x02779000` + LMR `0x0000028A` + `fb_length 0x0000001400000000`——一个三路不一致，它本身很可能就是不稳定的原因。见[80 GB 问题](../frontier/80gb.md)。

---

## 模型尺寸和主机要求

| 问题 | 答案 |
|---|---|---|
| Qwen3.6 27B bf16 装进一张 64 GB 卡吗？ | 装得进，约 **54-56 GB**，几乎留不下 KV 余量。同一个模型的 Q4_K_M 量化是 **18-24 GB** |
| 越过 q4 值得吗？ | 频道内判断，由未说明的基准测试支持：不明确。一张 64 GB 卡上 KV 余量更要紧 |
| 需要多少主机 RAM？ | 对非常大的模型**至少约 256 GB**。一个 GLM-5.2 4 位 467 GB 模型在一台 88 GiB-RAM 主机上**即使有 512 GiB VRAM 可用也加载不了**：权重达到约 431 GiB 的 VRAM 平台（405 GiB 模型加 KV/开销），但加载器把 RSS 钉在 **87.6 GB**，持续**约 820 MB/s 的磁盘重读**直到 OOM。在裸 `llama-server` 和 Unsloth studio 运行，以及 `-c 1024` / `-c 8192`、no-warmup 和批调优之间复现 |
| 模型加载时间？ | 单卡 Gen1 约 30 s；8 卡上 239 GB 模型约 6 分钟；GLM-5.2 在 vLLM 下约 440-620 s。经 RPC，>=500B 模型在 Q4-6 下 20-60 分钟；Kimi K3 类模型跨 170HX 卡 4-6 小时 |
| Kimi K3 需要几张卡？ | 约 1.4T 权重在 MXFP4（e2m1）带 MXFP8 激活，是**每权重 4.25 位**（权重 4 位、每 32 个权重 8 位缩放 0.25 位），所以约 **744 GB 权重、十二张 64 GB 卡的量**。频道内估计随口且更高："so... 25 cards XD" 仅流水线并行、"more like 32 to account for inefficiencies, kv cache, and a reasonable parallelism setup"（更像 32 张、把低效、kv 缓存和一个合理的并行设置算进去）。没人调和过算术，那个估计的 tp8 一半在 Gen1 x4 不成立。GA100 经 Marlin 内核处理组缩放 |

> [!NOTE]
> **这个范围里、VRAM 单独不是模型选择的约束**
>
> 从 40 GB 到 84 GB，让一个用户用更长的上下文跑同一个 27B 模型。另外两人佐证："even with an 8x64 and 512GB, LLMs like deepseek pro still cant run"（即使 8x64 和 512GB，deepseek pro 这类 LLM 仍跑不了）、"I think 27b unmatched up to like 200gb"（我觉得 27b 到约 200gb 不匹配）。这是关于这些尺寸下模型格局的陈述，不是关于硬件的。提出的反方是更大量化和未量化上下文。

---

## 这张卡相对其它硬件的位置

| 参考 | 数字 | 备注 |
|---|---|---|
| RTX 3090、Qwen 27B q4_k_m | 带 MTP 60 tok/s、不带 40、prefill 约 1,200 t/s | 频道内使用的对比基线 |
| 170HX 对比 3090 | 对**dense** 模型的单流解码大致 3090 级、VRAM 远多；MoE prefill 在 3090 **之上**；MoE decode 在它**之下**，那是带宽绑定的 | "3090 级" 的定性有争议，双方可能对不同模型类都对 |
| 两张 170HX 对比一张 RTX 5090、图像和视频 | "A little bit slower, but same power draw and would let you run concurrent tasks in 2 separate comfyui containers"（稍慢一点、但功耗相同、能让你在 2 个独立 comfyui 容器里跑并发任务） | 一个测试者、租用硬件、只有截图、从未复现：低置信度 |
| A100、GLM-5.2 | 55 tok/s | 二手、无配置、低置信度 |

---

## 非 LLM CUDA 工作负载

扩散和图像生成是一个强契合：INT8 卷积 "is fast and works well on the cmp170 in ComfyUI"（在 cmp170 的 ComfyUI 里快且工作良好），一位从 Pascal 来的拥有者叫它 "a speed demon"（一个速度恶魔）。机制是：工作负载算力绑定且完全装进 VRAM，所以 Gen1 x4 链路不咬人；而扩散比语言模型更好地容忍低精度噪声，因为错误不会以同样方式复合。一个提出的注意：扩散-变换器权重有比 LLM 权重更差的离群值，所以 W8A8 式量化不自动安全。实测扩散数字在[性能](performance.md) 制成表。

视频生成有效：单张解锁卡上的 LTX 2.3 在约 2 分钟内产出约 **30 秒的片段**，带 "zero optimization going"（零优化进行中），卡在 USB 控制鼓风机下持续 250 W 并保持在 65 C 以下。那份报告没给分辨率、帧数或步数，所以它是低到中置信度。

一个六-GPU 10 GB 到 40 GB 主机被验证服务 **五个并发 vLLM OpenAI 兼容端点**（GPU 0-4、每个一个模型：`Qwen/Qwen2.5-7B-Instruct-AWQ`、`cyankiwi/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit`、`Qwen/Qwen2.5-32B-Instruct-AWQ`、`Qwen/Qwen2.5-VL-32B-Instruct-AWQ`、`Qwen/Qwen2.5-Omni-7B-AWQ`）加 GPU 5 上的 ComfyUI。那明确是一次并发冒烟测试，不是基准测试。

> [!NOTE]
> **未解问题：3D 高斯泼溅训练**
>
> 被预测为差，而非测量为差。泼溅有很少的稠密矩阵乘，通常不用低精度格式，所以它们在标准 CUDA 核上运行，那里这张卡约 12 TFLOPS FP32、大致一块 3060。没人跑过实际泼溅基准测试。

---

## 开放问题

1. **让 MTP 在 vLLM 里与流水线并行工作。** 基准测试报告预测 "PP8 上约 1.7x decode（30 到约 50 t/s）"，如果 RFC #44697 里的未合并修复落地；同一位作者后来在聊天里说 MTP "should push GLM 5.2 closer to 45 t/s"（应该把 GLM 5.2 推到更接近 45 t/s）。两者都是从实测 30.2 t/s 的预测，不是测量。
2. **在文档化的 4 卡分叉机架上重跑 Gen2 x4 的并行 A/B。**
3. **用数字回答 Gen2 下的 x4 对比 x16。** 被硬件阻塞。
4. **逐字跑一个已发布配置来调和约 27B 单卡解码数字。**
5. **解释 vLLM 长上下文回退：** 一个测试者看到 vLLM 在约 130k 上下文时掉到 22 tok/s，而 llama.cpp 在同一个卡上带两边 MTP 保持 48 tok/s，在正常上下文时 vLLM 领先 90 对 60 之后。8 卡结果显示 vLLM prefill 随上下文*改善*，所以一个配置原因很可能。没人复现过。
6. **确定 P2P 能否被启用。** 解锁器已经到达 SEC2/PLM 寄存器；一个 P2P 能力位是否活在 `0x00823804` 处 FEAT PLM 管辖的同一个空间里，从未被检查。
7. **Colibri 式专家放置**，直接在 CPU 上从 RAM 执行非驻留 MoE 专家，而不是经慢链路上传它们。提示性先前证据：prefill 在这个链路上已经比 GPU 卸载在 CPU 上更快。
8. **显存解锁是否通过刷新冲突稍微拖慢已不再节流的算力。** 没人跑过前后对比，因为安装器同时应用两个解锁。

见[未解问题](../frontier/open-questions.md)、[多卡](../procedures/multi-gpu.md) 和[死路](../history/dead-ends.md)。
