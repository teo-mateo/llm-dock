from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .wire_types import (
    STATES,
    is_int,
    is_nullable_model,
    is_nullable_number,
    is_nullable_str,
    is_nullable_usage,
    is_prompt_body,
)

MAX_EVENTS_BATCH = 50

ORIGINS = frozenset({"terminal", "extension"})
OUTCOMES = frozenset({"completed", "aborted", "error"})
PROMPT_TYPES = ("prompt_open", "prompt_closed")


@dataclass(frozen=True)
class Event:
    seq: int
    ts: int
    type: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class EventsFrame:
    session_id: str
    instance_id: str
    events: Tuple[Event, ...]


@dataclass(frozen=True)
class EventsEnvelope:
    session_id: str
    instance_id: str
    body: Dict[str, Any]


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    type: str
    ts: int
    payload: Dict[str, Any]


@dataclass(frozen=True)
class IngestResult:
    acked_seq: int
    inserted: Tuple[StoredEvent, ...]


@dataclass(frozen=True)
class AckedEvent:
    seq: int
    type: str
    from_seq: Optional[int] = None
    to_seq: Optional[int] = None


def _valid_gap(body: Dict[str, Any]) -> bool:
    return (
        is_int(body.get("from_seq"))
        and is_int(body.get("to_seq"))
        and body["from_seq"] >= 1
        and body["to_seq"] >= body["from_seq"]
    )


def _valid_user_message(body: Dict[str, Any]) -> bool:
    return (
        isinstance(body.get("text"), str)
        and is_int(body.get("image_count"))
        and body["image_count"] >= 0
        and body.get("origin") in ORIGINS
    )


def _valid_assistant_message(body: Dict[str, Any]) -> bool:
    return (
        isinstance(body.get("text"), str)
        and isinstance(body.get("thinking"), str)
        and is_nullable_model(body.get("model"))
        and is_nullable_usage(body.get("usage"))
        and is_nullable_str(body.get("stop_reason"))
    )


def _valid_tool(event_type: str, body: Dict[str, Any]) -> bool:
    if not isinstance(body.get("call_id"), str) or not isinstance(body.get("name"), str):
        return False
    if not isinstance(body.get("truncated"), bool):
        return False
    if event_type == "tool_start":
        return is_nullable_str(body.get("args"))
    if event_type == "tool_update":
        return is_nullable_str(body.get("partial"))
    return (
        is_nullable_str(body.get("result"))
        and isinstance(body.get("is_error"), bool)
        and is_nullable_number(body.get("duration_ms"))
    )


def _valid_payload(event_type: str, body: Dict[str, Any]) -> bool:
    if event_type == "gap":
        return _valid_gap(body)
    if event_type == "state":
        return body.get("state") in STATES
    if event_type == "user_message":
        return _valid_user_message(body)
    if event_type == "assistant_delta":
        return isinstance(body.get("text"), str) and isinstance(body.get("thinking"), str)
    if event_type == "assistant_message":
        return _valid_assistant_message(body)
    if event_type in ("tool_start", "tool_update", "tool_end"):
        return _valid_tool(event_type, body)
    if event_type in ("turn_end", "run_end"):
        return body.get("outcome") in OUTCOMES
    if event_type == "model_changed":
        return is_nullable_model(body.get("model")) and is_nullable_model(body.get("previous"))
    if event_type == "thinking_changed":
        return is_nullable_str(body.get("level")) and is_nullable_str(body.get("previous"))
    if event_type == "compaction":
        return (
            isinstance(body.get("summary"), str)
            and is_nullable_number(body.get("tokens_before"))
            and isinstance(body.get("reason"), str)
        )
    if event_type in PROMPT_TYPES:
        return is_prompt_body(event_type, body)
    return True

def _parse_event(raw: Any) -> Optional[Event]:
    if not isinstance(raw, dict):
        return None
    event_type = raw.get("type")
    seq = raw.get("seq")
    ts = raw.get("ts")
    if not isinstance(event_type, str) or not event_type:
        return None
    if not is_int(seq) or seq < 1:
        return None
    if not is_int(ts) or ts < 0:
        return None
    if not _valid_payload(event_type, raw):
        return None
    payload = {key: value for key, value in raw.items() if key not in ("type", "seq", "ts")}
    return Event(seq=seq, ts=ts, type=event_type, payload=payload)


def parse_events_envelope(body: Dict[str, Any]) -> Optional[EventsEnvelope]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    return EventsEnvelope(session_id=session_id, instance_id=instance_id, body=body)


def parse_events(body: Dict[str, Any]) -> Optional[EventsFrame]:
    envelope = parse_events_envelope(body)
    if envelope is None:
        return None
    raw_events = body.get("events")
    if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS_BATCH:
        return None
    parsed: List[Event] = []
    for raw in raw_events:
        event = _parse_event(raw)
        if event is None:
            return None
        parsed.append(event)
    return EventsFrame(
        session_id=envelope.session_id,
        instance_id=envelope.instance_id,
        events=tuple(parsed),
    )


def acked_seq(events: Iterable[AckedEvent], start: Optional[int] = None) -> int:
    intervals: List[Tuple[int, int]] = []
    for event in events:
        intervals.append((event.seq, event.seq))
        if event.type == "gap" and event.from_seq is not None and event.to_seq is not None:
            if event.from_seq >= 1 and event.to_seq >= event.from_seq:
                intervals.append((event.from_seq, event.to_seq))
    if not intervals:
        return 0 if start is None else start
    intervals.sort()
    acked = intervals[0][0] - 1 if start is None or start == 0 else start
    for begin, end in intervals:
        if begin <= acked + 1:
            if end > acked:
                acked = end
        else:
            break
    return acked
