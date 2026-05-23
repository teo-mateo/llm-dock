"""Tests for the /api/chat/mcp-registry admin route.

Focused on the redaction contract: header values configured in
mcp_servers.json must not appear in the public registry view.
"""

import importlib
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-mcp-admin")

TOKEN = "test-token-mcp-admin"
REGISTRY_PATH = "/api/chat/mcp-registry"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_MCP_SERVERS_FILE", str(tmp_path / "mcp_servers.json"))
    # Reload chat.* modules so a fresh Blueprint is created with this
    # test's config path. Order matters: mcp_admin_routes binds to
    # chat.routes at import time, so both must be re-imported each test
    # — otherwise the SECOND test reuses the first test's stale bp.
    for mod_name in [m for m in list(sys.modules) if m == "chat" or m.startswith("chat.")]:
        sys.modules.pop(mod_name, None)
    from chat.routes import chat_bp
    # Force the mcp_admin_routes side-effect import (it's behind chat.routes' tail import).
    import chat.mcp_admin_routes  # noqa: F401

    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client(), tmp_path / "mcp_servers.json"


def _write_servers(path, data):
    path.write_text(json.dumps(data))


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_registry_view_redacts_http_header_values(client):
    test_client, cfg_path = client
    secret = "Bearer super-secret-token-do-not-leak"
    _write_servers(
        cfg_path,
        {
            "ragflow": {
                "enabled": True,
                "name": "RagFlow",
                "description": "Query the KB",
                "transport": "http",
                "url": "http://localhost:9382/mcp",
                "headers": {"Authorization": secret, "X-Tenant": "acme"},
                "icon": "fa-cloud",
                "tool_hint": "Use it.",
            }
        },
    )

    r = test_client.get(REGISTRY_PATH, headers=_auth())
    assert r.status_code == 200
    body_text = r.get_data(as_text=True)

    # The header VALUE must never appear in the response, anywhere.
    assert secret not in body_text
    # The "headers" object itself is not in the public shape.
    assert '"headers":' not in body_text

    payload = r.get_json()
    rf = next(s for s in payload["servers"] if s["id"] == "ragflow")
    assert rf["transport"] == "http"
    assert rf["url"] == "http://localhost:9382/mcp"
    # Only the key names are exposed, and they're sorted for stable UI.
    assert rf["header_keys"] == ["Authorization", "X-Tenant"]


def test_registry_view_omits_command_for_http_entries(client):
    test_client, cfg_path = client
    _write_servers(
        cfg_path,
        {
            "ragflow": {
                "enabled": True,
                "name": "RagFlow",
                "description": "Query the KB",
                "transport": "http",
                "url": "http://localhost:9382/mcp",
                "icon": "fa-cloud",
                "tool_hint": "Use it.",
            }
        },
    )
    r = test_client.get(REGISTRY_PATH, headers=_auth())
    assert r.status_code == 200, r.get_data(as_text=True)
    payload = r.get_json()
    rf = next(s for s in payload["servers"] if s["id"] == "ragflow")
    # The HTTP-entry shape replaces command/args, not augments them.
    assert "command" not in rf
    assert "args" not in rf
    # command_exists stays True so the "no command" badge in the UI
    # doesn't fire spuriously for remote entries.
    assert rf["command_exists"] is True


def test_registry_view_preserves_stdio_command_shape(client):
    test_client, cfg_path = client
    _write_servers(
        cfg_path,
        {
            "ws": {
                "enabled": True,
                "name": "Web Search",
                "description": "Search",
                "command": "/abs/path/python",
                "args": ["/abs/path/main.py"],
                "icon": "fa-search",
                "tool_hint": "Use it.",
            }
        },
    )
    r = test_client.get(REGISTRY_PATH, headers=_auth())
    assert r.status_code == 200
    payload = r.get_json()
    ws = next(s for s in payload["servers"] if s["id"] == "ws")
    assert ws["transport"] == "stdio"
    assert ws["command"] == "/abs/path/python"
    assert ws["args"] == ["/abs/path/main.py"]
    assert "url" not in ws
    assert "header_keys" not in ws
