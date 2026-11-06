import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from .bus import SessionKey
from .commands import CommandResult


@dataclass(frozen=True)
class QueuedCommand:
    command_id: str
    kind: str
    args: Mapping[str, Any]
    issued_at: int


# Ids must stay unique across dashboard restarts: pi_commands keeps every id, and a
# long-running pi dedupes by id, so a per-process counter would collide with stored
# rows and make pi skip a new command as one it already ran.
def new_command_id() -> str:
    return f"cmd-{uuid.uuid4().hex}"


class CommandQueue:
    def __init__(
        self,
        redeliver_after_ms: int = 30000,
        max_per_key: int = 50,
        new_id: Callable[[], str] = new_command_id,
    ) -> None:
        self.redeliver_after_ms = redeliver_after_ms
        self.max_per_key = max_per_key
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._queues: Dict[SessionKey, List[QueuedCommand]] = {}
        self._handed_at: Dict[str, int] = {}
        self._results: Dict[str, CommandResult] = {}
        self._closed = False
        self._new_id = new_id

    def enqueue(
        self,
        key: SessionKey,
        kind: str,
        args: Mapping[str, Any],
        now: int,
    ) -> Optional[QueuedCommand]:
        with self._condition:
            if self._closed:
                return None
            queue = self._queues.setdefault(key, [])
            if len(queue) >= self.max_per_key:
                return None
            command = QueuedCommand(
                command_id=self._new_id(),
                kind=kind,
                args=dict(args),
                issued_at=now,
            )
            queue.append(command)
            self._condition.notify_all()
            return command

    def take(self, key: SessionKey, now: int, wait_s: float) -> List[QueuedCommand]:
        deadline = time.monotonic() + max(0.0, wait_s)
        with self._condition:
            while True:
                if self._closed:
                    return []
                commands = self._available(key, now)
                if commands:
                    self._condition.notify_all()
                    return commands
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)

    def _available(self, key: SessionKey, now: int) -> List[QueuedCommand]:
        queue = self._queues.get(key, [])
        available = []
        for command in queue:
            if command.command_id in self._results:
                continue
            handed_at = self._handed_at.get(command.command_id)
            if handed_at is None or now - handed_at >= self.redeliver_after_ms:
                self._handed_at[command.command_id] = now
                available.append(command)
        return available

    def complete(self, key: SessionKey, results: Iterable[CommandResult]) -> List[CommandResult]:
        known = []
        with self._condition:
            queue = self._queues.get(key, [])
            by_id = {command.command_id: command for command in queue}
            for result in results:
                command = by_id.get(result.command_id)
                if command is None:
                    continue
                queue.remove(command)
                by_id.pop(result.command_id, None)
                self._handed_at.pop(result.command_id, None)
                self._results[result.command_id] = result
                known.append(result)
            if not queue:
                self._queues.pop(key, None)
            self._condition.notify_all()
        return known

    def wait_result(self, command_id: str, timeout_s: float) -> Optional[CommandResult]:
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._condition:
            while True:
                result = self._results.get(command_id)
                if result is not None:
                    return result
                if self._closed:
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def drop_key(self, key: SessionKey) -> List[QueuedCommand]:
        with self._condition:
            commands = self._queues.pop(key, [])
            for command in commands:
                self._handed_at.pop(command.command_id, None)
            self._condition.notify_all()
            return commands

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()
