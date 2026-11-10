import json
import logging
import sqlite3
import uuid

from flask import jsonify, request

from auth import require_auth
from .models import (Conversation, Message, Critique, Project,
                     DeleteMessageOutcome)
from .constants import DEFAULT_SIDEKICK_SYSTEM_PROMPT, DEFAULT_CONTEXT_WINDOW
from .llm_proxy import stream_chat_completion
from .tool_loop import stream_with_tools
from .critique import build_critique_context, request_critique, validate_annotations
from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from .runs import TERMINAL_STATUSES
from . import conversation_policy, http, run_config, run_start, settings_store
from .outcomes import PolicyError
from .blueprint import chat_bp
from .bootstrap import init_chat  # noqa: F401
from .app_deps import deps
import sampling_params as sampling

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


# -- Runs (observation + cancellation) --


@chat_bp.route("/api/chat/runs/<run_id>", methods=["GET"])
@require_auth
def get_run(run_id):
    run = deps().db.get_chat_run(run_id)
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
    db = deps().db
    manager = deps().run_manager
    run = db.get_chat_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404

    if run.status in TERMINAL_STATUSES:
        def terminal():
            yield encode_sse_event("run_status", {"status": run.status, "error": run.error})
        return http.sse_response(terminal(), wrap=False)

    q, replay = manager.subscribe_with_replay(run_id)
    return http.sse_response(manager.observe(run_id, q, replay))


@chat_bp.route("/api/chat/runs/<run_id>/cancel", methods=["POST"])
@require_auth
def cancel_run(run_id):
    """Cancel a run's server-side work, independent of any SSE observer.

    Cancelling an already-terminal run is a harmless no-op that returns 200
    with the run's existing status (terminal-guarded in the DB).
    """
    run = deps().run_manager.request_cancel(run_id)
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
    db = deps().db
    if db.get_conversation(conv_id) is None:
        return jsonify({"error": "Conversation not found"}), 404
    body = request.get_json(silent=True) or {}
    expected_run_id = body.get("expected_run_id")
    run = deps().run_manager.request_cancel_for_conversation(
        conv_id, expected_run_id=expected_run_id)
    return jsonify({"run": run.to_dict() if run is not None else None})


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

    return http.sse_response(generate())


# -- Ghost chat (ephemeral, zero-trace) --

@chat_bp.route("/api/chat/ghost", methods=["POST"])
@require_auth
def ghost_chat():
    """Stateless ghost chat — no persistence, no trace. The request carries the
    full message history and the reply streams back without any db write, so a
    refresh erases the thread as designed. mcp_servers enables the tool loop
    without a conversation; tool results are streamed, never stored."""
    data = request.get_json() or {}
    service_name = data.get("service_name")
    messages_array = data.get("messages", [])
    mcp_servers = data.get("mcp_servers") or []

    if not service_name:
        return jsonify({"error": "service_name is required"}), 400
    if not messages_array:
        return jsonify({"error": "messages array is required"}), 400
    if not isinstance(mcp_servers, list):
        return jsonify({"error": "mcp_servers must be a list of server ids"}), 400

    mcp = deps().mcp

    def generate():
        # One manager for the whole stream — discovery is cached, so repeated
        # ghost turns against the same servers do not re-spawn the subprocess.
        tools = mcp.get_all_tools(mcp_servers) if mcp_servers else None
        if tools:
            stream = stream_with_tools(service_name, messages_array, tools, mcp)
        else:
            stream = stream_chat_completion(service_name, messages_array)
        for event_type, event_data in stream:
            if event_type == "delta":
                yield encode_sse_delta(event_data["raw"])
            elif event_type == "tool_call":
                yield encode_sse_event("tool_call", event_data)
            elif event_type == "tool_result":
                yield encode_sse_event("tool_result", event_data)
            elif event_type == "artifact":
                yield encode_sse_event("artifact", {
                    "artifact_type": event_data.get("type"),
                    "title": event_data.get("title"),
                    "content": event_data.get("content"),
                })
            elif event_type == "done":
                yield DONE
            elif event_type == "error":
                yield encode_sse({"error": event_data["message"]})
                return

    # no-store, not just no-cache: ghost replies must never be written to any
    # HTTP cache (browser or intermediate proxy) — the deniability is part of
    # the feature, so a cached body would be a trace.
    return http.sse_response(generate(), headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


# Register admin routes onto chat_bp at module-load time. Importing this
# from inside init_chat() runs after app.register_blueprint(chat_bp), which
# Flask 3 rejects with "The setup method 'route' can no longer be called on
# the blueprint 'chat'". This bottom-of-file import runs while chat.routes
# is being imported by app.py — before the blueprint is registered.
from . import mcp_admin_routes  # noqa: E402,F401
from . import project_files_routes  # noqa: E402,F401
from . import providers_routes  # noqa: E402,F401
from . import settings_routes  # noqa: E402,F401
from . import openrouter_routes  # noqa: E402,F401
