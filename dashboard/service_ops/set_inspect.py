import logging

from .deps import SetInspectDeps
from .hooks import Cause, Phase, ServicesChangedContext, run_phase
from .outcomes import InspectSet, OpError

logger = logging.getLogger(__name__)


def set_inspect(deps: SetInspectDeps, name: str, enabled: bool) -> InspectSet | OpError:
    """Turn request inspection on or off for a service.

    The hooks reconcile the proxies right after the services DB changes, and
    their position relative to the container is the constraint: enabling
    recreates the container first so it releases the public port before the
    proxy claims it; disabling reconciles first so the proxy releases the port
    before the container takes it back. The upstream port is kept on disable
    so the allocation does not drift across toggles. Toggling to the state a
    service is already in changes nothing. The metadata event is emitted
    either way. Anything that fails propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return OpError(404, f'Service "{name}" not found')

    current = bool(config.get("inspect", False))
    restarted = False
    changed = ServicesChangedContext(name, Cause.INSPECT, [name])

    if enabled and not current:
        config["inspect_upstream_port"] = deps.allocate_upstream_port(compose.list_services_in_db(), name)
        config["inspect"] = True
        compose.update_service_in_db(name, config)
        compose.rebuild_compose_file()
        restarted = deps.recreate_if_running(name).get("restarted", False)
        run_phase(infra.hooks, Phase.AFTER_SERVICES_CHANGED, changed)
    elif not enabled and current:
        config["inspect"] = False
        compose.update_service_in_db(name, config)
        run_phase(infra.hooks, Phase.AFTER_SERVICES_CHANGED, changed)
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
