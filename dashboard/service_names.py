import re
from typing import Collection

SERVICE_NAME_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*")
SERVICE_NAME_ERROR = (
    "Service name must start with a letter or digit and contain only "
    "alphanumerics, hyphens, underscores or dots"
)
MAX_SERVICE_NAME_LENGTH = 63


def valid_service_name(name: str) -> bool:
    return SERVICE_NAME_PATTERN.fullmatch(name) is not None


def validate_rename(old_name: str, new_name: str, existing: Collection[str]) -> str | None:
    """The reason a rename must be refused, or None. Pure: the caller supplies
    the names that exist, so it can run before any side effect."""
    if not new_name:
        return "Service name cannot be empty"
    if len(new_name) > MAX_SERVICE_NAME_LENGTH:
        return f"Service name too long (max {MAX_SERVICE_NAME_LENGTH} characters)"
    if not valid_service_name(new_name):
        return SERVICE_NAME_ERROR
    if old_name not in existing:
        return f"Service '{old_name}' not found in database"
    if new_name in existing:
        return f"Service '{new_name}' already exists"
    return None
