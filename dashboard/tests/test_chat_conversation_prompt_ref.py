"""Conversations reference a managed prompt by id (#123).

The stored main_system_prompt is still the copy the run path reads — setting
prompt_id resolves and stores the prompt's content, so old rows and hand
written prompts (prompt_id NULL) are untouched. The id is provenance: it
names the prompt the stored copy came from, which is why an explicit
main_system_prompt in the same body wins and establishes no reference, and
why editing a prompt does not rewrite conversations.
"""
import os
import sqlite3
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-conv-prompt-ref")

from chat.db import ChatDB
from chat.models import Conversation
from chat.routes import chat_bp

TOKEN = "test-token-conv-prompt-ref"
CONVERSATIONS_PATH = "/api/chat/conversations"
PROMPTS_PATH = "/api/chat/prompts"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Chat blueprint on an in-memory DB, settings file pointed at a tmp dir."""
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(tmp_path / "chat_settings.json"))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create_prompt(client, name="Managed", content="You are terse."):
    r = client.post(PROMPTS_PATH, json={"name": name, "content": content}, headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _create_conversation(client, **body):
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "svc-a", **body}, headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# -- DB layer ---------------------------------------------------------------


def test_migration_adds_prompt_id_to_a_pre_existing_database(tmp_path):
    """A pre-feature database gets the column, and its old rows read back NULL."""
    path = str(tmp_path / "chat.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE conversations (
            id                     TEXT PRIMARY KEY,
            title                  TEXT NOT NULL DEFAULT 'New Conversation',
            main_service           TEXT NOT NULL,
            sidekick_service       TEXT,
            main_system_prompt     TEXT NOT NULL DEFAULT '',
            sidekick_system_prompt TEXT NOT NULL DEFAULT '',
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        );
        INSERT INTO conversations (id, main_service, main_system_prompt,
                                   created_at, updated_at)
        VALUES ('old', 'svc-a', 'legacy text', '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z');
    """)
    conn.commit()
    conn.close()

    db = ChatDB(path)
    cols = {r[1] for r in db._get_conn().execute("PRAGMA table_info(conversations)")}
    assert "prompt_id" in cols
    old = db.get_conversation("old")
    assert old.prompt_id is None
    assert old.main_system_prompt == "legacy text"


def test_update_allowlist_accepts_prompt_id():
    db = ChatDB(":memory:")
    db.create_conversation(Conversation(id="c1", title="t", main_service="s"))
    db.create_prompt("p", "managed text")
    prompt = db.list_prompts()[0]

    assert db.update_conversation("c1", prompt_id=prompt.id).prompt_id == prompt.id
    assert db.update_conversation("c1", prompt_id=None).prompt_id is None
    # A key outside the allowlist is still ignored rather than injected.
    db.update_conversation("c1", not_a_column="x")
    assert db.get_conversation("c1").main_service == "s"


def test_fk_triggers_reject_a_dangling_prompt_id():
    db = ChatDB(":memory:")
    with pytest.raises(sqlite3.IntegrityError, match="prompt not found"):
        db.create_conversation(Conversation(
            id="c1", title="t", main_service="s", prompt_id="ghost"))
    db.create_conversation(Conversation(id="c2", title="t", main_service="s"))
    with pytest.raises(sqlite3.IntegrityError, match="prompt not found"):
        db.update_conversation("c2", prompt_id="ghost")


def test_delete_prompt_sets_the_reference_null_and_keeps_the_copy():
    db = ChatDB(":memory:")
    prompt = db.create_prompt("p", "managed text")
    db.create_conversation(Conversation(
        id="c1", title="t", main_service="s",
        main_system_prompt="managed text", prompt_id=prompt.id))
    assert db.delete_prompt(prompt.id) is True
    conv = db.get_conversation("c1")
    assert conv.prompt_id is None
    assert conv.main_system_prompt == "managed text"


# -- create -----------------------------------------------------------------


def test_create_stores_the_reference_and_resolves_the_content(client):
    prompt = _create_prompt(client)
    conv = _create_conversation(client, prompt_id=prompt["id"])
    assert conv["prompt_id"] == prompt["id"]
    assert conv["main_system_prompt"] == "You are terse."


def test_create_with_explicit_text_wins_and_stores_no_reference(client):
    prompt = _create_prompt(client)
    conv = _create_conversation(client, prompt_id=prompt["id"],
                                main_system_prompt="hand written")
    assert conv["prompt_id"] is None
    assert conv["main_system_prompt"] == "hand written"


def test_create_with_non_string_prompt_id_is_rejected(client):
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "svc-a",
                                              "prompt_id": 123}, headers=_auth())
    assert r.status_code == 400
    assert r.get_json()["error"] == "prompt_id must be a string or null"


def test_create_payload_carries_prompt_id_in_the_list_and_single(client):
    prompt = _create_prompt(client)
    created = _create_conversation(client, prompt_id=prompt["id"])
    listed = client.get(CONVERSATIONS_PATH, headers=_auth()).get_json()
    row = next(c for c in listed["conversations"] if c["id"] == created["id"])
    assert row["prompt_id"] == prompt["id"]
    single = client.get(f"{CONVERSATIONS_PATH}/{created['id']}", headers=_auth()).get_json()
    assert single["prompt_id"] == prompt["id"]


# -- update -----------------------------------------------------------------


def test_update_points_an_existing_conversation_at_a_managed_prompt(client):
    """The gap #123 names: today an existing conversation cannot be pointed
    at a managed prompt at all, so this is the whole feature for old rows."""
    prompt = _create_prompt(client, content="fresh managed text")
    conv = _create_conversation(client, main_system_prompt="stale text")
    assert conv["prompt_id"] is None

    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": prompt["id"]}, headers=_auth())
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["prompt_id"] == prompt["id"]
    assert body["main_system_prompt"] == "fresh managed text"


def test_update_with_explicit_text_wins_and_keeps_the_reference(client):
    prompt = _create_prompt(client)
    conv = _create_conversation(client, prompt_id=prompt["id"])
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": prompt["id"], "main_system_prompt": "edited"},
                   headers=_auth())
    body = r.get_json()
    assert body["main_system_prompt"] == "edited"
    # The body carried its own text, so the write establishes no reference —
    # the previous one is kept, not overwritten by a lie.
    assert body["prompt_id"] == prompt["id"]


def test_update_with_null_prompt_id_detaches_and_keeps_the_text(client):
    prompt = _create_prompt(client)
    conv = _create_conversation(client, prompt_id=prompt["id"])
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": None}, headers=_auth())
    body = r.get_json()
    assert body["prompt_id"] is None
    assert body["main_system_prompt"] == "You are terse."


def test_update_with_nonexistent_prompt_id_is_rejected(client):
    conv = _create_conversation(client, main_system_prompt="keep me")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": "ghost"}, headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "Prompt not found"
    # The rejection changed nothing.
    after = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth()).get_json()
    assert after["prompt_id"] is None
    assert after["main_system_prompt"] == "keep me"


def test_update_with_non_string_prompt_id_is_rejected(client):
    conv = _create_conversation(client, main_system_prompt="keep me")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": 7}, headers=_auth())
    assert r.status_code == 400
    assert r.get_json()["error"] == "prompt_id must be a string or null"


def test_deleting_the_prompt_detaches_the_reference_but_keeps_the_text(client):
    prompt = _create_prompt(client)
    conv = _create_conversation(client, prompt_id=prompt["id"])
    r = client.delete(f"{PROMPTS_PATH}/{prompt['id']}", headers=_auth())
    assert r.status_code == 200
    after = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth()).get_json()
    assert after["prompt_id"] is None
    assert after["main_system_prompt"] == "You are terse."


# -- the open question, pinned ----------------------------------------------


def test_editing_a_prompt_does_not_rewrite_conversations(client):
    """Decided in #123: the stored copy wins. Re-pointing is an explicit
    update that pulls the fresh content."""
    prompt = _create_prompt(client, content="v1")
    conv = _create_conversation(client, prompt_id=prompt["id"])

    r = client.put(f"{PROMPTS_PATH}/{prompt['id']}",
                   json={"name": prompt["name"], "content": "v2"}, headers=_auth())
    assert r.status_code == 200
    after = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth()).get_json()
    assert after["prompt_id"] == prompt["id"]
    assert after["main_system_prompt"] == "v1"

    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"prompt_id": prompt["id"]}, headers=_auth())
    body = r.get_json()
    assert body["main_system_prompt"] == "v2"
