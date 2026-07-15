"""Project Files MCP server — read-only view of one project's file area.

Spawned per tool call by MCPClientManager like the other built-ins, but
scoped: the dashboard injects LLM_DOCK_PROJECT_ROOT (the absolute
directory of the conversation's project) into the subprocess environment
at spawn time (see chat/project_files_mcp.py). Without it, every tool
answers with a clear error instead of guessing a directory.

All path handling is delegated to chat.project_files — the same layer the
HTTP file routes use — so `..` traversal, absolute paths and symlink
escapes are rejected here exactly as they are in the UI.
"""
import os
import sys

# Runs as a bare script, not a package member; make the dashboard
# directory importable so `chat.project_files` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from chat import project_files as pf  # noqa: E402
from chat.project_files_mcp import PROJECT_ROOT_ENV  # noqa: E402

mcp = FastMCP("project-files")

MAX_SEARCH_RESULTS = 200
MAX_MATCH_LINE_CHARS = 200

NO_PROJECT_ERROR = (
    "Error: this conversation is not part of a project, so there are no "
    "project files to access."
)


def _project_root():
    """The scoped project directory, or None when unscoped."""
    return os.environ.get(PROJECT_ROOT_ENV) or None


def _flatten(nodes: list) -> list:
    """Depth-first (path, node) pairs over a build_tree() result."""
    out = []
    for node in nodes:
        out.append(node)
        if node["type"] == "dir":
            out.extend(_flatten(node.get("children", [])))
    return out


@mcp.tool()
def list_files(path: str = "") -> str:
    """List the project's files and folders.

    Optionally pass a directory path (relative to the project root) to
    list only that subtree. Returns one entry per line: directories end
    with '/', files show their size. Use the printed paths verbatim with
    read_file / search_files.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not os.path.isdir(root):
        return "(the project has no files yet)"
    try:
        tree = pf.build_tree(root, path)
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    lines = []
    for node in _flatten(tree):
        if node["type"] == "dir":
            lines.append(f"{node['path']}/")
        else:
            lines.append(f"{node['path']} ({node['size']} bytes)")
    if not lines:
        return "(no files here)"
    return "\n".join(lines)


@mcp.tool()
def read_file(path: str) -> str:
    """Read a text file from the project (UTF-8, up to 2 MB).

    path is relative to the project root, e.g. 'docs/plan.md'. Binary
    files and files over the size cap are rejected — use list_files to
    check sizes first.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not os.path.isdir(root):
        return "Error: file not found (the project has no files yet)"
    try:
        return pf.read_text(root, path)["content"]
    except pf.ProjectFilesError as e:
        return f"Error: {e}"


@mcp.tool()
def search_files(query: str, path: str = "") -> str:
    """Search the project's files for a substring (case-insensitive).

    Matches file names and the contents of text files (binary and
    oversized files are skipped). Optionally restrict the search to a
    subdirectory via path. Content matches are returned as
    'path:line_number: line text'.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not isinstance(query, str) or not query.strip():
        return "Error: query must be a non-empty string"
    if not os.path.isdir(root):
        return "No matches (the project has no files yet)."
    try:
        tree = pf.build_tree(root, path)
    except pf.ProjectFilesError as e:
        return f"Error: {e}"

    needle = query.lower()
    matches = []
    truncated = False
    for node in _flatten(tree):
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        if needle in node["name"].lower():
            suffix = "/" if node["type"] == "dir" else ""
            matches.append(f"{node['path']}{suffix} (name match)")
        if node["type"] != "file":
            continue
        try:
            content = pf.read_text(root, node["path"])["content"]
        except pf.ProjectFilesError:
            continue  # binary, oversized, or a symlink — not searchable
        for lineno, line in enumerate(content.splitlines(), start=1):
            if needle in line.lower():
                matches.append(
                    f"{node['path']}:{lineno}: {line.strip()[:MAX_MATCH_LINE_CHARS]}"
                )
                if len(matches) >= MAX_SEARCH_RESULTS:
                    truncated = True
                    break

    if not matches:
        return "No matches."
    result = "\n".join(matches)
    if truncated:
        result += f"\n(truncated at {MAX_SEARCH_RESULTS} matches — refine the query)"
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
