import logging
from datetime import datetime
from flask import Blueprint, jsonify

from auth import require_auth
from docker_utils import check_docker, check_nvidia_smi, get_image_build_metadata
from model_discovery import discover_all_models, get_disk_usage

logger = logging.getLogger(__name__)

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint - no authentication required"""
    return jsonify(
        {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "docker_available": check_docker(),
            "nvidia_available": check_nvidia_smi(),
        }
    )


@system_bp.route("/api/auth/verify", methods=["POST"])
@require_auth
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({"valid": True, "message": "Token is valid"})


@system_bp.route("/api/images/metadata", methods=["GET"])
@require_auth
def get_images_metadata():
    """Return build metadata for llm-dock images"""
    return jsonify(
        {
            "llamacpp": get_image_build_metadata("llm-dock-llamacpp"),
            "vllm": get_image_build_metadata("llm-dock-vllm"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@system_bp.route("/api/system/info", methods=["GET"])
@require_auth
def get_system_info():
    """Get system information including models and disk usage"""
    try:
        disk = get_disk_usage()
        models = discover_all_models()
        total_model_size = sum(m["size"] for m in models)

        return jsonify(
            {
                "disk": disk,
                "models": models,
                "model_count": len(models),
                "total_model_size": total_model_size,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )

    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return jsonify({"error": f"Failed to retrieve system information: {e}"}), 500
