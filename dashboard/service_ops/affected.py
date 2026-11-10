from dataclasses import dataclass


@dataclass(frozen=True)
class AffectedState:
    """What a default-key rotation touches: every service in services.json,
    which of them run, and which are registered with Open WebUI."""

    services: list
    running: list
    openwebui_registered: list


def affected_services(db_names, docker_services) -> AffectedState:
    """Only services present in services.json are affected by a rotation; infra
    containers like open-webui are never in services.json so they are
    excluded naturally. Every list is sorted."""
    db_services = set(db_names)
    running = []
    openwebui_registered = []
    for svc in docker_services:
        name = svc["name"]
        if name not in db_services:
            continue
        if svc.get("status") == "running":
            running.append(name)
        if svc.get("openwebui_registered"):
            openwebui_registered.append(name)

    return AffectedState(sorted(db_services), sorted(running), sorted(openwebui_registered))
