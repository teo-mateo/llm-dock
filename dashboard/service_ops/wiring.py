import subprocess
import time
from dataclasses import replace

import config
import tabby_keys
from compose_manager import ComposeManager
from docker_utils import control_service, get_docker_services, get_service_container
from key_rotation import rotate_keys_in_db
from inspector.ports import allocate_upstream_port
from inspector.supervisor import proxy_supervisor
import port_conflicts
from port_conflicts import next_free_port
from service_recreate import restart_if_running
from service_templates import generate_api_key
from openwebui_integration import (
    add_service_to_openwebui,
    is_service_registered_in_openwebui,
    remove_service_from_openwebui,
)

from .deps import DeleteDeps, Infra, RenameDeps, RotateKeyDeps, SetInspectDeps, SetPublicPortDeps
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
    return RenameDeps(replace(build_infra(compose_file), **overrides))


def delete_deps(compose_file: str, stop_container=None, **overrides) -> DeleteDeps:
    return DeleteDeps(
        replace(build_infra(compose_file), **overrides),
        stop_container=stop_container or (lambda name: _compose_run(compose_file, ["stop"], name, 30)),
    )


def recreate_if_running(compose_file: str, name: str, rebuild: bool = False, finish=lambda services, n: None) -> dict:
    container = get_service_container(name)
    status = container.status if container else "not-created"
    return restart_if_running(compose_file, name, status, rebuild, finish)


def set_public_port_deps(compose_file: str, next_port=None, recreate=None, **overrides) -> SetPublicPortDeps:
    return SetPublicPortDeps(
        replace(build_infra(compose_file), **overrides),
        next_free_port=next_port or (
            lambda services, used: next_free_port(services, used, *port_conflicts.PUBLIC_PORT_RANGE)
        ),
        recreate_if_running=recreate or (lambda name: recreate_if_running(compose_file, name)),
    )


def set_inspect_deps(compose_file: str, allocate=None, recreate=None, status=None, **overrides) -> SetInspectDeps:
    return SetInspectDeps(
        replace(build_infra(compose_file), **overrides),
        allocate_upstream_port=allocate or allocate_upstream_port,
        recreate_if_running=recreate or (lambda name: recreate_if_running(compose_file, name)),
        proxy_status=status or (lambda: proxy_supervisor.status()),
    )


def affected_services_state(compose_file: str):
    """Return (db_service_names, running, openwebui_registered) for rotation.

    Only services present in services.json are affected by a rotation; infra
    containers like open-webui are never in services.json so they're excluded
    naturally.
    """
    db_services = set(ComposeManager(compose_file).list_services_in_db().keys())

    running = []
    openwebui_registered = []
    for svc in get_docker_services():
        name = svc["name"]
        if name not in db_services:
            continue
        if svc.get("status") == "running":
            running.append(name)
        if svc.get("openwebui_registered"):
            openwebui_registered.append(name)

    return sorted(db_services), sorted(running), sorted(openwebui_registered)


def rotate_key_deps(compose_file: str, **overrides) -> RotateKeyDeps:
    return RotateKeyDeps(
        replace(build_infra(compose_file), **overrides),
        affected_state=lambda: affected_services_state(compose_file),
        generate_key=lambda: generate_api_key(),
        rotate_in_db=lambda compose, key: rotate_keys_in_db(compose, key),
        commit_key=lambda key: config.set_global_api_key(key),
        stop_service=lambda name: control_service(name, "stop"),
    )
