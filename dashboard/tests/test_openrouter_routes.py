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
from chat import critique, llm_proxy, openrouter, openrouter_catalog
from chat.db import ChatDB
from chat.openrouter import DEFAULT_MODELS
from chat.routes import chat_bp

TOKEN = "test-token-openrouter"
SETTINGS_PATH = "/api/chat/settings/openrouter-models"
CATALOG_PATH = "/api/chat/settings/openrouter-catalog"

MODELS_A = [{"id": "vendor/model-a", "label": "Model A"}]

RAW_CATALOG = {
    "data": [
        {
            "id": "z-ai/glm-5.2:free",
            "name": "Z.ai: GLM 5.2 (free)",
            "created": 1780000000,
            "context_length": 200000,
            "description": "A free tool-capable model.",
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "supported_parameters": ["tools"],
        },
        {
            "id": "openrouter/auto",
            "name": "Auto Router",
            "pricing": {"prompt": "0.000003", "completion": "0.000009"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "supported_parameters": [],
        },
    ]
}

RAW_ENDPOINTS = {
    "data": {
        "id": "tencent/hy3",
        "endpoints": [
            {
                "provider_name": "DeepInfra",
                "quantization": "fp8",
                "context_length": 262144,
                "pricing": {"prompt": "0.00000014", "completion": "0.00000042"},
                "uptime_last_1d": 98.4301,
                "status": 0,
                "supported_parameters": ["tools"],
            },
            {
                "provider_name": "Tencent",
                "quantization": "fp8",
                "context_length": 262144,
                "pricing": {"prompt": "0.0000000825", "completion": "0.00000033"},
                "uptime_last_1d": 99.895,
                "status": 0,
                "supported_parameters": ["tools"],
            },
        ],
    }
}


class _CatalogFake:
    """Minimal stand-in for the ``requests`` module inside openrouter_catalog."""

    def __init__(self, exc=None, status=200):
        self.calls = []
        self.exc = exc
        self.status = status

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url})
        if self.exc:
            raise self.exc
        if url.endswith("/endpoints"):
            return _CatalogResponse(RAW_ENDPOINTS, self.status)
        return _CatalogResponse(RAW_CATALOG, self.status)


class _CatalogResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    """Keeps the process-wide catalog cache from bleeding between tests."""
    openrouter_catalog.clear_cache()
    yield
    openrouter_catalog.clear_cache()


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


# -- Live catalog endpoint ------------------------------------------------


def test_catalog_requires_auth(client):
    assert client.get(CATALOG_PATH).status_code == 401


def test_catalog_shape(client, monkeypatch):
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    body = client.get(CATALOG_PATH, headers=_auth()).get_json()
    assert body["count"] == 2
    assert body["stale"] is False and body["cached"] is False and body["error"] is None
    assert body["fetched_at"].endswith("Z")
    assert {"id", "name", "label", "price_in", "chat_model", "tools"} <= set(body["models"][0])
    assert body["known_ids"] == ["openrouter/auto", "z-ai/glm-5.2:free"]


def test_catalog_reports_key_presence(client, monkeypatch):
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    assert client.get(CATALOG_PATH, headers=_auth()).get_json()["configured"] is False
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    assert client.get(CATALOG_PATH, headers=_auth()).get_json()["configured"] is True


def test_catalog_available_without_api_key(client, monkeypatch):
    """Upstream is public: authoring the list works before the key exists."""
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    assert client.get(CATALOG_PATH, headers=_auth()).status_code == 200


def test_catalog_serves_cache_on_second_call(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    client.get(CATALOG_PATH, headers=_auth())
    second = client.get(CATALOG_PATH, headers=_auth()).get_json()
    assert len(fake.calls) == 1
    assert second["cached"] is True


def test_catalog_refresh_bypasses_cache(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    client.get(CATALOG_PATH, headers=_auth())
    client.get(f"{CATALOG_PATH}?refresh=1", headers=_auth())
    assert len(fake.calls) == 2


def test_catalog_detail_adds_descriptions(client, monkeypatch):
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    body = client.get(f"{CATALOG_PATH}?detail=1", headers=_auth()).get_json()
    entry = next(m for m in body["models"] if m["id"] == "z-ai/glm-5.2:free")
    assert entry["description"] == "A free tool-capable model."


def test_catalog_502_when_upstream_unreachable(client, monkeypatch):
    """With nothing cached the UI needs a 502 it can render as a retry."""
    import requests as real_requests

    monkeypatch.setattr(
        openrouter_catalog, "requests", _CatalogFake(exc=real_requests.ConnectionError("down"))
    )
    r = client.get(CATALOG_PATH, headers=_auth())
    assert r.status_code == 502
    body = r.get_json()
    assert body["models"] == [] and body["count"] == 0
    assert "OpenRouter catalog unavailable" in body["error"]


def test_catalog_serves_stale_instead_of_failing(client, monkeypatch):
    """Once something is cached, an outage degrades rather than erroring."""
    import requests as real_requests

    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    client.get(CATALOG_PATH, headers=_auth())
    monkeypatch.setattr(
        openrouter_catalog, "requests", _CatalogFake(exc=real_requests.ConnectionError("down"))
    )
    monkeypatch.setitem(openrouter_catalog._cache, "fetched_at_epoch", 0)
    body = client.get(CATALOG_PATH, headers=_auth()).get_json()
    assert body["stale"] is True and body["count"] == 2
    assert "down" in body["error"]


def test_catalog_502_on_upstream_error_status(client, monkeypatch):
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake(status=503))
    assert client.get(CATALOG_PATH, headers=_auth()).status_code == 502


def test_catalog_does_not_disturb_curated_list(client, monkeypatch):
    """The catalog is display-time enrichment: storage is untouched."""
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    client.get(CATALOG_PATH, headers=_auth())
    body = client.get(SETTINGS_PATH, headers=_auth()).get_json()
    assert body["current"] == DEFAULT_MODELS and body["customized"] is False


# -- Picker payload round-trips the existing storage contract -------------


def test_put_accepts_catalog_derived_picker_payload(client, monkeypatch):
    """What the new picker sends — catalog ids with derived labels — is a valid
    PUT body, proving the storage contract held without a schema change."""
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    catalog_models = client.get(CATALOG_PATH, headers=_auth()).get_json()["models"]
    picked = [{"id": m["id"], "label": m["label"]} for m in catalog_models]
    r = client.put(SETTINGS_PATH, json={"models": picked}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["current"] == picked
    assert r.get_json()["customized"] is True


# -- Provider detail -----------------------------------------------------

PROVIDERS_PATH = "/api/chat/settings/openrouter-catalog/endpoints"


def test_providers_requires_auth(client):
    assert client.post(PROVIDERS_PATH, json={"ids": ["a/b"]}).status_code == 401


def test_providers_shape(client, monkeypatch):
    monkeypatch.setattr(openrouter_catalog, "requests", _CatalogFake())
    body = client.post(PROVIDERS_PATH, json={"ids": ["tencent/hy3"]}, headers=_auth()).get_json()
    assert sorted(body) == ["cached", "fetched", "missing", "models", "stale"]
    providers = body["models"]["tencent/hy3"]
    assert [p["provider"] for p in providers] == ["Tencent", "DeepInfra"]   # cheapest first
    assert providers[0]["price_in"] == 0.0825
    assert providers[0]["uptime_1d"] in (99.89, 99.9)
    assert body["fetched"] == 1 and body["cached"] == 0


def test_providers_are_cached_per_id(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    client.post(PROVIDERS_PATH, json={"ids": ["tencent/hy3", "z-ai/glm-5.2:free"]}, headers=_auth())
    calls = len(fake.calls)
    body = client.post(PROVIDERS_PATH, json={"ids": ["tencent/hy3"]}, headers=_auth()).get_json()
    assert len(fake.calls) == calls            # fresh entry, nothing fetched
    assert body["cached"] == 1 and body["fetched"] == 0


def test_providers_deduplicates_ids(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    body = client.post(
        PROVIDERS_PATH, json={"ids": ["tencent/hy3", " tencent/hy3 ", "tencent/hy3"]}, headers=_auth()
    ).get_json()
    assert body["fetched"] == 1


def test_providers_force_refetches(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    client.post(PROVIDERS_PATH, json={"ids": ["tencent/hy3"]}, headers=_auth())
    calls = len(fake.calls)
    client.post(PROVIDERS_PATH, json={"ids": ["tencent/hy3"], "force": True}, headers=_auth())
    assert len(fake.calls) == calls + 1


def test_providers_empty_batch_is_free(client, monkeypatch):
    fake = _CatalogFake()
    monkeypatch.setattr(openrouter_catalog, "requests", fake)
    body = client.post(PROVIDERS_PATH, json={"ids": []}, headers=_auth()).get_json()
    assert body["models"] == {} and body["fetched"] == 0
    assert fake.calls == []


def test_providers_rejects_bodies_that_are_not_id_lists(client):
    assert client.post(PROVIDERS_PATH, json="ids", headers=_auth()).status_code == 400
    assert client.post(PROVIDERS_PATH, json={"ids": "a/b"}, headers=_auth()).status_code == 400
    assert client.post(PROVIDERS_PATH, json={"ids": [""]}, headers=_auth()).status_code == 400
    assert client.post(PROVIDERS_PATH, json={"ids": [3]}, headers=_auth()).status_code == 400


def test_providers_caps_batch_size(client):
    """A POST must not become a back door for a catalog-wide sweep."""
    ids = [f"vendor/model-{i}" for i in range(openrouter_catalog.MAX_PROVIDER_IDS + 1)]
    r = client.post(PROVIDERS_PATH, json={"ids": ids}, headers=_auth())
    assert r.status_code == 400
    assert "max" in r.get_json()["error"]


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


def test_stream_final_usage_chunk_with_empty_choices(monkeypatch):
    """OpenRouter emits a final usage chunk with `choices: []` before [DONE]
    (https://openrouter.ai/docs/api/reference/overview#responses). It must be
    a no-op, not an IndexError that fails the run after a complete answer."""
    resp = _FakeResp([
        ': OPENROUTER PROCESSING',
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":1}}',
        'data: [DONE]',
    ])
    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})
    monkeypatch.setattr(llm_proxy.requests, "post", lambda *a, **k: resp)

    events = list(llm_proxy.stream_chat_completion("svc", []))
    kinds = [e[0] for e in events]
    assert kinds == ["delta", "done"]
    assert events[-1][1]["content"] == "hello"


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


def test_critique_null_content_falls_back_to_reasoning(monkeypatch):
    """Non-streaming message.content is string|null; an explicit null must
    not crash .strip() — the critique should be parsed from `reasoning`."""
    monkeypatch.setattr(critique, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})

    class _JsonResp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {
                "content": None,
                "reasoning": '{"verdict": "ok", "summary": "s", "annotations": []}',
            }}]}

    monkeypatch.setattr(critique.requests, "post", lambda *a, **k: _JsonResp())
    result = critique.request_critique("svc", "ctx")
    assert result.get("verdict") == "ok"
    assert "error" not in result


def test_critique_unconfigured_returns_specific_error(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    result = critique.request_critique("openrouter:vendor/model-a", "ctx")
    assert "OPENROUTER_API_KEY" in result["error"]
