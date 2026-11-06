"""OpenAI-compatible model providers configured at runtime (Mistral, …).

A provider model is addressed as ``<provider-id>:<model-id>``, stored in the same
service columns as local service names and ``openrouter:`` strings. Docker
container names cannot contain ``:``, so the separator alone tells a provider
model from a local service. Design: ``docs/plans/chat-providers.md``.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time

import requests

from reasoning_levels import ENGINE_PROVIDER

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "providers.json",
)

PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
RESERVED_IDS = frozenset({"openrouter"})
MAX_NAME_CHARS = 60
MAX_KEY_CHARS = 512

PRESETS = [
    {
        "id": "mistral",
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
    },
]

MODELS_TTL_S = 15 * 60
FETCH_TIMEOUT = (5, 20)

_lock = threading.Lock()
_cache_lock = threading.Lock()
_models_cache: dict = {}


class ProviderError(ValueError):
    pass


class ProviderUnavailable(Exception):
    pass


def providers_file_path() -> str:
    return os.environ.get("LLM_DOCK_PROVIDERS_FILE", _DEFAULT_PATH)


def _load_unlocked() -> dict:
    path = providers_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("providers: cannot read %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("providers: %s top-level must be a JSON object; ignoring", path)
        return {}
    return {pid: entry for pid, entry in data.items()
            if PROVIDER_ID_RE.match(pid) and isinstance(entry, dict)}


def _save_unlocked(data: dict) -> None:
    path = providers_file_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".providers.", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def get_provider(provider_id: str):
    with _lock:
        return _load_unlocked().get(provider_id)


def api_key(entry: dict):
    stored = entry.get("api_key")
    if isinstance(stored, str) and stored:
        return stored
    env_name = entry.get("api_key_env")
    if isinstance(env_name, str) and env_name:
        return os.environ.get(env_name) or None
    return None


def key_source(entry: dict):
    stored = entry.get("api_key")
    if isinstance(stored, str) and stored:
        return "stored"
    env_name = entry.get("api_key_env")
    if isinstance(env_name, str) and env_name and os.environ.get(env_name):
        return "env"
    return None


def public_entry(provider_id: str, entry: dict) -> dict:
    """The only shape that leaves the server: the key itself is never in it."""
    return {
        "id": provider_id,
        "name": entry.get("name") or provider_id,
        "base_url": entry.get("base_url") or "",
        "api_key_env": entry.get("api_key_env") or "",
        "enabled": bool(entry.get("enabled", True)),
        "key_source": key_source(entry),
    }


def list_providers() -> list:
    with _lock:
        data = _load_unlocked()
    return [public_entry(pid, entry) for pid, entry in sorted(data.items())]


def _clean_base_url(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError("base_url is required")
    value = value.strip().rstrip("/")
    if not (value.startswith("https://") or value.startswith("http://")):
        raise ProviderError("base_url must start with http:// or https://")
    if any(c.isspace() for c in value):
        raise ProviderError("base_url must not contain whitespace")
    return value


def upsert_provider(provider_id: str, body: dict) -> dict:
    """Create or update one provider.

    ``api_key`` is write-only: a non-empty string stores it, ``null`` removes the
    stored key, and leaving the field out keeps whatever is stored — so an edit
    form that never echoes the key cannot erase it.
    """
    if not isinstance(provider_id, str) or not PROVIDER_ID_RE.match(provider_id):
        raise ProviderError("provider id must be 2-32 chars of a-z, 0-9 and '-', starting with a letter")
    if provider_id in RESERVED_IDS:
        raise ProviderError(f"provider id '{provider_id}' is reserved")
    if not isinstance(body, dict):
        raise ProviderError("body must be a JSON object")

    with _lock:
        data = _load_unlocked()
        entry = dict(data.get(provider_id) or {})

        name = body.get("name", entry.get("name"))
        if not isinstance(name, str) or not name.strip():
            raise ProviderError("name is required")
        if len(name.strip()) > MAX_NAME_CHARS:
            raise ProviderError(f"name must be at most {MAX_NAME_CHARS} characters")
        entry["name"] = name.strip()

        entry["base_url"] = _clean_base_url(body.get("base_url", entry.get("base_url")))

        if "api_key_env" in body:
            env_name = body["api_key_env"]
            if env_name in (None, ""):
                entry.pop("api_key_env", None)
            elif not isinstance(env_name, str) or not ENV_NAME_RE.match(env_name):
                raise ProviderError("api_key_env must be an environment variable name (A-Z, 0-9, _)")
            else:
                entry["api_key_env"] = env_name

        if "api_key" in body:
            key = body["api_key"]
            if key is None:
                entry.pop("api_key", None)
            elif not isinstance(key, str) or not key.strip():
                raise ProviderError("api_key must be a non-empty string, or null to remove it")
            elif len(key.strip()) > MAX_KEY_CHARS or any(c.isspace() for c in key.strip()):
                raise ProviderError("api_key looks malformed")
            else:
                entry["api_key"] = key.strip()

        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                raise ProviderError("enabled must be a boolean")
            entry["enabled"] = body["enabled"]
        entry.setdefault("enabled", True)

        data[provider_id] = entry
        _save_unlocked(data)
    clear_models_cache(provider_id)
    return public_entry(provider_id, entry)


def delete_provider(provider_id: str) -> bool:
    with _lock:
        data = _load_unlocked()
        if provider_id not in data:
            return False
        del data[provider_id]
        _save_unlocked(data)
    clear_models_cache(provider_id)
    return True


def parse_service(service_name):
    """``(provider_id, model_id)`` for a provider service string, else None.

    Syntax only, independent of what is configured: a conversation whose provider
    was deleted must still be recognised as a provider model, so it fails with the
    provider message instead of being looked up as a Docker service.
    """
    if not isinstance(service_name, str) or ":" not in service_name:
        return None
    provider_id, model = service_name.split(":", 1)
    if provider_id in RESERVED_IDS or not PROVIDER_ID_RE.match(provider_id) or not model:
        return None
    return provider_id, model


def is_provider_service(service_name) -> bool:
    return parse_service(service_name) is not None


def resolve(service_name: str):
    parsed = parse_service(service_name)
    if parsed is None:
        return None
    provider_id, model = parsed
    entry = get_provider(provider_id)
    if not entry or not entry.get("enabled", True):
        return None
    key = api_key(entry)
    if not key or not entry.get("base_url"):
        return None
    return {
        "base_url": entry["base_url"],
        "api_key": key,
        "model": model,
        "template_type": ENGINE_PROVIDER,
        "reasoning_levels": [],
        "provider_id": provider_id,
    }


def unreachable_message(service_name: str) -> str:
    parsed = parse_service(service_name)
    provider_id = parsed[0] if parsed else service_name
    entry = get_provider(provider_id)
    if entry is None:
        return f"Provider '{provider_id}' is not configured (Settings → Model providers)."
    if not entry.get("enabled", True):
        return f"Provider '{provider_id}' is disabled (Settings → Model providers)."
    return f"Provider '{provider_id}' has no API key (Settings → Model providers)."


def _is_listed(raw: dict) -> bool:
    caps = raw.get("capabilities")
    if isinstance(caps, dict) and "completion_chat" in caps and not caps["completion_chat"]:
        return False
    return not raw.get("deprecation")


def _canonical(members: list) -> str:
    latest = [m for m in members if m.endswith("-latest")]
    if latest:
        return min(latest, key=lambda m: (len(m), m))
    return members[0]


def normalize_models(payload) -> list:
    """Chat models from an OpenAI-style ``/models`` body, one row per alias group.

    Mistral lists every alias as its own entry (``mistral-large-latest`` and
    ``mistral-large-2512`` are one model); a group collapses to its shortest
    ``-latest`` id when it has one. Providers that publish no ``aliases`` or
    ``capabilities`` pass through unchanged.
    """
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ProviderUnavailable("provider /models returned no data list")

    listed = [e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)
              and e["id"] and _is_listed(e)]
    present = {e["id"]: e for e in listed}
    seen = set()
    models = []
    for raw in listed:
        if raw["id"] in seen:
            continue
        aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        members = [raw["id"]] + [a for a in aliases if isinstance(a, str) and a in present and a != raw["id"]]
        seen.update(members)
        seen.update(a for a in aliases if isinstance(a, str))
        canonical = _canonical(members)
        source = present[canonical]
        caps = source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}
        context = source.get("max_context_length") or source.get("context_length")
        models.append({
            "id": canonical,
            "label": canonical,
            "aliases": sorted(m for m in members if m != canonical),
            "vision": caps.get("vision") if isinstance(caps.get("vision"), bool) else None,
            "tools": caps.get("function_calling") if isinstance(caps.get("function_calling"), bool) else None,
            "context_length": context if isinstance(context, int) else None,
        })
    models.sort(key=lambda m: m["id"])
    return models


def _signature(entry: dict, key: str) -> str:
    return hashlib.sha256(f"{entry.get('base_url')}\0{key}".encode()).hexdigest()


def clear_models_cache(provider_id=None) -> None:
    with _cache_lock:
        if provider_id is None:
            _models_cache.clear()
        else:
            _models_cache.pop(provider_id, None)


def fetch_models(provider_id: str, entry: dict, *, force: bool = False, serve_stale: bool = True):
    """``(models, stale)`` for one provider, served from a per-provider TTL cache.

    A failed refresh serves the last good list with ``stale=True``; only a
    provider that has never answered raises :class:`ProviderUnavailable`.
    ``serve_stale=False`` is for the settings Test button, which must report a
    rejected key instead of the list cached before it was rejected.
    """
    key = api_key(entry)
    if not key:
        raise ProviderUnavailable("no API key")
    signature = _signature(entry, key)
    now = time.monotonic()
    with _cache_lock:
        cached = _models_cache.get(provider_id)
    if cached and cached["signature"] == signature and not force and now - cached["at"] < MODELS_TTL_S:
        return cached["models"], False

    try:
        resp = requests.get(
            f"{entry['base_url']}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=FETCH_TIMEOUT,
        )
        if resp.status_code != 200:
            raise ProviderUnavailable(f"provider /models returned HTTP {resp.status_code}")
        models = normalize_models(resp.json())
    except (requests.RequestException, ValueError, ProviderUnavailable) as e:
        message = str(e) if isinstance(e, ProviderUnavailable) else f"provider /models failed: {type(e).__name__}"
        logger.warning("providers: %s: %s", provider_id, message)
        if serve_stale and cached and cached["signature"] == signature:
            return cached["models"], True
        raise ProviderUnavailable(message) from e

    with _cache_lock:
        _models_cache[provider_id] = {"at": now, "signature": signature, "models": models}
    return models, False


def models_payload(*, force: bool = False) -> list:
    """Every enabled provider with the chat models it serves, for the pickers."""
    with _lock:
        data = _load_unlocked()
    out = []
    for provider_id, entry in sorted(data.items()):
        if not entry.get("enabled", True):
            continue
        row = {
            "id": provider_id,
            "name": entry.get("name") or provider_id,
            "configured": bool(api_key(entry)),
            "models": [],
            "stale": False,
            "error": None,
        }
        if row["configured"]:
            try:
                row["models"], row["stale"] = fetch_models(provider_id, entry, force=force)
            except ProviderUnavailable as e:
                row["error"] = str(e)
        out.append(row)
    return out
