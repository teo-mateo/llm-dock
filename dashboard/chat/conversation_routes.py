"""HTTP surface for conversation CRUD and the per-service sampling field capabilities."""

import sqlite3
import uuid

from flask import jsonify, request

import sampling_params as sampling
from auth import require_auth

from . import conversation_policy, http, run_config, settings_store
from .app_deps import deps
from .blueprint import chat_bp
from .constants import DEFAULT_SIDEKICK_SYSTEM_PROMPT
from .models import Conversation
from .outcomes import PolicyError

@chat_bp.route("/api/chat/sampling-fields", methods=["GET"])
@require_auth
def get_sampling_fields():
    """Fields the composer may offer for one service, with their bounds.

    Read from the same module that builds the request, so a knob the engine has no
    verified mapping for is absent here and absent from the payload — the picker
    cannot offer what the runner would drop. Unverified is indistinguishable from
    absent, on purpose: offering a knob an engine ignores is the failure this
    endpoint exists to prevent.
    """
    service = request.args.get("service") or ""
    engine = run_config.service_engine(service, deps().services)
    return jsonify({
        "service": service,
        "engine": engine,
        "fields": sampling.fields_descriptor(sampling.supported_fields(engine)),
    })


# -- Conversations CRUD --

@chat_bp.route("/api/chat/conversations", methods=["POST"])
@require_auth
def create_conversation():
    data = request.get_json() or {}
    d = deps()
    db = d.db
    outcome = conversation_policy.resolve_new_conversation(
        data,
        get_prompt=db.get_prompt,
        get_project=db.get_project,
        default_prompt=settings_store.get_main_system_prompt,
        services=d.services,
    )
    if isinstance(outcome, PolicyError):
        return http.error_response(outcome)

    conv = Conversation(
        id=str(uuid.uuid4()),
        title=data.get("title", "New Conversation"),
        main_service=outcome.main_service,
        sidekick_service=data.get("sidekick_service"),
        main_system_prompt=outcome.main_system_prompt,
        sidekick_system_prompt=data.get("sidekick_system_prompt", DEFAULT_SIDEKICK_SYSTEM_PROMPT),
        parent_conversation_id=data.get("parent_conversation_id"),
        selected_text=data.get("selected_text"),
        project_id=outcome.project_id,
        prompt_id=outcome.prompt_id,
        reasoning_level=outcome.reasoning_level,
        sampling_params_json=outcome.sampling_params_json,
    )
    try:
        conv = db.create_conversation(conv)
    except sqlite3.IntegrityError as e:
        return http.error_response(conversation_policy.integrity_error(e))
    return jsonify(conv.to_dict(include_messages=True)), 201


@chat_bp.route("/api/chat/conversations", methods=["GET"])
@require_auth
def list_conversations():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    # `unfiled=true` restricts the list to conversations with no project —
    # clients that don't support projects (the Android app) opt in so
    # desktop-created project threads never appear in their flat list.
    unfiled = request.args.get("unfiled", "false").lower() in ("true", "1", "yes")
    convs, total = deps().db.list_conversations(limit=limit, offset=offset, unfiled=unfiled)
    return jsonify({
        "conversations": [c.to_dict() for c in convs],
        "total": total,
    })


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@require_auth
def get_conversation(conv_id):
    db = deps().db
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    critiques = db.get_critiques_for_conversation(conv_id)
    artifacts = db.get_artifacts_for_conversation(conv_id)
    result = conv.to_dict(include_messages=True)
    result["critiques"] = {msg_id: c.to_dict() for msg_id, c in critiques.items()}
    result["artifacts"] = {msg_id: [a.to_dict() for a in arts] for msg_id, arts in artifacts.items()}
    return jsonify(result)


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["PUT"])
@require_auth
def update_conversation(conv_id):
    data = request.get_json() or {}
    d = deps()
    db = d.db
    fields = conversation_policy.resolve_conversation_update(
        data,
        conv_id=conv_id,
        get_conversation=db.get_conversation,
        get_prompt=db.get_prompt,
        get_project=db.get_project,
        services=d.services,
    )
    if isinstance(fields, PolicyError):
        return http.error_response(fields)
    try:
        conv = db.update_conversation(conv_id, **fields)
    except sqlite3.IntegrityError as e:
        return http.error_response(conversation_policy.integrity_error(e))
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(conv.to_dict())


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
@require_auth
def delete_conversation(conv_id):
    if deps().db.delete_conversation(conv_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Conversation not found"}), 404


@chat_bp.route("/api/chat/conversations/delete", methods=["POST"])
@require_auth
def delete_conversations_batch():
    data = request.get_json() or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return jsonify({"error": "ids must be a list of strings"}), 400
    deleted = deps().db.delete_conversations(ids)
    return jsonify({"ok": True, "deleted": deleted})
