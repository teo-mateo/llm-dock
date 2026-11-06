import threading

from pi_remote.contract import STALE_AFTER_MS
from pi_remote.events import Event, EventsFrame
from pi_remote.frames import HelloFrame
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB
from pi_remote.sweeper import PURGE_INTERVAL_MS, StaleSweeper


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


def test_thread_survives_one_store_exception():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    store.upsert_session(hello(), 1000)
    registry.register(hello(), 1000)
    late = 1000 + STALE_AFTER_MS + 1
    sweeper = StaleSweeper(registry, store, clock=lambda: late, interval_ms=10)

    calls = []
    second_sweep = threading.Event()
    original_expire = registry.expire

    def counting_expire(now):
        calls.append(now)
        if len(calls) >= 2:
            second_sweep.set()
        return original_expire(now)

    original_end = store.end_session
    fail_once = [True]

    def flaky_end(session_id, instance_id, reason, now):
        if fail_once[0]:
            fail_once[0] = False
            raise RuntimeError("database locked")
        return original_end(session_id, instance_id, reason, now)

    registry.expire = counting_expire
    store.end_session = flaky_end
    sweeper.start()
    assert second_sweep.wait(2) is True
    sweeper.stop()
    assert len(calls) >= 2
    store.close()



def test_sweeper_purges_at_most_once_per_hour():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    store.insert_events(
        EventsFrame(session_id="s1", instance_id="i1", events=(Event(1, 1000, "state", {"state": "idle"}),)),
        1000,
    )
    calls = []
    original_purge = store.purge_old_events

    def counting_purge(now):
        calls.append(now)
        return original_purge(now)

    store.purge_old_events = counting_purge
    sweeper = StaleSweeper(registry, store, clock=lambda: 1000, interval_ms=1000)
    sweeper.start()
    sweeper.sweep(1000)
    assert calls == []
    sweeper.sweep(1000 + PURGE_INTERVAL_MS)
    assert calls == [1000 + PURGE_INTERVAL_MS]
    sweeper.sweep(1000 + PURGE_INTERVAL_MS + 1)
    assert len(calls) == 1
    sweeper.stop()
    store.close()
