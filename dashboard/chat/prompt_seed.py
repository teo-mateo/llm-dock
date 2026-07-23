"""Seed chat_prompts from docs/prompts/*.md on first initialization.

The seed is idempotent: it only inserts when the chat_prompts table is
empty, so user edits and reordering survive dashboard restarts.
"""
import logging
import os
import uuid
from pathlib import Path

from .db import ChatDB

logger = logging.getLogger(__name__)

_DEFAULT_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "prompts",
)


def _prompts_dir() -> str:
    """Return the directory to seed prompts from, honoring an env override."""
    return os.environ.get("LLM_DOCK_PROMPTS_DIR", _DEFAULT_PROMPTS_DIR)


def _humanize_name(filename: str) -> str:
    """Convert a kebab-case filename to a human-readable name.

    "agentic-project-work.md" -> "Agentic Project Work"
    """
    stem = Path(filename).stem
    return " ".join(word.capitalize() for word in stem.split("-"))


def seed_default_prompts(db: ChatDB) -> int:
    """Seed chat_prompts from docs/prompts/*.md if the table is empty.

    Returns the number of prompts inserted (0 if the table was already
    populated or no source files were found).
    """
    conn = db._get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM chat_prompts").fetchone()[0]
    finally:
        db._close_conn(conn)

    if count > 0:
        logger.info("chat_prompts already has %d rows; skipping seed", count)
        return 0

    prompts_dir = _prompts_dir()
    if not os.path.isdir(prompts_dir):
        logger.warning("prompt seed: directory not found: %s", prompts_dir)
        return 0

    md_files = sorted(f for f in os.listdir(prompts_dir) if f.endswith(".md"))
    if not md_files:
        logger.warning("prompt seed: no .md files found in %s", prompts_dir)
        return 0

    conn = db._get_conn()
    try:
        for idx, filename in enumerate(md_files):
            path = os.path.join(prompts_dir, filename)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            prompt_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO chat_prompts (id, name, content, sort_order) VALUES (?, ?, ?, ?)",
                (prompt_id, _humanize_name(filename), content, idx),
            )
        conn.commit()
        logger.info("seeded %d default prompts from %s", len(md_files), prompts_dir)
        return len(md_files)
    finally:
        db._close_conn(conn)
