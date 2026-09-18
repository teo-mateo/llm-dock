UPSTREAM_PORT_BAND = range(34000, 35000)


def allocate_upstream_port(services: dict, service_name: str) -> int:
    config = services.get(service_name, {})
    existing = config.get("inspect_upstream_port")
    if existing is not None:
        return int(existing)

    taken = set()
    for svc in services.values():
        if svc.get("port") is not None:
            taken.add(int(svc["port"]))
        if svc.get("inspect_upstream_port") is not None:
            taken.add(int(svc["inspect_upstream_port"]))

    for port in UPSTREAM_PORT_BAND:
        if port not in taken:
            return port
    raise ValueError(
        f"No free inspector upstream port in {UPSTREAM_PORT_BAND.start}-{UPSTREAM_PORT_BAND.stop - 1}"
    )
