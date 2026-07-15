"""Tests for the project-files MCP server and its scoping plumbing.

Three layers:
  1. The server's tool functions, called directly (FastMCP's decorator
     returns the plain function) with LLM_DOCK_PROJECT_ROOT pointed at a
     tmp directory — listing, reading, searching, and the unscoped /
     traversal error paths.
  2. The glue: ProjectScopedMCPManager env injection, with_project_files,
     runtime._build_stream auto-enable, and routes._mcp_for_conversation.
  3. One end-to-end call through a real MCPClientManager, spawning the
     actual server subprocess with the env injected — proves the
     stdio env plumbing works against the installed MCP SDK.
"""
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-pf-mcp")

from chat import project_files as pf
from chat import project_files_mcp
from chat.project_files_mcp import (
    PROJECT_ROOT_ENV,
    SERVER_ID,
    ProjectScopedMCPManager,
    with_project_files,
)
from chat.mcp_servers import project_files_server as srv
from chat.models import Conversation
from chat.runtime import ChatRunner


# ---------------------------------------------------------------------------
# Server tool functions (direct calls)
# ---------------------------------------------------------------------------


@pytest.fixture
def proj_root(tmp_path, monkeypatch):
    root = tmp_path / "proj-1"
    root.mkdir()
    (root / "notes.md").write_text("hello project\nsecond LINE with Needle\n")
    (root / "docs").mkdir()
    (root / "docs" / "plan.txt").write_text("the needle is here\n")
    (root / "docs" / "image.bin").write_bytes(b"\x00\x01\x02binary")
    monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
    return root


class TestUnscoped:
    """Without the env var every tool refuses with a clear message."""

    @pytest.fixture(autouse=True)
    def no_env(self, monkeypatch):
        monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)

    def test_list_files(self):
        assert "not part of a project" in srv.list_files()

    def test_read_file(self):
        assert "not part of a project" in srv.read_file("notes.md")

    def test_search_files(self):
        assert "not part of a project" in srv.search_files("x")


class TestListFiles:
    def test_lists_tree_with_relative_paths(self, proj_root):
        out = srv.list_files()
        lines = out.splitlines()
        assert "docs/" in lines
        assert any(l.startswith("docs/plan.txt (") for l in lines)
        assert any(l.startswith("notes.md (") for l in lines)

    def test_subdirectory_listing(self, proj_root):
        out = srv.list_files("docs")
        assert "docs/plan.txt" in out
        assert "notes.md" not in out

    def test_missing_root_reads_as_no_files_yet(self, tmp_path, monkeypatch):
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(tmp_path / "never-created"))
        assert srv.list_files() == "(the project has no files yet)"

    def test_empty_root(self, tmp_path, monkeypatch):
        root = tmp_path / "empty"
        root.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
        assert srv.list_files() == "(no files here)"

    def test_traversal_rejected(self, proj_root):
        out = srv.list_files("../..")
        assert out.startswith("Error:")

    def test_entry_cap_truncates_with_notice(self, proj_root, monkeypatch):
        # regression: codex 1.1 — unbounded listings would blow the model
        # context on a big-but-legitimate project
        monkeypatch.setattr(srv, "MAX_LIST_ENTRIES", 3)
        for i in range(6):
            (proj_root / f"file-{i}.txt").write_text("x")
        out = srv.list_files()
        lines = out.splitlines()
        assert len(lines) == 4  # 3 entries + notice
        assert "truncated at 3 of" in lines[-1]

    def test_missing_subdir_is_an_error_not_a_crash(self, proj_root):
        assert srv.list_files("nope").startswith("Error:")


class TestReadFile:
    def test_reads_content(self, proj_root):
        assert srv.read_file("docs/plan.txt") == "the needle is here\n"

    def test_missing_file(self, proj_root):
        assert srv.read_file("nope.txt").startswith("Error:")

    def test_binary_file_rejected(self, proj_root):
        assert srv.read_file("docs/image.bin").startswith("Error:")

    def test_traversal_rejected(self, proj_root):
        assert srv.read_file("../outside.txt").startswith("Error:")

    def test_symlink_rejected(self, proj_root, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("outside")
        os.symlink(secret, proj_root / "link.txt")
        assert srv.read_file("link.txt").startswith("Error:")

    def test_missing_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(tmp_path / "never-created"))
        assert srv.read_file("x.txt").startswith("Error:")

    def test_long_file_is_chunked_with_continuation_offset(self, proj_root, monkeypatch):
        # regression: codex 2.1 — a near-2MB file must not enter the model
        # context in one tool response
        monkeypatch.setattr(srv, "MAX_READ_CHARS", 10)
        (proj_root / "long.txt").write_text("abcdefghijKLMNO")
        first = srv.read_file("long.txt")
        assert first.startswith("abcdefghij")
        assert "offset=10" in first
        assert "KLMNO" not in first.split("\n(truncated")[0]
        second = srv.read_file("long.txt", offset=10)
        assert second == "KLMNO"  # final chunk: no notice

    def test_near_cap_file_response_is_bounded(self, proj_root):
        big = "x" * (pf.MAX_TEXT_EDIT_BYTES - 100)
        (proj_root / "big.txt").write_text(big)
        out = srv.read_file("big.txt")
        assert len(out) <= srv.MAX_READ_CHARS + 200  # chunk + notice, never the whole file
        assert "call read_file again with offset=" in out

    def test_offset_validation(self, proj_root):
        assert srv.read_file("notes.md", offset=-1).startswith("Error:")
        assert srv.read_file("notes.md", offset=True).startswith("Error:")
        assert "past the end" in srv.read_file("notes.md", offset=10_000)

    def test_zero_offset_on_empty_file_is_fine(self, proj_root):
        (proj_root / "empty.txt").write_text("")
        assert srv.read_file("empty.txt") == ""


class TestSearchFiles:
    def test_content_match_case_insensitive_with_line_numbers(self, proj_root):
        out = srv.search_files("NEEDLE")
        assert "docs/plan.txt:1: the needle is here" in out
        assert "notes.md:2: second LINE with Needle" in out

    def test_name_match(self, proj_root):
        out = srv.search_files("plan")
        assert "docs/plan.txt (name match)" in out

    def test_binary_files_skipped(self, proj_root):
        out = srv.search_files("binary")
        assert "image.bin:" not in out

    def test_scoped_to_subdirectory(self, proj_root):
        out = srv.search_files("needle", path="docs")
        assert "docs/plan.txt:1:" in out
        assert "notes.md" not in out

    def test_no_matches(self, proj_root):
        assert srv.search_files("zzz-not-there") == "No matches."

    def test_empty_query_rejected(self, proj_root):
        assert srv.search_files("  ").startswith("Error:")

    def test_traversal_rejected(self, proj_root):
        assert srv.search_files("x", path="../..").startswith("Error:")

    def test_missing_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(tmp_path / "never-created"))
        assert "no files yet" in srv.search_files("x")

    def test_truncation_cap(self, proj_root, monkeypatch):
        monkeypatch.setattr(srv, "MAX_SEARCH_RESULTS", 2)
        (proj_root / "many.txt").write_text("needle\n" * 10)
        out = srv.search_files("needle")
        assert "truncated at 2 matches" in out
        # cap counts matches, not lines scanned: 2 matches + the notice
        assert len(out.splitlines()) == 3

    def test_cap_enforced_after_name_match(self, tmp_path, monkeypatch):
        # regression: codex 1.3 — a name match landing exactly on the cap
        # let the same file's content matches overshoot it
        root = tmp_path / "cap-proj"
        root.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
        monkeypatch.setattr(srv, "MAX_SEARCH_RESULTS", 2)
        (root / "aaa.txt").write_text("needle\n")            # content match 1
        (root / "needle-b.txt").write_text("needle inside\n")  # name match 2, content would be 3
        out = srv.search_files("needle")
        lines = out.splitlines()
        assert len(lines) == 3  # exactly cap + notice, no overshoot
        assert "needle-b.txt (name match)" in lines
        assert not any("needle-b.txt:1:" in l for l in lines)
        assert "truncated at 2 matches" in lines[-1]

    def test_scan_budget_stops_early_with_notice(self, tmp_path, monkeypatch):
        # regression: codex 1.2 — a no-match query must stop reading files
        # once the byte budget is spent instead of grinding to the timeout
        root = tmp_path / "budget-proj"
        root.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
        monkeypatch.setattr(srv, "MAX_SEARCH_SCAN_BYTES", 10)
        (root / "aaa.txt").write_text("needle A\n")  # 9 bytes: within budget
        (root / "bbb.txt").write_text("needle B\n")  # would exceed: not scanned
        out = srv.search_files("needle")
        assert "aaa.txt:1:" in out
        assert "bbb.txt" not in out
        assert "scan budget reached" in out

    def test_scan_budget_notice_even_with_no_matches(self, tmp_path, monkeypatch):
        root = tmp_path / "budget-proj-2"
        root.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
        monkeypatch.setattr(srv, "MAX_SEARCH_SCAN_BYTES", 1)
        (root / "aaa.txt").write_text("nothing here\n")
        out = srv.search_files("zzz-not-there")
        assert out.startswith("No matches.")
        assert "scan budget reached" in out

    def test_oversized_files_do_not_consume_budget(self, tmp_path, monkeypatch):
        # files read_text would reject are skipped before budget accounting
        root = tmp_path / "budget-proj-3"
        root.mkdir()
        monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
        monkeypatch.setattr(srv, "MAX_SEARCH_SCAN_BYTES", 20)
        big = "x" * (pf.MAX_TEXT_EDIT_BYTES + 1)
        (root / "aaa-big.txt").write_text(big)
        (root / "bbb.txt").write_text("needle\n")
        out = srv.search_files("needle")
        assert "bbb.txt:1: needle" in out
        assert "scan budget" not in out


# ---------------------------------------------------------------------------
# Glue: scoped manager, auto-enable, routes helper
# ---------------------------------------------------------------------------


class FakeManager:
    def __init__(self):
        self.calls = []

    def get_tools(self, server_id):
        return [{"id": server_id}]

    def get_all_tools(self, server_ids):
        self.calls.append(("get_all_tools", list(server_ids)))
        return [{"id": sid} for sid in server_ids]

    def call_tool(self, server_id, tool_name, arguments, extra_env=None):
        self.calls.append(("call_tool", server_id, tool_name, arguments, extra_env))
        return ("ok", [])


class TestScopedManager:
    def test_injects_env_for_project_files_only(self):
        inner = FakeManager()
        scoped = ProjectScopedMCPManager(inner, "/data/projects/p1")
        scoped.call_tool(SERVER_ID, "list_files", {})
        scoped.call_tool("sympy-math", "solve_equation", {"equation": "x"})
        assert inner.calls[0] == (
            "call_tool", SERVER_ID, "list_files", {},
            {PROJECT_ROOT_ENV: "/data/projects/p1"},
        )
        assert inner.calls[1][4] is None

    def test_delegates_tool_listing(self):
        inner = FakeManager()
        scoped = ProjectScopedMCPManager(inner, "/p")
        assert scoped.get_all_tools(["a", "b"]) == [{"id": "a"}, {"id": "b"}]
        assert scoped.get_tools("a") == [{"id": "a"}]


class TestWithProjectFiles:
    def test_appends_when_absent(self):
        assert with_project_files(["sympy-math"]) == ["sympy-math", SERVER_ID]

    def test_no_duplicate_when_present(self):
        assert with_project_files([SERVER_ID]) == [SERVER_ID]

    def test_empty(self):
        assert with_project_files([]) == [SERVER_ID]


def _conv(**kw):
    return Conversation(id="c1", title="t", main_service="svc", **kw)


def _conv2(conv_id, **kw):
    return Conversation(id=conv_id, title="t", main_service="svc", **kw)


class FakePersistence:
    def load_messages(self, conv):
        return []


class TestRuntimeAutoEnable:
    """_build_stream consumes the effective project snapshotted at run
    creation (ChatTurnRequest.effective_project_id) — it never re-resolves,
    so the runner is exercised with the id passed explicitly."""

    def test_project_conversation_gets_project_files_tools_and_hint(self):
        runner = ChatRunner(persistence=FakePersistence())
        mgr = FakeManager()
        conv = _conv(project_id="p1", mcp_servers_json=json.dumps(["sympy-math"]))
        runner._build_stream(conv, mgr, "p1")
        assert ("get_all_tools", ["sympy-math", SERVER_ID]) in mgr.calls

    def test_project_conversation_with_no_toggles_still_gets_tools(self):
        runner = ChatRunner(persistence=FakePersistence())
        mgr = FakeManager()
        runner._build_stream(_conv(project_id="p1"), mgr, "p1")
        assert ("get_all_tools", [SERVER_ID]) in mgr.calls

    def test_hint_lands_in_system_prompt(self):
        from chat.prompt_builder import build_chat_messages
        messages = build_chat_messages("base prompt", [], [SERVER_ID])
        assert "list_files" in messages[0]["content"]

    def test_non_project_conversation_unchanged(self):
        runner = ChatRunner(persistence=FakePersistence())
        mgr = FakeManager()
        runner._build_stream(_conv(), mgr)
        assert mgr.calls == []  # no enabled servers -> no tool discovery

    def test_runner_does_not_resolve_on_its_own(self):
        # The row carries a project, but no snapshot was passed: the runner
        # must NOT fall back to conv.project_id — resolution has exactly one
        # owner (routes._effective_project_id at run creation).
        runner = ChatRunner(persistence=FakePersistence())
        mgr = FakeManager()
        runner._build_stream(_conv(project_id="p1"), mgr)
        assert mgr.calls == []

class TestSnapshotThreading:
    """The snapshot must actually travel start() → executor → _execute →
    ChatTurnRequest → run() → _build_stream, not merely exist as a field
    (regression: codex #82 1.2)."""

    def test_run_manager_threads_snapshot_into_the_request(self):
        import threading as _threading
        from types import SimpleNamespace
        from chat.db import ChatDB
        from chat.event_bus import EventBus
        from chat.run_manager import ChatRunManager

        manager = ChatRunManager(ChatDB(":memory:"), EventBus())
        captured = {}
        done = _threading.Event()

        class SpyRunner:
            def run(self, run, request, cancel_check=None):
                captured["request"] = request
                done.set()
                return None

        manager.runner = SpyRunner()
        conv = _conv(project_id="p1")
        try:
            manager.start(conv, SimpleNamespace(id="r1"), mcp_manager=None,
                          effective_project_id="p9")
            assert done.wait(timeout=5)
        finally:
            manager.shutdown()
        assert captured["request"].effective_project_id == "p9"
        assert captured["request"].conversation is conv

    def test_dbless_run_consumes_the_snapshot(self):
        # The ephemeral-caller contract (the Ghost Chat #57 shape): no db
        # wired, the run-creation site passes the snapshot explicitly, and
        # it reaches _build_stream through run() itself — resolution stays
        # with the caller, never the runner (codex #82 1.1).
        from types import SimpleNamespace
        from chat.persistence import NullPersistencePolicy
        from chat.runtime import ChatTurnRequest

        captured = {}

        class CapturingRunner(ChatRunner):
            def _build_stream(self, conv, mcp_manager, effective_project_id=None):
                captured["project_id"] = effective_project_id
                yield ("done", {"content": "ok", "reasoning_content": None})

        runner = CapturingRunner(db=None, persistence=NullPersistencePolicy())
        conv = _conv(project_id="p1")
        msg = runner.run(SimpleNamespace(id="r1"),
                         ChatTurnRequest(conversation=conv, mcp_manager=None,
                                         effective_project_id="p1"))
        assert captured["project_id"] == "p1"
        assert msg is not None and msg.content == "ok"


class TestRoutesHelper:
    @pytest.fixture
    def app(self, tmp_path):
        app = Flask(__name__)
        app.config["MCP_MANAGER"] = FakeManager()
        app.config["PROJECT_FILES_DIR"] = str(tmp_path / "storage")
        return app

    def test_none_without_servers_or_project(self, app):
        from chat.routes import _mcp_for_conversation
        with app.app_context():
            assert _mcp_for_conversation(_conv(), [], None) is None

    def test_plain_manager_for_toggled_non_project_conversation(self, app):
        from chat.routes import _mcp_for_conversation
        with app.app_context():
            mgr = _mcp_for_conversation(_conv(), ["sympy-math"], None)
        assert mgr is app.config["MCP_MANAGER"]

    def test_scoped_manager_for_project_conversation(self, app, tmp_path):
        # NOTE: import the class inside the test, not at module top —
        # test_mcp_admin_routes purges chat.* from sys.modules and
        # re-imports, so the top-level binding can be a different class
        # object than the one chat.routes instantiates (isinstance against
        # it fails on suite ordering, not on behavior).
        from chat.routes import _mcp_for_conversation
        from chat.project_files_mcp import ProjectScopedMCPManager as CurrentScoped
        with app.app_context():
            mgr = _mcp_for_conversation(_conv(project_id="p1"), [], "p1")
        assert isinstance(mgr, CurrentScoped)
        mgr.call_tool(SERVER_ID, "list_files", {})
        call = app.config["MCP_MANAGER"].calls[-1]
        assert call[4] == {PROJECT_ROOT_ENV: str(tmp_path / "storage" / "p1")}


class TestSpinoffInheritance:
    """Membership is root-only: spin-offs keep project_id NULL and follow
    their root ancestor. Tool scoping must resolve through the chain
    (regression: codex 3.1)."""

    @pytest.fixture
    def db(self, tmp_path):
        from chat.db import ChatDB
        from chat.models import Project
        db = ChatDB(str(tmp_path / "chat.db"))
        db.create_project(Project(id="p1", name="P"))
        db.create_conversation(_conv2("root", project_id="p1"))
        db.create_conversation(_conv2("child", parent_conversation_id="root"))
        db.create_conversation(_conv2("grand", parent_conversation_id="child"))
        db.create_conversation(_conv2("loner"))
        return db

    def test_resolve_project_id(self, db):
        assert db.resolve_project_id("root") == "p1"
        assert db.resolve_project_id("child") == "p1"
        assert db.resolve_project_id("grand") == "p1"
        assert db.resolve_project_id("loner") is None
        assert db.resolve_project_id("missing") is None

    def test_resolve_survives_a_parent_cycle(self, db):
        # Impossible through the API; the walk must still terminate on
        # corrupt data instead of hanging the request.
        conn = db._get_conn()
        try:
            conn.execute(
                "UPDATE conversations SET parent_conversation_id = 'grand' WHERE id = 'child'"
            )
            conn.commit()
        finally:
            db._close_conn(conn)
        assert db.resolve_project_id("child") is None

    def test_effective_project_id_resolves_through_the_chain(self, db):
        from chat.routes import _effective_project_id
        app = Flask(__name__)
        app.config["CHAT_DB"] = db
        with app.app_context():
            assert _effective_project_id(db.get_conversation("root")) == "p1"
            assert _effective_project_id(db.get_conversation("child")) == "p1"
            assert _effective_project_id(db.get_conversation("grand")) == "p1"
            assert _effective_project_id(db.get_conversation("loner")) is None

    def test_routes_scope_spinoff_to_root_project(self, db, tmp_path):
        from chat.routes import _effective_project_id, _mcp_for_conversation
        app = Flask(__name__)
        app.config["MCP_MANAGER"] = FakeManager()
        app.config["PROJECT_FILES_DIR"] = str(tmp_path / "storage")
        app.config["CHAT_DB"] = db
        child = db.get_conversation("child")
        assert child.project_id is None  # root-only membership held
        with app.app_context():
            project_id = _effective_project_id(child)
            mgr = _mcp_for_conversation(child, [], project_id)
        assert mgr is not None
        mgr.call_tool(SERVER_ID, "list_files", {})
        call = app.config["MCP_MANAGER"].calls[-1]
        assert call[4] == {PROJECT_ROOT_ENV: str(tmp_path / "storage" / "p1")}

    def test_runtime_auto_enables_for_spinoff_snapshot(self, db):
        # The runner gets the resolved project as a snapshot, the same value
        # routes bound the manager with — spin-off rows carry NULL themselves.
        runner = ChatRunner(db=db, persistence=FakePersistence())
        mgr = FakeManager()
        grand = db.get_conversation("grand")
        assert grand.project_id is None
        runner._build_stream(grand, mgr, db.resolve_project_id("grand"))
        assert ("get_all_tools", [SERVER_ID]) in mgr.calls

    def test_spinoff_cannot_carry_project_directly(self, db):
        # DB-level enforcement of root-only membership (codex arch rec 2):
        # neither inserting a spin-off with a project nor attaching a
        # project to an existing spin-off can slip past the triggers.
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            db.create_conversation(
                _conv2("bad", parent_conversation_id="root", project_id="p1"))
        conn = db._get_conn()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE conversations SET project_id = 'p1' WHERE id = 'child'")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE conversations SET parent_conversation_id = 'loner' WHERE id = 'root'")
        finally:
            db._close_conn(conn)
        # detach-on-delete stays allowed: setting NULL never trips the trigger
        conn = db._get_conn()
        try:
            conn.execute("UPDATE conversations SET project_id = NULL WHERE id = 'root'")
            conn.commit()
        finally:
            db._close_conn(conn)


class TestRunAsyncTimeout:
    def test_timeout_cancels_the_coroutine(self):
        # regression: codex 1.2 — a timed-out call must not leave the
        # coroutine (and the server subprocess it holds) running on the
        # loop after the caller has already received the error
        import asyncio
        import concurrent.futures
        import threading
        from chat.mcp_client import MCPClientManager

        manager = MCPClientManager()
        cancelled = threading.Event()

        async def slow():
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        with pytest.raises(concurrent.futures.TimeoutError):
            manager._run_async(slow(), timeout=0.2)
        assert cancelled.wait(timeout=5)


# ---------------------------------------------------------------------------
# End-to-end: real subprocess spawn with env injection
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_call_tool_spawns_scoped_server(self, tmp_path):
        from chat.mcp_client import MCPClientManager

        root = tmp_path / "p-e2e"
        root.mkdir()
        (root / "hello.txt").write_text("end to end needle\n")

        manager = MCPClientManager()
        scoped = ProjectScopedMCPManager(manager, str(root))

        text, artifacts = scoped.call_tool(SERVER_ID, "list_files", {})
        assert "hello.txt" in text
        assert artifacts == []

        text, _ = scoped.call_tool(SERVER_ID, "read_file", {"path": "hello.txt"})
        assert text == "end to end needle\n"

        text, _ = scoped.call_tool(SERVER_ID, "search_files", {"query": "NEEDLE"})
        assert "hello.txt:1: end to end needle" in text

    def test_unscoped_call_reports_no_project(self):
        from chat.mcp_client import MCPClientManager

        manager = MCPClientManager()
        text, _ = manager.call_tool(SERVER_ID, "list_files", {})
        assert "not part of a project" in text

    def test_tool_discovery_lists_all_three(self):
        from chat.mcp_client import MCPClientManager

        manager = MCPClientManager()
        tools = manager.get_tools(SERVER_ID)
        names = {t["function"]["name"] for t in tools}
        assert names == {
            f"{SERVER_ID}__list_files",
            f"{SERVER_ID}__read_file",
            f"{SERVER_ID}__search_files",
        }
