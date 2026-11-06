import os
from typing import Optional

DEFAULT_SOCKET_PATH = os.path.expanduser("~/.cache/pi-remote/pi-remote.sock")
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pi_remote.db"
)


def resolve_socket_path(value: Optional[str] = None) -> str:
    if value:
        return os.path.expanduser(value)
    return os.path.expanduser(
        os.environ.get("LLM_DOCK_PI_REMOTE_SOCKET") or DEFAULT_SOCKET_PATH
    )


def resolve_db_path(value: Optional[str] = None) -> str:
    if value:
        return os.path.expanduser(value)
    return os.path.expanduser(os.environ.get("LLM_DOCK_PI_REMOTE_DB") or DEFAULT_DB_PATH)
