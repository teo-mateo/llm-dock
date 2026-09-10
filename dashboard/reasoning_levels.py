"""Per-service reasoning levels: declaration grammar, lookup and wire mapping.

Pure module — no disk I/O, no Flask, no Docker. It owns the whole lifecycle of a
reasoning level so the three places that touch one (config validation, service
payload exposure, request construction) cannot disagree about what a declared
level means:

    services.json  "reasoning_levels": "off,low,medium,xhigh"
        -> validate_levels()  on every config write
        -> parse_levels()     on every read, exposed on the service payload
        -> find_level()       on conversation write and again at run creation
        -> request_fields()   at request-build time, per engine

Why the operator declares levels instead of llm-dock offering a fixed ladder:
the accepted tokens are a property of each model's chat template, not of
llm-dock. ``docs/reasoning-level-sweep-qwen3.8-27b.md`` shows the Qwen3.8
template answering an undeclared level with HTTP 500. So this module never
synthesises a token — it only forwards what was declared.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

# Reserved id: "actively disable thinking", not "say nothing". A conversation
# with no level stores NULL and sends nothing at all; "off" is an instruction.
OFF_LEVEL = "off"

MAX_LEVELS = 8
MAX_RAW_CHARS = 120
LEVEL_NAME_MAX = 16

# Plain names only: lowercase, must start with a letter. No ':' — a future
# token-budget syntax (`low:512`) must fail loudly here rather than be
# silently truncated to `low`.
LEVEL_NAME_RE = re.compile(rf"^[a-z][a-z0-9_-]{{0,{LEVEL_NAME_MAX - 1}}}$")

GRAMMAR_HINT = (
    f"expected a comma-separated list of plain level names "
    f"(lowercase, [a-z][a-z0-9_-] up to {LEVEL_NAME_MAX} chars, "
    f"max {MAX_LEVELS} levels, '{OFF_LEVEL}' reserved); "
    f"token budgets (name:budget) are not supported"
)

# Engines with a verified request-level mapping. Anything absent from this table
# — ik_llamacpp, tabbyapi, ds4, OpenRouter, unknown — sends nothing, on purpose:
# an unverified mapping is worse than no mapping, because a wrong field can
# change behaviour invisibly instead of failing.
ENGINE_LLAMACPP = "llamacpp"
ENGINE_VLLM = "vllm"


def _normalize(raw: Any) -> Optional[str]:
    """Return the declaration with outer whitespace removed, or None when the
    entry declares no levels (missing key, empty, whitespace-only, or a
    non-string, which is treated as absent here — callers that must reject it
    use validate_levels)."""
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def validate_levels(raw: Any) -> Tuple[bool, List[str]]:
    """Strict grammar check for a write path.

    Returns (is_valid, errors). Absent/empty declarations are valid — that is
    how a service opts out, and how an edit clears the feature.
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
            # Deliberately not normalised: level tokens are case-sensitive to
            # the chat template, so "Low" would be sent as "low" and rejected
            # (or silently accepted) by the model rather than fixed here.
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

    Tolerant by design — this runs on every read of every service, and a
    hand-edited ``services.json`` must not break the Services page. Anything
    invalid yields ``[]`` (validate_levels owns the rejection, at write time).
    Declaration order is preserved: that is the UI order.
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

    Returns the level dict, or None when the id is not offered. The caller
    decides what a miss means — a 400 on a conversation write, or dropping the
    level for one run.
    """
    if not isinstance(level_id, str) or not level_id:
        return None
    ids = _as_ids(source)
    if level_id not in ids:
        return None
    return {"id": level_id, "effort": level_id}


def request_fields(level: Any, engine: Optional[str]) -> Dict[str, Any]:
    """Request-body fields for one level on one engine.

    ``{}`` means "change nothing", which is what every unmapped engine and
    every unmapped level returns, so an unselected level leaves the outgoing
    request byte-identical to the pre-feature payload.
    """
    level_id = level.get("id") if isinstance(level, dict) else level
    if not level_id or not engine:
        return {}
    if engine == ENGINE_LLAMACPP:
        # llama.cpp reads a request-level reasoning_effort and merges request
        # chat_template_kwargs OVER the --chat-template-kwargs server default
        # (server-common.cpp:1308-1311), so an edit needs no container restart.
        # `off` sends both fields because templates differ: the server parses
        # enable_thinking itself (:1315-1322) while some templates only honor
        # the kwarg, and reasoning_effort="none" erases the effort kwarg
        # (:1329) — the one state the sweep measured as reliably silent.
        if level_id == OFF_LEVEL:
            return {
                "reasoning_effort": "none",
                "chat_template_kwargs": {"enable_thinking": False},
            }
        return {"reasoning_effort": level_id}
    if engine == ENGINE_VLLM:
        # vLLM passes reasoning_effort into the template kwargs and derives
        # enable_thinking itself (protocol.py:574-592), so one field is enough.
        return {"reasoning_effort": "none" if level_id == OFF_LEVEL else level_id}
    return {}
