"""Validation + normalization tests for the MCP external-server registry."""

import importlib
import json
import os
import sys
import tempfile

import pytest

# Allow `import chat.mcp_config` when run via pytest from the dashboard dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mcp_config(tmp_path, monkeypatch):
    """Fresh mcp_config module with an isolated config file path.

    The module holds load state in module globals, so we reimport it per
    test to avoid leakage between cases.
    """
    cfg_path = tmp_path / "mcp_servers.json"
    monkeypatch.setenv("LLM_DOCK_MCP_SERVERS_FILE", str(cfg_path))
    if "chat.mcp_config" in sys.modules:
        del sys.modules["chat.mcp_config"]
    mod = importlib.import_module("chat.mcp_config")
    return mod, cfg_path


_BUILTIN_IDS = {"sympy-math", "schemdraw-circuits", "render-html"}


def _valid_stdio_entry(**overrides):
    base = {
        "enabled": True,
        "name": "Web Search",
        "description": "Search the web",
        "command": "/abs/path/python",
        "args": ["/abs/path/server.py"],
        "icon": "fa-search",
        "tool_hint": "Use it when fresh info is needed.",
    }
    base.update(overrides)
    return base


def _valid_http_entry(**overrides):
    base = {
        "enabled": True,
        "name": "Ragflow",
        "description": "Query the knowledge base",
        "transport": "http",
        "url": "http://localhost:9382/mcp",
        "headers": {},
        "icon": "fa-cloud",
        "tool_hint": "Use it to look up KB content.",
    }
    base.update(overrides)
    return base


class TestValidation:
    def test_stdio_entry_accepted(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry("ws", _valid_stdio_entry(), _BUILTIN_IDS)
        assert err is None

    def test_http_entry_accepted(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry("rf", _valid_http_entry(), _BUILTIN_IDS)
        assert err is None

    def test_http_entry_via_type_remote_alias(self, mcp_config):
        # Claude Code's shape uses `type: "remote"` instead of `transport`.
        # Accepting it as a synonym means users can paste their existing
        # configs in without re-keying.
        mod, _ = mcp_config
        entry = _valid_http_entry()
        del entry["transport"]
        entry["type"] = "remote"
        err = mod._validate_entry("rf", entry, _BUILTIN_IDS)
        assert err is None

    @pytest.mark.parametrize("missing", ["name", "description", "icon", "tool_hint"])
    def test_common_required_fields_enforced(self, mcp_config, missing):
        mod, _ = mcp_config
        entry = _valid_stdio_entry()
        del entry[missing]
        err = mod._validate_entry("ws", entry, _BUILTIN_IDS)
        assert err and missing in err

    def test_stdio_requires_command_and_args(self, mcp_config):
        mod, _ = mcp_config
        entry = _valid_stdio_entry()
        del entry["command"]
        err = mod._validate_entry("ws", entry, _BUILTIN_IDS)
        assert err and "command" in err

    def test_stdio_command_must_be_absolute(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry(
            "ws", _valid_stdio_entry(command="relative/python"), _BUILTIN_IDS
        )
        assert err and "absolute" in err

    def test_http_requires_url(self, mcp_config):
        mod, _ = mcp_config
        entry = _valid_http_entry()
        del entry["url"]
        err = mod._validate_entry("rf", entry, _BUILTIN_IDS)
        assert err and "url" in err

    @pytest.mark.parametrize("bad_url", ["ftp://example.com", "example.com", ""])
    def test_http_url_must_have_http_scheme(self, mcp_config, bad_url):
        mod, _ = mcp_config
        err = mod._validate_entry("rf", _valid_http_entry(url=bad_url), _BUILTIN_IDS)
        assert err is not None

    def test_http_headers_must_be_string_map(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry(
            "rf", _valid_http_entry(headers={"Authorization": 42}), _BUILTIN_IDS
        )
        assert err and "headers" in err

    def test_unknown_transport_rejected(self, mcp_config):
        mod, _ = mcp_config
        entry = _valid_stdio_entry(transport="websocket")
        err = mod._validate_entry("ws", entry, _BUILTIN_IDS)
        assert err and "transport" in err

    def test_id_with_double_underscore_rejected(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry("bad__id", _valid_stdio_entry(), _BUILTIN_IDS)
        assert err and "__" in err

    def test_id_colliding_with_builtin_rejected(self, mcp_config):
        mod, _ = mcp_config
        err = mod._validate_entry("sympy-math", _valid_stdio_entry(), _BUILTIN_IDS)
        assert err and "built-in" in err


class TestNormalization:
    def test_stdio_normalizes_to_command_list(self, mcp_config):
        mod, _ = mcp_config
        out = mod._normalize_external("ws", _valid_stdio_entry())
        assert out["transport"] == "stdio"
        assert out["command"] == ["/abs/path/python", "/abs/path/server.py"]
        assert out["external"] is True
        assert out["enabled"] is True
        assert "url" not in out

    def test_http_normalizes_to_url_and_headers(self, mcp_config):
        mod, _ = mcp_config
        out = mod._normalize_external(
            "rf", _valid_http_entry(headers={"Authorization": "Bearer x"})
        )
        assert out["transport"] == "http"
        assert out["url"] == "http://localhost:9382/mcp"
        assert out["headers"] == {"Authorization": "Bearer x"}
        assert "command" not in out

    def test_type_remote_normalizes_to_http_transport(self, mcp_config):
        mod, _ = mcp_config
        entry = _valid_http_entry()
        del entry["transport"]
        entry["type"] = "remote"
        out = mod._normalize_external("rf", entry)
        assert out["transport"] == "http"
        assert out["url"] == "http://localhost:9382/mcp"


class TestChatAvailability:
    def test_http_entry_available_when_enabled_with_url(self, mcp_config):
        mod, _ = mcp_config
        cfg = mod._normalize_external("rf", _valid_http_entry())
        assert mod._chat_available(cfg) is True

    def test_http_entry_not_available_when_disabled(self, mcp_config):
        mod, _ = mcp_config
        cfg = mod._normalize_external("rf", _valid_http_entry(enabled=False))
        assert mod._chat_available(cfg) is False

    def test_stdio_entry_not_available_when_command_missing(
        self, mcp_config, tmp_path
    ):
        mod, _ = mcp_config
        # Use a definitely-not-on-disk command path. Pass validation first
        # by skipping straight to _normalize_external — validation
        # requires absolute path, which we supply.
        cfg = mod._normalize_external(
            "ws",
            _valid_stdio_entry(command=str(tmp_path / "does-not-exist")),
        )
        assert mod._chat_available(cfg) is False


class TestFileLoading:
    def test_http_entry_loaded_from_external_json(self, mcp_config):
        mod, cfg_path = mcp_config
        cfg_path.write_text(json.dumps({"rf": _valid_http_entry()}))
        state = mod.reload()
        assert "rf" in state["merged"]
        assert state["merged"]["rf"]["transport"] == "http"
        assert state["external_errors"] == []
        assert state["load_error"] is None

    def test_invalid_http_entry_reported_with_error(self, mcp_config):
        mod, cfg_path = mcp_config
        bad = _valid_http_entry()
        del bad["url"]
        cfg_path.write_text(json.dumps({"rf": bad}))
        state = mod.reload()
        assert any(e["entry_id"] == "rf" for e in state["external_errors"])
        assert "rf" not in {
            sid for sid, c in state["merged"].items() if c.get("external")
        }
