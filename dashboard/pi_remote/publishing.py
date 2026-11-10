from typing import Callable, Optional, Tuple

from .bus import BusMessage, EventBus, SessionKey
from .read_model import EventView, SessionSummary, resolve_parent, session_summary
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
    presence = registry.get(session_id, instance_id, now)
    prompts = store.prompts.open_for(session_id, instance_id)
    parents = resolve_parent(store.sessions.list())
    summary = session_summary(row, presence, prompts, parents)
    publish("session", (session_id, instance_id), (), summary)
