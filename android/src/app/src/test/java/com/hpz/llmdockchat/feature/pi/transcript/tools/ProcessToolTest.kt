package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProcessToolTest {
    private fun tool(args: String?, output: String? = null) = PiItem.Tool(
        id = "item",
        callId = "call",
        name = "process",
        args = args,
        output = output,
        status = ToolStatus.DONE,
        durationMs = 3,
        truncated = false,
        ts = 0,
    )

    private fun info(args: String?, output: String? = null) = processInfo(parseToolArgs(args), parseToolResult(output))

    @Test
    fun `reads a start process block`() {
        val args = """{"action":"start","command":"cd /forgejo/wt/backend && dotnet test HeapzillaMail.sln 2>&1 | tail -40","name":"hzm30-tests"}"""
        val output = """{"content":[{"type":"text","text":"Started process hzm30-tests (proc_4d64) with pid 330487."}],"details":{"action":"start","process":{"id":"proc_4d64","name":"hzm30-tests","pid":330487,"command":"cd /forgejo/wt/backend && dotnet test HeapzillaMail.sln 2>&1 | tail -40","cwd":"/forgejo/heapzilla-mail-checker","status":"running","exitCode":null}}}"""
        val parsed = info(args, output)
        assertEquals("start", parsed.action)
        assertEquals("proc_4d64", parsed.id)
        assertEquals("hzm30-tests", parsed.name)
        assertEquals(330487, parsed.pid)
        assertEquals("running", parsed.status)
        assertNull(parsed.exitCode)
        assertEquals("cd /forgejo/wt/backend && dotnet test HeapzillaMail.sln 2>&1 | tail -40", parsed.command)
        assertEquals("/forgejo/heapzilla-mail-checker", parsed.cwd)
    }

    @Test
    fun `reads output details`() {
        val args = """{"action":"output","id":"proc_4d64","tailLines":45}"""
        val output = """{"content":[{"type":"text","text":"No output yet."}],"details":{"action":"output","id":"proc_4d64","processName":"hzm30-tests","processStatus":"running","tailLines":45}}"""
        val parsed = info(args, output)
        assertEquals("output", parsed.action)
        assertEquals("proc_4d64", parsed.id)
        assertEquals("hzm30-tests", parsed.name)
        assertEquals("running", parsed.status)
        assertNull(parsed.pid)
        assertNull(parsed.exitCode)
        assertNull(parsed.command)
        assertNull(parsed.cwd)
    }

    @Test
    fun `reads a stop with only args`() {
        val parsed = info("""{"action":"stop","id":"proc_4d64"}""")
        assertEquals("stop", parsed.action)
        assertEquals("proc_4d64", parsed.id)
        assertNull(parsed.name)
        assertNull(parsed.pid)
        assertNull(parsed.status)
        assertNull(parsed.exitCode)
    }

    @Test
    fun `reads a stop result info`() {
        val output = """{"content":[{"type":"text","text":"Stopped process hzm351-main-web (proc_e997)."}],"details":{"action":"stop","result":{"ok":true,"info":{"id":"proc_e997","name":"hzm351-main-web","pid":1033315,"command":"cd /forgejo/heapzilla-mail-checker/frontend && npm run dev","cwd":"/forgejo/heapzilla-mail-checker","status":"killed","exitCode":null}}}}"""
        val parsed = info("""{"action":"stop","id":"proc_e997"}""", output)
        assertEquals("stop", parsed.action)
        assertEquals("proc_e997", parsed.id)
        assertEquals("hzm351-main-web", parsed.name)
        assertEquals(1033315, parsed.pid)
        assertEquals("killed", parsed.status)
        assertEquals("/forgejo/heapzilla-mail-checker", parsed.cwd)
    }

    @Test
    fun `tolerates null and unknown details`() {
        val empty = info(null, null)
        assertNull(empty.action)
        assertNull(empty.id)
        assertNull(empty.name)
        assertNull(empty.pid)
        assertNull(empty.status)
        assertNull(empty.exitCode)
        assertNull(empty.command)
        assertNull(empty.cwd)

        val output = """{"content":[{"type":"text","text":"ok"}],"details":{"weird":true}}"""
        val parsed = info("""{"action":"output","id":"proc_x"}""", output)
        assertEquals("output", parsed.action)
        assertEquals("proc_x", parsed.id)
        assertNull(parsed.name)
        assertNull(parsed.status)
    }

    @Test
    fun `maps status tones`() {
        assertEquals(ProcessStatusTone.RUNNING, processStatusTone("running", null))
        assertEquals(ProcessStatusTone.SUCCESS, processStatusTone("exited", 0))
        assertEquals(ProcessStatusTone.SUCCESS, processStatusTone("success", null))
        assertEquals(ProcessStatusTone.FAILURE, processStatusTone("failed", null))
        assertEquals(ProcessStatusTone.FAILURE, processStatusTone("killed", null))
        assertEquals(ProcessStatusTone.FAILURE, processStatusTone("exited", 1))
        assertEquals(ProcessStatusTone.NEUTRAL, processStatusTone(null, 0))
        assertEquals(ProcessStatusTone.NEUTRAL, processStatusTone("queued", null))
    }

    @Test
    fun `summarizes a start`() {
        val args = """{"action":"start","command":"cd /forgejo/wt/backend && dotnet test HeapzillaMail.sln 2>&1 | tail -40","name":"hzm30-tests"}"""
        val output = """{"content":[{"type":"text","text":"Started process."}],"details":{"action":"start","process":{"name":"hzm30-tests","status":"running","exitCode":null}}}"""
        assertEquals(
            "start hzm30-tests · dotnet test HeapzillaMail.sln 2>&1 | tail -40 · running",
            processSummary(tool(args, output)),
        )
    }

    @Test
    fun `summarizes a stop`() {
        assertEquals("stop proc_4d64", processSummary(tool("""{"action":"stop","id":"proc_4d64"}""")))
    }

    @Test
    fun `summarizes an output`() {
        val args = """{"action":"output","id":"proc_4d64","tailLines":45}"""
        val output = """{"content":[{"type":"text","text":"No output yet."}],"details":{"action":"output","id":"proc_4d64","processName":"hzm30-tests","processStatus":"running"}}"""
        assertEquals("output hzm30-tests · running", processSummary(tool(args, output)))
    }

    @Test
    fun `summarizes a list`() {
        assertEquals("list", processSummary(tool("""{"action":"list"}""")))
    }

    @Test
    fun `falls back for an unknown action`() {
        assertEquals("action=spawn · name=x", processSummary(tool("""{"action":"spawn","name":"x"}""")))
    }

    @Test
    fun `reports a non-zero exit`() {
        val args = """{"action":"start","command":"echo hi","name":"demo"}"""
        val output = """{"content":[{"type":"text","text":"Started."}],"details":{"action":"start","process":{"name":"demo","status":"exited","exitCode":1}}}"""
        assertEquals("start demo · echo hi · exited · exit 1", processSummary(tool(args, output)))
    }
}
