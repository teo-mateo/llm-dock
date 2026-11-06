import queue
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from .read_model import EventView, SessionSummary

SessionKey = Tuple[str, str]

_CLOSED = object()


@dataclass(frozen=True)
class BusMessage:
    kind: str
    key: SessionKey
    events: Tuple[EventView, ...] = ()
    summary: Optional[SessionSummary] = None


class Subscription:
    def __init__(self, max_queue: int, key: Optional[SessionKey], unsubscribe: Callable[[], None]) -> None:
        self.key = key
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._lock = threading.RLock()
        self._closed = False
        self._lagged = False
        self._unsubscribe = unsubscribe

    def get(self, timeout: float) -> Optional[BusMessage]:
        if self.closed:
            return None
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _CLOSED:
            return None
        return item

    @property
    def lagged(self) -> bool:
        return self._lagged

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            try:
                self._queue.put_nowait(_CLOSED)
            except queue.Full:
                pass
        self._unsubscribe()

    def _offer(self, message: BusMessage) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                self._lagged = True
                self._closed = True
                self._unsubscribe()
                self._drain_and_signal()

    def _drain_and_signal(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._queue.put_nowait(_CLOSED)
        except queue.Full:
            pass


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self.max_queue = max_queue
        self._lock = threading.RLock()
        self._subscriptions: set[Subscription] = set()

    def subscribe(self, key: Optional[SessionKey] = None) -> Subscription:
        with self._lock:
            subscription = Subscription(self.max_queue, key, lambda: self._remove(subscription))
            self._subscriptions.add(subscription)
        return subscription

    def publish(self, message: BusMessage) -> None:
        with self._lock:
            subscribers = list(self._subscriptions)
        for subscription in subscribers:
            try:
                if subscription.key is None or subscription.key == message.key:
                    subscription._offer(message)
            except Exception:
                subscription.close()

    def close(self) -> None:
        with self._lock:
            subscribers = list(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscribers:
            subscription.close()

    def _remove(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)
