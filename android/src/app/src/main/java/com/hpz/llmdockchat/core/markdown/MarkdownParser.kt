package com.hpz.llmdockchat.core.markdown

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import com.hpz.llmdockchat.core.ui.theme.LlmColors

/**
 * A hand-rolled block-level Markdown renderer (F05-R1/R2/R5/R7). No third-party
 * Markdown library is in Architecture D7's verified dependency set — the
 * construct list here is fixed and modest, syntax highlighting is explicitly
 * out of scope, and streaming needs precise control over how an unterminated
 * construct renders, which a general GFM library does not expose. See the F05
 * implementation report for the fuller reasoning.
 *
 * Two-phase, matching Architecture P2:
 *
 * 1. [splitMdBlocks] — a cheap line scan that finds block *boundaries* only.
 *    It is prefix-stable: once a block is closed (a blank line, or a new block
 *    starter appears), its raw text never changes as the stream grows, so it
 *    is only ever computed once per block. Only the last, still-open block's
 *    raw text keeps growing.
 * 2. [parseMdBlock] — the expensive part (regex-driven inline parsing,
 *    `AnnotatedString` construction) on one block's raw text. Callers
 *    `remember(raw, colors) { parseMdBlock(raw, colors) }` per block, so
 *    Compose's own equality check skips re-running this for every
 *    already-closed block — only the open tail block, whose `raw` actually
 *    changed, re-parses.
 */
private const val FENCE_BACKTICK = "```"
private const val FENCE_TILDE = "~~~"

fun splitMdBlocks(text: String): List<String> {
    if (text.isEmpty()) return emptyList()
    // CRLF (or a bare CR) would otherwise fail `LIST_UNORDERED_RE`/`LIST_ORDERED_RE`'s
    // `matches()` on the trailing `\r` and leave a stray `\r` in quoted text —
    // normalising once here kills both instead of chasing `\r` in every regex.
    val normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    val lines = normalized.split("\n")
    val blocks = mutableListOf<MutableList<String>>()
    var inFence = false
    var fenceMarker = ""

    fun current(): MutableList<String>? = blocks.lastOrNull()
    fun startBlock(line: String) {
        blocks += mutableListOf(line)
    }
    fun append(line: String) {
        current()?.let { it += line } ?: startBlock(line)
    }

    for (line in lines) {
        val trimmed = line.trimStart()
        if (inFence) {
            append(line)
            if (trimmed.startsWith(fenceMarker)) inFence = false
            continue
        }
        when {
            trimmed.startsWith(FENCE_BACKTICK) || trimmed.startsWith(FENCE_TILDE) -> {
                startBlock(line)
                fenceMarker = if (trimmed.startsWith(FENCE_BACKTICK)) FENCE_BACKTICK else FENCE_TILDE
                inFence = true
            }
            line.isBlank() -> blocks.add(mutableListOf()) // forces the next line to start a fresh block
            isHeadingLine(line) || isRuleLine(line) -> startBlock(line)
            isListItemLine(line) -> {
                if (current()?.let { it.isNotEmpty() && isListItemLine(it.first()) } == true) append(line)
                else startBlock(line)
            }
            isQuoteLine(line) -> {
                if (current()?.let { it.isNotEmpty() && isQuoteLine(it.first()) } == true) append(line)
                else startBlock(line)
            }
            looksLikeTableRow(line) -> {
                val cur = current()
                when {
                    cur == null || cur.isEmpty() -> startBlock(line)
                    looksLikeTableRow(cur.first()) -> append(line)
                    else -> startBlock(line)
                }
            }
            else -> {
                val cur = current()
                val continuesParagraph = cur != null && cur.isNotEmpty() &&
                    !isHeadingLine(cur.first()) && !isRuleLine(cur.first()) &&
                    !isListItemLine(cur.first()) && !isQuoteLine(cur.first()) &&
                    !cur.first().trimStart().let { it.startsWith(FENCE_BACKTICK) || it.startsWith(FENCE_TILDE) }
                if (continuesParagraph) append(line) else startBlock(line)
            }
        }
    }
    return blocks.filter { it.isNotEmpty() }.map { it.joinToString("\n") }
}

fun parseMdBlock(raw: String, colors: LlmColors): MdBlock {
    val lines = raw.split("\n")
    val first = lines.first()
    val firstTrimmed = first.trimStart()

    return when {
        firstTrimmed.startsWith(FENCE_BACKTICK) || firstTrimmed.startsWith(FENCE_TILDE) -> parseCodeBlock(lines)
        isHeadingLine(first) -> parseHeading(first, colors)
        isRuleLine(first) && lines.size == 1 -> MdBlock.Rule
        lines.size >= 2 && looksLikeTableRow(lines[0]) && isTableDelimiterLine(lines[1]) -> parseTable(lines, colors)
        isListItemLine(first) -> parseList(lines, colors)
        isQuoteLine(first) -> parseQuote(lines, colors)
        raw.trim().startsWith("$$") -> MdBlock.MathBlock(raw)
        else -> MdBlock.Paragraph(parseInline(joinParagraphLines(lines), colors))
    }
}

private fun joinParagraphLines(lines: List<String>): String = lines.joinToString(" ") { it.trim() }

private fun isHeadingLine(line: String): Boolean {
    val t = line.trimStart()
    if (!t.startsWith("#")) return false
    val hashes = t.takeWhile { it == '#' }
    return hashes.length in 1..6 && (t.length == hashes.length || t[hashes.length] == ' ')
}

private fun parseHeading(line: String, colors: LlmColors): MdBlock.Heading {
    val t = line.trimStart()
    val level = t.takeWhile { it == '#' }.length
    val text = t.drop(level).trim()
    return MdBlock.Heading(level, parseInline(text, colors))
}

private fun isRuleLine(line: String): Boolean {
    val t = line.trim()
    if (t.length < 3) return false
    val c = t[0]
    if (c != '-' && c != '*' && c != '_') return false
    return t.all { it == c || it == ' ' } && t.count { it == c } >= 3
}

private val FENCE_INFO_RE = Regex("^(```+|~~~+)\\s*([A-Za-z0-9_+-]*)")

private fun parseCodeBlock(lines: List<String>): MdBlock.CodeBlock {
    val openMatch = FENCE_INFO_RE.find(lines.first().trimStart())
    val marker = openMatch?.groupValues?.get(1)?.take(3) ?: FENCE_BACKTICK
    val language = openMatch?.groupValues?.get(2)?.takeIf { it.isNotBlank() }
    val closeIndex = (1 until lines.size).firstOrNull { lines[it].trimStart().startsWith(marker) }
    val body = if (closeIndex != null) lines.subList(1, closeIndex) else lines.drop(1)
    return MdBlock.CodeBlock(language, body.joinToString("\n"), closed = closeIndex != null)
}

private val LIST_UNORDERED_RE = Regex("^(\\s*)([-*+])\\s+(.*)$")
private val LIST_ORDERED_RE = Regex("^(\\s*)(\\d+)[.)]\\s+(.*)$")

private fun isListItemLine(line: String): Boolean =
    LIST_UNORDERED_RE.matches(line) || LIST_ORDERED_RE.matches(line)

private fun parseList(lines: List<String>, colors: LlmColors): MdBlock.ListBlock {
    val items = mutableListOf<MdListItem>()
    for (line in lines) {
        val unordered = LIST_UNORDERED_RE.matchEntire(line)
        val ordered = LIST_ORDERED_RE.matchEntire(line)
        when {
            unordered != null -> {
                val depth = unordered.groupValues[1].length / 2
                items += MdListItem(depth, ordered = false, index = null, text = parseInline(unordered.groupValues[3], colors))
            }
            ordered != null -> {
                val depth = ordered.groupValues[1].length / 2
                val idx = ordered.groupValues[2].toIntOrNull()
                items += MdListItem(depth, ordered = true, index = idx, text = parseInline(ordered.groupValues[3], colors))
            }
            else -> {
                // A continuation line (soft-wrapped text under the current item):
                // appended to the last item rather than dropped, so nothing is lost.
                val last = items.removeLastOrNull()
                if (last != null) {
                    val joined = last.text.text + " " + line.trim()
                    items += last.copy(text = parseInline(joined, colors))
                }
            }
        }
    }
    return MdBlock.ListBlock(items)
}

private fun isQuoteLine(line: String): Boolean = line.trimStart().startsWith(">")

private fun parseQuote(lines: List<String>, colors: LlmColors): MdBlock.Quote {
    val quoteLines = lines.map { line ->
        var stripped = line.trimStart()
        if (stripped.startsWith(">")) stripped = stripped.removePrefix(">").removePrefix(" ")
        parseInline(stripped, colors)
    }
    return MdBlock.Quote(quoteLines)
}

/**
 * A bare `|` mid-sentence — `P(A|B) using Bayes' theorem` — must not read as a
 * table row and fracture the paragraph around it (a real risk with this rig's
 * models, which write conditional-probability notation often). Requiring an
 * edge pipe or a second pipe is enough signal without needing a real GFM
 * grammar: genuine tables almost always have a leading/trailing `|` or 2+
 * columns.
 */
private fun looksLikeTableRow(line: String): Boolean {
    val t = line.trim()
    if (t.isEmpty()) return false
    return t.startsWith("|") || t.endsWith("|") || t.count { it == '|' } >= 2
}

private val TABLE_DELIMITER_CELL_RE = Regex("^:?-+:?$")

private fun isTableDelimiterLine(line: String): Boolean {
    val cells = splitTableRow(line)
    return cells.isNotEmpty() && cells.all { TABLE_DELIMITER_CELL_RE.matches(it.trim()) }
}

private fun splitTableRow(line: String): List<String> {
    var t = line.trim()
    if (t.startsWith("|")) t = t.drop(1)
    if (t.endsWith("|") && !t.endsWith("\\|")) t = t.dropLast(1)
    // Split on unescaped pipes.
    val cells = mutableListOf<String>()
    val current = StringBuilder()
    var i = 0
    while (i < t.length) {
        val c = t[i]
        if (c == '\\' && i + 1 < t.length && t[i + 1] == '|') {
            current.append('|')
            i += 2
            continue
        }
        if (c == '|') {
            cells += current.toString()
            current.clear()
        } else {
            current.append(c)
        }
        i++
    }
    cells += current.toString()
    return cells
}

private fun parseTable(lines: List<String>, colors: LlmColors): MdBlock {
    val header = splitTableRow(lines[0]).map { parseInline(it.trim(), colors) }
    val alignments = splitTableRow(lines[1]).map { cell ->
        val c = cell.trim()
        when {
            c.startsWith(":") && c.endsWith(":") -> TableAlign.CENTER
            c.endsWith(":") -> TableAlign.RIGHT
            else -> TableAlign.LEFT
        }
    }
    // A ragged row (too few/many cells) is padded/truncated rather than
    // crashing the message (F05-R5's second criterion).
    val rows = lines.drop(2).filter { it.isNotBlank() }.map { rowLine ->
        val cells = splitTableRow(rowLine).map { it.trim() }
        List(header.size) { i -> parseInline(cells.getOrElse(i) { "" }, colors) }
    }
    return MdBlock.Table(header, alignments, rows)
}

// -- Inline formatting ------------------------------------------------------

/**
 * Bold, italic, inline code, links and `$…$`/`$$…$$` maths passthrough
 * (F05-R7), single pass, no recursive nesting of emphasis inside emphasis —
 * a deliberate scope cut (this renders one model's output on one phone; see
 * the F05 implementation report).
 *
 * An unterminated marker (an opening `**` with no closing `**` anywhere in
 * the text that has arrived so far) falls back to its literal characters
 * rather than being swallowed — F05-R1's fourth criterion and F05-R7's
 * second: nothing is silently stripped.
 */
fun parseInline(raw: String, colors: LlmColors): AnnotatedString = buildAnnotatedString {
    var i = 0
    val n = raw.length
    while (i < n) {
        val c = raw[i]
        when {
            c == '\\' && i + 1 < n && raw[i + 1] in ESCAPABLE -> {
                append(raw[i + 1])
                i += 2
            }
            c == '`' -> {
                val end = raw.indexOf('`', i + 1)
                if (end < 0) {
                    append(raw.substring(i)); i = n
                } else {
                    withStyle(codeSpanStyle(colors)) { append(raw.substring(i + 1, end)) }
                    i = end + 1
                }
            }
            raw.startsWith("$$", i) -> {
                val end = raw.indexOf("$$", i + 2)
                if (end < 0) {
                    withStyle(mathSpanStyle(colors)) { append(raw.substring(i)) }; i = n
                } else {
                    appendMath(raw.substring(i + 2, end), raw.substring(i, end + 2), colors)
                    i = end + 2
                }
            }
            c == '$' -> {
                val end = findInlineMathClose(raw, i + 1)
                if (end < 0) {
                    append(c); i++
                } else {
                    appendMath(raw.substring(i + 1, end), raw.substring(i, end + 1), colors)
                    i = end + 1
                }
            }
            raw.startsWith("**", i) || raw.startsWith("__", i) -> {
                val marker = raw.substring(i, i + 2)
                val end = raw.indexOf(marker, i + 2)
                if (end <= i + 2) {
                    append(marker); i += 2
                } else {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(raw.substring(i + 2, end)) }
                    i = end + 2
                }
            }
            (c == '*' || c == '_') -> {
                val end = raw.indexOf(c, i + 1)
                if (end <= i + 1) {
                    append(c); i++
                } else {
                    withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(raw.substring(i + 1, end)) }
                    i = end + 1
                }
            }
            // Must be tested before the `[` case, or the `!` falls through to
            // the default branch as a literal and the rest is picked up as an
            // ordinary link — which is exactly what shipped: `!` followed by
            // blue underlined alt text pointing at a URL the phone cannot
            // fetch. Every schemdraw turn hit it, because the tool emits a
            // Markdown image next to the artifact that already draws it.
            c == '!' && i + 1 < n && raw[i + 1] == '[' -> {
                val image = matchImage(raw, i)
                if (image == null) {
                    append(c); i++
                } else {
                    // Inline images are not rendered on the phone (F05-R6
                    // covers artifacts, not arbitrary remote images), so this
                    // is a caption, not a control: no link, nothing to tap,
                    // and no pretence that the picture is one tap away. With
                    // no alt text there is nothing to caption, so the literal
                    // source stands in — this parser never silently strips.
                    withStyle(imageRefStyle(colors)) {
                        append(
                            if (image.text.isBlank()) {
                                raw.substring(i, image.end)
                            } else {
                                "Image: ${image.text}"
                            },
                        )
                    }
                    i = image.end
                }
            }
            c == '[' -> {
                val link = matchLink(raw, i)
                if (link == null) {
                    append(c); i++
                } else {
                    withLink(
                        LinkAnnotation.Url(
                            link.url,
                            TextLinkStyles(style = SpanStyle(color = colors.accent, textDecoration = TextDecoration.Underline)),
                        ),
                    ) { append(link.text) }
                    i = link.end
                }
            }
            else -> {
                append(c); i++
            }
        }
    }
}

/**
 * Inline maths, translated to Unicode where that is faithful and shown as its
 * own source where it is not.
 *
 * The fallback keeps the monospace style, because at that point the reader is
 * being shown TeX and should be able to tell. What it must never do is print
 * `$\rightarrow$` in the middle of a sentence in a serif face, which is what
 * unconditional passthrough did.
 */
private fun AnnotatedString.Builder.appendMath(inner: String, source: String, colors: LlmColors) {
    val translated = LatexUnicode.translate(inner)
    if (translated != null) append(translated) else withStyle(mathSpanStyle(colors)) { append(source) }
}

private val ESCAPABLE = "\\`*_{}[]()#+-.!$>~".toSet()

private data class LinkMatch(val text: String, val url: String, val end: Int)

/**
 * `![alt](url)` — the same shape as a link, one character further along.
 * [LinkMatch.end] is still an index into `raw`, so it spans the leading `!`.
 */
private fun matchImage(raw: String, start: Int): LinkMatch? = matchLink(raw, start + 1)

/** `[text](url)`. Anything short of the full shape falls through as literal `[`. */
private fun matchLink(raw: String, start: Int): LinkMatch? {
    val closeText = raw.indexOf(']', start + 1)
    if (closeText < 0 || closeText + 1 >= raw.length || raw[closeText + 1] != '(') return null
    val closeUrl = raw.indexOf(')', closeText + 2)
    if (closeUrl < 0) return null
    val text = raw.substring(start + 1, closeText)
    val url = raw.substring(closeText + 2, closeUrl)
    if (url.isBlank()) return null
    return LinkMatch(text, url, closeUrl + 1)
}

/**
 * The closing `$` of an inline maths span. Requires non-blank content on
 * both edges and no newline crossing, which keeps ordinary currency prose
 * ("$5 and $10") from being swept up most of the time without needing a
 * full LaTeX grammar — this renders one model's output, not arbitrary text.
 */
private fun findInlineMathClose(raw: String, from: Int): Int {
    var i = from
    while (i < raw.length) {
        val c = raw[i]
        if (c == '\n') return -1
        if (c == '$') {
            if (i == from) return -1 // empty span
            if (raw[from] == ' ' || raw[i - 1] == ' ') return -1
            return i
        }
        i++
    }
    return -1
}

private fun codeSpanStyle(colors: LlmColors) = SpanStyle(
    fontFamily = FontFamily.Monospace,
    background = colors.sunken,
)

private fun mathSpanStyle(colors: LlmColors) = SpanStyle(
    fontFamily = FontFamily.Monospace,
    color = colors.muted,
)

/** Reads as a figure caption — deliberately not the accent colour a link uses. */
private fun imageRefStyle(colors: LlmColors) = SpanStyle(
    color = colors.subtle,
    fontStyle = FontStyle.Italic,
)
