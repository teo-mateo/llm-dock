package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.testing.readFixture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Every row of F04's frame table, against SSE recorded from the dashboard
 * (Architecture Part IV — a hand-written fixture only encodes what you think
 * the server sends).
 *
 * The recordings under `fixtures/sse` were captured with `curl -N` against
 * `llamacpp-gemma-4-26b-a4b-it-q8` on :3301; `backend-frames.sse` was produced
 * by running the dashboard's own `chat/run_manager.py:_sse_frames_for` over the
 * events that are impractical to provoke on demand (a heartbeat needs a >3 s
 * silence, a parse warning needs a model that emits a malformed tool call).
 */
class RunEventParserTest {

    // -- the table, frame by frame -------------------------------------------

    @Test
    fun `run started carries the run id Stop needs`() {
        val event = parseFrame("""{"type": "run_started", "run_id": "035d944d-5105"}""")
        assertEquals(RunEvent.RunStarted("035d944d-5105"), event)
    }

    @Test
    fun `a content delta is a raw OpenAI chunk with no type key`() {
        val event = parseFrame(
            """{"choices":[{"finish_reason":null,"index":0,"delta":{"content":"hello"}}],"model":"m"}""",
        )
        assertEquals(RunEvent.Delta(content = "hello", reasoning = ""), event)
    }

    @Test
    fun `reasoning_content is read as reasoning, never as content`() {
        val event = parseFrame("""{"choices":[{"index":0,"delta":{"reasoning_content":"The user"}}]}""")
        assertEquals(RunEvent.Delta(content = "", reasoning = "The user"), event)
    }

    /** Architecture D6: some models send `reasoning` instead of `reasoning_content`. */
    @Test
    fun `a model that sends reasoning instead of reasoning_content is read the same way`() {
        val event = parseFrame("""{"choices":[{"delta":{"reasoning":"thinking"}}]}""")
        assertEquals(RunEvent.Delta(content = "", reasoning = "thinking"), event)
    }

    @Test
    fun `a chunk with an empty choices array is an empty delta, not an unknown frame`() {
        assertEquals(RunEvent.Delta("", ""), parseFrame("""{"choices":[],"usage":{"total_tokens":9}}"""))
    }

    @Test
    fun `tool call pending carries the namespaced name before the arguments exist`() {
        val event = parseFrame("""{"type": "tool_call_pending", "index": 0, "name": "sympy-math__differentiate"}""")
        assertEquals(RunEvent.ToolCallPending(0, "sympy-math__differentiate"), event)
    }

    @Test
    fun `tool call renders its object arguments as displayable JSON`() {
        val event = parseFrame(
            """{"type": "tool_call", "name": "differentiate", "arguments": {"expression": "x**3"}, "server_id": "sympy-math"}""",
        )
        event as RunEvent.ToolCall
        assertEquals("differentiate", event.name)
        assertEquals("sympy-math", event.serverId)
        assertTrue(event.arguments.contains("x**3"))
    }

    @Test
    fun `tool result unwraps a string result rather than leaving it quoted`() {
        val event = parseFrame(
            """{"type": "tool_result", "name": "differentiate", "result": "x**3*cos(x)", "server_id": "sympy-math"}""",
        )
        assertEquals(RunEvent.ToolResult("differentiate", "x**3*cos(x)", "sympy-math"), event)
    }

    @Test
    fun `artifact carries its type, title and body`() {
        val event = parseFrame(
            """{"type": "artifact", "artifact_type": "svg", "title": "RC divider", "content": "<svg/>"}""",
        )
        assertEquals(RunEvent.Artifact("svg", "RC divider", "<svg/>"), event)
    }

    @Test
    fun `parse warning keeps the server's own description`() {
        val event = parseFrame(
            """{"type": "parse_warning", "kind": "silent_drop", "snippet": "", "description": "Model emitted reasoning but no content"}""",
        )
        assertEquals(
            RunEvent.ParseWarning("silent_drop", "Model emitted reasoning but no content", ""),
            event,
        )
    }

    @Test
    fun `heartbeat is liveness, not content`() {
        assertEquals(RunEvent.Heartbeat(6.0), parseFrame("""{"type": "heartbeat", "elapsed_s": 6.0}"""))
    }

    @Test
    fun `the DONE sentinel is its own event`() {
        assertEquals(RunEvent.Done, parseFrame("[DONE]"))
    }

    /** `message_id` is a UUID string, not the integer the shape suggests. */
    @Test
    fun `message saved carries a string message id`() {
        val event = parseFrame("""{"type": "message_saved", "message_id": "9b755560-aab9", "seq": 2}""")
        assertEquals(RunEvent.MessageSaved("9b755560-aab9", 2), event)
    }

    @Test
    fun `conversation updated carries the auto-generated title`() {
        val event = parseFrame("""{"type": "conversation_updated", "id": "c1", "title": "Transistor history"}""")
        assertEquals(RunEvent.ConversationUpdated("c1", "Transistor history"), event)
    }

    @Test
    fun `an error frame has no type key either`() {
        val event = parseFrame("""{"error": "Service 'x' is not reachable. Is it running?"}""")
        assertEquals(RunEvent.Failed("Service 'x' is not reachable. Is it running?"), event)
    }

    @Test
    fun `run status carries the durable status and, when failed, the error`() {
        assertEquals(
            RunEvent.RunStatus("completed", null),
            parseFrame("""{"type": "run_status", "status": "completed", "error": null}"""),
        )
        assertEquals(
            RunEvent.RunStatus("failed", "boom"),
            parseFrame("""{"type": "run_status", "status": "failed", "error": "boom"}"""),
        )
    }

    // -- the cases that must not crash the stream (Architecture D2) -----------

    @Test
    fun `an unrecognised typed frame becomes Unknown rather than throwing`() {
        val raw = """{"type": "token_usage", "prompt_tokens": 40}"""
        assertEquals(RunEvent.Unknown(raw), parseFrame(raw))
    }

    @Test
    fun `a malformed payload becomes Unknown`() {
        val truncated = "{\"type\": \"trun"
        assertEquals(RunEvent.Unknown(truncated), parseFrame(truncated))
        assertEquals(RunEvent.Unknown("not json at all"), parseFrame("not json at all"))
        assertEquals(RunEvent.Unknown(""), parseFrame(""))
    }

    @Test
    fun `a JSON array payload becomes Unknown rather than being mistaken for a frame`() {
        assertEquals(RunEvent.Unknown("[1,2,3]"), parseFrame("[1,2,3]"))
    }

    @Test
    fun `a typed frame missing its required field is Unknown, not a half-built event`() {
        val raw = """{"type": "run_started"}"""
        assertEquals(RunEvent.Unknown(raw), parseFrame(raw))
    }

    /**
     * A delta is upstream model output, and upstream is free to add keys. A
     * `type` this build does not know must not shadow the text beside it —
     * dispatch falls through to `choices` instead of giving up on the frame.
     */
    @Test
    fun `an unrecognised type alongside choices still yields the delta`() {
        val raw = """{"type": "token_usage", "choices": [{"delta": {"content": "hi"}}]}"""
        assertEquals(RunEvent.Delta("hi", ""), parseFrame(raw))
    }

    /** A type this build *does* know still wins — `run_status` is not a delta. */
    @Test
    fun `a recognised type wins over choices`() {
        val raw = """{"type": "heartbeat", "elapsed_s": 3.0, "choices": [{"delta": {"content": "hi"}}]}"""
        assertEquals(RunEvent.Heartbeat(3.0), parseFrame(raw))
    }

    // -- the recordings ------------------------------------------------------

    @Test
    fun `the recorded simple send parses to run_started, deltas, DONE, message_saved, run_status`() {
        val events = parseFixture("send-simple.sse")

        assertEquals(RunEvent.RunStarted("035d944d-5105-451c-96d6-0d84d831a128"), events.first())
        assertEquals(RunEvent.Done, events[events.size - 3])
        assertEquals(RunEvent.MessageSaved("9b755560-aab9-42b9-9eba-289e5aaa1727", 2), events[events.size - 2])
        assertEquals(RunEvent.RunStatus("completed", null), events.last())
        assertTrue(events.none { it is RunEvent.Unknown })

        val deltas = events.filterIsInstance<RunEvent.Delta>()
        assertEquals("hello there", deltas.joinToString("") { it.content })
        assertTrue(deltas.any { it.reasoning.isNotEmpty() })
    }

    /**
     * `[DONE]` is not the end of the stream — the load-bearing fact behind
     * F04-R7. Two frames follow it in this recording.
     */
    @Test
    fun `frames follow the DONE sentinel in a real recording`() {
        val events = parseFixture("send-simple.sse")
        val after = events.drop(events.indexOf(RunEvent.Done) + 1)
        assertEquals(2, after.size)
    }

    @Test
    fun `the recorded tool call yields pending, call and result in order`() {
        val events = parseFixture("send-toolcall.sse")

        assertEquals(
            RunEvent.ToolCallPending(0, "sympy-math__differentiate"),
            events.filterIsInstance<RunEvent.ToolCallPending>().single(),
        )
        val call = events.filterIsInstance<RunEvent.ToolCall>().single()
        assertEquals("differentiate", call.name)
        assertEquals("sympy-math", call.serverId)
        assertTrue(call.arguments.contains("x**3"))
        assertEquals(
            RunEvent.ToolResult("differentiate", "x**3*cos(x) + 3*x**2*sin(x)", "sympy-math"),
            events.filterIsInstance<RunEvent.ToolResult>().single(),
        )
        assertTrue(events.none { it is RunEvent.Unknown })
    }

    @Test
    fun `the recorded failure is run_started then a bare error frame`() {
        val events = parseFixture("send-failure.sse")
        assertEquals(2, events.size)
        assertTrue(events.first() is RunEvent.RunStarted)
        assertEquals(
            RunEvent.Failed("Service 'llamacpp-f04-test-missing' is not reachable. Is it running?"),
            events.last(),
        )
    }

    /** A cancelled run emits no terminal frame — the recording just stops. */
    @Test
    fun `the recorded cancel ends on a delta with no terminal frame`() {
        val events = parseFixture("send-cancel.sse")
        assertTrue(events.last() is RunEvent.Delta)
        assertTrue(events.none { it is RunEvent.Done })
        assertTrue(events.none { it is RunEvent.MessageSaved })
        assertTrue(events.none { it is RunEvent.RunStatus })
        assertTrue(events.none { it is RunEvent.Failed })
    }

    /**
     * The replay buffer folds a whole run of deltas into one frame carrying
     * both halves at once, so the client must not assume one delta is one
     * token (Architecture P1's note, F09-R2).
     */
    @Test
    fun `the recorded reattach replays a coalesced delta before the live tail`() {
        val events = parseFixture("reattach-replay.sse")

        assertTrue(events.first() is RunEvent.RunStarted)
        val coalesced = events.filterIsInstance<RunEvent.Delta>().first()
        assertTrue("replay chunk should be far larger than a token", coalesced.reasoning.length > 200)
        assertTrue(events.any { it is RunEvent.MessageSaved })
        assertTrue(events.none { it is RunEvent.Unknown })
    }

    @Test
    fun `reattaching to a finished run yields a single run_status frame`() {
        assertEquals(listOf(RunEvent.RunStatus("completed", null)), parseFixture("reattach-terminal.sse"))
    }

    @Test
    fun `the backend-generated frames cover heartbeat, parse_warning, artifact and the title`() {
        val events = parseFixture("backend-frames.sse")

        assertTrue(events.any { it is RunEvent.Heartbeat })
        assertTrue(events.any { it is RunEvent.ParseWarning })
        assertTrue(events.any { it is RunEvent.Artifact })
        assertEquals(
            RunEvent.ConversationUpdated("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "Transistor history"),
            events.last(),
        )
        assertTrue(events.none { it is RunEvent.Unknown })
    }

    private fun parseFixture(name: String): List<RunEvent> =
        readFixture("sse/$name")
            .split("\n\n")
            .filter { it.isNotBlank() }
            .map { parseFrame(it.removePrefix("data: ")) }
}
