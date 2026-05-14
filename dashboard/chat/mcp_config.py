"""Declarative MCP server registry.

Merges built-in MCP servers (defined in `mcp_registry.MCP_SERVERS`) with
external servers declared in a JSON file on disk. The chat side of the app
keeps talking to `mcp_registry`'s public API; this module is what backs it.

External servers cover the case where the server lives outside this repo
(its own venv, its own path, machine-local). They're declared in
`LLM_DOCK_MCP_SERVERS_FILE` (default `dashboard/mcp_servers.json`) instead
of in Python, so adding one is a config edit, not a code change + restart.
"""

import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_servers.json",
)

REQUIRED_FIELDS = ("name", "description", "command", "args", "icon", "tool_hint")

_lock = threading.Lock()
_state = {
    "merged": {},          # id -> normalized config dict
    "external_errors": [], # [{"entry_id": str|None, "message": str}]
    "load_error": None,    # top-level parse error string, if any
}

# Reference to the chat app's MCPClientManager. Set by `bind_manager` at
# startup so reload() can invalidate the tool cache.
_manager = None


def config_file_path() -> str:
    return os.environ.get("LLM_DOCK_MCP_SERVERS_FILE", DEFAULT_CONFIG_FILE)


def bind_manager(manager) -> None:
    """Wire the MCPClientManager so reload() can drop its tool cache."""
    global _manager
    _manager = manager


def _validate_entry(server_id: str, entry: dict, builtin_ids: set) -> Optional[str]:
    """Return None if valid, otherwise an error message."""
    if not isinstance(server_id, str) or not server_id:
        return "id must be a non-empty string"
    if "__" in server_id:
        return "id must not contain '__' (collides with tool-name namespacing)"
    if server_id in builtin_ids:
        return f"id '{server_id}' collides with a built-in server"
    if not isinstance(entry, dict):
        return "entry must be a JSON object"
    for field in REQUIRED_FIELDS:
        if field not in entry:
            return f"missing required field '{field}'"
    for field in ("name", "description", "icon", "tool_hint"):
        if not isinstance(entry[field], str) or not entry[field]:
            return f"field '{field}' must be a non-empty string"
    if not isinstance(entry["command"], str) or not entry["command"]:
        return "field 'command' must be a non-empty string"
    if not os.path.isabs(entry["command"]):
        return "field 'command' must be an absolute path"
    if not isinstance(entry["args"], list) or not all(isinstance(a, str) for a in entry["args"]):
        return "field 'args' must be a list of strings"
    if "enabled" in entry and not isinstance(entry["enabled"], bool):
        return "field 'enabled' must be a boolean"
    return None


def _normalize_external(server_id: str, entry: dict) -> dict:
    return {
        "name": entry["name"],
        "description": entry["description"],
        "command": [entry["command"], *entry["args"]],
        "icon": entry["icon"],
        "tool_hint": entry["tool_hint"],
        "external": True,
        "enabled": entry.get("enabled", True),
    }


def _load_external(builtin_ids: set):
    """Read and validate the external file. Returns (entries, errors, load_error)."""
    path = config_file_path()
    if not os.path.exists(path):
        return {}, [], None

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {}, [], f"{path}: invalid JSON: {e}"
    except OSError as e:
        return {}, [], f"{path}: cannot read: {e}"

    if not isinstance(data, dict):
        return {}, [], f"{path}: top-level must be a JSON object keyed by server id"

    entries = {}
    errors = []
    for server_id, entry in data.items():
        err = _validate_entry(server_id, entry, builtin_ids)
        if err is not None:
            errors.append({"entry_id": server_id, "message": err})
            continue
        entries[server_id] = _normalize_external(server_id, entry)
    return entries, errors, None


def _merge(builtin: dict, external: dict) -> dict:
    merged = {sid: {**cfg, "external": False, "enabled": True} for sid, cfg in builtin.items()}
    for sid, cfg in external.items():
        merged[sid] = cfg
    return merged


def reload() -> dict:
    """Re-read the external file, refresh the merged registry, drop tool cache.

    Returns the new state dict (merged + external_errors + load_error).
    Safe to call from any thread.
    """
    from .mcp_registry import MCP_SERVERS as BUILTIN

    with _lock:
        builtin_ids = set(BUILTIN.keys())
        external, errors, load_error = _load_external(builtin_ids)

        # On a top-level parse error: keep the previous external entries
        # (the user is editing the file), but always re-merge built-ins so
        # they survive even on a first-time load against a broken file.
        if load_error is not None:
            previous_external = {
                sid: cfg for sid, cfg in _state["merged"].items() if cfg.get("external")
            }
            _state["merged"] = _merge(BUILTIN, previous_external)
            _state["load_error"] = load_error
            _state["external_errors"] = []
            logger.warning("MCP registry external file failed to load: %s", load_error)
            return _snapshot_locked()

        _state["merged"] = _merge(BUILTIN, external)
        _state["external_errors"] = errors
        _state["load_error"] = None
        for err in errors:
            logger.warning("MCP registry external entry '%s' invalid: %s", err["entry_id"], err["message"])

        if _manager is not None:
            _manager.invalidate_cache()
        return _snapshot_locked()


def _snapshot_locked() -> dict:
    return {
        "merged": dict(_state["merged"]),
        "external_errors": list(_state["external_errors"]),
        "load_error": _state["load_error"],
    }


def get_registry() -> dict:
    """Return the full merged registry (built-in + external, enabled and not)."""
    with _lock:
        if not _state["merged"]:
            # Lazy init on first read so callers don't have to remember to
            # invoke reload() at startup. After this the explicit reload()
            # is what refreshes state.
            pass
    if not _state["merged"] and _state["load_error"] is None:
        reload()
    with _lock:
        return dict(_state["merged"])


def get_state() -> dict:
    """Return a snapshot of the merged registry + any validation errors."""
    if not _state["merged"] and _state["load_error"] is None:
        reload()
    with _lock:
        return _snapshot_locked()


def _chat_available(cfg: dict) -> bool:
    """Is this entry usable from the chat path?

    Built-in entries are always available. External entries must be enabled
    AND have an existing command on disk — otherwise the model would be
    told it has a tool that tool discovery can't actually surface, risking
    fabricated "I used the tool" answers. The Tools page reads the raw
    state and still shows unavailable external entries so the user can
    debug them.
    """
    if not cfg.get("enabled", True):
        return False
    if not cfg.get("external"):
        return True
    command = cfg.get("command") or []
    return bool(command) and os.path.exists(command[0])


def get_config(server_id: str) -> Optional[dict]:
    """Return config for a chat-available server, or None."""
    reg = get_registry()
    cfg = reg.get(server_id)
    if cfg is None or not _chat_available(cfg):
        return None
    return cfg


def list_enabled() -> list:
    """Return [{id, name, description, icon}] for chat-available servers."""
    reg = get_registry()
    return [
        {"id": sid, "name": cfg["name"], "description": cfg["description"], "icon": cfg["icon"]}
        for sid, cfg in reg.items()
        if _chat_available(cfg)
    ]


def write_external_json(content: str) -> tuple:
    """Validate and atomically write the external JSON file.

    Returns (ok: bool, errors: list[dict], load_error: str|None).
    On success, the file is replaced and the registry is reloaded.
    On failure, the file is left untouched.
    """
    from .mcp_registry import MCP_SERVERS as BUILTIN

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, [], f"invalid JSON: {e}"

    if not isinstance(data, dict):
        return False, [], "top-level must be a JSON object keyed by server id"

    builtin_ids = set(BUILTIN.keys())
    errors = []
    for server_id, entry in data.items():
        err = _validate_entry(server_id, entry, builtin_ids)
        if err is not None:
            errors.append({"entry_id": server_id, "message": err})
    if errors:
        return False, errors, None

    path = config_file_path()
    # Atomic write: tempfile in same dir, then os.replace. Same-dir is
    # required so rename stays on one filesystem.
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except OSError as e:
        # Best-effort cleanup of the tempfile.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False, [], f"failed to write {path}: {e}"

    reload()
    return True, [], None
