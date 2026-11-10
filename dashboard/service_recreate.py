import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping

from port_conflicts import PORT_IN_USE
from service_start_guard import check_start, finish_start

logger = logging.getLogger(__name__)

RECREATE_TIMEOUT_S = 240
RESTART_TIMEOUT_S = 60

NOT_FOUND = "not_found"
RECREATE_FAILED = "recreate_failed"

Runner = Callable[[list[str], int], subprocess.CompletedProcess]


def run_compose(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


@dataclass(frozen=True)
class RecreateResult:
    ok: bool
    service: str
    was_running: bool = False
    error: str | None = None
    code: str | None = None

    def body(self) -> dict:
        if self.ok:
            return {"success": True, "service": self.service, "was_running": self.was_running}
        return {"success": False, "error": self.error, "code": self.code}

    def http_status(self) -> int:
        if self.ok:
            return 200
        return 404 if self.code == NOT_FOUND else 400


def force_recreate(
    compose_file: str,
    service_name: str,
    run: Runner = run_compose,
    timeout: int = RECREATE_TIMEOUT_S,
) -> str | None:
    command = [
        "docker", "compose", "-f", compose_file,
        "up", "-d", "--force-recreate", service_name,
    ]
    try:
        result = run(command, timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Recreate of %s timed out after %ss", service_name, timeout)
        return f"Recreate timed out after {timeout}s; the container may still be coming up"
    if result.returncode != 0:
        logger.warning("Failed to recreate %s: %s", service_name, result.stderr)
        return result.stderr or "docker compose failed with no output"
    return None


def recreate_service(
    services: dict,
    name: str,
    statuses: Mapping[str, str],
    compose_file: str,
    rebuild: Callable[[], None],
    run: Runner = run_compose,
    finish: Callable[[dict, str], None] = finish_start,
) -> RecreateResult:
    if name not in services:
        return RecreateResult(False, name, error=f'Service "{name}" not found', code=NOT_FOUND)

    blocked = check_start(services, name, statuses)
    if blocked:
        return RecreateResult(False, name, error=blocked["error"], code=PORT_IN_USE)

    rebuild()
    error = force_recreate(compose_file, name, run)
    if error:
        return RecreateResult(False, name, error=error, code=RECREATE_FAILED)

    finish(services, name)
    logger.info("Recreated service: %s", name)
    return RecreateResult(True, name, was_running=statuses.get(name) == "running")
