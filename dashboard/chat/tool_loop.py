"""Tool-calling loop — handles multi-turn tool execution during streaming."""

import json
import logging

from .llm_proxy import stream_chat_completion
from .mcp_client import MCPClientManager, parse_tool_name

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


def stream_with_tools(service_name: str, messages_array: list, tools: list, mcp_manager: MCPClientManager):
    """Stream a chat completion with tool-calling support.

    Yields (event_type, data) tuples:
      - ("delta", {"content": ..., "reasoning_content": ..., "raw": ...})
      - ("tool_call", {"name": ..., "arguments": ..., "server_id": ...})
      - ("tool_result", {"name": ..., "result": ..., "server_id": ...})
      - ("done", {"content": ..., "reasoning_content": ...})
      - ("error", {"message": ...})
    """
    for round_num in range(MAX_TOOL_ROUNDS):
        tool_calls_received = False

        for event_type, data in stream_chat_completion(service_name, messages_array, tools):
            if event_type == "delta":
                yield ("delta", data)

            elif event_type == "tool_calls":
                tool_calls_received = True
                tool_calls = data["tool_calls"]

                # Build assistant message with tool_calls for conversation history
                assistant_tool_msg = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc["id"] or f"call_{round_num}_{i}",
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        }
                        for i, tc in enumerate(tool_calls)
                    ],
                }
                messages_array.append(assistant_tool_msg)

                # Execute each tool call
                for i, tc in enumerate(tool_calls):
                    namespaced_name = tc["function"]["name"]
                    server_id, tool_name = parse_tool_name(namespaced_name)
                    try:
                        arguments = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}

                    # Notify frontend about the tool call
                    yield ("tool_call", {
                        "name": tool_name,
                        "arguments": arguments,
                        "server_id": server_id,
                    })

                    # Execute the tool
                    if server_id:
                        result_text, artifacts = mcp_manager.call_tool(server_id, tool_name, arguments)
                    else:
                        result_text = f"Error: Could not determine server for tool '{namespaced_name}'"
                        artifacts = []

                    # Notify frontend about the result
                    yield ("tool_result", {
                        "name": tool_name,
                        "result": result_text,
                        "server_id": server_id,
                    })

                    # Yield any artifacts
                    for artifact in artifacts:
                        yield ("artifact", {
                            "tool_name": tool_name,
                            "server_id": server_id,
                            **artifact,
                        })

                    # Add tool result to conversation history
                    call_id = tc["id"] or f"call_{round_num}_{i}"
                    messages_array.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_text,
                    })

                # Break inner loop to start next round with updated messages
                break

            elif event_type == "done":
                yield ("done", data)
                return

            elif event_type == "error":
                yield ("error", data)
                return

        if not tool_calls_received:
            # No tool calls and no done event — shouldn't happen, but handle gracefully
            return

    # Exceeded max rounds — do one final call without tools to force a response
    logger.warning(f"Exceeded {MAX_TOOL_ROUNDS} tool call rounds, forcing final response")
    for event_type, data in stream_chat_completion(service_name, messages_array, tools=None):
        if event_type == "delta":
            yield ("delta", data)
        elif event_type == "done":
            yield ("done", data)
            return
        elif event_type == "error":
            yield ("error", data)
            return
