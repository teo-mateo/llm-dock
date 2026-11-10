import json
import uuid
from dataclasses import dataclass
from typing import Callable, Iterable

from . import project_files as pf
from . import run_config
from .models import ChatRun
from .outcomes import PolicyError
from .project_files_mcp import ProjectScopedMCPManager
from .runs import ChatRunStatus

RUN_ACTIVE_CODE = "run_already_active"
RUN_ACTIVE_MESSAGE = "A run is already active for this conversation"


@dataclass(frozen=True)
class Started:
    run_id: str
    observer: Iterable


def mcp_for_conversation(conv, enabled_servers, project_id, *, db, get_mcp: Callable, storage_root: str):
    """MCP manager for a run, or None when the turn has no tools.

    project_id is the pre-resolved effective project (see
    run_config.effective_project_id). Project conversations always get a manager —
    the project-files server is auto-enabled for them (see
    runtime._build_stream) — wrapped so its subprocess spawns learn the
    project's directory via the environment.

    The wrapper revalidates after every project-files call: the run
    snapshotted its project at start, so a write tool can land after the user
    deletes the project, and the project directory would be recreated as an
    orphan the UI can never show. The check runs on the runner thread, so it
    closes over db and storage_root rather than reading an app context.
    """
    if not (enabled_servers or project_id):
        return None
    manager = get_mcp()
    if project_id:

        def _revalidate():
            if db.get_project(project_id) is None:
                pf.delete_project_root(storage_root, project_id)

        manager = ProjectScopedMCPManager(
            manager, pf.project_root(storage_root, project_id), revalidate=_revalidate)
    return manager


def start_run(
    *,
    db,
    run_manager,
    get_mcp: Callable,
    storage_root: str,
    conv,
    user_msg,
    is_first: bool,
    first_user_content: str,
    services: Callable[[], list],
    delete_from_seq: int | None = None,
) -> Started | PolicyError:
    """Snapshot the run's configuration, atomically persist the user message and
    a queued run (rejecting a second run while one is active), and start the
    background job.

    The observer is only a view of the event bus: a client that disconnects
    leaves the run going on the worker pool, and the reply is persisted
    regardless. The bus is subscribed BEFORE the job starts so no early event
    is missed. On a conflict the user message, and any edit truncation, are
    rolled back by the database.
    """
    cfg = run_config.prepare_run_config(conv, db.resolve_project_id, services)
    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    mcp_manager = mcp_for_conversation(
        conv, enabled_servers, cfg.project_id, db=db, get_mcp=get_mcp, storage_root=storage_root
    )

    run = ChatRun(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        status=ChatRunStatus.QUEUED,
        user_message_id=user_msg.id,
    )
    if db.create_run_with_user_message(user_msg, run, delete_from_seq=delete_from_seq) is None:
        return PolicyError(409, RUN_ACTIVE_MESSAGE, RUN_ACTIVE_CODE)

    queue = run_manager.subscribe(run.id)
    run_manager.start(conv, run, mcp_manager=mcp_manager, is_first=is_first,
                      first_user_content=first_user_content,
                      effective_project_id=cfg.project_id,
                      reasoning_level=cfg.reasoning_level,
                      sampling_params=cfg.sampling_params)
    return Started(
        run.id, run_manager.observe(run.id, queue, run_started_extra=cfg.started_extra())
    )
