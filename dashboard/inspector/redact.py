from typing import Dict, Tuple

REDACTED = "***redacted***"
SENSITIVE_HEADERS = {"authorization", "x-api-key", "api-key", "x-totp-code", "cookie"}
MAX_BODY_CHARS = 1_000_000
TRUNCATION_MARKER = "\n…[truncated by llm-dock inspector]"


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        name: (REDACTED if name.lower() in SENSITIVE_HEADERS else value)
        for name, value in headers.items()
    }


def truncate(text: str, cap: int = MAX_BODY_CHARS) -> Tuple[str, bool]:
    if len(text) <= cap:
        return text, False
    return text[:cap] + TRUNCATION_MARKER, True
