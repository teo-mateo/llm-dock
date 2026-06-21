"""Chat run status vocabulary (Phase 2 of #58).

A *run* is one model/tool turn whose lifecycle is tracked independently of the
HTTP response that started it. This module holds only the status vocabulary so
both the DB layer and (later) the background runner agree on the allowed values
without importing each other. The persistence methods live on ChatDB; a richer
ChatRunRepository may wrap them once the background runner needs it (Phase 3+).
"""


class ChatRunStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# A run is "active" while it is queued or running — these are the only states
# that should surface as an active_run on a conversation.
ACTIVE_STATUSES = frozenset({ChatRunStatus.QUEUED, ChatRunStatus.RUNNING})

# Terminal states never reactivate.
TERMINAL_STATUSES = frozenset(
    {ChatRunStatus.COMPLETED, ChatRunStatus.FAILED, ChatRunStatus.CANCELLED}
)

ALL_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES


def is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES
