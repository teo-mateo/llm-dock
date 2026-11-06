import threading
from typing import Any, Dict, List


class RateLimiter:
    def __init__(self, max_events: int = 10, window_ms: int = 60000) -> None:
        self.max_events = max_events
        self.window_ms = window_ms
        self._lock = threading.RLock()
        self._events: Dict[Any, List[int]] = {}

    def allow(self, key: Any, now: int) -> bool:
        with self._lock:
            events = [
                timestamp
                for timestamp in self._events.get(key, [])
                if now - timestamp < self.window_ms
            ]
            if len(events) >= self.max_events:
                self._events[key] = events
                return False
            events.append(now)
            self._events[key] = events
            return True
