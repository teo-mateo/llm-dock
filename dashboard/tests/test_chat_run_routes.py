"""Run observation + cancellation APIs (Phase 5 of #58).

Covers GET /api/chat/runs/<id>, GET /api/chat/runs/<id>/stream, and
POST /api/chat/runs/<id>/cancel, plus cooperative mid-stream cancellation and
the observe() DB backstop. File-backed ChatDB (worker thread); streams
monkeypatched.
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

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-run-routes")

from chat import runtime
from chat import run_manager as run_manager_module
from chat.db import ChatDB
from chat.event_bus import EventBus
from chat.run_manager import ChatRunManager
from chat.models import Conversation, Message, ChatRun
from chat.runs import ChatRunStatus
from chat.routes import chat_bp

TOKEN = "test-token-run-routes"


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


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
    app.register_blueprint(chat_bp)
    app.testing = True
    try:
        yield app, db, manager
    finally:
        manager.shutdown()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _conv(db, title="t"):
    conv = Conversation(id=str(uuid.uuid4()), title=title, main_service="svc")
    db.create_conversation(conv)
    return conv


def _run_row(db, conv, status=ChatRunStatus.RUNNING):
    return db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                      status=status))


def _seed_queued(db, conv):
    user = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user",
                   content="hi", seq=db.next_seq(conv.id))
    db.add_message(user)
    return db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                                      status=ChatRunStatus.QUEUED, user_message_id=user.id))


def _delta(content):
    return ("delta", {"content": content, "reasoning_content": "",
                      "raw": json.dumps({"choices": [{"delta": {"content": content}}]})})


def _patch(monkeypatch, factory):
    def _wrap(*a, **k):
        return factory()
    monkeypatch.setattr(runtime, "stream_chat_completion", _wrap)
    monkeypatch.setattr(runtime, "stream_with_tools", _wrap)


# -- Auth ---------------------------------------------------------------


def test_run_routes_require_auth(ctx):
    client = ctx[0].test_client()
    assert client.get("/api/chat/runs/x").status_code == 401
    assert client.get("/api/chat/runs/x/stream").status_code == 401
    assert client.post("/api/chat/runs/x/cancel").status_code == 401


# -- GET run ------------------------------------------------------------


def test_get_run_returns_metadata(ctx):
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    r = app.test_client().get(f"/api/chat/runs/{run.id}", headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["id"] == run.id
    assert body["status"] == "running"
    assert body["conversation_id"] == conv.id


def test_get_run_not_found(ctx):
    r = ctx[0].test_client().get("/api/chat/runs/nope", headers=_auth())
    assert r.status_code == 404


# -- Cancel -------------------------------------------------------------


def test_cancel_active_run_marks_cancelled(ctx):
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    r = app.test_client().post(f"/api/chat/runs/{run.id}/cancel", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["status"] == "cancelled"
    assert db.get_chat_run(run.id).status == "cancelled"
    assert db.get_active_run_for_conversation(conv.id) is None


def test_cancel_completed_run_is_noop(ctx):
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    db.complete_chat_run(run.id)
    r = app.test_client().post(f"/api/chat/runs/{run.id}/cancel", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["status"] == "completed"  # unchanged, harmless no-op


def test_cancel_not_found(ctx):
    r = ctx[0].test_client().post("/api/chat/runs/nope/cancel", headers=_auth())
    assert r.status_code == 404


# -- Cancel active run by conversation (Stop button, Phase 6) ------------


def test_cancel_active_run_by_conversation(ctx):
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run", headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["run"]["id"] == run.id
    assert body["run"]["status"] == "cancelled"
    assert db.get_chat_run(run.id).status == "cancelled"
    assert db.get_active_run_for_conversation(conv.id) is None


def test_cancel_active_run_by_conversation_cancels_queued(ctx):
    # Stop must work before the run starts executing (queued), not only while
    # running — the early-Stop window the cancel-by-conversation path closes.
    app, db, _ = ctx
    conv = _conv(db)
    run = _seed_queued(db, conv)
    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["run"]["id"] == run.id
    assert db.get_chat_run(run.id).status == "cancelled"


def test_cancel_active_run_by_conversation_no_active_run_is_noop(ctx):
    # No active run (e.g. it already finished) → 200 with run: null, no error.
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    db.complete_chat_run(run.id)
    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["run"] is None
    assert db.get_chat_run(run.id).status == "completed"  # untouched


def test_cancel_active_run_by_conversation_expected_run_id_matches(ctx):
    # When the expected run id matches the active run, it cancels normally.
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run",
        json={"expected_run_id": run.id}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["run"]["id"] == run.id
    assert db.get_chat_run(run.id).status == "cancelled"


def test_cancel_active_run_by_conversation_stale_expected_run_id_is_noop(ctx):
    # The iter-4 race: a Stop meant for run A arrives after A finished and a
    # newer run B is active. With expected_run_id=A, B must NOT be cancelled.
    app, db, _ = ctx
    conv = _conv(db)
    run_a = _run_row(db, conv, ChatRunStatus.RUNNING)
    db.complete_chat_run(run_a.id)
    run_b = _run_row(db, conv, ChatRunStatus.RUNNING)  # newer active run
    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run",
        json={"expected_run_id": run_a.id}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["run"] is None
    # B is untouched; A stays completed.
    assert db.get_chat_run(run_b.id).status == "running"
    assert db.get_chat_run(run_a.id).status == "completed"


def test_cancel_active_run_by_conversation_unknown_conversation_404(ctx):
    r = ctx[0].test_client().post(
        "/api/chat/conversations/nope/cancel-active-run", headers=_auth())
    assert r.status_code == 404


def test_cancel_active_run_by_conversation_requires_auth(ctx):
    r = ctx[0].test_client().post("/api/chat/conversations/x/cancel-active-run")
    assert r.status_code == 401


def test_cancel_active_run_by_conversation_stops_run_midstream(ctx, monkeypatch):
    """Cancel-by-conversation during streaming stops the model and writes no
    assistant message — same cooperative cancellation as the run-id path, but
    targeted without the client ever knowing the run id."""
    app, db, manager = ctx
    conv = _conv(db)
    run = _seed_queued(db, conv)

    midstream = threading.Event()

    def stub():
        for i in range(100000):
            yield _delta(f"t{i}")
            if i == 2:
                midstream.set()
            time.sleep(0.002)
        yield ("done", {"content": "should not finish", "reasoning_content": None})

    _patch(monkeypatch, stub)
    manager.start(conv, run, is_first=False, first_user_content="hi")
    assert midstream.wait(2), "stream never reached mid-flight"

    r = app.test_client().post(
        f"/api/chat/conversations/{conv.id}/cancel-active-run", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["run"]["id"] == run.id

    assert wait_for(lambda: db.get_chat_run(run.id).status == "cancelled")
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]  # no assistant


def test_cancel_stops_run_midstream(ctx, monkeypatch):
    """A cancel during streaming stops the model and writes no assistant
    message (cooperative cancellation)."""
    app, db, manager = ctx
    conv = _conv(db)
    run = _seed_queued(db, conv)

    midstream = threading.Event()

    def stub():
        for i in range(100000):
            yield _delta(f"t{i}")
            if i == 2:
                midstream.set()
            time.sleep(0.002)
        yield ("done", {"content": "should not finish", "reasoning_content": None})

    _patch(monkeypatch, stub)
    manager.start(conv, run, is_first=False, first_user_content="hi")
    assert midstream.wait(2), "stream never reached mid-flight"

    manager.request_cancel(run.id)

    assert wait_for(lambda: db.get_chat_run(run.id).status == "cancelled")
    assert [m.role for m in db.get_messages(conv.id)] == ["user"]  # no assistant


# -- Stream -------------------------------------------------------------


def test_stream_terminal_run_emits_status_and_closes(ctx):
    app, db, _ = ctx
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)
    db.fail_chat_run(run.id, "boom")

    r = app.test_client().get(f"/api/chat/runs/{run.id}/stream", headers=_auth())
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '"type": "run_status"' in body
    assert '"status": "failed"' in body
    assert '"error": "boom"' in body


def test_stream_run_not_found(ctx):
    r = ctx[0].test_client().get("/api/chat/runs/nope/stream", headers=_auth())
    assert r.status_code == 404


def test_observe_backstop_closes_when_run_goes_terminal(ctx, monkeypatch):
    """A reattached observer that never receives STREAM_END still closes once
    the run is terminal in the DB (the heartbeat-path backstop)."""
    app, db, manager = ctx
    monkeypatch.setattr(run_manager_module, "HEARTBEAT_INTERVAL_S", 0.02)
    conv = _conv(db)
    run = _run_row(db, conv, ChatRunStatus.RUNNING)  # active in DB, no worker

    q = manager.subscribe(run.id)
    gen = manager.observe(run.id, q)

    started = next(gen)  # synthetic run_started always comes first
    assert "run_started" in started and run.id in started
    first = next(gen)  # active, no events -> heartbeat
    assert "heartbeat" in first

    db.complete_chat_run(run.id)
    nxt = next(gen)  # backstop detects terminal
    assert "run_status" in nxt and "completed" in nxt
    with pytest.raises(StopIteration):
        next(gen)


def test_run_started_emitted_first_even_when_workers_saturated(tmp_path, monkeypatch):
    """run_started reaches the client immediately even if the run's worker is
    still queued behind a saturated pool (the observer synthesizes it)."""
    db = ChatDB(str(tmp_path / "chat.db"))
    manager = ChatRunManager(db, EventBus(), max_workers=1)
    try:
        block = threading.Event()

        def stub():
            block.wait(2)
            yield ("done", {"content": "x", "reasoning_content": None})

        monkeypatch.setattr(runtime, "stream_chat_completion", lambda *a, **k: stub())
        monkeypatch.setattr(runtime, "stream_with_tools", lambda *a, **k: stub())

        # Occupy the single worker with run A (different conversation).
        conv_a = _conv(db, "a")
        run_a = _seed_queued(db, conv_a)
        manager.start(conv_a, run_a, is_first=False, first_user_content="a")

        # Run B is queued behind A; its worker hasn't started.
        conv_b = _conv(db, "b")
        run_b = _seed_queued(db, conv_b)
        q = manager.subscribe(run_b.id)
        manager.start(conv_b, run_b, is_first=False, first_user_content="b")

        gen = manager.observe(run_b.id, q)
        first = next(gen)  # must be run_started, NOT a heartbeat
        assert "run_started" in first and run_b.id in first
    finally:
        block.set()
        manager.shutdown()
