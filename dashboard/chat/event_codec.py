"""SSE encoding for chat runtime events.

Extracted from chat.routes (Phase 1 of #58) so the wire format lives in one
place and can be shared by persisted chat, spinoff, run reattachment, and
future ghost streams. The frontend SSE parser should not need to know which
producer emitted a frame.

This phase only centralizes the framing — it does NOT change any byte that
goes out. In particular, model deltas are still forwarded as the raw upstream
chunk (see encode_sse_delta); normalizing them into a typed frame is deferred
to its own paired frontend+backend PR.
"""
import json

# Terminal sentinel that closes a stream. Kept as a constant because it is
# emitted verbatim and parsed verbatim on the client.
DONE = "data: [DONE]\n\n"


def encode_sse(payload: dict) -> str:
    """Frame an already-shaped payload dict as an SSE `data:` line.

    Used for frames that don't carry a `type` key — currently just the legacy
    error frame `{"error": "..."}`. `default=str` is a safety net for
    non-JSON-serializable values (e.g. artifact content objects); it never
    fires for plain dicts, so output is identical to a bare json.dumps.
    """
    return f"data: {json.dumps(payload, default=str)}\n\n"


def encode_sse_event(event_type: str, data: dict = None) -> str:
    """Frame a typed runtime event as `{"type": event_type, **data}`.

    Insertion order is `type` first, matching the hand-written frames this
    replaced, so the serialized bytes are unchanged.
    """
    payload = {"type": event_type}
    if data:
        payload.update(data)
    return encode_sse(payload)


def encode_sse_delta(raw: str) -> str:
    """Forward an upstream model delta chunk verbatim.

    Deltas are deliberately NOT re-encoded into a typed `{"type": "delta"}`
    frame: the raw OpenAI-compatible chunk is passed straight through, exactly
    as the old code did. This is the one documented exception to typed framing.
    Normalizing it is a coordinated frontend+backend change deferred to its own
    PR (#58); keeping the exception in one function makes that change a
    one-line edit here plus its frontend counterpart.
    """
    return f"data: {raw}\n\n"
