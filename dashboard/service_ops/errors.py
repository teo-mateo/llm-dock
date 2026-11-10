from dataclasses import dataclass
from enum import Enum


class ErrorKind(Enum):
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID = "invalid"


@dataclass(frozen=True)
class OpError:
    """A refusal an operation reports instead of raising. It carries a kind,
    never an HTTP status: the route owns the mapping."""

    kind: ErrorKind
    message: str

    def body(self) -> dict:
        return {"error": self.message}


def service_not_found(name: str) -> OpError:
    return OpError(ErrorKind.NOT_FOUND, f'Service "{name}" not found')
