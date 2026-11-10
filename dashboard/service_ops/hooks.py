import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

logger = logging.getLogger(__name__)


class Phase(Enum):
    BEFORE_RENAME = "before_rename"
    AFTER_RENAME = "after_rename"
    AFTER_SERVICES_CHANGED = "after_services_changed"


class Cause(Enum):
    DELETE = "delete"
    PUBLIC_PORT = "public_port"
    INSPECT = "inspect"
    KEY_ROTATION = "key_rotation"


class HookContext:
    state: dict

    def state_for(self, hook_name: str) -> dict:
        return self.state.setdefault(hook_name, {})


@dataclass
class RenameContext(HookContext):
    old_name: str
    new_name: str
    config: dict
    state: dict = field(default_factory=dict)

    @property
    def subject(self) -> str:
        return self.old_name


@dataclass
class ServicesChangedContext(HookContext):
    subject: str
    cause: Cause
    affected: list
    state: dict = field(default_factory=dict)


class ServiceHook:
    """A subsystem that keeps per-service state and follows a change to services.json.

    A phase a hook does not need stays a no-op. Rename has a before and an
    after phase because they carry distinct data; every other change is one
    AFTER_SERVICES_CHANGED phase whose ctx.cause says what happened and
    ctx.affected which services. best_effort means a failure is logged and the
    operation continues; a hook that sets it False aborts the operation with
    its exception. Every phase runs the hooks in registration order, so the
    order of the list given to the operation's deps is the order of the side
    effects. A hook keeps what it learns in one phase for a later one in
    ctx.state_for(self.name).

    PHASE_METHODS is the only place a Phase is tied to the method it calls; a
    before_*/after_* method outside it fails at class creation, so a misspelt
    override cannot silently never run.
    """

    name = "hook"
    best_effort = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _check_phase_methods(cls)

    def before_rename(self, ctx: RenameContext) -> None:
        pass

    def after_rename(self, ctx: RenameContext) -> None:
        pass

    def after_services_changed(self, ctx: ServicesChangedContext) -> None:
        pass


PHASE_METHODS = {
    Phase.BEFORE_RENAME: "before_rename",
    Phase.AFTER_RENAME: "after_rename",
    Phase.AFTER_SERVICES_CHANGED: "after_services_changed",
}


def _check_phase_methods(cls) -> None:
    missing = [p for p in Phase if p not in PHASE_METHODS]
    if missing:
        raise TypeError(f"Phase without a method in PHASE_METHODS: {missing}")
    known = set(PHASE_METHODS.values())
    for attr in dir(cls):
        if attr.startswith(("before_", "after_")) and callable(getattr(cls, attr)) and attr not in known:
            raise TypeError(f"{cls.__name__}.{attr} is not a hook phase; known: {sorted(known)}")


_check_phase_methods(ServiceHook)


def run_phase(hooks: Iterable[ServiceHook], phase: Phase, ctx) -> None:
    for hook in hooks:
        method = getattr(hook, PHASE_METHODS[phase])
        try:
            method(ctx)
        except Exception as e:
            if not hook.best_effort:
                raise
            logger.warning(f"{hook.name} {phase.value} failed for '{ctx.subject}': {e}")
