import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from .command_store import CommandStore
from .event_store import EventStore
from .prompt_store import PromptStore
from .schema import SCHEMA_SQL
from .session_store import SessionStore


class PiRemoteDB:
    def __init__(self, db_path: str = "pi_remote.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()
        self.sessions = SessionStore(self)
        self.events = EventStore(self)
        self.commands = CommandStore(self)
        self.prompts = PromptStore(self)

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

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._get_conn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._close_conn(conn)

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(SCHEMA_SQL)
            for table, column, definition in (
                ("pi_sessions", "acked_seq", "INTEGER NOT NULL DEFAULT 0"),
                ("pi_events", "gap_from", "INTEGER"),
                ("pi_events", "gap_to", "INTEGER"),
                ("pi_prompts", "applied_seq", "INTEGER NOT NULL DEFAULT 0"),
            ):
                columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                if column not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def close(self) -> None:
        with self._lock:
            conn = self._persistent_conn
            self._persistent_conn = None
        if conn is not None:
            conn.close()
