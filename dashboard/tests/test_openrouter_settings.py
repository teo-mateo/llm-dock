"""Tests for the curated OpenRouter model list in chat.settings_store.

Mirrors test_settings_store.py: the store falls back to the built-in
``DEFAULT_MODELS`` from ``chat.openrouter`` whenever the file is missing,
unreadable, malformed, or holds an invalid value for the key. Unlike the
system prompt, an *empty list* is a valid stored value — it hides every
OpenRouter model from the picker without unsetting the API key.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import settings_store
from chat.openrouter import DEFAULT_MODELS, ladder_from_reasoning

MODELS_A = [{"id": "vendor/model-a", "label": "Model A"}]


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the store at a tmp file via the env override."""
    path = tmp_path / "chat_settings.json"
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path))
    return path


# -- Ladder derivation: upstream capability metadata to declaration string --


def test_ladder_puts_off_first_and_levels_least_to_most():
    # Measured upstream: gpt-5.5 lists efforts descending, allows switching off.
    meta = {"supported_efforts": ["xhigh", "high", "medium", "low", "none"],
            "default_effort": "medium", "mandatory": False}
    assert ladder_from_reasoning(meta) == "off,low,medium,high,xhigh"


def test_ladder_omits_off_when_upstream_lists_no_way_to_switch_off():
    meta = {"supported_efforts": ["max", "xhigh", "high", "medium", "low"], "mandatory": False}
    assert ladder_from_reasoning(meta) == "low,medium,high,xhigh,max"


def test_ladder_omits_off_when_reasoning_is_mandatory():
    # Sending effort=none to a mandatory model is a 400, so offering `off` would be
    # offering a failure -- even on a ladder that could otherwise be switched off.
    meta = {"supported_efforts": ["high", "medium", "low", "minimal", "none"], "mandatory": True}
    assert ladder_from_reasoning(meta) == "minimal,low,medium,high"


def test_ladder_is_empty_when_the_model_exposes_no_effort_selection():
    assert ladder_from_reasoning({"mandatory": False}) == ""
    assert ladder_from_reasoning({"supported_efforts": []}) == ""
    assert ladder_from_reasoning(None) == ""
    assert ladder_from_reasoning("nonsense") == ""


def test_unknown_effort_sorts_after_the_known_ones():
    # Ordering comes from a rank, not from reversing upstream, so a token added
    # tomorrow lands at the end rather than in the middle of the ladder.
    meta = {"supported_efforts": ["turbo", "low", "high"], "mandatory": False}
    assert ladder_from_reasoning(meta) == "low,high,turbo"


def test_effort_outside_the_declaration_grammar_costs_one_level_not_the_save():
    meta = {"supported_efforts": ["high", "Medium", "low"], "mandatory": False}
    assert ladder_from_reasoning(meta) == "low,high"


def test_ladder_is_capped_at_the_grammar_limit():
    meta = {"supported_efforts": [f"level{n}" for n in range(12)], "mandatory": False}
    assert len(ladder_from_reasoning(meta).split(",")) == 8


# -- Storage: a derived field a client cannot author --


def test_ladder_roundtrips(settings_file):
    settings_store.set_openrouter_models(MODELS_A, {"vendor/model-a": "off,low,high"})
    assert settings_store.get_openrouter_models()[0]["reasoning_levels"] == "off,low,high"


def test_a_model_without_a_ladder_carries_no_key(settings_file):
    # Absent is the representation of "no ladder", so the stored shape for an
    # unladdered model is identical to what it was before ladders existed.
    settings_store.set_openrouter_models(MODELS_A)
    assert "reasoning_levels" not in settings_store.get_openrouter_models()[0]


def test_body_supplied_ladder_is_ignored(settings_file):
    # The field is server-owned: the picker round-trips {id, label} alone, so a ladder in
    # a request body would be a ladder a client invented.
    settings_store.set_openrouter_models([{"id": "vendor/model-a", "label": "A",
                                          "reasoning_levels": "low,ultra"}])
    assert "reasoning_levels" not in settings_store.get_openrouter_models()[0]


def test_ladder_survives_a_save_that_does_not_mention_it(settings_file):
    # What lets a picker that knows nothing about ladders reorder the list without
    # wiping them: the merge is by id, over whatever is already stored.
    settings_store.set_openrouter_models(MODELS_A, {"vendor/model-a": "off,low"})
    settings_store.set_openrouter_models([{"id": "vendor/model-a", "label": "Renamed"}])
    stored = settings_store.get_openrouter_models()[0]
    assert stored["label"] == "Renamed" and stored["reasoning_levels"] == "off,low"


def test_refresh_with_an_empty_ladder_clears_it(settings_file):
    # A refresh that finds the model lost its efforts must record "no ladder", not
    # silently keep a stale one.
    settings_store.set_openrouter_models(MODELS_A, {"vendor/model-a": "off,low"})
    settings_store.set_openrouter_models(MODELS_A, {"vendor/model-a": ""})
    assert "reasoning_levels" not in settings_store.get_openrouter_models()[0]


def test_unreadable_stored_ladder_degrades_to_absent(settings_file):
    # Rejecting the whole list here would silently revert the user's curated selection,
    # so a bad field costs that model its control and nothing else.
    settings_file.write_text(json.dumps({"openrouter_models": [
        {"id": "vendor/model-a", "label": "A", "reasoning_levels": "low,LOW"}
    ]}))
    stored = settings_store.get_openrouter_models()
    assert stored[0]["id"] == "vendor/model-a"
    assert "reasoning_levels" not in stored[0]


def test_a_ladder_alone_does_not_count_as_customized(settings_file):
    # The ladder is derived, not chosen, so it cannot make the list read as hand-picked.
    settings_store.set_openrouter_models(
        [{"id": m["id"], "label": m["label"]} for m in DEFAULT_MODELS],
        {DEFAULT_MODELS[0]["id"]: "off,low"},
    )
    assert settings_store.is_openrouter_models_customized() is False


def test_missing_file_returns_builtin(settings_file):
    assert not settings_file.exists()
    assert settings_store.get_openrouter_models() == DEFAULT_MODELS
    assert settings_store.is_openrouter_models_customized() is False


def test_builtin_result_is_a_copy(settings_file):
    """Mutating the returned default list must not corrupt DEFAULT_MODELS."""
    models = settings_store.get_openrouter_models()
    models[0]["id"] = "mutated/mutated"
    assert settings_store.get_openrouter_models() == DEFAULT_MODELS


def test_set_and_get_roundtrip(settings_file):
    settings_store.set_openrouter_models(MODELS_A)
    assert settings_store.get_openrouter_models() == MODELS_A
    assert settings_store.is_openrouter_models_customized() is True
    with open(settings_file) as f:
        data = json.load(f)
    assert data == {"openrouter_models": MODELS_A}


def test_label_defaults_to_id(settings_file):
    settings_store.set_openrouter_models([{"id": "vendor/no-label"}])
    assert settings_store.get_openrouter_models() == [
        {"id": "vendor/no-label", "label": "vendor/no-label"}
    ]


def test_empty_list_is_honored(settings_file):
    """An empty list is a deliberate 'hide all', not 'unset'."""
    settings_store.set_openrouter_models([])
    assert settings_store.get_openrouter_models() == []
    assert settings_store.is_openrouter_models_customized() is True


def test_set_rejects_non_list(settings_file):
    with pytest.raises(TypeError):
        settings_store.set_openrouter_models("not a list")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        settings_store.set_openrouter_models(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "models",
    [
        ["bare string"],
        [{"label": "no id"}],
        [{"id": ""}],
        [{"id": "   "}],
        [{"id": 42}],
        [{"id": "a/b", "label": 42}],
        [{"id": "a/b"}, {"id": "a/b"}],  # duplicate ids
    ],
)
def test_set_rejects_malformed_entries(settings_file, models):
    with pytest.raises(ValueError):
        settings_store.set_openrouter_models(models)
    # Nothing was persisted.
    assert settings_store.is_openrouter_models_customized() is False


def test_reset_removes_file_when_only_field(settings_file):
    settings_store.set_openrouter_models(MODELS_A)
    assert settings_file.exists()
    settings_store.reset_openrouter_models()
    assert not settings_file.exists()
    assert settings_store.get_openrouter_models() == DEFAULT_MODELS
    assert settings_store.is_openrouter_models_customized() is False


def test_reset_keeps_other_keys(settings_file):
    settings_file.write_text(
        json.dumps({"openrouter_models": MODELS_A, "main_system_prompt": "custom"})
    )
    settings_store.reset_openrouter_models()
    with open(settings_file) as f:
        data = json.load(f)
    assert data == {"main_system_prompt": "custom"}


def test_reset_when_nothing_stored_is_noop(settings_file):
    settings_store.reset_openrouter_models()
    settings_store.reset_openrouter_models()  # idempotent
    assert not settings_file.exists()


def test_invalid_stored_value_falls_back_to_builtin(settings_file):
    """A hand-edited file with a malformed list must not break reads."""
    settings_file.write_text(json.dumps({"openrouter_models": [{"label": "no id"}]}))
    assert settings_store.get_openrouter_models() == DEFAULT_MODELS
    assert settings_store.is_openrouter_models_customized() is False


def test_value_matching_builtin_is_not_customized(settings_file):
    settings_store.set_openrouter_models(DEFAULT_MODELS)
    assert settings_store.is_openrouter_models_customized() is False


def test_coexists_with_main_system_prompt(settings_file):
    """Both settings share one file without clobbering each other."""
    settings_store.set_main_system_prompt("custom prompt")
    settings_store.set_openrouter_models(MODELS_A)
    assert settings_store.get_main_system_prompt() == "custom prompt"
    assert settings_store.get_openrouter_models() == MODELS_A
