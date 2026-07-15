"""Filesystem-backed project files.

Each project owns a real directory tree under a machine-local storage root
(default ``<dashboard>/project_files/<project_id>/``, override with
``LLM_DOCK_PROJECT_FILES_DIR``). The filesystem is the source of truth —
there is no files table to keep in sync; the API walks the directory.

Every public function takes the project's root and *relative* paths from
the client. ``resolve()`` is the single choke point for path safety:
component validation plus a realpath containment check, so neither
``..`` traversal nor a symlink planted inside the tree can escape the
project root.
"""
import os
import shutil
import logging
import tempfile

logger = logging.getLogger(__name__)

# Uploads and (later) editor writes are capped; project files are meant as
# context material for chat, not bulk storage.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_NAME_LENGTH = 255
# Path depth cap: keeps recursive tree walks and rmtree far away from
# Python's recursion limit no matter what gets created through the API.
MAX_PATH_DEPTH = 32


def configure_max_content_length(app):
    """Give the Flask app a request-body cap keyed to the upload limit.

    Flask pre-seeds MAX_CONTENT_LENGTH with None in every app's default
    config, so setdefault() would be a no-op — assign only when it is
    still None, preserving an explicit deployment override. Werkzeug then
    enforces the cap DURING multipart parsing, covering chunked bodies
    that carry no Content-Length.
    """
    if app.config.get("MAX_CONTENT_LENGTH") is None:
        app.config["MAX_CONTENT_LENGTH"] = int(MAX_UPLOAD_BYTES * 1.05)


class ProjectFilesError(Exception):
    """Client-facing error with an HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def default_storage_root() -> str:
    configured = os.environ.get("LLM_DOCK_PROJECT_FILES_DIR")
    if configured:
        return configured
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "project_files")


def project_root(storage_root: str, project_id: str) -> str:
    """Absolute directory for one project's files (not created here).

    project_id is server-generated (uuid4), but validate it like a single
    path component anyway — defense in depth against a crafted id ever
    reaching this layer.
    """
    _validate_component(project_id)
    return os.path.join(os.path.abspath(storage_root), project_id)


def ensure_project_root(storage_root: str, project_id: str) -> str:
    root = project_root(storage_root, project_id)
    os.makedirs(root, exist_ok=True)
    return root


def delete_project_root(storage_root: str, project_id: str):
    """Remove a project's entire files directory (project deletion)."""
    root = project_root(storage_root, project_id)
    shutil.rmtree(root, ignore_errors=True)


def _validate_component(name: str):
    if not isinstance(name, str) or not name:
        raise ProjectFilesError("empty path component")
    if name in (".", ".."):
        raise ProjectFilesError("invalid path component")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ProjectFilesError("invalid character in path component")
    if len(name) > MAX_NAME_LENGTH:
        raise ProjectFilesError("path component too long")


def split_rel_path(rel_path: str) -> list:
    """Split a client-supplied relative path into validated components.

    '' resolves to the project root (zero components).
    """
    if rel_path is None:
        raise ProjectFilesError("path is required")
    if not isinstance(rel_path, str):
        raise ProjectFilesError("path must be a string")
    rel_path = rel_path.strip("/")
    if rel_path == "":
        return []
    parts = rel_path.split("/")
    if len(parts) > MAX_PATH_DEPTH:
        raise ProjectFilesError("path too deep")
    for part in parts:
        _validate_component(part)
    return parts


def resolve(root: str, rel_path: str) -> str:
    """Resolve a relative path against the project root, safely.

    Containment is checked on the realpath of the nearest EXISTING
    ancestor, so a symlink anywhere along the way that points outside the
    root is rejected even when the final path doesn't exist yet.
    """
    parts = split_rel_path(rel_path)
    abs_path = os.path.join(root, *parts) if parts else root

    probe = abs_path
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    real_root = os.path.realpath(root)
    real_probe = os.path.realpath(probe)
    if real_probe != real_root and not real_probe.startswith(real_root + os.sep):
        raise ProjectFilesError("path escapes project root", status=400)
    return abs_path


def _node(abs_path: str, rel_path: str) -> dict:
    st = os.lstat(abs_path)
    is_dir = os.path.isdir(abs_path) and not os.path.islink(abs_path)
    node = {
        "name": os.path.basename(abs_path) or "/",
        "path": rel_path,
        "type": "dir" if is_dir else "file",
    }
    if not is_dir:
        node["size"] = st.st_size
    node["modified_at"] = int(st.st_mtime)
    return node


def build_tree(root: str, rel_path: str = "") -> list:
    """Nested listing of a directory, dirs first then files, both sorted
    case-insensitively. Symlinks are listed as files and never followed
    (their content is unreachable through resolve()'s realpath check if
    they point outside the root)."""
    abs_dir = resolve(root, rel_path)
    if not os.path.isdir(abs_dir):
        raise ProjectFilesError("not a directory", status=404)
    entries = []
    for name in os.listdir(abs_dir):
        child_rel = f"{rel_path}/{name}" if rel_path else name
        child_abs = os.path.join(abs_dir, name)
        node = _node(child_abs, child_rel)
        if node["type"] == "dir":
            node["children"] = build_tree(root, child_rel)
        entries.append(node)
    entries.sort(key=lambda n: (n["type"] != "dir", n["name"].lower()))
    return entries


def stat_file(root: str, rel_path: str) -> str:
    """Resolve rel_path and require it to be an existing regular file.
    Returns the absolute path (for send_file)."""
    abs_path = resolve(root, rel_path)
    if not os.path.exists(abs_path):
        raise ProjectFilesError("file not found", status=404)
    if os.path.isdir(abs_path):
        raise ProjectFilesError("path is a directory", status=400)
    return abs_path


def save_stream(root: str, dir_rel: str, filename: str, stream, overwrite: bool = False) -> dict:
    """Write an uploaded file into dir_rel. The target directory must
    already exist (create it with mkdir first). Refuses to replace an
    existing file unless overwrite is set; never replaces a directory."""
    _validate_component(filename)
    abs_dir = resolve(root, dir_rel)
    if not os.path.isdir(abs_dir):
        raise ProjectFilesError("target directory not found", status=404)
    rel_target = f"{dir_rel.strip('/')}/{filename}" if dir_rel.strip("/") else filename
    abs_target = resolve(root, rel_target)
    if os.path.isdir(abs_target):
        raise ProjectFilesError("a directory with that name exists", status=409)
    if os.path.exists(abs_target) and not overwrite:
        raise ProjectFilesError("file already exists", status=409)

    # Stage in a UNIQUE, exclusively-created temp file in the destination
    # directory (same filesystem → atomic publication). A deterministic
    # "<target>.uploading" name would collide with a legitimate user file
    # of that name and with a concurrent upload of the same target.
    written = 0
    fd, tmp_path = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=abs_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise ProjectFilesError("file too large", status=413)
                f.write(chunk)
        if overwrite:
            os.replace(tmp_path, abs_target)
        else:
            # Atomic no-replace publication: link() fails with EEXIST if the
            # target appeared since the pre-check, upholding the 409 contract
            # even against a concurrent upload of the same name.
            try:
                os.link(tmp_path, abs_target)
            except FileExistsError:
                raise ProjectFilesError("file already exists", status=409)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return _node(abs_target, rel_target)


def mkdir(root: str, rel_path: str) -> dict:
    parts = split_rel_path(rel_path)
    if not parts:
        raise ProjectFilesError("path is required")
    abs_path = resolve(root, rel_path)
    if os.path.exists(abs_path):
        raise ProjectFilesError("path already exists", status=409)
    os.makedirs(abs_path)
    rel = "/".join(parts)
    return _node(abs_path, rel)


def move(root: str, rel_src: str, rel_dst: str) -> dict:
    """Rename/move a file or directory to a new relative path. The
    destination's parent must exist; the destination itself must not."""
    src_parts = split_rel_path(rel_src)
    dst_parts = split_rel_path(rel_dst)
    if not src_parts:
        raise ProjectFilesError("cannot move project root")
    if not dst_parts:
        raise ProjectFilesError("destination is required")
    abs_src = resolve(root, rel_src)
    abs_dst = resolve(root, rel_dst)
    if not os.path.exists(abs_src):
        raise ProjectFilesError("source not found", status=404)
    if os.path.exists(abs_dst):
        raise ProjectFilesError("destination already exists", status=409)
    if dst_parts[:len(src_parts)] == src_parts:
        raise ProjectFilesError("cannot move a directory into itself")
    if not os.path.isdir(os.path.dirname(abs_dst)):
        raise ProjectFilesError("destination directory not found", status=404)
    shutil.move(abs_src, abs_dst)
    return _node(abs_dst, "/".join(dst_parts))


def delete(root: str, rel_path: str):
    parts = split_rel_path(rel_path)
    if not parts:
        raise ProjectFilesError("cannot delete project root")
    abs_path = resolve(root, rel_path)
    if not os.path.exists(abs_path) and not os.path.islink(abs_path):
        raise ProjectFilesError("path not found", status=404)
    if os.path.isdir(abs_path) and not os.path.islink(abs_path):
        shutil.rmtree(abs_path)
    else:
        os.unlink(abs_path)
