import json
import logging
import re

import requests

logger = logging.getLogger(__name__)


# Known wrong-format markers Qwen3.6 (and similar) emit when the structured
# tool-call format drifts. The qwen3_coder parser strips the canonical
# `<tool_call>…</tool_call>` block, but if the model writes any of these
# instead, the garbage leaks into `content` (or content ends up empty after
# the parser tries to consume a malformed call). Detecting these gives the
# UI a chip to surface the failure ad-hoc rather than rendering an empty
# bubble. Kinds line up 1:1 with the `format drift modes` we've observed.
FORMAT_DRIFT_PATTERNS = [
    ("arg_key_tags", re.compile(r"<arg_key>"),
     "Model emitted `<arg_key>` XML tags in content — Qwen3.6 family format drift."),
    ("arg_value_tags", re.compile(r"<arg_value>"),
     "Model emitted `<arg_value>` XML tags in content — Qwen3.6 family format drift."),
    ("function_text_tag", re.compile(r"<function="),
     "Model emitted `<function=…>` text instead of a structured tool_call."),
    ("json_codeblock_call", re.compile(r"```(?:json|tool_code)\s*\{[\s\S]{0,40}\"(?:name|tool|function)\"\s*:"),
     "Model emitted a JSON tool call in a markdown codeblock instead of structured tool_calls."),
    ("orphan_tool_call_tag", re.compile(r"<tool_call>"),
     "Model emitted a `<tool_call>` tag in content — parser likely failed to consume it."),
    ("orphan_close_function", re.compile(r"</function>"),
     "Model emitted a stray `</function>` close tag — partial/malformed tool call."),
]


def detect_format_drift(content: str, reasoning: str = "", had_tool_calls: bool = False):
    """Return a {kind, snippet, description} dict if content shows known drift, else None.

    Also flags the silent-drop case: reasoning produced but no content and no
    tool calls. That usually means the parser swallowed a malformed call and
    left nothing behind, which is the most confusing failure mode to debug.
    """
    if content:
        for kind, pat, description in FORMAT_DRIFT_PATTERNS:
            m = pat.search(content)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(content), m.end() + 160)
                snippet = content[start:end]
                if start > 0:
                    snippet = "…" + snippet
                if end < len(content):
                    snippet = snippet + "…"
                return {"kind": kind, "snippet": snippet, "description": description}
    if not (content and content.strip()) and not had_tool_calls and reasoning and reasoning.strip():
        return {
            "kind": "silent_drop",
            "snippet": "",
            "description": "Model emitted reasoning but no content and no tool calls. Parser may have silently dropped a malformed tool call.",
        }
    return None


def resolve_service(service_name: str) -> dict:
    """Resolve a service name to connection details.

    Local Docker services resolve to ``{host_port, api_key}`` via
    docker_utils; ``openrouter:<model-id>`` strings resolve to
    ``{base_url, api_key, model, extra_headers}`` (or None when no
    OPENROUTER_API_KEY is configured).
    """
    from . import openrouter
    if openrouter.is_openrouter_service(service_name):
        return openrouter.resolve(service_name)
    from docker_utils import get_docker_services
    services = get_docker_services()
    for svc in services:
        if svc["name"] == service_name and svc["status"] == "running":
            return {
                "host_port": svc["host_port"],
                "api_key": svc["api_key"],
            }
    return None


def unreachable_message(service_name: str) -> str:
    """Error text for a service that failed to resolve."""
    from . import openrouter
    if openrouter.is_openrouter_service(service_name):
        return ("OpenRouter is not configured "
                "(OPENROUTER_API_KEY missing in dashboard/.env).")
    return f"Service '{service_name}' is not reachable. Is it running?"


def build_endpoint(svc: dict) -> tuple:
    """Return (url, headers) for a resolved service — local docker or remote.

    ``base_url`` (when present) is an OpenAI-style base already ending in
    ``/v1``, e.g. ``https://openrouter.ai/api/v1``.
    """
    base = svc.get("base_url") or f"http://localhost:{svc['host_port']}/v1"
    headers = {
        "Authorization": f"Bearer {svc['api_key']}",
        "Content-Type": "application/json",
    }
    headers.update(svc.get("extra_headers") or {})
    return f"{base}/chat/completions", headers


def _extract_error_message(resp) -> str:
    """Pull the provider's error message out of a non-200 response body.

    OpenAI-compatible providers return ``{"error": {"message": ...}}``;
    fall back to the raw body when that shape isn't there.
    """
    try:
        err = resp.json().get("error")
        if isinstance(err, dict) and err.get("message"):
            return err["message"]
    except (ValueError, AttributeError):
        pass
    return resp.text


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


def stream_chat_completion(service_name: str, messages_array: list, tools: list = None,
                           tool_choice: str = None):
    """Stream a chat completion from a llama.cpp service.

    Yields (event_type, data) tuples:
      - ("delta", {"content": ..., "reasoning_content": ..., "raw": ...})
      - ("done", {"content": full_content, "reasoning_content": full_reasoning})
      - ("tool_calls", {"tool_calls": [{"id": ..., "function": {"name": ..., "arguments": ...}}]})
      - ("error", {"message": ...})

    `tool_choice` overrides the default. When `tools` are supplied it defaults to
    "auto"; pass "none" to forbid tool calls (e.g. the tool-loop's forced final
    response, which must produce prose, not yet another tool call).
    """
    svc = resolve_service(service_name)
    if svc is None:
        yield ("error", {"message": unreachable_message(service_name)})
        return

    url, headers = build_endpoint(svc)
    payload = {
        "messages": messages_array,
        "stream": True,
    }
    if svc.get("model"):
        # Remote multi-model providers (OpenRouter) require an explicit model;
        # local single-model servers don't get one and ignore its absence.
        payload["model"] = svc["model"]
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
        # Tool-using turns are sensitive to sampling variance: at vLLM's
        # default temperature=1.0, the model occasionally drifts from the
        # structured tool-call format into XML-in-content (`<arg_key>...`
        # `</function>` ghost calls, etc.). 0.3 keeps the format on-rails
        # without making the answer prose feel robotic.
        payload["temperature"] = 0.3
    elif tool_choice is not None:
        # No tool schemas in the request, but still pin tool_choice (e.g.
        # "none" on the forced final response) for backends that honor it.
        payload["tool_choice"] = tool_choice

    collected_content = ""
    collected_reasoning = ""
    collected_tool_calls = []  # accumulated from streaming chunks
    pending_emitted = set()    # tool-call indices we've already announced via tool_call_pending
    finish_reason = None

    resp = None
    try:
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=300)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            error_body = _extract_error_message(resp)
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

            # OpenRouter can deliver an error object mid-stream (e.g. a rate
            # limit hit after streaming started) instead of a choices chunk.
            if isinstance(chunk, dict) and "error" in chunk:
                err = chunk["error"] or {}
                message = err.get("message") if isinstance(err, dict) else None
                yield ("error", {"message": f"Provider error: {message or json.dumps(err)}"})
                return

            # `choices` can be legitimately empty — OpenRouter emits a final
            # usage chunk with `choices: []` before [DONE]. Treat it (and any
            # other choice-less chunk) as a no-op instead of IndexError-ing.
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta", {})
            chunk_finish = choice.get("finish_reason")
            if chunk_finish:
                finish_reason = chunk_finish

            # Accumulate content
            content_piece = delta.get("content", "")
            reasoning_piece = delta.get("reasoning_content") or delta.get("reasoning") or ""
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
                    # Surface a "pending" event the first time this index has any
                    # name fragment — the full tool_calls event only fires at
                    # finish_reason, which can leave the UI silent for seconds
                    # while the model assembles the call.
                    if idx not in pending_emitted:
                        current_name = collected_tool_calls[idx]["function"]["name"]
                        if current_name:
                            pending_emitted.add(idx)
                            yield ("tool_call_pending", {"index": idx, "name": current_name})

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
            # Format-drift detection — surface known wrong-format failure
            # modes before the `done` event so the UI can render a chip on
            # the assistant bubble even when content is empty/garbage.
            drift = detect_format_drift(
                collected_content,
                reasoning=collected_reasoning,
                had_tool_calls=bool(collected_tool_calls),
            )
            if drift is not None:
                yield ("parse_warning", drift)
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
    finally:
        # Always release the upstream socket — including when the generator is
        # closed early (cooperative cancellation calls stream.close(), which
        # raises GeneratorExit here). Without this, a cancelled run leaves the
        # model-server connection alive until garbage collection.
        if resp is not None:
            resp.close()
