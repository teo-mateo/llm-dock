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
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.feature.share.SharedContentReader
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** A reader with a canned answer, so the test is about the composer's states. */
private class StubReader(private val attachment: String? = null, private val block: (() -> Unit)? = null) :
    SharedContentReader {
    var imagesRead = 0

    override fun displayName(uri: String): String? = null

    override fun readInlineText(uri: String): String? = null

    override fun readImageAttachment(uri: String): String? {
        imagesRead += 1
        block?.invoke()
        return attachment
    }
}

/**
 * Importing a picked or captured image: the composer shows that the pick was
 * taken, the encoded attachment arrives when the read does, and a read that
 * fails says so in the caller's words.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadAttachmentImportTest {

    private lateinit var server: MockWebServer
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private lateinit var attachmentStore: SharedDraftStore
    private val store = ViewModelStore()

    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "test-main") }

    companion object {
        private const val CONVERSATION_ID = "5ebf5a99-e1d7-421d-86be-c16d1d53d166"
        private const val PICKED = "content://media/picker/42"
        private const val ENCODED = "data:image/jpeg;base64,AAA"
    }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        drafts = FakeDraftStore()
        attachmentStore = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(
                SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential),
            )
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), FakeSseTransport())
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        // Inert: this is not about the reasoning ladder, and a live one would consume a
        // queued response and move every takeRequest() assertion.
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

    private fun conversation() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversation_completed.json")).build())
    }

    /** The same conversation under another title, so a reload is observable in the state. */
    private fun conversationReloaded() {
        val body = readFixture("conversation_completed.json")
            .replace("Testing Specific Greeting Request", "Reloaded After The Pick")
        server.enqueue(MockResponse.Builder().body(body).build())
    }

    private fun viewModel(reader: SharedContentReader?): ThreadViewModel {
        val importer = reader?.let { AttachmentImporter(it, Dispatchers.IO) }
        return ViewModelProvider.create(
            store,
            viewModelFactory {
                initializer {
                    ThreadViewModel(
                        conversationId = CONVERSATION_ID,
                        repository = repository,
                        drafts = drafts,
                        attachmentStore = attachmentStore,
                        servicesStreamRepository = servicesStreamRepository,
                        servicesRepository = servicesRepository,
                        openRouterModelsRepository = openRouterModelsRepository,
                        conversationsRepository = conversationsRepository,
                        mcpServersRepository = mcpServersRepository,
                        promptsRepository = promptsRepository,
                        coalesceWindowMs = 0,
                        attachmentImporter = importer,
                    )
                }
            },
        )[ThreadViewModel::class]
    }

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded() =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        message: String = "condition",
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded {
        val loaded = withTimeout(10_000) {
            state.first { it is ThreadUiState.Loaded && predicate(it as ThreadUiState.Loaded) } as ThreadUiState.Loaded
        }
        assertTrue(message, predicate(loaded))
        return loaded
    }

    @Test
    fun `a picked image says it is being read, then lands in the strip`() = threadTest {
        conversation()
        // The read parks until the test releases it, so the in-between state is a fact
        // rather than a race against a fast fake.
        val reading = CountDownLatch(1)
        val release = CountDownLatch(1)
        val reader = StubReader(ENCODED, block = {
            reading.countDown()
            assertTrue("the import never resumed", release.await(5, TimeUnit.SECONDS))
        })
        val viewModel = viewModel(reader)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.importAttachment(PICKED, "That image could not be read.")

        assertTrue(reading.await(5, TimeUnit.SECONDS))
        val busy = viewModel.awaitState("the pick was never acknowledged as reading") { it.attachmentImporting }
        assertEquals(emptyList<String>(), busy.attachments)

        release.countDown()
        val done = viewModel.awaitState("the attachment never arrived") { it.attachments.isNotEmpty() }
        assertEquals(listOf(ENCODED), done.attachments)
        assertFalse(done.attachmentImporting)
        assertEquals(1, reader.imagesRead)
    }

    @Test
    fun `an image that cannot be read reports the caller's message and stops claiming to be busy`() = threadTest {
        conversation()
        val viewModel = viewModel(StubReader(attachment = null))
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.importAttachment(PICKED, "That photo could not be read.")

        val failed = viewModel.awaitState("a failed import never reported") { it.actionError != null }
        assertEquals("That photo could not be read.", failed.actionError)
        assertEquals(emptyList<String>(), failed.attachments)
        assertFalse(failed.attachmentImporting)
    }

    /**
     * The composer calls this without an importer in tests and previews; silently
     * swallowing the pick would be indistinguishable from a photo that failed to
     * arrive, so the caller's message still has to surface.
     */
    @Test
    fun `with no importer wired the pick still reports a failure`() = threadTest {
        conversation()
        val viewModel = viewModel(null)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.importAttachment(PICKED, "That image could not be read.")

        val failed = viewModel.awaitState("an unwired pick went silent") { it.actionError != null }
        assertEquals("That image could not be read.", failed.actionError)
        assertFalse(failed.attachmentImporting)
    }

    /**
     * Send snapshots the strip, so a turn started mid-import would go out without
     * the photo and leave it materialising in a composer the run has disabled.
     */
    @Test
    fun `a turn cannot be sent while a pick is still being read`() = threadTest {
        conversation()
        val release = CountDownLatch(1)
        val reader = StubReader(ENCODED, block = {
            assertTrue("the import never resumed", release.await(5, TimeUnit.SECONDS))
        })
        val viewModel = viewModel(reader)
        viewModel.load()
        viewModel.awaitLoaded()

        viewModel.importAttachment(PICKED, "That image could not be read.")
        viewModel.onComposerChange("a caption")
        val busy = viewModel.awaitState("the pick was never acknowledged as reading") { it.attachmentImporting }

        assertFalse("Send would have shipped the turn without the photo", busy.canSend)
        viewModel.send()

        release.countDown()
        val done = viewModel.awaitState("the attachment never arrived") { it.attachments.isNotEmpty() }
        assertTrue("the composer unlocks once the bytes exist", done.canSend)
    }

    /**
     * The failure path hands back a Retry button, and a reload rebuilds the screen
     * state: losing the in-flight flag there would let the camera cleanup delete a
     * file the import is still holding open.
     */
    @Test
    fun `a reload while a pick is being read keeps the pick acknowledged`() = threadTest {
        conversation()
        conversationReloaded()
        val release = CountDownLatch(1)
        val reader = StubReader(ENCODED, block = {
            assertTrue("the import never resumed", release.await(5, TimeUnit.SECONDS))
        })
        val viewModel = viewModel(reader)
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.importAttachment(PICKED, "That image could not be read.")
        viewModel.awaitState("the pick was never acknowledged as reading") { it.attachmentImporting }

        viewModel.load()
        val reloaded = withTimeout(10_000) {
            viewModel.state.first {
                it is ThreadUiState.Loaded && it.conversation.title == "Reloaded After The Pick"
            } as ThreadUiState.Loaded
        }

        assertTrue("the reload dropped the in-flight pick", reloaded.attachmentImporting)
        release.countDown()
    }
}
