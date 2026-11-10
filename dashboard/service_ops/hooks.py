import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class RenameContext:
    old_name: str
    new_name: str
    config: dict
    state: dict = field(default_factory=dict)


@dataclass
class DeleteContext:
    name: str
    config: dict
    state: dict = field(default_factory=dict)


class ServiceHook:
    """A subsystem that keeps per-service state and follows a rename or delete.

    A phase a hook does not need stays a no-op. best_effort means a failure is
    logged and the operation continues; a hook that sets it False aborts the
    operation with its exception. Every phase runs the hooks in registration
    order, so the order of the list passed to ServiceOpsDeps is the order of
    the side effects.
    """

    name = "hook"
    best_effort = True

    def before_rename(self, ctx: RenameContext) -> None:
        pass

    def after_rename(self, ctx: RenameContext) -> None:
        pass

    def after_delete(self, ctx: DeleteContext) -> None:
        pass


def run_phase(hooks: Iterable[ServiceHook], phase: str, ctx) -> None:
    for hook in hooks:
        try:
            getattr(hook, phase)(ctx)
        except Exception as e:
            if not hook.best_effort:
                raise
            logger.warning(f"{hook.name} {phase} failed for '{getattr(ctx, 'name', None) or ctx.old_name}': {e}")
