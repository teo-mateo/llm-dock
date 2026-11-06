from copy import deepcopy

NAMES = ("empty", "waiting", "absent", "offline")
PROMPT = {
    "prompt_id": "fixture-prompt-1", "kind": "select", "title": "Which check should run?",
    "message": "Fixture question, not a real request.", "options": ["Unit tests", "UI check"],
    "allow_free_text": False, "timeout_ms": None,
}


def sessions(name):
    if name not in NAMES:
        raise ValueError("unknown scenario")
    common = {
        "instance_id": "fixture-instance", "cwd": "/fixture/llm-dock", "model": "fixture/model",
        "thinking_level": "low", "first_seen": 1000, "last_seen": 2000,
        "ended_at": None, "end_reason": None, "live": True, "state": "idle", "context_percent": 12,
        "prompts": [],
    }
    live = {**deepcopy(common), "session_id": "fixture-live", "name": "Fixture live session"}
    ended = {**deepcopy(common), "session_id": "fixture-ended", "name": "Fixture ended session",
             "live": False, "state": None, "ended_at": 2000, "end_reason": "shutdown"}
    if name == "waiting":
        live["prompts"] = [deepcopy(PROMPT)]
        ended["prompts"] = [deepcopy(PROMPT)]
    if name == "absent":
        live.pop("prompts")
        ended.pop("prompts")
    if name == "offline":
        live.update(live=False, state=None, ended_at=2000, end_reason="shutdown")
    return [live, ended]
