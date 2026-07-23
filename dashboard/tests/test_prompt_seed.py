"""Tests for chat.prompt_seed — seeding chat_prompts from docs/prompts/*.md.

Covers: humanization of filenames, seeding from the real docs/prompts
directory, idempotency, sort_order assignment, content fidelity, and
graceful handling of missing/empty directories.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.db import ChatDB
from chat.prompt_seed import seed_default_prompts, _humanize_name


REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DOCS_PROMPTS_DIR = os.path.join(REPO_ROOT, "docs", "prompts")


@pytest.fixture
def db():
    return ChatDB(":memory:")


# -- _humanize_name --------------------------------------------------------


def test_humanize_name_multi_word():
    assert _humanize_name("agentic-project-work.md") == "Agentic Project Work"


def test_humanize_name_single_word():
    assert _humanize_name("hello.md") == "Hello"


def test_humanize_name_two_words():
    assert _humanize_name("terse-expert-oracle.md") == "Terse Expert Oracle"


def test_humanize_name_capitalizes_each_word():
    assert _humanize_name("my-cool-prompt.md") == "My Cool Prompt"


# -- seed from real docs/prompts -------------------------------------------


def test_seed_from_real_docs_prompts(db):
    seeded = seed_default_prompts(db)
    assert seeded == 3

    prompts = db.list_prompts()
    assert len(prompts) == 3

    names = [p.name for p in prompts]
    assert "Agentic Project Work" in names
    assert "Terse Expert Oracle" in names
    assert "Thinking Partner" in names


def test_seed_from_real_docs_prompts_sort_order(db):
    seed_default_prompts(db)
    prompts = db.list_prompts()
    assert [p.sort_order for p in prompts] == [0, 1, 2]


def test_seed_from_real_docs_prompts_alphabetical(db):
    seed_default_prompts(db)
    prompts = db.list_prompts()
    filenames = sorted(f for f in os.listdir(DOCS_PROMPTS_DIR) if f.endswith(".md"))
    expected_names = [_humanize_name(f) for f in filenames]
    assert [p.name for p in prompts] == expected_names


def test_seed_content_matches_file_contents(db):
    seed_default_prompts(db)
    prompts = {p.name: p for p in db.list_prompts()}

    for filename in os.listdir(DOCS_PROMPTS_DIR):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(DOCS_PROMPTS_DIR, filename), "r", encoding="utf-8") as fh:
            expected = fh.read()
        name = _humanize_name(filename)
        assert prompts[name].content == expected


def test_seed_generates_uuids(db):
    seed_default_prompts(db)
    prompts = db.list_prompts()
    for p in prompts:
        assert len(p.id) == 36
        assert p.id.count("-") == 4


def test_seed_sets_timestamps(db):
    seed_default_prompts(db)
    prompts = db.list_prompts()
    for p in prompts:
        assert p.created_at is not None
        assert p.updated_at is not None


# -- idempotency -----------------------------------------------------------


def test_seed_is_idempotent(db):
    seed_default_prompts(db)
    assert len(db.list_prompts()) == 3
    seeded_again = seed_default_prompts(db)
    assert seeded_again == 0
    assert len(db.list_prompts()) == 3


def test_seed_skips_when_table_not_empty(db):
    db.create_prompt("Existing", "content")
    seeded = seed_default_prompts(db)
    assert seeded == 0
    prompts = db.list_prompts()
    assert len(prompts) == 1
    assert prompts[0].name == "Existing"


def test_seed_skips_when_single_row_exists(db):
    db.create_prompt("Solo", "content")
    seeded = seed_default_prompts(db)
    assert seeded == 0
    assert len(db.list_prompts()) == 1


# -- custom directory via env override --------------------------------------


def test_seed_from_custom_dir(db, tmp_path, monkeypatch):
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "zebra.md").write_text("z content", encoding="utf-8")
    (d / "alpha.md").write_text("a content", encoding="utf-8")
    (d / "mid.md").write_text("m content", encoding="utf-8")
    (d / "not_a_prompt.txt").write_text("ignored", encoding="utf-8")

    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", str(d))
    seeded = seed_default_prompts(db)
    assert seeded == 3

    prompts = db.list_prompts()
    names = [p.name for p in prompts]
    assert names == ["Alpha", "Mid", "Zebra"]
    assert [p.sort_order for p in prompts] == [0, 1, 2]
    assert prompts[0].content == "a content"
    assert prompts[1].content == "m content"
    assert prompts[2].content == "z content"


def test_seed_empty_dir_returns_zero(db, tmp_path, monkeypatch):
    d = tmp_path / "empty_prompts"
    d.mkdir()
    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", str(d))
    seeded = seed_default_prompts(db)
    assert seeded == 0
    assert db.list_prompts() == []


def test_seed_missing_dir_returns_zero(db, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", "/nonexistent/path/that/does/not/exist")
    seeded = seed_default_prompts(db)
    assert seeded == 0
    assert db.list_prompts() == []


def test_seed_only_reads_md_files(db, tmp_path, monkeypatch):
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "real.md").write_text("real content", encoding="utf-8")
    (d / "readme.txt").write_text("txt content", encoding="utf-8")
    (d / "notes.json").write_text('{"key": "val"}', encoding="utf-8")
    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", str(d))
    seeded = seed_default_prompts(db)
    assert seeded == 1
    prompts = db.list_prompts()
    assert prompts[0].name == "Real"
    assert prompts[0].content == "real content"


# -- sort_order correctness with custom files -------------------------------


def test_seed_sort_order_alphabetical_by_filename(db, tmp_path, monkeypatch):
    d = tmp_path / "prompts"
    d.mkdir()
    for name in ["charlie.md", "alpha.md", "bravo.md"]:
        (d / name).write_text(f"content for {name}", encoding="utf-8")
    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", str(d))
    seed_default_prompts(db)

    prompts = db.list_prompts()
    assert [p.name for p in prompts] == ["Alpha", "Bravo", "Charlie"]
    assert [p.sort_order for p in prompts] == [0, 1, 2]


def test_seed_single_file_sort_order_zero(db, tmp_path, monkeypatch):
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "only.md").write_text("only content", encoding="utf-8")
    monkeypatch.setenv("LLM_DOCK_PROMPTS_DIR", str(d))
    seed_default_prompts(db)

    prompts = db.list_prompts()
    assert len(prompts) == 1
    assert prompts[0].sort_order == 0


# -- init_chat integration --------------------------------------------------


def test_init_chat_seeds_prompts(tmp_path, monkeypatch):
    """init_chat should seed the chat DB on startup."""
    from chat.routes import init_chat
    from flask import Flask

    monkeypatch.setenv("DASHBOARD_TOKEN", "test-token-seed")
    chat_db_path = str(tmp_path / "chat.db")
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = "test-token-seed"
    init_chat(app, db_path=chat_db_path)

    db = app.config["CHAT_DB"]
    prompts = db.list_prompts()
    assert len(prompts) == 3
    names = [p.name for p in prompts]
    assert "Agentic Project Work" in names
    assert "Terse Expert Oracle" in names
    assert "Thinking Partner" in names


def test_init_chat_idempotent(tmp_path, monkeypatch):
    """A second init_chat on the same DB file should not duplicate prompts."""
    from chat.routes import init_chat
    from flask import Flask

    monkeypatch.setenv("DASHBOARD_TOKEN", "test-token-seed2")
    chat_db_path = str(tmp_path / "chat.db")

    app1 = Flask(__name__)
    app1.config["DASHBOARD_TOKEN"] = "test-token-seed2"
    init_chat(app1, db_path=chat_db_path)
    assert len(app1.config["CHAT_DB"].list_prompts()) == 3

    app2 = Flask(__name__)
    app2.config["DASHBOARD_TOKEN"] = "test-token-seed2"
    init_chat(app2, db_path=chat_db_path)
    assert len(app2.config["CHAT_DB"].list_prompts()) == 3
