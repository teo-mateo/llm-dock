import json
import os
import stat
import sys

import pytest
import requests
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import llm_proxy, providers
from chat.deps import install
from chat.db import ChatDB
from chat.routes import chat_bp
from reasoning_levels import ENGINE_PROVIDER

TOKEN = "test-token-providers"
SETTINGS = "/api/chat/settings/providers"
MODELS = "/api/chat/providers/models"
SECRET = "sk-mistral-test-secret"

MISTRAL_LIKE = {
    "data": [
        {"id": "mistral-large-2512", "aliases": ["mistral-large-latest"],
         "capabilities": {"completion_chat": True, "function_calling": True, "vision": True},
         "max_context_length": 262144, "deprecation": None},
        {"id": "mistral-large-latest", "aliases": ["mistral-large-2512"],
         "capabilities": {"completion_chat": True, "function_calling": True, "vision": True},
         "max_context_length": 262144, "deprecation": None},
        {"id": "codestral-2508", "aliases": ["codestral-latest", "mistral-code-latest"],
         "capabilities": {"completion_chat": True, "function_calling": True, "vision": False}},
        {"id": "codestral-latest", "aliases": ["codestral-2508", "mistral-code-latest"],
         "capabilities": {"completion_chat": True}},
        {"id": "mistral-code-latest", "aliases": ["codestral-2508", "codestral-latest"],
         "capabilities": {"completion_chat": True}},
        {"id": "mistral-large-4", "aliases": ["mistral-large-4-0"],
         "capabilities": {"completion_chat": True}},
        {"id": "mistral-large-4-0", "aliases": ["mistral-large-4"],
         "capabilities": {"completion_chat": True}},
        {"id": "mistral-embed", "aliases": [], "capabilities": {"completion_chat": False}},
        {"id": "old-model", "capabilities": {"completion_chat": True}, "deprecation": "2026-01-01"},
    ]
}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _Upstream:
    def __init__(self, payload=MISTRAL_LIKE, status=200, exc=None):
        self.payload, self.status, self.exc = payload, status, exc
        self.calls = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers})
        if self.exc:
            raise self.exc
        return _Resp(self.payload, self.status)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_PROVIDERS_FILE", str(tmp_path / "providers.json"))
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    providers.clear_models_cache()
    yield
    providers.clear_models_cache()


@pytest.fixture
def upstream(monkeypatch):
    fake = _Upstream()
    monkeypatch.setattr(providers.requests, "get", fake)
    return fake


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    install(app, db=ChatDB(":memory:"))
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _mistral(**extra):
    body = {"name": "Mistral", "base_url": "https://api.mistral.ai/v1/"}
    body.update(extra)
    return providers.upsert_provider("mistral", body)


def test_service_string_grammar():
    assert providers.parse_service("mistral:mistral-large-latest") == ("mistral", "mistral-large-latest")
    assert providers.parse_service("acme:org/model:tag") == ("acme", "org/model:tag")
    assert providers.parse_service("openrouter:vendor/m") is None
    assert providers.parse_service("llamacpp-gemma") is None
    assert providers.parse_service("mistral:") is None
    assert providers.parse_service("Bad:x") is None
    assert providers.parse_service(None) is None


def test_upsert_validates():
    for pid, body in [
        ("openrouter", {"name": "x", "base_url": "https://a"}),
        ("BAD", {"name": "x", "base_url": "https://a"}),
        ("acme", {"base_url": "https://a"}),
        ("acme", {"name": "x", "base_url": "ftp://a"}),
        ("acme", {"name": "x", "base_url": "https://a", "api_key_env": "lower"}),
        ("acme", {"name": "x", "base_url": "https://a", "api_key": ""}),
        ("acme", {"name": "x", "base_url": "https://a", "enabled": "yes"}),
    ]:
        with pytest.raises(providers.ProviderError):
            providers.upsert_provider(pid, body)


def test_stored_key_is_write_only_and_file_is_private():
    entry = _mistral(api_key=SECRET)
    assert entry["key_source"] == "stored"
    assert entry["base_url"] == "https://api.mistral.ai/v1"
    assert SECRET not in json.dumps(providers.list_providers())
    assert stat.S_IMODE(os.stat(providers.providers_file_path()).st_mode) == 0o600

    providers.upsert_provider("mistral", {"name": "Mistral AI"})
    assert providers.api_key(providers.get_provider("mistral")) == SECRET

    providers.upsert_provider("mistral", {"api_key": None})
    assert providers.get_provider("mistral").get("api_key") is None


def test_env_key_is_read_at_request_time(monkeypatch):
    _mistral(api_key_env="MISTRAL_API_KEY")
    assert providers.list_providers()[0]["key_source"] is None
    assert providers.resolve("mistral:mistral-small-latest") is None
    monkeypatch.setenv("MISTRAL_API_KEY", SECRET)
    assert providers.list_providers()[0]["key_source"] == "env"
    svc = providers.resolve("mistral:mistral-small-latest")
    assert svc["api_key"] == SECRET
    assert svc["model"] == "mistral-small-latest"
    assert svc["template_type"] == ENGINE_PROVIDER


def test_disabled_or_deleted_provider_does_not_resolve():
    _mistral(api_key=SECRET, enabled=False)
    assert providers.resolve("mistral:m") is None
    assert "disabled" in llm_proxy.unreachable_message("mistral:m")
    providers.delete_provider("mistral")
    assert llm_proxy.resolve_service("mistral:m") is None
    assert "not configured" in llm_proxy.unreachable_message("mistral:m")


def test_normalize_collapses_aliases_and_drops_non_chat():
    models = providers.normalize_models(MISTRAL_LIKE)
    ids = [m["id"] for m in models]
    assert ids == ["codestral-latest", "mistral-large-4", "mistral-large-latest"]
    large = next(m for m in models if m["id"] == "mistral-large-latest")
    assert large["aliases"] == ["mistral-large-2512"]
    assert large["vision"] is True and large["context_length"] == 262144


def test_normalize_passes_plain_openai_lists_through():
    models = providers.normalize_models({"data": [{"id": "b"}, {"id": "a"}]})
    assert [m["id"] for m in models] == ["a", "b"]


def test_models_are_cached_and_served_stale_on_failure(upstream):
    _mistral(api_key=SECRET)
    entry = providers.get_provider("mistral")
    models, stale = providers.fetch_models("mistral", entry)
    assert not stale and len(models) == 3
    assert upstream.calls[0]["url"] == "https://api.mistral.ai/v1/models"
    assert upstream.calls[0]["headers"]["Authorization"] == f"Bearer {SECRET}"

    providers.fetch_models("mistral", entry)
    assert len(upstream.calls) == 1

    upstream.exc = requests.ConnectionError("down")
    models, stale = providers.fetch_models("mistral", entry, force=True)
    assert stale and len(models) == 3

    providers.clear_models_cache()
    with pytest.raises(providers.ProviderUnavailable):
        providers.fetch_models("mistral", entry)


def test_editing_the_key_invalidates_the_cache(upstream):
    _mistral(api_key=SECRET)
    providers.fetch_models("mistral", providers.get_provider("mistral"))
    providers.upsert_provider("mistral", {"api_key": "sk-other"})
    providers.fetch_models("mistral", providers.get_provider("mistral"))
    assert len(upstream.calls) == 2


def test_settings_routes_crud(client):
    assert client.get(SETTINGS).status_code == 401
    body = client.get(SETTINGS, headers=_auth()).get_json()
    assert body["providers"] == [] and body["presets"][0]["id"] == "mistral"

    r = client.put(f"{SETTINGS}/mistral", json={"name": "Mistral", "base_url": "https://api.mistral.ai/v1",
                                                "api_key": SECRET}, headers=_auth())
    assert r.status_code == 200
    assert SECRET not in r.get_data(as_text=True)
    assert r.get_json()["providers"][0]["key_source"] == "stored"

    assert client.put(f"{SETTINGS}/mistral", json={"base_url": "nope"}, headers=_auth()).status_code == 400
    assert client.delete(f"{SETTINGS}/ghost", headers=_auth()).status_code == 404
    assert client.delete(f"{SETTINGS}/mistral", headers=_auth()).get_json()["providers"] == []


def test_test_route_reports_upstream(client, upstream):
    _mistral(api_key=SECRET)
    assert client.post(f"{SETTINGS}/mistral/test", headers=_auth()).get_json() == {
        "ok": True, "error": None, "model_count": 3}
    upstream.status = 401
    body = client.post(f"{SETTINGS}/mistral/test", headers=_auth()).get_json()
    assert body["ok"] is False and "401" in body["error"]


def test_models_route_lists_enabled_providers(client, upstream):
    _mistral(api_key=SECRET)
    providers.upsert_provider("nokey", {"name": "No Key", "base_url": "https://x.example/v1"})
    providers.upsert_provider("off", {"name": "Off", "base_url": "https://y.example/v1",
                                      "api_key": "k", "enabled": False})
    rows = client.get(MODELS, headers=_auth()).get_json()["providers"]
    assert [r["id"] for r in rows] == ["mistral", "nokey"]
    assert len(rows[0]["models"]) == 3 and rows[0]["configured"] is True
    assert rows[1]["configured"] is False and rows[1]["models"] == []
    assert SECRET not in json.dumps(rows)


def test_engine_and_levels_for_provider_services():
    from chat import run_config
    assert run_config.service_engine("mistral:m", lambda: []) == ENGINE_PROVIDER
    assert run_config.service_reasoning_levels("mistral:m", lambda: []) == []


class _Stream:
    status_code = 200
    encoding = None

    def iter_lines(self, decode_unicode=True):
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
        yield "data: [DONE]"

    def close(self):
        pass


def _capture_post(monkeypatch):
    captured = {}

    def _post(url, **kwargs):
        captured.update(url=url, json=kwargs["json"], headers=kwargs["headers"])
        return _Stream()

    monkeypatch.setattr(llm_proxy.requests, "post", _post)
    return captured


HISTORY = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hey", "reasoning_content": "thinking"},
    {"role": "user", "content": "again"},
]


def test_provider_request_shape_strips_reasoning_content(monkeypatch):
    _mistral(api_key=SECRET)
    captured = _capture_post(monkeypatch)
    events = list(llm_proxy.stream_chat_completion("mistral:mistral-small-latest", HISTORY,
                                                   reasoning_level="high",
                                                   sampling_params={"temperature": 0.2}))
    assert any(e[0] == "done" for e in events)
    assert captured["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == f"Bearer {SECRET}"
    sent = captured["json"]
    assert sent["model"] == "mistral-small-latest"
    assert all("reasoning_content" not in m for m in sent["messages"])
    assert set(sent) == {"model", "messages", "stream"}
    assert HISTORY[1]["reasoning_content"] == "thinking"


def test_local_request_keeps_reasoning_content(monkeypatch):
    monkeypatch.setattr(llm_proxy, "resolve_service", lambda name: {"host_port": 1234, "api_key": "k"})
    captured = _capture_post(monkeypatch)
    list(llm_proxy.stream_chat_completion("llamacpp-x", HISTORY))
    assert captured["json"]["messages"][1]["reasoning_content"] == "thinking"


class _ChunkStream(_Stream):
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        yield from self._lines


MISTRAL_THINKING_STREAM = [
    'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}',
    'data: {"choices":[{"delta":{"content":[{"type":"thinking","thinking":[{"type":"text","text":"The user"}],"closed":true}]}}]}',
    'data: {"choices":[{"delta":{"content":[{"type":"thinking","thinking":[{"type":"text","text":" says hi."}]}]}}]}',
    'data: {"choices":[{"delta":{"content":[{"type":"text","text":"Hi"}]}}]}',
    'data: {"choices":[{"delta":{"content":" there"},"finish_reason":"stop"}]}',
    "data: [DONE]",
]


def test_list_shaped_content_is_split_into_text_and_thinking(monkeypatch):
    _mistral(api_key=SECRET)
    monkeypatch.setattr(llm_proxy.requests, "post", lambda url, **kw: _ChunkStream(MISTRAL_THINKING_STREAM))
    events = list(llm_proxy.stream_chat_completion("mistral:mistral-large-4", HISTORY))
    assert ("done", {"content": "Hi there", "reasoning_content": "The user says hi."}) in events
    deltas = [d for kind, d in events if kind == "delta"]
    for d in deltas:
        assert isinstance(json.loads(d["raw"])["choices"][0]["delta"]["content"], str)
    assert json.loads(deltas[0]["raw"])["choices"][0]["delta"]["reasoning_content"] == "The user"


def test_split_content_parts():
    assert llm_proxy.split_content_parts("plain") == ("plain", "")
    assert llm_proxy.split_content_parts(None) == ("", "")
    assert llm_proxy.split_content_parts([
        {"type": "thinking", "thinking": "a"}, {"type": "text", "text": "b"}, {"type": "image_url"}, "x",
    ]) == ("b", "a")
