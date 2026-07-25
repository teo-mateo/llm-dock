package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F04 review probe — adversarial input against [parseFrame]'s totality claim
 * (Architecture D2). Left in place per WORK_INSTRUCTIONS §4; delete before
 * committing the feature.
 */
class RunEventParserAdversarialTest {

    private fun survives(payload: String): RunEvent =
        runCatching { parseFrame(payload) }
            .getOrElse { throw AssertionError("parseFrame threw on <<$payload>>: $it") }

    @Test
    fun `degenerate payloads never throw`() {
        val inputs = listOf(
            "",
            "   ",
            "\n\t ",
            "null",
            "true",
            "42",
            "-0.0e-9",
            "\"a bare string\"",
            "[1,2,3]",
            "[]",
            "{}",
            "{",
            "}{",
            "{\"unterminated\": ",
            "data: [DONE]",
            "[DONE] ",
            " [DONE]",
            "[done]",
            "\u0000\u0001\uFFFF",
            "\uD83D\uDE00 emoji only",
            "{\"a\":\"\\uD800\"}",
        )
        inputs.forEach { survives(it) }
    }

    @Test
    fun `deeply nested garbage does not blow the stack`() {
        val deep = "[".repeat(20_000) + "]".repeat(20_000)
        assertTrue(survives(deep) is RunEvent.Unknown)
        val deepObj = "{\"a\":".repeat(20_000) + "1" + "}".repeat(20_000)
        survives(deepObj)
    }

    @Test
    fun `a huge delta payload is parsed, not rejected`() {
        val text = "x".repeat(1_000_000)
        val event = survives("""{"choices":[{"delta":{"content":"$text"}}]}""")
        assertEquals(RunEvent.Delta(text, ""), event)
    }

    // -- the three-way dispatch ----------------------------------------------

    @Test
    fun `a type key wins over choices`() {
        val event = survives(
            """{"type":"heartbeat","elapsed_s":3.0,"choices":[{"delta":{"content":"hi"}}]}""",
        )
        assertEquals(RunEvent.Heartbeat(3.0), event)
    }

    // An unrecognised `type` alongside `choices` used to lose the text. It no
    // longer does; the inverted assertion lives in RunEventParserTest.

    @Test
    fun `a non-string type falls through to the choices branch`() {
        val event = survives("""{"type":7,"choices":[{"delta":{"content":"hi"}}]}""")
        assertEquals(RunEvent.Delta("hi", ""), event)
    }

    @Test
    fun `a non-string type with nothing else is Unknown`() {
        assertTrue(survives("""{"type":{"nested":true}}""") is RunEvent.Unknown)
        assertTrue(survives("""{"type":null}""") is RunEvent.Unknown)
    }

    @Test
    fun `error wins over choices`() {
        val event = survives("""{"error":"boom","choices":[{"delta":{"content":"hi"}}]}""")
        assertEquals(RunEvent.Failed("boom"), event)
    }

    @Test
    fun `a structured error object is not recognised as a failure`() {
        // The dashboard only ever sends a string (event_codec.encode_sse over
        // {"error": d["error"]}), but an upstream OpenAI-shaped error would be
        // swallowed as Unknown rather than surfacing.
        val event = survives("""{"error":{"message":"Invalid API Key","type":"auth"}}""")
        assertTrue("got $event", event is RunEvent.Unknown)
    }

    @Test
    fun `duplicate keys do not throw`() {
        survives("""{"type":"heartbeat","type":"run_started","run_id":"abc"}""")
    }

    // -- delta shapes ---------------------------------------------------------

    @Test
    fun `choices variants degrade to an empty delta rather than throwing`() {
        val empty = RunEvent.Delta("", "")
        assertEquals(empty, survives("""{"choices":[]}"""))
        assertEquals(empty, survives("""{"choices":[null]}"""))
        assertEquals(empty, survives("""{"choices":["a string"]}"""))
        assertEquals(empty, survives("""{"choices":[{}]}"""))
        assertEquals(empty, survives("""{"choices":[{"delta":null}]}"""))
        assertEquals(empty, survives("""{"choices":[{"delta":"text"}]}"""))
        assertEquals(empty, survives("""{"choices":[{"delta":{}}]}"""))
        assertEquals(empty, survives("""{"choices":[{"delta":{"content":null}}]}"""))
        assertEquals(empty, survives("""{"choices":[{"delta":{"content":123}}]}"""))
    }

    @Test
    fun `choices as a non-array is not a delta`() {
        assertTrue(survives("""{"choices":{"0":{"delta":{"content":"hi"}}}}""") is RunEvent.Unknown)
        assertTrue(survives("""{"choices":null}""") is RunEvent.Unknown)
    }

    @Test
    fun `only the first choice is read`() {
        val event = survives(
            """{"choices":[{"delta":{"content":"a"}},{"delta":{"content":"b"}}]}""",
        )
        assertEquals(RunEvent.Delta("a", ""), event)
    }

    @Test
    fun `reasoning_content wins over reasoning when both are present`() {
        val event = survives(
            """{"choices":[{"delta":{"reasoning_content":"rc","reasoning":"r"}}]}""",
        )
        assertEquals(RunEvent.Delta("", "rc"), event)
    }

    // -- typed frames with wrong-typed fields ---------------------------------

    @Test
    fun `typed frames tolerate wrong-typed optional fields`() {
        assertEquals(RunEvent.Heartbeat(0.0), survives("""{"type":"heartbeat","elapsed_s":"abc"}"""))
        assertEquals(RunEvent.Heartbeat(0.0), survives("""{"type":"heartbeat"}"""))
        assertEquals(
            RunEvent.ToolCallPending(0, "x"),
            survives("""{"type":"tool_call_pending","index":"nope","name":"x"}"""),
        )
        assertEquals(
            RunEvent.MessageSaved("m1", 0),
            survives("""{"type":"message_saved","message_id":"m1","seq":null}"""),
        )
        assertEquals(
            RunEvent.ConversationUpdated("c1", ""),
            survives("""{"type":"conversation_updated","id":"c1"}"""),
        )
        assertEquals(
            RunEvent.RunStatus("failed", null),
            survives("""{"type":"run_status","status":"failed","error":null}"""),
        )
    }

    @Test
    fun `typed frames missing their identifying field are Unknown`() {
        listOf(
            """{"type":"run_started"}""",
            """{"type":"tool_call_pending","index":1}""",
            """{"type":"tool_call","arguments":{}}""",
            """{"type":"tool_result","result":"x"}""",
            """{"type":"artifact","content":"x"}""",
            """{"type":"message_saved","seq":2}""",
            """{"type":"conversation_updated","title":"t"}""",
            """{"type":"run_status"}""",
        ).forEach { assertTrue("$it -> ${survives(it)}", survives(it) is RunEvent.Unknown) }
    }

    @Test
    fun `Unknown keeps the raw payload so nothing is silently discarded`() {
        val raw = """{"type":"brand_new_frame","payload":{"a":1}}"""
        assertEquals(RunEvent.Unknown(raw), survives(raw))
    }

    @Test
    fun `lenient parsing accepts unquoted keys the server never sends`() {
        // Not a defect — recorded so the behaviour is known rather than assumed.
        survives("""{type: run_started, run_id: abc}""")
    }
}
