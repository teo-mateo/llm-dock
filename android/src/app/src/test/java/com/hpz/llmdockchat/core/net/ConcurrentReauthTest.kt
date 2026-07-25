package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Credential
import com.hpz.llmdockchat.core.auth.CredentialReauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.testing.FakeCredentialStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * The whole F01-R6 stack over a real socket: a dead token stored, several
 * requests in flight, the dashboard rejecting every one of them.
 *
 * A dashboard restart invalidates all session tokens at once, so this is the
 * ordinary case rather than an exotic one. It must cost exactly one credential
 * exchange and no visit to Connect.
 */
class ConcurrentReauthTest {

    private lateinit var server: MockWebServer
    private val tokenStore = FakeTokenStore("totp-stale")
    private val credentials = FakeCredentialStore(Credential.Password("hunter2"))
    private val sessionState = SessionState()
    private val exchanges = AtomicInteger(0)

    private val parked = setOf(
        Thread.State.WAITING,
        Thread.State.TIMED_WAITING,
        Thread.State.BLOCKED,
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse =
                if (request.headers["Authorization"] == "Bearer totp-fresh") {
                    MockResponse.Builder().body("{}").build()
                } else {
                    MockResponse.Builder().code(401).body("""{"error": "expired"}""").build()
                }
        }
        server.start()
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `a fleet of simultaneous 401s costs one credential exchange`() {
        val inExchange = CountDownLatch(1)
        val releaseExchange = CountDownLatch(1)

        val reauthenticator = CredentialReauthenticator(
            credentials = credentials,
            sessionState = sessionState,
        ) {
            exchanges.incrementAndGet()
            inExchange.countDown()
            check(releaseExchange.await(10, TimeUnit.SECONDS)) { "the test never released it" }
            Result.success("totp-fresh")
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState, reauthenticator))
            .authenticator(SessionAuthenticator(tokenStore, sessionState, reauthenticator))
            .build()

        val callers = 8
        val codes = arrayOfNulls<Int>(callers)
        val threads = (0 until callers).map { index ->
            Thread {
                codes[index] = client
                    .newCall(Request.Builder().url(server.url("/api/chat/conversations")).build())
                    .execute()
                    .use { it.code }
            }
        }

        // The first caller's 401 opens the exchange and holds it. Every other
        // caller then arrives to find no stored token (the 401 discarded it) —
        // the exact pile-up that used to mean N sign-ins, or worse, N trips to
        // Connect.
        threads.first().start()
        assertTrue(inExchange.await(10, TimeUnit.SECONDS))
        threads.drop(1).forEach(Thread::start)
        awaitUntil("callers never queued behind the exchange") {
            threads.drop(1).all { it.state in parked }
        }

        releaseExchange.countDown()
        threads.forEach { it.join(20_000) }

        assertEquals(List(callers) { 200 }, codes.toList())
        assertEquals(1, exchanges.get())
        assertEquals("totp-fresh", tokenStore.current())
        assertFalse("nothing should have routed to Connect", sessionState.authenticationRequired.value)
    }

    private fun awaitUntil(what: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
        while (System.nanoTime() < deadline) {
            if (condition()) return
            Thread.sleep(10)
        }
        throw AssertionError(what)
    }
}
