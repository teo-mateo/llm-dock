"""Registration shim for the chat blueprint.

Importing this module imports every endpoint module, which attaches its routes
to chat_bp. That has to happen while app.py imports chat.routes, before
app.register_blueprint(chat_bp): Flask 3 rejects adding routes to a blueprint
that is already registered ("The setup method 'route' can no longer be called
on the blueprint 'chat'"). chat_bp and init_chat are re-exported for app.py.
"""

from .blueprint import chat_bp  # noqa: F401
from .bootstrap import init_chat  # noqa: F401
from . import (  # noqa: F401
    conversation_routes,
    critique_routes,
    ephemeral_routes,
    mcp_admin_routes,
    message_routes,
    openrouter_routes,
    project_files_routes,
    project_routes,
    prompt_routes,
    providers_routes,
    run_routes,
    settings_routes,
)
