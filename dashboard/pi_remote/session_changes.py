from typing import Any, Dict, Iterable, Optional

from .events import StoredEvent

SESSION_CHANGE_TYPES = frozenset({"model_changed", "thinking_changed"})


def _model_columns(model: Any) -> Dict[str, Optional[str]]:
    if not isinstance(model, dict):
        return {"model_provider": None, "model_id": None}
    return {"model_provider": model.get("provider"), "model_id": model.get("id")}


def session_changes(events: Iterable[StoredEvent]) -> Dict[str, Optional[str]]:
    changes: Dict[str, Optional[str]] = {}
    for event in sorted(events, key=lambda item: item.seq):
        if event.type == "model_changed":
            changes.update(_model_columns(event.payload.get("model")))
        elif event.type == "thinking_changed":
            changes["thinking_level"] = event.payload.get("level")
    return changes
