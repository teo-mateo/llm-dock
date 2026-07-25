package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.model.MessageRole
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
import java.util.concurrent.Executors
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/**
 * The run lifecycle as the thread screen sees it (F04).
 *
 * The stream is a [FakeSseTransport] so frame timing is deterministic; the JSON
 * calls — the load, the refetch every terminal triggers, the cancel — go
 * through a real [MockWebServer], because *whether a cancel request was sent*
 * is exactly what F04-R10 turns on.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadViewModelTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private val store = ViewModelStore()

    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "test-main") }

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
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
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

    /**
     * Built through a [ViewModelStore] rather than by calling the constructor,
     * so `store.clear()` reaches `onCleared()` and cancels `viewModelScope` —
     * which is exactly what leaving the screen does, and what F04-R10 is about.
     */
    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    // Zero so a flush is still scheduled through the
                    // dispatcher; the window itself is asserted in
                    // ThreadCoalescingTest.
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1,
                )
            }
        },
    )[ThreadViewModel::class]

    /**
     * Real time on a single-threaded Main, not a test scheduler. The stream is
     * faked but every JSON call is real IO against MockWebServer, and virtual
     * time races past a real socket — a `withTimeout` on the test scheduler
     * fires before the loopback request it is waiting for has even landed.
     * Single-threaded because that is what Main is.
     */
    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    // -- F04-R2 · the user's message renders first ---------------------------

    @Test
    fun `the user's message shows before the first token, and never in the message list`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.onComposerChange("what is a transistor")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming?.userMessage != null }
        assertEquals("what is a transistor", state.thread.streaming?.userMessage?.content)
        // Architecture D3: `messages` still holds only what the server sent.
        assertEquals(2, state.thread.messages.size)
        assertTrue(state.thread.messages.none { it.content == "what is a transistor" })
        assertEquals("", state.composer)
    }

    @Test
    fun `send is unavailable while a run is active in this thread`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("first")
        viewModel.send()

        val state = viewModel.awaitState { it.runActive }
        assertFalse(state.canSend)
    }

    /**
     * The server rolls the user message back on a 409, so the client must too —
     * a phantom turn in the thread would be a message that does not exist.
     */
    @Test
    fun `a 409 leaves no phantom user message and puts the text back in the composer`() = threadTest {
        conversation()
        transport.failWith = ApiException(
            AppError.Http(409, "A run is already active for this conversation", fromServer = true),
        )
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.onComposerChange("second turn")
        viewModel.send()

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals("A run is already active for this conversation", state.actionError)
        assertNull(state.thread.streaming)
        assertEquals(2, state.thread.messages.size)
        assertEquals("second turn", state.composer)
        assertEquals("second turn", drafts.saved[CONVERSATION_ID])
    }

    // -- F04-R3 / D3 · streamed text is separate state -----------------------

    @Test
    fun `deltas accumulate on the streaming turn, not into the message list`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("Hel"), delta("lo"), delta(" there"))
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming?.content == "Hello there" }
        assertEquals(2, state.thread.messages.size)
    }

    @Test
    fun `reasoning is accumulated separately and never mixed into the answer`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, reasoningDelta("think"), reasoningDelta("ing"), delta("answer"))
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val turn = viewModel.awaitState { it.thread.streaming?.content == "answer" }.thread.streaming!!
        assertEquals("thinking", turn.reasoning)
        assertEquals("answer", turn.content)
    }

    /** The replay chunk carries both halves at once, and must not be split wrongly. */
    @Test
    fun `a coalesced replay delta lands as one chunk of each kind`() = threadTest {
        conversation()
        transport.payloads = listOf(
            RUN_STARTED,
            """{"choices": [{"delta": {"content": "abc", "reasoning_content": "why"}}]}""",
        )
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val turn = viewModel.awaitState { it.thread.streaming?.content == "abc" }.thread.streaming!!
        assertEquals("why", turn.reasoning)
    }

    // -- F04-R5 · tool calls -------------------------------------------------

    @Test
    fun `a pending call becomes one card that gains its arguments and result in place`() = threadTest {
        conversation()
        transport.payloads = listOf(
            RUN_STARTED,
            """{"type": "tool_call_pending", "index": 0, "name": "sympy-math__differentiate"}""",
            """{"type": "tool_call", "name": "differentiate", "arguments": {"expression": "x**3"}, "server_id": "sympy-math"}""",
            """{"type": "tool_result", "name": "differentiate", "result": "3*x**2", "server_id": "sympy-math"}""",
        )
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("differentiate")
        viewModel.send()

        val calls = viewModel.awaitState { it.thread.streaming?.toolCalls?.firstOrNull()?.result != null }
            .thread.streaming!!.toolCalls
        assertEquals(1, calls.size)
        assertEquals("differentiate", calls.single().name)
        assertEquals("sympy-math", calls.single().serverId)
        assertTrue(calls.single().arguments!!.contains("x**3"))
        assertEquals("3*x**2", calls.single().result)
    }

    @Test
    fun `two calls in one turn stay two cards, in order`() = threadTest {
        conversation()
        transport.payloads = listOf(
            RUN_STARTED,
            """{"type": "tool_call", "name": "alpha", "arguments": {}, "server_id": "s"}""",
            """{"type": "tool_result", "name": "alpha", "result": "1", "server_id": "s"}""",
            """{"type": "tool_call", "name": "beta", "arguments": {}, "server_id": "s"}""",
            """{"type": "tool_result", "name": "beta", "result": "2", "server_id": "s"}""",
        )
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        viewModel.send()

        val calls = viewModel.awaitState {
            it.thread.streaming?.toolCalls?.let { calls -> calls.size == 2 && calls.last().result != null } == true
        }.thread.streaming!!.toolCalls
        assertEquals(listOf("alpha", "beta"), calls.map { it.name })
        assertEquals(listOf("1", "2"), calls.map { it.result })
    }

    @Test
    fun `a parse warning is carried on the turn`() = threadTest {
        conversation()
        transport.payloads = listOf(
            RUN_STARTED,
            """{"type": "parse_warning", "kind": "silent_drop", "snippet": "", "description": "Parser dropped a malformed tool call"}""",
        )
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        viewModel.send()

        val warning = viewModel.awaitState { it.thread.streaming?.parseWarning != null }.thread.streaming!!.parseWarning!!
        assertEquals("Parser dropped a malformed tool call", warning.displayText)
    }

    // -- F04-R7 · completion and title ---------------------------------------

    @Test
    fun `on message_saved the server's message replaces the streamed text`() = threadTest {
        conversation()
        // The stream carries "hello"; the server has "hello there". After the
        // terminal, what is on screen must be the server's, not the client's.
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED)
        conversation() // the refetch every terminal triggers
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming == null }
        assertEquals(2, state.thread.messages.size)
        assertEquals(MessageRole.ASSISTANT, state.thread.messages.last().role)
        assertEquals("hello there", state.thread.messages.last().content)
    }

    /** `[DONE]` does not end the stream — the title frame arrives after it. */
    @Test
    fun `a conversation_updated frame after message_saved retitles the thread`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(
            RUN_STARTED,
            delta("hello"),
            DONE,
            MESSAGE_SAVED,
            """{"type": "conversation_updated", "id": "$CONVERSATION_ID", "title": "Greeting test"}""",
        )
        conversation("conversation_untitled.json")
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        // The title lands during the drain phase, while the turn is still on
        // screen — the stream is deliberately still open at that point.
        viewModel.awaitState { it.conversation.title == "Greeting test" }
        viewModel.awaitState { it.thread.streaming == null }
    }

    /**
     * The frame is frequently never delivered: `auto_generate_title` runs after
     * the run is already marked complete, and the SSE observer closes on the
     * durable status after three idle seconds. So the app polls briefly instead
     * of trusting the frame — see F04's *Deviations*.
     */
    @Test
    fun `a title that arrives only after the stream closed is still picked up`() = threadTest {
        conversation("conversation_untitled.json")
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED, RUN_STATUS_COMPLETED)
        conversation("conversation_untitled.json") // refetch: title not generated yet
        conversation() // settle poll: the auto-title has landed
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val state = viewModel.awaitState { it.conversation.title == "Testing Specific Greeting Request" }
        assertNull(state.thread.streaming)
    }

    @Test
    fun `a thread that already has a title is not polled for one`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED)
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        viewModel.awaitState { it.thread.streaming == null }
        // load + refetch, and no settle polls on top.
        assertEquals(2, server.requestCount)
    }

    // -- F04-R8 · failure ----------------------------------------------------

    @Test
    fun `an error frame drops the streamed turn and surfaces the persisted run error`() = threadTest {
        conversation("conversation_failed_run.json")
        transport.payloads = listOf(RUN_STARTED, ERROR_FRAME)
        conversation("conversation_failed_run.json")
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hello")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming == null && it.runError != null }
        assertEquals(
            "Service 'llamacpp-f04-test-missing' is not reachable. Is it running?",
            state.runError,
        )
        // The thread stays usable once the run is terminal.
        assertFalse(state.runActive)
    }

    /**
     * The other half of F04-R8: a failure keeps the partial. Unlike a cancel,
     * `ChatRunner._fail` persists whatever text accumulated *and* stamps the
     * error onto that same assistant message, so after the refetch the turn is
     * a real message with real text — not an empty bubble with an error note.
     * The fixture is that conversation, recorded from the dashboard's own
     * runner with the model failing mid-answer.
     */
    @Test
    fun `a failure keeps the partial text, with the error on that turn`() = threadTest {
        conversation("conversation_partial_failure.json")
        transport.payloads = listOf(RUN_STARTED, delta(PARTIAL_HEAD), ERROR_FRAME)
        conversation("conversation_partial_failure.json")
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("Write a long essay about the transistor.")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming == null && it.thread.messages.size == 2 }
        val answer = state.thread.messages.last()
        assertEquals(MessageRole.ASSISTANT, answer.role)
        assertTrue("the partial answer was not kept", answer.content.startsWith(PARTIAL_HEAD))
        assertEquals(MODEL_DIED, answer.error)
        assertEquals(MODEL_DIED, state.runError)
        // The error belongs to the message, so the thread must not repeat it as
        // a standalone note as well.
        assertNull(state.actionError)
        assertFalse(state.runActive)
    }

    // -- F04-R6 · stop -------------------------------------------------------

    @Test
    fun `stop cancels by conversation with the captured run id`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("Once upon"))
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        server.takeRequest()
        viewModel.onComposerChange("write an essay")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming?.runId != null }

        server.enqueue(MockResponse.Builder().body("""{"run": {"id": "run-1", "status": "cancelled"}}""").build())
        viewModel.stop()

        val request = withTimeout(10_000) { server.takeRequest() }
        assertEquals("POST", request.method)
        assertEquals("/api/chat/conversations/$CONVERSATION_ID/cancel-active-run", request.url.encodedPath)
        assertEquals("""{"expected_run_id":"run-1"}""", request.body?.utf8())
    }

    /**
     * A cancelled run persists **no** assistant message. The stream just ends;
     * the partial existed only in the client's buffer and must not be presented
     * as a saved turn (F04-R6, and the mockup's own correction).
     */
    @Test
    fun `after a cancel the partial answer is dropped and not presented as saved`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("Once upon a time"))
        conversation() // the refetch: the server has no assistant turn for this run
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("write an essay")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming == null }
        assertTrue(state.thread.messages.none { it.content.contains("Once upon") })
        assertNull(state.actionError)
    }

    // -- F04-R10 · leaving is not cancelling ---------------------------------

    /**
     * The whole point of the background run model: the app unsubscribes and the
     * server keeps generating. If this ever issues a cancel, every glance at
     * another screen would kill the answer.
     */
    @Test
    fun `clearing the screen's ViewModel cancels the stream and sends no cancel request`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("still going"))
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        server.takeRequest()
        viewModel.onComposerChange("write an essay")
        viewModel.send()
        viewModel.awaitState { it.thread.streaming?.content == "still going" }
        val requestsBefore = server.requestCount

        store.clear()

        withTimeout(10_000) { transport.cancelled.await() }
        assertNull(
            "leaving the thread must not send a cancel request",
            server.takeRequest(500, TimeUnit.MILLISECONDS),
        )
        assertEquals(requestsBefore, server.requestCount)
    }

    // -- Architecture P1 · deltas are coalesced ------------------------------

    /**
     * The distinguishing test for P1. A thousand tokens are consumed and the
     * UI state is still untouched, because nothing reaches it until the window
     * elapses — an implementation that copied state per token would have
     * published a thousand times before this assertion ran.
     */
    @Test
    fun `a burst of deltas reaches UI state as one update, not one per token`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED) + (1..1000).map { delta("t") }
        transport.stayOpen = true
        val viewModel = viewModelWithWindow(coalesceWindowMs = 60_000)
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        viewModel.send()

        // Every delta has been consumed by the run layer…
        withTimeout(10_000) { transport.parked.await() }
        // …and none of them has reached the screen.
        val state = viewModel.awaitState { it.thread.streaming?.runId != null }
        assertEquals("", state.thread.streaming?.content)
    }

    @Test
    fun `the coalesced text lands once the window elapses`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED) + (1..1000).map { delta("t") }
        transport.stayOpen = true
        val viewModel = viewModelWithWindow(coalesceWindowMs = 1)
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming?.content?.length == 1000 }
        assertEquals("t".repeat(1000), state.thread.streaming?.content)
    }

    private fun viewModelWithWindow(coalesceWindowMs: Long): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(CONVERSATION_ID, repository, drafts, coalesceWindowMs, titleSettleDelayMs = 1)
            }
        },
    )[ThreadViewModel::class]

    // -- F04-R1 · the draft --------------------------------------------------

    @Test
    fun `a stored draft is restored when the thread opens, and cleared once sent`() = threadTest {
        drafts.saved[CONVERSATION_ID] = "half-written question"
        conversation()
        val viewModel = viewModel()
        viewModel.load()

        assertEquals("half-written question", viewModel.awaitLoaded().composer)

        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        viewModel.send()
        viewModel.awaitState { it.thread.streaming != null }
        assertFalse(CONVERSATION_ID in drafts.saved)
    }

    @Test
    fun `typing is persisted so it survives the screen being destroyed`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.onComposerChange("survives a 401")

        assertEquals("survives a 401", drafts.saved[CONVERSATION_ID])
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
        const val DONE = "[DONE]"
        const val MESSAGE_SAVED = """{"type": "message_saved", "message_id": "m2", "seq": 2}"""
        const val RUN_STATUS_COMPLETED = """{"type": "run_status", "status": "completed", "error": null}"""
        const val ERROR_FRAME =
            """{"error": "Service 'llamacpp-f04-test-missing' is not reachable. Is it running?"}"""

        /** As recorded in `conversation_partial_failure.json`. */
        const val PARTIAL_HEAD = "The transistor was invented at Bell Labs in 1947"
        const val MODEL_DIED = "Model returned HTTP 500: llama server terminated unexpectedly"

        fun delta(text: String) = """{"choices":[{"index":0,"delta":{"content":"$text"}}]}"""
        fun reasoningDelta(text: String) = """{"choices":[{"index":0,"delta":{"reasoning_content":"$text"}}]}"""
    }
}
