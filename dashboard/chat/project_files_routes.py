"""HTTP surface for project files, registered onto chat_bp.

Imported at the bottom of chat/routes.py (same pattern as
mcp_admin_routes) so the routes attach before the blueprint is
registered on the app.
"""
import logging
import os

from flask import jsonify, request, current_app, send_file

from auth import require_auth
from . import project_files as pf
from .routes import chat_bp, _get_db

logger = logging.getLogger(__name__)


def _storage_root() -> str:
    return current_app.config.get("PROJECT_FILES_DIR") or pf.default_storage_root()


def _project_root_or_404(project_id, create=False):
    """Returns (root, error_response). The project must exist in the DB.

    Only MUTATING routes pass create=True — read-only routes must never
    (re)create the directory, or a GET racing a project delete would leave
    an orphan directory behind.
    """
    if _get_db().get_project(project_id) is None:
        return None, (jsonify({"error": "Project not found"}), 404)
    if create:
        root = pf.ensure_project_root(_storage_root(), project_id)
    else:
        root = pf.project_root(_storage_root(), project_id)
    return root, None


def _revalidate_or_cleanup(project_id):
    """Commit-point check for mutating routes: if the project row vanished
    while the file operation ran (concurrent project delete — its rmtree
    may have run before our write recreated paths), remove the project's
    directory again and report 404. Whichever side acts last cleans up, so
    no orphan directory survives the race in either interleaving.
    """
    if _get_db().get_project(project_id) is None:
        pf.delete_project_root(_storage_root(), project_id)
        return jsonify({"error": "Project not found"}), 404
    return None


@chat_bp.errorhandler(pf.ProjectFilesError)
def _handle_pf_error(e):
    return jsonify({"error": str(e)}), e.status


@chat_bp.route("/api/chat/projects/<project_id>/files", methods=["GET"])
@require_auth
def project_files_tree(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    # Directory is created lazily by the first mutating operation; before
    # that, the project simply has no files.
    if not os.path.isdir(root):
        return jsonify({"tree": []})
    return jsonify({"tree": pf.build_tree(root)})


@chat_bp.route("/api/chat/projects/<project_id>/files/upload", methods=["POST"])
@require_auth
def project_files_upload(project_id):
    # Reject oversized requests BEFORE touching request.files/form —
    # multipart parsing consumes (and spools) the whole body. The app-level
    # MAX_CONTENT_LENGTH (set in init_chat) makes Werkzeug enforce this
    # during parsing too, covering chunked bodies with no Content-Length;
    # the byte counter inside save_stream is the last line of defense.
    if request.content_length and request.content_length > pf.MAX_UPLOAD_BYTES * 1.05:
        return jsonify({"error": "file too large"}), 413
    root, err = _project_root_or_404(project_id, create=True)
    if err:
        return err
    if "file" not in request.files:
        return jsonify({"error": "multipart 'file' field is required"}), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "filename is required"}), 400
    dir_rel = request.form.get("dir", "")
    overwrite = request.form.get("overwrite", "").lower() in ("1", "true", "yes")
    node = pf.save_stream(root, dir_rel, upload.filename, upload.stream, overwrite=overwrite)
    stale = _revalidate_or_cleanup(project_id)
    if stale:
        return stale
    logger.info("project %s: uploaded %s (%d bytes)", project_id, node["path"], node.get("size", 0))
    return jsonify(node), 201


@chat_bp.route("/api/chat/projects/<project_id>/files/download", methods=["GET"])
@require_auth
def project_files_download(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    abs_path = pf.stat_file(root, request.args.get("path", ""))
    return send_file(abs_path, as_attachment=True)


@chat_bp.route("/api/chat/projects/<project_id>/files/mkdir", methods=["POST"])
@require_auth
def project_files_mkdir(project_id):
    root, err = _project_root_or_404(project_id, create=True)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {path: string}"}), 400
    node = pf.mkdir(root, data.get("path"))
    stale = _revalidate_or_cleanup(project_id)
    if stale:
        return stale
    return jsonify(node), 201


@chat_bp.route("/api/chat/projects/<project_id>/files/move", methods=["POST"])
@require_auth
def project_files_move(project_id):
    root, err = _project_root_or_404(project_id, create=True)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {path, new_path}"}), 400
    node = pf.move(root, data.get("path"), data.get("new_path"))
    stale = _revalidate_or_cleanup(project_id)
    if stale:
        return stale
    return jsonify(node)


@chat_bp.route("/api/chat/projects/<project_id>/files", methods=["DELETE"])
@require_auth
def project_files_delete(project_id):
    root, err = _project_root_or_404(project_id, create=True)
    if err:
        return err
    pf.delete(root, request.args.get("path", ""))
    stale = _revalidate_or_cleanup(project_id)
    if stale:
        return stale
    return jsonify({"ok": True})
