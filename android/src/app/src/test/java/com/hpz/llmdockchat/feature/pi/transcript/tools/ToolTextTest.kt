package com.hpz.llmdockchat.feature.pi.transcript.tools

import org.junit.Assert.assertEquals
import org.junit.Test

class ToolTextTest {
    @Test
    fun keepsOnlyTheFirstLine() {
        assertEquals("first line", firstCollapsedLine("first line\nsecond line"))
    }

    @Test
    fun collapsesWhitespaceAndTrims() {
        assertEquals("a b c", firstCollapsedLine("  a \t b   c  \r\nnext"))
    }

    @Test
    fun emptyTextGivesEmptyString() {
        assertEquals("", firstCollapsedLine(""))
    }
}
