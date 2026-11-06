import threading
import time

from pi_remote.bus import BusMessage, EventBus
from pi_remote.read_model import EventView


def _message(key, seq=1):
    return BusMessage(
        "events",
        key,
        events=(EventView(seq, "state", 1000, {"state": "idle"}),),
    )


def test_subscriber_gets_published_message():
    bus = EventBus()
    subscription = bus.subscribe()
    message = _message(("s1", "i1"))
    bus.publish(message)
    assert subscription.get(1) == message
    bus.close()


def test_key_filter_only_delivers_that_session():
    bus = EventBus()
    subscription = bus.subscribe(("s1", "i1"))
    bus.publish(_message(("s2", "i2")))
    assert subscription.get(0.1) is None

    message = _message(("s1", "i1"))
    bus.publish(message)
    assert subscription.get(1) == message
    bus.close()


def test_none_key_receives_all():
    bus = EventBus()
    subscription = bus.subscribe()
    first = _message(("s1", "i1"), 1)
    second = _message(("s2", "i2"), 2)
    bus.publish(first)
    bus.publish(second)
    assert subscription.get(1) == first
    assert subscription.get(1) == second
    bus.close()


def test_overflow_marks_lagged_and_closes():
    bus = EventBus(max_queue=1)
    subscription = bus.subscribe()
    bus.publish(_message(("s1", "i1"), 1))
    bus.publish(_message(("s1", "i1"), 2))
    assert subscription.lagged is True
    assert subscription.closed is True
    assert subscription.get(0.2) is None
    bus.publish(_message(("s1", "i1"), 3))
    bus.close()


def test_publish_with_no_subscribers_is_noop():
    bus = EventBus()
    bus.publish(_message(("s1", "i1")))
    bus.close()


def test_close_unblocks_waiting_get():
    bus = EventBus()
    subscription = bus.subscribe()
    result = []
    thread = threading.Thread(target=lambda: result.append(subscription.get(5)))
    thread.start()
    time.sleep(0.1)
    bus.close()
    thread.join(timeout=1)
    assert thread.is_alive() is False
    assert result == [None]


def test_publish_never_blocks_when_subscriber_is_slow():
    bus = EventBus(max_queue=1)
    subscription = bus.subscribe()
    started = time.monotonic()
    for seq in range(1, 4):
        bus.publish(_message(("s1", "i1"), seq))
    elapsed = time.monotonic() - started
    assert elapsed < 1
    assert subscription.lagged is True
    assert subscription.closed is True
    bus.close()
