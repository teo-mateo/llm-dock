import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

MAX_EVENTS_BATCH = 50
MAX_EVENTS_BODY_BYTES = 1024 * 1024

STATES = frozenset({"idle", "working"})
ORIGINS = frozenset({"terminal", "extension"})
OUTCOMES = frozenset({"completed", "aborted", "error"})


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
class StoredEvent:
    seq: int
    type: str
    payload: Dict[str, Any]


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nullable_str(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _nullable_number(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )


def _model(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    return isinstance(value.get("provider"), str) and isinstance(value.get("id"), str)


def _usage(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    for key in ("input", "output", "cache_read", "cache_write", "total_tokens"):
        if not isinstance(value.get(key), (int, float)) or isinstance(value.get(key), bool):
            return False
    return _nullable_number(value.get("reasoning")) and _nullable_number(value.get("cost_total"))


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
        and _model(body.get("model"))
        and _usage(body.get("usage"))
        and _nullable_str(body.get("stop_reason"))
    )


def _valid_tool(event_type: str, body: Dict[str, Any]) -> bool:
    if not isinstance(body.get("call_id"), str) or not isinstance(body.get("name"), str):
        return False
    if not isinstance(body.get("truncated"), bool):
        return False
    if event_type == "tool_start":
        return _nullable_str(body.get("args"))
    if event_type == "tool_update":
        return _nullable_str(body.get("partial"))
    return (
        _nullable_str(body.get("result"))
        and isinstance(body.get("is_error"), bool)
        and _nullable_number(body.get("duration_ms"))
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
        return _model(body.get("model")) and _model(body.get("previous"))
    if event_type == "thinking_changed":
        return _nullable_str(body.get("level")) and _nullable_str(body.get("previous"))
    if event_type == "compaction":
        return (
            isinstance(body.get("summary"), str)
            and _nullable_number(body.get("tokens_before"))
            and isinstance(body.get("reason"), str)
        )
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


def parse_events(body: Dict[str, Any]) -> Optional[EventsFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    raw_events = body.get("events")
    if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS_BATCH:
        return None
    if len(json.dumps(body, separators=(",", ":")).encode("utf-8")) > MAX_EVENTS_BODY_BYTES:
        return None
    parsed: List[Event] = []
    for raw in raw_events:
        event = _parse_event(raw)
        if event is None:
            return None
        parsed.append(event)
    return EventsFrame(session_id=session_id, instance_id=instance_id, events=tuple(parsed))


def acked_seq(events: Iterable[StoredEvent]) -> int:
    intervals: List[Tuple[int, int]] = []
    for event in events:
        intervals.append((event.seq, event.seq))
        if event.type == "gap":
            from_seq = event.payload.get("from_seq")
            to_seq = event.payload.get("to_seq")
            if is_int(from_seq) and is_int(to_seq) and from_seq >= 1 and to_seq >= from_seq:
                intervals.append((from_seq, to_seq))
    if not intervals:
        return 0
    intervals.sort()
    first = intervals[0][0]
    acked = first - 1
    for start, end in intervals:
        if start <= acked + 1:
            if end > acked:
                acked = end
        else:
            break
    return acked
