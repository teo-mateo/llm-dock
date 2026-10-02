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
import com.hpz.llmdockchat.core.prefs.EditSession
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeEditStateStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import java.nio.file.Files
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
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

/**
 * Issue #271 — the edit identity survives every reload shape: rotation-style
 * re-entry is a fresh `load()` over a live ViewModel; process restoration is a
 * new ViewModel replaying the persisted record; and a target the server
 * dropped cancels explicitly with a notice instead of stranding the edit text
 * as a new-message draft.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadEditReloadTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var editStates: FakeEditStateStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "reload-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
        drafts = FakeDraftStore()
        editStates = FakeEditStateStore()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        servicesRepository = ServicesRepository(ApiClient(client, FakeServerUrlStore(), ApiJson, Dispatchers.IO))
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

    private fun conversationReloaded() =
        server.enqueue(
            MockResponse.Builder()
                .body(readFixture("conversation_multi_turn.json").replace("F06-TEST multi turn", RELOADED_TITLE))
                .build(),
        )

    private fun viewModel(
        target: ViewModelStore = store,
        attachmentStore: SharedDraftStore? = null,
    ): ThreadViewModel = ViewModelProvider.create(
        target,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    attachmentStore = attachmentStore,
                    editStates = editStates,
                    servicesStreamRepository = servicesStreamRepository,
                    servicesRepository = servicesRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversationsRepository,
                    mcpServersRepository = mcpServersRepository,
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
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

    /** The debounced draft mirror must have landed before a process-death simulation. */
    private suspend fun awaitDraftMirror(text: String) {
        withTimeout(10_000) { while (drafts.saved[CONVERSATION_ID] != text) delay(10) }
    }

    private suspend fun ThreadViewModel.editInto(message: ChatMessage, prior: String?, text: String) {
        if (prior != null) {
            onComposerChange(prior)
            awaitState { it.composer == prior }
        }
        beginEdit(message)
        awaitState { it.editingMessage != null }
        onComposerChange(text)
        awaitState { it.composer == text }
        awaitDraftMirror(text)
    }

    /** AC1 — reload, the rotation path, keeps the open edit: mode, text, identity. */
    @Test
    fun `1 rotation reload keeps edit mode and the edited text`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)

        conversationReloaded()
        viewModel.load()

        val afterReload = viewModel.awaitState {
            it.conversation.title == RELOADED_TITLE && it.editingMessage != null && it.thread.messages.size == 4
        }
        assertEquals("m1", afterReload.editingMessage?.id)
        assertEquals(EDIT_TEXT, afterReload.composer)
        assertNull(afterReload.pendingEdit)
        assertNull(afterReload.actionError)
        assertEquals(EDIT_TEXT, drafts.saved[CONVERSATION_ID])
    }

    /** AC2 (+AC4) — after a reload, Send opens the edit/discard confirmation
     *  on the original message, and confirming updates that message in place:
     *  one PUT on its id, never an appended user turn. */
    @Test
    fun `2 send after a reload still opens the discard confirmation and updates the original message`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)

        conversationReloaded()
        viewModel.load()
        val afterReload = viewModel.awaitState {
            it.conversation.title == RELOADED_TITLE && it.editingMessage != null && it.thread.messages.size == 4
        }
        assertEquals("m1", afterReload.editingMessage?.id)
        assertEquals(EDIT_TEXT, afterReload.composer)

        transport.payloads = listOf(
            """{"type": "run_started", "run_id": "run-2"}""",
            """{"choices":[{"index":0,"delta":{"content":"A diode is"}}]}""",
            "[DONE]",
            """{"type": "message_saved", "message_id": "m5", "seq": 2}""",
        )
        conversation("conversation_multi_turn_after_edit.json")
        viewModel.requestEditConfirm()

        val edit = viewModel.awaitState { it.pendingEdit != null }.pendingEdit!!
        assertEquals("m1", edit.message.id)
        assertEquals(3, edit.discardCount)
        assertEquals(EDIT_TEXT, edit.content)
        viewModel.confirmEdit()

        withTimeout(10_000) { while (transport.requests.isEmpty()) delay(10) }
        val putRequest = transport.requests.last()
        assertEquals("PUT", putRequest.method)
        assertEquals("/api/chat/conversations/$CONVERSATION_ID/messages/m1", putRequest.path)
        assertTrue(transport.requests.none { it.method == "POST" })

        val settled = viewModel.awaitState {
            it.thread.streaming == null && it.thread.messages.size == 2
        }
        assertEquals("m1-edited", settled.thread.messages[0].id)
        assertEquals(EDIT_TEXT, settled.thread.messages[0].content)
        assertEquals(MessageRole.ASSISTANT, settled.thread.messages[1].role)
    }

    /** AC3 — Cancel after a reload restores both the pre-edit composer text
     *  and the pre-edit attachments, without touching the network, and the
     *  restored draft then survives another reload. */
    @Test
    fun `3 cancel after a reload restores the pre-edit text and attachments`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.onComposerChange(PRIOR_DRAFT)
        viewModel.addAttachment("data:image/png;base64,AAAA")
        viewModel.awaitState { it.composer == PRIOR_DRAFT && it.attachments.size == 1 }
        viewModel.beginEdit(loaded.message("m1"))
        viewModel.awaitState { it.editingMessage != null }
        viewModel.onComposerChange(EDIT_TEXT)
        viewModel.awaitState { it.composer == EDIT_TEXT }

        conversationReloaded()
        viewModel.load()
        val midReload = viewModel.awaitState {
            it.conversation.title == RELOADED_TITLE && it.editingMessage != null && it.thread.messages.size == 4
        }
        assertEquals("m1", midReload.editingMessage?.id)
        assertEquals(EDIT_TEXT, midReload.composer)
        // During an edit the composer carries the edited message's images;
        // the pre-edit picks are staged for Cancel, asserted below.
        assertEquals(emptyList<String>(), midReload.attachments)

        val requestsBeforeCancel = server.requestCount
        viewModel.cancelEdit()
        val settled = viewModel.awaitState { it.editingMessage == null }
        assertEquals(PRIOR_DRAFT, settled.composer)
        assertEquals(listOf("data:image/png;base64,AAAA"), settled.attachments)
        assertEquals(PRIOR_DRAFT, drafts.saved[CONVERSATION_ID])
        assertEquals(requestsBeforeCancel, server.requestCount)

        conversationReloaded()
        viewModel.load()
        val cancelled = viewModel.awaitState {
            it.conversation.title == RELOADED_TITLE && it.editingMessage == null
        }
        assertEquals(PRIOR_DRAFT, cancelled.composer)
        assertEquals(listOf("data:image/png;base64,AAAA"), cancelled.attachments)
    }

    @Test
    fun `4 an open edit confirmation survives a reload and rebinds with a recomputed count`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.beginEdit(loaded.message("m1"))
        viewModel.onComposerChange(EDIT_TEXT)
        viewModel.requestEditConfirm()
        assertEquals(3, viewModel.awaitState { it.pendingEdit != null }.pendingEdit!!.discardCount)

        conversation("conversation_multi_turn_after_delete.json")
        viewModel.load()

        val rebound = viewModel.awaitState { it.pendingEdit?.discardCount == 2 }
        assertEquals("m1", rebound.editingMessage?.id)
        assertNotNull(rebound.pendingEdit)
        assertEquals("m1", rebound.pendingEdit!!.message.id)
        assertNull(rebound.actionError)
    }

    @Test
    fun `5 a reload that drops the edit target cancels with a notice and restores the prior draft`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)

        conversation("conversation_multi_turn_no_m1.json")
        viewModel.load()

        val settled = viewModel.awaitState { it.actionError != null }
        assertNull(settled.editingMessage)
        assertNull(settled.pendingEdit)
        assertEquals(ThreadViewModel.EDIT_TARGET_GONE_NOTICE, settled.actionError)
        assertEquals(PRIOR_DRAFT, settled.composer)
        assertEquals(PRIOR_DRAFT, drafts.saved[CONVERSATION_ID])
        assertNull(editStates.records[CONVERSATION_ID])
    }

    @Test
    fun `6 a dropped target with no prior draft keeps the typed edit text`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.editInto(loaded.message("m1"), prior = null, text = EDIT_TEXT)

        conversation("conversation_multi_turn_no_m1.json")
        viewModel.load()

        val settled = viewModel.awaitState { it.actionError != null }
        assertNull(settled.editingMessage)
        assertEquals(EDIT_TEXT, settled.composer)
        assertEquals(EDIT_TEXT, drafts.saved[CONVERSATION_ID])
    }

    @Test
    fun `7 a message edited elsewhere stays the same original target`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)

        server.enqueue(
            MockResponse.Builder()
                .body(readFixture("conversation_multi_turn.json").replace("What is a transistor?", "What is a BJT?"))
                .build(),
        )
        viewModel.load()

        val afterReload = viewModel.awaitState { it.editingMessage?.content == "What is a BJT?" }
        assertEquals("m1", afterReload.editingMessage?.id)
        assertEquals(EDIT_TEXT, afterReload.composer)
        assertNull(afterReload.actionError)
    }

    @Test
    fun `8 process restoration re-enters edit mode with the draft mirror text`() = threadTest {
        conversation()
        val first = viewModel()
        first.load()
        val loaded = first.awaitLoaded()
        first.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)
        assertEquals(EditSession("m1", PRIOR_DRAFT), editStates.records[CONVERSATION_ID])
        store.clear()

        val restoredStore = ViewModelStore()
        conversation()
        val restored = viewModel(restoredStore)
        restored.load()

        val afterReload = restored.awaitState { it.editingMessage != null }
        assertEquals("m1", afterReload.editingMessage?.id)
        assertEquals(EDIT_TEXT, afterReload.composer)
        restored.cancelEdit()
        assertEquals(PRIOR_DRAFT, restored.awaitState { it.editingMessage == null }.composer)
        restoredStore.clear()
    }

    @Test
    fun `9 process restoration with a deleted target discards with the notice and keeps the text`() = threadTest {
        conversation()
        val first = viewModel()
        first.load()
        val loaded = first.awaitLoaded()
        first.editInto(loaded.message("m1"), PRIOR_DRAFT, EDIT_TEXT)
        store.clear()

        val restoredStore = ViewModelStore()
        conversation("conversation_multi_turn_no_m1.json")
        val restored = viewModel(restoredStore)
        restored.load()

        val settled = restored.awaitState { it.actionError != null }
        assertNull(settled.editingMessage)
        assertNull(settled.pendingEdit)
        assertEquals(ThreadViewModel.EDIT_TARGET_GONE_NOTICE, settled.actionError)
        assertEquals(PRIOR_DRAFT, settled.composer)
        assertEquals(PRIOR_DRAFT, drafts.saved[CONVERSATION_ID])
        assertNull(editStates.records[CONVERSATION_ID])
        restoredStore.clear()
    }

    @Test
    fun `10 beginEdit records the session and cancelEdit or confirmEdit clears it`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        viewModel.onComposerChange(PRIOR_DRAFT)
        viewModel.awaitState { it.composer == PRIOR_DRAFT }

        viewModel.beginEdit(loaded.message("m1"))
        viewModel.awaitState { it.editingMessage != null }
        assertEquals(EditSession("m1", PRIOR_DRAFT), editStates.records[CONVERSATION_ID])

        val requestsBefore = server.requestCount
        viewModel.cancelEdit()
        viewModel.awaitState { it.editingMessage == null }
        assertNull(editStates.records[CONVERSATION_ID])
        assertEquals(requestsBefore, server.requestCount)

        viewModel.beginEdit(loaded.message("m1"))
        assertEquals(EditSession("m1", PRIOR_DRAFT), editStates.records[CONVERSATION_ID])
        viewModel.requestEditConfirm()
        viewModel.awaitState { it.pendingEdit != null }
        conversation()
        viewModel.confirmEdit()
        assertNull(editStates.records[CONVERSATION_ID])
    }

    @Test
    fun `11 a delete confirmation survives reload while the message exists and drops silently when it does not`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()

        viewModel.requestDelete(loaded.message("m3"))
        viewModel.awaitState { it.pendingDelete != null }
        conversation("conversation_multi_turn_after_delete.json")
        viewModel.load()
        val kept = viewModel.awaitState { it.thread.messages.size == 3 }
        assertEquals("m3", kept.pendingDelete?.id)
        assertNull(kept.actionError)

        viewModel.requestDelete(kept.message("m1"))
        viewModel.awaitState { it.pendingDelete?.id == "m1" }
        conversation("conversation_multi_turn_no_m1.json")
        viewModel.load()
        val dropped = viewModel.awaitState { it.pendingDelete == null }
        assertNull(dropped.actionError)
    }

    @Test
    fun `12 an auto-send claim overrides a restored edit`() = threadTest {
        val claimStore = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        claimStore.stageForAutoSend(CONVERSATION_ID, CLAIM)
        editStates.records[CONVERSATION_ID] = EditSession("m1", PRIOR_DRAFT)
        drafts.saved[CONVERSATION_ID] = EDIT_TEXT

        conversation()
        conversation()
        val viewModel = viewModel(attachmentStore = claimStore)
        viewModel.load()

        withTimeout(10_000) {
            while (transport.requests.isEmpty()) delay(10)
        }
        val sent = transport.requests.first()
        assertEquals("POST", sent.method)
        assertTrue(sent.path.endsWith("/messages"))
        assertTrue(sent.body!!.contains(CLAIM))
        delay(300)
        val settled = viewModel.state.value as ThreadUiState.Loaded
        assertNull(settled.editingMessage)
        assertNull(editStates.records[CONVERSATION_ID])
        assertNull(claimStore.takeAutoSend(CONVERSATION_ID))
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f5072a571b"
        const val PRIOR_DRAFT = "a half-written question"
        const val EDIT_TEXT = "What is a diode?"
        const val RELOADED_TITLE = "F06-TEST reloaded"
        const val CLAIM = "Summarise https://example.com/a please"
    }
}
