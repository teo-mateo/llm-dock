from dataclasses import dataclass

import flag_surfaces
from flag_metadata import validate_service_config
from port_conflicts import PortOwner, find_port_owner

from .deps import ComposeStore


@dataclass(frozen=True)
class ValidationFailed:
    details: list


@dataclass(frozen=True)
class PortInUse:
    port: int
    owner: PortOwner


def validate(template_type: str, data: dict) -> ValidationFailed | None:
    valid, errors = validate_service_config(template_type, data)
    return None if valid else ValidationFailed(errors)


def port_conflict(compose: ComposeStore, port: int, exclude: str | None = None) -> PortInUse | None:
    owner = find_port_owner(
        compose.list_services_in_db(), port, exclude=exclude, compose_ports=compose.get_used_ports()
    )
    return PortInUse(port, owner) if owner else None


def unknown_flag_warnings(template_type: str, params) -> list[str]:
    """Advisory only: the flag still ships to the container verbatim, so an
    unknown one warns instead of rejecting the write. A typo or an
    upstream-removed flag otherwise fails at container startup."""
    return [
        f"Unknown {template_type} flag: {flag} (not in the engine's recorded "
        f"flag surface; it will be passed through and may fail at startup)"
        for flag in flag_surfaces.unknown_service_params(template_type, params)
    ]
