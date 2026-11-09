package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChatterboxToolsTest {
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

    private val sendArgs =
        """{"audience":"participant","to":"product-owner","text":"Mid-#30, no blocker. Done so far…\n\nNext: the drawer."}"""
    private val confirmedOutput =
        """{"content":[{"type":"text","text":"Sent to product-owner in #mailbox; confirmed by the server."}],"details":{"outcome":"confirmed"}}"""

    @Test
    fun `send target points at the participant`() {
        assertEquals("→ product-owner", sendTarget(parseToolArgs(sendArgs)))
    }

    @Test
    fun `send target for a channel audience`() {
        assertEquals("→ channel", sendTarget(parseToolArgs("""{"audience":"channel","text":"Announcement"}""")))
    }

    @Test
    fun `send target without a recipient is empty`() {
        assertEquals("", sendTarget(parseToolArgs("""{"audience":"participant","text":"Hi"}""")))
        assertEquals("", sendTarget(null))
    }

    @Test
    fun `chat lines map real look items`() {
        val output = """
            {"content":[{"type":"text","text":"- 12:41:58Z llmdock-po (bot): Hi all"}],
             "details":{"items":[{"time":"2026-11-09T12:41:58Z","channel":"#llmdock","from":"llmdock-po","kind":"bot","addressed":false,"important":false,"private":false,"replayed":false,"msgid":"68giyp28t7x9cutuqeixi9mv8w","text":"Hi all, …"},
               {"time":"2026-11-09T12:45:02Z","channel":"#llmdock","from":"developer","kind":"human","addressed":true,"important":true,"private":false,"replayed":false,"msgid":"abc","text":"Received.\nSecond line"}]}}
        """.trimIndent()
        val lines = chatLines(parseToolResult(output))!!
        assertEquals(2, lines.size)
        assertEquals("12:41", lines[0].time)
        assertEquals("llmdock-po", lines[0].from)
        assertEquals(true, lines[0].bot)
        assertEquals("Hi all, …", lines[0].text)
        assertEquals(false, lines[0].toYou)
        assertEquals(false, lines[0].important)
        assertEquals("12:45", lines[1].time)
        assertEquals("developer", lines[1].from)
        assertEquals(false, lines[1].bot)
        assertEquals(true, lines[1].toYou)
        assertEquals(true, lines[1].important)
        assertEquals("Received.\nSecond line", lines[1].text)
    }

    @Test
    fun `chat lines cut malformed times verbatim`() {
        val output = """{"content":[],"details":{"items":[{"time":"no-time","from":"a","text":"x"}]}}"""
        val lines = chatLines(parseToolResult(output))!!
        assertEquals("no-time", lines[0].time)
        assertEquals("a", lines[0].from)
        assertEquals(false, lines[0].bot)
    }

    @Test
    fun `chat lines need details items`() {
        assertNull(chatLines(null))
        assertNull(chatLines(parseToolResult(confirmedOutput)))
        assertNull(chatLines(parseToolResult("""{"content":[{"type":"text","text":"developer2 bot"}],"details":{"people":[{"nick":"developer2","kind":"bot"}]}}""")))
    }

    @Test
    fun `send summary reads the first text line`() {
        assertEquals(
            "→ product-owner: Mid-#30, no blocker. Done so far…",
            chatterboxSummary(tool("chatterbox_send", sendArgs, confirmedOutput)),
        )
    }

    @Test
    fun `send summary appends an unconfirmed outcome`() {
        val output = """{"content":[{"type":"text","text":"NOT SENT."}],"details":{"outcome":"pending"}}"""
        assertEquals(
            "→ product-owner: Mid-#30, no blocker. Done so far… · pending",
            chatterboxSummary(tool("chatterbox_send", sendArgs, output)),
        )
    }

    @Test
    fun `send summary for a channel audience`() {
        assertEquals(
            "→ channel: Announcement",
            chatterboxSummary(tool("chatterbox_send", """{"audience":"channel","text":"Announcement"}""", confirmedOutput)),
        )
    }

    @Test
    fun `send summary falls back without a target`() {
        val summary = chatterboxSummary(tool("chatterbox_send", """{"audience":"participant","text":"Hi"}""", null))
        assertEquals(argsSummary("""{"audience":"participant","text":"Hi"}"""), summary)
    }

    @Test
    fun `look summary carries the what and count`() {
        assertEquals(
            "look recent · 10",
            chatterboxSummary(tool("chatterbox_look", """{"what":"recent","count":10}""", confirmedOutput)),
        )
        assertEquals("look who", chatterboxSummary(tool("chatterbox_look", """{"what":"who"}""", null)))
    }

    @Test
    fun `look summary for an unknown what`() {
        assertEquals("look status", chatterboxSummary(tool("chatterbox_look", """{"what":"status"}""", null)))
    }

    @Test
    fun `look summary without args falls back`() {
        assertEquals("", chatterboxSummary(tool("chatterbox_look", null, null)))
    }

    @Test
    fun `join and leave summaries`() {
        assertEquals("join #mailchecker", chatterboxSummary(tool("chatterbox_join", """{"channel":"#mailchecker"}""", null)))
        assertEquals("join", chatterboxSummary(tool("chatterbox_join", """{"nick":"developer"}""", null)))
        assertEquals("leave", chatterboxSummary(tool("chatterbox_leave", "{}", null)))
    }
}
