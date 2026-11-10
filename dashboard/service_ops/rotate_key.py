import logging

from .deps import RotateKeyDeps
from .outcomes import KeyRotated

logger = logging.getLogger(__name__)


def rotate_key(deps: RotateKeyDeps) -> KeyRotated:
    """Rotate the default API key across every service.

    The order is the safety property. services.json and the compose file are
    committed first, and deps.rotate_in_db undoes them itself if that fails,
    so a failure leaves .env untouched. The key is committed second; if that
    fails the services.json and compose changes are undone, so the process
    never advertises a key the files do not hold. Running containers are
    stopped last, because they keep the revoked key in memory; a failed stop
    is reported per container, anything that raises propagates. The caller
    holds the services DB lock across the whole operation."""
    db_services, running, openwebui_registered = deps.affected_state()

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
    for name in running:
        res = deps.stop_service(name)
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
        total_services=len(db_services),
        stopped=stopped,
        stop_errors=stop_errors,
        openwebui_registered=openwebui_registered,
    )
