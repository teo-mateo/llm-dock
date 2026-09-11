"""Wire shape for reasoning levels (R5, R6, R7), asserted on the payload dict.

The interesting assertion is the negative one: with no level the payload gains
no key at all, which is what makes the feature invisible to services that don't
declare one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import llm_proxy, tool_loop


class _FakeResp:
    def __init__(self, lines=("data: [DONE]",)):
        self.status_code = 200
        self.encoding = None
        self._lines = list(lines)

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line

    def close(self):
        pass


class _MCP:
    """Minimal tool executor: every call returns a fixed result, no artifacts."""

    def __init__(self):
        self.calls = 0

    def call_tool(self, server_id, tool_name, arguments, progress_callback=None):
        self.calls += 1
        return ("tool result text", [])


def _patch(monkeypatch, svc, captured):
    monkeypatch.setattr(llm_proxy, "resolve_service", lambda name: dict(svc))

    def _post(*a, **k):
        captured.clear()
        captured.update(k.get("json", {}))
        return _FakeResp()
    monkeypatch.setattr(llm_proxy.requests, "post", _post)


def _llamacpp(levels="off,low,medium,xhigh", **extra):
    return {"host_port": 1234, "api_key": "k", "template_type": "llamacpp",
            "reasoning_levels": [{"id": i, "effort": i} for i in levels.split(",")] if levels else [],
            **extra}


def _send(monkeypatch, svc, level):
    captured = {}
    _patch(monkeypatch, svc, captured)
    list(llm_proxy.stream_chat_completion("svc", [{"role": "user", "content": "hi"}],
                                          reasoning_level=level))
    return captured


# -- no level: today's payload exactly -----------------------------------


@pytest.mark.parametrize("svc", [
    _llamacpp(),
    _llamacpp(levels=""),
    {"host_port": 1234, "api_key": "k", "template_type": "vllm"},
])
def test_payload_is_unchanged_without_a_level(monkeypatch, svc):
    """R6. Not merely "no reasoning field was added" — the payload is the exact
    key set an un-featured request produces."""
    captured = _send(monkeypatch, svc, None)
    assert set(captured) == {"messages", "stream"}
    assert captured["stream"] is True
    for key in ("reasoning_effort", "chat_template_kwargs", "thinking_budget_tokens",
                "thinking_token_budget"):
        assert key not in captured


def test_empty_string_level_behaves_as_absent(monkeypatch):
    assert set(_send(monkeypatch, _llamacpp(), "")) == {"messages", "stream"}


# -- llamacpp (R5) --------------------------------------------------------


def test_llamacpp_named_level_sets_reasoning_effort(monkeypatch):
    captured = _send(monkeypatch, _llamacpp(), "xhigh")
    assert captured["reasoning_effort"] == "xhigh"
    assert "chat_template_kwargs" not in captured


def test_llamacpp_off_disables_thinking_two_ways(monkeypatch):
    """Templates differ: the server reads enable_thinking itself, some templates
    only honor the kwarg, and effort "none" erases the effort kwarg. Sending
    both is what the sweep measured as reliably silent."""
    captured = _send(monkeypatch, _llamacpp(), "off")
    assert captured["reasoning_effort"] == "none"
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}


def test_llamacpp_level_coexists_with_tools(monkeypatch):
    captured = {}
    _patch(monkeypatch, _llamacpp(), captured)
    list(llm_proxy.stream_chat_completion("svc", [], tools=[{"type": "function"}],
                                          reasoning_level="low"))
    assert captured["reasoning_effort"] == "low"
    assert captured["tool_choice"] == "auto"
    assert captured["temperature"] == 0.3


# -- vllm ----------------------------------------------------------------


def test_vllm_named_level_and_off(monkeypatch):
    svc = {"host_port": 1234, "api_key": "k", "template_type": "vllm",
           "reasoning_levels": [{"id": "off", "effort": "off"},
                                {"id": "minimal", "effort": "minimal"}]}
    assert _send(monkeypatch, svc, "minimal")["reasoning_effort"] == "minimal"
    assert _send(monkeypatch, svc, "off")["reasoning_effort"] == "none"


def test_vllm_off_sends_no_kwargs(monkeypatch):
    """vLLM derives enable_thinking from reasoning_effort itself, so pushing the
    kwarg too would fight the server."""
    svc = {"host_port": 1234, "api_key": "k", "template_type": "vllm",
           "reasoning_levels": [{"id": "off", "effort": "off"}]}
    captured = _send(monkeypatch, svc, "off")
    assert captured["reasoning_effort"] == "none"
    assert "chat_template_kwargs" not in captured


# -- unmapped engines (R7) -----------------------------------------------


@pytest.mark.parametrize("engine", ["ik_llamacpp", "tabbyapi", "ds4", ""])
def test_unmapped_engine_sends_nothing_even_with_a_declared_level(monkeypatch, engine):
    svc = {"host_port": 1234, "api_key": "k", "template_type": engine,
           "reasoning_levels": [{"id": "low", "effort": "low"}]}
    assert set(_send(monkeypatch, svc, "low")) == {"messages", "stream"}


def test_openrouter_payload_is_unchanged(monkeypatch):
    """The exclusion, asserted on the wire: OpenRouter resolves no
    template_type/reasoning_levels, so a level can't reach it even if a client
    somehow stored one."""
    svc = {"base_url": "https://openrouter.ai/api/v1", "api_key": "k", "model": "x",
           "extra_headers": {}}
    captured = _send(monkeypatch, svc, "low")
    assert set(captured) == {"messages", "stream", "model"}
    assert "reasoning_effort" not in captured


# -- a level the service no longer offers (R7) ---------------------------


@pytest.mark.parametrize("level", ["ultra", "minimal", "LOW", " low"])
def test_undeclared_level_never_reaches_the_wire(monkeypatch, level):
    """Rejection is at the wire boundary, not only at the conversation write:
    the service's current declaration is re-read here, so a stale id from any
    route — an old client, a hand-edited row, a ladder since edited — produces
    the no-level payload."""
    captured = _send(monkeypatch, _llamacpp(), level)
    assert set(captured) == {"messages", "stream"}


def test_service_with_no_declaration_ignores_a_stored_level(monkeypatch):
    captured = _send(monkeypatch, _llamacpp(levels=""), "low")
    assert set(captured) == {"messages", "stream"}


def test_no_numeric_budget_field_ever_appears(monkeypatch):
    for svc in (_llamacpp(), _llamacpp(levels=""),
                {"host_port": 1, "api_key": "k", "template_type": "vllm",
                 "reasoning_levels": [{"id": "off", "effort": "off"}]}):
        for level in (None, "off", "low", "xhigh"):
            captured = _send(monkeypatch, svc, level)
            assert "thinking_budget_tokens" not in captured
            assert "thinking_token_budget" not in captured


# -- threaded through the tool loop -------------------------------------


def test_tool_loop_forwards_the_level_to_every_request_including_the_forced_final(monkeypatch):
    """Five tool rounds then a forced final answer: a turn must not change
    thinking posture halfway through, and the forced call is still this turn."""
    seen = []

    def _scripted(service_name, messages_array, tools=None, tool_choice=None, *, reasoning_level=None):
        seen.append({"tool_choice": tool_choice, "reasoning_level": reasoning_level,
                     "rounds": len(messages_array)})
        if len(seen) <= tool_loop.MAX_TOOL_ROUNDS:
            yield ("tool_calls", {"tool_calls": [
                {"id": "t1", "function": {"name": "srv__noop", "arguments": "{}"}}]})
            return
        yield ("done", {"content": "final", "reasoning_content": ""})

    async def _noop(name, arguments):
        return [{"type": "text", "text": "ok"}]

    monkeypatch.setattr(tool_loop, "stream_chat_completion", _scripted)
    events = list(tool_loop.stream_with_tools(
        "svc", [{"role": "user", "content": "hi"}], [{"type": "function"}], _MCP(),
        reasoning_level="medium"))

    assert len(seen) == tool_loop.MAX_TOOL_ROUNDS + 1
    assert all(s["reasoning_level"] == "medium" for s in seen), seen
    assert seen[-1]["tool_choice"] == "none"
    assert events[-1][0] == "done"


def test_tool_loop_defaults_to_no_level(monkeypatch):
    seen = {}

    def _scripted(service_name, messages_array, tools=None, tool_choice=None, *, reasoning_level=None):
        seen["reasoning_level"] = reasoning_level
        yield ("done", {"content": "x", "reasoning_content": ""})

    monkeypatch.setattr(tool_loop, "stream_chat_completion", _scripted)
    list(tool_loop.stream_with_tools("svc", [], [{"type": "function"}], _MCP()))
    assert seen["reasoning_level"] is None
