import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flag_metadata import (
    BOOL_FLAG_VALUE_REJECTED,
    LLAMACPP_LLAMA_BENCH_FLAGS,
    TABBYAPI_FLAGS,
    VLLM_FLAGS,
    get_flag_metadata,
)


def test_enable_auto_tool_choice_prefills_nothing():
    # ParameterReference inserts `f.default || ''` as the flag value on click.
    # With "true" stored, the rendered command line is
    # `--enable-auto-tool-choice true`, which vLLM's parser rejects as an
    # unrecognized argument; the bare flag is what passes.
    entry = VLLM_FLAGS["enable_auto_tool_choice"]
    assert entry["type"] == "bool"
    assert entry.get("default", "") in (None, "")


def test_value_rejected_engines_carry_no_bool_prefill_default():
    # The per-engine rule: on a parser that rejects `--flag value` for its
    # boolean flags, no bool metadata entry may carry a prefill default.
    # This is the guard that failed on the pre-fix metadata (vllm carried
    # "true" on --enable-auto-tool-choice).
    for template_type in sorted(BOOL_FLAG_VALUE_REJECTED):
        offenders = [
            meta["cli"]
            for meta in get_flag_metadata(template_type).values()
            if meta.get("type") == "bool" and str(meta.get("default", "")).strip()
        ]
        assert offenders == [], f"{template_type}: {offenders}"


def test_tabbyapi_keeps_its_value_defaults():
    # The inverse class: tabbyapi's argparse requires a value for every flag,
    # booleans included (a bare `--vision` is rejected), so its "True"/"False"
    # defaults are load-bearing and must not be "fixed" to empty.
    assert "tabbyapi" not in BOOL_FLAG_VALUE_REJECTED
    bools = [m for m in TABBYAPI_FLAGS.values() if m.get("type") == "bool"]
    assert len(bools) == 11
    for meta in bools:
        assert str(meta.get("default", "")).strip(), f"{meta['cli']} lost its value"


def test_llamacpp_bench_value_defaults_unchanged():
    # The bench parser accepts explicit values for its bools (<0|1> metavars),
    # so these prefills are valid, not landmines. -v is the one bench bool the
    # parser rejects a value for; its absence is asserted in
    # test_llamacpp_bench_verbose_carries_no_default.
    assert "llamacpp_bench" not in BOOL_FLAG_VALUE_REJECTED
    for key, value in {
        "no_kv_offload": "0",
        "no_op_offload": "0",
        "flash_attn": "0",
        "mmap": "1",
        "embeddings": "0",
        "cpu_strict": "0",
    }.items():
        assert LLAMACPP_LLAMA_BENCH_FLAGS[key]["default"] == value, key


def test_llamacpp_bench_verbose_carries_no_default():
    # llama-bench's -v takes no value (bare flag), unlike the other bench
    # bools' <0|1> metavars: with a prefill default, click-to-add stored
    # `"-v": "off"` and the parser rejected the rendered `-v off`. The
    # engine-level guard cannot express this (the bench dict mixes
    # value-taking and bare bools), so the per-flag fact lives here.
    entry = LLAMACPP_LLAMA_BENCH_FLAGS["verbose"]
    assert entry["type"] == "bool"
    assert entry.get("default", "") in (None, "")
