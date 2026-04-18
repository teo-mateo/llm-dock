import difflib
import json
import logging
import re

import requests

from .constants import CRITIQUE_SYSTEM_PROMPT, DEFAULT_CONTEXT_WINDOW
from .llm_proxy import resolve_service
from .models import Message

logger = logging.getLogger(__name__)


def build_critique_context(messages: list, target_msg: Message, context_window: int = DEFAULT_CONTEXT_WINDOW) -> str:
    """Build the critique context from recent messages.
    Only includes role + content (no reasoning)."""
    # Get messages up to and including the target
    relevant = [m for m in messages if m.seq <= target_msg.seq]
    # Take last N messages
    if len(relevant) > context_window:
        relevant = relevant[-context_window:]

    parts = []
    for m in relevant:
        tag = "user" if m.role == "user" else "assistant"
        parts.append(f"<{tag}>\n{m.content}\n</{tag}>")

    return "\n\n".join(parts)


def request_critique(sidekick_service: str, context: str, extra_instructions: str = "") -> dict:
    """Send a critique request to the sidekick model and parse the response."""
    svc = resolve_service(sidekick_service)
    if svc is None:
        return {"error": f"Service '{sidekick_service}' is not reachable. Is it running?"}

    url = f"http://localhost:{svc['host_port']}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {svc['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the conversation:\n\n{context}\n\nPlease critique the last assistant response.{chr(10) + chr(10) + 'Additional instructions: ' + extra_instructions if extra_instructions else ''}"},
        ],
        "temperature": 0.3,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        if resp.status_code != 200:
            return {"error": f"Sidekick returned HTTP {resp.status_code}: {resp.text}"}

        data = resp.json()
        raw_content = data["choices"][0]["message"].get("content", "")
        raw_reasoning = data["choices"][0]["message"].get("reasoning_content", "")

        # The actual critique may be in content or reasoning_content depending on model
        critique_text = raw_content if raw_content.strip() else raw_reasoning

        return parse_critique_response(critique_text, raw_content or raw_reasoning)

    except requests.ConnectionError:
        return {"error": f"Service '{sidekick_service}' is not reachable. Is it running?"}
    except requests.Timeout:
        return {"error": f"Critique request to '{sidekick_service}' timed out."}
    except Exception as e:
        logger.exception("Failed to get critique")
        return {"error": str(e)}


def parse_critique_response(text: str, raw_response: str) -> dict:
    """Parse the critique JSON from the model's response."""
    # Try direct JSON parse
    try:
        result = json.loads(text)
        result["raw_response"] = raw_response
        return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned.strip(), flags=re.MULTILINE)

    try:
        result = json.loads(cleaned)
        result["raw_response"] = raw_response
        return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Last resort: try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            result = json.loads(match.group())
            result["raw_response"] = raw_response
            return result
        except json.JSONDecodeError:
            pass

    return {
        "verdict": "error",
        "summary": "Failed to parse critique response",
        "annotations": [],
        "raw_response": raw_response,
    }


def validate_annotations(annotations: list, original_content: str) -> list:
    """Validate and fix span_text matches against the original content."""
    validated = []
    for ann in annotations:
        span = ann.get("span_text", "")
        if not span:
            continue

        # Exact match
        if span in original_content:
            validated.append(ann)
            continue

        # Case-insensitive match
        lower_content = original_content.lower()
        lower_span = span.lower()
        if lower_span in lower_content:
            # Find the actual text in original case
            idx = lower_content.index(lower_span)
            ann["span_text"] = original_content[idx:idx + len(span)]
            validated.append(ann)
            continue

        # Fuzzy match
        best_ratio = 0
        best_match = None
        span_len = len(span)
        for i in range(len(original_content) - span_len + 1):
            candidate = original_content[i:i + span_len]
            ratio = difflib.SequenceMatcher(None, span, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate

        if best_ratio >= 0.7 and best_match:
            ann["span_text"] = best_match
            validated.append(ann)
        else:
            logger.warning(f"Dropping annotation: span_text not found (best ratio: {best_ratio:.2f}): {span[:50]}...")

    return validated
