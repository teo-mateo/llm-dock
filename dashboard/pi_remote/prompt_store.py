from typing import Dict, Iterable, List, Optional, Tuple

from .events import StoredEvent
from .prompts import PromptRow, close_values, open_values, prompt_row
from .schema import CLOSE_PROMPT_SQL, UPSERT_PROMPT_SQL
from .wire_types import is_prompt_closed_body, is_prompt_open_body

SELECT_COLUMNS = """
    prompt_id, kind, title, message, options_json, allow_free_text, timeout_ms,
    status, value_json, answered_by
"""


def apply_prompt_events(
    conn, session_id: str, instance_id: str, events: Iterable[StoredEvent]
) -> None:
    for event in sorted(events, key=lambda item: item.seq):
        if event.type == "prompt_open" and is_prompt_open_body(event.payload):
            values = open_values(session_id, instance_id, event)
            if values is not None:
                conn.execute(UPSERT_PROMPT_SQL, values)
        elif event.type == "prompt_closed" and is_prompt_closed_body(event.payload):
            values = close_values(session_id, instance_id, event)
            if values is not None:
                conn.execute(CLOSE_PROMPT_SQL, values)


class PromptStore:
    def __init__(self, db) -> None:
        self.db = db

    def get(self, session_id: str, instance_id: str, prompt_id: str) -> Optional[PromptRow]:
        with self.db._connection() as conn:
            row = conn.execute(
                f"SELECT {SELECT_COLUMNS} FROM pi_prompts"
                " WHERE session_id = ? AND instance_id = ? AND prompt_id = ?",
                (session_id, instance_id, prompt_id),
            ).fetchone()
        return prompt_row(dict(row)) if row is not None else None

    def open_for(self, session_id: str, instance_id: str) -> List[PromptRow]:
        with self.db._connection() as conn:
            rows = conn.execute(
                f"SELECT {SELECT_COLUMNS}, opened_seq FROM pi_prompts"
                " WHERE session_id = ? AND instance_id = ? AND status = 'open'"
                " ORDER BY opened_seq",
                (session_id, instance_id),
            ).fetchall()
        return [prompt_row(dict(row)) for row in rows]

    def open_by_session(self) -> Dict[Tuple[str, str], List[PromptRow]]:
        with self.db._connection() as conn:
            rows = conn.execute(
                f"SELECT session_id, instance_id, {SELECT_COLUMNS}, opened_seq FROM pi_prompts"
                " WHERE status = 'open' ORDER BY session_id, instance_id, opened_seq"
            ).fetchall()
        grouped: Dict[Tuple[str, str], List[PromptRow]] = {}
        for row in rows:
            item = dict(row)
            key = (item["session_id"], item["instance_id"])
            grouped.setdefault(key, []).append(prompt_row(item))
        return grouped

    def purge_closed(self, cutoff: int) -> int:
        with self.db._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM pi_prompts WHERE status != 'open' AND closed_ts < ?", (cutoff,)
            )
            return cursor.rowcount
