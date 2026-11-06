from typing import Any, Dict

STATES = frozenset({"idle", "working"})


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_nullable_str(value: Any) -> bool:
    return value is None or isinstance(value, str)


def is_nullable_number(value: Any) -> bool:
    return value is None or is_number(value)


def is_model(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return isinstance(value.get("provider"), str) and isinstance(value.get("id"), str)


def is_nullable_model(value: Any) -> bool:
    return value is None or is_model(value)


def is_usage(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key in ("input", "output", "cache_read", "cache_write", "total_tokens"):
        if not is_number(value.get(key)):
            return False
    return is_nullable_number(value.get("reasoning")) and is_nullable_number(value.get("cost_total"))


def is_nullable_usage(value: Any) -> bool:
    return value is None or is_usage(value)

PROMPT_KINDS = frozenset({"confirm", "select", "input", "approval"})
PROMPT_SOURCES = frozenset({"terminal", "remote"})
PROMPT_REASONS = frozenset({"answered", "cancelled", "expired"})
APPROVAL_CHOICES = frozenset({"allow_once", "allow_session", "deny"})
PROMPT_MESSAGE_MAX = 4000
PROMPT_OPTIONS_MAX = 32


def is_str_array(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_prompt_value(value: Any) -> bool:
    if isinstance(value, bool) or isinstance(value, str):
        return True
    if not isinstance(value, dict):
        return False
    return value.get("choice") in APPROVAL_CHOICES and is_nullable_str(value.get("reason"))


def is_prompt_open_body(body: Dict[str, Any]) -> bool:
    options = body.get("options")
    return (
        isinstance(body.get("prompt_id"), str)
        and bool(body["prompt_id"])
        and body.get("kind") in PROMPT_KINDS
        and is_nullable_str(body.get("title"))
        and is_nullable_str(body.get("message"))
        and is_str_array(options)
        and len(options or []) <= PROMPT_OPTIONS_MAX
        and isinstance(body.get("allow_free_text"), bool)
        and is_nullable_number(body.get("timeout_ms"))
    )


def is_prompt_closed_body(body: Dict[str, Any]) -> bool:
    return (
        isinstance(body.get("prompt_id"), str)
        and bool(body["prompt_id"])
        and body.get("reason") in PROMPT_REASONS
        and (body.get("value") is None or is_prompt_value(body.get("value")))
        and (body.get("answered_by") is None or body.get("answered_by") in PROMPT_SOURCES)
    )


def is_prompt_body(event_type: str, body: Dict[str, Any]) -> bool:
    if event_type == "prompt_open":
        return is_prompt_open_body(body)
    return is_prompt_closed_body(body)
