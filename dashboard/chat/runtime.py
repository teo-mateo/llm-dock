"""Chat turn runtime (Phase 3 of #58).

ChatRunner is the background job-runner core: it executes one model/tool turn
and persists the result, decoupled from any Flask SSE response. It can be
called directly (a unit test, a background thread in Phase 4) — it never reads
Flask globals and never depends on a live SSE client.

Responsibilities (mirrors the persistence the old routes._stream_response did
inline, minus the SSE framing and the partial-save-on-disconnect logic, which
is obsolete once a run completes in the background):

  - mark the run running
  - build the prompt from persisted conversation state
  - drive the plain model stream or the MCP tool loop
  - accumulate content / reasoning / tool calls / artifacts / parse warning
  - on completion: persist the assistant message + artifacts, mark run completed
  - on model/tool error: mark run failed with useful error text, persist no
    completed assistant message
  - publish runtime events to the in-memory event bus for any live observer

The user message is assumed to be already persisted (the caller creates it and
the run before invoking the runner); the runner builds messages from
db.get_messages().
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .models import Message, Artifact, Conversation
from .runs import ChatRunStatus
from .llm_proxy import stream_chat_completion
from .tool_loop import stream_with_tools
from .prompt_builder import build_chat_messages

logger = logging.getLogger(__name__)


@dataclass
class ChatRuntimeEvent:
    """A normalized event published to the bus during a run.

    `type` is one of the runtime event types (#58): run_started, delta,
    tool_call_pending, tool_call, tool_result, artifact, parse_warning,
    run_completed, run_failed. SSE encoding of these lives in event_codec.
    """
    type: str
    data: dict = field(default_factory=dict)


@dataclass
class ChatTurnRequest:
    """Everything the runner needs to execute a turn, passed explicitly rather
    than read from Flask globals."""
    conversation: Conversation
    mcp_manager: object = None


class ChatRunner:
    def __init__(self, db, event_bus=None):
        self.db = db
        self.event_bus = event_bus

    def _emit(self, run_id: str, type: str, data: dict = None):
        if self.event_bus is not None:
            self.event_bus.publish(run_id, ChatRuntimeEvent(type, data or {}))

    def _build_stream(self, conv: Conversation, mcp_manager):
        messages = self.db.get_messages(conv.id)
        enabled_servers = json.loads(conv.mcp_servers_json) if conv.mcp_servers_json else []
        messages_array = build_chat_messages(conv.main_system_prompt, messages, enabled_servers)
        tools = mcp_manager.get_all_tools(enabled_servers) if mcp_manager and enabled_servers else None
        if tools:
            return stream_with_tools(conv.main_service, messages_array, tools, mcp_manager)
        return stream_chat_completion(conv.main_service, messages_array)

    def run(self, run, request: ChatTurnRequest) -> Optional[Message]:
        """Execute the turn for an existing (queued) run.

        Returns the persisted assistant Message on success, or None on failure
        (the run is marked failed). Never raises for model/tool errors — they
        are recorded on the run.
        """
        db = self.db
        conv = request.conversation
        mcp_manager = request.mcp_manager
        run_id = run.id

        # Claim the run. update_chat_run_status no-ops on a terminal row, so if
        # the run was cancelled before the worker picked it up, the transition
        # doesn't win — do no work and surface the terminal state.
        started = db.update_chat_run_status(run_id, ChatRunStatus.RUNNING, active_step="generating")
        if started is None or started.status != ChatRunStatus.RUNNING:
            status = started.status if started else "cancelled"
            self._emit(run_id, f"run_{status}", {"run_id": run_id})
            return None
        self._emit(run_id, "run_started", {"run_id": run_id, "conversation_id": conv.id})

        assistant_msg_id = str(uuid.uuid4())
        accumulated_content = ""
        accumulated_reasoning = ""
        collected_tool_calls = []
        collected_artifacts = []
        last_parse_warning = None

        try:
            stream = self._build_stream(conv, mcp_manager)
            for event_type, data in stream:
                if event_type == "delta":
                    accumulated_content += data.get("content", "") or ""
                    accumulated_reasoning += data.get("reasoning_content", "") or ""
                    self._emit(run_id, "delta", data)
                elif event_type == "tool_call_pending":
                    self._emit(run_id, "tool_call_pending", {"index": data["index"], "name": data["name"]})
                elif event_type == "parse_warning":
                    last_parse_warning = data
                    self._emit(run_id, "parse_warning", data)
                elif event_type == "tool_call":
                    collected_tool_calls.append({
                        "name": data["name"],
                        "arguments": data["arguments"],
                        "server_id": data["server_id"],
                    })
                    self._emit(run_id, "tool_call", {"name": data["name"], "arguments": data["arguments"], "server_id": data["server_id"]})
                elif event_type == "tool_result":
                    for tc in reversed(collected_tool_calls):
                        if tc["name"] == data["name"] and "result" not in tc:
                            tc["result"] = data["result"]
                            break
                    self._emit(run_id, "tool_result", {"name": data["name"], "result": data["result"], "server_id": data["server_id"]})
                elif event_type == "artifact":
                    collected_artifacts.append(data)
                    self._emit(run_id, "artifact", {"artifact_type": data["type"], "title": data.get("title"), "content": data["content"]})
                elif event_type == "done":
                    assistant_msg = Message(
                        id=assistant_msg_id,
                        conversation_id=conv.id,
                        role="assistant",
                        content=data["content"],
                        # Full cross-round reasoning the user saw wins over the
                        # final round's reasoning (matches _stream_response);
                        # falls back to the done payload for the single round.
                        reasoning_content=(accumulated_reasoning or data["reasoning_content"]) or None,
                        model_service=conv.main_service,
                        tool_calls_json=json.dumps(collected_tool_calls) if collected_tool_calls else None,
                        parse_warning_json=json.dumps(last_parse_warning) if last_parse_warning else None,
                        seq=0,  # assigned inside the atomic completion
                    )
                    artifacts = [
                        Artifact(
                            id=str(uuid.uuid4()),
                            message_id=assistant_msg_id,
                            artifact_type=art["type"],
                            content=art["content"],
                            title=art.get("title"),
                            language=art.get("language"),
                        )
                        for art in collected_artifacts
                    ]
                    # Atomic + terminal-guarded: writes the message, artifacts,
                    # and the completed status together, or nothing if the run
                    # was cancelled mid-stream.
                    saved = db.complete_run_with_message(run_id, assistant_msg, artifacts)
                    if saved is None:
                        self._emit(run_id, "run_cancelled", {"run_id": run_id})
                        return None
                    self._emit(run_id, "run_completed", {"message_id": saved.id, "seq": saved.seq})
                    return saved
                elif event_type == "error":
                    return self._fail(run_id, data["message"])

            # Stream exhausted without a `done` event.
            return self._fail(run_id, "Stream ended unexpectedly")
        except Exception as exc:
            logger.exception("Chat run %s crashed", run_id)
            return self._fail(run_id, str(exc) or "internal error")

    def _fail(self, run_id: str, error: str) -> None:
        self.db.fail_chat_run(run_id, error)
        self._emit(run_id, "run_failed", {"error": error})
        return None
