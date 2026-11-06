from pi_remote.events import StoredEvent, acked_seq


def event(seq, event_type="state", **payload):
    return StoredEvent(seq, event_type, payload)


def test_empty_stream_acks_zero():
    assert acked_seq([]) == 0


def test_stream_starting_at_five_acks_six():
    events = [event(5), event(6)]
    assert acked_seq(events) == 6


def test_gap_covers_dropped_seqs():
    events = [
        event(1, "gap", from_seq=1, to_seq=2),
        event(3),
        event(4),
    ]
    assert acked_seq(events) == 4


def test_immutable_gaps_advance_the_mark():
    events = [
        event(10, "gap", from_seq=10, to_seq=10),
        event(11, "gap", from_seq=11, to_seq=11),
    ]
    assert acked_seq(events) == 11


def test_non_contiguous_stream_stops_at_the_hole():
    events = [event(1), event(3)]
    assert acked_seq(events) == 1
