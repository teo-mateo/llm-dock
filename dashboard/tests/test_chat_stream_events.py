"""Characterization tests for the chat SSE stream (Phase 0 of #58).

These pin the *current* behavior of `chat.routes._stream_response` before the
runtime is extracted into a background-run architecture. They assert the exact
SSE frames the generator emits and the rows it persists, so the upcoming
extraction can be proven behavior-preserving.

Nothing here needs Docker, a GPU, or a running model: the model/tool stream is
monkeypatched with a stub generator (same technique as test_partial_save.py).
"""
import json
import os
import sys
import uuid

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-stream-events")

from chat import routes
from chat.db import ChatDB
from chat.models import Conversation, Message
from chat.routes import chat_bp

TOKEN = "test-token-stream-events"


# -- Helpers ------------------------------------------------------------


def _seed_conversation(db, mcp_servers_json=None):
    """Create a conversation + an unsaved user message (saved by _stream_response)."""
    conv = Conversation(
        id=str(uuid.uuid4()),
        title="t",
        main_service="test-service",
        mcp_servers_json=mcp_servers_json,
    )
    db.create_conversation(conv)
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="user",
        content="hello",
        seq=db.next_seq(conv.id),
    )
    return conv, user_msg


def _delta(content, reasoning="", raw=None):
    """A delta tuple matching what stream_chat_completion yields."""
    return (
        "delta",
        {
            "content": content,
            "reasoning_content": reasoning,
            "raw": raw or json.dumps({"choices": [{"delta": {"content": content}}]}),
        },
    )


def _patch_stream(monkeypatch, stream_factory):
    """Replace both stream_chat_completion and stream_with_tools with a stub.

    Both are patched because _stream_response picks one based on whether MCP
    tools are present; the test drives event content directly via the stub
    regardless of which branch is taken.
    """
    def _wrapper(*args, **kwargs):
        return stream_factory()

    monkeypatch.setattr(routes, "stream_chat_completion", _wrapper)
    monkeypatch.setattr(routes, "stream_with_tools", _wrapper)


def _drain(db, conv, user_msg):
    """Run _stream_response to completion, returning the list of SSE frames."""
    return list(routes._stream_response(db, conv, user_msg))


def _frame_payloads(frames):
    """Parse `data: ...` SSE frames into Python objects.

    Returns a list of (kind, value): kind is "json" with the decoded dict,
    "done" for the [DONE] sentinel, or "raw" for a non-JSON / raw upstream
    chunk that isn't a typed event.
    """
    out = []
    for f in frames:
        assert f.startswith("data: ") and f.endswith("\n\n"), f"bad SSE framing: {f!r}"
        body = f[len("data: "):-2]
        if body == "[DONE]":
            out.append(("done", body))
            continue
        try:
            out.append(("json", json.loads(body)))
        except json.JSONDecodeError:
            out.append(("raw", body))
    return out


def _types(payloads):
    """Collect the `type` field of every typed-JSON frame."""
    return [v.get("type") for kind, v in payloads if kind == "json" and "type" in v]


# -- Plain model stream -------------------------------------------------


def test_plain_stream_emits_deltas_and_done(monkeypatch):
    """A plain completion forwards delta frames, then [DONE] and message_saved."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield _delta("Hello ")
        yield _delta("world")
        yield ("done", {"content": "Hello world", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    frames = _drain(db, conv, user_msg)
    payloads = _frame_payloads(frames)

    # Deltas are forwarded as the raw upstream chunk verbatim, NOT a typed
    # `{"type": "delta"}` frame. The chunk is valid JSON but carries `choices`
    # and no `type` key — this raw passthrough is exactly what #58's
    # event_codec must preserve (or normalize in a separate FE+BE PR).
    delta_chunks = [
        v for kind, v in payloads
        if kind == "json" and "type" not in v and "choices" in v
    ]
    assert any(c["choices"][0]["delta"].get("content") == "Hello " for c in delta_chunks), delta_chunks
    assert any(c["choices"][0]["delta"].get("content") == "world" for c in delta_chunks), delta_chunks

    # Terminal sentinel + the persisted-message handshake.
    assert ("done", "[DONE]") in payloads
    saved = [v for kind, v in payloads if kind == "json" and v.get("type") == "message_saved"]
    assert len(saved) == 1
    assert saved[0]["seq"] == 2

    # The assistant row is persisted with the full content.
    msgs = db.get_messages(conv.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "Hello world"
    assert msgs[1].model_service == "test-service"


# -- Tool stream --------------------------------------------------------


def test_tool_stream_emits_all_event_types_and_persists(monkeypatch):
    """A tool turn forwards pending/call/result/artifact frames and persists them."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db, mcp_servers_json=json.dumps(["sympy-math"]))

    def stub():
        yield ("tool_call_pending", {"index": 0, "name": "solve"})
        yield ("tool_call", {"name": "solve", "arguments": {"x": 1}, "server_id": "sympy-math"})
        yield ("tool_result", {"name": "solve", "result": "x = 1", "server_id": "sympy-math"})
        yield ("artifact", {"type": "code", "title": "snippet", "content": "print(1)", "language": "python"})
        yield _delta("The answer is 1.")
        yield ("done", {"content": "The answer is 1.", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    payloads = _frame_payloads(_drain(db, conv, user_msg))
    seen = _types(payloads)

    for expected in ("tool_call_pending", "tool_call", "tool_result", "artifact"):
        assert expected in seen, f"missing {expected!r} frame; saw {seen}"
    assert ("done", "[DONE]") in payloads

    # The tool_call frame carries name/arguments/server_id.
    tc = next(v for kind, v in payloads if kind == "json" and v.get("type") == "tool_call")
    assert tc["name"] == "solve"
    assert tc["arguments"] == {"x": 1}
    assert tc["server_id"] == "sympy-math"

    # Assistant message persisted with final content and the tool call (incl.
    # the matched-back result) in tool_calls_json.
    msgs = db.get_messages(conv.id)
    assistant = msgs[1]
    assert assistant.content == "The answer is 1."
    persisted_calls = json.loads(assistant.tool_calls_json)
    assert persisted_calls[0]["name"] == "solve"
    assert persisted_calls[0]["result"] == "x = 1"

    # Artifact persisted and linked to the assistant message.
    arts = db.get_artifacts_for_conversation(conv.id)
    assert assistant.id in arts
    assert arts[assistant.id][0].content == "print(1)"
    assert arts[assistant.id][0].title == "snippet"


# -- Parse warning ------------------------------------------------------


def test_parse_warning_forwarded_and_persisted(monkeypatch):
    """A format-drift parse_warning is forwarded live and stored on the message."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    warning = {"kind": "json_codeblock_call", "snippet": "```json", "description": "drift"}

    def stub():
        yield _delta("partial ")
        yield ("parse_warning", dict(warning))
        yield _delta("answer")
        yield ("done", {"content": "partial answer", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    payloads = _frame_payloads(_drain(db, conv, user_msg))

    pw = [v for kind, v in payloads if kind == "json" and v.get("type") == "parse_warning"]
    assert len(pw) == 1
    assert pw[0]["kind"] == "json_codeblock_call"
    assert pw[0]["description"] == "drift"

    msgs = db.get_messages(conv.id)
    assert json.loads(msgs[1].parse_warning_json) == warning


# -- Cross-round reasoning accumulation (regression guard) --------------


def test_accumulated_reasoning_wins_over_final_round(monkeypatch):
    """Full cross-round reasoning the user saw is persisted, not just the last round.

    Pins routes.py behavior: `accumulated_reasoning or done.reasoning_content`.
    In a multi-round tool flow, reasoning streamed before each tool round must
    survive the post-save refetch.
    """
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield _delta("", reasoning="thinking round one... ")
        yield _delta("", reasoning="round two... ")
        yield _delta("Final.")
        # done carries only the final round's reasoning, which must NOT win.
        yield ("done", {"content": "Final.", "reasoning_content": "round two... "})

    _patch_stream(monkeypatch, stub)
    _drain(db, conv, user_msg)

    assistant = db.get_messages(conv.id)[1]
    assert assistant.reasoning_content == "thinking round one... round two... "


# -- Artifacts surface through the GET endpoint -------------------------


@pytest.fixture
def app_db():
    """Flask app sharing one ChatDB instance with direct _stream_response calls."""
    db = ChatDB(":memory:")
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = db
    app.register_blueprint(chat_bp)
    app.testing = True
    return app, db


def test_artifacts_returned_by_get_conversation(monkeypatch, app_db):
    """Artifacts persisted during a turn are returned by GET /conversations/<id>."""
    app, db = app_db
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield ("artifact", {"type": "html", "title": "page", "content": "<h1>hi</h1>", "language": "html"})
        yield _delta("Rendered.")
        yield ("done", {"content": "Rendered.", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    _drain(db, conv, user_msg)  # same db instance the route reads from

    client = app.test_client()
    r = client.get(
        f"/api/chat/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200
    body = r.get_json()

    assistant_id = body["messages"][1]["id"]
    assert assistant_id in body["artifacts"]
    art = body["artifacts"][assistant_id][0]
    assert art["content"] == "<h1>hi</h1>"
    assert art["title"] == "page"
