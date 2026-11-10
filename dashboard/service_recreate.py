import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping

from compose_manager import ComposeManager
from port_conflicts import PORT_IN_USE
from service_start_guard import check_start, finish_start

logger = logging.getLogger(__name__)

# Recreate stops the old container first, and Maya alone has a 150 s
# stop_grace_period.
RECREATE_TIMEOUT_S = 240
# Rename, update, set-public-port and the inspect toggle recreate inside a
# request that holds SERVICES_DB_LOCK; raising this holds every other write
# behind them for longer.
RESTART_TIMEOUT_S = 60

NOT_FOUND = "not_found"
RECREATE_FAILED = "recreate_failed"
RECREATE_TIMEOUT = "recreate_timeout"
COMPOSE_REBUILD_FAILED = "compose_rebuild_failed"

Runner = Callable[[list[str], int], subprocess.CompletedProcess]


def run_compose(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


@dataclass(frozen=True)
class ComposeOutcome:
    status: str
    message: str | None = None


@dataclass(frozen=True)
class RecreateResult:
    ok: bool
    service: str
    was_running: bool = False
    recreated: bool = False
    error: str | None = None
    code: str | None = None

    def body(self) -> dict:
        if self.ok:
            return {"success": True, "service": self.service, "was_running": self.was_running}
        return {"success": False, "error": self.error, "code": self.code}

    def restart_status(self) -> dict:
        if self.error:
            return {"restarted": False, "error": self.error}
        return {"restarted": self.recreated}


def force_recreate(
    compose_file: str,
    service_name: str,
    run: Runner = run_compose,
    timeout: int = RECREATE_TIMEOUT_S,
) -> ComposeOutcome:
    command = [
        "docker", "compose", "-f", compose_file,
        "up", "-d", "--force-recreate", service_name,
    ]
    try:
        result = run(command, timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Recreate of %s timed out after %ss", service_name, timeout)
        return ComposeOutcome(
            "timeout", f"Recreate timed out after {timeout}s; the container may still be coming up"
        )
    if result.returncode != 0:
        logger.warning("Failed to recreate %s: %s", service_name, result.stderr)
        return ComposeOutcome("failed", result.stderr or "docker compose failed with no output")
    return ComposeOutcome("ok")


def recreate_service(
    services: dict,
    name: str,
    statuses: Mapping[str, str],
    compose_file: str,
    rebuild: Callable[[], None],
    run: Runner = run_compose,
    finish: Callable[[dict, str], None] = finish_start,
    only_if_running: bool = False,
    timeout: int = RECREATE_TIMEOUT_S,
) -> RecreateResult:
    if name not in services:
        return RecreateResult(False, name, error=f'Service "{name}" not found', code=NOT_FOUND)

    was_running = statuses.get(name) == "running"
    will_recreate = was_running or not only_if_running

    if will_recreate:
        blocked = check_start(services, name, statuses)
        if blocked:
            return RecreateResult(
                False, name, was_running, error=blocked["error"], code=PORT_IN_USE
            )

    try:
        try:
            rebuild()
        except Exception as e:
            logger.error("Compose rebuild failed before recreating %s: %s", name, e)
            return RecreateResult(
                False, name, was_running, error=str(e), code=COMPOSE_REBUILD_FAILED
            )
        if not will_recreate:
            return RecreateResult(True, name, was_running)

        outcome = force_recreate(compose_file, name, run, timeout)
        if outcome.status == "ok":
            logger.info("Recreated service: %s", name)
            return RecreateResult(True, name, was_running, recreated=True)
        code = RECREATE_TIMEOUT if outcome.status == "timeout" else RECREATE_FAILED
        return RecreateResult(False, name, was_running, error=outcome.message, code=code)
    finally:
        finish(services, name)


def recreate(compose_file: str, name: str, statuses: Mapping[str, str]) -> RecreateResult:
    compose_mgr = ComposeManager(compose_file)
    return recreate_service(
        compose_mgr.list_services_in_db(),
        name,
        statuses,
        compose_file,
        compose_mgr.rebuild_compose_file,
    )


def restart_if_running(
    compose_file: str,
    name: str,
    status: str,
    rebuild: bool = False,
    finish: Callable[[dict, str], None] = lambda services, name: None,
) -> dict:
    compose_mgr = ComposeManager(compose_file)
    result = recreate_service(
        compose_mgr.list_services_in_db(),
        name,
        {name: status},
        compose_file,
        compose_mgr.rebuild_compose_file if rebuild else (lambda: None),
        finish=finish,
        only_if_running=True,
        timeout=RESTART_TIMEOUT_S,
    )
    if result.code == COMPOSE_REBUILD_FAILED:
        raise ValueError(result.error)
    return result.restart_status()
