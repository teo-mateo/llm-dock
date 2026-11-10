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
