package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SseFrameParserTest {

    private val parser = SseFrameParser()

    private fun feed(vararg lines: String): List<String> =
        lines.mapNotNull(parser::onLine)

    @Test
    fun `a data line is dispatched by the blank line that follows it`() {
        assertNull(parser.onLine("""data: {"type": "heartbeat"}"""))
        assertEquals("""{"type": "heartbeat"}""", parser.onLine(""))
    }

    @Test
    fun `a colon comment keepalive produces nothing`() {
        assertEquals(emptyList<String>(), feed(": keepalive", "", ": keepalive", ""))
    }

    @Test
    fun `exactly one leading space after the colon is stripped`() {
        assertEquals(listOf("x", "x", " x"), feed("data: x", "", "data:x", "", "data:  x", ""))
    }

    @Test
    fun `consecutive data lines join with a newline`() {
        assertEquals(listOf("one\ntwo"), feed("data: one", "data: two", ""))
    }

    @Test
    fun `other fields are ignored`() {
        assertEquals(listOf("payload"), feed("event: delta", "id: 7", "retry: 100", "data: payload", ""))
    }

    @Test
    fun `CRLF line endings are tolerated`() {
        assertEquals(listOf("payload"), feed("data: payload\r", "\r"))
    }

    @Test
    fun `a payload is never interpreted`() {
        assertEquals(listOf("[DONE]"), feed("data: [DONE]", ""))
    }

    @Test
    fun `an unterminated event is not dispatched`() {
        assertEquals(emptyList<String>(), feed("data: half a frame"))
    }
}
