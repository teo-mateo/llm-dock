import logging

from .deps import DeleteDeps
from .hooks import Cause, Phase, ServicesChangedContext, run_phase
from .outcomes import Deleted, OpError

logger = logging.getLogger(__name__)


def delete(deps: DeleteDeps, name: str) -> Deleted | OpError:
    """Delete a service: its container (best-effort, stop then remove), its DB
    entry and compose section, the hooks that follow, then the deleted event.
    Everything outside the container removal and the best-effort hooks
    propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return OpError(404, f'Service "{name}" not found')

    try:
        deps.stop_container(name)
        infra.remove_container(name)
        logger.info(f"Stopped and removed container for: {name}")
    except Exception as e:
        logger.warning(f"Error stopping container (may not be running): {e}")

    compose.remove_service_from_db(name)
    compose.rebuild_compose_file()
    run_phase(
        infra.hooks, Phase.AFTER_SERVICES_CHANGED,
        ServicesChangedContext(name, Cause.DELETE, [name]),
    )

    infra.emit({
        "service_name": name,
        "action": "service-deleted",
        "status": "deleted",
        "container_id": "",
        "timestamp": infra.now(),
    })
    logger.info(f"Service deleted: {name}")
    return Deleted(name)
