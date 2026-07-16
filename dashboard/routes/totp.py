#!/usr/bin/env python3
import base64
import io
import logging
from flask import Blueprint, jsonify, request
import pyotp

import config
from auth import require_auth

totp_bp = Blueprint("totp", __name__, url_prefix="/api/totp")

logger = logging.getLogger(__name__)


@totp_bp.route("/setup", methods=["POST"])
@require_auth
def setup():
    """Generate a new TOTP secret and return QR code data for setup."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name="llm-dock", issuer_name="LLM-Dock"
    )

    qr_base64 = ""
    try:
        import qrcode

        qr_code = qrcode.make(provisioning_uri)
        buffer = io.BytesIO()
        qr_code.save(buffer, "PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    except ImportError:
        logger.warning("qrcode package not available, returning base32 secret only")

    return (
        jsonify(
            {
                "secret": secret,
                "provisioning_uri": provisioning_uri,
                "qr_code": qr_base64,
                "message": (
                    "Scan the QR code with your authenticator app, or manually "
                    "enter the secret. After scanning, call POST /api/totp/verify "
                    "with a 6-digit code to complete setup."
                ),
            }
        ),
        200,
    )


@totp_bp.route("/verify", methods=["POST"])
@require_auth
def verify():
    """Verify a TOTP code and persist the secret if valid."""
    data = request.get_json(silent=True)
    if not data or "totp_code" not in data:
        return jsonify({"error": "Missing 'totp_code' in request body"}), 400

    totp_code = data["totp_code"]
    secret = data.get("totp_secret", "")

    if not secret:
        if not config.TOTP_SECRET:
            return (
                jsonify(
                    {
                        "error": "No secret configured. Call POST /api/totp/setup first."
                    }
                ),
                400,
            )
        secret = config.TOTP_SECRET

    totp = pyotp.TOTP(secret)
    if not totp.verify(totp_code):
        return jsonify({"error": "Invalid TOTP code. Please try again."}), 401

    config.set_totp_secret(secret)
    logger.info("TOTP authentication enabled successfully")
    return (
        jsonify(
            {
                "message": "TOTP verification successful. TOTP authentication is now enabled.",
                "status": "enabled",
            }
        ),
        200,
    )


@totp_bp.route("/status", methods=["GET"])
@require_auth
def status():
    """Check whether TOTP is configured."""
    return (
        jsonify(
            {
                "enabled": bool(config.TOTP_SECRET),
                "message": (
                    "TOTP is configured" if config.TOTP_SECRET else "TOTP is not configured"
                ),
            }
        ),
        200,
    )


@totp_bp.route("/disable", methods=["POST"])
@require_auth
def disable():
    """Disable TOTP authentication by removing the stored secret."""
    if not config.TOTP_SECRET:
        return jsonify({"error": "TOTP is not currently configured"}), 400

    config.set_totp_secret("")
    logger.info("TOTP authentication disabled")
    return jsonify({"message": "TOTP authentication has been disabled"}), 200