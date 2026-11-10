import logging

from flask import jsonify, request

from auth import require_auth
from .llm_proxy import stream_chat_completion
from .tool_loop import stream_with_tools
from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from . import http
from .blueprint import chat_bp
from .bootstrap import init_chat  # noqa: F401
from .app_deps import deps

logger = logging.getLogger(__name__)



# -- Spinoff (ephemeral) --

@chat_bp.route("/api/chat/spinoff", methods=["POST"])
@require_auth
def spinoff():
    """Stateless streaming chat — no persistence. Used for ephemeral spin-off conversations."""
    data = request.get_json() or {}
    service_name = data.get("service_name")
    messages_array = data.get("messages", [])

    if not service_name:
        return jsonify({"error": "service_name is required"}), 400
    if not messages_array:
        return jsonify({"error": "messages array is required"}), 400

    def generate():
        for event_type, event_data in stream_chat_completion(service_name, messages_array):
            if event_type == "delta":
                yield encode_sse_delta(event_data["raw"])
            elif event_type == "done":
                yield DONE
            elif event_type == "error":
                yield encode_sse({"error": event_data["message"]})
                return

    return http.sse_response(generate())


# -- Ghost chat (ephemeral, zero-trace) --

@chat_bp.route("/api/chat/ghost", methods=["POST"])
@require_auth
def ghost_chat():
    """Stateless ghost chat — no persistence, no trace. The request carries the
    full message history and the reply streams back without any db write, so a
    refresh erases the thread as designed. mcp_servers enables the tool loop
    without a conversation; tool results are streamed, never stored."""
    data = request.get_json() or {}
    service_name = data.get("service_name")
    messages_array = data.get("messages", [])
    mcp_servers = data.get("mcp_servers") or []

    if not service_name:
        return jsonify({"error": "service_name is required"}), 400
    if not messages_array:
        return jsonify({"error": "messages array is required"}), 400
    if not isinstance(mcp_servers, list):
        return jsonify({"error": "mcp_servers must be a list of server ids"}), 400

    mcp = deps().mcp

    def generate():
        # One manager for the whole stream — discovery is cached, so repeated
        # ghost turns against the same servers do not re-spawn the subprocess.
        tools = mcp.get_all_tools(mcp_servers) if mcp_servers else None
        if tools:
            stream = stream_with_tools(service_name, messages_array, tools, mcp)
        else:
            stream = stream_chat_completion(service_name, messages_array)
        for event_type, event_data in stream:
            if event_type == "delta":
                yield encode_sse_delta(event_data["raw"])
            elif event_type == "tool_call":
                yield encode_sse_event("tool_call", event_data)
            elif event_type == "tool_result":
                yield encode_sse_event("tool_result", event_data)
            elif event_type == "artifact":
                yield encode_sse_event("artifact", {
                    "artifact_type": event_data.get("type"),
                    "title": event_data.get("title"),
                    "content": event_data.get("content"),
                })
            elif event_type == "done":
                yield DONE
            elif event_type == "error":
                yield encode_sse({"error": event_data["message"]})
                return

    # no-store, not just no-cache: ghost replies must never be written to any
    # HTTP cache (browser or intermediate proxy) — the deniability is part of
    # the feature, so a cached body would be a trace.
    return http.sse_response(generate(), headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


# Register admin routes onto chat_bp at module-load time. Importing this
# from inside init_chat() runs after app.register_blueprint(chat_bp), which
# Flask 3 rejects with "The setup method 'route' can no longer be called on
# the blueprint 'chat'". This bottom-of-file import runs while chat.routes
# is being imported by app.py — before the blueprint is registered.
from . import mcp_admin_routes  # noqa: E402,F401
from . import project_files_routes  # noqa: E402,F401
from . import providers_routes  # noqa: E402,F401
from . import settings_routes  # noqa: E402,F401
from . import openrouter_routes  # noqa: E402,F401
from . import project_routes  # noqa: E402,F401
from . import conversation_routes  # noqa: E402,F401
from . import prompt_routes  # noqa: E402,F401
from . import message_routes  # noqa: E402,F401
from . import run_routes  # noqa: E402,F401
from . import critique_routes  # noqa: E402,F401
