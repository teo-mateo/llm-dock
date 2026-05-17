"""Default API-key rotation.

The "default API key" is the single shared key every model service in
``services.json`` authenticates with, mirrored into ``LLM_DOCK_API_KEY`` in
``.env``. Rotating it rewrites every service entry, regenerates the compose
file, and (at the route layer) stops any running containers so they don't keep
serving with the now-revoked key still held in memory.

This module holds the pure, file-level mutation so it can be unit tested
without Docker.
"""

import logging

from service_templates import generate_api_key

logger = logging.getLogger(__name__)


def rotate_keys_in_db(compose_mgr, new_key: str | None = None) -> dict:
    """Set every service's ``api_key`` to ``new_key`` and rebuild compose.

    Args:
        compose_mgr: a :class:`ComposeManager` bound to the target
            ``docker-compose.yml`` / ``services.json``.
        new_key: the key to apply. Generated if not supplied.

    Returns:
        ``{"new_key": str, "updated": [service_name, ...]}`` — ``updated`` lists
        services whose key actually changed (already-matching entries are left
        untouched, but compose is still rebuilt for consistency).
    """
    if not new_key:
        new_key = generate_api_key()

    services = compose_mgr.list_services_in_db()
    updated = []
    for name, config in services.items():
        if config.get("api_key") != new_key:
            config["api_key"] = new_key
            compose_mgr.update_service_in_db(name, config)
            updated.append(name)

    compose_mgr.rebuild_compose_file()
    logger.info(
        "Rotated default API key across %d service(s) (%d changed)",
        len(services),
        len(updated),
    )
    return {"new_key": new_key, "updated": updated}
