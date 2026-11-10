"""HTTP surface for MCP server listing and the default system prompt setting."""

import logging

from flask import jsonify, request

from auth import require_auth

from . import settings_store, url_retrieval
from .app_deps import deps
from .blueprint import chat_bp
from .constants import DEFAULT_MAIN_SYSTEM_PROMPT
from .mcp_registry import list_available_servers

logger = logging.getLogger(__name__)


@chat_bp.route("/api/chat/mcp-servers", methods=["GET"])
@require_auth
def get_mcp_servers():
    servers = list_available_servers()
    if request.args.get(url_retrieval.PROBE_PARAM) == url_retrieval.URL_FETCH_PROBE:
        return jsonify({"servers": servers, "url_fetch": _url_fetch_probe(servers)})
    return jsonify({"servers": servers})


def _url_fetch_probe(servers: list) -> dict:
    """`url_fetch` payload for `?probe=url-fetch` — see chat/url_retrieval.py."""
    try:
        manager = deps().mcp
    except LookupError:
        manager = None

    def discover(server_id: str) -> list:
        if manager is None:
            raise RuntimeError("MCP manager not initialised")
        return manager.discover_bounded(server_id, url_retrieval.PROBE_TIMEOUT)

    return url_retrieval.probe(servers, discover)


# -- Settings: editable default main system prompt --

def _settings_payload() -> dict:
    """Shape returned by every main-system-prompt settings endpoint."""
    return {
        "current": settings_store.get_main_system_prompt(),
        "builtin": DEFAULT_MAIN_SYSTEM_PROMPT,
        "customized": settings_store.is_main_system_prompt_customized(),
    }


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["GET"])
@require_auth
def get_main_system_prompt_setting():
    """Return current default, built-in baseline, and whether they differ.

    The frontend uses ``builtin`` to power the Reset button and
    ``customized`` for the "modified from built-in" indicator without
    needing a client-side string compare.
    """
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["PUT"])
@require_auth
def put_main_system_prompt_setting():
    # get_json(silent=True) returns whatever was parsed — including a bare
    # list/str/number for a non-object body — so guard the type before
    # calling .get(), otherwise a body like [1] would 500 instead of 400.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {content: string}"}), 400
    content = data.get("content")
    if not isinstance(content, str):
        return jsonify({"error": "body must be {content: string}"}), 400
    try:
        settings_store.set_main_system_prompt(content)
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    logger.info("default main_system_prompt updated (%d chars)", len(content))
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["DELETE"])
@require_auth
def delete_main_system_prompt_setting():
    """Drop any customization, reverting new conversations to the built-in."""
    settings_store.reset_main_system_prompt()
    logger.info("default main_system_prompt reset to built-in")
    return jsonify(_settings_payload())
