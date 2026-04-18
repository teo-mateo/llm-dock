import json
import logging

import requests

logger = logging.getLogger(__name__)


def resolve_service(service_name: str) -> dict:
    """Resolve a service name to host_port and api_key using docker_utils."""
    from docker_utils import get_docker_services
    services = get_docker_services()
    for svc in services:
        if svc["name"] == service_name and svc["status"] == "running":
            return {
                "host_port": svc["host_port"],
                "api_key": svc["api_key"],
            }
    return None


def build_messages_array(system_prompt: str, messages: list) -> list:
    """Build the messages array for the OpenAI-compatible API.
    Only includes role and content (no reasoning_content).
    Messages with images use the multipart content format."""
    arr = []
    if system_prompt:
        arr.append({"role": "system", "content": system_prompt})
    for msg in messages:
        images = json.loads(msg.images_json) if msg.images_json else []
        if images:
            content_parts = []
            if msg.content:
                content_parts.append({"type": "text", "text": msg.content})
            for data_url in images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
            arr.append({"role": msg.role, "content": content_parts})
        else:
            arr.append({"role": msg.role, "content": msg.content})
    return arr


def stream_chat_completion(service_name: str, messages_array: list, tools: list = None):
    """Stream a chat completion from a llama.cpp service.

    Yields (event_type, data) tuples:
      - ("delta", {"content": ..., "reasoning_content": ..., "raw": ...})
      - ("done", {"content": full_content, "reasoning_content": full_reasoning})
      - ("tool_calls", {"tool_calls": [{"id": ..., "function": {"name": ..., "arguments": ...}}]})
      - ("error", {"message": ...})
    """
    svc = resolve_service(service_name)
    if svc is None:
        yield ("error", {"message": f"Service '{service_name}' is not reachable. Is it running?"})
        return

    url = f"http://localhost:{svc['host_port']}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {svc['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": messages_array,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    collected_content = ""
    collected_reasoning = ""
    collected_tool_calls = []  # accumulated from streaming chunks
    finish_reason = None

    try:
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=300)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            error_body = resp.text
            yield ("error", {"message": f"Model returned HTTP {resp.status_code}: {error_body}"})
            return

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            choice = chunk.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            chunk_finish = choice.get("finish_reason")
            if chunk_finish:
                finish_reason = chunk_finish

            # Accumulate content
            content_piece = delta.get("content", "")
            reasoning_piece = delta.get("reasoning_content", "")
            if content_piece:
                collected_content += content_piece
            if reasoning_piece:
                collected_reasoning += reasoning_piece

            # Accumulate tool calls from streaming chunks
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    while len(collected_tool_calls) <= idx:
                        collected_tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                    if "id" in tc and tc["id"]:
                        collected_tool_calls[idx]["id"] = tc["id"]
                    if "function" in tc:
                        fn = tc["function"]
                        if "name" in fn and fn["name"]:
                            collected_tool_calls[idx]["function"]["name"] += fn["name"]
                        if "arguments" in fn and fn["arguments"]:
                            collected_tool_calls[idx]["function"]["arguments"] += fn["arguments"]

            # Forward content deltas to frontend
            if content_piece or reasoning_piece:
                yield ("delta", {
                    "content": content_piece,
                    "reasoning_content": reasoning_piece,
                    "raw": data,
                })

        # Stream ended — determine what happened
        if finish_reason == "tool_calls" or (collected_tool_calls and not collected_content):
            yield ("tool_calls", {"tool_calls": collected_tool_calls})
        else:
            yield ("done", {
                "content": collected_content,
                "reasoning_content": collected_reasoning or None,
            })

    except requests.ConnectionError:
        yield ("error", {"message": f"Service '{service_name}' is not reachable. Is it running?"})
    except requests.Timeout:
        yield ("error", {"message": f"Request to '{service_name}' timed out."})
    except Exception as e:
        logger.exception("Unexpected error during streaming")
        yield ("error", {"message": f"Unexpected error: {str(e)}"})
