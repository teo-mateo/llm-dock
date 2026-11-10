from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpError:
    status: int
    message: str

    def body(self) -> dict:
        return {"error": self.message}


@dataclass(frozen=True)
class Renamed:
    old_name: str
    new_name: str


@dataclass(frozen=True)
class Deleted:
    name: str


@dataclass(frozen=True)
class AlreadyPublic:
    name: str
    port: int


@dataclass(frozen=True)
class PublicPortSet:
    name: str
    port: int
    updates: list
    restarts: list


@dataclass(frozen=True)
class InspectSet:
    service: str
    enabled: bool
    port: int | None
    upstream_port: int | None
    proxy_running: bool
    restarted: bool
    error: str | None

    def body(self) -> dict:
        return {
            "service": self.service,
            "enabled": self.enabled,
            "port": self.port,
            "upstream_port": self.upstream_port,
            "proxy_running": self.proxy_running,
            "restarted": self.restarted,
            "error": self.error,
        }


@dataclass(frozen=True)
class KeyRotated:
    """A stop that failed leaves a container accepting the OLD key, so the
    rotation is then partial rather than a success."""

    new_key: str
    updated: list
    total_services: int
    stopped: list
    stop_errors: dict
    openwebui_registered: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stop_errors

    @property
    def status(self) -> int:
        return 200 if self.ok else 207

    def message(self) -> str:
        if self.ok:
            return (
                f"Default API key rotated across {len(self.updated)} "
                f"service(s); {len(self.stopped)} running container(s) stopped."
            )
        return (
            f"Default API key rotated across {len(self.updated)} "
            f"service(s), but {len(self.stop_errors)} running container(s) "
            f"could NOT be stopped and still accept the OLD key — stop "
            f"them manually: {', '.join(sorted(self.stop_errors))}."
        )

    def body(self) -> dict:
        return {
            "success": self.ok,
            "partial": not self.ok,
            "new_api_key": self.new_key,
            "services_updated": len(self.updated),
            "total_services": self.total_services,
            "stopped": self.stopped,
            "stop_errors": self.stop_errors,
            "openwebui_registered": self.openwebui_registered,
            "message": self.message(),
        }
