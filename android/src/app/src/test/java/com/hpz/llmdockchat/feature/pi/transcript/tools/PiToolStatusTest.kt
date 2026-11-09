package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class PiToolStatusTest {
    private fun tool(status: ToolStatus, durationMs: Long? = null) =
        PiItem.Tool("t1", "c1", "bash", null, null, status, durationMs, false, 0)

    @Test
    fun `a few milliseconds`() {
        assertEquals("3 ms", toolStatusText(tool(ToolStatus.DONE, 3)))
    }

    @Test
    fun `just under a second stays in milliseconds`() {
        assertEquals("999 ms", toolStatusText(tool(ToolStatus.DONE, 999)))
    }

    @Test
    fun `a second or more renders one decimal`() {
        assertEquals("3.7 s", toolStatusText(tool(ToolStatus.DONE, 3707)))
    }

    @Test
    fun `no duration renders nothing`() {
        assertEquals("", toolStatusText(tool(ToolStatus.DONE)))
    }

    @Test
    fun `a zero duration renders nothing`() {
        assertEquals("", toolStatusText(tool(ToolStatus.DONE, 0)))
    }

    @Test
    fun `running is unchanged`() {
        assertEquals("running…", toolStatusText(tool(ToolStatus.RUNNING)))
    }

    @Test
    fun `error is unchanged`() {
        assertEquals("error", toolStatusText(tool(ToolStatus.ERROR)))
    }

    @Test
    fun `the description keeps the word done with the duration`() {
        assertEquals("done · 3 ms", toolStatusDescription(tool(ToolStatus.DONE, 3)))
        assertEquals("done · 3.7 s", toolStatusDescription(tool(ToolStatus.DONE, 3707)))
    }

    @Test
    fun `the description says done without a duration`() {
        assertEquals("done", toolStatusDescription(tool(ToolStatus.DONE)))
    }

    @Test
    fun `the description mirrors the other statuses`() {
        assertEquals("running…", toolStatusDescription(tool(ToolStatus.RUNNING)))
        assertEquals("error", toolStatusDescription(tool(ToolStatus.ERROR)))
    }
}
