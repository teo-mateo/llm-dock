import hashlib
import json
from typing import Any, Dict, Iterable, Optional, Tuple

from .command_queue import QueuedCommand
from .commands import CommandResult


class CommandStore:
    def __init__(self, db) -> None:
        self.db = db

    def record(self, command: QueuedCommand, key: Tuple[str, str]) -> None:
        digest = hashlib.sha256(
            json.dumps(dict(command.args), separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        with self.db._connection() as conn:
            conn.execute(
                """INSERT INTO pi_commands (
                    command_id, session_id, instance_id, kind, args_digest,
                    issued_at, completed_at, ok, error, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'pending')""",
                (
                    command.command_id,
                    key[0],
                    key[1],
                    command.kind,
                    digest,
                    command.issued_at,
                ),
            )

    def complete(self, result: CommandResult, now: int) -> bool:
        with self.db._connection() as conn:
            cursor = conn.execute(
                """UPDATE pi_commands
                   SET completed_at = ?, ok = ?, error = ?, outcome = 'done'
                   WHERE command_id = ? AND outcome = 'pending'""",
                (now, 1 if result.ok else 0, result.error, result.command_id),
            )
            return cursor.rowcount > 0

    def drop(self, command_ids: Iterable[str], now: int) -> int:
        ids = list(command_ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.db._connection() as conn:
            cursor = conn.execute(
                f"""UPDATE pi_commands
                    SET completed_at = ?, outcome = 'dropped'
                    WHERE outcome = 'pending' AND command_id IN ({placeholders})""",
                (now, *ids),
            )
            return cursor.rowcount

    def get(self, command_id: str) -> Optional[Dict[str, Any]]:
        with self.db._connection() as conn:
            row = conn.execute(
                "SELECT * FROM pi_commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        return dict(row) if row is not None else None
