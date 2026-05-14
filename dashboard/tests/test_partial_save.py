"""Tests for save-on-disconnect in chat._stream_response.

When the client aborts mid-stream (navigation, tab close, network drop),
the assistant message we'd have eventually written should still land in
the DB with whatever was generated so far — so the user doesn't lose
visible work when they come back. The guard logic also has to prevent
stale streams from overwriting newer state.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-partial-save")

from chat import routes
from chat.db import ChatDB
from chat.models import Conversation, Message


def _seed_conversation(db):
    """Create a conversation in the DB and return (Conversation, user_msg)."""
    conv = Conversation(
        id=str(uuid.uuid4()),
        title="t",
        main_service="test-service",
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


def _delta(content, raw=None):
    """Build a delta tuple matching what stream_chat_completion yields."""
    return ("delta", {"content": content, "reasoning_content": "", "raw": raw or json.dumps({"choices": [{"delta": {"content": content}}]})})


def _patch_stream(monkeypatch, stream_factory):
    """Replace both stream_chat_completion and stream_with_tools with the same stub.

    stream_factory() returns a fresh generator each time so the test can
    re-invoke _stream_response in the same process without exhausting a
    one-shot iterator.
    """
    def _wrapper(*args, **kwargs):
        return stream_factory()
    monkeypatch.setattr(routes, "stream_chat_completion", _wrapper)
    monkeypatch.setattr(routes, "stream_with_tools", _wrapper)


def test_partial_save_persists_accumulated_deltas_on_disconnect(monkeypatch, tmp_path):
    """A close() after consuming some deltas should leave the partial in DB."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield _delta("hello ")
        yield _delta("world")
        # block forever — simulates a still-generating model
        while True:
            yield _delta("")  # never reached after close() but keeps the generator alive

    _patch_stream(monkeypatch, stub)

    gen = routes._stream_response(db, conv, user_msg)
    # Consume two deltas + the upstream "yields" forwarded to SSE.
    next(gen)
    next(gen)
    gen.close()

    msgs = db.get_messages(conv.id)
    assert len(msgs) == 2, f"expected user + partial assistant, got {len(msgs)}"
    assistant = msgs[1]
    assert assistant.role == "assistant"
    assert assistant.content == "hello world"
    assert assistant.model_service == "test-service"


def test_close_before_any_delta_writes_nothing(monkeypatch, tmp_path):
    """Disconnect with no deltas accumulated must NOT write a partial.

    Drives the generator to its first yield via a tool_call (which doesn't
    accumulate content), then closes. The user message gets persisted
    inside _stream_response, but no assistant row should appear.
    """
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield ("tool_call", {"name": "noop", "arguments": {}, "server_id": "x"})
        while True:
            yield ("tool_call", {"name": "noop", "arguments": {}, "server_id": "x"})

    _patch_stream(monkeypatch, stub)

    gen = routes._stream_response(db, conv, user_msg)
    next(gen)  # advances past user-msg insert and the first tool_call yield
    gen.close()

    msgs = db.get_messages(conv.id)
    assert len(msgs) == 1, f"expected only user message, got {len(msgs)}: {[m.role for m in msgs]}"
    assert msgs[0].role == "user"


def test_error_event_does_not_save_partial(monkeypatch, tmp_path):
    """A model-side error after some deltas must NOT write a partial assistant row."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield _delta("partial answer")
        yield ("error", {"message": "model exploded"})

    _patch_stream(monkeypatch, stub)

    gen = routes._stream_response(db, conv, user_msg)
    # Drain to completion — the error branch will yield then return.
    sse_events = list(gen)

    # Sanity: the error event was delivered to the client.
    assert any('"error"' in e for e in sse_events), sse_events

    msgs = db.get_messages(conv.id)
    assert len(msgs) == 1, f"error path must not save a partial, got {len(msgs)}"
    assert msgs[0].role == "user"


def test_stale_stream_skips_save_when_user_msg_deleted(monkeypatch, tmp_path, caplog):
    """If the user message was deleted mid-stream (e.g. edit), drop the partial."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    deleted = {"flag": False}

    def stub():
        yield _delta("hello")
        # Between this and the next yield the test will delete the user msg
        # and close the generator. The partial-save check sees user_msg
        # missing and skips.
        deleted["flag"] = True
        while True:
            yield _delta("")

    _patch_stream(monkeypatch, stub)

    gen = routes._stream_response(db, conv, user_msg)
    next(gen)  # forwards "hello"
    next(gen)  # triggers the deletion flag inside stub; "" is forwarded as a delta

    # Now simulate the edit: drop the user message (and any descendants).
    db.delete_messages_from_seq(conv.id, user_msg.seq)
    assert deleted["flag"]
    assert db.get_message(user_msg.id) is None

    import logging
    with caplog.at_level(logging.INFO, logger="chat.routes"):
        gen.close()

    msgs = db.get_messages(conv.id)
    assert len(msgs) == 0, f"stale partial must not be written; got {len(msgs)} rows"

    # The skip log line should mention this assistant_msg_id was dropped.
    assert any("no longer exists" in r.message for r in caplog.records), (
        "expected a 'no longer exists' info log, got " + repr([r.message for r in caplog.records])
    )


def test_normal_completion_does_not_double_save(monkeypatch, tmp_path):
    """The done branch already inserts; the finally must not write a second row."""
    db = ChatDB(":memory:")
    conv, user_msg = _seed_conversation(db)

    def stub():
        yield _delta("complete answer")
        yield ("done", {"content": "complete answer", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)

    gen = routes._stream_response(db, conv, user_msg)
    list(gen)  # drain to completion (no close)

    msgs = db.get_messages(conv.id)
    assert len(msgs) == 2, f"expected user + one assistant, got {len(msgs)}"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "complete answer"
