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
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import com.hpz.llmdockchat.testing.quiesceAndRelease
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
import java.util.concurrent.TimeUnit
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Delete and edit-and-resend (F06-R2, F06-R3): the confirm-then-request shape,
 * the two 409 paths (delete refused mid-run, edit rejected after the local
 * truncation already ran), and the discard count against a four-message
 * fixture recorded the same way the F04 ones were.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadMessageActionsTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "actions-main") }

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
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsRepository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
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

    private fun conversation(fixture: String = "conversation_multi_turn.json") =
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
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    private fun ThreadUiState.Loaded.message(id: String): ChatMessage = thread.messages.single { it.id == id }

    // -- F06-R2 · delete -------------------------------------------------------

    @Test
    fun `deleting removes the message and it stays gone after a refetch`() = threadTest {
        conversation()
        server.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        conversation("conversation_multi_turn_after_delete.json") // the reload confirmDelete triggers
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        server.takeRequest() // drain the initial load

        viewModel.requestDelete(loaded.message("m2"))
        assertNotNull(viewModel.awaitState { it.pendingDelete != null }.pendingDelete)
        viewModel.confirmDelete()

        val settled = viewModel.awaitState { it.thread.messages.size == 3 }
        assertTrue(settled.thread.messages.none { it.id == "m2" })
        assertNull(settled.pendingDelete)

        val deleteRequest = withTimeout(10_000) { server.takeRequest() }
        assertEquals("DELETE", deleteRequest.method)
        assertEquals("/api/chat/conversations/$CONVERSATION_ID/messages/m2", deleteRequest.url.encodedPath)
    }

    /**
     * The server's 409 guard against deleting mid-run — F06-R2's second
     * criterion. The message must not vanish and reappear; it must never have
     * moved, because nothing is removed until the request succeeds.
     */
    @Test
    fun `a 409 on delete shows the server's message and removes nothing`() = threadTest {
        conversation()
        server.enqueue(
            MockResponse.Builder()
                .code(409)
                .body("""{"error": "Cannot delete a message while a run is active"}""")
                .build(),
        )
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.requestDelete(loaded.message("m2"))
        viewModel.confirmDelete()

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals("Cannot delete a message while a run is active", state.actionError)
        assertEquals(4, state.thread.messages.size)
        assertTrue(state.thread.messages.any { it.id == "m2" })
    }

    /** The ViewModel's own guard — the menu is the first one, this is the second (F06-R2's third criterion). */
    @Test
    fun `requestDelete is refused while a run is active, so confirming does nothing`() = threadTest {
        conversation()
        transport.payloads = listOf("""{"type": "run_started", "run_id": "run-1"}""")
        transport.stayOpen = true
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("another turn")
        viewModel.send()
        val running = viewModel.awaitState { it.runActive }

        viewModel.requestDelete(running.message("m2"))

        // No confirm was opened, so nothing to confirm — and no DELETE request follows.
        assertNull(viewModel.state.value.let { (it as ThreadUiState.Loaded).pendingDelete })
        val requestsBefore = server.requestCount
        viewModel.confirmDelete()
        assertEquals(requestsBefore, server.requestCount)
    }

    @Test
    fun `cancelling the delete confirm makes no request`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        val requestsBefore = server.requestCount

        viewModel.requestDelete(loaded.message("m2"))
        viewModel.awaitState { it.pendingDelete != null }
        viewModel.cancelDelete()

        val settled = viewModel.awaitState { it.pendingDelete == null }
        assertEquals(4, settled.thread.messages.size)
        assertEquals(requestsBefore, server.requestCount)
    }

    // -- F06-R3 · edit and resend -----------------------------------------------

    /**
     * `seq >= msg.seq` is what the server deletes (`db.py:create_run_with_user_message`);
     * the message itself survives in edited form, so the count shown to the
     * user is everything **strictly after** it — three messages when editing
     * the first turn of this four-message fixture.
     */
    @Test
    fun `the discard count is every message strictly after the edited one`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.beginEdit(loaded.message("m1"))
        viewModel.onComposerChange("What is a diode?")
        viewModel.requestEditConfirm()

        val edit = viewModel.awaitState { it.pendingEdit != null }.pendingEdit!!
        assertEquals("m1", edit.message.id)
        assertEquals(3, edit.discardCount)
    }

    @Test
    fun `editing the last user turn before its reply discards exactly one message`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.beginEdit(loaded.message("m3"))
        viewModel.onComposerChange("Who patented it?")
        viewModel.requestEditConfirm()

        assertEquals(1, viewModel.awaitState { it.pendingEdit != null }.pendingEdit!!.discardCount)
    }

    /** Only a user message may be edited — the ViewModel's own guard, behind the menu's (F06-R3's fourth criterion). */
    @Test
    fun `beginEdit on an assistant message is refused`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.beginEdit(loaded.message("m2"))

        assertNull(viewModel.state.value.let { (it as ThreadUiState.Loaded).editingMessage })
    }

    @Test
    fun `editing a message discards everything after it and streams a new answer from the edit`() = threadTest {
        conversation()
        transport.payloads = listOf(
            """{"type": "run_started", "run_id": "run-2"}""",
            """{"choices":[{"index":0,"delta":{"content":"A diode is"}}]}""",
            "[DONE]",
            """{"type": "message_saved", "message_id": "m5", "seq": 2}""",
        )
        conversation("conversation_multi_turn_after_edit.json") // the refetch after the run completes
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.beginEdit(loaded.message("m1"))
        viewModel.onComposerChange("What is a diode?")
        viewModel.requestEditConfirm()
        viewModel.awaitState { it.pendingEdit != null }
        viewModel.confirmEdit()

        // Truncated locally before the first frame even lands — no stale
        // m2/m3/m4 shown underneath the new streaming answer.
        val truncated = viewModel.awaitState { it.thread.streaming?.userMessage != null }
        assertTrue(truncated.thread.messages.isEmpty())
        assertEquals("What is a diode?", truncated.thread.streaming?.userMessage?.content)
        assertNull(truncated.editingMessage)

        val settled = viewModel.awaitState { it.thread.streaming == null }
        assertEquals(2, settled.thread.messages.size)
        assertEquals("What is a diode?", settled.thread.messages[0].content)
        assertEquals(MessageRole.ASSISTANT, settled.thread.messages[1].role)

        // `editAndResend` is the stream transport, not a plain JSON call — see
        // `ChatRepositoryTest` for the PUT method/path assertion against a real
        // request; what belongs here is that this ViewModel actually invoked it
        // for the edited message, not `send`.
        val putRequest = transport.requests.last()
        assertEquals("PUT", putRequest.method)
        assertEquals("/api/chat/conversations/$CONVERSATION_ID/messages/m1", putRequest.path)
    }

    /**
     * The truncation in [ThreadViewModel.confirmEdit] is optimistic — applied
     * before the server has actually accepted the edit. A 409 means it
     * accepted nothing, so the rollback has to prove that by asking the
     * server again rather than trusting its own arithmetic (F06-R3's last
     * criterion).
     */
    @Test
    fun `a 409 on edit leaves the thread intact, verified by refetch`() = threadTest {
        conversation()
        transport.failWith = ApiException(
            AppError.Http(409, "A run is already active for this conversation", fromServer = true),
        )
        conversation() // the refetch confirmEdit's early-failure path issues to undo the local truncation
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.beginEdit(loaded.message("m1"))
        viewModel.onComposerChange("What is a diode?")
        viewModel.requestEditConfirm()
        viewModel.awaitState { it.pendingEdit != null }
        viewModel.confirmEdit()

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals(4, state.thread.messages.size)
        assertTrue(state.thread.messages.any { it.id == "m1" && it.content == "What is a transistor?" })
        assertTrue(state.thread.messages.any { it.id == "m2" })
        assertTrue(state.thread.messages.any { it.id == "m3" })
        assertTrue(state.thread.messages.any { it.id == "m4" })
        assertNull(state.thread.streaming)
        assertFalse(state.runActive)
    }

    @Test
    fun `cancelling the edit confirm leaves the thread byte-identical and sends no request`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        val requestsBefore = server.requestCount

        viewModel.beginEdit(loaded.message("m1"))
        viewModel.onComposerChange("What is a diode?")
        viewModel.requestEditConfirm()
        viewModel.awaitState { it.pendingEdit != null }
        viewModel.cancelEditConfirm()

        val settled = viewModel.awaitState { it.pendingEdit == null }
        assertEquals(4, settled.thread.messages.size)
        // Still in edit mode — only the confirm was dismissed.
        assertEquals("m1", settled.editingMessage?.id)
        assertEquals(requestsBefore, server.requestCount)
    }

    @Test
    fun `cancelling the edit itself restores the composer and sends no request`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("a half-written question")
        val loaded = viewModel.awaitState { it.composer == "a half-written question" }
        val requestsBefore = server.requestCount

        viewModel.beginEdit(loaded.message("m1"))
        assertEquals("What is a transistor?", viewModel.awaitState { it.editingMessage != null }.composer)

        viewModel.cancelEdit()

        val settled = viewModel.awaitState { it.editingMessage == null }
        assertEquals("a half-written question", settled.composer)
        assertEquals(4, settled.thread.messages.size)
        assertEquals(requestsBefore, server.requestCount)
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
    }
}
