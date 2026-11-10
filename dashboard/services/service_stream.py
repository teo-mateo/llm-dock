import logging
import threading
from collections import deque
from datetime import datetime
from typing import Callable, Generator

from services.service_stream_frames import (
    DELTA,
    KEEPALIVE_FRAME,
    SNAPSHOT,
    Clock,
    delta_frame,
    error_frame,
    snapshot_frame,
)

logger = logging.getLogger(__name__)

MAX_PENDING_EVENTS = 256


class ServiceStream:
    """One subscriber's SSE view of the service list: a snapshot plus the deltas after it.

    frames() owns the whole lifecycle, so the ordering that makes it correct
    lives in one place: register the callback, then snapshot, then replay queued
    deltas. An event emitted while the snapshot is acquired, or right after the
    first frame, is queued instead of lost. Deltas replay in arrival order, so
    the last one per service wins.

    The queue is bounded. On overflow it is dropped and the next frame is a
    fresh snapshot, which clients treat as a full replacement.

    _poll() clears the wake flag before it drains and _wait() consumes it, so
    a set landing between an empty poll and the wait is not lost. Callers must
    not reorder them, which is why neither is public.
    """

    def __init__(self, event_manager, max_pending: int = MAX_PENDING_EVENTS):
        self._manager = event_manager
        self._max_pending = max_pending
        self._pending: deque[dict] = deque()
        self._lagged = False
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._callback: Callable[[dict], None] | None = None

    def frames(self, keepalive_s: float, now: Clock = datetime.utcnow) -> Generator[str, None, None]:
        try:
            yield snapshot_frame(self._open(), now)
            while True:
                item = self._poll()
                if item is None:
                    yield KEEPALIVE_FRAME
                    self._wait(keepalive_s)
                    continue
                kind, body = item
                yield delta_frame(body) if kind == DELTA else snapshot_frame(body, now)
        except GeneratorExit:
            raise
        except Exception as e:
            logger.error("SSE stream error: %s", e)
            yield error_frame(str(e))
        finally:
            self._close()

    def _open(self) -> list[dict]:
        if self._callback is None:
            self._callback = self._on_event
            self._manager.register_callback(self._callback)
        return self._manager.get_services_snapshot()

    def _poll(self) -> tuple[str, object] | None:
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

    def _wait(self, timeout: float) -> None:
        self._wake.wait(timeout)

    def _close(self) -> None:
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
