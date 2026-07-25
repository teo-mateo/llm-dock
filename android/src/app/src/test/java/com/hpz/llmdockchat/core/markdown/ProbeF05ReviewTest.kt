package com.hpz.llmdockchat.core.markdown

import com.hpz.llmdockchat.core.ui.theme.DarkLlmColors
import org.junit.Test

/**
 * Scratch probes for the F05 review — not part of the feature's test suite.
 * Prints observations to stdout; no assertions, so it can't fail a real run.
 */
class ProbeF05ReviewTest {

    private val colors = DarkLlmColors

    @Test
    fun `probe - pipe character mid-paragraph`() {
        val text = "The classifier estimates\nP(A|B) using Bayes' theorem\nand returns a probability."
        val blocks = splitMdBlocks(text)
        println("PROBE pipe-mid-paragraph blocks=${blocks.size}")
        blocks.forEachIndexed { i, b -> println("  block[$i]=${b.replace("\n", "\\n")}") }
    }

    @Test
    fun `probe - CRLF line endings`() {
        val text = "# Heading\r\n\r\nSome *bold-ish* text with a line\r\nthat wraps.\r\n"
        val blocks = splitMdBlocks(text)
        println("PROBE crlf blocks=${blocks.size}")
        blocks.forEach { raw ->
            val parsed = parseMdBlock(raw, colors)
            println("  raw=${raw.replace("\r", "\\r").replace("\n", "\\n")} -> $parsed")
            if (parsed is MdBlock.Paragraph) println("  text=[${parsed.text.text}] length=${parsed.text.text.length}")
        }
    }

    @Test
    fun `probe - CRLF in list and quote`() {
        val list = "- item one\r\n- item two\r\n"
        val listBlocks = splitMdBlocks(list)
        listBlocks.forEach { raw ->
            val parsed = parseMdBlock(raw, colors)
            println("PROBE list raw=[${raw.replace("\r", "\\r").replace("\n", "\\n")}] parsed=$parsed")
            if (parsed is MdBlock.ListBlock) parsed.items.forEach { println("  item text=[${it.text.text}] len=${it.text.text.length}") }
        }
        val quote = "> line one\r\n> line two\r\n"
        val quoteBlocks = splitMdBlocks(quote)
        quoteBlocks.forEach { raw ->
            val parsed = parseMdBlock(raw, colors)
            println("PROBE quote raw=[${raw.replace("\r", "\\r").replace("\n", "\\n")}] parsed=$parsed")
            if (parsed is MdBlock.Quote) parsed.lines.forEach { println("  quote line=[${it.text}] len=${it.text.length}") }
        }
    }

    @Test
    fun `probe - stray markdown chars content loss check`() {
        val samples = listOf(
            "stray chars: * _ # ` | unmatched [ and ) here",
            "html tag <div class=\"x\"> inline </div> stays literal",
            "unmatched bracket [oops and *unmatched emphasis",
            "a".repeat(500),
        )
        for (s in samples) {
            val blocks = splitMdBlocks(s)
            val rendered = blocks.joinToString("") { raw ->
                when (val b = parseMdBlock(raw, colors)) {
                    is MdBlock.Paragraph -> b.text.text
                    else -> "<${b::class.simpleName}>"
                }
            }
            println("PROBE input=[${s.take(60)}...] blocks=${blocks.size} renderedLen=${rendered.length} inputLen=${s.length}")
        }
    }

    @Test
    fun `probe - table delimiter reclassify count`() {
        var prevType: String? = null
        var changes = 0
        val full = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        for (end in 1..full.length) {
            val prefix = full.substring(0, end)
            val blocks = splitMdBlocks(prefix)
            val last = blocks.lastOrNull() ?: continue
            val type = parseMdBlock(last, colors)::class.simpleName
            if (type != prevType) {
                changes++
                println("PROBE at len=$end type=$type raw=[${last.replace("\n", "\\n")}]")
            }
            prevType = type
        }
        println("PROBE total type changes for last block = $changes")
    }
}
