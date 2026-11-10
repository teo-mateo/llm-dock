from dataclasses import dataclass
from typing import Any, Callable, Collection, Mapping, Protocol, Sequence

from .hooks import ServiceHook


class Container(Protocol):
    status: str
    attrs: Mapping[str, Any]


class ComposeStore(Protocol):
    def get_service_from_db(self, name: str) -> dict | None: ...

    def list_services_in_db(self) -> Mapping[str, Any]: ...

    def add_service_to_db(self, name: str, config: dict) -> None: ...

    def rename_service(self, old_name: str, new_name: str) -> None: ...

    def remove_service_from_db(self, name: str) -> None: ...

    def update_service_in_db(self, name: str, config: dict) -> None: ...

    def get_used_ports(self) -> Collection[int]: ...

    def save_services_db(self, services: Mapping[str, Any]) -> None: ...

    def rebuild_compose_file(self) -> None: ...


@dataclass(frozen=True)
class Infra:
    """What every operation needs from outside, injected so an operation runs
    against fakes without Flask or Docker. hooks run in registration order in
    every phase; compose is a factory for the compose store."""

    compose: Callable[[], ComposeStore]
    get_container: Callable[[str], Container | None]
    remove_container: Callable[[str], None]
    emit: Callable[[dict], None]
    now: Callable[[], float]
    hooks: Sequence[ServiceHook]
