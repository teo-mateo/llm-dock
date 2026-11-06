import threading
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .contract import END_REASON_STALE, STALE_AFTER_MS
from .frames import ByeFrame, ContextUsage, HeartbeatFrame, HelloFrame


class RegistryResult(str, Enum):
    OK = "ok"
    UNKNOWN = "unknown"
    STALE = END_REASON_STALE


@dataclass
class PresenceEntry:
    hello: HelloFrame
    last_seen: int
    state: Optional[str] = None
    context: Optional[ContextUsage] = None
    sent_at: Optional[int] = None

    @property
    def session_id(self) -> str:
        return self.hello.session_id

    @property
    def instance_id(self) -> str:
        return self.hello.instance_id


def is_live(entry: PresenceEntry, now: int) -> bool:
    return now - entry.last_seen <= STALE_AFTER_MS


class PresenceRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[Tuple[str, str], PresenceEntry] = {}

    def register(self, frame: HelloFrame, now: int) -> PresenceEntry:
        key = (frame.session_id, frame.instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = PresenceEntry(hello=frame, last_seen=now)
                self._entries[key] = entry
            else:
                entry.hello = frame
                entry.last_seen = now
            return entry

    def heartbeat(self, frame: HeartbeatFrame, now: int) -> RegistryResult:
        key = (frame.session_id, frame.instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return RegistryResult.UNKNOWN
            if not is_live(entry, now):
                return RegistryResult.STALE
            entry.last_seen = now
            entry.state = frame.state
            entry.context = frame.context
            entry.sent_at = frame.sent_at
            return RegistryResult.OK

    def touch(self, session_id: str, instance_id: str, now: int) -> RegistryResult:
        key = (session_id, instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return RegistryResult.UNKNOWN
            if not is_live(entry, now):
                return RegistryResult.STALE
            entry.last_seen = now
            return RegistryResult.OK

    def bye(self, frame: ByeFrame, now: int) -> RegistryResult:
        key = (frame.session_id, frame.instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return RegistryResult.UNKNOWN
            if not is_live(entry, now):
                return RegistryResult.STALE
            del self._entries[key]
            return RegistryResult.OK

    def expire(self, now: int) -> List[Tuple[str, str]]:
        with self._lock:
            stale_keys = [
                key for key, entry in self._entries.items() if not is_live(entry, now)
            ]
            for key in stale_keys:
                del self._entries[key]
            return stale_keys

    def entries(self, now: int) -> List[PresenceEntry]:
        with self._lock:
            return [
                PresenceEntry(
                    hello=entry.hello,
                    last_seen=entry.last_seen,
                    state=entry.state,
                    context=entry.context,
                    sent_at=entry.sent_at,
                )
                for entry in self._entries.values()
                if is_live(entry, now)
            ]

    def get(self, session_id: str, instance_id: str, now: int) -> Optional[PresenceEntry]:
        with self._lock:
            entry = self._entries.get((session_id, instance_id))
            if entry is None or not is_live(entry, now):
                return None
            return PresenceEntry(
                hello=entry.hello,
                last_seen=entry.last_seen,
                state=entry.state,
                context=entry.context,
                sent_at=entry.sent_at,
            )
