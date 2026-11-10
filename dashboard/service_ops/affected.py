def affected_services(db_names, docker_services) -> tuple[list, list, list]:
    """Return (db_service_names, running, openwebui_registered), each sorted.

    Only services present in services.json are affected by a rotation; infra
    containers like open-webui are never in services.json so they are
    excluded naturally."""
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

    return sorted(db_services), sorted(running), sorted(openwebui_registered)
