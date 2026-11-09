package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EditToolTest {
    private val patch = """
        --- /forgejo/wt/AccountView.cs
        +++ /forgejo/wt/AccountView.cs
        @@ -1,5 +1,6 @@
         using HeapzillaMail.Api.Attachments;
        +using HeapzillaMail.Core.Models;
         
         namespace HeapzillaMail.Api.Accounts;
         
         /// <summary>
    """.trimIndent()

    private val successResult = """
        {"content":[{"type":"text","text":"Successfully replaced 1 block(s) in /forgejo/wt-hzm-accounts-crud/backend/src/HeapzillaMail.Api/Accounts/AccountView.cs."}],
         "details":{"diff":"1: using","patch":${jsonString(patch)},"firstChangedLine":2}}
    """.trimIndent()

    private val errorResult = """
        {"content":[{"type":"text","text":"Could not find the exact text in /forgejo/wt-hzm-accounts-edit/frontend/src/queries.ts. The old text must match exactly including all whitespace and newlines."}],"details":{}}
    """.trimIndent()

    private fun tool(
        args: String? = """{"path":"/forgejo/wt-hzm-74/frontend/src/api.ts","edits":[{"oldText":"a","newText":"a\nb"}]}""",
        output: String? = null,
        status: ToolStatus = ToolStatus.DONE,
    ) = PiItem.Tool(
        id = "item",
        callId = "call",
        name = "edit",
        args = args,
        output = output,
        status = status,
        durationMs = 3,
        truncated = false,
        ts = 0,
    )

    @Test
    fun `parses kinds in order`() {
        val lines = parsePatch(patch)
        assertEquals(
            listOf(DiffKind.HEADER, DiffKind.HEADER, DiffKind.HUNK, DiffKind.CONTEXT, DiffKind.ADD, DiffKind.CONTEXT, DiffKind.CONTEXT, DiffKind.CONTEXT, DiffKind.CONTEXT),
            lines.map { it.kind },
        )
    }

    @Test
    fun `strips the line markers`() {
        val lines = parsePatch(patch)
        assertEquals("using HeapzillaMail.Api.Attachments;", lines[3].text)
        assertEquals("using HeapzillaMail.Core.Models;", lines[4].text)
        assertEquals("", lines[5].text)
    }

    @Test
    fun `stats count adds and removes`() {
        assertEquals(1 to 0, editStats(parsePatch(patch)))
    }

    @Test
    fun `an empty patch has no lines`() {
        assertTrue(parsePatch("").isEmpty())
    }

    @Test
    fun `success summary shows the file name and the counts`() {
        assertEquals("api.ts +1 −0", editSummary(tool(output = successResult)))
    }

    @Test
    fun `error summary shows failed`() {
        assertEquals("api.ts · failed", editSummary(tool(output = errorResult, status = ToolStatus.ERROR)))
    }

    @Test
    fun `running summary shows only the file name`() {
        assertEquals("api.ts", editSummary(tool(output = null, status = ToolStatus.RUNNING)))
    }

    @Test
    fun `summary falls back to the args when there is no path`() {
        assertEquals("foo=bar", editSummary(tool(args = """{"foo":"bar"}""")))
    }

    @Test
    fun `fallback diff renders each edit block`() {
        val args = parseToolArgs(
            """{"path":"/a/b/c.kt","edits":[{"oldText":"a\nb","newText":"a\nb\nc"},{"oldText":"x","newText":"y"}]}""",
        )
        val lines = fallbackDiff(args)
        assertEquals(
            listOf(
                DiffKind.HUNK to "edit 1",
                DiffKind.REMOVE to "a",
                DiffKind.REMOVE to "b",
                DiffKind.ADD to "a",
                DiffKind.ADD to "b",
                DiffKind.ADD to "c",
                DiffKind.HUNK to "edit 2",
                DiffKind.REMOVE to "x",
                DiffKind.ADD to "y",
            ),
            lines.map { it.kind to it.text },
        )
    }

    @Test
    fun `fallback diff tolerates a missing edits list`() {
        assertTrue(fallbackDiff(parseToolArgs("""{"path":"/a/b/c.kt"}""")).isEmpty())
        assertTrue(fallbackDiff(null).isEmpty())
    }

    private fun jsonString(value: String): String =
        "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""
}
