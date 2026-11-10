from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .frames import HelloFrame
from .schema import UPSERT_SQL

if TYPE_CHECKING:
    from .store import PiRemoteDB


class SessionStore:
    def __init__(self, db: "PiRemoteDB") -> None:
        self.db = db

    def upsert(self, frame: HelloFrame, now: int) -> None:
        model = frame.model
        values = [
            frame.session_id, frame.instance_id, frame.session_file, frame.cwd,
            frame.name, frame.pid,
            model.provider if model is not None else None,
            model.id if model is not None else None,
            frame.thinking_level, frame.reason, frame.previous_session_id,
            frame.parent_session_id, frame.pi_version, frame.ext_version, now, now,
        ]
        with self.db._connection() as conn:
            conn.execute(UPSERT_SQL, values)

    def touch(self, session_id: str, instance_id: str, now: int) -> bool:
        with self.db._connection() as conn:
            cursor = conn.execute(
                """UPDATE pi_sessions SET last_seen = ?
                   WHERE session_id = ? AND instance_id = ? AND ended_at IS NULL""",
                (now, session_id, instance_id),
            )
            return cursor.rowcount > 0

    def end(self, session_id: str, instance_id: str, reason: Optional[str], now: int) -> bool:
        with self.db._connection() as conn:
            cursor = conn.execute(
                """UPDATE pi_sessions SET ended_at = ?, end_reason = ?
                   WHERE session_id = ? AND instance_id = ? AND ended_at IS NULL""",
                (now, reason, session_id, instance_id),
            )
            return cursor.rowcount > 0

    def end_open(self, reason: str, now: int) -> int:
        with self.db._connection() as conn:
            cursor = conn.execute(
                """UPDATE pi_sessions SET ended_at = ?, end_reason = ?
                   WHERE ended_at IS NULL""",
                (now, reason),
            )
            return cursor.rowcount

    def delete(self, session_id: str, instance_id: str) -> bool:
        with self.db._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM pi_sessions WHERE session_id = ? AND instance_id = ?",
                (session_id, instance_id),
            )
            for table in ("pi_events", "pi_prompts", "pi_commands"):
                conn.execute(
                    f"DELETE FROM {table} WHERE session_id = ? AND instance_id = ?",
                    (session_id, instance_id),
                )
            return cursor.rowcount > 0

    def get(self, session_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        with self.db._connection() as conn:
            row = conn.execute(
                "SELECT * FROM pi_sessions WHERE session_id = ? AND instance_id = ?",
                (session_id, instance_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list(self) -> List[Dict[str, Any]]:
        with self.db._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pi_sessions ORDER BY first_seen DESC, rowid DESC"
            ).fetchall()
        return [dict(row) for row in rows]
