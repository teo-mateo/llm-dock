import json
import sqlite3
import logging
from typing import Optional, List, Tuple

from .models import Conversation, Message, Critique, Artifact

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
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
        finally:
            self._close_conn(conn)

    def _migrate(self, conn: sqlite3.Connection):
        migrations = [
            ("messages", "images_json", "ALTER TABLE messages ADD COLUMN images_json TEXT"),
            ("conversations", "parent_conversation_id", "ALTER TABLE conversations ADD COLUMN parent_conversation_id TEXT"),
            ("conversations", "selected_text", "ALTER TABLE conversations ADD COLUMN selected_text TEXT"),
            ("conversations", "mcp_servers_json", "ALTER TABLE conversations ADD COLUMN mcp_servers_json TEXT"),
            ("messages", "tool_calls_json", "ALTER TABLE messages ADD COLUMN tool_calls_json TEXT"),
        ]
        for table, column, sql in migrations:
            try:
                conn.execute(sql)
                conn.commit()
                logger.info(f"Migration: added {column} column to {table}")
            except sqlite3.OperationalError:
                pass  # column already exists

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
                    parent_conversation_id, selected_text, mcp_servers_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conv.id, conv.title, conv.main_service, conv.sidekick_service,
                 conv.main_system_prompt, conv.sidekick_system_prompt,
                 conv.parent_conversation_id, conv.selected_text, conv.mcp_servers_json),
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
            return conv
        finally:
            self._close_conn(conn)

    def list_conversations(self, limit: int = 50, offset: int = 0) -> Tuple[List[Conversation], int]:
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            convs = [self._row_to_conversation(row) for row in rows]
            return convs, total
        finally:
            self._close_conn(conn)

    def update_conversation(self, conv_id: str, **kwargs) -> Optional[Conversation]:
        allowed = {"title", "main_service", "sidekick_service",
                    "main_system_prompt", "sidekick_system_prompt", "mcp_servers_json"}
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

    def delete_conversation(self, conv_id: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()
            return cursor.rowcount > 0
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

    def add_message(self, msg: Message) -> Message:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO messages
                   (id, conversation_id, role, content, reasoning_content, model_service, images_json, tool_calls_json, seq)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg.id, msg.conversation_id, msg.role, msg.content,
                 msg.reasoning_content, msg.model_service, msg.images_json, msg.tool_calls_json, msg.seq),
            )
            conn.commit()
            return self.get_message(msg.id)
        finally:
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

    def save_artifact(self, artifact: Artifact) -> Artifact:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO artifacts
                   (id, message_id, artifact_type, content, title, language)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (artifact.id, artifact.message_id, artifact.artifact_type,
                 artifact.content, artifact.title, artifact.language),
            )
            conn.commit()
            return artifact
        finally:
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
