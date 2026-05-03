import queue
import threading
from datetime import datetime, timezone


def iter_log_events(container, tail: int, stop_event: threading.Event):
    """
    Yield (event_type, data) tuples from a Docker container's log stream.

    Yields:
        ('log', line_str)       — one complete log line
        ('snapshot_end', None)  — after the initial tail is drained
        ('stream_end', None)    — Docker stream closed cleanly
        ('error', message_str)  — unrecoverable exception in reader thread
        ('keepalive', None)     — emitted when queue is idle for ~5 s

    The caller is responsible for setting stop_event to terminate the reader
    thread early (e.g. on client disconnect).
    """
    q = queue.Queue(maxsize=500)

    def _reader():
        try:
            # Capture T₀ before the phase-1 fetch so the follow window
            # overlaps slightly rather than leaving a gap.
            since = datetime.now(timezone.utc)

            raw = container.logs(tail=tail, timestamps=True, stream=False)
            for line in raw.decode("utf-8", errors="replace").splitlines():
                if stop_event.is_set():
                    return
                if line:
                    q.put(("log", line))
            q.put(("snapshot_end", None))

            if stop_event.is_set():
                return

            for chunk in container.logs(since=since, stream=True, follow=True, timestamps=True):
                if stop_event.is_set():
                    break
                for line in chunk.decode("utf-8", errors="replace").splitlines():
                    if line:
                        q.put(("log", line))

            q.put(("stream_end", None))
        except Exception as exc:
            q.put(("error", str(exc)))

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    while True:
        try:
            item = q.get(timeout=5.0)
            yield item
            if item[0] in ("stream_end", "error"):
                break
        except queue.Empty:
            yield ("keepalive", None)
