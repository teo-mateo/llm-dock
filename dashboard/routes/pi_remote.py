from flask import Blueprint, jsonify, request

from auth import require_auth
from pi_remote.api_json import page_json, parse_paging, summary_json
from pi_remote.supervisor import pi_remote_supervisor

pi_remote_bp = Blueprint("pi_remote", __name__)


@pi_remote_bp.route("/api/pi/sessions", methods=["GET"])
@require_auth
def sessions():
    return jsonify(
        {"sessions": [summary_json(summary) for summary in pi_remote_supervisor.sessions()]}
    )


@pi_remote_bp.route(
    "/api/pi/sessions/<session_id>/<instance_id>/events", methods=["GET"]
)
@require_auth
def session_events(session_id, instance_id):
    after_seq, limit, error = parse_paging(request.args)
    if error is not None:
        return jsonify({"error": error}), 400
    page = pi_remote_supervisor.events(session_id, instance_id, after_seq, limit)
    if page is None:
        return jsonify({"error": "unknown_session"}), 404
    return jsonify(page_json(page))
