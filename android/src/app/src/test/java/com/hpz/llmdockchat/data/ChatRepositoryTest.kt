package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.OkHttpSseTransport
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/**
 * The three run-producing endpoints through the real transport (F04).
 *
 * The fixtures are dashboard recordings, replayed byte for byte — including the
 * throttled case, which forces every frame to span several socket reads.
 */
class ChatRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: ChatRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(
            api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO),
            transport = OkHttpSseTransport(client, urlStore, Dispatchers.IO),
        )
    }

    @After
    fun tearDown() = server.close()

    private fun sse(fixture: String, builder: MockResponse.Builder.() -> Unit = {}) = server.enqueue(
        MockResponse.Builder()
            .setHeader("Content-Type", "text/event-stream")
            .body(readFixture("sse/$fixture"))
            .apply(builder)
            .build(),
    )

    // -- load ----------------------------------------------------------------

    @Test
    fun `a recorded conversation maps to messages, model and last run`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversation_completed.json")).build())

        val conversation = repository.load("c1").getOrThrow()

        assertEquals("Testing Specific Greeting Request", conversation.title)
        assertEquals(ModelRef.Local("llamacpp-gemma-4-26b-a4b-it-q8"), conversation.modelRef)
        assertEquals(2, conversation.messages.size)
        assertEquals(MessageRole.USER, conversation.messages[0].role)
        assertEquals("hello there", conversation.messages[1].content)
        assertTrue(conversation.messages[1].reasoning!!.isNotBlank())
        assertEquals("completed", conversation.lastRun?.status)
        assertEquals(false, conversation.lastRun?.hasFailed)
    }

    /**
     * A run that failed before producing any text saves no assistant message —
     * the error lives on `last_run`, which is the only place the app can find
     * it after reopening the thread (F04-R8's third criterion).
     */
    @Test
    fun `a failed run's error survives on last_run with no assistant message`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversation_failed_run.json")).build())

        val conversation = repository.load("c1").getOrThrow()

        assertEquals(1, conversation.messages.size)
        assertEquals(MessageRole.USER, conversation.messages.single().role)
        assertEquals(true, conversation.lastRun?.hasFailed)
        assertEquals(
            "Service 'llamacpp-f04-test-missing' is not reachable. Is it running?",
            conversation.lastRun?.error,
        )
    }

    @Test
    fun `persisted tool calls carry rendered arguments and their result`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversation_tool_calls.json")).build())

        val call = repository.load("c1").getOrThrow().messages.last().toolCalls.single()

        assertEquals("differentiate", call.name)
        assertEquals("sympy-math", call.serverId)
        assertTrue(call.arguments.contains("x**3 * sin(x)"))
        assertEquals("x**3*cos(x) + 3*x**2*sin(x)", call.result)
        assertEquals(false, call.isRunning)
    }

    // -- send ----------------------------------------------------------------

    @Test
    fun `send posts content to the conversation's messages path`() = runTest {
        sse("send-simple.sse")

        repository.send("c1", "Reply with exactly: hello there").toList()

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/chat/conversations/c1/messages", request.url.encodedPath)
        assertEquals("""{"content":"Reply with exactly: hello there"}""", request.body?.utf8())
    }

    @Test
    fun `images are sent only when there are some`() = runTest {
        sse("send-simple.sse")
        repository.send("c1", "look", listOf("data:image/jpeg;base64,AAAA")).toList()
        assertEquals(
            """{"content":"look","images":["data:image/jpeg;base64,AAAA"]}""",
            server.takeRequest().body?.utf8(),
        )
    }

    @Test
    fun `a whole recorded turn arrives as run started, deltas, done, saved`() = runTest {
        sse("send-simple.sse")

        val events = repository.send("c1", "hi").toList()

        assertTrue(events.first() is RunEvent.RunStarted)
        assertEquals("hello there", events.filterIsInstance<RunEvent.Delta>().joinToString("") { it.content })
        assertTrue(events.any { it == RunEvent.Done })
        assertTrue(events.any { it is RunEvent.MessageSaved })
        assertTrue(events.none { it is RunEvent.Unknown })
    }

    /**
     * Every frame here spans several socket reads. The transport reassembles
     * them (F00), so the parser sees whole payloads and the event sequence is
     * byte-for-byte the same as the unthrottled case.
     */
    @Test
    fun `frames split across socket reads produce the same events`() = runTest {
        sse("send-toolcall.sse") { throttleBody(16, 5, TimeUnit.MILLISECONDS) }

        val events = repository.send("c1", "differentiate x**3 sin x").toList()

        assertEquals(1, events.filterIsInstance<RunEvent.ToolCallPending>().size)
        assertEquals(1, events.filterIsInstance<RunEvent.ToolCall>().size)
        assertEquals(1, events.filterIsInstance<RunEvent.ToolResult>().size)
        assertTrue(events.none { it is RunEvent.Unknown })
    }

    /**
     * The POST *is* the stream, so a second send while a run is active fails
     * the flow before a single frame — which is how the ViewModel knows to drop
     * the optimistic user message rather than leave a phantom (F04-R2).
     */
    @Test
    fun `a concurrent send fails the stream with the server's 409 message`() = runTest {
        server.enqueue(
            MockResponse.Builder()
                .code(409)
                .body("""{"error": "A run is already active for this conversation"}""")
                .build(),
        )

        val failure = runCatching { repository.send("c1", "again").toList() }.exceptionOrNull()

        val http = (failure as ApiException).error as AppError.Http
        assertEquals(409, http.status)
        assertEquals("A run is already active for this conversation", http.message)
        assertTrue(http.fromServer)
    }

    @Test
    fun `a cancelled run's stream simply ends, with no terminal frame`() = runTest {
        sse("send-cancel.sse")

        val events = repository.send("c1", "write an essay").toList()

        assertTrue(events.last() is RunEvent.Delta)
        assertTrue(events.none { it == RunEvent.Done })
        assertTrue(events.none { it is RunEvent.MessageSaved })
    }

    @Test
    fun `a failed run streams a bare error frame`() = runTest {
        sse("send-failure.sse")

        val events = repository.send("c1", "hello").toList()

        assertEquals(
            "Service 'llamacpp-f04-test-missing' is not reachable. Is it running?",
            events.filterIsInstance<RunEvent.Failed>().single().message,
        )
    }

    // -- edit and reattach: the same reader ----------------------------------

    @Test
    fun `edit and resend PUTs to the message path and streams the same frames`() = runTest {
        sse("send-simple.sse")

        val events = repository.editAndResend("c1", "m1", "fixed").toList()

        val request = server.takeRequest()
        assertEquals("PUT", request.method)
        assertEquals("/api/chat/conversations/c1/messages/m1", request.url.encodedPath)
        assertTrue(events.any { it is RunEvent.MessageSaved })
    }

    @Test
    fun `reattach GETs the run stream and replays before the live tail`() = runTest {
        sse("reattach-replay.sse")

        val events = repository.reattach("r1").toList()

        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/chat/runs/r1/stream", request.url.encodedPath)
        assertTrue(events.first() is RunEvent.RunStarted)
        assertTrue(events.filterIsInstance<RunEvent.Delta>().first().reasoning.length > 200)
    }

    // -- delete (F06) ----------------------------------------------------------

    @Test
    fun `delete DELETEs the message path`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())

        repository.deleteMessage("c1", "m2").getOrThrow()

        val request = server.takeRequest()
        assertEquals("DELETE", request.method)
        assertEquals("/api/chat/conversations/c1/messages/m2", request.url.encodedPath)
    }

    /** The server refuses a delete while a run is active in that conversation. */
    @Test
    fun `a 409 on delete fails with the server's message`() = runTest {
        server.enqueue(
            MockResponse.Builder()
                .code(409)
                .body("""{"error": "Cannot delete a message while a run is active"}""")
                .build(),
        )

        val failure = repository.deleteMessage("c1", "m2").exceptionOrNull()

        val http = (failure as ApiException).error as AppError.Http
        assertEquals(409, http.status)
        assertEquals("Cannot delete a message while a run is active", http.message)
    }

    // -- cancel --------------------------------------------------------------

    @Test
    fun `stop cancels by conversation and guards with the run id`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"run": {"id": "r1", "status": "cancelled"}}""").build())

        repository.cancelActiveRun("c1", "r1").getOrThrow()

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/chat/conversations/c1/cancel-active-run", request.url.encodedPath)
        assertEquals("""{"expected_run_id":"r1"}""", request.body?.utf8())
    }

    /** Stopping a run that already finished is a 200 no-op, not an error (F04-R6). */
    @Test
    fun `cancelling a finished run succeeds with a null run`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"run": null}""").build())

        assertTrue(repository.cancelActiveRun("c1", "r1").isSuccess)
    }

    @Test
    fun `an early Stop with no run id yet omits the guard`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"run": null}""").build())

        repository.cancelActiveRun("c1", null).getOrThrow()

        assertEquals("{}", server.takeRequest().body?.utf8())
    }
}
