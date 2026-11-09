package com.hpz.llmdockchat.feature.pi.transcript.tools

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiToolPayloadTest {
    @Test
    fun `envelope with one text part`() {
        val result = parseToolResult("""{"content":[{"type":"text","text":"hello"}]}""")!!
        assertEquals("hello", result.text)
        assertTrue(result.images.isEmpty())
        assertNull(result.details)
        assertNull(result.structured)
        assertFalse(result.isError)
    }

    @Test
    fun `two text parts join with a newline`() {
        val result = parseToolResult(
            """{"content":[{"type":"text","text":"first"},{"type":"text","text":"second"}]}""",
        )!!
        assertEquals("first\nsecond", result.text)
    }

    @Test
    fun `text and image parts are separated`() {
        val result = parseToolResult(
            """{"content":[{"type":"text","text":"see"},{"type":"image","data":"QUJD","mimeType":"image/png"}]}""",
        )!!
        assertEquals("see", result.text)
        assertEquals(listOf(ToolImage("image/png", "QUJD")), result.images)
    }

    @Test
    fun `envelope keeps structured content details and the error flag`() {
        val result = parseToolResult(
            """{"content":[{"type":"text","text":"boom"}],"structuredContent":{"output":"boom","exit_code":1},"details":{"diff":"+a"},"isError":true}""",
        )!!
        assertEquals("boom", result.text)
        assertEquals(1, result.structured?.int("exit_code"))
        assertEquals("+a", result.details?.str("diff"))
        assertTrue(result.isError)
    }

    @Test
    fun `json string primitive becomes text`() {
        assertEquals("some text", parseToolResult("\"some text\"")!!.text)
    }

    @Test
    fun `truncated json is returned verbatim`() {
        val raw = """{"content":[{"type":"text","text":"cut"""
        val result = parseToolResult(raw)!!
        assertEquals(raw, result.text)
        assertTrue(result.images.isEmpty())
        assertNull(result.details)
        assertNull(result.structured)
        assertFalse(result.isError)
    }

    @Test
    fun `object without content is returned verbatim`() {
        val raw = """{"output":"plain"}"""
        val result = parseToolResult(raw)!!
        assertEquals(raw, result.text)
        assertNull(result.structured)
    }

    @Test
    fun `null result is null`() {
        assertNull(parseToolResult(null))
    }

    @Test
    fun `args object is parsed`() {
        val args = parseToolArgs("""{"command":"ls","timeout":30}""")!!
        assertEquals("ls", args.str("command"))
        assertEquals(30, args.int("timeout"))
        assertNull(args.obj("command"))
    }

    @Test
    fun `args that are not an object are rejected`() {
        assertNull(parseToolArgs("[1,2]"))
        assertNull(parseToolArgs("\"text\""))
    }

    @Test
    fun `invalid args json is rejected`() {
        assertNull(parseToolArgs("""{"command":"ls"""))
    }

    @Test
    fun `null args are rejected`() {
        assertNull(parseToolArgs(null))
    }

    @Test
    fun `image byte size is the decoded length`() {
        assertEquals(3, ToolImage("image/png", "QUJD").byteSize())
    }
}
