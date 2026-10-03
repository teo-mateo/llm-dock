package com.hpz.llmdockchat.feature.conversations

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.model.ConversationSummary
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.drainMain
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.ConnectionPool
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.Executors
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** List state transitions and selection. */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ConversationListViewModelTest {

    // A real Main, not the virtual-time one in MainDispatcherRule: the undo window
    // is a delay, and a test that has to wait for it needs a clock that ticks.
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "test-main") }

    private lateinit var server: MockWebServer
    private lateinit var repository: ConversationsRepository
    private lateinit var viewModel: ConversationListViewModel

    /** HTTP methods this test has popped off the server, oldest first. */
    private val methods = mutableListOf<String>()

    /** Held so a test that fails midway cannot leave a response unwritten. */
    private var gate: GatedListResponse? = null

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            // No connection reuse: MockWebServer records a request when its
            // connection closes, so a keep-alive pool makes "what has the server
            // seen so far" a question with a lagging answer.
            .connectionPool(ConnectionPool(0, 1, TimeUnit.NANOSECONDS))
            .build()
        repository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        viewModel = ConversationListViewModel(repository)
    }

    /** Rebuilds the ViewModel with an undo window short enough to drive both orderings. */
    private fun withUndoWindow(milliseconds: Long): ConversationListViewModel =
        ConversationListViewModel(repository, milliseconds).also { viewModel = it }

    @After
    fun tearDown() {
        // Cancels an undo timer still running, so a test that leaves a window open
        // does not send a DELETE into a server that is about to close.
        viewModel.undoDelete()
        gate?.releaseList()
        gate?.releaseDelete()
        mainExecutor.drainMain()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun settled(): ConversationListUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is ConversationListUiState.Loading }
        }
    }

    private fun settledWhere(predicate: (ConversationListUiState) -> Boolean): ConversationListUiState =
        runBlocking {
            withTimeout(10_000) { viewModel.state.first(predicate) }
        }

    /** Loads the fixture list and hands back its rows. */
    private fun loadedRows(): List<ConversationSummary> {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        return (settled() as ConversationListUiState.Loaded).conversations
    }

    /** Swaps in a dispatcher that holds the next list response until the test says so. */
    private fun gateNextListResponse(body: String): GatedListResponse =
        GatedListResponse(body).also { server.dispatcher = it; gate = it }

    /**
     * Pops recorded requests until none is waiting, so a test can say what the
     * server saw. Requests already popped by an assertion are added by hand.
     */
    private fun collectRequests(timeoutMs: Long = 300): List<String> {
        while (true) {
            val request = server.takeRequest(timeoutMs, TimeUnit.MILLISECONDS) ?: break
            methods += request.method.orEmpty()
        }
        return methods
    }

    /**
     * A list response the test releases by hand, so "while a refresh is in
     * flight" is a step in the test rather than a race. MockWebServer serves each
     * request on its own thread, so waiting here holds the response without
     * holding the client. Requests after the first come off the queue, as with the
     * default dispatcher.
     */
    private class GatedListResponse(private val body: String) : Dispatcher() {
        private val queued = ConcurrentLinkedQueue<MockResponse>()
        private val seen = CountDownLatch(1)
        private val release = CountDownLatch(1)
        private val written = CountDownLatch(1)
        private val deleteSeen = CountDownLatch(1)
        private val deleteRelease = CountDownLatch(1)
        private var gating = true

        fun enqueue(response: MockResponse) {
            queued.add(response)
        }

        fun awaitListRequest() = seen.await(5, TimeUnit.SECONDS)
        fun releaseList() = release.countDown()
        fun awaitWritten() = written.await(5, TimeUnit.SECONDS)
        fun awaitDeleteRequest() = deleteSeen.await(5, TimeUnit.SECONDS)
        fun releaseDelete() = deleteRelease.countDown()

        override fun dispatch(request: RecordedRequest): MockResponse {
            if (request.method == "DELETE") {
                deleteSeen.countDown()
                deleteRelease.await()
                return queued.poll()
                    ?: MockResponse.Builder().code(500).body("""{"error": "nothing queued"}""").build()
            }
            if (gating) {
                gating = false
                seen.countDown()
                release.await()
                written.countDown()
                return MockResponse.Builder().body(body).build()
            }
            return queued.poll()
                ?: MockResponse.Builder().code(500).body("""{"error": "nothing queued"}""").build()
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
        // blank the screen over content that is already on it.
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

    // -- swiping while a refresh is in flight ---------------------------------

    @Test
    fun `a swipe during a refresh keeps the row hidden and its undo available`() {
        withUndoWindow(5_000)
        val rows = loadedRows()
        val gated = gateNextListResponse(readFixture("conversations.json"))
        viewModel.refresh()
        assertTrue(gated.awaitListRequest())

        viewModel.deleteWithUndo(rows[0])
        gated.releaseList()

        // Reachable only once the response has been applied: a response that
        // dropped the undo would clear `refreshing` and leave the row in the list.
        val state = settledWhere {
            (it as? ConversationListUiState.Loaded)?.let { s -> !s.refreshing && s.pendingUndo != null } == true
        } as ConversationListUiState.Loaded
        assertEquals(rows[0].id, state.pendingUndo?.id)
        assertFalse(state.visible.any { it.id == rows[0].id })
        // The server still lists the row; the screen is what hides it.
        assertTrue(state.conversations.any { it.id == rows[0].id })
    }

    @Test
    fun `a delete sent when the window expires is not undone by a refresh listing it`() {
        withUndoWindow(50)
        val rows = loadedRows()
        collectRequests(500)
        val gated = gateNextListResponse(readFixture("conversations.json"))
        gated.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        viewModel.refresh()
        assertTrue(gated.awaitListRequest())
        collectRequests(500)

        viewModel.deleteWithUndo(rows[0])

        // The undo window is shorter than the held response, so the DELETE is
        // already sent before the list that still contains the row arrives.
        assertEquals("DELETE", server.takeRequest(5, TimeUnit.SECONDS)?.method)
        methods += "DELETE"
        gated.releaseList()
        gated.releaseDelete()
        val state = settledWhere {
            (it as? ConversationListUiState.Loaded)?.refreshing == false
        } as ConversationListUiState.Loaded

        assertFalse(state.visible.any { it.id == rows[0].id })
        // Exactly one DELETE for the swipe: the refresh that arrived afterwards
        // does not re-arm a deletion of a row it cannot see.
        assertEquals(1, collectRequests().count { it == "DELETE" })
    }

    @Test
    fun `undo inside the window sends no delete and puts the row back`() {
        withUndoWindow(5_000)
        val rows = loadedRows()
        collectRequests(500)

        viewModel.deleteWithUndo(rows[0])
        val swiped = viewModel.state.value as ConversationListUiState.Loaded
        assertEquals(rows[0].id, swiped.pendingUndo?.id)
        assertFalse(swiped.visible.any { it.id == rows[0].id })

        viewModel.undoDelete()

        val undone = viewModel.state.value as ConversationListUiState.Loaded
        assertNull(undone.pendingUndo)
        assertTrue(undone.visible.any { it.id == rows[0].id })
        assertFalse(collectRequests(1_000).contains("DELETE"))
    }

    @Test
    fun `a failed delete after the window brings the row back with the server's message`() {
        withUndoWindow(50)
        val rows = loadedRows()
        server.enqueue(MockResponse.Builder().code(404).body("""{"error": "Conversation not found"}""").build())

        viewModel.deleteWithUndo(rows[0])

        val state = settledWhere {
            (it as? ConversationListUiState.Loaded)?.actionError != null
        } as ConversationListUiState.Loaded
        assertEquals("Conversation not found", state.actionError)
        assertNull(state.pendingUndo)
        assertTrue(state.visible.any { it.id == rows[0].id })
        assertTrue(state.pendingDeletion.isEmpty())
    }

    @Test
    fun `a refresh landing between the undo window and the delete response keeps the row out`() {
        withUndoWindow(50)
        val rows = loadedRows()
        collectRequests(500)
        val gated = gateNextListResponse(readFixture("conversations.json"))
        gated.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        viewModel.refresh()
        assertTrue(gated.awaitListRequest())
        collectRequests(500)

        viewModel.deleteWithUndo(rows[0])
        assertTrue(gated.awaitDeleteRequest())

        // The stale list lands while the DELETE is still open: the server still
        // lists the row, and nothing has told this screen it is gone yet.
        gated.releaseList()
        val midDelete = settledWhere {
            (it as? ConversationListUiState.Loaded)?.refreshing == false
        } as ConversationListUiState.Loaded
        assertFalse(midDelete.visible.any { it.id == rows[0].id })

        gated.releaseDelete()
        val done = settledWhere {
            (it as? ConversationListUiState.Loaded)?.deletedIds?.contains(rows[0].id) == true
        } as ConversationListUiState.Loaded
        assertFalse(done.visible.any { it.id == rows[0].id })
        assertTrue(done.pendingDeletion.isEmpty())
        assertEquals(1, collectRequests().count { it == "DELETE" })
    }

    @Test
    fun `a second swipe while the first delete is open does not delete the first row twice`() {
        withUndoWindow(50)
        val rows = loadedRows()
        collectRequests(500)
        val gated = gateNextListResponse(readFixture("conversations.json"))
        gated.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        gated.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())
        viewModel.refresh()
        assertTrue(gated.awaitListRequest())
        collectRequests(500)

        viewModel.deleteWithUndo(rows[0])
        assertTrue(gated.awaitDeleteRequest())

        // Swiping the next row commits the first one — whose DELETE is already
        // open — rather than sending a second one for the same conversation.
        viewModel.deleteWithUndo(rows[1])
        gated.releaseList()

        val midFlight = settledWhere {
            (it as? ConversationListUiState.Loaded)?.let { s ->
                !s.refreshing && s.pendingUndo?.id == rows[1].id
            } == true
        } as ConversationListUiState.Loaded
        assertTrue(midFlight.visible.isEmpty())

        gated.releaseDelete()
        val paths = mutableListOf<String>()
        val deadline = System.currentTimeMillis() + 5_000
        var sawSecondDelete = false
        while (!sawSecondDelete && System.currentTimeMillis() < deadline) {
            val request = server.takeRequest(200, TimeUnit.MILLISECONDS) ?: continue
            paths += "${request.method} ${request.url.encodedPath}"
            sawSecondDelete = request.method == "DELETE" && request.url.encodedPath.contains(rows[1].id)
        }
        assertTrue("the second row's own delete never arrived", sawSecondDelete)
        while (true) {
            val request = server.takeRequest(200, TimeUnit.MILLISECONDS) ?: break
            paths += "${request.method} ${request.url.encodedPath}"
        }

        assertEquals(1, paths.count { it.startsWith("DELETE") && it.contains(rows[0].id) })
        assertEquals(1, paths.count { it.startsWith("DELETE") && it.contains(rows[1].id) })
        val done = settledWhere {
            (it as? ConversationListUiState.Loaded)?.deletedIds?.contains(rows[1].id) == true
        } as ConversationListUiState.Loaded
        assertTrue(done.visible.isEmpty())
    }

    @Test
    fun `a selection made while a refresh is in flight survives the response`() {
        val rows = loadedRows()
        val gated = gateNextListResponse(readFixture("conversations.json"))
        viewModel.refresh()
        assertTrue(gated.awaitListRequest())

        viewModel.toggleSelection(rows[1].id)
        gated.releaseList()

        val state = settledWhere {
            (it as? ConversationListUiState.Loaded)?.let { s -> !s.refreshing && s.selection.isNotEmpty() } == true
        } as ConversationListUiState.Loaded
        assertEquals(setOf(rows[1].id), state.selection)
    }

    @Test
    fun `a superseded refresh response cannot overwrite the newer list`() {
        val rows = loadedRows()
        assertEquals(2, rows.size)
        collectRequests(500)
        val gated = gateNextListResponse(readFixture("conversations.json"))
        gated.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.refresh()
        assertTrue(gated.awaitListRequest())
        viewModel.refresh()

        val newer = settledWhere { it is ConversationListUiState.Loaded && it.isEmpty } as ConversationListUiState.Loaded
        assertEquals(0, newer.conversations.size)

        // The superseded response is written and had time to be applied; the
        // newer list has to be what is on screen afterwards.
        gated.releaseList()
        assertTrue(gated.awaitWritten())
        Thread.sleep(250)
        val after = viewModel.state.value as ConversationListUiState.Loaded
        assertEquals(0, after.conversations.size)
        assertEquals(2, rows.size)
    }
}
