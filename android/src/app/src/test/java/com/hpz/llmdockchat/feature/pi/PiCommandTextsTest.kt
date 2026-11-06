package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.Rejection
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PiCommandTextsTest {

    @Test
    fun `pending message matches the web`() {
        assertEquals(
            "Sent — pi will pick it up",
            outcomeMessage(PiCommandOutcome.Pending),
        )
    }

    @Test
    fun `done has no message`() {
        assertNull(outcomeMessage(PiCommandOutcome.Done))
    }

    @Test
    fun `failed includes the error`() {
        assertEquals(
            "pi could not run it (no model)",
            outcomeMessage(PiCommandOutcome.Failed("no model")),
        )
    }

    @Test
    fun `offline matches the web`() {
        assertEquals(
            "pi is offline",
            outcomeMessage(PiCommandOutcome.Rejected(Rejection.OFFLINE)),
        )
    }

    @Test
    fun `rate limited matches the web`() {
        assertEquals(
            "Too many messages — wait a minute",
            outcomeMessage(PiCommandOutcome.Rejected(Rejection.RATE_LIMITED)),
        )
    }

    @Test
    fun `busy matches the web`() {
        assertEquals(
            "The dashboard is busy — try again",
            outcomeMessage(PiCommandOutcome.Rejected(Rejection.BUSY)),
        )
    }

    @Test
    fun `invalid text matches the web`() {
        assertEquals(
            "Message is empty or too long",
            outcomeMessage(PiCommandOutcome.Rejected(Rejection.INVALID_TEXT)),
        )
    }

    @Test
    fun `other matches the web`() {
        assertEquals(
            "Could not send",
            outcomeMessage(PiCommandOutcome.Rejected(Rejection.OTHER)),
        )
    }

    @Test
    fun `stopped within 30 s`() {
        assertEquals("stopped", runEndLabel("error", 1000, 1000))
        assertEquals("stopped", runEndLabel("error", 31_000, 1000))
    }

    @Test
    fun `not stopped after 30 s`() {
        assertEquals("error", runEndLabel("error", 31_001, 1000))
        assertEquals("error", runEndLabel("error", 999, 1000))
    }

    @Test
    fun `no stop`() {
        assertEquals("run completed", runEndLabel("completed", 1000, null))
        assertEquals("aborted", runEndLabel("aborted", 1000, null))
        assertEquals("error", runEndLabel("error", 1000, null))
    }
}
