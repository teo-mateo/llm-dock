"""Tests for chat.openrouter_catalog — normalization, caching, failure posture.

No network: ``requests.get`` is monkeypatched. The raw fixtures mirror the
upstream shape, including the asymmetries the normalizer exists to absorb:
prices as strings of $/token, ``:free`` suffix vs. zero price, pseudo-router
rows, non-text output rows, far-future ``expiration_date`` sentinels, and
sparse keys.
"""
import copy
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import openrouter_catalog as catalog

RAW = {
    "data": [
        {
            "id": "ibm-granite/granite-4.2-8b",
            "name": "IBM: Granite 4.2 8B",
            "created": 1788206780,
            "context_length": 131072,
            "description": "A dense   reasoning\nmodel from IBM.",
            "pricing": {"prompt": "0.0000001", "completion": "0.00000015", "input_cache_read": "0.00000005"},
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "tokenizer": "Other",
            },
            "supported_parameters": ["tools", "structured_outputs", "reasoning", "temperature"],
            "benchmarks": {"artificial_analysis": {"intelligence_index": 57.5, "coding_index": 71.5, "agentic_index": 58.2}},
            "expiration_date": "2098-12-31",
        },
        {
            "id": "z-ai/glm-5.2:free",
            "name": "Z.ai: GLM 5.2 (free)",
            "created": 1780000000,
            "context_length": 200000,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "supported_parameters": ["tools"],
            "hugging_face_id": "zai-org/GLM-5.2",
        },
        {
            # Zero price without the ":free" suffix — the free test must be
            # the price, not the id.
            "id": "google/lyria-3-pro-preview",
            "name": "Google: Lyria 3 Pro (preview)",
            "created": 1770000000,
            "context_length": 32000,
            "description": "$0.08 per song.",
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text", "audio"]},
            "supported_parameters": [],
        },
        {
            "id": "openrouter/auto",
            "name": "Auto Router",
            "created": 1700000000,
            "context_length": 2000000,
            "pricing": {"prompt": "0.000003", "completion": "0.000009"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text", "image"]},
            "supported_parameters": ["tools"],
        },
        {
            "id": "google/gemini-3-pro-image",
            "name": "Google: Gemini 3 Pro Image",
            "pricing": {"prompt": "0.000002"},
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["image", "text"]},
            "supported_parameters": ["tools"],
            "expiration_date": "2020-01-02",
        },
        {
            # Sparse row: no name, no pricing, no architecture, no parameters.
            "id": "vendor/sparse-model",
        },
        {"id": "", "name": "no id, skipped"},
        "not an object",
    ]
}


class FakeResponse:
    def __init__(self, payload=None, status=200, text=None):
        self._payload = payload
        self.status_code = status
        self._text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeRequests:
    """Stands in for ``requests`` in the catalog module; counts calls.

    Installed autouse and pre-loaded with :data:`RAW`, so no test can reach the
    network by forgetting to configure it.
    """

    def __init__(self):
        self.calls = []
        self.exc = None
        self.delay = 0.0
        self.response = None
        self.reset()

    def reset(self, response=None, exc=None, delay=0.0):
        self.calls = []
        self.response = response if response is not None else FakeResponse(copy.deepcopy(RAW))
        self.exc = exc
        self.delay = delay
        return self

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.delay:
            threading.Event().wait(self.delay)
        if self.exc:
            raise self.exc
        return self.response


@pytest.fixture(autouse=True)
def clean_cache():
    catalog.clear_cache()
    yield
    catalog.clear_cache()


@pytest.fixture(autouse=True)
def recorder(monkeypatch):
    """The installed fake, pre-loaded with RAW. ``calls`` counts upstream hits."""
    fake_requests = FakeRequests()
    monkeypatch.setattr(catalog, "requests", fake_requests)
    return fake_requests


@pytest.fixture
def fake(recorder):
    """Re-configure the installed fake; returns it, for call-count assertions."""
    def install(response=None, exc=None, delay=0.0):
        return recorder.reset(response=response, exc=exc, delay=delay)

    return install


def _by_id(models, model_id):
    return next(m for m in models if m["id"] == model_id)


# -- Normalization ------------------------------------------------------

def test_catalog_url_reuses_openrouter_base_url():
    from chat import openrouter

    assert catalog.CATALOG_URL == f"{openrouter.OPENROUTER_BASE_URL}/models"


def test_fetch_returns_envelope(fake):
    fake()
    out = catalog.fetch()
    assert set(out) == {"models", "count", "fetched_at", "stale", "cached", "error"}
    assert out["stale"] is False and out["cached"] is False and out["error"] is None
    assert out["count"] == len(out["models"]) == 6
    assert out["fetched_at"].endswith("Z")


def test_prices_converted_to_dollars_per_million(fake):
    models = catalog.fetch()["models"]
    granite = _by_id(models, "ibm-granite/granite-4.2-8b")
    assert granite["price_in"] == 0.1
    assert granite["price_out"] == 0.15
    assert granite["price_cache_read"] == 0.05


def test_unparseable_price_degrades_to_zero(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "vendor/sparse-model")["price_in"] == 0.0
    assert _by_id(models, "vendor/sparse-model")["price_cache_read"] is None


def test_free_derived_from_price_not_suffix(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "z-ai/glm-5.2:free")["free"] is True
    assert _by_id(models, "google/lyria-3-pro-preview")["free"] is True
    assert _by_id(models, "ibm-granite/granite-4.2-8b")["free"] is False


def test_variant_suffix_extracted(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "z-ai/glm-5.2:free")["variant"] == "free"
    assert _by_id(models, "ibm-granite/granite-4.2-8b")["variant"] is None


def test_vendor_from_id_prefix(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "ibm-granite/granite-4.2-8b")["vendor"] == "ibm-granite"


def test_flags_on_routers_and_non_text_output(fake):
    models = catalog.fetch()["models"]
    auto = _by_id(models, "openrouter/auto")
    assert auto["router"] is True and auto["chat_model"] is False
    lyria = _by_id(models, "google/lyria-3-pro-preview")
    assert (lyria["audio_out"], lyria["chat_model"]) == (True, False)
    image = _by_id(models, "google/gemini-3-pro-image")
    assert (image["image_out"], image["chat_model"]) == (True, False)
    granite = _by_id(models, "ibm-granite/granite-4.2-8b")
    assert granite["chat_model"] is True


def test_non_chat_rows_flagged_despite_listing_text_output():
    """Upstream image/audio models still list ``text`` among their outputs, so
    a \"text absent from output_modalities\" test would hide nothing."""
    models = catalog.fetch()["models"]
    hidden = [m for m in models if not m["chat_model"]]
    assert len(hidden) == 3
    assert all("text" in m["input_modalities"] for m in hidden)


def test_capability_flags_from_supported_parameters(fake):
    models = catalog.fetch()["models"]
    granite = _by_id(models, "ibm-granite/granite-4.2-8b")
    assert (granite["tools"], granite["structured_outputs"], granite["reasoning"]) == (True, True, True)
    assert _by_id(models, "google/lyria-3-pro-preview")["tools"] is False


def test_label_strips_vendor_prefix(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "ibm-granite/granite-4.2-8b")["label"] == "Granite 4.2 8B"
    assert _by_id(models, "openrouter/auto")["label"] == "Auto Router"


def test_sparse_entry_degrades_without_raising(fake):
    entry = _by_id(catalog.fetch()["models"], "vendor/sparse-model")
    assert entry["name"] == "vendor/sparse-model"          # falls back to id
    assert entry["label"] == "vendor/sparse-model"
    assert entry["context_length"] is None
    assert entry["input_modalities"] == []
    assert entry["benchmarks"] is None
    assert entry["tokenizer"] is None
    assert entry["expires"] is None and entry["deprecated"] is False


def test_expiration_sentinel_dropped(fake):
    models = catalog.fetch()["models"]
    assert _by_id(models, "ibm-granite/granite-4.2-8b")["expires"] is None


def test_real_expiration_kept_and_marked_deprecated(fake):
    entry = _by_id(catalog.fetch()["models"], "google/gemini-3-pro-image")
    assert entry["expires"] == "2020-01-02"
    assert entry["deprecated"] is True


def test_benchmarks_normalized(fake):
    entry = _by_id(catalog.fetch()["models"], "ibm-granite/granite-4.2-8b")
    assert entry["benchmarks"] == {"intelligence": 57.5, "coding": 71.5, "agentic": 58.2}


def test_rows_without_id_are_skipped_and_sorted_by_name(fake):
    models = catalog.fetch()["models"]
    assert all(m["id"] for m in models)
    assert len(models) == 6
    names = [m["name"].lower() for m in models]
    assert names == sorted(names)


def test_description_not_in_default_payload_but_in_detail(fake):
    default = catalog.fetch()["models"][0]
    assert "description" not in default
    catalog.clear_cache()
    fake()
    detailed = catalog.fetch(detail=True)["models"][0]
    assert "description" in detailed


def test_description_whitespace_collapsed_and_truncated(fake, monkeypatch):
    monkeypatch.setattr(catalog, "_DESCRIPTION_CHARS", 10)
    fake()
    out = catalog.fetch(detail=True)
    entry = _by_id(out["models"], "ibm-granite/granite-4.2-8b")
    assert entry["description"] == "A dense re…"


# -- Caching ------------------------------------------------------------

def test_second_call_served_from_cache(fake):
    recorder = fake()
    first = catalog.fetch()
    second = catalog.fetch()
    assert len(recorder.calls) == 1
    assert second["cached"] is True and second["stale"] is False
    assert second["models"] == first["models"]


def test_force_bypasses_cache(fake):
    recorder = fake()
    catalog.fetch()
    catalog.fetch(force=True)
    assert len(recorder.calls) == 2


def test_expired_cache_refetches(fake, monkeypatch):
    recorder = fake()
    catalog.fetch()
    monkeypatch.setitem(catalog._cache, "fetched_at_epoch", 0)
    catalog.fetch()
    assert len(recorder.calls) == 2


def test_request_url_headers_and_timeout(fake, monkeypatch):
    monkeypatch.setattr("config.OPENROUTER_API_KEY", "sk-or-test")
    recorder = fake()
    catalog.fetch()
    call = recorder.calls[0]
    assert call["url"] == catalog.CATALOG_URL
    assert call["headers"] == {"Authorization": "Bearer sk-or-test"}
    assert call["timeout"] == catalog.FETCH_TIMEOUT_SECONDS


def test_no_auth_header_without_key(fake, monkeypatch):
    monkeypatch.setattr("config.OPENROUTER_API_KEY", "")
    recorder = fake()
    catalog.fetch()
    assert recorder.calls[0]["headers"] == {}


def test_lock_serialises_concurrent_fetches(fake):
    """Five threads arriving at once must produce one upstream request."""
    recorder = fake(delay=0.05)
    results = []

    def worker():
        results.append(catalog.fetch())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(recorder.calls) == 1
    assert len(results) == 5
    assert all(r["count"] == 6 for r in results)


def test_known_ids_from_cache(fake):
    assert catalog.known_ids() == set()
    fake()
    catalog.fetch()
    assert "z-ai/glm-5.2:free" in catalog.known_ids()
    assert len(catalog.known_ids()) == 6


def test_clear_cache_resets(fake):
    fake()
    catalog.fetch()
    catalog.clear_cache()
    assert catalog.known_ids() == set()
    assert catalog._cache["models"] is None


# -- Failure posture: stale-if-error, raise only on first-ever ------------

def test_network_error_raises_when_nothing_cached(fake):
    import requests as real_requests

    fake(exc=real_requests.ConnectTimeout("boom"))
    with pytest.raises(catalog.CatalogUnavailable):
        catalog.fetch()


def test_network_error_serves_stale_payload(fake):
    import requests as real_requests

    fake()
    catalog.fetch()
    fake(exc=real_requests.ConnectionError("down"))
    catalog._cache["fetched_at_epoch"] = 0          # expire the entry
    out = catalog.fetch()
    assert out["stale"] is True and out["cached"] is True
    assert "down" in out["error"]
    assert out["count"] == 6


def test_non_2xx_treated_as_failure(fake):
    fake(response=FakeResponse(None, status=503))
    with pytest.raises(catalog.CatalogUnavailable):
        catalog.fetch()


def test_malformed_json_treated_as_failure(fake):
    fake(response=FakeResponse(None, status=200))
    with pytest.raises(catalog.CatalogUnavailable, match="malformed JSON"):
        catalog.fetch()


def test_missing_data_key_treated_as_failure(fake):
    fake(response=FakeResponse({"models": []}))
    with pytest.raises(catalog.CatalogUnavailable, match="no models"):
        catalog.fetch()


def test_empty_data_list_treated_as_failure(fake):
    """An empty catalog would silently wipe the picker; keep the old payload."""
    fake(response=FakeResponse({"data": []}))
    with pytest.raises(catalog.CatalogUnavailable, match="no models"):
        catalog.fetch()


def test_stale_serves_detail_when_requested(fake):
    fake()
    catalog.fetch()
    import requests as real_requests

    fake(exc=real_requests.ConnectionError("down"))
    catalog._cache["fetched_at_epoch"] = 0
    out = catalog.fetch(detail=True)
    assert out["stale"] is True
    assert _by_id(out["models"], "ibm-granite/granite-4.2-8b")["description"]
