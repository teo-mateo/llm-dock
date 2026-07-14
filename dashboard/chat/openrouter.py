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
runtime via ``settings_store`` (Tools page), with :data:`DEFAULT_MODELS` as
the built-in baseline.
"""

import config

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
