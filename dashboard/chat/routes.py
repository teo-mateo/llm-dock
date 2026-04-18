import json
import logging
import os
import threading
import uuid

from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context

from auth import require_auth
from .db import ChatDB
from .models import Conversation, Message, Critique, Artifact
from .constants import DEFAULT_MAIN_SYSTEM_PROMPT, DEFAULT_SIDEKICK_SYSTEM_PROMPT, DEFAULT_CONTEXT_WINDOW
from .llm_proxy import stream_chat_completion, build_messages_array, resolve_service
from .critique import build_critique_context, request_critique, validate_annotations
from .mcp_registry import list_available_servers, get_tool_hints
from .tool_loop import stream_with_tools

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


def init_chat(app, db_path: str = None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chat.db")
    db = ChatDB(db_path)
    app.config["CHAT_DB"] = db

    from .mcp_client import MCPClientManager
    app.config["MCP_MANAGER"] = MCPClientManager()

    logger.info("Chat subsystem initialized")


def _get_db() -> ChatDB:
    return current_app.config["CHAT_DB"]


def _get_mcp():
    return current_app.config["MCP_MANAGER"]


@chat_bp.route("/api/chat/mcp-servers", methods=["GET"])
@require_auth
def get_mcp_servers():
    return jsonify({"servers": list_available_servers()})


# -- Conversations CRUD --

@chat_bp.route("/api/chat/conversations", methods=["POST"])
@require_auth
def create_conversation():
    data = request.get_json() or {}
    main_service = data.get("main_service")
    if not main_service:
        return jsonify({"error": "main_service is required"}), 400

    conv = Conversation(
        id=str(uuid.uuid4()),
        title=data.get("title", "New Conversation"),
        main_service=main_service,
        sidekick_service=data.get("sidekick_service"),
        main_system_prompt=data.get("main_system_prompt", DEFAULT_MAIN_SYSTEM_PROMPT),
        sidekick_system_prompt=data.get("sidekick_system_prompt", DEFAULT_SIDEKICK_SYSTEM_PROMPT),
        parent_conversation_id=data.get("parent_conversation_id"),
        selected_text=data.get("selected_text"),
    )
    conv = _get_db().create_conversation(conv)
    return jsonify(conv.to_dict(include_messages=True)), 201


@chat_bp.route("/api/chat/conversations", methods=["GET"])
@require_auth
def list_conversations():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    convs, total = _get_db().list_conversations(limit=limit, offset=offset)
    return jsonify({
        "conversations": [c.to_dict() for c in convs],
        "total": total,
    })


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@require_auth
def get_conversation(conv_id):
    db = _get_db()
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    # Include critiques and artifacts
    critiques = db.get_critiques_for_conversation(conv_id)
    artifacts = db.get_artifacts_for_conversation(conv_id)
    result = conv.to_dict(include_messages=True)
    result["critiques"] = {msg_id: c.to_dict() for msg_id, c in critiques.items()}
    result["artifacts"] = {msg_id: [a.to_dict() for a in arts] for msg_id, arts in artifacts.items()}
    return jsonify(result)


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["PUT"])
@require_auth
def update_conversation(conv_id):
    data = request.get_json() or {}
    db = _get_db()
    conv = db.update_conversation(conv_id, **data)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(conv.to_dict())


@chat_bp.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
@require_auth
def delete_conversation(conv_id):
    if _get_db().delete_conversation(conv_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Conversation not found"}), 404


# -- Messages --

def _stream_response(db: ChatDB, conv: Conversation, user_msg: Message, mcp_manager=None):
    """Generator that streams SSE events for a chat completion."""
    # Save user message
    db.add_message(user_msg)
    db.touch_conversation(conv.id)

    # Build messages array, augmenting system prompt with tool hints
    messages = db.get_messages(conv.id)
    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    system_prompt = conv.main_system_prompt
    if enabled_servers:
        hints = get_tool_hints(enabled_servers)
        if hints:
            system_prompt = f"{system_prompt}\n\n{hints}" if system_prompt else hints
    messages_array = build_messages_array(system_prompt, messages)

    # Get MCP tools
    tools = mcp_manager.get_all_tools(enabled_servers) if mcp_manager and enabled_servers else None

    # Choose streaming method
    if tools:
        stream = stream_with_tools(conv.main_service, messages_array, tools, mcp_manager)
    else:
        stream = stream_chat_completion(conv.main_service, messages_array)

    assistant_msg_id = str(uuid.uuid4())
    done = False
    collected_tool_calls = []
    collected_artifacts = []

    for event_type, data in stream:
        if event_type == "delta":
            yield f"data: {data['raw']}\n\n"
        elif event_type == "tool_call":
            collected_tool_calls.append({
                "name": data["name"],
                "arguments": data["arguments"],
                "server_id": data["server_id"],
            })
            yield f"data: {json.dumps({'type': 'tool_call', 'name': data['name'], 'arguments': data['arguments'], 'server_id': data['server_id']})}\n\n"
        elif event_type == "tool_result":
            for tc in reversed(collected_tool_calls):
                if tc["name"] == data["name"] and "result" not in tc:
                    tc["result"] = data["result"]
                    break
            yield f"data: {json.dumps({'type': 'tool_result', 'name': data['name'], 'result': data['result'], 'server_id': data['server_id']})}\n\n"
        elif event_type == "artifact":
            collected_artifacts.append(data)
            # Send artifact to frontend (without full content to keep SSE lean)
            yield f"data: {json.dumps({'type': 'artifact', 'artifact_type': data['type'], 'title': data.get('title'), 'content': data['content']}, default=str)}\n\n"
        elif event_type == "done":
            next_seq = db.next_seq(conv.id)
            assistant_msg = Message(
                id=assistant_msg_id,
                conversation_id=conv.id,
                role="assistant",
                content=data["content"],
                reasoning_content=data["reasoning_content"],
                model_service=conv.main_service,
                tool_calls_json=json.dumps(collected_tool_calls) if collected_tool_calls else None,
                seq=next_seq,
            )
            db.add_message(assistant_msg)
            # Save artifacts linked to this message
            for art_data in collected_artifacts:
                db.save_artifact(Artifact(
                    id=str(uuid.uuid4()),
                    message_id=assistant_msg_id,
                    artifact_type=art_data["type"],
                    content=art_data["content"],
                    title=art_data.get("title"),
                    language=art_data.get("language"),
                ))
            db.touch_conversation(conv.id)
            done = True
            yield "data: [DONE]\n\n"
            yield f"data: {json.dumps({'type': 'message_saved', 'message_id': assistant_msg_id, 'seq': next_seq})}\n\n"
        elif event_type == "error":
            yield f"data: {json.dumps({'error': data['message']})}\n\n"
            return

    if not done:
        yield f"data: {json.dumps({'error': 'Stream ended unexpectedly'})}\n\n"


def _auto_generate_title(app, db_path: str, conv_id: str, first_user_content: str, service_name: str):
    """Background thread to auto-generate a conversation title."""
    try:
        from .db import ChatDB as _ChatDB
        _db = _ChatDB(db_path)
        conv = _db.get_conversation(conv_id)
        if conv is None or conv.title != "New Conversation":
            return

        title_messages = [
            {"role": "system", "content": "Generate a concise 3-6 word title for a conversation that starts with the following message. Return ONLY the title, nothing else. Do not explain or add anything."},
            {"role": "user", "content": first_user_content},
        ]

        full_content = ""
        full_reasoning = ""
        for event_type, data in stream_chat_completion(service_name, title_messages):
            if event_type == "delta":
                full_content += data.get("content", "")
            elif event_type == "done":
                full_content = data["content"]
                full_reasoning = data.get("reasoning_content") or ""
                break

        # Some models put short responses in reasoning_content instead of content
        title = full_content.strip() or full_reasoning.strip()
        # Extract last non-empty line as the likely title if reasoning is verbose
        if '\n' in title:
            lines = [l.strip().strip('"\'').strip() for l in title.split('\n') if l.strip()]
            title = lines[-1] if lines else title
        title = title.strip('"\'*#').strip()
        if title:
            _db.update_conversation(conv_id, title=title[:100])
            logger.info(f"Auto-generated title for {conv_id}: {title}")
    except Exception:
        logger.exception("Failed to auto-generate conversation title")


@chat_bp.route("/api/chat/conversations/<conv_id>/messages", methods=["POST"])
@require_auth
def send_message(conv_id):
    db = _get_db()
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json() or {}
    content = data.get("content", "").strip()
    images = data.get("images", [])
    if not content and not images:
        return jsonify({"error": "content or images required"}), 400

    images_json = json.dumps(images) if images else None

    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="user",
        content=content,
        images_json=images_json,
        seq=db.next_seq(conv_id),
    )

    # Grab MCP manager inside request context
    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    mcp_manager = _get_mcp() if enabled_servers else None

    # Check if this is the first message — trigger auto-title after response
    existing_messages = db.get_messages(conv_id)
    is_first = len(existing_messages) == 0

    def generate():
        yield from _stream_response(db, conv, user_msg, mcp_manager=mcp_manager)
        # Generate title after the main response is done (same model, single slot)
        if is_first:
            db_path = db.db_path
            t = threading.Thread(
                target=_auto_generate_title,
                args=(None, db_path, conv_id, content, conv.main_service),
                daemon=True,
            )
            t.start()

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@chat_bp.route("/api/chat/conversations/<conv_id>/messages/<msg_id>", methods=["PUT"])
@require_auth
def edit_message(conv_id, msg_id):
    db = _get_db()
    conv = db.get_conversation(conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    msg = db.get_message(msg_id)
    if msg is None or msg.conversation_id != conv_id:
        return jsonify({"error": "Message not found"}), 404
    if msg.role != "user":
        return jsonify({"error": "Can only edit user messages"}), 400

    data = request.get_json() or {}
    content = data.get("content", "").strip()
    images = data.get("images", [])
    if not content and not images:
        return jsonify({"error": "content or images required"}), 400

    images_json = json.dumps(images) if images else None

    # Delete this message and all subsequent
    db.delete_messages_from_seq(conv_id, msg.seq)

    # Grab MCP manager inside request context
    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    mcp_mgr = _get_mcp() if enabled_servers else None

    # Create new user message at same seq
    new_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="user",
        content=content,
        images_json=images_json,
        seq=msg.seq,
    )

    def generate():
        yield from _stream_response(db, conv, new_msg, mcp_manager=mcp_mgr)

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# -- Critique --

@chat_bp.route("/api/chat/messages/<msg_id>/critique", methods=["POST"])
@require_auth
def create_critique(msg_id):
    db = _get_db()
    msg = db.get_message(msg_id)
    if msg is None:
        return jsonify({"error": "Message not found"}), 404
    if msg.role != "assistant":
        return jsonify({"error": "Can only critique assistant messages"}), 400

    conv = db.get_conversation(msg.conversation_id)
    if conv is None or not conv.sidekick_service:
        return jsonify({"error": "No sidekick service configured for this conversation"}), 400

    data = request.get_json() or {}
    context_window = data.get("context_window", DEFAULT_CONTEXT_WINDOW)
    extra_instructions = data.get("extra_instructions", "")

    # Build context from conversation messages
    messages = db.get_messages(conv.id)
    context = build_critique_context(messages, msg, context_window)

    # Request critique from sidekick
    result = request_critique(conv.sidekick_service, context, extra_instructions=extra_instructions)

    if "error" in result and "verdict" not in result:
        return jsonify(result), 502

    # Validate annotation spans against original content
    annotations = result.get("annotations", [])
    validated = validate_annotations(annotations, msg.content)

    critique = Critique(
        id=str(uuid.uuid4()),
        message_id=msg_id,
        sidekick_service=conv.sidekick_service,
        annotations_json=json.dumps(validated),
        summary=result.get("summary"),
        verdict=result.get("verdict"),
        raw_response=result.get("raw_response"),
    )
    saved = db.save_critique(critique)
    return jsonify(saved.to_dict())


@chat_bp.route("/api/chat/messages/<msg_id>/critique", methods=["GET"])
@require_auth
def get_critique(msg_id):
    critique = _get_db().get_critique(msg_id)
    if critique is None:
        return jsonify({"error": "No critique found"}), 404
    return jsonify(critique.to_dict())


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
                yield f"data: {event_data['raw']}\n\n"
            elif event_type == "done":
                yield "data: [DONE]\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'error': event_data['message']})}\n\n"
                return

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
