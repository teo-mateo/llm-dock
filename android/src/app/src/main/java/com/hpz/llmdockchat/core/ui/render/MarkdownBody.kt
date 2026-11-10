package com.hpz.llmdockchat.core.ui.render

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.markdown.MAX_FITTED_TABLE_COLUMNS
import com.hpz.llmdockchat.core.markdown.MdBlock
import com.hpz.llmdockchat.core.markdown.TableAlign
import com.hpz.llmdockchat.core.markdown.fittedColumnWeights
import com.hpz.llmdockchat.core.markdown.parseMdBlock
import com.hpz.llmdockchat.core.markdown.splitMdBlocks
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import kotlin.math.max
import kotlin.math.min

/**
 * The assistant answer's body: split into blocks, each block
 * memoized on its own raw text so a growing streamed answer only re-parses the
 * one block still being written (see
  * core/markdown/MarkdownParser.kt for the two-phase design).
 *
 * [selectable] wraps the blocks in one [SelectionContainer] so selection spans
 * every block, not just a single paragraph — but
 * only while the message is in selection mode. A [SelectionContainer]
 * claims long-press for its own selection-start gesture, which is exactly the
  * gesture the action menu needs; rather than fight that
 * conflict on every message all the time, selection is off by default and
 * turned on per-message from the long-press menu's "Select text" row
 * (`ThreadMessages.kt`'s `LongPressableMessage`), which simultaneously stops
 * offering the long-press gesture for as long as it's on. The
  * deviation record explains why this changes how the already-shipped
  * selection is invoked, not whether it works.
 */
@Composable
fun MarkdownBody(raw: String, modifier: Modifier = Modifier, selectable: Boolean = false) {
    val colors = LlmTheme.colors
    val blocks = remember(raw) { splitMdBlocks(raw) }
    val body: @Composable () -> Unit = {
        // 6dp between blocks ran paragraphs together into one grey mass at
        // this body size; 12 is about half a line, which is what separates
        // paragraphs on paper. Headings take more, above only, so a heading
        // binds to the text under it rather than floating between two
        // sections.
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            blocks.forEachIndexed { index, rawBlock ->
                val block = remember(rawBlock, colors) { parseMdBlock(rawBlock, colors) }
                if (block is MdBlock.Heading && index > 0) Spacer(Modifier.height(6.dp))
                MdBlockView(block, colors)
            }
        }
    }
    if (selectable) {
        SelectionContainer(modifier = modifier.testTag("markdown_body"), content = body)
    } else {
        Box(modifier.testTag("markdown_body")) { body() }
    }
}

@Composable
private fun MdBlockView(block: MdBlock, colors: LlmColors) {
    when (block) {
        is MdBlock.Heading -> Text(
            block.text,
            color = colors.fg,
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.Bold,
            style = headingStyle(block.level),
        )
        is MdBlock.Paragraph -> Text(
            block.text,
            color = colors.fg,
            fontFamily = FontFamily.Serif,
            style = MaterialTheme.typography.bodyLarge,
        )
        is MdBlock.CodeBlock -> CodeBlockView(block, colors)
        is MdBlock.ListBlock -> ListBlockView(block, colors)
        is MdBlock.Quote -> QuoteView(block, colors)
        is MdBlock.Table -> TableView(block, colors)
        MdBlock.Rule -> HorizontalRuleView(colors)
        is MdBlock.MathBlock -> Text(
            block.source,
            color = colors.muted,
            fontFamily = MonoFontFamily,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(colors.sunken)
                .padding(10.dp),
        )
    }
}

/**
 * Sizes given outright rather than pulled from [MaterialTheme.typography].
 *
 * The theme defines neither `headlineSmall` nor `titleSmall`, so h1 and h4+ were
 * silently falling back to Material's defaults — and Material's `titleSmall` is
 * 14sp, *smaller* than this body text at 16sp. A model that writes `#### ` got a
 * heading that looked like de-emphasised prose. Every level is now at least body
 * size, and each is strictly larger than the one below it.
 */
@Composable
private fun headingStyle(level: Int) = MaterialTheme.typography.bodyLarge.copy(
    fontSize = when (level) {
        1 -> 24.sp
        2 -> 21.sp
        3 -> 18.sp
        else -> 16.sp
    },
    lineHeight = when (level) {
        1 -> 30.sp
        2 -> 27.sp
        3 -> 24.sp
        else -> 22.sp
    },
)

/**
 * Language label, copy button, and its own horizontal scroll so a
 * long line never pushes the message column sideways.
 */
@Composable
private fun CodeBlockView(block: MdBlock.CodeBlock, colors: LlmColors) {
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) {
        if (copied) {
            kotlinx.coroutines.delay(1200)
            copied = false
        }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .testTag("code_block"),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(colors.surfaceElevated)
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                block.language?.uppercase() ?: "CODE",
                color = colors.subtle,
                fontFamily = MonoFontFamily,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.weight(1f),
            )
            Text(
                if (copied) "Copied" else "Copy",
                color = if (copied) colors.green else colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier
                    .clickable {
                        // Exact code only — no fence markers, no reformatting
                        //.
                        clipboard.setText(AnnotatedString(block.code))
                        copied = true
                    }
                    .testTag("code_copy"),
            )
        }
        // C4: the padding goes *outside* the scroll container, so the viewport
        // ends at the inset and long lines are clipped there. Inside it, the
        // padding scrolled along with the text and code slid out under the
        // block's own left edge.
        Box(Modifier.fillMaxWidth().padding(10.dp).horizontalScroll(rememberScrollState())) {
            Text(
                block.code,
                color = colors.fg,
                fontFamily = MonoFontFamily,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun ListBlockView(block: MdBlock.ListBlock, colors: LlmColors) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        block.items.forEach { item ->
            Row(Modifier.padding(start = (item.depth * 16).dp)) {
                val marker = if (item.ordered) "${item.index ?: 1}." else bulletFor(item.depth)
                Text(
                    marker,
                    color = colors.subtle,
                    fontFamily = FontFamily.Serif,
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.width(24.dp),
                )
                Text(
                    item.text,
                    color = colors.fg,
                    fontFamily = FontFamily.Serif,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
    }
}

private fun bulletFor(depth: Int): String = when (depth % 3) {
    0 -> "•"
    1 -> "◦"
    else -> "▪"
}

@Composable
private fun QuoteView(block: MdBlock.Quote, colors: LlmColors) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .background(colors.sunken)
            .padding(start = 10.dp, top = 8.dp, bottom = 8.dp, end = 10.dp),
    ) {
        Box(Modifier.width(3.dp).background(colors.accent))
        Column(Modifier.padding(start = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            block.lines.forEach { line ->
                Text(line, color = colors.muted, fontFamily = FontFamily.Serif, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** Up to [MAX_FITTED_TABLE_COLUMNS] columns fit the message width and wrap; wider tables scroll sideways in their own box, never the message column. */
@Composable
private fun TableView(block: MdBlock.Table, colors: LlmColors) {
    val weights = fittedColumnWeights(block)
    val box = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(8.dp))
        .background(colors.sunken)
    Box(
        (if (weights == null) box.horizontalScroll(rememberScrollState()) else box).testTag("md_table"),
    ) {
        Column {
            TableRow(block.header, weights, Modifier.background(colors.surfaceElevated)) { i, cell, cellModifier ->
                TableCell(cell, colors.fg, bold = true, align = block.alignments.getOrElse(i) { TableAlign.LEFT }, modifier = cellModifier)
            }
            block.rows.forEach { row ->
                TableRow(row, weights, Modifier) { i, cell, cellModifier ->
                    TableCell(cell, colors.muted, bold = false, align = block.alignments.getOrElse(i) { TableAlign.LEFT }, modifier = cellModifier)
                }
            }
        }
    }
}

@Composable
private fun TableRow(
    cells: List<AnnotatedString>,
    weights: List<Float>?,
    modifier: Modifier,
    cell: @Composable RowScope.(Int, AnnotatedString, Modifier) -> Unit,
) {
    Row(if (weights == null) modifier else modifier.fillMaxWidth()) {
        cells.forEachIndexed { i, text ->
            val sizing = weights?.getOrNull(i)?.let { Modifier.weight(it) } ?: Modifier.width(140.dp)
            cell(i, text, sizing)
        }
    }
}

@Composable
private fun TableCell(text: AnnotatedString, color: androidx.compose.ui.graphics.Color, bold: Boolean, align: TableAlign, modifier: Modifier) {
    Text(
        text,
        color = color,
        fontFamily = FontFamily.Serif,
        style = if (bold) MaterialTheme.typography.labelLarge else MaterialTheme.typography.bodyMedium,
        textAlign = when (align) {
            TableAlign.LEFT -> androidx.compose.ui.text.style.TextAlign.Start
            TableAlign.CENTER -> androidx.compose.ui.text.style.TextAlign.Center
            TableAlign.RIGHT -> androidx.compose.ui.text.style.TextAlign.End
        },
        modifier = modifier.padding(horizontal = 8.dp, vertical = 8.dp),
    )
}

@Composable
private fun HorizontalRuleView(colors: LlmColors) {
    Box(Modifier.fillMaxWidth().height(1.dp).background(colors.line))
}
