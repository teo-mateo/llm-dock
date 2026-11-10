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
    row = store.sessions.get(session_id, instance_id)
    if row is None:
        return
    parents = resolve_parent(store.sessions.list())
    presence = registry.get(session_id, instance_id, now)
    prompts = store.prompts.open_for(session_id, instance_id)
    publish(
        "session",
        (session_id, instance_id),
        (),
        session_summary(row, presence, prompts, parents),
    )
    publish_children(store, registry, publish, session_id, now)


def publish_children(
    store: PiRemoteDB,
    registry: PresenceRegistry,
    publish: PublishCallback,
    session_id: str,
    now: int,
) -> None:
    rows = store.sessions.list()
    by_key = {row_key(row): row for row in rows}
    parents = resolve_parent(rows)
    for key in children_to_republish(rows, session_id):
        presence = registry.get(key[0], key[1], now)
        prompts = store.prompts.open_for(key[0], key[1])
        publish("session", key, (), session_summary(by_key[key], presence, prompts, parents))
