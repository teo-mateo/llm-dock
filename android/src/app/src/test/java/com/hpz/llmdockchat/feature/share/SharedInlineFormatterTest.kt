package com.hpz.llmdockchat.feature.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The inline file format must match the web's `ChatInput.jsx` `buildMessage`:
 * `**Attached file: \`name\`**` plus a fenced code block, fence-picked so
 * content containing backticks never breaks it (F14-R3).
 */
class SharedInlineFormatterTest {

    @Test
    fun `a text file becomes a fenced block with the file name`() {
        val out = SharedInlineFormatter.inlineFile("notes.txt", "line one\nline two")
        assertEquals(
            "**Attached file: `notes.txt`**\n\n```txt\nline one\nline two\n```",
            out,
        )
    }

    @Test
    fun `markdown files fence with the markdown language hint`() {
        val out = SharedInlineFormatter.inlineFile("readme.md", "# Title")
        assertTrue(out.contains("```markdown\n# Title\n```"))
    }

    @Test
    fun `content containing backticks still fences cleanly, matching pickFence`() {
        val content = "a `b` c"
        val out = SharedInlineFormatter.inlineFile("tick.txt", content)
        // The longest run in "a `b` c" is one backtick; the fence is the
        // web's max(3, longest + 1) = 3, which the single backticks don't break.
        assertTrue(out.contains("\n```txt\na `b` c\n```"))
    }

    @Test
    fun `a file over the inline cap is truncated with the web's marker`() {
        val big = "x".repeat(SharedKindParser.MAX_INLINE_BYTES + 100)
        val out = SharedInlineFormatter.inlineFile("big.log", big)
        assertTrue(out.contains(" (truncated to ${SharedKindParser.MAX_INLINE_BYTES} bytes)"))
        // The content itself is capped at MAX_INLINE_BYTES chars, like the web.
        val content = out.substringAfter("\n\n").substringAfter("\n").substringBeforeLast("\n")
        assertEquals(SharedKindParser.MAX_INLINE_BYTES, content.length)
    }

    @Test
    fun `a file under the cap is not marked truncated`() {
        val out = SharedInlineFormatter.inlineFile("small.txt", "tiny")
        assertFalse(out.contains("truncated"))
    }

    @Test
    fun `pickFence matches the web - three backticks when content is clean`() {
        assertEquals("```", SharedInlineFormatter.pickFence("plain text"))
    }

    @Test
    fun `pickFence matches the web - max of three and one past the longest run`() {
        // A single backtick does not grow the fence (web: max(3, longest + 1)).
        assertEquals("```", SharedInlineFormatter.pickFence("`"))
        // A run of five grows it to six.
        assertEquals("``````", SharedInlineFormatter.pickFence("`````"))
    }
}
