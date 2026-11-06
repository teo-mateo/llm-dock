from typing import Any

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
