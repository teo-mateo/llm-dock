import sqlite3
import logging
from typing import Optional, List, Tuple

from .models import Conversation, Message, Critique, Artifact, ChatRun, Project
from .runs import ChatRunStatus, ACTIVE_STATUSES, TERMINAL_STATUSES, ALL_STATUSES

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_project_updated ON projects(updated_at DESC);

CREATE TABLE IF NOT EXISTS conversations (
    id                     TEXT PRIMARY KEY,
    title                  TEXT NOT NULL DEFAULT 'New Conversation',
    main_service           TEXT NOT NULL,
    sidekick_service       TEXT,
    main_system_prompt     TEXT NOT NULL DEFAULT '',
    sidekick_system_prompt TEXT NOT NULL DEFAULT '',
    created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content         TEXT NOT NULL DEFAULT '',
    reasoning_content TEXT,
    model_service   TEXT,
    seq             INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_msg_conv_seq ON messages(conversation_id, seq);

CREATE TABLE IF NOT EXISTS critiques (
    id               TEXT PRIMARY KEY,
    message_id       TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    sidekick_service TEXT NOT NULL,
    annotations_json TEXT NOT NULL DEFAULT '[]',
    summary          TEXT,
    verdict          TEXT,
    raw_response     TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_critique_msg ON critiques(message_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id            TEXT PRIMARY KEY,
    message_id    TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    title         TEXT,
    content       TEXT NOT NULL,
    language      TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_artifact_msg ON artifacts(message_id);

CREATE TABLE IF NOT EXISTS chat_runs (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    status          TEXT NOT NULL,
    active_step     TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at      TEXT,
    completed_at    TEXT,
    cancelled_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_runs_conversation ON chat_runs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_runs_status ON chat_runs(status);
"""

# conversations.project_id was added via ALTER TABLE, which in sqlite cannot
# carry a foreign key — these triggers provide the referential half. They
# close the validate-then-write race (a project deleted between a route's
# existence check and the conversation write): the write itself fails with
# IntegrityError('project not found') instead of persisting an orphan id.
# delete_project detaches conversations in the same transaction as the
# project row's deletion, so the triggers never fire on that path.
TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_conversations_project_fk_insert
BEFORE INSERT ON conversations
WHEN NEW.project_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM projects WHERE id = NEW.project_id)
BEGIN
    SELECT RAISE(ABORT, 'project not found');
END;

CREATE TRIGGER IF NOT EXISTS trg_conversations_project_fk_update
BEFORE UPDATE OF project_id ON conversations
WHEN NEW.project_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM projects WHERE id = NEW.project_id)
BEGIN
    SELECT RAISE(ABORT, 'project not found');
END;
"""


class ChatDB:
    def __init__(self, db_path: str = "chat.db"):
        self.db_path = db_path
        self._persistent_conn = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Background runs mean concurrent writers (worker thread + request
        # threads). Wait for the write lock instead of erroring with
        # SQLITE_BUSY, so the conditional run-insert below serializes cleanly.
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _close_conn(self, conn: sqlite3.Connection):
        if conn is not self._persistent_conn:
            conn.close()

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            self._migrate(conn)
            # Created AFTER migrations: the triggers reference
            # conversations.project_id, which on a pre-existing DB only
            # exists once _migrate has added it.
            conn.executescript(TRIGGERS_SQL)
            conn.commit()
        finally:
            self._close_conn(conn)

    def _migrate(self, conn: sqlite3.Connection):
        migrations = [
            ("messages", "images_json", "ALTER TABLE messages ADD COLUMN images_json TEXT"),
            ("conversations", "parent_conversation_id", "ALTER TABLE conversations ADD COLUMN parent_conversation_id TEXT"),
            ("conversations", "selected_text", "ALTER TABLE conversations ADD COLUMN selected_text TEXT"),
            ("conversations", "mcp_servers_json", "ALTER TABLE conversations ADD COLUMN mcp_servers_json TEXT"),
            ("messages", "tool_calls_json", "ALTER TABLE messages ADD COLUMN tool_calls_json TEXT"),
            ("messages", "parse_warning_json", "ALTER TABLE messages ADD COLUMN parse_warning_json TEXT"),
            # No FK here: sqlite's ALTER TABLE can't add one, so project
            # detachment on delete is handled explicitly in delete_project.
            ("conversations", "project_id", "ALTER TABLE conversations ADD COLUMN project_id TEXT"),
        ]
        for table, column, sql in migrations:
            try:
                conn.execute(sql)
                conn.commit()
                logger.info(f"Migration: added {column} column to {table}")
            except sqlite3.OperationalError:
                pass  # column already exists

    # -- Projects --

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(self, project: Project) -> Project:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
                (project.id, project.name, project.description),
            )
            conn.commit()
            return self.get_project(project.id)
        finally:
            self._close_conn(conn)

    def get_project(self, project_id: str) -> Optional[Project]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                return None
            project = self._row_to_project(row)
            project.conversation_count = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            return project
        finally:
            self._close_conn(conn)

    def list_projects(self) -> List[Project]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY name COLLATE NOCASE"
            ).fetchall()
            projects = [self._row_to_project(row) for row in rows]
            counts = dict(conn.execute(
                "SELECT project_id, COUNT(*) FROM conversations "
                "WHERE project_id IS NOT NULL GROUP BY project_id"
            ).fetchall())
            for p in projects:
                p.conversation_count = counts.get(p.id, 0)
            return projects
        finally:
            self._close_conn(conn)

    def update_project(self, project_id: str, **kwargs) -> Optional[Project]:
        allowed = {"name", "description"}
        fields = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                fields.append(f"{key} = ?")
                params.append(val)
        if not fields:
            return self.get_project(project_id)
        fields.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')")
        params.append(project_id)
        conn = self._get_conn()
        try:
            conn.execute(
                f"UPDATE projects SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
            return self.get_project(project_id)
        finally:
            self._close_conn(conn)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project, detaching its conversations (they become
        unfiled rather than being destroyed)."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE conversations SET project_id = NULL WHERE project_id = ?",
                (project_id,),
            )
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close_conn(conn)

    # -- Conversations --

    def _row_to_conversation(self, row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"],
            title=row["title"],
            main_service=row["main_service"],
            sidekick_service=row["sidekick_service"],
            main_system_prompt=row["main_system_prompt"],
            sidekick_system_prompt=row["sidekick_system_prompt"],
            parent_conversation_id=row["parent_conversation_id"],
            selected_text=row["selected_text"],
            mcp_servers_json=row["mcp_servers_json"],
            project_id=row["project_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_conversation(self, conv: Conversation) -> Conversation:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO conversations
                   (id, title, main_service, sidekick_service,
                    main_system_prompt, sidekick_system_prompt,
                    parent_conversation_id, selected_text, mcp_servers_json, project_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conv.id, conv.title, conv.main_service, conv.sidekick_service,
                 conv.main_system_prompt, conv.sidekick_system_prompt,
                 conv.parent_conversation_id, conv.selected_text, conv.mcp_servers_json,
                 conv.project_id),
            )
            conn.commit()
            return self.get_conversation(conv.id)
        finally:
            self._close_conn(conn)

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if row is None:
                return None
            conv = self._row_to_conversation(row)
            conv.messages = self.get_messages(conv_id, conn=conn)
            run = self._active_run_for(conn, conv_id)
            conv.active_run = run.active_run_dict() if run else None
            last = self._latest_run_for(conn, conv_id)
            conv.last_run = last.last_run_dict() if last else None
            return conv
        finally:
            self._close_conn(conn)

    def list_conversations(self, limit: int = 50, offset: int = 0) -> Tuple[List[Conversation], int]:
        """List conversations, newest-updated first.

        A negative limit returns the ENTIRE list in one statement — a
        consistent snapshot (offset pagination over the mutable
        updated_at ordering can skip or duplicate rows when conversations
        are touched between page fetches).
        """
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            if limit is None or limit < 0:
                rows = conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            convs = [self._row_to_conversation(row) for row in rows]
            self._attach_active_runs(conn, convs)
            return convs, total
        finally:
            self._close_conn(conn)

    def update_conversation(self, conv_id: str, **kwargs) -> Optional[Conversation]:
        allowed = {"title", "main_service", "sidekick_service",
                    "main_system_prompt", "sidekick_system_prompt", "mcp_servers_json",
                    "project_id"}
        fields = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                fields.append(f"{key} = ?")
                params.append(val)
        if not fields:
            return self.get_conversation(conv_id)
        fields.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')")
        params.append(conv_id)
        conn = self._get_conn()
        try:
            conn.execute(
                f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
            return self.get_conversation(conv_id)
        finally:
            self._close_conn(conn)

    def _delete_conversations_recursive(self, conn: sqlite3.Connection, conv_ids: List[str]) -> int:
        """Delete the named conversations and every descendant spinoff in one
        recursive CTE. Messages cascade via FK. Returns the number of
        conversation rows deleted (sqlite3 reports -1 for DELETE-with-subquery,
        so we count via the same CTE first).
        """
        if not conv_ids:
            return 0
        placeholders = ",".join("?" for _ in conv_ids)
        cte = f"""
            WITH RECURSIVE d(id) AS (
                SELECT id FROM conversations WHERE id IN ({placeholders})
                UNION ALL
                SELECT c.id FROM conversations c JOIN d ON c.parent_conversation_id = d.id
            )
        """
        params = list(conv_ids)
        # COUNT(DISTINCT id) — UNION ALL in the recursive arm means the CTE
        # may yield duplicates when the input list already includes both a
        # parent and one of its descendants. The subsequent DELETE dedupes
        # naturally, but the raw COUNT(*) would over-report.
        count = conn.execute(cte + "SELECT COUNT(DISTINCT id) FROM d", params).fetchone()[0]
        if count == 0:
            return 0
        # Explicitly clear chat_runs for the deleted conversations. The FK is
        # ON DELETE CASCADE, but the in-memory test DB (the persistent
        # connection) doesn't enable PRAGMA foreign_keys, so don't rely on it.
        conn.execute(cte + "DELETE FROM chat_runs WHERE conversation_id IN (SELECT id FROM d)", params)
        conn.execute(cte + "DELETE FROM conversations WHERE id IN (SELECT id FROM d)", params)
        return count

    def delete_conversation(self, conv_id: str) -> bool:
        conn = self._get_conn()
        try:
            rowcount = self._delete_conversations_recursive(conn, [conv_id])
            conn.commit()
            return rowcount > 0
        finally:
            self._close_conn(conn)

    def delete_conversations(self, conv_ids: List[str]) -> int:
        """Delete multiple conversations (plus their descendant spinoffs) in
        one statement. Returns rowcount."""
        if not conv_ids:
            return 0
        conn = self._get_conn()
        try:
            rowcount = self._delete_conversations_recursive(conn, list(conv_ids))
            conn.commit()
            return rowcount
        finally:
            self._close_conn(conn)

    def touch_conversation(self, conv_id: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                (conv_id,),
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    # -- Messages --

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            reasoning_content=row["reasoning_content"],
            model_service=row["model_service"],
            images_json=row["images_json"],
            tool_calls_json=row["tool_calls_json"],
            parse_warning_json=row["parse_warning_json"] if "parse_warning_json" in row.keys() else None,
            seq=row["seq"],
            created_at=row["created_at"],
        )

    def get_messages(self, conv_id: str, conn: sqlite3.Connection = None) -> List[Message]:
        should_close = conn is None
        if conn is None:
            conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq",
                (conv_id,),
            ).fetchall()
            return [self._row_to_message(row) for row in rows]
        finally:
            if should_close:
                self._close_conn(conn)

    def get_message(self, msg_id: str) -> Optional[Message]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_message(row)
        finally:
            self._close_conn(conn)

    def next_seq(self, conv_id: str, conn: sqlite3.Connection = None) -> int:
        should_close = conn is None
        if conn is None:
            conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()
            return row[0] + 1
        finally:
            if should_close:
                self._close_conn(conn)

    def add_message(self, msg: Message, conn: sqlite3.Connection = None) -> Message:
        """Insert a message. When `conn` is passed, the caller owns the
        transaction (no commit/close here) so the insert can be part of a
        larger atomic unit; otherwise this commits on its own."""
        should_close = conn is None
        if conn is None:
            conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO messages
                   (id, conversation_id, role, content, reasoning_content, model_service, images_json, tool_calls_json, parse_warning_json, seq)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg.id, msg.conversation_id, msg.role, msg.content,
                 msg.reasoning_content, msg.model_service, msg.images_json, msg.tool_calls_json,
                 msg.parse_warning_json, msg.seq),
            )
            if should_close:
                conn.commit()
                return self.get_message(msg.id)
            # Shared transaction not yet committed — a re-fetch on a fresh
            # connection wouldn't see the row, so return the object as-is.
            return msg
        finally:
            if should_close:
                self._close_conn(conn)

    def delete_messages_from_seq(self, conv_id: str, from_seq: int) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND seq >= ?",
                (conv_id, from_seq),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            self._close_conn(conn)

    # -- Critiques --

    def _row_to_critique(self, row: sqlite3.Row) -> Critique:
        return Critique(
            id=row["id"],
            message_id=row["message_id"],
            sidekick_service=row["sidekick_service"],
            annotations_json=row["annotations_json"],
            summary=row["summary"],
            verdict=row["verdict"],
            raw_response=row["raw_response"],
            created_at=row["created_at"],
        )

    def get_critique(self, msg_id: str) -> Optional[Critique]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM critiques WHERE message_id = ?", (msg_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_critique(row)
        finally:
            self._close_conn(conn)

    def save_critique(self, critique: Critique) -> Critique:
        conn = self._get_conn()
        try:
            # Replace existing critique for same message
            conn.execute("DELETE FROM critiques WHERE message_id = ?", (critique.message_id,))
            conn.execute(
                """INSERT INTO critiques
                   (id, message_id, sidekick_service, annotations_json, summary, verdict, raw_response)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (critique.id, critique.message_id, critique.sidekick_service,
                 critique.annotations_json, critique.summary, critique.verdict,
                 critique.raw_response),
            )
            conn.commit()
            return self.get_critique(critique.message_id)
        finally:
            self._close_conn(conn)

    def get_critiques_for_conversation(self, conv_id: str) -> dict:
        """Returns a dict of message_id -> Critique for all critiqued messages in a conversation."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT c.* FROM critiques c
                   JOIN messages m ON c.message_id = m.id
                   WHERE m.conversation_id = ?""",
                (conv_id,),
            ).fetchall()
            return {row["message_id"]: self._row_to_critique(row) for row in rows}
        finally:
            self._close_conn(conn)

    # -- Artifacts --

    def _row_to_artifact(self, row: sqlite3.Row) -> Artifact:
        return Artifact(
            id=row["id"],
            message_id=row["message_id"],
            artifact_type=row["artifact_type"],
            content=row["content"],
            title=row["title"],
            language=row["language"],
            created_at=row["created_at"],
        )

    def save_artifact(self, artifact: Artifact, conn: sqlite3.Connection = None) -> Artifact:
        """Insert an artifact. When `conn` is passed, the caller owns the
        transaction (no commit/close) so it can be batched atomically."""
        should_close = conn is None
        if conn is None:
            conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO artifacts
                   (id, message_id, artifact_type, content, title, language)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (artifact.id, artifact.message_id, artifact.artifact_type,
                 artifact.content, artifact.title, artifact.language),
            )
            if should_close:
                conn.commit()
            return artifact
        finally:
            if should_close:
                self._close_conn(conn)

    def get_artifacts_for_conversation(self, conv_id: str) -> dict:
        """Returns a dict of message_id -> [Artifact] for all messages in a conversation."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT a.* FROM artifacts a
                   JOIN messages m ON a.message_id = m.id
                   WHERE m.conversation_id = ?""",
                (conv_id,),
            ).fetchall()
            result = {}
            for row in rows:
                msg_id = row["message_id"]
                if msg_id not in result:
                    result[msg_id] = []
                result[msg_id].append(self._row_to_artifact(row))
            return result
        finally:
            self._close_conn(conn)

    # -- Chat runs (issue #58) --

    def _row_to_chat_run(self, row: sqlite3.Row) -> ChatRun:
        return ChatRun(
            id=row["id"],
            conversation_id=row["conversation_id"],
            status=row["status"],
            user_message_id=row["user_message_id"],
            active_step=row["active_step"],
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            cancelled_at=row["cancelled_at"],
        )

    def _active_run_for(self, conn: sqlite3.Connection, conv_id: str) -> Optional[ChatRun]:
        """Most recent queued/running run for a conversation, or None.

        Shares the caller's connection so it can run inside get_conversation /
        list enrichment without reopening.
        """
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        # rowid (not id) is the chronological tiebreaker: created_at is only
        # second-precision and ids are random UUIDs, so within one second only
        # insertion order (rowid) reflects which run is actually newer.
        row = conn.execute(
            f"""SELECT * FROM chat_runs
                WHERE conversation_id = ? AND status IN ({placeholders})
                ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (conv_id, *sorted(ACTIVE_STATUSES)),
        ).fetchone()
        return self._row_to_chat_run(row) if row else None

    def _latest_run_for(self, conn: sqlite3.Connection, conv_id: str) -> Optional[ChatRun]:
        """Most recent run for a conversation regardless of status, or None.

        Unlike _active_run_for this includes terminal runs, so the caller can
        surface a failed background run's error after the fact. Same
        created_at/rowid ordering as _active_run_for for a consistent tiebreak.
        """
        row = conn.execute(
            """SELECT * FROM chat_runs WHERE conversation_id = ?
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (conv_id,),
        ).fetchone()
        return self._row_to_chat_run(row) if row else None

    def _attach_active_runs(self, conn: sqlite3.Connection, convs: List[Conversation]):
        """Populate conv.active_run for a batch of conversations in one query."""
        if not convs:
            return
        conv_ids = [c.id for c in convs]
        status_ph = ",".join("?" for _ in ACTIVE_STATUSES)
        conv_ph = ",".join("?" for _ in conv_ids)
        rows = conn.execute(
            f"""SELECT * FROM chat_runs
                WHERE status IN ({status_ph}) AND conversation_id IN ({conv_ph})
                ORDER BY created_at ASC, rowid ASC""",
            (*sorted(ACTIVE_STATUSES), *conv_ids),
        ).fetchall()
        # ASC by insertion order (rowid) means the last write per conversation
        # is the most recent run — chronological even within a one-second tie.
        latest = {}
        for row in rows:
            run = self._row_to_chat_run(row)
            latest[run.conversation_id] = run
        for c in convs:
            run = latest.get(c.id)
            c.active_run = run.active_run_dict() if run else None

    def create_chat_run(self, run: ChatRun) -> ChatRun:
        if run.status not in ALL_STATUSES:
            raise ValueError(f"invalid run status: {run.status!r}")
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO chat_runs
                   (id, conversation_id, user_message_id, status, active_step, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run.id, run.conversation_id, run.user_message_id,
                 run.status, run.active_step, run.error),
            )
            conn.commit()
            return self.get_chat_run(run.id)
        finally:
            self._close_conn(conn)

    def get_chat_run(self, run_id: str) -> Optional[ChatRun]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM chat_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return self._row_to_chat_run(row) if row else None
        finally:
            self._close_conn(conn)

    def get_active_run_for_conversation(self, conversation_id: str) -> Optional[ChatRun]:
        conn = self._get_conn()
        try:
            return self._active_run_for(conn, conversation_id)
        finally:
            self._close_conn(conn)

    def list_active_runs(self) -> List[ChatRun]:
        conn = self._get_conn()
        try:
            placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
            rows = conn.execute(
                f"""SELECT * FROM chat_runs WHERE status IN ({placeholders})
                    ORDER BY created_at ASC, rowid ASC""",
                tuple(sorted(ACTIVE_STATUSES)),
            ).fetchall()
            return [self._row_to_chat_run(row) for row in rows]
        finally:
            self._close_conn(conn)

    def update_chat_run_status(self, run_id: str, status: str,
                               active_step: str = None, error: str = None) -> Optional[ChatRun]:
        """Set a run's status, stamping the matching lifecycle timestamp.

        active_step / error are only written when provided (non-None), so a
        plain status bump doesn't clobber an earlier active_step. Timestamps:
        running -> started_at (first time only), completed/failed ->
        completed_at, cancelled -> cancelled_at.

        Terminal runs are frozen: the WHERE clause excludes already-terminal
        rows, so a completed/failed/cancelled run can never move back to an
        active state (the lifecycle contract). Such a call is a harmless no-op
        and returns the run unchanged.
        """
        if status not in ALL_STATUSES:
            raise ValueError(f"invalid run status: {status!r}")
        now = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"
        sets = ["status = ?"]
        params = [status]
        if active_step is not None:
            sets.append("active_step = ?")
            params.append(active_step)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if status == ChatRunStatus.RUNNING:
            sets.append(f"started_at = COALESCE(started_at, {now})")
        elif status in (ChatRunStatus.COMPLETED, ChatRunStatus.FAILED):
            sets.append(f"completed_at = {now}")
        elif status == ChatRunStatus.CANCELLED:
            sets.append(f"cancelled_at = {now}")
        terminal_ph = ",".join("?" for _ in TERMINAL_STATUSES)
        params.append(run_id)
        params.extend(sorted(TERMINAL_STATUSES))
        conn = self._get_conn()
        try:
            conn.execute(
                f"""UPDATE chat_runs SET {', '.join(sets)}
                    WHERE id = ? AND status NOT IN ({terminal_ph})""",
                params,
            )
            conn.commit()
            return self.get_chat_run(run_id)
        finally:
            self._close_conn(conn)

    def create_run_with_user_message(self, user_msg: Message, run: ChatRun,
                                     delete_from_seq: int = None) -> Optional[ChatRun]:
        """Atomically start a turn: (optionally truncate from a seq for edits),
        insert the user message, and insert the run — but ONLY if no active run
        exists for the conversation.

        The active-run guard and the message insert share one transaction, so
        the one-active-run-per-conversation invariant holds even under two
        concurrent sends (the loser's INSERT ... WHERE NOT EXISTS affects 0
        rows; everything it wrote, including an edit's truncation, is rolled
        back). Returns the created run, or None if an active run already exists.
        """
        active_ph = ",".join("?" for _ in ACTIVE_STATUSES)
        now = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"
        conn = self._get_conn()
        # Take the write lock UP FRONT with BEGIN IMMEDIATE so next_seq() is
        # allocated under the same lock as the active-run guard and the inserts.
        # A deferred transaction would read next_seq under only a read lock,
        # letting a competing request advance the tail in between and this one
        # commit a stale/duplicate seq. busy_timeout makes the second writer
        # wait for the first rather than erroring. We drive the transaction
        # manually (autocommit), restoring isolation_level afterwards because
        # the in-memory test DB reuses one persistent connection.
        prev_iso = conn.isolation_level
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if delete_from_seq is not None:
                    conn.execute(
                        "DELETE FROM messages WHERE conversation_id = ? AND seq >= ?",
                        (user_msg.conversation_id, delete_from_seq),
                    )
                user_msg.seq = self.next_seq(user_msg.conversation_id, conn=conn)
                self.add_message(user_msg, conn=conn)
                cur = conn.execute(
                    f"""INSERT INTO chat_runs
                           (id, conversation_id, user_message_id, status, active_step, error)
                        SELECT ?, ?, ?, ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM chat_runs
                            WHERE conversation_id = ? AND status IN ({active_ph})
                        )""",
                    (run.id, run.conversation_id, run.user_message_id, run.status,
                     run.active_step, run.error,
                     run.conversation_id, *sorted(ACTIVE_STATUSES)),
                )
                if cur.rowcount == 0:
                    conn.execute("ROLLBACK")  # active run already exists — undo everything
                    return None
                conn.execute(
                    f"UPDATE conversations SET updated_at = {now} WHERE id = ?",
                    (run.conversation_id,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            return self.get_chat_run(run.id)
        finally:
            conn.isolation_level = prev_iso
            self._close_conn(conn)

    def complete_run_with_message(self, run_id: str, assistant_msg: Message,
                                  artifacts: List[Artifact] = None) -> Optional[Message]:
        """Atomically finish a run: assign the message's seq, insert it and its
        artifacts, mark the run completed, and touch the conversation — all in
        one transaction.

        Terminal-guarded and all-or-nothing:
        - If the run is already terminal (e.g. cancelled mid-stream), the
          guarded UPDATE changes 0 rows; the whole transaction is rolled back
          and None is returned — no assistant message is written.
        - If any insert raises, the transaction is rolled back (re-raising) so
          a failed run never leaves an orphan completed assistant message.

        On success returns the persisted assistant_msg (with seq assigned).
        """
        artifacts = artifacts or []
        terminal_ph = ",".join("?" for _ in TERMINAL_STATUSES)
        now = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"
        conn = self._get_conn()
        try:
            assistant_msg.seq = self.next_seq(assistant_msg.conversation_id, conn=conn)
            self.add_message(assistant_msg, conn=conn)
            for art in artifacts:
                self.save_artifact(art, conn=conn)
            cur = conn.execute(
                f"""UPDATE chat_runs SET status = ?, completed_at = {now}
                    WHERE id = ? AND status NOT IN ({terminal_ph})""",
                (ChatRunStatus.COMPLETED, run_id, *sorted(TERMINAL_STATUSES)),
            )
            if cur.rowcount == 0:
                # Run went terminal (cancelled) before we could complete it —
                # discard the assistant message and artifacts entirely.
                conn.rollback()
                return None
            conn.execute(
                f"UPDATE conversations SET updated_at = {now} WHERE id = ?",
                (assistant_msg.conversation_id,),
            )
            conn.commit()
            return assistant_msg
        except Exception:
            conn.rollback()
            raise
        finally:
            self._close_conn(conn)

    def complete_chat_run(self, run_id: str) -> Optional[ChatRun]:
        return self.update_chat_run_status(run_id, ChatRunStatus.COMPLETED)

    def fail_chat_run(self, run_id: str, error: str) -> Optional[ChatRun]:
        return self.update_chat_run_status(run_id, ChatRunStatus.FAILED, error=error)

    def cancel_chat_run(self, run_id: str) -> Optional[ChatRun]:
        return self.update_chat_run_status(run_id, ChatRunStatus.CANCELLED)
