"""Tests for project files: the path-safe filesystem layer and its HTTP
surface. Path traversal and symlink-escape rejection are the critical
properties here — every route funnels through project_files.resolve().
"""
import io
import os
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


def test_project_delete_removes_files_dir(client, tmp_path):
    pid = _mkproject(client)
    _upload(client, pid, "a.txt")
    files_dir = tmp_path / "storage" / pid
    assert files_dir.exists()
    r = client.delete(f"{PROJECTS_PATH}/{pid}", headers=_auth())
    assert r.status_code == 200
    assert not files_dir.exists()
