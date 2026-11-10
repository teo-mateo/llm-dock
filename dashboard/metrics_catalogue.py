from dataclasses import dataclass

VLLM_CURATED_METRICS = {
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:num_preemptions_total",
    "vllm:engine_sleep_state",
    "vllm:kv_cache_usage_perc",
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:prompt_tokens_recomputed_total",
    "vllm:generation_tokens_total",
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_per_pos_total",
    "vllm:estimated_flops_per_gpu_total",
    "vllm:estimated_read_bytes_per_gpu_total",
    "vllm:estimated_write_bytes_per_gpu_total",
}

LLAMACPP_CURATED_METRICS = {
    "llamacpp:prompt_tokens_total",
    "llamacpp:prompt_seconds_total",
    "llamacpp:tokens_predicted_total",
    "llamacpp:tokens_predicted_seconds_total",
    "llamacpp:n_decode_total",
    "llamacpp:n_tokens_max",
    "llamacpp:prompt_tokens_seconds",
    "llamacpp:predicted_tokens_seconds",
    "llamacpp:requests_processing",
    "llamacpp:requests_deferred",
    "llamacpp:n_busy_slots_per_decode",
}

# Emitted by the ninfer-metrics.patch engine route (12 unlabeled families rendered
# from the engine's published RuntimeStats snapshot plus the startup-resolved KV
# capacity). Spec-acceptance and preemption families are deliberately absent: NInfer
# has no service-level aggregate for either, so the panel renders those as "—".
NINFER_CURATED_METRICS = {
    "ninfer:prompt_tokens_total",
    "ninfer:generation_tokens_total",
    "ninfer:decode_rounds_total",
    "ninfer:num_requests_running",
    "ninfer:num_requests_waiting",
    "ninfer:num_requests_prefilling",
    "ninfer:kv_cache_usage_perc",
    "ninfer:kv_occupied_pages",
    "ninfer:kv_capacity_page_groups",
    "ninfer:prefix_cache_queries_total",
    "ninfer:prefix_cache_hits_total",
    "ninfer:host_kv_occupied_bytes",
}

# Mirrors the Pennyroyal metrics collector (image pin in sglang/Dockerfile).
# The two acceptance/cache-hit values are gauges, not lifetime counter ratios.
SGLANG_CURATED_METRICS = {
    "sglang:num_running_reqs", "sglang:num_queue_reqs",
    "sglang:token_usage", "sglang:cache_hit_rate", "sglang:gen_throughput",
    "sglang:prompt_tokens_total", "sglang:generation_tokens_total",
    "sglang:spec_accept_rate", "sglang:spec_accept_length",
    "sglang:num_retracted_requests_total",
    "sglang:realtime_tokens_total", "sglang:num_requests_total",
    "sglang:max_total_num_tokens", "sglang:context_len",
    "sglang:kv_used_tokens", "sglang:kv_evictable_tokens", "sglang:kv_available_tokens",
    "sglang:mamba_used_tokens", "sglang:mamba_evictable_tokens", "sglang:mamba_available_tokens",
    "sglang:hicache_host_used_tokens", "sglang:hicache_host_total_tokens",
    "sglang:weight_memory_usage_gb", "sglang:kv_cache_memory_usage_gb",
    "sglang:graph_memory_usage_gb",
}

# Curated set per engine: the whitelist keeps uninteresting families out.
CURATED_METRICS = {
    "vllm": VLLM_CURATED_METRICS,
    "llamacpp": LLAMACPP_CURATED_METRICS,
    "ninfer": NINFER_CURATED_METRICS,
    "sglang": SGLANG_CURATED_METRICS,
}

METRICS_ENGINES = frozenset(CURATED_METRICS)


@dataclass(frozen=True)
class ParseOptions:
    """Per-engine quirks of reading the Prometheus text.

    position_family: a family whose samples are keyed by their `position`
    label (as position_<n>) instead of by the whole label set.
    drop_created_samples: Python counters also emit a *_created timestamp that
    shares the counter's labels but is not a count; keep only the counter.
    """

    position_family: str | None = None
    drop_created_samples: bool = False


PARSE_OPTIONS = {
    "vllm": ParseOptions(position_family="vllm:spec_decode_num_accepted_tokens_per_pos_total"),
    "sglang": ParseOptions(drop_created_samples=True),
}
DEFAULT_PARSE_OPTIONS = ParseOptions()

# Engines whose server answers /slots with live per-slot generation state.
SLOTS_ENGINES = frozenset({"llamacpp"})
