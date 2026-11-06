import os
import stat

from pi_remote.socket_path import clear_stale_socket, ensure_directory, socket_is_live


def test_ensure_directory_creates_0700(tmp_path):
    socket_path = str(tmp_path / "new" / "pi.sock")
    assert ensure_directory(socket_path) is None
    assert stat.S_IMODE(os.stat(tmp_path / "new").st_mode) == 0o700


def test_ensure_directory_refuses_group_access(tmp_path):
    directory = tmp_path / "bad"
    directory.mkdir()
    os.chmod(directory, 0o755)
    error = ensure_directory(str(directory / "pi.sock"))
    assert error is not None
    assert "0700" in error


def test_ensure_directory_reports_parent_file(tmp_path):
    parent = tmp_path / "not-a-dir"
    parent.write_text("x")
    error = ensure_directory(str(parent / "pi.sock"))
    assert error is not None
    assert "cannot create" in error


def test_socket_is_live_for_missing_and_regular_paths(tmp_path):
    assert socket_is_live(str(tmp_path / "missing.sock")) is False
    regular = tmp_path / "regular.sock"
    regular.write_text("stale")
    assert socket_is_live(str(regular)) is False


def test_clear_stale_socket_removes_a_regular_file(tmp_path):
    path = tmp_path / "regular.sock"
    path.write_text("stale")
    assert clear_stale_socket(str(path)) is None
    assert not os.path.exists(path)


def test_clear_stale_socket_ignores_a_missing_path(tmp_path):
    assert clear_stale_socket(str(tmp_path / "missing.sock")) is None
