#!/usr/bin/env python3
import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import current_app, jsonify, request

import pyotp

import config

logger = logging.getLogger(__name__)

# Session store for short-lived TOTP tokens: token -> expiry_timestamp
_totp_sessions: dict[str, datetime] = {}

TOTP_TOKEN_EXPIRY_SECONDS = 300  # 5 minutes


def verify_totp_code(code: str) -> bool:
    """Verify a TOTP code against the configured secret."""
    if not config.TOTP_SECRET:
        return False
    totp = pyotp.TOTP(config.TOTP_SECRET)
    return totp.verify(code)


def require_auth(f):
    """Authentication decorator that accepts bearer token or TOTP code."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try bearer token first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

            # Check if this is a short-lived TOTP session token
            if token.startswith("totp-"):
                expiry = _totp_sessions.get(token)
                if expiry and expiry > datetime.now(timezone.utc):
                    return f(*args, **kwargs)
                else:
                    _totp_sessions.pop(token, None)
                    return jsonify({"error": "TOTP session expired"}), 401

            # Check against configured credentials
            dashboard_token = current_app.config["DASHBOARD_TOKEN"]
            if secrets.compare_digest(token, dashboard_token):
                return f(*args, **kwargs)

        # Try TOTP code via X-TOTP-Code header
        totp_code = request.headers.get("X-TOTP-Code")
        if totp_code:
            if verify_totp_code(totp_code):
                # Issue short-lived token for convenience
                short_token = f"totp-{secrets.token_urlsafe(16)}"
                _totp_sessions[short_token] = (
                    datetime.now(timezone.utc) + timedelta(seconds=TOTP_TOKEN_EXPIRY_SECONDS)
                )
                response = f(*args, **kwargs)
                if isinstance(response, tuple):
                    resp, status = response
                    resp.headers["X-TOTP-Token"] = short_token
                    return resp, status
                else:
                    response.headers["X-TOTP-Token"] = short_token
                    return response

        logger.warning(f"Authentication failed from {request.remote_addr}")
        return (
            jsonify(
                {
                    "error": "Authentication failed",
                    "hint": "Provide 'Authorization: Bearer <token>' or 'X-TOTP-Code' header",
                }
            ),
            401,
        )

    return decorated_function
