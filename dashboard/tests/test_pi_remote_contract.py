from pi_remote.contract import (
    ByeFrame,
    ContextUsage,
    ErrorCode,
    HeartbeatFrame,
    HelloFrame,
    ModelRef,
    validate_request,
)


HELLO = {
    "protocol": 1,
    "type": "hello",
    "session_id": "s1",
    "instance_id": "i1",
    "session_file": None,
    "cwd": "/tmp",
    "name": None,
    "pid": 1,
    "model": {"provider": "mistral", "id": "mistral-small-latest"},
    "thinking_level": None,
    "reason": "startup",
    "previous_session_id": None,
    "pi_version": None,
    "ext_version": "0.1.0",
}

HEARTBEAT = {
    "protocol": 1,
    "type": "heartbeat",
    "session_id": "s1",
    "instance_id": "i1",
    "state": "idle",
    "context": {"tokens": 5, "window": 100, "percent": 5},
    "sent_at": 1,
}

BYE = {
    "protocol": 1,
    "type": "bye",
    "session_id": "s1",
    "instance_id": "i1",
    "reason": "shutdown",
}


def test_non_post_is_not_found():
    assert validate_request("GET", "/v1/hello", HELLO) == (404, ErrorCode.NOT_FOUND, None)


def test_unknown_path_is_not_found():
    assert validate_request("POST", "/v1/nope", HELLO) == (404, ErrorCode.NOT_FOUND, None)


def test_protocol_checked_before_path():
    assert validate_request("POST", "/v1/nope", {"protocol": 2}) == (
        400,
        ErrorCode.UNSUPPORTED_PROTOCOL,
        None,
    )


def test_body_must_be_an_object():
    assert validate_request("POST", "/v1/hello", None) == (400, ErrorCode.BAD_FRAME, None)
    assert validate_request("POST", "/v1/hello", []) == (400, ErrorCode.BAD_FRAME, None)


def test_type_must_match_the_path():
    body = dict(HELLO, type="heartbeat")
    assert validate_request("POST", "/v1/hello", body) == (400, ErrorCode.BAD_FRAME, None)


def test_identity_is_required():
    body = dict(HELLO)
    body.pop("instance_id")
    assert validate_request("POST", "/v1/hello", body) == (400, ErrorCode.BAD_FRAME, None)


def test_hello_required_fields():
    body = dict(HELLO, cwd=None)
    assert validate_request("POST", "/v1/hello", body) == (400, ErrorCode.BAD_FRAME, None)


def test_hello_returns_a_typed_frame():
    status, code, frame = validate_request("POST", "/v1/hello", dict(HELLO, unknown_field="x"))
    assert status == 200
    assert code is None
    assert isinstance(frame, HelloFrame)
    assert frame.session_id == "s1"
    assert frame.model == ModelRef(provider="mistral", id="mistral-small-latest")
    assert not hasattr(frame, "unknown_field")


def test_heartbeat_returns_a_typed_frame():
    status, code, frame = validate_request("POST", "/v1/heartbeat", HEARTBEAT)
    assert status == 200
    assert code is None
    assert isinstance(frame, HeartbeatFrame)
    assert frame.context == ContextUsage(tokens=5, window=100, percent=5)


def test_heartbeat_required_fields():
    body = dict(HEARTBEAT)
    body["state"] = "sleeping"
    assert validate_request("POST", "/v1/heartbeat", body) == (400, ErrorCode.BAD_FRAME, None)
    body = dict(HEARTBEAT)
    body["context"] = {"tokens": "five"}
    assert validate_request("POST", "/v1/heartbeat", body) == (400, ErrorCode.BAD_FRAME, None)


def test_bye_returns_a_typed_frame():
    status, code, frame = validate_request("POST", "/v1/bye", BYE)
    assert status == 200
    assert code is None
    assert isinstance(frame, ByeFrame)
    assert frame.reason == "shutdown"
