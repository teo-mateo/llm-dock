"""Pure reasoning-level layer: grammar, lookup, per-engine request mapping."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import reasoning_levels as rl


# -- grammar --------------------------------------------------------------


def test_absent_declarations_are_valid_and_parse_to_nothing():
    for raw in (None, "", "   ", "\t\n"):
        valid, errors = rl.validate_levels(raw)
        assert valid and errors == []
        assert rl.parse_levels(raw) == []
    assert rl.parse_levels({}) == []


def test_single_off_level():
    assert rl.parse_levels("off") == [{"id": "off", "effort": "off"}]


def test_ladder_parses_in_declaration_order():
    assert rl.parse_levels("off,low,medium,xhigh") == [
        {"id": "off", "effort": "off"},
        {"id": "low", "effort": "low"},
        {"id": "medium", "effort": "medium"},
        {"id": "xhigh", "effort": "xhigh"},
    ]


def test_whitespace_around_entries_is_separator_not_content():
    assert rl.format_levels(rl.parse_levels(" off , low ,medium ")) == "off,low,medium"


def test_internal_whitespace_is_rejected_not_trimmed():
    valid, errors = rl.validate_levels("low, medium high")
    assert not valid
    assert "medium high" in errors[0]


@pytest.mark.parametrize("raw", ["Low", "OFF", "Off", "medium, HIGH"])
def test_case_is_never_silently_normalised(raw):
    # Tokens are case-sensitive to the template: lowering "Low" would send a
    # different instruction than the operator declared.
    valid, errors = rl.validate_levels(raw)
    assert not valid
    assert any("Low" in e or "OFF" in e or "Off" in e or "HIGH" in e for e in errors)


def test_duplicate_ids_rejected():
    valid, errors = rl.validate_levels("low,medium,low")
    assert not valid
    assert "duplicate" in errors[0]


def test_empty_entry_rejected():
    valid, errors = rl.validate_levels("low,,medium")
    assert not valid
    assert "empty entry" in errors[0]


def test_colon_bearing_value_is_rejected_naming_the_grammar():
    # A future budget syntax (level name plus a token count) must fail loudly
    # rather than truncate to the bare level name.
    valid, errors = rl.validate_levels("low:512")
    assert not valid
    assert "budget" in errors[0]
    assert "comma-separated" in errors[0]


def test_too_many_levels():
    raw = ",".join(f"lvl{i}" for i in range(9))
    valid, errors = rl.validate_levels(raw)
    assert not valid
    assert "too many" in errors[0]
    assert len(rl.parse_levels(raw)) == 0


def test_eight_levels_is_the_maximum():
    raw = ",".join(f"lvl{i}" for i in range(8))
    assert rl.validate_levels(raw)[0]
    assert len(rl.parse_levels(raw)) == 8


def test_too_long_declaration():
    raw = ",".join(f"level{i:02d}" for i in range(16))
    assert len(raw) == 127
    assert len(raw) > rl.MAX_RAW_CHARS
    valid, errors = rl.validate_levels(raw)
    assert not valid
    assert "too long" in errors[0]


def test_long_but_within_limits_is_accepted():
    # The level cap binds well before the char cap; both must be satisfiable.
    raw = ",".join(f"level{i}extra" for i in range(8))
    assert 60 < len(raw) < rl.MAX_RAW_CHARS
    assert rl.validate_levels(raw)[0]


def test_overlong_single_name():
    valid, errors = rl.validate_levels("a" * (rl.LEVEL_NAME_MAX + 1))
    assert not valid
    assert "invalid level name" in errors[0]


@pytest.mark.parametrize("raw", [123, ["low"], {"id": "low"}, True])
def test_non_string_declaration_rejected(raw):
    valid, errors = rl.validate_levels(raw)
    assert not valid
    assert "must be a string" in errors[0]


def test_parses_tolerantly_so_a_hand_edited_file_cannot_break_a_read():
    # The read path must survive a garbage value; validate owns rejection.
    assert rl.parse_levels("low, LOW") == []
    assert rl.parse_levels("low:512") == []


def test_off_is_an_ordinary_level_in_the_grammar():
    assert rl.validate_levels("low,off")[0]
    assert rl.format_levels(rl.parse_levels("low,off")) == "low,off"


# -- lookup ---------------------------------------------------------------


def test_find_level_accepts_raw_string_and_parsed_list():
    levels = rl.parse_levels("off,low,medium")
    assert rl.find_level("off,low,medium", "low") == {"id": "low", "effort": "low"}
    assert rl.find_level(levels, "off") == {"id": "off", "effort": "off"}


def test_find_level_misses_are_misses():
    levels = rl.parse_levels("off,low,medium")
    assert rl.find_level(levels, "xhigh") is None
    assert rl.find_level("off,low", "high") is None
    assert rl.find_level(None, "low") is None
    assert rl.find_level(levels, None) is None
    assert rl.find_level(levels, "") is None
    assert rl.find_level(levels, 5) is None
    assert rl.find_level(levels, "low ") is None


def test_format_levels_round_trips():
    for raw in ("off", "off,low,medium,xhigh", "off,minimal,max"):
        assert rl.format_levels(rl.parse_levels(raw)) == raw
    assert rl.format_levels([]) == ""
    assert rl.format_levels(None) == ""


# -- wire mapping ---------------------------------------------------------


def test_llamacpp_off_sends_effort_none_and_disables_thinking():
    assert rl.request_fields({"id": "off", "effort": "off"}, "llamacpp") == {
        "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False},
    }


def test_llamacpp_named_level_sends_effort_only():
    assert rl.request_fields({"id": "xhigh", "effort": "xhigh"}, "llamacpp") == {
        "reasoning_effort": "xhigh"
    }


def test_vllm_maps_off_to_none_and_names_to_themselves():
    assert rl.request_fields({"id": "off", "effort": "off"}, "vllm") == {
        "reasoning_effort": "none"
    }
    assert rl.request_fields({"id": "medium", "effort": "medium"}, "vllm") == {
        "reasoning_effort": "medium"
    }


@pytest.mark.parametrize(
    "engine",
    ["ik_llamacpp", "tabbyapi", "ds4", "", None, "unknown-engine"],
)
def test_unmapped_engines_send_nothing(engine):
    assert rl.request_fields({"id": "low", "effort": "low"}, engine) == {}


@pytest.mark.parametrize("level", [None, "", {}, {"id": ""}, {"id": None}, 0])
def test_no_level_never_produces_fields(level):
    # R6: no selection means no new key, on any engine.
    for engine in ("llamacpp", "vllm"):
        assert rl.request_fields(level, engine) == {}


def test_no_numeric_budget_field_is_ever_emitted():
    # No numeric budget field is ever generated, on any engine.
    for engine in ("llamacpp", "vllm", "tabbyapi"):
        for level_id in ("off", "low", "minimal", "xhigh", "max"):
            fields = rl.request_fields({"id": level_id}, engine)
            assert "thinking_budget_tokens" not in fields
            assert "thinking_token_budget" not in fields
            assert not any(isinstance(v, int) for v in fields.values())
