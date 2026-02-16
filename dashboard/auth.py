import logging
import secrets
from datetime import datetime
from functools import wraps
from flask import current_app, jsonify, request

logger = logging.getLogger(__name__)


def require_auth(f):
    """Decorator to require authentication for endpoints"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(f"Missing Authorization header from {request.remote_addr}")
            return jsonify(
                {
                    "error": {
                        "code": "MISSING_TOKEN",
                        "message": "Authorization header is required",
                    },
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ), 401

        if not auth_header.startswith("Bearer "):
            logger.warning(
                f"Invalid Authorization header format from {request.remote_addr}"
            )
            return jsonify(
                {
                    "error": {
                        "code": "INVALID_FORMAT",
                        "message": "Authorization header must be: Bearer <token>",
                    },
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ), 401

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        dashboard_token = current_app.config["DASHBOARD_TOKEN"]

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(token, dashboard_token):
            logger.warning(f"Invalid token attempt from {request.remote_addr}")
            return jsonify(
                {
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "Authentication failed",
                    },
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ), 401

        logger.debug(
            f"Authenticated request to {request.path} from {request.remote_addr}"
        )
        return f(*args, **kwargs)

    return decorated_function
