"""LiteLLM gateway for `template_type: "litellm"`: routes published model names
to dock services or provider models behind one Anthropic `/v1/messages` port.

`routes` is the pure core; `files` writes config.yaml (no secrets) and the 0600
gateway.env during compose rendering, the one seam every name/port/key change
passes through. Design: issue #507.
"""

from .files import compose_context, ensure, provider_lookup, remove, route_warnings, routes_dir, service_dir
from .routes import (
    ProviderCreds,
    ResolvedRoute,
    check_and_resolve,
    rename_routed_service,
    render_config,
    render_env,
    resolve_routes,
    validate_routes,
)

__all__ = [
    "ProviderCreds",
    "ResolvedRoute",
    "check_and_resolve",
    "compose_context",
    "ensure",
    "provider_lookup",
    "remove",
    "rename_routed_service",
    "render_config",
    "render_env",
    "resolve_routes",
    "route_warnings",
    "routes_dir",
    "service_dir",
    "validate_routes",
]
