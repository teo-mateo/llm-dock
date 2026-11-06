import logging
import threading
import time
from typing import Callable, Optional

from .bus import EventBus
from .client import PiRemoteClient
from .command_queue import CommandQueue
from .contract import END_REASON_DASHBOARD_RESTART
from .handler import PiRemoteHandler
from .limits import RateLimiter
from .listener import UdsListener
from .publishing import bus_publisher
from .registry import PresenceRegistry
from .settings import resolve_db_path, resolve_socket_path
from .store import PiRemoteDB
from .sweeper import StaleSweeper

logger = logging.getLogger(__name__)


def now_ms() -> int:
    return int(time.time() * 1000)


class PiRemoteSupervisor:
    def __init__(
        self,
        socket_path: Optional[str] = None,
        db_path: Optional[str] = None,
        clock: Optional[Callable[[], int]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._clock = clock or now_ms
        self._socket_path = resolve_socket_path(socket_path)
        self._db_path = resolve_db_path(db_path)
        self._listener: Optional[UdsListener] = None
        self._registry: Optional[PresenceRegistry] = None
        self._store: Optional[PiRemoteDB] = None
        self._handler: Optional[PiRemoteHandler] = None
        self._sweeper: Optional[StaleSweeper] = None
        self._bus: Optional[EventBus] = None
        self._queue: Optional[CommandQueue] = None
        self._rate_limiter = RateLimiter()
        self._client: Optional[PiRemoteClient] = None
        self._startup_error: Optional[str] = None

    def configure(self, socket_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
        with self._lock:
            resolved_socket = resolve_socket_path(socket_path)
            resolved_db = resolve_db_path(db_path)
            if resolved_socket != self._socket_path or resolved_db != self._db_path:
                listener, sweeper, store, bus, queue = (
                    self._listener,
                    self._sweeper,
                    self._store,
                    self._bus,
                    self._queue,
                )
                self._listener = None
                self._registry = None
                self._store = None
                self._handler = None
                self._sweeper = None
                self._bus = None
                self._queue = None
                self._client = None
                self._startup_error = None
                if queue is not None:
                    queue.close()
                if listener is not None:
                    listener.stop()
                if sweeper is not None:
                    sweeper.stop()
                if bus is not None:
                    bus.close()
                if store is not None:
                    store.close()
            self._socket_path = resolved_socket
            self._db_path = resolved_db

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
            self._store.sessions.end_open(END_REASON_DASHBOARD_RESTART, self._clock())
            if self._registry is None:
                self._registry = PresenceRegistry()
            if self._bus is None:
                self._bus = EventBus()
            if self._queue is None:
                self._queue = CommandQueue()
            if self._client is None:
                self._client = PiRemoteClient(
                    self._store,
                    self._registry,
                    self._bus,
                    self._queue,
                    self._rate_limiter,
                    self._clock,
                )
            publish = bus_publisher(self._bus)
            if self._handler is None:
                self._handler = PiRemoteHandler(
                    self._registry,
                    self._store,
                    publish=publish,
                    queue=self._queue,
                )
            if self._sweeper is None:
                self._sweeper = StaleSweeper(
                    self._registry,
                    self._store,
                    self._clock,
                    publish=publish,
                    queue=self._queue,
                )
            if self._listener is None:
                handler = self._handler
                clock = self._clock
                self._listener = UdsListener(
                    self._socket_path,
                    lambda method, path, body: handler.handle(
                        method, path, body, clock()
                    ),
                )
            self._listener.start()
            if self._listener.running:
                self._sweeper.start()
                logger.info("pi remote listening on %s", self._socket_path)
            else:
                logger.warning(
                    "pi remote listener is not running on %s: %s",
                    self._socket_path,
                    self._listener.bind_error,
                )

    def stop_all(self) -> None:
        with self._lock:
            listener, sweeper, store, bus, queue = (
                self._listener,
                self._sweeper,
                self._store,
                self._bus,
                self._queue,
            )
            self._listener = None
            self._registry = None
            self._store = None
            self._handler = None
            self._sweeper = None
            self._bus = None
            self._queue = None
            self._client = None
            self._startup_error = None
        if queue is not None:
            queue.close()
        if listener is not None:
            listener.stop()
        if sweeper is not None:
            sweeper.stop()
        if bus is not None:
            bus.close()
        if store is not None:
            store.close()

    @property
    def client(self) -> Optional[PiRemoteClient]:
        with self._lock:
            return self._client

    def status(self) -> dict:
        with self._lock:
            listener = self._listener
            sweeper = self._sweeper
        if listener is None:
            return {
                "running": False,
                "socket_path": self._socket_path,
                "db_path": self._db_path,
                "bind_error": self._startup_error,
                "sweeper_running": False,
            }
        return {
            "running": listener.running,
            "socket_path": self._socket_path,
            "db_path": self._db_path,
            "bind_error": listener.bind_error,
            "sweeper_running": sweeper.running if sweeper is not None else False,
        }


pi_remote_supervisor = PiRemoteSupervisor()
