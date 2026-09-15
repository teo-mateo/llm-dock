"""Per-conversation sampling params: persistence, write-time guard, run-time guard.

Two enforcement points, copied from the reasoning-level design on purpose. The
write paths reject what the grammar forbids, so a stored blob was legal when it
was written. Run creation re-checks it against the engine the conversation is on
now, because between those two moments the model can have changed — and a field
the current engine cannot take must be dropped and *named*, not quietly skipped.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-sp-chat")

from chat.db import ChatDB
from chat.models import Conversation
from chat.routes import chat_bp

TOKEN = "test-token-sp-chat"
CONVERSATIONS_PATH = "/api/chat/conversations"

# Engines chosen so that one takes the whole set and one takes none, which is the
# only distinction the feature claims to make.
ENGINES = {
    "vllm-a": "vllm",
    "llamacpp-b": "llamacpp",
    "ds4-c": "ds4",
    "openrouter-x": "openrouter",
}


@pytest.fixture
def client(monkeypatch):
    """Chat blueprint on an in-memory DB, with service engines stubbed.

    `_service_engine` is the only seam touching Docker; stubbing it keeps this
    file about the column and its guards. Its own test drives the real one.
    """
    import chat.routes as routes

    monkeypatch.setattr(routes, "_service_engine",
                        lambda svc, _e=ENGINES: _e.get(svc))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create(client, **extra):
    body = {"main_service": "vllm-a"}
    body.update(extra)
    r = client.post(CONVERSATIONS_PATH, json=body, headers=_auth())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# -- storage -------------------------------------------------------------


def test_new_conversation_has_no_params_by_default(client):
    assert _create(client)["sampling_params"] is None


def test_created_params_come_back_round_tripped(client):
    conv = _create(client, sampling_params={"temperature": 0.4, "top_k": 40,
                                            "stop": ["END"]})
    assert conv["sampling_params"] == {"temperature": 0.4, "top_k": 40, "stop": ["END"]}


def test_stored_blob_is_one_column_of_json(client):
    """One blob, not a column per knob — the shape the migration promises, and the
    shape a client that reads the column directly (Android, a future export) sees."""
    conv = _create(client, sampling_params={"seed": 7, "temperature": 0.5})
    with client.application.app_context():
        from chat.routes import _get_db
        stored = _get_db().get_conversation(conv["id"]).sampling_params_json
    assert stored == '{"temperature":0.5,"seed":7}'


def test_integers_survive_the_column(client):
    """A float-parsing round trip would make top_k 40.0 and vLLM would 400 it."""
    conv = _create(client, sampling_params={"top_k": 40, "max_tokens": 1024, "seed": 1})
    values = conv["sampling_params"]
    assert all(isinstance(values[k], int) for k in ("top_k", "max_tokens", "seed"))


def test_list_payload_carries_the_params(client):
    _create(client, sampling_params={"temperature": 0.2})
    r = client.get(f"{CONVERSATIONS_PATH}?limit=10", headers=_auth())
    assert r.get_json()["conversations"][0]["sampling_params"] == {"temperature": 0.2}


# -- write-time guard ----------------------------------------------------


@pytest.mark.parametrize("value", [
    {"temperature": 2.5},
    {"top_p": 0},
    {"top_p": 1.5},
    {"max_tokens": 0},
    {"repetition_penalty": 0},
    {"presence_penalty": -3},
    {"seed": -1},
    {"stop": "END"},
    {"stop": ["a"] * 5},
    {"temp": 0.5},
    "0.5",
    [0.5],
])
def test_create_rejects_and_says_why(client, value):
    r = client.post(CONVERSATIONS_PATH,
                    json={"main_service": "vllm-a", "sampling_params": value},
                    headers=_auth())
    assert r.status_code == 400, r.get_json()
    # Machine-readable: the composer retries on this code and on nothing else.
    assert r.get_json()["code"] == "invalid_sampling_params"


def test_rejected_create_names_the_field(client):
    r = client.post(CONVERSATIONS_PATH,
                    json={"main_service": "vllm-a", "sampling_params": {"temperature": 9}},
                    headers=_auth())
    assert "temperature" in r.get_json()["error"]


def test_put_replaces_the_whole_blob(client):
    """Merge semantics for an open knob set is where "why did my temperature
    change" bugs live, so a save carries the complete set."""
    conv = _create(client, sampling_params={"temperature": 0.4, "top_p": 0.9})
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"sampling_params": {"seed": 3}}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["sampling_params"] == {"seed": 3}


@pytest.mark.parametrize("value", [None, {}])
def test_put_clears_with_null_or_empty(client, value):
    conv = _create(client, sampling_params={"seed": 3})
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"sampling_params": value}, headers=_auth())
    assert r.status_code == 200 and r.get_json()["sampling_params"] is None


def test_rejected_put_leaves_the_stored_params_untouched(client):
    conv = _create(client, sampling_params={"temperature": 0.5})
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"sampling_params": {"top_p": 2}}, headers=_auth())
    assert r.status_code == 400
    r = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth())
    assert r.get_json()["sampling_params"] == {"temperature": 0.5}


def test_an_unrelated_put_does_not_touch_the_params(client):
    """A rename or a title edit must not silently drop a sampling set."""
    conv = _create(client, sampling_params={"seed": 5})
    client.put(f"{CONVERSATIONS_PATH}/{conv['id']}", json={"title": "x"}, headers=_auth())
    r = client.get(f"{CONVERSATIONS_PATH}/{conv['id']}", headers=_auth())
    assert r.get_json()["sampling_params"] == {"seed": 5}


def test_the_sampling_code_is_distinct_from_the_level_code(client):
    """A client branches on the code, so a level rejection must not look like a
    params rejection or the composer retries the wrong thing."""
    r = client.post(CONVERSATIONS_PATH,
                    json={"main_service": "vllm-a", "reasoning_level": "ultra"},
                    headers=_auth())
    assert r.status_code == 400
    assert r.get_json()["code"] == "invalid_reasoning_level"


# -- run-time guard ------------------------------------------------------


def _conv(main_service, params_json=None):
    return Conversation(id="c", title="t", main_service=main_service,
                        sampling_params_json=params_json)


def test_run_keeps_params_the_engine_can_take(client, monkeypatch):
    import chat.routes as routes
    assert routes._effective_sampling_params(_conv("vllm-a", '{"temperature": 0.3}')) \
        == ({"temperature": 0.3}, None)


def test_run_drops_fields_an_engine_cannot_take_and_names_them(client, monkeypatch):
    """The whole point of the note: a dropped temperature must not look like a
    model that ignored it."""
    import chat.routes as routes
    params, note = routes._effective_sampling_params(
        _conv("ds4-c", '{"temperature": 0.3, "seed": 4}'))
    assert params is None
    assert "temperature" in note and "seed" in note


def test_run_drops_everything_for_an_engine_that_takes_nothing(client, monkeypatch):
    """ik_llamacpp ships the same flags as llama.cpp but is unverified, so it is
    unmapped and every stored field is dropped — and every one is listed, because
    the note is the only signal the user gets."""
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_engine", lambda svc: "ik_llamacpp")
    params, note = routes._effective_sampling_params(_conv("x", '{"top_k": 5, "seed": 2}'))
    assert params is None
    assert "top_k" in note and "seed" in note


def test_run_for_an_unknown_service_drops_everything(client, monkeypatch):
    import chat.routes as routes
    monkeypatch.setattr(routes, "_service_engine", lambda svc: None)
    params, note = routes._effective_sampling_params(_conv("gone", '{"seed": 1}'))
    assert params is None
    assert "seed" in note


def test_run_without_params_produces_no_value_and_no_note(client):
    import chat.routes as routes
    assert routes._effective_sampling_params(_conv("vllm-a", None)) == (None, None)


def test_run_started_frame_carries_the_applied_params(client, monkeypatch):
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

    conv = _create(client, sampling_params={"temperature": 0.6})
    r = client.post(f"{CONVERSATIONS_PATH}/{conv['id']}/messages",
                    json={"content": "hi"}, headers=_auth())
    assert r.status_code == 200
    # What the worker was told and what the client was told are one value.
    assert calls["start"]["sampling_params"] == {"temperature": 0.6}
    assert calls["observe_extra"]["sampling_params"] == {"temperature": 0.6}
    assert "sampling_params_note" not in calls["observe_extra"]


def test_run_started_frame_reports_a_drop(client, monkeypatch):
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

    body = {"main_service": "ds4-c", "sampling_params": {"temperature": 0.6}}
    conv = client.post(CONVERSATIONS_PATH, json=body, headers=_auth()).get_json()
    r = client.post(f"{CONVERSATIONS_PATH}/{conv['id']}/messages",
                    json={"content": "hi"}, headers=_auth())
    assert r.status_code == 200
    assert calls["start"]["sampling_params"] is None
    assert "temperature" in calls["observe_extra"]["sampling_params_note"]


def test_the_column_is_left_alone_after_a_drop(client, monkeypatch):
    """Switching the model back must restore the choice, so the run-time guard
    never rewrites what the user stored."""
    class _Mgr:
        def subscribe(self, run_id):
            return object()

        def start(self, conv, run, **kwargs):
            return None

        def observe(self, run_id, q, run_started_extra=None):
            return iter([b""])

    import chat.routes as routes
    monkeypatch.setattr(routes, "_get_run_manager", lambda: _Mgr())

    body = {"main_service": "ds4-c", "sampling_params": {"temperature": 0.6}}
    conv = client.post(CONVERSATIONS_PATH, json=body, headers=_auth()).get_json()
    client.post(f"{CONVERSATIONS_PATH}/{conv['id']}/messages", json={"content": "hi"},
                headers=_auth())
    r = client.put(f"{CONVERSATIONS_PATH}/{conv['id']}",
                   json={"main_service": "vllm-a"}, headers=_auth())
    assert r.get_json()["sampling_params"] == {"temperature": 0.6}


# -- what the composer is allowed to offer -------------------------------


@pytest.mark.parametrize("service,expected", [
    ("vllm-a", 10),
    ("llamacpp-b", 10),
    ("ds4-c", 0),
    ("openrouter-x", 0),
    ("nope", 0),
])
def test_capabilities_endpoint_matches_the_mapping(client, service, expected):
    """The picker offers exactly what the runner would send: one table, read by
    both, so a knob can never be offered that the payload would drop."""
    r = client.get(f"/api/chat/sampling-fields?service={service}", headers=_auth())
    assert r.status_code == 200
    fields = r.get_json()["fields"]
    assert len(fields) == expected
    if fields:
        names = [f["name"] for f in fields]
        assert "temperature" in names and "stop" in names
        assert all("min" in f and "max" in f and "step" in f for f in fields)


def test_capabilities_endpoint_names_the_engine_it_resolved(client):
    r = client.get("/api/chat/sampling-fields?service=vllm-a", headers=_auth())
    assert r.get_json()["engine"] == "vllm"


def test_endpoint_requires_auth(client):
    assert client.get("/api/chat/sampling-fields?service=vllm-a").status_code == 401
