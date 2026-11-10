from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .hooks import ServiceHook


@dataclass(frozen=True)
class ServiceOpsDeps:
    """What a service operation needs from outside, injected so an operation
    runs against fakes without Flask or Docker.

    hooks run in registration order in every phase. compose is a factory for
    the compose manager (service lookup, rename, remove, rebuild).
    """

    compose: Callable[[], Any]
    get_container: Callable[[str], Any]
    stop_container: Callable[[str], None]
    remove_container: Callable[[str], None]
    hooks: Sequence[ServiceHook]
    emit: Callable[[dict], None]
    now: Callable[[], float]
