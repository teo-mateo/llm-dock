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
from chat.openrouter import DEFAULT_MODELS

MODELS_A = [{"id": "vendor/model-a", "label": "Model A"}]


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the store at a tmp file via the env override."""
    path = tmp_path / "chat_settings.json"
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path))
    return path


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
