from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .events import StoredEvent
from .registry import PresenceEntry


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    instance_id: str
    name: Optional[str]
    cwd: str
    model: Optional[str]
    thinking_level: Optional[str]
    first_seen: int
    last_seen: int
    ended_at: Optional[int]
    end_reason: Optional[str]
    live: bool
    state: Optional[str]
    context_percent: Optional[float]


@dataclass(frozen=True)
class EventView:
    seq: int
    type: str
    ts: int
    payload: Dict[str, Any]


@dataclass(frozen=True)
class EventPage:
    events: List[EventView]
    next_after: int
    has_more: bool


def session_summary(row: Mapping[str, Any], presence: Optional[PresenceEntry]) -> SessionSummary:
    provider = row.get("model_provider")
    model_id = row.get("model_id")
    model = f"{provider}/{model_id}" if provider and model_id else None
    live = presence is not None
    context = presence.context if presence is not None else None
    return SessionSummary(
        session_id=row["session_id"],
        instance_id=row["instance_id"],
        name=row.get("name"),
        cwd=row["cwd"],
        model=model,
        thinking_level=row.get("thinking_level"),
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        ended_at=row.get("ended_at"),
        end_reason=row.get("end_reason"),
        live=live,
        state=presence.state if presence is not None else None,
        context_percent=context.percent if context is not None else None,
    )


def event_page(rows: Sequence[StoredEvent], after_seq: int, limit: int) -> EventPage:
    has_more = len(rows) > limit
    selected = list(rows[:limit])
    events = [EventView(row.seq, row.type, row.ts, row.payload) for row in selected]
    next_after = selected[-1].seq if selected else after_seq
    return EventPage(events, next_after, has_more)


def clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return 200
    return max(1, min(500, limit))
