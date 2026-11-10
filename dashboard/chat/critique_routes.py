"""HTTP surface for message critiques."""

import json
import uuid

from flask import jsonify, request

from auth import require_auth

from .app_deps import deps
from .blueprint import chat_bp
from .constants import DEFAULT_CONTEXT_WINDOW
from .critique import build_critique_context, request_critique, validate_annotations
from .models import Critique

# -- Critique --

@chat_bp.route("/api/chat/messages/<msg_id>/critique", methods=["POST"])
@require_auth
def create_critique(msg_id):
    db = deps().db
    msg = db.get_message(msg_id)
    if msg is None:
        return jsonify({"error": "Message not found"}), 404
    if msg.role != "assistant":
        return jsonify({"error": "Can only critique assistant messages"}), 400

    conv = db.get_conversation(msg.conversation_id)
    if conv is None or not conv.sidekick_service:
        return jsonify({"error": "No sidekick service configured for this conversation"}), 400

    data = request.get_json() or {}
    context_window = data.get("context_window", DEFAULT_CONTEXT_WINDOW)
    extra_instructions = data.get("extra_instructions", "")

    messages = db.get_messages(conv.id)
    context = build_critique_context(messages, msg, context_window)

    result = request_critique(conv.sidekick_service, context, extra_instructions=extra_instructions)

    if "error" in result and "verdict" not in result:
        return jsonify(result), 502

    annotations = result.get("annotations", [])
    validated = validate_annotations(annotations, msg.content)

    critique = Critique(
        id=str(uuid.uuid4()),
        message_id=msg_id,
        sidekick_service=conv.sidekick_service,
        annotations_json=json.dumps(validated),
        summary=result.get("summary"),
        verdict=result.get("verdict"),
        raw_response=result.get("raw_response"),
    )
    saved = db.save_critique(critique)
    return jsonify(saved.to_dict())


@chat_bp.route("/api/chat/messages/<msg_id>/critique", methods=["GET"])
@require_auth
def get_critique(msg_id):
    critique = deps().db.get_critique(msg_id)
    if critique is None:
        return jsonify({"error": "No critique found"}), 404
    return jsonify(critique.to_dict())
