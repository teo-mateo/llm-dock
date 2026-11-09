package com.hpz.llmdockchat.feature.pi.transcript.tools

import org.junit.Assert.assertEquals
import org.junit.Test

class ToolKindTest {
    @Test
    fun `wire names map to their kind`() {
        assertEquals(ToolKind.BASH, classifyTool("bash"))
        assertEquals(ToolKind.EDIT, classifyTool("edit"))
        assertEquals(ToolKind.READ, classifyTool("read"))
        assertEquals(ToolKind.WRITE, classifyTool("write"))
        assertEquals(ToolKind.PROCESS, classifyTool("process"))
    }

    @Test
    fun `chatterbox tools share one kind`() {
        assertEquals(ToolKind.CHATTERBOX, classifyTool("chatterbox_send"))
        assertEquals(ToolKind.CHATTERBOX, classifyTool("chatterbox_look"))
        assertEquals(ToolKind.CHATTERBOX, classifyTool("chatterbox_join"))
        assertEquals(ToolKind.CHATTERBOX, classifyTool("chatterbox_leave"))
    }

    @Test
    fun `unknown names map to generic`() {
        assertEquals(ToolKind.GENERIC, classifyTool("bash="))
        assertEquals(ToolKind.GENERIC, classifyTool("codemode"))
        assertEquals(ToolKind.GENERIC, classifyTool(""))
    }
}
