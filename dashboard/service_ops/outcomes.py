from dataclasses import dataclass


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
