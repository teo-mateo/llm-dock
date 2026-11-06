import os

from pi_remote.supervisor import PiRemoteSupervisor


def _socket_dir(tmp_path):
    directory = tmp_path / "sockdir"
    directory.mkdir()
    os.chmod(directory, 0o700)
    return directory


def test_supervisor_starts_and_stops(tmp_path):
    directory = _socket_dir(tmp_path)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
    )
    supervisor.start()
    status = supervisor.status()
    assert status["running"] is True
    assert status["bind_error"] is None
    assert os.path.exists(status["socket_path"])
    supervisor.start()
    assert supervisor.status()["running"] is True
    supervisor.stop_all()
    assert supervisor.status()["running"] is False
    assert not os.path.exists(status["socket_path"])
    assert os.path.exists(status["db_path"])


def test_supervisor_reports_bind_error(tmp_path):
    directory = _socket_dir(tmp_path)
    os.chmod(directory, 0o755)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
    )
    supervisor.start()
    status = supervisor.status()
    assert status["running"] is False
    assert status["bind_error"] is not None
    supervisor.stop_all()
