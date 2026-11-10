import os
import sys
import logging
import logging.handlers
from dotenv import load_dotenv, set_key

# Resolve .env next to this file so it works regardless of CWD.
DOTENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(DOTENV_PATH)

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 3305))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN")
TRUST_PROXY_HEADERS = os.getenv("DASHBOARD_TRUST_PROXY_HEADERS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "../docker-compose.yml")
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT_NAME", "dockerized-models")
GLOBAL_API_KEY = os.getenv("LLM_DOCK_API_KEY")
# Optional. When set, OpenRouter-hosted models become selectable in the chat
# model pickers. Read via ``config.OPENROUTER_API_KEY`` (attribute access).
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# Optional. When set, TOTP (time-based one-time password) authentication is
# enabled alongside the bearer-token method. Read via ``config.TOTP_SECRET``.
TOTP_SECRET = os.getenv("TOTP_SECRET")

DEFAULT_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.log")
DEFAULT_LOG_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 5


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class QuietAccessFilter(logging.Filter):
    """Drops werkzeug access lines for successful requests; 4xx/5xx still pass."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not (isinstance(record.msg, str) and record.msg.rstrip().endswith('"%s" %s %s')):
            return True
        if not (isinstance(args, tuple) and len(args) == 3):
            return True
        return str(args[1])[:1] not in ("1", "2", "3")


def set_global_api_key(new_key: str, dotenv_path: str = DOTENV_PATH):
    """Persist a new global API key to .env and update the in-process value.

    Other modules must reference ``config.GLOBAL_API_KEY`` (not a name imported
    via ``from config import GLOBAL_API_KEY``) to observe the rotated value
    without a process restart.
    """
    global GLOBAL_API_KEY
    set_key(dotenv_path, "LLM_DOCK_API_KEY", new_key)
    GLOBAL_API_KEY = new_key
    return new_key


def set_totp_secret(new_secret: str, dotenv_path: str = DOTENV_PATH):
    """Persist a new TOTP secret to .env and update the in-process value.

    Other modules must reference ``config.TOTP_SECRET`` (not a name imported
    via ``from config import TOTP_SECRET``) to observe the rotated value
    without a process restart.
    """
    global TOTP_SECRET
    set_key(dotenv_path, "TOTP_SECRET", new_secret)
    TOTP_SECRET = new_secret
    return new_secret


_config_initialized = False


def init_config():
    """Validate config and set up logging. Called from the app factory. Idempotent."""
    global _config_initialized
    if _config_initialized:
        return

    if not DASHBOARD_TOKEN:
        raise ValueError("DASHBOARD_TOKEN environment variable is required")

    # Configure logging with file and console handlers
    log_level = getattr(logging, LOG_LEVEL)
    log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        os.getenv("DASHBOARD_LOG_FILE", DEFAULT_LOG_FILE),
        maxBytes=_env_int("DASHBOARD_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES),
        backupCount=_env_int("DASHBOARD_LOG_BACKUPS", DEFAULT_LOG_BACKUPS),
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(log_format)

    # Console handler: sys.__stderr__ survives pytest's capture buffers, which
    # are closed before atexit handlers run and would make the exit-time stop
    # logs raise "I/O operation on closed file".
    console_handler = logging.StreamHandler(sys.__stderr__)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    werkzeug_logger = logging.getLogger("werkzeug")
    if not any(isinstance(f, QuietAccessFilter) for f in werkzeug_logger.filters):
        werkzeug_logger.addFilter(QuietAccessFilter())

    # Set only after validation and handler setup have both succeeded, so a
    # failed first call can't disable re-validation (and logging setup) for
    # the rest of the process.
    _config_initialized = True
