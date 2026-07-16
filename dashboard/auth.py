#!/usr/bin/env python3
import logging
import secrets
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import current_app, jsonify, make_response, request

import pyotp

import config

logger = logging.getLogger(__name__)

# Session store for short-lived TOTP tokens: token -> expiry_timestamp
_totp_sessions: OrderedDict[str, datetime] = OrderedDict()
MAX_SESSIONS = 1000

TOTP_TOKEN_EXPIRY_SECONDS = 28800  # 8 hours


def _cleanup_sessions():
    """Remove expired entries and evict oldest if over capacity."""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _totp_sessions.items() if v <= now]
    for k in expired:
        del _totp_sessions[k]
    while len(_totp_sessions) > MAX_SESSIONS:
        _totp_sessions.popitem(last=False)


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
        _cleanup_sessions()

        # Try bearer token first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

            # Check if this is a short-lived TOTP session token
            if token.startswith("totp-"):
                expiry = _totp_sessions.get(token)
                if expiry and expiry > datetime.now(timezone.utc):
                    # Extend expiry (sliding window) without rotating the
                    # token, so concurrent requests with the same token
                    # all succeed.
                    _totp_sessions[token] = (
                        datetime.now(timezone.utc) + timedelta(seconds=TOTP_TOKEN_EXPIRY_SECONDS)
                    )
                    logger.info("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, token[:8])
                    return f(*args, **kwargs)
                else:
                    _totp_sessions.pop(token, None)
                    return jsonify({"error": "TOTP session expired"}), 401

            # Check against configured credentials
            dashboard_token = current_app.config["DASHBOARD_TOKEN"]
            if secrets.compare_digest(token, dashboard_token):
                logger.info("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, token[:8])
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
                logger.info("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, short_token[:8])
                response = make_response(f(*args, **kwargs))
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
