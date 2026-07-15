import json
import logging
import os
import sqlite3
import uuid

from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context

from auth import require_auth
from .db import ChatDB
from .models import Conversation, Message, Critique, ChatRun, Project
from .constants import DEFAULT_MAIN_SYSTEM_PROMPT, DEFAULT_SIDEKICK_SYSTEM_PROMPT, DEFAULT_CONTEXT_WINDOW
from .llm_proxy import stream_chat_completion
from .critique import build_critique_context, request_critique, validate_annotations
from .mcp_registry import list_available_servers
from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from .event_bus import EventBus
from .run_manager import ChatRunManager
from .runs import ChatRunStatus, TERMINAL_STATUSES
from . import openrouter, settings_store

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
    # Cap request bodies so Werkzeug rejects an oversized upload DURING
    # multipart parsing (before it is fully spooled to disk) — covers
    # chunked bodies that carry no Content-Length. Slightly above the
    # per-file cap to leave room for multipart framing; an explicit
    # deployment override is preserved.
    from .project_files import configure_max_content_length
    configure_max_content_length(app)

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


def _effective_project_id(conv):
    """The conversation's effective project. Membership is root-only: a
    spin-off keeps project_id NULL and follows its root ancestor.

    This is the SINGLE owner of project resolution for a chat turn: it is
    called once when the run is created, and the result is snapshotted into
    the run (manager scoping AND tool auto-enable both consume the same
    value), so a root moved mid-turn cannot split scope from toggles.
    """
    if conv.project_id:
        return conv.project_id
    if conv.parent_conversation_id:
        return _get_db().resolve_project_id(conv.id)
    return None


def _mcp_for_conversation(conv, enabled_servers, project_id):
    """MCP manager for a run, or None when the turn has no tools.

    project_id is the pre-resolved effective project (see
    _effective_project_id). Project conversations always get a manager —
    the project-files server is auto-enabled for them (see
    runtime._build_stream) — wrapped so its subprocess spawns learn the
    project's directory via the environment.
    """
    from . import project_files as pf
    from .project_files_mcp import ProjectScopedMCPManager

    if not (enabled_servers or project_id):
        return None
    manager = _get_mcp()
    if project_id:
        storage_root = current_app.config.get("PROJECT_FILES_DIR") or pf.default_storage_root()
        manager = ProjectScopedMCPManager(manager, pf.project_root(storage_root, project_id))
    return manager


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


# -- Settings: curated OpenRouter model list --

def _openrouter_settings_payload() -> dict:
    """Shape returned by every openrouter-models settings endpoint.

    ``configured`` tells the frontend whether OPENROUTER_API_KEY is set —
    the chat picker hides the OpenRouter group when it isn't, while the
    Tools-page editor stays usable and just shows a banner.
    """
    return {
        "configured": openrouter.is_configured(),
        "current": settings_store.get_openrouter_models(),
        "builtin": openrouter.DEFAULT_MODELS,
        "customized": settings_store.is_openrouter_models_customized(),
    }


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["GET"])
@require_auth
def get_openrouter_models_setting():
    return jsonify(_openrouter_settings_payload())


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["PUT"])
@require_auth
def put_openrouter_models_setting():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be {models: [{id, label?}]}"}), 400
    models = data.get("models")
    try:
        settings_store.set_openrouter_models(models)
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    logger.info("openrouter model list updated (%d models)", len(models))
    return jsonify(_openrouter_settings_payload())


@chat_bp.route("/api/chat/settings/openrouter-models", methods=["DELETE"])
@require_auth
def delete_openrouter_models_setting():
    """Drop any customization, reverting the picker to the built-in list."""
    settings_store.reset_openrouter_models()
    logger.info("openrouter model list reset to built-in")
    return jsonify(_openrouter_settings_payload())


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
    project = _get_db().create_project(project)
    return jsonify(project.to_dict()), 201


@chat_bp.route("/api/chat/projects", methods=["GET"])
@require_auth
def list_projects():
    projects = _get_db().list_projects()
    return jsonify({"projects": [p.to_dict() for p in projects]})


@chat_bp.route("/api/chat/projects/<project_id>", methods=["GET"])
@require_auth
def get_project(project_id):
    project = _get_db().get_project(project_id)
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
    db = _get_db()
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
    db = _get_db()
    if db.get_project(project_id) is None:
        return jsonify({"error": "Project not found"}), 404
    storage_root = current_app.config.get("PROJECT_FILES_DIR") or pf.default_storage_root()
    try:
        pf.delete_project_root(storage_root, project_id, strict=True)
    except OSError as e:
        logger.error("project %s: files cleanup failed, aborting delete: %s", project_id, e)
        return jsonify({"error": f"failed to remove project files: {e}"}), 500
    if db.delete_project(project_id):
        pf.delete_project_root(storage_root, project_id)  # sweep, best-effort
        return jsonify({"ok": True})
    return jsonify({"error": "Project not found"}), 404


# -- Conversations CRUD --

@chat_bp.route("/api/chat/conversations", methods=["POST"])
@require_auth
def create_conversation():
    data = request.get_json() or {}
    main_service = data.get("main_service")
    if not main_service:
        return jsonify({"error": "main_service is required"}), 400

    project_id = data.get("project_id")
    if project_id is not None:
        if not isinstance(project_id, str):
            return jsonify({"error": "project_id must be a string or null"}), 400
        # Membership is root-only: spin-offs follow their parent's project.
        if data.get("parent_conversation_id"):
            return jsonify({"error": "Spin-off conversations inherit their parent's project"}), 400
        if _get_db().get_project(project_id) is None:
            return jsonify({"error": "Project not found"}), 400

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
        project_id=project_id,
    )
    try:
        conv = _get_db().create_conversation(conv)
    except sqlite3.IntegrityError:
        # The project was deleted between the existence check above and the
        # insert — the DB trigger rejected the orphan reference.
        return jsonify({"error": "Project not found"}), 400
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
    # project_id: null detaches (back to unfiled); a non-null value must be
    # a string naming an existing project, and only root conversations can
    # be assigned — spin-offs follow their parent's project.
    if "project_id" in data and data["project_id"] is not None:
        if not isinstance(data["project_id"], str):
            return jsonify({"error": "project_id must be a string or null"}), 400
        existing = db.get_conversation(conv_id)
        if existing is None:
            return jsonify({"error": "Conversation not found"}), 404
        if existing.parent_conversation_id:
            return jsonify({"error": "Spin-off conversations inherit their parent's project"}), 400
        if db.get_project(data["project_id"]) is None:
            return jsonify({"error": "Project not found"}), 400
    try:
        conv = db.update_conversation(conv_id, **data)
    except sqlite3.IntegrityError:
        # The project was deleted between the existence check above and the
        # write — the DB trigger rejected the orphan reference.
        return jsonify({"error": "Project not found"}), 400
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
                        first_user_content, delete_from_seq=None,
                        effective_project_id=None):
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
                  first_user_content=first_user_content,
                  effective_project_id=effective_project_id)

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
    project_id = _effective_project_id(conv)
    mcp_manager = _mcp_for_conversation(conv, enabled_servers, project_id)

    return _start_run_response(db, conv, user_msg, mcp_manager, is_first, content,
                               effective_project_id=project_id)


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
    project_id = _effective_project_id(conv)
    mcp_mgr = _mcp_for_conversation(conv, enabled_servers, project_id)

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
                               first_user_content=content, delete_from_seq=msg.seq,
                               effective_project_id=project_id)


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

    q, replay = manager.subscribe_with_replay(run_id)
    return Response(stream_with_context(manager.observe(run_id, q, replay)),
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


@chat_bp.route("/api/chat/conversations/<conv_id>/cancel-active-run", methods=["POST"])
@require_auth
def cancel_active_run(conv_id):
    """Cancel whatever run is active for a conversation, by conversation id.

    The Stop button uses this so cancellation never depends on the client
    having captured the run id from the run_started frame: the server creates
    the run when the turn starts, so it is always findable from the
    conversation.

    An optional {"expected_run_id": "<id>"} body guards against a stale Stop:
    if the run the client meant to stop has already finished and a newer run is
    active in this conversation, the cancel is a no-op rather than killing the
    newer run.

    Returns {"run": <run>} when a run was cancelled, or {"run": null} (still
    200) when the conversation has no active run, or its active run does not
    match expected_run_id — both harmless no-ops. 404 only if the conversation
    does not exist.
    """
    db = _get_db()
    if db.get_conversation(conv_id) is None:
        return jsonify({"error": "Conversation not found"}), 404
    body = request.get_json(silent=True) or {}
    expected_run_id = body.get("expected_run_id")
    run = _get_run_manager().request_cancel_for_conversation(
        conv_id, expected_run_id=expected_run_id)
    return jsonify({"run": run.to_dict() if run is not None else None})


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
from . import project_files_routes  # noqa: E402,F401
