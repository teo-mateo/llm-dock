import os
from dataclasses import replace

import pytest

from pi_remote.contract import STALE_AFTER_MS
from pi_remote.events import Event, EventsFrame
from pi_remote.frames import HelloFrame, ModelRef
from pi_remote.store import PiRemoteDB
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


def test_sessions_live_first_then_last_seen_desc(tmp_path):
    directory = _socket_dir(tmp_path)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    supervisor.start()
    store = supervisor._store
    store.upsert_session(replace(_hello(), session_id="s2"), 2000)
    store.end_session("s2", "i1", "remote_off", 2000)
    store.upsert_session(replace(_hello(), session_id="s3"), 1500)
    store.end_session("s3", "i1", "remote_off", 1500)
    store.upsert_session(_hello(), 1000)
    supervisor._registry.register(_hello(), 1000)

    summaries = supervisor.sessions()
    assert [summary.session_id for summary in summaries] == ["s1", "s2", "s3"]
    assert summaries[0].live is True
    assert summaries[0].last_seen == 1000
    assert summaries[1].live is False
    assert summaries[2].live is False
    supervisor.stop_all()


def test_events_unknown_key_is_none(tmp_path):
    directory = _socket_dir(tmp_path)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    supervisor.start()
    assert supervisor.events("missing", "i1") is None
    supervisor.stop_all()


def test_events_pages_through_all_stored_events(tmp_path):
    directory = _socket_dir(tmp_path)
    supervisor = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    supervisor.start()
    store = supervisor._store
    store.upsert_session(_hello(), 1000)
    events = tuple(
        Event(seq, seq * 1000, "state", {"state": "idle"})
        for seq in range(1, 451)
    )
    store.ingest(EventsFrame("s1", "i1", events), 1000)

    first = supervisor.events("s1", "i1", after_seq=0, limit=200)
    assert len(first.events) == 200
    assert first.next_after == 200
    assert first.has_more is True

    second = supervisor.events("s1", "i1", after_seq=first.next_after, limit=200)
    assert len(second.events) == 200
    assert second.next_after == 400
    assert second.has_more is True

    third = supervisor.events("s1", "i1", after_seq=second.next_after, limit=200)
    assert len(third.events) == 50
    assert third.next_after == 450
    assert third.has_more is False
    supervisor.stop_all()


@pytest.fixture
def supervisor(tmp_path):
    directory = _socket_dir(tmp_path)
    instance = PiRemoteSupervisor(
        socket_path=str(directory / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.stop_all()


def _hello_body():
    return {
        "protocol": 1,
        "type": "hello",
        "session_id": "s1",
        "instance_id": "i1",
        "session_file": None,
        "cwd": "/tmp",
        "name": "probe",
        "pid": 1,
        "model": {"provider": "mistral", "id": "mistral-small-latest"},
        "thinking_level": "high",
        "reason": "startup",
        "previous_session_id": None,
        "pi_version": None,
        "ext_version": "0.1.0",
    }


def _heartbeat_body(state):
    return {
        "protocol": 1,
        "type": "heartbeat",
        "session_id": "s1",
        "instance_id": "i1",
        "state": state,
        "context": None,
        "sent_at": 1000,
    }


def _bye_body(reason="shutdown"):
    return {
        "protocol": 1,
        "type": "bye",
        "session_id": "s1",
        "instance_id": "i1",
        "reason": reason,
    }


def _events_body(events):
    return {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": events,
    }


def test_events_batch_publishes_inserted_events(supervisor):
    assert supervisor._handler.handle("POST", "/v1/hello", _hello_body(), 1000).status == 200
    subscription = supervisor.subscribe(("s1", "i1"))
    body = _events_body([
        {"type": "state", "seq": 1, "ts": 1000, "state": "idle"},
    ])
    assert supervisor._handler.handle("POST", "/v1/events", body, 1000).status == 200
    message = subscription.get(1)
    assert message.kind == "events"
    assert message.key == ("s1", "i1")
    assert [event.seq for event in message.events] == [1]
    assert message.summary is None


def test_duplicate_batch_publishes_nothing(supervisor):
    assert supervisor._handler.handle("POST", "/v1/hello", _hello_body(), 1000).status == 200
    subscription = supervisor.subscribe(("s1", "i1"))
    body = _events_body([
        {"type": "state", "seq": 1, "ts": 1000, "state": "idle"},
    ])
    supervisor._handler.handle("POST", "/v1/events", body, 1000)
    assert subscription.get(1) is not None
    supervisor._handler.handle("POST", "/v1/events", body, 1000)
    assert subscription.get(0.2) is None


def test_hello_and_bye_publish_session_messages(supervisor):
    subscription = supervisor.subscribe(("s1", "i1"))
    supervisor._handler.handle("POST", "/v1/hello", _hello_body(), 1000)
    hello_message = subscription.get(1)
    assert hello_message.kind == "session"
    assert hello_message.summary.live is True
    assert hello_message.summary.name == "probe"

    supervisor._handler.handle("POST", "/v1/bye", _bye_body(), 1000)
    bye_message = subscription.get(1)
    assert bye_message.kind == "session"
    assert bye_message.summary.live is False
    assert bye_message.summary.end_reason == "shutdown"


def test_state_change_heartbeat_publishes_once(supervisor):
    supervisor._handler.handle("POST", "/v1/hello", _hello_body(), 1000)
    subscription = supervisor.subscribe(("s1", "i1"))

    supervisor._handler.handle("POST", "/v1/heartbeat", _heartbeat_body("idle"), 1000)
    first = subscription.get(1)
    assert first.kind == "session"
    assert first.summary.state == "idle"

    supervisor._handler.handle("POST", "/v1/heartbeat", _heartbeat_body("idle"), 1000)
    assert subscription.get(0.2) is None

    supervisor._handler.handle("POST", "/v1/heartbeat", _heartbeat_body("working"), 1000)
    second = subscription.get(1)
    assert second.kind == "session"
    assert second.summary.state == "working"


def test_stale_expiry_publishes_session_message(supervisor):
    supervisor._store.upsert_session(_hello(), 1000)
    supervisor._registry.register(_hello(), 1000)
    subscription = supervisor.subscribe(("s1", "i1"))
    supervisor._sweeper.sweep(1000 + STALE_AFTER_MS + 1)
    message = subscription.get(1)
    assert message.kind == "session"
    assert message.key == ("s1", "i1")
    assert message.summary.live is False
    assert message.summary.end_reason == "stale"


def test_stop_all_closes_subscriptions(supervisor):
    subscription = supervisor.subscribe()
    supervisor.stop_all()
    assert subscription.closed is True
    assert subscription.get(0.2) is None
