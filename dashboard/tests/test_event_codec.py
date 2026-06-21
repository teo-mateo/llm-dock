"""Unit tests for chat.event_codec (Phase 1 of #58).

Pin the SSE framing so the wire format is stable across persisted chat,
spinoff, and future run/ghost streams. The delta passthrough is asserted to
stay raw (the documented exception that a later paired FE+BE PR will change).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import event_codec


def test_done_sentinel():
    assert event_codec.DONE == "data: [DONE]\n\n"


def test_encode_sse_event_prefixes_type_and_frames():
    out = event_codec.encode_sse_event("tool_call", {"name": "solve", "server_id": "x"})
    assert out.startswith("data: ") and out.endswith("\n\n")
    payload = json.loads(out[len("data: "):-2])
    assert payload == {"type": "tool_call", "name": "solve", "server_id": "x"}
    # `type` is the first key so the serialized bytes match the old hand-written
    # frames.
    assert out.startswith('data: {"type": "tool_call"')


def test_encode_sse_event_without_data():
    assert event_codec.encode_sse_event("done_marker") == 'data: {"type": "done_marker"}\n\n'


def test_encode_sse_typeless_payload():
    # The legacy error frame carries no `type` key.
    assert event_codec.encode_sse({"error": "boom"}) == 'data: {"error": "boom"}\n\n'


def test_encode_sse_delta_passthrough_is_raw():
    raw = '{"choices":[{"delta":{"content":"hi"}}]}'
    out = event_codec.encode_sse_delta(raw)
    # Forwarded verbatim — NOT wrapped in a typed {"type":"delta"} frame.
    assert out == f"data: {raw}\n\n"
    assert "\"type\"" not in out


def test_encode_sse_handles_non_serializable_via_default_str():
    class Weird:
        def __str__(self):
            return "weird!"

    out = event_codec.encode_sse({"x": Weird()})
    assert json.loads(out[len("data: "):-2]) == {"x": "weird!"}
