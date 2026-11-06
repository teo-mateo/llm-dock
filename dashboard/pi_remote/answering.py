from typing import Any, Dict, Optional, Tuple

from .bus import SessionKey
from .prompts import parse_answer_body

ANSWER_ERROR_STATUS = {
    "pi_session_offline": 409,
    "rate_limited": 429,
    "queue_full": 503,
    "unsupported_command": 400,
    "prompt_already_answered": 409,
    "prompt_unknown": 404,
    "invalid_value": 400,
    "invalid_body": 400,
}

ANSWER_WAIT_S = 5.0


def already_answered(value: Any, reason: str, answered_by: Optional[str]) -> Dict[str, Any]:
    return {
        "error": "prompt_already_answered",
        "value": value,
        "reason": reason,
        "answered_by": answered_by,
    }


def answer_prompt(
    client: Any, key: SessionKey, prompt_id: str, body: Any, wait_s: float = ANSWER_WAIT_S
) -> Tuple[int, Dict[str, Any]]:
    value, error = parse_answer_body(body)
    if error is not None:
        return ANSWER_ERROR_STATUS[error], {"error": error, "prompt_id": prompt_id}

    stored = client.store.prompts.get(key[0], key[1], prompt_id)
    if stored is None:
        return 404, {"error": "unknown_prompt", "prompt_id": prompt_id}
    if stored.status != "open":
        return 409, already_answered(stored.value, stored.status, stored.answered_by)

    command_id, error = client.send_command(
        key, "answer_prompt", {"prompt_id": prompt_id, "value": value}
    )
    if error is not None:
        return ANSWER_ERROR_STATUS.get(error, 400), {"error": error, "prompt_id": prompt_id}

    result = client.await_command(command_id, wait_s)
    if result is None:
        return 202, {"command_id": command_id, "prompt_id": prompt_id, "pending": True}
    if result.ok:
        return 200, {"command_id": command_id, "prompt_id": prompt_id, "ok": True}

    settled = client.store.prompts.get(key[0], key[1], prompt_id)
    if result.error == "prompt_already_answered" and settled is not None:
        return 409, already_answered(settled.value, settled.status, settled.answered_by)
    reason = result.error or "failed"
    return ANSWER_ERROR_STATUS.get(reason, 400), {
        "error": reason,
        "prompt_id": prompt_id,
        "command_id": command_id,
    }
