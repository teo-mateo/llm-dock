"""Tests for the chat prompt CRUD HTTP API (issue #96).

Covers all six routes: GET /list, POST /create, GET /single, PUT /update,
DELETE, and PATCH /reorder. Each route is exercised for auth gating, happy
path, input validation, and not-found handling.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-chat-prompts")

from chat.db import ChatDB
from chat.routes import chat_bp

TOKEN = "test-token-chat-prompts"
PROMPTS_PATH = "/api/chat/prompts"


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


def _create_prompt(client, name="My Prompt", content="You are helpful."):
    r = client.post(PROMPTS_PATH, json={"name": name, "content": content},
                    headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# -- Auth ---------------------------------------------------------------


def test_prompts_require_auth(client):
    assert client.get(PROMPTS_PATH).status_code == 401
    assert client.post(PROMPTS_PATH, json={"name": "x", "content": "y"}).status_code == 401
    assert client.get(f"{PROMPTS_PATH}/abc").status_code == 401
    assert client.put(f"{PROMPTS_PATH}/abc", json={"name": "x", "content": "y"}).status_code == 401
    assert client.delete(f"{PROMPTS_PATH}/abc").status_code == 401
    assert client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": []}).status_code == 401


# -- GET /list ----------------------------------------------------------


def test_list_prompts_empty(client):
    r = client.get(PROMPTS_PATH, headers=_auth())
    assert r.status_code == 200
    assert r.get_json() == {"prompts": []}


def test_list_prompts_returns_all_ordered(client):
    p1 = _create_prompt(client, name="First", content="c1")
    p2 = _create_prompt(client, name="Second", content="c2")
    p3 = _create_prompt(client, name="Third", content="c3")
    r = client.get(PROMPTS_PATH, headers=_auth())
    body = r.get_json()
    assert len(body["prompts"]) == 3
    ids = [p["id"] for p in body["prompts"]]
    assert ids == [p1["id"], p2["id"], p3["id"]]


def test_list_prompts_reflects_reorder(client):
    p1 = _create_prompt(client, name="First", content="c1")
    p2 = _create_prompt(client, name="Second", content="c2")
    p3 = _create_prompt(client, name="Third", content="c3")
    client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": [p3["id"], p1["id"], p2["id"]]},
                 headers=_auth())
    r = client.get(PROMPTS_PATH, headers=_auth())
    ids = [p["id"] for p in r.get_json()["prompts"]]
    assert ids == [p3["id"], p1["id"], p2["id"]]


# -- POST /create -------------------------------------------------------


def test_create_prompt_returns_201_and_data(client):
    r = client.post(PROMPTS_PATH, json={"name": "Test", "content": "Hello"},
                    headers=_auth())
    assert r.status_code == 201
    body = r.get_json()
    assert body["name"] == "Test"
    assert body["content"] == "Hello"
    assert body["sort_order"] >= 1
    assert body["created_at"]
    assert body["updated_at"]
    assert body["id"]


def test_create_prompt_persists(client):
    created = _create_prompt(client, name="Persisted", content="data")
    fetched = client.get(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.get_json()["name"] == "Persisted"
    assert fetched.get_json()["content"] == "data"


def test_create_prompt_rejects_missing_name(client):
    r = client.post(PROMPTS_PATH, json={"content": "y"}, headers=_auth())
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_prompt_rejects_missing_content(client):
    r = client.post(PROMPTS_PATH, json={"name": "x"}, headers=_auth())
    assert r.status_code == 400
    assert "content" in r.get_json()["error"]


def test_create_prompt_rejects_blank_name(client):
    r = client.post(PROMPTS_PATH, json={"name": "  ", "content": "y"},
                    headers=_auth())
    assert r.status_code == 400


def test_create_prompt_rejects_blank_content(client):
    r = client.post(PROMPTS_PATH, json={"name": "x", "content": "   "},
                    headers=_auth())
    assert r.status_code == 400


def test_create_prompt_rejects_non_string_name(client):
    r = client.post(PROMPTS_PATH, json={"name": 42, "content": "y"},
                    headers=_auth())
    assert r.status_code == 400


def test_create_prompt_rejects_non_string_content(client):
    r = client.post(PROMPTS_PATH, json={"name": "x", "content": 42},
                    headers=_auth())
    assert r.status_code == 400


def test_create_prompt_rejects_non_object_body(client):
    r = client.post(PROMPTS_PATH, json=["not", "a", "dict"], headers=_auth())
    assert r.status_code == 400


def test_create_prompt_rejects_no_body(client):
    r = client.post(PROMPTS_PATH, headers=_auth())
    assert r.status_code == 400


# -- GET /single --------------------------------------------------------


def test_get_prompt_returns_data(client):
    created = _create_prompt(client, name="Get Me", content="content")
    r = client.get(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["id"] == created["id"]
    assert body["name"] == "Get Me"
    assert body["content"] == "content"
    assert body["sort_order"] == created["sort_order"]


def test_get_prompt_not_found_404(client):
    r = client.get(f"{PROMPTS_PATH}/nonexistent-id", headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "Prompt not found"


# -- PUT /update --------------------------------------------------------


def test_update_prompt_returns_200_and_updated_data(client):
    created = _create_prompt(client, name="Original", content="old")
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json={"name": "Updated", "content": "new"}, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "Updated"
    assert body["content"] == "new"
    assert body["id"] == created["id"]


def test_update_prompt_persists(client):
    created = _create_prompt(client, name="Original", content="old")
    client.put(f"{PROMPTS_PATH}/{created['id']}",
               json={"name": "Updated", "content": "new"}, headers=_auth())
    fetched = client.get(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert fetched.get_json()["name"] == "Updated"
    assert fetched.get_json()["content"] == "new"


def test_update_prompt_updates_timestamp(client):
    import time
    created = _create_prompt(client, name="P", content="c")
    original_updated = created["updated_at"]
    time.sleep(1.1)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json={"name": "P2", "content": "c2"}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["updated_at"] != original_updated


def test_update_prompt_not_found_404(client):
    r = client.put(f"{PROMPTS_PATH}/nonexistent-id",
                   json={"name": "x", "content": "y"}, headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "Prompt not found"


def test_update_prompt_rejects_missing_name(client):
    created = _create_prompt(client)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json={"content": "y"}, headers=_auth())
    assert r.status_code == 400


def test_update_prompt_rejects_missing_content(client):
    created = _create_prompt(client)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json={"name": "x"}, headers=_auth())
    assert r.status_code == 400


def test_update_prompt_rejects_blank_name(client):
    created = _create_prompt(client)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json={"name": "  ", "content": "y"}, headers=_auth())
    assert r.status_code == 400


def test_update_prompt_rejects_non_object_body(client):
    created = _create_prompt(client)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}",
                   json=["not", "a", "dict"], headers=_auth())
    assert r.status_code == 400


def test_update_prompt_rejects_no_body(client):
    created = _create_prompt(client)
    r = client.put(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert r.status_code == 400


# -- DELETE -------------------------------------------------------------


def test_delete_prompt_returns_200(client):
    created = _create_prompt(client)
    r = client.delete(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_delete_prompt_removes_it(client):
    created = _create_prompt(client)
    client.delete(f"{PROMPTS_PATH}/{created['id']}", headers=_auth())
    assert client.get(f"{PROMPTS_PATH}/{created['id']}", headers=_auth()).status_code == 404


def test_delete_prompt_not_found_404(client):
    r = client.delete(f"{PROMPTS_PATH}/nonexistent-id", headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "Prompt not found"


def test_delete_prompt_does_not_affect_others(client):
    p1 = _create_prompt(client, name="Keep", content="c1")
    p2 = _create_prompt(client, name="Delete", content="c2")
    client.delete(f"{PROMPTS_PATH}/{p2['id']}", headers=_auth())
    r = client.get(PROMPTS_PATH, headers=_auth())
    ids = [p["id"] for p in r.get_json()["prompts"]]
    assert ids == [p1["id"]]


# -- PATCH /reorder -----------------------------------------------------


def test_reorder_returns_200(client):
    p1 = _create_prompt(client, name="A", content="c1")
    p2 = _create_prompt(client, name="B", content="c2")
    r = client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": [p2["id"], p1["id"]]},
                     headers=_auth())
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_reorder_updates_sort_order(client):
    p1 = _create_prompt(client, name="A", content="c1")
    p2 = _create_prompt(client, name="B", content="c2")
    p3 = _create_prompt(client, name="C", content="c3")
    client.patch(f"{PROMPTS_PATH}/reorder",
                 json={"ids": [p3["id"], p1["id"], p2["id"]]}, headers=_auth())
    r = client.get(PROMPTS_PATH, headers=_auth())
    prompts = {p["id"]: p for p in r.get_json()["prompts"]}
    assert prompts[p3["id"]]["sort_order"] == 0
    assert prompts[p1["id"]]["sort_order"] == 1
    assert prompts[p2["id"]]["sort_order"] == 2


def test_reorder_empty_list(client):
    _create_prompt(client, name="A", content="c")
    r = client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": []}, headers=_auth())
    assert r.status_code == 200


def test_reorder_rejects_missing_ids(client):
    r = client.patch(f"{PROMPTS_PATH}/reorder", json={"foo": "bar"},
                     headers=_auth())
    assert r.status_code == 400
    assert "ids" in r.get_json()["error"]


def test_reorder_rejects_non_list_ids(client):
    r = client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": "not-a-list"},
                     headers=_auth())
    assert r.status_code == 400


def test_reorder_rejects_non_string_ids(client):
    r = client.patch(f"{PROMPTS_PATH}/reorder", json={"ids": [1, 2, 3]},
                     headers=_auth())
    assert r.status_code == 400


def test_reorder_rejects_non_object_body(client):
    r = client.patch(f"{PROMPTS_PATH}/reorder", json=["not", "a", "dict"],
                     headers=_auth())
    assert r.status_code == 400


def test_reorder_rejects_no_body(client):
    r = client.patch(f"{PROMPTS_PATH}/reorder", headers=_auth())
    assert r.status_code == 400
