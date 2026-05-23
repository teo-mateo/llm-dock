"""Admin endpoints for the declarative MCP registry.

Mounted on the same `chat_bp` blueprint as the rest of the chat API. All
routes require the standard bearer auth. None of these handlers echo
process environment or secrets back to the client — the only things
returned are the configured `command` + `args` (which are paths the user
already chose) and tool metadata produced by the MCP server itself.
"""

import json
import logging
import os
from concurrent.futures import TimeoutError as FuturesTimeoutError

from flask import current_app, jsonify, request

from auth import require_auth
from . import mcp_config
from .mcp_client import MCPClientManager
from .mcp_registry import MCP_SERVERS as BUILTIN
from .routes import chat_bp

logger = logging.getLogger(__name__)

DISCOVER_TIMEOUT = 5.0
CALL_TIMEOUT = 10.0


def _get_mcp() -> MCPClientManager:
    return current_app.config["MCP_MANAGER"]


def _registry_view(state: dict) -> dict:
    """Build the public registry view.

    Built-in entries don't include `command` — it's a Python path inside
    the repo, uninteresting to the user and just noise in the UI. External
    entries include their command + args (the configured executable path
    is the whole point of the external registry).
    """
    servers = []
    merged = state["merged"]
    for sid, cfg in merged.items():
        is_builtin = sid in BUILTIN and not cfg.get("external")
        entry = {
            "id": sid,
            "name": cfg["name"],
            "description": cfg["description"],
            "icon": cfg["icon"],
            "source": "built-in" if is_builtin else "external",
            "enabled": bool(cfg.get("enabled", True)),
        }
        if not is_builtin:
            transport = cfg.get("transport", "stdio")
            entry["transport"] = transport
            if transport == "http":
                entry["url"] = cfg.get("url", "")
                entry["headers"] = dict(cfg.get("headers") or {})
                # HTTP entries have no on-disk presence to check; the
                # field stays True so the existing "no command" badge in
                # the UI doesn't fire spuriously.
                entry["command_exists"] = True
            else:
                cmd = cfg["command"]
                entry["command"] = cmd[0]
                entry["args"] = cmd[1:]
                entry["command_exists"] = bool(cmd) and os.path.exists(cmd[0])
        else:
            entry["transport"] = "stdio"
            entry["command_exists"] = True
        servers.append(entry)
    return {
        "servers": servers,
        "external_errors": list(state.get("external_errors", [])),
        "load_error": state.get("load_error"),
        "config_file": mcp_config.config_file_path(),
    }


@chat_bp.route("/api/chat/mcp-registry", methods=["GET"])
@require_auth
def get_mcp_registry():
    return jsonify(_registry_view(mcp_config.get_state()))


@chat_bp.route("/api/chat/mcp-registry/json", methods=["GET"])
@require_auth
def get_mcp_registry_json():
    path = mcp_config.config_file_path()
    if not os.path.exists(path):
        return jsonify({"content": "", "path": path})
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError as e:
        return jsonify({"error": f"cannot read {path}: {e}"}), 500
    return jsonify({"content": content, "path": path})


@chat_bp.route("/api/chat/mcp-registry/json", methods=["PUT"])
@require_auth
def put_mcp_registry_json():
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    if not isinstance(content, str):
        return jsonify({"error": "body must be {content: string}"}), 400

    ok, errors, load_error = mcp_config.write_external_json(content)
    if not ok:
        body = {"error": "validation failed"}
        if errors:
            body["entry_errors"] = errors
        if load_error:
            body["load_error"] = load_error
        return jsonify(body), 400

    return jsonify(_registry_view(mcp_config.get_state()))


@chat_bp.route("/api/chat/mcp-registry/reload", methods=["POST"])
@require_auth
def reload_mcp_registry():
    state = mcp_config.reload()
    return jsonify(_registry_view(state))


@chat_bp.route("/api/chat/mcp-registry/test", methods=["POST"])
@require_auth
def test_mcp_registry():
    data = request.get_json(silent=True) or {}
    server_id = data.get("server_id")
    tool_name = data.get("tool_name")
    arguments = data.get("arguments") or {}

    if not isinstance(server_id, str) or not server_id:
        return jsonify({"error": "server_id is required"}), 400
    if tool_name is not None and not isinstance(tool_name, str):
        return jsonify({"error": "tool_name must be a string"}), 400
    if not isinstance(arguments, dict):
        return jsonify({"error": "arguments must be an object"}), 400

    cfg = mcp_config.get_config(server_id)
    if cfg is None:
        return jsonify({"error": f"unknown or disabled server '{server_id}'"}), 404

    mgr = _get_mcp()

    if tool_name is None:
        # Discovery — list_tools only.
        try:
            tools = mgr.run_with_timeout(mgr._discover_tools(cfg, server_id), DISCOVER_TIMEOUT)
        except FuturesTimeoutError:
            return jsonify({"ok": False, "error": f"timed out after {DISCOVER_TIMEOUT}s"}), 200
        except Exception as e:
            logger.exception("MCP test discover failed for %s", server_id)
            return jsonify({"ok": False, "error": str(e)}), 200
        return jsonify({
            "ok": True,
            "tools": [
                {
                    "name": t["function"]["name"].split("__", 1)[-1],
                    "namespaced_name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"].get("parameters", {}),
                }
                for t in tools
            ],
        })

    # Call.
    try:
        result_text, artifacts = mgr.run_with_timeout(
            mgr._execute_tool(cfg, tool_name, arguments), CALL_TIMEOUT
        )
    except FuturesTimeoutError:
        return jsonify({"ok": False, "error": f"timed out after {CALL_TIMEOUT}s"}), 200
    except Exception as e:
        logger.exception("MCP test call failed for %s.%s", server_id, tool_name)
        return jsonify({"ok": False, "error": str(e)}), 200

    return jsonify({
        "ok": True,
        "result_text": result_text,
        "artifacts": [
            {
                "type": a.get("type"),
                "title": a.get("title"),
                "language": a.get("language"),
                "content_size": len(a.get("content", "")) if isinstance(a.get("content"), str) else 0,
            }
            for a in artifacts
        ],
    })
