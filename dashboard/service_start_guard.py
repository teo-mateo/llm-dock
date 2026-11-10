from typing import Mapping

from port_conflicts import port_in_use_body, start_blocker


def current_statuses() -> dict[str, str]:
    from docker_utils import get_docker_services

    return {s["name"]: s["status"] for s in get_docker_services()}


def check_start(services: dict, name: str, statuses: Mapping[str, str]) -> dict | None:
    if name not in services:
        return None
    owner = start_blocker(services, name, lambda n: statuses.get(n) == "running")
    if owner is None:
        return None
    return port_in_use_body(services[name]["port"], owner)


def finish_start(services: dict, name: str) -> None:
    if services.get(name, {}).get("inspect"):
        from inspector.supervisor import proxy_supervisor

        proxy_supervisor.sync()
