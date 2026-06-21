"""Tests for chat_runs storage (Phase 2 of #58).

No background execution yet — these exercise the DB methods and the
active_run enrichment on conversation payloads. Stub-free; pure SQLite.
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.db import ChatDB
from chat.models import Conversation, Message, ChatRun
from chat.runs import ChatRunStatus


def _conv(db, title="t"):
    conv = Conversation(id=str(uuid.uuid4()), title=title, main_service="svc")
    db.create_conversation(conv)
    return conv


def _user_msg(db, conv):
    msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user",
                  content="hi", seq=db.next_seq(conv.id))
    db.add_message(msg)
    return msg


def _run(conv, status=ChatRunStatus.QUEUED, user_message_id=None):
    return ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                   status=status, user_message_id=user_message_id)


# -- create / get / update ----------------------------------------------


def test_create_get_run():
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _user_msg(db, conv)
    run = db.create_chat_run(_run(conv, ChatRunStatus.QUEUED, user_message_id=msg.id))

    assert run.id is not None
    assert run.status == "queued"
    assert run.user_message_id == msg.id
    assert run.created_at  # DB default stamped
    assert run.started_at is None

    fetched = db.get_chat_run(run.id)
    assert fetched.id == run.id
    assert fetched.conversation_id == conv.id


def test_get_missing_run_returns_none():
    db = ChatDB(":memory:")
    assert db.get_chat_run("nope") is None


def test_create_run_rejects_bad_status():
    db = ChatDB(":memory:")
    conv = _conv(db)
    with pytest.raises(ValueError):
        db.create_chat_run(_run(conv, status="bogus"))


def test_update_status_stamps_started_at():
    db = ChatDB(":memory:")
    conv = _conv(db)
    run = db.create_chat_run(_run(conv, ChatRunStatus.QUEUED))

    updated = db.update_chat_run_status(run.id, ChatRunStatus.RUNNING, active_step="generating")
    assert updated.status == "running"
    assert updated.active_step == "generating"
    assert updated.started_at is not None

    # A second running bump must not move started_at (COALESCE).
    first_started = updated.started_at
    again = db.update_chat_run_status(run.id, ChatRunStatus.RUNNING)
    assert again.started_at == first_started
    # active_step not passed -> preserved, not clobbered.
    assert again.active_step == "generating"


def test_complete_fail_cancel_helpers_stamp_timestamps():
    db = ChatDB(":memory:")
    conv = _conv(db)

    r1 = db.create_chat_run(_run(conv))
    done = db.complete_chat_run(r1.id)
    assert done.status == "completed" and done.completed_at is not None

    r2 = db.create_chat_run(_run(conv))
    failed = db.fail_chat_run(r2.id, "model exploded")
    assert failed.status == "failed" and failed.error == "model exploded"
    assert failed.completed_at is not None

    r3 = db.create_chat_run(_run(conv))
    cancelled = db.cancel_chat_run(r3.id)
    assert cancelled.status == "cancelled" and cancelled.cancelled_at is not None


# -- active-run lookup --------------------------------------------------


def test_active_run_lookup_returns_only_active():
    db = ChatDB(":memory:")
    conv = _conv(db)

    assert db.get_active_run_for_conversation(conv.id) is None

    queued = db.create_chat_run(_run(conv, ChatRunStatus.QUEUED))
    active = db.get_active_run_for_conversation(conv.id)
    assert active.id == queued.id

    db.update_chat_run_status(queued.id, ChatRunStatus.RUNNING)
    assert db.get_active_run_for_conversation(conv.id).id == queued.id


@pytest.mark.parametrize("terminal", [
    ChatRunStatus.COMPLETED, ChatRunStatus.FAILED, ChatRunStatus.CANCELLED,
])
def test_terminal_runs_are_not_active(terminal):
    db = ChatDB(":memory:")
    conv = _conv(db)
    run = db.create_chat_run(_run(conv, ChatRunStatus.RUNNING))
    db.update_chat_run_status(run.id, terminal)

    assert db.get_active_run_for_conversation(conv.id) is None
    assert run.id not in [r.id for r in db.list_active_runs()]


def test_active_run_picks_most_recent():
    db = ChatDB(":memory:")
    conv = _conv(db)
    old = db.create_chat_run(ChatRun(id="aaa-old", conversation_id=conv.id,
                                     status=ChatRunStatus.QUEUED))
    new = db.create_chat_run(ChatRun(id="zzz-new", conversation_id=conv.id,
                                     status=ChatRunStatus.RUNNING))
    # Same created_at second in a fast test; the id tiebreaker keeps it
    # deterministic. Both are active here; lookup returns one, deterministically.
    active = db.get_active_run_for_conversation(conv.id)
    assert active.id in {old.id, new.id}


def test_list_active_runs_spans_conversations():
    db = ChatDB(":memory:")
    c1, c2 = _conv(db), _conv(db)
    db.create_chat_run(_run(c1, ChatRunStatus.QUEUED))
    db.create_chat_run(_run(c2, ChatRunStatus.RUNNING))
    db.create_chat_run(_run(c2, ChatRunStatus.COMPLETED))  # not active

    active = db.list_active_runs()
    assert len(active) == 2
    assert {r.conversation_id for r in active} == {c1.id, c2.id}


# -- conversation payload enrichment ------------------------------------


def test_conversation_list_includes_active_run_null_when_none():
    db = ChatDB(":memory:")
    _conv(db)
    convs, _ = db.list_conversations()
    assert len(convs) == 1
    assert convs[0].active_run is None
    assert convs[0].to_dict()["active_run"] is None


def test_conversation_list_surfaces_active_run_metadata():
    db = ChatDB(":memory:")
    conv = _conv(db)
    run = db.create_chat_run(_run(conv, ChatRunStatus.RUNNING))
    db.update_chat_run_status(run.id, ChatRunStatus.RUNNING, active_step="generating")

    convs, _ = db.list_conversations()
    ar = convs[0].to_dict()["active_run"]
    assert ar == {
        "id": run.id,
        "status": "running",
        "active_step": "generating",
        "started_at": convs[0].active_run["started_at"],
    }
    assert ar["started_at"] is not None
    # Trimmed shape: no error/timestamps beyond started_at.
    assert set(ar.keys()) == {"id", "status", "active_step", "started_at"}


def test_get_conversation_includes_active_run():
    db = ChatDB(":memory:")
    conv = _conv(db)
    db.create_chat_run(_run(conv, ChatRunStatus.QUEUED))
    fetched = db.get_conversation(conv.id)
    assert fetched.active_run is not None
    assert fetched.active_run["status"] == "queued"


def test_completed_run_clears_active_run_in_list():
    db = ChatDB(":memory:")
    conv = _conv(db)
    run = db.create_chat_run(_run(conv, ChatRunStatus.RUNNING))
    db.complete_chat_run(run.id)

    convs, _ = db.list_conversations()
    assert convs[0].active_run is None


# -- deletion cleanup ---------------------------------------------------


def test_deleting_conversation_removes_its_runs():
    db = ChatDB(":memory:")
    conv = _conv(db)
    run = db.create_chat_run(_run(conv, ChatRunStatus.RUNNING))

    assert db.delete_conversation(conv.id) is True
    # Run is gone, and nothing surfaces a broken active-run response.
    assert db.get_chat_run(run.id) is None
    assert db.list_active_runs() == []
    convs, total = db.list_conversations()
    assert total == 0 and convs == []
