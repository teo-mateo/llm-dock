from typing import Any, Callable, Dict

from .contract import (
    PATHS,
    ByeFrame,
    ErrorCode,
    HTTP_NOT_FOUND,
    HeartbeatFrame,
    HelloFrame,
    JsonResponse,
    bye_ok,
    error_response,
    heartbeat_ok,
    hello_ok,
    validate_request,
)
from .registry import PresenceRegistry, RegistryResult
from .store import PiRemoteDB


class PiRemoteHandler:
    def __init__(self, registry: PresenceRegistry, store: PiRemoteDB) -> None:
        self.registry = registry
        self.store = store
        self._routes: Dict[str, Callable[[Any, int], JsonResponse]] = {
            PATHS["hello"]: self._hello,
            PATHS["heartbeat"]: self._heartbeat,
            PATHS["bye"]: self._bye,
        }

    def handle(self, method: str, path: str, body: Any, now: int) -> JsonResponse:
        status, code, frame = validate_request(method, path, body)
        if code is not None:
            return error_response(status, code)
        route = self._routes[path]
        return route(frame, now)

    def _hello(self, frame: HelloFrame, now: int) -> JsonResponse:
        self.registry.register(frame, now)
        self.store.upsert_session(frame, now)
        return hello_ok(frame.session_id, frame.instance_id, now)

    def _heartbeat(self, frame: HeartbeatFrame, now: int) -> JsonResponse:
        result = self.registry.heartbeat(frame, now)
        if result is RegistryResult.OK:
            self.store.touch_session(frame.session_id, frame.instance_id, now)
            return heartbeat_ok(now)
        return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)

    def _bye(self, frame: ByeFrame, now: int) -> JsonResponse:
        result = self.registry.bye(frame, now)
        if result is RegistryResult.OK:
            self.store.end_session(
                frame.session_id, frame.instance_id, frame.reason, now
            )
            return bye_ok()
        return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)
