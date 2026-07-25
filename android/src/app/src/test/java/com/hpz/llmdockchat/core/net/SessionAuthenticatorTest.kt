package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.testing.FakeTokenStore
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SessionAuthenticatorTest {

    private lateinit var server: MockWebServer
    private lateinit var tokenStore: FakeTokenStore
    private lateinit var sessionState: SessionState

    private val unauthorized = MockResponse.Builder()
        .code(401)
        .body("""{"error": "TOTP session expired"}""")
        .build()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        tokenStore = FakeTokenStore("totp-stale")
        sessionState = SessionState()
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun clientWith(reauthenticator: Reauthenticator) = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor(tokenStore, sessionState))
        .authenticator(SessionAuthenticator(tokenStore, sessionState, reauthenticator))
        .build()

    private fun OkHttpClient.get(path: String): Int =
        newCall(Request.Builder().url(server.url(path)).build()).execute().use { it.code }

    @Test
    fun `a 401 with no credential discards the token and raises the signal`() {
        server.enqueue(unauthorized)
        val code = clientWith(Reauthenticator.NoCredential).get("/api/chat/conversations")

        assertEquals(401, code)
        assertNull(tokenStore.current())
        assertTrue(sessionState.authenticationRequired.value)
    }

    @Test
    fun `a 401 is retried once with a freshly obtained token`() {
        server.enqueue(unauthorized)
        server.enqueue(MockResponse.Builder().body("{}").build())

        val code = clientWith { "totp-fresh" }.get("/api/chat/conversations")

        assertEquals(200, code)
        assertEquals("totp-fresh", tokenStore.current())
        assertFalse(sessionState.authenticationRequired.value)
        assertEquals("Bearer totp-stale", server.takeRequest().headers["Authorization"])
        assertEquals("Bearer totp-fresh", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `a rejected login is not re-attempted through the credential exchange`() {
        server.enqueue(unauthorized)
        var reauthAttempts = 0

        val code = clientWith { reauthAttempts++; "totp-fresh" }
            .newCall(
                Request.Builder()
                    .url(server.url("/api/auth/session"))
                    .header("Authorization", "Bearer wrong-password")
                    .post("".toRequestBody())
                    .build(),
            ).execute().use { it.code }

        assertEquals(401, code)
        assertEquals(0, reauthAttempts)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `a server that keeps rejecting is not retried forever`() {
        repeat(4) { server.enqueue(unauthorized) }

        val code = clientWith { "totp-fresh" }.get("/api/chat/conversations")

        assertEquals(401, code)
        assertEquals(2, server.requestCount)
        assertTrue(sessionState.authenticationRequired.value)
    }
}
