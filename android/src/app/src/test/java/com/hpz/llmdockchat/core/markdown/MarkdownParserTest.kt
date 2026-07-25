package com.hpz.llmdockchat.core.markdown

import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import com.hpz.llmdockchat.core.ui.theme.DarkLlmColors
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F05-R1/R2/R5/R7's hand-rolled block parser (`MarkdownParser.kt`). Every
 * construct, its unterminated form, LaTeX passthrough and non-Markdown text
 * are exercised here — logic criteria backed by a JVM test, per
 * `WORK_INSTRUCTIONS.md` §7.
 */
class MarkdownParserTest {

    private val colors = DarkLlmColors
    private fun block(raw: String) = parseMdBlock(raw, colors)
    private fun blocksOf(text: String) = splitMdBlocks(text).map { block(it) }

    // -- headings ------------------------------------------------------------

    @Test
    fun `ATX headings of every level parse with their text`() {
        assertEquals(1, (block("# Title") as MdBlock.Heading).level)
        assertEquals("Title", (block("# Title") as MdBlock.Heading).text.text)
        assertEquals(3, (block("### Sub") as MdBlock.Heading).level)
    }

    // -- emphasis --------------------------------------------------------------

    @Test
    fun `bold and italic apply the expected span styles`() {
        val bold = parseInline("this is **bold** text", colors)
        assertEquals("this is bold text", bold.text)
        assertTrue(bold.spanStyles.any { it.item.fontWeight == FontWeight.Bold && bold.text.substring(it.start, it.end) == "bold" })

        val italic = parseInline("this is *italic* text", colors)
        assertEquals("this is italic text", italic.text)
        assertTrue(italic.spanStyles.any { it.item.fontStyle == FontStyle.Italic && italic.text.substring(it.start, it.end) == "italic" })
    }

    @Test
    fun `underscore emphasis works the same as asterisks`() {
        val bold = parseInline("__bold__ and _italic_", colors)
        assertEquals("bold and italic", bold.text)
        assertTrue(bold.spanStyles.any { it.item.fontWeight == FontWeight.Bold })
        assertTrue(bold.spanStyles.any { it.item.fontStyle == FontStyle.Italic })
    }

    @Test
    fun `an unterminated bold marker falls back to literal asterisks, nothing lost`() {
        val text = parseInline("Value is **bold text without close", colors)
        assertEquals("Value is **bold text without close", text.text)
        assertTrue(text.spanStyles.none { it.item.fontWeight == FontWeight.Bold })
    }

    @Test
    fun `an unterminated inline code backtick falls back to literal text`() {
        val text = parseInline("here is `code without close", colors)
        assertEquals("here is `code without close", text.text)
    }

    // -- inline code -----------------------------------------------------------

    @Test
    fun `inline code is preserved verbatim including special characters`() {
        val text = parseInline("run `git diff --stat` now", colors)
        assertEquals("run git diff --stat now", text.text)
    }

    // -- links -------------------------------------------------------------

    @Test
    fun `a markdown link renders its text and carries the url`() {
        val text = parseInline("see [the docs](https://example.com/path) for more", colors)
        assertEquals("see the docs for more", text.text)
        val annotations = text.getLinkAnnotations(0, text.length)
        assertEquals(1, annotations.size)
    }

    @Test
    fun `an unclosed link bracket falls back to literal text, nothing lost`() {
        val text = parseInline("this [is not a link at all", colors)
        assertEquals("this [is not a link at all", text.text)
    }

    // -- lists ---------------------------------------------------------------

    @Test
    fun `unordered and ordered list items parse with their depth`() {
        val list = block("- one\n- two\n  - nested") as MdBlock.ListBlock
        assertEquals(3, list.items.size)
        assertEquals("one", list.items[0].text.text)
        assertFalse(list.items[0].ordered)
        assertEquals(1, list.items[2].depth)

        val ordered = block("1. first\n2. second") as MdBlock.ListBlock
        assertTrue(ordered.items[0].ordered)
        assertEquals(1, ordered.items[0].index)
        assertEquals(2, ordered.items[1].index)
    }

    @Test
    fun `nested lists at multiple depths keep their own indentation`() {
        val list = block("- top\n  - mid\n    - deep") as MdBlock.ListBlock
        assertEquals(listOf(0, 1, 2), list.items.map { it.depth })
    }

    // -- blockquote ------------------------------------------------------------

    @Test
    fun `a blockquote strips the marker but keeps the text`() {
        val quote = block("> line one\n> line two") as MdBlock.Quote
        assertEquals(listOf("line one", "line two"), quote.lines.map { it.text })
    }

    // -- horizontal rule ---------------------------------------------------

    @Test
    fun `three or more dashes alone is a rule`() {
        assertTrue(block("---") is MdBlock.Rule)
        assertTrue(block("***") is MdBlock.Rule)
    }

    // -- fenced code -----------------------------------------------------------

    @Test
    fun `a closed fenced code block carries its language and exact body`() {
        val code = block("```python\nprint(1)\nprint(2)\n```") as MdBlock.CodeBlock
        assertEquals("python", code.language)
        assertEquals("print(1)\nprint(2)", code.code)
        assertTrue(code.closed)
    }

    @Test
    fun `an open fence with no closing marker still renders as a code block, not raw text`() {
        // The mid-stream case (F05-R1's second criterion): the fence opened but
        // has not closed yet. It must already be a CodeBlock, not a Paragraph
        // that later flips — that flip is exactly the flicker the spec forbids.
        val code = block("```python\nprint(1)\nstill typ") as MdBlock.CodeBlock
        assertEquals("python", code.language)
        assertEquals("print(1)\nstill typ", code.code)
        assertFalse(code.closed)
    }

    @Test
    fun `code block content is exact, no reformatting or stripped indentation`() {
        val code = block("```\n    indented line\n\ttabbed\n```") as MdBlock.CodeBlock
        assertEquals("    indented line\n\ttabbed", code.code)
    }

    // -- tables (F05-R5) -----------------------------------------------------

    @Test
    fun `a well-formed table parses its header, alignment and rows`() {
        val table = block("| A | B |\n|---|:-:|\n| 1 | 2 |") as MdBlock.Table
        assertEquals(listOf("A", "B"), table.header.map { it.text })
        assertEquals(listOf(TableAlign.LEFT, TableAlign.CENTER), table.alignments)
        assertEquals(listOf(listOf("1", "2")), table.rows.map { row -> row.map { it.text } })
    }

    @Test
    fun `a ragged row is padded rather than crashing the block`() {
        val table = block("| A | B | C |\n|---|---|---|\n| 1 |") as MdBlock.Table
        assertEquals(listOf("1", "", ""), table.rows[0].map { it.text })
    }

    @Test
    fun `a bare pipe mid-sentence does not fracture the paragraph around it`() {
        // Review fix S3: conditional-probability notation is exactly the kind
        // of thing this rig's models write, and a single `|` is not a table.
        val text = "The result is P(A|B) using Bayes' theorem, which is useful."
        val blocks = blocksOf(text)
        assertEquals(1, blocks.size)
        assertEquals(text, (blocks[0] as MdBlock.Paragraph).text.text)
    }

    @Test
    fun `a real table still forms even with edge pipes and multiple columns`() {
        // The stricter check must not regress genuine tables: an edge `|` or
        // 2+ columns is still enough signal on its own.
        assertTrue(block("| A | B |\n|---|---|") is MdBlock.Table)
        assertTrue(block("A|B|C\n-|-|-") is MdBlock.Table)
    }

    @Test
    fun `a header row with no delimiter yet is plain text, not a broken table`() {
        // Before the second (delimiter) line has arrived, this must not be
        // rendered as a table — and once it never arrives, it is ordinary text.
        val result = block("| A | B |")
        assertTrue(result is MdBlock.Paragraph || result is MdBlock.CodeBlock)
    }

    // -- maths passthrough (F05-R7) --------------------------------------------

    @Test
    fun `inline math with underscores, asterisks and backslashes survives intact`() {
        val source = "the loss is \$\\frac{\\partial L}{\\partial \\theta} = \\sum_i x_i^2 * \\alpha_i\$ here"
        val text = parseInline(source, colors)
        assertTrue(text.text.contains("\\frac{\\partial L}{\\partial \\theta} = \\sum_i x_i^2 * \\alpha_i"))
        // Nothing was consumed as bold/italic despite the `*` inside the span.
        assertTrue(text.spanStyles.none { it.item.fontWeight == FontWeight.Bold || it.item.fontStyle == FontStyle.Italic })
    }

    @Test
    fun `a block dollar-dollar formula round-trips as literal source`() {
        val source = "$$\\sum_{i=0}^n x_i * \\alpha_i \\\\ \\text{next line}$$"
        val result = block(source) as MdBlock.MathBlock
        assertEquals(source, result.source)
    }

    @Test
    fun `an unterminated inline math span is not silently stripped`() {
        val text = parseInline("partial formula \$x_i^2 with no close", colors)
        assertTrue(text.text.contains("x_i^2 with no close"))
    }

    @Test
    fun `plain currency text with two dollar signs is not lost even if mis-tagged as math`() {
        val text = parseInline("costs \$5 and \$10 today", colors)
        assertEquals("costs \$5 and \$10 today", text.text)
    }

    // -- non-markdown / prefix stability --------------------------------------

    @Test
    fun `CRLF line endings do not break list detection`() {
        // Review fix S4: `split("\n")` leaves a trailing `\r` that fails
        // `matches()` on the list regexes, collapsing every item into one
        // paragraph. A backend on this rig is unlikely to emit CRLF, but it
        // costs one line to normalise. Goes through `splitMdBlocks` (not
        // `parseMdBlock` directly) since that is where the normalisation
        // lives, matching how `MarkdownBody` actually calls this pipeline.
        val list = blocksOf("- item one\r\n- item two\r").single() as MdBlock.ListBlock
        assertEquals(listOf("item one", "item two"), list.items.map { it.text.text })
    }

    @Test
    fun `a CRLF blockquote carries no stray carriage return in its text`() {
        val quote = blocksOf("> line one\r\n> line two\r").single() as MdBlock.Quote
        assertEquals(listOf("line one", "line two"), quote.lines.map { it.text })
    }

    @Test
    fun `plain text with no markdown constructs renders unchanged, nothing lost`() {
        val plain = "Just a normal sentence with no special characters at all."
        val blocks = blocksOf(plain)
        assertEquals(1, blocks.size)
        assertEquals(plain, (blocks[0] as MdBlock.Paragraph).text.text)
    }

    @Test
    fun `splitting is prefix-stable — earlier blocks are byte-identical as the text grows`() {
        val before = "First paragraph.\n\nSecond paragraph starts here"
        val after = before + " and keeps going with more words."
        val blocksBefore = splitMdBlocks(before)
        val blocksAfter = splitMdBlocks(after)
        assertEquals(2, blocksBefore.size)
        assertEquals(2, blocksAfter.size)
        // The closed first block is untouched by what streams in after it.
        assertEquals(blocksBefore[0], blocksAfter[0])
    }

    @Test
    fun `a table forming across deltas reclassifies once, not on every delta`() {
        val headerOnly = splitMdBlocks("| A | B |")
        val withDelimiter = splitMdBlocks("| A | B |\n|---|---|")
        val withRow = splitMdBlocks("| A | B |\n|---|---|\n| 1 | 2 |")
        assertTrue(block(headerOnly.last()) !is MdBlock.Table)
        assertTrue(block(withDelimiter.last()) is MdBlock.Table)
        assertTrue(block(withRow.last()) is MdBlock.Table)
    }
}
