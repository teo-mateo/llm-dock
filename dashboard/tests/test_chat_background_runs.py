"""Background-run lifecycle tests (Phase 4 of #58).

Sends now start a background run; the SSE response is only an observer.
These cover: a run completing after the observer detaches (navigation is not
cancellation), the one-active-run-per-conversation 409 guard, active_run
clearing on completion/failure, and startup recovery of interrupted runs.

File-backed ChatDB (not :memory:) because the runner executes on a worker
thread and the shared :memory: connection (check_same_thread=True) would break.
Model/tool streams are monkeypatched — no Docker/GPU/model.
"""
import json
import os
import sys
import threading
import time
import uuid

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-bg-runs")

from chat import runtime
from chat.db import ChatDB
from chat.event_bus import EventBus
from chat.run_manager import ChatRunManager
from chat.models import Conversation, Message, ChatRun
from chat.runs import ChatRunStatus
from chat.routes import chat_bp

TOKEN = "test-token-bg-runs"
MESSAGES = "/api/chat/conversations/{}/messages"


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeMCPManager:
    def get_all_tools(self, servers):
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


def _new_conv(db, title="New Conversation"):
    conv = Conversation(id=str(uuid.uuid4()), title=title, main_service="svc")
    db.create_conversation(conv)
    return conv


def _patch(monkeypatch, factory):
    def _wrap(*a, **k):
        return factory()
    monkeypatch.setattr(runtime, "stream_chat_completion", _wrap)
    monkeypatch.setattr(runtime, "stream_with_tools", _wrap)


def _delta(content, reasoning=""):
    return ("delta", {"content": content, "reasoning_content": reasoning,
                      "raw": json.dumps({"choices": [{"delta": {"content": content}}]})})


# -- Navigation is not cancellation -------------------------------------


def test_run_completes_after_observer_detaches_midstream(ctx, monkeypatch):
    """The run keeps going (and persists) after its only observer detaches."""
    app, db, manager = ctx
    conv = _new_conv(db, title="t")
    user = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user",
                   content="hi", seq=db.next_seq(conv.id))
    db.add_message(user)
    run = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                     status=ChatRunStatus.QUEUED, user_message_id=user.id))

    midstream = threading.Event()
    released = threading.Event()

    def stub():
        yield _delta("partial ")
        midstream.set()
        released.wait(2)
        yield ("done", {"content": "partial done", "reasoning_content": None})

    _patch(monkeypatch, stub)

    q = manager.subscribe(run.id)
    manager.start(conv, run, is_first=False, first_user_content="hi")
    assert midstream.wait(2), "stub never reached mid-stream"

    # Simulate client disconnect: drop the observer without draining.
    manager.event_bus.unsubscribe(run.id, q)
    released.set()

    assert wait_for(lambda: db.get_chat_run(run.id).status == "completed")
    msgs = db.get_messages(conv.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "partial done"


def test_send_route_disconnect_still_persists_reply(ctx, monkeypatch):
    """HTTP-level: consume one SSE frame, disconnect, run still completes."""
    app, db, manager = ctx
    conv = _new_conv(db, title="t")

    midstream = threading.Event()
    released = threading.Event()

    def stub():
        yield _delta("hello ")
        midstream.set()
        released.wait(2)
        yield ("done", {"content": "hello world", "reasoning_content": None})

    _patch(monkeypatch, stub)

    client = app.test_client()
    resp = client.post(MESSAGES.format(conv.id), headers=_auth(),
                       json={"content": "hi"}, buffered=False)
    chunks = resp.iter_encoded()
    first = next(chunks)  # consume one frame
    assert b"data:" in first
    assert midstream.wait(2)

    resp.close()  # disconnect before the run finishes
    released.set()

    assert wait_for(lambda: len(db.get_messages(conv.id)) == 2)
    assert db.get_messages(conv.id)[1].content == "hello world"
    assert wait_for(lambda: db.get_active_run_for_conversation(conv.id) is None)


# -- One active run per conversation ------------------------------------


def test_second_send_while_run_active_returns_409(ctx):
    app, db, manager = ctx
    conv = _new_conv(db, title="t")
    # An in-flight run already exists for this conversation.
    db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                               status=ChatRunStatus.RUNNING))

    resp = app.test_client().post(MESSAGES.format(conv.id), headers=_auth(),
                                  json={"content": "hi"})
    assert resp.status_code == 409
    assert "active" in resp.get_json()["error"].lower()
    # The rejected send did not persist a user message.
    assert db.get_messages(conv.id) == []


# -- active_run clearing -------------------------------------------------


def test_completed_send_clears_active_run(ctx, monkeypatch):
    app, db, manager = ctx
    conv = _new_conv(db, title="t")

    def stub():
        yield _delta("ok")
        yield ("done", {"content": "ok", "reasoning_content": None})

    _patch(monkeypatch, stub)
    resp = app.test_client().post(MESSAGES.format(conv.id), headers=_auth(),
                                  json={"content": "hi"})
    resp.get_data()  # drain to completion

    assert resp.status_code == 200
    assert db.get_active_run_for_conversation(conv.id) is None
    convs, _ = db.list_conversations()
    assert convs[0].active_run is None
    assert db.get_messages(conv.id)[1].content == "ok"


def test_failed_send_clears_active_run_and_surfaces_error(ctx, monkeypatch):
    app, db, manager = ctx
    conv = _new_conv(db, title="t")

    def stub():
        yield _delta("partial")
        yield ("error", {"message": "model exploded"})

    _patch(monkeypatch, stub)
    resp = app.test_client().post(MESSAGES.format(conv.id), headers=_auth(),
                                  json={"content": "hi"})
    body = resp.get_data(as_text=True)

    assert '"error": "model exploded"' in body  # error metadata surfaced on the stream
    assert db.get_active_run_for_conversation(conv.id) is None
    # Failed run wrote a partial assistant message with accumulated content.
    messages = db.get_messages(conv.id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assistant = messages[1]
    assert assistant.content == "partial"
    assert assistant.error == "model exploded"


# -- Startup recovery ----------------------------------------------------


def test_recover_interrupted_runs_marks_active_failed(tmp_path):
    db = ChatDB(str(tmp_path / "chat.db"))
    conv = _new_conv(db, title="t")
    running = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                         status=ChatRunStatus.RUNNING))
    queued = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                        status=ChatRunStatus.QUEUED))
    done = db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                      status=ChatRunStatus.RUNNING))
    db.complete_chat_run(done.id)  # terminal — must be left alone

    manager = ChatRunManager(db, EventBus())
    try:
        n = manager.recover_interrupted_runs()
    finally:
        manager.shutdown()

    assert n == 2
    for r in (running, queued):
        rec = db.get_chat_run(r.id)
        assert rec.status == "failed"
        assert "Interrupted by dashboard restart" in rec.error
    assert db.get_chat_run(done.id).status == "completed"
    assert db.list_active_runs() == []
