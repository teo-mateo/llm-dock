from port_conflicts import next_free_port

UPSTREAM_PORT_BAND = range(34000, 35000)


def allocate_upstream_port(services: dict, service_name: str) -> int:
    existing = services.get(service_name, {}).get("inspect_upstream_port")
    if existing is not None:
        return int(existing)
    return next_free_port(services, (), UPSTREAM_PORT_BAND.start, UPSTREAM_PORT_BAND.stop - 1)
