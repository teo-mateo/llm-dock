package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FileToolsTest {
    private fun tool(name: String, args: String?, output: String? = null) = PiItem.Tool(
        id = "item",
        callId = "call",
        name = name,
        args = args,
        output = output,
        status = ToolStatus.DONE,
        durationMs = 3,
        truncated = false,
        ts = 0,
    )

    @Test
    fun `numbers lines with a trailing newline`() {
        assertEquals(listOf(NumberedLine(1, "a"), NumberedLine(2, "b")), numberLines("a\nb\n", 1))
    }

    @Test
    fun `numbers lines without a trailing newline`() {
        assertEquals(listOf(NumberedLine(1, "a"), NumberedLine(2, "b")), numberLines("a\nb", 1))
    }

    @Test
    fun `an empty string has no lines`() {
        assertTrue(numberLines("", 1).isEmpty())
    }

    @Test
    fun `numbers from a first line offset`() {
        assertEquals(listOf(NumberedLine(120, "a"), NumberedLine(121, "b")), numberLines("a\nb", 120))
    }

    @Test
    fun `read summary with offset and limit`() {
        val item = tool("read", """{"path":"/forgejo/wt/AuthFlowTests.cs","offset":120,"limit":60}""")
        assertEquals("AuthFlowTests.cs L120–179", readSummary(item))
    }

    @Test
    fun `read summary with offset only`() {
        val item = tool("read", """{"path":"/forgejo/wt/AuthFlowTests.cs","offset":120}""")
        assertEquals("AuthFlowTests.cs L120–", readSummary(item))
    }

    @Test
    fun `read summary without a range`() {
        val item = tool("read", """{"path":"/forgejo/wt/AuthFlowTests.cs"}""")
        assertEquals("AuthFlowTests.cs", readSummary(item))
    }

    @Test
    fun `read summary names an image result`() {
        val item = tool(
            "read",
            """{"path":"/forgejo/wt/screenshot.png"}""",
            """{"content":[{"type":"text","text":"Read image file [image/png]"},{"type":"image","data":"AAAA","mimeType":"image/png"}]}""",
        )
        assertEquals("screenshot.png · image", readSummary(item))
    }

    @Test
    fun `read summary falls back without a path`() {
        val item = tool("read", """{"limit":60}""")
        assertEquals("limit=60", readSummary(item))
    }

    @Test
    fun `write summary counts content lines`() {
        val item = tool("write", """{"path":"/forgejo/wt/AccountRules.cs","content":"a\nb\n"}""")
        assertEquals("AccountRules.cs · 2 lines", writeSummary(item))
    }

    @Test
    fun `downsamples an image larger than the target`() {
        assertEquals(2, imageSampleSize(2000, 1000, 1000))
        assertEquals(4, imageSampleSize(4000, 3000, 1000))
    }

    @Test
    fun `keeps the original size at the target`() {
        assertEquals(1, imageSampleSize(1000, 1000, 1000))
        assertEquals(2, imageSampleSize(1025, 1000, 1000))
    }

    @Test
    fun `treats invalid dimensions as one`() {
        assertEquals(1, imageSampleSize(0, 1000, 1000))
        assertEquals(1, imageSampleSize(1000, 1000, 0))
    }

    @Test
    fun `write summary falls back without a path`() {
        val item = tool("write", """{"content":"a"}""")
        assertEquals("content=a", writeSummary(item))
    }
}
