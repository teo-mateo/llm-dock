package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.testing.FakePiCommandsRepository
import com.hpz.llmdockchat.testing.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiCachedCommandsTest {
    @get:Rule val main = MainDispatcherRule()
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `cached live state and prompts cannot enable send or stop before a current summary`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val transport = DrivenPiTransport()
        val commands = FakePiCommandsRepository()
        val viewModel = PiSessionViewModel(seed.identity.key, fixture.runtime(transport, seed.identity.key), commands)
        try {
            viewModel.start()
            runCurrent()
            assertTrue((viewModel.state.value as PiSessionUiState.Loaded).summary!!.live)
            assertTrue((viewModel.state.value as PiSessionUiState.Loaded).summary!!.prompts.isNotEmpty())
            viewModel.onDraftChange("send me")
            viewModel.send(); viewModel.stop()
            assertNull(commands.sentText)
            assertFalse(commands.abortCalled)
            transport.send(piBatch(9, "suffix"))
            runCurrent()
            viewModel.send(); viewModel.stop()
            assertNull(commands.sentText)
            assertFalse(commands.abortCalled)
            transport.send(resumeSummary())
            runCurrent()
            viewModel.send(); viewModel.stop()
            assertEquals("send me", commands.sentText)
            assertTrue(commands.abortCalled)
            assertEquals(fixture.server, commands.sentServer)
            assertEquals(fixture.server, commands.abortServer)
            assertEquals("", viewModel.composerState.value.draft)
            transport.fail(java.io.IOException("offline"))
            runCurrent()
            commands.sentText = null
            commands.abortCalled = false
            viewModel.onDraftChange("do not send offline")
            viewModel.send(); viewModel.stop()
            assertNull(commands.sentText)
            assertFalse(commands.abortCalled)
        } finally {
            viewModel.viewModelScope.cancel()
        }
    }
}
