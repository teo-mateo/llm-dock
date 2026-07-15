"""Glue between chat runs and the built-in project-files MCP server.

The project-files server is spawned per tool call like every other
built-in, but it is *scoped*: it must know which project's directory the
current conversation belongs to. That scope travels as an environment
variable injected into the subprocess at spawn time — the model never
sees or supplies a project id.

Kept import-light on purpose: the server script
(`mcp_servers/project_files_server.py`) imports the constants from here,
and it runs outside Flask.
"""

SERVER_ID = "project-files"

# Absolute path of the conversation's project directory, injected into the
# server subprocess. Absent (e.g. the server was manually enabled on a
# conversation that belongs to no project) every tool answers with a clear
# error instead of guessing a directory.
PROJECT_ROOT_ENV = "LLM_DOCK_PROJECT_ROOT"


def with_project_files(enabled_servers: list) -> list:
    """Effective server list for a project conversation: project-files is
    always on — membership in a project IS the toggle."""
    if SERVER_ID in enabled_servers:
        return list(enabled_servers)
    return [*enabled_servers, SERVER_ID]


class ProjectScopedMCPManager:
    """Delegating wrapper around MCPClientManager that injects the
    conversation's project root into project-files server spawns.

    Built per run (in routes, where the conversation is known) so the same
    process-wide manager — and its tool cache — serves every conversation;
    only the spawn environment differs.
    """

    def __init__(self, inner, project_root: str):
        self._inner = inner
        self._project_root = project_root

    def get_tools(self, server_id: str) -> list:
        return self._inner.get_tools(server_id)

    def get_all_tools(self, server_ids: list) -> list:
        return self._inner.get_all_tools(server_ids)

    def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> tuple:
        extra_env = None
        if server_id == SERVER_ID:
            extra_env = {PROJECT_ROOT_ENV: self._project_root}
        return self._inner.call_tool(server_id, tool_name, arguments, extra_env=extra_env)
