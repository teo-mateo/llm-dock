import os
import threading
from types import SimpleNamespace

import pytest
from flask import Flask

import routes.pi_remote as pi_remote_routes
from pi_remote.api_json import page_json, summary_json
from pi_remote.bus import EventBus
from pi_remote.commands import CommandResult
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


class _FakeClient:
    def __init__(self, summaries=None, page=None):
        self._summaries = summaries or []
        self._page = page
        self.calls = []
        self.bus = EventBus()
        self.command_id = "cmd-1"
        self.command_error = None
        self.result = None
        self.command_calls = []
        self.await_calls = []
        self.delete_calls = []
        self.delete_error = None

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

    def delete_session(self, key):
        self.delete_calls.append(key)
        return self.delete_error

    def send_command(self, key, kind, args):
        self.command_calls.append((key, kind, args))
        return self.command_id, self.command_error

    def await_command(self, command_id, timeout_s):
        self.await_calls.append((command_id, timeout_s))
        return self.result


class _FakeSupervisor:
    def __init__(self, summaries=None, page=None):
        self.client = _FakeClient(summaries, page)


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


def test_client_unavailable_is_503(monkeypatch):
    monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", SimpleNamespace(client=None))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.register_blueprint(pi_remote_bp)
    app.testing = True
    response = app.test_client().get("/api/pi/sessions", headers=_auth())
    assert response.status_code == 503
    assert response.get_json() == {"error": "pi_remote_unavailable"}


def test_sessions_lists_summaries_in_supervisor_order(env):
    first = _summary("s1")
    second = _summary("s2", live=False)
    env["fake"].client._summaries = [first, second]

    response = env["client"].get("/api/pi/sessions", headers=_auth())

    assert response.status_code == 200
    assert response.get_json() == {"sessions": [summary_json(first), summary_json(second)]}


def test_delete_requires_auth(env):
    assert env["client"].delete("/api/pi/sessions/s1/i1").status_code == 401


def test_delete_session_returns_200(env):
    response = env["client"].delete("/api/pi/sessions/s1/i1", headers=_auth())

    assert response.status_code == 200
    assert response.get_json() == {"deleted": True}
    assert env["fake"].client.delete_calls == [("s1", "i1")]


def test_delete_live_session_is_409(env):
    env["fake"].client.delete_error = "pi_session_live"

    response = env["client"].delete("/api/pi/sessions/s1/i1", headers=_auth())

    assert response.status_code == 409
    assert response.get_json() == {"error": "pi_session_live"}


def test_delete_unknown_session_is_404(env):
    env["fake"].client.delete_error = "unknown_session"

    response = env["client"].delete("/api/pi/sessions/nope/i1", headers=_auth())

    assert response.status_code == 404
    assert response.get_json() == {"error": "unknown_session"}


def test_events_returns_page(env):
    env["fake"].client._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events", headers=_auth()
    )
    assert response.status_code == 200
    assert response.get_json() == page_json(_page())


def test_events_passes_after_and_limit_to_facade(env):
    env["fake"].client._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/events?after=5&limit=10", headers=_auth()
    )
    assert response.status_code == 200
    assert env["fake"].client.calls == [("s1", "i1", 5, 10)]


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
    assert env["fake"].client.calls == []


def _post_message(env, body):
    return env["client"].post(
        "/api/pi/sessions/s1/i1/messages", headers=_auth(), json=body
    )


def test_messages_requires_auth(env):
    response = env["client"].post(
        "/api/pi/sessions/s1/i1/messages", json={"text": "hello"}
    )
    assert response.status_code == 401


def test_messages_returns_result_when_completed(env):
    env["fake"].client.result = CommandResult("cmd-1", True, None)
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 200
    assert response.get_json() == {"command_id": "cmd-1", "ok": True, "error": None}
    assert env["fake"].client.command_calls == [
        (("s1", "i1"), "send_message", {"text": "hello"})
    ]
    assert env["fake"].client.await_calls == [("cmd-1", 5.0)]


def test_messages_returns_202_when_pending(env):
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 202
    assert response.get_json() == {"command_id": "cmd-1", "pending": True}
    assert env["fake"].client.await_calls == [("cmd-1", 5.0)]


def test_messages_offline_is_409(env):
    env["fake"].client.command_id = None
    env["fake"].client.command_error = "pi_session_offline"
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 409
    assert response.get_json() == {"error": "pi_session_offline"}
    assert env["fake"].client.await_calls == []


def test_messages_rate_limited_is_429(env):
    env["fake"].client.command_id = None
    env["fake"].client.command_error = "rate_limited"
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 429
    assert response.get_json() == {"error": "rate_limited"}


def test_messages_queue_full_is_503(env):
    env["fake"].client.command_id = None
    env["fake"].client.command_error = "queue_full"
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 503
    assert response.get_json() == {"error": "queue_full"}


def test_messages_unsupported_command_is_400(env):
    env["fake"].client.command_id = None
    env["fake"].client.command_error = "unsupported_command"
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 400
    assert response.get_json() == {"error": "unsupported_command"}


def test_messages_invalid_text_is_400(env):
    response = _post_message(env, {"text": "   "})
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_text"}
    assert env["fake"].client.command_calls == []


def test_messages_non_object_body_is_400(env):
    response = env["client"].post(
        "/api/pi/sessions/s1/i1/messages", headers=_auth(), json=[]
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_body"}


def test_abort_returns_result(env):
    env["fake"].client.result = CommandResult("cmd-1", True, None)
    response = env["client"].post(
        "/api/pi/sessions/s1/i1/abort", headers=_auth(), json={}
    )
    assert response.status_code == 200
    assert response.get_json() == {"command_id": "cmd-1", "ok": True, "error": None}
    assert env["fake"].client.command_calls == [(("s1", "i1"), "abort", {})]


def test_failed_command_is_200_with_ok_false(env):
    env["fake"].client.result = CommandResult("cmd-1", False, "failed")
    response = _post_message(env, {"text": "hello"})
    assert response.status_code == 200
    assert response.get_json() == {"command_id": "cmd-1", "ok": False, "error": "failed"}


def test_send_message_through_real_supervisor(tmp_path, monkeypatch):
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
        assert supervisor._handler.handle("POST", "/v1/hello", hello, 1000).status == 200

        monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", supervisor)
        app = Flask(__name__)
        app.config["DASHBOARD_TOKEN"] = TOKEN
        app.register_blueprint(pi_remote_bp)
        app.testing = True
        test_client = app.test_client()
        holder = {}

        def post_message():
            holder["response"] = test_client.post(
                "/api/pi/sessions/s1/i1/messages",
                headers=_auth(),
                json={"text": "hello"},
            )

        thread = threading.Thread(target=post_message)
        thread.start()

        poll = supervisor._handler.handle(
            "POST",
            "/v1/commands/poll",
            {
                "protocol": 1,
                "type": "commands_poll",
                "session_id": "s1",
                "instance_id": "i1",
                "wait_ms": 1000,
            },
            1000,
        )
        assert poll.status == 200
        command = poll.payload["commands"][0]
        assert command["kind"] == "send_message"

        result_body = {
            "protocol": 1,
            "type": "command_results",
            "session_id": "s1",
            "instance_id": "i1",
            "results": [
                {"command_id": command["command_id"], "ok": True, "error": None}
            ],
        }
        assert supervisor._handler.handle(
            "POST", "/v1/command-results", result_body, 1000
        ).status == 200

        thread.join(6)
        assert not thread.is_alive()
        response = holder["response"]
        assert response.status_code == 200
        assert response.get_json() == {
            "command_id": command["command_id"],
            "ok": True,
            "error": None,
        }
        assert supervisor._store.commands.get(command["command_id"])["outcome"] == "done"
    finally:
        supervisor.stop_all()


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
    env["fake"].client._summaries = [_summary()]
    env["fake"].client._page = _page()
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream",
        headers={**_auth(), "Last-Event-ID": "7"},
        buffered=False,
    )
    assert response.status_code == 200
    _next_frame(response)
    _next_frame(response)
    env["fake"].client.bus.close()
    assert list(response.response) == []
    assert env["fake"].client.calls == [("s1", "i1", 7, 500)]


def test_stream_invalid_after_is_400(env):
    env["fake"].client._summaries = [_summary()]
    response = env["client"].get(
        "/api/pi/sessions/s1/i1/stream?after=-1", headers=_auth()
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_paging"}
    assert env["fake"].client.calls == []


def test_sessions_stream_path_is_not_a_session_id(env):
    env["fake"].client._summaries = [_summary()]
    response = env["client"].get(
        "/api/pi/sessions/stream", headers=_auth(), buffered=False
    )
    assert response.status_code == 200
    snapshot = _next_frame(response)
    assert snapshot.startswith("event: snapshot\n")
    env["fake"].client.bus.close()
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
