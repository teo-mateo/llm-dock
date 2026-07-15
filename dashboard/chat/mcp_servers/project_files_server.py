"""Project Files MCP server — read/write access to one project's file area.

Spawned per tool call by MCPClientManager like the other built-ins, but
scoped: the dashboard injects LLM_DOCK_PROJECT_ROOT (the absolute
directory of the conversation's project) into the subprocess environment
at spawn time (see chat/project_files_mcp.py). Without it, every tool
answers with a clear error instead of guessing a directory.

Read tools: list_files, read_file, search_files. Write tools:
create_file, write_file (full replace), edit_file (exact-snippet
replace), insert_text (line-based insert). Writes go through
chat.project_files.write_text — atomic temp-file publication, UTF-8/NUL
validation, the 2 MB text cap, and (for the read-modify-write tools) the
content-revision guard, so a concurrent editor save turns into a clear
error instead of a silent overwrite.

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


def _ensure_parent(root: str, path: str):
    """Create the missing parent folders of `path` (resolve-safe).

    Raises ProjectFilesError for invalid paths or when a parent component
    exists but is not a directory.
    """
    parts = pf.split_rel_path(path)
    if not parts:
        raise pf.ProjectFilesError("path is required")
    parent = "/".join(parts[:-1])
    if not parent:
        return
    abs_parent = pf.resolve(root, parent)
    if os.path.isdir(abs_parent):
        return
    if os.path.lexists(abs_parent):
        raise pf.ProjectFilesError("parent path exists and is not a directory")
    pf.mkdir(root, parent)


@mcp.tool()
def create_file(path: str, content: str = "") -> str:
    """Create a new text file in the project (UTF-8, up to 2 MB).

    path is relative to the project root, e.g. 'docs/plan.md'; missing
    parent folders are created automatically. Fails if the file already
    exists — use write_file to replace an existing file's content, or
    edit_file / insert_text for targeted changes.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not isinstance(content, str):
        return "Error: content must be a string"
    try:
        # The project directory itself is created lazily by the first
        # mutation, mirroring the HTTP upload/write routes.
        os.makedirs(root, exist_ok=True)
        _ensure_parent(root, path)
        node = pf.write_text(root, path, content, create_only=True)
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    return f"Created {node['path']} ({node['size']} bytes)"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Replace an existing project text file's ENTIRE content (UTF-8, up to 2 MB).

    Fails if the file does not exist — use create_file for new files.
    For small changes prefer edit_file or insert_text, which modify only
    part of the file and guard against concurrent edits.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not isinstance(content, str):
        return "Error: content must be a string"
    if not os.path.isdir(root):
        return "Error: file not found (the project has no files yet) — use create_file"
    try:
        pf.stat_file(root, path)  # must already exist as a regular file
        node = pf.write_text(root, path, content)
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    return f"Wrote {node['path']} ({node['size']} bytes)"


@mcp.tool()
def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """Replace an exact text snippet inside a project text file.

    old_text must match the file's content exactly — same whitespace,
    same line breaks — so call read_file first and copy the text
    verbatim. Unless replace_all is true, old_text must occur exactly
    once; include a few surrounding lines to make it unique. new_text
    may be empty to delete the snippet.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not isinstance(old_text, str) or old_text == "":
        return "Error: old_text must be a non-empty string"
    if not isinstance(new_text, str):
        return "Error: new_text must be a string"
    if not os.path.isdir(root):
        return "Error: file not found (the project has no files yet)"
    try:
        doc = pf.read_text(root, path)
        count = doc["content"].count(old_text)
        if count == 0:
            return ("Error: old_text was not found in the file — call read_file "
                    "and copy the exact text, including whitespace and line breaks")
        if count > 1 and not replace_all:
            return (f"Error: old_text occurs {count} times — include more "
                    f"surrounding context to make it unique, or pass replace_all=true")
        updated = doc["content"].replace(old_text, new_text)
        # base_revision: if the file changed on disk between our read and
        # this write (e.g. the user saved the in-browser editor), fail
        # loudly instead of silently reverting their edit.
        node = pf.write_text(root, path, updated, base_revision=doc["revision"])
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    return f"Replaced {count} occurrence{'s' if count != 1 else ''} in {node['path']} ({node['size']} bytes)"


@mcp.tool()
def insert_text(path: str, line: int, text: str) -> str:
    """Insert text into a project text file after a given line.

    line is 1-based and refers to the line the text is inserted AFTER;
    pass 0 to insert at the very top of the file. text is inserted as
    whole lines (a trailing newline is added if missing). Use read_file
    to find the right line number first.
    """
    root = _project_root()
    if root is None:
        return NO_PROJECT_ERROR
    if not isinstance(line, int) or isinstance(line, bool) or line < 0:
        return "Error: line must be a non-negative integer (0 inserts at the top)"
    if not isinstance(text, str) or text == "":
        return "Error: text must be a non-empty string"
    if not os.path.isdir(root):
        return "Error: file not found (the project has no files yet)"
    try:
        doc = pf.read_text(root, path)
        lines = doc["content"].splitlines(keepends=True)
        if line > len(lines):
            return f"Error: line {line} is past the end of the file ({len(lines)} lines)"
        # Appending after a final line that lacks its newline must not
        # glue the two lines together.
        if line == len(lines) and lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.insert(line, text if text.endswith("\n") else text + "\n")
        node = pf.write_text(root, path, "".join(lines), base_revision=doc["revision"])
    except pf.ProjectFilesError as e:
        return f"Error: {e}"
    return f"Inserted after line {line} of {node['path']} ({node['size']} bytes)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
