"""E2E check of stream_with_tools with the REAL MCP manager + project-files
server: a mocked model yields a tool_calls event, the tool executes, and
progress notifications must surface as tool_progress events in the stream."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chat.tool_loop as tool_loop
from chat.mcp_client import MCPClientManager
from chat.project_files_mcp import ProjectScopedMCPManager


def _model_stream(service_name, messages_array, tools=None, tool_choice=None):
    content = "line one\n" + "x" * 200000 + "\ntail"
    args_json = json.dumps({"path": "sub/out.txt", "content": content})
    yield ("tool_calls", {"tool_calls": [
        {"id": "call_0", "function": {"name": "project-files__write_file", "arguments": args_json}},
    ]})


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sub").mkdir()
        (root / "sub" / "out.txt").write_text("", encoding="utf-8")
        inner = MCPClientManager()
        scoped = ProjectScopedMCPManager(inner, str(root))

        # This is what runtime._build_stream passes: it publishes to the bus.
        seen = []

        async def progress_callback(progress, total, message, tool_name):
            seen.append({"tool_name": tool_name, "message": message})

        tool_loop.stream_chat_completion = _model_stream
        # Stop after the first round so we don't loop forever.
        events = []
        for t, d in tool_loop.stream_with_tools(
            "svc", [{"role": "user", "content": "write it"}],
            tools=[{"type": "function"}], mcp_manager=scoped,
            progress_callback=progress_callback,
        ):
            events.append((t, d))
            if t == "tool_result":
                break

        # Direct comparison: replicate stream_with_tools' closure-in-loop
        # pattern EXACTLY, passed straight to scoped.call_tool.
        seen_direct = []

        async def direct_cb(progress, total, message, tool_name):
            seen_direct.append({"tool_name": tool_name, "message": message})

        for tool_name in ["write_file"]:
            async def _progress(progress, total, message, _tool_name=tool_name):
                if direct_cb:
                    await direct_cb(progress, total, message, _tool_name)
            scoped.call_tool("project-files", tool_name,
                             {"path": "sub/out.txt", "content": "abc" * 30000},
                             progress_callback=_progress)

        print("=== event sequence (first round) ===")
        for t, d in events:
            if t in ("tool_call", "tool_result"):
                print(f"  {t}: name={d['name']}")
            else:
                print(f"  {t}: {d}")

        types = [t for t, _ in events]
        assert "tool_call" in types, "no tool_call event"
        assert "tool_result" in types, "no tool_result event"
        print(f"\nstream_with_tools path: progress_callback invoked {len(seen)}x")
        print(f"direct scoped.call_tool path: progress_callback invoked {len(seen_direct)}x")
        assert len(seen_direct) > 0, "direct path also failed!"
        assert len(seen) > 0, "stream_with_tools path dropped progress — BUG"
        print("PASS: both paths deliver progress")


if __name__ == "__main__":
    main()
