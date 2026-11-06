import logging
import threading
from typing import Callable, List, Optional, Tuple

from .command_queue import CommandQueue
from .contract import END_REASON_STALE
from .publishing import PublishCallback, publish_session
from .registry import PresenceRegistry
from .store import PiRemoteDB

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS = 15000
PURGE_INTERVAL_MS = 3600000


class StaleSweeper:
    def __init__(
        self,
        registry: PresenceRegistry,
        store: PiRemoteDB,
        clock: Callable[[], int],
        interval_ms: int = DEFAULT_INTERVAL_MS,
        publish: Optional[PublishCallback] = None,
        queue: Optional[CommandQueue] = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.clock = clock
        self.interval_ms = interval_ms
        self.publish = publish or (lambda *args: None)
        self.queue = queue
        self._lock = threading.RLock()
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._last_purge_ms: Optional[int] = None

    def sweep(self, now: int) -> List[Tuple[str, str]]:
        keys = self.registry.expire(now)
        for session_id, instance_id in keys:
            try:
                if self.queue is not None:
                    pending = self.queue.drop_key((session_id, instance_id))
                    self.store.commands.drop(
                        [command.command_id for command in pending], now
                    )
                self.store.sessions.end(
                    session_id, instance_id, END_REASON_STALE, now
                )
            except Exception:
                logger.exception(
                    "pi remote: could not end stale session %s/%s",
                    session_id,
                    instance_id,
                )
            publish_session(
                self.store, self.registry, self.publish,
                session_id, instance_id, now,
            )
        if self._last_purge_ms is None or now - self._last_purge_ms >= PURGE_INTERVAL_MS:
            try:
                self.store.events.purge_old(now)
            except Exception:
                logger.exception("pi remote: event retention purge failed")
            self._last_purge_ms = now
        return keys

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run,
                name="pi-remote-sweeper",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while True:
            event = self._stop_event
            if event is None or event.is_set():
                return
            try:
                self.sweep(self.clock())
            except Exception:
                logger.exception("pi remote: stale sweep failed; continuing")
            event.wait(self.interval_ms / 1000)

    def stop(self) -> None:
        with self._lock:
            event, thread = self._stop_event, self._thread
            self._stop_event = None
            self._thread = None
        if event is not None:
            event.set()
        if thread is not None:
            thread.join(timeout=5)

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()
