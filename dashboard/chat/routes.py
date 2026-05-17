import datetime
import json
import logging
import os
import queue
import threading
import time
import uuid
from typing import Optional

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
    from . import mcp_config
    mgr = MCPClientManager()
    app.config["MCP_MANAGER"] = mgr
    mcp_config.bind_manager(mgr)
    mcp_config.reload()

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


@chat_bp.route("/api/chat/conversations/delete", methods=["POST"])
@require_auth
def delete_conversations_batch():
    data = request.get_json() or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return jsonify({"error": "ids must be a list of strings"}), 400
    deleted = _get_db().delete_conversations(ids)
    return jsonify({"ok": True, "deleted": deleted})


# -- Messages --

HEARTBEAT_INTERVAL_S = 3.0
# Bounded queue size between producer and consumer. Large enough to absorb a
# burst of token deltas without blocking the producer in normal operation;
# small enough that an abandoned producer can't grow unbounded memory.
HEARTBEAT_QUEUE_MAX = 64
# Polling interval on the producer side. Caps how long after the consumer
# sets `stop` the producer waits before noticing on a full-queue path.
HEARTBEAT_PRODUCER_POLL_S = 0.5


def _with_heartbeat(it, interval: float = HEARTBEAT_INTERVAL_S):
    """Yield items from `it` and inject ("__heartbeat__", {elapsed_s}) on idle.

    The inner stream blocks on upstream HTTP (`requests.iter_lines`), so a
    naive `for ev in it:` can sit for seconds without emitting anything. We
    drive the inner iterator on a worker thread feeding a bounded queue, and
    the outer loop pops with a timeout — on every timeout we yield a
    heartbeat event so the SSE pipe stays visibly alive.

    Cancellation contract (client disconnect / Stop button / navigation):

    - The consumer's `finally` sets `stop` and drains the queue, which both
      caps memory and unblocks the producer if it's parked on a full queue.
    - The producer checks `stop` between events and on every full-queue
      retry. Once it notices, it closes the inner generator and exits.
    - Closing the inner generator (`it.close()`) propagates `GeneratorExit`
      into `stream_with_tools` / `stream_chat_completion` at their next
      yield, which short-circuits any further tool execution in
      `tool_loop.py` and prevents new MCP side-effects after disconnect.

    Caveat: this is cooperative. If the producer is currently inside
    `requests.iter_lines` waiting on a socket read, it won't notice `stop`
    until the next chunk arrives (or the upstream times out). Likewise, a
    tool call already in progress in `mcp_manager.call_tool()` runs to
    completion — those subprocess calls aren't interruptible from here.
    True interruption would need a cancel token threaded through to
    `stream_chat_completion`/`stream_with_tools`; tracked as a follow-up.
    """
    q = queue.Queue(maxsize=HEARTBEAT_QUEUE_MAX)
    sentinel = object()
    stop = threading.Event()
    # Out-of-band termination flag. The queued `sentinel` is a fast-path
    # optimization for prompt shutdown, but it can be dropped if the queue
    # is full for the whole producer-put timeout (slow/stalled consumer).
    # `finished` is set unconditionally in the producer's finally, so the
    # consumer can always detect end-of-stream even when the sentinel never
    # makes it into the queue.
    finished = threading.Event()

    def producer():
        try:
            for ev in it:
                if stop.is_set():
                    break
                # Bounded put with periodic stop checks so a dead consumer
                # can't permanently park us here.
                while True:
                    try:
                        q.put(("ev", ev), timeout=HEARTBEAT_PRODUCER_POLL_S)
                        break
                    except queue.Full:
                        if stop.is_set():
                            break
                if stop.is_set():
                    break
        except BaseException as e:
            try:
                q.put(("exc", e), timeout=HEARTBEAT_PRODUCER_POLL_S)
            except queue.Full:
                logger.warning("_with_heartbeat: dropped exception on full queue", exc_info=e)
        finally:
            # Close the inner generator FROM THIS THREAD. The generator
            # protocol forbids closing a generator that's running on another
            # thread, so the consumer-side `finally` only sets `stop` and
            # leaves the actual close to us.
            try:
                it.close()
            except Exception:
                logger.exception("_with_heartbeat: error closing inner stream")
            # Mark completion BEFORE the (droppable) sentinel put so the
            # consumer can terminate via `finished` even if the queue stays
            # full and the sentinel never lands.
            finished.set()
            try:
                q.put(sentinel, timeout=HEARTBEAT_PRODUCER_POLL_S)
            except queue.Full:
                pass

    threading.Thread(target=producer, daemon=True).start()
    idle_since = time.monotonic()
    try:
        while True:
            try:
                item = q.get(timeout=interval)
            except queue.Empty:
                # Queue is empty. If the producer already finished, the
                # sentinel was either consumed or dropped on a full queue —
                # either way there is nothing more coming, so terminate
                # instead of emitting heartbeats forever.
                if finished.is_set():
                    return
                yield ("__heartbeat__", {"elapsed_s": round(time.monotonic() - idle_since, 1)})
                continue
            if item is sentinel:
                return
            kind, payload = item
            if kind == "exc":
                raise payload
            idle_since = time.monotonic()
            yield payload
    finally:
        # Consumer is exiting (normal completion, GeneratorExit from client
        # disconnect, or an exception thrown into us). Signal the producer
        # to stop and drain anything pending so it isn't blocked on a full
        # queue put. The drain is required: without it, a producer parked
        # in q.put() at maxsize won't notice the stop event until its 0.5s
        # timeout fires, and meanwhile would still process its next event.
        stop.set()
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass


def _stream_response(db: ChatDB, conv: Conversation, user_msg: Message, mcp_manager=None):
    """Generator that streams SSE events for a chat completion."""
    # Save user message
    db.add_message(user_msg)
    db.touch_conversation(conv.id)

    # Build messages array, augmenting system prompt with tool hints and
    # an explicit "today's date" line. Models keep training on data with a
    # past cutoff, so without this they'll write 2024/2025 in queries even
    # when the user is asking about now.
    messages = db.get_messages(conv.id)
    enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
    system_prompt = conv.main_system_prompt
    if enabled_servers:
        hints = get_tool_hints(enabled_servers)
        if hints:
            system_prompt = f"{system_prompt}\n\n{hints}" if system_prompt else hints
    today = datetime.date.today()
    date_line = f"Current date: {today.isoformat()} ({today.strftime('%A')}). Use this as \"today\" when interpreting time-sensitive questions."
    system_prompt = f"{system_prompt}\n\n{date_line}" if system_prompt else date_line
    messages_array = build_messages_array(system_prompt, messages)

    # Get MCP tools
    tools = mcp_manager.get_all_tools(enabled_servers) if mcp_manager and enabled_servers else None

    # Choose streaming method
    if tools:
        stream = stream_with_tools(conv.main_service, messages_array, tools, mcp_manager)
    else:
        stream = stream_chat_completion(conv.main_service, messages_array)
    stream = _with_heartbeat(stream)

    assistant_msg_id = str(uuid.uuid4())
    done = False
    had_error = False              # gate _save_partial against the error path
    saved_partial = False          # avoid double-save
    accumulated_content = ""       # per-delta accumulators for partial-save
    accumulated_reasoning = ""
    collected_tool_calls = []
    collected_artifacts = []
    last_parse_warning = None      # most recent parse_warning event, persisted on done

    def _save_partial():
        """Persist whatever we accumulated when the client disconnects mid-stream.

        Called from the GeneratorExit handler and the finally clause. No-op
        when the stream completed normally, errored, already saved, or never
        produced any text. Includes stale-stream guards so an old
        disconnected stream can't append a partial after newer state has
        landed (a user edit or a fresh user turn).
        """
        nonlocal saved_partial
        if saved_partial or done or had_error:
            return
        if not (accumulated_content or accumulated_reasoning):
            return
        # Stale-stream guard:
        #   (1) user message deleted — edit_message at routes.py:340 calls
        #       delete_messages_from_seq, dropping user_msg from the DB.
        #   (2) newer messages have landed — next_seq advanced past
        #       user_msg.seq, so a partial inserted now would attach after
        #       unrelated history.
        if db.get_message(user_msg.id) is None:
            logger.info(
                "Skipping partial-save for %s: user message %s no longer exists (edited?)",
                assistant_msg_id, user_msg.id,
            )
            return
        if db.next_seq(conv.id) - 1 != user_msg.seq:
            logger.info(
                "Skipping partial-save for %s: conversation advanced past user_msg.seq=%d",
                assistant_msg_id, user_msg.seq,
            )
            return
        try:
            db.add_message(Message(
                id=assistant_msg_id,
                conversation_id=conv.id,
                role="assistant",
                content=accumulated_content,
                reasoning_content=accumulated_reasoning or None,
                model_service=conv.main_service,
                # Skip partial tool_calls: a tool_call without its result is
                # misleading in the UI. Text content is the primary value.
                seq=db.next_seq(conv.id),
            ))
            db.touch_conversation(conv.id)
            saved_partial = True
            logger.info(
                "Saved partial assistant message %s (%d content chars, %d reasoning chars)",
                assistant_msg_id, len(accumulated_content), len(accumulated_reasoning),
            )
        except Exception:
            logger.exception("Failed to save partial assistant message on disconnect")

    try:
        for event_type, data in stream:
            if event_type == "__heartbeat__":
                yield f"data: {json.dumps({'type': 'heartbeat', 'elapsed_s': data['elapsed_s']})}\n\n"
                continue
            if event_type == "delta":
                accumulated_content += data.get("content", "") or ""
                accumulated_reasoning += data.get("reasoning_content", "") or ""
                yield f"data: {data['raw']}\n\n"
            elif event_type == "tool_call_pending":
                yield f"data: {json.dumps({'type': 'tool_call_pending', 'index': data['index'], 'name': data['name']})}\n\n"
            elif event_type == "parse_warning":
                # Format-drift signal from llm_proxy. Stash so we can persist
                # alongside the message on `done`; also forward live so the UI
                # shows the chip before the response finishes streaming.
                last_parse_warning = data
                yield f"data: {json.dumps({'type': 'parse_warning', **data})}\n\n"
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
                    # `data["reasoning_content"]` is only the FINAL model
                    # round's reasoning. In a multi-round tool flow the
                    # reasoning emitted before each `finish_reason=tool_calls`
                    # is streamed to the UI (continuous reasoning display) but
                    # would be dropped on the post-save refetch if we persisted
                    # only the last round. `accumulated_reasoning` is the full
                    # cross-round trace the user actually saw; persist that.
                    # Falls back to the done payload for the single-round case
                    # where they are identical.
                    reasoning_content=(accumulated_reasoning or data["reasoning_content"]) or None,
                    model_service=conv.main_service,
                    tool_calls_json=json.dumps(collected_tool_calls) if collected_tool_calls else None,
                    parse_warning_json=json.dumps(last_parse_warning) if last_parse_warning else None,
                    seq=next_seq,
                )
                db.add_message(assistant_msg)
                # Flip done IMMEDIATELY after the assistant row is in. If an
                # artifact save throws below, the finally clause must NOT
                # attempt a second insert with the same assistant_msg_id.
                done = True
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
                yield "data: [DONE]\n\n"
                yield f"data: {json.dumps({'type': 'message_saved', 'message_id': assistant_msg_id, 'seq': next_seq})}\n\n"
            elif event_type == "error":
                # Set had_error BEFORE yielding — a client disconnect during
                # the yield would otherwise fire GeneratorExit -> finally
                # without the flag set, and a server-side model failure with
                # accumulated deltas would still write a partial.
                had_error = True
                yield f"data: {json.dumps({'error': data['message']})}\n\n"
                return

        if not done:
            yield f"data: {json.dumps({'error': 'Stream ended unexpectedly'})}\n\n"
    except GeneratorExit:
        # Client disconnected mid-stream (navigation, tab close, network
        # drop). Flask raises this at the next yield after the WSGI layer
        # notices the broken socket. Persist whatever we have so the user
        # doesn't lose the in-progress reply when they return.
        _save_partial()
        raise                       # MUST re-raise so the generator closes
    finally:
        # Belt and suspenders: any non-GeneratorExit exit that didn't already
        # save still tries to flush. No-op when done=True, had_error=True,
        # or already saved.
        _save_partial()


def _auto_generate_title(db, conv_id: str, first_user_content: str, service_name: str) -> Optional[str]:
    """Generate a 3–6 word title for a fresh conversation and persist it.

    Runs synchronously inside the SSE response that delivered the assistant
    reply — see send_message. Returns the new title on success so the caller
    can emit a conversation_updated event to the open client, or None if
    nothing should be pushed (manual rename already won, model produced
    empty output, etc).
    """
    conv = db.get_conversation(conv_id)
    if conv is None or conv.title != "New Conversation":
        return None

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
    if '\n' in title:
        lines = [l.strip().strip('"\'').strip() for l in title.split('\n') if l.strip()]
        title = lines[-1] if lines else title
    title = title.strip('"\'*#').strip()
    if not title:
        return None

    # Re-check before write: a rename arriving DURING the model call would
    # otherwise be clobbered.
    conv2 = db.get_conversation(conv_id)
    if conv2 is None or conv2.title != "New Conversation":
        return None

    final = title[:100]
    db.update_conversation(conv_id, title=final)
    logger.info(f"Auto-generated title for {conv_id}: {final}")
    return final


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
        # Generate the title inline so we can push it to the client over the
        # same SSE pipe before closing — otherwise the sidebar shows
        # "New Conversation" until the next manual refetch.
        if is_first:
            try:
                new_title = _auto_generate_title(db, conv_id, content, conv.main_service)
                if new_title:
                    yield f"data: {json.dumps({'type': 'conversation_updated', 'id': conv_id, 'title': new_title})}\n\n"
            except Exception:
                logger.exception("auto-title failed")

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


# Register admin routes onto chat_bp at module-load time. Importing this
# from inside init_chat() runs after app.register_blueprint(chat_bp), which
# Flask 3 rejects with "The setup method 'route' can no longer be called on
# the blueprint 'chat'". This bottom-of-file import runs while chat.routes
# is being imported by app.py — before the blueprint is registered.
from . import mcp_admin_routes  # noqa: E402,F401
