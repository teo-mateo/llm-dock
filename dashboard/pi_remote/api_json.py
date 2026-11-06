from dataclasses import asdict
from typing import Any, Dict, Mapping, Optional, Tuple

from .read_model import EventPage, SessionSummary

MAX_MESSAGE_TEXT = 32000


def summary_json(summary: SessionSummary) -> Dict[str, Any]:
    return asdict(summary)


def page_json(page: EventPage) -> Dict[str, Any]:
    return {
        "events": [asdict(event) for event in page.events],
        "next_after": page.next_after,
        "has_more": page.has_more,
    }


def parse_message_body(body: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(body, dict):
        return None, "invalid_body"
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_TEXT:
        return None, "invalid_text"
    return text, None


def parse_paging(
    args: Mapping[str, str],
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    after_seq = 0
    raw_after = args.get("after")
    if raw_after is not None:
        try:
            after_seq = int(raw_after)
        except (TypeError, ValueError):
            return None, None, "invalid_paging"
        if after_seq < 0:
            return None, None, "invalid_paging"

    limit = None
    raw_limit = args.get("limit")
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return None, None, "invalid_paging"
        if limit < 1:
            return None, None, "invalid_paging"

    return after_seq, limit, None
