from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .frames import Frame, is_int, parse_bye, parse_hello, parse_heartbeat

PROTOCOL_VERSION = 1
STALE_AFTER_MS = 45000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404

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


def validate_request(
    method: str, path: str, body: Any
) -> Tuple[int, Optional[ErrorCode], Optional[Frame]]:
    if method != "POST":
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    if not isinstance(body, dict):
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    protocol = body.get("protocol")
    if not is_int(protocol) or protocol != PROTOCOL_VERSION:
        return HTTP_BAD_REQUEST, ErrorCode.UNSUPPORTED_PROTOCOL, None
    kind = PATH_TO_TYPE.get(path)
    if kind is None:
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    if body.get("type") != kind:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    if kind == "hello":
        frame = parse_hello(body)
    elif kind == "heartbeat":
        frame = parse_heartbeat(body)
    else:
        frame = parse_bye(body)
    if frame is None:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    return HTTP_OK, None, frame
