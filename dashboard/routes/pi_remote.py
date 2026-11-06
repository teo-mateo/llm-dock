from flask import Blueprint, Response, jsonify, request, stream_with_context

from auth import require_auth
from pi_remote.api_json import page_json, parse_message_body, parse_paging, summary_json
from pi_remote.stream import session_stream as build_session_stream
from pi_remote.stream import sessions_stream as build_sessions_stream
from pi_remote.supervisor import pi_remote_supervisor

pi_remote_bp = Blueprint("pi_remote", __name__)

COMMAND_WAIT_S = 5.0
COMMAND_ERROR_STATUS = {
    "pi_session_offline": 409,
    "rate_limited": 429,
    "queue_full": 503,
    "unsupported_command": 400,
}


def _stream_response(generator):
    return Response(
        stream_with_context(generator),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _client_or_503():
    client = pi_remote_supervisor.client
    if client is None:
        return None, (jsonify({"error": "pi_remote_unavailable"}), 503)
    return client, None


def _command_response(client, key, kind, args):
    command_id, error = client.send_command(key, kind, args)
    if error is not None:
        return jsonify({"error": error}), COMMAND_ERROR_STATUS.get(error, 400)
    result = client.await_command(command_id, COMMAND_WAIT_S)
    if result is None:
        return jsonify({"command_id": command_id, "pending": True}), 202
    return jsonify(
        {"command_id": result.command_id, "ok": result.ok, "error": result.error}
    ), 200


@pi_remote_bp.route("/api/pi/sessions", methods=["GET"])
@require_auth
def sessions():
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    return jsonify(
        {"sessions": [summary_json(summary) for summary in client.sessions()]}
    )


@pi_remote_bp.route("/api/pi/sessions/stream", methods=["GET"])
@require_auth
def sessions_sse():
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    return _stream_response(build_sessions_stream(client))


@pi_remote_bp.route(
    "/api/pi/sessions/<session_id>/<instance_id>/messages", methods=["POST"]
)
@require_auth
def session_messages(session_id, instance_id):
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    text, error = parse_message_body(request.get_json(silent=True))
    if error is not None:
        return jsonify({"error": error}), 400
    return _command_response(
        client, (session_id, instance_id), "send_message", {"text": text}
    )


@pi_remote_bp.route(
    "/api/pi/sessions/<session_id>/<instance_id>/abort", methods=["POST"]
)
@require_auth
def session_abort(session_id, instance_id):
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    return _command_response(client, (session_id, instance_id), "abort", {})


@pi_remote_bp.route(
    "/api/pi/sessions/<session_id>/<instance_id>/events", methods=["GET"]
)
@require_auth
def session_events(session_id, instance_id):
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    after_seq, limit, error = parse_paging(request.args)
    if error is not None:
        return jsonify({"error": error}), 400
    page = client.events(session_id, instance_id, after_seq, limit)
    if page is None:
        return jsonify({"error": "unknown_session"}), 404
    return jsonify(page_json(page))


@pi_remote_bp.route(
    "/api/pi/sessions/<session_id>/<instance_id>/stream", methods=["GET"]
)
@require_auth
def session_sse(session_id, instance_id):
    client, unavailable = _client_or_503()
    if unavailable is not None:
        return unavailable
    key = (session_id, instance_id)
    if client.session(key) is None:
        return jsonify({"error": "unknown_session"}), 404
    raw_after = request.args.get("after")
    if raw_after is None:
        raw_after = request.headers.get("Last-Event-ID")
    if raw_after is None:
        after_seq = 0
    else:
        after_seq, _, error = parse_paging({"after": raw_after})
        if error is not None:
            return jsonify({"error": error}), 400
    return _stream_response(build_session_stream(client, key, after_seq))
