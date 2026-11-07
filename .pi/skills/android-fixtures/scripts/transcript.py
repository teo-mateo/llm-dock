from copy import deepcopy
import hashlib
import json
import time

SESSION_ID = "fixture-cache"
INSTANCE_ID = "fixture-instance"
FIRST_SEEN = 1_700_000_000_000
TURNS = 1000
PAGE_SIZE = 500


def summary(last_seq=0, first_seen=FIRST_SEEN, live=True):
    return {
        "session_id": SESSION_ID, "instance_id": INSTANCE_ID,
        "name": "Fixture cache transcript", "cwd": "/fixture/cache-verification",
        "model": "fixture/review-model", "thinking_level": "medium",
        "first_seen": first_seen, "last_seen": first_seen + last_seq * 10,
        "ended_at": None if live else first_seen + last_seq * 10,
        "end_reason": None if live else "fixture-ended", "live": live,
        "state": "idle" if live else None, "context_percent": 37.5, "prompts": [],
    }


def turn_events(turn, start, marker):
    paragraphs = [
        f"Reviewing retry module {turn}: the request keeps its original correlation id while "
        "a transient transport error is retried. The cancellation boundary must run before "
        "another attempt starts, rather than relying on a later UI update.\n\n",
        f"For shard {turn % 31}, the trace includes both an accepted response and a delayed failure. "
        "A replacement request owns a distinct generation, so an older callback cannot mutate "
        "the replacement's state or commit its stale checkpoint.\n\n",
        f"The focused tests for module {turn} cover retry, cancellation and duplicate responses. "
        "The expected state is checked independently of the scheduling order. The patch below "
        "leaves unrelated services and persistent user data unchanged.",
    ]
    source = "\n".join(
        f"{line:04d} module_{turn}/retry_{line % 7}.py trace={hashlib.sha256(f'{turn}/{line}'.encode()).hexdigest()[:20]} "
        "assert accepted.generation == request.generation; preserve committed state on cancellation"
        for line in range(1, 19)
    )
    test_output = "\n".join(
        f"test_module_{turn}_case_{case} PASSED trace={hashlib.sha256(f'test/{turn}/{case}'.encode()).hexdigest()[:20]} "
        "(request cursor and immutable snapshot agree)"
        for case in range(1, 9)
    )
    read_id, test_id = f"read-{turn}", f"tests-{turn}"
    records = [
        ("state", {"state": "working"}),
        ("user_message", {"text": f"Review retry module {turn}, inspect its source and run focused cancellation tests.", "origin": "terminal", "image_count": 0}),
        ("assistant_delta", {"text": paragraphs[0], "thinking": "Check ownership before modifying the retry boundary."}),
        ("assistant_delta", {"text": paragraphs[1], "thinking": "The old failure must not invalidate a replacement request."}),
        ("compaction", {"tokens_before": 12000 + turn}),
        ("assistant_delta", {"text": paragraphs[2], "thinking": "Use a controlled completion order in the regression."}),
        ("assistant_message", {"text": "".join(paragraphs), "thinking": "Ownership and cursor validation precede persistence.", "model": {"provider": "fixture", "id": "review-model"}, "usage": {"output": 220}, "stop_reason": "tool_use"}),
        ("tool_start", {"call_id": read_id, "name": "read", "args": json.dumps({"path": f"src/module_{turn}/retry.py", "offset": 1, "limit": 80})}),
        ("tool_update", {"call_id": read_id, "partial": source[:600]}),
        ("tool_end", {"call_id": read_id, "name": "read", "result": source, "duration_ms": 17, "is_error": False}),
        ("tool_start", {"call_id": test_id, "name": "bash", "args": json.dumps({"command": f"pytest tests/module_{turn}/test_retry.py -q"})}),
        ("tool_update", {"call_id": test_id, "partial": test_output[:400]}),
        ("tool_end", {"call_id": test_id, "name": "bash", "result": test_output, "duration_ms": 83, "is_error": False}),
        ("assistant_message", {"text": f"{marker}\n\nModule {turn}: source inspection and eight focused checks agree. "
                               "The cursor is consistent with the visible transcript; replacement work retains ownership.",
                               "thinking": "", "usage": {"output": 48}, "stop_reason": "stop"}),
        ("run_end", {"outcome": "completed"}),
        ("state", {"state": "idle"}),
    ]
    return [{"seq": start + index, "type": kind, "ts": FIRST_SEEN + (start + index) * 10, "payload": payload}
            for index, (kind, payload) in enumerate(records)]


class TranscriptFixture:
    def __init__(self):
        self.generation = 0
        self.reset()

    def reset(self):
        self.generation += 1
        self.first_seen = FIRST_SEEN + self.generation
        self.events = []
        for turn in range(1, TURNS + 1):
            marker = f"CACHE_BASELINE_END_{TURNS}" if turn == TURNS else f"Fixture result {turn}"
            self.events.extend(turn_events(turn, len(self.events) + 1, marker))
        self.suffixes = 0
        self.gate = "open"
        self.offline = False
        self.deleted = False
        self.live = True
        self.requests = []
        self.request_id = 0

    def rows(self):
        return [] if self.deleted else [summary(len(self.events), self.first_seen, self.live)]

    def control(self, action, gate=None):
        if action == "reset":
            self.reset()
        elif action == "gate" and gate in ("open", "replay", "summary"):
            self.gate = gate
        elif action == "append" and not self.deleted:
            self.suffixes += 1
            self.events.extend(turn_events(TURNS + self.suffixes, len(self.events) + 1,
                                           f"CACHE_SUFFIX_{self.suffixes}_END"))
        elif action in ("offline", "online"):
            self.offline = action == "offline"
        elif action == "end" and not self.deleted:
            self.live = False
        elif action == "remove":
            self.deleted = True
        else:
            raise ValueError("invalid transcript control")

    def request(self, after, status):
        self.request_id += 1
        entry = {"id": self.request_id, "after": after, "status": status, "started_monotonic": time.monotonic(),
                 "batches": [], "sent_events": 0, "sse_body_bytes": 0, "summary_sent": False}
        self.requests.append(entry)
        self.requests = self.requests[-100:]
        return entry

    def stats(self):
        byte_counts = {}
        for event in self.events:
            size = len(json.dumps(event).encode())
            byte_counts[event["type"]] = byte_counts.get(event["type"], 0) + size
        return {"session_id": SESSION_ID, "instance_id": INSTANCE_ID, "first_seen": self.first_seen,
                "event_count": len(self.events), "event_json_bytes": sum(byte_counts.values()),
                "event_bytes_by_type": byte_counts, "latest_seq": len(self.events), "suffixes": self.suffixes,
                "gate": self.gate, "offline": self.offline, "deleted": self.deleted, "live": self.live,
                "requests": deepcopy(self.requests)}
