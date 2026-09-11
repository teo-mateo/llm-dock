package com.hpz.llmdockchat.feature.thread

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F15-R1/R2/R3 as pure functions — the whole decision behind the chip and the
 * sheet, with no Compose rule and no device.
 *
 * This is the split `feature/modelpicker/ModelPickerSheetTest` already uses
 * (`runningChatCapable` pulled out of the sheet for exactly this reason): the
 * rendering is verified on device, and the *rules* are verified where a failure
 * is a stack trace rather than a screenshot.
 */
class ReasoningLevelSheetTest {

    @Test
    fun `the options are default then the declared levels, in the server's order`() {
        val options = reasoningLevelOptions(listOf("off", "low", "xhigh"), null)

        assertEquals(
            listOf(null, "off", "low", "xhigh"),
            options.map { it.id },
        )
        assertEquals(REASONING_DEFAULT_LABEL, options.first().label)
        assertTrue(options.first().isDefault)
        assertFalse(options.any { it.stale })
    }

    /** F15-R1: the ladder is the operator's declaration — not sorted, not filled in. */
    @Test
    fun `nothing is invented between the declared rungs`() {
        val options = reasoningLevelOptions(listOf("xhigh", "off", "low"), null)

        assertEquals(listOf(null, "xhigh", "off", "low"), options.map { it.id })
        // "high" exists on some models and is not offered by this one.
        assertFalse(options.any { it.id == "high" })
    }

    @Test
    fun `an empty ladder still offers the default and nothing else`() {
        val options = reasoningLevelOptions(emptyList(), null)

        assertEquals(listOf<String?>(null), options.map { it.id })
    }

    /** F15-R3: a stranded level is listed last, labelled, and marked stale. */
    @Test
    fun `a stored level the ladder lost appears last and is marked not offered`() {
        val options = reasoningLevelOptions(listOf("off", "low"), "high")

        assertEquals(listOf(null, "off", "low", "high"), options.map { it.id })
        val stranded = options.last()
        assertTrue(stranded.stale)
        assertFalse(stranded.isDefault)
        assertEquals("high", stranded.label)
    }

    @Test
    fun `the stale row disappears once the level is one the ladder declares`() {
        assertFalse(reasoningLevelOptions(listOf("off", "low"), "low").any { it.stale })
    }

    @Test
    fun `staleness is about the ladder, not about emptiness`() {
        assertTrue(isReasoningLevelStale(listOf("low"), "off"))
        assertTrue(isReasoningLevelStale(emptyList(), "low"))
        assertFalse(isReasoningLevelStale(emptyList(), null))
        assertFalse(isReasoningLevelStale(listOf("low", "off"), "off"))
    }

    /** F15-R3 + F15-R8: visibility of the control, in the four cases that matter. */
    @Test
    fun `the control shows only with a ladder or a stored level, and never on OpenRouter`() {
        assertTrue(showsReasoningControl(listOf("low"), null, onOpenRouter = false))
        assertTrue(showsReasoningControl(emptyList(), "low", onOpenRouter = false))
        assertFalse(showsReasoningControl(emptyList(), null, onOpenRouter = false))
        assertFalse(showsReasoningControl(listOf("low"), "low", onOpenRouter = true))
    }

    @Test
    fun `the not-offered wording is the same sentence the web client shows`() {
        assertEquals("not offered by this model", REASONING_NOT_OFFERED_LABEL)
        assertEquals("Model default", REASONING_DEFAULT_LABEL)
    }
}
