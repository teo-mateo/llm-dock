import json
from pathlib import Path

from pi_remote.handler import PiRemoteHandler
from pi_remote.registry import PresenceRegistry
from pi_remote.store import PiRemoteDB


FIXTURES = Path(__file__).resolve().parents[2] / "pi-extension" / "test" / "contract" / "frames.json"


def test_golden_contract_frames():
    cases = json.loads(FIXTURES.read_text())
    registry = PresenceRegistry()
    store = PiRemoteDB(":memory:")
    handler = PiRemoteHandler(registry, store)

    for index, case in enumerate(cases):
        status, payload = handler.handle(
            "POST", case["path"], case["request"], case["now"]
        )
        assert status == case["status"], f"case {index} {case['path']} at {case['now']}"
        assert payload == case["response"], f"case {index} {case['path']} at {case['now']}"

    store.close()
