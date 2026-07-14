"""Tests for the OpenRouter settings HTTP API and the resolver branch.

Mirrors test_chat_settings_routes.py for the endpoint trio, plus resolver /
request-building coverage for the ``openrouter:`` provider branch in
chat.llm_proxy and chat.critique.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-openrouter")

import config
from chat import critique, llm_proxy, openrouter
from chat.db import ChatDB
from chat.openrouter import DEFAULT_MODELS
from chat.routes import chat_bp

TOKEN = "test-token-openrouter"
SETTINGS_PATH = "/api/chat/settings/openrouter-models"

MODELS_A = [{"id": "vendor/model-a", "label": "Model A"}]


@pytest.fixture
def client(tmp_path, monkeypatch):
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
    assert client.get(SETTINGS_PATH).status_code == 401


def test_put_requires_auth(client):
    assert client.put(SETTINGS_PATH, json={"models": []}).status_code == 401


def test_delete_requires_auth(client):
    assert client.delete(SETTINGS_PATH).status_code == 401


# -- GET ----------------------------------------------------------------


def test_get_fresh_returns_builtin(client, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    r = client.get(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == DEFAULT_MODELS
    assert body["builtin"] == DEFAULT_MODELS
    assert body["customized"] is False
    assert body["configured"] is False


def test_configured_flips_with_api_key(client, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["configured"] is True
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["configured"] is False


# -- PUT ----------------------------------------------------------------


def test_put_persists_and_marks_customized(client):
    r = client.put(SETTINGS_PATH, json={"models": MODELS_A}, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == MODELS_A
    assert body["customized"] is True
    # Survives a fresh GET.
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["current"] == MODELS_A


def test_put_works_without_api_key(client, monkeypatch):
    """Editing the curated list is independent of key presence."""
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    r = client.put(SETTINGS_PATH, json={"models": MODELS_A}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["configured"] is False


def test_put_empty_list_is_valid(client):
    r = client.put(SETTINGS_PATH, json={"models": []}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["current"] == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"models": "not a list"},
        {"models": None},
        {"models": [{"label": "no id"}]},
        {"models": [{"id": ""}]},
        {"models": [{"id": "a/b"}, {"id": "a/b"}]},
    ],
)
def test_put_rejects_invalid_payload(client, body):
    r = client.put(SETTINGS_PATH, json=body, headers=_auth())
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert client.get(SETTINGS_PATH, headers=_auth()).get_json()["customized"] is False


@pytest.mark.parametrize("raw_body", ["[1]", '"x"', "123", "true", "null"])
def test_put_rejects_non_object_json_body(client, raw_body):
    r = client.put(
        SETTINGS_PATH, data=raw_body, content_type="application/json", headers=_auth()
    )
    assert r.status_code == 400, f"body {raw_body!r} should 400, got {r.status_code}"


# -- DELETE -------------------------------------------------------------


def test_delete_reverts_to_builtin(client):
    client.put(SETTINGS_PATH, json={"models": MODELS_A}, headers=_auth())
    r = client.delete(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    body = r.get_json()
    assert body["current"] == DEFAULT_MODELS
    assert body["customized"] is False


def test_delete_when_no_customization_is_noop(client):
    r = client.delete(SETTINGS_PATH, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["customized"] is False


# -- Resolver branch ------------------------------------------------------


def test_resolve_openrouter_service_with_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    svc = llm_proxy.resolve_service("openrouter:vendor/model-a")
    assert svc == {
        "base_url": openrouter.OPENROUTER_BASE_URL,
        "api_key": "sk-or-test",
        "model": "vendor/model-a",
        "extra_headers": openrouter.OPENROUTER_EXTRA_HEADERS,
    }


def test_resolve_openrouter_service_without_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    assert llm_proxy.resolve_service("openrouter:vendor/model-a") is None


def test_resolution_ignores_curated_list(monkeypatch, tmp_path):
    """The curated list is a picker convenience, not an allowlist."""
    monkeypatch.setenv("LLM_DOCK_CHAT_SETTINGS_FILE", str(tmp_path / "s.json"))
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    svc = llm_proxy.resolve_service("openrouter:vendor/not-in-any-list")
    assert svc is not None
    assert svc["model"] == "vendor/not-in-any-list"


def test_unreachable_message_mentions_key_for_openrouter():
    msg = llm_proxy.unreachable_message("openrouter:vendor/model-a")
    assert "OPENROUTER_API_KEY" in msg
    msg = llm_proxy.unreachable_message("vllm-local")
    assert "OPENROUTER_API_KEY" not in msg


def test_stream_unconfigured_yields_specific_error(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    events = list(llm_proxy.stream_chat_completion("openrouter:vendor/model-a", []))
    assert events[0][0] == "error"
    assert "OPENROUTER_API_KEY" in events[0][1]["message"]


# -- Request building ------------------------------------------------------


class _FakeResp:
    def __init__(self, lines):
        self.status_code = 200
        self.encoding = None
        self._lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        yield from self._lines

    def close(self):
        self.closed = True


def test_stream_openrouter_request_shape(monkeypatch):
    """OpenRouter requests hit the remote URL with model + extra headers."""
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    captured = {}

    def _post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return _FakeResp(['data: {"choices":[{"delta":{"content":"hi"}}]}',
                          'data: [DONE]'])

    monkeypatch.setattr(llm_proxy.requests, "post", _post)
    events = list(llm_proxy.stream_chat_completion("openrouter:vendor/model-a", []))
    assert any(e[0] == "done" for e in events)
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["json"]["model"] == "vendor/model-a"
    assert captured["headers"]["Authorization"] == "Bearer sk-or-test"
    assert captured["headers"]["X-Title"] == "llm-dock"


def test_stream_local_request_has_no_model_field(monkeypatch):
    """Regression: local single-model services must NOT get a model field."""
    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})
    captured = {}

    def _post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _FakeResp(['data: [DONE]'])

    monkeypatch.setattr(llm_proxy.requests, "post", _post)
    list(llm_proxy.stream_chat_completion("svc", []))
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert "model" not in captured["json"]


def test_stream_midstream_error_chunk(monkeypatch):
    """An {\"error\": ...} SSE chunk (e.g. mid-stream rate limit) surfaces
    as an error event instead of being silently swallowed."""
    resp = _FakeResp([
        'data: {"choices":[{"delta":{"content":"partial"}}]}',
        'data: {"error":{"message":"Rate limit exceeded","code":429}}',
        'data: {"choices":[{"delta":{"content":"never seen"}}]}',
    ])
    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})
    monkeypatch.setattr(llm_proxy.requests, "post", lambda *a, **k: resp)

    events = list(llm_proxy.stream_chat_completion("svc", []))
    kinds = [e[0] for e in events]
    assert kinds == ["delta", "error"]
    assert "Rate limit exceeded" in events[-1][1]["message"]
    assert resp.closed


def test_critique_openrouter_request_shape(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    captured = {}

    class _JsonResp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {
                "content": '{"verdict": "ok", "summary": "s", "annotations": []}'
            }}]}

    def _post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _JsonResp()

    monkeypatch.setattr(critique.requests, "post", _post)
    result = critique.request_critique("openrouter:vendor/model-a", "ctx")
    assert "error" not in result
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["json"]["model"] == "vendor/model-a"


def test_critique_unconfigured_returns_specific_error(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    result = critique.request_critique("openrouter:vendor/model-a", "ctx")
    assert "OPENROUTER_API_KEY" in result["error"]
