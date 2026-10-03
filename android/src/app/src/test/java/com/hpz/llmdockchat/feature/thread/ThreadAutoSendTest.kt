package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
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
 * The other half: the thread a summarize tap opened sends its one claim
 * on opening — once, ever — and a send that never reached the server puts the
 * prepared turn back where the user can tap Send themselves.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadAutoSendTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var claimStore: SharedDraftStore
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
        claimStore = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    /** Over-queued on purpose: a run that ends without a frame refetches the thread. */
    private fun conversation() {
        repeat(4) {
            server.enqueue(MockResponse.Builder().body(readFixture("conversation_completed.json")).build())
        }
    }

    private fun viewModel(): ThreadViewModel {
        val client = OkHttpClient.Builder().build()
        val api = ApiClient(client, FakeServerUrlStore(), ApiJson, Dispatchers.IO)
        return ViewModelProvider.create(
            store,
            viewModelFactory {
                initializer {
                    ThreadViewModel(
                        conversationId = CONVERSATION_ID,
                        repository = repository,
                        drafts = drafts,
                        attachmentStore = claimStore,
                        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport()),
                        servicesRepository = ServicesRepository(api),
                        openRouterModelsRepository = OpenRouterModelsRepository(api),
                        conversationsRepository = ConversationsRepository(api),
                        mcpServersRepository = McpServersRepository(api),
                        promptsRepository = PromptsRepository(api),
                        coalesceWindowMs = 0,
                    )
                }
            },
        )[ThreadViewModel::class]
    }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun awaitSend(): Int {
        withTimeout(10_000) {
            while (transport.requests.isEmpty()) delay(10)
        }
        // The POST is the stream; let the run settle before reading it back.
        delay(200)
        return transport.requests.size
    }

    @Test
    fun `a filed claim sends one turn when the thread opens`() = runBlocking {
        conversation()
        claimStore.stageForAutoSend(CONVERSATION_ID, CLAIM)

        viewModel().apply { load() }.awaitLoaded()

        assertEquals(1, awaitSend())
        val sent = transport.requests.first()
        assertTrue(sent.path.endsWith("/messages"))
        assertTrue(sent.body!!.contains("example.com/a"))
    }

    @Test
    fun `the claim is spent - reopening the thread sends nothing more`() = runBlocking {
        conversation()
        claimStore.stageForAutoSend(CONVERSATION_ID, CLAIM)
        val first = viewModel()
        first.load()
        first.awaitLoaded()
        assertEquals(1, awaitSend())

        store.clear()
        conversation()
        val again = viewModel()
        again.load()
        again.awaitLoaded()
        delay(300)

        assertEquals(1, transport.requests.size)
    }

    /** A send that never got a frame hands the text back to the user. */
    @Test
    fun `an early failure restores the prepared turn to the composer`() = runBlocking {
        conversation()
        transport.failWith = java.io.IOException("offline")
        claimStore.stageForAutoSend(CONVERSATION_ID, CLAIM)
        val viewModel = viewModel()

        viewModel.load()
        val state = withTimeout(10_000) {
            viewModel.state.first { (it as? ThreadUiState.Loaded)?.composer?.contains("example.com/a") == true }
        } as ThreadUiState.Loaded

        assertTrue(state.canSend)
        assertEquals(CLAIM, drafts.saved[CONVERSATION_ID])
    }

    /** Ordinary threads are untouched: no claim, no send. */
    @Test
    fun `a thread with no claim loads with nothing sent`() = runBlocking {
        conversation()

        viewModel().apply { load() }.awaitLoaded()
        delay(300)

        assertEquals(0, transport.requests.size)
    }

    private companion object {
        const val CONVERSATION_ID = "5ebf5a99-e1d7-421d-86be-c16d1d53d166"
        const val CLAIM = "Summarise this page.\n\nhttps://example.com/a\n\nUse the available URL-fetching tool."
    }
}
