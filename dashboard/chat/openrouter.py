"""OpenRouter provider support for chat.

An OpenRouter model is addressed with a ``openrouter:<model-id>`` service
string (e.g. ``openrouter:anthropic/claude-sonnet-5``) stored in the same
``main_service`` / ``sidekick_service`` / ``model_service`` columns as local
Docker service names — no schema changes. ``llm_proxy.resolve_service``
branches on the prefix and calls :func:`resolve` here instead of the Docker
lookup.

The curated model list shown in the picker is a convenience, not an
allowlist: any ``openrouter:`` service string resolves as long as
``OPENROUTER_API_KEY`` is configured, so conversations keep working when
their model is later removed from the list. The list itself is editable at
runtime via ``settings_store`` (Settings page), with :data:`DEFAULT_MODELS` as
the built-in baseline.
"""

import logging

import config
from reasoning_levels import LEVEL_NAME_RE, MAX_LEVELS, OFF_LEVEL

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SERVICE_PREFIX = "openrouter:"

# Optional attribution headers OpenRouter recommends; they identify the app
# in OpenRouter's logs and rankings.
OPENROUTER_EXTRA_HEADERS = {
    "HTTP-Referer": "https://github.com/teo-mateo/llm-dock",
    "X-Title": "llm-dock",
}

# Built-in curated selection of popular models (all tool-capable, verified
# against openrouter.ai/api/v1/models). Overridable at runtime via
# settings_store.set_openrouter_models().
DEFAULT_MODELS = [
    {"id": "anthropic/claude-sonnet-5", "label": "Claude Sonnet 5"},
    {"id": "anthropic/claude-opus-4.8", "label": "Claude Opus 4.8"},
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5"},
    {"id": "openai/gpt-5.5", "label": "GPT-5.5"},
    {"id": "openai/gpt-5.4-mini", "label": "GPT-5.4 Mini"},
    {"id": "google/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro (Preview)"},
    {"id": "google/gemini-3.5-flash", "label": "Gemini 3.5 Flash"},
    {"id": "x-ai/grok-4.5", "label": "Grok 4.5"},
    {"id": "deepseek/deepseek-v3.2", "label": "DeepSeek V3.2"},
    {"id": "deepseek/deepseek-v4-pro", "label": "DeepSeek V4 Pro"},
    {"id": "deepseek/deepseek-v4-flash", "label": "DeepSeek V4 Flash"},
    {"id": "mistralai/mistral-medium-3-5", "label": "Mistral Medium 3.5"},
    {"id": "mistralai/mistral-large-2512", "label": "Mistral Large 3"},
    {"id": "mistralai/mistral-small-2603", "label": "Mistral Small 4"},
    {"id": "mistralai/devstral-2512", "label": "Devstral 2"},
    {"id": "qwen/qwen3.7-max", "label": "Qwen3.7 Max"},
    {"id": "moonshotai/kimi-k2.6", "label": "Kimi K2.6"},
    {"id": "z-ai/glm-5", "label": "GLM 5"},
    {"id": "z-ai/glm-5.2", "label": "GLM 5.2"},
    {"id": "tencent/hy3", "label": "Hunyuan 3"},
]


def is_configured() -> bool:
    """True when an OpenRouter API key is present in the environment."""
    return bool(config.OPENROUTER_API_KEY)


def is_openrouter_service(service_name) -> bool:
    return isinstance(service_name, str) and service_name.startswith(SERVICE_PREFIX)


def model_id(service_name: str) -> str:
    return service_name[len(SERVICE_PREFIX):]


# Upstream lists efforts descending; the ladder reads least-to-most, so ordering comes
# from this rank rather than from a reversal, and an effort OpenRouter adds tomorrow
# lands after the known ones instead of somewhere arbitrary.
_EFFORT_RANK = {"minimal": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4, "max": 5}

# The effort that switches reasoning off, and the level id llm-dock reserves for it.
_EFFORT_NONE = "none"


def ladder_from_reasoning(meta) -> str:
    """Derive a declaration string from one model's upstream capability metadata.

    Takes the ``reasoning_meta`` the catalogue normaliser keeps and returns what an
    operator would otherwise type into ``reasoning_levels``: least-to-most, ``off``
    first, ``""`` when the model exposes no effort selection at all.

    ``off`` appears only where upstream lists ``none`` and reasoning is not mandatory,
    because ``effort: "none"`` is answered with a 400 on a mandatory model - offering it
    would be offering a failure. Tokens outside the declaration grammar are dropped
    rather than raised: a ladder comes from the network, and a surprising token must
    cost one level, not the whole shortlist save.
    """
    if not isinstance(meta, dict):
        return ""
    efforts = meta.get("supported_efforts")
    if not isinstance(efforts, list) or not efforts:
        return ""

    known, unknown = [], []
    for token in efforts:
        if not isinstance(token, str) or token == _EFFORT_NONE:
            continue
        if not LEVEL_NAME_RE.match(token):
            logger.warning("openrouter: dropping effort outside the grammar: %r", token)
            continue
        (known if token in _EFFORT_RANK else unknown).append(token)

    levels = sorted(known, key=lambda token: _EFFORT_RANK[token]) + unknown
    if not meta.get("mandatory") and _EFFORT_NONE in efforts:
        levels.insert(0, OFF_LEVEL)

    if len(levels) > MAX_LEVELS:
        logger.warning("openrouter: truncating %d levels to %d", len(levels), MAX_LEVELS)
        levels = levels[:MAX_LEVELS]
    return ",".join(levels)


def ladder_for_model(model: str) -> str:
    """The stored ladder for one OpenRouter model id, "" when it has none.

    The single reader behind both enforcement points, so the ladder offered and the
    ladder enforced cannot drift - the property ``routes._service_reasoning_levels``
    documents for local services, provided here for a remote one.

    The settings import is deferred because ``settings_store`` imports this module at
    module level for its built-in baseline; a module-level import here is a circular
    ImportError in either load order.
    """
    if not isinstance(model, str) or not model:
        return ""
    from . import settings_store
    for entry in settings_store.get_openrouter_models():
        if isinstance(entry, dict) and entry.get("id") == model:
            return entry.get("reasoning_levels") or ""
    return ""


def resolve(service_name: str):
    """Provider-branch counterpart of ``llm_proxy.resolve_service``.

    Returns the connection dict for an ``openrouter:`` service string, or
    ``None`` when no API key is configured (same shape as a stopped local
    service, so callers hit their existing unreachable path).
    """
    if not is_configured():
        return None
    return {
        "base_url": OPENROUTER_BASE_URL,
        "api_key": config.OPENROUTER_API_KEY,
        "model": model_id(service_name),
        "extra_headers": dict(OPENROUTER_EXTRA_HEADERS),
    }
