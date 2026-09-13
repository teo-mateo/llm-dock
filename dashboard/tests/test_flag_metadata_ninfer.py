import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import (
    NINFER_FLAGS,
    get_bool_cli_flags,
    get_flag_metadata,
    validate_service_config,
)


def _cfg(**overrides):
    cfg = {
        "port": 3340,
        "model_path": "/hf-cache/hub/models--neroued--Qwen3.8-27B-nvfp4-NInfer"
        "/snapshots/abc123/qwen3_8_27b_nvfp4.ninfer",
        "alias": "qwen38-nvfp4",
        "api_key": "llmd-ninfer",
        "params": {},
    }
    cfg.update(overrides)
    return cfg


def test_flag_metadata_is_registered():
    assert get_flag_metadata("ninfer") is NINFER_FLAGS
    assert NINFER_FLAGS


def test_every_flag_key_mirrors_its_cli_spelling():
    """The metadata is the only place a flag's spelling lives; a drift here ships a
    flag ninfer-serve does not know, and the container dies at startup instead of
    failing at config time."""
    for key, meta in NINFER_FLAGS.items():
        assert meta["cli"] == "--" + key.replace("_", "-")
        assert meta["type"] in ("bool", "int", "float", "string", "path")
        assert meta["category"]
        assert meta["description"]


def test_bool_flags_are_rendered_bare():
    bools = get_bool_cli_flags("ninfer")
    assert "--vision" in bools
    assert "--no-cuda-graph" in bools
    assert "--greedy" in bools
    assert "--kv-dtype" not in bools  # string-typed, takes a value


def test_bare_bool_param_is_accepted():
    """ninfer-serve wants a bare --vision; unlike tabbyapi, an empty value is correct."""
    valid, errors = validate_service_config("ninfer", _cfg(params={"--vision": ""}))
    assert valid, errors


def test_missing_model_path_is_rejected():
    cfg = _cfg()
    del cfg["model_path"]
    valid, errors = validate_service_config("ninfer", cfg)
    assert not valid
    assert any("model_path" in e for e in errors)
