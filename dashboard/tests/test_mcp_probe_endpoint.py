"""`GET /api/chat/mcp-servers` with and without `?probe=url-fetch` (issue 255).

The no-param response shape is pinned because the web dashboard's tool toggles
read it and must not see a new key.
"""

import importlib
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-url-probe")

TOKEN = "test-token-url-probe"
PATH = "/api/chat/mcp-servers"

_NO_MANAGER = object()

_SERVERS = {
    "webfetch": {
        "enabled": True,
        "name": "WebFetch",
        "description": "Fetch a web page as readable text",
        "icon": "fa-plug",
        "tool_hint": "Use it when the user shares a link.",
        "command": "/bin/true",
        "args": [],
    },
    "websearch": {
        "enabled": True,
        "name": "Web Search",
        "description": "Search the web for a query",
        "icon": "fa-plug",
        "tool_hint": "Use it when the user shares a link.",
        "command": "/bin/true",
        "args": [],
    },
    "ragflow": {
        "enabled": True,
        "name": "RagFlow",
        "description": "Query the local knowledge base",
        "icon": "fa-plug",
        "tool_hint": "Use it when the user shares a link.",
        "command": "/bin/true",
        "args": [],
    },
    "brokenfetch": {
        "enabled": True,
        "name": "Broken Fetch",
        "description": "Fetch pages over HTTP",
        "icon": "fa-plug",
        "tool_hint": "Use it when the user shares a link.",
        "command": "/bin/true",
        "args": [],
    },
}


def _url_tool(server_id: str, name: str, description: str = "Fetch readable text") -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"{server_id}__{name}",
            "description": description,
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
    }


def _query_tool(server_id: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"{server_id}__search",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }


class _FakeManager:
    """Stands in for MCPClientManager.discover_bounded."""

    def __init__(self, tools: dict, raises: tuple = ()):
        self._tools = tools
        self._raises = raises
        self.calls = []

    def discover_bounded(self, server_id: str, timeout: float) -> list:
        self.calls.append((server_id, timeout))
        if server_id in self._raises:
            raise RuntimeError("server did not answer")
        return self._tools.get(server_id, [])


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_MCP_SERVERS_FILE", str(tmp_path / "mcp_servers.json"))
    (tmp_path / "mcp_servers.json").write_text(json.dumps(_SERVERS))

    def build(manager=_NO_MANAGER):
        for mod_name in [m for m in list(sys.modules) if m == "chat" or m.startswith("chat.")]:
            sys.modules.pop(mod_name, None)
        from chat.routes import chat_bp

        app = Flask(__name__)
        app.config["DASHBOARD_TOKEN"] = TOKEN
        if manager is not _NO_MANAGER:
            app.config["MCP_MANAGER"] = manager
        app.register_blueprint(chat_bp)
        app.testing = True
        return app.test_client()

    return build


def _get(client, query=""):
    return client.get(PATH + query, headers={"Authorization": f"Bearer {TOKEN}"})


def test_request_without_a_token_is_rejected(make_client):
    client = make_client(_FakeManager({}))
    assert client.get(PATH).status_code == 401


def test_without_the_probe_param_the_payload_keeps_its_shape(make_client):
    client = make_client(_FakeManager({}))
    body = _get(client).get_json()
    assert set(body) == {"servers"}
    ids = {s["id"] for s in body["servers"]}
    assert ids >= set(_SERVERS)
    assert ids >= {"sympy-math"}, "built-ins are always offered"
    assert set(body["servers"][0]) == {"id", "name", "description", "icon"}


def test_an_unrecognised_probe_value_is_ignored(make_client):
    client = make_client(_FakeManager({}))
    assert set(_get(client, "?probe=other").get_json()) == {"servers"}


def test_probe_lists_only_servers_whose_tools_take_a_url(make_client):
    manager = _FakeManager({
        "webfetch": [_url_tool("webfetch", "fetch_readable"), _query_tool("webfetch")],
        "websearch": [_query_tool("websearch")],
        "brokenfetch": [],
    })
    body = _get(make_client(manager), "?probe=url-fetch").get_json()
    assert set(body) == {"servers", "url_fetch"}
    assert body["url_fetch"]["available"] is True
    assert body["url_fetch"]["servers"] == [
        {"id": "webfetch", "name": "WebFetch", "tools": ["fetch_readable"]}
    ]
    assert body["url_fetch"]["failures"] == []


def test_probe_never_spawns_a_server_that_is_not_a_retrieval_candidate(make_client):
    manager = _FakeManager({"webfetch": [_url_tool("webfetch", "fetch_readable")]})
    _get(make_client(manager), "?probe=url-fetch")
    assert sorted(sid for sid, _ in manager.calls) == ["brokenfetch", "webfetch", "websearch"]


def test_probe_passes_a_bounded_deadline(make_client):
    from chat import url_retrieval

    manager = _FakeManager({"webfetch": [_url_tool("webfetch", "fetch_readable")]})
    _get(make_client(manager), "?probe=url-fetch")
    assert {timeout for _, timeout in manager.calls} == {url_retrieval.PROBE_TIMEOUT}
    assert url_retrieval.PROBE_TIMEOUT <= 5.0


def test_a_server_that_does_not_answer_is_reported_not_fatal(make_client):
    manager = _FakeManager(
        {"webfetch": [_url_tool("webfetch", "fetch_readable")]},
        raises=("brokenfetch",),
    )
    body = _get(make_client(manager), "?probe=url-fetch").get_json()
    failures = body["url_fetch"]["failures"]
    assert [f["id"] for f in failures] == ["brokenfetch"]
    assert "server did not answer" in failures[0]["error"]
    assert body["url_fetch"]["available"] is True


def test_a_missing_manager_reads_as_a_failure_not_a_crash(make_client):
    body = _get(make_client(), "?probe=url-fetch").get_json()
    assert body["url_fetch"]["available"] is False
    assert len(body["url_fetch"]["failures"]) == 3


def test_probe_url_fetch_requires_a_token(make_client):
    client = make_client(_FakeManager({}))
    assert client.get(PATH + "?probe=url-fetch").status_code == 401
