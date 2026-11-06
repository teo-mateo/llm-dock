from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, Union

from .commands import (
    CommandResultsFrame,
    CommandsPollFrame,
    parse_command_results,
    parse_commands_poll,
)
from .events import EventsEnvelope, parse_events_envelope
from .frames import Frame, parse_bye, parse_hello, parse_heartbeat
from .wire_types import is_int

PROTOCOL_VERSION = 1
STALE_AFTER_MS = 45000
MAX_EVENTS_BODY_BYTES = 1024 * 1024
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404

PATHS = {
    "hello": "/v1/hello",
    "heartbeat": "/v1/heartbeat",
    "bye": "/v1/bye",
    "events": "/v1/events",
    "commands_poll": "/v1/commands/poll",
    "command_results": "/v1/command-results",
}

PATH_TO_TYPE = {path: kind for kind, path in PATHS.items()}

FrameOrEnvelope = Union[Frame, EventsEnvelope, CommandsPollFrame, CommandResultsFrame]

PARSERS: Dict[str, Callable[[Dict[str, Any]], Optional[FrameOrEnvelope]]] = {
    "hello": parse_hello,
    "heartbeat": parse_heartbeat,
    "bye": parse_bye,
    "events": parse_events_envelope,
    "commands_poll": parse_commands_poll,
    "command_results": parse_command_results,
}


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


def hello_ok(
    session_id: str, instance_id: str, now: int, acked_seq: int
) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "session_id": session_id,
            "instance_id": instance_id,
            "server_time": now,
            "acked_seq": acked_seq,
        },
    )


def events_ok(acked_seq: int) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {"ok": True, "protocol": PROTOCOL_VERSION, "acked_seq": acked_seq},
    )


def heartbeat_ok(now: int) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {"ok": True, "protocol": PROTOCOL_VERSION, "server_time": now},
    )


def bye_ok() -> JsonResponse:
    return JsonResponse(HTTP_OK, {"ok": True, "protocol": PROTOCOL_VERSION})


def commands_ok(commands: Iterable[Any]) -> JsonResponse:
    return JsonResponse(
        HTTP_OK,
        {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "commands": [
                {
                    "command_id": command.command_id,
                    "kind": command.kind,
                    "args": dict(command.args),
                    "issued_at": command.issued_at,
                }
                for command in commands
            ],
        },
    )


def command_results_ok() -> JsonResponse:
    return JsonResponse(HTTP_OK, {"ok": True, "protocol": PROTOCOL_VERSION})


def validate_request(
    method: str, path: str, body: Any
) -> Tuple[int, Optional[ErrorCode], Optional[FrameOrEnvelope]]:
    if method != "POST":
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    kind = PATH_TO_TYPE.get(path)
    if kind is None:
        return HTTP_NOT_FOUND, ErrorCode.NOT_FOUND, None
    if not isinstance(body, dict):
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    protocol = body.get("protocol")
    if not is_int(protocol) or protocol != PROTOCOL_VERSION:
        return HTTP_BAD_REQUEST, ErrorCode.UNSUPPORTED_PROTOCOL, None
    if body.get("type") != kind:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    frame = PARSERS[kind](body)
    if frame is None:
        return HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME, None
    return HTTP_OK, None, frame
