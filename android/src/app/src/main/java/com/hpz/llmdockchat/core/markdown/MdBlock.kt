package com.hpz.llmdockchat.core.markdown

import androidx.compose.ui.text.AnnotatedString

/**
 * A block-level Markdown construct (F05-R1), already inline-styled — bold,
 * italic, inline code and links are resolved into the [AnnotatedString]s here,
 * so the render layer only lays blocks out.
 *
 * Produced by [parseMdBlock] from one raw block's source text. The block
 * boundaries themselves come from [splitMdBlocks], which is prefix-stable
 * (Architecture P2): an already-closed block's raw text never changes as the
 * stream grows, so only the still-open last block needs reparsing.
 */
sealed interface MdBlock {
    data class Heading(val level: Int, val text: AnnotatedString) : MdBlock

    data class Paragraph(val text: AnnotatedString) : MdBlock

    /**
     * `closed` is false while the block still lacks its closing fence — the
     * content keeps growing but the block never stops being a code block, which
     * is what keeps an open fence from flickering (F05-R1's second criterion).
     */
    data class CodeBlock(val language: String?, val code: String, val closed: Boolean) : MdBlock

    data class ListBlock(val items: List<MdListItem>) : MdBlock

    data class Quote(val lines: List<AnnotatedString>) : MdBlock

    data class Table(
        val header: List<AnnotatedString>,
        val alignments: List<TableAlign>,
        val rows: List<List<AnnotatedString>>,
    ) : MdBlock

    data object Rule : MdBlock

    /** `$$…$$` on its own line(s) — F05-R7, literal source, not evaluated. */
    data class MathBlock(val source: String) : MdBlock
}

data class MdListItem(val depth: Int, val ordered: Boolean, val index: Int?, val text: AnnotatedString)

enum class TableAlign { LEFT, CENTER, RIGHT }
