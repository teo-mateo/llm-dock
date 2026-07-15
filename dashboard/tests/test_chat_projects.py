"""Tests for chat projects: CRUD API and conversation membership.

Projects are lightweight folders for conversations. Deleting a project
detaches its conversations (they become unfiled) rather than deleting them.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-chat-projects")

from chat.db import ChatDB
from chat.routes import chat_bp

TOKEN = "test-token-chat-projects"
PROJECTS_PATH = "/api/chat/projects"
CONVERSATIONS_PATH = "/api/chat/conversations"


@pytest.fixture
def client():
    """Minimal Flask app exposing the chat blueprint with an in-memory DB."""
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create_project(client, name="My Project", **extra):
    r = client.post(PROJECTS_PATH, json={"name": name, **extra}, headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _create_conversation(client, **extra):
    r = client.post(CONVERSATIONS_PATH, json={"main_service": "svc", **extra},
                    headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# -- Auth ---------------------------------------------------------------


def test_projects_require_auth(client):
    assert client.get(PROJECTS_PATH).status_code == 401
    assert client.post(PROJECTS_PATH, json={"name": "x"}).status_code == 401
    assert client.put(f"{PROJECTS_PATH}/abc", json={"name": "x"}).status_code == 401
    assert client.delete(f"{PROJECTS_PATH}/abc").status_code == 401


# -- CRUD ---------------------------------------------------------------


def test_create_and_get_project(client):
    p = _create_project(client, name="Research", description="LLM stuff")
    assert p["name"] == "Research"
    assert p["description"] == "LLM stuff"
    assert p["conversation_count"] == 0
    assert p["created_at"] and p["updated_at"]

    r = client.get(f"{PROJECTS_PATH}/{p['id']}", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["name"] == "Research"


def test_create_project_trims_name(client):
    p = _create_project(client, name="  padded  ")
    assert p["name"] == "padded"


def test_create_project_rejects_blank_name(client):
    for bad in [{}, {"name": ""}, {"name": "   "}, {"name": 42}]:
        r = client.post(PROJECTS_PATH, json=bad, headers=_auth())
        assert r.status_code == 400


def test_create_project_rejects_non_object_body(client):
    r = client.post(PROJECTS_PATH, json=["not", "a", "dict"], headers=_auth())
    assert r.status_code == 400


def test_create_project_rejects_non_string_description(client):
    r = client.post(PROJECTS_PATH, json={"name": "x", "description": 7},
                    headers=_auth())
    assert r.status_code == 400


def test_list_projects_sorted_by_name(client):
    _create_project(client, name="zebra")
    _create_project(client, name="Alpha")
    _create_project(client, name="beta")
    r = client.get(PROJECTS_PATH, headers=_auth())
    names = [p["name"] for p in r.get_json()["projects"]]
    assert names == ["Alpha", "beta", "zebra"]


def test_update_project(client):
    p = _create_project(client)
    r = client.put(f"{PROJECTS_PATH}/{p['id']}",
                   json={"name": "Renamed", "description": "new desc"},
                   headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "Renamed"
    assert body["description"] == "new desc"


def test_update_project_rejects_blank_name(client):
    p = _create_project(client)
    r = client.put(f"{PROJECTS_PATH}/{p['id']}", json={"name": "  "},
                   headers=_auth())
    assert r.status_code == 400


def test_update_missing_project_404(client):
    r = client.put(f"{PROJECTS_PATH}/nope", json={"name": "x"}, headers=_auth())
    assert r.status_code == 404


def test_update_project_deleted_between_check_and_write_404(client, monkeypatch):
    """Two-tab rename/delete race: the route's existence check passes but
    the row vanishes before the update — must be a JSON 404, not a 500."""
    from chat.db import ChatDB
    p = _create_project(client)
    real_update = ChatDB.update_project

    def racing_update(self, project_id, **kwargs):
        # The concurrent delete wins just before the update runs.
        self.delete_project(project_id)
        return real_update(self, project_id, **kwargs)

    monkeypatch.setattr(ChatDB, "update_project", racing_update)
    r = client.put(f"{PROJECTS_PATH}/{p['id']}", json={"name": "renamed"},
                   headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "Project not found"


def test_get_missing_project_404(client):
    assert client.get(f"{PROJECTS_PATH}/nope", headers=_auth()).status_code == 404


def test_delete_project(client):
    p = _create_project(client)
    r = client.delete(f"{PROJECTS_PATH}/{p['id']}", headers=_auth())
    assert r.status_code == 200
    assert client.get(f"{PROJECTS_PATH}/{p['id']}", headers=_auth()).status_code == 404


def test_delete_missing_project_404(client):
    assert client.delete(f"{PROJECTS_PATH}/nope", headers=_auth()).status_code == 404


# -- Conversation membership ---------------------------------------------


def test_create_conversation_in_project(client):
    p = _create_project(client)
    conv = _create_conversation(client, project_id=p["id"])
    assert conv["project_id"] == p["id"]

    # Reflected in the project's conversation_count
    r = client.get(f"{PROJECTS_PATH}/{p['id']}", headers=_auth())
    assert r.get_json()["conversation_count"] == 1


def test_create_conversation_unknown_project_400(client):
    r = client.post(CONVERSATIONS_PATH,
                    json={"main_service": "svc", "project_id": "nope"},
                    headers=_auth())
    assert r.status_code == 400


def test_create_conversation_without_project(client):
    conv = _create_conversation(client)
    assert conv["project_id"] is None


def test_move_conversation_into_and_out_of_project(client):
    p = _create_project(client)
    conv = _create_conversation(client)

    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"project_id": p["id"]}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["project_id"] == p["id"]

    # Detach with explicit null
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"project_id": None}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["project_id"] is None


def test_move_conversation_to_unknown_project_400(client):
    conv = _create_conversation(client)
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"project_id": "nope"}, headers=_auth())
    assert r.status_code == 400


def test_delete_project_detaches_conversations(client):
    p = _create_project(client)
    conv = _create_conversation(client, project_id=p["id"])

    r = client.delete(f"{PROJECTS_PATH}/{p['id']}", headers=_auth())
    assert r.status_code == 200

    # Conversation survives, unfiled
    r = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["project_id"] is None


def test_conversation_list_carries_project_id(client):
    p = _create_project(client)
    _create_conversation(client, project_id=p["id"])
    _create_conversation(client)
    r = client.get(CONVERSATIONS_PATH, headers=_auth())
    convs = r.get_json()["conversations"]
    assert {c["project_id"] for c in convs} == {p["id"], None}


def test_create_conversation_non_string_project_id_400(client):
    for bad in [{"x": 1}, ["x"], 42, True]:
        r = client.post(CONVERSATIONS_PATH,
                        json={"main_service": "svc", "project_id": bad},
                        headers=_auth())
        assert r.status_code == 400, bad


def test_update_conversation_non_string_project_id_400(client):
    conv = _create_conversation(client)
    for bad in [{"x": 1}, ["x"], 42, True]:
        r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                       json={"project_id": bad}, headers=_auth())
        assert r.status_code == 400, bad


def test_spinoff_cannot_be_created_with_project(client):
    p = _create_project(client)
    parent = _create_conversation(client, project_id=p["id"])
    r = client.post(CONVERSATIONS_PATH,
                    json={"main_service": "svc",
                          "parent_conversation_id": parent["id"],
                          "project_id": p["id"]},
                    headers=_auth())
    assert r.status_code == 400
    assert "inherit" in r.get_json()["error"]


def test_spinoff_cannot_be_moved_into_project(client):
    p = _create_project(client)
    parent = _create_conversation(client)
    spinoff = _create_conversation(client, parent_conversation_id=parent["id"])
    r = client.put(f"{CONVERSATIONS_PATH}/{spinoff['id']}",
                   json={"project_id": p["id"]}, headers=_auth())
    assert r.status_code == 400
    assert "inherit" in r.get_json()["error"]


def test_db_trigger_rejects_orphan_project_reference():
    """The referential triggers close the validate-then-write race: a
    write carrying a project_id whose project no longer exists must fail
    at the DB layer, not persist an orphan."""
    import sqlite3
    import pytest as _pytest
    from chat.db import ChatDB
    from chat.models import Conversation, Project

    db = ChatDB(":memory:")
    p = db.create_project(Project(id="p1", name="p"))
    conv = db.create_conversation(Conversation(id="c1", title="t", main_service="svc"))

    db.delete_project(p.id)

    # Update path: moving into the now-deleted project must abort.
    with _pytest.raises(sqlite3.IntegrityError):
        db.update_conversation(conv.id, project_id="p1")
    assert db.get_conversation(conv.id).project_id is None

    # Insert path: creating directly into the deleted project must abort.
    with _pytest.raises(sqlite3.IntegrityError):
        db.create_conversation(
            Conversation(id="c2", title="t", main_service="svc", project_id="p1"))
    assert db.get_conversation("c2") is None


def test_list_projects_counts(client):
    p1 = _create_project(client, name="one")
    p2 = _create_project(client, name="two")
    _create_conversation(client, project_id=p1["id"])
    _create_conversation(client, project_id=p1["id"])
    r = client.get(PROJECTS_PATH, headers=_auth())
    counts = {p["id"]: p["conversation_count"] for p in r.get_json()["projects"]}
    assert counts == {p1["id"]: 2, p2["id"]: 0}
