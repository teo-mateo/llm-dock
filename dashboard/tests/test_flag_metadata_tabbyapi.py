import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import get_bool_cli_flags, validate_service_config


def test_get_bool_cli_flags_returns_dash_form_flags():
    flags = get_bool_cli_flags("tabbyapi")
    assert "--vision" in flags
    assert "--output-chunking" in flags
    assert "--max-seq-len" not in flags  # int-typed, not bool


def test_empty_bool_value_is_rejected():
    cfg = {
        "port": 3328,
        "model_path": "/exl3/foo",
        "alias": "a",
        "api_key": "k",
        "params": {"--vision": ""},
    }
    valid, errors = validate_service_config("tabbyapi", cfg)
    assert not valid
    assert any("--vision" in e for e in errors)


def test_bool_value_present_is_accepted():
    cfg = {
        "port": 3328,
        "model_path": "/exl3/foo",
        "alias": "a",
        "api_key": "k",
        "params": {"--vision": "True"},
    }
    valid, errors = validate_service_config("tabbyapi", cfg)
    assert valid
    assert errors == []
