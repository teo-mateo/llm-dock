"""HTTP surface for project CRUD; project file operations live in project_files_routes."""

import logging
import uuid

from flask import jsonify, request

from auth import require_auth

from .app_deps import deps
from .blueprint import chat_bp
from .models import Project

logger = logging.getLogger(__name__)


# -- Projects CRUD --

def _validate_project_name(name):
    """Returns (cleaned_name, error). A name is required and non-blank."""
    if not isinstance(name, str) or not name.strip():
        return None, "name is required"
    return name.strip(), None


@chat_bp.route("/api/chat/projects", methods=["POST"])
@require_auth
def create_project():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    name, err = _validate_project_name(data.get("name"))
    if err:
        return jsonify({"error": err}), 400
    description = data.get("description", "")
    if not isinstance(description, str):
        return jsonify({"error": "description must be a string"}), 400
    project = Project(id=str(uuid.uuid4()), name=name, description=description)
    project = deps().db.create_project(project)
    return jsonify(project.to_dict()), 201


@chat_bp.route("/api/chat/projects", methods=["GET"])
@require_auth
def list_projects():
    projects = deps().db.list_projects()
    return jsonify({"projects": [p.to_dict() for p in projects]})


@chat_bp.route("/api/chat/projects/<project_id>", methods=["GET"])
@require_auth
def get_project(project_id):
    project = deps().db.get_project(project_id)
    if project is None:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project.to_dict())


@chat_bp.route("/api/chat/projects/<project_id>", methods=["PUT"])
@require_auth
def update_project(project_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    updates = {}
    if "name" in data:
        name, err = _validate_project_name(data.get("name"))
        if err:
            return jsonify({"error": err}), 400
        updates["name"] = name
    if "description" in data:
        if not isinstance(data["description"], str):
            return jsonify({"error": "description must be a string"}), 400
        updates["description"] = data["description"]
    db = deps().db
    if db.get_project(project_id) is None:
        return jsonify({"error": "Project not found"}), 404
    project = db.update_project(project_id, **updates)
    if project is None:
        # The project was deleted between the existence check and the
        # update (two-tab rename/delete race) — a 404, not a 500.
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project.to_dict())


@chat_bp.route("/api/chat/projects/<project_id>", methods=["DELETE"])
@require_auth
def delete_project(project_id):
    """Delete a project. Its conversations are detached (become unfiled),
    not deleted; its files directory IS removed.

    Files are removed BEFORE the DB row, strictly: if cleanup fails
    (permissions, IO), the row survives and the delete stays retryable —
    otherwise the data would be orphaned with no API path back to it. The
    post-delete sweep is best-effort and only mops up a directory that a
    concurrent file write recreated in the window.
    """
    from . import project_files as pf
    db = deps().db
    if db.get_project(project_id) is None:
        return jsonify({"error": "Project not found"}), 404
    storage_root = deps().storage_root()
    try:
        pf.delete_project_root(storage_root, project_id, strict=True)
    except OSError as e:
        logger.error("project %s: files cleanup failed, aborting delete: %s", project_id, e)
        return jsonify({"error": f"failed to remove project files: {e}"}), 500
    if db.delete_project(project_id):
        pf.delete_project_root(storage_root, project_id)  # sweep, best-effort
        return jsonify({"ok": True})
    return jsonify({"error": "Project not found"}), 404
