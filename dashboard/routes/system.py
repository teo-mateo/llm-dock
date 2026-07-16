import logging
import secrets
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request

import config as config_module
import pyotp

from auth import require_auth, _totp_sessions, TOTP_TOKEN_EXPIRY_SECONDS
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


@system_bp.route("/api/auth/login", methods=["POST"])
def login_with_totp():
    """Unauthenticated TOTP login endpoint.

    Accepts X-TOTP-Code header, verifies against configured secret,
    and returns a short-lived convenience token for subsequent requests.
    """
    totp_code = request.headers.get("X-TOTP-Code")
    if not totp_code:
        return jsonify({"error": "Missing X-TOTP-Code header"}), 400

    if not config_module.TOTP_SECRET:
        return jsonify({"error": "TOTP is not configured"}), 400

    totp = pyotp.TOTP(config_module.TOTP_SECRET)
    if not totp.verify(totp_code):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Issue short-lived token for convenience
    short_token = f"totp-{secrets.token_urlsafe(16)}"
    expiry = datetime.now(timezone.utc) + timedelta(seconds=TOTP_TOKEN_EXPIRY_SECONDS)
    _totp_sessions[short_token] = expiry
    logger.info("TOTP login successful")
    return jsonify({
        "token": short_token,
        "expires_in": TOTP_TOKEN_EXPIRY_SECONDS,
    })


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
            "ds4": get_image_build_metadata("llm-dock-ds4"),
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
