import json
from dataclasses import asdict
from typing import Any, Iterator, List, Mapping, Optional, Protocol

from .api_json import summary_json
from .bus import SessionKey, Subscription
from .read_model import EventPage, SessionSummary

KEEPALIVE = ": keepalive\n\n"


class StreamSource(Protocol):
    def subscribe(self, key: Optional[SessionKey] = None) -> Subscription: ...
    def events(
        self, session_id: str, instance_id: str, after_seq: int, limit: int
    ) -> Optional[EventPage]: ...
    def sessions(self) -> List[SessionSummary]: ...
    def session(self, key: SessionKey) -> Optional[SessionSummary]: ...


def sse(event: str, data: Mapping[str, Any], event_id: Optional[int] = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}\n")
    parts.append(f"event: {event}\n")
    payload = {"type": event, **data}
    payload["type"] = event
    parts.append("data: " + json.dumps(payload, separators=(",", ":")) + "\n\n")
    return "".join(parts)


def session_stream(
    source: StreamSource,
    key: SessionKey,
    after_seq: int,
    keepalive_s: float = 15.0,
) -> Iterator[str]:
    subscription = source.subscribe(key)
    try:
        cursor = after_seq
        while True:
            page = source.events(key[0], key[1], cursor, 500)
            if page is None or not page.events:
                break
            cursor = page.events[-1].seq
            yield sse(
                "events",
                {"events": [asdict(event) for event in page.events]},
                event_id=cursor,
            )
            if not page.has_more:
                break

        summary = source.session(key)
        if summary is not None:
            yield sse("session", summary_json(summary))

        while True:
            message = subscription.get(keepalive_s)
            if message is None:
                if subscription.lagged:
                    yield sse("lagged", {"after": cursor})
                    return
                if subscription.closed:
                    return
                yield KEEPALIVE
                continue
            if message.kind == "events":
                remaining = [event for event in message.events if event.seq > cursor]
                if remaining:
                    cursor = remaining[-1].seq
                    yield sse(
                        "events",
                        {"events": [asdict(event) for event in remaining]},
                        event_id=cursor,
                    )
            elif message.kind == "session" and message.summary is not None:
                yield sse("session", summary_json(message.summary))
    finally:
        subscription.close()


def sessions_stream(
    source: StreamSource,
    keepalive_s: float = 15.0,
) -> Iterator[str]:
    subscription = source.subscribe(None)
    try:
        yield sse(
            "snapshot",
            {"sessions": [summary_json(summary) for summary in source.sessions()]},
        )
        while True:
            message = subscription.get(keepalive_s)
            if message is None:
                if subscription.lagged:
                    yield sse("lagged", {})
                    return
                if subscription.closed:
                    return
                yield KEEPALIVE
                continue
            if message.kind == "session" and message.summary is not None:
                yield sse("session", summary_json(message.summary))
    finally:
        subscription.close()
