import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

logger = logging.getLogger(__name__)


class Phase(Enum):
    BEFORE_RENAME = "before_rename"
    AFTER_RENAME = "after_rename"
    AFTER_DELETE = "after_delete"
    AFTER_PUBLIC_PORT = "after_public_port"


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
class DeleteContext(HookContext):
    name: str
    config: dict
    state: dict = field(default_factory=dict)

    @property
    def subject(self) -> str:
        return self.name


@dataclass
class PublicPortContext(HookContext):
    name: str
    displaced: list
    state: dict = field(default_factory=dict)

    @property
    def subject(self) -> str:
        return self.name


class ServiceHook:
    """A subsystem that keeps per-service state and follows a rename or delete.

    A phase a hook does not need stays a no-op. best_effort means a failure is
    logged and the operation continues; a hook that sets it False aborts the
    operation with its exception. Every phase runs the hooks in registration
    order, so the order of the list given to the operation's deps is the order
    of the side effects. A hook keeps what it learns in one phase for a later
    one in ctx.state_for(self.name).
    """

    name = "hook"
    best_effort = True

    def before_rename(self, ctx: RenameContext) -> None:
        pass

    def after_rename(self, ctx: RenameContext) -> None:
        pass

    def after_delete(self, ctx: DeleteContext) -> None:
        pass

    def after_public_port(self, ctx: PublicPortContext) -> None:
        pass


def run_phase(hooks: Iterable[ServiceHook], phase: Phase, ctx) -> None:
    for hook in hooks:
        method = getattr(hook, phase.value)
        try:
            method(ctx)
        except Exception as e:
            if not hook.best_effort:
                raise
            logger.warning(f"{hook.name} {phase.value} failed for '{ctx.subject}': {e}")
