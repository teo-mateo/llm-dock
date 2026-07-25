package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import kotlinx.coroutines.launch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * F04 review probe — the D3 edges the feature's own suite does not reach.
 * Left in place per WORK_INSTRUCTIONS §4.
 *
 * The three probes that documented broken behaviour — a failed refetch losing
 * the turn, and the coalescing tail being dropped — moved to
 * [ThreadTerminalPathTest] with their assertions inverted when those two were
 * fixed. What is left here is the title backstop's bounds, D3's no-leak rule
 * and the 409 rollback.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadStreamingEdgeTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "probe-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
        drafts = FakeDraftStore()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(
                SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential),
            )
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        Dispatchers.resetMain()
        mainExecutor.shutdownNow()
    }

    private fun conversation(fixture: String = "conversation_completed.json") =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun serverError(code: Int = 500) =
        server.enqueue(MockResponse.Builder().code(code).body("""{"error":"boom"}""").build())

    private fun viewModel(titleSettleDelayMs: Long = 1L): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = titleSettleDelayMs,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded() =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(p: (ThreadUiState.Loaded) -> Boolean) =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded && p(it) } as ThreadUiState.Loaded }

    // -- the title backstop ---------------------------------------------------

    /** Bounded: at most TITLE_SETTLE_ATTEMPTS extra loads, then it stops for good. */
    @Test
    fun `the title backstop gives up after a bounded number of polls`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED, RUN_STATUS_COMPLETED)
        // refetch + every poll returns a still-untitled thread
        repeat(1 + ThreadViewModel.TITLE_SETTLE_ATTEMPTS + 2) { conversation("conversation_untitled.json") }
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming == null }

        // load + refetch + at most the four polls, and no more once it settles.
        withTimeout(5_000) {
            while (server.requestCount < 2 + ThreadViewModel.TITLE_SETTLE_ATTEMPTS) {
                kotlinx.coroutines.delay(20)
            }
        }
        kotlinx.coroutines.delay(500)
        assertEquals(2 + ThreadViewModel.TITLE_SETTLE_ATTEMPTS, server.requestCount)
    }

    /** A poll that fails aborts the backstop rather than retrying forever. */
    @Test
    fun `a failing title poll stops the backstop`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED, RUN_STATUS_COMPLETED)
        conversation("conversation_untitled.json") // refetch
        serverError() // first poll fails
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming == null }
        kotlinx.coroutines.delay(500)
        assertEquals(3, server.requestCount)
    }

    /** Leaving the screen must kill the backstop too — no polling a dead screen. */
    @Test
    fun `leaving the thread stops the title backstop`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED, RUN_STATUS_COMPLETED)
        repeat(8) { conversation("conversation_untitled.json") }
        val viewModel = viewModel(titleSettleDelayMs = 300)
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming == null }
        store.clear() // navigate away
        val atClear = server.requestCount
        kotlinx.coroutines.delay(1_500)
        assertEquals("polled after the screen went away", atClear, server.requestCount)
    }

    // -- a cancel on an untitled thread --------------------------------------

    /** A cancelled first turn generates no title, so the backstop just burns polls. */
    @Test
    fun `a cancelled first turn still triggers the title backstop`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(RUN_STARTED, delta("Once upon"))
        repeat(8) { conversation("conversation_untitled.json") }
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming == null }
        kotlinx.coroutines.delay(500)
        // load + refetch + the four wasted polls.
        assertEquals(2 + ThreadViewModel.TITLE_SETTLE_ATTEMPTS, server.requestCount)
    }

    // -- streamed text is never in `messages` --------------------------------

    @Test
    fun `no observed state ever carries streamed text inside the message list`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("zzstreamedzz"), DONE, MESSAGE_SAVED)
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        val seen = mutableListOf<ThreadUiState.Loaded>()
        val collector = kotlinx.coroutines.CoroutineScope(Dispatchers.Unconfined).launchCollect(viewModel, seen)
        viewModel.onComposerChange("hi")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming == null && it.thread.messages.size == 2 }
        collector.cancel()

        assertTrue(seen.isNotEmpty())
        seen.forEach { s ->
            assertTrue(
                "streamed text leaked into messages",
                s.thread.messages.none { it.content.contains("zzstreamedzz") },
            )
        }
    }

    // -- 409 -------------------------------------------------------------------

    @Test
    fun `a 409 restores images as well as text and leaves no phantom`() = threadTest {
        conversation()
        transport.failWith = com.hpz.llmdockchat.core.net.ApiException(
            com.hpz.llmdockchat.core.error.AppError.Http(409, "A run is already active", fromServer = true),
        )
        val viewModel = viewModel()
        viewModel.load()
        val before = viewModel.awaitLoaded()
        viewModel.onComposerChange("hi there")
        viewModel.addAttachment("data:image/png;base64,AAAA")
        viewModel.send()

        val state = viewModel.awaitState { it.actionError != null }
        assertNull(state.thread.streaming)
        assertEquals(before.thread.messages.size, state.thread.messages.size)
        assertEquals("hi there", state.composer)
        assertEquals(listOf("data:image/png;base64,AAAA"), state.attachments)
        assertEquals("hi there", drafts.saved[CONVERSATION_ID])
        assertNotNull(state.actionError)
    }

    private fun CoroutineScope.launchCollect(
        viewModel: ThreadViewModel,
        into: MutableList<ThreadUiState.Loaded>,
    ) = this.launch {
        viewModel.state.collect { if (it is ThreadUiState.Loaded) into += it }
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
        const val DONE = "[DONE]"
        const val MESSAGE_SAVED = """{"type": "message_saved", "message_id": "m2", "seq": 2}"""
        const val RUN_STATUS_COMPLETED = """{"type": "run_status", "status": "completed", "error": null}"""
        const val ERROR_FRAME = """{"error": "Service 'x' is not reachable. Is it running?"}"""

        fun delta(text: String) = """{"choices":[{"index":0,"delta":{"content":"$text"}}]}"""
    }
}
