package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiFormattingTest {
    @Test
    fun `cache bytes use KB below a megabyte and MB above`() {
        assertEquals("1 KB", formatCacheBytes(1))
        assertEquals("200 KB", formatCacheBytes(200L * 1024))
        assertEquals("8.4 MB", formatCacheBytes((8.4 * 1024 * 1024).toLong()))
    }

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
    fun `session meta head leads with the model and uses the server project label`() {
        assertEquals(
            "llm-dock/pennyroyal-qwen3-8-flash-next · forgejo/tubevault",
            piSessionMetaHead("forgejo/tubevault", "llm-dock/pennyroyal-qwen3-8-flash-next"),
        )
    }

    @Test
    fun `session meta head omits an unknown model or project instead of faking one`() {
        assertEquals("repo", piSessionMetaHead("repo", null))
        assertEquals("repo", piSessionMetaHead("repo", "  "))
        assertEquals("model", piSessionMetaHead(null, "model"))
        assertEquals("model", piSessionMetaHead("  ", "model"))
        assertEquals("", piSessionMetaHead(null, null))
    }

    @Test
    fun `context label is absent rather than zero when unknown`() {
        assertNull(piContextLabel(null))
        assertEquals("ctx 0%", piContextLabel(0.0))
        assertEquals("ctx 34%", piContextLabel(33.6))
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

    private fun session(state: PiState) = PiSession(
        key = PiSessionKey("s1", "i1"),
        name = null,
        cwd = "/repo",
        model = null,
        thinkingLevel = null,
        firstSeen = 0,
        lastSeen = 0,
        endedAt = null,
        endReason = null,
        live = state != PiState.ENDED,
        state = state,
        contextPercent = null,
    )

    @Test
    fun `status label names every state`() {
        assertEquals("working", piStatusLabel(session(PiState.WORKING)))
        assertEquals("idle", piStatusLabel(session(PiState.IDLE)))
        assertEquals("ended", piStatusLabel(session(PiState.ENDED)))
    }
}
