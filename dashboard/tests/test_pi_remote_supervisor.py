import os

from pi_remote.events import Event, EventsFrame
from pi_remote.frames import HelloFrame, ModelRef
from pi_remote.store import PiRemoteDB, RETENTION_MS
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
    assert supervisor.status()["sweeper_running"] is True
    supervisor.stop_all()
    assert supervisor.status()["running"] is False
    assert supervisor.status()["sweeper_running"] is False
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


def _hello():
    return HelloFrame(
        session_id="s1",
        instance_id="i1",
        session_file=None,
        cwd="/tmp",
        name=None,
        pid=1,
        model=ModelRef(provider="mistral", id="mistral-small-latest"),
        thinking_level=None,
        reason="startup",
        previous_session_id=None,
        pi_version=None,
        ext_version="0.1.0",
    )


def test_supervisor_closes_open_rows_on_start(tmp_path):
    db_path = str(tmp_path / "pi_remote.db")
    seed = PiRemoteDB(db_path)
    seed.upsert_session(_hello(), 1000)
    seed.close()
    directory = _socket_dir(tmp_path)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=db_path,
        clock=lambda: 2000,
    )
    supervisor.start()
    reader = PiRemoteDB(db_path)
    row = reader.get_session("s1", "i1")
    assert row["ended_at"] == 2000
    assert row["end_reason"] == "dashboard_restart"
    reader.close()
    supervisor.stop_all()

def test_supervisor_start_purges_expired_events(tmp_path):
    db_path = str(tmp_path / "pi_remote.db")
    seed = PiRemoteDB(db_path)
    seed.insert_events(
        EventsFrame(session_id="s1", instance_id="i1", events=(Event(1, 1000, "state", {"state": "idle"}),)),
        1000,
    )
    seed.close()
    directory = _socket_dir(tmp_path)
    now = 1000 + RETENTION_MS + 1
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=db_path,
        clock=lambda: now,
    )
    supervisor.start()
    reader = PiRemoteDB(db_path)
    assert reader.stored_events("s1", "i1") == []
    reader.close()
    supervisor.stop_all()
