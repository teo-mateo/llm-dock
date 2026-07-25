package com.hpz.llmdockchat.data.model

import org.junit.Assert.assertEquals
import org.junit.Test

/** [classifyLogLevel] — pattern matching over unstructured lines (F12-R4). Never touches the text. */
class LogLevelTest {

    @Test
    fun `ERROR, CRITICAL and traceback lines classify as error`() {
        assertEquals(LogLevel.ERROR, classifyLogLevel("2026-07-25 ERROR api_server.py:1487 failed to bind"))
        assertEquals(LogLevel.ERROR, classifyLogLevel("CRITICAL: out of memory"))
        assertEquals(LogLevel.ERROR, classifyLogLevel("Traceback (most recent call last):"))
    }

    @Test
    fun `WARN and WARNING both classify as warn`() {
        assertEquals(LogLevel.WARN, classifyLogLevel("WARN cudagraph capture may add ~1.2 GiB"))
        assertEquals(LogLevel.WARN, classifyLogLevel("2026-07-25 12:00:00 WARNING: retrying"))
    }

    @Test
    fun `INFO classifies as info`() {
        assertEquals(LogLevel.INFO, classifyLogLevel("INFO api_server.py:1487 vLLM API server version 0.24.0"))
    }

    @Test
    fun `a line matching nothing degrades to plain, not a crash`() {
        assertEquals(LogLevel.PLAIN, classifyLogLevel("Loading safetensors shards:  33% 3/9"))
        assertEquals(LogLevel.PLAIN, classifyLogLevel(""))
    }

    @Test
    fun `a word merely containing INFO, like informant, does not match on substring`() {
        assertEquals(LogLevel.PLAIN, classifyLogLevel("the informant provided a tip"))
    }

    @Test
    fun `error takes priority over a warn mentioned in the same line`() {
        assertEquals(LogLevel.ERROR, classifyLogLevel("WARN: retrying after ERROR from upstream"))
    }
}
