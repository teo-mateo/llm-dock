import os

import pytest
from flask import Flask

import routes.pi_remote as pi_remote_routes
from pi_remote.api_json import page_json, summary_json
from pi_remote.bus import EventBus
from pi_remote.read_model import EventPage, EventView, SessionSummary
from pi_remote.supervisor import PiRemoteSupervisor
from routes import pi_remote_bp

TOKEN = "test-token-pi-remote"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _summary(session_id="s1", instance_id="i1", live=True):
    return SessionSummary(
        session_id=session_id,
        instance_id=instance_id,
        name="probe",
        cwd="/tmp",
        model="mistral/mistral-small-latest",
        thinking_level="high",
        first_seen=1000,
        last_seen=2000,
        ended_at=None,
        end_reason=None,
        live=live,
        state="idle" if live else None,
        context_percent=None,
    )


def _page():
    return EventPage(
        events=[EventView(1, "state", 1000, {"state": "idle"})],
        next_after=1,
        has_more=False,
    )


class _FakeSupervisor:
    def __init__(self, summaries=None, page=None):
        self._summaries = summaries or []
        self._page = page
        self.calls = []
        self.bus = EventBus()

    def subscribe(self, key=None):
        return self.bus.subscribe(key)

    def session(self, key):
        for summary in self._summaries:
            if (summary.session_id, summary.instance_id) == key:
                return summary
        return None

    def sessions(self):
        return self._summaries

    def events(self, session_id, instance_id, after_seq=0, limit=None):
        self.calls.append((session_id, instance_id, after_seq, limit))
        return self._page


@pytest.fixture
def env(monkeypatch):
    fake = _FakeSupervisor()
    monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", fake)
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.register_blueprint(pi_remote_bp)
    app.testing = True
    return {"client": app.test_client(), "fake": fake}


def test_sessions_requires_auth(env):
    response = env["client"].get("/api/pi/sessions")
    assert response.status_code == 401


def test_sessions_lists_summaries_in_supervisor_order(env):
    first = _summary("s1")
    second = _summary("s2", live=False)
    env["fake"]._summaries = [first, second]

    response = env["client"].get("/api/pi/sessions", headers=_auth())

    assert response.status_code == 200
    assert response.get_json() == {"sessions": [summary_json(first), summary_json(second)]}


def test_events_returns_page(env):
    env["fake"]._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events", headers=_auth()
    )
    assert response.status_code == 200
    assert response.get_json() == page_json(_page())


def test_events_passes_after_and_limit_to_facade(env):
    env["fake"]._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events?after=5&limit=10", headers=_auth()
    )
    assert response.status_code == 200
    assert env["fake"].calls == [("s1", "i1", 5, 10)]


def test_events_unknown_session_is_404(env):
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events", headers=_auth()
    )
    assert response.status_code == 404
    assert response.get_json() == {"error": "unknown_session"}


def test_events_invalid_paging_is_400(env):
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events?after=-1", headers=_auth()
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_paging"}
    assert env["fake"].calls == []


def _socket_dir(tmp_path):
    directory = tmp_path / "sockdir"
    directory.mkdir()
    os.chmod(directory, 0o700)
    return directory


def test_routes_against_real_supervisor(tmp_path, monkeypatch):
    supervisor = PiRemoteSupervisor(
        socket_path=str(_socket_dir(tmp_path) / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    supervisor.start()
    try:
        hello = {
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
        events = {
            "protocol": 1,
            "type": "events",
            "session_id": "s1",
            "instance_id": "i1",
            "events": [{"type": "state", "seq": 1, "ts": 1000, "state": "idle"}],
        }
        assert supervisor._handler.handle("POST", "/v1/hello", hello, 1000).status == 200
        assert supervisor._handler.handle("POST", "/v1/events", events, 1000).status == 200

        monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", supervisor)
        app = Flask(__name__)
        app.config["DASHBOARD_TOKEN"] = TOKEN
        app.register_blueprint(pi_remote_bp)
        app.testing = True
        client = app.test_client()

        sessions = client.get("/api/pi/sessions", headers=_auth())
        assert sessions.status_code == 200
        summary = sessions.get_json()["sessions"][0]
        assert summary["session_id"] == "s1"
        assert summary["live"] is True

        page = client.get(
            "/api/pi/sessions/s1/i1/events?after=0&limit=10", headers=_auth()
        )
        assert page.status_code == 200
        body = page.get_json()
        assert body["events"] == [
            {"seq": 1, "type": "state", "ts": 1000, "payload": {"state": "idle"}}
        ]
        assert body["next_after"] == 1
        assert body["has_more"] is False
    finally:
        supervisor.stop_all()


def _next_frame(response):
    return next(response.response).decode("utf-8")


def test_stream_requires_auth(env):
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream", buffered=False
    )
    assert response.status_code == 401


def test_stream_unknown_session_is_404(env):
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream", headers=_auth()
    )
    assert response.status_code == 404
    assert response.get_json() == {"error": "unknown_session"}


def test_stream_after_from_last_event_id(env):
    env["fake"]._summaries = [_summary()]
    env["fake"]._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream",
        headers={**_auth(), "Last-Event-ID": "7"},
        buffered=False,
    )
    assert response.status_code == 200
    _next_frame(response)
    _next_frame(response)
    env["fake"].bus.close()
    assert list(response.response) == []
    assert env["fake"].calls == [("s1", "i1", 7, 500)]


def test_stream_invalid_after_is_400(env):
    env["fake"]._summaries = [_summary()]
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream?after=-1", headers=_auth()
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_paging"}
    assert env["fake"].calls == []


def test_sessions_stream_path_is_not_a_session_id(env):
    env["fake"]._summaries = [_summary()]
    response = env["client"].get(
        "/api/pi/sessions/stream", headers=_auth(), buffered=False
    )
    assert response.status_code == 200
    snapshot = _next_frame(response)
    assert snapshot.startswith("event: snapshot\n")
    env["fake"].bus.close()
    assert list(response.response) == []


def test_session_stream_through_test_client(tmp_path, monkeypatch):
    supervisor = PiRemoteSupervisor(
        socket_path=str(_socket_dir(tmp_path) / "pi.sock"),
        db_path=str(tmp_path / "pi_remote.db"),
        clock=lambda: 1000,
    )
    supervisor.start()
    try:
        hello = {
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
        events = {
            "protocol": 1,
            "type": "events",
            "session_id": "s1",
            "instance_id": "i1",
            "events": [{"type": "state", "seq": 1, "ts": 1000, "state": "idle"}],
        }
        supervisor._handler.handle("POST", "/v1/hello", hello, 1000)
        supervisor._handler.handle("POST", "/v1/events", events, 1000)

        monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", supervisor)
        app = Flask(__name__)
        app.config["DASHBOARD_TOKEN"] = TOKEN
        app.register_blueprint(pi_remote_bp)
        app.testing = True
        client = app.test_client()

        response = client.get(
            "/api/pi/sessions/s1/i1/stream?after=0",
            headers=_auth(),
            buffered=False,
        )
        assert response.status_code == 200
        replay = _next_frame(response)
        session_frame = _next_frame(response)
        assert replay.startswith("id: 1\nevent: events\n")
        assert session_frame.startswith("event: session\n")

        supervisor._bus.close()
        assert list(response.response) == []
    finally:
        supervisor.stop_all()
