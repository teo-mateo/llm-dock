import http.client
import json
import os
import socket

from pi_remote.handler import PiRemoteHandler
from pi_remote.listener import UdsListener
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB
from pi_remote.supervisor import now_ms


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=5):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _post(socket_path, path, body):
    connection = UnixHTTPConnection(socket_path)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_listener_ingests_hello_heartbeat_bye(tmp_path):
    directory = tmp_path / "sockdir"
    directory.mkdir()
    os.chmod(directory, 0o700)
    socket_path = str(directory / "pi.sock")
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    handler = PiRemoteHandler(PresenceRegistry(), store)
    listener = UdsListener(
        socket_path, lambda method, path, body: handler.handle(method, path, body, now_ms())
    )
    listener.start()
    assert listener.running

    hello = {
        "protocol": 1,
        "type": "hello",
        "session_id": "s1",
        "instance_id": "i1",
        "session_file": str(tmp_path / "s1.jsonl"),
        "cwd": "/tmp",
        "name": "probe",
        "pid": 42,
        "model": {"provider": "mistral", "id": "mistral-small-latest"},
        "thinking_level": "high",
        "reason": "startup",
        "previous_session_id": None,
        "pi_version": "1.0.4",
        "ext_version": "0.1.0",
    }
    status, payload = _post(socket_path, "/v1/hello", hello)
    assert status == 200
    assert payload["session_id"] == "s1"
    assert payload["instance_id"] == "i1"
    assert isinstance(payload["server_time"], int)

    heartbeat = {
        "protocol": 1,
        "type": "heartbeat",
        "session_id": "s1",
        "instance_id": "i1",
        "state": "idle",
        "context": {"tokens": 5, "window": 100, "percent": 5},
        "sent_at": now_ms(),
    }
    status, payload = _post(socket_path, "/v1/heartbeat", heartbeat)
    assert status == 200
    assert payload["ok"] is True

    row = store.get_session("s1", "i1")
    assert row is not None
    assert row["last_seen"] >= row["first_seen"]
    assert row["ended_at"] is None

    bye = {
        "protocol": 1,
        "type": "bye",
        "session_id": "s1",
        "instance_id": "i1",
        "reason": "shutdown",
    }
    status, payload = _post(socket_path, "/v1/bye", bye)
    assert status == 200
    row = store.get_session("s1", "i1")
    assert row["ended_at"] is not None
    assert row["end_reason"] == "shutdown"

    listener.stop()
    store.close()
    assert not os.path.exists(socket_path)

def test_listener_ingests_events(tmp_path):
    directory = tmp_path / "sockdir"
    directory.mkdir()
    os.chmod(directory, 0o700)
    socket_path = str(directory / "pi.sock")
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    handler = PiRemoteHandler(PresenceRegistry(), store)
    listener = UdsListener(
        socket_path, lambda method, path, body: handler.handle(method, path, body, now_ms())
    )
    listener.start()
    assert listener.running

    hello = {
        "protocol": 1,
        "type": "hello",
        "session_id": "s1",
        "instance_id": "i1",
        "session_file": None,
        "cwd": "/tmp",
        "name": None,
        "pid": 1,
        "model": None,
        "thinking_level": None,
        "reason": "startup",
        "previous_session_id": None,
        "pi_version": None,
        "ext_version": "0.1.0",
    }
    status, _ = _post(socket_path, "/v1/hello", hello)
    assert status == 200

    events = {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [
            {"type": "state", "seq": 1, "ts": now_ms(), "state": "idle"},
            {"type": "state", "seq": 2, "ts": now_ms(), "state": "working"},
        ],
    }
    status, payload = _post(socket_path, "/v1/events", events)
    assert status == 200
    assert payload["acked_seq"] == 2
    assert [row.seq for row in store.stored_events("s1", "i1")] == [1, 2]

    listener.stop()
    store.close()
    assert not os.path.exists(socket_path)
