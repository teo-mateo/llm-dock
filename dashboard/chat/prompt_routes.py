"""HTTP surface for managed chat prompts."""

import logging

from flask import jsonify, request

from auth import require_auth

from .app_deps import deps
from .blueprint import chat_bp

logger = logging.getLogger(__name__)


# -- Chat Prompts --


@chat_bp.route("/api/chat/prompts", methods=["GET"])
@require_auth
def list_prompts():
    """Return all managed prompts, ordered by sort_order."""
    prompts = deps().db.list_prompts()
    return jsonify({"prompts": [p.to_dict() for p in prompts]})


@chat_bp.route("/api/chat/prompts", methods=["POST"])
@require_auth
def create_prompt():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    name = data.get("name")
    content = data.get("content")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name is required"}), 400
    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "content is required"}), 400
    prompt = deps().db.create_prompt(name, content)
    logger.info("chat prompt created: %s", prompt.id)
    return jsonify(prompt.to_dict()), 201


@chat_bp.route("/api/chat/prompts/<prompt_id>", methods=["GET"])
@require_auth
def get_prompt(prompt_id):
    prompt = deps().db.get_prompt(prompt_id)
    if prompt is None:
        return jsonify({"error": "Prompt not found"}), 404
    return jsonify(prompt.to_dict())


@chat_bp.route("/api/chat/prompts/<prompt_id>", methods=["PUT"])
@require_auth
def update_prompt(prompt_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    name = data.get("name")
    content = data.get("content")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name is required"}), 400
    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "content is required"}), 400
    db = deps().db
    if db.get_prompt(prompt_id) is None:
        return jsonify({"error": "Prompt not found"}), 404
    prompt = db.update_prompt(prompt_id, name, content)
    if prompt is None:
        return jsonify({"error": "Prompt not found"}), 404
    logger.info("chat prompt updated: %s", prompt_id)
    return jsonify(prompt.to_dict())


@chat_bp.route("/api/chat/prompts/<prompt_id>", methods=["DELETE"])
@require_auth
def delete_prompt(prompt_id):
    db = deps().db
    if db.get_prompt(prompt_id) is None:
        return jsonify({"error": "Prompt not found"}), 404
    db.delete_prompt(prompt_id)
    logger.info("chat prompt deleted: %s", prompt_id)
    return jsonify({"ok": True})


@chat_bp.route("/api/chat/prompts/reorder", methods=["PATCH"])
@require_auth
def reorder_prompts():
    """Reorder prompts by supplying the full ordered list of ids."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return jsonify({"error": "ids must be a list of strings"}), 400
    deps().db.reorder_prompts(ids)
    logger.info("chat prompts reordered (%d ids)", len(ids))
    return jsonify({"ok": True})
