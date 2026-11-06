from pi_remote.contract import validate_request


HELLO = {
    "protocol": 1,
    "type": "hello",
    "session_id": "s1",
    "instance_id": "i1",
    "session_file": None,
    "cwd": "/tmp",
    "name": None,
    "pid": 1,
    "model": None,
    "thinking_level": None,
    "reason": "startup",
    "previous_session_id": None,
    "pi_version": None,
    "ext_version": "0.1.0",
}


def test_non_post_is_not_found():
    assert validate_request("GET", "/v1/hello", HELLO) == (404, "not_found", None)


def test_unknown_path_is_not_found():
    assert validate_request("POST", "/v1/nope", HELLO) == (404, "not_found", None)


def test_protocol_checked_before_path():
    assert validate_request("POST", "/v1/nope", {"protocol": 2}) == (
        400,
        "unsupported_protocol",
        None,
    )


def test_body_must_be_an_object():
    assert validate_request("POST", "/v1/hello", None) == (400, "bad_frame", None)
    assert validate_request("POST", "/v1/hello", []) == (400, "bad_frame", None)


def test_type_must_match_the_path():
    body = dict(HELLO, type="heartbeat")
    assert validate_request("POST", "/v1/hello", body) == (400, "bad_frame", None)


def test_identity_is_required():
    body = dict(HELLO)
    body.pop("instance_id")
    assert validate_request("POST", "/v1/hello", body) == (400, "bad_frame", None)


def test_hello_required_fields():
    body = dict(HELLO, cwd=None)
    assert validate_request("POST", "/v1/hello", body) == (400, "bad_frame", None)


def test_heartbeat_required_fields():
    body = {
        "protocol": 1,
        "type": "heartbeat",
        "session_id": "s1",
        "instance_id": "i1",
        "state": "idle",
        "context": None,
        "sent_at": 1,
    }
    assert validate_request("POST", "/v1/heartbeat", body) == (200, None, body)
    body["state"] = "sleeping"
    assert validate_request("POST", "/v1/heartbeat", body) == (400, "bad_frame", None)


def test_unknown_fields_are_ignored():
    body = dict(HELLO, unknown_field="ignored")
    assert validate_request("POST", "/v1/hello", body) == (200, None, body)
