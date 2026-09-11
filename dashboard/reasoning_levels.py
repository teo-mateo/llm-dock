"""Per-service reasoning levels: declaration grammar, lookup and wire mapping.

Pure module, and the single owner of what a declared level means, so validation,
payload exposure and request construction cannot disagree. Levels are declared by
the operator rather than offered by llm-dock because the accepted tokens are a
property of each model's chat template -- see
``docs/reasoning-level-sweep-qwen3.8-27b.md`` for a template that answers an
undeclared level with HTTP 500. Nothing here ever synthesises a token.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

# "off" actively disables thinking; a conversation with no level sends nothing.
OFF_LEVEL = "off"

MAX_LEVELS = 8
MAX_RAW_CHARS = 120
LEVEL_NAME_MAX = 16

# No ':' -- a budget syntax has to fail here, not truncate to the level name.
LEVEL_NAME_RE = re.compile(rf"^[a-z][a-z0-9_-]{{0,{LEVEL_NAME_MAX - 1}}}$")

GRAMMAR_HINT = (
    f"expected a comma-separated list of plain level names "
    f"(lowercase, [a-z][a-z0-9_-] up to {LEVEL_NAME_MAX} chars, "
    f"max {MAX_LEVELS} levels, '{OFF_LEVEL}' reserved); "
    f"token budgets (name:budget) are not supported"
)

# Only these engines have a verified request mapping. Anything else sends
# nothing, deliberately: an unverified field changes behaviour invisibly instead
# of failing.
ENGINE_LLAMACPP = "llamacpp"
ENGINE_VLLM = "vllm"


def _normalize(raw: Any) -> Optional[str]:
    """Declaration with outer whitespace removed; None when none is declared."""
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def validate_levels(raw: Any) -> Tuple[bool, List[str]]:
    """Strict grammar check for a write path: (is_valid, errors).

    Absent/empty is valid -- that is how a service opts out or clears.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return True, []
    if not isinstance(raw, str):
        return False, [f"reasoning_levels must be a string; {GRAMMAR_HINT}"]

    text = raw.strip()
    if len(text) > MAX_RAW_CHARS:
        return False, [
            f"reasoning_levels is too long ({len(text)} chars, max {MAX_RAW_CHARS}); {GRAMMAR_HINT}"
        ]

    errors: List[str] = []
    ids: List[str] = []
    for part in text.split(","):
        name = part.strip()
        if not name:
            errors.append(f"reasoning_levels has an empty entry; {GRAMMAR_HINT}")
            continue
        if ":" in name:
            errors.append(
                f"reasoning_levels entry '{name}': token budgets are not supported; {GRAMMAR_HINT}"
            )
            continue
        if not LEVEL_NAME_RE.match(name):
            # Not normalised: the token is case-sensitive to the chat template.
            errors.append(f"reasoning_levels: invalid level name '{name}'; {GRAMMAR_HINT}")
            continue
        if name in ids:
            errors.append(f"reasoning_levels: duplicate level '{name}'")
            continue
        ids.append(name)

    if len(ids) > MAX_LEVELS:
        errors.append(f"reasoning_levels: too many levels ({len(ids)}), max {MAX_LEVELS}")

    return (len(errors) == 0, errors)


def parse_levels(raw: Any) -> List[Dict[str, str]]:
    """Parse a declaration into ``[{"id": ..., "effort": ...}, ...]``.

    Tolerant: invalid yields ``[]`` rather than raising, since this runs on every
    read of every service. Declaration order is preserved.
    """
    valid, _ = validate_levels(raw)
    if not valid:
        return []
    text = _normalize(raw)
    if text is None:
        return []
    levels = []
    for part in text.split(","):
        name = part.strip()
        if name and not any(existing["id"] == name for existing in levels):
            levels.append({"id": name, "effort": name})
    return levels[:MAX_LEVELS]


def format_levels(levels: Union[List[Dict[str, str]], None]) -> str:
    """Render parsed levels back to the declaration string (empty when none)."""
    if not levels:
        return ""
    return ",".join(level["id"] for level in levels
                 if isinstance(level, dict) and level.get("id"))


def _as_ids(source: Union[str, List[Dict[str, str]], None]) -> List[str]:
    if isinstance(source, str):
        return [level["id"] for level in parse_levels(source)]
    if isinstance(source, list):
        return [level["id"] for level in source if isinstance(level, dict) and level.get("id")]
    return []


def find_level(
    source: Union[str, List[Dict[str, str]], None], level_id: Any
) -> Optional[Dict[str, str]]:
    """Look up one level by id in a declaration (raw string or parsed list).

    None when the id is not offered; the caller decides what a miss means.
    """
    if not isinstance(level_id, str) or not level_id:
        return None
    ids = _as_ids(source)
    if level_id not in ids:
        return None
    return {"id": level_id, "effort": level_id}


def request_fields(level: Any, engine: Optional[str]) -> Dict[str, Any]:
    """Request-body fields for one level on one engine; ``{}`` changes nothing."""
    level_id = level.get("id") if isinstance(level, dict) else level
    if not level_id or not engine:
        return {}
    if engine == ENGINE_LLAMACPP:
        # Request-level chat_template_kwargs merge over the --chat-template-kwargs
        # server default, so a ladder edit needs no container restart. `off` sends
        # both fields: templates disagree on which they honor.
        if level_id == OFF_LEVEL:
            return {
                "reasoning_effort": "none",
                "chat_template_kwargs": {"enable_thinking": False},
            }
        return {"reasoning_effort": level_id}
    if engine == ENGINE_VLLM:
        # vLLM derives enable_thinking from reasoning_effort itself: one field.
        return {"reasoning_effort": "none" if level_id == OFF_LEVEL else level_id}
    return {}
