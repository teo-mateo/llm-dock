from pi_remote.events import StoredEvent
from pi_remote.frames import ContextUsage, HelloFrame, ModelRef
from pi_remote.read_model import (
    children_to_republish,
    clamp_limit,
    event_page,
    project_label,
    resolve_parent,
    session_summary,
)
from pi_remote.registry import PresenceEntry


def _hello():
    return HelloFrame(
        session_id="s1",
        instance_id="i1",
        session_file=None,
        cwd="/tmp",
        name="probe",
        pid=1,
        model=ModelRef(provider="mistral", id="mistral-small-latest"),
        thinking_level="high",
        reason="startup",
        previous_session_id=None,
        parent_session_id=None,
        pi_version=None,
        ext_version="0.1.0",
    )


def _row(**overrides):
    row = {
        "session_id": "s1",
        "instance_id": "i1",
        "name": "probe",
        "cwd": "/tmp",
        "model_provider": "mistral",
        "model_id": "mistral-small-latest",
        "thinking_level": "high",
        "first_seen": 1000,
        "last_seen": 2000,
        "ended_at": None,
        "end_reason": None,
        "parent_session_id": None,
    }
    row.update(overrides)
    return row


def test_summary_of_ended_session_is_not_live():
    summary = session_summary(
        _row(ended_at=3000, end_reason="shutdown"), None
    )
    assert summary.live is False
    assert summary.state is None
    assert summary.context_percent is None
    assert summary.ended_at == 3000
    assert summary.end_reason == "shutdown"


def test_summary_of_live_session_carries_state_and_context():
    presence = PresenceEntry(
        hello=_hello(),
        last_seen=2000,
        state="working",
        context=ContextUsage(tokens=25.0, window=100.0, percent=25.0),
    )
    summary = session_summary(_row(), presence)
    assert summary.live is True
    assert summary.state == "working"
    assert summary.context_percent == 25.0


def test_model_is_provider_slash_id_or_none():
    assert session_summary(_row(), None).model == "mistral/mistral-small-latest"
    assert session_summary(_row(model_provider=None, model_id=None), None).model is None
    assert session_summary(_row(model_provider=None), None).model is None


def test_event_page_has_more_when_store_returns_limit_plus_one():
    rows = [
        StoredEvent(1, "state", 1000, {"state": "idle"}),
        StoredEvent(2, "state", 2000, {"state": "working"}),
        StoredEvent(3, "state", 3000, {"state": "idle"}),
    ]
    page = event_page(rows, 0, 2)
    assert [event.seq for event in page.events] == [1, 2]
    assert page.next_after == 2
    assert page.has_more is True


def test_event_page_next_after_is_last_seq_or_after_seq():
    rows = [
        StoredEvent(4, "state", 1000, {"state": "idle"}),
        StoredEvent(5, "state", 2000, {"state": "working"}),
    ]
    page = event_page(rows, 3, 5)
    assert page.next_after == 5
    assert page.has_more is False

    empty = event_page([], 7, 5)
    assert empty.next_after == 7
    assert empty.events == []
    assert empty.has_more is False


def test_clamp_limit_default_min_max():
    assert clamp_limit(None) == 200
    assert clamp_limit(0) == 1
    assert clamp_limit(1000) == 500
    assert clamp_limit(50) == 50


def test_project_label_uses_the_last_two_segments():
    assert project_label("/github/teo-mateo/llm-dock") == "teo-mateo/llm-dock"
    assert project_label("/github/teo-mateo/llm-dock/") == "teo-mateo/llm-dock"
    assert project_label("/repo") == "repo"
    assert project_label("/home/teodor") == "home/teodor"
    assert project_label("/") == "/"
    assert project_label("") == "/"
    assert project_label("C:\\Users\\teo\\proj") == "teo/proj"


def test_project_label_collides_for_equal_tails():
    assert project_label("/a/x/y") == project_label("/b/x/y") == "x/y"


def test_summary_carries_parent_and_project():
    summary = session_summary(
        _row(parent_session_id="root", cwd="/github/teo-mateo/llm-dock"), None
    )
    assert summary.parent_session_id == "root"
    assert summary.project == "teo-mateo/llm-dock"


def test_summary_of_a_root_session_has_no_parent():
    summary = session_summary(_row(), None)
    assert summary.parent_session_id is None
    assert summary.project == "tmp"


def test_resolve_parent_prefers_the_live_row():
    rows = [
        _row(instance_id="old", ended_at=10, last_seen=50),
        _row(instance_id="new", ended_at=None, last_seen=1),
        _row(session_id="child", instance_id="c1", parent_session_id="s1"),
    ]

    assert resolve_parent(rows) == {("child", "c1"): ("s1", "new")}


def test_resolve_parent_breaks_a_tie_by_last_seen_then_first_seen():
    rows = [
        _row(instance_id="a", ended_at=1, last_seen=100, first_seen=1),
        _row(instance_id="b", ended_at=1, last_seen=100, first_seen=2),
        _row(session_id="child", instance_id="c1", parent_session_id="s1"),
    ]

    assert resolve_parent(rows)[("child", "c1")] == ("s1", "b")


def test_resolve_parent_leaves_a_missing_parent_unresolved():
    rows = [_row(session_id="child", instance_id="c1", parent_session_id="gone")]

    assert resolve_parent(rows) == {}


def test_resolve_parent_ignores_self_and_cycles():
    rows = [
        _row(session_id="a", instance_id="i1", parent_session_id="a"),
        _row(session_id="b", instance_id="i1", parent_session_id="c"),
        _row(session_id="c", instance_id="i1", parent_session_id="b"),
    ]

    assert resolve_parent(rows) == {}


def test_resolve_parent_keeps_a_chain():
    rows = [
        _row(session_id="root", instance_id="i1"),
        _row(session_id="child", instance_id="i1", parent_session_id="root"),
        _row(session_id="grandchild", instance_id="i1", parent_session_id="child"),
    ]

    assert resolve_parent(rows) == {
        ("child", "i1"): ("root", "i1"),
        ("grandchild", "i1"): ("child", "i1"),
    }


def test_summary_carries_the_resolved_parent_instance():
    rows = [
        _row(instance_id="old", ended_at=10, last_seen=50),
        _row(instance_id="new", ended_at=None, last_seen=1),
    ]
    child = _row(session_id="child", instance_id="c1", parent_session_id="s1")

    summary = session_summary(child, None, parents=resolve_parent(rows + [child]))

    assert summary.parent_session_id == "s1"
    assert summary.parent_instance_id == "new"


def test_summary_of_an_unresolved_parent_keeps_the_declared_id():
    child = _row(session_id="child", instance_id="c1", parent_session_id="gone")

    summary = session_summary(child, None, parents=resolve_parent([child]))

    assert summary.parent_session_id == "gone"
    assert summary.parent_instance_id is None


def test_children_to_republish_lists_every_row_declaring_the_session():
    rows = [
        _row(session_id="root", instance_id="i1"),
        _row(session_id="child", instance_id="c1", parent_session_id="root"),
        _row(session_id="child", instance_id="c2", parent_session_id="root"),
        _row(session_id="other", instance_id="o1", parent_session_id="elsewhere"),
    ]

    assert children_to_republish(rows, "root") == [("child", "c1"), ("child", "c2")]
