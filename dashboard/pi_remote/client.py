from typing import Any, Callable, List, Mapping, Optional, Tuple

from .bus import BusMessage, EventBus, SessionKey, Subscription
from .command_queue import CommandQueue
from .commands import CommandResult
from .limits import RateLimiter
from .publishing import bus_publisher, publish_children
from .read_model import (
    EventPage,
    SessionSummary,
    clamp_limit,
    event_page,
    resolve_parent,
    session_summary,
)
from .registry import PresenceRegistry
from .store import PiRemoteDB

SUPPORTED_COMMANDS = frozenset({"send_message", "abort", "answer_prompt"})


class PiRemoteClient:
    def __init__(
        self,
        store: PiRemoteDB,
        registry: PresenceRegistry,
        bus: EventBus,
        queue: CommandQueue,
        limiter: RateLimiter,
        clock: Callable[[], int],
    ) -> None:
        self.store = store
        self.registry = registry
        self.bus = bus
        self.queue = queue
        self.limiter = limiter
        self.clock = clock

    def subscribe(self, key: Optional[SessionKey] = None) -> Subscription:
        return self.bus.subscribe(key)

    def session(self, key: SessionKey) -> Optional[SessionSummary]:
        row = self.store.sessions.get(key[0], key[1])
        if row is None:
            return None
        presence = self.registry.get(key[0], key[1], self.clock())
        prompts = self.store.prompts.open_for(key[0], key[1])
        parents = resolve_parent(self.store.sessions.list())
        return session_summary(row, presence, prompts, parents)

    def sessions(self) -> List[SessionSummary]:
        now = self.clock()
        grouped = self.store.prompts.open_by_session()
        rows = self.store.sessions.list()
        parents = resolve_parent(rows)
        summaries = [
            session_summary(
                row,
                self.registry.get(row["session_id"], row["instance_id"], now),
                grouped.get((row["session_id"], row["instance_id"]), []),
                parents,
            )
            for row in rows
        ]
        return sorted(summaries, key=lambda summary: (not summary.live, -summary.last_seen))

    def events(
        self,
        session_id: str,
        instance_id: str,
        after_seq: int = 0,
        limit: Optional[int] = None,
    ) -> Optional[EventPage]:
        if self.store.sessions.get(session_id, instance_id) is None:
            return None
        page_limit = clamp_limit(limit)
        rows = self.store.events.page(session_id, instance_id, after_seq, page_limit)
        return event_page(rows, after_seq, page_limit)

    def delete_session(self, key: SessionKey) -> Optional[str]:
        """Drops the captured session, or returns the reason it could not be dropped.

        A session the extension is still heartbeating for is refused: the next
        hello re-inserts the row, so accepting the delete would only hide a
        session that is about to reappear.
        """
        now = self.clock()
        if self.registry.get(key[0], key[1], now) is not None:
            return "pi_session_live"
        if self.store.sessions.get(key[0], key[1]) is None:
            return "unknown_session"
        pending = self.queue.drop_key(key)
        self.store.commands.drop([command.command_id for command in pending], now)
        self.store.sessions.delete(key[0], key[1])
        self.bus.publish(BusMessage("removed", key))
        publish_children(self.store, self.registry, bus_publisher(self.bus), key[0], now)
        return None

    def send_command(
        self, key: SessionKey, kind: str, args: Mapping[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        now = self.clock()
        if self.registry.get(key[0], key[1], now) is None:
            return None, "pi_session_offline"
        if kind not in SUPPORTED_COMMANDS:
            return None, "unsupported_command"
        if not self.limiter.allow(key, now):
            return None, "rate_limited"
        command = self.queue.enqueue(key, kind, args, now)
        if command is None:
            return None, "queue_full"
        self.store.commands.record(command, key)
        return command.command_id, None

    def await_command(self, command_id: str, timeout_s: float) -> Optional[CommandResult]:
        return self.queue.wait_result(command_id, timeout_s)
