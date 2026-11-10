import logging
from typing import Callable

from .hooks import DeleteContext, RenameContext, ServiceHook

logger = logging.getLogger(__name__)


class InspectorHook(ServiceHook):
    """Moves the capture history and reconciles the proxies. Not best-effort:
    a proxy left on the old name would keep a listener for a service that no
    longer exists, so a failure aborts the operation."""

    name = "inspector"
    best_effort = False

    def __init__(self, rename_captures: Callable[[str, str], None], sync: Callable[[], None]):
        self._rename_captures = rename_captures
        self._sync = sync

    def after_rename(self, ctx: RenameContext) -> None:
        self._rename_captures(ctx.old_name, ctx.new_name)
        self._sync()

    def after_delete(self, ctx: DeleteContext) -> None:
        self._sync()


class BenchmarkHook(ServiceHook):
    name = "benchmarks"

    def __init__(self, rename_rows: Callable[[str, str], int]):
        self._rename_rows = rename_rows

    def after_rename(self, ctx: RenameContext) -> None:
        updated = self._rename_rows(ctx.old_name, ctx.new_name)
        logger.info(f"Updated {updated} benchmark records from '{ctx.old_name}' to '{ctx.new_name}'")


class KeyFileHook(ServiceHook):
    """Removes a per-service key file (a no-op for a service that never had one)
    so a deleted service does not leave its api/admin keys on disk."""

    name = "key file"

    def __init__(self, remove: Callable[[str], object]):
        self._remove = remove

    def after_delete(self, ctx: DeleteContext) -> None:
        self._remove(ctx.name)


class OpenWebUIHook(ServiceHook):
    name = "open webui"

    def __init__(
        self,
        is_registered: Callable[[str, str], bool],
        unregister: Callable[[str, str], object],
        register: Callable[[str, int, str, str], object],
    ):
        self._is_registered = is_registered
        self._unregister = unregister
        self._register = register

    def before_rename(self, ctx: RenameContext) -> None:
        engine = ctx.config.get("template_type", "")
        if engine and self._is_registered(ctx.old_name, engine):
            ctx.state["openwebui_registered"] = True
            self._unregister(ctx.old_name, engine)

    def after_rename(self, ctx: RenameContext) -> None:
        engine = ctx.config.get("template_type", "")
        if ctx.state.get("openwebui_registered") and engine:
            self._register(
                ctx.new_name, ctx.config.get("port", 0), ctx.config.get("api_key", ""), engine
            )
