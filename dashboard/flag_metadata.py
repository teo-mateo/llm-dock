"""
Flag metadata and validation for service templates.
Defines how flags are rendered and validated for each template type.
"""

from typing import Dict, Any, List, Tuple, Optional
from service_templates import sanitize_service_name

# ============================================
# MANDATORY FIELDS (per template type)
# ============================================

MANDATORY_FIELDS = {
    "llamacpp": ["port", "model_path", "alias", "api_key"],
    "vllm": ["port", "model_name", "alias", "api_key"],
}

# ============================================
# FLAG METADATA
# Defines CLI mapping and type for each flag
# ============================================

LLAMACPP_FLAGS = {
    # Core model flags
    "mmproj_path": {
        "cli": "--mmproj",
        "type": "path",
        "description": "Path to multi-modal projector (for vision models)",
        "tip": "Path to the <b>multimodal projector weights</b> (.gguf) that bridge a vision encoder to the language model, required for image-understanding models like LLaVA or Qwen-VL. When loading from Hugging Face with <code>-hf</code>, the projector is downloaded automatically; GPU offloading is on by default and can be disabled with <code>--no-mmproj-offload</code> if VRAM is tight.",
    },
    # Context and performance
    "context_length": {
        "cli": "-c",
        "type": "int",
        "description": "Context length in tokens",
        "default": "128000",
        "tip": "Sets the <b>maximum context window</b> in tokens \u2014 the total amount of text (prompt + response) the model can hold in memory at once. Larger values consume significantly more VRAM because the KV cache scales linearly with context size; <code>0</code> loads the model's native default from its metadata. Start with the model default and only increase if you need long conversations or large document inputs.",
    },
    "gpu_layers": {
        "cli": "-ngl",
        "type": "int",
        "description": "Number of layers to offload to GPU (999 = all)",
        "default": "999",
        "tip": "Controls how many model layers are <b>offloaded to GPU VRAM</b> \u2014 more layers on GPU means much faster inference, but requires sufficient VRAM. Use <code>auto</code> to let llama-server determine the optimal split, <code>all</code> to force full GPU offload, or an explicit integer to cap VRAM usage and allow CPU fallback for remaining layers.",
    },
    "batch_size": {
        "cli": "-b",
        "type": "int",
        "description": "Logical batch size for prompt processing",
        "default": "2048",
        "tip": "The <b>logical maximum batch size</b> \u2014 how many tokens can be grouped together conceptually for prompt processing (default: 2048). Increasing this can improve throughput when processing long prompts or many parallel requests, but has little effect unless <code>-ub</code> (ubatch) is also tuned upward. This sets the scheduling ceiling; actual hardware allocation is controlled by <code>-ub</code>.",
    },
    "ubatch_size": {
        "cli": "-ub",
        "type": "int",
        "description": "Physical micro-batch size",
        "default": "512",
        "tip": "The <b>physical micro-batch size</b> \u2014 the actual number of tokens sent to the GPU in a single hardware pass (default: 512). Smaller values reduce peak VRAM usage but may lower throughput; larger values (e.g. <code>1024</code> or <code>2048</code>) improve prompt processing speed at the cost of more VRAM. Tune this first if you are hitting out-of-memory errors during long prompt ingestion.",
    },
    # Sampling parameters
    "repeat_penalty": {
        "cli": "--repeat-penalty",
        "type": "float",
        "description": "Penalty for repeating tokens",
        "default": "1.0",
        "tip": "Penalizes tokens that have already appeared in the output. Values &gt; <b>1.0</b> reduce repetition; <code>1.0</code> disables it entirely. Raise to <code>1.1</code>\u2013<code>1.3</code> when the model loops on phrases, but too-high values can degrade coherence by forcing it away from contextually correct repeated words.",
    },
    "top_p": {
        "cli": "--top-p",
        "type": "float",
        "description": "Top-p sampling",
        "default": "0.95",
        "tip": "Nucleus sampling: at each step, considers only the smallest set of tokens whose cumulative probability reaches <b>top_p</b>. Lower values (e.g. <code>0.7</code>) make output more focused and factual; higher values (e.g. <code>0.95</code>) allow more diversity. Set to <code>1.0</code> to disable; many practitioners now prefer <code>min_p</code> over top_p for local inference.",
    },
    "top_k": {
        "cli": "--top-k",
        "type": "float",
        "description": "Top-k sampling",
        "default": "40.0",
        "tip": "Limits sampling to the <b>k</b> highest-probability tokens at each step. Smaller values (e.g. <code>10</code>\u2013<code>20</code>) produce more focused, predictable output; larger values allow more variety. Set to <code>0</code> to disable; consider relying on <code>min_p</code> instead for more adaptive truncation.",
    },
    "temperature": {
        "cli": "--temp",
        "type": "float",
        "description": "Temperature for sampling",
        "default": "0.8",
        "tip": "Scales the token probability distribution before sampling. Values &lt; <b>1.0</b> make output sharper and more deterministic; values &gt; <b>1.0</b> increase randomness and creativity. A starting point of <code>0.7</code>\u2013<code>0.8</code> suits most tasks; use <code>0.0</code>\u2013<code>0.3</code> for code or factual Q&amp;A, and <code>1.0</code>+ for creative writing.",
    },
    # CPU
    "threads": {
        "cli": "-t",
        "type": "int",
        "description": "Number of CPU threads for generation (auto-detects by default)",
        "tip": "Controls how many CPU threads are used for <b>token generation</b> (the autoregressive decode phase). Setting this above your physical core count rarely helps and often hurts \u2014 start with the number of <b>performance cores</b> on your CPU and tune down if you observe thrashing. For GPU-heavy setups with minimal CPU offload, a low value like <code>2</code>\u2013<code>4</code> is often optimal.",
    },
    "threads_batch": {
        "cli": "-tb",
        "type": "int",
        "description": "CPU threads for batch/prompt processing (default: same as -t)",
        "tip": "Controls CPU threads used during <b>prompt ingestion / prefill</b> (the batch processing phase), which is typically more parallelizable than generation. Defaults to the same value as <code>-t</code>, but you can set it higher \u2014 up to the full physical core count \u2014 to speed up long prompt evaluation without affecting generation latency.",
    },
    "prio": {
        "cli": "--prio",
        "type": "int",
        "description": "Process priority: -1 low, 0 normal, 1 medium, 2 high, 3 realtime",
        "default": "0",
        "tip": "Sets the OS scheduling priority for the llama-server process and its worker threads. Values: <code>-1</code> low, <code>0</code> normal (default), <code>1</code> medium, <code>2</code> high, <code>3</code> realtime. Raising priority to <code>2</code> can reduce latency jitter on a loaded machine, but <code>3</code> (realtime) can starve the OS on single-socket systems \u2014 use with caution.",
    },
    "poll": {
        "cli": "--poll",
        "type": "int",
        "description": "Polling level for work waiting (0=no polling, 50=default, 100=max)",
        "default": "50",
        "tip": "Sets the CPU <b>busy-wait (polling) level</b> from <code>0</code> (pure sleep/wake, lowest CPU burn) to <code>100</code> (mostly spinning). The default of <code>50</code> is a middle ground. Higher values reduce inter-token latency at the cost of idle CPU usage; lower values are better for shared servers or power-constrained environments.",
    },
    "numa": {
        "cli": "--numa",
        "type": "string",
        "description": "NUMA optimization mode: distribute, isolate, numactl",
        "tip": "Enables NUMA-aware memory and thread placement on multi-socket systems. <b>distribute</b> spreads execution evenly across all nodes (good default for dual-socket); <b>isolate</b> keeps threads on the node where the process started (low cross-node traffic); <b>numactl</b> defers to an external <code>numactl</code> CPU map.",
    },
    "cpu_mask": {
        "cli": "-C",
        "type": "string",
        "description": "CPU affinity mask (hex,hex for core/hyperthread masks)",
        "tip": "Sets <b>CPU affinity</b> using hexadecimal masks to pin specific threads to specific cores. Format is <code>core_mask,ht_mask</code> where <code>core_mask</code> selects physical cores and <code>ht_mask</code> selects hyperthreads. Use this to isolate the server from other processes or to pin to high-performance cores only. Example: <code>0xff,0x0</code> uses first 8 physical cores with hyperthreading disabled.",
    },
    "cpu_strict": {
        "cli": "--cpu-strict",
        "type": "bool",
        "description": "Strict CPU affinity (0=relaxed, 1=strict)",
        "tip": "Enforces <b>strict CPU affinity</b> when <code>-C</code> is set. With strict mode (<code>1</code>), threads will never migrate to cores outside their assigned mask, even under load. Relaxed mode (<code>0</code>, default) allows some migration for better load balancing. Use strict mode when you need deterministic latency guarantees.",
    },
    "numa_mode": {
        "cli": "-d",
        "type": "string",
        "description": "NUMA distribute mode: distribute, isolate, interleave",
        "tip": "Controls how memory is distributed across NUMA nodes. <b>distribute</b> spreads allocations evenly (default); <b>isolate</b> keeps memory on the local node; <b>interleave</b> stripes allocations across nodes for balanced access. Only effective when <code>--numa</code> is enabled.",
    },
    # KV Cache
    "cache_type_k": {
        "cli": "-ctk",
        "type": "string",
        "description": "KV cache data type for K (f16, q8_0, q4_0, iq4_nl, q5_0, q5_1)",
        "default": "f16",
        "tip": "Data type for the <b>key</b> component of the KV cache. Quantized types like <code>q8_0</code> or <code>q4_0</code> can cut K-cache VRAM by 30\u201350% with minimal perplexity impact, but on CUDA may reduce generation throughput by up to ~47% compared to <code>f16</code>; the tradeoff pays off most when you are VRAM-constrained or running very long contexts.",
    },
    "cache_type_v": {
        "cli": "-ctv",
        "type": "string",
        "description": "KV cache data type for V (f16, q8_0, q4_0, iq4_nl, q5_0, q5_1)",
        "default": "f16",
        "tip": "Data type for the <b>value</b> component of the KV cache. The V cache is generally harder to quantize than K without quality loss, so prefer <code>q8_0</code> over lower precisions here; use the same type as <code>-ctk</code> for simplicity, or keep it at <code>f16</code>/<code>bf16</code> if you notice output degradation.",
    },
    "no_kv_offload": {
        "cli": "-nkvo",
        "type": "bool",
        "description": "Disable KV cache GPU offloading (offloading is enabled by default)",
        "tip": "When set, disables offloading the KV cache to the GPU; the cache stays in CPU RAM instead. By default KV offloading is <b>enabled</b>, keeping the cache on the GPU for best throughput. Disable this if your VRAM is nearly exhausted and you have ample system RAM \u2014 you will trade some speed for the ability to run larger contexts or more parallel slots without an out-of-memory error.",
    },
    "mmap": {
        "cli": "-mmp",
        "type": "bool",
        "description": "Enable memory-mapped model loading (default: on)",
        "tip": "Enables <b>memory-mapped loading</b> for the model file. When enabled (default), the OS pages model weights in on demand, which is fast to start and allows efficient sharing between processes. Disable with <code>--no-mmap</code> if you want the entire model loaded into RAM upfront to avoid page faults during inference.",
    },
    "direct_io": {
        "cli": "-dio",
        "type": "bool",
        "description": "Enable direct I/O for model loading",
        "tip": "Bypasses OS page cache with <b>direct I/O</b> when loading the model file. Useful for very large models on systems with limited RAM where you want to avoid polluting the page cache. Can improve performance on NVMe storage by reducing cache thrashing.",
    },
    "embeddings": {
        "cli": "-embd",
        "type": "bool",
        "description": "Enable embeddings output mode",
        "tip": "Enables <b>embeddings-only mode</b> where the server returns vector embeddings instead of text generations. Use this when you need the model for semantic search, clustering, or other embedding-based tasks rather than chat/completion. Disables generation-related parameters.",
    },
    "cpu_moe": {
        "cli": "-ncmoe",
        "type": "int",
        "description": "Number of MoE experts to run on CPU (0 = all on GPU)",
        "tip": "For Mixture-of-Experts models (DeepSeek, Qwen-MoE), controls how many <b>expert layers run on CPU</b> when GPU VRAM is insufficient. Experts are sparse-activated, so only 1-2 are typically active per token. Set to <code>auto</code> to let the server determine the split, or an explicit integer to pin specific experts to CPU.",
    },
    "no_op_offload": {
        "cli": "-nopo",
        "type": "bool",
        "description": "Disable offloading of no-op operations to GPU",
        "tip": "Prevents <b>no-op (null) operations</b> from being offloaded to GPU. These are tiny operations that perform no actual computation but may have host-device synchronization overhead. Disabling their offload can reduce synchronization calls and improve throughput on high-latency GPU paths.",
    },
    "kv_unified": {
        "cli": "-kvu",
        "type": "bool",
        "description": "Use a single unified KV buffer shared across all sequences",
        "tip": "Allocates a <b>single unified KV buffer</b> shared across all inference slots instead of per-slot buffers. Automatically enabled when the slot count is determined at runtime (<code>--parallel auto</code>). Unified allocation is more memory-efficient under variable load, but disabling it (manual slot counts) can give more predictable per-slot memory bounds.",
    },
    "cache_ram": {
        "cli": "-cram",
        "type": "int",
        "description": "Max RAM cache size in MiB (-1 = no limit, 0 = disable)",
        "default": "8192",
        "tip": "Maximum size of the <b>RAM-side KV cache</b> in MiB (default <code>8192</code>). Set to <code>-1</code> for no limit (allow the cache to grow freely) or <code>0</code> to disable RAM caching entirely. Relevant mainly when KV offloading is disabled or when the GPU cache overflows; raising this cap prevents evictions at the cost of higher system RAM usage.",
    },
    "cache_reuse": {
        "cli": "--cache-reuse",
        "type": "int",
        "description": "Min chunk size for KV cache reuse via shifting (requires prompt caching)",
        "default": "0",
        "tip": "Minimum token-chunk size that the server will attempt to reuse from a previous request's KV cache via <b>KV shifting</b>, rather than re-processing the prefix. Setting a value like <code>64</code>\u2013<code>256</code> speeds up requests that share a long common prefix (e.g. a fixed system prompt); leave at <code>0</code> (disabled) if requests are diverse.",
    },
    # Multi-GPU
    "split_mode": {
        "cli": "-sm",
        "type": "string",
        "description": "How to split model across GPUs: none, layer (default), row",
        "default": "layer",
        "tip": "Controls how the model is distributed across multiple GPUs. <code>layer</code> (default) assigns whole layers sequentially \u2014 lowest synchronization overhead and usually fastest on PCIe systems. <code>row</code> splits each weight matrix in parallel, which can outperform <code>layer</code> on NVLink-connected cards. <code>none</code> uses a single GPU only \u2014 pair with <code>-mg</code> to pick which one.",
    },
    "tensor_split": {
        "cli": "-ts",
        "type": "string",
        "description": "Per-GPU memory proportions, comma-separated (e.g. 3,1 for 75%/25%)",
        "tip": "Relative proportions of VRAM to use on each GPU, as a comma-separated list \u2014 e.g. <code>3,1</code> gives GPU 0 75% and GPU 1 25%. Values are treated as ratios, so <code>1,2,2,2</code> means GPU 0 gets 1/7th and GPUs 1\u20133 each get 2/7ths. Use this when your GPUs have unequal VRAM; leaving it unset divides evenly.",
    },
    "main_gpu": {
        "cli": "-mg",
        "type": "int",
        "description": "Primary GPU index (for split-mode=none or row)",
        "default": "0",
        "tip": "Index of the GPU (0-based) used for intermediate computation and the KV cache. With <code>-sm none</code> this is the only GPU that runs the model; with <code>-sm row</code> it also holds the KV cache and handles reduction steps. On a multi-GPU system where one card is faster or has more VRAM, point <code>-mg</code> at it to reduce bottlenecks.",
    },
    "device": {
        "cli": "-dev",
        "type": "string",
        "description": "Comma-separated devices for offloading (none = CPU only)",
        "tip": "Explicit comma-separated list of devices to offload to, e.g. <code>CUDA0,CUDA1</code>. Use <code>--list-devices</code> to see device names available on your system. Useful when you want to restrict llama.cpp to a subset of installed GPUs \u2014 for example, reserving one GPU for other workloads \u2014 without relying on <code>CUDA_VISIBLE_DEVICES</code>.",
    },
    "override_tensor": {
        "cli": "-ot",
        "type": "string",
        "description": "Override tensor buffer type: pattern=type,... (e.g. blk\\..*\\.attn=CPU)",
        "tip": "Selectively redirects specific tensors to a different backend using a regex pattern: <code>pattern=BUFFER_TYPE</code>, e.g. <code>exps=CPU</code>. Most valuable for Mixture-of-Experts models (DeepSeek, Qwen-MoE): offload the rarely-activated conditional experts to CPU while keeping attention tensors on GPU. Run with <code>-v</code> to see tensor names.",
    },
    # Server slots
    "parallel": {
        "cli": "-np",
        "type": "int",
        "description": "Number of parallel server slots (concurrent requests, default: auto)",
        "tip": "Sets the number of <b>parallel request slots</b> the server handles simultaneously. Each slot maintains its own KV cache, so memory usage scales linearly: <code>-np 4</code> with a 4k context costs ~4\u00d7 the KV cache of a single slot. Increase for higher throughput under concurrent load; keep at <code>1</code> for lowest single-request latency.",
    },
    "no_cont_batching": {
        "cli": "-nocb",
        "type": "bool",
        "description": "Disable continuous batching (enabled by default)",
        "tip": "Disables <b>continuous (dynamic) batching</b>, which by default merges tokens from multiple in-flight requests into a single forward pass. Turning it off means each slot is processed sequentially, which can lower individual request latency at the cost of throughput. Only useful when you have a single user or when per-request determinism matters more than aggregate tokens/s.",
    },
    "slot_prompt_similarity": {
        "cli": "-sps",
        "type": "float",
        "description": "Min prompt similarity to reuse a slot KV cache (0.0 = disabled)",
        "default": "0.10",
        "tip": "Minimum cosine similarity (0.0\u20131.0) between a new prompt and an idle slot's cached prompt for the server to <b>reuse that slot's KV cache</b> instead of recomputing from scratch. The default <code>0.10</code> is very permissive. Raise toward <code>0.5</code>\u2013<code>0.8</code> for genuinely similar prompts only; set to <code>0.0</code> to always reuse the closest slot.",
    },
    "context_shift": {
        "cli": "--context-shift",
        "type": "bool",
        "description": "Enable context shift for infinite text generation (disabled by default)",
        "tip": "When enabled, allows <b>infinite text generation</b> by sliding older tokens out of the context window as it fills, rather than stopping with an error. This enables very long conversations without restarting, but early context is permanently lost. Not compatible with SWA-based models (e.g. Gemma 3) unless <code>--swa-full</code> is also enabled.",
    },
    "ctx_checkpoints": {
        "cli": "--ctx-checkpoints",
        "type": "int",
        "description": "Max context checkpoints per slot",
        "default": "8",
        "tip": "Sets the <b>maximum number of KV cache snapshots</b> stored per slot (default: 8). Checkpoints let the server instantly restore a past cache state when a request branches to a previously seen position, dramatically reducing recomputation \u2014 especially beneficial on large models with limited VRAM. Set to <code>0</code> to disable entirely.",
    },
    "no_cache_prompt": {
        "cli": "--no-cache-prompt",
        "type": "bool",
        "description": "Disable prompt caching (prompt caching is enabled by default)",
        "tip": "Disables <b>prompt caching</b>: by default the server reuses the KV cache from a previous request whenever the prompt shares a common prefix, avoiding redundant recomputation. Turning this off guarantees fully independent, deterministic processing of every request (useful for strict reproducibility), but eliminates the performance benefit for repeated or templated prompts.",
    },
    "swa_full": {
        "cli": "--swa-full",
        "type": "bool",
        "description": "Use full-size SWA cache instead of sliding window",
        "tip": "Forces the <b>SWA (Sliding Window Attention) cache to full context size</b>, disabling the default memory-saving token pruning used by models like Gemma 3. With default SWA, only a recent token window is cached (~80% less VRAM), but prompt caching, context reuse, and context-shift are unavailable. Enable if you need multi-turn prompt caching on SWA-based models, accepting the higher VRAM cost.",
    },
    "no_warmup": {
        "cli": "--no-warmup",
        "type": "bool",
        "description": "Disable warmup run with empty input (warmup is enabled by default)",
        "tip": "Skips the <b>empty-prompt warmup run</b> that llama-server performs before accepting requests. The warmup pre-heats CPU/GPU caches and JIT-compiled kernels so the first real request is not penalized. Disabling it saves a few seconds at startup but means your <b>first inference will be noticeably slower</b> \u2014 only recommended for development or rapid restart workflows.",
    },
    "fit": {
        "cli": "-fit",
        "type": "string",
        "description": "Auto-adjust unset args to fit device memory (on/off)",
        "default": "on",
        "tip": "When <b>on</b> (default), llama-server automatically reduces unset parameters like context size and batch size to fit within available device memory, preventing out-of-memory crashes without manual tuning. However, it may silently shrink your effective context length \u2014 use <code>--fit-ctx</code> to enforce a minimum floor (default: 4096 tokens).",
    },
    "override_kv": {
        "cli": "--override-kv",
        "type": "string",
        "description": "Override model metadata key (KEY=TYPE:VALUE) e.g. tokenizer.ggml.add_bos_token=bool:false",
        "tip": "Injects or overrides key-value metadata in the model's GGUF header at runtime, without modifying the file. Format: <code>key=type:value</code>, e.g. <code>tokenizer.ggml.bos_token_id=int:1</code>. Useful for correcting wrong tokenizer metadata in community models, forcing a specific rope scaling factor, or patching context length fields.",
    },
    # Sampling (additional)
    "min_p": {
        "cli": "--min-p",
        "type": "float",
        "description": "Min-p sampling (0.0 = disabled)",
        "default": "0.05",
        "tip": "Filters out tokens whose probability is below <b>min_p \u00d7 p_max</b> (the top token's probability), so the cutoff adapts to model confidence. Values of <code>0.05</code>\u2013<code>0.1</code> work well: <code>0.05</code> for creative tasks, <code>0.1</code> for general-purpose generation. Increasingly preferred over <code>top_p</code> in local deployments for better coherence at high temperatures.",
    },
    "presence_penalty": {
        "cli": "--presence-penalty",
        "type": "float",
        "description": "Presence penalty for repeated tokens (0.0 = disabled)",
        "default": "0.0",
        "tip": "Applies a <b>flat one-time penalty</b> to any token that has appeared at least once in the preceding context, regardless of how often. Non-zero values (e.g. <code>0.1</code>\u2013<code>0.5</code>) nudge the model toward introducing new topics and vocabulary; useful for open-ended brainstorming but can disrupt factual or structured output.",
    },
    "frequency_penalty": {
        "cli": "--frequency-penalty",
        "type": "float",
        "description": "Frequency penalty scaling with token frequency (0.0 = disabled)",
        "default": "0.0",
        "tip": "Applies a <b>proportional penalty</b> to tokens based on how many times they have already appeared \u2014 the more a token is used, the harder it is penalized. Values of <code>0.1</code>\u2013<code>0.4</code> help reduce word-level overuse without fully banning terms. Leave at <code>0.0</code> for tasks where consistent terminology matters (e.g. code, technical writing).",
    },
    "seed": {
        "cli": "-s",
        "type": "int",
        "description": "RNG seed for reproducible outputs (-1 = random)",
        "default": "-1",
        "tip": "Sets the <b>random number generator seed</b> for sampling, enabling reproducible outputs from the same prompt and settings. Use any fixed integer (e.g. <code>42</code>) when debugging or regression-testing. Note that exact determinism is not guaranteed across different hardware, batch sizes, or llama.cpp versions \u2014 treat it as best-effort reproducibility.",
    },
    "predict": {
        "cli": "-n",
        "type": "int",
        "description": "Max tokens to predict (-1 = infinite)",
        "default": "-1",
        "tip": "Sets the <b>maximum number of tokens to generate</b> per request (default: <code>-1</code> = unlimited). Use a positive value to cap runaway generation and protect against clients that omit <code>max_tokens</code>; <code>-1</code> defers entirely to per-request limits. A server-wide cap is recommended for multi-user deployments.",
    },
    "mirostat": {
        "cli": "--mirostat",
        "type": "int",
        "description": "Mirostat sampling: 0 disabled, 1 Mirostat, 2 Mirostat 2.0",
        "default": "0",
        "tip": "Selects the <b>Mirostat adaptive sampling algorithm</b>: <code>0</code> = disabled (use standard top-k/top-p), <code>1</code> = Mirostat v1, <code>2</code> = Mirostat 2.0 (recommended if enabling). Mirostat targets a specific perplexity level rather than fixed cutoffs, which can produce more consistently engaging output.",
    },
    "mirostat_lr": {
        "cli": "--mirostat-lr",
        "type": "float",
        "description": "Mirostat learning rate (eta)",
        "default": "0.1",
        "tip": "The <b>learning rate (eta)</b> for Mirostat: controls how quickly the algorithm adjusts its internal temperature estimate. Typical range is <code>0.05</code>\u2013<code>0.2</code>; lower values give smoother, slower adjustments, higher values make it react faster but can oscillate. The default <code>0.1</code> is a safe starting point for most models.",
    },
    "mirostat_ent": {
        "cli": "--mirostat-ent",
        "type": "float",
        "description": "Mirostat target entropy (tau)",
        "default": "5.0",
        "tip": "The <b>target entropy (tau)</b> for Mirostat: sets the desired perplexity of the generated text. Lower values (e.g. <code>2</code>\u2013<code>4</code>) produce more focused, coherent output; higher values (e.g. <code>6</code>\u2013<code>8</code>) allow more creative and varied text. The default <code>5.0</code> is a balanced starting point; tune downward for factual tasks and upward for storytelling.",
    },
    "dynatemp_range": {
        "cli": "--dynatemp-range",
        "type": "float",
        "description": "Dynamic temperature range (0.0 = disabled)",
        "default": "0.0",
        "tip": "Enables <b>dynamic temperature</b>: the actual sampling temperature is varied within <code>[temp \u2212 range, temp + range]</code> based on the entropy of the token distribution \u2014 lower entropy pulls temperature down, higher entropy pulls it up. A range of <code>0.1</code>\u2013<code>0.5</code> can help balance determinism on clear-cut tokens with creativity on ambiguous ones.",
    },
    # RoPE (additional)
    "rope_scaling": {
        "cli": "--rope-scaling",
        "type": "string",
        "description": "RoPE frequency scaling method: none, linear, yarn",
        "tip": "Selects the <b>RoPE context-extension algorithm</b>: <code>none</code> disables scaling (use when staying within trained context), <code>linear</code> compresses positional frequencies uniformly, and <code>yarn</code> uses the YaRN method which preserves short-range attention quality better at high extension ratios. For extending 2\u20134\u00d7 beyond trained context, <code>yarn</code> is generally the best choice.",
    },
    "rope_scale": {
        "cli": "--rope-scale",
        "type": "float",
        "description": "RoPE context scaling factor \u2014 expands context by N",
        "tip": "A convenience shorthand that sets the <b>RoPE context scaling factor</b> to expand context by N (equivalent to setting <code>--rope-freq-scale</code> to <code>1/N</code>). Use with <code>--rope-scaling yarn</code> and <code>--yarn-orig-ctx</code> for a clean YaRN setup \u2014 e.g. <code>-c 131072 --rope-scaling yarn --rope-scale 4 --yarn-orig-ctx 32768</code>.",
    },
    "yarn_orig_ctx": {
        "cli": "--yarn-orig-ctx",
        "type": "int",
        "description": "YaRN: original training context size of the model",
        "tip": "Tells YaRN the <b>original training context size</b> of the model so it can correctly calibrate the interpolation/extrapolation split. If left at <code>0</code>, llama.cpp reads this from model metadata, which is correct for most GGUF models \u2014 only set it manually if your model lacks this metadata or the auto-detected value is wrong.",
    },
    "yarn_ext_factor": {
        "cli": "--yarn-ext-factor",
        "type": "float",
        "description": "YaRN: extrapolation mix factor (0.0 = full interpolation, -1 = model default)",
        "tip": 'Controls the <b>blend between interpolation and extrapolation</b> in YaRN: <code>0.0</code> is pure interpolation (safest, best short-context quality), while <code>1.0</code> is full extrapolation (better for very long ranges but risks incoherence). The default <code>-1.0</code> means "use the model\'s recommended value." For most use cases leave it at <code>-1.0</code>.',
    },
    # LoRA
    "lora": {
        "cli": "--lora",
        "type": "path",
        "description": "LoRA adapter path (comma-separated for multiple adapters)",
        "tip": "Path to a <b>GGUF-format LoRA adapter</b> to apply on top of the base model at inference time; the flag can be repeated to stack multiple adapters. LoRA adapters add virtually no latency overhead compared to merged weights but do consume extra VRAM proportional to rank and layer coverage. Use this to hot-swap personality, style, or domain adaptations without reloading the base model.",
    },
    "lora_scaled": {
        "cli": "--lora-scaled",
        "type": "string",
        "description": "LoRA adapter with custom scale: FNAME:SCALE,...",
        "tip": "Like <code>--lora</code> but lets you specify a <b>custom scale factor</b> in the format <code>path/to/adapter.gguf:SCALE</code>. A scale of <code>1.0</code> is full strength (same as <code>--lora</code>); values below <code>1.0</code> soften the adapter's influence, useful for blending style adapters or reducing overfitting. Try values between <code>0.5</code>\u2013<code>0.8</code> when an adapter feels too dominant.",
    },
    # Speculative decoding
    "model_draft": {
        "cli": "-md",
        "type": "path",
        "description": "Draft model path for speculative decoding",
        "tip": "Path to the <b>smaller draft model</b> used for speculative decoding; it must share the same tokenizer vocabulary as the main model. The draft model generates candidate token sequences that the main model then verifies in parallel, yielding <b>2\u20133\u00d7 throughput gains</b> when the draft acceptance rate is high. A good rule of thumb is a draft model 5\u201310\u00d7 smaller than the target.",
    },
    "gpu_layers_draft": {
        "cli": "-ngld",
        "type": "int",
        "description": "Max GPU layers for draft model",
        "tip": "Controls how many <b>draft model layers are offloaded to VRAM</b>. Offloading the draft model fully to GPU is strongly recommended \u2014 draft generation is the latency bottleneck and a CPU-bound draft model will negate most speculative decoding gains. If VRAM is tight, prioritize keeping the main model fully on GPU instead.",
    },
    "draft_max": {
        "cli": "--draft",
        "type": "int",
        "description": "Max draft tokens for speculative decoding",
        "default": "16",
        "tip": "Maximum number of <b>tokens the draft model generates per speculative step</b> before the main model verifies them (default: <code>16</code>). Higher values increase throughput when the draft acceptance rate is high, but each rejected token wastes compute. Tune up to <code>32</code>\u2013<code>64</code> for predictable workloads; reduce to <code>4</code>\u2013<code>8</code> for creative tasks where the draft model diverges frequently.",
    },
    "threads_draft": {
        "cli": "-td",
        "type": "int",
        "description": "CPU threads for draft model generation (default: same as -t)",
        "tip": "Number of <b>CPU threads dedicated to the draft model</b> during generation (defaults to same as <code>-t</code>). Because draft generation must finish before the main model can verify, keeping this at a lower value (e.g. <code>2</code>\u2013<code>4</code>) frees cores for the main model when both share the same CPU.",
    },
    # Chat template
    "chat_template": {
        "cli": "--chat-template",
        "type": "string",
        "description": "Custom Jinja chat template (overrides model metadata). Use built-in name or full template string.",
        "tip": "Overrides the <b>chat template</b> embedded in the model's metadata with a custom Jinja string, or selects a named built-in (e.g. <code>llama3</code>, <code>chatml</code>, <code>mistral-v3</code>, <code>phi4</code>). Use this when the model ships with an incorrect or missing template, or to standardize formatting across multiple models.",
    },
    "chat_template_file": {
        "cli": "--chat-template-file",
        "type": "path",
        "description": "Path to a Jinja chat template file (overrides model metadata)",
        "tip": "Loads a <b>Jinja chat template from a file</b> instead of a command-line string, avoiding shell escaping issues for complex templates. Functionally equivalent to <code>--chat-template</code> but preferred for long or multi-line templates; if both are set, the file takes precedence.",
    },
    "chat_template_kwargs": {
        "cli": "--chat-template-kwargs",
        "type": "string",
        "description": 'Additional JSON params for the chat template parser, e.g. \'{"key":"value"}\'',
        "tip": "Passes a <b>JSON object</b> of extra variables into the Jinja template renderer. Use this to supply template-specific flags or metadata that the model's Jinja template references but that standard chat fields do not cover; must be valid JSON or the server will reject it at startup.",
    },
    # Features
    "flash_attn": {
        "cli": "-fa",
        "type": "string",
        "description": "Flash attention mode (on, off, or auto)",
        "default": "auto",
        "tip": "Controls <b>Flash Attention</b>, a memory-efficient attention algorithm that reduces VRAM usage and often increases throughput on supported GPUs. Set to <code>on</code> to force-enable (requires compatible hardware), <code>off</code> if you encounter stability issues, or leave as <code>auto</code> (default) to let the server detect support automatically.",
    },
    "jinja": {
        "cli": "--jinja",
        "type": "bool",
        "description": "Enable Jinja template parsing",
        "tip": "Enables the <b>Jinja template engine</b> for processing chat templates, required for models with complex or custom prompt formatting (e.g. tool-use, reasoning models). Disable with <code>--no-jinja</code> only if you encounter template parsing errors or need raw prompt pass-through \u2014 most modern models expect Jinja to be active.",
    },
    "verbose": {
        "cli": "-v",
        "type": "bool",
        "description": "Enable verbose logging (max verbosity)",
        "tip": "Sets log verbosity to <b>maximum level</b>, printing every internal message including token sampling, KV-cache events, and decode timings. Use during initial setup or debugging to diagnose hangs and misconfiguration; avoid in production as output volume can be overwhelming and may impact performance.",
    },
    "log_verbosity": {
        "cli": "--log-verbosity",
        "type": "int",
        "description": "Verbosity threshold: 0 generic, 1 error, 2 warning, 3 info (default), 4 debug",
        "default": "3",
        "tip": "Filters log output by severity threshold: <code>0</code>=generic, <code>1</code>=errors only, <code>2</code>=warnings, <code>3</code>=info (default), <code>4</code>=debug. Lower values reduce noise in production; raise to <code>4</code> when troubleshooting subtle issues like template mismatches or slow inference without enabling full <code>-v</code> flood.",
    },
    "log_file": {
        "cli": "--log-file",
        "type": "string",
        "description": "Log output to file",
        "tip": "Redirects all log output to a <b>file</b> instead of stdout, useful for capturing server activity in background/daemon deployments. Pair with <code>--log-verbosity 4</code> for a persistent debug trace; remember to rotate or truncate the file over long runs to avoid unbounded disk growth.",
    },
    "reasoning_format": {
        "cli": "--reasoning-format",
        "type": "string",
        "description": "Reasoning format (auto, cot, etc.)",
        "tip": "Controls how <b>chain-of-thought / reasoning tokens</b> are surfaced in API responses. <code>auto</code> (default) detects the model's capability; <code>deepseek</code> extracts <code>&lt;think&gt;</code> blocks into a separate <code>reasoning_content</code> field; <code>none</code> leaves thought tags raw inside <code>content</code>.",
    },
    # Memory
    "no_mmap": {
        "cli": "--no-mmap",
        "type": "bool",
        "description": "Disable memory-mapped model loading (loads fully into RAM)",
        "tip": "Disables memory-mapping the model file from disk. By default, <b>mmap is on</b>: the OS pages model weights in on demand, which is fast to start and allows the kernel to evict pages under memory pressure. Disabling mmap forces the entire model to be <b>read into RAM up front</b>, making startup slower but eliminating page-fault stalls during inference.",
    },
    # RoPE scaling
    "rope_freq_base": {
        "cli": "--rope-freq-base",
        "type": "int",
        "description": "RoPE frequency base",
        "tip": "Controls the <b>base theta frequency</b> for RoPE positional encoding; higher values (e.g. <code>500000</code> for Llama 3) effectively stretch positional space and are the primary knob for <b>NTK-aware context extension</b> without retraining. The default is loaded from the model \u2014 only override when you need to push context beyond what the model was trained on.",
    },
    "rope_freq_scale": {
        "cli": "--rope-freq-scale",
        "type": "float",
        "description": "RoPE frequency scaling factor",
        "tip": "Scales all RoPE frequencies by <code>1/N</code>, effectively expanding usable context by a factor of <b>N</b> through linear interpolation of position embeddings. For example, <code>0.5</code> doubles context from 4096 to 8192, but expect a measurable perplexity penalty unless the model was fine-tuned with the same scale. Use in combination with <code>--rope-freq-base</code> for NTK-aware scaling.",
    },
}

VLLM_FLAGS = {
    # ========== CONTEXT & MEMORY (Top Priority) ==========
    "max_model_len": {
        "cli": "--max-model-len",
        "type": "int",
        "category": "Context & Memory",
        "description": "Maximum context length in tokens. Determines longest input the model can process.",
        "impact": "Critical",
    },
    "gpu_memory_utilization": {
        "cli": "--gpu-memory-utilization",
        "type": "float",
        "category": "Context & Memory",
        "description": "Fraction of GPU memory to use (0.0-1.0). Higher = more concurrent requests but risk of OOM.",
        "default": "0.92",
        "impact": "High",
    },
    "swap_space": {
        "cli": "--swap-space",
        "type": "float",
        "category": "Context & Memory",
        "description": "CPU swap space per GPU in GiB. Spills to CPU when GPU full, reduces OOM but slower.",
        "default": "4",
        "impact": "Medium",
    },
    "cpu_offload_gb": {
        "cli": "--cpu-offload-gb",
        "type": "float",
        "category": "Context & Memory",
        "description": "Offload this much memory to CPU. Virtually increases GPU capacity at cost of speed.",
        "default": "0",
        "impact": "Medium",
    },
    # ========== QUANTIZATION & PRECISION ==========
    "quantization": {
        "cli": "--quantization",
        "type": "string",
        "category": "Quantization & Precision",
        "description": "Quantization method (awq, gptq, fp8, etc.). Reduces model size and speeds up inference.",
        "options": "aqlm, awq, deepspeedfp, fp8, gptq_marlin, awq_marlin, gptq, bitsandbytes, qqq, hqq, marlin",
        "impact": "Critical",
    },
    "dtype": {
        "cli": "--dtype",
        "type": "string",
        "category": "Quantization & Precision",
        "description": "Model data type (auto, float16, bfloat16, float32). Affects speed and memory.",
        "options": "auto, float16, bfloat16, float32",
        "impact": "High",
    },
    "kv_cache_dtype": {
        "cli": "--kv-cache-dtype",
        "type": "string",
        "category": "Quantization & Precision",
        "description": "KV cache format (auto, fp8, fp8_e5m2, fp8_e4m3). FP8 saves 40-50% memory for long sequences.",
        "options": "auto, fp8, fp8_e5m2, fp8_e4m3",
        "impact": "High",
    },
    # ========== BATCHING & THROUGHPUT ==========
    "max_num_batched_tokens": {
        "cli": "--max-num-batched-tokens",
        "type": "int",
        "category": "Batching & Throughput",
        "description": "Maximum tokens processed per batch iteration. Higher = better throughput, higher memory.",
        "default": "8192",
        "impact": "High",
    },
    "max_num_seqs": {
        "cli": "--max-num-seqs",
        "type": "int",
        "category": "Batching & Throughput",
        "description": "Maximum concurrent sequences. Higher = more parallel requests but uses more memory.",
        "default": "128",
        "impact": "High",
    },
    "max_num_partial_prefills": {
        "cli": "--max-num-partial-prefills",
        "type": "int",
        "category": "Batching & Throughput",
        "description": "Maximum concurrent chunked prefills. Improves throughput for long prompts.",
        "default": "1",
        "impact": "Medium",
    },
    "enable_chunked_prefill": {
        "cli": "--enable-chunked-prefill",
        "type": "bool",
        "category": "Batching & Throughput",
        "description": "Split large prompts into chunks to reduce first-token latency.",
        "impact": "Medium",
    },
    # ========== CACHING & OPTIMIZATION ==========
    "enable_prefix_caching": {
        "cli": "--enable-prefix-caching",
        "type": "bool",
        "category": "Caching & Optimization",
        "description": "Reuse computation for repeated prompt prefixes. Massive speedup for repeated queries.",
        "impact": "High",
    },
    "block_size": {
        "cli": "--block-size",
        "type": "int",
        "category": "Caching & Optimization",
        "description": "Token block size (8, 16, 32, 64, 128). Affects memory efficiency vs latency.",
        "options": "8, 16, 32, 64, 128",
        "impact": "Low",
    },
    # ========== DISTRIBUTED & SCALING ==========
    "tensor_parallel_size": {
        "cli": "--tensor-parallel-size",
        "type": "int",
        "category": "Distributed & Scaling",
        "description": "Shard model across N GPUs. Essential for models larger than single GPU.",
        "default": "1",
        "impact": "Critical",
    },
    "pipeline_parallel_size": {
        "cli": "--pipeline-parallel-size",
        "type": "int",
        "category": "Distributed & Scaling",
        "description": "Pipeline parallelism across N stages. Distribute across multiple nodes.",
        "default": "1",
        "impact": "High",
    },
    # ========== MODEL FORMAT & LOADING ==========
    "load_format": {
        "cli": "--load-format",
        "type": "string",
        "category": "Model Format & Loading",
        "description": "Weight format (auto, safetensors, tensorizer, gguf, etc.). Auto-detect or force specific format.",
        "options": "auto, safetensors, pt, gguf, tensorizer, npcache",
        "impact": "Medium",
    },
    "trust_remote_code": {
        "cli": "--trust-remote-code",
        "type": "bool",
        "category": "Model Format & Loading",
        "description": "Allow execution of custom code from model repo. Required for some models.",
        "impact": "Low",
    },
    # ========== GENERATION & SAMPLING ==========
    "max_logprobs": {
        "cli": "--max-logprobs",
        "type": "int",
        "category": "Generation & Sampling",
        "description": "Maximum log probabilities to return. For ranking/uncertainty estimation.",
        "default": "20",
        "impact": "Low",
    },
    "seed": {
        "cli": "--seed",
        "type": "int",
        "category": "Generation & Sampling",
        "description": "Random seed for reproducible outputs.",
        "impact": "Low",
    },
    # ========== LORA & ADAPTERS ==========
    "enable_lora": {
        "cli": "--enable-lora",
        "type": "bool",
        "category": "LoRA & Adapters",
        "description": "Enable LoRA adapter support for fine-tuned model variants.",
        "impact": "Medium",
    },
    "max_loras": {
        "cli": "--max-loras",
        "type": "int",
        "category": "LoRA & Adapters",
        "description": "Maximum LoRA adapters in a single batch.",
        "default": "1",
        "impact": "Low",
    },
    "max_lora_rank": {
        "cli": "--max-lora-rank",
        "type": "int",
        "category": "LoRA & Adapters",
        "description": "Maximum LoRA rank (complexity of adapter).",
        "default": "16",
        "impact": "Low",
    },
    # ========== MULTIMODAL ==========
    "limit_mm_per_prompt": {
        "cli": "--limit-mm-per-prompt",
        "type": "string",
        "category": "Multimodal",
        "description": 'Limit multimodal inputs per request. Format: "image=16,video=2"',
        "impact": "Low",
    },
    # ========== FEATURES & TOOLS ==========
    "enable_auto_tool_choice": {
        "cli": "--enable-auto-tool-choice",
        "type": "bool",
        "category": "Features & Tools",
        "description": "Enable automatic tool choice in function calling.",
        "default": "true",
        "impact": "Low",
    },
    "tool_call_parser": {
        "cli": "--tool-call-parser",
        "type": "string",
        "category": "Features & Tools",
        "description": "Tool call parser (hermes, pythonic, etc.). Model-specific.",
        "options": "hermes, pythonic, auto",
        "default": "hermes",
        "impact": "Low",
    },
    # ========== ROPE SCALING ==========
    "rope_scaling": {
        "cli": "--rope-scaling",
        "type": "string",
        "category": "RoPE Scaling",
        "description": 'RoPE scaling config as JSON. Extends context length. Example: {"type":"dynamic","factor":2.0}',
        "impact": "Medium",
    },
    "rope_theta": {
        "cli": "--rope-theta",
        "type": "float",
        "category": "RoPE Scaling",
        "description": "RoPE theta parameter. Frequency base for positional encoding.",
        "impact": "Low",
    },
    # ========== ATTENTION & OPTIMIZATION ==========
    "attention_backend": {
        "cli": "VLLM_ATTENTION_BACKEND",
        "type": "env",
        "category": "Attention & Optimization",
        "description": "Attention backend (FLASHINFER, XFORMERS, TORCH, etc.). FLASHINFER is fastest.",
        "options": "FLASHINFER, XFORMERS, TORCH",
        "default": "FLASHINFER",
        "impact": "High",
    },
    # ========== SCHEDULING ==========
    "scheduling_policy": {
        "cli": "--scheduling-policy",
        "type": "string",
        "category": "Scheduling",
        "description": "Scheduling policy (fcfs=first-come-first-serve, priority=by priority).",
        "options": "fcfs, priority",
        "default": "fcfs",
        "impact": "Low",
    },
    "preemption_mode": {
        "cli": "--preemption-mode",
        "type": "string",
        "category": "Scheduling",
        "description": "Preemption mode (recompute=recompute from checkpoint, swap=swap to CPU).",
        "options": "recompute, swap",
        "impact": "Medium",
    },
}

# ============================================
# VALIDATION RULES
# ============================================

LLAMACPP_VALIDATION = {
    "context_length": {"type": "int", "min": 512, "max": 1000000},
    "gpu_layers": {"type": "int", "min": 0, "max": 999},
    "batch_size": {"type": "int", "min": 1, "max": 16384},
    "ubatch_size": {"type": "int", "min": 1, "max": 16384},
    "repeat_penalty": {"type": "float", "min": 0.0, "max": 2.0},
    "top_p": {"type": "float", "min": 0.0, "max": 1.0},
    "top_k": {"type": "float", "min": 1.0, "max": 100.0},
    "temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "rope_freq_base": {"type": "int", "min": 1, "max": 1000000},
    "rope_freq_scale": {"type": "float", "min": 0.0, "max": 10.0},
    "cpu_mask": {"type": "string"},
    "cpu_strict": {"type": "int", "min": 0, "max": 1},
    "numa_mode": {"type": "string"},
    "mmap": {"type": "bool"},
    "direct_io": {"type": "bool"},
    "embeddings": {"type": "bool"},
    "cpu_moe": {"type": "int", "min": 0, "max": 100},
    "no_op_offload": {"type": "bool"},
}

VLLM_VALIDATION = {
    "max_model_len": {"type": "int", "min": 512, "max": 1000000},
    "gpu_memory_utilization": {"type": "float", "min": 0.1, "max": 1.0},
    "max_num_batched_tokens": {"type": "int", "min": 1, "max": 100000},
    "max_num_seqs": {"type": "int", "min": 1, "max": 1000},
}

# ============================================
# LLAMACPP CATEGORIES (applied programmatically)
# ============================================

_LLAMACPP_CATEGORIES = {
    "mmproj_path": "Features",
    "context_length": "Context",
    "gpu_layers": "GPU",
    "batch_size": "Batching",
    "ubatch_size": "Batching",
    "repeat_penalty": "Sampling",
    "top_p": "Sampling",
    "top_k": "Sampling",
    "temperature": "Sampling",
    "threads": "CPU",
    "threads_batch": "CPU",
    "prio": "CPU",
    "poll": "CPU",
    "numa": "CPU",
    "cpu_mask": "CPU",
    "cpu_strict": "CPU",
    "numa_mode": "CPU",
    "cache_type_k": "KV Cache",
    "cache_type_v": "KV Cache",
    "no_kv_offload": "KV Cache",
    "mmap": "Memory",
    "direct_io": "Memory",
    "embeddings": "Features",
    "cpu_moe": "Multi-GPU",
    "no_op_offload": "GPU",
    "kv_unified": "KV Cache",
    "cache_ram": "KV Cache",
    "cache_reuse": "KV Cache",
    "split_mode": "Multi-GPU",
    "tensor_split": "Multi-GPU",
    "main_gpu": "Multi-GPU",
    "device": "Multi-GPU",
    "override_tensor": "Multi-GPU",
    "parallel": "Batching",
    "no_cont_batching": "Batching",
    "slot_prompt_similarity": "Batching",
    "context_shift": "Context",
    "ctx_checkpoints": "Context",
    "no_cache_prompt": "KV Cache",
    "swa_full": "Context",
    "no_warmup": "Memory",
    "fit": "GPU",
    "override_kv": "Features",
    "min_p": "Sampling",
    "presence_penalty": "Sampling",
    "frequency_penalty": "Sampling",
    "seed": "Sampling",
    "predict": "Context",
    "mirostat": "Sampling",
    "mirostat_lr": "Sampling",
    "mirostat_ent": "Sampling",
    "dynatemp_range": "Sampling",
    "rope_scaling": "RoPE",
    "rope_scale": "RoPE",
    "yarn_orig_ctx": "RoPE",
    "yarn_ext_factor": "RoPE",
    "lora": "LoRA",
    "lora_scaled": "LoRA",
    "model_draft": "Speculative",
    "gpu_layers_draft": "Speculative",
    "draft_max": "Speculative",
    "threads_draft": "Speculative",
    "chat_template": "Features",
    "chat_template_file": "Features",
    "chat_template_kwargs": "Features",
    "flash_attn": "GPU",
    "jinja": "Features",
    "verbose": "Features",
    "log_verbosity": "Features",
    "log_file": "Features",
    "reasoning_format": "Features",
    "no_mmap": "Memory",
    "rope_freq_base": "RoPE",
    "rope_freq_scale": "RoPE",
}

for _key, _cat in _LLAMACPP_CATEGORIES.items():
    if _key in LLAMACPP_FLAGS:
        LLAMACPP_FLAGS[_key]["category"] = _cat

# ============================================
# HELPER FUNCTIONS
# ============================================


def get_flag_metadata(template_type: str) -> Dict[str, Any]:
    """Get flag metadata for template type"""
    if template_type == "llamacpp":
        return LLAMACPP_FLAGS
    elif template_type == "vllm":
        return VLLM_FLAGS
    else:
        return {}


def get_validation_rules(template_type: str) -> Dict[str, Any]:
    """Get validation rules for template type"""
    if template_type == "llamacpp":
        return LLAMACPP_VALIDATION
    elif template_type == "vllm":
        return VLLM_VALIDATION
    else:
        return {}


def generate_service_name(template_type: str, alias: str) -> str:
    """
    Generate service name from template type and alias.

    Convention: {template_type}-{alias}
    Example: llamacpp-minimax-m2-q2

    Args:
        template_type: 'llamacpp' or 'vllm'
        alias: Model alias

    Returns:
        Sanitized service name
    """
    return sanitize_service_name(f"{template_type}-{alias}")


def render_cli_flag(flag_name: str, flag_value: str) -> Optional[str]:
    """
    Render a CLI flag (already in CLI form like -ngl, --flash-attn) as argument.

    Args:
        flag_name: The CLI flag (e.g. "-ngl", "--flash-attn", "-fa")
        flag_value: The flag value (empty string for boolean flags)

    Returns:
        Rendered CLI argument string, or None if flag name is invalid.

    Note:
        For boolean flags (no value needed), pass empty string as flag_value.
        The flag will be rendered as just the flag name (e.g., "--verbose").

        This function includes defensive validation - it returns None for
        invalid flag names rather than raising an exception. Use
        validate_custom_flag_name() for explicit validation with error messages.
    """
    if not flag_name or not flag_name.startswith("-"):
        return None
    if not flag_value or flag_value.strip() == "":
        return flag_name  # Boolean flag
    return f"{flag_name} {flag_value}"


def validate_custom_flag_name(flag_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate custom flag name format.

    Args:
        flag_name: The flag name to validate

    Returns:
        (is_valid, error_message or None)
    """
    if not flag_name:
        return False, "Flag name cannot be empty"
    if not flag_name.startswith("-"):
        return False, "Flag name must start with - or --"
    name_part = flag_name.lstrip("-")
    if not name_part:
        return False, "Flag name cannot be just dashes"
    if not all(c.isalnum() or c in "-_" for c in name_part):
        return False, "Invalid characters in flag name"
    return True, None


def validate_service_config(
    template_type: str, config: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validate service configuration.

    Args:
        template_type: 'llamacpp' or 'vllm'
        config: Service configuration dict

    Returns:
        (is_valid, list_of_error_messages)
    """
    errors = []

    # Check mandatory fields
    mandatory = MANDATORY_FIELDS.get(template_type, [])
    for field in mandatory:
        if field not in config or not config[field]:
            errors.append(f"Missing mandatory field: {field}")

    # Check port
    if "port" not in config:
        errors.append("Missing port number")
    else:
        try:
            port = int(config["port"])
            if port < 1024 or port > 65535:
                errors.append(f"Port must be between 1024 and 65535, got {port}")
        except (ValueError, TypeError):
            errors.append(f"Invalid port: {config['port']}")

    # Validate params (unified CLI-keyed format)
    params = config.get("params", {})
    for flag_name, flag_value in params.items():
        if flag_name.startswith("-"):
            is_valid, error = validate_custom_flag_name(flag_name)
            if not is_valid:
                errors.append(f"Param '{flag_name}': {error}")

    return len(errors) == 0, errors
