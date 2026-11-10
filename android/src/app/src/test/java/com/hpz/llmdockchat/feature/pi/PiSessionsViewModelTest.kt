package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.data.PiSessionsRepository
import com.hpz.llmdockchat.testing.FakePiSessionDeleteRepository
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class PiSessionsViewModelTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private fun sessionFields(
        id: String,
        name: String,
        cwd: String,
        live: Boolean,
        lastSeen: Long,
        contextPercent: Double?,
        parent: String? = null,
        project: String? = null,
    ): String = """
        "session_id":"$id","instance_id":"i1","name":"$name","cwd":"$cwd",
        "model":null,"thinking_level":null,"first_seen":0,"last_seen":$lastSeen,
        "ended_at":null,"end_reason":null,"live":$live,"state":"idle",
        "context_percent":$contextPercent
        ${parent?.let { ",\"parent_session_id\":\"$it\"" } ?: ""}
        ${project?.let { ",\"project\":\"$it\"" } ?: ""}
    """.trimIndent()

    private fun snapshotJson(): String = """
        {"type":"snapshot","sessions":[
            {${sessionFields("live", "live-one", "/repo/live", true, 2000, 22.5)}},
            {${sessionFields("ended", "ended-one", "/repo/ended", false, 1000, null)}}
        ]}
    """.trimIndent()

    private fun settle(viewModel: PiSessionsViewModel): PiSessionsUiState.Loaded = runBlocking {
        withTimeout(5_000) {
            viewModel.state.first { it is PiSessionsUiState.Loaded }
        }
    } as PiSessionsUiState.Loaded

    private fun viewModel(
        repository: PiSessionsRepository,
        deletes: FakePiSessionDeleteRepository = FakePiSessionDeleteRepository(),
        undoWindowMs: Long = 0L,
    ) = PiSessionsViewModel(repository, deletes, undoWindowMs)

    @Test
    fun `starts loading`() {
        val viewModel = viewModel(PiSessionsRepository(FakeSseTransport()))
        assertTrue(viewModel.state.value is PiSessionsUiState.Loading)
    }

    @Test
    fun `loaded splits live and ended`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(snapshotJson())
        val viewModel = viewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = settle(viewModel)
        assertEquals(listOf("live"), loaded.live.map { it.key.sessionId })
        assertEquals(listOf("ended"), loaded.ended.map { it.key.sessionId })
        assertFalse(loaded.stale)
    }

    @Test
    fun `needs answer reaches the loaded state through the stream`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            snapshotJson(),
            """
                {"type":"session","session_id":"live","instance_id":"i1","name":"live-one",
                 "cwd":"/repo/live","model":null,"thinking_level":null,"first_seen":0,
                 "last_seen":2000,"ended_at":null,"end_reason":null,"live":true,
                 "state":"working","context_percent":null,
                 "prompts":[{"prompt_id":"p1","kind":"approval","title":"Approve rm?"}]}
            """.trimIndent(),
        )
        val viewModel = viewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = runBlocking {
            withTimeout(5_000) {
                viewModel.state.first { state ->
                    state is PiSessionsUiState.Loaded && state.live.single().needsAnswer
                }
            }
        } as PiSessionsUiState.Loaded
        assertEquals(listOf("live"), loaded.live.map { it.key.sessionId })
    }

    @Test
    fun `stale is passed through`() {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(failWith = RuntimeException("down")))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = viewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = settle(viewModel)
        assertTrue(loaded.stale)
        assertTrue(loaded.live.isEmpty())
        assertTrue(loaded.ended.isEmpty())
    }

    @Test
    fun `start is idempotent`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(snapshotJson())
        val viewModel = viewModel(PiSessionsRepository(transport))
        viewModel.start()
        viewModel.start()

        assertEquals(1, transport.requests.size)
    }

    private fun swipeAndSettle(
        undoWindowMs: Long,
    ): Triple<PiSessionsViewModel, PiSessionsUiState.Loaded, FakePiSessionDeleteRepository> {
        val transport = FakeSseTransport()
        transport.payloads = listOf(snapshotJson())
        val deletes = FakePiSessionDeleteRepository()
        val viewModel = viewModel(PiSessionsRepository(transport), deletes, undoWindowMs)
        viewModel.start()
        return Triple(viewModel, settle(viewModel), deletes)
    }

    @Test
    fun `a swipe hides the row before anything is sent`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 60_000L)

        viewModel.deleteWithUndo(loaded.ended.single())

        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertEquals(listOf("ended"), after.ended.map { it.key.sessionId })
        assertEquals(emptyList<String>(), after.visibleEnded.map { it.key.sessionId })
        assertEquals(listOf("live"), after.visibleLive.map { it.key.sessionId })
        assertTrue(deletes.deleted.isEmpty())
    }

    @Test
    fun `the delete is sent when the undo window closes`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 0L)

        viewModel.deleteWithUndo(loaded.ended.single())

        assertEquals(listOf("ended"), deletes.deleted.map { it.sessionId })
        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertNull(after.pendingUndo)
    }

    @Test
    fun `undo inside the window sends nothing and brings the row back`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 60_000L)
        viewModel.deleteWithUndo(loaded.ended.single())

        viewModel.undoDelete()

        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertTrue(deletes.deleted.isEmpty())
        assertNull(after.pendingUndo)
        assertEquals(listOf("ended"), after.visibleEnded.map { it.key.sessionId })
    }

    @Test
    fun `a second swipe commits the first`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 60_000L)

        viewModel.deleteWithUndo(loaded.ended.single())
        viewModel.deleteWithUndo(loaded.live.single())

        assertEquals(listOf("ended"), deletes.deleted.map { it.sessionId })
        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertEquals("live", after.pendingUndo?.key?.sessionId)
    }

    @Test
    fun `a failed delete brings the row back and names the failure`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 0L)
        deletes.failure = ApiException(AppError.Http(500, "The server failed to handle this request (HTTP 500).", false))

        viewModel.deleteWithUndo(loaded.ended.single())

        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertEquals(listOf("ended"), after.visibleEnded.map { it.key.sessionId })
        assertEquals("The server failed to handle this request (HTTP 500).", after.actionError)
    }

    @Test
    fun `a running session refuses with its own message`() {
        val (viewModel, loaded, deletes) = swipeAndSettle(undoWindowMs = 0L)
        deletes.failure = ApiException(AppError.Http(409, "pi_session_live", true))

        viewModel.deleteWithUndo(loaded.live.single())

        val after = viewModel.state.value as PiSessionsUiState.Loaded
        assertEquals("A running session can't be deleted.", after.actionError)
        assertEquals(listOf("live"), after.visibleLive.map { it.key.sessionId })
    }

    @Test
    fun `a live subagent run nests under its ended parent`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """
                {"type":"snapshot","sessions":[
                    {${sessionFields("root", "root", "/repo", false, 1000, null, project = "repo/one")}},
                    {${sessionFields("run", "run", "/repo", true, 2000, null, parent = "root", project = "repo/one")}}
                ]}
            """.trimIndent(),
        )
        val viewModel = viewModel(PiSessionsRepository(transport))
        viewModel.start()

        val loaded = settle(viewModel)
        assertTrue(loaded.tree.live.isEmpty())
        val group = loaded.tree.ended.single()
        assertEquals("repo/one", group.project)
        assertEquals("root", group.roots.single().session.key.sessionId)
        assertEquals(listOf("run"), group.roots.single().children.map { it.key.sessionId })
    }

    @Test
    fun `swiping a parent promotes its children until the undo window closes`() {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """
                {"type":"snapshot","sessions":[
                    {${sessionFields("root", "root", "/repo", true, 1000, null, project = "repo/one")}},
                    {${sessionFields("run", "run", "/repo", true, 2000, null, parent = "root", project = "repo/one")}}
                ]}
            """.trimIndent(),
        )
        val viewModel = viewModel(PiSessionsRepository(transport), undoWindowMs = 60_000L)
        viewModel.start()
        val loaded = settle(viewModel)

        viewModel.deleteWithUndo(loaded.tree.live.single().roots.single().session)

        val after = viewModel.state.value as PiSessionsUiState.Loaded
        val roots = after.tree.live.single().roots
        assertEquals(listOf("run"), roots.map { it.session.key.sessionId })
        assertTrue(roots.single().children.isEmpty())
    }
}
