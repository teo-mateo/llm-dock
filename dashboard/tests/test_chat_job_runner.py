"""Tests for the background ChatRunner (Phase 3 of #58).

The runner executes a turn and persists the result without any Flask SSE
response. Model/tool streams are monkeypatched — no Docker, GPU, or model.

These use a temp FILE-backed ChatDB (not :memory:) so the persistence path
matches Phase 4, where the runner executes on a background thread and the
shared :memory: connection (check_same_thread=True) would break.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import runtime
from chat.db import ChatDB
from chat.event_bus import EventBus
from chat.models import Conversation, Message, ChatRun
from chat.runs import ChatRunStatus
from chat.runtime import ChatRunner, ChatTurnRequest


@pytest.fixture
def db(tmp_path):
    return ChatDB(str(tmp_path / "chat.db"))


def _seed(db, mcp_servers_json=None):
    """Create a conversation + a persisted user message + a queued run."""
    conv = Conversation(id=str(uuid.uuid4()), title="t", main_service="svc",
                        mcp_servers_json=mcp_servers_json)
    db.create_conversation(conv)
    user_msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user",
                       content="hi", seq=db.next_seq(conv.id))
    db.add_message(user_msg)
    run = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                     status=ChatRunStatus.QUEUED, user_message_id=user_msg.id))
    return conv, user_msg, run


def _delta(content, reasoning=""):
    return ("delta", {"content": content, "reasoning_content": reasoning,
                      "raw": json.dumps({"choices": [{"delta": {"content": content}}]})})


def _patch_stream(monkeypatch, factory):
    """Patch both stream functions in the runtime module namespace."""
    def _wrap(*a, **k):
        return factory()
    monkeypatch.setattr(runtime, "stream_chat_completion", _wrap)
    monkeypatch.setattr(runtime, "stream_with_tools", _wrap)


class _FakeMCPManager:
    def __init__(self):
        self.tools_requested = None

    def get_all_tools(self, servers):
        self.tools_requested = list(servers)
        return [{"type": "function", "function": {"name": "solve"}}]


def _drain(bus, run_id):
    """Subscribe and return a function that reads everything published so far."""
    q = bus.subscribe(run_id)

    def read():
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

    return read


# -- Successful plain run -----------------------------------------------


def test_plain_run_persists_reply_and_completes(db, monkeypatch):
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("Hello ", reasoning="thinking ")
        yield _delta("world")
        yield ("done", {"content": "Hello world", "reasoning_content": "ignored final"})

    _patch_stream(monkeypatch, stub)
    bus = EventBus()
    read_events = _drain(bus, run.id)

    result = ChatRunner(db, event_bus=bus).run(run, ChatTurnRequest(conversation=conv))

    assert result is not None
    msgs = db.get_messages(conv.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assistant = msgs[1]
    assert assistant.content == "Hello world"
    # Accumulated reasoning wins over the final round's reasoning.
    assert assistant.reasoning_content == "thinking "
    assert assistant.model_service == "svc"

    finished = db.get_chat_run(run.id)
    assert finished.status == "completed"
    assert finished.started_at is not None and finished.completed_at is not None

    types = [e.type for e in read_events()]
    assert types[0] == "run_started"
    assert "delta" in types
    assert types[-1] == "run_completed"


# -- Tool run -----------------------------------------------------------


def test_tool_run_persists_calls_results_artifacts_and_reply(db, monkeypatch):
    conv, user_msg, run = _seed(db, mcp_servers_json=json.dumps(["sympy-math"]))

    def stub():
        yield ("tool_call_pending", {"index": 0, "name": "solve"})
        yield ("tool_call", {"name": "solve", "arguments": {"x": 1}, "server_id": "sympy-math"})
        yield ("tool_result", {"name": "solve", "result": "x = 1", "server_id": "sympy-math"})
        yield ("artifact", {"type": "code", "title": "snip", "content": "print(1)", "language": "python"})
        yield _delta("The answer is 1.")
        yield ("done", {"content": "The answer is 1.", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    mgr = _FakeMCPManager()
    result = ChatRunner(db).run(run, ChatTurnRequest(conversation=conv, mcp_manager=mgr))

    assert mgr.tools_requested == ["sympy-math"]  # routed through the tool loop
    assert result.content == "The answer is 1."

    assistant = db.get_messages(conv.id)[1]
    calls = json.loads(assistant.tool_calls_json)
    assert calls[0]["name"] == "solve"
    assert calls[0]["result"] == "x = 1"  # matched-back result

    arts = db.get_artifacts_for_conversation(conv.id)
    assert arts[assistant.id][0].content == "print(1)"
    assert db.get_chat_run(run.id).status == "completed"


# -- Parse warning ------------------------------------------------------


def test_parse_warning_persisted_on_assistant_message(db, monkeypatch):
    conv, user_msg, run = _seed(db)
    warning = {"kind": "json_codeblock_call", "snippet": "```json", "description": "drift"}

    def stub():
        yield _delta("partial ")
        yield ("parse_warning", dict(warning))
        yield _delta("answer")
        yield ("done", {"content": "partial answer", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    ChatRunner(db).run(run, ChatTurnRequest(conversation=conv))

    assistant = db.get_messages(conv.id)[1]
    assert json.loads(assistant.parse_warning_json) == warning


# -- Model error --------------------------------------------------------


def test_model_error_marks_run_failed_and_persists_no_assistant(db, monkeypatch):
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("partial answer")
        yield ("error", {"message": "model exploded"})

    _patch_stream(monkeypatch, stub)
    bus = EventBus()
    read_events = _drain(bus, run.id)
    result = ChatRunner(db, event_bus=bus).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    # No completed assistant message was written.
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]

    failed = db.get_chat_run(run.id)
    assert failed.status == "failed"
    assert failed.error == "model exploded"

    types = [e.type for e in read_events()]
    assert types[-1] == "run_failed"


def test_stream_without_done_marks_failed(db, monkeypatch):
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("incomplete")
        # generator ends with no done/error

    _patch_stream(monkeypatch, stub)
    result = ChatRunner(db).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]
    failed = db.get_chat_run(run.id)
    assert failed.status == "failed"
    assert "unexpectedly" in failed.error.lower()


def test_exception_in_stream_marks_failed(db, monkeypatch):
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("boom incoming")
        raise RuntimeError("kaboom")

    _patch_stream(monkeypatch, stub)
    result = ChatRunner(db).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    failed = db.get_chat_run(run.id)
    assert failed.status == "failed"
    assert "kaboom" in failed.error


def test_persistence_exception_rolls_back_no_assistant(db, monkeypatch):
    """If artifact persistence throws after the message insert, the whole
    completion rolls back: no orphan assistant message on the failed run."""
    conv, user_msg, run = _seed(db)

    def stub():
        yield ("artifact", {"type": "code", "title": "t", "content": "x", "language": "py"})
        yield _delta("answer")
        yield ("done", {"content": "answer", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)

    real_save = db.save_artifact

    def boom(artifact, conn=None):
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "save_artifact", boom)

    result = ChatRunner(db).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    # The assistant insert was rolled back with the failed artifact.
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]
    failed = db.get_chat_run(run.id)
    assert failed.status == "failed"
    assert "disk full" in failed.error


def test_cancelled_before_start_does_no_work(db, monkeypatch):
    """A run cancelled before the worker picks it up must not run the model
    or write an assistant message."""
    conv, user_msg, run = _seed(db)
    db.cancel_chat_run(run.id)

    started = {"n": 0}

    def stub():
        started["n"] += 1
        yield ("done", {"content": "should not run", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    result = ChatRunner(db).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    assert started["n"] == 0  # the stream was never built/consumed
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]
    assert db.get_chat_run(run.id).status == "cancelled"


def test_cancelled_mid_stream_writes_no_completed_message(db, monkeypatch):
    """If the run is cancelled while streaming, the done handler's atomic
    completion loses the terminal guard and writes nothing."""
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("partial ")
        # Simulate another thread cancelling the run mid-stream.
        db.cancel_chat_run(run.id)
        yield _delta("more")
        yield ("done", {"content": "partial more", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    bus = EventBus()
    read_events = _drain(bus, run.id)
    result = ChatRunner(db, event_bus=bus).run(run, ChatTurnRequest(conversation=conv))

    assert result is None
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]
    assert db.get_chat_run(run.id).status == "cancelled"
    assert [e.type for e in read_events()][-1] == "run_cancelled"


def test_runner_works_without_event_bus(db, monkeypatch):
    """The bus is optional; a None bus must not break persistence."""
    conv, user_msg, run = _seed(db)

    def stub():
        yield _delta("ok")
        yield ("done", {"content": "ok", "reasoning_content": None})

    _patch_stream(monkeypatch, stub)
    result = ChatRunner(db, event_bus=None).run(run, ChatTurnRequest(conversation=conv))
    assert result.content == "ok"
    assert db.get_chat_run(run.id).status == "completed"
