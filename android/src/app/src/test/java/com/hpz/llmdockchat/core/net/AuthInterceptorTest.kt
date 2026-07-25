package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
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

class AuthInterceptorTest {

    private lateinit var server: MockWebServer
    private lateinit var tokenStore: FakeTokenStore
    private lateinit var sessionState: SessionState
    private lateinit var client: OkHttpClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        tokenStore = FakeTokenStore("totp-first")
        sessionState = SessionState()
        client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState))
            .build()
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun get(path: String) = client.newCall(
        Request.Builder().url(server.url(path)).build(),
    ).execute().use { it.code }

    @Test
    fun `every ordinary request carries the bearer token`() {
        server.enqueue(MockResponse.Builder().body("{}").build())
        get("/api/chat/conversations")
        assertEquals("Bearer totp-first", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `GET health is the one exemption`() {
        server.enqueue(MockResponse.Builder().body("{}").build())
        get("/api/health")
        assertNull(server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `the health exemption is scoped to GET`() {
        server.enqueue(MockResponse.Builder().body("{}").build())
        client.newCall(
            Request.Builder().url(server.url("/api/health")).post("{}".toRequestBody()).build(),
        ).execute().close()
        assertEquals("Bearer totp-first", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `TOTP login goes out without a session token, from a cold install`() {
        tokenStore.clear()
        server.enqueue(MockResponse.Builder().body("""{"token":"totp-new"}""").build())

        client.newCall(
            Request.Builder()
                .url(server.url("/api/auth/login"))
                .header("X-TOTP-Code", "123456")
                .post("".toRequestBody())
                .build(),
        ).execute().close()

        val recorded = server.takeRequest()
        assertNull(recorded.headers["Authorization"])
        assertEquals("123456", recorded.headers["X-TOTP-Code"])
    }

    @Test
    fun `a caller-supplied Authorization header is left alone`() {
        server.enqueue(MockResponse.Builder().body("""{"token":"totp-new"}""").build())

        client.newCall(
            Request.Builder()
                .url(server.url("/api/auth/session"))
                .header("Authorization", "Bearer the-dashboard-password")
                .post("".toRequestBody())
                .build(),
        ).execute().close()

        assertEquals("Bearer the-dashboard-password", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `with no token and nothing to mint one from, the request never reaches the network`() {
        tokenStore.clear()
        val thrown = runCatching { get("/api/chat/conversations") }.exceptionOrNull()
        assertTrue(thrown is ApiException)
        assertEquals(AppError.Unauthenticated, (thrown as ApiException).error)
        assertEquals(0, server.requestCount)
        assertTrue(sessionState.authenticationRequired.value)
    }

    /**
     * F01-R6 narrows the rule above. A dashboard restart 401s the first
     * request, which discards the dead token; failing everything queued behind
     * it would take a signed-in user to Connect for no reason.
     */
    @Test
    fun `with no token but a credential, one is minted before sending`() {
        tokenStore.clear()
        server.enqueue(MockResponse.Builder().body("{}").build())
        val minted = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState) { "totp-minted" })
            .build()

        val code = minted.newCall(
            Request.Builder().url(server.url("/api/chat/conversations")).build(),
        ).execute().use { it.code }

        assertEquals(200, code)
        assertEquals("Bearer totp-minted", server.takeRequest().headers["Authorization"])
        assertEquals("totp-minted", tokenStore.current())
        assertFalse(sessionState.authenticationRequired.value)
    }

    @Test
    fun `an X-TOTP-Token header rotates the stored token for the next request`() {
        server.enqueue(
            MockResponse.Builder()
                .setHeader(AuthInterceptor.TOTP_TOKEN_HEADER, "totp-rotated")
                .body("{}")
                .build(),
        )
        server.enqueue(MockResponse.Builder().body("{}").build())

        get("/api/chat/conversations")
        assertEquals("totp-rotated", tokenStore.current())

        get("/api/chat/conversations")
        server.takeRequest()
        assertEquals("Bearer totp-rotated", server.takeRequest().headers["Authorization"])
        assertFalse(sessionState.authenticationRequired.value)
    }
}
