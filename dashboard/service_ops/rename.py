import logging

from .deps import ServiceOpsDeps
from .hooks import RenameContext, run_phase
from .outcomes import OpError, Renamed

logger = logging.getLogger(__name__)


def rename(deps: ServiceOpsDeps, name: str, new_name: str) -> Renamed | OpError:
    """Rename a stopped service: hooks first, the old container, the compose
    DB, then the hooks that follow it. Anything but a ValueError from the
    compose DB (an invalid or taken name) propagates."""
    compose = deps.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return OpError(404, f'Service "{name}" not found')

    container = deps.get_container(name)
    if container and container.status == "running":
        return OpError(409, "Service must be stopped before renaming")

    ctx = RenameContext(name, new_name, config)
    run_phase(deps.hooks, "before_rename", ctx)

    if container:
        try:
            deps.remove_container(name)
        except Exception as e:
            logger.warning(f"Failed to remove old container: {e}")

    try:
        compose.rename_service(name, new_name)
    except ValueError as e:
        return OpError(400, str(e))

    run_phase(deps.hooks, "after_rename", ctx)
    logger.info(f"Service renamed: {name} -> {new_name}")
    return Renamed(name, new_name)
