import json
from pathlib import Path

from pi_remote.events import MAX_EVENTS_BODY_BYTES
from pi_remote.handler import PiRemoteHandler
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB


FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "frames.json"
EVENTS_FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "events.json"

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


def test_golden_contract_frames():
    cases = json.loads(FIXTURES.read_text())
    registry = PresenceRegistry()
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(registry, store)

    for index, case in enumerate(cases):
        response = handler.handle(
            "POST", case["path"], case["request"], case["now"]
        )
        assert response.status == case["status"], f"case {index} {case['path']} at {case['now']}"
        assert response.payload == case["response"], f"case {index} {case['path']} at {case['now']}"

    store.close()


def test_golden_contract_events():
    cases = json.loads(EVENTS_FIXTURES.read_text())
    registry = PresenceRegistry()
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(registry, store)

    for index, case in enumerate(cases):
        response = handler.handle(
            "POST", case["path"], case["request"], case["now"]
        )
        assert response.status == case["status"], f"case {index} {case['path']} at {case['now']}"
        assert response.payload == case["response"], f"case {index} {case['path']} at {case['now']}"

    store.close()


def test_oversize_events_body_is_rejected():
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(PresenceRegistry(), store)
    handler.handle("POST", "/v1/hello", HELLO, 1000)
    body = {
        "protocol": 1,
        "type": "events",
        "session_id": "s1",
        "instance_id": "i1",
        "events": [
            {
                "type": "assistant_message",
                "seq": 1,
                "ts": 1000,
                "text": "x" * (MAX_EVENTS_BODY_BYTES + 1),
                "thinking": "",
                "model": None,
                "usage": None,
                "stop_reason": "stop",
            }
        ],
    }
    response = handler.handle("POST", "/v1/events", body, 1000)
    assert response.status == 400
    assert response.payload == {"ok": False, "protocol": 1, "error": "bad_frame"}
    assert store.stored_events("s1", "i1") == []
    store.close()
