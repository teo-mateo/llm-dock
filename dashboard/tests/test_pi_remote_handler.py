from pi_remote.contract import STALE_AFTER_MS
from pi_remote.handler import PiRemoteHandler
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB


HELLO = {
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

HEARTBEAT = {
    "protocol": 1,
    "type": "heartbeat",
    "session_id": "s1",
    "instance_id": "i1",
    "state": "idle",
    "context": None,
    "sent_at": 0,
}

BYE = {
    "protocol": 1,
    "type": "bye",
    "session_id": "s1",
    "instance_id": "i1",
    "reason": "remote_off",
}


def test_hello_writes_the_session():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    response = handler.handle("POST", "/v1/hello", HELLO, 1000)
    assert response.status == 200
    assert response.payload["session_id"] == "s1"
    assert response.payload["server_time"] == 1000
    row = store.get_session("s1", "i1")
    assert row["first_seen"] == 1000
    assert row["last_seen"] == 1000
    store.close()


def test_stale_heartbeat_does_not_end_the_row():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    response = handler.handle(
        "POST", "/v1/heartbeat", HEARTBEAT, 1000 + STALE_AFTER_MS + 1
    )
    assert response.status == 404
    assert response.payload["error"] == "unknown_session"
    row = store.get_session("s1", "i1")
    assert row["ended_at"] is None
    store.close()


def test_unknown_heartbeat_writes_nothing():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    response = handler.handle("POST", "/v1/heartbeat", HEARTBEAT, 1000)
    assert response.status == 404
    assert response.payload["error"] == "unknown_session"
    assert store.list_sessions() == []
    store.close()


def test_bye_sets_the_reason():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    response = handler.handle("POST", "/v1/bye", BYE, 2000)
    assert response.status == 200
    assert response.payload == {"ok": True, "protocol": 1}
    row = store.get_session("s1", "i1")
    assert row["ended_at"] == 2000
    assert row["end_reason"] == "remote_off"
    store.close()


def test_non_post_is_rejected_without_touching_the_store():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    response = handler.handle("GET", "/v1/hello", HELLO, 1000)
    assert response.status == 404
    assert response.payload["error"] == "not_found"
    assert store.list_sessions() == []
    store.close()
