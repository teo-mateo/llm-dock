from flask import Response, jsonify, stream_with_context

from .outcomes import PolicyError


def error_response(error: PolicyError):
    return jsonify(error.body()), error.status


def sse_response(observer):
    return Response(
        stream_with_context(observer),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
