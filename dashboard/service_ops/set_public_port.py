import logging

from .deps import SetPublicPortDeps
from .hooks import Cause, Phase, ServicesChangedContext, run_phase
from .outcomes import AlreadyPublic, OpError, PublicPortSet

logger = logging.getLogger(__name__)


def set_public_port(deps: SetPublicPortDeps, name: str, public_port: int) -> PublicPortSet | AlreadyPublic | OpError:
    """Put a service on the public port, moving every other holder of it to a
    free port first. The compose entries are rewritten and rebuilt, each
    affected running service is recreated (a failure is reported per service,
    not raised), then the hooks reconcile their subsystems. Anything else that
    fails propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return OpError(404, f'Service "{name}" not found')

    current_port = config.get("port")
    if current_port == public_port:
        return AlreadyPublic(name, public_port)

    all_services = compose.list_services_in_db()
    displaced = [
        other for other, cfg in all_services.items()
        if other != name and cfg.get("port") == public_port
    ]

    updates = []
    for other in displaced:
        new_port = deps.next_free_port(all_services, compose.get_used_ports())
        all_services[other]["port"] = new_port
        compose.update_service_in_db(other, all_services[other])
        updates.append({"service": other, "old_port": public_port, "new_port": new_port})

    config["port"] = public_port
    compose.update_service_in_db(name, config)
    updates.append({"service": name, "old_port": current_port, "new_port": public_port})

    compose.rebuild_compose_file()

    restarts = []
    for affected in [name, *displaced]:
        try:
            restarts.append({"service": affected, **deps.recreate_if_running(affected)})
        except Exception as e:
            restarts.append({"service": affected, "restarted": False, "error": str(e)})

    run_phase(
        infra.hooks,
        Phase.AFTER_SERVICES_CHANGED,
        ServicesChangedContext(name, Cause.PUBLIC_PORT, [name, *displaced]),
    )
    logger.info(f"Service {name} now on public port {public_port}")
    return PublicPortSet(name, public_port, updates, restarts)
