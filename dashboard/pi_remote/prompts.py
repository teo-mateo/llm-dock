import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .events import StoredEvent
from .wire_types import PROMPT_KINDS, PROMPT_REASONS, is_prompt_value

PROMPT_EVENT_TYPES = frozenset({"prompt_open", "prompt_closed"})
MAX_ANSWER_TEXT = 4000

OPEN_FIELDS = (
    "prompt_id",
    "kind",
    "title",
    "message",
    "options",
    "allow_free_text",
    "timeout_ms",
)


@dataclass(frozen=True)
class PromptRow:
    prompt_id: str
    kind: str
    title: Optional[str]
    message: Optional[str]
    options: List[str]
    allow_free_text: bool
    timeout_ms: Optional[int]
    status: str
    value: Any = None
    answered_by: Optional[str] = None

    def question(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "kind": self.kind,
            "title": self.title,
            "message": self.message,
            "options": list(self.options),
            "allow_free_text": self.allow_free_text,
            "timeout_ms": self.timeout_ms,
        }


def open_values(session_id: str, instance_id: str, event: StoredEvent) -> Optional[Tuple]:
    body = event.payload
    if body.get("kind") not in PROMPT_KINDS:
        return None
    return (
        session_id,
        instance_id,
        body.get("prompt_id"),
        body.get("kind"),
        body.get("title"),
        body.get("message"),
        json.dumps(body.get("options") or []),
        1 if body.get("allow_free_text") else 0,
        body.get("timeout_ms"),
        event.seq,
        event.ts,
    )


def close_values(session_id: str, instance_id: str, event: StoredEvent) -> Optional[Tuple]:
    body = event.payload
    reason = body.get("reason")
    if reason not in PROMPT_REASONS:
        return None
    value = body.get("value")
    return (
        reason,
        None if value is None else json.dumps(value),
        body.get("answered_by"),
        event.seq,
        event.ts,
        session_id,
        instance_id,
        body.get("prompt_id"),
        event.seq,
    )


def prompt_row(row: Dict[str, Any]) -> PromptRow:
    options = row.get("options_json")
    return PromptRow(
        prompt_id=row["prompt_id"],
        kind=row["kind"],
        title=row.get("title"),
        message=row.get("message"),
        options=json.loads(options) if options else [],
        allow_free_text=bool(row.get("allow_free_text")),
        timeout_ms=row.get("timeout_ms"),
        status=row["status"],
        value=_load(row.get("value_json")),
        answered_by=row.get("answered_by"),
    )


def _load(raw: Optional[str]) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def open_questions(rows: Sequence[PromptRow]) -> List[Dict[str, Any]]:
    return [row.question() for row in rows if row.status == "open"]


def parse_answer_body(body: Any) -> Tuple[Any, Optional[str]]:
    if not isinstance(body, dict) or "value" not in body:
        return None, "invalid_body"
    value = body["value"]
    if isinstance(value, str) and len(value) > MAX_ANSWER_TEXT:
        return None, "invalid_value"
    if isinstance(value, dict) and set(value) != {"choice", "reason"}:
        return None, "invalid_value"
    if not is_prompt_value(value):
        return None, "invalid_value"
    return value, None
