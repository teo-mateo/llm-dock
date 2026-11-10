from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class PreviewKeyRotationDeps:
    affected_state: Callable[[], tuple[Sequence[str], Sequence[str], Sequence[str]]]


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
    db_services, running, openwebui_registered = deps.affected_state()
    return RotationPreview(len(db_services), list(running), list(openwebui_registered))
