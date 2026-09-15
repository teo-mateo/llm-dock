"""Ghost chat (issue #57): POST /api/chat/ghost — stateless, zero-trace SSE.

The endpoint must stream the same wire surface as a normal turn (raw deltas,
tool_call / tool_result / artifact, [DONE], legacy error frame) while
performing zero DB writes: no conversation, no message, no artifact row.
The stream source is monkeypatched, so the tests pin the route's event
mapping, validation, headers, and the no-trace contract — not the model.
"""
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-ghost")

from chat.db import ChatDB
from chat.routes import chat_bp

TOKEN = "test-token-ghost"
RAW_DELTA = '{"id":"x","object":"chat.completion.chunk","choices":[{"delta":{"content":"hello"}}]}'


@pytest.fixture
def ctx(tmp_path):
    db = ChatDB(str(tmp_path / "chat.db"))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = db
    app.config["MCP_MANAGER"] = FakeMCP()
    app.register_blueprint(chat_bp)
    app.testing = True
    yield app, db


def post(ctx, payload, token=TOKEN):
    app = ctx[0]
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/chat/ghost", json=payload, headers=headers)


def frames(body: str):
    """Parsed `data:` payloads of an SSE body, in order."""
    out = []
    for block in body.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                data = line[6:]
                out.append(data if data == "[DONE]" else json.loads(data))
    return out


class FakeMCP:
    def __init__(self, tools=None):
        self._tools = tools or []
        self.requested_servers = None

    def get_all_tools(self, server_ids):
        self.requested_servers = server_ids
        return self._tools


def _patch_stream(monkeypatch, events, with_tools=False):
    fake = {"stream_with_tools": None, "stream_chat_completion": None}

    def fake_with_tools(service_name, messages_array, tools, mcp_manager, **kw):
        fake["stream_with_tools"] = (service_name, messages_array, tools)
        yield from events

    def fake_plain(service_name, messages_array, **kw):
        fake["stream_chat_completion"] = (service_name, messages_array)
        yield from events

    import chat.routes as routes
    monkeypatch.setattr(routes, "stream_with_tools", fake_with_tools)
    monkeypatch.setattr(routes, "stream_chat_completion", fake_plain)
    return fake


# -- validation ---------------------------------------------------------------

def test_requires_service_name(ctx):
    r = post(ctx, {"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    assert "service_name" in r.get_json()["error"]


def test_requires_messages(ctx):
    r = post(ctx, {"service_name": "vllm-test"})
    assert r.status_code == 400
    assert "messages" in r.get_json()["error"]


def test_rejects_non_list_mcp_servers(ctx):
    r = post(ctx, {"service_name": "vllm-test", "messages": [{"role": "user", "content": "hi"}],
                   "mcp_servers": "sympy-math"})
    assert r.status_code == 400
    assert "mcp_servers" in r.get_json()["error"]


def test_requires_auth(ctx):
    r = post(ctx, {"service_name": "vllm-test", "messages": [{"role": "user", "content": "hi"}]},
             token=None)
    assert r.status_code == 401


# -- stream mapping -------------------------------------------------------------

def test_plain_stream_maps_delta_and_done(ctx, monkeypatch):
    fake = _patch_stream(monkeypatch, [
        ("delta", {"content": "hello", "reasoning_content": None, "raw": RAW_DELTA}),
        ("done", {"content": "hello", "reasoning_content": None}),
    ])
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.content_type.startswith("text/event-stream")
    parsed = frames(r.get_data(as_text=True))
    # The raw delta chunk is forwarded verbatim — the documented exception.
    assert RAW_DELTA in r.get_data(as_text=True)
    assert parsed[-1] == "[DONE]"
    # No persistence frames ride a ghost stream.
    assert all(not (isinstance(p, dict) and p.get("type") in ("message_saved", "conversation_updated"))
               for p in parsed)
    assert fake["stream_chat_completion"][0] == "vllm-test"
    assert fake["stream_chat_completion"][1] == [{"role": "user", "content": "hi"}]


def test_error_event_emits_legacy_frame_and_no_done(ctx, monkeypatch):
    _patch_stream(monkeypatch, [
        ("error", {"message": "service unreachable"}),
    ])
    r = post(ctx, {"service_name": "vllm-dead", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    parsed = frames(r.get_data(as_text=True))
    assert parsed == [{"error": "service unreachable"}]


def test_tool_events_pass_through_in_order(ctx, monkeypatch):
    monkeypatch.setattr("chat.routes._get_mcp",
                        lambda: FakeMCP(tools=[{"type": "function", "function": {"name": "render-html__render_html"}}]))
    _patch_stream(monkeypatch, [
        ("tool_call", {"name": "render_html", "arguments": {"html": "<b>x</b>"}, "server_id": "render-html"}),
        ("tool_result", {"name": "render_html", "result": "ok", "server_id": "render-html"}),
        ("artifact", {"type": "html", "title": "Rendered", "content": "<b>x</b>"}),
        ("done", {"content": "done", "reasoning_content": None}),
    ], with_tools=True)
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "render <b>x</b>"}],
                   "mcp_servers": ["render-html"]})
    assert r.status_code == 200
    parsed = frames(r.get_data(as_text=True))
    assert [p.get("type") for p in parsed if isinstance(p, dict)] == [
        "tool_call", "tool_result", "artifact",
    ]
    assert parsed[0]["name"] == "render_html"
    assert parsed[0]["server_id"] == "render-html"
    assert parsed[2]["artifact_type"] == "html"
    assert parsed[-1] == "[DONE]"


def test_tools_are_built_from_the_requested_servers_only(ctx, monkeypatch):
    fake_mcp = FakeMCP(tools=[{"type": "function", "function": {"name": "sympy-math__solve"}}])
    monkeypatch.setattr("chat.routes._get_mcp", lambda: fake_mcp)
    _patch_stream(monkeypatch, [("done", {"content": "ok", "reasoning_content": None})], with_tools=True)
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "hi"}],
                   "mcp_servers": ["sympy-math"]})
    assert r.status_code == 200
    assert fake_mcp.requested_servers == ["sympy-math"]


def test_no_mcp_servers_skips_the_tool_loop(ctx, monkeypatch):
    fake_mcp = FakeMCP(tools=[{"type": "function", "function": {"name": "x"}}])
    monkeypatch.setattr("chat.routes._get_mcp", lambda: fake_mcp)
    fake = _patch_stream(monkeypatch, [("done", {"content": "ok", "reasoning_content": None})])
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    # get_all_tools is only called when mcp_servers is present — the plain
    # path must not even consult the manager.
    assert fake_mcp.requested_servers is None
    assert fake["stream_chat_completion"] is not None
    assert fake["stream_with_tools"] is None


def test_unknown_mcp_server_degrades_to_plain_stream(ctx, monkeypatch):
    fake_mcp = FakeMCP(tools=[])
    monkeypatch.setattr("chat.routes._get_mcp", lambda: fake_mcp)
    fake = _patch_stream(monkeypatch, [("done", {"content": "ok", "reasoning_content": None})])
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "hi"}],
                   "mcp_servers": ["no-such-server"]})
    assert r.status_code == 200
    assert fake["stream_chat_completion"] is not None
    assert fake["stream_with_tools"] is None


# -- headers --------------------------------------------------------------------

def test_response_headers_forbid_caching(ctx, monkeypatch):
    _patch_stream(monkeypatch, [("done", {"content": "ok", "reasoning_content": None})])
    r = post(ctx, {"service_name": "vllm-test", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "no-store" in r.headers["Cache-Control"]
    assert r.headers["Pragma"] == "no-cache"
    assert r.headers["Expires"] == "0"
    assert r.headers["X-Accel-Buffering"] == "no"


# -- zero-trace contract ----------------------------------------------------------

def test_nothing_is_written_to_the_database(ctx, monkeypatch):
    _patch_stream(monkeypatch, [
        ("delta", {"content": "hello", "raw": RAW_DELTA}),
        ("done", {"content": "hello", "reasoning_content": None}),
    ])
    r = post(ctx, {"service_name": "vllm-test",
                   "messages": [{"role": "user", "content": "sensitive"}]})
    assert r.status_code == 200
    db = ctx[1]
    conversations, total = db.list_conversations(limit=-1)
    assert total == 0
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    try:
        for table in ("conversations", "messages", "artifacts"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"ghost chat wrote rows to {table}"
    finally:
        conn.close()
