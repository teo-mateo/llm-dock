package com.hpz.llmdockchat.core.error

import com.hpz.llmdockchat.core.net.httpError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ErrorMappingTest {

    @Test
    fun `the dashboard's own message is extracted`() {
        assertEquals(
            "A run is already active for this conversation",
            ErrorBody.extract("""{"error": "A run is already active for this conversation"}"""),
        )
    }

    @Test
    fun `a nested message object is extracted`() {
        assertEquals(
            "Invalid API Key",
            ErrorBody.extract("""{"error": {"message": "Invalid API Key", "code": 401}}"""),
        )
    }

    @Test
    fun `a body with no message yields none`() {
        assertNull(ErrorBody.extract("""{"status": "nope"}"""))
        assertNull(ErrorBody.extract("<html><body>502 Bad Gateway</body></html>"))
        assertNull(ErrorBody.extract(""))
        assertNull(ErrorBody.extract(null))
        assertNull(ErrorBody.extract("""{"error": ""}"""))
    }

    @Test
    fun `a 409 carries the server's words through`() {
        val error = httpError(409, """{"error": "A run is already active for this conversation"}""")
        error as AppError.Http
        assertEquals(409, error.status)
        assertEquals("A run is already active for this conversation", error.message)
        assertTrue(error.fromServer)
        assertEquals("A run is already active for this conversation", error.displayMessage)
    }

    @Test
    fun `an http error without a message is still displayable and marked as ours`() {
        val error = httpError(502, "<html>gateway</html>")
        error as AppError.Http
        assertEquals(502, error.status)
        assertFalse(error.fromServer)
        assertTrue(error.displayMessage.contains("502"))
    }

    @Test
    fun `a 401 is an auth failure whatever the body says`() {
        assertEquals(
            AppError.Unauthenticated,
            httpError(401, """{"error": "Authentication failed", "hint": "..."}"""),
        )
    }

    @Test
    fun `network and parse failures are distinguishable`() {
        val network: AppError = AppError.Network(java.net.ConnectException("Connection refused"))
        val parse: AppError = AppError.Parse(IllegalArgumentException("bad json"))
        assertTrue(network.displayMessage.contains("Connection refused"))
        assertTrue(parse.displayMessage.isNotBlank())
        assertTrue(network != parse)
    }
}
