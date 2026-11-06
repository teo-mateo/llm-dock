import json
from typing import List

from .events import (
    AckedEvent,
    EventsFrame,
    IngestResult,
    StoredEvent,
    acked_seq as compute_acked_seq,
)
from .prompt_store import apply_prompt_events
from .schema import INSERT_EVENT_SQL
from .session_changes import session_changes

RETENTION_DAYS = 30
RETENTION_MS = RETENTION_DAYS * 24 * 60 * 60 * 1000


class EventStore:
    def __init__(self, db) -> None:
        self.db = db

    def ingest(self, frame: EventsFrame, now: int) -> IngestResult:
        with self.db._connection() as conn:
            row = conn.execute(
                "SELECT acked_seq FROM pi_sessions WHERE session_id = ? AND instance_id = ?",
                (frame.session_id, frame.instance_id),
            ).fetchone()
            mark = row["acked_seq"] if row is not None else 0
            inserted = []
            for event in frame.events:
                cursor = conn.execute(
                    INSERT_EVENT_SQL,
                    (
                        frame.session_id,
                        frame.instance_id,
                        event.seq,
                        event.type,
                        event.ts,
                        json.dumps(event.payload),
                        event.payload.get("from_seq") if event.type == "gap" else None,
                        event.payload.get("to_seq") if event.type == "gap" else None,
                        now,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted.append(
                        StoredEvent(event.seq, event.type, event.ts, event.payload)
                    )
            covered = conn.execute(
                """SELECT seq, type, gap_from, gap_to FROM pi_events
                   WHERE session_id = ? AND instance_id = ? AND seq > ?
                   ORDER BY seq""",
                (frame.session_id, frame.instance_id, mark),
            ).fetchall()
            apply_prompt_events(
                conn, frame.session_id, frame.instance_id, tuple(frame.events)
            )
            new_mark = compute_acked_seq(
                (AckedEvent(row["seq"], row["type"], row["gap_from"], row["gap_to"])
                 for row in covered),
                mark,
            )
            conn.execute(
                """UPDATE pi_sessions SET last_seen = ?, acked_seq = ?
                   WHERE session_id = ? AND instance_id = ?""",
                (now, new_mark, frame.session_id, frame.instance_id),
            )
            changes = session_changes(inserted)
            if changes:
                assignments = ", ".join(f"{column} = ?" for column in changes)
                conn.execute(
                    f"UPDATE pi_sessions SET {assignments} WHERE session_id = ? AND instance_id = ?",
                    (*changes.values(), frame.session_id, frame.instance_id),
                )
            inserted.sort(key=lambda event: event.seq)
            return IngestResult(new_mark, tuple(inserted))

    def stored(self, session_id: str, instance_id: str, after_seq: int = 0) -> List[StoredEvent]:
        with self.db._connection() as conn:
            rows = conn.execute(
                """SELECT seq, type, ts, payload_json FROM pi_events
                   WHERE session_id = ? AND instance_id = ? AND seq > ?
                   ORDER BY seq""",
                (session_id, instance_id, after_seq),
            ).fetchall()
        return [
            StoredEvent(row["seq"], row["type"], row["ts"], json.loads(row["payload_json"]))
            for row in rows
        ]

    def page(self, session_id: str, instance_id: str, after_seq: int, limit: int) -> List[StoredEvent]:
        with self.db._connection() as conn:
            rows = conn.execute(
                """SELECT seq, type, ts, payload_json FROM pi_events
                   WHERE session_id = ? AND instance_id = ? AND seq > ?
                   ORDER BY seq LIMIT ?""",
                (session_id, instance_id, after_seq, limit + 1),
            ).fetchall()
        return [
            StoredEvent(row["seq"], row["type"], row["ts"], json.loads(row["payload_json"]))
            for row in rows
        ]

    def acked_seq(self, session_id: str, instance_id: str) -> int:
        row = self.db.sessions.get(session_id, instance_id)
        return row["acked_seq"] if row is not None else 0

    def purge_old(self, now: int) -> int:
        with self.db._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM pi_events WHERE received_at < ?", (now - RETENTION_MS,)
            )
            deleted = cursor.rowcount
        deleted += self.db.prompts.purge_closed(now - RETENTION_MS)
        return deleted
