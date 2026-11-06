package com.hpz.llmdockchat.feature.pi

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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

    @Test
    fun `following never reports unseen content`() {
        assertFalse(FollowState(following = true, seen = "a").hasUnseen("b"))
    }

    @Test
    fun `paused reports content that changed since the pause`() {
        val paused = FollowState(following = true, seen = null).pause("a")
        assertFalse(paused.hasUnseen("a"))
        assertTrue(paused.hasUnseen("b"))
    }

    @Test
    fun `settling at the bottom resumes following`() {
        assertTrue(FollowState(following = false, seen = "a").settle(atBottom = true, current = "b").following)
        assertFalse(FollowState(following = true, seen = "a").settle(atBottom = false, current = "b").following)
    }

    @Test
    fun `jump resumes following and clears unseen`() {
        val jumped = FollowState(following = false, seen = "a").jump("b")
        assertTrue(jumped.following)
        assertFalse(jumped.hasUnseen("b"))
    }
}
