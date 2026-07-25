package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F09-R4's third criterion, as arithmetic: bounded in both directions. No wall
 * clock is involved — the schedule is a pure function, so the property is
 * asserted rather than timed.
 */
class ReconnectBackoffTest {

    @Test
    fun `the delay grows and then stops growing`() {
        val schedule = (0..9).map { reconnectDelayMs(it, initialMs = 1_000, maxMs = 8_000) }
        assertEquals(
            listOf(1_000L, 2_000L, 4_000L, 8_000L, 8_000L, 8_000L, 8_000L, 8_000L, 8_000L, 8_000L),
            schedule,
        )
    }

    /**
     * The "does not give up permanently" half. A phone in a tunnel for an hour
     * comes back to a delay that is still the ceiling — never a longer one, and
     * never a value meaning "stop trying", because there is no such value.
     */
    @Test
    fun `an arbitrarily long outage never exceeds the ceiling and never stops`() {
        for (attempt in listOf(30, 62, 63, 64, 1_000, Int.MAX_VALUE)) {
            val delay = reconnectDelayMs(attempt, initialMs = 1_000, maxMs = 8_000)
            assertEquals("attempt $attempt", 8_000L, delay)
        }
    }

    @Test
    fun `every delay is positive so a dead server is never hammered in a tight loop`() {
        for (attempt in 0..40) {
            assertTrue(reconnectDelayMs(attempt, initialMs = 1, maxMs = 8) >= 1)
        }
    }

    /** A ceiling below the first delay is a misconfiguration, not a zero wait. */
    @Test
    fun `a ceiling under the initial delay still waits the initial delay`() {
        assertEquals(1_000L, reconnectDelayMs(0, initialMs = 1_000, maxMs = 10))
        assertEquals(1_000L, reconnectDelayMs(5, initialMs = 1_000, maxMs = 10))
    }

    @Test
    fun `resetting after a connection that worked starts over at the short delay`() {
        val backoff = ReconnectBackoff(initialMs = 1_000, maxMs = 8_000)
        assertEquals(1_000L, backoff.next())
        assertEquals(2_000L, backoff.next())
        assertEquals(4_000L, backoff.next())
        backoff.reset()
        assertEquals(1_000L, backoff.next())
    }
}
