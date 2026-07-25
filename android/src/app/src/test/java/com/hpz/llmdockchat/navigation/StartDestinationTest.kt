package com.hpz.llmdockchat.navigation

import com.hpz.llmdockchat.testing.baseUrl
import org.junit.Assert.assertEquals
import org.junit.Test

class StartDestinationTest {

    private val server = baseUrl("http://10.0.2.2:3399")

    @Test
    fun `a cold install opens on Connect`() {
        assertEquals(
            Destinations.CONNECT,
            startDestination(server = null, token = null, hasCredential = false),
        )
    }

    /** F01-R6: the credential renews the session, so a dead token is not a prompt. */
    @Test
    fun `a stored credential is enough on its own`() {
        assertEquals(
            Destinations.TABS,
            startDestination(server = server, token = null, hasCredential = true),
        )
    }

    /** A TOTP sign-in: a live token, nothing to renew it with. Still signed in. */
    @Test
    fun `a stored token is enough on its own`() {
        assertEquals(
            Destinations.TABS,
            startDestination(server = server, token = "totp-abc", hasCredential = false),
        )
    }

    @Test
    fun `secrets without a server address cannot be used`() {
        assertEquals(
            Destinations.CONNECT,
            startDestination(server = null, token = "totp-abc", hasCredential = true),
        )
    }

    @Test
    fun `an address alone is not a session`() {
        assertEquals(
            Destinations.CONNECT,
            startDestination(server = server, token = null, hasCredential = false),
        )
        assertEquals(
            Destinations.CONNECT,
            startDestination(server = server, token = "  ", hasCredential = false),
        )
    }
}
