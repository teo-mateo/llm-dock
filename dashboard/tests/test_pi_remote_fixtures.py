import itertools
import json
from pathlib import Path

from pi_remote.command_queue import CommandQueue
from pi_remote.frames import HelloFrame
from pi_remote.handler import PiRemoteHandler
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB


FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "frames.json"
EVENTS_FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "events.json"
COMMANDS_FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "commands.json"



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


def test_golden_contract_commands():
    cases = json.loads(COMMANDS_FIXTURES.read_text())
    registry = PresenceRegistry()
    store = PiRemoteDB(":memory:")
    counter = itertools.count(1)
    queue = CommandQueue(new_id=lambda: f"cmd-{next(counter)}")
    handler = PiRemoteHandler(registry, store, queue=queue)
    seed = HelloFrame(
        session_id="s1",
        instance_id="i1",
        session_file=None,
        cwd="/tmp",
        name=None,
        pid=1,
        model=None,
        thinking_level=None,
        reason="startup",
        previous_session_id=None,
        parent_session_id=None,
        pi_version=None,
        ext_version="0.1.0",
    )
    registry.register(seed, cases[0]["now"])
    store.sessions.upsert(seed, cases[0]["now"])

    for index, case in enumerate(cases[1:], start=1):
        enqueue = case.get("enqueue")
        if enqueue is not None:
            queue.enqueue(
                ("s1", "i1"),
                enqueue["kind"],
                enqueue["args"],
                enqueue["issued_at"],
            )
        response = handler.handle(
            "POST", case["path"], case["request"], case["now"]
        )
        assert response.status == case["status"], f"case {index} {case['path']} at {case['now']}"
        assert response.payload == case["response"], f"case {index} {case['path']} at {case['now']}"

    store.close()
