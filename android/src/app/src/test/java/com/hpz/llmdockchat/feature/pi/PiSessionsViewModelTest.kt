package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.PiSessionsRepository
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class PiSessionsViewModelTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private fun sessionFields(
        id: String,
        name: String,
        cwd: String,
        live: Boolean,
        lastSeen: Long,
        contextPercent: Double?,
    ): String = """
        "session_id":"$id","instance_id":"i1","name":"$name","cwd":"$cwd",
        "model":null,"thinking_level":null,"first_seen":0,"last_seen":$lastSeen,
        "ended_at":null,"end_reason":null,"live":$live,"state":"idle",
        "context_percent":$contextPercent
    """.trimIndent()

    private fun snapshotJson(): String = """
        {"type":"snapshot","sessions":[
            {${sessionFields("live", "live-one", "/repo/live", true, 2000, 22.5)}},
            {${sessionFields("ended", "ended-one", "/repo/ended", false, 1000, null)}}
        ]}
    """.trimIndent()

    private fun settle(viewModel: PiSessionsViewModel): PiSessionsUiState.Loaded = runBlocking {
        withTimeout(5_000) {
            viewModel.state.first { it is PiSessionsUiState.Loaded }
        }
    } as PiSessionsUiState.Loaded

    @Test
    fun `starts loading`() {
        val viewModel = PiSessionsViewModel(PiSessionsRepository(FakeSseTransport()))
        assertTrue(viewModel.state.value is PiSessionsUiState.Loading)
    }

    @Test
    fun `loaded splits live and ended`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(snapshotJson())
        val viewModel = PiSessionsViewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = settle(viewModel)
        assertEquals(listOf("live"), loaded.live.map { it.key.sessionId })
        assertEquals(listOf("ended"), loaded.ended.map { it.key.sessionId })
        assertFalse(loaded.stale)
    }

    @Test
    fun `needs answer reaches the loaded state through the stream`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            snapshotJson(),
            """
                {"type":"session","session_id":"live","instance_id":"i1","name":"live-one",
                 "cwd":"/repo/live","model":null,"thinking_level":null,"first_seen":0,
                 "last_seen":2000,"ended_at":null,"end_reason":null,"live":true,
                 "state":"working","context_percent":null,
                 "prompts":[{"prompt_id":"p1","kind":"approval","title":"Approve rm?"}]}
            """.trimIndent(),
        )
        val viewModel = PiSessionsViewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = runBlocking {
            withTimeout(5_000) {
                viewModel.state.first { state ->
                    state is PiSessionsUiState.Loaded && state.live.single().needsAnswer
                }
            }
        } as PiSessionsUiState.Loaded
        assertEquals(listOf("live"), loaded.live.map { it.key.sessionId })
    }

    @Test
    fun `stale is passed through`() {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(failWith = RuntimeException("down")))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = PiSessionsViewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = settle(viewModel)
        assertTrue(loaded.stale)
        assertTrue(loaded.live.isEmpty())
        assertTrue(loaded.ended.isEmpty())
    }

    @Test
    fun `start is idempotent`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(snapshotJson())
        val viewModel = PiSessionsViewModel(PiSessionsRepository(transport))
        viewModel.start()
        viewModel.start()

        assertEquals(1, transport.requests.size)
    }
}
