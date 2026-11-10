from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .events import StoredEvent
from .prompts import PromptRow
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
    parent_session_id: Optional[str]
    parent_instance_id: Optional[str]
    project: str
    prompts: List[Dict[str, Any]] = field(default_factory=list)


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


SessionKey = Tuple[str, str]


def project_label(cwd: str) -> str:
    segments = [segment for segment in cwd.replace("\\", "/").split("/") if segment]
    return "/".join(segments[-2:]) if segments else "/"


def _row_key(row: Mapping[str, Any]) -> SessionKey:
    return (row["session_id"], row["instance_id"])


def _parent_candidate(
    row: Mapping[str, Any],
    by_session: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Optional[SessionKey]:
    parent_session_id = row.get("parent_session_id")
    if not parent_session_id:
        return None
    candidates = [
        candidate
        for candidate in by_session.get(parent_session_id, ())
        if _row_key(candidate) != _row_key(row)
    ]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda candidate: (
            candidate.get("ended_at") is not None,
            -candidate["last_seen"],
            -candidate["first_seen"],
            candidate["instance_id"],
        ),
    )
    return _row_key(best)


def resolve_parent(rows: Sequence[Mapping[str, Any]]) -> Dict[SessionKey, SessionKey]:
    by_session: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(row["session_id"], []).append(row)

    direct = {_row_key(row): _parent_candidate(row, by_session) for row in rows}
    resolved: Dict[SessionKey, SessionKey] = {}
    for key, parent in direct.items():
        if parent is None or _reaches_a_cycle(key, direct):
            continue
        resolved[key] = parent
    return resolved


def _reaches_a_cycle(
    key: SessionKey,
    direct: Mapping[SessionKey, Optional[SessionKey]],
) -> bool:
    visited = {key}
    current = direct.get(key)
    while current is not None:
        if current in visited:
            return True
        visited.add(current)
        current = direct.get(current)
    return False


def session_summary(
    row: Mapping[str, Any],
    presence: Optional[PresenceEntry],
    prompts: Sequence[PromptRow] = (),
    parents: Optional[Mapping[SessionKey, SessionKey]] = None,
) -> SessionSummary:
    provider = row.get("model_provider")
    model_id = row.get("model_id")
    model = f"{provider}/{model_id}" if provider and model_id else None
    live = presence is not None
    context = presence.context if presence is not None else None
    parent = (parents or {}).get(_row_key(row))
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
        parent_session_id=row.get("parent_session_id"),
        parent_instance_id=parent[1] if parent is not None else None,
        project=project_label(row["cwd"]),
        prompts=[prompt.question() for prompt in prompts if prompt.status == "open"],
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
