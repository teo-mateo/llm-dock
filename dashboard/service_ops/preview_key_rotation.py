from dataclasses import dataclass
from typing import Callable

from .affected import AffectedState


@dataclass(frozen=True)
class PreviewKeyRotationDeps:
    affected_state: Callable[[], AffectedState]


@dataclass(frozen=True)
class RotationPreview:
    total_services: int
    running: list
    openwebui_registered: list

    def body(self) -> dict:
        return {
            "total_services": self.total_services,
            "running": self.running,
            "openwebui_registered": self.openwebui_registered,
        }


def preview_key_rotation(deps: PreviewKeyRotationDeps) -> RotationPreview:
    """Describe what rotating the default key would touch, changing nothing."""
    state = deps.affected_state()
    return RotationPreview(len(state.services), list(state.running), list(state.openwebui_registered))
