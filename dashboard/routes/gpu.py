import logging
from datetime import datetime
from flask import Blueprint, jsonify

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
