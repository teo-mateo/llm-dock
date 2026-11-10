import logging
from dataclasses import dataclass

from service_names import validate_rename

from .deps import Infra
from .errors import ErrorKind, OpError, service_not_found
from .hooks import Phase, RenameContext, run_phase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenameDeps:
    infra: Infra


@dataclass(frozen=True)
class Renamed:
    old_name: str
    new_name: str


def rename(deps: RenameDeps, name: str, new_name: str) -> Renamed | OpError:
    """Rename a stopped service. A refused name is a 400 before any side effect;
    then the hooks, the old container, the compose DB and the hooks that follow
    it. A ValueError from the compose DB is still a 400; anything else
    propagates."""
    infra = deps.infra
    compose = infra.compose()
    config = compose.get_service_from_db(name)
    if not config:
        return service_not_found(name)

    container = infra.get_container(name)
    if container and container.status == "running":
        return OpError(ErrorKind.CONFLICT, "Service must be stopped before renaming")

    refusal = validate_rename(name, new_name, compose.list_services_in_db())
    if refusal:
        return OpError(ErrorKind.INVALID, refusal)

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
        return OpError(ErrorKind.INVALID, str(e))

    run_phase(infra.hooks, Phase.AFTER_RENAME, ctx)
    logger.info(f"Service renamed: {name} -> {new_name}")
    return Renamed(name, new_name)
