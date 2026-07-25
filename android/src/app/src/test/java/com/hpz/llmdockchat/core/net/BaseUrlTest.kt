package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BaseUrlTest {

    private fun normalized(raw: String): String {
        val result = BaseUrl.normalize(raw)
        assertTrue("expected $raw to normalize, got $result", result is BaseUrlResult.Valid)
        return (result as BaseUrlResult.Valid).baseUrl.value
    }

    @Test
    fun `emulator host survives untouched`() {
        assertEquals("http://10.0.2.2:3399", normalized("http://10.0.2.2:3399"))
    }

    @Test
    fun `surrounding whitespace is absorbed`() {
        assertEquals("http://10.0.2.2:3399", normalized("  http://10.0.2.2:3399\n"))
    }

    @Test
    fun `trailing slashes are stripped`() {
        assertEquals("http://10.0.2.2:3399", normalized("http://10.0.2.2:3399/"))
        assertEquals("http://10.0.2.2:3399", normalized("http://10.0.2.2:3399///"))
    }

    @Test
    fun `an api suffix the user pasted is stripped`() {
        assertEquals("http://10.0.2.2:3399", normalized("http://10.0.2.2:3399/api"))
        assertEquals("http://10.0.2.2:3399", normalized("http://10.0.2.2:3399/api/"))
        assertEquals("https://dock.example.com", normalized("https://dock.example.com/API"))
    }

    @Test
    fun `a missing scheme defaults to http`() {
        assertEquals("http://10.0.2.2:3399", normalized("10.0.2.2:3399"))
        assertEquals("http://dock.lan", normalized("dock.lan"))
    }

    @Test
    fun `https keeps its scheme and drops its default port`() {
        assertEquals("https://dock.example.com", normalized("https://dock.example.com"))
        assertEquals("https://dock.example.com", normalized("https://dock.example.com:443"))
        assertEquals("https://dock.example.com:8443", normalized("https://dock.example.com:8443"))
    }

    @Test
    fun `host case is normalised`() {
        assertEquals("http://dock.lan:3399", normalized("HTTP://Dock.LAN:3399"))
    }

    @Test
    fun `a reverse proxy path prefix is preserved`() {
        assertEquals("https://example.com/llmdock", normalized("https://example.com/llmdock/api/"))
    }

    @Test
    fun `blank and unparseable input is rejected`() {
        assertTrue(BaseUrl.normalize("") is BaseUrlResult.Invalid)
        assertTrue(BaseUrl.normalize("   ") is BaseUrlResult.Invalid)
        assertTrue(BaseUrl.normalize("http://") is BaseUrlResult.Invalid)
        assertTrue(BaseUrl.normalize("ftp://dock.lan") is BaseUrlResult.Invalid)
    }

    @Test
    fun `resolve builds the same path from either form`() {
        val plain = (BaseUrl.normalize("http://10.0.2.2:3399") as BaseUrlResult.Valid).baseUrl
        val pasted = (BaseUrl.normalize("http://10.0.2.2:3399/api/") as BaseUrlResult.Valid).baseUrl
        assertEquals("http://10.0.2.2:3399/api/health", plain.resolve("/api/health").toString())
        assertEquals("http://10.0.2.2:3399/api/health", pasted.resolve("/api/health").toString())
    }

    @Test
    fun `resolve keeps a proxy path prefix in front of the endpoint`() {
        val proxied = (BaseUrl.normalize("https://example.com/llmdock") as BaseUrlResult.Valid).baseUrl
        assertEquals("https://example.com/llmdock/api/health", proxied.resolve("/api/health").toString())
    }

    @Test
    fun `resolve appends query parameters`() {
        val base = (BaseUrl.normalize("http://10.0.2.2:3399") as BaseUrlResult.Valid).baseUrl
        assertEquals(
            "http://10.0.2.2:3399/api/services/vllm-x/logs?tail=200",
            base.resolve("/api/services/vllm-x/logs", mapOf("tail" to "200")).toString(),
        )
    }

    @Test
    fun `restore round-trips a stored value`() {
        val stored = normalized("http://10.0.2.2:3399/api/")
        assertEquals(stored, BaseUrl.restore(stored)?.value)
    }
}
