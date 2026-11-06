import sqlite3
from dataclasses import replace

from pi_remote.events import Event, EventsFrame
from pi_remote.frames import HelloFrame, ModelRef
from pi_remote.schema import SCHEMA_SQL
from pi_remote.store import PiRemoteDB, RETENTION_MS


def hello(instance_id="i1", reason="startup", name="probe"):
    return HelloFrame(
        session_id="s1",
        instance_id=instance_id,
        session_file="/tmp/s1.jsonl",
        cwd="/tmp",
        name=name,
        pid=42,
        model=ModelRef(provider="mistral", id="mistral-small-latest"),
        thinking_level="high",
        reason=reason,
        previous_session_id=None,
        pi_version="1.0.4",
        ext_version="0.1.0",
    )


def test_hello_upserts_and_preserves_first_seen(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    first = store.get_session("s1", "i1")
    assert first["first_seen"] == 1000
    assert first["last_seen"] == 1000
    assert first["model_provider"] == "mistral"
    assert first["ended_at"] is None

    store.upsert_session(hello(reason="resume", name="renamed"), 2000)
    second = store.get_session("s1", "i1")
    assert second["first_seen"] == 1000
    assert second["last_seen"] == 2000
    assert second["reason"] == "resume"
    assert second["name"] == "renamed"
    assert len(store.list_sessions()) == 1
    store.close()


def test_heartbeat_touch_and_bye_end(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
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
    store.upsert_session(hello(), 1000)
    store.end_session("s1", "i1", "shutdown", 2000)
    store.upsert_session(hello(), 3000)
    row = store.get_session("s1", "i1")
    assert row["ended_at"] is None
    assert row["end_reason"] is None
    assert row["first_seen"] == 1000
    assert row["last_seen"] == 3000
    store.close()


def test_two_instances_one_session(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.upsert_session(replace(hello(), instance_id="i2"), 1000)
    assert len(store.list_sessions()) == 2
    store.close()


def test_end_open_sessions_closes_leftovers(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.upsert_session(replace(hello(), instance_id="i2"), 1000)
    assert store.end_open_sessions("dashboard_restart", 2000) == 2
    assert store.end_open_sessions("dashboard_restart", 3000) == 0
    rows = store.list_sessions()
    assert all(row["ended_at"] == 2000 for row in rows)
    assert all(row["end_reason"] == "dashboard_restart" for row in rows)
    store.close()



def events_frame(events):
    return EventsFrame(session_id="s1", instance_id="i1", events=tuple(events))


def test_events_round_trip_and_first_copy_wins(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.ingest(
        events_frame([
            Event(1, 1000, "state", {"state": "idle"}),
            Event(2, 1000, "user_message", {"text": "hi", "image_count": 0, "origin": "terminal"}),
            Event(2, 1000, "user_message", {"text": "second", "image_count": 0, "origin": "terminal"}),
        ]),
        1000,
    )
    rows = store.stored_events("s1", "i1")
    assert [row.seq for row in rows] == [1, 2]
    assert rows[1].payload["text"] == "hi"
    assert store.acked_seq("s1", "i1") == 2
    assert [row.seq for row in store.stored_events("s1", "i1", after_seq=1)] == [2]
    store.close()


def test_event_stream_survives_reopen(tmp_path):
    db_path = str(tmp_path / "pi_remote.db")
    store = PiRemoteDB(db_path)
    store.upsert_session(hello(), 1000)
    store.ingest(events_frame([Event(5, 1000, "state", {"state": "idle"})]), 1000)
    assert store.acked_seq("s1", "i1") == 5
    store.close()

    reopened = PiRemoteDB(db_path)
    assert reopened.acked_seq("s1", "i1") == 5
    reopened.close()


def test_purge_keeps_events_inside_the_retention_window(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.ingest(events_frame([Event(1, 1000, "state", {"state": "idle"})]), 1000)
    now = 1000 + RETENTION_MS + 1
    store.ingest(events_frame([Event(2, now, "state", {"state": "idle"})]), now)
    assert store.purge_old_events(now) == 1
    assert [row.seq for row in store.stored_events("s1", "i1")] == [2]
    store.close()

def test_old_session_schema_is_migrated(tmp_path):
    db_path = str(tmp_path / "pi_remote.db")
    old = SCHEMA_SQL.replace(
        "    acked_seq           INTEGER NOT NULL DEFAULT 0,\n", ""
    ).replace("    gap_from     INTEGER,\n", "").replace("    gap_to       INTEGER,\n", "")
    connection = sqlite3.connect(db_path)
    connection.executescript(old)
    connection.commit()
    connection.close()

    store = PiRemoteDB(db_path)
    store.close()
    connection = sqlite3.connect(db_path)
    session_columns = {row[1] for row in connection.execute("PRAGMA table_info(pi_sessions)")}
    event_columns = {row[1] for row in connection.execute("PRAGMA table_info(pi_events)")}
    connection.close()
    assert "acked_seq" in session_columns
    assert {"gap_from", "gap_to"} <= event_columns


def test_events_page_returns_after_seq_in_order_with_ts(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.ingest(
        events_frame([
            Event(1, 1000, "state", {"state": "idle"}),
            Event(2, 2000, "state", {"state": "working"}),
            Event(3, 3000, "state", {"state": "idle"}),
        ]),
        3000,
    )
    rows = store.events_page("s1", "i1", after_seq=1, limit=10)
    assert [row.seq for row in rows] == [2, 3]
    assert [row.ts for row in rows] == [2000, 3000]
    assert rows[0].type == "state"
    assert rows[0].payload == {"state": "working"}
    store.close()


def test_events_page_fetches_limit_plus_one(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    store.ingest(
        events_frame([
            Event(1, 1000, "state", {"state": "idle"}),
            Event(2, 2000, "state", {"state": "idle"}),
            Event(3, 3000, "state", {"state": "idle"}),
            Event(4, 4000, "state", {"state": "idle"}),
        ]),
        4000,
    )
    rows = store.events_page("s1", "i1", after_seq=0, limit=2)
    assert [row.seq for row in rows] == [1, 2, 3]
    store.close()


def test_ingest_reports_only_inserted_rows(tmp_path):
    store = PiRemoteDB(str(tmp_path / "pi_remote.db"))
    store.upsert_session(hello(), 1000)
    result = store.ingest(
        events_frame([
            Event(1, 1000, "state", {"state": "idle"}),
            Event(2, 1000, "state", {"state": "working"}),
            Event(2, 1000, "state", {"state": "idle"}),
        ]),
        1000,
    )
    assert result.acked_seq == 2
    assert [event.seq for event in result.inserted] == [1, 2]
    assert result.inserted[1].payload == {"state": "working"}

    duplicate = store.ingest(
        events_frame([
            Event(1, 1000, "state", {"state": "idle"}),
            Event(2, 1000, "state", {"state": "working"}),
        ]),
        1000,
    )
    assert duplicate.acked_seq == 2
    assert duplicate.inserted == ()
    store.close()
