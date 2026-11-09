package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BashToolTest {
    private val success = """
        {"content":[{"type":"text","text":"ok\n0\n"}],"structuredContent":{"output":"ok\n0\n"}}
    """.trimIndent()

    private val failed = """
        {"content":[{"type":"text","text":"ok\n0\n\n\nCommand exited with code 1"}],
         "structuredContent":{"output":"ok\n0\n","truncated":false,"exit_code":1,"wall_time_seconds":3.1},
         "isError":true}
    """.trimIndent()

    private fun tool(
        args: String? = """{"command":"ls"}""",
        output: String? = null,
        status: ToolStatus = ToolStatus.DONE,
    ) = PiItem.Tool(
        id = "item",
        callId = "call",
        name = "bash",
        args = args,
        output = output,
        status = status,
        durationMs = 3,
        truncated = false,
        ts = 0,
    )

    @Test
    fun `strips a plain cd prefix`() {
        assertEquals(BashCommand("/a", "ls"), splitCdPrefix("cd /a && ls"))
    }

    @Test
    fun `strips a quoted cd prefix`() {
        assertEquals(BashCommand("/a b", "ls"), splitCdPrefix("cd '/a b' && ls"))
        assertEquals(BashCommand("/a b", "ls"), splitCdPrefix("cd \"/a b\" && ls"))
    }

    @Test
    fun `strips a semicolon cd prefix`() {
        assertEquals(BashCommand("/a", "ls"), splitCdPrefix("cd /a; ls"))
    }

    @Test
    fun `leaves a command without a prefix alone`() {
        assertEquals(BashCommand(null, "ls"), splitCdPrefix("ls"))
    }

    @Test
    fun `leaves a bare cd alone`() {
        assertEquals(BashCommand(null, "cd /a"), splitCdPrefix("cd /a"))
    }

    @Test
    fun `strips the prefix of a multi-line command`() {
        assertEquals(BashCommand("/a", "ls\nfoo"), splitCdPrefix("cd /a && ls\nfoo"))
    }

    @Test
    fun `reads output and exit code from a successful envelope`() {
        val result = parseToolResult(success)
        assertEquals("ok\n0\n", bashOutput(result))
        assertNull(bashExitCode(result))
    }

    @Test
    fun `reads output and exit code from a failed envelope`() {
        val result = parseToolResult(failed)
        assertEquals("ok\n0\n", bashOutput(result))
        assertEquals(1, bashExitCode(result))
    }

    @Test
    fun `falls back to a plain string result`() {
        val result = parseToolResult("""{"content":[{"type":"text","text":"plain"}]}""")
        assertEquals("plain", bashOutput(result))
        assertNull(bashExitCode(result))
    }

    @Test
    fun `returns null without a result`() {
        assertNull(bashOutput(null))
        assertNull(bashExitCode(null))
    }

    @Test
    fun `summarises a successful command`() {
        val item = tool(args = """{"command":"cd /a && ls -la"}""", output = success)
        assertEquals("$ ls -la", bashSummary(item))
    }

    @Test
    fun `summarises a failing command with its exit code`() {
        val item = tool(args = """{"command":"cd /a && ls"}""", output = failed, status = ToolStatus.ERROR)
        assertEquals("$ ls · exit 1", bashSummary(item))
    }

    @Test
    fun `summarises a running command without output`() {
        val item = tool(args = """{"command":"cd /a && ls"}""", output = null, status = ToolStatus.RUNNING)
        assertEquals("$ ls", bashSummary(item))
    }

    @Test
    fun `marks a timed out command`() {
        val output = """{"content":[{"type":"text","text":"Command timed out after 30s"}],"isError":true}"""
        val item = tool(args = """{"command":"sleep 60","timeout":30}""", output = output, status = ToolStatus.ERROR)
        assertEquals("$ sleep 60 · timed out", bashSummary(item))
    }
}
