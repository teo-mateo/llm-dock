import json

from inspector.sse_assembly import assemble_json, assemble_stream

EMPTY = {"text": "", "reasoning": "", "tool_calls": [], "finish_reason": None, "usage": None}


class TestAssembleStream:
    def test_plain_text_deltas(self):
        raw = (
            'data: {"choices": [{"delta": {"content": "Hel"}, "index": 0}]}\n\n'
            'data: {"choices": [{"delta": {"content": "lo"}, "index": 0}]}\n\n'
            'data: [DONE]\n\n'
        )
        assert assemble_stream(raw) == {
            "text": "Hello",
            "reasoning": "",
            "tool_calls": [],
            "finish_reason": None,
            "usage": None,
        }

    def test_reasoning_content_and_reasoning_both_collected(self):
        raw_a = (
            'data: {"choices": [{"delta": {"reasoning_content": "step "}, "index": 0}]}\n\n'
            'data: {"choices": [{"delta": {"reasoning_content": "done"}, "index": 0}]}\n\n'
        )
        assert assemble_stream(raw_a)["reasoning"] == "step done"
        raw_b = 'data: {"choices": [{"delta": {"reasoning": "thought"}, "index": 0}]}\n\n'
        assert assemble_stream(raw_b)["reasoning"] == "thought"

    def test_tool_calls_interleaved_by_index(self):
        raw = (
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "call-b", '
            '"function": {"name": "beta", "arguments": ""}}]}, "index": 0}]}\n\n'
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-a", '
            '"function": {"name": "alpha", "arguments": "x"}}, '
            '{"index": 1, "function": {"arguments": "y"}}]}, "index": 0}]}\n\n'
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, '
            '"function": {"arguments": "z"}}]}, "index": 0}]}\n\n'
        )
        result = assemble_stream(raw)
        assert result["tool_calls"] == [
            {"index": 0, "id": "call-a", "function": {"name": "alpha", "arguments": "xz"}},
            {"index": 1, "id": "call-b", "function": {"name": "beta", "arguments": "y"}},
        ]

    def test_usage_and_finish_reason(self):
        raw = (
            'data: {"choices": [{"delta": {"content": "a"}, "index": 0}]}\n\n'
            'data: {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}], '
            '"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}\n\n'
            'data: [DONE]\n\n'
        )
        result = assemble_stream(raw)
        assert result["text"] == "a"
        assert result["finish_reason"] == "stop"
        assert result["usage"] == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    def test_malformed_data_line_skipped(self):
        raw = (
            'data: {broken json\n\n'
            'data: {"choices": [{"delta": {"content": "ok"}, "index": 0}]}\n\n'
            'data: [DONE]\n\n'
        )
        result = assemble_stream(raw)
        assert result["text"] == "ok"
        assert result["reasoning"] == ""
        assert result["tool_calls"] == []

    def test_empty_body_returns_empty_shape(self):
        assert assemble_stream("") == EMPTY

    def test_body_parsing_to_nothing_returns_empty_shape(self):
        raw = ": keep-alive comment\ndata: [DONE]\n\n"
        assert assemble_stream(raw) == EMPTY


class TestAssembleJson:
    def test_message_fields(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hi",
                        "reasoning_content": "thinking",
                        "tool_calls": [
                            {"id": "call-1", "type": "function",
                             "function": {"name": "f", "arguments": "{}"}}
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
        }
        result = assemble_json(json.dumps(payload))
        assert result["text"] == "hi"
        assert result["reasoning"] == "thinking"
        assert result["tool_calls"] == payload["choices"][0]["message"]["tool_calls"]
        assert result["finish_reason"] == "tool_calls"
        assert result["usage"] == payload["usage"]

    def test_reasoning_key_variant(self):
        payload = {"choices": [{"message": {"content": "hi", "reasoning": "alt"},
                                "finish_reason": "stop"}]}
        assert assemble_json(json.dumps(payload))["reasoning"] == "alt"

    def test_embeddings_response_returns_empty_shape_plus_usage(self):
        payload = {
            "data": [{"embedding": [0.1, 0.2], "index": 0}],
            "usage": {"prompt_tokens": 8, "total_tokens": 8},
        }
        result = assemble_json(json.dumps(payload))
        assert result["text"] == ""
        assert result["reasoning"] == ""
        assert result["tool_calls"] == []
        assert result["finish_reason"] is None
        assert result["usage"] == {"prompt_tokens": 8, "completion_tokens": None, "total_tokens": 8}

    def test_malformed_json_returns_empty_shape(self):
        assert assemble_json("not json") == EMPTY
        assert assemble_json("") == EMPTY
        assert assemble_json("[1, 2]") == EMPTY
