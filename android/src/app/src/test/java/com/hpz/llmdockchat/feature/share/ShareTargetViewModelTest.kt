package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.nio.file.Files

/** The share-target picker's four states (F14-R2, F00-R5). */
class ShareTargetViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var viewModel: ShareTargetViewModel
    private lateinit var store: SharedDraftStore

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .build()
        val repository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        store = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        viewModel = ShareTargetViewModel(repository, store)
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun settled(): ShareTargetUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is ShareTargetUiState.Loading }
        }
    }

    @Test
    fun `starts loading, then populates from the server with the staged share`() {
        assertTrue(viewModel.state.value is ShareTargetUiState.Loading)
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "hello"))

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        assertEquals(2, state.conversations.size)
        assertEquals("hello", state.share.text)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `an empty list is the empty state, not an error`() {
        server.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded
        assertTrue(state.isEmpty)
    }

    @Test
    fun `a failing server is the failed state`() {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())

        viewModel.refresh()
        val state = settled()
        assertTrue(state is ShareTargetUiState.Failed)
        assertEquals("Docker socket unavailable", (state as ShareTargetUiState.Failed).message)
    }

    @Test
    fun `an unsupported share is carried into the loaded state, not an error`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(error = "PDFs can't be shared into a chat"))

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        assertEquals("PDFs can't be shared into a chat", state.share.error)
        assertEquals(2, state.conversations.size)
    }

    @Test
    fun `a second share while the picker is open replaces the staged content`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "first"))
        viewModel.refresh()
        settled()

        store.stage(StagedShare(text = "second"))
        val state = runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as ShareTargetUiState.Loaded).share.text == "second" } }
        } as ShareTargetUiState.Loaded
        assertEquals("second", state.share.text)
    }

    @Test
    fun `rows are in the server's order - updated_at DESC, most recent first`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        val first = state.conversations[0]
        val second = state.conversations[1]
        assertTrue(first.updatedAt!! > second.updatedAt!!)
    }
}
