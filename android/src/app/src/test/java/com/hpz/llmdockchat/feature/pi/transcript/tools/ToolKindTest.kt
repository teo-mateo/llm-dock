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
    fun `each chatterbox tool has its own kind`() {
        assertEquals(ToolKind.CHATTERBOX_SEND, classifyTool("chatterbox_send"))
        assertEquals(ToolKind.CHATTERBOX_LOOK, classifyTool("chatterbox_look"))
        assertEquals(ToolKind.CHATTERBOX_JOIN, classifyTool("chatterbox_join"))
        assertEquals(ToolKind.CHATTERBOX_LEAVE, classifyTool("chatterbox_leave"))
    }

    @Test
    fun `unknown names map to generic`() {
        assertEquals(ToolKind.GENERIC, classifyTool("bash="))
        assertEquals(ToolKind.GENERIC, classifyTool("codemode"))
        assertEquals(ToolKind.GENERIC, classifyTool("chatterbox"))
        assertEquals(ToolKind.GENERIC, classifyTool(""))
    }
}
