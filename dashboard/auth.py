#!/usr/bin/env python3
import logging
import secrets
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from functools import wraps

import pyotp
from flask import current_app, g, jsonify, make_response, request, send_from_directory

import config
from page_paths import PageAccess, is_page_path, page_access

logger = logging.getLogger(__name__)

# Session store for short-lived TOTP tokens: token -> expiry_timestamp
_totp_sessions: OrderedDict[str, datetime] = OrderedDict()
MAX_SESSIONS = 1000

TOTP_TOKEN_EXPIRY_SECONDS = 28800  # 8 hours

SESSION_COOKIE_NAME = "llm_dock_session"
SESSION_COOKIE_PATH = "/"


def _cleanup_sessions():
    """Remove expired entries and evict oldest if over capacity."""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _totp_sessions.items() if v <= now]
    for k in expired:
        del _totp_sessions[k]
    while len(_totp_sessions) > MAX_SESSIONS:
        _totp_sessions.popitem(last=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_session() -> str:
    token = f"totp-{secrets.token_urlsafe(16)}"
    _totp_sessions[token] = _now() + timedelta(seconds=TOTP_TOKEN_EXPIRY_SECONDS)
    return token


def session_valid(token: str) -> bool:
    if not token:
        return False
    expiry = _totp_sessions.get(token)
    return bool(expiry and expiry > _now())


def touch_session(token: str) -> bool:
    if not session_valid(token):
        _totp_sessions.pop(token, None)
        return False
    _totp_sessions[token] = _now() + timedelta(seconds=TOTP_TOKEN_EXPIRY_SECONDS)
    return True


def revoke_session(token: str) -> None:
    if token and token.startswith("totp-"):
        _totp_sessions.pop(token, None)


def verify_totp_code(code: str) -> bool:
    """Verify a TOTP code against the configured secret."""
    if not config.TOTP_SECRET:
        return False
    totp = pyotp.TOTP(config.TOTP_SECRET)
    return totp.verify(code)


def _cookie_secure() -> bool:
    if request.is_secure:
        return True
    if not config.TRUST_PROXY_HEADERS:
        return False
    proto = request.headers.get("X-Forwarded-Proto", "")
    return proto.split(",")[0].strip().lower() == "https"


def set_session_cookie(response, token: str):
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=TOTP_TOKEN_EXPIRY_SECONDS,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        samesite="Strict",
        secure=_cookie_secure(),
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        samesite="Strict",
        secure=_cookie_secure(),
    )
    return response


def login_page():
    response = make_response(send_from_directory("static", "login.html"))
    response.headers["Cache-Control"] = "no-store"
    return response


def _unauthorized_401():
    response = jsonify({"error": "Authentication required"})
    response.status_code = 401
    response.headers["Cache-Control"] = "no-store"
    return response


def install(app):
    @app.before_request
    def _page_guard():
        if request.method == "OPTIONS":
            return None
        token = request.cookies.get(SESSION_COOKIE_NAME)
        authenticated = bool(token) and touch_session(token)
        decision = page_access(request.path, authenticated=authenticated)
        if decision is PageAccess.LOGIN:
            if request.method not in ("GET", "HEAD"):
                return _unauthorized_401()
            return login_page()
        if decision is PageAccess.UNAUTHORIZED:
            return _unauthorized_401()
        if authenticated and request.method in ("GET", "HEAD") and is_page_path(request.path):
            g.session_token = token
        return None

    @app.after_request
    def _session_cookie(response):
        token = getattr(g, "session_token", None)
        if token and request.cookies.get(SESSION_COOKIE_NAME) == token:
            set_session_cookie(response, token)
        if is_page_path(request.path) and response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response


def require_auth(f):
    """Authentication decorator that accepts bearer token or TOTP code."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        _cleanup_sessions()

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

            if token.startswith("totp-"):
                if touch_session(token):
                    g.session_token = token
                    logger.debug("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, token[:8])
                    return f(*args, **kwargs)
                return jsonify({"error": "TOTP session expired"}), 401

            dashboard_token = current_app.config["DASHBOARD_TOKEN"]
            if secrets.compare_digest(token, dashboard_token):
                logger.debug("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, token[:8])
                return f(*args, **kwargs)

        totp_code = request.headers.get("X-TOTP-Code")
        if totp_code and verify_totp_code(totp_code):
            short_token = issue_session()
            g.session_token = short_token
            logger.debug("Authenticated request from %s to %s (token: %s...)", request.remote_addr, request.path, short_token[:8])
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
