package com.hpz.llmdockchat.feature.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Which shared text counts as "a page was shared" . */
class SharedUrlExtractorTest {

    @Test
    fun `a bare link is the shared page`() {
        assertEquals("https://example.com/a", SharedUrlExtractor.firstUrl("https://example.com/a"))
    }

    @Test
    fun `a link inside prose is still the shared page`() {
        val text = "Look at this: https://example.com/x?y=1#z — wild stuff"
        assertEquals("https://example.com/x?y=1#z", SharedUrlExtractor.firstUrl(text))
    }

    @Test
    fun `a title folded above the link keeps the link`() {
        val text = "https://example.com/article\n\nExample Article"
        assertEquals("https://example.com/article", SharedUrlExtractor.firstUrl(text))
    }

    @Test
    fun `the first of several links wins`() {
        assertEquals("https://a.example/1", SharedUrlExtractor.firstUrl("https://a.example/1 then https://b.example/2"))
    }

    @Test
    fun `punctuation a sharer appends is not part of the url`() {
        assertEquals("https://example.com/a", SharedUrlExtractor.firstUrl("see https://example.com/a."))
        assertEquals("https://example.com/a", SharedUrlExtractor.firstUrl("(https://example.com/a)"))
        assertEquals("https://example.com/a", SharedUrlExtractor.firstUrl("link: https://example.com/a,"))
        assertEquals("https://example.com/a", SharedUrlExtractor.firstUrl("[a](https://example.com/a)"))
    }

    @Test
    fun `an uppercase scheme is still a link`() {
        assertEquals("HTTP://example.com/a", SharedUrlExtractor.firstUrl("HTTP://example.com/a"))
    }

    @Test
    fun `a loopback url with a port is a link`() {
        assertEquals("http://localhost:3399/v2", SharedUrlExtractor.firstUrl("http://localhost:3399/v2"))
    }

    @Test
    fun `plain prose is not a link`() {
        assertNull(SharedUrlExtractor.firstUrl("check this out"))
        assertNull(SharedUrlExtractor.firstUrl("example.com/a"))
        assertNull(SharedUrlExtractor.firstUrl("//example.com/a"))
        assertNull(SharedUrlExtractor.firstUrl("ftp://example.com/a"))
    }

    @Test
    fun `a scheme with nothing after it is not a link`() {
        assertNull(SharedUrlExtractor.firstUrl("https://"))
        assertNull(SharedUrlExtractor.firstUrl("go to https:// now"))
    }

    @Test
    fun `blank input yields no link`() {
        assertNull(SharedUrlExtractor.firstUrl(""))
    }
}
