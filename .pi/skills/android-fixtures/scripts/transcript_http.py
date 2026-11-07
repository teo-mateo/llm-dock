import time
from urllib.parse import parse_qs

from transcript import INSTANCE_ID, PAGE_SIZE, SESSION_ID

SESSION_PATH = f"/api/pi/sessions/{SESSION_ID}/{INSTANCE_ID}"
CONTROL_PATH = "/__fixture/transcript"


def get(handler, path, query):
    state = handler.server.state
    if path == CONTROL_PATH:
        with state.condition:
            body = state.transcript.stats()
        handler.respond(200, body)
    elif path == SESSION_PATH + "/stream":
        try:
            after = int(parse_qs(query).get("after", ["0"])[0])
            if after < 0:
                raise ValueError("negative cursor")
        except ValueError:
            handler.respond(400, {"error": "invalid_after"})
            return True
        stream(handler, after)
    else:
        return False
    return True


def post(handler, path, body):
    if path != CONTROL_PATH:
        return False
    state = handler.server.state
    with state.condition:
        state.transcript.control(body["action"], body.get("gate"))
        state.changed()
        result = state.transcript.stats()
    handler.respond(200, result)
    return True


def delete(handler, path):
    if path != SESSION_PATH:
        return False
    state = handler.server.state
    with state.condition:
        transcript = state.transcript
        if transcript.deleted:
            status, body = 404, {"error": "unknown_session"}
        elif transcript.live:
            status, body = 409, {"error": "pi_session_live"}
        else:
            transcript.deleted = True
            state.changed()
            status, body = 200, {"deleted": True}
    handler.respond(status, body)
    return True


def stream(handler, after):
    state = handler.server.state
    with state.condition:
        transcript = state.transcript
        status = 404 if transcript.deleted else 503 if transcript.offline else 200
        request = transcript.request(after, status)
        generation = transcript.generation
    if status != 200:
        handler.respond(status, {"error": "unknown_session" if status == 404 else "fixture_offline"})
        return
    handler.start_stream()
    handler.close_connection = True
    cursor, summary_version = after, None
    try:
        while True:
            with state.condition:
                if transcript.generation != generation or transcript.offline:
                    return
                fresh = []
                if transcript.deleted:
                    event, payload = "session_removed", {"session_id": SESSION_ID, "instance_id": INSTANCE_ID}
                elif transcript.gate == "replay":
                    state.condition.wait(timeout=1)
                    continue
                else:
                    fresh = [event for event in transcript.events if event["seq"] > cursor][:PAGE_SIZE]
                    if fresh:
                        event, payload = "events", {"events": fresh}
                    elif transcript.gate == "summary":
                        state.condition.wait(timeout=1)
                        continue
                    elif summary_version != state.version:
                        event, payload = "session", transcript.rows()[0]
                        summary_version = state.version
                    else:
                        state.condition.wait(timeout=1)
                        event, payload = None, None
            if event is None:
                handler.heartbeat()
                continue
            body_bytes = handler.send_frame(event, payload)
            with state.condition:
                request["sse_body_bytes"] += body_bytes
                if fresh:
                    cursor = fresh[-1]["seq"]
                    request["batches"].append({"first": fresh[0]["seq"], "last": cursor, "count": len(fresh)})
                    request["sent_events"] += len(fresh)
                    request.setdefault("first_event_monotonic", time.monotonic())
                    request["last_event_monotonic"] = time.monotonic()
                if event == "session":
                    request["summary_sent"] = True
                    request.setdefault("summary_monotonic", time.monotonic())
                state.condition.notify_all()
            if event == "session_removed":
                return
    except (BrokenPipeError, ConnectionResetError, OSError):
        return
