import json
from datetime import datetime
from typing import Callable

SNAPSHOT = "snapshot"
DELTA = "delta"
ERROR = "error"

KEEPALIVE_FRAME = ": keepalive\n\n"

Clock = Callable[[], datetime]


def _frame(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def snapshot_frame(snapshot: list[dict], now: Clock) -> str:
    return _frame({
        "type": SNAPSHOT,
        "data": {
            "services": snapshot,
            "total": len(snapshot),
            "running": sum(1 for s in snapshot if s["status"] == "running"),
            "stopped": sum(1 for s in snapshot if s["status"] != "running"),
        },
        "timestamp": now().isoformat() + "Z",
    })


def delta_frame(event: dict) -> str:
    payload = {
        "type": DELTA,
        "service_name": event["service_name"],
        "status": event["status"],
        "action": event["action"],
        "container_id": event["container_id"],
        "timestamp": datetime.fromtimestamp(event["timestamp"]).isoformat() + "Z",
    }
    if "metadata" in event:
        payload["metadata"] = event["metadata"]
    return _frame(payload)


def error_frame(message: str) -> str:
    return _frame({"type": ERROR, "message": message})
