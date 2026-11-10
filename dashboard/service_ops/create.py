import logging
from dataclasses import dataclass, field
from typing import Callable

from flag_metadata import SERVICE_ENGINES, effective_image, generate_service_name, service_engines_message

from .config_checks import PortInUse, ValidationFailed, port_conflict, unknown_flag_warnings, validate
from .deps import Infra
from .errors import ErrorKind, OpError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreateDeps:
    infra: Infra
    generate_key: Callable[[], str]
    image_presence_warnings: Callable[[str | None], list]


@dataclass(frozen=True)
class Created:
    name: str
    port: int
    api_key: str
    configured_image: str
    warnings: list = field(default_factory=list)


def create(deps: CreateDeps, data: dict) -> Created | ValidationFailed | PortInUse | OpError:
    """Add a service to the services DB and rebuild the compose file.

    A missing key is generated. inspect_upstream_port is server-owned: a value
    in the body is dropped, never stored. The name comes from the engine and
    the alias, and an existing name is refused before the port is checked.
    Nothing is started and no event is emitted. A failure of the DB write or
    the rebuild propagates."""
    template_type = data.get("template_type")
    if not template_type:
        return OpError(ErrorKind.INVALID, "template_type is required")
    if template_type not in SERVICE_ENGINES:
        return OpError(ErrorKind.INVALID, service_engines_message())

    if not data.get("api_key"):
        data["api_key"] = deps.generate_key()
    data.pop("inspect_upstream_port", None)

    invalid = validate(template_type, data)
    if invalid:
        return invalid

    warnings = unknown_flag_warnings(template_type, data.get("params"))
    if warnings:
        logger.warning(f"Service create with unknown {template_type} flags: {warnings}")
    warnings += deps.image_presence_warnings(data.get("image"))

    name = generate_service_name(template_type, data.get("alias"))
    compose = deps.infra.compose()
    if compose.get_service_from_db(name):
        return OpError(ErrorKind.CONFLICT, f'Service "{name}" already exists')

    port = int(data["port"])
    conflict = port_conflict(compose, port)
    if conflict:
        return conflict

    compose.add_service_to_db(name, data)
    compose.rebuild_compose_file()

    logger.info(f"Service created: {name} on port {port}")
    return Created(name, port, data["api_key"], effective_image(template_type, data), warnings)
