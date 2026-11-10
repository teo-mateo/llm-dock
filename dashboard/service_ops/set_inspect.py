import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .deps import Infra
from .errors import OpError, service_not_found
from .hooks import Cause, Phase, ServicesChangedContext, run_phase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetInspectDeps:
    infra: Infra
    allocate_upstream_port: Callable[[Mapping[str, Any], str], int]
    recreate_if_running: Callable[[str], dict]
    proxy_status: Callable[[], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class InspectSet:
    service: str
    enabled: bool
    port: int | None
    upstream_port: int | None
    proxy_running: bool
    restarted: bool
    error: str | None

    def body(self) -> dict:
        return {
            "service": self.service,
            "enabled": self.enabled,
            "port": self.port,
            "upstream_port": self.upstream_port,
            "proxy_running": self.proxy_running,
            "restarted": self.restarted,
            "error": self.error,
        }


def set_inspect(deps: SetInspectDeps, name: str, enabled: bool) -> InspectSet | OpError:
    """Turn request inspection on or off for a service.

    The hooks' position relative to the container is the constraint: enabling
    runs AFTER_CONTAINER_SWAP so the container has released the public port
    before the proxy claims it; disabling runs BEFORE_CONTAINER_SWAP so the
    proxy releases the port before the container takes it back. The upstream port is kept on disable
    so the allocation does not drift across toggles. Toggling to the state a
    service is already in changes nothing. The metadata event is emitted
    either way. Anything that fails propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return service_not_found(name)

    current = bool(config.get("inspect", False))
    restarted = False
    changed = ServicesChangedContext(name, Cause.INSPECT, [name])

    if enabled and not current:
        config["inspect_upstream_port"] = deps.allocate_upstream_port(compose.list_services_in_db(), name)
        config["inspect"] = True
        compose.update_service_in_db(name, config)
        compose.rebuild_compose_file()
        restarted = deps.recreate_if_running(name).get("restarted", False)
        run_phase(infra.hooks, Phase.AFTER_CONTAINER_SWAP, changed)
    elif not enabled and current:
        config["inspect"] = False
        compose.update_service_in_db(name, config)
        run_phase(infra.hooks, Phase.BEFORE_CONTAINER_SWAP, changed)
        compose.rebuild_compose_file()
        restarted = deps.recreate_if_running(name).get("restarted", False)

    now_inspected = bool(config.get("inspect", False))
    infra.emit({
        "service_name": name,
        "action": "metadata-changed",
        "status": None,
        "container_id": None,
        "metadata": {"inspect": now_inspected},
        "timestamp": infra.now(),
    })

    row = next((r for r in deps.proxy_status() if r["service"] == name), None)
    return InspectSet(
        service=name,
        enabled=now_inspected,
        port=config.get("port"),
        upstream_port=config.get("inspect_upstream_port"),
        proxy_running=bool(row and row["running"]),
        restarted=restarted,
        error=row["error"] if row else None,
    )
