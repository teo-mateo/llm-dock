"""HTTP surface for project files, registered onto chat_bp.

Imported at the bottom of chat/routes.py (same pattern as
mcp_admin_routes) so the routes attach before the blueprint is
registered on the app.
"""
import logging

from flask import jsonify, request, current_app, send_file

from auth import require_auth
from . import project_files as pf
from .routes import chat_bp, _get_db

logger = logging.getLogger(__name__)


def _storage_root() -> str:
    return current_app.config.get("PROJECT_FILES_DIR") or pf.default_storage_root()


def _project_root_or_404(project_id):
    """Returns (root, error_response). The project must exist in the DB;
    its directory is created lazily."""
    if _get_db().get_project(project_id) is None:
        return None, (jsonify({"error": "Project not found"}), 404)
    root = pf.ensure_project_root(_storage_root(), project_id)
    return root, None


@chat_bp.errorhandler(pf.ProjectFilesError)
def _handle_pf_error(e):
    return jsonify({"error": str(e)}), e.status


@chat_bp.route("/api/chat/projects/<project_id>/files", methods=["GET"])
@require_auth
def project_files_tree(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    return jsonify({"tree": pf.build_tree(root)})


@chat_bp.route("/api/chat/projects/<project_id>/files/upload", methods=["POST"])
@require_auth
def project_files_upload(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    if "file" not in request.files:
        return jsonify({"error": "multipart 'file' field is required"}), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "filename is required"}), 400
    if request.content_length and request.content_length > pf.MAX_UPLOAD_BYTES * 1.05:
        return jsonify({"error": "file too large"}), 413
    dir_rel = request.form.get("dir", "")
    overwrite = request.form.get("overwrite", "").lower() in ("1", "true", "yes")
    node = pf.save_stream(root, dir_rel, upload.filename, upload.stream, overwrite=overwrite)
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
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {path: string}"}), 400
    node = pf.mkdir(root, data.get("path"))
    return jsonify(node), 201


@chat_bp.route("/api/chat/projects/<project_id>/files/move", methods=["POST"])
@require_auth
def project_files_move(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {path, new_path}"}), 400
    node = pf.move(root, data.get("path"), data.get("new_path"))
    return jsonify(node)


@chat_bp.route("/api/chat/projects/<project_id>/files", methods=["DELETE"])
@require_auth
def project_files_delete(project_id):
    root, err = _project_root_or_404(project_id)
    if err:
        return err
    pf.delete(root, request.args.get("path", ""))
    return jsonify({"ok": True})
