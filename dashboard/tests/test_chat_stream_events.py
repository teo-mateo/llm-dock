"""SSE frame-contract tests for the send route (Phase 4 of #58).

Originally these characterized routes._stream_response directly. That function
was removed in Phase 4 (sends now start a background run observed over the
event bus), so the same wire-format guarantees are re-asserted here through the
real POST .../messages route and the run_manager observer: the frontend SSE
parser must see identical frames regardless of the new background-run plumbing.

File-backed ChatDB (the runner executes on a worker thread); model/tool streams
are monkeypatched — no Docker/GPU/model.
"""
import json
import os
import sys
import uuid

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-stream-events")

from chat import runtime
from chat.db import ChatDB
from chat.event_bus import EventBus
from chat.run_manager import ChatRunManager
from chat.models import Conversation
from chat.routes import chat_bp

TOKEN = "test-token-stream-events"
MESSAGES = "/api/chat/conversations/{}/messages"


class _FakeMCPManager:
    def __init__(self):
        self.tools_requested = None

    def get_all_tools(self, servers):
        self.tools_requested = list(servers)
        return [{"type": "function", "function": {"name": "solve"}}]


@pytest.fixture
def ctx(tmp_path):
    db = ChatDB(str(tmp_path / "chat.db"))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = db
    bus = EventBus()
    manager = ChatRunManager(db, bus, max_workers=2)
    app.config["CHAT_EVENT_BUS"] = bus
    app.config["CHAT_RUN_MANAGER"] = manager
    app.config["MCP_MANAGER"] = _FakeMCPManager()
    app.register_blueprint(chat_bp)
    app.testing = True
    try:
        yield app, db, manager
    finally:
        manager.shutdown()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _conv(db, title="t", mcp_servers_json=None):
    conv = Conversation(id=str(uuid.uuid4()), title=title, main_service="svc",
                        mcp_servers_json=mcp_servers_json)
    db.create_conversation(conv)
    return conv


def _delta(content, reasoning=""):
    return ("delta", {"content": content, "reasoning_content": reasoning,
                      "raw": json.dumps({"choices": [{"delta": {"content": content}}]})})


def _patch(monkeypatch, factory):
    def _wrap(*a, **k):
        return factory()
    monkeypatch.setattr(runtime, "stream_chat_completion", _wrap)
    monkeypatch.setattr(runtime, "stream_with_tools", _wrap)


def _send(app, conv_id, content="hi"):
    """POST a message and return the fully-drained list of SSE frames."""
    resp = app.test_client().post(MESSAGES.format(conv_id), headers=_auth(),
                                  json={"content": content})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    return [chunk + "\n\n" for chunk in text.split("\n\n") if chunk.strip()]


def _payloads(frames):
    out = []
    for f in frames:
        assert f.startswith("data: ") and f.endswith("\n\n"), repr(f)
        body = f[len("data: "):-2]
        if body == "[DONE]":
            out.append(("done", body))
            continue
        try:
            out.append(("json", json.loads(body)))
        except json.JSONDecodeError:
            out.append(("raw", body))
    return out


def _kinds(payloads):
    """Reduce frames to ordered labels. Heartbeats are dropped (they may
    appear on a slow worker and are not part of the content contract)."""
    kinds = []
    for kind, v in payloads:
        if kind == "done":
            kinds.append("[DONE]")
        elif kind == "json" and v.get("type") == "heartbeat":
            continue
        elif kind == "json" and "type" in v:
            kinds.append(v["type"])
        elif kind == "json" and "choices" in v:
            kinds.append("delta")
        elif kind == "json" and "error" in v:
            kinds.append("error")
        else:
            kinds.append("raw")
    return kinds


def _by_type(payloads, t):
    return next(v for kind, v in payloads if kind == "json" and v.get("type") == t)


# -- Plain stream -------------------------------------------------------


def test_plain_send_emits_raw_deltas_then_handshake(ctx, monkeypatch):
    app, db = ctx[0], ctx[1]
    conv = _conv(db)

    def stub():
        yield _delta("Hello ")
        yield _delta("world")
        yield ("done", {"content": "Hello world", "reasoning_content": None})

    _patch(monkeypatch, stub)
    payloads = _payloads(_send(app, conv.id))

    # Deltas are forwarded as raw upstream chunks (no typed "delta" frame).
    delta_chunks = [v for kind, v in payloads if kind == "json" and "type" not in v and "choices" in v]
    assert [c["choices"][0]["delta"]["content"] for c in delta_chunks] == ["Hello ", "world"]
    assert _kinds(payloads) == ["delta", "delta", "[DONE]", "message_saved"]

    msgs = db.get_messages(conv.id)
    assert msgs[1].content == "Hello world"
    saved = _by_type(payloads, "message_saved")
    assert saved["message_id"] == msgs[1].id
    assert saved["seq"] == msgs[1].seq == 2


# -- Tool stream --------------------------------------------------------


def test_tool_send_emits_all_frames_and_persists(ctx, monkeypatch):
    app, db = ctx[0], ctx[1]
    conv = _conv(db, mcp_servers_json=json.dumps(["sympy-math"]))

    def stub():
        yield ("tool_call_pending", {"index": 0, "name": "solve"})
        yield ("tool_call", {"name": "solve", "arguments": {"x": 1}, "server_id": "sympy-math"})
        yield ("tool_result", {"name": "solve", "result": "x = 1", "server_id": "sympy-math"})
        yield ("artifact", {"type": "code", "title": "snip", "content": "print(1)", "language": "python"})
        yield _delta("The answer is 1.")
        yield ("done", {"content": "The answer is 1.", "reasoning_content": None})

    _patch(monkeypatch, stub)
    payloads = _payloads(_send(app, conv.id))

    assert _kinds(payloads) == [
        "tool_call_pending", "tool_call", "tool_result", "artifact",
        "delta", "[DONE]", "message_saved",
    ]
    tr = _by_type(payloads, "tool_result")
    assert (tr["name"], tr["result"], tr["server_id"]) == ("solve", "x = 1", "sympy-math")
    art = _by_type(payloads, "artifact")
    assert (art["artifact_type"], art["title"], art["content"]) == ("code", "snip", "print(1)")

    assistant = db.get_messages(conv.id)[1]
    calls = json.loads(assistant.tool_calls_json)
    assert calls[0]["result"] == "x = 1"
    assert db.get_artifacts_for_conversation(conv.id)[assistant.id][0].content == "print(1)"


# -- Parse warning ------------------------------------------------------


def test_parse_warning_frame_and_persisted(ctx, monkeypatch):
    app, db = ctx[0], ctx[1]
    conv = _conv(db)
    warning = {"kind": "json_codeblock_call", "snippet": "```json", "description": "drift"}

    def stub():
        yield _delta("partial ")
        yield ("parse_warning", dict(warning))
        yield _delta("answer")
        yield ("done", {"content": "partial answer", "reasoning_content": None})

    _patch(monkeypatch, stub)
    payloads = _payloads(_send(app, conv.id))

    assert _kinds(payloads) == ["delta", "parse_warning", "delta", "[DONE]", "message_saved"]
    assert _by_type(payloads, "parse_warning")["kind"] == "json_codeblock_call"
    assert json.loads(db.get_messages(conv.id)[1].parse_warning_json) == warning


# -- Error --------------------------------------------------------------


def test_error_frame_and_no_message_saved(ctx, monkeypatch):
    app, db = ctx[0], ctx[1]
    conv = _conv(db)

    def stub():
        yield _delta("partial")
        yield ("error", {"message": "boom"})

    _patch(monkeypatch, stub)
    payloads = _payloads(_send(app, conv.id))

    assert ("done", "[DONE]") not in payloads
    assert not any(kind == "json" and v.get("type") == "message_saved" for kind, v in payloads)
    err = next(v for kind, v in payloads if kind == "json" and "error" in v)
    assert err["error"] == "boom"
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]


# -- First-message conversation_updated tail ----------------------------


def test_first_message_emits_conversation_updated_tail(ctx, monkeypatch):
    app, db = ctx[0], ctx[1]
    conv = _conv(db, title="New Conversation")  # enables auto-title

    def stub():
        yield _delta("Hi")
        yield ("done", {"content": "Hi", "reasoning_content": None})

    _patch(monkeypatch, stub)
    payloads = _payloads(_send(app, conv.id))

    assert _kinds(payloads) == ["delta", "[DONE]", "message_saved", "conversation_updated"]
    cu = _by_type(payloads, "conversation_updated")
    assert cu["id"] == conv.id and cu["title"] == "Hi"
    assert db.get_conversation(conv.id).title == "Hi"
