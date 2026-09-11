"""Per-conversation reasoning level: persistence, write-time guard, run-time guard (R4, R7).

Two enforcement points by design. The conversation write paths reject a level
the service does not declare, so a stored value is always one that was legal
when written. Run creation re-checks it, because between those two moments the
ladder can be edited or the model swapped — and nothing undeclared may reach
the wire. The stored column is never rewritten by the run-time check: the drop
belongs to one run, so switching the model back restores the user's choice.
"""
import os
import sqlite3
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-rl-chat")

from chat.db import ChatDB
from chat.models import Conversation
from chat.routes import chat_bp

TOKEN = "test-token-rl-chat"
CONVERSATIONS_PATH = "/api/chat/conversations"

# Two services with different ladders: what one offers and the other does not
# is the substance of R7.
LEVELS = {
    "llamacpp-a": "off,low,medium,xhigh",
    "vllm-b": "off,minimal,max",
}


@pytest.fixture
def client(monkeypatch):
    """Chat blueprint on an in-memory DB, with service levels stubbed.

    `_service_reasoning_levels` is the only seam that touches Docker; stubbing
    it keeps this file about the column and its guards. Its own test patches
    one level lower, at get_docker_services.
    """
    import chat.routes as routes

    monkeypatch.setattr(routes, "_service_reasoning_levels",
                        lambda svc, _levels=LEVELS: _parse(_levels.get(svc)))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _parse(raw):
    import reasoning_levels as rl
    return rl.parse_levels(raw)


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create(client, **extra):
    body = {"main_service": "llamacpp-a"}
    body.update(extra)
    r = client.post(CONVERSATIONS_PATH, json=body, headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# -- storage (R4) ---------------------------------------------------------


def test_new_conversation_without_a_level_is_null(client):
    conv = _create(client)
    assert conv["reasoning_level"] is None


def test_level_is_stored_and_returned_on_reload(client):
    conv = _create(client, reasoning_level="medium")
    assert conv["reasoning_level"] == "medium"
    r = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth())
    assert r.get_json()["reasoning_level"] == "medium"


def test_level_survives_a_restart(tmp_path):
    """Real storage, not run state: a fresh ChatDB on the same file returns it."""
    path = str(tmp_path / "chat.db")
    db = ChatDB(path)
    db.create_conversation(Conversation(id="c1", title="t", main_service="llamacpp-a",
                                        reasoning_level="xhigh"))
    assert ChatDB(path).get_conversation("c1").reasoning_level == "xhigh"


def test_migration_adds_the_column_to_a_pre_existing_database(tmp_path):
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
        INSERT INTO conversations (id, main_service, created_at, updated_at)
        VALUES ('old', 'llamacpp-a', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
    """)
    conn.commit()
    conn.close()

    db = ChatDB(path)
    cols = {r[1] for r in db._get_conn().execute("PRAGMA table_info(conversations)")}
    assert "reasoning_level" in cols
    assert db.get_conversation("old").reasoning_level is None


def test_update_conversation_accepts_the_column_in_the_allowlist():
    db = ChatDB(":memory:")
    db.create_conversation(Conversation(id="c1", title="t", main_service="s"))
    assert db.update_conversation("c1", reasoning_level="low").reasoning_level == "low"
    assert db.update_conversation("c1", reasoning_level=None).reasoning_level is None
    # A key outside the allowlist is still ignored rather than injected.
    db.update_conversation("c1", not_a_column="x")
    assert db.get_conversation("c1").main_service == "s"


# -- write-time guard (R7) ------------------------------------------------


def test_level_offered_by_the_service_is_accepted(client):
    assert _create(client, reasoning_level="off")["reasoning_level"] == "off"


def test_level_not_offered_is_rejected_naming_service_and_ladder(client):
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "llamacpp-a",
                                             "reasoning_level": "minimal"}, headers=_auth())
    assert r.status_code == 400
    body = r.get_json()
    msg = body["error"]
    assert "minimal" in msg and "llamacpp-a" in msg
    assert "off,low,medium,xhigh" in msg
    # The create-retry must key off this code, not prose: a 500 can arrive after
    # the first create succeeded, and retrying that duplicates a conversation.
    assert body["code"] == "invalid_reasoning_level"


def test_put_level_rejection_carries_the_same_code(client):
    conv = _create(client, reasoning_level="low")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}", json={"reasoning_level": "ultra"},
                   headers=_auth())
    assert r.status_code == 400
    assert r.get_json()["code"] == "invalid_reasoning_level"


def test_level_offered_only_by_another_service_is_rejected(client):
    # "minimal" exists on vllm-b, not on the chosen llamacpp-a.
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "vllm-b",
                                             "reasoning_level": "low"}, headers=_auth())
    assert r.status_code == 400
    assert "low" in r.get_json()["error"]


def test_service_with_no_declaration_rejects_any_level(client, monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_reasoning_levels", lambda svc: [])
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "llamacpp-a",
                                             "reasoning_level": "low"}, headers=_auth())
    assert r.status_code == 400
    assert "none" in r.get_json()["error"]


@pytest.mark.parametrize("value", [5, True, ["low"], " low"])
def test_non_string_level_is_rejected(client, value):
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "llamacpp-a",
                                             "reasoning_level": value}, headers=_auth())
    assert r.status_code == 400


def test_explicit_null_is_accepted_everywhere(client):
    assert _create(client, reasoning_level=None)["reasoning_level"] is None


def test_openrouter_conversation_cannot_carry_a_level(client, monkeypatch):
    # No ladder, no level: the shortlist entry carries none, so nothing is legal.
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "openrouter:deepseek/r1",
                                             "reasoning_level": "low"}, headers=_auth())
    assert r.status_code == 400


def test_openrouter_conversation_carries_a_level_its_ladder_offers(client, monkeypatch):
    # The ladder a shortlist entry carries stands in for a service declaration, so the
    # same guard applies to it rather than a blanket refusal.
    import chat.routes as routes

    monkeypatch.setattr(routes, "_service_reasoning_levels",
                        lambda svc: _parse("off,low,high") if svc == "openrouter:x" else [])
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "openrouter:x",
                                             "reasoning_level": "low"}, headers=_auth())
    assert r.status_code == 201


def test_openrouter_conversation_rejects_a_level_outside_its_ladder(client, monkeypatch):
    import chat.routes as routes

    monkeypatch.setattr(routes, "_service_reasoning_levels",
                        lambda svc: _parse("off,low") if svc == "openrouter:x" else [])
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "openrouter:x",
                                             "reasoning_level": "xhigh"}, headers=_auth())
    assert r.status_code == 400
    assert r.get_json()["code"] == "invalid_reasoning_level"


def test_put_changes_and_clears_the_level(client):
    conv = _create(client, reasoning_level="low")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}", json={"reasoning_level": "off"},
                   headers=_auth())
    assert r.status_code == 200 and r.get_json()["reasoning_level"] == "off"
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}", json={"reasoning_level": None},
                   headers=_auth())
    assert r.status_code == 200 and r.get_json()["reasoning_level"] is None


def test_put_rejects_a_level_the_new_service_does_not_offer(client):
    """A PUT that switches model and level together is judged against the model
    the conversation ends up on, not the one it started on."""
    conv = _create(client, reasoning_level="low")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"main_service": "vllm-b", "reasoning_level": "low"}, headers=_auth())
    assert r.status_code == 400
    assert "vllm-b" in r.get_json()["error"]

    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"main_service": "vllm-b", "reasoning_level": "minimal"}, headers=_auth())
    assert r.status_code == 200 and r.get_json()["reasoning_level"] == "minimal"


def test_rejected_put_leaves_the_stored_level_untouched(client):
    conv = _create(client, reasoning_level="medium")
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}", json={"reasoning_level": "ultra"},
                   headers=_auth())
    assert r.status_code == 400
    r = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth())
    assert r.get_json()["reasoning_level"] == "medium"


def test_list_payload_carries_the_level(client):
    _create(client, reasoning_level="low")
    r = client.get(f"{CONVERSATIONS_PATH}?limit=10", headers=_auth())
    assert r.get_json()["conversations"][0]["reasoning_level"] == "low"


# -- run-time guard ------------------------------------------------------


def _conv(main_service, level):
    return Conversation(id="c", title="t", main_service=main_service, reasoning_level=level)


def test_run_keeps_a_level_the_service_still_offers(monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_reasoning_levels", lambda svc: _parse(LEVELS.get(svc)))
    assert routes._effective_reasoning_level(_conv("llamacpp-a", "low")) == ("low", None)


def test_run_drops_a_level_the_service_lost_and_says_so(monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_reasoning_levels", lambda svc: _parse(LEVELS.get(svc)))
    level, note = routes._effective_reasoning_level(_conv("vllm-b", "low"))
    assert level is None
    assert "low" in note and "ignored" in note


def test_run_drops_a_level_when_the_service_declares_nothing_now(monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_reasoning_levels", lambda svc: [])
    assert routes._effective_reasoning_level(_conv("llamacpp-a", "off"))[0] is None


def test_run_without_a_level_produces_no_note_and_no_value(monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_reasoning_levels", lambda svc: _parse(LEVELS.get(svc)))
    assert routes._effective_reasoning_level(_conv("llamacpp-a", None)) == (None, None)


def test_run_started_frame_reports_the_resolved_level(client, monkeypatch):
    """The UI must be able to tell "no level" from "your level was dropped", so
    the run's resolved level rides the first SSE frame."""
    calls = {}

    class _Mgr:
        def subscribe(self, run_id):
            return object()

        def start(self, conv, run, **kwargs):
            calls["start"] = kwargs

        def observe(self, run_id, q, run_started_extra=None):
            calls["observe_extra"] = run_started_extra
            return iter([b""])

    import chat.routes as routes
    monkeypatch.setattr(routes, "_get_run_manager", lambda: _Mgr())
    monkeypatch.setattr(routes, "_effective_reasoning_level",
                        lambda conv: (None, "Reasoning level 'low' is not offered by this model and was ignored"))

    conv = _create(client, reasoning_level="low")
    r = client.post(f"{CONVERSATIONS_PATH}/{conv['id']}/messages", json={"content": "hi"},
                    headers=_auth())
    assert r.status_code == 200
    assert calls["start"]["reasoning_level"] is None
    assert calls["observe_extra"]["reasoning_level"] is None
    assert "not offered" in calls["observe_extra"]["reasoning_level_note"]


def test_run_started_frame_carries_the_level_when_it_holds(client, monkeypatch):
    calls = {}

    class _Mgr:
        def subscribe(self, run_id):
            return object()

        def start(self, conv, run, **kwargs):
            calls["start"] = kwargs

        def observe(self, run_id, q, run_started_extra=None):
            calls["observe_extra"] = run_started_extra
            return iter([b""])

    import chat.routes as routes
    monkeypatch.setattr(routes, "_get_run_manager", lambda: _Mgr())

    conv = _create(client, reasoning_level="medium")
    r = client.post(f"{CONVERSATIONS_PATH}/{conv['id']}/messages", json={"content": "hi"},
                    headers=_auth())
    assert r.status_code == 200
    # What the worker was told and what the client was told are the same value.
    assert calls["start"]["reasoning_level"] == "medium"
    assert calls["observe_extra"] == {"reasoning_level": "medium"}
