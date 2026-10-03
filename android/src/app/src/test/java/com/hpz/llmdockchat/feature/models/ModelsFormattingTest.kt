package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.data.model.Engine
import com.hpz.llmdockchat.data.model.ServiceSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneOffset

/**
 * [ServiceSummary.statusLabel] and [ServiceSummary.subtitle] — F10-R1's third
 * and fourth criteria (an exited service names its exit code; not-created is
 * distinguishable from exited) and the Deviations note on uptime (never say
 * "uptime" for a value that is really the container's creation time).
 */
class ModelsFormattingTest {

    private val now = Instant.parse("2026-07-25T12:00:00Z")
    private val zone = ZoneOffset.UTC

    @Test
    fun `a running service's status label is Running`() {
        assertEquals("Running", ServiceSummary("llamacpp-a", "running", "chat").statusLabel())
    }

    @Test
    fun `an exited service names its exit code`() {
        val service = ServiceSummary("llamacpp-a", "exited", "chat", exitCode = 137)
        assertEquals("Exited (code 137)", service.statusLabel())
    }

    @Test
    fun `an exited service with no exit code still says exited, not a crash`() {
        val service = ServiceSummary("llamacpp-a", "exited", "chat", exitCode = null)
        assertEquals("Exited", service.statusLabel())
    }

    @Test
    fun `not-created is its own label, distinguishable from exited`() {
        val service = ServiceSummary("llamacpp-a", "not-created", "chat")
        assertEquals("Not created", service.statusLabel())
    }

    @Test
    fun `a running service's subtitle shows port, size and created-ago, never the word uptime`() {
        val service = ServiceSummary(
            "llamacpp-a", "running", "chat", port = 3301,
            modelSizeStr = "26.1 GB",
            createdAt = "2026-07-25T08:00:00Z", // 4 hours before `now`
        )
        val subtitle = service.subtitle(now, zone)
        assertEquals(":3301 · 26.1 GB · created 08:00", subtitle)
    }

    @Test
    fun `an exited service's subtitle carries the exit code, not a created-ago figure`() {
        val service = ServiceSummary("llamacpp-a", "exited", "chat", port = 3303, modelSizeStr = "33.73 GB", exitCode = 1)
        assertEquals(":3303 · 33.73 GB · exited (code 1)", service.subtitle(now, zone))
    }

    @Test
    fun `a not-created service's subtitle shows what it needs, not a blank size`() {
        val service = ServiceSummary("ds4-a", "not-created", "chat", port = 3315, modelSizeStr = "80.76 GB")
        assertEquals(":3315 · needs ~80.76 GB", service.subtitle(now, zone))
    }

    @Test
    fun `a not-created service with no known size still renders, just without a needs figure`() {
        val service = ServiceSummary("ds4-a", "not-created", "chat", port = 3315, modelSizeStr = null)
        assertEquals(":3315 · not created", service.subtitle(now, zone))
    }

    @Test
    fun `chip labels cover the engines added for the #269 gap`() {
        assertEquals("ik.cpp", engineLabel(Engine.IK_LLAMA_CPP))
        assertEquals("exl3", engineLabel(Engine.TABBYAPI))
        assertEquals("ninfer", engineLabel(Engine.NINFER))
        assertEquals(listOf("ik", "cpp"), engineLabelLines(Engine.IK_LLAMA_CPP))
        // The chip renders engineLabelLines (split on '.' and space) at a fixed
        // width with a bounded font ramp, so every engine's label must yield at
        // least one line and no line longer than the ramp's floor — otherwise a
        // future relabel silently overflows the chip instead of failing here.
        for (engine in Engine.entries) {
            val lines = engineLabelLines(engine)
            assertTrue("$engine must render at least one line", lines.isNotEmpty())
            assertTrue("$engine chip line too long: $lines", lines.maxOf { it.length } <= 6)
        }
    }

    @Test
    fun `mibToGb renders up to one decimal place, dropping a trailing zero`() {
        // Matches the mockup's own style — "61.4 / 96 GB", not "61.4 / 96.0 GB".
        assertEquals("95.6", mibToGb(97887))
        assertEquals("60", mibToGb(61440))
    }
}
