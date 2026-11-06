PATHS = {
    "hello": "/v1/hello",
    "heartbeat": "/v1/heartbeat",
    "bye": "/v1/bye",
}

PATH_TO_TYPE = {path: kind for kind, path in PATHS.items()}

PROTOCOL_VERSION = 1
STALE_AFTER_MS = 45000
SESSION_REASONS = frozenset({"startup", "reload", "new", "resume", "fork"})
STATES = frozenset({"idle", "working"})


def error_payload(code):
    return {"ok": False, "protocol": PROTOCOL_VERSION, "error": code}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _optional_str(body, key):
    value = body.get(key)
    return value is None or isinstance(value, str)


def _valid_hello(body):
    if not isinstance(body.get("cwd"), str):
        return False
    if not _is_int(body.get("pid")):
        return False
    if body.get("reason") not in SESSION_REASONS:
        return False
    if not isinstance(body.get("ext_version"), str):
        return False
    for key in ("session_file", "name", "thinking_level", "previous_session_id", "pi_version"):
        if not _optional_str(body, key):
            return False
    model = body.get("model")
    if model is not None:
        if not isinstance(model, dict):
            return False
        if not isinstance(model.get("provider"), str) or not isinstance(model.get("id"), str):
            return False
    return True


def _valid_heartbeat(body):
    if body.get("state") not in STATES:
        return False
    if not _is_int(body.get("sent_at")):
        return False
    context = body.get("context")
    if context is None:
        return True
    if not isinstance(context, dict):
        return False
    for key in ("tokens", "window", "percent"):
        value = context.get(key)
        if value is not None and not _is_number(value):
            return False
    return True


def _valid_bye(body):
    return _optional_str(body, "reason")


def validate_request(method, path, body):
    if method != "POST":
        return 404, "not_found", None
    if not isinstance(body, dict):
        return 400, "bad_frame", None
    protocol = body.get("protocol")
    if not _is_int(protocol) or protocol != PROTOCOL_VERSION:
        return 400, "unsupported_protocol", None
    kind = PATH_TO_TYPE.get(path)
    if kind is None:
        return 404, "not_found", None
    if body.get("type") != kind:
        return 400, "bad_frame", None
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return 400, "bad_frame", None
    if not isinstance(instance_id, str) or not instance_id:
        return 400, "bad_frame", None
    if kind == "hello" and not _valid_hello(body):
        return 400, "bad_frame", None
    if kind == "heartbeat" and not _valid_heartbeat(body):
        return 400, "bad_frame", None
    if kind == "bye" and not _valid_bye(body):
        return 400, "bad_frame", None
    return 200, None, body
