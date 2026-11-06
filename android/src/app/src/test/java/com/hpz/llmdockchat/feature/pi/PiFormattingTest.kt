package com.hpz.llmdockchat.feature.pi

import org.junit.Assert.assertEquals
import org.junit.Test

class PiFormattingTest {
    @Test
    fun `now under a minute`() {
        assertEquals("now", formatAgo(100_000_000L, 99_970_000L))
    }

    @Test
    fun `minutes`() {
        assertEquals("1 min ago", formatAgo(100_000_000L, 99_940_000L))
        assertEquals("2 min ago", formatAgo(100_000_000L, 99_880_000L))
    }

    @Test
    fun `hours`() {
        assertEquals("1 h ago", formatAgo(100_000_000L, 96_400_000L))
        assertEquals("2 h ago", formatAgo(100_000_000L, 92_800_000L))
    }

    @Test
    fun `days`() {
        assertEquals("1 d ago", formatAgo(100_000_000L, 13_600_000L))
        assertEquals("2 d ago", formatAgo(100_000_000L, -72_800_000L))
    }
}
