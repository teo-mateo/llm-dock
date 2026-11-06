from typing import Any, Callable, Dict, Optional, Tuple

from .command_queue import CommandQueue
from .commands import CommandResultsFrame, CommandsPollFrame
from .contract import (
    PATHS,
    ErrorCode,
    HTTP_BAD_REQUEST,
    HTTP_NOT_FOUND,
    JsonResponse,
    bye_ok,
    command_results_ok,
    commands_ok,
    error_response,
    events_ok,
    heartbeat_ok,
    hello_ok,
    validate_request,
)
from .events import EventsEnvelope, parse_events
from .frames import ByeFrame, HeartbeatFrame, HelloFrame
from .read_model import EventView, SessionSummary, session_summary
from .registry import PresenceRegistry, RegistryResult
from .store import PiRemoteDB


PublishCallback = Callable[
    [str, Tuple[str, str], Tuple[EventView, ...], Optional[SessionSummary]], None
]


def _noop(*args) -> None:
    return None


class PiRemoteHandler:
    def __init__(
        self,
        registry: PresenceRegistry,
        store: PiRemoteDB,
        publish: Optional[PublishCallback] = None,
        queue: Optional[CommandQueue] = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.publish = publish or _noop
        self.queue = queue or CommandQueue()
        self._routes: Dict[str, Callable[[Any, int], JsonResponse]] = {
            PATHS["hello"]: self._hello,
            PATHS["heartbeat"]: self._heartbeat,
            PATHS["bye"]: self._bye,
            PATHS["events"]: self._events,
            PATHS["commands_poll"]: self._commands_poll,
            PATHS["command_results"]: self._command_results,
        }

    def handle(self, method: str, path: str, body: Any, now: int) -> JsonResponse:
        status, code, frame = validate_request(method, path, body)
        if code is not None:
            return error_response(status, code)
        route = self._routes[path]
        return route(frame, now)

    def _publish_session(self, session_id: str, instance_id: str, now: int) -> None:
        row = self.store.get_session(session_id, instance_id)
        if row is None:
            return
        presence = self.registry.get(session_id, instance_id, now)
        summary = session_summary(row, presence)
        self.publish("session", (session_id, instance_id), (), summary)

    def _hello(self, frame: HelloFrame, now: int) -> JsonResponse:
        self.registry.register(frame, now)
        self.store.upsert_session(frame, now)
        self._publish_session(frame.session_id, frame.instance_id, now)
        acked = self.store.acked_seq(frame.session_id, frame.instance_id)
        return hello_ok(frame.session_id, frame.instance_id, now, acked)

    def _heartbeat(self, frame: HeartbeatFrame, now: int) -> JsonResponse:
        previous = self.registry.get(frame.session_id, frame.instance_id, now)
        result = self.registry.heartbeat(frame, now)
        if result is RegistryResult.OK:
            self.store.touch_session(frame.session_id, frame.instance_id, now)
            if previous is None or previous.state != frame.state:
                self._publish_session(frame.session_id, frame.instance_id, now)
            return heartbeat_ok(now)
        return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)

    def _bye(self, frame: ByeFrame, now: int) -> JsonResponse:
        result = self.registry.bye(frame, now)
        if result is RegistryResult.OK:
            key = (frame.session_id, frame.instance_id)
            pending = self.queue.drop_key(key)
            self.store.drop_commands(
                [command.command_id for command in pending], now
            )
            self.store.end_session(
                frame.session_id, frame.instance_id, frame.reason, now
            )
            self._publish_session(frame.session_id, frame.instance_id, now)
            return bye_ok()
        return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)

    def _events(self, envelope: EventsEnvelope, now: int) -> JsonResponse:
        result = self.registry.touch(envelope.session_id, envelope.instance_id, now)
        if result is not RegistryResult.OK:
            return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)
        frame = parse_events(envelope.body)
        if frame is None:
            return error_response(HTTP_BAD_REQUEST, ErrorCode.BAD_FRAME)
        result = self.store.ingest(frame, now)
        if result.inserted:
            events = tuple(
                EventView(event.seq, event.type, event.ts, event.payload)
                for event in result.inserted
            )
            self.publish("events", (frame.session_id, frame.instance_id), events, None)
        return events_ok(result.acked_seq)

    def _commands_poll(self, frame: CommandsPollFrame, now: int) -> JsonResponse:
        key = (frame.session_id, frame.instance_id)
        result = self.registry.touch(frame.session_id, frame.instance_id, now)
        if result is not RegistryResult.OK:
            return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)
        self.store.touch_session(frame.session_id, frame.instance_id, now)
        commands = self.queue.take(key, now, frame.wait_ms / 1000)
        return commands_ok(commands)

    def _command_results(self, frame: CommandResultsFrame, now: int) -> JsonResponse:
        key = (frame.session_id, frame.instance_id)
        result = self.registry.touch(frame.session_id, frame.instance_id, now)
        if result is not RegistryResult.OK:
            return error_response(HTTP_NOT_FOUND, ErrorCode.UNKNOWN_SESSION)
        self.store.touch_session(frame.session_id, frame.instance_id, now)
        known = self.queue.complete(key, frame.results)
        for command_result in known:
            self.store.complete_command(command_result, now)
        return command_results_ok()
