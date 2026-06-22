"""stream_with_tools forced-final-response contract (issue #70).

When a turn exhausts MAX_TOOL_ROUNDS, the loop makes one forced final call.
That final call must ALWAYS terminate the turn with a `done` event — even if a
backend that ignores `tool_choice="none"` emits yet another tool call. Without
this, the caller (runtime) sees the generator exhaust with no `done` and fails
the run as "Stream ended unexpectedly" after the user already waited out every
tool round.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chat.tool_loop as tool_loop


class _MCP:
    """Minimal tool executor: every call returns a fixed result, no artifacts."""

    def __init__(self):
        self.calls = 0

    def call_tool(self, server_id, tool_name, arguments):
        self.calls += 1
        return ("search result text", [])


def _tool_calls_event(name="srv__search"):
    return ("tool_calls", {"tool_calls": [
        {"id": "", "function": {"name": name, "arguments": "{}"}},
    ]})


def _scripted_stream(scripts, record):
    """Return a stream_chat_completion stand-in driven by per-call scripts.

    `scripts[i]` is the event list yielded on the i-th invocation; the last
    script repeats for any further calls. Each call's kwargs are appended to
    `record` so tests can assert how the forced final call was made.
    """
    def _stream(service_name, messages_array, tools=None, tool_choice=None):
        record.append({"tools": tools, "tool_choice": tool_choice})
        idx = len(record) - 1
        events = scripts[idx] if idx < len(scripts) else scripts[-1]
        for ev in events:
            yield ev
    return _stream


def _run(monkeypatch, scripts):
    record = []
    monkeypatch.setattr(tool_loop, "stream_chat_completion", _scripted_stream(scripts, record))
    events = list(tool_loop.stream_with_tools("svc", [{"role": "user", "content": "hi"}],
                                              tools=[{"type": "function"}], mcp_manager=_MCP()))
    return events, record


def test_forced_final_tool_call_still_yields_done(monkeypatch):
    """Regression for #70: 5 rounds of tool calls, then the forced final call
    emits ANOTHER tool call (backend ignored tool_choice). The turn must still
    end on a synthesized `done`, never fall through to no terminal event."""
    rounds = [[_tool_calls_event()] for _ in range(tool_loop.MAX_TOOL_ROUNDS)]
    forced = [("delta", {"content": "Partial answer.", "reasoning_content": ""}),
              _tool_calls_event()]  # unhandled on the forced pass -> falls through
    events, record = _run(monkeypatch, rounds + [forced])

    types = [e[0] for e in events]
    assert types[-1] == "done", f"turn did not terminate with done: {types}"
    # The synthesized done carries whatever prose streamed on the forced pass.
    done = events[-1][1]
    assert done["content"] == "Partial answer."
    # The forced final call (the 6th) forbade tool calls.
    assert len(record) == tool_loop.MAX_TOOL_ROUNDS + 1
    assert record[-1]["tool_choice"] == "none"


def test_forced_final_silent_exhaustion_with_prose_yields_done(monkeypatch):
    """The forced final stream ends with neither done nor tool_calls (silent
    exhaustion) but DID stream prose — finalize that partial answer."""
    rounds = [[_tool_calls_event()] for _ in range(tool_loop.MAX_TOOL_ROUNDS)]
    forced = [("delta", {"content": "Hi", "reasoning_content": ""})]  # no done
    events, _ = _run(monkeypatch, rounds + [forced])

    assert events[-1][0] == "done"
    assert events[-1][1]["content"] == "Hi"


def test_forced_final_tool_only_no_content_yields_error(monkeypatch):
    """Codex #71 iter1 P1: the forced final emits ONLY a tool call (no prose).
    There is genuinely no answer, so the turn must terminate as an error — not
    an empty `done` that ChatRunner would persist as a silent success."""
    rounds = [[_tool_calls_event()] for _ in range(tool_loop.MAX_TOOL_ROUNDS)]
    forced = [("tool_call_pending", {"index": 0, "name": "srv__search"}),
              _tool_calls_event()]  # no content delta at all
    events, _ = _run(monkeypatch, rounds + [forced])

    assert events[-1][0] == "error"
    assert "done" not in [e[0] for e in events]  # never falsely completes
    msg = events[-1][1]["message"]
    assert "tool" in msg.lower()


def test_forced_final_whitespace_only_content_yields_error(monkeypatch):
    """Whitespace-only prose is not a real answer — treat as the empty case."""
    rounds = [[_tool_calls_event()] for _ in range(tool_loop.MAX_TOOL_ROUNDS)]
    forced = [("delta", {"content": "  \n", "reasoning_content": ""}), _tool_calls_event()]
    events, _ = _run(monkeypatch, rounds + [forced])

    assert events[-1][0] == "error"
    assert "done" not in [e[0] for e in events]


def test_forced_final_normal_done_is_forwarded(monkeypatch):
    """When the forced final call returns a proper done, it is forwarded as-is
    (no duplicate synthesized done)."""
    rounds = [[_tool_calls_event()] for _ in range(tool_loop.MAX_TOOL_ROUNDS)]
    forced = [("delta", {"content": "Final.", "reasoning_content": ""}),
              ("done", {"content": "Final.", "reasoning_content": None})]
    events, record = _run(monkeypatch, rounds + [forced])

    assert [e[0] for e in events].count("done") == 1
    assert events[-1][1]["content"] == "Final."
    assert record[-1]["tool_choice"] == "none"


def test_normal_completion_before_cap_unaffected(monkeypatch):
    """A turn that answers (done) on the first round never reaches the forced
    path and is not sent tool_choice="none"."""
    events, record = _run(monkeypatch, [[("done", {"content": "ok", "reasoning_content": None})]])

    assert [e[0] for e in events] == ["done"]
    assert len(record) == 1
    assert record[0]["tool_choice"] is None  # default auto-choice path
