import os

from pi_remote import settings


def test_explicit_values_win():
    assert settings.resolve_socket_path("~/.cache/custom.sock") == os.path.expanduser("~/.cache/custom.sock")
    assert settings.resolve_db_path("~/custom.db") == os.path.expanduser("~/custom.db")


def test_env_wins_over_defaults(monkeypatch, tmp_path):
    socket_path = str(tmp_path / "env.sock")
    db_path = str(tmp_path / "env.db")
    monkeypatch.setenv("LLM_DOCK_PI_REMOTE_SOCKET", socket_path)
    monkeypatch.setenv("LLM_DOCK_PI_REMOTE_DB", db_path)
    assert settings.resolve_socket_path() == socket_path
    assert settings.resolve_db_path() == db_path


def test_defaults_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("LLM_DOCK_PI_REMOTE_SOCKET", raising=False)
    monkeypatch.delenv("LLM_DOCK_PI_REMOTE_DB", raising=False)
    assert settings.resolve_socket_path() == settings.DEFAULT_SOCKET_PATH
    assert settings.resolve_db_path() == settings.DEFAULT_DB_PATH
