"""Persistence-policy seam for the chat runtime (Phase 8 of #58).

Runs the SAME monkeypatched model stream through ChatRunner under two
policies — DbPersistencePolicy (durable) and NullPersistencePolicy (ephemeral)
— and asserts the runtime drives an identical event stream either way, while
only the durable policy writes to SQLite. This is the architectural hook Ghost
Chat (#57) needs.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import runtime
from chat.db import ChatDB
from chat.models import Conversation, Message, ChatRun
from chat.runs import ChatRunStatus
from chat.runtime import ChatRunner, ChatTurnRequest
from chat.persistence import (
    DbPersistencePolicy,
    NullPersistencePolicy,
    PersistencePolicy,
)


class _RecordingBus:
    """Captures the (type, data) of every runtime event the runner publishes."""

    def __init__(self):
        self.events = []

    def publish(self, run_id, event):
        self.events.append(event)

    def types(self):
        return [e.type for e in self.events]


def _delta(content, reasoning=""):
    return ("delta", {"content": content, "reasoning_content": reasoning,
                      "raw": json.dumps({"choices": [{"delta": {"content": content}}]})})


def _patch_stream(monkeypatch, factory):
    def _wrap(*a, **k):
        return factory()
    monkeypatch.setattr(runtime, "stream_chat_completion", _wrap)
    monkeypatch.setattr(runtime, "stream_with_tools", _wrap)


def _stub():
    yield _delta("Hello ")
    yield _delta("world")
    yield ("done", {"content": "Hello world", "reasoning_content": None})


def _conv():
    return Conversation(id=str(uuid.uuid4()), title="t", main_service="svc")


def _user_msg(conv):
    return Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user",
                   content="hi", seq=1)


# -- durable policy ------------------------------------------------------


def test_db_policy_persists_and_completes(tmp_path, monkeypatch):
    _patch_stream(monkeypatch, _stub)
    db = ChatDB(str(tmp_path / "chat.db"))
    conv = _conv()
    db.create_conversation(conv)
    user = _user_msg(conv)
    db.add_message(user)
    run = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                     status=ChatRunStatus.QUEUED, user_message_id=user.id))
    bus = _RecordingBus()

    runner = ChatRunner(db, event_bus=bus)
    saved = runner.run(run, ChatTurnRequest(conversation=conv))

    assert saved is not None
    assert saved.content == "Hello world"
    # Durable: the assistant message and completed status are in SQLite.
    roles = [m.role for m in db.get_messages(conv.id)]
    assert roles == ["user", "assistant"]
    assert db.get_chat_run(run.id).status == "completed"
    assert bus.types() == ["run_started", "delta", "delta", "run_completed"]


# -- ephemeral policy ----------------------------------------------------


def test_null_policy_runs_without_persisting(tmp_path, monkeypatch):
    _patch_stream(monkeypatch, _stub)
    # A real DB exists but the null policy must never touch it.
    db = ChatDB(str(tmp_path / "chat.db"))
    conv = _conv()
    db.create_conversation(conv)

    user = _user_msg(conv)
    policy = NullPersistencePolicy(messages=[user])
    bus = _RecordingBus()
    run = ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id, status=ChatRunStatus.QUEUED)

    runner = ChatRunner(persistence=policy, event_bus=bus)
    saved = runner.run(run, ChatTurnRequest(conversation=conv))

    assert saved is not None
    assert saved.content == "Hello world"
    # Ephemeral: nothing written to SQLite, but the transcript is kept in memory.
    assert db.get_messages(conv.id) == []
    assert db.get_chat_run(run.id) is None
    assert [m.role for m in policy.messages] == ["user", "assistant"]
    assert policy.messages[-1].seq == 2
    assert bus.types() == ["run_started", "delta", "delta", "run_completed"]


def test_same_stream_identical_events_across_policies(tmp_path, monkeypatch):
    """Acceptance: the same model stream produces the same runtime event
    sequence regardless of persistence policy."""
    _patch_stream(monkeypatch, _stub)

    db = ChatDB(str(tmp_path / "chat.db"))
    conv = _conv()
    db.create_conversation(conv)
    user = _user_msg(conv)
    db.add_message(user)
    run = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                     status=ChatRunStatus.QUEUED, user_message_id=user.id))
    db_bus = _RecordingBus()
    ChatRunner(db, event_bus=db_bus).run(run, ChatTurnRequest(conversation=conv))

    null_bus = _RecordingBus()
    null_run = ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id, status=ChatRunStatus.QUEUED)
    ChatRunner(persistence=NullPersistencePolicy(messages=[_user_msg(conv)]),
               event_bus=null_bus).run(null_run, ChatTurnRequest(conversation=conv))

    assert db_bus.types() == null_bus.types()


def test_null_policy_failure_does_not_persist(tmp_path, monkeypatch):
    def _boom():
        yield ("error", {"message": "model exploded"})

    _patch_stream(monkeypatch, _boom)
    db = ChatDB(str(tmp_path / "chat.db"))
    conv = _conv()
    db.create_conversation(conv)
    policy = NullPersistencePolicy(messages=[_user_msg(conv)])
    bus = _RecordingBus()
    run = ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id, status=ChatRunStatus.QUEUED)

    saved = ChatRunner(persistence=policy, event_bus=bus).run(
        run, ChatTurnRequest(conversation=conv))

    assert saved is None
    assert bus.types() == ["run_started", "run_failed"]
    # No assistant turn was appended on failure.
    assert [m.role for m in policy.messages] == ["user"]


# -- seam shape ----------------------------------------------------------


def test_default_runner_uses_db_policy(tmp_path):
    db = ChatDB(str(tmp_path / "chat.db"))
    runner = ChatRunner(db)
    assert isinstance(runner.persistence, DbPersistencePolicy)
    assert runner.persistence.db is db


def test_policies_implement_the_interface():
    assert issubclass(DbPersistencePolicy, PersistencePolicy)
    assert issubclass(NullPersistencePolicy, PersistencePolicy)
