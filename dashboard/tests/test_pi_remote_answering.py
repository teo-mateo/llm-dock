import json
from types import SimpleNamespace

import pytest
from flask import Flask

import routes.pi_remote as pi_remote_routes
from pi_remote.answering import answer_prompt
from pi_remote.commands import CommandResult
from pi_remote.prompts import PromptRow, parse_answer_body
from routes import pi_remote_bp

TOKEN = "test-token-pi-remote"
KEY = ("s1", "i1")


def question_prompt_id(prompt_id="call-1", status="open", value=None, answered_by=None):
    return PromptRow(
        prompt_id=prompt_id,
        kind="select",
        title="Which colour",
        message="pick one",
        options=["red", "green"],
        allow_free_text=False,
        timeout_ms=None,
        status=status,
        value=value,
        answered_by=answered_by,
    )


class FakeClient:
    def __init__(self, row=None, result=None, send_error=None, command_id="cmd-9"):
        self.row = row
        self.result = result
        self.send_error = send_error
        self.command_id = command_id
        self.sent = []
        self.awaited = []
        self.store = SimpleNamespace(prompts=SimpleNamespace(get=lambda *_a: self.row))

    def send_command(self, key, kind, args):
        self.sent.append((key, kind, args))
        return self.command_id, self.send_error

    def await_command(self, command_id, timeout_s):
        self.awaited.append((command_id, timeout_s))
        return self.result


def run(client, prompt_id="call-1", body=None, wait_s=1.0):
    return answer_prompt(client, KEY, prompt_id, {"value": "red"} if body is None else body, wait_s)


def test_parse_answer_body_accepts_every_prompt_kind():
    assert parse_answer_body({"value": "red"}) == ("red", None)
    assert parse_answer_body({"value": True}) == (True, None)
    accepted = parse_answer_body({"value": {"choice": "deny", "reason": "no"}})
    assert accepted[1] is None
    assert parse_answer_body({}) == (None, "invalid_body")
    assert parse_answer_body({"value": None}) == (None, "invalid_value")
    assert parse_answer_body([]) == (None, "invalid_body")
    assert parse_answer_body(None) == (None, "invalid_body")
    assert parse_answer_body({"value": 7}) == (None, "invalid_value")
    assert parse_answer_body({"value": ["red"]}) == (None, "invalid_value")
    assert parse_answer_body({"value": {"choice": "sometimes"}}) == (None, "invalid_value")
    assert parse_answer_body({"value": "x" * 4001}) == (None, "invalid_value")


def test_an_accepted_answer_forwards_the_command_and_returns_pi_s_result():
    client = FakeClient(row=question_prompt_id(), result=CommandResult("cmd-9", True, None))
    status, payload = run(client)
    assert status == 200
    assert payload == {"command_id": "cmd-9", "prompt_id": "call-1", "ok": True}
    assert client.sent == [(KEY, "answer_prompt", {"prompt_id": "call-1", "value": "red"})]
    assert client.awaited == [("cmd-9", 1.0)]


def test_an_unknown_prompt_is_404_and_reaches_no_command():
    client = FakeClient(row=None)
    status, payload = run(client)
    assert status == 404
    assert payload == {"error": "unknown_prompt", "prompt_id": "call-1"}
    assert client.sent == []


def test_a_closed_prompt_is_409_carrying_the_winning_value():
    closed_row = question_prompt_id(status="answered", value="green", answered_by="remote")
    client = FakeClient(row=closed_row)
    status, payload = run(client)
    assert status == 409
    assert payload["error"] == "prompt_already_answered"
    assert payload["value"] == "green"
    assert payload["answered_by"] == "remote"
    assert payload["reason"] == "answered"
    assert client.sent == []


def test_a_cancelled_prompt_reports_the_same_conflict_with_no_value():
    client = FakeClient(row=question_prompt_id(status="cancelled"))
    status, payload = run(client)
    assert status == 409
    assert payload["value"] is None
    assert payload["reason"] == "cancelled"


def test_a_malformed_body_is_400_before_any_lookup():
    client = FakeClient(row=question_prompt_id())
    assert run(client, body={"nope": 1})[0] == 400
    assert run(client, body={"value": 12})[0] == 400
    assert client.sent == []


def test_pi_rejecting_the_value_for_the_kind_is_400_with_that_reason():
    client = FakeClient(
        row=question_prompt_id(), result=CommandResult("cmd-9", False, "invalid_value")
    )
    status, payload = run(client)
    assert status == 400
    assert payload["error"] == "invalid_value"
    assert payload["command_id"] == "cmd-9"


def test_pi_answering_already_answered_is_409_with_the_row_pi_just_closed():
    already = CommandResult("cmd-9", False, "prompt_already_answered")
    client = FakeClient(row=question_prompt_id(), result=already)
    client.row = question_prompt_id(status="answered", value="green", answered_by="terminal")
    status, payload = run(client)
    assert status == 409
    assert payload["error"] == "prompt_already_answered"
    assert payload["value"] == "green"


def test_pi_not_knowing_the_prompt_is_404():
    unknown = CommandResult("cmd-9", False, "prompt_unknown")
    client = FakeClient(row=question_prompt_id(), result=unknown)
    status, payload = run(client)
    assert status == 404
    assert payload["error"] == "prompt_unknown"


def test_an_offline_session_is_409():
    client = FakeClient(row=question_prompt_id(), send_error="pi_session_offline")
    status, payload = run(client)
    assert status == 409
    assert payload["error"] == "pi_session_offline"


def test_a_command_pi_has_not_settled_is_202_pending():
    client = FakeClient(row=question_prompt_id(), result=None)
    status, payload = run(client)
    assert status == 202
    assert payload == {"command_id": "cmd-9", "prompt_id": "call-1", "pending": True}


@pytest.fixture
def env(monkeypatch):
    ok = CommandResult("cmd-9", True, None)
    client = FakeClient(row=question_prompt_id(), result=ok)
    monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", SimpleNamespace(client=client))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.register_blueprint(pi_remote_bp)
    app.testing = True
    return {"client": app.test_client(), "fake": client}


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def answer_route(env, body, prompt_id="call-1", headers=None):
    return env["client"].post(
        f"/api/pi/sessions/s1/i1/prompts/{prompt_id}/answer",
        headers=_auth() if headers is None else headers,
        data=body,
        content_type="application/json" if isinstance(body, str) else None,
    )


def test_the_answer_route_returns_what_answering_decided(env):
    response = answer_route(env, json.dumps({"value": "red"}))
    assert response.status_code == 200
    assert response.get_json() == {"command_id": "cmd-9", "prompt_id": "call-1", "ok": True}
    assert env["fake"].sent[0][2] == {"prompt_id": "call-1", "value": "red"}


def test_the_answer_route_needs_a_token(env):
    response = env["client"].post(
        "/api/pi/sessions/s1/i1/prompts/call-1/answer", json={"value": "red"}
    )
    assert response.status_code == 401


def test_the_answer_route_is_503_without_a_client(monkeypatch):
    monkeypatch.setattr(pi_remote_routes, "pi_remote_supervisor", SimpleNamespace(client=None))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.register_blueprint(pi_remote_bp)
    app.testing = True
    response = app.test_client().post(
        "/api/pi/sessions/s1/i1/prompts/call-1/answer",
        headers=_auth(),
        json={"value": "red"},
    )
    assert response.status_code == 503
    assert response.get_json() == {"error": "pi_remote_unavailable"}


def test_the_answer_route_rejects_a_body_that_is_not_json(env):
    response = answer_route(env, "not json")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_body"
