import subprocess
import time

import tabby_keys
from compose_manager import ComposeManager
from docker_utils import get_service_container
from inspector.supervisor import proxy_supervisor
from openwebui_integration import (
    add_service_to_openwebui,
    is_service_registered_in_openwebui,
    remove_service_from_openwebui,
)

from .deps import DeleteDeps, Infra, RenameDeps
from .subsystems import BenchmarkHook, InspectorHook, KeyFileHook, OpenWebUIHook


def _rename_benchmarks(old_name: str, new_name: str) -> int:
    from benchmarking.routes import rename_service

    return rename_service(old_name, new_name)


def _hooks():
    return [
        InspectorHook(lambda old, new: proxy_supervisor.rename_service(old, new), lambda: proxy_supervisor.sync()),
        BenchmarkHook(lambda old, new: _rename_benchmarks(old, new)),
        KeyFileHook(lambda name: tabby_keys.remove(name)),
        OpenWebUIHook(
            lambda name, engine: is_service_registered_in_openwebui(name, engine),
            lambda name, engine: remove_service_from_openwebui(name, engine),
            lambda name, port, key, engine: add_service_to_openwebui(name, port, key, engine),
        ),
    ]


def _compose_run(compose_file: str, action: list[str], name: str, timeout: int):
    return subprocess.run(
        ["docker", "compose", "-f", compose_file, *action, name], capture_output=True, timeout=timeout
    )


def build_infra(compose_file: str, emit=None) -> Infra:
    if emit is None:
        from services import event_manager

        emit = lambda event: event_manager.emit(event)  # noqa: E731
    return Infra(
        compose=lambda: ComposeManager(compose_file),
        get_container=lambda name: get_service_container(name),
        remove_container=lambda name: _compose_run(compose_file, ["rm", "-f"], name, 10),
        emit=emit,
        now=time.time,
        hooks=_hooks(),
    )


def rename_deps(compose_file: str, **overrides) -> RenameDeps:
    from dataclasses import replace

    return RenameDeps(replace(build_infra(compose_file), **overrides))


def delete_deps(compose_file: str, **overrides) -> DeleteDeps:
    from dataclasses import replace

    return DeleteDeps(
        replace(build_infra(compose_file), **overrides),
        stop_container=lambda name: _compose_run(compose_file, ["stop"], name, 30),
    )
