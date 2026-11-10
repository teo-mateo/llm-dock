from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyError:
    status: int
    message: str
    code: str | None = None

    def body(self) -> dict:
        body = {"error": self.message}
        if self.code:
            body["code"] = self.code
        return body
