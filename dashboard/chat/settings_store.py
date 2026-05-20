"""Persistent chat settings (singleton).

Currently holds one value: the user-customized default
``main_system_prompt`` used for new conversations. If the setting is
absent (or the settings file does not exist or fails to parse), the
built-in ``DEFAULT_MAIN_SYSTEM_PROMPT`` from ``constants.py`` is used.
This lets the dashboard surface the default prompt as something the user
can edit without a code change + service restart.

Storage: a single JSON file (``dashboard/chat_settings.json`` by
default), one top-level object. Written atomically via tempfile + fsync +
``os.replace``. The path is overridable through
``LLM_DOCK_CHAT_SETTINGS_FILE`` so tests can point at a tmp directory.

Existing conversations are unaffected — they carry their own copy of
``main_system_prompt`` in the chat DB, and ``create_conversation`` only
reads this module's value at insert time when the client did not pass an
explicit prompt.
"""

import json
import logging
import os
import tempfile
import threading

from .constants import DEFAULT_MAIN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chat_settings.json",
)

# Serializes reads and writes within one process. The atomic on-disk
# replace is what makes the file safe against external readers; this lock
# is only here so concurrent in-process writers can't lose updates by
# racing read-modify-write.
_lock = threading.Lock()


def settings_file_path() -> str:
    """Return the path of the settings file, honoring the env override."""
    return os.environ.get("LLM_DOCK_CHAT_SETTINGS_FILE", _DEFAULT_PATH)


def _load_unlocked() -> dict:
    path = settings_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("chat_settings: cannot read %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "chat_settings: %s top-level must be a JSON object; ignoring", path
        )
        return {}
    return data


def _save_unlocked(data: dict) -> None:
    path = settings_file_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".chat_settings.", suffix=".json.tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def get_main_system_prompt() -> str:
    """Return the customized default prompt, or the built-in if not set."""
    with _lock:
        data = _load_unlocked()
    value = data.get("main_system_prompt")
    if isinstance(value, str) and value:
        return value
    return DEFAULT_MAIN_SYSTEM_PROMPT


def is_main_system_prompt_customized() -> bool:
    """True if a non-empty override is stored AND differs from the built-in."""
    with _lock:
        data = _load_unlocked()
    value = data.get("main_system_prompt")
    return (
        isinstance(value, str)
        and value != ""
        and value != DEFAULT_MAIN_SYSTEM_PROMPT
    )


def set_main_system_prompt(content: str) -> None:
    """Persist ``content`` as the default prompt for new conversations.

    Raises ``TypeError`` if not a string, ``ValueError`` if empty/whitespace.
    """
    if not isinstance(content, str):
        raise TypeError("main_system_prompt must be a string")
    if not content.strip():
        raise ValueError("main_system_prompt must not be empty")
    with _lock:
        data = _load_unlocked()
        data["main_system_prompt"] = content
        _save_unlocked(data)


def reset_main_system_prompt() -> None:
    """Remove any stored override so new conversations get the built-in."""
    with _lock:
        data = _load_unlocked()
        if "main_system_prompt" not in data:
            return
        del data["main_system_prompt"]
        if data:
            _save_unlocked(data)
            return
        # File would be empty after the delete — unlink it so a fresh load
        # has nothing to read at all.
        path = settings_file_path()
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError as e:
                logger.warning("chat_settings: cannot unlink %s: %s", path, e)
