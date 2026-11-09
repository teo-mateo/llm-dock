package com.hpz.llmdockchat.feature.pi.transcript.tools

import org.junit.Assert.assertEquals
import org.junit.Test

class ToolPathsTest {
    @Test
    fun `splits an absolute path`() {
        assertEquals(SplitPath("/a/b/", "c.kt"), splitPath("/a/b/c.kt"))
    }

    @Test
    fun `splits a bare file name`() {
        assertEquals(SplitPath("", "c.kt"), splitPath("c.kt"))
    }

    @Test
    fun `splits a trailing directory`() {
        assertEquals(SplitPath("/a/b/", ""), splitPath("/a/b/"))
    }

    @Test
    fun `splits the root`() {
        assertEquals(SplitPath("/", ""), splitPath("/"))
    }
}
