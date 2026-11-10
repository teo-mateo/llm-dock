"""HTTP surface for sending, editing and deleting messages; a send or edit starts a run."""

import json
import logging
import uuid

from flask import jsonify, request

from auth import require_auth

from . import http, run_start
from .app_deps import deps
from .blueprint import chat_bp
from .models import DeleteMessageOutcome, Message
from .outcomes import PolicyError

logger = logging.getLogger(__name__)


# -- Messages --


def _start_run(conv, user_msg, *, is_first, first_user_content, delete_from_seq=None):
    d = deps()
    result = run_start.start_run(
        db=d.db,
        run_manager=d.run_manager,
        get_mcp=lambda: d.mcp,
        storage_root=d.storage_root(),
        services=d.services,
        conv=conv,
        user_msg=user_msg,
        is_first=is_first,
        first_user_content=first_user_content,
        delete_from_seq=delete_from_seq,
    )
    if isinstance(result, PolicyError):
        return http.error_response(result)
    return http.sse_response(result.observer)


@chat_bp.route("/api/chat/conversations/<conv_id>/messages", methods=["POST"])
@require_auth
def send_message(conv_id):
    db = deps().db
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json() or {}
    content = data.get("content", "").strip()
    images = data.get("images", [])
    if not content and not images:
        return jsonify({"error": "content or images required"}), 400

    images_json = json.dumps(images) if images else None

    # First message? (computed before persisting the new user message) —
    # drives one-shot auto-title generation in the background job. The actual
    # one-active-run-per-conversation guard is enforced atomically in
    # create_run_with_user_message (a pre-check here would be racy).
    is_first = len(db.get_messages(conv_id)) == 0

    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="user",
        content=content,
        images_json=images_json,
        seq=0,  # assigned atomically inside create_run_with_user_message
    )

    return _start_run(conv, user_msg, is_first=is_first, first_user_content=content)


@chat_bp.route("/api/chat/conversations/<conv_id>/messages/<msg_id>", methods=["PUT"])
@require_auth
def edit_message(conv_id, msg_id):
    db = deps().db
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    msg = db.get_message(msg_id)
    if msg is None or msg.conversation_id != conv_id:
        return jsonify({"error": "Message not found"}), 404
    if msg.role != "user":
        return jsonify({"error": "Can only edit user messages"}), 400

    data = request.get_json() or {}
    content = data.get("content", "").strip()
    images = data.get("images", [])
    if not content and not images:
        return jsonify({"error": "content or images required"}), 400

    images_json = json.dumps(images) if images else None

    new_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="user",
        content=content,
        images_json=images_json,
        seq=0,  # assigned atomically inside create_run_with_user_message
    )

    # The truncate-from-seq and re-send happen in one transaction (with the
    # active-run guard), so a rejected edit doesn't destroy the tail. An edit
    # replaces an existing turn, so it never triggers auto-title.
    return _start_run(conv, new_msg, is_first=False, first_user_content=content,
                      delete_from_seq=msg.seq)


@chat_bp.route("/api/chat/conversations/<conv_id>/messages/<msg_id>", methods=["DELETE"])
@require_auth
def delete_message(conv_id, msg_id):
    db = deps().db
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    result = db.delete_message_guarded(conv_id, msg_id)
    if result.outcome is DeleteMessageOutcome.CONFLICT:
        return jsonify({"error": "Cannot delete a message while a run is active"}), 409
    if result.outcome is DeleteMessageOutcome.NOT_FOUND:
        return jsonify({"error": "Message not found"}), 404
    logger.info("message deleted: %s from conversation %s", msg_id, conv_id)
    return jsonify({"ok": True})
