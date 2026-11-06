import logging
import os
import threading
import time
from typing import Any, Optional, Tuple

from .handler import PiRemoteHandler
from .listener import UdsListener
from .registry import PresenceRegistry
from .store import PiRemoteDB

logger = logging.getLogger(__name__)

DEFAULT_SOCKET = os.path.expanduser("~/.cache/pi-remote/pi-remote.sock")
DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pi_remote.db"
)


def resolve_socket_path(value: Optional[str] = None) -> str:
    if value:
        return os.path.expanduser(value)
    return os.path.expanduser(
        os.environ.get("LLM_DOCK_PI_REMOTE_SOCKET") or DEFAULT_SOCKET
    )


def resolve_db_path(value: Optional[str] = None) -> str:
    if value:
        return value
    return os.environ.get("LLM_DOCK_PI_REMOTE_DB") or DEFAULT_DB


def now_ms() -> int:
    return int(time.time() * 1000)


class PiRemoteSupervisor:
    def __init__(self, socket_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._socket_path = resolve_socket_path(socket_path)
        self._db_path = resolve_db_path(db_path)
        self._listener: Optional[UdsListener] = None
        self._registry: Optional[PresenceRegistry] = None
        self._store: Optional[PiRemoteDB] = None
        self._handler: Optional[PiRemoteHandler] = None
        self._startup_error: Optional[str] = None

    def configure(self, socket_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
        with self._lock:
            resolved_socket = resolve_socket_path(socket_path)
            resolved_db = resolve_db_path(db_path)
            if resolved_socket != self._socket_path or resolved_db != self._db_path:
                listener, store = self._listener, self._store
                self._listener = None
                self._registry = None
                self._store = None
                self._handler = None
                self._startup_error = None
                if listener is not None:
                    listener.stop()
                if store is not None:
                    store.close()
            self._socket_path = resolved_socket
            self._db_path = resolved_db

    def _request(self, method: str, path: str, body: Any) -> Tuple[int, Any]:
        with self._lock:
            handler = self._handler
        if handler is None:
            return 503, {"ok": False, "protocol": 1, "error": "unavailable"}
        return handler.handle(method, path, body, now_ms())

    def start(self) -> None:
        with self._lock:
            if self._listener is not None and self._listener.running:
                return
            if self._store is None:
                try:
                    self._store = PiRemoteDB(self._db_path)
                except Exception as exc:
                    self._startup_error = str(exc)
                    logger.error("pi remote: cannot open %s: %s", self._db_path, exc)
                    return
            if self._registry is None:
                self._registry = PresenceRegistry()
            if self._handler is None:
                self._handler = PiRemoteHandler(self._registry, self._store)
            if self._listener is None:
                self._listener = UdsListener(self._socket_path, self._request)
            self._listener.start()
            if self._listener.running:
                logger.info("pi remote listening on %s", self._socket_path)
            else:
                logger.warning(
                    "pi remote listener is not running on %s: %s",
                    self._socket_path,
                    self._listener.bind_error,
                )

    def stop_all(self) -> None:
        with self._lock:
            listener, store = self._listener, self._store
            self._listener = None
            self._registry = None
            self._store = None
            self._handler = None
            self._startup_error = None
        if listener is not None:
            listener.stop()
        if store is not None:
            store.close()

    def status(self) -> dict:
        with self._lock:
            listener = self._listener
        if listener is None:
            return {
                "running": False,
                "socket_path": self._socket_path,
                "db_path": self._db_path,
                "bind_error": self._startup_error,
            }
        return {
            "running": listener.running,
            "socket_path": self._socket_path,
            "db_path": self._db_path,
            "bind_error": listener.bind_error,
        }


pi_remote_supervisor = PiRemoteSupervisor()
