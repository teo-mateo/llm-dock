"""HTTP surface for observing and cancelling runs."""


from flask import jsonify, request

from auth import require_auth

from . import http
from .app_deps import deps
from .blueprint import chat_bp
from .event_codec import encode_sse_event
from .runs import TERMINAL_STATUSES

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
