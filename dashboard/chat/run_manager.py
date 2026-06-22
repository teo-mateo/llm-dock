"""Background chat-run orchestration (Phase 4 of #58).

Owns the thread pool that executes ChatRunner turns off the request thread, the
post-completion auto-title step, startup recovery of interrupted runs, and the
SSE observer that any HTTP response attaches to.

Design rules (#58):
  - Navigation is not cancellation. The HTTP response is only an observer of
    the event bus; closing it unsubscribes but does not stop the run.
  - The DB is the source of truth. The bus only carries live updates; if the
    process restarts, completed data comes from SQLite.

The observer translates runtime events back into the existing SSE wire format
(via event_codec) so the current frontend keeps working unchanged.
"""
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .event_codec import DONE, encode_sse, encode_sse_event, encode_sse_delta
from .runs import TERMINAL_STATUSES
from .runtime import ChatRunner, ChatRuntimeEvent, ChatTurnRequest, auto_generate_title

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 3.0
# Sentinel event published once a job has fully finished (run + title tail).
# The observer closes the SSE stream when it sees this — distinct from
# run_completed so a trailing conversation_updated can still be delivered.
STREAM_END = "stream_end"


def _sse_frames_for(event: ChatRuntimeEvent):
    """Translate one runtime event into zero or more SSE frames matching the
    legacy wire format. Internal events (run_started, run_cancelled,
    stream_end) produce no frame."""
    t, d = event.type, event.data
    if t == "run_started":
        # Suppressed here: observe() synthesizes run_started up front from the
        # run id it already has, so the client gets the id as the first frame
        # even when a saturated worker pool delays the worker's own publish.
        return []
    if t == "delta":
        return [encode_sse_delta(d["raw"])]
    if t == "tool_call_pending":
        return [encode_sse_event("tool_call_pending", {"index": d["index"], "name": d["name"]})]
    if t == "parse_warning":
        return [encode_sse_event("parse_warning", d)]
    if t == "tool_call":
        return [encode_sse_event("tool_call", {"name": d["name"], "arguments": d["arguments"], "server_id": d["server_id"]})]
    if t == "tool_result":
        return [encode_sse_event("tool_result", {"name": d["name"], "result": d["result"], "server_id": d["server_id"]})]
    if t == "artifact":
        return [encode_sse_event("artifact", {"artifact_type": d["artifact_type"], "title": d.get("title"), "content": d["content"]})]
    if t == "run_completed":
        return [DONE, encode_sse_event("message_saved", {"message_id": d["message_id"], "seq": d["seq"]})]
    if t == "run_failed":
        return [encode_sse({"error": d["error"]})]
    if t == "conversation_updated":
        return [encode_sse_event("conversation_updated", {"id": d["id"], "title": d["title"]})]
    return []


class ChatRunManager:
    def __init__(self, db, event_bus, max_workers: int = 4):
        self.db = db
        self.event_bus = event_bus
        self.runner = ChatRunner(db, event_bus=event_bus)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="chat-run")
        # run_id -> threading.Event, present only while a worker is executing
        # that run. Set to request cooperative mid-stream cancellation.
        self._cancel_flags = {}
        self._flags_lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------

    def recover_interrupted_runs(self) -> int:
        """Mark any run left queued/running by a previous process as failed.

        Called at startup: those workers died with the process and will never
        complete, so they must not linger as a stuck active_run forever.
        """
        stale = self.db.list_active_runs()
        for run in stale:
            self.db.fail_chat_run(run.id, "Interrupted by dashboard restart")
        if stale:
            logger.info("Recovered %d interrupted chat run(s) as failed", len(stale))
        return len(stale)

    def shutdown(self):
        self._executor.shutdown(wait=False)

    # -- starting a run ---------------------------------------------------

    def start(self, conv, run, mcp_manager=None, is_first=False, first_user_content=""):
        """Submit the run to the worker pool and return immediately.

        The caller should already have subscribed an observer to the bus for
        run.id (see subscribe) so no early events are missed.
        """
        self._executor.submit(
            self._execute, conv, run, mcp_manager, is_first, first_user_content,
        )

    def request_cancel(self, run_id):
        """Cancel a run independently of any observer (the Stop button path).

        Sets the cooperative cancel flag (so an executing worker stops at its
        next stream event) AND marks the run cancelled in the DB. The DB update
        is terminal-guarded, so cancelling an already-finished run is a harmless
        no-op that returns the run with its existing status. Returns the run, or
        None if it does not exist.
        """
        with self._flags_lock:
            ev = self._cancel_flags.get(run_id)
        if ev is not None:
            ev.set()
        return self.db.cancel_chat_run(run_id)

    def request_cancel_for_conversation(self, conversation_id, expected_run_id=None):
        """Cancel a conversation's active (queued/running) run by conversation id.

        The Stop button uses this so it never depends on the client having
        captured the run id: the server already created the run when the turn
        started, so it can always be found from the conversation. Returns the
        cancelled run, or None if the conversation has no active run (a harmless
        no-op — e.g. the run already finished). Delegates to request_cancel so
        the cooperative flag is set and the DB update stays terminal-guarded.

        expected_run_id guards against a stale Stop cancelling the wrong run: if
        the caller knows which run it meant to stop (captured from the
        run_started frame), a late-arriving cancel whose target has since
        finished — with a *newer* run now active in the same conversation — must
        not cancel that newer run. When expected_run_id is given and the active
        run is a different one, this is a no-op. When it's omitted (a genuine
        early Stop before run_started), the active run is provably still the one
        the user meant, so "cancel whatever is active" is safe.
        """
        run = self.db.get_active_run_for_conversation(conversation_id)
        if run is None:
            return None
        if expected_run_id is not None and run.id != expected_run_id:
            return None
        return self.request_cancel(run.id)

    def _execute(self, conv, run, mcp_manager, is_first, first_user_content):
        cancel_event = threading.Event()
        with self._flags_lock:
            self._cancel_flags[run.id] = cancel_event
        try:
            msg = self.runner.run(
                run, ChatTurnRequest(conversation=conv, mcp_manager=mcp_manager),
                cancel_check=cancel_event.is_set,
            )
            # Auto-title runs here (not in the SSE response) so a first-message
            # title is generated and persisted even if the client disconnected.
            if msg is not None and is_first:
                try:
                    new_title = auto_generate_title(self.db, conv.id, first_user_content, conv.main_service)
                    if new_title:
                        self.event_bus.publish(run.id, ChatRuntimeEvent("conversation_updated", {"id": conv.id, "title": new_title}))
                except Exception:
                    logger.exception("auto-title failed for run %s", run.id)
        except Exception:
            # ChatRunner.run already records model/tool failures; this guards
            # against anything unexpected so the observer is always released.
            logger.exception("chat run %s crashed in executor", run.id)
        finally:
            with self._flags_lock:
                self._cancel_flags.pop(run.id, None)
            self.event_bus.publish(run.id, ChatRuntimeEvent(STREAM_END, {}))

    # -- observing a run --------------------------------------------------

    def subscribe(self, run_id: str):
        return self.event_bus.subscribe(run_id)

    def subscribe_with_replay(self, run_id: str):
        """Subscribe and capture the run's in-flight history (for reattach)."""
        return self.event_bus.subscribe_with_replay(run_id)

    def observe(self, run_id: str, q, replay=()):
        """SSE generator: drain the bus queue for a run, emitting legacy SSE
        frames, until the STREAM_END sentinel. Injects heartbeats on idle so
        the connection stays alive during slow model output.

        `replay` is the history captured atomically with the subscription (see
        subscribe_with_replay): for a client reattaching mid-run it replays
        everything generated before it subscribed, so the in-progress turn
        renders in full before the live tail. Empty for the fresh-send path.

        Closing this generator (client disconnect) only unsubscribes — the
        background run keeps going.
        """
        start = time.monotonic()
        try:
            # Expose the run id to the client as the very first frame, before
            # any heartbeat — independent of when the (possibly queued) worker
            # actually starts and publishes its own run_started (suppressed in
            # _sse_frames_for to avoid a duplicate). Lets the client POST
            # /runs/<id>/cancel even for a still-queued run.
            yield encode_sse_event("run_started", {"run_id": run_id})
            # Replay the in-flight history first so a reattaching client sees the
            # content generated before it returned. These events are NOT on the
            # live queue (the snapshot was taken atomically with the subscribe),
            # so there is no duplication with the loop below.
            for event in replay:
                for frame in _sse_frames_for(event):
                    yield frame
                if event.type == STREAM_END:
                    return
            while True:
                try:
                    event = q.get(timeout=HEARTBEAT_INTERVAL_S)
                except queue.Empty:
                    # Backstop for a reattaching observer that subscribed after
                    # the run already published STREAM_END: close on the durable
                    # DB state instead of heartbeating forever.
                    run = self.db.get_chat_run(run_id)
                    if run is None or run.status in TERMINAL_STATUSES:
                        yield encode_sse_event("run_status", {"status": run.status if run else "unknown"})
                        return
                    yield encode_sse_event("heartbeat", {"elapsed_s": round(time.monotonic() - start, 1)})
                    continue
                for frame in _sse_frames_for(event):
                    yield frame
                if event.type == STREAM_END:
                    return
        finally:
            self.event_bus.unsubscribe(run_id, q)
