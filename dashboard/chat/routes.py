import json
import logging
import uuid

from flask import jsonify, request

from auth import require_auth
from .models import (Critique)
from .constants import DEFAULT_CONTEXT_WINDOW
from .llm_proxy import stream_chat_completion
from .tool_loop import stream_with_tools
from .critique import build_critique_context, request_critique, validate_annotations
from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from .runs import TERMINAL_STATUSES
from . import http
from .blueprint import chat_bp
from .bootstrap import init_chat  # noqa: F401
from .app_deps import deps

logger = logging.getLogger(__name__)



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
from . import project_routes  # noqa: E402,F401
from . import conversation_routes  # noqa: E402,F401
from . import prompt_routes  # noqa: E402,F401
from . import message_routes  # noqa: E402,F401
