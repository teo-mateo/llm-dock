from pi_remote.events import AckedEvent, acked_seq


def event(seq, event_type="state", from_seq=None, to_seq=None):
    return AckedEvent(seq, event_type, from_seq, to_seq)


def test_empty_stream_acks_zero():
    assert acked_seq([]) == 0


def test_stream_starting_at_five_acks_six():
    assert acked_seq([event(5), event(6)]) == 6


def test_gap_covers_dropped_seqs():
    assert acked_seq([event(1, "gap", 1, 2), event(3), event(4)]) == 4


def test_immutable_gaps_advance_the_mark():
    assert acked_seq([event(10, "gap", 10, 10), event(11, "gap", 11, 11)]) == 11


def test_non_contiguous_stream_stops_at_the_hole():
    assert acked_seq([event(1), event(3)]) == 1


def test_incremental_mark_never_moves_backwards():
    assert acked_seq([event(12)], 10) == 10
    assert acked_seq([event(11), event(12)], 10) == 12
