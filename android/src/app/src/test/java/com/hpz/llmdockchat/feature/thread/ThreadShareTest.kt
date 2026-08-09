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
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.testing.FakeDraftStore
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.nio.file.Files
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * F14's staged-share lifecycle inside the thread: the record is read back on
 * load (force-stop survival), spent on send and on leave, and kept aligned on
 * remove — the "no ghost" rules of F14-R5.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadShareTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var servicesTransport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private lateinit var attachmentStore: SharedDraftStore
    private val store = ViewModelStore()

    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "test-main") }

    companion object {
        private const val CONVERSATION_ID = "5ebf5a99-e1d7-421d-86be-c16d1d53d166"
        private val IMAGE = listOf("data:image/jpeg;base64,AAA")
    }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
        servicesTransport = FakeSseTransport()
        drafts = FakeDraftStore()
        attachmentStore = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
        servicesStreamRepository = ServicesStreamRepository(servicesTransport)
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

    private fun conversation() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversation_completed.json")).build())
    }

    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    attachmentStore = attachmentStore,
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

    // -- staging on load ----------------------------------------------------

    @Test
    fun `load applies staged attachments for this conversation`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, IMAGE)
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertEquals(IMAGE, state.attachments)
    }

    @Test
    fun `a re-entry within the same process does not duplicate the attachments`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, IMAGE)
        val viewModel = viewModel()
        viewModel.load()
        val first = viewModel.awaitLoaded()
        assertEquals(IMAGE, first.attachments)

        // The record is still there (it survives until send/leave), so a
        // second load must not re-add what the state already holds.
        conversation()
        viewModel.load()
        val second = viewModel.awaitLoaded()
        assertEquals(IMAGE, second.attachments)
    }

    @Test
    fun `a force-stop re-stages from disk - a fresh ViewModel applies the record again`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, IMAGE)
        val first = viewModel()
        first.load()
        first.awaitLoaded()

        // Process death: the ViewModelStore is gone, the record is not.
        store.clear()
        val reborn = viewModel()
        conversation()
        reborn.load()

        val state = reborn.awaitLoaded()
        assertEquals(IMAGE, state.attachments)
    }

    @Test
    fun `shared text lands in the composer through the draft store`() = threadTest {
        conversation()
        drafts.save(CONVERSATION_ID, "**Attached file: `notes.txt`**\n\n```txt\nhello\n```")
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertTrue(state.composer.contains("notes.txt"))
        assertTrue(state.canSend)
    }

    // -- spending the record -------------------------------------------------

    @Test
    fun `send clears the staged record`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, IMAGE)
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.send()

        assertTrue(attachmentStore.attachments(CONVERSATION_ID).isEmpty())
    }

    @Test
    fun `leaving the thread clears the staged record - no ghost on the next visit`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, IMAGE)
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.leaveThread()

        assertTrue(attachmentStore.attachments(CONVERSATION_ID).isEmpty())
    }

    @Test
    fun `removing an attachment keeps the record aligned`() = threadTest {
        conversation()
        attachmentStore.saveAttachments(CONVERSATION_ID, listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"))
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        assertEquals(2, loaded.attachments.size)

        viewModel.removeAttachment(0)

        val state = viewModel.awaitLoaded()
        assertEquals(listOf("data:image/jpeg;base64,BBB"), state.attachments)
        assertEquals(listOf("data:image/jpeg;base64,BBB"), attachmentStore.attachments(CONVERSATION_ID))
    }

    @Test
    fun `a conversation with no record loads with no attachments`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()

        val state = viewModel.awaitLoaded()
        assertTrue(state.attachments.isEmpty())
    }
}
