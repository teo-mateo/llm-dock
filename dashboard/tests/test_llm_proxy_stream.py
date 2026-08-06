"""stream_chat_completion upstream-connection teardown (Phase 5 of #58).

Cooperative cancellation closes the generator (GeneratorExit); the streaming
`requests` response must be released in a finally either way, so a cancelled
run doesn't leak the model-server socket.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import llm_proxy


class _FakeResp:
    def __init__(self, lines):
        self.status_code = 200
        self.encoding = None
        self._lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


def _patch(monkeypatch, resp, captured=None):
    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})

    def _post(*a, **k):
        if captured is not None:
            captured.update(k.get("json", {}))
        return resp
    monkeypatch.setattr(llm_proxy.requests, "post", _post)


def test_response_closed_on_normal_completion(monkeypatch):
    resp = _FakeResp([
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        '',
        'data: [DONE]',
    ])
    _patch(monkeypatch, resp)

    events = list(llm_proxy.stream_chat_completion("svc", []))
    assert any(e[0] == "done" for e in events)
    assert resp.closed


def test_response_closed_on_early_generator_close(monkeypatch):
    # A long stream the consumer abandons mid-way (cooperative cancel).
    resp = _FakeResp([f'data: {{"choices":[{{"delta":{{"content":"t{i}"}}}}]}}'
                      for i in range(1000)])
    _patch(monkeypatch, resp)

    gen = llm_proxy.stream_chat_completion("svc", [])
    assert next(gen)[0] == "delta"   # consume one event, leaving the stream open
    gen.close()                      # GeneratorExit -> finally -> resp.close()
    assert resp.closed


def test_tool_choice_override_with_tools(monkeypatch):
    # tool_choice overrides the default "auto" when tools are supplied.
    resp = _FakeResp(['data: [DONE]'])
    captured = {}
    _patch(monkeypatch, resp, captured)

    list(llm_proxy.stream_chat_completion("svc", [], tools=[{"type": "function"}],
                                          tool_choice="none"))
    assert captured["tool_choice"] == "none"
    assert "tools" in captured


def test_tool_choice_pinned_without_tools(monkeypatch):
    # tool_choice="none" is still sent even when no tool schemas are in the
    # request (the forced-final path), for backends that honor it.
    resp = _FakeResp(['data: [DONE]'])
    captured = {}
    _patch(monkeypatch, resp, captured)

    list(llm_proxy.stream_chat_completion("svc", [], tools=None, tool_choice="none"))
    assert captured["tool_choice"] == "none"
    assert "tools" not in captured


def test_default_tool_choice_auto_with_tools(monkeypatch):
    # Unchanged default: tools without an explicit tool_choice -> "auto".
    resp = _FakeResp(['data: [DONE]'])
    captured = {}
    _patch(monkeypatch, resp, captured)

    list(llm_proxy.stream_chat_completion("svc", [], tools=[{"type": "function"}]))
    assert captured["tool_choice"] == "auto"


def test_tool_call_event_preserves_accumulated_reasoning(monkeypatch):
    resp = _FakeResp([
        'data: {"choices":[{"delta":{"reasoning_content":"I should search. "}}]}',
        'data: {"choices":[{"delta":{"reasoning_content":"Now calling it.","tool_calls":[{"index":0,"id":"call_1","function":{"name":"srv__search","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}',
        'data: [DONE]',
    ])
    _patch(monkeypatch, resp)

    events = list(llm_proxy.stream_chat_completion(
        "svc",
        [],
        tools=[{"type": "function"}],
    ))
    tool_calls = next(data for event_type, data in events if event_type == "tool_calls")
    assert tool_calls["reasoning_content"] == "I should search. Now calling it."


# -- Streaming tool-call assembly ---------------------------------------


def _tool_arg_chunks(args: str, piece: int = 40):
    """SSE lines delivering `args` as a streamed tool call, piece chars at a time."""
    lines = []
    for i in range(0, len(args), piece):
        name = "project-files__write_file" if i == 0 else ""
        lines.append(
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":'
            f'{{"name":"{name}","arguments":{json.dumps(args[i:i + piece])}}}}}]}}}}]}}'
        )
    lines.append('data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}')
    lines.append('data: [DONE]')
    return lines


def test_pending_ticks_upward_while_arguments_stream(monkeypatch):
    """A big write_file is minutes of streamed JSON. tool_call_pending must keep
    reporting the growing argument size, or the UI shows one frozen
    'assembling call…' for the whole assembly (what the user actually saw).
    """
    args = json.dumps({"path": "big.txt", "content": "x" * 150_000})
    _patch(monkeypatch, _FakeResp(_tool_arg_chunks(args)))

    pending = [d for t, d in llm_proxy.stream_chat_completion(
        "svc", [], tools=[{"type": "function"}]) if t == "tool_call_pending"]

    assert len(pending) > 100, "pending was not re-emitted as arguments grew"
    assert all(p["name"] == "project-files__write_file" for p in pending)
    lens = [p["args_len"] for p in pending]
    assert lens == sorted(lens) and lens[0] < lens[-1]
    assert lens[-1] >= len(args) - llm_proxy.PENDING_ARGS_STEP_CHARS


def test_pending_is_throttled_not_per_token(monkeypatch):
    """One event per PENDING_ARGS_STEP_CHARS of growth, not one per chunk."""
    args = json.dumps({"path": "a.txt", "content": "y" * 20_000})
    _patch(monkeypatch, _FakeResp(_tool_arg_chunks(args, piece=8)))

    pending = [d for t, d in llm_proxy.stream_chat_completion(
        "svc", [], tools=[{"type": "function"}]) if t == "tool_call_pending"]

    chunks = -(-len(args) // 8)
    assert len(pending) < chunks / 10  # far fewer events than argument chunks
    steps = [b["args_len"] - a["args_len"] for a, b in zip(pending, pending[1:])]
    assert all(s >= llm_proxy.PENDING_ARGS_STEP_CHARS for s in steps)


def test_short_tool_call_still_announces_once(monkeypatch):
    """A small call never crosses the throttle step — it must still emit."""
    args = json.dumps({"equation": "x+1"})
    _patch(monkeypatch, _FakeResp(_tool_arg_chunks(args)))

    pending = [d for t, d in llm_proxy.stream_chat_completion(
        "svc", [], tools=[{"type": "function"}]) if t == "tool_call_pending"]

    assert len(pending) >= 1
    assert pending[0]["name"] == "project-files__write_file"
