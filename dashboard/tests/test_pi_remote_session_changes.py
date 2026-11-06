from pi_remote.events import StoredEvent
from pi_remote.session_changes import session_changes


def event(seq, event_type, **payload):
    return StoredEvent(seq, event_type, 1000, payload)


def test_no_change_events_means_no_changes():
    assert session_changes([event(1, "state", state="idle")]) == {}


def test_model_change_sets_provider_and_id():
    changes = session_changes([event(1, "model_changed", model={"provider": "mistral", "id": "small"}, previous=None)])
    assert changes == {"model_provider": "mistral", "model_id": "small"}


def test_thinking_change_sets_the_level():
    assert session_changes([event(1, "thinking_changed", level="max", previous="high")]) == {"thinking_level": "max"}


def test_latest_change_wins_regardless_of_input_order():
    changes = session_changes([
        event(3, "model_changed", model={"provider": "b", "id": "two"}, previous=None),
        event(2, "model_changed", model={"provider": "a", "id": "one"}, previous=None),
    ])
    assert changes == {"model_provider": "b", "model_id": "two"}


def test_null_model_clears_both_columns():
    changes = session_changes([event(1, "model_changed", model=None, previous=None)])
    assert changes == {"model_provider": None, "model_id": None}
