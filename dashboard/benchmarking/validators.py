import re
from typing import Tuple, Optional, Dict

RESERVED_FLAGS = {"-m", "-o"}

# Flags that are benchmark-only and must not be applied to service config
BENCHMARK_ONLY_FLAGS = {"-p", "-n", "-r", "-o", "-m"}

# Valid flag pattern: starts with -, followed by alphanumeric/hyphens
FLAG_PATTERN = re.compile(r"^--?[a-zA-Z][a-zA-Z0-9\-]*$")


def validate_flag_name(flag: str) -> Tuple[bool, Optional[str]]:
    if not flag:
        return False, "Flag name cannot be empty"

    if not flag.startswith("-"):
        return False, f"Flag must start with '-': {flag}"

    if flag in RESERVED_FLAGS:
        return False, f"Reserved flag cannot be overridden: {flag}"

    if not FLAG_PATTERN.match(flag):
        return False, f"Invalid flag format: {flag}"

    return True, None


UNSAFE_VALUE_PATTERN = re.compile(r"[;|`$\n]")


def validate_flag_value(value: str) -> Tuple[bool, Optional[str]]:
    if len(value) > 1024:
        return False, "Value too long (max 1024 characters)"

    if UNSAFE_VALUE_PATTERN.search(value):
        return False, "Unsafe characters in value"

    return True, None


def validate_params(params: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    if not isinstance(params, dict):
        return False, "params must be a JSON object"

    if len(params) > 50:
        return False, "Too many parameters (max 50)"

    for flag, value in params.items():
        valid, error = validate_flag_name(flag)
        if not valid:
            return False, error

        if not isinstance(value, str):
            return False, f"Value for {flag} must be a string"

        valid, error = validate_flag_value(value)
        if not valid:
            return False, error

    return True, None


def validate_service_name(service_name: str) -> Tuple[bool, Optional[str]]:
    if not service_name:
        return False, "service_name is required"

    if not isinstance(service_name, str):
        return False, "service_name must be a string"

    if len(service_name) > 100:
        return False, "service_name too long"

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]*$", service_name):
        return False, "service_name contains invalid characters"

    return True, None
