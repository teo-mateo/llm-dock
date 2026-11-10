import logging
import threading
from collections import deque
from typing import Callable

logger = logging.getLogger(__name__)

MAX_PENDING_EVENTS = 256

SNAPSHOT = "snapshot"
DELTA = "delta"


class ServiceStream:
    """One subscriber's view of the service list: a snapshot plus the deltas after it.

    open() registers the callback before it takes the snapshot, so an event
    emitted while the snapshot is being acquired, or between the snapshot and
    the caller's first read, is queued instead of lost. Queued deltas are
    replayed in arrival order, so the last one per service wins and a replay can
    never leave a client older than the final event.

    The queue is bounded. On overflow it is dropped and the next poll() returns
    a fresh snapshot, which clients treat as a full replacement.
    """

    def __init__(self, event_manager, max_pending: int = MAX_PENDING_EVENTS):
        self._manager = event_manager
        self._max_pending = max_pending
        self._pending: deque[dict] = deque()
        self._lagged = False
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._callback: Callable[[dict], None] | None = None

    def open(self) -> list[dict]:
        if self._callback is None:
            self._callback = self._on_event
            self._manager.register_callback(self._callback)
        return self._manager.get_services_snapshot()

    def poll(self) -> tuple[str, object] | None:
        self._wake.clear()
        with self._lock:
            lagged = self._lagged
            self._lagged = False
            event = self._pending.popleft() if self._pending and not lagged else None
        if lagged:
            return SNAPSHOT, self._manager.get_services_snapshot()
        if event is not None:
            return DELTA, event
        return None

    def wait(self, timeout: float) -> None:
        self._wake.wait(timeout)

    def close(self) -> None:
        callback, self._callback = self._callback, None
        if callback is not None:
            self._manager.unregister_callback(callback)

    def _on_event(self, event: dict) -> None:
        with self._lock:
            if self._lagged:
                pass
            elif len(self._pending) >= self._max_pending:
                self._pending.clear()
                self._lagged = True
                logger.warning("services stream subscriber lagged; resnapshotting")
            else:
                self._pending.append(event)
        self._wake.set()
