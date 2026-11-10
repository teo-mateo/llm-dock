import logging

from service_names import validate_rename

from .deps import RenameDeps
from .hooks import Phase, RenameContext, run_phase
from .outcomes import OpError, Renamed

logger = logging.getLogger(__name__)


def rename(deps: RenameDeps, name: str, new_name: str) -> Renamed | OpError:
    """Rename a stopped service. A refused name is a 400 before any side effect;
    then the hooks, the old container, the compose DB and the hooks that follow
    it. A ValueError from the compose DB is still a 400; anything else
    propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return OpError(404, f'Service "{name}" not found')

    container = infra.get_container(name)
    if container and container.status == "running":
        return OpError(409, "Service must be stopped before renaming")

    refusal = validate_rename(name, new_name, compose.list_services_in_db())
    if refusal:
        return OpError(400, refusal)

    ctx = RenameContext(name, new_name, config)
    run_phase(infra.hooks, Phase.BEFORE_RENAME, ctx)

    if container:
        try:
            infra.remove_container(name)
        except Exception as e:
            logger.warning(f"Failed to remove old container: {e}")

    try:
        compose.rename_service(name, new_name)
    except ValueError as e:
        return OpError(400, str(e))

    run_phase(infra.hooks, Phase.AFTER_RENAME, ctx)
    logger.info(f"Service renamed: {name} -> {new_name}")
    return Renamed(name, new_name)
