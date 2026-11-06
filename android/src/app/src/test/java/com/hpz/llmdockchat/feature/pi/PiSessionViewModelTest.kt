package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.data.PiSessionEventsRepository
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class PiSessionViewModelTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private val key = PiSessionKey("s1", "i1")

    private fun eventsFrame(): String = """
        {"type":"events","events":[
            {"seq":1,"type":"user_message","ts":1000,"payload":{"text":"hi","image_count":0,"origin":"terminal"}},
            {"seq":2,"type":"assistant_delta","ts":2000,"payload":{"text":"hello","thinking":""}}
        ]}
    """.trimIndent()

    private suspend fun awaitLoaded(viewModel: PiSessionViewModel): PiSessionUiState.Loaded =
        viewModel.state.first { it is PiSessionUiState.Loaded } as PiSessionUiState.Loaded

    @Test
    fun `starts loading`() {
        val viewModel = PiSessionViewModel(key, PiSessionEventsRepository(FakeSseTransport()))
        assertTrue(viewModel.state.value is PiSessionUiState.Loading)
    }

    @Test
    fun `first emission loads transcript`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(payloads = listOf(eventsFrame()), park = true))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = PiSessionViewModel(key, PiSessionEventsRepository(transport))
        viewModel.start()

        val loaded = awaitLoaded(viewModel)
        assertEquals(2, loaded.transcript.items.size)
        assertTrue(loaded.transcript.items[0] is PiItem.User)
        assertTrue(loaded.transcript.items[1] is PiItem.Assistant)
        assertFalse(loaded.stale)
    }

    @Test
    fun `unknown maps to Unknown`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                failWith = ApiException(AppError.Http(404, "unknown_session", true)),
            ),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = PiSessionViewModel(key, PiSessionEventsRepository(transport))
        viewModel.start()

        assertTrue(
            viewModel.state.first { it is PiSessionUiState.Unknown } is PiSessionUiState.Unknown,
        )
    }

    @Test
    fun `stale passed through`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(failWith = RuntimeException("down")))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = PiSessionViewModel(key, PiSessionEventsRepository(transport))
        viewModel.start()

        val loaded = awaitLoaded(viewModel)
        assertTrue(loaded.stale)
        assertTrue(loaded.transcript.items.isEmpty())
    }

    @Test
    fun `start is idempotent`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(eventsFrame())
        val viewModel = PiSessionViewModel(key, PiSessionEventsRepository(transport))
        viewModel.start()
        viewModel.start()

        awaitLoaded(viewModel)
        assertEquals(1, transport.requests.size)
    }
}
