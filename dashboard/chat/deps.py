from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app

from . import project_files as pf

DEPS_KEY = "CHAT_DEPS"


def default_services() -> list:
    from docker_utils import get_docker_services

    return get_docker_services()


@dataclass(frozen=True)
class ChatDeps:
    """Everything the chat handlers and policy need from outside, built once.

    services is the service catalog (name, template_type, reasoning_levels) the
    policy modules read; production reads it from docker, tests pass a list.
    """

    db: Any
    mcp: Any = None
    run_manager: Any = None
    bus: Any = None
    project_files_dir: str | None = None
    services: Callable[[], list] = default_services

    def storage_root(self) -> str:
        return self.project_files_dir or pf.default_storage_root()


def deps() -> ChatDeps:
    return current_app.config[DEPS_KEY]


def install(app, **parts) -> ChatDeps:
    chat_deps = ChatDeps(**parts)
    app.config[DEPS_KEY] = chat_deps
    return chat_deps
