import os
import socket
import stat
from typing import Optional


def ensure_directory(socket_path: str) -> Optional[str]:
    parent = os.path.dirname(socket_path) or "."
    try:
        if not os.path.isdir(parent):
            os.makedirs(parent, mode=0o700)
            os.chmod(parent, 0o700)
    except OSError as exc:
        return f"cannot create socket directory {parent}: {exc}"
    try:
        mode = stat.S_IMODE(os.stat(parent).st_mode)
    except OSError as exc:
        return f"cannot stat socket directory {parent}: {exc}"
    if mode & 0o077:
        return f"socket directory {parent} must be mode 0700, found {oct(mode)}"
    return None


def socket_is_live(path: str) -> bool:
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        probe.connect(path)
        return True
    except OSError:
        return False
    finally:
        probe.close()


def clear_stale_socket(path: str) -> Optional[str]:
    if not os.path.lexists(path):
        return None
    if socket_is_live(path):
        return f"socket {path} is already in use"
    try:
        os.unlink(path)
    except OSError as exc:
        return f"cannot remove stale socket {path}: {exc}"
    return None
