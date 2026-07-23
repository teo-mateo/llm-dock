"""Tests for the editable-default-prompt HTTP API.

These endpoints sit alongside the rest of the chat blueprint. The settings
endpoints themselves need no chat DB, but the conversation-creation
integration tests do, so the fixture wires an in-memory ChatDB into the
app config. No MCP manager or subprocess infra is needed.
"""
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure require_auth has a value to compare against. Some modules read
# this from config at import time.
os.environ.setdefault("DASHBOARD_TOKEN", "test-token-chat-settings")

from chat import settings_store
from chat.constants import DEFAULT_MAIN_SYSTEM_PROMPT
from chat.db import ChatDB
from chat.routes import chat_bp

TOKEN = "test-token-chat-settings"
SETTINGS_PATH = "/api/chat/settings/main-system-prompt"
CONVERSATIONS_PATH = "/api/chat/conversations"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Minimal Flask app exposing the chat blueprint with an in-memory DB."""
    settings_file = tmp_path / "chat_settings.json"
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(settings_file))

    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


# -- Auth ---------------------------------------------------------------


def test_get_requires_auth(client):
    r = client.get(SETTINGS_PATH)
    assert r.status_code == 401


def test_put_requires_auth(client):
    r = client.put(SETTINGS_PATH, json={"content": "x"})
    assert r.status_code == 401


def test_delete_requires_auth(client):
    r = client.delete(SETTINGS_PATH)
    assert r.status_code == 401


# -- GET ----------------------------------------------------------------


def test_get_fresh_returns_builtin_uncustomized(client):
    r = client.get(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == DEFAULT_MAIN_SYSTEM_PROMPT
    assert body["builtin"] == DEFAULT_MAIN_SYSTEM_PROMPT
    assert body["customized"] is False


# -- PUT ----------------------------------------------------------------


def test_put_persists_and_marks_customized(client):
    new_prompt = "Be terse. Answer the question. No preamble."
    r = client.put(SETTINGS_PATH, json={"content": new_prompt}, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == new_prompt
    assert body["builtin"] == DEFAULT_MAIN_SYSTEM_PROMPT
    assert body["customized"] is True
    # Survives a GET on a fresh request (i.e., it landed on disk).
    r = client.get(SETTINGS_PATH, headers=_auth())
    assert r.get_json()["current"] == new_prompt


@pytest.mark.parametrize(
    "body, expected_msg_substring",
    [
        ({}, "body must be"),
        ({"content": 42}, "body must be"),
        ({"content": None}, "body must be"),
        ({"content": ""}, "empty"),
        ({"content": "   \n  "}, "empty"),
    ],
)
def test_put_rejects_invalid_payload(client, body, expected_msg_substring):
    r = client.put(SETTINGS_PATH, json=body, headers=_auth())
    assert r.status_code == 400
    assert expected_msg_substring in r.get_json()["error"]
    # No customization should have been recorded.
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["customized"] is False


def test_put_with_no_body(client):
    """A missing JSON body must be a 400, not a 500."""
    r = client.put(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 400


@pytest.mark.parametrize("raw_body", ["[1]", '"x"', "123", "true", "null"])
def test_put_rejects_non_object_json_body(client, raw_body):
    """A valid-JSON but non-object body must 400, not 500.

    request.get_json(silent=True) returns the parsed value as-is, so a
    bare list/string/number would reach .get() and raise AttributeError
    without an isinstance guard.
    """
    r = client.put(
        SETTINGS_PATH,
        data=raw_body,
        content_type="application/json",
        headers=_auth(),
    )
    assert r.status_code == 400, f"body {raw_body!r} should 400, got {r.status_code}"
    assert "body must be" in r.get_json()["error"]
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["customized"] is False


# -- DELETE -------------------------------------------------------------


def test_delete_reverts_to_builtin(client):
    client.put(SETTINGS_PATH, json={"content": "custom"}, headers=_auth())
    assert (
        client.get(SETTINGS_PATH, headers=_auth()).get_json()["customized"] is True
    )
    r = client.delete(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == DEFAULT_MAIN_SYSTEM_PROMPT
    assert body["customized"] is False


def test_delete_when_no_customization_is_noop(client):
    r = client.delete(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["customized"] is False
    assert body["current"] == DEFAULT_MAIN_SYSTEM_PROMPT


# -- Regression for acceptance criterion #2 -----------------------------


def test_builtin_prompt_has_no_tool_specific_guidance():
    """The default prompt must NOT mention any specific tool category.

    Acceptance criterion #2: "A new conversation created with no MCP
    servers enabled has a system prompt with no mention of web search,
    web fetch, or other tool-specific behavior." The augmentation step
    in routes._stream_response only appends tool_hints when MCP servers
    are enabled — so this guarantee reduces to "the built-in baseline
    is clean".
    """
    # Words and phrases that would indicate tool-specific guidance has
    # leaked back into the baseline. We compare case-insensitively. The
    # list mirrors the categories called out in issue #23.
    banned = [
        "web search", "web_search", "websearch",
        "web fetch", "web_fetch", "fetch_url",
        "sympy", "schemdraw", "render_html",
        "search→fetch", "search → fetch",
        "403", "404",  # specific HTTP statuses mentioned in old guidance
        "citation",
        "source quality",
    ]
    lowered = DEFAULT_MAIN_SYSTEM_PROMPT.lower()
    leaked = [needle for needle in banned if needle.lower() in lowered]
    assert leaked == [], (
        "Tool-specific guidance leaked back into the default prompt: "
        f"{leaked}. Move it into the relevant MCP server's tool_hint."
    )


def test_get_after_put_is_a_consistent_snapshot(client):
    """A read after a write must observe the write — basic store sanity."""
    client.put(SETTINGS_PATH, json={"content": "A"}, headers=_auth())
    body = client.get(SETTINGS_PATH, headers=_auth()).get_json()
    assert body["current"] == "A"
    client.put(SETTINGS_PATH, json={"content": "B"}, headers=_auth())
    body = client.get(SETTINGS_PATH, headers=_auth()).get_json()
    assert body["current"] == "B"


# -- Integration: create_conversation system-prompt resolution ----------


def test_new_conversation_defaults_to_empty_string(client):
    """POST /conversations with no prompt_id or main_system_prompt defaults
    to an empty string — the old global-default fallback is gone."""
    client.put(SETTINGS_PATH, json={"content": "global default"}, headers=_auth())
    r = client.post(
        CONVERSATIONS_PATH, json={"main_service": "svc-a"}, headers=_auth()
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == ""


def test_new_conversation_defaults_to_empty_string_no_customization(client):
    """With no global customization at all, the default is still ""."""
    r = client.post(
        CONVERSATIONS_PATH, json={"main_service": "svc-a"}, headers=_auth()
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == ""


def test_explicit_main_system_prompt_takes_precedence(client):
    """An explicit main_system_prompt in the request body wins outright."""
    r = client.post(
        CONVERSATIONS_PATH,
        json={"main_service": "svc-a", "main_system_prompt": "explicit override"},
        headers=_auth(),
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == "explicit override"


def test_explicit_empty_prompt_is_honored_not_replaced(client):
    """An explicit empty-string prompt is a deliberate choice, not 'unset'.

    create_conversation branches on key presence, so passing
    main_system_prompt="" must store "" rather than silently substituting
    the global default.
    """
    client.put(SETTINGS_PATH, json={"content": "global default"}, headers=_auth())
    r = client.post(
        CONVERSATIONS_PATH,
        json={"main_service": "svc-a", "main_system_prompt": ""},
        headers=_auth(),
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == ""


def test_new_conversation_with_prompt_id(client):
    """A prompt_id fetches the managed prompt's content as main_system_prompt."""
    prompt_content = "You are a pirate. Speak like one."
    r = client.post(
        "/api/chat/prompts",
        json={"name": "pirate", "content": prompt_content},
        headers=_auth(),
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    prompt_id = r.get_json()["id"]

    r = client.post(
        CONVERSATIONS_PATH,
        json={"main_service": "svc-a", "prompt_id": prompt_id},
        headers=_auth(),
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == prompt_content


def test_new_conversation_with_invalid_prompt_id(client):
    """A non-existent prompt_id returns 404."""
    r = client.post(
        CONVERSATIONS_PATH,
        json={"main_service": "svc-a", "prompt_id": "nonexistent-prompt-id"},
        headers=_auth(),
    )
    assert r.status_code == 404
    assert "not found" in r.get_json()["error"].lower()


def test_explicit_prompt_overrides_prompt_id(client):
    """When both prompt_id and main_system_prompt are given, the explicit
    main_system_prompt wins."""
    prompt_content = "Prompt content from DB"
    r = client.post(
        "/api/chat/prompts",
        json={"name": "test", "content": prompt_content},
        headers=_auth(),
    )
    assert r.status_code == 201
    prompt_id = r.get_json()["id"]

    r = client.post(
        CONVERSATIONS_PATH,
        json={
            "main_service": "svc-a",
            "prompt_id": prompt_id,
            "main_system_prompt": "explicit override",
        },
        headers=_auth(),
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["main_system_prompt"] == "explicit override"


def test_existing_conversation_prompt_is_unaffected(client):
    """A conversation created with a specific main_system_prompt retains it
    on retrieval — regression for existing stored prompts."""
    explicit = "Stored prompt that must survive."
    r = client.post(
        CONVERSATIONS_PATH,
        json={"main_service": "svc-a", "main_system_prompt": explicit},
        headers=_auth(),
    )
    assert r.status_code == 201
    conv_id = r.get_json()["id"]

    r = client.get(f"{CONVERSATIONS_PATH}/{conv_id}", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["main_system_prompt"] == explicit
