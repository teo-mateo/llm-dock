"""Tests for chat_prompts table and ChatDB CRUD methods (issue #93).

Covers table creation, create/get/list/update/delete, reordering, and
timestamp semantics (created_at set on create only; updated_at on both).
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.db import ChatDB
from chat.models import Prompt


@pytest.fixture
def db():
    return ChatDB(":memory:")


# -- Table creation -------------------------------------------------------


def test_chat_prompts_table_exists(db):
    row = db._get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_prompts'"
    ).fetchone()
    assert row is not None


def test_chat_prompts_columns(db):
    cols = db._get_conn().execute(
        "PRAGMA table_info(chat_prompts)"
    ).fetchall()
    names = {c["name"] for c in cols}
    assert names == {"id", "name", "content", "sort_order", "created_at", "updated_at"}


# -- create_prompt --------------------------------------------------------


def test_create_prompt_returns_prompt(db):
    p = db.create_prompt("My Prompt", "You are a helpful assistant.")
    assert isinstance(p, Prompt)
    assert p.id
    assert p.name == "My Prompt"
    assert p.content == "You are a helpful assistant."
    assert p.sort_order >= 1
    assert p.created_at is not None
    assert p.updated_at is not None


def test_create_prompt_sets_created_and_updated_at(db):
    p = db.create_prompt("P1", "content 1")
    assert p.created_at == p.updated_at


def test_create_prompt_assigns_increasing_sort_order(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    p3 = db.create_prompt("Third", "content 3")
    assert p1.sort_order < p2.sort_order < p3.sort_order


def test_create_prompt_persists(db):
    p = db.create_prompt("Persisted", "content")
    fetched = db.get_prompt(p.id)
    assert fetched is not None
    assert fetched.name == "Persisted"
    assert fetched.content == "content"


def test_create_prompt_generates_uuid(db):
    p = db.create_prompt("UUID Test", "content")
    assert len(p.id) == 36
    assert p.id.count("-") == 4


# -- get_prompt -----------------------------------------------------------


def test_get_prompt_returns_none_for_missing(db):
    assert db.get_prompt("nonexistent-id") is None


def test_get_prompt_returns_prompt(db):
    p = db.create_prompt("Get Me", "content")
    fetched = db.get_prompt(p.id)
    assert fetched is not None
    assert fetched.id == p.id
    assert fetched.name == "Get Me"
    assert fetched.content == "content"
    assert fetched.sort_order == p.sort_order


def test_get_prompt_returns_full_data(db):
    p = db.create_prompt("Full Data", "detailed content here")
    fetched = db.get_prompt(p.id)
    assert fetched.content == "detailed content here"
    assert fetched.created_at == p.created_at
    assert fetched.updated_at == p.updated_at


# -- list_prompts ---------------------------------------------------------


def test_list_prompts_empty(db):
    assert db.list_prompts() == []


def test_list_prompts_returns_all(db):
    db.create_prompt("A", "content a")
    db.create_prompt("B", "content b")
    prompts = db.list_prompts()
    assert len(prompts) == 2


def test_list_prompts_ordered_by_sort_order(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    p3 = db.create_prompt("Third", "content 3")
    db.reorder_prompts([p3.id, p2.id, p1.id])
    prompts = db.list_prompts()
    assert [p.id for p in prompts] == [p3.id, p2.id, p1.id]
    assert [p.sort_order for p in prompts] == [0, 1, 2]


def test_list_prompts_default_order_is_creation_order(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    p3 = db.create_prompt("Third", "content 3")
    prompts = db.list_prompts()
    assert [p.id for p in prompts] == [p1.id, p2.id, p3.id]


# -- update_prompt --------------------------------------------------------


def test_update_prompt_modifies_name_and_content(db):
    p = db.create_prompt("Original", "original content")
    updated = db.update_prompt(p.id, "Updated", "updated content")
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.content == "updated content"
    assert updated.id == p.id


def test_update_prompt_sets_updated_at(db):
    p = db.create_prompt("P", "content")
    original_updated = p.updated_at
    time.sleep(1.1)
    updated = db.update_prompt(p.id, "New Name", "new content")
    assert updated.updated_at != original_updated


def test_update_prompt_does_not_change_created_at(db):
    p = db.create_prompt("P", "content")
    original_created = p.created_at
    updated = db.update_prompt(p.id, "New Name", "new content")
    assert updated.created_at == original_created


def test_update_prompt_returns_none_for_missing(db):
    assert db.update_prompt("nonexistent-id", "Name", "content") is None


def test_update_prompt_persists(db):
    p = db.create_prompt("Original", "original content")
    db.update_prompt(p.id, "Updated", "updated content")
    fetched = db.get_prompt(p.id)
    assert fetched.name == "Updated"
    assert fetched.content == "updated content"


# -- delete_prompt --------------------------------------------------------


def test_delete_prompt_returns_true_for_existing(db):
    p = db.create_prompt("Delete Me", "content")
    assert db.delete_prompt(p.id) is True


def test_delete_prompt_returns_false_for_missing(db):
    assert db.delete_prompt("nonexistent-id") is False


def test_delete_prompt_removes_prompt(db):
    p = db.create_prompt("Delete Me", "content")
    db.delete_prompt(p.id)
    assert db.get_prompt(p.id) is None


def test_delete_prompt_only_deletes_target(db):
    p1 = db.create_prompt("Keep Me", "content 1")
    p2 = db.create_prompt("Delete Me", "content 2")
    db.delete_prompt(p2.id)
    assert db.get_prompt(p1.id) is not None
    assert db.get_prompt(p2.id) is None


def test_delete_prompt_preserves_others_order(db):
    p1 = db.create_prompt("A", "content a")
    p2 = db.create_prompt("B", "content b")
    p3 = db.create_prompt("C", "content c")
    db.reorder_prompts([p3.id, p1.id, p2.id])
    db.delete_prompt(p3.id)
    prompts = db.list_prompts()
    assert [p.id for p in prompts] == [p1.id, p2.id]


# -- reorder_prompts ------------------------------------------------------


def test_reorder_prompts_updates_sort_order(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    p3 = db.create_prompt("Third", "content 3")
    db.reorder_prompts([p3.id, p1.id, p2.id])
    prompts = {p.id: p for p in db.list_prompts()}
    assert prompts[p3.id].sort_order == 0
    assert prompts[p1.id].sort_order == 1
    assert prompts[p2.id].sort_order == 2


def test_reorder_prompts_reflected_in_list(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    db.reorder_prompts([p2.id, p1.id])
    prompts = db.list_prompts()
    assert prompts[0].id == p2.id
    assert prompts[1].id == p1.id


def test_reorder_prompts_partial_list(db):
    p1 = db.create_prompt("First", "content 1")
    p2 = db.create_prompt("Second", "content 2")
    p3 = db.create_prompt("Third", "content 3")
    db.reorder_prompts([p2.id, p1.id])
    prompts = {p.id: p for p in db.list_prompts()}
    assert prompts[p2.id].sort_order == 0
    assert prompts[p1.id].sort_order == 1
    assert prompts[p3.id].sort_order == 3


def test_reorder_prompts_empty_list(db):
    db.create_prompt("A", "content")
    db.reorder_prompts([])
    prompts = db.list_prompts()
    assert len(prompts) == 1


def test_reorder_prompts_single(db):
    p = db.create_prompt("Only", "content")
    db.reorder_prompts([p.id])
    fetched = db.get_prompt(p.id)
    assert fetched.sort_order == 0


# -- Prompt.to_dict -------------------------------------------------------


def test_prompt_to_dict(db):
    p = db.create_prompt("Test", "content")
    d = p.to_dict()
    assert d["id"] == p.id
    assert d["name"] == "Test"
    assert d["content"] == "content"
    assert d["sort_order"] == p.sort_order
    assert d["created_at"] == p.created_at
    assert d["updated_at"] == p.updated_at
