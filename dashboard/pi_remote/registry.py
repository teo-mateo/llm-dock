import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .contract import STALE_AFTER_MS


@dataclass
class PresenceEntry:
    session_id: str
    instance_id: str
    fields: Dict[str, Any] = field(default_factory=dict)
    last_seen: int = 0
    state: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    sent_at: Optional[int] = None


class PresenceRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._entries: Dict[Tuple[str, str], PresenceEntry] = {}

    def register(self, fields, now):
        key = (fields["session_id"], fields["instance_id"])
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = PresenceEntry(
                    session_id=fields["session_id"],
                    instance_id=fields["instance_id"],
                    fields=dict(fields),
                    last_seen=now,
                )
                self._entries[key] = entry
            else:
                entry.fields = dict(fields)
                entry.last_seen = now
            return entry

    def heartbeat(self, session_id, instance_id, state, context, sent_at, now):
        key = (session_id, instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return "unknown"
            if now - entry.last_seen > STALE_AFTER_MS:
                del self._entries[key]
                return "stale"
            entry.last_seen = now
            entry.state = state
            entry.context = context
            entry.sent_at = sent_at
            return "ok"

    def bye(self, session_id, instance_id, now):
        key = (session_id, instance_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return "unknown"
            if now - entry.last_seen > STALE_AFTER_MS:
                del self._entries[key]
                return "stale"
            del self._entries[key]
            return "ok"

    def entries(self) -> List[PresenceEntry]:
        with self._lock:
            return [
                PresenceEntry(
                    session_id=entry.session_id,
                    instance_id=entry.instance_id,
                    fields=dict(entry.fields),
                    last_seen=entry.last_seen,
                    state=entry.state,
                    context=entry.context,
                    sent_at=entry.sent_at,
                )
                for entry in self._entries.values()
            ]

    def get(self, session_id: str, instance_id: str) -> Optional[PresenceEntry]:
        with self._lock:
            entry = self._entries.get((session_id, instance_id))
            if entry is None:
                return None
            return PresenceEntry(
                session_id=entry.session_id,
                instance_id=entry.instance_id,
                fields=dict(entry.fields),
                last_seen=entry.last_seen,
                state=entry.state,
                context=entry.context,
                sent_at=entry.sent_at,
            )
