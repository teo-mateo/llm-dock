package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.data.dto.ServiceDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [parseServiceStreamFrame] against the shapes `services_stream` actually
 * sends (`dashboard/routes/services.py:services_stream`) — a snapshot on
 * connect, then deltas, mirrored from the real payload shapes documented
 * there rather than guessed.
 */
class ServiceStreamEventParserTest {

    @Test
    fun `a snapshot carries every service row, api_key and all, but api_key never survives decoding`() {
        val event = parseServiceStreamFrame(
            """
            {"type": "snapshot", "data": {"services": [
                {"name": "llamacpp-gemma-4-26b-a4b-it-q8", "status": "running", "kind": "chat",
                 "host_port": 3301, "favorite": true, "api_key": "llmd-super-secret-value"},
                {"name": "vllm-bge-m3", "status": "not-created", "kind": "embedding",
                 "host_port": 3370, "favorite": false, "api_key": "llmd-another-secret"}
            ], "total": 2, "running": 1, "stopped": 1}, "timestamp": "2026-07-25T00:00:00Z"}
            """.trimIndent(),
        )
        val snapshot = event as ServiceStreamEvent.Snapshot
        assertEquals(2, snapshot.services.size)
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", snapshot.services[0].name)
        assertEquals(3301, snapshot.services[0].hostPort)
        assertTrue(snapshot.services[0].favorite)
        assertEquals("embedding", snapshot.services[1].kind)
        // ServiceDto has no api_key property at all — there is nowhere for the
        // value to have landed, which is exactly F07-R6's point.
        val fields = ServiceDto::class.java.declaredFields.map { it.name }
        assertTrue(fields.none { it.contains("api_key", ignoreCase = true) || it.equals("apiKey", ignoreCase = true) })
    }

    @Test
    fun `a delta updates status and favorite for the one named service`() {
        val event = parseServiceStreamFrame(
            """{"type": "delta", "service_name": "llamacpp-gemma-4-26b-a4b-it-q8", "status": "exited",
                "action": "die", "container_id": "abc123", "timestamp": "2026-07-25T00:00:01Z",
                "metadata": {"favorite": true}}""",
        )
        assertEquals(
            ServiceStreamEvent.Delta(serviceName = "llamacpp-gemma-4-26b-a4b-it-q8", status = "exited", favorite = true),
            event,
        )
    }

    @Test
    fun `a delta with no metadata carries a null favorite, not false`() {
        val event = parseServiceStreamFrame(
            """{"type": "delta", "service_name": "vllm-qwen3-6-27b-fp8", "status": "running",
                "action": "start", "container_id": "def456", "timestamp": "2026-07-25T00:00:02Z"}""",
        )
        assertEquals(
            ServiceStreamEvent.Delta(serviceName = "vllm-qwen3-6-27b-fp8", status = "running", favorite = null),
            event,
        )
    }

    @Test
    fun `an error frame carries the server's message`() {
        val event = parseServiceStreamFrame("""{"type": "error", "message": "Docker socket unavailable"}""")
        assertEquals(ServiceStreamEvent.Error("Docker socket unavailable"), event)
    }

    @Test
    fun `a keepalive comment line is not valid JSON and is Unknown, not a crash`() {
        val event = parseServiceStreamFrame(": keepalive")
        assertTrue(event is ServiceStreamEvent.Unknown)
    }

    @Test
    fun `an unrecognised type is Unknown rather than dropped silently`() {
        val payload = """{"type": "future_frame_type", "stuff": 1}"""
        assertEquals(ServiceStreamEvent.Unknown(payload), parseServiceStreamFrame(payload))
    }

    @Test
    fun `a delta missing service_name is Unknown, since nothing can be updated with it`() {
        val payload = """{"type": "delta", "status": "running"}"""
        assertEquals(ServiceStreamEvent.Unknown(payload), parseServiceStreamFrame(payload))
    }

    @Test
    fun `garbage that is not JSON at all never throws`() {
        assertEquals(ServiceStreamEvent.Unknown("not json"), parseServiceStreamFrame("not json"))
    }
}
