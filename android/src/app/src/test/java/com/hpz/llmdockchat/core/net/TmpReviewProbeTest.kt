package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
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
 * TEMPORARY independent review probe (f00-review, narrow re-review pass).
 *
 * Safe to delete — it duplicates coverage `OkHttpSseTransportTest` already
 * owns and adds no production dependency. Deliberately kept to the one case
 * that runs fast and cannot hang.
 */
class TmpReviewProbeTest {

    private lateinit var server: MockWebServer
    private lateinit var client: OkHttpClient
    private lateinit var transport: SseTransport

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-abc"), SessionState()))
            .authenticator(
                SessionAuthenticator(
                    FakeTokenStore("totp-abc"),
                    SessionState(),
                    Reauthenticator.NoCredential,
                ),
            )
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

    private fun awaitTrue(what: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (System.nanoTime() < deadline) {
            if (condition()) return
            Thread.sleep(20)
        }
        throw AssertionError(what)
    }

    /**
     * The BUSY path. `OkHttpSseTransportTest` covers the quiet stream, where
     * the original `invokeOnCompletion` defect lived; this covers the path that
     * masked it, to confirm the `channelFlow` rewrite did not trade one for the
     * other. Cancellation must be prompt and leave nothing behind.
     */
    @Test
    fun probeBusyStreamCancellationLeavesNothingBehind() = runBlocking {
        val body = buildString { repeat(400) { append("data: busy-$it\n\n") } }
        server.enqueue(
            MockResponse.Builder()
                .setHeader("Content-Type", "text/event-stream")
                .body(body)
                .throttleBody(16, 25, TimeUnit.MILLISECONDS)
                .build(),
        )

        val t0 = System.nanoTime()
        val got = transport.open(StreamRequest("/api/x")).take(2).toList()
        val elapsedMs = (System.nanoTime() - t0) / 1_000_000

        assertEquals(listOf("busy-0", "busy-1"), got)
        awaitTrue("busy: call still running") { client.dispatcher.runningCallsCount() == 0 }
        awaitTrue("busy: connection still open") { client.connectionPool.connectionCount() == 0 }
        assertTrue("did not cancel early (${elapsedMs}ms)", elapsedMs < 3000)
    }
}
