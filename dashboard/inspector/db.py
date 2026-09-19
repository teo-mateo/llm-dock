import json
import logging
import sqlite3
import threading
from typing import List, Optional, Tuple

from .models import Capture

logger = logging.getLogger(__name__)

MAX_CAPTURES = 2000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS captures (
    id                   TEXT PRIMARY KEY,
    service_name         TEXT NOT NULL,
    model                TEXT,
    template_type        TEXT,
    method               TEXT NOT NULL,
    path                 TEXT NOT NULL,
    status_code          INTEGER,
    stream               INTEGER NOT NULL DEFAULT 0,
    request_headers_json TEXT NOT NULL DEFAULT '{}',
    request_body         TEXT NOT NULL DEFAULT '',
    response_body        TEXT,
    response_text        TEXT,
    reasoning_text       TEXT,
    tool_calls_json      TEXT,
    finish_reason        TEXT,
    prompt_tokens        INTEGER,
    completion_tokens    INTEGER,
    total_tokens         INTEGER,
    ttfb_ms              INTEGER,
    duration_ms          INTEGER,
    error                TEXT,
    request_truncated    INTEGER NOT NULL DEFAULT 0,
    response_truncated   INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_captures_created ON captures(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_captures_service ON captures(service_name, created_at DESC);
"""

BOOLEAN_COLUMNS = ("stream", "request_truncated", "response_truncated")

BODY_COLUMNS = (
    "request_headers_json",
    "request_body",
    "response_body",
    "response_text",
    "reasoning_text",
    "tool_calls_json",
)

SUMMARY_COLUMNS = (
    "id",
    "service_name",
    "model",
    "template_type",
    "method",
    "path",
    "status_code",
    "stream",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "ttfb_ms",
    "duration_ms",
    "error",
    "request_truncated",
    "response_truncated",
    "created_at",
)

INSERT_COLUMNS = [
    "id",
    "service_name",
    "model",
    "template_type",
    "method",
    "path",
    "status_code",
    "stream",
    "request_headers_json",
    "request_body",
    "response_body",
    "response_text",
    "reasoning_text",
    "tool_calls_json",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "ttfb_ms",
    "duration_ms",
    "error",
    "request_truncated",
    "response_truncated",
]


class InspectorDB:
    def __init__(self, db_path: str = "inspector.db") -> None:
        self.db_path = db_path
        # the proxy serves requests on per-connection threads, so this instance is
        # shared across threads; the RLock is the serialisation sqlite3 then requires
        self._lock = threading.RLock()
        self._persistent_conn = None
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

    def _row_to_capture(self, row: sqlite3.Row) -> Capture:
        fields = {}
        for name in row.keys():
            value = row[name]
            if name in BOOLEAN_COLUMNS:
                value = bool(value)
            elif name == "request_headers_json" and value:
                value = json.loads(value)
            fields[name] = value
        for name in BODY_COLUMNS:
            fields.setdefault(name, None)
        return Capture(**fields)

    def insert_capture(self, capture: Capture) -> Capture:
        with self._lock:
            conn = self._get_conn()
            try:
                columns = list(INSERT_COLUMNS)
                values = [
                    capture.id,
                    capture.service_name,
                    capture.model,
                    capture.template_type,
                    capture.method,
                    capture.path,
                    capture.status_code,
                    int(capture.stream),
                    json.dumps(capture.request_headers_json),
                    capture.request_body,
                    capture.response_body,
                    capture.response_text,
                    capture.reasoning_text,
                    capture.tool_calls_json,
                    capture.finish_reason,
                    capture.prompt_tokens,
                    capture.completion_tokens,
                    capture.total_tokens,
                    capture.ttfb_ms,
                    capture.duration_ms,
                    capture.error,
                    int(capture.request_truncated),
                    int(capture.response_truncated),
                ]
                if capture.created_at is not None:
                    columns.append("created_at")
                    values.append(capture.created_at)
                conn.execute(
                    "INSERT INTO captures ({}) VALUES ({})".format(
                        ", ".join(columns), ", ".join("?" for _ in columns)
                    ),
                    values,
                )
                conn.commit()
                return self.get_capture(capture.id)
            finally:
                self._close_conn(conn)

    def get_capture(self, capture_id: str) -> Optional[Capture]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM captures WHERE id = ?", (capture_id,)
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_capture(row)
            finally:
                self._close_conn(conn)

    def list_captures(
        self,
        service: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Capture], int]:
        with self._lock:
            conn = self._get_conn()
            try:
                where = ""
                params = []
                if service:
                    where = "WHERE service_name = ?"
                    params.append(service)

                total = conn.execute(
                    f"SELECT COUNT(*) FROM captures {where}", params
                ).fetchone()[0]

                rows = conn.execute(
                    "SELECT {} FROM captures {} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?".format(
                        ", ".join(SUMMARY_COLUMNS), where
                    ),
                    params + [limit, offset],
                ).fetchall()
                return [self._row_to_capture(row) for row in rows], total
            finally:
                self._close_conn(conn)

    def delete_captures(self, service: Optional[str] = None) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                if service:
                    cursor = conn.execute(
                        "DELETE FROM captures WHERE service_name = ?", (service,)
                    )
                else:
                    cursor = conn.execute("DELETE FROM captures")
                conn.commit()
                return cursor.rowcount
            finally:
                self._close_conn(conn)

    def rename_service(self, old_name: str, new_name: str) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "UPDATE captures SET service_name = ? WHERE service_name = ?",
                    (new_name, old_name),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                self._close_conn(conn)

    def trim(self, max_rows: int = MAX_CAPTURES) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """DELETE FROM captures
                       WHERE rowid NOT IN (
                           SELECT rowid FROM captures
                           ORDER BY created_at DESC, rowid DESC
                           LIMIT ?
                       )""",
                    (max_rows,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                self._close_conn(conn)

    def services_with_captures(self) -> List[str]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT service_name FROM captures ORDER BY service_name"
                ).fetchall()
                return [row["service_name"] for row in rows]
            finally:
                self._close_conn(conn)
