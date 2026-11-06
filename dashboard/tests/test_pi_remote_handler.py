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


def test_hello_writes_the_session():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    status, payload = handler.handle("POST", "/v1/hello", HELLO, 1000)
    assert status == 200
    assert payload["session_id"] == "s1"
    assert payload["server_time"] == 1000
    row = store.get_session("s1", "i1")
    assert row["first_seen"] == 1000
    assert row["last_seen"] == 1000
    store.close()


def test_stale_heartbeat_ends_the_row():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    status, payload = handler.handle(
        "POST", "/v1/heartbeat", HEARTBEAT, 1000 + STALE_AFTER_MS + 1
    )
    assert status == 404
    assert payload["error"] == "unknown_session"
    row = store.get_session("s1", "i1")
    assert row["ended_at"] == 1000 + STALE_AFTER_MS + 1
    assert row["end_reason"] == "stale"
    store.close()


def test_unknown_heartbeat_writes_nothing():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    status, payload = handler.handle("POST", "/v1/heartbeat", HEARTBEAT, 1000)
    assert status == 404
    assert payload["error"] == "unknown_session"
    assert store.list_sessions() == []
    store.close()


def test_bye_sets_the_reason():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    bye = {
        "protocol": 1,
        "type": "bye",
        "session_id": "s1",
        "instance_id": "i1",
        "reason": "remote_off",
    }
    status, payload = handler.handle("POST", "/v1/bye", bye, 2000)
    assert status == 200
    assert payload == {"ok": True, "protocol": 1}
    row = store.get_session("s1", "i1")
    assert row["ended_at"] == 2000
    assert row["end_reason"] == "remote_off"
    store.close()


def test_non_post_is_rejected_without_touching_the_store():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    status, payload = handler.handle("GET", "/v1/hello", HELLO, 1000)
    assert status == 404
    assert payload["error"] == "not_found"
    assert store.list_sessions() == []
    store.close()
