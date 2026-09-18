import json
from typing import Any, Dict, Optional


def _empty_shape() -> dict:
    return {"text": "", "reasoning": "", "tool_calls": [], "finish_reason": None, "usage": None}


def _usage(usage: Any) -> Optional[dict]:
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _reasoning_part(delta: dict) -> str:
    # llama.cpp and vLLM disagree on this field name; both appear on this wire
    for key in ("reasoning_content", "reasoning"):
        value = delta.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _accumulate_tool_call(slots: Dict[int, dict], entry: dict) -> None:
    index = entry.get("index")
    if not isinstance(index, int):
        index = len(slots)
    slot = slots.setdefault(
        index, {"index": index, "id": None, "function": {"name": None, "arguments": ""}}
    )
    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id and not slot["id"]:
        slot["id"] = entry_id
    function = entry.get("function") or {}
    name = function.get("name")
    if isinstance(name, str) and name and not slot["function"]["name"]:
        slot["function"]["name"] = name
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        slot["function"]["arguments"] += arguments


def assemble_stream(raw: str) -> dict:
    result = _empty_shape()
    if not raw:
        return result
    tool_call_slots: Dict[int, dict] = {}
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(chunk, dict):
            continue
        usage = chunk.get("usage")
        if usage is not None:
            result["usage"] = _usage(usage)
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        choice = choices[0]
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                result["text"] += content
            result["reasoning"] += _reasoning_part(delta)
            tool_calls = delta.get("tool_calls")
            if isinstance(tool_calls, list):
                for entry in tool_calls:
                    if isinstance(entry, dict):
                        _accumulate_tool_call(tool_call_slots, entry)
        finish_reason = choice.get("finish_reason")
        if finish_reason:
            result["finish_reason"] = finish_reason
    result["tool_calls"] = [tool_call_slots[i] for i in sorted(tool_call_slots)]
    return result


def assemble_json(raw: str) -> dict:
    result = _empty_shape()
    try:
        payload = json.loads(raw)
    except ValueError:
        return result
    if not isinstance(payload, dict):
        return result
    usage = payload.get("usage")
    if usage is not None:
        result["usage"] = _usage(usage)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return result
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    if isinstance(content, str):
        result["text"] = content
    reasoning = message.get("reasoning_content")
    if not (isinstance(reasoning, str) and reasoning):
        reasoning = message.get("reasoning")
    if isinstance(reasoning, str):
        result["reasoning"] = reasoning
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        result["tool_calls"] = [tc for tc in tool_calls if isinstance(tc, dict)]
    finish_reason = choice.get("finish_reason")
    if finish_reason:
        result["finish_reason"] = finish_reason
    return result
