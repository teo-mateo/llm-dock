import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import run_start
from chat.models import Message
from chat.outcomes import PolicyError
from reasoning_levels import parse_levels

SERVICES = lambda: [
    {"name": "svc", "template_type": "vllm", "reasoning_levels": parse_levels("off,low")},
]


class FakeDb:
    def __init__(self, creates=True):
        self.creates = creates
        self.calls = []

    def resolve_project_id(self, conv_id):
        return "root-project"

    def create_run_with_user_message(self, user_msg, run, delete_from_seq=None):
        self.calls.append(("create", user_msg.id, run.conversation_id, delete_from_seq))
        return (user_msg, run) if self.creates else None

    def get_project(self, project_id):
        return object()


class FakeRunManager:
    def __init__(self, log):
        self.log = log

    def subscribe(self, run_id):
        self.log.append(("subscribe", run_id))
        return "queue"

    def start(self, conv, run, **kwargs):
        self.log.append(("start", run.id, kwargs))

    def observe(self, run_id, queue, run_started_extra=None):
        self.log.append(("observe", run_id, queue, run_started_extra))
        return iter(["frame"])


def _conv(**extra):
    base = dict(id="c1", main_service="svc", mcp_servers_json=None, project_id=None,
                parent_conversation_id=None, reasoning_level="low", sampling_params_json='{"seed": 1}')
    base.update(extra)
    return SimpleNamespace(**base)


def _start(db=None, conv=None, **kwargs):
    log = []
    db = db or FakeDb()
    mcp_asked = []
    params = dict(
        db=db,
        run_manager=FakeRunManager(log),
        get_mcp=lambda: mcp_asked.append(1) or "mcp",
        storage_root="/tmp/storage",
        conv=conv or _conv(),
        user_msg=Message(id="m1", conversation_id="c1", role="user", content="hi", seq=0),
        is_first=True,
        first_user_content="hi",
        services=SERVICES,
    )
    params.update(kwargs)
    return run_start.start_run(**params), db, log, mcp_asked


def test_a_started_run_creates_then_subscribes_then_starts_then_observes():
    result, db, log, _ = _start()

    assert isinstance(result, run_start.Started)
    assert [entry[0] for entry in log] == ["subscribe", "start", "observe"]
    assert db.calls[0][0] == "create"
    assert list(result.observer) == ["frame"]


def test_start_receives_the_snapshotted_configuration():
    _, _, log, _ = _start(conv=_conv(parent_conversation_id="root"))

    kwargs = next(entry[2] for entry in log if entry[0] == "start")
    assert kwargs["effective_project_id"] == "root-project"
    assert kwargs["reasoning_level"] == "low"
    assert kwargs["sampling_params"] == {"seed": 1}
    assert kwargs["is_first"] is True and kwargs["first_user_content"] == "hi"
    assert kwargs["mcp_manager"] is not None


def test_a_conversation_with_no_project_and_no_servers_gets_no_manager():
    _, _, log, _ = _start()

    assert next(entry[2] for entry in log if entry[0] == "start")["mcp_manager"] is None


def test_run_started_extra_reaches_the_observer():
    _, _, log, _ = _start(conv=_conv(reasoning_level="ultra"))

    extra = next(entry[3] for entry in log if entry[0] == "observe")
    assert extra["reasoning_level"] is None and "ultra" in extra["reasoning_level_note"]


def test_a_conflict_is_a_409_policy_error_and_never_subscribes_or_starts():
    result, _, log, _ = _start(db=FakeDb(creates=False))

    assert result == PolicyError(409, run_start.RUN_ACTIVE_MESSAGE, "run_already_active")
    assert log == []


def test_delete_from_seq_is_passed_to_the_atomic_create():
    _, db, _, _ = _start(delete_from_seq=4)

    assert db.calls[0][3] == 4


def test_enabled_servers_hand_the_run_the_mcp_manager():
    _, _, log, asked = _start(conv=_conv(mcp_servers_json='["sympy-math"]'))

    assert next(entry[2] for entry in log if entry[0] == "start")["mcp_manager"] == "mcp"
    assert asked == [1]


def test_a_conversation_without_tools_never_asks_for_the_mcp_manager():
    _, _, _, asked = _start()

    assert asked == []


def test_the_run_belongs_to_the_conversation_and_carries_the_message():
    _, db, log, _ = _start()

    assert db.calls[0][1:3] == ("m1", "c1")
    assert next(entry[1] for entry in log if entry[0] == "start") == next(
        entry[1] for entry in log if entry[0] == "subscribe"
    )


def test_the_sse_helper_sets_the_headers_a_proxy_must_not_buffer():
    from flask import Flask
    from chat import http

    with Flask(__name__).test_request_context():
        response = http.sse_response(iter([b"x"]))

    assert response.mimetype == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"
