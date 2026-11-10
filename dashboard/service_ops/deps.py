from dataclasses import dataclass
from typing import Any, Callable, Collection, Mapping, Protocol, Sequence

from .hooks import ServiceHook


class Container(Protocol):
    status: str


class ComposeStore(Protocol):
    def get_service_from_db(self, name: str) -> dict | None: ...

    def list_services_in_db(self) -> Mapping[str, Any]: ...

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


@dataclass(frozen=True)
class RenameDeps:
    infra: Infra


@dataclass(frozen=True)
class DeleteDeps:
    infra: Infra
    stop_container: Callable[[str], None]


@dataclass(frozen=True)
class SetPublicPortDeps:
    infra: Infra
    next_free_port: Callable[[Mapping[str, Any], Collection[int]], int]
    recreate_if_running: Callable[[str], dict]


@dataclass(frozen=True)
class SetInspectDeps:
    infra: Infra
    allocate_upstream_port: Callable[[Mapping[str, Any], str], int]
    recreate_if_running: Callable[[str], dict]
    proxy_status: Callable[[], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class RotateKeyDeps:
    infra: Infra
    affected_state: Callable[[], tuple[Sequence[str], Sequence[str], Sequence[str]]]
    generate_key: Callable[[], str]
    rotate_in_db: Callable[[ComposeStore, str], dict]
    commit_key: Callable[[str], None]
    stop_service: Callable[[str], dict]
