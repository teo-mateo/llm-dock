"""Wire shape for per-conversation sampling params.

The interesting assertion is the negative one, mirroring
tests/test_reasoning_level_payload.py: with nothing stored the payload has
exactly the key set it had before this feature, which is what makes the feature
invisible to a conversation that never touched it. The second one that matters is
the tool-turn temperature: the pin is the default, so an explicit temperature
outranks it and an absent one does not add a key.
"""
import json
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


def _patch(monkeypatch, svc, captured):
    monkeypatch.setattr(llm_proxy, "resolve_service", lambda name: dict(svc))

    def _post(*a, **k):
        captured.clear()
        captured.update(k.get("json", {}))
        return _FakeResp()
    monkeypatch.setattr(llm_proxy.requests, "post", _post)


def _svc(template_type, **extra):
    return {"host_port": 1234, "api_key": "k", "template_type": template_type, **extra}


def _send(monkeypatch, svc, params, tools=None):
    captured = {}
    _patch(monkeypatch, svc, captured)
    list(llm_proxy.stream_chat_completion("svc", [{"role": "user", "content": "hi"}],
                                          tools=tools, sampling_params=params))
    return captured


# -- nothing stored: today's request, key set and all --------------------


@pytest.mark.parametrize("svc", [
    _svc("vllm"),
    _svc("llamacpp"),
    _svc("ik_llamacpp"),
    _svc("tabbyapi"),
])
def test_payload_is_unchanged_without_stored_params(monkeypatch, svc):
    captured = _send(monkeypatch, svc, None)
    assert set(captured) == {"messages", "stream"}
    assert captured["stream"] is True


def test_payload_is_unchanged_for_a_service_that_carries_a_model_id(monkeypatch):
    """NInfer and OpenRouter legitimately send ``model``; nothing else moves."""
    for svc in (_svc("ninfer", model="ninfer-a"), _svc("openrouter", model="x/y")):
        captured = _send(monkeypatch, svc, None)
        assert set(captured) == {"messages", "stream", "model"}
        assert captured["model"] == svc["model"]


def test_tool_turn_payload_without_params_is_unchanged(monkeypatch):
    """The tool-loop temperature pin is exactly where it was before this feature."""
    captured = _send(monkeypatch, _svc("vllm"), None, tools=[{"type": "function"}])
    assert set(captured) == {"messages", "stream", "tools", "tool_choice", "temperature"}
    assert captured["temperature"] == llm_proxy.TOOL_TURN_TEMPERATURE


# -- stored params reach the wire, per engine -----------------------------


def test_vllm_gets_the_openai_names(monkeypatch):
    captured = _send(monkeypatch, _svc("vllm"),
                     {"temperature": 0.4, "top_k": 40, "repetition_penalty": 1.1,
                      "max_tokens": 512, "stop": ["END"]})
    assert captured["temperature"] == 0.4
    assert captured["top_k"] == 40
    assert captured["repetition_penalty"] == 1.1
    assert captured["max_tokens"] == 512
    assert captured["stop"] == ["END"]
    assert "repeat_penalty" not in captured


def test_llamacpp_gets_the_repeat_penalty_name(monkeypatch):
    captured = _send(monkeypatch, _svc("llamacpp"), {"repetition_penalty": 1.2})
    assert captured["repeat_penalty"] == 1.2
    assert "repetition_penalty" not in captured


@pytest.mark.parametrize("engine", ["ik_llamacpp", "tabbyapi", "ds4", "ninfer", "openrouter"])
def test_unmapped_engine_gets_no_sampling_key_at_all(monkeypatch, engine):
    """Stored params cannot add a key for an engine with no verified mapping.

    Not "are ignored by the server" — they are never sent, so there is nothing to
    ignore. The user learns about it from the run_started note instead. Compared
    against the same service with nothing stored, because the engines do not all
    send the same base keys (`model` rides for NInfer and OpenRouter).
    """
    svc = _svc(engine, model="x/y")
    with_params = _send(monkeypatch, svc, {"temperature": 0.1, "top_k": 1, "seed": 5})
    without = _send(monkeypatch, svc, None)
    assert with_params == without
    assert "temperature" not in with_params


def test_empty_stored_dict_sends_nothing(monkeypatch):
    assert set(_send(monkeypatch, _svc("vllm"), {})) == {"messages", "stream"}


# -- the tool-turn temperature default ------------------------------------


def test_explicit_temperature_beats_the_tool_turn_default(monkeypatch):
    """Decision 4: the pin is the default for a tool-bearing turn, not a ceiling.

    Reversing the order would make every tool-using conversation silently ignore
    the operator's temperature, which is the failure this test exists to prevent.
    """
    captured = _send(monkeypatch, _svc("vllm"), {"temperature": 1.4},
                     tools=[{"type": "function"}])
    assert captured["temperature"] == 1.4
    assert captured["temperature"] != llm_proxy.TOOL_TURN_TEMPERATURE


def test_no_temperature_means_the_tool_turn_default_still_applies(monkeypatch):
    captured = _send(monkeypatch, _svc("vllm"), {"top_k": 30},
                     tools=[{"type": "function"}])
    assert captured["temperature"] == llm_proxy.TOOL_TURN_TEMPERATURE
    assert captured["top_k"] == 30


def test_sampling_does_not_disturb_the_reasoning_fields(monkeypatch):
    """Both features write the same payload; neither may drop the other's keys."""
    captured = {}
    _patch(monkeypatch, _svc("llamacpp", reasoning_levels=[{"id": "off", "effort": "off"}]),
           captured)
    list(llm_proxy.stream_chat_completion(
        "svc", [{"role": "user", "content": "hi"}], reasoning_level="off",
        sampling_params={"temperature": 0.5, "seed": 3}))
    assert captured["temperature"] == 0.5 and captured["seed"] == 3
    assert captured["reasoning_effort"] == "none"
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}


# -- the tool loop forwards them ------------------------------------------


def _scripted_stream(scripts, record):
    """Scripts the tool loop's requests; the last scripted stream repeats.

    Each call's kwargs are recorded so a test can assert how the forced final
    request was made, which is the one call a forward-the-first-request test
    would miss.
    """
    def _stream(service_name, messages_array, tools=None, tool_choice=None, *,
                reasoning_level=None, sampling_params=None):
        record.append({"tools": tools, "tool_choice": tool_choice,
                       "sampling_params": sampling_params})
        idx = len(record) - 1
        for event in scripts[idx if idx < len(scripts) else -1]:
            yield event
    return _stream


def _tool_calls_event():
    return ("tool_calls", {"tool_calls": [
        {"id": "c1", "function": {"name": "s__t", "arguments": "{}"}},
    ]})


def test_tool_loop_forwards_params_to_every_request_including_the_forced_final(monkeypatch):
    """A turn must not change its sampler halfway because a tool ran.

    Driven past MAX_TOOL_ROUNDS so the last request is the forced final one
    (tool_choice="none"), which is the call a naive forward-once implementation
    drops.
    """
    calls = []
    tools = [{"type": "function", "function": {"name": "s__t"}}]
    scripts = [_tool_calls_event()] * 5 + [("done", {"content": "final",
                                                     "reasoning_content": None})]

    class _MCP:
        def call_tool(self, server_id, tool_name, arguments, progress_callback=None):
            return ("result", [])

    monkeypatch.setattr(tool_loop, "stream_chat_completion",
                        _scripted_stream([scripts], calls))
    params = {"temperature": 0.2, "seed": 9}
    list(tool_loop.stream_with_tools("svc", [{"role": "user", "content": "hi"}], tools,
                                     _MCP(), sampling_params=params))
    assert len(calls) == 6, calls
    assert calls[-1]["tool_choice"] == "none", calls[-1]
    assert all(call["sampling_params"] == params for call in calls), calls


def test_tool_loop_defaults_to_no_params(monkeypatch):
    calls = []

    def _stream(service_name, messages_array, tools=None, tool_choice=None, *,
                reasoning_level=None, sampling_params=None):
        calls.append(sampling_params)
        yield ("done", {"content": "ok", "reasoning_content": None})

    monkeypatch.setattr(tool_loop, "stream_chat_completion", _stream)
    list(tool_loop.stream_with_tools("svc", [{"role": "user", "content": "hi"}],
                                     [{"type": "function"}], None))
    assert calls == [None]


def test_snapshot_survives_the_json_column(monkeypatch):
    """The runner passes the parsed blob; a round trip through sqlite must not
    change what goes on the wire."""
    import sampling_params as sp
    stored = sp.to_storage({"top_p": 0.8, "seed": 11})
    assert json.loads(stored) == {"top_p": 0.8, "seed": 11}
    captured = _send(monkeypatch, _svc("vllm"), sp.from_storage(stored))
    assert captured["top_p"] == 0.8 and captured["seed"] == 11
