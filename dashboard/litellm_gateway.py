"""
Generated LiteLLM gateway config for `template_type: "litellm"`.

The gateway exposes the Anthropic Messages API (`POST /v1/messages`, streaming
and tool use) for clients that speak only that format — Claude Desktop's 3P
deployment and Claude Code's gateway mode — and routes each published model
name either to a dock service (reached on llm-network by service name +
engine internal port, never by host port) or to a cloud provider from
providers.json (key resolved through chat/providers.api_key, so it is entered
once and survives dashboard restarts).

Files are (re)written during compose rendering for the same reason as
tabby_keys: every mutation that can change a name, port or key (create,
rename, default-key rotation) rebuilds docker-compose.yml, so rendering is
the one seam that covers them all.

Two files per gateway service, both machine-local and gitignored:

  <dir>/<service>/config.yaml   model_list with `os.environ/…` key
                                references; 0644, contains no secrets
  <dir>/<service>/gateway.env   master key + one UPSTREAM_<n>_KEY per route;
                                0600

A route whose service or provider no longer exists, has no key, or points at
another gateway or an embedding service is skipped with a warning rather than
failing the render: one deleted model must not take the gateway's compose
entry down with it. Stopped upstreams are NOT skipped — a start/stop must not
re-render anything, and a stopped model fails with LiteLLM's upstream error
until its container is back.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent / "litellm"

# Upstream model prefix per provider id. LiteLLM's native `mistral/` client is
# proven against Mistral (spike, 2026-11-15: streaming + tool round-trip);
# anything else is routed through the OpenAI-compatible client with the
# provider's own base_url.
_NATIVE_PROVIDER_PREFIXES = {"mistral": "mistral"}


def routes_dir() -> Path:
    """Directory holding per-gateway configs (machine-local, gitignored)."""
    override = os.environ.get("LLM_DOCK_LITELLM_DIR")
    return Path(override) if override else _DEFAULT_DIR


def service_dir(service_name: str) -> Path:
    return routes_dir() / service_name


def validate_routes(routes: Any) -> List[str]:
    """
    Grammar-check the `routes` list. Returns error messages, [] when valid.

    A route is {"model": <published name>, "service": <dock service>} or
    {"model": …, "provider": <providers.json id>, "upstream_model": …}.
    """
    errors: List[str] = []
    if not isinstance(routes, list) or not routes:
        return ["routes must be a non-empty list"]

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
    return errors


def _dock_route(services_db: Dict[str, Any], service_name: str) -> Optional[str]:
    """Skip-and-report reasons a dock route cannot be rendered, else None."""
    target = services_db.get(service_name)
    if target is None:
        return f"service '{service_name}' is not defined"
    if target.get("template_type") == "litellm":
        return f"service '{service_name}' is itself a gateway"
    if not target.get("api_key"):
        # ds4 has no key; LiteLLM needs some non-empty credential string.
        return f"service '{service_name}' has no api_key"
    return None


def resolve_routes(
    routes: List[Dict[str, Any]], services_db: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Resolve routes against the service database and providers.json.

    Returns (resolved, warnings). Each resolved route carries:
      model          published name (what /v1/models lists)
      upstream_model model string the upstream expects
      api_base       upstream base URL (dock services: container network)
      key            upstream credential (service key or provider key)
    """
    from flag_metadata import engine_internal_port
    from chat import providers as chat_providers

    resolved: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for route in routes:
        model = route["model"]
        if "service" in route:
            service_name = route["service"]
            reason = _dock_route(services_db, service_name)
            if reason:
                warnings.append(f"skipped route '{model}': {reason}")
                continue
            target = services_db[service_name]
            internal = engine_internal_port(target["template_type"])
            resolved.append({
                "model": model,
                # The upstream model string is the service's alias: vLLM and
                # SGLang serve it verbatim; llama.cpp ignores it.
                "upstream_model": target.get("alias") or service_name,
                "api_base": f"http://{service_name}:{internal}/v1",
                "key": target["api_key"],
            })
        else:
            provider_id = route["provider"]
            entry = chat_providers.get_provider(provider_id)
            if entry is None:
                warnings.append(
                    f"skipped route '{model}': provider '{provider_id}' "
                    "is not configured"
                )
                continue
            key = chat_providers.api_key(entry)
            if not key:
                warnings.append(
                    f"skipped route '{model}': provider '{provider_id}' "
                    "has no api key"
                )
                continue
            resolved.append({
                "model": model,
                "upstream_model": route["upstream_model"],
                "provider": provider_id,
                "api_base": entry.get("base_url"),
                "key": key,
            })
    return resolved, warnings


def render_config(service_name: str, resolved: List[Dict[str, Any]]) -> str:
    """
    Render the LiteLLM proxy config body. No secrets: every credential is an
    `os.environ/` reference resolved inside the container from gateway.env.
    """
    model_list = []
    for i, route in enumerate(resolved):
        params: Dict[str, Any] = {
            "api_key": f"os.environ/UPSTREAM_{i}_KEY",
        }
        native = _NATIVE_PROVIDER_PREFIXES.get(route.get("provider"))
        if native:
            params["model"] = f"{native}/{route['upstream_model']}"
        else:
            params["model"] = f"openai/{route['upstream_model']}"
            if route.get("api_base"):
                params["api_base"] = route["api_base"]
        model_list.append({"model_name": route["model"], "litellm_params": params})

    return yaml.safe_dump(
        {
            "model_list": model_list,
            "litellm_settings": {
                # Claude clients send cache_control breakpoints and
                # anthropic-version headers; upstreams that don't know them
                # must not 400.
                "drop_params": True,
            },
            "general_settings": {
                "master_key": "os.environ/LITELLM_MASTER_KEY",
            },
        },
        sort_keys=False,
    )


def render_env(master_key: str, resolved: List[Dict[str, Any]]) -> str:
    lines = [f"LITELLM_MASTER_KEY={master_key}"]
    for i, route in enumerate(resolved):
        lines.append(f"UPSTREAM_{i}_KEY={route['key']}")
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, body: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ensure(
    service_name: str,
    config: Dict[str, Any],
    services_db: Dict[str, Any],
) -> Tuple[Path, Path, List[str]]:
    """
    Validate, resolve and (re)write a gateway's config.yaml + gateway.env.

    Idempotent on purpose — compose rebuilds happen on every service mutation.
    Returns (config_path, env_path, warnings).
    """
    errors = validate_routes(config.get("routes"))
    if errors:
        raise ValueError("; ".join(errors))

    # Unresolvable routes never raise here: this runs inside every compose
    # rebuild, so raising would block deleting or renaming the gateway's last
    # upstream. The gateway then serves an empty model list until fixed.
    resolved, warnings = resolve_routes(config.get("routes"), services_db)

    directory = service_dir(service_name)
    _atomic_write(
        directory / "config.yaml", render_config(service_name, resolved), 0o644
    )
    _atomic_write(
        directory / "gateway.env",
        render_env(config["api_key"], resolved),
        0o600,  # upstream keys and the master key are secrets
    )
    logger.info(
        f"Wrote LiteLLM gateway config for '{service_name}' "
        f"({len(resolved)} routes, {len(warnings)} skipped)"
    )
    return directory / "config.yaml", directory / "gateway.env", warnings


def rename_routed_service(
    services_db: Dict[str, Any], old_name: str, new_name: str
) -> List[str]:
    """Point every gateway route at `old_name` to `new_name`, in place.
    Returns the gateways whose routes changed."""
    changed = []
    for name, cfg in services_db.items():
        if cfg.get("template_type") != "litellm":
            continue
        hit = False
        for route in cfg.get("routes") or []:
            if isinstance(route, dict) and route.get("service") == old_name:
                route["service"] = new_name
                hit = True
        if hit:
            changed.append(name)
    return changed


def remove(service_name: str) -> Optional[Path]:
    """Delete a gateway's config directory. Returns the path removed, if any."""
    import shutil

    directory = service_dir(service_name)
    if directory.is_dir():
        shutil.rmtree(directory)
        logger.info(f"Removed LiteLLM gateway config for '{service_name}'")
        return directory
    return None
