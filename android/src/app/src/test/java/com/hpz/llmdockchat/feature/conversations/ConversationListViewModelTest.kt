package com.hpz.llmdockchat.feature.conversations

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

/** List state transitions (F00-R5, F02-R1) and selection (F02-R5). */
class ConversationListViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var viewModel: ConversationListViewModel

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
        viewModel = ConversationListViewModel(repository)
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun settled(): ConversationListUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is ConversationListUiState.Loading }
        }
    }

    @Test
    fun `starts loading, then populates from the server`() {
        assertTrue(viewModel.state.value is ConversationListUiState.Loading)
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())

        viewModel.refresh()
        val state = settled() as ConversationListUiState.Loaded
        assertEquals(2, state.conversations.size)
        assertFalse(state.isEmpty)
        assertFalse(state.refreshing)
    }

    @Test
    fun `an empty conversations array is the empty state, not an error`() {
        server.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.refresh()
        val state = settled() as ConversationListUiState.Loaded
        assertTrue(state.isEmpty)
    }

    @Test
    fun `a failing server is the failed state, not a stuck spinner`() {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())

        viewModel.refresh()
        val state = settled()
        assertTrue(state is ConversationListUiState.Failed)
        assertEquals("Docker socket unavailable", (state as ConversationListUiState.Failed).message)
    }

    @Test
    fun `refreshing already-loaded content does not fall back to the full loading state`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        settled()

        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()

        // The very next state after kicking off a refresh from Loaded must
        // still be Loaded (with refreshing=true) — never Loading, which would
        // blank the screen over content that is already on it (F02-R1).
        assertTrue(viewModel.state.value is ConversationListUiState.Loaded)
        assertTrue((viewModel.state.value as ConversationListUiState.Loaded).refreshing)
    }

    @Test
    fun `long-press enters selection, tapping another row extends it, clearing exits it`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val loaded = settled() as ConversationListUiState.Loaded
        val ids = loaded.conversations.map { it.id }

        viewModel.enterSelection(ids[0])
        var state = viewModel.state.value as ConversationListUiState.Loaded
        assertTrue(state.selectionMode)
        assertEquals(setOf(ids[0]), state.selection)

        viewModel.toggleSelection(ids[1])
        state = viewModel.state.value as ConversationListUiState.Loaded
        assertEquals(setOf(ids[0], ids[1]), state.selection)

        viewModel.toggleSelection(ids[0])
        state = viewModel.state.value as ConversationListUiState.Loaded
        assertEquals(setOf(ids[1]), state.selection)

        viewModel.clearSelection()
        state = viewModel.state.value as ConversationListUiState.Loaded
        assertFalse(state.selectionMode)
        assertTrue(state.selection.isEmpty())
    }

    @Test
    fun `deleting one conversation calls the server and refreshes`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val ids = (settled() as ConversationListUiState.Loaded).conversations.map { it.id }

        server.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        server.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.delete(ids[0])
        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { it is ConversationListUiState.Loaded && it.isEmpty }
            }
        }
        assertTrue((finalState as ConversationListUiState.Loaded).isEmpty)

        server.takeRequest() // the initial GET
        assertEquals("DELETE", server.takeRequest().method)
        assertEquals("GET", server.takeRequest().method)
    }

    @Test
    fun `deleteSelected batches the current selection and clears it on success`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val ids = (settled() as ConversationListUiState.Loaded).conversations.map { it.id }
        viewModel.enterSelection(ids[0])
        viewModel.toggleSelection(ids[1])

        server.enqueue(MockResponse.Builder().body("""{"ok": true, "deleted": 2}""").build())
        server.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.deleteSelected()
        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { it is ConversationListUiState.Loaded && it.isEmpty }
            }
        }
        assertTrue((finalState as ConversationListUiState.Loaded).selection.isEmpty())

        server.takeRequest() // the initial GET
        val batch = server.takeRequest()
        assertEquals("POST", batch.method)
        assertEquals("/api/chat/conversations/delete", batch.url.encodedPath)
    }

    @Test
    fun `a failed delete surfaces the server's message instead of silently doing nothing`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val ids = (settled() as ConversationListUiState.Loaded).conversations.map { it.id }

        server.enqueue(MockResponse.Builder().code(404).body("""{"error": "Conversation not found"}""").build())

        viewModel.delete(ids[0])
        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { (it as? ConversationListUiState.Loaded)?.actionError != null }
            }
        }
        assertEquals("Conversation not found", (finalState as ConversationListUiState.Loaded).actionError)
        // The row was not optimistically removed on a failure.
        assertEquals(2, finalState.conversations.size)
    }
}
