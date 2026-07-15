"""Tests for project files: the path-safe filesystem layer and its HTTP
surface. Path traversal and symlink-escape rejection are the critical
properties here — every route funnels through project_files.resolve().
"""
import io
import os
import stat as stat_mod
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-project-files")

from chat import project_files as pf
from chat.db import ChatDB
from chat.routes import chat_bp

TOKEN = "test-token-project-files"
PROJECTS_PATH = "/api/chat/projects"


# ---------------------------------------------------------------------------
# Pure filesystem layer
# ---------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / "proj")


@pytest.fixture
def made_root(root):
    os.makedirs(root)
    return root


class TestResolve:
    def test_resolves_inside_root(self, made_root):
        assert pf.resolve(made_root, "a/b.txt") == os.path.join(made_root, "a", "b.txt")

    def test_empty_path_is_root(self, made_root):
        assert pf.resolve(made_root, "") == made_root

    @pytest.mark.parametrize("bad", [
        "../x", "a/../../x", "..", "a/..", "./x", "a//b", "a/./b",
        "a\\b", "a\x00b",
    ])
    def test_rejects_traversal_components(self, made_root, bad):
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, bad)

    def test_rejects_non_string(self, made_root):
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, None)
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, ["a"])

    def test_rejects_symlink_escape(self, made_root, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("s")
        os.symlink(str(outside), os.path.join(made_root, "link"))
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, "link/secret.txt")

    def test_rejects_symlink_escape_for_nonexistent_target(self, made_root, tmp_path):
        outside = tmp_path / "outside2"
        outside.mkdir()
        os.symlink(str(outside), os.path.join(made_root, "link"))
        # Target doesn't exist yet — the nearest existing ancestor is the
        # escaping symlink, which must still be rejected (upload path).
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, "link/new.txt")

    def test_component_too_long(self, made_root):
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, "x" * 256)

    def test_path_depth_cap(self, made_root):
        ok = "/".join(["d"] * pf.MAX_PATH_DEPTH)
        assert pf.resolve(made_root, ok)
        too_deep = "/".join(["d"] * (pf.MAX_PATH_DEPTH + 1))
        with pytest.raises(pf.ProjectFilesError):
            pf.resolve(made_root, too_deep)
        # mkdir creates missing parents, so it must respect the same cap.
        with pytest.raises(pf.ProjectFilesError):
            pf.mkdir(made_root, too_deep)


def test_configure_max_content_length():
    """Flask pre-seeds MAX_CONTENT_LENGTH=None, so a setdefault would be a
    no-op — the helper must assign over None but preserve an explicit
    deployment override."""
    app = Flask(__name__)
    assert app.config["MAX_CONTENT_LENGTH"] is None  # Flask default
    pf.configure_max_content_length(app)
    assert app.config["MAX_CONTENT_LENGTH"] == int(pf.MAX_UPLOAD_BYTES * 1.05)

    app2 = Flask(__name__)
    app2.config["MAX_CONTENT_LENGTH"] = 12345
    pf.configure_max_content_length(app2)
    assert app2.config["MAX_CONTENT_LENGTH"] == 12345


class TestOps:
    def test_mkdir_and_tree(self, made_root):
        pf.mkdir(made_root, "docs")
        pf.mkdir(made_root, "docs/notes")
        with open(os.path.join(made_root, "docs", "a.txt"), "w") as f:
            f.write("hello")
        tree = pf.build_tree(made_root)
        assert [n["name"] for n in tree] == ["docs"]
        docs = tree[0]
        assert docs["type"] == "dir"
        assert [n["name"] for n in docs["children"]] == ["notes", "a.txt"]  # dirs first
        a = docs["children"][1]
        assert a["type"] == "file" and a["size"] == 5 and a["path"] == "docs/a.txt"

    def test_mkdir_existing_409(self, made_root):
        pf.mkdir(made_root, "d")
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.mkdir(made_root, "d")
        assert e.value.status == 409

    def test_mkdir_empty_path_rejected(self, made_root):
        with pytest.raises(pf.ProjectFilesError):
            pf.mkdir(made_root, "")

    def test_save_stream_and_overwrite_semantics(self, made_root):
        node = pf.save_stream(made_root, "", "f.txt", io.BytesIO(b"one"))
        assert node["size"] == 3
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.save_stream(made_root, "", "f.txt", io.BytesIO(b"two"))
        assert e.value.status == 409
        node = pf.save_stream(made_root, "", "f.txt", io.BytesIO(b"twoo"), overwrite=True)
        assert node["size"] == 4

    def test_save_stream_missing_dir_404(self, made_root):
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.save_stream(made_root, "nope", "f.txt", io.BytesIO(b"x"))
        assert e.value.status == 404

    def test_save_stream_size_cap(self, made_root, monkeypatch):
        monkeypatch.setattr(pf, "MAX_UPLOAD_BYTES", 10)
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.save_stream(made_root, "", "big.bin", io.BytesIO(b"x" * 11))
        assert e.value.status == 413
        # Nothing left behind — neither the file nor the temp.
        assert os.listdir(made_root) == []

    def test_upload_never_clobbers_dot_uploading_user_file(self, made_root):
        """Regression: a deterministic '<target>.uploading' staging name
        would open-truncate a legitimate user file of that name."""
        pf.save_stream(made_root, "", "report.uploading", io.BytesIO(b"user data"))
        pf.save_stream(made_root, "", "report", io.BytesIO(b"new"))
        with open(os.path.join(made_root, "report.uploading"), "rb") as f:
            assert f.read() == b"user data"
        with open(os.path.join(made_root, "report"), "rb") as f:
            assert f.read() == b"new"

    def test_no_overwrite_publication_is_atomic(self, made_root, monkeypatch):
        """The 409 contract holds even when the target appears AFTER the
        pre-check (concurrent upload of the same name): the final link()
        is no-replace, so the existing file survives untouched."""
        real_mkstemp = pf.tempfile.mkstemp

        def racing_mkstemp(*args, **kwargs):
            # The competing upload wins between pre-check and publication.
            with open(os.path.join(made_root, "f.txt"), "wb") as f:
                f.write(b"winner")
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(pf.tempfile, "mkstemp", racing_mkstemp)
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.save_stream(made_root, "", "f.txt", io.BytesIO(b"loser"))
        assert e.value.status == 409
        with open(os.path.join(made_root, "f.txt"), "rb") as f:
            assert f.read() == b"winner"
        # No stray temp files left behind.
        assert os.listdir(made_root) == ["f.txt"]

    def test_move_and_conflicts(self, made_root):
        pf.mkdir(made_root, "a")
        pf.save_stream(made_root, "a", "f.txt", io.BytesIO(b"x"))
        node = pf.move(made_root, "a/f.txt", "a/g.txt")
        assert node["path"] == "a/g.txt"
        pf.save_stream(made_root, "a", "f.txt", io.BytesIO(b"y"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.move(made_root, "a/f.txt", "a/g.txt")
        assert e.value.status == 409

    def test_move_dir_into_itself_rejected(self, made_root):
        pf.mkdir(made_root, "a")
        with pytest.raises(pf.ProjectFilesError):
            pf.move(made_root, "a", "a/b")

    def test_move_source_missing_404(self, made_root):
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.move(made_root, "nope.txt", "x.txt")
        assert e.value.status == 404

    def test_delete_file_and_dir(self, made_root):
        pf.mkdir(made_root, "d")
        pf.save_stream(made_root, "d", "f.txt", io.BytesIO(b"x"))
        pf.delete(made_root, "d/f.txt")
        assert os.listdir(os.path.join(made_root, "d")) == []
        pf.save_stream(made_root, "d", "g.txt", io.BytesIO(b"x"))
        pf.delete(made_root, "d")  # recursive
        assert os.listdir(made_root) == []

    def test_delete_root_rejected(self, made_root):
        with pytest.raises(pf.ProjectFilesError):
            pf.delete(made_root, "")

    def test_delete_missing_404(self, made_root):
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.delete(made_root, "nope")
        assert e.value.status == 404

    def test_read_write_text_roundtrip(self, made_root):
        pf.mkdir(made_root, "notes")
        node = pf.write_text(made_root, "notes/todo.md", "# hello\n")
        assert node["path"] == "notes/todo.md"
        doc = pf.read_text(made_root, "notes/todo.md")
        assert doc["content"] == "# hello\n"
        assert doc["revision"] == node["revision"]

    def test_write_text_requires_parent_dir(self, made_root):
        # notes/ doesn't exist and write_text does NOT create parents
        # implicitly for a nested path whose parent is missing.
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "nope/deep/f.txt", "x")
        assert e.value.status == 404

    def test_write_text_conflict_detection(self, made_root):
        node = pf.write_text(made_root, "f.txt", "one")
        # Same base → accepted.
        pf.write_text(made_root, "f.txt", "two", base_revision=node["revision"])
        assert pf.read_text(made_root, "f.txt")["content"] == "two"
        # Stale base → 409, content untouched.
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "f.txt", "three", base_revision=node["revision"])
        assert e.value.status == 409
        assert pf.read_text(made_root, "f.txt")["content"] == "two"

    def test_write_text_conflict_even_with_identical_mtime(self, made_root):
        """Regression (PR #79 codex 1.1): the revision must not be
        timestamp-based at ANY precision — Linux stamps writes within one
        kernel timer tick identically, so even mtime_ns collides for quick
        successive saves. Force the worst case: content changed while the
        mtime (seconds AND nanoseconds) is byte-for-byte identical. The
        content-hash revision must still detect the change."""
        node = pf.write_text(made_root, "f.txt", "one")
        abs_path = os.path.join(made_root, "f.txt")
        st = os.lstat(abs_path)
        with open(abs_path, "w") as f:
            f.write("other tab")
        os.utime(abs_path, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert os.lstat(abs_path).st_mtime_ns == st.st_mtime_ns
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "f.txt", "stale save", base_revision=node["revision"])
        assert e.value.status == 409
        assert pf.read_text(made_root, "f.txt")["content"] == "other tab"

    def test_write_text_create_only(self, made_root):
        """Regression (PR #79 codex 2.2): a new-file save carries a
        create-only precondition, so a stale tree snapshot can't silently
        overwrite a file that appeared on disk since."""
        node = pf.write_text(made_root, "f.txt", "created", create_only=True)
        assert node["path"] == "f.txt"
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "f.txt", "stale create", create_only=True)
        assert e.value.status == 409
        assert pf.read_text(made_root, "f.txt")["content"] == "created"
        # Dangling symlinks occupy their name for create-only too.
        os.symlink("gone", os.path.join(made_root, "link"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "link", "x", create_only=True)
        assert e.value.status == 409

    def test_writes_preserve_permission_bits(self, made_root):
        """Regression (PR #79 codex 3.2): mkstemp stages at 0600 — an edit
        or overwriting upload must not strip the target's mode (e.g. a
        0755 script's exec bit), and fresh files get 0644, not 0600."""
        node = pf.write_text(made_root, "run.sh", "#!/bin/sh\n")
        abs_path = os.path.join(made_root, "run.sh")
        assert stat_mod.S_IMODE(os.lstat(abs_path).st_mode) == 0o644  # new-file default
        os.chmod(abs_path, 0o755)
        pf.write_text(made_root, "run.sh", "#!/bin/sh\necho hi\n")
        assert stat_mod.S_IMODE(os.lstat(abs_path).st_mode) == 0o755  # edit preserves

        pf.save_stream(made_root, "", "run.sh", io.BytesIO(b"#!/bin/sh\n"), overwrite=True)
        assert stat_mod.S_IMODE(os.lstat(abs_path).st_mode) == 0o755  # overwrite upload preserves
        pf.save_stream(made_root, "", "fresh.bin", io.BytesIO(b"x"))
        assert stat_mod.S_IMODE(os.lstat(os.path.join(made_root, "fresh.bin")).st_mode) == 0o644

    def test_write_text_conflict_when_file_deleted(self, made_root):
        node = pf.write_text(made_root, "f.txt", "one")
        pf.delete(made_root, "f.txt")
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "f.txt", "two", base_revision=node["revision"])
        assert e.value.status == 409

    def test_write_text_never_replaces_special_entries(self, made_root):
        os.symlink("anywhere", os.path.join(made_root, "link"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "link", "x")
        assert e.value.status == 409
        assert os.path.islink(os.path.join(made_root, "link"))

    def test_read_text_rejects_binary_and_oversized(self, made_root, monkeypatch):
        with open(os.path.join(made_root, "bin.dat"), "wb") as f:
            f.write(b"ab\x00cd")
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.read_text(made_root, "bin.dat")
        assert e.value.status == 400

        with open(os.path.join(made_root, "latin1.txt"), "wb") as f:
            f.write("café".encode("latin-1"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.read_text(made_root, "latin1.txt")
        assert e.value.status == 400

        monkeypatch.setattr(pf, "MAX_TEXT_EDIT_BYTES", 4)
        with open(os.path.join(made_root, "big.txt"), "w") as f:
            f.write("12345")
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.read_text(made_root, "big.txt")
        assert e.value.status == 413

    def test_write_text_size_cap(self, made_root, monkeypatch):
        monkeypatch.setattr(pf, "MAX_TEXT_EDIT_BYTES", 4)
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.write_text(made_root, "f.txt", "12345")
        assert e.value.status == 413
        assert os.listdir(made_root) == []

    def test_dangling_symlink_is_a_first_class_entry(self, made_root):
        """A broken symlink is an ordinary tree entry: renamable, occupying
        its name for mkdir and as a move destination (exists() would follow
        the link and misreport the slot as free)."""
        os.symlink("no-such-target", os.path.join(made_root, "broken"))

        # mkdir at its path: 409, not FileExistsError → 500.
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.mkdir(made_root, "broken")
        assert e.value.status == 409

        # It can't be silently replaced as a move destination.
        pf.save_stream(made_root, "", "f.txt", io.BytesIO(b"x"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.move(made_root, "f.txt", "broken")
        assert e.value.status == 409

        # And it is itself movable (the link, not its target).
        node = pf.move(made_root, "broken", "renamed-link")
        assert node["path"] == "renamed-link"
        assert os.path.islink(os.path.join(made_root, "renamed-link"))

    def test_download_rejects_non_regular_files(self, made_root, tmp_path):
        """stat_file only serves regular files: symlinks are never followed
        (even in-root ones) and FIFOs would block the worker forever."""
        (tmp_path / "target.txt").write_text("outside")
        os.symlink(str(tmp_path / "target.txt"), os.path.join(made_root, "link.txt"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.stat_file(made_root, "link.txt")
        assert e.value.status == 400

        os.mkfifo(os.path.join(made_root, "pipe"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.stat_file(made_root, "pipe")
        assert e.value.status == 400

        # Dangling symlink: still 400 (an entry, but not a regular file).
        os.symlink("gone", os.path.join(made_root, "broken"))
        with pytest.raises(pf.ProjectFilesError) as e:
            pf.stat_file(made_root, "broken")
        assert e.value.status == 400

    def test_symlink_listed_as_file_never_followed(self, made_root, tmp_path):
        outside = tmp_path / "out"
        outside.mkdir()
        (outside / "x.txt").write_text("x")
        os.symlink(str(outside), os.path.join(made_root, "link"))
        tree = pf.build_tree(made_root)
        assert tree[0]["name"] == "link"
        assert tree[0]["type"] == "file"  # not recursed into
        assert "children" not in tree[0]


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["CHAT_DB"] = ChatDB(":memory:")
    app.config["PROJECT_FILES_DIR"] = str(tmp_path / "storage")
    app.register_blueprint(chat_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _mkproject(client, name="P"):
    r = client.post(PROJECTS_PATH, json={"name": name}, headers=_auth())
    assert r.status_code == 201
    return r.get_json()["id"]


def _upload(client, pid, name, content=b"data", dir="", **form):
    return client.post(
        f"{PROJECTS_PATH}/{pid}/files/upload",
        data={"file": (io.BytesIO(content), name), "dir": dir, **form},
        headers=_auth(),
        content_type="multipart/form-data",
    )


def test_files_require_auth(client):
    pid = _mkproject(client)
    assert client.get(f"{PROJECTS_PATH}/{pid}/files").status_code == 401
    assert client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": "x"}).status_code == 401
    assert client.delete(f"{PROJECTS_PATH}/{pid}/files?path=x").status_code == 401


def test_files_unknown_project_404(client):
    r = client.get(f"{PROJECTS_PATH}/nope/files", headers=_auth())
    assert r.status_code == 404


def test_upload_tree_download_roundtrip(client):
    pid = _mkproject(client)
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": "docs"}, headers=_auth())
    assert r.status_code == 201
    r = _upload(client, pid, "a.txt", b"hello", dir="docs")
    assert r.status_code == 201
    assert r.get_json()["path"] == "docs/a.txt"

    r = client.get(f"{PROJECTS_PATH}/{pid}/files", headers=_auth())
    tree = r.get_json()["tree"]
    assert tree[0]["name"] == "docs"
    assert tree[0]["children"][0]["name"] == "a.txt"

    r = client.get(f"{PROJECTS_PATH}/{pid}/files/download?path=docs/a.txt", headers=_auth())
    assert r.status_code == 200
    assert r.data == b"hello"


def test_upload_duplicate_409_then_overwrite(client):
    pid = _mkproject(client)
    assert _upload(client, pid, "f.txt", b"one").status_code == 201
    assert _upload(client, pid, "f.txt", b"two").status_code == 409
    assert _upload(client, pid, "f.txt", b"two", overwrite="true").status_code == 201


def test_upload_missing_file_field_400(client):
    pid = _mkproject(client)
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/upload", data={},
                    headers=_auth(), content_type="multipart/form-data")
    assert r.status_code == 400


def test_traversal_rejected_on_all_routes(client):
    pid = _mkproject(client)
    bad = "../../etc/passwd"
    assert client.get(f"{PROJECTS_PATH}/{pid}/files/download?path={bad}",
                      headers=_auth()).status_code == 400
    assert client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": bad},
                       headers=_auth()).status_code == 400
    assert client.post(f"{PROJECTS_PATH}/{pid}/files/move",
                       json={"path": bad, "new_path": "x"},
                       headers=_auth()).status_code == 400
    assert client.delete(f"{PROJECTS_PATH}/{pid}/files?path={bad}",
                         headers=_auth()).status_code == 400
    r = _upload(client, pid, "f.txt", b"x", dir=bad)
    assert r.status_code == 400


def test_download_from_fresh_project_is_404_not_traversal(client):
    """Before any mutation the project root doesn't exist on disk; a
    download of a missing file must be an ordinary 404, not a
    'path escapes project root' 400."""
    pid = _mkproject(client)
    r = client.get(f"{PROJECTS_PATH}/{pid}/files/download?path=missing.txt",
                   headers=_auth())
    assert r.status_code == 404
    assert r.get_json()["error"] == "file not found"


def test_download_of_directory_400(client):
    pid = _mkproject(client)
    client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": "d"}, headers=_auth())
    r = client.get(f"{PROJECTS_PATH}/{pid}/files/download?path=d", headers=_auth())
    assert r.status_code == 400


def test_move_via_http(client):
    pid = _mkproject(client)
    _upload(client, pid, "a.txt")
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/move",
                    json={"path": "a.txt", "new_path": "b.txt"}, headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["path"] == "b.txt"


def test_delete_via_http(client):
    pid = _mkproject(client)
    _upload(client, pid, "a.txt")
    r = client.delete(f"{PROJECTS_PATH}/{pid}/files?path=a.txt", headers=_auth())
    assert r.status_code == 200
    r = client.get(f"{PROJECTS_PATH}/{pid}/files", headers=_auth())
    assert r.get_json()["tree"] == []


def test_upload_oversized_request_rejected_before_parsing(client, monkeypatch):
    """HTTP-level 413: the Content-Length check runs BEFORE request.files
    is touched, so an oversized body is refused without multipart parsing."""
    monkeypatch.setattr(pf, "MAX_UPLOAD_BYTES", 10)
    pid = _mkproject(client)
    r = _upload(client, pid, "big.bin", b"x" * 1000)
    assert r.status_code == 413


def test_tree_get_does_not_create_project_dir(client, tmp_path):
    """Read-only routes must never (re)create the files directory — a GET
    racing a project delete would otherwise leave an orphan dir."""
    pid = _mkproject(client)
    r = client.get(f"{PROJECTS_PATH}/{pid}/files", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["tree"] == []
    assert not (tmp_path / "storage" / pid).exists()


def test_mutating_op_racing_project_delete_cleans_up(client, tmp_path, monkeypatch):
    """A mutating file op that races a project delete must not leave an
    orphan directory: the commit-point revalidation notices the row is
    gone, removes the directory it recreated, and returns 404.

    NOTE: patch the module-level `pf` imported at the top of THIS file —
    it is the same module object the blueprint's route functions closed
    over. Re-importing chat.project_files_routes here would grab a fresh
    module copy when another test file (test_mcp_admin_routes) has purged
    chat.* from sys.modules, and the patch would miss the routes.
    """
    pid = _mkproject(client)
    files_dir = tmp_path / "storage" / pid

    real_mkdir = pf.mkdir
    state = {"deleted": False}

    def racing_mkdir(root, rel_path):
        node = real_mkdir(root, rel_path)
        if not state["deleted"]:
            state["deleted"] = True
            # The concurrent project delete wins mid-operation: row gone,
            # directory rmtree'd — but our mkdir already recreated paths.
            client.delete(f"{PROJECTS_PATH}/{pid}", headers=_auth())
        return node

    monkeypatch.setattr(pf, "mkdir", racing_mkdir)
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": "d"},
                    headers=_auth())
    assert r.status_code == 404
    assert not files_dir.exists()


def test_upload_multibyte_name_over_255_bytes_400(client):
    """255 characters of emoji is ~4x the filesystem's 255-BYTE component
    cap — must be a validation 400, not an ENAMETOOLONG 500."""
    pid = _mkproject(client)
    name = "😀" * 100  # 100 chars, 400 UTF-8 bytes
    r = _upload(client, pid, name, b"x")
    assert r.status_code == 400


def test_total_path_over_path_max_400(client):
    """Within the depth cap, components can still sum past PATH_MAX —
    the ENAMETOOLONG from the syscall maps to a 400."""
    pid = _mkproject(client)
    deep = "/".join(["x" * 250] * 17)  # ~4.2 KB > PATH_MAX (4096)
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir", json={"path": deep},
                    headers=_auth())
    assert r.status_code == 400


def test_lone_surrogate_path_400(client):
    """JSON delivers escaped lone surrogates that are not UTF-8-encodable;
    validation must 400, not UnicodeEncodeError → 500."""
    pid = _mkproject(client)
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir",
                    data='{"path": "\\ud800"}', headers=_auth(),
                    content_type="application/json")
    assert r.status_code == 400
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/move",
                    data='{"path": "\\ud800", "new_path": "x"}', headers=_auth(),
                    content_type="application/json")
    assert r.status_code == 400


def test_mkdir_through_regular_file_400(client):
    """mkdir with an intermediate component that is a regular file is
    ordinary bad input: 400, not NotADirectoryError → 500."""
    pid = _mkproject(client)
    assert _upload(client, pid, "parent", b"x").status_code == 201
    r = client.post(f"{PROJECTS_PATH}/{pid}/files/mkdir",
                    json={"path": "parent/child"}, headers=_auth())
    assert r.status_code == 400
    # Upload into the file-as-dir path gets the same treatment.
    r = _upload(client, pid, "f.txt", b"x", dir="parent")
    assert r.status_code == 404  # save_stream's isdir pre-check


def test_content_http_roundtrip(client):
    pid = _mkproject(client)
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "notes.md", "content": "# hi"}, headers=_auth())
    assert r.status_code == 200
    base = r.get_json()["revision"]

    r = client.get(f"{PROJECTS_PATH}/{pid}/files/content?path=notes.md", headers=_auth())
    assert r.status_code == 200
    assert r.get_json()["content"] == "# hi"

    # Save with the current revision → accepted; reusing it → 409.
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "notes.md", "content": "x", "base_revision": base},
                   headers=_auth())
    assert r.status_code == 200
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "notes.md", "content": "y", "base_revision": base},
                   headers=_auth())
    assert r.status_code == 409


def test_content_read_fresh_project_404(client):
    pid = _mkproject(client)
    r = client.get(f"{PROJECTS_PATH}/{pid}/files/content?path=missing.md", headers=_auth())
    assert r.status_code == 404


def test_content_traversal_and_bad_bodies_400(client):
    pid = _mkproject(client)
    r = client.get(f"{PROJECTS_PATH}/{pid}/files/content?path=../../etc/passwd",
                   headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "../x", "content": "c"}, headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json=["nope"], headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": 42}, headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": "c", "base_revision": 12345},
                   headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": "c", "create_only": "yes"},
                   headers=_auth())
    assert r.status_code == 400
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": "c", "create_only": True,
                         "base_revision": "abc"},
                   headers=_auth())
    assert r.status_code == 400


def test_content_create_only_http(client):
    """Stale-tree case end to end: creating over an existing file is a
    409, not a silent overwrite."""
    pid = _mkproject(client)
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": "original", "create_only": True},
                   headers=_auth())
    assert r.status_code == 200
    r = client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                   json={"path": "f.txt", "content": "stale", "create_only": True},
                   headers=_auth())
    assert r.status_code == 409
    r = client.get(f"{PROJECTS_PATH}/{pid}/files/content?path=f.txt", headers=_auth())
    assert r.get_json()["content"] == "original"


def test_content_requires_auth(client):
    pid = _mkproject(client)
    assert client.get(f"{PROJECTS_PATH}/{pid}/files/content?path=x").status_code == 401
    assert client.put(f"{PROJECTS_PATH}/{pid}/files/content",
                      json={"path": "x", "content": ""}).status_code == 401


def test_project_delete_aborts_when_files_cleanup_fails(client, tmp_path, monkeypatch):
    """A failed files cleanup must not claim success: the DB row survives
    so the delete can be retried once the filesystem problem is fixed."""
    import shutil as _shutil

    pid = _mkproject(client)
    _upload(client, pid, "a.txt")

    def failing_rmtree(path, *a, **kw):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(_shutil, "rmtree", failing_rmtree)
    r = client.delete(f"{PROJECTS_PATH}/{pid}", headers=_auth())
    assert r.status_code == 500
    monkeypatch.undo()

    # Row survived → retry succeeds and removes everything.
    r = client.delete(f"{PROJECTS_PATH}/{pid}", headers=_auth())
    assert r.status_code == 200
    assert not (tmp_path / "storage" / pid).exists()


def test_project_delete_removes_files_dir(client, tmp_path):
    pid = _mkproject(client)
    _upload(client, pid, "a.txt")
    files_dir = tmp_path / "storage" / pid
    assert files_dir.exists()
    r = client.delete(f"{PROJECTS_PATH}/{pid}", headers=_auth())
    assert r.status_code == 200
    assert not files_dir.exists()
