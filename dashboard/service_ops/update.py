import logging
from dataclasses import dataclass, field
from typing import Callable

from flag_metadata import plan_image_change
from reasoning_levels import parse_levels

from .config_checks import PortInUse, ValidationFailed, port_conflict, unknown_flag_warnings, validate
from .deps import Infra
from .errors import ErrorKind, OpError, service_not_found
from .hooks import Cause, Phase, ServicesChangedContext, run_phase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateDeps:
    """recreate_for_image(name, container_status, finish) rebuilds the compose
    file and recreates the container if it runs, calling finish once the
    container is settled; it returns {"restarted": bool, "error"?: str}."""

    infra: Infra
    image_presence_warnings: Callable[[str | None], list]
    recreate_for_image: Callable[[str, str, Callable[[], None]], dict]
    reported_image: Callable[[str | None, str], str]


@dataclass(frozen=True)
class Updated:
    name: str
    configured_image: str
    restarted: bool = False
    recreate_error: str | None = None
    warnings: list = field(default_factory=list)


def update(deps: UpdateDeps, name: str, data: dict) -> Updated | ValidationFailed | PortInUse | OpError:
    """Merge a config change into a service and apply it.

    The engine cannot change, and inspect_upstream_port is server-owned: a
    value in the body is dropped, never stored. The body is merged into the
    stored entry, so a field the client did not send survives, and the flag
    warnings are computed over the merged params so a typo stored earlier
    surfaces on the next write.

    The hooks run AFTER_CONTAINER_SWAP. With the image unchanged that is right
    after the compose rebuild, and no container is touched. With a new image
    the container is recreated if it runs, and the hooks run when that
    settles, including after a failed recreate or a failed rebuild; a service
    blocked from starting is neither rebuilt nor reconciled. A failed recreate
    is reported in the outcome, anything else that fails propagates."""
    infra = deps.infra
    compose = infra.compose()
    existing = compose.get_service_from_db(name)
    if not existing:
        return service_not_found(name)

    if "template_type" in data and data["template_type"] != existing["template_type"]:
        return OpError(ErrorKind.INVALID, "Cannot change template_type of existing service")

    template_type = existing["template_type"]
    data["template_type"] = template_type
    data.pop("inspect_upstream_port", None)

    invalid = validate(template_type, data)
    if invalid:
        return invalid

    if "port" in data and int(data["port"]) != int(existing.get("port", 0)):
        conflict = port_conflict(compose, int(data["port"]), exclude=name)
        if conflict:
            return conflict

    before = dict(existing)
    existing.update(data)
    plan = plan_image_change(template_type, before, existing)
    compose.update_service_in_db(name, existing)

    warnings = unknown_flag_warnings(template_type, existing.get("params"))
    if warnings:
        logger.warning(f"Service {name} update with unknown {template_type} flags: {warnings}")
    if plan.changed:
        warnings += deps.image_presence_warnings(existing.get("image"))

    container = infra.get_container(name)

    def reconcile() -> None:
        run_phase(infra.hooks, Phase.AFTER_CONTAINER_SWAP, ServicesChangedContext(name, Cause.UPDATE, [name]))

    restarted = False
    recreate_error = None
    metadata = {"reasoning_levels": parse_levels(existing.get("reasoning_levels"))}
    if not plan.changed:
        compose.rebuild_compose_file()
        reconcile()
    else:
        status = container.status if container else "not-created"
        result = deps.recreate_for_image(name, status, reconcile)
        restarted = bool(result["restarted"])
        recreate_error = result.get("error")
        current = container.attrs["Config"]["Image"] if container else None
        metadata["image"] = deps.reported_image(None if restarted else current, plan.new_image)

    infra.emit({
        "service_name": name,
        "action": "metadata-changed",
        "status": None,
        "container_id": None,
        "metadata": metadata,
        "timestamp": infra.now(),
    })
    logger.info(f"Service updated: {name}")
    return Updated(name, plan.new_image, restarted, recreate_error, warnings)
