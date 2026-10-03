package com.hpz.llmdockchat.feature.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The prepared summarize turn and the label it is offered under. */
class SummarizeMessageTest {

    private val url = "https://example.com/a/b?x=1#frag"
    private val message = SummarizeMessage.build(url)

    @Test
    fun `the url is carried verbatim, exactly once`() {
        assertEquals(1, Regex("https://example\\.com/a/b\\?x=1#frag").findAll(message).count())
    }

    @Test
    fun `the contract forbids answering without the fetch`() {
        assertTrue(message.contains("not summarise from the URL, the site name, or prior knowledge."))
        assertTrue(message.contains("say exactly which of those happened"))
    }

    /** Nothing may assume this install's server or tool names. */
    @Test
    fun `no tool or server name is baked into the turn`() {
        listOf("webfetch", "websearch", "browser-fetch", "fetch_readable", "ragflow").forEach {
            assertFalse("message must not name $it", message.contains(it))
        }
    }

    @Test
    fun `the label names the host, not the whole url`() {
        assertEquals("example.com", SummarizeMessage.domain(url))
        assertEquals("example.com", SummarizeMessage.domain("https://example.com"))
        assertEquals("localhost", SummarizeMessage.domain("http://localhost:3399/v2"))
        assertEquals("this page", SummarizeMessage.domain("not a url"))
    }
}
