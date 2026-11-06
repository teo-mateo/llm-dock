from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .wire_types import is_int, is_nullable_str

MAX_WAIT_MS = 25000


@dataclass(frozen=True)
class CommandResult:
    command_id: str
    ok: bool
    error: Optional[str]


@dataclass(frozen=True)
class CommandsPollFrame:
    session_id: str
    instance_id: str
    wait_ms: int


@dataclass(frozen=True)
class CommandResultsFrame:
    session_id: str
    instance_id: str
    results: Tuple[CommandResult, ...]


def _parse_command_result(raw: Any) -> Optional[CommandResult]:
    if not isinstance(raw, dict):
        return None
    command_id = raw.get("command_id")
    if not isinstance(command_id, str) or not command_id:
        return None
    ok = raw.get("ok")
    if not isinstance(ok, bool):
        return None
    error = raw.get("error")
    if not is_nullable_str(error):
        return None
    return CommandResult(command_id=command_id, ok=ok, error=error)


def parse_commands_poll(body: Any) -> Optional[CommandsPollFrame]:
    if not isinstance(body, dict):
        return None
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    wait_ms = body.get("wait_ms")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not is_int(wait_ms) or wait_ms < 0 or wait_ms > MAX_WAIT_MS:
        return None
    return CommandsPollFrame(session_id=session_id, instance_id=instance_id, wait_ms=wait_ms)


def parse_command_results(body: Any) -> Optional[CommandResultsFrame]:
    if not isinstance(body, dict):
        return None
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    raw_results = body.get("results")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not isinstance(raw_results, list):
        return None
    results = []
    for raw in raw_results:
        result = _parse_command_result(raw)
        if result is None:
            return None
        results.append(result)
    return CommandResultsFrame(
        session_id=session_id,
        instance_id=instance_id,
        results=tuple(results),
    )
