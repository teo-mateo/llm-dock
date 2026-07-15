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
import errno
import hashlib
import os
import stat as stat_mod
import shutil
import logging
import tempfile
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Uploads and (later) editor writes are capped; project files are meant as
# context material for chat, not bulk storage.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_NAME_LENGTH = 255
# Path depth cap: keeps recursive tree walks and rmtree far away from
# Python's recursion limit no matter what gets created through the API.
MAX_PATH_DEPTH = 32
# Editor cap — the in-browser editor is for notes/configs/snippets, not
# for logs; a textarea with more than this is unusable anyway.
MAX_TEXT_EDIT_BYTES = 2 * 1024 * 1024  # 2 MB


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
    """Client-facing error with an HTTP status.

    `code` is a stable machine-readable identifier for conditions the
    frontend must branch on (conflict bars, overwrite prompts) — clients
    match on it, never on the human-readable message, so wording can
    change freely. Only conditions with a UI behavior get a code.
    """

    def __init__(self, message: str, status: int = 400, code: str = None):
        super().__init__(message)
        self.status = status
        self.code = code


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


def delete_project_root(storage_root: str, project_id: str, strict: bool = False):
    """Remove a project's entire files directory (project deletion).

    strict=True propagates cleanup failures (used BEFORE the DB row is
    deleted, so a permissions/IO error surfaces as a retryable 500
    instead of silently orphaning data). The default best-effort mode is
    for post-delete sweeps where the row is already gone — failures are
    logged, never raised.
    """
    root = project_root(storage_root, project_id)
    if strict:
        try:
            shutil.rmtree(root)
        except FileNotFoundError:
            pass
        return
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("best-effort cleanup of project files failed: %s", root)


@contextmanager
def _fs_errors():
    """Translate filesystem rejections of otherwise-validated paths into
    client errors. A component can pass the 255-CHARACTER check yet exceed
    the filesystem's 255-BYTE limit (multibyte names → ENAMETOOLONG), the
    total path can exceed PATH_MAX, or an intermediate component can turn
    out to be a regular file (ENOTDIR). All are bad input, not server
    faults."""
    try:
        yield
    except OSError as e:
        if e.errno == errno.ENAMETOOLONG:
            raise ProjectFilesError("name or path too long for the filesystem")
        if e.errno == errno.ENOTDIR:
            raise ProjectFilesError("a path component is not a directory")
        raise


def _validate_component(name: str):
    if not isinstance(name, str) or not name:
        raise ProjectFilesError("empty path component")
    if name in (".", ".."):
        raise ProjectFilesError("invalid path component")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ProjectFilesError("invalid character in path component")
    # Filesystems cap components at 255 BYTES, not characters — a name of
    # 100 emoji passes a character check and still fails at the syscall.
    # JSON happily delivers lone surrogates ("\ud800"), which are not
    # UTF-8-encodable at all — that's bad input, not a server fault.
    try:
        encoded = name.encode("utf-8")
    except UnicodeEncodeError:
        raise ProjectFilesError("path component is not valid unicode")
    if len(encoded) > MAX_NAME_LENGTH:
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
    """Resolve rel_path and require it to be an existing REGULAR file
    (lstat: symlinks are never followed, matching the tree contract, and
    FIFOs/sockets/devices are rejected rather than handed to send_file —
    opening a FIFO would block the worker indefinitely). Returns the
    absolute path (for send_file)."""
    abs_path = resolve(root, rel_path)
    try:
        st = os.lstat(abs_path)
    except FileNotFoundError:
        raise ProjectFilesError("file not found", status=404)
    if stat_mod.S_ISDIR(st.st_mode):
        raise ProjectFilesError("path is a directory", status=400)
    if not stat_mod.S_ISREG(st.st_mode):
        raise ProjectFilesError("not a regular file", status=400)
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
        raise ProjectFilesError("file already exists", status=409, code="already_exists")
    # Same permission fidelity as write_text: mkstemp stages at 0600, so an
    # overwriting upload must keep the target's mode and a fresh one gets
    # a normal default instead of 0600.
    publish_mode = 0o644
    if overwrite and os.path.lexists(abs_target):
        target_st = os.lstat(abs_target)
        if stat_mod.S_ISREG(target_st.st_mode):
            publish_mode = stat_mod.S_IMODE(target_st.st_mode)

    # Stage in a UNIQUE, exclusively-created temp file in the destination
    # directory (same filesystem → atomic publication). A deterministic
    # "<target>.uploading" name would collide with a legitimate user file
    # of that name and with a concurrent upload of the same target.
    written = 0
    with _fs_errors():
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
            os.chmod(tmp_path, publish_mode)
            if overwrite:
                os.replace(tmp_path, abs_target)
            else:
                # Atomic no-replace publication: link() fails with EEXIST if the
                # target appeared since the pre-check, upholding the 409 contract
                # even against a concurrent upload of the same name.
                try:
                    os.link(tmp_path, abs_target)
                except FileExistsError:
                    raise ProjectFilesError("file already exists", status=409, code="already_exists")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    return _node(abs_target, rel_target)


def _content_revision(data: bytes) -> str:
    """Opaque optimistic-concurrency token for the editor. Content-based:
    mtime — even at nanosecond precision — is unreliable, because Linux
    timestamps consecutive writes within one kernel timer tick
    identically. A hash only matches when the bytes actually match."""
    return hashlib.sha256(data).hexdigest()[:16]


def read_text(root: str, rel_path: str) -> dict:
    """Read a regular file as UTF-8 text for the editor. Rejects
    non-regular files (via stat_file), oversized files, and binary
    content (NUL byte or invalid UTF-8)."""
    abs_path = stat_file(root, rel_path)
    st = os.lstat(abs_path)
    if st.st_size > MAX_TEXT_EDIT_BYTES:
        raise ProjectFilesError("file too large to edit", status=413)
    with open(abs_path, "rb") as f:
        data = f.read()
    if b"\x00" in data:
        raise ProjectFilesError("not a text file", status=400)
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ProjectFilesError("not a text file (not valid UTF-8)", status=400)
    return {
        "path": "/".join(split_rel_path(rel_path)),
        "content": content,
        "size": st.st_size,
        "modified_at": int(st.st_mtime),
        "revision": _content_revision(data),
    }


def write_text(root: str, rel_path: str, content: str,
               base_revision: str = None, create_only: bool = False) -> dict:
    """Write UTF-8 text to a file (create or overwrite), atomically via a
    temp file in the same directory. The target's parent must exist and
    the target itself must be absent or a regular file — symlinks and
    special files are never written through or replaced.

    base_revision (optional) is the opaque revision the client loaded
    (read_text's ``revision``, a content hash): if the file's bytes
    changed on disk since, the save is rejected with 409 so an edit from
    another tab/editor isn't silently overwritten.

    create_only=True is the new-file precondition: the save is rejected
    with 409 if the path already exists (the client believed it was
    creating a file, but its tree snapshot was stale). Publication is an
    atomic no-replace link, mirroring save_stream's upload contract.
    """
    parts = split_rel_path(rel_path)
    if not parts:
        raise ProjectFilesError("path is required")
    if not isinstance(content, str):
        raise ProjectFilesError("content must be a string")
    if "\x00" in content:
        # read_text treats NUL as binary; accepting it here would create a
        # file this editor then refuses to reopen.
        raise ProjectFilesError("content must not contain NUL bytes")
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError:
        raise ProjectFilesError("content is not valid unicode")
    if len(encoded) > MAX_TEXT_EDIT_BYTES:
        raise ProjectFilesError("content too large", status=413)

    abs_path = resolve(root, rel_path)
    abs_dir = os.path.dirname(abs_path)
    if not os.path.isdir(abs_dir):
        raise ProjectFilesError("parent directory not found", status=404)
    # mkstemp stages at 0600; without this an edit would silently strip the
    # target's permission bits (e.g. a 0755 script losing its exec bit).
    publish_mode = 0o644
    if os.path.lexists(abs_path):
        if create_only:
            raise ProjectFilesError("file already exists", status=409, code="already_exists")
        st = os.lstat(abs_path)
        if not stat_mod.S_ISREG(st.st_mode):
            raise ProjectFilesError("not a regular file", status=409)
        publish_mode = stat_mod.S_IMODE(st.st_mode)
        if base_revision is not None:
            # A file too large for read_text can't be what the client
            # loaded — it definitely changed. Otherwise compare content.
            if st.st_size > MAX_TEXT_EDIT_BYTES:
                raise ProjectFilesError("file changed on disk since it was loaded", status=409, code="revision_conflict")
            with open(abs_path, "rb") as f:
                current = f.read()
            if _content_revision(current) != base_revision:
                raise ProjectFilesError("file changed on disk since it was loaded", status=409, code="revision_conflict")
    elif base_revision is not None:
        # Client edited a file that has since been deleted/renamed.
        raise ProjectFilesError("file changed on disk since it was loaded", status=409, code="revision_conflict")

    with _fs_errors():
        fd, tmp_path = tempfile.mkstemp(prefix=".edit-", suffix=".tmp", dir=abs_dir)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encoded)
            os.chmod(tmp_path, publish_mode)
            if create_only:
                # Atomic no-replace publication, same as upload's contract.
                try:
                    os.link(tmp_path, abs_path)
                except FileExistsError:
                    raise ProjectFilesError("file already exists", status=409, code="already_exists")
            else:
                os.replace(tmp_path, abs_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    node = _node(abs_path, "/".join(parts))
    node["revision"] = _content_revision(encoded)
    return node


def mkdir(root: str, rel_path: str) -> dict:
    parts = split_rel_path(rel_path)
    if not parts:
        raise ProjectFilesError("path is required")
    abs_path = resolve(root, rel_path)
    # lexists: a dangling symlink is an ordinary entry in the tree (listed
    # by build_tree) and must count as occupying its name — exists() would
    # follow the link and report the slot free.
    if os.path.lexists(abs_path):
        raise ProjectFilesError("path already exists", status=409, code="already_exists")
    with _fs_errors():
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
    # lexists on both sides: a dangling symlink is movable (the operation
    # applies to the link itself, as delete already does) and occupies its
    # destination name.
    if not os.path.lexists(abs_src):
        raise ProjectFilesError("source not found", status=404)
    if os.path.lexists(abs_dst):
        raise ProjectFilesError("destination already exists", status=409, code="already_exists")
    if dst_parts[:len(src_parts)] == src_parts:
        raise ProjectFilesError("cannot move a directory into itself")
    if not os.path.isdir(os.path.dirname(abs_dst)):
        raise ProjectFilesError("destination directory not found", status=404)
    with _fs_errors():
        shutil.move(abs_src, abs_dst)
    return _node(abs_dst, "/".join(dst_parts))


def _precheck_copy_tree(abs_src: str, dst_depth: int):
    """Pre-scan a directory before copytree: reject special files (opening
    a FIFO to copy it would block the worker forever) and enforce the path
    depth cap at the DESTINATION — the source obeys it relative to its own
    location, but copying deep subtree into an already-deep folder could
    mint paths build_tree/rmtree would then have to recurse past."""
    for dirpath, dirnames, filenames in os.walk(abs_src):
        rel_depth = 0 if dirpath == abs_src else len(os.path.relpath(dirpath, abs_src).split(os.sep))
        child_depth = dst_depth + rel_depth + 1
        if child_depth > MAX_PATH_DEPTH and (dirnames or filenames):
            raise ProjectFilesError("copy would exceed maximum path depth")
        for name in filenames:
            st = os.lstat(os.path.join(dirpath, name))
            if not (stat_mod.S_ISREG(st.st_mode) or stat_mod.S_ISLNK(st.st_mode)):
                raise ProjectFilesError("directory contains a special file that cannot be copied")


def copy_path(root: str, rel_src: str, rel_dst: str) -> dict:
    """Copy a file, symlink, or directory tree to a new relative path.
    Same contract as move: the destination's parent must exist and the
    destination itself must not. Symlinks are copied as links, never
    followed (matching the tree/delete contract — a link pointing outside
    the root must not smuggle its target's content into the project)."""
    src_parts = split_rel_path(rel_src)
    dst_parts = split_rel_path(rel_dst)
    if not src_parts:
        raise ProjectFilesError("cannot copy project root")
    if not dst_parts:
        raise ProjectFilesError("destination is required")
    abs_src = resolve(root, rel_src)
    abs_dst = resolve(root, rel_dst)
    if not os.path.lexists(abs_src):
        raise ProjectFilesError("source not found", status=404)
    if os.path.lexists(abs_dst):
        raise ProjectFilesError("destination already exists", status=409, code="already_exists")
    if dst_parts[:len(src_parts)] == src_parts:
        raise ProjectFilesError("cannot copy a directory into itself")
    abs_dst_dir = os.path.dirname(abs_dst)
    if not os.path.isdir(abs_dst_dir):
        raise ProjectFilesError("destination directory not found", status=404)

    src_st = os.lstat(abs_src)
    with _fs_errors():
        if stat_mod.S_ISDIR(src_st.st_mode):
            # The component-prefix check above only sees CLIENT paths; an
            # in-root symlink alias (alias -> d) would let "d" ->
            # "alias/copy" physically target d/copy and send copytree
            # into its own output. Compare physical paths: the real
            # destination is its existing parent's realpath plus the
            # final component.
            real_src = os.path.realpath(abs_src)
            real_dst = os.path.join(os.path.realpath(abs_dst_dir), os.path.basename(abs_dst))
            if real_dst == real_src or real_dst.startswith(real_src + os.sep):
                raise ProjectFilesError("cannot copy a directory into itself")
            _precheck_copy_tree(abs_src, len(dst_parts))
            try:
                shutil.copytree(abs_src, abs_dst, symlinks=True)
            except FileExistsError:
                raise ProjectFilesError("destination already exists", status=409, code="already_exists")
            except Exception:
                # A partial tree is worse than no tree: the client will
                # retry the whole copy, and a half-populated destination
                # would then 409 as already_exists.
                shutil.rmtree(abs_dst, ignore_errors=True)
                raise
        elif stat_mod.S_ISLNK(src_st.st_mode):
            try:
                os.symlink(os.readlink(abs_src), abs_dst)
            except FileExistsError:
                raise ProjectFilesError("destination already exists", status=409, code="already_exists")
        elif stat_mod.S_ISREG(src_st.st_mode):
            # Stage in the destination directory, then publish with an
            # atomic no-replace link — same 409 contract as save_stream
            # even against a concurrent claim of the destination name.
            fd, tmp_path = tempfile.mkstemp(prefix=".copy-", suffix=".tmp", dir=abs_dst_dir)
            try:
                os.close(fd)
                shutil.copy2(abs_src, tmp_path)  # preserves mode
                try:
                    os.link(tmp_path, abs_dst)
                except FileExistsError:
                    raise ProjectFilesError("destination already exists", status=409, code="already_exists")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        else:
            raise ProjectFilesError("not a copyable file type")
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
