import logging
import os

from .db import ChatDB
from .deps import default_services, install
from .event_bus import EventBus
from .project_files import configure_max_content_length
from .prompt_seed import seed_default_prompts
from .run_manager import ChatRunManager

logger = logging.getLogger(__name__)


def init_chat(app, db_path: str = None):
    if db_path is None:
        db_path = os.environ.get("LLM_DOCK_CHAT_DB") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "chat.db"
        )
    db = ChatDB(db_path)
    seed_default_prompts(db)

    from .mcp_client import MCPClientManager
    from . import mcp_config
    mgr = MCPClientManager()
    mcp_config.bind_manager(mgr)
    mcp_config.reload()

    # Cap request bodies so Werkzeug rejects an oversized upload DURING
    # multipart parsing (before it is fully spooled to disk) — covers
    # chunked bodies that carry no Content-Length. Slightly above the
    # per-file cap to leave room for multipart framing; an explicit
    # deployment override is preserved.
    configure_max_content_length(app)

    # Runs from a previous process that died mid-flight are marked failed so
    # they don't linger as stuck active runs.
    bus = EventBus()
    run_manager = ChatRunManager(db, bus)
    run_manager.recover_interrupted_runs()

    install(app, db=db, mcp=mgr, run_manager=run_manager, bus=bus, services=default_services)
    logger.info("Chat subsystem initialized")
