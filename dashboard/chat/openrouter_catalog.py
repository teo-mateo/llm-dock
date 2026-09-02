"""Live OpenRouter model catalog, proxied and cached server-side.

Backs the dynamic model picker on the settings page: the dashboard fetches
OpenRouter's public ``GET /api/v1/models`` list, normalizes each entry down to
what a picker needs (and what it needs in display units — upstream prices are
per token, which is unreadable), and serves it from an in-process TTL cache.

Why a proxy rather than a browser-side fetch: one network egress path, the
upstream response shape stays out of the client, and there is a single place to
normalize units and to serve stale data when OpenRouter is unreachable.

The catalog is **display-time enrichment only** — it is never persisted. The
curated short list keeps its ``[{id, label}]`` shape in ``settings_store``, so
nothing here can go stale in storage, and no migration is involved.

Failure posture is stale-if-error: an unreachable OpenRouter degrades to the
previous good payload flagged ``stale=True`` rather than breaking the page.
Only a first-ever failure raises :class:`CatalogUnavailable`.

Upstream facts worth knowing (all verified against the live API): the endpoint
is public, so nothing here requires ``OPENROUTER_API_KEY`` — passing it only
buys better rate limits; ``pricing`` values are decimal-ish strings in
**dollars per token**; ``expiration_date`` is dominated by a far-future
sentinel; and a zero price is not the same signal as a ``:free`` id suffix.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from urllib.parse import quote

import requests
from requests.exceptions import RequestException

import config

from . import openrouter

logger = logging.getLogger(__name__)

CATALOG_URL = f"{openrouter.OPENROUTER_BASE_URL}/models"

# The catalog drifts slowly and the settings page should not hammer the API on
# every visit, so a fetched payload is reused for a while. Explicit Refresh
# (``?refresh=1``) bypasses this.
CACHE_TTL_SECONDS = 900
FETCH_TIMEOUT_SECONDS = 10

# ``expiration_date`` is mostly a placeholder upstream — most rows that carry
# one read 2098-12-31. Anything further out than this is treated as "no
# expiry" rather than surfaced as a date the user can parse meaningfully.
_EXPIRY_HORIZON_DAYS = 3650

# Truncation for the opt-in descriptions payload (see ``detail`` in fetch()).
_DESCRIPTION_CHARS = 200

# Per-model provider detail. Names are not in the model list — upstream exposes
# them only through /models/{id}/endpoints, one request per model — so this is
# fetched per model and cached per model: a page of ~40 rows costs about 0.4 s
# once warm, whereas sweeping the whole catalog is ~14 s and fails on ~2 % of
# models. That asymmetry is why providers appear for the rows you can see
# rather than as a catalog-wide filter.
ENDPOINT_TTL_SECONDS = 300
ENDPOINT_CONCURRENCY = 6

# Cap on one batch, so a POST can't be turned into a catalog-wide sweep (425
# upstream requests) by a caller with a token. The picker never asks for more
# than the page it is showing.
MAX_PROVIDER_IDS = 60

# Fields a picker sorts/filters on that upstream may omit for some models.
_KNOWN_VARIANTS = ("free", "batch", "extended")

_lock = threading.Lock()

# Separate lock and cache: provider fan-out must never block a catalog read,
# and the two payloads have different lifetimes.
_endpoints_lock = threading.Lock()
_endpoints_cache: dict = {}  # model_id -> {providers, fetched_at, error}

# One catalog for all users, keyed by nothing but time. ``descriptions`` is
# kept out of ``models`` because it is by far the heaviest field and only
# wanted on hover; it is joined back in when a caller asks for detail.
_cache: dict = {"models": None, "descriptions": {}, "fetched_at": None}


class CatalogUnavailable(RuntimeError):
    """Raised when the catalog has never been fetched and cannot be fetched now."""


def _price_per_mtok(raw) -> float:
    """Upstream prices are strings of dollars-per-token; render as $/1M."""
    try:
        return round(float(raw) * 1_000_000, 4)
    except (TypeError, ValueError):
        return 0.0


def _expiry(value):
    """Parse ``expiration_date``, discarding far-future sentinels."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    if (parsed - date.today()).days > _EXPIRY_HORIZON_DAYS:
        return None
    return parsed.isoformat()


def _label(name: str, model_id: str) -> str:
    """Short-form label: OpenRouter names are ``"Vendor: Model"``, and the
    vendor has a column of its own upstream of that."""
    if ": " in name:
        stripped = name.split(": ", 1)[1].strip()
        if stripped:
            return stripped
    return name or model_id


def _variant(model_id: str):
    """The ``:free`` / ``:batch`` style suffix of an id, when it has one."""
    if ":" not in model_id:
        return None
    suffix = model_id.split(":", 1)[1]
    return suffix if suffix in _KNOWN_VARIANTS else suffix or None


def _normalize(raw: list) -> tuple:
    """Turn a raw upstream ``data`` array into picker records.

    Pure function: no I/O, no clock reads beyond ``_expiry``, no Flask import.
    Returns ``(models, descriptions)`` where ``descriptions`` maps id to a
    truncated description string and is deliberately separate from the payload
    the client loads on mount.

    Missing fields degrade to ``None`` / empty rather than raising — key
    presence is not uniform across models upstream.
    """
    models = []
    descriptions = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()

        pricing = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else {}
        arch = entry.get("architecture") if isinstance(entry.get("architecture"), dict) else {}
        params = entry.get("supported_parameters")
        params = params if isinstance(params, list) else []
        output_modalities = arch.get("output_modalities")
        output_modalities = output_modalities if isinstance(output_modalities, list) else []
        input_modalities = arch.get("input_modalities")
        input_modalities = input_modalities if isinstance(input_modalities, list) else []
        analysis = (
            (entry.get("benchmarks") or {}).get("artificial_analysis")
            if isinstance(entry.get("benchmarks"), dict)
            else None
        )
        analysis = analysis if isinstance(analysis, dict) else {}

        price_in = _price_per_mtok(pricing.get("prompt"))
        price_out = _price_per_mtok(pricing.get("completion"))
        cache_read = pricing.get("input_cache_read")
        router = model_id.split("/")[0] == "openrouter"
        image_out = "image" in output_modalities
        audio_out = "audio" in output_modalities
        expires = _expiry(entry.get("expiration_date"))
        name = entry.get("name") if isinstance(entry.get("name"), str) else ""
        name = name.strip() or model_id

        models.append(
            {
                "id": model_id,
                "name": name,
                "label": _label(name, model_id),
                "created": entry.get("created") if isinstance(entry.get("created"), int) else None,
                "context_length": (
                    entry.get("context_length") if isinstance(entry.get("context_length"), int) else None
                ),
                "price_in": price_in,
                "price_out": price_out,
                "price_cache_read": _price_per_mtok(cache_read) if cache_read is not None else None,
                # Zero price, not a ":free" suffix: some free rows carry no
                # suffix, and a zero price can still hide per-unit billing.
                "free": price_in == 0 and price_out == 0,
                "variant": _variant(model_id),
                "vendor": model_id.split("/")[0],
                # Pseudo-models that route to other models (openrouter/auto…),
                # and rows whose output is not chat text. These are flags, not
                # server-side exclusions — the client decides what to hide so
                # a new upstream pseudo-model needs no backend change.
                "router": router,
                "image_out": image_out,
                "audio_out": audio_out,
                "chat_model": not (router or image_out or audio_out),
                "tools": "tools" in params,
                "structured_outputs": "structured_outputs" in params,
                "reasoning": "reasoning" in params,
                "input_modalities": input_modalities,
                "tokenizer": arch.get("tokenizer") if isinstance(arch.get("tokenizer"), str) else None,
                "hugging_face_id": (
                    entry.get("hugging_face_id") if isinstance(entry.get("hugging_face_id"), str) else None
                ),
                "expires": expires,
                "deprecated": bool(expires) and expires < date.today().isoformat(),
                "benchmarks": (
                    {
                        "intelligence": analysis.get("intelligence_index"),
                        "coding": analysis.get("coding_index"),
                        "agentic": analysis.get("agentic_index"),
                    }
                    if analysis
                    else None
                ),
            }
        )

        description = entry.get("description")
        if isinstance(description, str) and description.strip():
            text = " ".join(description.split())
            descriptions[model_id] = (
                text[:_DESCRIPTION_CHARS] + "…" if len(text) > _DESCRIPTION_CHARS else text
            )

    models.sort(key=lambda m: m["name"].lower())
    return models, descriptions


def _headers() -> dict:
    # Attribute access on the config module, not a from-import binding, so a
    # key picked up after startup is honored without reloading this module.
    key = config.OPENROUTER_API_KEY
    return {"Authorization": f"Bearer {key}"} if key else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _fresh() -> bool:
    if not _cache.get("models") or _cache.get("fetched_at_epoch") is None:
        return False
    return (_epoch() - _cache["fetched_at_epoch"]) < CACHE_TTL_SECONDS


def fetch(force: bool = False, detail: bool = False) -> dict:
    """Return the catalog, from cache when fresh.

    ``force`` bypasses the TTL (the Refresh button). ``detail`` joins in the
    truncated description of each model — it costs roughly a third of the
    payload, so it is opt-in.

    Returns ``{models, count, fetched_at, stale, cached, error}``. Raises
    :class:`CatalogUnavailable` only when there is no cached payload at all to
    fall back on.
    """
    with _lock:
        if _cache["models"] is not None and not force:
            if _fresh():
                return _payload(stale=False, cached=True, error=None, detail=detail)
            # Expired but present: try to refresh, serve stale on failure.
        try:
            response = requests.get(
                CATALOG_URL, headers=_headers(), timeout=FETCH_TIMEOUT_SECONDS
            )
        except RequestException as exc:
            return _degrade(f"request failed: {exc}", detail)
        if response.status_code // 100 != 2:
            return _degrade(f"upstream returned HTTP {response.status_code}", detail)
        try:
            body = response.json()
        except ValueError:
            return _degrade("upstream returned malformed JSON", detail)
        raw = body.get("data") if isinstance(body, dict) else None
        if not isinstance(raw, list) or not raw:
            return _degrade("upstream returned no models", detail)

        models, descriptions = _normalize(raw)
        _cache["models"] = models
        _cache["descriptions"] = descriptions
        _cache["fetched_at"] = _now_iso()
        _cache["fetched_at_epoch"] = _epoch()
        logger.info("openrouter catalog fetched (%d models)", len(models))
        return _payload(stale=False, cached=False, error=None, detail=detail)


def _degrade(reason: str, detail: bool = False) -> dict:
    """Serve the previous good payload flagged stale, or raise if there is none."""
    if _cache["models"] is not None:
        logger.warning("openrouter catalog refresh failed (%s); serving stale", reason)
        return _payload(stale=True, cached=True, error=reason, detail=detail)
    raise CatalogUnavailable(reason)


def _payload(stale: bool, cached: bool, error, detail: bool = False) -> dict:
    models = _cache["models"] or []
    if detail:
        descriptions = _cache["descriptions"]
        models = [dict(m, description=descriptions.get(m["id"], "")) for m in models]
    return {
        "models": models,
        "count": len(models),
        "fetched_at": _cache["fetched_at"],
        "stale": stale,
        "cached": cached,
        "error": error,
    }


def known_ids() -> set:
    """Ids in the last good catalog — empty when never fetched.

    Lets the short list badge curated entries that upstream no longer offers
    without paying for a second catalog read.
    """
    with _lock:
        return {m["id"] for m in (_cache["models"] or [])}


def _endpoints_url(model_id: str) -> str:
    """Provider list URL for one model. Slashes stay literal so the path
    segments survive; the ``:free`` / ``:batch`` colon is escaped."""
    return f"{CATALOG_URL}/{quote(model_id, safe='/')}/endpoints"


def _normalize_endpoints(raw: list) -> list:
    """One record per endpoint, cheapest first.

    ``uptime_last_1d`` is already a percentage upstream. ``status`` is an
    upstream integer enum passed through untouched: its non-zero values are not
    documented, so the UI prints it verbatim rather than inventing a label.
    """
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        provider = entry.get("provider_name")
        if not isinstance(provider, str) or not provider.strip():
            continue
        pricing = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else {}
        params = entry.get("supported_parameters")
        uptime = entry.get("uptime_last_1d")
        out.append(
            {
                "provider": provider.strip(),
                "quantization": entry.get("quantization") or "unknown",
                "context_length": entry.get("context_length") if isinstance(entry.get("context_length"), int) else None,
                "max_completion_tokens": (
                    entry.get("max_completion_tokens") if isinstance(entry.get("max_completion_tokens"), int) else None
                ),
                "price_in": _price_per_mtok(pricing.get("prompt")),
                "price_out": _price_per_mtok(pricing.get("completion")),
                "uptime_1d": round(uptime, 2) if isinstance(uptime, (int, float)) else None,
                "status": entry.get("status") if isinstance(entry.get("status"), int) else None,
                "tools": "tools" in (params if isinstance(params, list) else []),
            }
        )
    out.sort(key=lambda p: (p["price_in"], p["provider"]))
    return out


def _fetch_endpoints(model_id: str):
    """Fetch and normalize one model's endpoints -> ``(providers, error)``.

    ``providers`` is ``None`` on failure so the caller can fall back to a cached
    entry per id: a fan-out over 40 rows that died because one id 500'd would
    make the whole list look broken.
    """
    try:
        response = requests.get(
            _endpoints_url(model_id), headers=_headers(), timeout=FETCH_TIMEOUT_SECONDS
        )
    except RequestException as exc:
        return None, f"request failed: {exc}"
    if response.status_code // 100 != 2:
        return None, f"upstream returned HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        return None, "upstream returned malformed JSON"
    data = body.get("data") if isinstance(body, dict) else None
    raw = data.get("endpoints") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return None, "upstream returned no endpoints"
    return _normalize_endpoints(raw), None


def summarize_endpoints(ids: list, force: bool = False) -> dict:
    """Provider detail for ``ids``, fetching only what isn't fresh.

    Returns ``{models, missing, stale, fetched, cached}``. ``missing`` holds ids
    with neither a fresh entry nor a stale one to fall back on; those rows render
    without provider chips and are retried on the next request, so a failed
    fan-out leaves no permanent hole in the cache.
    """
    now = _epoch()
    models = {}
    due = []
    with _endpoints_lock:
        for model_id in ids:
            entry = _endpoints_cache.get(model_id)
            if entry and not force and (now - entry["fetched_at"]) < ENDPOINT_TTL_SECONDS:
                models[model_id] = entry["providers"]
            else:
                due.append(model_id)
    cached = len(models)
    missing = []
    stale = []
    if due:
        with ThreadPoolExecutor(max_workers=ENDPOINT_CONCURRENCY) as pool:
            results = list(pool.map(lambda mid: (mid,) + _fetch_endpoints(mid), due))
        for model_id, providers, error in results:
            if providers is not None:
                with _endpoints_lock:
                    _endpoints_cache[model_id] = {
                        "providers": providers,
                        "fetched_at": _epoch(),
                        "error": None,
                    }
                models[model_id] = providers
                continue
            logger.warning("openrouter endpoints for '%s' unavailable: %s", model_id, error)
            with _endpoints_lock:
                entry = _endpoints_cache.get(model_id)
            if entry:
                models[model_id] = entry["providers"]
                stale.append(model_id)
            else:
                missing.append(model_id)
    return {
        "models": models,
        "missing": missing,
        "stale": stale,
        "fetched": len(due),
        "cached": cached,
    }


def clear_cache() -> None:
    """Drop the cached catalog and provider detail (tests, key rotation)."""
    with _lock:
        _cache["models"] = None
        _cache["descriptions"] = {}
        _cache["fetched_at"] = None
        _cache.pop("fetched_at_epoch", None)
    with _endpoints_lock:
        _endpoints_cache.clear()
