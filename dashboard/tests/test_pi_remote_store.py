from pi_remote.store import PiRemoteDB


FIELDS = {
    "session_id": "s1",
    "instance_id": "i1",
    "session_file": "/tmp/s1.jsonl",
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


def test_hello_upserts_and_preserves_first_seen(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(FIELDS, 1000)
    first = store.get_session("s1", "i1")
    assert first["first_seen"] == 1000
    assert first["last_seen"] == 1000
    assert first["model_provider"] == "mistral"
    assert first["ended_at"] is None

    updated = dict(FIELDS, reason="resume", name="renamed")
    store.upsert_session(updated, 2000)
    second = store.get_session("s1", "i1")
    assert second["first_seen"] == 1000
    assert second["last_seen"] == 2000
    assert second["reason"] == "resume"
    assert second["name"] == "renamed"
    assert len(store.list_sessions()) == 1
    store.close()


def test_heartbeat_touch_and_bye_end(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(FIELDS, 1000)
    assert store.touch_session("s1", "i1", 2000) is True
    assert store.get_session("s1", "i1")["last_seen"] == 2000
    assert store.end_session("s1", "i1", "remote_off", 3000) is True
    row = store.get_session("s1", "i1")
    assert row["ended_at"] == 3000
    assert row["end_reason"] == "remote_off"
    assert store.touch_session("s1", "i1", 4000) is False
    assert store.end_session("s1", "i1", "shutdown", 5000) is False
    store.close()


def test_rehello_clears_ended_state(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(FIELDS, 1000)
    store.end_session("s1", "i1", "shutdown", 2000)
    store.upsert_session(FIELDS, 3000)
    row = store.get_session("s1", "i1")
    assert row["ended_at"] is None
    assert row["end_reason"] is None
    assert row["first_seen"] == 1000
    assert row["last_seen"] == 3000
    store.close()


def test_two_instances_one_session(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(FIELDS, 1000)
    store.upsert_session(dict(FIELDS, instance_id="i2"), 1000)
    assert len(store.list_sessions()) == 2
    store.close()
