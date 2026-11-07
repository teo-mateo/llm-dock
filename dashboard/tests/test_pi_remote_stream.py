import pytest

from pi_remote.bus import BusMessage, EventBus
from pi_remote.read_model import EventPage, EventView, SessionSummary
from pi_remote.stream import KEEPALIVE, session_stream, sessions_stream, sse


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


def _event(seq):
    return EventView(seq, "state", seq * 1000, {"state": "idle"})


class _FakeSource:
    def __init__(self, events=None, summaries=None, bus=None, on_events=None):
        self._events = list(events or [])
        self._summaries = list(summaries or [])
        self._summary_map = {
            (summary.session_id, summary.instance_id): summary
            for summary in self._summaries
        }
        self.bus = bus or EventBus()
        self.calls = []
        self.last_subscription = None
        self.on_events = on_events

    def subscribe(self, key=None):
        self.last_subscription = self.bus.subscribe(key)
        return self.last_subscription

    def events(self, session_id, instance_id, after_seq, limit):
        self.calls.append((session_id, instance_id, after_seq, limit))
        if self.on_events is not None:
            self.on_events()
        rows = [event for event in self._events if event.seq > after_seq]
        selected = rows[:limit]
        next_after = selected[-1].seq if selected else after_seq
        return EventPage(selected, next_after, len(rows) > limit)

    def sessions(self):
        return self._summaries

    def session(self, key):
        return self._summary_map.get(key)


def _message(key, seq):
    return BusMessage("events", key, events=(_event(seq),))


def test_sse_format_with_and_without_id():
    assert sse("events", {"a": 1}, 2) == (
        "id: 2\nevent: events\ndata: {\"type\":\"events\",\"a\":1}\n\n"
    )
    assert sse("events", {"a": 1}) == (
        "event: events\ndata: {\"type\":\"events\",\"a\":1}\n\n"
    )


def test_sse_data_carries_type():
    assert sse("session", {"session_id": "s1"}) == (
        "event: session\ndata: {\"type\":\"session\",\"session_id\":\"s1\"}\n\n"
    )


def test_replay_pages_until_done_then_session_frame():
    source = _FakeSource(
        events=[_event(seq) for seq in range(1, 502)],
        summaries=[_summary()],
    )
    generator = session_stream(source, ("s1", "i1"), 0)
    first = next(generator)
    second = next(generator)
    third = next(generator)
    source.bus.close()
    assert list(generator) == []
    assert first.startswith("id: 500\nevent: events\n")
    assert second.startswith("id: 501\nevent: events\n")
    assert third.startswith("event: session\n")


def test_events_published_during_replay_are_not_lost():
    source = _FakeSource(
        events=[_event(1)],
        summaries=[_summary()],
        on_events=lambda: source.bus.publish(_message(("s1", "i1"), 2)),
    )
    generator = session_stream(source, ("s1", "i1"), 0)
    replay = next(generator)
    session = next(generator)
    live = next(generator)
    source.bus.close()
    assert list(generator) == []
    assert replay.startswith("id: 1\nevent: events\n")
    assert session.startswith("event: session\n")
    assert live.startswith("id: 2\nevent: events\n")


def test_overlap_between_replay_and_live_is_not_duplicated():
    source = _FakeSource(
        events=[_event(1), _event(2)],
        summaries=[_summary()],
    )

    def publish_overlap():
        source.bus.publish(
            BusMessage("events", ("s1", "i1"), events=(_event(2), _event(3)))
        )

    source.on_events = publish_overlap
    generator = session_stream(source, ("s1", "i1"), 0)
    replay = next(generator)
    session = next(generator)
    live = next(generator)
    source.bus.close()
    assert list(generator) == []
    assert replay.startswith("id: 2\nevent: events\n")
    assert "\"seq\":2" in replay
    assert session.startswith("event: session\n")
    assert live.startswith("id: 3\nevent: events\n")
    assert "\"seq\":2" not in live
    assert "\"seq\":3" in live


def test_live_events_after_replay():
    source = _FakeSource(events=[_event(1)], summaries=[_summary()])
    generator = session_stream(source, ("s1", "i1"), 0)
    next(generator)
    next(generator)
    source.bus.publish(_message(("s1", "i1"), 2))
    live = next(generator)
    source.bus.close()
    assert list(generator) == []
    assert live.startswith("id: 2\nevent: events\n")


def test_keepalive_on_idle():
    source = _FakeSource(summaries=[_summary()])
    generator = session_stream(source, ("s1", "i1"), 0, keepalive_s=0.01)
    assert next(generator).startswith("event: session\n")
    assert next(generator) == KEEPALIVE
    generator.close()


def test_lagged_ends_stream_with_cursor():
    source = _FakeSource(summaries=[_summary()], bus=EventBus(max_queue=1))
    generator = session_stream(source, ("s1", "i1"), 0, keepalive_s=0.01)
    assert next(generator).startswith("event: session\n")
    source.bus.publish(_message(("s1", "i1"), 1))
    source.bus.publish(_message(("s1", "i1"), 2))
    lagged = next(generator)
    assert lagged == "event: lagged\ndata: {\"type\":\"lagged\",\"after\":0}\n\n"
    assert list(generator) == []


def test_bus_close_ends_stream():
    source = _FakeSource(summaries=[_summary()])
    generator = session_stream(source, ("s1", "i1"), 0, keepalive_s=0.01)
    assert next(generator).startswith("event: session\n")
    source.bus.close()
    with pytest.raises(StopIteration):
        next(generator)


def test_generator_close_closes_subscription():
    source = _FakeSource(summaries=[_summary()])
    generator = session_stream(source, ("s1", "i1"), 0, keepalive_s=0.01)
    assert next(generator).startswith("event: session\n")
    generator.close()
    assert source.last_subscription.closed is True


def test_sessions_stream_snapshot_then_session_deltas_ignores_events():
    source = _FakeSource(summaries=[_summary()])
    generator = sessions_stream(source, keepalive_s=0.01)
    snapshot = next(generator)
    assert snapshot.startswith("event: snapshot\n")
    source.bus.publish(BusMessage("events", ("s1", "i1"), events=(_event(1),)))
    source.bus.publish(BusMessage("session", ("s1", "i1"), summary=_summary()))
    delta = next(generator)
    assert delta.startswith("event: session\n")
    source.bus.close()
    assert list(generator) == []


def test_sessions_stream_reports_a_removed_session_and_keeps_running():
    source = _FakeSource(summaries=[_summary()])
    generator = sessions_stream(source, keepalive_s=0.01)
    assert next(generator).startswith("event: snapshot\n")

    source.bus.publish(BusMessage("removed", ("s1", "i1")))
    frame = next(generator)
    assert frame.startswith("event: session_removed\n")
    assert '"session_id":"s1"' in frame
    assert '"instance_id":"i1"' in frame

    source.bus.publish(BusMessage("session", ("s2", "i2"), summary=_summary("s2")))
    assert next(generator).startswith("event: session\n")
    source.bus.close()


def test_session_stream_ends_once_its_session_is_removed():
    source = _FakeSource(summaries=[_summary()])
    generator = session_stream(source, ("s1", "i1"), 0, keepalive_s=0.01)
    assert next(generator).startswith("event: session\n")

    source.bus.publish(BusMessage("removed", ("s1", "i1")))
    assert next(generator).startswith("event: session_removed\n")
    assert list(generator) == []
