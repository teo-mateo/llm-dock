import json
import logging

from flask import Blueprint, current_app, jsonify, request

from auth import require_auth
from inspector.db import InspectorDB
from inspector.supervisor import proxy_supervisor

logger = logging.getLogger(__name__)

inspector_bp = Blueprint("inspector", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _inspector_db() -> InspectorDB:
    # App config wins so tests can inject a scratch DB; the supervisor's
    # instance is the production path and the one the proxies write into.
    try:
        db = current_app.config.get("INSPECTOR_DB")
    except RuntimeError:
        db = None
    if db is None:
        db = proxy_supervisor.db
    return db


def _summary_row(capture) -> dict:
    # The body fields are intentionally absent: the list must not pay for
    # megabytes it won't render (#235's summary read).
    return {
        "id": capture.id,
        "service_name": capture.service_name,
        "model": capture.model,
        "template_type": capture.template_type,
        "method": capture.method,
        "path": capture.path,
        "status_code": capture.status_code,
        "stream": capture.stream,
        "finish_reason": capture.finish_reason,
        "prompt_tokens": capture.prompt_tokens,
        "completion_tokens": capture.completion_tokens,
        "total_tokens": capture.total_tokens,
        "ttfb_ms": capture.ttfb_ms,
        "duration_ms": capture.duration_ms,
        "error": capture.error,
        "request_truncated": capture.request_truncated,
        "response_truncated": capture.response_truncated,
        "created_at": capture.created_at,
    }


def _detail_row(capture) -> dict:
    headers = capture.request_headers_json
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except ValueError:
            headers = {}
    if not isinstance(headers, dict):
        headers = {}

    tool_calls = []
    if capture.tool_calls_json:
        try:
            parsed = json.loads(capture.tool_calls_json)
            if isinstance(parsed, list):
                tool_calls = parsed
        except ValueError:
            tool_calls = []

    return {
        **_summary_row(capture),
        "request_headers": headers,
        # Verbatim as sent: a malformed or truncated body must still be
        # fetchable and displayable, so it is never re-parsed.
        "request_body": capture.request_body,
        "response_body": capture.response_body,
        "response_text": capture.response_text,
        "reasoning_text": capture.reasoning_text,
        "tool_calls": tool_calls,
    }


@inspector_bp.route("/api/inspector/captures", methods=["GET"])
@require_auth
def list_captures():
    raw_limit = request.args.get("limit")
    raw_offset = request.args.get("offset")
    limit = DEFAULT_LIMIT
    offset = 0
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except ValueError:
            return jsonify({"error": "limit must be an integer"}), 400
        if limit < 1:
            return jsonify({"error": "limit must be at least 1"}), 400
    limit = min(limit, MAX_LIMIT)
    if raw_offset is not None:
        try:
            offset = int(raw_offset)
        except ValueError:
            return jsonify({"error": "offset must be an integer"}), 400
        if offset < 0:
            return jsonify({"error": "offset must be non-negative"}), 400

    service = request.args.get("service") or None
    db = _inspector_db()
    rows, total = db.list_captures(service=service, limit=limit, offset=offset)
    return jsonify(
        {
            "captures": [_summary_row(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@inspector_bp.route("/api/inspector/captures/<capture_id>", methods=["GET"])
@require_auth
def get_capture(capture_id):
    db = _inspector_db()
    capture = db.get_capture(capture_id)
    if capture is None:
        return jsonify({"error": f"Capture '{capture_id}' not found"}), 404
    return jsonify(_detail_row(capture))


@inspector_bp.route("/api/inspector/captures/<capture_id>", methods=["DELETE"])
@require_auth
def delete_capture(capture_id):
    db = _inspector_db()
    if not db.delete_capture(capture_id):
        return jsonify({"error": f"Capture '{capture_id}' not found"}), 404
    return jsonify({"deleted": 1})


@inspector_bp.route("/api/inspector/captures", methods=["DELETE"])
@require_auth
def delete_captures():
    db = _inspector_db()
    service = request.args.get("service") or None
    deleted = db.delete_captures(service)
    return jsonify({"deleted": deleted})


@inspector_bp.route("/api/inspector/services", methods=["GET"])
@require_auth
def inspector_services():
    db = _inspector_db()
    proxy_rows = proxy_supervisor.status()
    names = set(db.services_with_captures())
    names.update(row["service"] for row in proxy_rows)

    services = []
    for name in sorted(names):
        proxy_row = next((row for row in proxy_rows if row["service"] == name), None)
        services.append(
            {
                "service_name": name,
                "capture_count": db.list_captures(service=name, limit=1)[1],
                "inspect": proxy_row is not None,
                "listen_port": proxy_row["listen_port"] if proxy_row else None,
                "upstream_port": proxy_row["upstream_port"] if proxy_row else None,
                "proxy_running": bool(proxy_row and proxy_row["running"]),
                "error": proxy_row["error"] if proxy_row else None,
            }
        )
    return jsonify({"services": services})
