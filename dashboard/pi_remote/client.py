from typing import Any, Callable, List, Mapping, Optional, Tuple

from .bus import EventBus, SessionKey, Subscription
from .command_queue import CommandQueue
from .commands import CommandResult
from .limits import RateLimiter
from .read_model import EventPage, SessionSummary, clamp_limit, event_page, session_summary
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
        return session_summary(row, presence, prompts)

    def sessions(self) -> List[SessionSummary]:
        now = self.clock()
        grouped = self.store.prompts.open_by_session()
        summaries = [
            session_summary(
                row,
                self.registry.get(row["session_id"], row["instance_id"], now),
                grouped.get((row["session_id"], row["instance_id"]), []),
            )
            for row in self.store.sessions.list()
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
