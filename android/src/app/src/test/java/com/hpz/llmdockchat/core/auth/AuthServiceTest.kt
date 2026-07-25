package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class AuthServiceTest {

    private lateinit var server: MockWebServer
    private lateinit var service: AuthService
    private lateinit var tokenStore: FakeTokenStore
    private var reauthAttempts = 0

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        // A token IS stored: the point of most of these tests is that the login
        // routes go out without it anyway.
        tokenStore = FakeTokenStore("totp-stale")
        val sessionState = SessionState()
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState))
            .authenticator(
                SessionAuthenticator(tokenStore, sessionState) {
                    reauthAttempts++
                    "totp-should-never-be-used"
                },
            )
            .build()
        service = AuthService(
            ApiClient(
                client,
                FakeServerUrlStore(baseUrl(server.url("/").toString())),
                ApiJson,
                Dispatchers.IO,
            ),
        )
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun session(token: String = "totp-fresh") = MockResponse.Builder()
        .body("""{"token": "$token", "expires_in": 28800}""")
        .build()

    @Test
    fun `a password login sends the password as its own bearer and no session token`() = runBlocking {
        server.enqueue(session())

        val result = service.signIn(Credential.Password("hunter2"))

        assertEquals("totp-fresh", result.getOrNull())
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/auth/session", request.url.encodedPath)
        assertEquals("Bearer hunter2", request.headers["Authorization"])
        assertNull(request.headers[AuthService.TOTP_CODE_HEADER])
    }

    @Test
    fun `a TOTP login sends only the code header`() = runBlocking {
        server.enqueue(session())

        val result = service.signInWithTotpCode("419283")

        assertEquals("totp-fresh", result.getOrNull())
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/auth/login", request.url.encodedPath)
        assertEquals("419283", request.headers[AuthService.TOTP_CODE_HEADER])
        // The stored bearer must not ride along: `/api/auth/login` is not
        // decorated with `require_auth`, and a stale `totp-` bearer on an
        // ordinary route makes the dashboard 401 before it reads the code.
        assertNull(request.headers["Authorization"])
    }

    /**
     * F01-R3: "shows the server's message". A 401 from a login route means the
     * credential just supplied is wrong, not that the session has gone, so the
     * dashboard's own words have to survive the error mapping.
     */
    @Test
    fun `an invalid code surfaces the dashboard's own message`() = runBlocking {
        server.enqueue(
            MockResponse.Builder().code(401).body("""{"error": "Invalid TOTP code"}""").build(),
        )

        val error = service.signInWithTotpCode("000000").exceptionOrNull()?.appError

        assertEquals("Invalid TOTP code", error?.displayMessage)
        assertEquals(0, reauthAttempts)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `an invalid password surfaces the dashboard's own message`() = runBlocking {
        server.enqueue(
            MockResponse.Builder().code(401).body("""{"error": "Invalid token"}""").build(),
        )

        val error = service.signIn(Credential.Password("wrong")).exceptionOrNull()?.appError

        assertEquals("Invalid token", error?.displayMessage)
        assertEquals(0, reauthAttempts)
    }

    /** TOTP not configured server-side answers 400, and it is worth reading. */
    @Test
    fun `a 400 from the login route is shown as the server wrote it`() = runBlocking {
        server.enqueue(
            MockResponse.Builder().code(400).body("""{"error": "TOTP is not configured"}""").build(),
        )

        val error = service.signInWithTotpCode("123456").exceptionOrNull()?.appError

        assertTrue(error is AppError.Http)
        assertEquals("TOTP is not configured", error?.displayMessage)
    }

    @Test
    fun `verify carries the session token, unlike the login routes`() = runBlocking {
        server.enqueue(MockResponse.Builder().body("""{"valid": true}""").build())

        assertEquals(true, service.verify().getOrNull())
        assertEquals("Bearer totp-stale", server.takeRequest().headers["Authorization"])
    }
}
