import os
import stat
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tabby_keys


@pytest.fixture(autouse=True)
def keys_dir(tmp_path, monkeypatch):
    """Point the keys directory at a temp dir so tests never touch the repo."""
    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    return tmp_path / "keys"


def test_ensure_creates_file_with_key():
    path = tabby_keys.ensure("exl3-demo", "llmd-secret")
    assert path.is_file()
    body = path.read_text()
    assert "api_key: llmd-secret" in body
    assert "admin_key: llmd-secret" in body


def test_ensure_sets_owner_only_mode():
    path = tabby_keys.ensure("exl3-demo", "llmd-secret")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_ensure_is_idempotent():
    first = tabby_keys.ensure("exl3-demo", "llmd-secret")
    content = first.read_text()
    second = tabby_keys.ensure("exl3-demo", "llmd-secret")
    assert second == first
    assert second.read_text() == content


def test_ensure_rewrites_on_key_change():
    path = tabby_keys.ensure("exl3-demo", "llmd-old")
    tabby_keys.ensure("exl3-demo", "llmd-new")
    assert "llmd-new" in path.read_text()
    assert "llmd-old" not in path.read_text()


def test_remove_deletes_file():
    tabby_keys.ensure("exl3-demo", "llmd-secret")
    removed = tabby_keys.remove("exl3-demo")
    assert removed is not None
    assert not removed.exists()


def test_remove_missing_returns_none():
    assert tabby_keys.remove("exl3-nope") is None
