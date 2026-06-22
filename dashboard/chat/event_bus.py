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
import queue
import threading

# Per-observer queue cap. Generous enough to absorb a normal burst of token
# deltas, but bounded so a live-but-non-draining client (TCP backpressure, a
# stalled proxy) can't make the publishing worker accumulate memory without
# limit. On overflow the OLDEST event is evicted, which keeps the newest
# events — crucially including the terminal stream_end — so the observer still
# terminates. Dropped middle deltas don't lose data: the DB has the full reply.
SUBSCRIBER_QUEUE_MAX = 2048

# Event type that marks a run fully finished. Matches run_manager.STREAM_END;
# kept as a literal so the bus stays free of a run_manager import. On this event
# the run's replay history is dropped (the run is over — reattachers fall back
# to the DB).
_STREAM_END_TYPE = "stream_end"


class EventBus:
    def __init__(self):
        self._subscribers = {}  # run_id -> list[queue.Queue]
        # run_id -> list[event]: the in-flight history of an active run, kept so
        # a client that reattaches mid-run (navigated away and back) can replay
        # everything generated before it subscribed. Appended in publish, dropped
        # when the run ends (STREAM_END). Unlike the per-observer queues this is
        # NOT bounded/evicted — losing the oldest deltas would blank the start of
        # the reply on reattach — so it lives only for one active run at a time
        # and is freed as soon as that run finishes.
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
            history = list(self._replay.get(run_id, ()))
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
        replay it) and, on the terminal stream_end, drops that history. Both the
        history append and the subscriber snapshot happen under the lock so a
        concurrent subscribe_with_replay sees a consistent cut.

        No-op for delivery when nobody is listening — the run keeps going
        regardless; the event is simply not replayed live (the DB holds the
        durable result), though it is still recorded for an in-flight reattach.
        """
        is_end = getattr(event, "type", None) == _STREAM_END_TYPE
        with self._lock:
            subs = list(self._subscribers.get(run_id, ()))
            if is_end:
                # Run finished: future reattachers fall back to the DB.
                self._replay.pop(run_id, None)
            else:
                self._replay.setdefault(run_id, []).append(event)
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
