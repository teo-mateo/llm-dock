"""Prompt construction for chat turns.

Extracted from chat.routes._stream_response (Phase 1 of #58) so the message
array can be built from explicit inputs rather than Flask globals / a live
Conversation row. This lets the upcoming background runtime and non-persisted
modes (Ghost Chat, #57) build prompts the same way persisted chat does.
"""
import datetime

from .llm_proxy import build_messages_array
from .mcp_registry import get_tool_hints


def _date_line(today: datetime.date) -> str:
    # Models keep training on data with a past cutoff, so without an explicit
    # "today" they write stale years into time-sensitive queries.
    return (
        f"Current date: {today.isoformat()} ({today.strftime('%A')}). "
        'Use this as "today" when interpreting time-sensitive questions.'
    )


def build_chat_messages(
    system_prompt: str,
    messages: list,
    enabled_servers: list,
    include_date_line: bool = True,
) -> list:
    """Build the OpenAI-compatible message array for a chat turn.

    Augments the system prompt with MCP tool hints (when servers are enabled)
    and an explicit current-date line, then delegates row->dict shaping
    (including image multipart content) to build_messages_array.

    Mirrors the behavior previously inlined in _stream_response; the only
    new affordance is `include_date_line`, which defaults to the historical
    always-on behavior.
    """
    prompt = system_prompt or ""

    if enabled_servers:
        hints = get_tool_hints(enabled_servers)
        if hints:
            prompt = f"{prompt}\n\n{hints}" if prompt else hints

    if include_date_line:
        line = _date_line(datetime.date.today())
        prompt = f"{prompt}\n\n{line}" if prompt else line

    return build_messages_array(prompt, messages)
