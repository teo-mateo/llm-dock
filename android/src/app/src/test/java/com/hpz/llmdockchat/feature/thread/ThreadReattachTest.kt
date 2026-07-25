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
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.core.net.parseFrame
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CompletableDeferred
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * F09 · coming back to a run that was already going.
 *
 * The three run-producing endpoints share one reader (Architecture D2), so
 * nothing here is a second parser — these tests are about what the *reader is
 * pointed at*, and about the one thing reattachment can get catastrophically
 * wrong: `GET /api/chat/runs/<id>/stream` replays the whole run from the
 * beginning on **every** subscribe, so any client that accumulates across two
 * connections shows the answer twice.
 *
 * The two replay fixtures are consecutive reattaches to one real run on
 * `llamacpp-laguna-s-2.1-q4`, recorded 2026-07-25 and cut at a frame boundary.
 * The second one's first delta is 12,304 characters and contains every
 * character the first one delivered — that is the trap, in the dashboard's own
 * bytes rather than in a hand-written mock.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadReattachTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: ScriptedSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "reattach-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = ScriptedSseTransport()
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
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsRepository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        mcpServersRepository = McpServersRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        Dispatchers.resetMain()
        mainExecutor.shutdownNow()
    }

    private fun conversation(fixture: String) =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    servicesStreamRepository = servicesStreamRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversationsRepository,
                    mcpServersRepository = mcpServersRepository,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1L,
                    // Real backoff arithmetic is asserted in ReconnectBackoffTest;
                    // here the schedule is compressed so the *loop* can be, without
                    // any test waiting on a real second.
                    reconnectInitialMs = 1L,
                    reconnectMaxMs = 2L,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded() =
        withTimeout(TIMEOUT_MS) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    /** Names what it is waiting for, so a timeout reads as a failed expectation. */
    private suspend fun ThreadViewModel.awaitState(
        what: String,
        p: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded {
        val reached = runCatching {
            withTimeout(TIMEOUT_MS) { state.first { it is ThreadUiState.Loaded && p(it) } }
        }
        return reached.getOrNull() as? ThreadUiState.Loaded
            ?: throw AssertionError("never reached: $what — last state was ${state.value}")
    }

    // -- F09-R1 · detect an in-flight run --------------------------------------

    /**
     * The criterion is "*before any stream data arrives*", so the reattach leg
     * is parked on a gate that this test never opens: if the generating state
     * depended on a frame, nothing would ever satisfy it.
     */
    @Test
    fun `opening a thread with a running turn shows it generating before any frame arrives`() = threadTest {
        conversation("conversation_active_run.json")
        val neverOpens = CompletableDeferred<Unit>()
        val leg = ScriptedSseTransport.Leg(openGate = neverOpens, park = true)
        transport.script(leg)

        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitState("a generating turn") { it.thread.streaming != null }
        assertTrue("the thread must read as generating", state.runActive)
        assertEquals("nothing was streamed yet", "", state.thread.streaming?.content)
        assertTrue("this turn was picked up, not sent here", state.thread.streaming?.reattached == true)

        // The mechanism, not the symptom: a subscribe to *this run's* stream.
        withTimeout(TIMEOUT_MS) { leg.opened.await() }
        val request = transport.requests.single()
        assertEquals("/api/chat/runs/$ACTIVE_RUN_ID/stream", request.path)
        assertEquals("GET", request.method)
    }

    @Test
    fun `a thread with no active run neither reattaches nor shows a generating state`() = threadTest {
        conversation("conversation_completed.json")
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertNull(state.thread.streaming)
        assertFalse(state.runActive)
        assertTrue("nothing should have been subscribed", transport.requests.isEmpty())
    }

    // -- F09-R2 · reattach with replay ------------------------------------------

    /**
     * **The duplication test.** Two consecutive reattaches to one run, as
     * recorded: the second replays everything the first delivered and then some.
     * A client that keeps accumulating across the two shows 8,168 characters
     * twice; the answer on screen must be exactly the second replay, once.
     */
    @Test
    fun `reattaching twice does not duplicate the text the first attach already showed`() = threadTest {
        val first = fixtureFrames("sse/reattach-replay-first.sse")
        val second = fixtureFrames("sse/reattach-replay-second.sse")
        val firstText = contentOf(first)
        val secondText = contentOf(second)
        assertTrue("fixture precondition: the second attach replays the first in full",
            secondText.startsWith(firstText))

        conversation("conversation_active_run.json")
        val dropFirst = CompletableDeferred<Unit>()
        transport.script(
            ScriptedSseTransport.Leg(payloads = first, endGate = dropFirst, failWith = dropped()),
            ScriptedSseTransport.Leg(payloads = second, park = true),
        )

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitState("the first replay") { it.thread.streaming?.content == firstText }

        dropFirst.complete(Unit)

        // Any growth past the first attach means the second one has landed; what
        // it grew *to* is the actual assertion, so a client that appended the
        // replay reports the duplication rather than timing out on a length it
        // will never reach.
        val state = viewModel.awaitState("the second replay") {
            (it.thread.streaming?.content?.length ?: 0) > firstText.length
        }
        val shown = state.thread.streaming?.content.orEmpty()
        assertEquals(
            "the replayed prefix was appended to what was already on screen " +
                "(${shown.length} chars for a ${secondText.length}-char answer)",
            secondText,
            shown,
        )
    }

    /**
     * A mid-run reattach continues live from where the run is now: the replayed
     * chunk *and* the tokens that follow it, in one turn.
     */
    @Test
    fun `a reattached run continues live after its replay`() = threadTest {
        conversation("conversation_active_run.json")
        val liveTail = CompletableDeferred<Unit>()
        transport.script(
            ScriptedSseTransport.Leg(
                // What `observe()` sends a mid-run subscriber: the run id, then
                // the coalesced history…
                payloads = listOf(RUN_STARTED, delta("everything generated while away. ")),
                endGate = liveTail,
                // …then the live tail, on the same connection.
                tailPayloads = listOf(delta("and the rest"), DONE, MESSAGE_SAVED),
            ),
        )
        conversation("conversation_completed.json")

        val viewModel = viewModel()
        viewModel.load()
        val replayed = viewModel.awaitState("the replay") {
            it.thread.streaming?.content == "everything generated while away. "
        }
        assertFalse("mid-run is not reconnecting", replayed.thread.streaming?.reconnecting == true)

        liveTail.complete(Unit)
        viewModel.awaitState("the live tail") {
            it.thread.streaming?.content == "everything generated while away. and the rest"
        }
        // And it lands on the server's copy, like any other terminal (D3).
        viewModel.awaitState("the settled thread") { it.thread.streaming == null && !it.runActive }
    }

    /**
     * Reattaching to a run that has already ended: one `run_status` frame, the
     * stream closes, and the answer comes from the conversation payload —
     * `streaming` must be gone, and the saved text must appear exactly once.
     */
    @Test
    fun `reattaching to a finished run shows the saved answer once`() = threadTest {
        conversation("conversation_active_run.json")
        transport.script(ScriptedSseTransport.Leg(payloads = fixtureFrames("sse/reattach-terminal.sse")))
        conversation("conversation_completed.json")

        val viewModel = viewModel()
        viewModel.load()

        // Both halves matter, and both must be in the predicate: `load()` emits
        // its Loaded state a moment before the reattach puts the placeholder up,
        // so "streaming is null" alone can match the wrong emission — the one
        // where the conversation still says a run is live.
        val settled = viewModel.awaitState("the saved thread") {
            it.thread.streaming == null && !it.runActive
        }
        assertEquals("the refetched thread", 2, settled.thread.messages.size)
        val answer = settled.thread.messages.last().content
        assertTrue("the saved answer is missing", answer.isNotBlank())
        assertEquals("the answer appears more than once", 1, settled.thread.messages.count { it.content == answer })
    }

    @Test
    fun `an unknown run id reports the error instead of hanging`() = threadTest {
        conversation("conversation_active_run.json")
        transport.script(
            ScriptedSseTransport.Leg(
                failWith = ApiException(AppError.Http(404, "Run not found", fromServer = true)),
            ),
        )
        // The refetch that every terminal triggers; this one is what corrects
        // the stale `active_run` the load came back with.
        conversation("conversation_completed.json")

        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitState("the error") { it.actionError != null }
        assertEquals("Run not found", state.actionError)
        assertNull("nothing should still be shown as generating", state.thread.streaming)
        assertFalse("a run that does not exist must not lock the composer", state.runActive)
    }

    // -- F09-R3 · Stop still works after reattaching -----------------------------

    /**
     * The guard has to be the run id the *reattached* stream announced, not
     * whatever the conversation payload happened to hold — that is what stops a
     * late Stop from killing a run that started after the one it meant to stop
     * (`request_cancel_for_conversation`'s `expected_run_id`).
     */
    @Test
    fun `stop after a reattach cancels with the reattached run's id`() = threadTest {
        conversation("conversation_active_run.json")
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("half an answer")), park = true),
        )
        server.enqueue(MockResponse.Builder().body("""{"run":null}""").build())

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitState("the replay") { it.thread.streaming?.content == "half an answer" }
        viewModel.stop()

        server.takeRequest() // load()'s own GET, issued first
        val cancel = withTimeout(TIMEOUT_MS) { server.takeRequest() }
        assertEquals("POST", cancel.method)
        assertEquals("/api/chat/conversations/$CONVERSATION_ID/cancel-active-run", cancel.url.encodedPath)
        // Not the conversation payload's `active_run.id` — the id this stream
        // announced. They differ here on purpose.
        assertEquals("""{"expected_run_id":"$STREAM_RUN_ID"}""", cancel.body?.utf8())
    }

    // -- F09-R4 · honest offline behaviour ---------------------------------------

    /**
     * The fourth criterion, which is the one with teeth: mid-drop, the turn must
     * not read as finished. It is still `streaming`, the run still counts as
     * active, and it says *reconnecting* — and when frames resume, it stops
     * saying so.
     */
    @Test
    fun `a dropped connection reads as reconnecting, never as a finished answer`() = threadTest {
        conversation("conversation_active_run.json")
        val drop = CompletableDeferred<Unit>()
        val resume = CompletableDeferred<Unit>()
        transport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(RUN_STARTED, delta("half an answer")),
                endGate = drop,
                failWith = dropped(),
            ),
            ScriptedSseTransport.Leg(
                payloads = listOf(RUN_STARTED, delta("half an answer and the rest")),
                openGate = resume,
                park = true,
            ),
        )

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitState("the first half") { it.thread.streaming?.content == "half an answer" }

        drop.complete(Unit)
        val reconnecting = viewModel.awaitState("the reconnecting state") {
            it.thread.streaming?.reconnecting == true
        }
        assertEquals("the text already shown must stay", "half an answer", reconnecting.thread.streaming?.content)
        assertTrue("a dropped run is not a finished one", reconnecting.runActive)
        assertNull("nothing was saved, so nothing may be reported", reconnecting.actionError)

        resume.complete(Unit)
        val resumed = viewModel.awaitState("the resumed stream") {
            it.thread.streaming?.content == "half an answer and the rest"
        }
        assertFalse("reconnecting must clear once frames resume", resumed.thread.streaming?.reconnecting == true)
    }

    /**
     * The retry is always a *reattach*. Re-issuing the POST would create a
     * second run and a second copy of the user's message — the one mistake in
     * this feature that damages the thread rather than the screen.
     */
    @Test
    fun `a drop on the send path retries by reattaching, never by posting again`() = threadTest {
        conversation("conversation_completed.json")
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("hi")), failWith = dropped()),
            ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("hi there"), DONE, MESSAGE_SAVED)),
        )
        conversation("conversation_completed.json")

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hello")
        viewModel.send()

        viewModel.awaitState("the settled thread") { it.thread.streaming == null && !it.runActive }
        val paths = transport.requests.map { "${it.method} ${it.path}" }
        assertEquals(
            listOf(
                "POST /api/chat/conversations/$CONVERSATION_ID/messages",
                "GET /api/chat/runs/$STREAM_RUN_ID/stream",
            ),
            paths,
        )
    }

    /**
     * "Does not give up permanently." Five refused connections in a row and the
     * app is still trying — and still only ever with a reattach.
     */
    @Test
    fun `reconnect attempts keep coming while the server is unreachable`() = threadTest {
        conversation("conversation_active_run.json")
        repeat(REFUSALS) { transport.script(ScriptedSseTransport.Leg(failWith = dropped())) }
        val recovered = ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("back")), park = true)
        transport.script(recovered)

        val viewModel = viewModel()
        viewModel.load()

        withTimeout(TIMEOUT_MS) { recovered.opened.await() }
        viewModel.awaitState("the recovered stream") { it.thread.streaming?.content == "back" }
        assertEquals(REFUSALS + 1, transport.requests.size)
        assertTrue("every retry is a reattach", transport.requests.all { it.method == "GET" })
    }

    /** The second criterion. A send that never reaches the server loses nothing. */
    @Test
    fun `a send with no network keeps the text in the composer and says why`() = threadTest {
        conversation("conversation_completed.json")
        transport.script(ScriptedSseTransport.Leg(failWith = dropped()))

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("worth keeping")
        viewModel.send()

        val state = viewModel.awaitState("the failure") { it.actionError != null }
        assertEquals("worth keeping", state.composer)
        assertEquals("worth keeping", drafts.saved[CONVERSATION_ID])
        assertNull("no phantom turn may be left behind", state.thread.streaming)
        // One attempt only: a send that never connected must not be retried,
        // because a retry that *did* connect would be a second turn.
        assertEquals(1, transport.requests.size)
    }

    // -- F09-R5 · catching up on what happened while away -------------------------

    @Test
    fun `a run that failed while the app was away shows its error on reopening`() = threadTest {
        conversation("conversation_failed_run.json")
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertEquals(
            "Service 'llamacpp-f04-test-missing' is not reachable. Is it running?",
            state.runError,
        )
        assertFalse(state.runActive)
        assertTrue("a terminal run must not be reattached to", transport.requests.isEmpty())
    }

    /**
     * Cancelled elsewhere — the desktop, or this app on a previous visit. The
     * server keeps no assistant message for it, `active_run` is null and
     * `last_run` is `cancelled`, so the thread must simply look idle: no
     * generating spinner, and no error either, because nothing failed.
     */
    @Test
    fun `a run cancelled elsewhere leaves no phantom generating state`() = threadTest {
        conversation("conversation_cancelled_run.json")
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertNull(state.thread.streaming)
        assertFalse(state.runActive)
        assertNull("a cancel is not a failure", state.runError)
        assertTrue(transport.requests.isEmpty())
        // The partial the cancelled run produced was never persisted, so the
        // thread ends on the user's own message.
        assertEquals(MessageRole.USER, state.thread.messages.last().role)
    }

    private companion object {
        const val TIMEOUT_MS = 10_000L
        const val REFUSALS = 5
        const val CONVERSATION_ID = "ac743d66-9611-4b48-9bf3-df25df79f81e"

        /** The `active_run.id` in `conversation_active_run.json`. */
        const val ACTIVE_RUN_ID = "2ace573e-6084-4f28-b154-fe052082fc6c"

        /** The `run_id` the scripted [RUN_STARTED] frame announces. */
        const val STREAM_RUN_ID = "run-1"

        const val RUN_STARTED = """{"type": "run_started", "run_id": "$STREAM_RUN_ID"}"""
        const val DONE = "[DONE]"
        const val MESSAGE_SAVED = """{"type": "message_saved", "message_id": "m2", "seq": 2}"""

        fun delta(text: String) = """{"choices":[{"index":0,"delta":{"content":"$text"}}]}"""

        /** What OkHttp raises when a stream dies under it. */
        fun dropped() = ApiException(AppError.Network(IOException("unexpected end of stream")))

        /** The `data:` payloads of a recorded stream, in order. */
        fun fixtureFrames(name: String): List<String> = readFixture(name)
            .lineSequence()
            .filter { it.startsWith("data: ") }
            .map { it.removePrefix("data: ") }
            .toList()

        fun contentOf(frames: List<String>): String = frames
            .map(::parseFrame)
            .filterIsInstance<RunEvent.Delta>()
            .joinToString("") { it.content }
    }
}
