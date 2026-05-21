"""Tests for chat.settings_store — the persistent singleton settings file.

The store currently holds the editable default ``main_system_prompt``. It
falls back to the built-in baked into ``constants.py`` on every read path
where the file is missing, unreadable, malformed, or simply has no value
for the key — so callers never have to handle a None/empty case.
"""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import settings_store
from chat.constants import DEFAULT_MAIN_SYSTEM_PROMPT


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the store at a tmp file via the env override."""
    path = tmp_path / "chat_settings.json"
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path))
    return path


def test_missing_file_returns_builtin(settings_file):
    assert not settings_file.exists()
    assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert settings_store.is_main_system_prompt_customized() is False


def test_set_and_get_roundtrip(settings_file):
    settings_store.set_main_system_prompt("custom prompt body")
    assert settings_store.get_main_system_prompt() == "custom prompt body"
    assert settings_store.is_main_system_prompt_customized() is True
    # And the file actually exists and is parseable.
    assert settings_file.exists()
    with open(settings_file) as f:
        data = json.load(f)
    assert data == {"main_system_prompt": "custom prompt body"}


def test_set_rejects_non_string(settings_file):
    with pytest.raises(TypeError):
        settings_store.set_main_system_prompt(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        settings_store.set_main_system_prompt(None)  # type: ignore[arg-type]


def test_set_rejects_empty_and_whitespace(settings_file):
    with pytest.raises(ValueError):
        settings_store.set_main_system_prompt("")
    with pytest.raises(ValueError):
        settings_store.set_main_system_prompt("   \n\t  ")


def test_reset_removes_file_when_only_field(settings_file):
    settings_store.set_main_system_prompt("custom")
    assert settings_file.exists()
    settings_store.reset_main_system_prompt()
    assert not settings_file.exists()
    assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert settings_store.is_main_system_prompt_customized() is False


def test_reset_keeps_other_keys(settings_file):
    # Manually plant an unrelated key alongside the override.
    settings_file.write_text(
        json.dumps({"main_system_prompt": "custom", "future_setting": 42})
    )
    settings_store.reset_main_system_prompt()
    assert settings_file.exists()
    with open(settings_file) as f:
        data = json.load(f)
    assert data == {"future_setting": 42}


def test_reset_when_nothing_stored_is_noop(settings_file):
    settings_store.reset_main_system_prompt()
    settings_store.reset_main_system_prompt()  # idempotent
    assert not settings_file.exists()


def test_malformed_json_falls_back_to_builtin(settings_file, caplog):
    settings_file.write_text("{not json")
    with caplog.at_level("WARNING", logger="chat.settings_store"):
        assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert any("cannot read" in r.message for r in caplog.records)


def test_non_object_top_level_falls_back(settings_file, caplog):
    settings_file.write_text(json.dumps(["not", "an", "object"]))
    with caplog.at_level("WARNING", logger="chat.settings_store"):
        assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert settings_store.is_main_system_prompt_customized() is False


def test_empty_string_value_treated_as_unset(settings_file):
    """An empty string stored on disk should not count as a customization.

    The PUT endpoint rejects empty content, but a hand-edited file could
    contain ``""`` — treat that the same as a missing key so we never
    serve an empty prompt to the model.
    """
    settings_file.write_text(json.dumps({"main_system_prompt": ""}))
    assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert settings_store.is_main_system_prompt_customized() is False


def test_value_matching_builtin_is_not_customized(settings_file):
    """Storing the exact built-in text should report customized=False.

    Makes the Reset button's "modified from built-in" indicator true to
    its name even if a user pastes the built-in back in by accident.
    """
    settings_store.set_main_system_prompt(DEFAULT_MAIN_SYSTEM_PROMPT)
    assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    assert settings_store.is_main_system_prompt_customized() is False


def test_atomic_write_leaves_no_tempfile(settings_file):
    """The tempfile + os.replace path must not litter .tmp files."""
    settings_store.set_main_system_prompt("custom")
    leftovers = [
        p for p in os.listdir(settings_file.parent)
        if p.startswith(".chat_settings.") and p.endswith(".tmp")
    ]
    assert leftovers == [], f"tempfiles left behind: {leftovers}"


def test_concurrent_writes_serialize(settings_file):
    """Concurrent setters must not lose updates or corrupt the file.

    The actual guarantee the lock gives is "one of the writes wins, and
    the final file is internally consistent JSON". We can verify both.
    """
    errors = []

    def writer(value):
        try:
            settings_store.set_main_system_prompt(value)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(f"value-{i}",)) for i in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], errors
    # File parses cleanly and the stored value is one of the ones we set.
    with open(settings_file) as f:
        data = json.load(f)
    assert data["main_system_prompt"] in {f"value-{i}" for i in range(20)}


def test_env_override_isolates_state(tmp_path, monkeypatch):
    """LLM_DOCK_CHAT_SETTINGS_FILE redirects all reads/writes."""
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"

    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path_a))
    settings_store.set_main_system_prompt("from a")
    assert settings_store.get_main_system_prompt() == "from a"

    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path_b))
    # Fresh file → built-in default
    assert settings_store.get_main_system_prompt() == DEFAULT_MAIN_SYSTEM_PROMPT
    settings_store.set_main_system_prompt("from b")

    # Switch back — A still holds its own value.
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(path_a))
    assert settings_store.get_main_system_prompt() == "from a"
