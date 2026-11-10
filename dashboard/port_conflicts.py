from dataclasses import dataclass
from typing import Callable, Iterable

PORT_IN_USE = "port_in_use"

DASHBOARD_PORT = 3399

COMPOSE_OWNER = "another compose service"
DASHBOARD_OWNER = "the dashboard"


@dataclass(frozen=True)
class PortOwner:
    service: str
    kind: str

    def describe(self) -> str:
        if self.kind == "compose":
            return COMPOSE_OWNER
        if self.kind == "reserved":
            return DASHBOARD_OWNER
        if self.kind == "inspect_upstream_port":
            return f"the inspector upstream port of service '{self.service}'"
        return f"service '{self.service}'"


def _declared_ports(config: dict) -> list[tuple[int, str]]:
    claimed = []
    for field in ("port", "inspect_upstream_port"):
        value = config.get(field)
        if value is not None:
            claimed.append((int(value), field))
    return claimed


def find_port_owner(
    services: dict,
    port: int,
    exclude: str | None = None,
    compose_ports: Iterable[int] = (),
) -> PortOwner | None:
    port = int(port)
    if port == DASHBOARD_PORT:
        return PortOwner(DASHBOARD_OWNER, "reserved")
    for name, config in services.items():
        if name == exclude:
            continue
        for claimed, kind in _declared_ports(config):
            if claimed == port:
                return PortOwner(name, kind)
    if port in set(compose_ports):
        return PortOwner(COMPOSE_OWNER, "compose")
    return None


def duplicate_ports(services: dict) -> dict[int, list[str]]:
    claimants: dict[int, list[str]] = {}
    for name, config in services.items():
        for claimed, _ in _declared_ports(config):
            claimants.setdefault(claimed, []).append(name)
    return {p: names for p, names in claimants.items() if len(names) > 1}


def conflicts_for(services: dict) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for names in duplicate_ports(services).values():
        for name in names:
            result.setdefault(name, set()).update(set(names) - {name})
    return {name: sorted(others) for name, others in result.items()}


def holds_port(services: dict, name: str, is_running: Callable[[str], bool]) -> bool:
    if is_running(name):
        return True
    config = services[name]
    if not config.get("inspect") or config.get("port") is None:
        return False
    return find_port_owner(services, config["port"], exclude=name) is None


def start_blocker(
    services: dict, name: str, is_running: Callable[[str], bool]
) -> PortOwner | None:
    port = services[name].get("port")
    if port is None:
        return None
    port = int(port)
    for other, config in services.items():
        if other == name:
            continue
        if config.get("port") is not None and int(config["port"]) == port:
            if holds_port(services, other, is_running):
                return PortOwner(other, "port")
        upstream = config.get("inspect_upstream_port")
        if upstream is not None and int(upstream) == port and is_running(other):
            return PortOwner(other, "inspect_upstream_port")
    return None


def next_free_port(
    services: dict, compose_ports: Iterable[int], start: int, end: int
) -> int:
    taken = set(compose_ports) | {DASHBOARD_PORT}
    for config in services.values():
        taken.update(p for p, _ in _declared_ports(config))
    for port in range(start, end + 1):
        if port not in taken:
            return port
    raise ValueError(f"No available ports in range {start}-{end}")


def port_in_use_body(port: int, owner: PortOwner) -> dict:
    return {
        "error": f"Port {int(port)} is already in use by {owner.describe()}",
        "code": PORT_IN_USE,
    }
