from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .wire_types import STATES, is_int, is_model, is_nullable_str, is_number

SESSION_REASONS = frozenset({"startup", "reload", "new", "resume", "fork"})


@dataclass(frozen=True)
class ModelRef:
    provider: str
    id: str


@dataclass(frozen=True)
class ContextUsage:
    tokens: Optional[float]
    window: Optional[float]
    percent: Optional[float]


@dataclass(frozen=True)
class HelloFrame:
    session_id: str
    instance_id: str
    session_file: Optional[str]
    cwd: str
    name: Optional[str]
    pid: int
    model: Optional[ModelRef]
    thinking_level: Optional[str]
    reason: str
    previous_session_id: Optional[str]
    parent_session_id: Optional[str]
    pi_version: Optional[str]
    ext_version: str


@dataclass(frozen=True)
class HeartbeatFrame:
    session_id: str
    instance_id: str
    state: str
    context: Optional[ContextUsage]
    sent_at: int


@dataclass(frozen=True)
class ByeFrame:
    session_id: str
    instance_id: str
    reason: Optional[str]


Frame = Union[HelloFrame, HeartbeatFrame, ByeFrame]


def _parse_model(body: Dict[str, Any]) -> Optional[ModelRef]:
    model = body.get("model")
    if model is None:
        return None
    if not is_model(model):
        return None
    return ModelRef(provider=model["provider"], id=model["id"])


def _parse_context(body: Dict[str, Any]) -> Optional[ContextUsage]:
    context = body.get("context")
    if context is None:
        return None
    if not isinstance(context, dict):
        return None
    for key in ("tokens", "window", "percent"):
        value = context.get(key)
        if value is not None and not is_number(value):
            return None
    return ContextUsage(
        tokens=context.get("tokens"),
        window=context.get("window"),
        percent=context.get("percent"),
    )


def parse_hello(body: Dict[str, Any]) -> Optional[HelloFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not isinstance(body.get("cwd"), str):
        return None
    if not is_int(body.get("pid")):
        return None
    if body.get("reason") not in SESSION_REASONS:
        return None
    if not isinstance(body.get("ext_version"), str):
        return None
    for key in (
        "session_file",
        "name",
        "thinking_level",
        "previous_session_id",
        "parent_session_id",
        "pi_version",
    ):
        if not is_nullable_str(body.get(key)):
            return None
    model = _parse_model(body)
    if body.get("model") is not None and model is None:
        return None
    return HelloFrame(
        session_id=session_id,
        instance_id=instance_id,
        session_file=body.get("session_file"),
        cwd=body["cwd"],
        name=body.get("name"),
        pid=body["pid"],
        model=model,
        thinking_level=body.get("thinking_level"),
        reason=body["reason"],
        previous_session_id=body.get("previous_session_id"),
        parent_session_id=body.get("parent_session_id"),
        pi_version=body.get("pi_version"),
        ext_version=body["ext_version"],
    )


def parse_heartbeat(body: Dict[str, Any]) -> Optional[HeartbeatFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if body.get("state") not in STATES:
        return None
    if not is_int(body.get("sent_at")):
        return None
    context = _parse_context(body)
    if body.get("context") is not None and context is None:
        return None
    return HeartbeatFrame(
        session_id=session_id,
        instance_id=instance_id,
        state=body["state"],
        context=context,
        sent_at=body["sent_at"],
    )


def parse_bye(body: Dict[str, Any]) -> Optional[ByeFrame]:
    session_id = body.get("session_id")
    instance_id = body.get("instance_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not is_nullable_str(body.get("reason")):
        return None
    return ByeFrame(
        session_id=session_id,
        instance_id=instance_id,
        reason=body.get("reason"),
    )
