"""Pure layer for sampling params: grammar, ranges, and the per-engine mapping.

The mapping rows are the measured ones from docs/plans/chat-sampling-params.md,
and this file is what stops them from drifting: the llama.cpp spelling in
particular is pinned here because vLLM answers 200 and drops the llama.cpp name,
and llama.cpp answers 200 and drops the vLLM one — a wrong name is invisible.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sampling_params as sp


# -- what the write path accepts -----------------------------------------


@pytest.mark.parametrize("value", [None, {}, {"temperature": 0.7}, {"stop": ["a", "b"]}])
def test_absent_and_empty_are_valid(value):
    """Clearing is a legal write, not an error — it is how a conversation opts out."""
    valid, errors = sp.validate(value)
    assert valid, errors


@pytest.mark.parametrize("value,fragment", [
    ("0.7", "must be an object or null"),
    ([1], "must be an object or null"),
    ({"temp": 0.5}, "unknown field"),
    ({"temperature": "hot"}, "must be a number"),
    ({"temperature": True}, "must be a number"),
    ({"temperature": 2.1}, "must be <= 2"),
    ({"temperature": -0.1}, "must be >= 0"),
    ({"top_p": 0}, "must be > 0"),
    ({"top_p": 1.5}, "must be <= 1"),
    ({"top_k": 2.5}, "must be an integer"),
    ({"max_tokens": 0}, "must be >= 1"),
    ({"min_p": 1.5}, "must be <= 1"),
    ({"repetition_penalty": 0}, "must be > 0"),
    ({"presence_penalty": 2.5}, "must be <= 2"),
    ({"frequency_penalty": -2.5}, "must be >= -2"),
    ({"seed": -1}, "must be >= 0"),
    ({"stop": "hello"}, "must be a non-empty list of strings"),
    ({"stop": []}, "must be a non-empty list of strings"),
    ({"stop": ["a"] * 5}, "accepts at most 4 entries"),
    ({"stop": ["" ]}, "non-empty strings"),
    ({"stop": ["x" * 200]}, "at most 128 chars"),
    ({"temperature": float("nan")}, "must be finite"),
])
def test_rejects_with_a_reason(value, fragment):
    valid, errors = sp.validate(value)
    assert not valid
    assert any(fragment in e for e in errors), errors


def test_every_violation_is_reported_not_just_the_first():
    """A client fixing one field must not meet a fresh error on the next save.

    Counted, not `any(...)`: an earlier feature shipped a duplicated block behind
    an `any(...)` assertion that could not see it.
    """
    valid, errors = sp.validate({"temperature": 9, "top_p": 0, "bogus": 1})
    assert not valid
    assert len(errors) == 3


def test_one_violation_produces_exactly_one_error():
    assert len(sp.validate({"temperature": 9})[1]) == 1


# -- storage shape --------------------------------------------------------


def test_normalize_orders_by_declaration_and_casts_ints():
    assert sp.normalize({"seed": 7.0, "temperature": 0.4}) == {"temperature": 0.4, "seed": 7}


def test_empty_and_invalid_normalise_to_none():
    assert sp.normalize({}) is None
    assert sp.normalize(None) is None
    assert sp.normalize({"temperature": 9}) is None


def test_storage_round_trip():
    blob = sp.to_storage({"top_k": 40, "stop": ["END"]})
    assert blob.startswith("{") and '"' in blob
    assert sp.from_storage(blob) == {"top_k": 40, "stop": ["END"]}


def test_to_storage_clears_on_empty():
    """NULL is the column's only empty state, so {} and null write the same thing."""
    assert sp.to_storage(None) is None
    assert sp.to_storage({}) is None


def test_from_storage_tolerates_junk():
    assert sp.from_storage("not json") is None
    assert sp.from_storage("") is None
    assert sp.from_storage(None) is None
    assert sp.from_storage("[1,2]") is None


def test_per_field_bounds_alone_keep_the_column_bounded():
    """No size cap on the blob: the field bounds are what bound it.

    A second cap would be unreachable and read as a guard - this asserts the
    worst legal payload fits comfortably, so adding an unbounded field later is
    what has to revisit the column.
    """
    worst = {name: ("x" * sp.MAX_STOP_CHARS) if name == "stop" else spec.maximum
             for name, spec in sp.FIELDS.items()}
    worst["stop"] = ["x" * sp.MAX_STOP_CHARS] * sp.MAX_STOP_ENTRIES
    worst["seed"] = sp.MAX_TOKEN_VALUE
    assert sp.validate(worst)[0], sp.validate(worst)[1]
    assert len(sp.to_storage(worst)) < 2048


# -- the mapping ----------------------------------------------------------


def test_engine_without_a_mapping_gets_nothing():
    """An unmapped engine sends no sampling field at all.

    Deliberate, and copied from the reasoning feature: an unverified field changes
    behaviour invisibly instead of failing. ik_llamacpp, tabbyapi, ds4, ninfer and
    openrouter are unmapped today.
    """
    params = {"temperature": 0.4, "top_k": 20, "seed": 1}
    for engine in ("ik_llamacpp", "tabbyapi", "ds4", "ninfer", "openrouter", "", None):
        assert sp.request_fields(params, engine) == {}
        assert sp.supported_fields(engine) == []


def test_vllm_uses_the_openai_spellings():
    assert sp.request_fields({"temperature": 0.4, "top_p": 0.9, "top_k": 40, "min_p": 0.1,
                              "max_tokens": 256, "repetition_penalty": 1.1,
                              "presence_penalty": 0.2, "frequency_penalty": 0.2,
                              "seed": 7, "stop": ["END"]}, "vllm") == {
        "temperature": 0.4, "top_p": 0.9, "top_k": 40, "min_p": 0.1, "max_tokens": 256,
        "repetition_penalty": 1.1, "presence_penalty": 0.2, "frequency_penalty": 0.2,
        "seed": 7, "stop": ["END"],
    }


def test_llamacpp_renames_repetition_penalty_and_keeps_the_rest():
    """The one rename in the table, and the reason the table exists.

    Measured: `repetition_penalty` on llama.cpp answers 200 and ignores it; the
    sampler reads `repeat_penalty`. Sending the OpenAI name would silently do
    nothing.
    """
    out = sp.request_fields({"repetition_penalty": 1.2, "top_k": 5}, "llamacpp")
    assert out == {"top_k": 5, "repeat_penalty": 1.2}
    assert "repetition_penalty" not in out


def test_request_fields_revalidates_rather_than_trusting_its_argument():
    """A caller that skipped validation cannot put a rejected value on the wire."""
    assert sp.request_fields({"temperature": 9}, "vllm") == {}
    assert sp.request_fields({"temperature": 1.0, "bogus": 2}, "vllm") == {}


def test_partial_params_send_only_what_was_set():
    assert sp.request_fields({"temperature": 0.2}, "vllm") == {"temperature": 0.2}
    assert sp.request_fields(None, "vllm") == {}


def test_drop_unsupported_reports_the_field_name_not_the_wire_key():
    """The run_started note names `temperature`, not the engine's spelling of it."""
    applicable, dropped = sp.drop_unsupported({"temperature": 0.3}, "ds4")
    assert applicable is None
    assert dropped == ["temperature"]


def test_drop_unsupported_on_an_unmapped_engine_lists_every_stored_field():
    applicable, dropped = sp.drop_unsupported({"seed": 1, "top_p": 0.5}, "tabbyapi")
    assert applicable is None
    assert dropped == ["top_p", "seed"]


def test_drop_unsupported_keeps_applicable_fields():
    applicable, dropped = sp.drop_unsupported({"temperature": 0.3, "top_k": 8}, "vllm")
    assert applicable == {"temperature": 0.3, "top_k": 8}
    assert dropped == []


def test_capabilities_only_narrow():
    """A per-model capability list can remove a knob, never invent one."""
    full = [f.name for f in sp.supported_fields("vllm")]
    assert len(full) == len(sp.FIELDS)
    assert [f.name for f in sp.supported_fields("vllm", ["temperature", "seed"])] == \
        ["temperature", "seed"]
    assert [f.name for f in sp.supported_fields("vllm", ["temperature", "min_p", "bogus"])] == \
        ["temperature", "min_p"]
    assert sp.supported_fields("ds4", ["temperature"]) == []


def test_descriptor_carries_the_bounds_so_no_client_hardcodes_them():
    d = {f["name"]: f for f in sp.fields_descriptor(sp.supported_fields("vllm"))}
    assert d["temperature"]["min"] == 0.0 and d["temperature"]["max"] == 2.0
    assert d["max_tokens"]["kind"] == "integer"
    assert d["stop"]["kind"] == "strings"


def test_bounds_are_the_intersection_of_the_engines_that_take_the_field():
    """Every offered value must be accepted by every engine offering it.

    vLLM rejects temperature > 2 and llama.cpp clamps it; vLLM rejects top_p == 0
    and llama.cpp accepts it — the narrower bound wins, in both directions.
    """
    temp = sp.FIELDS["temperature"]
    assert (temp.minimum, temp.maximum) == (0.0, 2.0)
    top_p = sp.FIELDS["top_p"]
    assert (top_p.minimum, top_p.maximum, top_p.exclusive_min) == (0.0, 1.0, True)
    penalties = sp.FIELDS["presence_penalty"]
    assert (penalties.minimum, penalties.maximum) == (-2.0, 2.0)
    assert sp.FIELDS["seed"].maximum == sp.MAX_TOKEN_VALUE
