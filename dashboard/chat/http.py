from flask import Response, jsonify, stream_with_context

from .outcomes import PolicyError


def error_response(error: PolicyError):
    return jsonify(error.body()), error.status


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse_response(body, *, headers=None, wrap=True):
    return Response(
        stream_with_context(body) if wrap else body,
        mimetype="text/event-stream",
        headers={**SSE_HEADERS, **(headers or {})},
    )
