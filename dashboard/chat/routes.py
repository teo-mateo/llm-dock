import json
import logging
import os
import uuid

from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context

from auth import require_auth
from .db import ChatDB
from .models import Conversation, Message, Critique, ChatRun
from .constants import DEFAULT_MAIN_SYSTEM_PROMPT, DEFAULT_SIDEKICK_SYSTEM_PROMPT, DEFAULT_CONTEXT_WINDOW
from .llm_proxy import stream_chat_completion
from .critique import build_critique_context, request_critique, validate_annotations
from .mcp_registry import list_available_servers
from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from .event_bus import EventBus
from .run_manager import ChatRunManager
from .runs import ChatRunStatus, TERMINAL_STATUSES
from . import settings_store

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


def init_chat(app, db_path: str = None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chat.db")
    db = ChatDB(db_path)
    app.config["CHAT_DB"] = db

    from .mcp_client import MCPClientManager
    from . import mcp_config
    mgr = MCPClientManager()
    app.config["MCP_MANAGER"] = mgr
    mcp_config.bind_manager(mgr)
    mcp_config.reload()

    # Background-run infrastructure (#58): an event bus for live observers and
    # a manager owning the worker pool. Runs from a previous process that died
    # mid-flight are marked failed so they don't linger as stuck active runs.
    bus = EventBus()
    run_manager = ChatRunManager(db, bus)
    run_manager.recover_interrupted_runs()
    app.config["CHAT_EVENT_BUS"] = bus
    app.config["CHAT_RUN_MANAGER"] = run_manager

    logger.info("Chat subsystem initialized")


def _get_db() -> ChatDB:
    return current_app.config["CHAT_DB"]


def _get_mcp():
    return current_app.config["MCP_MANAGER"]


def _get_run_manager():
    return current_app.config["CHAT_RUN_MANAGER"]


@chat_bp.route("/api/chat/mcp-servers", methods=["GET"])
@require_auth
def get_mcp_servers():
    return jsonify({"servers": list_available_servers()})


# -- Settings: editable default main system prompt --

def _settings_payload() -> dict:
    """Shape returned by every main-system-prompt settings endpoint."""
    return {
        "current": settings_store.get_main_system_prompt(),
        "builtin": DEFAULT_MAIN_SYSTEM_PROMPT,
        "customized": settings_store.is_main_system_prompt_customized(),
    }


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["GET"])
@require_auth
def get_main_system_prompt_setting():
    """Return current default, built-in baseline, and whether they differ.

    The frontend uses ``builtin`` to power the Reset button and
    ``customized`` for the "modified from built-in" indicator without
    needing a client-side string compare.
    """
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["PUT"])
@require_auth
def put_main_system_prompt_setting():
    # get_json(silent=True) returns whatever was parsed — including a bare
    # list/str/number for a non-object body — so guard the type before
    # calling .get(), otherwise a body like [1] would 500 instead of 400.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {content: string}"}), 400
    content = data.get("content")
    if not isinstance(content, str):
        return jsonify({"error": "body must be {content: string}"}), 400
    try:
        settings_store.set_main_system_prompt(content)
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    logger.info("default main_system_prompt updated (%d chars)", len(content))
    return jsonify(_settings_payload())


@chat_bp.route("/api/chat/settings/main-system-prompt", methods=["DELETE"])
@require_auth
def delete_main_system_prompt_setting():
    """Drop any customization, reverting new conversations to the built-in."""
    settings_store.reset_main_system_prompt()
    logger.info("default main_system_prompt reset to built-in")
    return jsonify(_settings_payload())


# -- Conversations CRUD --

@chat_bp.route("/api/chat/conversations", methods=["POST"])
@require_auth
def create_conversation():
    data = request.get_json() or {}
    main_service = data.get("main_service")
    if not main_service:
        return jsonify({"error": "main_service is required"}), 400

    # Honor an explicit prompt from the client (a fork or programmatic
    # caller may want one), otherwise fall back to whatever the user has
    # configured as the dashboard-wide default — and only then to the
    # built-in baked into constants.py.
    if "main_system_prompt" in data:
        main_system_prompt = data["main_system_prompt"]
    else:
        main_system_prompt = settings_store.get_main_system_prompt()

    conv = Conversation(
        id=str(uuid.uuid4()),
        title=data.get("title", "New Conversation"),
        main_service=main_service,
        sidekick_service=data.get("sidekick_service"),
        main_system_prompt=main_system_prompt,
        sidekick_system_prompt=data.get("sidekick_system_prompt", DEFAULT_SIDEKICK_SYSTEM_PROMPT),
        parent_conversation_id=data.get("parent_conversation_id"),
        selected_text=data.get("selected_text"),
    )
    conv = _get_db().create_conversation(conv)
    return jsonify(conv.to_dict(include_messages=True)), 201


@chat_bp.route("/api/chat/conversations", methods=["GET"])
@require_auth
def list_conversations():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    convs, total = _get_db().list_conversations(limit=limit, offset=offset)
    return jsonify({
        "conversations": [c.to_dict() for c in convs],
        "total": total,
    })


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@require_auth
def get_conversation(conv_id):
    db = _get_db()
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    # Include critiques and artifacts
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
    db = _get_db()
    conv = db.update_conversation(conv_id, **data)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(conv.to_dict())


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
@require_auth
def delete_conversation(conv_id):
    if _get_db().delete_conversation(conv_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Conversation not found"}), 404


@chat_bp.route("/api/chat/conversations/delete", methods=["POST"])
@require_auth
def delete_conversations_batch():
    data = request.get_json() or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return jsonify({"error": "ids must be a list of strings"}), 400
    deleted = _get_db().delete_conversations(ids)
    return jsonify({"ok": True, "deleted": deleted})


# -- Messages --


def _start_run_response(db, conv, user_msg, mcp_manager, is_first,
                        first_user_content, delete_from_seq=None):
    """Atomically persist the user message + a queued run (rejecting a second
    run while one is active), start the background job, and return an SSE
    Response that observes it.

    The HTTP response is only an observer (event_bus): if the client
    disconnects, the run keeps going on the worker pool and the assistant
    reply is persisted regardless. We subscribe to the bus BEFORE starting the
    job so no early events are missed.

    Returns a 409 response tuple when an active run already exists for the
    conversation (the user message — and any edit truncation — is rolled back).
    """
    run = ChatRun(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        status=ChatRunStatus.QUEUED,
        user_message_id=user_msg.id,
    )
    created = db.create_run_with_user_message(user_msg, run, delete_from_seq=delete_from_seq)
    if created is None:
        return jsonify({"error": "A run is already active for this conversation"}), 409

    manager = _get_run_manager()
    q = manager.subscribe(run.id)
    manager.start(conv, run, mcp_manager=mcp_manager, is_first=is_first,
                  first_user_content=first_user_content)

    return Response(
        stream_with_context(manager.observe(run.id, q)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_bp.route("/api/chat/conversations/<conv_id>/messages", methods=["POST"])
@require_auth
def send_message(conv_id):
    db = _get_db()
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

    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    mcp_manager = _get_mcp() if enabled_servers else None

    return _start_run_response(db, conv, user_msg, mcp_manager, is_first, content)


@chat_bp.route("/api/chat/conversations/<conv_id>/messages/<msg_id>", methods=["PUT"])
@require_auth
def edit_message(conv_id, msg_id):
    db = _get_db()
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

    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    mcp_mgr = _get_mcp() if enabled_servers else None

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
    return _start_run_response(db, conv, new_msg, mcp_mgr, is_first=False,
                               first_user_content=content, delete_from_seq=msg.seq)


# -- Runs (observation + cancellation, issue #58) --


@chat_bp.route("/api/chat/runs/<run_id>", methods=["GET"])
@require_auth
def get_run(run_id):
    run = _get_db().get_chat_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run.to_dict())


@chat_bp.route("/api/chat/runs/<run_id>/stream", methods=["GET"])
@require_auth
def stream_run(run_id):
    """Reattach to a run's live event stream.

    If the run is already terminal, emit a single run_status frame and close
    (there is nothing live to replay — the conversation refetch carries the
    saved content). Otherwise subscribe to the bus and observe like the send
    path; the observer's DB backstop closes the stream even if the run finishes
    between this check and the subscribe.
    """
    db = _get_db()
    manager = _get_run_manager()
    run = db.get_chat_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

    if run.status in TERMINAL_STATUSES:
        def terminal():
            yield encode_sse_event("run_status", {"status": run.status, "error": run.error})
        return Response(terminal(), mimetype="text/event-stream", headers=headers)

    q = manager.subscribe(run_id)
    return Response(stream_with_context(manager.observe(run_id, q)),
                    mimetype="text/event-stream", headers=headers)


@chat_bp.route("/api/chat/runs/<run_id>/cancel", methods=["POST"])
@require_auth
def cancel_run(run_id):
    """Cancel a run's server-side work, independent of any SSE observer.

    Cancelling an already-terminal run is a harmless no-op that returns 200
    with the run's existing status (terminal-guarded in the DB).
    """
    run = _get_run_manager().request_cancel(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run.to_dict())


# -- Critique --

@chat_bp.route("/api/chat/messages/<msg_id>/critique", methods=["POST"])
@require_auth
def create_critique(msg_id):
    db = _get_db()
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

    # Build context from conversation messages
    messages = db.get_messages(conv.id)
    context = build_critique_context(messages, msg, context_window)

    # Request critique from sidekick
    result = request_critique(conv.sidekick_service, context, extra_instructions=extra_instructions)

    if "error" in result and "verdict" not in result:
        return jsonify(result), 502

    # Validate annotation spans against original content
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
    critique = _get_db().get_critique(msg_id)
    if critique is None:
        return jsonify({"error": "No critique found"}), 404
    return jsonify(critique.to_dict())


# -- Spinoff (ephemeral) --

@chat_bp.route("/api/chat/spinoff", methods=["POST"])
@require_auth
def spinoff():
    """Stateless streaming chat — no persistence. Used for ephemeral spin-off conversations."""
    data = request.get_json() or {}
    service_name = data.get("service_name")
    messages_array = data.get("messages", [])

    if not service_name:
        return jsonify({"error": "service_name is required"}), 400
    if not messages_array:
        return jsonify({"error": "messages array is required"}), 400

    def generate():
        for event_type, event_data in stream_chat_completion(service_name, messages_array):
            if event_type == "delta":
                yield encode_sse_delta(event_data["raw"])
            elif event_type == "done":
                yield DONE
            elif event_type == "error":
                yield encode_sse({"error": event_data["message"]})
                return

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Register admin routes onto chat_bp at module-load time. Importing this
# from inside init_chat() runs after app.register_blueprint(chat_bp), which
# Flask 3 rejects with "The setup method 'route' can no longer be called on
# the blueprint 'chat'". This bottom-of-file import runs while chat.routes
# is being imported by app.py — before the blueprint is registered.
from . import mcp_admin_routes  # noqa: E402,F401
