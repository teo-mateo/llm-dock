import json

import pytest
from pi_remote.bus import EventBus
from pi_remote.client import PiRemoteClient
from pi_remote.command_queue import CommandQueue
from pi_remote.handler import PiRemoteHandler
from pi_remote.limits import RateLimiter
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB
from pi_remote.stream import session_stream

HELLO = {
    "protocol": 1,
    "type": "hello",
    "session_id": "s1",
    "instance_id": "i1",
    "session_file": None,
    "cwd": "/tmp",
    "name": "probe",
    "pid": 1,
    "model": None,
    "thinking_level": None,
    "reason": "startup",
    "previous_session_id": None,
    "pi_version": None,
    "ext_version": "0.1.0",
}

QUESTION = {
    "prompt_id": "call-1",
    "kind": "select",
    "title": "Which colour",
    "message": "pick one",
    "options": ["red", "green"],
    "allow_free_text": False,
    "timeout_ms": 30000,
}


def frame(events_with_bodies, first_seq):
    return {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [
            {"type": event_type, "seq": first_seq + index, "ts": 1000 + index, **body}
            for index, (event_type, body) in enumerate(events_with_bodies)
        ],
    }


def opened(**overrides):
    return "prompt_open", {**QUESTION, **overrides}


def closed(**overrides):
    body = {
        "prompt_id": "call-1",
        "reason": "answered",
        "value": "red",
        "answered_by": "remote",
    }
    return "prompt_closed", {**body, **overrides}


@pytest.fixture
def env():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    bus = EventBus()
    queue = CommandQueue()
    published = []
    state = {"seq": 0}
    client = PiRemoteClient(store, registry, bus, queue, RateLimiter(), lambda: 2000)
    handler = PiRemoteHandler(
        registry,
        store,
        publish=lambda kind, key, batch, summary: published.append((kind, summary)),
        queue=queue,
    )
    handler.handle("POST", "/v1/hello", HELLO, 1000)

    def ingest(*payloads):
        first = state["seq"] + 1
        state["seq"] = first + len(payloads) - 1
        return handler.handle("POST", "/v1/events", frame(payloads, first), 1500)

    try:
        yield {
            "store": store,
            "client": client,
            "handler": handler,
            "published": published,
            "ingest": ingest,
        }
    finally:
        store.close()


def ingest(env, *payloads):
    return env["ingest"](*payloads)


def test_prompt_events_are_stored_and_replayed(env):
    assert ingest(env, opened(), closed()).status == 200
    page = env["client"].events("s1", "i1", 0)
    assert [(event.type, event.seq) for event in page.events] == [
        ("prompt_open", 1),
        ("prompt_closed", 2),
    ]
    assert page.events[0].payload["options"] == ["red", "green"]
    assert page.events[1].payload["value"] == "red"
    after = env["client"].events("s1", "i1", 1)
    assert [event.seq for event in after.events] == [2]


def test_session_carries_the_open_question(env):
    ingest(env, opened())
    summary = env["client"].session(("s1", "i1"))
    assert summary.prompts == [dict(QUESTION)]
    listed = {item.session_id: item.prompts for item in env["client"].sessions()}
    assert listed["s1"] == [dict(QUESTION)]


def test_the_question_is_gone_once_the_prompt_closes(env):
    ingest(env, opened(), closed(value="green", answered_by="terminal"))
    assert env["client"].session(("s1", "i1")).prompts == []
    row = env["store"].prompts.get("s1", "i1", "call-1")
    assert (row.status, row.value, row.answered_by) == ("answered", "green", "terminal")


def test_cancelled_and_expired_leave_the_open_set(env):
    ingest(
        env,
        opened(prompt_id="c1"),
        closed(prompt_id="c1", reason="cancelled", value=None, answered_by=None),
    )
    ingest(
        env,
        opened(prompt_id="c2"),
        closed(prompt_id="c2", reason="expired", value=None, answered_by=None),
    )
    assert env["client"].session(("s1", "i1")).prompts == []
    assert env["store"].prompts.get("s1", "i1", "c1").status == "cancelled"
    assert env["store"].prompts.get("s1", "i1", "c2").status == "expired"


def test_a_second_open_reopens_a_replayed_prompt(env):
    ingest(env, opened(), closed(), opened())
    assert env["client"].session(("s1", "i1")).prompts == [dict(QUESTION)]


def test_prompt_close_publishes_a_session_frame(env):
    ingest(env, opened())
    env["published"].clear()
    ingest(env, closed())
    kinds = [kind for kind, _ in env["published"]]
    assert kinds == ["events", "session"]
    assert env["published"][-1][1].prompts == []


def test_replayed_open_prompt_is_published_as_open(env):
    env["published"].clear()
    ingest(env, opened())
    kinds = [kind for kind, _ in env["published"]]
    assert kinds == ["events", "session"]
    assert env["published"][-1][1].prompts == [dict(QUESTION)]


def test_an_open_prompt_survives_a_dashboard_restart(tmp_path):
    path = str(tmp_path / "pi_remote.db")
    store = PiRemoteDB(path)
    registry = PresenceRegistry()
    handler = PiRemoteHandler(registry, store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    handler.handle(
        "POST", "/v1/events", frame([opened()], 1), 1500
    )
    store.close()

    reopened = PiRemoteDB(path)
    try:
        client = PiRemoteClient(
            reopened, PresenceRegistry(), EventBus(), CommandQueue(), RateLimiter(), lambda: 3000
        )
        assert client.session(("s1", "i1")).prompts == [dict(QUESTION)]
    finally:
        reopened.close()


def test_a_malformed_prompt_open_is_a_bad_frame(env):
    broken = dict(QUESTION, kind="multiple")
    no_id = {k: v for k, v in QUESTION.items() if k != "prompt_id"}
    assert ingest(env, ("prompt_open", broken)).status == 400
    assert ingest(env, ("prompt_open", no_id)).status == 400
    assert ingest(env, ("prompt_open", dict(QUESTION, options="red"))).status == 400
    assert ingest(env, ("prompt_open", dict(QUESTION, allow_free_text="yes"))).status == 400
    assert ingest(env, ("prompt_closed", {"prompt_id": "call-1", "reason": "gone"})).status == 400
    assert env["store"].prompts.open_for("s1", "i1") == []


def reingest(env, first_seq, *payloads):
    return env["handler"].handle("POST", "/v1/events", frame(payloads, first_seq), 2500)


def test_a_replayed_open_frame_does_not_resurrect_an_answered_prompt(env):
    ingest(env, opened(), closed(value="green", answered_by="terminal"))
    assert reingest(env, 1, opened()).status == 200
    assert env["client"].session(("s1", "i1")).prompts == []
    row = env["store"].prompts.get("s1", "i1", "call-1")
    assert (row.status, row.value, row.answered_by) == ("answered", "green", "terminal")


def test_an_out_of_order_open_cannot_reopen_a_prompt_closed_after_it(env):
    assert reingest(env, 5, opened()).status == 200
    assert reingest(env, 6, closed()).status == 200
    assert reingest(env, 1, opened()).status == 200
    assert env["client"].session(("s1", "i1")).prompts == []
    assert env["store"].prompts.get("s1", "i1", "call-1").status == "answered"


def test_a_reannounced_open_with_a_newer_seq_does_reopen(env):
    ingest(env, opened(), closed())
    assert env["client"].session(("s1", "i1")).prompts == []
    ingest(env, opened())
    assert env["client"].session(("s1", "i1")).prompts == [dict(QUESTION)]


def test_a_cancelled_winner_is_not_replaced_by_an_older_answer(env):
    ingest(env, opened(), closed(reason="cancelled", value=None, answered_by=None))
    assert reingest(env, 1, opened()).status == 200
    row = env["store"].prompts.get("s1", "i1", "call-1")
    assert (row.status, row.value, row.answered_by) == ("cancelled", None, None)


def test_closed_prompts_are_purged_after_retention(env):
    ingest(env, opened(), closed())
    assert env["store"].events.purge_old(1500 + 31 * 24 * 60 * 60 * 1000) >= 1
    assert env["store"].prompts.get("s1", "i1", "call-1") is None


def test_closed_prompt_without_an_open_one_changes_nothing(env):
    assert ingest(env, closed()).status == 200
    assert env["store"].prompts.open_for("s1", "i1") == []
    assert env["store"].prompts.get("s1", "i1", "call-1") is None


def take_until_session(stream, limit=8):
    frames = []
    for frame in stream:
        frames.append(frame)
        if '"type":"session"' in frame:
            break
        if len(frames) >= limit:
            break
    stream.close()
    return "".join(frames)


def test_the_session_stream_replays_prompts_and_the_open_state(env):
    ingest(env, opened())
    frames = take_until_session(
        session_stream(env["client"], ("s1", "i1"), 0, keepalive_s=0.01)
    )
    assert "event: events" in frames
    assert "prompt_open" in frames
    session_frame = [line for line in frames.splitlines() if line.startswith("data: ")][-1]
    payload = json.loads(session_frame[len("data: ") :])
    assert payload["type"] == "session"
    assert payload["prompts"] == [dict(QUESTION)]
