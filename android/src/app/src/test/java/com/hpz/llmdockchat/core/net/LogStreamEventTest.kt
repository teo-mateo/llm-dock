package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** [parseLogStreamFrame] — pure mapping of one SSE payload to a typed frame (F12-R1). */
class LogStreamEventTest {

    @Test
    fun `snapshot_start, log, snapshot_end and stream_end map to their own types`() {
        assertEquals(LogStreamEvent.SnapshotStart, parseLogStreamFrame("""{"type":"snapshot_start","service":"x"}"""))
        assertEquals(
            LogStreamEvent.Log("main: HTTP server is listening, hostname: 0.0.0.0, port: 8080"),
            parseLogStreamFrame("""{"type":"log","service":"x","line":"main: HTTP server is listening, hostname: 0.0.0.0, port: 8080"}"""),
        )
        assertEquals(LogStreamEvent.SnapshotEnd, parseLogStreamFrame("""{"type":"snapshot_end","service":"x"}"""))
        assertEquals(LogStreamEvent.StreamEnd, parseLogStreamFrame("""{"type":"stream_end","service":"x"}"""))
    }

    @Test
    fun `an error frame carries the server's message`() {
        val event = parseLogStreamFrame("""{"type":"error","service":"x","message":"container vanished"}""")
        assertEquals(LogStreamEvent.Error("container vanished"), event)
    }

    @Test
    fun `a log frame missing its line is unknown, not a crash`() {
        assertTrue(parseLogStreamFrame("""{"type":"log","service":"x"}""") is LogStreamEvent.Unknown)
    }

    @Test
    fun `an unrecognised type, and non-JSON, are both Unknown`() {
        assertTrue(parseLogStreamFrame("""{"type":"something_new"}""") is LogStreamEvent.Unknown)
        assertTrue(parseLogStreamFrame("not json at all") is LogStreamEvent.Unknown)
    }
}
