import logging
from dataclasses import dataclass, field
from typing import Callable

from .affected import AffectedState
from .deps import ComposeStore, Infra

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RotateKeyDeps:
    infra: Infra
    affected_state: Callable[[], AffectedState]
    generate_key: Callable[[], str]
    rotate_in_db: Callable[[ComposeStore, str], dict]
    commit_key: Callable[[str], None]
    stop_service: Callable[[str], dict]


@dataclass(frozen=True)
class KeyRotated:
    """A stop that failed leaves a container accepting the OLD key, so the
    rotation is then partial rather than a success."""

    new_key: str
    updated: list
    total_services: int
    stopped: list
    stop_errors: dict
    openwebui_registered: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stop_errors

    def message(self) -> str:
        if self.ok:
            return (
                f"Default API key rotated across {len(self.updated)} "
                f"service(s); {len(self.stopped)} running container(s) stopped."
            )
        return (
            f"Default API key rotated across {len(self.updated)} "
            f"service(s), but {len(self.stop_errors)} running container(s) "
            f"could NOT be stopped and still accept the OLD key — stop "
            f"them manually: {', '.join(sorted(self.stop_errors))}."
        )

    def body(self) -> dict:
        return {
            "success": self.ok,
            "partial": not self.ok,
            "new_api_key": self.new_key,
            "services_updated": len(self.updated),
            "total_services": self.total_services,
            "stopped": self.stopped,
            "stop_errors": self.stop_errors,
            "openwebui_registered": self.openwebui_registered,
            "message": self.message(),
        }


def rotate_key(deps: RotateKeyDeps) -> KeyRotated:
    """Rotate the default API key across every service.

    The order is the safety property. services.json and the compose file are
    committed first, and deps.rotate_in_db undoes them itself if that fails,
    so a failure leaves .env untouched. The key is committed second; if that
    fails the services.json and compose changes are undone, so the process
    never advertises a key the files do not hold. Running containers are
    stopped last, because they keep the revoked key in memory. A stop that
    fails or raises is reported per container and never keeps the others from
    stopping or the new key from reaching the caller.

    The caller holds the services DB lock across the whole operation."""
    state = deps.affected_state()

    new_key = deps.generate_key()
    compose = deps.infra.compose()
    services_before = compose.list_services_in_db()

    result = deps.rotate_in_db(compose, new_key)

    try:
        deps.commit_key(new_key)
    except Exception:
        compose.save_services_db(services_before)
        compose.rebuild_compose_file()
        raise

    stopped = []
    stop_errors = {}
    for name in state.running:
        try:
            res = deps.stop_service(name)
        except Exception as e:
            stop_errors[name] = str(e)
            continue
        if res.get("success"):
            stopped.append(name)
        else:
            stop_errors[name] = res.get("error", "unknown error")

    logger.info(
        "Default API key rotated: %d services updated, %d stopped, %d stop failures",
        len(result["updated"]),
        len(stopped),
        len(stop_errors),
    )
    return KeyRotated(
        new_key=new_key,
        updated=result["updated"],
        total_services=len(state.services),
        stopped=stopped,
        stop_errors=stop_errors,
        openwebui_registered=state.openwebui_registered,
    )
