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
    row = store.sessions.get("s1", "i1")
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
    row = store.sessions.get("s1", "i1")
    assert row["ended_at"] is None
    store.close()


def test_unknown_heartbeat_writes_nothing():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    response = handler.handle("POST", "/v1/heartbeat", HEARTBEAT, 1000)
    assert response.status == 404
    assert response.payload["error"] == "unknown_session"
    assert store.sessions.list() == []
    store.close()


def test_bye_sets_the_reason():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    response = handler.handle("POST", "/v1/bye", BYE, 2000)
    assert response.status == 200
    assert response.payload == {"ok": True, "protocol": 1}
    row = store.sessions.get("s1", "i1")
    assert row["ended_at"] == 2000
    assert row["end_reason"] == "remote_off"
    store.close()


def test_non_post_is_rejected_without_touching_the_store():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    response = handler.handle("GET", "/v1/hello", HELLO, 1000)
    assert response.status == 404
    assert response.payload["error"] == "not_found"
    assert store.sessions.list() == []
    store.close()




def events_request(seqs):
    return {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [
            {"type": "state", "seq": seq, "ts": 2000, "state": "idle"}
            for seq in seqs
        ],
    }


def test_events_advance_the_hello_mark_and_touch_the_session(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    response = handler.handle("POST", "/v1/events", events_request([1, 2]), 2000)
    assert response.status == 200
    assert response.payload["acked_seq"] == 2
    row = store.sessions.get("s1", "i1")
    assert row["last_seen"] == 2000

    again = handler.handle("POST", "/v1/hello", HELLO, 3000)
    assert again.payload["acked_seq"] == 2
    store.close()


def test_rebuilt_store_keeps_the_hello_mark(tmp_path):
    db_path = str(tmp_path / "pi_remote.db")
    first = PiRemoteDB(db_path)
    first_handler = PiRemoteHandler(PresenceRegistry(), first)
    first_handler.handle("POST", "/v1/hello", HELLO, 1000)
    first_handler.handle("POST", "/v1/events", events_request([5]), 1000)
    first.close()

    second = PiRemoteDB(db_path)
    handler = PiRemoteHandler(PresenceRegistry(), second)
    response = handler.handle("POST", "/v1/hello", HELLO, 3000)
    assert response.payload["acked_seq"] == 5
    second.close()


def test_stale_events_are_rejected_without_storage():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    response = handler.handle(
        "POST", "/v1/events", events_request([1]), 1000 + STALE_AFTER_MS + 1
    )
    assert response.status == 404
    assert response.payload["error"] == "unknown_session"
    assert store.events.stored("s1", "i1") == []
    store.close()

def test_stale_bad_payload_gets_unknown_session():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    body = {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [{"type": "state", "seq": 1, "ts": 2000}],
    }
    response = handler.handle(
        "POST", "/v1/events", body, 1000 + STALE_AFTER_MS + 1
    )
    assert response.status == 404
    assert response.payload["error"] == "unknown_session"
    assert store.events.stored("s1", "i1") == []
    store.close()


def test_model_and_thinking_changes_update_the_session_and_publish_it(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    published = []
    handler = PiRemoteHandler(
        PresenceRegistry(), store,
        publish=lambda kind, key, events, summary: published.append((kind, summary)),
    )
    handler.handle("POST", "/v1/hello", {**HELLO, "model": {"provider": "old", "id": "m1"}, "thinking_level": "high"}, 1000)
    published.clear()
    body = {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [
            {"type": "model_changed", "seq": 1, "ts": 2000,
             "model": {"provider": "mistral", "id": "small"}, "previous": {"provider": "old", "id": "m1"}},
            {"type": "thinking_changed", "seq": 2, "ts": 2000, "level": "max", "previous": "high"},
        ],
    }
    assert handler.handle("POST", "/v1/events", body, 2000).status == 200
    row = store.sessions.get("s1", "i1")
    assert (row["model_provider"], row["model_id"], row["thinking_level"]) == ("mistral", "small", "max")
    sessions = [summary for kind, summary in published if kind == "session"]
    assert len(sessions) == 1
    assert sessions[0].model == "mistral/small"
    assert sessions[0].thinking_level == "max"
    store.close()


def test_plain_events_do_not_publish_a_session(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    published = []
    handler = PiRemoteHandler(
        PresenceRegistry(), store,
        publish=lambda kind, key, events, summary: published.append(kind),
    )
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    published.clear()
    handler.handle("POST", "/v1/events", events_request([1]), 2000)
    assert published == ["events"]
    store.close()
