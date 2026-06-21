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


class EventBus:
    def __init__(self):
        self._subscribers = {}  # run_id -> list[queue.Queue]
        self._lock = threading.Lock()

    def subscribe(self, run_id: str) -> "queue.Queue":
        """Register an observer for a run and return its (bounded) event queue."""
        q = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

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

        No-op when nobody is listening — the run keeps going regardless; the
        event is simply not replayed (the DB holds the durable result).
        """
        with self._lock:
            subs = list(self._subscribers.get(run_id, ()))
        for q in subs:
            while True:
                try:
                    q.put_nowait(event)
                    break
                except queue.Full:
                    try:
                        q.get_nowait()  # evict oldest, then retry
                    except queue.Empty:
                        break

    def subscriber_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(run_id, ()))
