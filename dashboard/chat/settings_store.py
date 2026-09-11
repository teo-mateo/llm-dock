"""Persistent chat settings (singleton).

Holds user-customized settings that fall back to built-in defaults when
absent (or when the settings file does not exist or fails to parse):

- ``main_system_prompt`` — the default system prompt for new
  conversations (built-in: ``DEFAULT_MAIN_SYSTEM_PROMPT`` in
  ``constants.py``).
- ``openrouter_models`` — the curated OpenRouter model list shown in the
  chat model pickers (built-in: ``DEFAULT_MODELS`` in ``openrouter.py``).

This lets the dashboard surface these as editable without a code change +
service restart.

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
from .openrouter import DEFAULT_MODELS as DEFAULT_OPENROUTER_MODELS

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
    _reset_key("main_system_prompt")


def _reset_key(key: str) -> None:
    """Remove ``key`` from the store, unlinking the file if it ends up empty."""
    with _lock:
        data = _load_unlocked()
        if key not in data:
            return
        del data[key]
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


# -- Curated OpenRouter model list --

def _valid_openrouter_models(value) -> bool:
    """True if ``value`` is a well-formed stored model list (may be empty)."""
    if not isinstance(value, list):
        return False
    seen = set()
    for entry in value:
        if not isinstance(entry, dict):
            return False
        model = entry.get("id")
        if not isinstance(model, str) or not model.strip():
            return False
        label = entry.get("label")
        if label is not None and not isinstance(label, str):
            return False
        if model in seen:
            return False
        seen.add(model)
    return True


def _readable_ladder(value) -> str:
    """A stored ladder that a reader can trust, "" when the stored one cannot.

    Deliberately silent-and-empty rather than raising: on this store a rejected list
    means the whole curated selection silently reverts to the built-in, so a single
    unreadable field must cost one model its control and nothing more. Strictness
    belongs to the write path, where there is someone to tell.
    """
    if not isinstance(value, str) or not value.strip():
        return ""
    from reasoning_levels import validate_levels

    valid, errors = validate_levels(value)
    if not valid:
        logger.warning("openrouter model list: ignoring unreadable ladder %r (%s)", value, errors[0])
        return ""
    return value.strip()


def _normalize_openrouter_models(models: list, ladders: dict | None = None) -> list:
    """Storage shape for the curated list, carrying the ladder from the caller only.

    ``ladders`` is a server-owned channel keyed by model id, and the reason it exists:
    the picker's editor round-trips ``{id, label}`` alone, so a ladder accepted from a
    request body would be a ladder a client invented. Entries keep the field only when
    a caller with catalogue access supplied one.
    """
    normalized = []
    for entry in models:
        record = {
            "id": entry["id"].strip(),
            "label": (entry.get("label") or entry["id"]).strip() or entry["id"].strip(),
        }
        ladder = (ladders or {}).get(record["id"])
        ladder = _readable_ladder(ladder)
        if ladder:
            record["reasoning_levels"] = ladder
        normalized.append(record)
    return normalized


def get_openrouter_models() -> list:
    """Return the customized model list, or the built-in if not set/invalid.

    An empty stored list is honored — it means the user hid every
    OpenRouter model from the picker without unsetting the API key.
    """
    with _lock:
        data = _load_unlocked()
    value = data.get("openrouter_models")
    entries = value if _valid_openrouter_models(value) else [dict(m) for m in DEFAULT_OPENROUTER_MODELS]
    records = []
    for entry in entries:
        entry = dict(entry)
        ladder = _readable_ladder(entry.get("reasoning_levels"))
        # Absent is the representation of "no ladder", so an unreadable stored value
        # loses the key rather than handing back the bytes that failed to parse.
        if ladder:
            entry["reasoning_levels"] = ladder
        else:
            entry.pop("reasoning_levels", None)
        records.append(entry)
    return records


def is_openrouter_models_customized() -> bool:
    """True if a valid override is stored AND selects different models.

    Compared by id, not whole entry: a ladder is derived from the catalogue rather
    than chosen, so once entries carry one, a list naming the built-in models would
    otherwise read as hand-picked forever.
    """
    with _lock:
        data = _load_unlocked()
    value = data.get("openrouter_models")
    if not _valid_openrouter_models(value):
        return False
    return [entry["id"].strip() for entry in value] != [entry["id"].strip() for entry in DEFAULT_OPENROUTER_MODELS]


def set_openrouter_models(models: list, ladders: dict | None = None) -> None:
    """Persist ``models`` as the curated OpenRouter model list.

    Each entry must be a dict with a non-empty string ``id``; ``label`` is
    optional and defaults to the id. An empty list is allowed. Raises
    ``TypeError`` / ``ValueError`` on malformed input.

    ``ladders`` maps model id to a catalogue-derived declaration and is the only way a
    ladder is written. It is merged over the stored ones by id, so an id the caller
    does not mention keeps whatever it had — that is what lets a client that knows
    nothing about ladders reorder the list without wiping them. A key present with an
    empty value clears, which is how a refresh records that a model lost its efforts.
    """
    if not isinstance(models, list):
        raise TypeError("openrouter_models must be a list")
    seen = set()
    for entry in models:
        if not isinstance(entry, dict):
            raise ValueError("each model must be an object with an 'id'")
        model = entry.get("id")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("each model must have a non-empty string 'id'")
        label = entry.get("label")
        if label is not None and not isinstance(label, str):
            raise ValueError("model 'label' must be a string when present")
        if model.strip() in seen:
            raise ValueError(f"duplicate model id: {model.strip()}")
        seen.add(model.strip())
    with _lock:
        data = _load_unlocked()
        stored = data.get("openrouter_models")
        merged = {}
        if _valid_openrouter_models(stored):
            merged = {entry["id"].strip(): entry.get("reasoning_levels") or "" for entry in stored}
        if ladders:
            merged.update({key: value for key, value in ladders.items() if isinstance(key, str)})
        data["openrouter_models"] = _normalize_openrouter_models(models, merged)
        _save_unlocked(data)


def reset_openrouter_models() -> None:
    """Remove any stored override, reverting the picker to the built-in list."""
    _reset_key("openrouter_models")
