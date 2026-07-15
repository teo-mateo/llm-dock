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
# Tool output feeds straight into the model context; a big-but-legitimate
# project must degrade into an explicit truncation notice, not a
# context-blowing (or 30s-timeout-hitting) response.
MAX_LIST_ENTRIES = 500
MAX_SEARCH_SCAN_BYTES = 64 * 1024 * 1024
MAX_READ_CHARS = 64 * 1024

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
    if len(lines) > MAX_LIST_ENTRIES:
        total = len(lines)
        lines = lines[:MAX_LIST_ENTRIES]
        lines.append(
            f"(truncated at {MAX_LIST_ENTRIES} of {total} entries — "
            f"pass a subdirectory path to list less)"
        )
    return "\n".join(lines)


@mcp.tool()
def read_file(path: str, offset: int = 0) -> str:
    """Read a text file from the project (UTF-8, up to 2 MB).

    path is relative to the project root, e.g. 'docs/plan.md'. At most
    ~64k characters are returned per call; a longer file ends with a
    notice giving the offset to pass to read the next chunk. Binary
    files and files over the size cap are rejected — use list_files to
    check sizes first.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not os.path.isdir(root):
        return "Error: file not found (the project has no files yet)"
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return "Error: offset must be a non-negative integer"
    try:
        content = pf.read_text(root, path)["content"]
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    if offset > 0 and offset >= len(content):
        return f"Error: offset {offset} is past the end of the file ({len(content)} characters)"
    chunk = content[offset:offset + MAX_READ_CHARS]
    end = offset + len(chunk)
    if end < len(content):
        chunk += (
            f"\n(truncated: showing characters {offset}–{end} of {len(content)} — "
            f"call read_file again with offset={end} to continue)"
        )
    return chunk


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
    scan_capped = False
    scanned_bytes = 0
    for node in _flatten(tree):
        if needle in node["name"].lower():
            suffix = "/" if node["type"] == "dir" else ""
            matches.append(f"{node['path']}{suffix} (name match)")
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                break
        if node["type"] != "file":
            continue
        # Total read budget: a no-match query over a big-but-legitimate
        # project must stop scanning instead of grinding past the MCP
        # call timeout. Only count files read_text will actually accept.
        size = node.get("size", 0)
        if size > pf.MAX_TEXT_EDIT_BYTES:
            continue  # read_text would reject it anyway — skip the call
        if scanned_bytes + size > MAX_SEARCH_SCAN_BYTES:
            scan_capped = True
            break
        scanned_bytes += size
        try:
            content = pf.read_text(root, node["path"])["content"]
        except pf.ProjectFilesError:
            continue  # binary or a symlink — not searchable
        for lineno, line in enumerate(content.splitlines(), start=1):
            if needle in line.lower():
                matches.append(
                    f"{node['path']}:{lineno}: {line.strip()[:MAX_MATCH_LINE_CHARS]}"
                )
                if len(matches) >= MAX_SEARCH_RESULTS:
                    truncated = True
                    break
        if truncated:
            break

    if not matches:
        result = "No matches."
    else:
        result = "\n".join(matches)
    if truncated:
        result += f"\n(truncated at {MAX_SEARCH_RESULTS} matches — refine the query)"
    if scan_capped:
        result += (
            f"\n(search stopped early: {MAX_SEARCH_SCAN_BYTES // (1024 * 1024)} MB "
            f"scan budget reached — narrow the search with a subdirectory path)"
        )
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
