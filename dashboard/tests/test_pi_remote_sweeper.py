from pi_remote.contract import STALE_AFTER_MS, HelloFrame
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB
from pi_remote.sweeper import StaleSweeper


def hello():
    return HelloFrame(
        session_id="s1",
        instance_id="i1",
        session_file=None,
        cwd="/tmp",
        name=None,
        pid=1,
        model=None,
        thinking_level=None,
        reason="startup",
        previous_session_id=None,
        pi_version=None,
        ext_version="0.1.0",
    )


def test_sweeper_ends_stale_row_without_a_request():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    store.upsert_session(hello(), 1000)
    registry.register(hello(), 1000)
    late = 1000 + STALE_AFTER_MS + 1
    sweeper = StaleSweeper(registry, store, clock=lambda: late)
    keys = sweeper.sweep(late)
    assert keys == [("s1", "i1")]
    row = store.get_session("s1", "i1")
    assert row["ended_at"] == late
    assert row["end_reason"] == "stale"
    assert registry.entries(late) == []
    store.close()


def test_boundary_entry_is_not_expired():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    store.upsert_session(hello(), 1000)
    registry.register(hello(), 1000)
    boundary = 1000 + STALE_AFTER_MS
    sweeper = StaleSweeper(registry, store, clock=lambda: boundary)
    assert sweeper.sweep(boundary) == []
    assert store.get_session("s1", "i1")["ended_at"] is None
    store.close()


def test_start_and_stop_are_idempotent():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    sweeper = StaleSweeper(registry, store, clock=lambda: 1000, interval_ms=1000)
    sweeper.start()
    sweeper.start()
    assert sweeper.running is True
    sweeper.stop()
    sweeper.stop()
    assert sweeper.running is False
    store.close()
