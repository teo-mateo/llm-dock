package com.hpz.llmdockchat.feature.pi.transcript

import com.hpz.llmdockchat.data.model.PiEvent
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiTranscriptTest {

    private fun event(seq: Long, type: String, payload: JsonObject) =
        PiEvent(seq, type, seq * 1000, payload)

    private fun obj(block: JsonObjectBuilder.() -> Unit): JsonObject = buildJsonObject(block)

    private fun JsonObjectBuilder.put(key: String, value: String) = put(key, JsonPrimitive(value))
    private fun JsonObjectBuilder.put(key: String, value: Int) = put(key, JsonPrimitive(value))
    private fun JsonObjectBuilder.put(key: String, value: Long) = put(key, JsonPrimitive(value))
    private fun JsonObjectBuilder.put(key: String, value: Boolean) = put(key, JsonPrimitive(value))

    @Test
    fun `deltas stream into one open assistant item`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "assistant_delta", obj { put("text", "Hel"); put("thinking", "th") }),
                event(2, "assistant_delta", obj { put("text", "lo"); put("thinking", "ink") }),
            ),
        )
        assertEquals(1, transcript.items.size)
        val item = transcript.items.single() as PiItem.Assistant
        assertEquals("a1", item.id)
        assertEquals("Hello", item.text)
        assertEquals("think", item.thinking)
        assertTrue(item.streaming)
    }

    @Test
    fun `assistant_message replaces streamed text with the final text`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "assistant_delta", obj { put("text", "partial"); put("thinking", "part") }),
                event(
                    2,
                    "assistant_message",
                    obj {
                        put("text", "final")
                        put("thinking", "full think")
                        put("model", obj { put("provider", "mistral"); put("id", "small") })
                        put("usage", obj { put("input", 1); put("output", 2); put("total_tokens", 3) })
                        put("stop_reason", "stop")
                    },
                ),
            ),
        )
        val item = transcript.items.single() as PiItem.Assistant
        assertEquals("a1", item.id)
        assertEquals("final", item.text)
        assertEquals("full think", item.thinking)
        assertFalse(item.streaming)
        assertEquals("mistral/small", item.model)
        assertEquals(2L, item.outputTokens)
        assertEquals("stop", item.stopReason)
    }

    @Test
    fun `assistant_message without deltas creates a closed item`() {
        val transcript = buildPiTranscript(
            listOf(
                event(
                    4,
                    "assistant_message",
                    obj {
                        put("text", "final")
                        put("thinking", "")
                        put("model", JsonNull)
                        put("usage", JsonNull)
                        put("stop_reason", "stop")
                    },
                ),
            ),
        )
        val item = transcript.items.single() as PiItem.Assistant
        assertEquals("a4", item.id)
        assertEquals("final", item.text)
        assertFalse(item.streaming)
        assertNull(item.model)
        assertNull(item.outputTokens)
    }

    @Test
    fun `user message closes an open assistant item`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "assistant_delta", obj { put("text", "partial"); put("thinking", "") }),
                event(
                    2,
                    "user_message",
                    obj {
                        put("text", "hello")
                        put("image_count", 1)
                        put("origin", "terminal")
                    },
                ),
            ),
        )
        assertEquals(listOf("assistant", "user"), transcript.items.map { kindOf(it) })
        assertFalse((transcript.items[0] as PiItem.Assistant).streaming)
        val user = transcript.items[1] as PiItem.User
        assertEquals("u2", user.id)
        assertEquals("hello", user.text)
        assertEquals(1, user.imageCount)
        assertFalse(user.fromPhone)
    }

    @Test
    fun `tool lifecycle start update end`() {
        val transcript = buildPiTranscript(
            listOf(
                event(
                    1,
                    "tool_start",
                    obj { put("call_id", "c1"); put("name", "search"); put("args", """{"q":"x"}"""); put("truncated", false) },
                ),
                event(
                    2,
                    "tool_update",
                    obj { put("call_id", "c1"); put("name", "search"); put("partial", """{"hits":"""); put("truncated", true) },
                ),
                event(
                    3,
                    "tool_end",
                    obj {
                        put("call_id", "c1")
                        put("name", "search")
                        put("result", """{"hits":1}""")
                        put("is_error", false)
                        put("duration_ms", 12)
                        put("truncated", false)
                    },
                ),
            ),
        )
        val tool = transcript.items.single() as PiItem.Tool
        assertEquals("tc1", tool.id)
        assertEquals("c1", tool.callId)
        assertEquals("search", tool.name)
        assertEquals("""{"q":"x"}""", tool.args)
        assertEquals("""{"hits":1}""", tool.output)
        assertEquals(ToolStatus.DONE, tool.status)
        assertEquals(12L, tool.durationMs)
        assertTrue(tool.truncated)
    }

    @Test
    fun `tool error status`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "tool_start", obj { put("call_id", "c1"); put("name", "search"); put("args", JsonNull); put("truncated", false) }),
                event(
                    2,
                    "tool_end",
                    obj {
                        put("call_id", "c1")
                        put("name", "search")
                        put("result", "boom")
                        put("is_error", true)
                        put("duration_ms", 5)
                        put("truncated", false)
                    },
                ),
            ),
        )
        val tool = transcript.items.single() as PiItem.Tool
        assertEquals(ToolStatus.ERROR, tool.status)
        assertEquals("boom", tool.output)
    }

    @Test
    fun `tool update for unknown call creates the card`() {
        val transcript = buildPiTranscript(
            listOf(
                event(
                    1,
                    "tool_update",
                    obj { put("call_id", "c2"); put("name", "read"); put("partial", "abc"); put("truncated", true) },
                ),
            ),
        )
        val tool = transcript.items.single() as PiItem.Tool
        assertEquals("tc2", tool.id)
        assertEquals("c2", tool.callId)
        assertEquals("read", tool.name)
        assertNull(tool.args)
        assertEquals("abc", tool.output)
        assertEquals(ToolStatus.RUNNING, tool.status)
        assertTrue(tool.truncated)
    }

    @Test
    fun `truncated is sticky`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "tool_start", obj { put("call_id", "c1"); put("name", "x"); put("args", JsonNull); put("truncated", false) }),
                event(2, "tool_update", obj { put("call_id", "c1"); put("name", "x"); put("partial", JsonNull); put("truncated", true) }),
                event(
                    3,
                    "tool_end",
                    obj {
                        put("call_id", "c1")
                        put("name", "x")
                        put("result", JsonNull)
                        put("is_error", false)
                        put("duration_ms", JsonNull)
                        put("truncated", false)
                    },
                ),
            ),
        )
        assertTrue((transcript.items.single() as PiItem.Tool).truncated)
    }

    @Test
    fun `model and thinking notices`() {
        val transcript = buildPiTranscript(
            listOf(
                event(
                    1,
                    "model_changed",
                    obj {
                        put("previous", obj { put("provider", "a"); put("id", "1") })
                        put("model", obj { put("provider", "b"); put("id", "2") })
                    },
                ),
                event(2, "thinking_changed", obj { put("previous", "low"); put("level", "high") }),
            ),
        )
        assertEquals(
            listOf("Model: a/1 → b/2", "Thinking: low → high"),
            transcript.items.map { (it as PiItem.Notice).text },
        )
    }

    @Test
    fun `compaction notice with and without tokens`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "compaction", obj { put("summary", "x"); put("tokens_before", 123); put("reason", "auto") }),
                event(2, "compaction", obj { put("summary", "y"); put("tokens_before", JsonNull); put("reason", "auto") }),
            ),
        )
        assertEquals(
            listOf("Context compacted (123 tokens)", "Context compacted"),
            transcript.items.map { (it as PiItem.Notice).text },
        )
    }

    @Test
    fun `gap notice counts missing events`() {
        val transcript = buildPiTranscript(
            listOf(event(1, "gap", obj { put("from_seq", 5); put("to_seq", 7) })),
        )
        assertEquals("3 events missing (5–7)", (transcript.items.single() as PiItem.Notice).text)
    }

    @Test
    fun `state turn_end and unknown types add no items`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "state", obj { put("state", "idle") }),
                event(2, "turn_end", obj { put("outcome", "completed") }),
                event(3, "future_type", obj { put("anything", true) }),
            ),
        )
        assertEquals(emptyList<PiItem>(), transcript.items)
    }

    @Test
    fun `working follows the last state event`() {
        assertFalse(
            buildPiTranscript(
                listOf(
                    event(1, "state", obj { put("state", "working") }),
                    event(2, "state", obj { put("state", "idle") }),
                ),
            ).working,
        )
        assertTrue(
            buildPiTranscript(
                listOf(
                    event(1, "state", obj { put("state", "idle") }),
                    event(2, "state", obj { put("state", "working") }),
                ),
            ).working,
        )
    }

    @Test
    fun `ids are stable across rebuilds`() {
        val events = listOf(
            event(1, "user_message", obj { put("text", "hi"); put("image_count", 0); put("origin", "terminal") }),
            event(2, "assistant_delta", obj { put("text", "a"); put("thinking", "") }),
            event(
                3,
                "assistant_message",
                obj {
                    put("text", "a")
                    put("thinking", "")
                    put("model", JsonNull)
                    put("usage", JsonNull)
                    put("stop_reason", "stop")
                },
            ),
            event(4, "tool_start", obj { put("call_id", "c1"); put("name", "x"); put("args", JsonNull); put("truncated", false) }),
            event(5, "gap", obj { put("from_seq", 6); put("to_seq", 6) }),
        )
        assertEquals(buildPiTranscript(events), buildPiTranscript(events))
    }

    @Test
    fun `malformed payload fields do not throw`() {
        val transcript = buildPiTranscript(
            listOf(
                event(1, "assistant_delta", obj { put("text", 5); put("thinking", true) }),
                event(
                    2,
                    "assistant_message",
                    obj {
                        put("text", obj {})
                        put("thinking", false)
                        put("model", "not an object")
                        put("usage", 42)
                        put("stop_reason", false)
                    },
                ),
                event(3, "user_message", obj { put("text", JsonNull); put("image_count", "x"); put("origin", 1) }),
                event(4, "tool_start", obj { put("call_id", 1); put("name", true); put("args", 2); put("truncated", "yes") }),
                event(5, "tool_update", obj { put("call_id", 1); put("partial", true); put("truncated", "true") }),
                event(6, "model_changed", obj { put("previous", 1); put("model", "x") }),
                event(7, "gap", obj { put("from_seq", "a"); put("to_seq", JsonNull) }),
            ),
        )

        val assistant = transcript.items.first { it is PiItem.Assistant } as PiItem.Assistant
        assertEquals("", assistant.text)
        assertEquals("", assistant.thinking)
        assertNull(assistant.model)
        assertNull(assistant.outputTokens)
        assertNull(assistant.stopReason)

        val user = transcript.items.first { it is PiItem.User } as PiItem.User
        assertEquals("", user.text)
        assertEquals(0, user.imageCount)
        assertFalse(user.fromPhone)

        val tool = transcript.items.first { it is PiItem.Tool } as PiItem.Tool
        assertEquals("", tool.callId)
        assertEquals("", tool.name)
        assertNull(tool.args)
        assertNull(tool.output)
        assertEquals(ToolStatus.RUNNING, tool.status)
        assertFalse(tool.truncated)

        val notices = transcript.items.filterIsInstance<PiItem.Notice>()
        assertEquals("Model: — → —", notices[0].text)
        assertEquals("1 events missing (0–0)", notices[1].text)
    }

    private fun kindOf(item: PiItem): String = when (item) {
        is PiItem.User -> "user"
        is PiItem.Assistant -> "assistant"
        is PiItem.Tool -> "tool"
        is PiItem.Notice -> "notice"
        is PiItem.RunEnd -> "run_end"
    }
}
