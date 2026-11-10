from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Callable

from . import project_files as pf

if TYPE_CHECKING:
    from .db import ChatDB
    from .event_bus import EventBus
    from .mcp_client import MCPClientManager
    from .run_manager import ChatRunManager

def default_services() -> list:
    from docker_utils import get_docker_services

    return get_docker_services()


@dataclass(frozen=True)
class ChatDeps:
    """Everything the chat handlers and policy need from outside, built once.

    Every collaborator is required: a half-installed app fails in install(),
    not as a None attribute in some later handler. services is the service
    catalog (name, template_type, reasoning_levels) the policy modules read;
    production passes default_services, tests pass a list. project_files_dir
    falls back to the default storage root.
    """

    db: ChatDB
    mcp: MCPClientManager
    run_manager: ChatRunManager
    bus: EventBus
    services: Callable[[], list]
    project_files_dir: str | None = None

    def __post_init__(self):
        missing = [f.name for f in fields(self) if f.name != "project_files_dir" and getattr(self, f.name) is None]
        if missing:
            raise ValueError(f"ChatDeps requires {', '.join(missing)}")

    def storage_root(self) -> str:
        return self.project_files_dir or pf.default_storage_root()
