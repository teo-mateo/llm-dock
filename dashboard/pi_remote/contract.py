from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Union

PROTOCOL_VERSION = 1
STALE_AFTER_MS = 45000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
SESSION_REASONS = frozenset({"startup", "reload", "new", "resume", "fork"})
STATES = frozenset({"idle", "working"})

PATHS = {
    "hello": "/v1/hello",
    "heartbeat": "/v1/heartbeat",
    "bye": "/v1/bye",
}

PATH_TO_TYPE = {path: kind for kind, path in PATHS.items()}


class ErrorCode(str, Enum):
    BAD_FRAME = "bad_frame"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    UNKNOWN_SESSION = "unknown_session"
    NOT_FOUND = "not_found"


END_REASON_STALE = "stale"
END_REASON_DASHBOARD_RESTART = "dashboard_restart"


@dataclass(frozen=True)
class JsonResponse:
    status: int
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ModelRef:
    provider: str
    id: str


@dataclass(frozen=True)
class ContextUsage:
    tokens: Optional[float]
    window: Optional[float]
    percent: Optional[float]


@dataclass(frozen=True)
class HelloFrame:
    session_id: str
    instance_id: str
    session_file: Optional[str]
    cwd: str
    name: Optional[str]
    pid: int
    model: Optional[ModelRef]
    thinking_level: Optional[str]
    reason: str
    previous_session_id: Optional[str]
    pi_version: Optional[str]
    ext_version: str


@dataclass(frozen=True)
class HeartbeatFrame:
    session_id: str
    instance_id: str
    state: str
    context: Optional[ContextUsage]
    sent_at: int


@dataclass(frozen=True)
class ByeFrame:
    session_id: str
    instance_id: str
    reason: Optional[str]


Frame = Union[HelloFrame, HeartbeatFrame, ByeFrame]


def error_payload(code: ErrorCode) -> Dict[str, Any]:
    return {"ok": False, "protocol": PROTOCOL_VERSION, "error": code.value}


def error_response(status: int, code: ErrorCode) -> JsonResponse:
    return JsonResponse(status, error_payload(code))


def hello_ok(session_id: str, instance_id: str, now: int) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "session_id": session_id,
            "instance_id": instance_id,
            "server_time": now,
        },
    )


def heartbeat_ok(now: int) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {"ok": True, "protocol": PROTOCOL_VERSION, "server_time": now},
    )


def bye_ok() -> JsonResponse:
    return JsonResponse(HTTP_OK, {"ok": True, "protocol": PROTOCOL_VERSION})


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _optional_str(body: Dict[str, Any], key: str) -> bool:
    value = body.get(key)
    return value is None or isinstance(value, str)


def _parse_model(body: Dict[str, Any]) -> Optional[ModelRef]:
    model = body.get("model")
    if model is None:
        return None
    if not isinstance(model, dict):
        return None
    provider = model.get("provider")
    model_id = model.get("id")
    if not isinstance(provider, str) or not isinstance(model_id, str):
        return None
    return ModelRef(provider=provider, id=model_id)


def _parse_hello(body: Dict[str, Any]) -> Optional[HelloFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not isinstance(body.get("cwd"), str):
        return None
    if not _is_int(body.get("pid")):
        return None
    if body.get("reason") not in SESSION_REASONS:
        return None
    if not isinstance(body.get("ext_version"), str):
        return None
    for key in ("session_file", "name", "thinking_level", "previous_session_id", "pi_version"):
        if not _optional_str(body, key):
            return None
    model = _parse_model(body)
    if body.get("model") is not None and model is None:
        return None
    return HelloFrame(
        session_id=session_id,
        instance_id=instance_id,
        session_file=body.get("session_file"),
        cwd=body["cwd"],
        name=body.get("name"),
        pid=body["pid"],
        model=model,
        thinking_level=body.get("thinking_level"),
        reason=body["reason"],
        previous_session_id=body.get("previous_session_id"),
        pi_version=body.get("pi_version"),
        ext_version=body["ext_version"],
    )


def _parse_context(body: Dict[str, Any]) -> Optional[ContextUsage]:
    context = body.get("context")
    if context is None:
        return None
    if not isinstance(context, dict):
        return None
    for key in ("tokens", "window", "percent"):
        value = context.get(key)
        if value is not None and not _is_number(value):
            return None
    return ContextUsage(
        tokens=context.get("tokens"),
        window=context.get("window"),
        percent=context.get("percent"),
    )


def _parse_heartbeat(body: Dict[str, Any]) -> Optional[HeartbeatFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if body.get("state") not in STATES:
        return None
    if not _is_int(body.get("sent_at")):
        return None
    context = _parse_context(body)
    if body.get("context") is not None and context is None:
        return None
    return HeartbeatFrame(
        session_id=session_id,
        instance_id=instance_id,
        state=body["state"],
        context=context,
        sent_at=body["sent_at"],
    )


def _parse_bye(body: Dict[str, Any]) -> Optional[ByeFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not _optional_str(body, "reason"):
        return None
    return ByeFrame(
        session_id=session_id,
        instance_id=instance_id,
        reason=body.get("reason"),
    )


def validate_request(
    method: str, path: str, body: Any
) -> "tuple[int, Optional[ErrorCode], Optional[Frame]]":
    if method != "POST":
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    if not isinstance(body, dict):
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    protocol = body.get("protocol")
    if not _is_int(protocol) or protocol != PROTOCOL_VERSION:
        return HTTP_BAD_REQUEST, ErrorCode.UNSUPPORTED_PROTOCOL, None
    kind = PATH_TO_TYPE.get(path)
    if kind is None:
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    if body.get("type") != kind:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    if kind == "hello":
        frame = _parse_hello(body)
    elif kind == "heartbeat":
        frame = _parse_heartbeat(body)
    else:
        frame = _parse_bye(body)
    if frame is None:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    return HTTP_OK, None, frame
