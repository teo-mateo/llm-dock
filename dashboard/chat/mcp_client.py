"""MCP Client Manager — spawns MCP servers and executes tools."""

import asyncio
import json
import logging
import threading
from typing import Optional

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import ClientSession

from .mcp_registry import get_server_config

logger = logging.getLogger(__name__)


def _tool_to_openai_format(server_id: str, tool) -> dict:
    """Convert an MCP tool to OpenAI-compatible function format."""
    return {
        "type": "function",
        "function": {
            "name": f"{server_id}__{tool.name}",
            "description": tool.description or "",
            "parameters": tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}},
        },
    }


def parse_tool_name(namespaced_name: str) -> tuple:
    """Parse 'server_id__tool_name' into (server_id, tool_name)."""
    parts = namespaced_name.split("__", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, namespaced_name


class MCPClientManager:
    """Manages MCP server connections and tool execution.

    Since MCP uses async and Flask is sync, all async operations
    are run in a dedicated event loop on a background thread.
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._tools_cache = {}  # server_id -> [openai tool dicts]

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro):
        """Run an async coroutine from sync code."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    def get_tools(self, server_id: str) -> list:
        """Get tools for a server in OpenAI format. Uses cache."""
        if server_id in self._tools_cache:
            return self._tools_cache[server_id]

        config = get_server_config(server_id)
        if not config:
            logger.warning(f"Unknown MCP server: {server_id}")
            return []

        try:
            tools = self._run_async(self._discover_tools(config, server_id))
            self._tools_cache[server_id] = tools
            logger.info(f"Discovered {len(tools)} tools from {server_id}")
            return tools
        except Exception:
            logger.exception(f"Failed to discover tools from {server_id}")
            return []

    def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> tuple:
        """Execute a tool on an MCP server. Returns (result_text, artifacts)."""
        config = get_server_config(server_id)
        if not config:
            return (f"Error: Unknown MCP server '{server_id}'", [])

        try:
            return self._run_async(self._execute_tool(config, tool_name, arguments))
        except Exception as e:
            logger.exception(f"Failed to call tool {tool_name} on {server_id}")
            return (f"Error executing tool: {str(e)}", [])

    def get_all_tools(self, server_ids: list) -> list:
        """Get tools from multiple servers, combined."""
        all_tools = []
        for sid in server_ids:
            all_tools.extend(self.get_tools(sid))
        return all_tools

    def invalidate_cache(self, server_id: str = None):
        """Clear tool cache."""
        if server_id:
            self._tools_cache.pop(server_id, None)
        else:
            self._tools_cache.clear()

    async def _discover_tools(self, config: dict, server_id: str) -> list:
        """Connect to server, list tools, disconnect."""
        params = StdioServerParameters(
            command=config["command"][0],
            args=config["command"][1:],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_tool_to_openai_format(server_id, t) for t in result.tools]

    async def _execute_tool(self, config: dict, tool_name: str, arguments: dict) -> tuple:
        """Connect to server, call tool, return (result_text, artifacts)."""
        params = StdioServerParameters(
            command=config["command"][0],
            args=config["command"][1:],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                parts = []
                for block in result.content:
                    if hasattr(block, 'text'):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                text = "\n".join(parts) if parts else "No result"

                # Detect artifact convention: JSON with "artifact": true
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and parsed.get("artifact"):
                        artifact = {
                            "type": parsed["type"],
                            "title": parsed.get("title"),
                            "content": parsed["content"],
                            "language": parsed.get("language"),
                        }
                        description = parsed.get("description", f"Generated {parsed['type']} artifact")
                        return (description, [artifact])
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

                return (text, [])
