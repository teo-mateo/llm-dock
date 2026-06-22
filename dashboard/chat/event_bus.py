"""In-memory pub/sub for live run observers (Phase 3 of #58).

This is NOT a source of truth — it only fans out live runtime events from a
background run to whoever is currently watching (an SSE response, a reattached
stream). Completed data always comes from SQLite; if the process restarts, the
bus is empty and that's fine.

One bus instance is shared per dashboard process. Observers subscribe by
run_id and get a Queue they drain; publishers push events to every current
subscriber of that run. Thread-safe: the background runner publishes from a
worker thread while SSE generators drain from request threads.
"""
import json
import queue
import threading
from collections import namedtuple

# Per-observer queue cap. Generous enough to absorb a normal burst of token
# deltas, but bounded so a live-but-non-draining client (TCP backpressure, a
# stalled proxy) can't make the publishing worker accumulate memory without
# limit. On overflow the OLDEST event is evicted, which keeps the newest
# events — crucially including the terminal stream_end — so the observer still
# terminates. Dropped middle deltas don't lose data: the DB has the full reply.
SUBSCRIBER_QUEUE_MAX = 2048

# Event types after which a run is finished and its replay history is dropped
# (future reattachers fall back to the DB). Includes the per-turn terminal
# runtime events — so a ChatRunner used directly with a bus, which ends on
# run_completed/run_failed/run_cancelled and never emits the manager-only
# stream_end, still frees its history — as well as stream_end itself.
_TERMINAL_TYPES = frozenset({"run_completed", "run_failed", "run_cancelled", "stream_end"})

# A duck-typed stand-in for runtime.ChatRuntimeEvent, used only for the
# coalesced delta a reattach replay emits. Has .type / .data like the real
# event, so _sse_frames_for consumes it identically — and the bus stays free of
# a runtime import.
_ReplayEvent = namedtuple("_ReplayEvent", ["type", "data"])


class _ReplayBuffer:
    """A run's in-flight history, kept so a reattaching client can replay it.

    Consecutive deltas are folded into a single accumulated segment, so memory
    scales with the length of the generated text rather than the number of
    token events (a long reply would otherwise retain one dict + raw-JSON string
    per token until the run ends). Non-delta events (tool calls/results,
    artifacts, parse warnings) are kept discrete and in order; a delta segment
    that follows them starts fresh, preserving the per-round boundaries the
    frontend relies on (it resets visible content after each tool result).
    """
    __slots__ = ("_segments",)

    def __init__(self):
        # Each segment is either a [content_parts, reasoning_parts] list (a run
        # of coalesced deltas) or a non-delta event kept as-is.
        self._segments = []

    def add(self, event):
        if getattr(event, "type", None) == "delta":
            data = event.data or {}
            tail = self._segments[-1] if self._segments else None
            if isinstance(tail, list):
                tail[0].append(data.get("content") or "")
                tail[1].append(data.get("reasoning_content") or "")
            else:
                self._segments.append([[data.get("content") or ""],
                                       [data.get("reasoning_content") or ""]])
        else:
            self._segments.append(event)

    def snapshot(self):
        """Materialize the history into replayable events (deltas coalesced)."""
        out = []
        for seg in self._segments:
            if isinstance(seg, list):
                content = "".join(seg[0])
                reasoning = "".join(seg[1])
                raw = json.dumps({"choices": [{"delta": {
                    "content": content, "reasoning_content": reasoning}}]})
                out.append(_ReplayEvent("delta", {
                    "content": content, "reasoning_content": reasoning, "raw": raw}))
            else:
                out.append(seg)
        return out


class EventBus:
    def __init__(self):
        self._subscribers = {}  # run_id -> list[queue.Queue]
        # run_id -> _ReplayBuffer: the in-flight history of an active run, kept
        # so a client that reattaches mid-run (navigated away and back) can
        # replay everything generated before it subscribed. Folded in publish,
        # dropped when the run ends (any terminal event). Deltas are coalesced so
        # memory scales with text length, not token count; the buffer lives only
        # while its run is in flight and is freed as soon as the run finishes.
        self._replay = {}
        self._lock = threading.Lock()

    def subscribe(self, run_id: str) -> "queue.Queue":
        """Register an observer for a run and return its (bounded) event queue."""
        q = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    def subscribe_with_replay(self, run_id: str):
        """Register an observer AND atomically capture the run's history so far.

        Returns (queue, history). The snapshot and the queue registration happen
        under one lock, so every in-flight event is delivered to the new observer
        exactly once: events already published are in `history`; events published
        after this call arrive on the queue. Used by the reattach endpoint so a
        returning client replays the full in-progress turn before going live.
        """
        q = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
            buf = self._replay.get(run_id)
            history = buf.snapshot() if buf is not None else []
        return q, history

    def unsubscribe(self, run_id: str, q: "queue.Queue") -> None:
        with self._lock:
            subs = self._subscribers.get(run_id)
            if not subs:
                return
            try:
                subs.remove(q)
            except ValueError:
                pass
            if not subs:
                del self._subscribers[run_id]

    def publish(self, run_id: str, event) -> None:
        """Fan an event out to every current subscriber of run_id.

        Never blocks the caller (the publisher is the run's worker thread —
        blocking it would stall the run). On a full queue the oldest event is
        evicted to make room, so a slow observer's memory stays bounded and the
        newest events (incl. the terminal stream_end) are preserved.

        Records the event in the run's replay history (so a later reattach can
        replay it) and, on any terminal event (run_completed / run_failed /
        run_cancelled / stream_end), drops that history. Both the history fold
        and the subscriber snapshot happen under the lock so a concurrent
        subscribe_with_replay sees a consistent cut.

        No-op for delivery when nobody is listening — the run keeps going
        regardless; the event is simply not replayed live (the DB holds the
        durable result), though it is still recorded for an in-flight reattach.
        """
        is_terminal = getattr(event, "type", None) in _TERMINAL_TYPES
        with self._lock:
            subs = list(self._subscribers.get(run_id, ()))
            if is_terminal:
                # Run finished: future reattachers fall back to the DB.
                self._replay.pop(run_id, None)
            else:
                buf = self._replay.get(run_id)
                if buf is None:
                    buf = _ReplayBuffer()
                    self._replay[run_id] = buf
                buf.add(event)
        for q in subs:
            while True:
                try:
                    q.put_nowait(event)
                    break
                except queue.Full:
                    # Make room and retry. If a concurrent drainer already
                    # freed space (get_nowait -> Empty), there is now room, so
                    # we must still retry the put — NOT break — otherwise this
                    # event (possibly the terminal stream_end) would be lost
                    # and the observer would never close.
                    try:
                        q.get_nowait()  # evict oldest
                    except queue.Empty:
                        pass
                    # loop retries put_nowait; the single publisher per run
                    # means a retry always succeeds without spinning.

    def subscriber_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(run_id, ()))
