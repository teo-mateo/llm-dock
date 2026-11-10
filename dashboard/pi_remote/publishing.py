from typing import Callable, Optional, Tuple

from .bus import BusMessage, EventBus, SessionKey
from .read_model import (
    EventView,
    SessionSummary,
    children_to_republish,
    resolve_parent,
    row_key,
    session_summary,
)
from .registry import PresenceRegistry
from .store import PiRemoteDB

PublishCallback = Callable[
    [str, SessionKey, Tuple[EventView, ...], Optional[SessionSummary]], None
]


def bus_publisher(bus: EventBus) -> PublishCallback:
    def publish(kind, key, events, summary) -> None:
        bus.publish(BusMessage(kind, key, events, summary))
    return publish


def publish_session(
    store: PiRemoteDB,
    registry: PresenceRegistry,
    publish: PublishCallback,
    session_id: str,
    instance_id: str,
    now: int,
) -> None:
    rows = store.sessions.list()
    by_key = {row_key(row): row for row in rows}
    key = (session_id, instance_id)
    if key not in by_key:
        return
    parents = resolve_parent(rows)
    keys = [key]
    for child in children_to_republish(rows, session_id):
        if child not in keys:
            keys.append(child)
    for each in keys:
        presence = registry.get(each[0], each[1], now)
        prompts = store.prompts.open_for(each[0], each[1])
        summary = session_summary(by_key[each], presence, prompts, parents)
        publish("session", each, (), summary)
