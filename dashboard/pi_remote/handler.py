from typing import Any, Tuple

from .contract import PATH_TO_TYPE, error_payload, validate_request
from .registry import PresenceRegistry
from .store import PiRemoteDB


class PiRemoteHandler:
    def __init__(self, registry: PresenceRegistry, store: PiRemoteDB) -> None:
        self.registry = registry
        self.store = store

    def handle(self, method: str, path: str, body: Any, now: int) -> Tuple[int, Any]:
        status, code, frame = validate_request(method, path, body)
        if code is not None:
            return status, error_payload(code)

        kind = PATH_TO_TYPE[path]
        session_id = frame["session_id"]
        instance_id = frame["instance_id"]

        if kind == "hello":
            self.registry.register(frame, now)
            self.store.upsert_session(frame, now)
            return 200, {
                "ok": True,
                "protocol": 1,
                "session_id": session_id,
                "instance_id": instance_id,
                "server_time": now,
            }

        if kind == "heartbeat":
            result = self.registry.heartbeat(
                session_id,
                instance_id,
                frame["state"],
                frame.get("context"),
                frame["sent_at"],
                now,
            )
            if result == "ok":
                self.store.touch_session(session_id, instance_id, now)
                return 200, {"ok": True, "protocol": 1, "server_time": now}
            if result == "stale":
                self.store.end_session(session_id, instance_id, "stale", now)
            return 404, error_payload("unknown_session")

        result = self.registry.bye(session_id, instance_id, now)
        if result == "ok":
            self.store.end_session(
                session_id, instance_id, frame.get("reason"), now
            )
            return 200, {"ok": True, "protocol": 1}
        if result == "stale":
            self.store.end_session(session_id, instance_id, "stale", now)
        return 404, error_payload("unknown_session")
