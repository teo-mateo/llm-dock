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
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * Prompt selection by reference (F03 follow-up): the selection is the
 * conversation's `prompt_id`, not a content match. Selecting PUTs the id
 * alone (the server resolves the content); detaching PUTs an explicit
 * `prompt_id: null` with `main_system_prompt: ""`.
 *
 * The race half pins #264: writes serialize in selection order, a stale
 * failure is silent, a failed latest write rolls back to the confirmed
 * server value, and superseded unsent selections coalesce to nothing.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadPromptSelectionTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsApi: ApiClient
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "prompt-main") }

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
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        // Inert on purpose, for the same reason as the other thread tests: a
        // live ladder read would consume a queued MockWebServer response and
        // shift every takeRequest() assertion.
        servicesRepository = ServicesRepository(ApiClient(client, FakeServerUrlStore(), ApiJson, Dispatchers.IO))
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsApi = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        conversationsRepository = ConversationsRepository(conversationsApi)
        mcpServersRepository = McpServersRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        promptsRepository = PromptsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun enqueue(body: String) = server.enqueue(MockResponse.Builder().body(body).build())

    private fun conversation(fixture: String = "conversation_multi_turn.json") =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun viewModel(
        conversations: ConversationsRepository = conversationsRepository,
    ): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    servicesStreamRepository = servicesStreamRepository,
                    servicesRepository = servicesRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversations,
                    mcpServersRepository = mcpServersRepository,
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    /**
     * Runs the main dispatcher's queue dry. [mainExecutor] is single-threaded
     * and FIFO, so a task submitted now cannot finish before everything queued
     * ahead of it has run to its next suspension point — which makes "has the
     * next write gone out yet?" a settled question rather than a race.
     */
    private fun drainMain() {
        mainExecutor.submit { }.get(10, TimeUnit.SECONDS)
    }

    private suspend fun openedThread(): ThreadViewModel =
        viewModel().also { it.load() }.also { it.awaitLoaded() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    // -- selection ------------------------------------------------------------

    @Test
    fun `selecting a prompt updates the reference and PUTs the id alone`() = threadTest {
        conversation()
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()
        assertNull(viewModel.awaitLoaded().conversation.promptId)

        viewModel.selectPrompt("c2efe71a-cd7b")

        val state = viewModel.awaitState { it.conversation.promptId == "c2efe71a-cd7b" }
        assertEquals("c2efe71a-cd7b", state.conversation.promptId)
        server.takeRequest()
        assertEquals("""{"prompt_id":"c2efe71a-cd7b"}""", server.takeRequest().body?.utf8().orEmpty())
    }

    /**
     * The behaviour change the switch exists for: before it, a thread whose
     * stored text happened to equal a prompt's content was treated as
     * already on that prompt and the selection no-opped. The stored copy is
     * not the selection — the reference is — so the PUT still goes out.
     */
    @Test
    fun `a legacy conversation whose text matches a prompt's content is still unreferenced`() = threadTest {
        enqueue(
            """{"id":"$CONVERSATION_ID","title":"t","main_service":"llamacpp-gemma-4-26b-a4b-it-q8","messages":[],""" +
                """"mcp_servers":[],"active_run":null,""" +
                """"main_system_prompt":"You are a terse, careful assistant."}""",
        )
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()

        viewModel.selectPrompt("c2efe71a-cd7b")

        val state = viewModel.awaitState { it.conversation.promptId == "c2efe71a-cd7b" }
        assertEquals("You are a terse, careful assistant.", state.conversation.mainSystemPrompt)
        server.takeRequest()
        assertEquals("""{"prompt_id":"c2efe71a-cd7b"}""", server.takeRequest().body?.utf8().orEmpty())
    }

    // -- detach ----------------------------------------------------------------

    @Test
    fun `detaching clears the reference and sends the explicit null body`() = threadTest {
        conversation("conversation_with_prompt.json")
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()
        assertEquals("c2efe71a-cd7b", viewModel.awaitLoaded().conversation.promptId)

        viewModel.selectPrompt(null)

        val state = viewModel.awaitState { it.conversation.promptId == null }
        assertNull(state.conversation.promptId)
        server.takeRequest()
        assertEquals("""{"prompt_id":null,"main_system_prompt":""}""", server.takeRequest().body?.utf8().orEmpty())
    }

    // -- no-op and failure ------------------------------------------------------

    @Test
    fun `reselecting the current reference sends nothing`() = threadTest {
        conversation("conversation_with_prompt.json")
        val viewModel = openedThread()

        viewModel.selectPrompt("c2efe71a-cd7b")

        server.takeRequest()
        assertNull("no second request may be in flight", server.takeRequest(200, TimeUnit.MILLISECONDS))
    }

    @Test
    fun `a failed select reverts the reference and surfaces the server's error`() = threadTest {
        conversation()
        server.enqueue(
            MockResponse.Builder().code(404).body("""{"error": "Prompt not found"}""").build(),
        )
        val viewModel = openedThread()

        viewModel.selectPrompt("ghost-prompt")

        val state = viewModel.awaitState { it.actionError != null }
        assertNull(state.conversation.promptId)
        assertEquals("Prompt not found", state.actionError)
    }

    // -- race discipline (#264) -------------------------------------------------

    /**
     * The issue's probe: A fails late, after B has already settled successful.
     * A's verdict belongs to a selection the user moved past, so it must touch
     * nothing — no rollback of B, no error banner.
     */
    @Test
    fun `a late failure for a superseded select cannot erase the newer success`() = threadTest {
        conversation()
        val writes = GatedPromptWrites(conversationsApi)
        writes.script(0, PromptOutcome.Fail(404, "Prompt not found"))
        writes.script(1, PromptOutcome.Succeed("prompt-b"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-a")
        drainMain() // A is out and parked on its gate
        writes.awaitArrivals(1)
        viewModel.selectPrompt("prompt-b")
        drainMain() // B queues behind the prompt lock: it may not reach the fake yet
        assertNull(writes.pollArrival(ARRIVAL_GRACE_MS))

        writes.release(0)
        writes.awaitSettled(1)
        drainMain() // A's failure handler has now run, or it never will again
        val afterStaleFailure = viewModel.awaitLoaded()
        assertEquals("prompt-b", afterStaleFailure.conversation.promptId)
        assertNull("a superseded failure must stay silent", afterStaleFailure.actionError)

        writes.release(1)
        writes.awaitSettled(1)
        drainMain()
        val settledState = viewModel.awaitLoaded()
        assertEquals("prompt-b", settledState.conversation.promptId)
        assertNull(settledState.actionError)
        assertEquals("prompt-b", writes.stored)
        assertEquals(listOf<String?>("prompt-a", "prompt-b"), writes.seen.toList())
    }

    /**
     * Pre-fix both writes parked at once; with the lock the second cannot even
     * start. Pins "requests stay ordered".
     */
    @Test
    fun `prompt writes settle in selection order`() = threadTest {
        conversation()
        val writes = GatedPromptWrites(conversationsApi)
        writes.script(0, PromptOutcome.Succeed("prompt-a"))
        writes.script(1, PromptOutcome.Succeed("prompt-b"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-a")
        drainMain()
        writes.awaitArrivals(1)
        viewModel.selectPrompt("prompt-b")
        drainMain()
        assertNull("the second write may not start while the first holds the lock", writes.pollArrival(ARRIVAL_GRACE_MS))

        writes.release(0)
        writes.awaitSettled(1)
        writes.awaitArrivals(1)
        writes.release(1)
        writes.awaitSettled(1)
        drainMain()

        assertEquals(listOf<String?>("prompt-a", "prompt-b"), writes.seen.toList())
        assertEquals("prompt-b", writes.stored)
        assertEquals("prompt-b", viewModel.awaitLoaded().conversation.promptId)
    }

    /**
     * Superseded-skip shape: P2 is picked while P3's click is already queued, so
     * its token goes stale before it reaches the fake and no request carries it.
     * The failing latest write rolls back to the confirmed P1 — the click-time
     * `previous` pattern would restore P2, which the server never held.
     */
    @Test
    fun `a superseded select that never sent is skipped and the failed newest restores the confirmed one`() = threadTest {
        conversation("conversation_with_prompt.json")
        val writes = GatedPromptWrites(conversationsApi)
        writes.stored = PROMPT_P1
        writes.script(0, PromptOutcome.Fail(404, "Prompt not found"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-2")
        viewModel.selectPrompt("prompt-3")
        drainMain() // both launches have run: prompt-2's token is stale, so it was never sent

        writes.awaitArrivals(1)
        writes.release(0)
        writes.awaitSettled(1)
        drainMain()

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals(PROMPT_P1, state.conversation.promptId)
        assertEquals("Prompt not found", state.actionError)
        assertEquals(listOf<String?>("prompt-3"), writes.seen.toList())
        assertEquals(PROMPT_P1, writes.stored)
        assertEquals(1, server.requestCount)
    }

    /**
     * Confirmed-advances shape: P2 settles successful, then P3 fails as the
     * latest write. The rollback target is the advanced confirmed value P2 —
     * the server holds it — not the pre-P2 pick.
     */
    @Test
    fun `a failed newest write restores the advanced confirmed value not the prior pick`() = threadTest {
        conversation("conversation_with_prompt.json")
        val writes = GatedPromptWrites(conversationsApi)
        writes.stored = PROMPT_P1
        writes.script(0, PromptOutcome.Succeed("prompt-2"))
        writes.script(1, PromptOutcome.Fail(404, "Prompt not found"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-2")
        drainMain()
        writes.awaitArrivals(1)
        writes.release(0)
        writes.awaitSettled(1)
        drainMain()

        viewModel.selectPrompt("prompt-3")
        drainMain()
        writes.awaitArrivals(1)
        writes.release(1)
        writes.awaitSettled(1)
        drainMain()

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals("prompt-2", state.conversation.promptId)
        assertEquals("prompt-2", writes.stored)
    }

    /**
     * The issue's "multiple failed selections. Include selecting None": two
     * successive latest failures, the second a detach, and the confirmed
     * selection stands displayed with the newest error.
     */
    @Test
    fun `multiple failed selects including a detach leave the confirmed selection displayed`() = threadTest {
        conversation("conversation_with_prompt.json")
        val writes = GatedPromptWrites(conversationsApi)
        writes.stored = PROMPT_P1
        writes.script(0, PromptOutcome.Fail(404, "Prompt not found"))
        writes.script(1, PromptOutcome.Fail(404, "Prompt detach rejected"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-2")
        drainMain()
        writes.awaitArrivals(1)
        writes.release(0)
        writes.awaitSettled(1)
        val afterFirstFailure = viewModel.awaitState { it.actionError != null }
        assertEquals(PROMPT_P1, afterFirstFailure.conversation.promptId)

        viewModel.selectPrompt(null)
        drainMain()
        writes.awaitArrivals(1)
        writes.release(1)
        writes.awaitSettled(1)

        val state = viewModel.awaitState { it.actionError == "Prompt detach rejected" }
        assertEquals(PROMPT_P1, state.conversation.promptId)
        assertEquals(PROMPT_P1, writes.stored)
    }

    /**
     * Rapid A → B → C inside one un-interrupted main-queue stretch: the two
     * superseded tokens are dropped before sending, so exactly one PUT goes
     * out and it carries the last pick. Pins the coalescing criterion.
     */
    @Test
    fun `rapid selects coalesce to one PUT carrying the last pick`() = threadTest {
        conversation()
        val writes = GatedPromptWrites(conversationsApi)
        writes.script(0, PromptOutcome.Succeed("prompt-c"))
        val viewModel = viewModel(conversations = writes)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.selectPrompt("prompt-a")
        viewModel.selectPrompt("prompt-b")
        viewModel.selectPrompt("prompt-c")
        drainMain() // all three launches have run

        writes.awaitArrivals(1)
        writes.release(0)
        writes.awaitSettled(1)
        drainMain()

        assertEquals(listOf<String?>("prompt-c"), writes.seen.toList())
        assertEquals("prompt-c", writes.stored)
        assertEquals("prompt-c", viewModel.awaitLoaded().conversation.promptId)
        assertEquals(1, server.requestCount)
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val PROMPT_P1 = "c2efe71a-cd7b"

        /**
         * A ceiling on absence, not a timing assumption: a write that did start
         * signals its arrival, so this only has to outlast a misbehaving send.
         * Matches the takeRequest(200 ms) idiom the existing reselect test uses.
         */
        const val ARRIVAL_GRACE_MS = 200L
    }
}

private sealed interface PromptOutcome {
    data class Succeed(val value: String?) : PromptOutcome
    data class Fail(val status: Int, val message: String) : PromptOutcome
}

/**
 * A [ConversationsRepository] whose `prompt_id` writes settle only when the
 * test opens their gate, with a per-call scripted outcome applied to [stored] —
 * the fake's server copy, moved by successful settles only. [seen] records
 * arrival order, which is send order once the ViewModel's prompt lock holds.
 *
 * The write is [NonCancellable] with a bounded park, same reasons as
 * `ThreadToolsTest`'s gate: a PUT already on the wire is not recalled by
 * cancelling its coroutine, and a park the test never releases must not outlive
 * the class on Dispatchers.Main.
 */
private class GatedPromptWrites(api: ApiClient) : ConversationsRepository(api) {

    @Volatile
    var stored: String? = null

    val seen = CopyOnWriteArrayList<String?>()

    private val gates = List(GATE_COUNT) { CompletableDeferred<Unit>() }
    private val arrivals = Channel<String?>(Channel.UNLIMITED)
    private val settled = Channel<Int>(Channel.UNLIMITED)
    private val outcomes = ConcurrentHashMap<Int, PromptOutcome>()
    private val nextIndex = AtomicInteger(0)

    override suspend fun setPrompt(id: String, promptId: String?): Result<Unit> =
        withContext(NonCancellable) {
            val index = nextIndex.getAndIncrement()
            seen.add(promptId)
            arrivals.send(promptId)
            runCatching { withTimeout(GATE_TIMEOUT_MS) { gates[index].await() } }
            settled.send(index)
            when (val outcome = outcomes[index]) {
                is PromptOutcome.Succeed -> {
                    stored = outcome.value
                    Result.success(Unit)
                }
                is PromptOutcome.Fail -> Result.failure(
                    ApiException(AppError.Http(outcome.status, outcome.message, fromServer = true)),
                )
                null -> {
                    stored = promptId
                    Result.success(Unit)
                }
            }
        }

    fun script(index: Int, outcome: PromptOutcome) {
        outcomes[index] = outcome
    }

    /** Lets write [index] complete. Safe to call before that write has arrived. */
    fun release(index: Int) {
        gates[index].complete(Unit)
    }

    suspend fun awaitArrivals(count: Int) {
        withTimeout(AWAIT_TIMEOUT_MS) { repeat(count) { arrivals.receive() } }
    }

    /** The next arrival if one turns up within [timeoutMs], else null. */
    suspend fun pollArrival(timeoutMs: Long): String? =
        withTimeoutOrNull(timeoutMs) { arrivals.receive() }

    suspend fun awaitSettled(count: Int) {
        withTimeout(AWAIT_TIMEOUT_MS) { repeat(count) { settled.receive() } }
    }

    private companion object {
        const val GATE_COUNT = 8
        const val AWAIT_TIMEOUT_MS = 10_000L

        /** Ceiling on a non-cancellable park — must stay under teardown's awaitTermination. */
        const val GATE_TIMEOUT_MS = 2_000L
    }
}
