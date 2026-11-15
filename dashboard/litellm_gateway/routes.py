from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from flag_metadata import GATEWAY_ENGINES, openwebui_base_url, service_kind

# Upstream model prefix per provider id. LiteLLM's native `mistral/` client is
# proven against Mistral (spike, 2026-11-15: streaming + tool round-trip);
# any other provider goes through the OpenAI-compatible client with its own
# base_url.
_NATIVE_PROVIDER_PREFIXES = {"mistral": "mistral"}

# A route's params must not carry a credential or redirect it: config.yaml is
# the secret-free file, and api_base/model are what the route itself resolves.
RESERVED_ROUTE_PARAMS = frozenset({"api_key", "api_base", "model"})


@dataclass(frozen=True)
class ProviderCreds:
    base_url: Optional[str]
    key: str


@dataclass(frozen=True)
class ResolvedRoute:
    model: str
    upstream_model: str
    api_base: Optional[str]
    key: str
    provider: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


ProviderLookup = Callable[[str], Optional[ProviderCreds]]


def validate_routes(routes: Any) -> List[str]:
    """A route is {"model", "service"} or {"model", "provider", "upstream_model"}."""
    if not isinstance(routes, list) or not routes:
        return ["routes must be a non-empty list"]

    errors: List[str] = []
    seen_models = set()
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"routes[{i}]: must be an object")
            continue
        model = route.get("model")
        if not isinstance(model, str) or not model.strip():
            errors.append(f"routes[{i}]: missing 'model' (the published name)")
            continue
        if model in seen_models:
            errors.append(f"routes[{i}]: duplicate model name '{model}'")
        seen_models.add(model)

        has_service = "service" in route
        has_provider = "provider" in route
        if has_service == has_provider:
            errors.append(
                f"routes[{i}] ('{model}'): exactly one of 'service' or "
                "'provider' is required"
            )
        if has_provider and not route.get("upstream_model"):
            errors.append(
                f"routes[{i}] ('{model}'): provider routes need 'upstream_model'"
            )
        errors += _params_errors(i, model, route.get("params"))
    return errors


def _params_errors(i: int, model: str, params: Any) -> List[str]:
    if params is None:
        return []
    if not isinstance(params, dict):
        return [f"routes[{i}] ('{model}'): params must be an object"]
    reserved = sorted(RESERVED_ROUTE_PARAMS & set(params))
    if reserved:
        return [f"routes[{i}] ('{model}'): params may not set {', '.join(reserved)}"]
    return []


def _dock_skip_reason(services_db: Dict[str, Any], service_name: str) -> Optional[str]:
    target = services_db.get(service_name)
    if target is None:
        return f"service '{service_name}' is not defined"
    if target.get("template_type") in GATEWAY_ENGINES:
        return f"service '{service_name}' is itself a gateway"
    if service_kind(target) == "embedding":
        return f"service '{service_name}' is an embedding model"
    # LiteLLM needs a non-empty credential; ds4 services carry none.
    if not target.get("api_key"):
        return f"service '{service_name}' has no api_key"
    return None


def _resolve_dock(model: str, service_name: str, services_db: Dict[str, Any]) -> ResolvedRoute:
    target = services_db[service_name]
    return ResolvedRoute(
        model=model,
        upstream_model=target.get("alias") or service_name,
        api_base=openwebui_base_url(service_name, target["template_type"]),
        key=target["api_key"],
    )


def _with_params(route: Dict[str, Any], resolved: ResolvedRoute) -> ResolvedRoute:
    params = route.get("params")
    if not params:
        return resolved
    return replace(resolved, params=dict(params))


def resolve_routes(
    routes: List[Dict[str, Any]],
    services_db: Dict[str, Any],
    provider_lookup: ProviderLookup,
) -> Tuple[List[ResolvedRoute], List[str]]:
    """Stopped upstreams resolve: start/stop never re-renders, so a stopped
    model fails with LiteLLM's upstream error instead of vanishing."""
    resolved: List[ResolvedRoute] = []
    warnings: List[str] = []

    for route in routes:
        model = route["model"]
        if "service" in route:
            reason = _dock_skip_reason(services_db, route["service"])
            if reason:
                warnings.append(f"skipped route '{model}': {reason}")
                continue
            resolved.append(_with_params(route, _resolve_dock(model, route["service"], services_db)))
            continue

        provider_id = route["provider"]
        creds = provider_lookup(provider_id)
        if creds is None:
            warnings.append(f"skipped route '{model}': provider '{provider_id}' is not configured")
            continue
        if not creds.key:
            warnings.append(f"skipped route '{model}': provider '{provider_id}' has no api key")
            continue
        resolved.append(_with_params(route, ResolvedRoute(
            model=model,
            upstream_model=route["upstream_model"],
            api_base=creds.base_url,
            key=creds.key,
            provider=provider_id,
        )))
    return resolved, warnings


def check_and_resolve(
    routes: Any, services_db: Dict[str, Any], provider_lookup: ProviderLookup
) -> Tuple[List[ResolvedRoute], List[str]]:
    """Never raises: rendering runs inside every compose rebuild, so a bad
    route must cost the gateway its routes, not block every other service."""
    errors = validate_routes(routes)
    if errors:
        return [], [f"routes not rendered: {e}" for e in errors]
    return resolve_routes(routes, services_db, provider_lookup)


def render_config(resolved: List[ResolvedRoute]) -> str:
    """No secrets: every credential is an `os.environ/` reference into gateway.env."""
    model_list = []
    for i, route in enumerate(resolved):
        params: Dict[str, Any] = {**(route.params or {}), "api_key": f"os.environ/UPSTREAM_{i}_KEY"}
        native = _NATIVE_PROVIDER_PREFIXES.get(route.provider)
        if native:
            params["model"] = f"{native}/{route.upstream_model}"
        else:
            params["model"] = f"openai/{route.upstream_model}"
            if route.api_base:
                params["api_base"] = route.api_base
        model_list.append({"model_name": route.model, "litellm_params": params})

    return yaml.safe_dump(
        {
            "model_list": model_list,
            "litellm_settings": {
                # Claude clients send cache_control breakpoints that upstreams
                # which don't know them would 400 on.
                "drop_params": True,
                # Otherwise LiteLLM bridges /v1/messages to the OpenAI Responses
                # API for openai/ models. llama.cpp's /v1/responses rejects
                # replayed thinking blocks and splits Claude histories into a
                # mid-conversation system message that Qwen templates raise on.
                "use_chat_completions_url_for_anthropic_messages": True,
            },
            "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY"},
        },
        sort_keys=False,
    )


def render_env(master_key: str, resolved: List[ResolvedRoute]) -> str:
    lines = [f"LITELLM_MASTER_KEY={master_key}"]
    lines += [f"UPSTREAM_{i}_KEY={route.key}" for i, route in enumerate(resolved)]
    return "\n".join(lines) + "\n"


def rename_routed_service(services_db: Dict[str, Any], old_name: str, new_name: str) -> List[str]:
    """Rewrites in place; returns the gateways whose routes changed."""
    changed = []
    for name, cfg in services_db.items():
        if cfg.get("template_type") not in GATEWAY_ENGINES:
            continue
        hit = False
        for route in cfg.get("routes") or []:
            if isinstance(route, dict) and route.get("service") == old_name:
                route["service"] = new_name
                hit = True
        if hit:
            changed.append(name)
    return changed
