package com.hpz.llmdockchat.core.net

import app.cash.turbine.test
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockResponseBody
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import okio.BufferedSink
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.time.Duration.Companion.seconds

class OkHttpSseTransportTest {

    private lateinit var server: MockWebServer
    private lateinit var tokenStore: FakeTokenStore
    private lateinit var sessionState: SessionState
    private lateinit var transport: SseTransport
    private lateinit var client: OkHttpClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        tokenStore = FakeTokenStore("totp-abc")
        sessionState = SessionState()
        client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState))
            .authenticator(SessionAuthenticator(tokenStore, sessionState, Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        transport = OkHttpSseTransport(
            client = client,
            serverUrlStore = FakeServerUrlStore(
                (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
            ),
            ioDispatcher = Dispatchers.IO,
        )
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun sse(body: String, builder: MockResponse.Builder.() -> Unit = {}) =
        server.enqueue(
            MockResponse.Builder()
                .setHeader("Content-Type", "text/event-stream")
                .body(body)
                .apply(builder)
                .build(),
        )

    @Test
    fun `payloads are emitted verbatim and in order`() = runTest {
        sse(
            buildString {
                append("data: {\"type\": \"run_started\", \"run_id\": \"r1\"}\n\n")
                append("data: {\"choices\":[{\"delta\":{\"content\":\"Hel\"}}]}\n\n")
                append("data: [DONE]\n\n")
                append("data: {\"type\": \"message_saved\", \"message_id\": 12}\n\n")
                append("data: {\"type\": \"conversation_updated\", \"id\": \"c1\"}\n\n")
            },
        )

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 10.seconds) {
            assertEquals("""{"type": "run_started", "run_id": "r1"}""", awaitItem())
            assertEquals("""{"choices":[{"delta":{"content":"Hel"}}]}""", awaitItem())
            assertEquals("[DONE]", awaitItem())
            assertEquals("""{"type": "message_saved", "message_id": 12}""", awaitItem())
            assertEquals("""{"type": "conversation_updated", "id": "c1"}""", awaitItem())
            awaitComplete()
        }

        assertEquals("Bearer totp-abc", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `a frame split across socket reads is reassembled`() = runTest {
        val body = buildString {
            append("data: {\"type\": \"heartbeat\", \"elapsed_s\": 30.0}\n\n")
            append("data: {\"type\": \"log\", \"line\": \"a fairly long log line to force splitting\"}\n\n")
        }
        // 8 bytes per period guarantees every frame spans several reads.
        sse(body) { throttleBody(8, 15, TimeUnit.MILLISECONDS) }

        transport.open(StreamRequest("/api/services/x/logs/stream")).test(timeout = 30.seconds) {
            assertEquals("""{"type": "heartbeat", "elapsed_s": 30.0}""", awaitItem())
            assertEquals("""{"type": "log", "line": "a fairly long log line to force splitting"}""", awaitItem())
            awaitComplete()
        }
    }

    @Test
    fun `colon keepalives pass through without producing an event`() = runTest {
        sse(": keepalive\n\n: keepalive\n\ndata: {\"type\": \"snapshot_end\"}\n\n: keepalive\n\n")

        transport.open(StreamRequest("/api/services/stream")).test(timeout = 10.seconds) {
            assertEquals("""{"type": "snapshot_end"}""", awaitItem())
            awaitComplete()
        }
    }

    @Test
    fun `a stream that ends without a terminal frame completes rather than failing`() = runTest {
        sse("data: {\"type\": \"delta\"}\n\ndata: {\"type\": \"delta\"}\n\n")

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 10.seconds) {
            awaitItem()
            awaitItem()
            awaitComplete()
        }
    }

    @Test
    fun `a trailing half-frame is dropped, not emitted`() = runTest {
        sse("data: {\"type\": \"delta\"}\n\ndata: {\"type\": \"trun")

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 10.seconds) {
            assertEquals("""{"type": "delta"}""", awaitItem())
            awaitComplete()
        }
    }

    @Test
    fun `a failed open surfaces the server's message`() = runTest {
        server.enqueue(
            MockResponse.Builder()
                .code(404)
                .body("""{"error": "Service has not been created yet"}""")
                .build(),
        )

        transport.open(StreamRequest("/api/services/nope/logs/stream")).test(timeout = 10.seconds) {
            val error = (awaitError() as ApiException).error
            error as AppError.Http
            assertEquals(404, error.status)
            assertEquals("Service has not been created yet", error.message)
            assertTrue(error.fromServer)
        }
    }

    @Test
    fun `a 401 on open is an auth failure`() = runTest {
        server.enqueue(
            MockResponse.Builder().code(401).body("""{"error": "TOTP session expired"}""").build(),
        )

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 10.seconds) {
            assertEquals(AppError.Unauthenticated, (awaitError() as ApiException).error)
        }
        assertTrue(sessionState.authenticationRequired.value)
    }

    @Test
    fun `an unreachable server fails with a network error`() = runTest {
        server.close()

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 10.seconds) {
            assertTrue((awaitError() as ApiException).error is AppError.Network)
        }
    }

    /**
     * The distinguishing test: every other assertion here would also pass
     * against an implementation that buffered the whole body and split it on
     * blank lines. This one cannot — the response body physically cannot
     * finish until the collector has already received the first frame and
     * released the gate.
     */
    @Test
    fun `a frame is delivered while the response body is still open`() = runTest {
        val gate = CountDownLatch(1)
        val bodyFinished = CountDownLatch(1)
        val first = "data: {\"type\": \"run_started\", \"run_id\": \"r1\"}\n\n"
        val rest = "data: {\"type\": \"message_saved\", \"message_id\": 12}\n\n"

        server.enqueue(
            MockResponse.Builder()
                .setHeader("Content-Type", "text/event-stream")
                .body(GatedBody(first, rest, gate, bodyFinished))
                .build(),
        )

        transport.open(StreamRequest("/api/chat/runs/r1/stream")).test(timeout = 20.seconds) {
            assertEquals("""{"type": "run_started", "run_id": "r1"}""", awaitItem())
            assertEquals("the body was already complete", 1L, gate.count)
            assertEquals("the server had already written everything", 1L, bodyFinished.count)

            gate.countDown()

            assertEquals("""{"type": "message_saved", "message_id": 12}""", awaitItem())
            awaitComplete()
        }
    }

    /**
     * Navigating away from a screen cancels its collection. A chat run that has
     * gone quiet is the case that bites: the reader is parked inside a blocking
     * socket read, so cancellation is only noticed if the call is explicitly
     * cancelled. Leak it and every entry into a thread or a log view strands a
     * socket that the server keeps streaming into.
     */
    @Test
    fun `abandoning a quiet stream cancels the call and leaves no connection behind`() = runTest {
        val goesQuiet = CountDownLatch(1)
        val delivered = "data: {\"i\": 1}\n\n" + "data: {\"i\": 2}\n\n"
        val neverSeen = "data: {\"i\": 3}\n\n"
        server.enqueue(
            MockResponse.Builder()
                .setHeader("Content-Type", "text/event-stream")
                .body(GatedBody(delivered, neverSeen, goesQuiet, CountDownLatch(1)))
                .build(),
        )

        try {
            val received = transport.open(StreamRequest("/api/chat/runs/r1/stream")).take(2).toList()

            assertEquals(listOf("""{"i": 1}""", """{"i": 2}"""), received)
            awaitTrue("the call is still running") { client.dispatcher.runningCallsCount() == 0 }
            // A body that was not read to the end cannot be pooled, so a
            // cancelled stream must leave the pool empty rather than parked.
            awaitTrue("the connection is still open") { client.connectionPool.connectionCount() == 0 }
        } finally {
            goesQuiet.countDown()
        }
    }

    private fun awaitTrue(what: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (System.nanoTime() < deadline) {
            if (condition()) return
            Thread.sleep(20)
        }
        throw AssertionError(what)
    }

    private class GatedBody(
        private val first: String,
        private val rest: String,
        private val gate: CountDownLatch,
        private val finished: CountDownLatch,
    ) : MockResponseBody {

        override val contentLength: Long = (first.length + rest.length).toLong()

        override fun writeTo(sink: BufferedSink) {
            sink.writeUtf8(first)
            sink.flush()
            if (!gate.await(20, TimeUnit.SECONDS)) return
            sink.writeUtf8(rest)
            sink.flush()
            finished.countDown()
        }
    }
}
