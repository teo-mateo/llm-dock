import sqlite3
import threading
from typing import Any, Dict, List, Optional

from .frames import HelloFrame

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pi_sessions (
    session_id          TEXT NOT NULL,
    instance_id         TEXT NOT NULL,
    session_file        TEXT,
    cwd                 TEXT NOT NULL,
    name                TEXT,
    pid                 INTEGER NOT NULL,
    model_provider      TEXT,
    model_id            TEXT,
    thinking_level      TEXT,
    reason              TEXT NOT NULL,
    previous_session_id TEXT,
    pi_version          TEXT,
    ext_version         TEXT NOT NULL,
    first_seen          INTEGER NOT NULL,
    last_seen           INTEGER NOT NULL,
    ended_at            INTEGER,
    end_reason          TEXT,
    PRIMARY KEY (session_id, instance_id)
);

CREATE INDEX IF NOT EXISTS idx_pi_sessions_last_seen ON pi_sessions(last_seen);
"""

UPSERT_SQL = """
INSERT INTO pi_sessions (
    session_id, instance_id, session_file, cwd, name, pid,
    model_provider, model_id, thinking_level, reason,
    previous_session_id, pi_version, ext_version,
    first_seen, last_seen, ended_at, end_reason
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
ON CONFLICT(session_id, instance_id) DO UPDATE SET
    session_file = excluded.session_file,
    cwd = excluded.cwd,
    name = excluded.name,
    pid = excluded.pid,
    model_provider = excluded.model_provider,
    model_id = excluded.model_id,
    thinking_level = excluded.thinking_level,
    reason = excluded.reason,
    previous_session_id = excluded.previous_session_id,
    pi_version = excluded.pi_version,
    ext_version = excluded.ext_version,
    last_seen = excluded.last_seen,
    ended_at = NULL,
    end_reason = NULL
"""


class PiRemoteDB:
    def __init__(self, db_path: str = "pi_remote.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        if conn is not self._persistent_conn:
            conn.close()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript(SCHEMA_SQL)
                conn.commit()
            finally:
                self._close_conn(conn)

    def upsert_session(self, frame: HelloFrame, now: int) -> None:
        model = frame.model
        values = [
            frame.session_id,
            frame.instance_id,
            frame.session_file,
            frame.cwd,
            frame.name,
            frame.pid,
            model.provider if model is not None else None,
            model.id if model is not None else None,
            frame.thinking_level,
            frame.reason,
            frame.previous_session_id,
            frame.pi_version,
            frame.ext_version,
            now,
            now,
        ]
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(UPSERT_SQL, values)
                conn.commit()
            finally:
                self._close_conn(conn)

    def touch_session(self, session_id: str, instance_id: str, now: int) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """UPDATE pi_sessions SET last_seen = ?
                       WHERE session_id = ? AND instance_id = ? AND ended_at IS NULL""",
                    (now, session_id, instance_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)

    def end_session(self, session_id: str, instance_id: str, reason: Optional[str], now: int) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """UPDATE pi_sessions SET ended_at = ?, end_reason = ?
                       WHERE session_id = ? AND instance_id = ? AND ended_at IS NULL""",
                    (now, reason, session_id, instance_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)

    def end_open_sessions(self, reason: str, now: int) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """UPDATE pi_sessions SET ended_at = ?, end_reason = ?
                       WHERE ended_at IS NULL""",
                    (now, reason),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                self._close_conn(conn)

    def get_session(self, session_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM pi_sessions
                       WHERE session_id = ? AND instance_id = ?""",
                    (session_id, instance_id),
                ).fetchone()
                return dict(row) if row is not None else None
            finally:
                self._close_conn(conn)

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM pi_sessions ORDER BY first_seen DESC, rowid DESC"
                ).fetchall()
                return [dict(row) for row in rows]
            finally:
                self._close_conn(conn)

    def close(self) -> None:
        with self._lock:
            conn = self._persistent_conn
            self._persistent_conn = None
        if conn is not None:
            conn.close()
