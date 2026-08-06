"""Replaying persisted tool calls into the rebuilt chat history.

Without this, build_messages_array flattened an assistant turn down to its
prose. A model that had just written a file saw only its own claim ("Created
long-joke.txt") with no evidence a tool was ever involved — and on the next
"do another" it produced another claim and called nothing. Observed in
conversation f2bf0a6e (llamacpp-deepseek-v4-flash-q2): the file it announced
was never created.
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.llm_proxy import (
    MAX_REPLAYED_TOOL_ARG_CHARS,
    MAX_REPLAYED_TOOL_RESULT_CHARS,
    build_messages_array,
)
from chat.models import Message


def _msg(role, content, tool_calls=None, reasoning_content=None, seq=0):
    return Message(
        id=f"m{seq}",
        conversation_id="c",
        role=role,
        content=content,
        reasoning_content=reasoning_content,
        tool_calls_json=json.dumps(tool_calls) if tool_calls else None,
        seq=seq,
    )


def _call(name="create_file", arguments=None, result="Created a.txt (10 bytes)",
          server_id="project-files"):
    return {"name": name, "server_id": server_id,
            "arguments": {"path": "a.txt"} if arguments is None else arguments,
            "result": result}


def _roles(arr):
    return [m["role"] for m in arr]


class TestReplayShape:
    def test_tool_turn_expands_to_call_result_and_prose(self):
        msgs = [
            _msg("user", "write a joke file", seq=0),
            _msg("assistant", "Created `a.txt`.", tool_calls=[_call()], seq=1),
        ]
        arr = build_messages_array("", msgs)
        assert _roles(arr) == ["user", "assistant", "tool", "assistant"]

        call_msg, tool_msg, prose = arr[1], arr[2], arr[3]
        assert call_msg["content"] is None
        assert tool_msg["content"] == "Created a.txt (10 bytes)"
        assert prose["content"] == "Created `a.txt`."
        assert "tool_calls" not in prose

    def test_tool_call_id_links_call_to_result(self):
        msgs = [_msg("assistant", "done", tool_calls=[_call(), _call(name="read_file")], seq=1)]
        arr = build_messages_array("", msgs)
        ids = [tc["id"] for tc in arr[0]["tool_calls"]]
        assert ids == [m["tool_call_id"] for m in arr if m["role"] == "tool"]
        assert len(set(ids)) == 2  # distinct per call

    def test_name_is_namespaced_to_match_the_offered_schema(self):
        # mcp_client advertises tools as `server_id__tool_name`; a replayed call
        # naming the bare tool wouldn't correspond to anything the model is
        # offered this turn.
        msgs = [_msg("assistant", "ok", tool_calls=[_call()], seq=1)]
        arr = build_messages_array("", msgs)
        assert arr[0]["tool_calls"][0]["function"]["name"] == "project-files__create_file"

    def test_already_namespaced_name_is_not_doubled(self):
        msgs = [_msg("assistant", "ok",
                     tool_calls=[_call(name="project-files__create_file")], seq=1)]
        arr = build_messages_array("", msgs)
        assert arr[0]["tool_calls"][0]["function"]["name"] == "project-files__create_file"

    def test_tool_turn_with_no_prose_omits_the_trailing_assistant(self):
        msgs = [_msg("assistant", "", tool_calls=[_call()], seq=1)]
        assert _roles(build_messages_array("", msgs)) == ["assistant", "tool"]

    def test_reasoning_rides_on_the_call_not_the_prose(self):
        msgs = [_msg("assistant", "done", tool_calls=[_call()],
                     reasoning_content="thinking", seq=1)]
        arr = build_messages_array("", msgs)
        assert arr[0]["reasoning_content"] == "thinking"
        assert "reasoning_content" not in arr[-1]

    def test_missing_result_still_emits_a_tool_message(self):
        # A round cut short (cancel/crash) records the call but no result. An
        # assistant tool_calls entry with no matching tool message is a protocol
        # error for some backends, so emit a placeholder rather than drop it.
        msgs = [_msg("assistant", "", tool_calls=[_call(result=None)], seq=1)]
        arr = build_messages_array("", msgs)
        assert _roles(arr) == ["assistant", "tool"]
        assert "no result recorded" in arr[1]["content"]


class TestUnaffectedTurns:
    def test_plain_turns_are_untouched(self):
        msgs = [_msg("user", "hi", seq=0), _msg("assistant", "hello", seq=1)]
        arr = build_messages_array("SYS", msgs)
        assert arr == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

    def test_empty_tool_calls_json_is_not_a_tool_turn(self):
        msgs = [_msg("assistant", "hello", seq=1)]
        msgs[0].tool_calls_json = "[]"
        assert _roles(build_messages_array("", msgs)) == ["assistant"]

    def test_malformed_tool_calls_json_degrades_to_prose(self):
        msgs = [_msg("assistant", "hello", seq=1)]
        msgs[0].tool_calls_json = "{not json"
        arr = build_messages_array("", msgs)
        assert arr == [{"role": "assistant", "content": "hello"}]

    def test_images_still_use_multipart(self):
        msgs = [_msg("user", "look", seq=0)]
        msgs[0].images_json = json.dumps(["data:image/png;base64,AAA"])
        arr = build_messages_array("", msgs)
        assert arr[0]["content"][0] == {"type": "text", "text": "look"}
        assert arr[0]["content"][1]["type"] == "image_url"


class TestArgumentNormalization:
    def test_dict_arguments_become_json(self):
        msgs = [_msg("assistant", "", tool_calls=[_call(arguments={"path": "a.txt"})], seq=1)]
        arr = build_messages_array("", msgs)
        assert json.loads(arr[0]["tool_calls"][0]["function"]["arguments"]) == {"path": "a.txt"}

    def test_python_repr_arguments_are_recovered(self):
        # Older rows stored a str()'d dict rather than JSON.
        msgs = [_msg("assistant", "", tool_calls=[_call(arguments="{'path': 'Todo.md'}")], seq=1)]
        arr = build_messages_array("", msgs)
        assert json.loads(arr[0]["tool_calls"][0]["function"]["arguments"]) == {"path": "Todo.md"}

    def test_json_string_arguments_pass_through(self):
        msgs = [_msg("assistant", "", tool_calls=[_call(arguments='{"path": "a.txt"}')], seq=1)]
        arr = build_messages_array("", msgs)
        assert json.loads(arr[0]["tool_calls"][0]["function"]["arguments"]) == {"path": "a.txt"}

    def test_unparseable_arguments_become_an_empty_object(self):
        msgs = [_msg("assistant", "", tool_calls=[_call(arguments="<<garbage>>")], seq=1)]
        arr = build_messages_array("", msgs)
        assert arr[0]["tool_calls"][0]["function"]["arguments"] == "{}"


class TestBounding:
    def test_long_argument_values_are_clipped_but_stay_valid_json(self):
        # A 150k-char create_file must not be resent verbatim on every later
        # turn — that is the whole conversation's context budget.
        body = "x" * 150_000
        msgs = [_msg("assistant", "wrote it",
                     tool_calls=[_call(arguments={"path": "big.txt", "content": body})], seq=1)]
        arr = build_messages_array("", msgs)
        args = json.loads(arr[0]["tool_calls"][0]["function"]["arguments"])
        assert args["path"] == "big.txt"  # short values untouched
        assert len(args["content"]) < MAX_REPLAYED_TOOL_ARG_CHARS + 100
        assert "truncated" in args["content"]

    def test_long_results_are_clipped(self):
        msgs = [_msg("assistant", "", tool_calls=[_call(result="y" * 500_000)], seq=1)]
        arr = build_messages_array("", msgs)
        assert len(arr[1]["content"]) < MAX_REPLAYED_TOOL_RESULT_CHARS + 100
        assert "truncated" in arr[1]["content"]

    def test_short_results_are_untouched(self):
        msgs = [_msg("assistant", "", tool_calls=[_call(result="Created a.txt")], seq=1)]
        arr = build_messages_array("", msgs)
        assert arr[1]["content"] == "Created a.txt"


def test_the_regression_this_fixes():
    """The model must see that its file write went through a tool.

    Reproduces conversation f2bf0a6e's history: before the fix the rebuilt
    context held only prose claims, so 'do another' produced a third claim and
    no call.
    """
    msgs = [
        _msg("user", "write a new file with a joke", seq=0),
        _msg("assistant", "Created `long-joke.txt` with a long joke.",
             tool_calls=[_call(arguments={"path": "long-joke.txt", "content": "joke"},
                               result="Created long-joke.txt (3486 bytes)")], seq=1),
        _msg("user", "do another", seq=2),
    ]
    arr = build_messages_array("", msgs)
    assert any(m.get("tool_calls") for m in arr), "no tool call in the replayed history"
    assert any(m["role"] == "tool" for m in arr), "no tool result in the replayed history"
    wire = json.dumps(arr)
    assert "project-files__create_file" in wire
    assert "Created long-joke.txt (3486 bytes)" in wire
