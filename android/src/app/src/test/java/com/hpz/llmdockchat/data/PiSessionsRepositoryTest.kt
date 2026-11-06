package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PiSessionsRepositoryTest {

    private fun sessionFields(
        id: String,
        name: String = "llm-dock",
        lastSeen: Long = 1000,
        live: Boolean = true,
        prompts: String? = null,
    ): String = """
        "session_id":"$id","instance_id":"i1","name":"$name","cwd":"/repo",
        "model":null,"thinking_level":null,"first_seen":0,"last_seen":$lastSeen,
        "ended_at":null,"end_reason":null,"live":$live,"state":"idle","context_percent":null
        ${prompts?.let { ",\"prompts\":$it" } ?: ""}
    """.trimIndent()

    private fun snapshotJson(id: String, name: String = "llm-dock", lastSeen: Long = 1000) =
        """{"type":"snapshot","sessions":[{${sessionFields(id, name, lastSeen)}}]}"""

    private fun sessionJson(id: String, name: String = "llm-dock", lastSeen: Long = 1000) =
        """{"type":"session",${sessionFields(id, name, lastSeen)}}"""

    private fun sessionJsonWithPrompts(id: String, prompts: String) =
        """{"type":"session",${sessionFields(id, prompts = prompts)}}"""

    private fun session(id: String, live: Boolean = true, lastSeen: Long = 1000) = PiSession(
        key = PiSessionKey(id, "i1"),
        name = id,
        cwd = "/repo",
        model = null,
        thinkingLevel = null,
        firstSeen = 0,
        lastSeen = lastSeen,
        endedAt = null,
        endReason = null,
        live = live,
        state = if (live) PiState.IDLE else PiState.ENDED,
        contextPercent = null,
    )

    @Test
    fun `snapshot then upsert`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            snapshotJson("s1", name = "llm-dock", lastSeen = 1000),
            sessionJson("s1", name = "renamed", lastSeen = 3000),
        )
        val repository = PiSessionsRepository(transport)

        val emissions = withTimeout(5_000) {
            repository.streamWithStatus(reconnectDelayMs = 1L).take(2).toList()
        }

        assertFalse(emissions[0].stale)
        assertEquals("llm-dock", emissions[0].sessions.single().name)
        assertFalse(emissions[1].stale)
        assertEquals("renamed", emissions[1].sessions.single().name)
        assertEquals(3000L, emissions[1].sessions.single().lastSeen)
    }

    @Test
    fun `prompt open and closed frames drive needs answer`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            snapshotJson("s1"),
            sessionJsonWithPrompts("s1", """[{"prompt_id":"p1","kind":"confirm","title":"Run it?"}]"""),
            sessionJsonWithPrompts("s1", "[]"),
        )
        val repository = PiSessionsRepository(transport)

        val emissions = withTimeout(5_000) {
            repository.streamWithStatus(reconnectDelayMs = 1L).take(3).toList()
        }

        assertFalse(emissions[0].sessions.single().needsAnswer)
        assertTrue(emissions[1].sessions.single().needsAnswer)
        assertEquals("p1", emissions[1].sessions.single().prompts.single().promptId)
        assertFalse(emissions[2].sessions.single().needsAnswer)
    }

    @Test
    fun `sort live first then last seen desc`() {
        val rows = listOf(
            session("ended-old", live = false, lastSeen = 3000),
            session("live-new", live = true, lastSeen = 1000),
            session("ended-new", live = false, lastSeen = 5000),
        )
        assertEquals(
            listOf("live-new", "ended-new", "ended-old"),
            sortPiSessions(rows).map { it.key.sessionId },
        )
    }

    @Test
    fun `failure marks stale then recovers`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(snapshotJson("s1")),
                failWith = RuntimeException("connection reset"),
            ),
            ScriptedSseTransport.Leg(payloads = listOf(snapshotJson("s2"))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionsRepository(transport)

        val emissions = withTimeout(5_000) {
            repository.streamWithStatus(reconnectDelayMs = 1L).take(3).toList()
        }

        assertFalse(emissions[0].stale)
        assertEquals("s1", emissions[0].sessions.single().key.sessionId)
        assertTrue(emissions[1].stale)
        assertEquals("s1", emissions[1].sessions.single().key.sessionId)
        assertFalse(emissions[2].stale)
        assertEquals("s2", emissions[2].sessions.single().key.sessionId)
    }

    @Test
    fun `lagged reconnects without delay`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf("""{"type":"lagged"}""")),
            ScriptedSseTransport.Leg(payloads = listOf(snapshotJson("s1"))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionsRepository(transport)

        val emissions = withTimeout(5_000) {
            repository.streamWithStatus(reconnectDelayMs = 60_000L).take(1).toList()
        }

        assertEquals("s1", emissions.single().sessions.single().key.sessionId)
        assertEquals(2, transport.requests.size)
    }

    @Test
    fun `cancellation is not retried`() = runTest {
        val transport = FakeSseTransport().apply { stayOpen = true }
        val repository = PiSessionsRepository(transport)
        val job = launch {
            repository.streamWithStatus(reconnectDelayMs = 1L).collect { }
        }
        runCurrent()
        job.cancel()
        job.join()

        assertTrue(transport.cancelled.isCompleted)
        assertEquals(1, transport.requests.size)
    }
}
