import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flag_metadata import VLLM_FLAGS

# The 21 entries added in #196 (the issue's 20, plus --enable-prompt-tokens-details,
# re-derived from services.json in step 4: it runs on every vLLM service here and had
# no metadata entry).
NEW_KEYS = {
    "runner": "--runner",
    "convert": "--convert",
    "enforce_eager": "--enforce-eager",
    "reasoning_parser": "--reasoning-parser",
    "speculative_config": "--speculative-config",
    "distributed_executor_backend": "--distributed-executor-backend",
    "enable_sleep_mode": "--enable-sleep-mode",
    "kv_cache_memory_bytes": "--kv-cache-memory-bytes",
    "optimization_level": "--optimization-level",
    "cudagraph_capture_sizes": "--cudagraph-capture-sizes",
    "performance_mode": "--performance-mode",
    "chat_template": "--chat-template",
    "default_chat_template_kwargs": "--default-chat-template-kwargs",
    "override_generation_config": "--override-generation-config",
    "stream_interval": "--stream-interval",
    "language_model_only": "--language-model-only",
    "max_parallel_loading_workers": "--max-parallel-loading-workers",
    "safetensors_load_strategy": "--safetensors-load-strategy",
    "hf_overrides": "--hf-overrides",
    "enable_log_requests": "--enable-log-requests",
    "enable_prompt_tokens_details": "--enable-prompt-tokens-details",
}

# JSON-valued flags: the stored value must be pre-quoted per the services.json quoting
# rule, so an empty prefill is the only honest one — the example goes in `tip`.
JSON_VALUED = {
    "speculative_config",
    "override_generation_config",
    "hf_overrides",
    "default_chat_template_kwargs",
}

REQUIRED_FIELDS = ("cli", "type", "category", "description", "impact")


def test_coverage_grew_from_30_to_51():
    assert len(VLLM_FLAGS) == 51, (
        f"VLLM_FLAGS holds {len(VLLM_FLAGS)} entries; #196 added the 21 named in "
        "test_vllm_flag_metadata.py on top of the 30 pre-existing entries"
    )


def test_new_entries_exist_with_required_fields():
    missing = {k for k in NEW_KEYS if k not in VLLM_FLAGS}
    assert not missing, f"missing entries: {sorted(missing)}"
    for key in NEW_KEYS:
        meta = VLLM_FLAGS[key]
        for field in REQUIRED_FIELDS:
            assert field in meta and meta[field], f"{key}: missing {field!r}"


def test_new_cli_is_the_dashed_form_of_its_key():
    for key, cli in NEW_KEYS.items():
        assert VLLM_FLAGS[key]["cli"] == cli, f"{key}: cli drifted from {cli!r}"
        assert cli.startswith("--")


def test_no_bool_entry_carries_a_prefill_default():
    # A bool with a `default` renders as `--flag true` (render_cli_flag renders a
    # non-empty value as `--flag <value>`), which vLLM's parser rejects.
    offenders = [
        key
        for key, meta in VLLM_FLAGS.items()
        if meta.get("type") == "bool" and meta.get("default") not in (None, "")
    ]
    assert offenders == [], f"bool entries with a prefill default: {offenders}"


def test_json_valued_flags_have_no_prefill_default():
    offenders = [k for k in JSON_VALUED if VLLM_FLAGS.get(k, {}).get("default")]
    assert offenders == [], (
        f"JSON-valued flags must prefill empty (the example belongs in `tip`): {offenders}"
    )


def test_prefill_values_are_documented_choices():
    # Choices as documented for v0.24.0 and re-verified against the built image's
    # `serve --help=all` (image id and vllm --version are recorded in the PR body).
    assert VLLM_FLAGS["optimization_level"]["default"] in ("0", "1", "2", "3")
    assert VLLM_FLAGS["performance_mode"]["default"] in (
        "balanced",
        "interactivity",
        "throughput",
    )
    assert int(VLLM_FLAGS["stream_interval"]["default"]) >= 1
    assert VLLM_FLAGS["runner"]["type"] == "string"
    assert VLLM_FLAGS["convert"]["type"] == "string"


def test_new_bool_types_are_bool():
    bool_flags = {
        "enforce_eager",
        "enable_sleep_mode",
        "language_model_only",
        "enable_log_requests",
        "enable_prompt_tokens_details",
    }
    for key in bool_flags:
        assert VLLM_FLAGS[key]["type"] == "bool", f"{key}: expected type bool"
