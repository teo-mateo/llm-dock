from dataclasses import replace

import pytest

from pi_remote.bus import EventBus
from pi_remote.client import PiRemoteClient
from pi_remote.command_queue import CommandQueue
from pi_remote.commands import CommandResult
from pi_remote.events import Event, EventsFrame
from pi_remote.frames import HelloFrame, ModelRef
from pi_remote.handler import PiRemoteHandler
from pi_remote.limits import RateLimiter
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB


def hello(instance_id="i1"):
    return HelloFrame(
        session_id="s1",
        instance_id=instance_id,
        session_file=None,
        cwd="/tmp",
        name="probe",
        pid=1,
        model=ModelRef(provider="mistral", id="mistral-small-latest"),
        thinking_level="high",
        reason="startup",
        previous_session_id=None,
        pi_version="1.0.4",
        ext_version="0.1.0",
    )


@pytest.fixture
def env():
    store = PiRemoteDB(":memory:")
    registry = PresenceRegistry()
    bus = EventBus()
    queue = CommandQueue()
    limiter = RateLimiter()
    client = PiRemoteClient(store, registry, bus, queue, limiter, lambda: 1000)
    handler = PiRemoteHandler(registry, store, queue=queue)
    try:
        yield {"client": client, "store": store, "registry": registry, "handler": handler}
    finally:
        bus.close()
        store.close()


def _hello_body():
    return {
        "protocol": 1,
        "type": "hello",
        "session_id": "s1",
        "instance_id": "i1",
        "session_file": None,
        "cwd": "/tmp",
        "name": "probe",
        "pid": 1,
        "model": {"provider": "mistral", "id": "mistral-small-latest"},
        "thinking_level": "high",
        "reason": "startup",
        "previous_session_id": None,
        "pi_version": None,
        "ext_version": "0.1.0",
    }


def _commands_poll_body(wait_ms=0):
    return {
        "protocol": 1,
        "type": "commands_poll",
        "session_id": "s1",
        "instance_id": "i1",
        "wait_ms": wait_ms,
    }


def _command_results_body(results):
    return {
        "protocol": 1,
        "type": "command_results",
        "session_id": "s1",
        "instance_id": "i1",
        "results": results,
    }


def test_sessions_live_first_then_last_seen_desc(env):
    store = env["store"]
    registry = env["registry"]
    store.sessions.upsert(hello(), 1000)
    store.sessions.upsert(replace(hello(), session_id="s2"), 2000)
    store.sessions.end("s2", "i1", "remote_off", 2000)
    store.sessions.upsert(replace(hello(), session_id="s3"), 1500)
    store.sessions.end("s3", "i1", "remote_off", 1500)
    registry.register(hello(), 1000)

    summaries = env["client"].sessions()
    assert [summary.session_id for summary in summaries] == ["s1", "s2", "s3"]
    assert summaries[0].live is True
    assert summaries[0].last_seen == 1000
    assert summaries[1].live is False
    assert summaries[2].live is False


def test_events_unknown_key_is_none(env):
    assert env["client"].events("missing", "i1") is None


def test_events_pages_through_all_stored_events(env):
    store = env["store"]
    store.sessions.upsert(hello(), 1000)
    events = tuple(
        Event(seq, seq * 1000, "state", {"state": "idle"})
        for seq in range(1, 451)
    )
    store.events.ingest(EventsFrame("s1", "i1", events), 1000)

    first = env["client"].events("s1", "i1", after_seq=0, limit=200)
    assert len(first.events) == 200
    assert first.next_after == 200
    assert first.has_more is True

    second = env["client"].events("s1", "i1", after_seq=first.next_after, limit=200)
    assert len(second.events) == 200
    assert second.next_after == 400
    assert second.has_more is True

    third = env["client"].events("s1", "i1", after_seq=second.next_after, limit=200)
    assert len(third.events) == 50
    assert third.next_after == 450
    assert third.has_more is False


def test_send_command_offline(env):
    command_id, error = env["client"].send_command(("s1", "i1"), "abort", {})
    assert command_id is None
    assert error == "pi_session_offline"


def test_send_command_rate_limited_on_11th(env):
    env["handler"].handle("POST", "/v1/hello", _hello_body(), 1000)
    for _ in range(10):
        command_id, error = env["client"].send_command(("s1", "i1"), "abort", {})
        assert command_id is not None
        assert error is None
    command_id, error = env["client"].send_command(("s1", "i1"), "abort", {})
    assert command_id is None
    assert error == "rate_limited"


def test_send_command_unsupported_kind(env):
    env["handler"].handle("POST", "/v1/hello", _hello_body(), 1000)
    command_id, error = env["client"].send_command(("s1", "i1"), "set_model", {})
    assert command_id is None
    assert error == "unsupported_command"


def test_poll_delivers_and_results_resolve_await_command(env):
    env["handler"].handle("POST", "/v1/hello", _hello_body(), 1000)
    command_id, error = env["client"].send_command(("s1", "i1"), "abort", {})
    assert error is None

    poll = env["handler"].handle(
        "POST", "/v1/commands/poll", _commands_poll_body(), 1000
    )
    assert poll.status == 200
    assert poll.payload["commands"][0]["command_id"] == command_id
    assert poll.payload["commands"][0]["kind"] == "abort"

    result_body = _command_results_body([
        {"command_id": command_id, "ok": True, "error": None},
    ])
    assert env["handler"].handle(
        "POST", "/v1/command-results", result_body, 1000
    ).status == 200
    assert env["client"].await_command(command_id, 0.1) == CommandResult(command_id, True, None)
    assert env["store"].commands.get(command_id)["outcome"] == "done"


def test_audit_row_stores_a_digest_not_the_text(env):
    env["handler"].handle("POST", "/v1/hello", _hello_body(), 1000)
    command_id, error = env["client"].send_command(
        ("s1", "i1"), "send_message", {"text": "secret-text"}
    )
    assert error is None
    row = env["store"].commands.get(command_id)
    assert row["outcome"] == "pending"
    assert len(row["args_digest"]) == 64
    assert row["args_digest"] != "secret-text"
    assert "secret-text" not in str(row)
