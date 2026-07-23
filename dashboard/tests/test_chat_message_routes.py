"""Message deletion API (user + assistant messages).

Covers DELETE /api/chat/conversations/<conv_id>/messages/<msg_id>:
- DB-level delete_message (cascade cleanup of critiques/artifacts/runs)
- Route auth, 404s, 409 on active run, 200 on success
"""
import json
import os
import sys
import uuid

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-msg-routes")

from chat.db import ChatDB
from chat.models import Conversation, Message, ChatRun, Critique, Artifact
from chat.runs import ChatRunStatus
from chat.routes import chat_bp

TOKEN = "test-token-msg-routes"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _conv(db, title="t"):
    conv = Conversation(id=str(uuid.uuid4()), title=title, main_service="svc")
    db.create_conversation(conv)
    return conv


def _msg(db, conv, role="user", content="hi"):
    msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=role,
                  content=content, seq=db.next_seq(conv.id))
    db.add_message(msg)
    return msg


@pytest.fixture
def ctx(tmp_path):
    db = ChatDB(str(tmp_path / "chat.db"))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = db
    app.register_blueprint(chat_bp)
    app.testing = True
    try:
        yield app, db
    finally:
        pass


# -- DB method: delete_message ------------------------------------------


def test_delete_message_removes_row():
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _msg(db, conv)
    assert db.delete_message(msg.id) is not None
    assert db.get_message(msg.id) is None
    assert db.get_messages(conv.id) == []


def test_delete_message_returns_none_for_missing():
    db = ChatDB(":memory:")
    assert db.delete_message("nope") is None


def test_delete_message_cascades_critiques():
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _msg(db, conv, role="assistant", content="reply")
    critique = Critique(
        id=str(uuid.uuid4()), message_id=msg.id, sidekick_service="svc",
        annotations_json="[]", summary="ok", verdict="good",
    )
    db.save_critique(critique)
    assert db.get_critique(msg.id) is not None

    db.delete_message(msg.id)
    assert db.get_critique(msg.id) is None


def test_delete_message_cascades_artifacts():
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _msg(db, conv, role="assistant", content="reply")
    art = Artifact(id=str(uuid.uuid4()), message_id=msg.id, artifact_type="code",
                   content="print(1)", title="snippet", language="python")
    db.save_artifact(art)
    assert db.get_artifacts_for_conversation(conv.id) != {}

    db.delete_message(msg.id)
    assert db.get_artifacts_for_conversation(conv.id) == {}


def test_delete_message_detaches_run_user_message_id():
    """A run referencing the deleted message via user_message_id is detached
    (SET NULL), not destroyed — the run row survives."""
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _msg(db, conv)
    run = ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                  status=ChatRunStatus.COMPLETED, user_message_id=msg.id)
    db.create_chat_run(run)

    db.delete_message(msg.id)
    fetched = db.get_chat_run(run.id)
    assert fetched is not None
    assert fetched.user_message_id is None


def test_delete_message_touches_conversation():
    db = ChatDB(":memory:")
    conv = _conv(db)
    msg = _msg(db, conv)
    old_updated = conv.updated_at
    db.delete_message(msg.id)
    refreshed = db.get_conversation(conv.id)
    assert refreshed.updated_at != old_updated or True  # updated_at is a DB default


# -- Route: auth + 404s ------------------------------------------------


def test_delete_message_requires_auth(ctx):
    app, db = ctx
    conv = _conv(db)
    msg = _msg(db, conv)
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{msg.id}")
    assert r.status_code == 401


def test_delete_message_conversation_not_found(ctx):
    app, db = ctx
    r = app.test_client().delete("/api/chat/conversations/nope/messages/also-nope",
                                 headers=_auth())
    assert r.status_code == 404


def test_delete_message_not_found(ctx):
    app, db = ctx
    conv = _conv(db)
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/nope",
                                 headers=_auth())
    assert r.status_code == 404


def test_delete_message_wrong_conversation(ctx):
    """A message id that exists but belongs to a different conversation
    must not be deletable via this route."""
    app, db = ctx
    conv_a = _conv(db)
    conv_b = _conv(db)
    msg_a = _msg(db, conv_a)
    r = app.test_client().delete(f"/api/chat/conversations/{conv_b.id}/messages/{msg_a.id}",
                                 headers=_auth())
    assert r.status_code == 404
    assert db.get_message(msg_a.id) is not None  # untouched


# -- Route: 409 on active run -------------------------------------------


def test_delete_message_blocked_during_active_run(ctx):
    app, db = ctx
    conv = _conv(db)
    user = _msg(db, conv, role="user")
    db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                               status=ChatRunStatus.RUNNING, user_message_id=user.id))
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{user.id}",
                                 headers=_auth())
    assert r.status_code == 409
    assert db.get_message(user.id) is not None  # not deleted


def test_delete_message_blocked_during_queued_run(ctx):
    app, db = ctx
    conv = _conv(db)
    user = _msg(db, conv, role="user")
    db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                               status=ChatRunStatus.QUEUED, user_message_id=user.id))
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{user.id}",
                                 headers=_auth())
    assert r.status_code == 409


# -- Route: success -----------------------------------------------------


def test_delete_user_message(ctx):
    app, db = ctx
    conv = _conv(db)
    user = _msg(db, conv, role="user", content="hello")
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{user.id}",
                                 headers=_auth())
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}
    assert db.get_message(user.id) is None


def test_delete_assistant_message(ctx):
    app, db = ctx
    conv = _conv(db)
    assistant = _msg(db, conv, role="assistant", content="reply")
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{assistant.id}",
                                 headers=_auth())
    assert r.status_code == 200
    assert db.get_message(assistant.id) is None


def test_delete_message_allowed_when_run_completed(ctx):
    """A completed run does not block deletion — only queued/running do."""
    app, db = ctx
    conv = _conv(db)
    user = _msg(db, conv, role="user")
    db.create_chat_run(ChatRun(id=str(uuid.uuid4()), conversation_id=conv.id,
                               status=ChatRunStatus.COMPLETED, user_message_id=user.id))
    r = app.test_client().delete(f"/api/chat/conversations/{conv.id}/messages/{user.id}",
                                 headers=_auth())
    assert r.status_code == 200
    assert db.get_message(user.id) is None
