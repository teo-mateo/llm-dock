"""Tests for chat.openrouter_catalog — normalization, caching, failure posture.

No network: ``requests.get`` is monkeypatched. The raw fixtures mirror the
upstream shape, including the asymmetries the normalizer exists to absorb:
prices as strings of $/token, ``:free`` suffix vs. zero price, pseudo-router
rows, non-text output rows, far-future ``expiration_date`` sentinels, and
sparse keys.
"""
import copy
import itertools
import os
import sys
import threading
from urllib.parse import quote

import pytest
import requests as real_requests

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


RAW_ENDPOINTS = {
    "data": {
        "id": "tencent/hy3",
        "name": "Tencent: Hy3",
        "endpoints": [
            {
                "provider_name": "DeepInfra",
                "quantization": "fp8",
                "context_length": 262144,
                "max_completion_tokens": 131072,
                "pricing": {"prompt": "0.00000014", "completion": "0.00000042"},
                "uptime_last_1d": 98.43019372077488,
                "status": 0,
                "supported_parameters": ["tools", "temperature"],
            },
            {
                # Cheapest, so it must sort first.
                "provider_name": "Tencent",
                "quantization": "fp8",
                "context_length": 262144,
                "max_completion_tokens": 128000,
                "pricing": {"prompt": "0.0000000825", "completion": "0.00000033"},
                "uptime_last_1d": 99.89507485320378,
                "status": 0,
                "supported_parameters": ["temperature"],
            },
            {
                "provider_name": "GMICloud",
                "context_length": 262144,
                "pricing": {"prompt": "0.000000126", "completion": "0.000000504"},
                "uptime_last_1d": 95.29,
                "status": -2,
            },
            {"provider_name": "   ", "pricing": {"prompt": "0"}},
            "not an object",
        ],
    }
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
        self.endpoints_response = None
        self.fail_ids = set()
        self.explode_ids = set()
        self.inflight = 0
        self.max_inflight = 0
        self._peak_lock = threading.Lock()
        self.reset()

    def reset(self, response=None, exc=None, delay=0.0, endpoints_response=None):
        self.calls = []
        self.response = response if response is not None else FakeResponse(copy.deepcopy(RAW))
        self.endpoints_response = (
            endpoints_response
            if endpoints_response is not None
            else FakeResponse(copy.deepcopy(RAW_ENDPOINTS))
        )
        self.exc = exc
        self.delay = delay
        self.fail_ids = set()
        self.explode_ids = set()
        self.inflight = 0
        self.max_inflight = 0
        return self

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        is_endpoints = url.endswith("/endpoints")
        if is_endpoints and any(quote(model_id, safe="/") in url for model_id in self.fail_ids):
            raise real_requests.ConnectionError("forced endpoint failure")
        if is_endpoints and any(quote(model_id, safe="/") in url for model_id in self.explode_ids):
            raise TypeError("forced unforeseen endpoint failure")
        if self.exc:
            raise self.exc
        if self.delay:
            with self._peak_lock:
                self.inflight += 1
                self.max_inflight = max(self.max_inflight, self.inflight)
            threading.Event().wait(self.delay)
            with self._peak_lock:
                self.inflight -= 1
        return self.endpoints_response if is_endpoints else self.response


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


def _explode(raw):
    """Stands in for a shape the normalizer has no answer for."""
    raise RuntimeError("forced catalog normalization failure")


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


def test_unexpected_error_serves_stale_payload(fake, monkeypatch):
    """The catch-all is what keeps the pane alive on a shape nobody predicted.

    Everything except a request error would otherwise leave :func:`fetch` and
    surface as a 500 while a perfectly good payload sits in the cache — the one
    outcome the stale-if-error posture exists to avoid.
    """
    fake()
    catalog.fetch()
    monkeypatch.setattr(catalog, "_normalize", _explode)
    catalog._cache["fetched_at_epoch"] = 0
    out = catalog.fetch()
    assert out["stale"] is True and out["cached"] is True
    assert "forced catalog normalization failure" in out["error"]
    assert out["count"] == 6


def test_unexpected_error_raises_when_nothing_cached(fake, monkeypatch):
    fake()
    monkeypatch.setattr(catalog, "_normalize", _explode)
    with pytest.raises(catalog.CatalogUnavailable, match="forced catalog normalization failure"):
        catalog.fetch()


# -- Provider detail (per-model endpoints) --------------------------------
#
# Upstream exposes provider names only per model, so this is a fan-out with a
# per-model cache. The tests below pin the parts that make that survivable:
# capped concurrency, per-id failure isolation, and no permanent hole in the
# cache when an id fails.

ENDPOINT_IDS = ["tencent/hy3", "deepseek/deepseek-v4-flash", "z-ai/glm-5.2:free"]


def test_endpoints_url_keeps_slashes_and_escapes_colon():
    assert (
        catalog._endpoints_url("z-ai/glm-5.2:free")
        == f"{catalog.CATALOG_URL}/z-ai/glm-5.2%3Afree/endpoints"
    )


def test_model_id_shape_accepts_every_shape_upstream_ships():
    # Includes the `~vendor/model-latest` aliases, which are ordinary ids with a
    # leading tilde, and a variant suffix.
    for model_id in [
        "anthropic/claude-sonnet-5",
        "dots-studio/dots-3-note-preview",
        "ibm-granite/granite-4.2-8b",
        "z-ai/glm-5.2:free",
        "~anthropic/claude-opus-latest",
    ]:
        assert catalog.MODEL_ID_RE.fullmatch(model_id), model_id


def test_model_id_shape_rejects_anything_that_is_not_an_id():
    # Ids are interpolated into a request path, so nothing that could alter one
    # gets through — including the percent-encoded forms, which would be inert
    # but are not ids either, and the dot segments, which ``requests`` would
    # resolve out of the path before sending.
    for value in [
        "../x",
        "a b",
        "a?x=1",
        "a#b",
        "%2e%2e",
        "//evil",
        "a\nHost: evil",
        "a/../../etc/passwd",
        "a/./b",
        "vendor/model/..",
        "",
    ]:
        assert not catalog.MODEL_ID_RE.fullmatch(value), value


def test_dot_segments_cannot_retarget_the_upstream_path():
    """Slashes are literal in the URL built per id, so a traversal has to die here."""
    import requests as real_requests

    assert not catalog.MODEL_ID_RE.fullmatch("a/../../etc/passwd")
    # What a shape that *does* pass looks like on the wire: the id stays put.
    prepared = real_requests.Request(
        "GET", catalog._endpoints_url("dots-studio/dots-3-note-preview")
    ).prepare()
    assert prepared.url.endswith("/models/dots-studio/dots-3-note-preview/endpoints")


def test_normalize_endpoints_sorts_by_price_and_skips_nameless():
    providers = catalog._normalize_endpoints(RAW_ENDPOINTS["data"]["endpoints"])
    assert [p["provider"] for p in providers] == ["Tencent", "GMICloud", "DeepInfra"]


def test_normalize_endpoints_units_and_defaults():
    providers = catalog._normalize_endpoints(RAW_ENDPOINTS["data"]["endpoints"])
    tencent, gmicloud, deepinfra = providers
    assert (tencent["price_in"], tencent["price_out"]) == (0.0825, 0.33)
    assert tencent["uptime_1d"] == 99.9                      # already a percentage upstream
    assert tencent["quantization"] == "fp8"
    assert tencent["tools"] is False
    assert deepinfra["tools"] is True
    assert gmicloud["quantization"] == "unknown"              # absent upstream
    assert gmicloud["uptime_1d"] == 95.29
    assert gmicloud["status"] == -2                           # passed through, not interpreted
    assert gmicloud["max_completion_tokens"] is None


def test_summarize_fetches_every_id_when_cold(recorder):
    recorder.reset(delay=0.01)
    out = catalog.summarize_endpoints(ENDPOINT_IDS)
    assert len(out) == 5
    assert sorted(out["models"]) == sorted(ENDPOINT_IDS)
    assert out["fetched"] == 3 and out["cached"] == 0
    assert out["missing"] == [] and out["stale"] == []
    assert len([c for c in recorder.calls if c["url"].endswith("/endpoints")]) == 3


def test_summarize_serves_fresh_cache_without_refetching(fake):
    recorder = fake(delay=0.01)
    catalog.summarize_endpoints(ENDPOINT_IDS)
    before = len(recorder.calls)
    out = catalog.summarize_endpoints(ENDPOINT_IDS)
    assert len(recorder.calls) == before
    assert out["cached"] == 3 and out["fetched"] == 0


def test_summarize_force_refetches(fake):
    recorder = fake(delay=0.01)
    catalog.summarize_endpoints(ENDPOINT_IDS)
    before = len(recorder.calls)
    catalog.summarize_endpoints(ENDPOINT_IDS, force=True)
    assert len(recorder.calls) == before + 3


def test_summarize_partial_failure_keeps_the_other_rows(fake):
    recorder = fake(delay=0.01)
    catalog.summarize_endpoints(ENDPOINT_IDS[:2])
    fake(delay=0.01)
    recorder.fail_ids = {ENDPOINT_IDS[0]}
    catalog._endpoints_cache[ENDPOINT_IDS[0]]["fetched_at"] = 0      # expire one entry
    catalog._endpoints_cache[ENDPOINT_IDS[1]]["fetched_at"] = 0
    out = catalog.summarize_endpoints(ENDPOINT_IDS[:2])
    assert out["stale"] == [ENDPOINT_IDS[0]]
    assert set(out["models"]) == set(ENDPOINT_IDS[:2])               # stale beats nothing
    assert out["missing"] == []


def test_summarize_reports_ids_with_nothing_to_serve(fake):
    recorder = fake(delay=0.01)
    recorder.fail_ids = {ENDPOINT_IDS[0]}
    out = catalog.summarize_endpoints(ENDPOINT_IDS)
    assert out["missing"] == [ENDPOINT_IDS[0]]
    assert sorted(out["models"]) == sorted(ENDPOINT_IDS[1:])


def test_failed_id_is_not_cached_so_the_next_call_retries(fake):
    recorder = fake(delay=0.01)
    recorder.fail_ids = {ENDPOINT_IDS[0]}
    catalog.summarize_endpoints(ENDPOINT_IDS)
    assert ENDPOINT_IDS[0] not in catalog._endpoints_cache
    fake(delay=0.01)
    out = catalog.summarize_endpoints([ENDPOINT_IDS[0]])
    assert ENDPOINT_IDS[0] in out["models"]


def test_unforeseen_error_in_one_id_costs_only_that_row(fake):
    """Isolation has to cover errors nobody anticipated, not just request ones."""
    recorder = fake(delay=0.01)
    recorder.explode_ids = {ENDPOINT_IDS[0]}
    out = catalog.summarize_endpoints(ENDPOINT_IDS)
    assert out["missing"] == [ENDPOINT_IDS[0]]
    assert sorted(out["models"]) == sorted(ENDPOINT_IDS[1:])


def test_unforeseen_error_in_normalization_costs_only_that_row(fake, monkeypatch):
    """Same posture on the parse side: one row lost, not the whole batch."""
    fake(delay=0.01)
    real = catalog._normalize_endpoints
    seen = itertools.count()

    def flaky(raw):
        # ``next`` on a counter is atomic, so exactly one worker takes the hit
        # however the fan-out interleaves.
        if next(seen) == 0:
            raise RuntimeError("forced normalization failure")
        return real(raw)

    monkeypatch.setattr(catalog, "_normalize_endpoints", flaky)
    out = catalog.summarize_endpoints(ENDPOINT_IDS)
    assert len(out["missing"]) == 1
    assert len(out["models"]) == len(ENDPOINT_IDS) - 1


def test_fan_out_concurrency_is_capped(fake):
    recorder = fake(delay=0.06)
    ids = [f"vendor/model-{i}" for i in range(14)]
    out = catalog.summarize_endpoints(ids)
    assert len(out["models"]) == 14
    assert out["fetched"] == 14
    assert recorder.max_inflight <= catalog.ENDPOINT_CONCURRENCY
    assert recorder.max_inflight > 1          # it really did run in parallel


def test_empty_id_list_touches_nothing(fake):
    recorder = fake()
    out = catalog.summarize_endpoints([])
    assert out == {"models": {}, "missing": [], "stale": [], "fetched": 0, "cached": 0}
    assert recorder.calls == []


def test_clear_cache_drops_provider_detail(fake):
    recorder = fake(delay=0.01)
    catalog.summarize_endpoints(ENDPOINT_IDS)
    catalog.clear_cache()
    catalog.summarize_endpoints(ENDPOINT_IDS)
    assert len([c for c in recorder.calls if c["url"].endswith("/endpoints")]) == 6
