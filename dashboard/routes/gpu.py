import json
import logging
import time
from datetime import datetime
from flask import Blueprint, Response, jsonify, request, stream_with_context

from auth import require_auth
from docker_utils import get_gpu_stats

logger = logging.getLogger(__name__)

gpu_bp = Blueprint("gpu", __name__)


@gpu_bp.route("/api/gpu", methods=["GET"])
@require_auth
def gpu_stats():
    """Get GPU statistics"""
    try:
        gpus = get_gpu_stats()
        return jsonify({"gpus": gpus, "timestamp": datetime.utcnow().isoformat() + "Z"})
    except Exception as e:
        logger.error(f"Failed to get GPU stats: {e}")
        return jsonify({"error": f"Failed to retrieve GPU information: {e}"}), 500


@gpu_bp.route("/api/gpu/stream", methods=["GET"])
@require_auth
def gpu_stream():
    """Stream GPU statistics over Server-Sent Events."""
    try:
        interval = float(request.args.get("interval", 3.0))
    except (TypeError, ValueError):
        interval = 3.0
    interval = max(0.5, min(interval, 10.0))

    def generate():
        try:
            while True:
                try:
                    gpus = get_gpu_stats()
                    payload = {
                        "gpus": gpus,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                except Exception as e:
                    logger.error(f"gpu stream tick failed: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(interval)
        except GeneratorExit:
            return

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
