package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.str

data class NumberedLine(val number: Int, val text: String)

fun numberLines(text: String, firstLine: Int): List<NumberedLine> {
    if (text.isEmpty()) return emptyList()
    val parts = text.split("\n")
    val lines = if (parts.size > 1 && parts.last().isEmpty()) parts.dropLast(1) else parts
    return lines.mapIndexed { index, line -> NumberedLine(firstLine + index, line) }
}

fun readSummary(item: PiItem.Tool): String {
    val args = parseToolArgs(item.args) ?: return argsSummary(item.args)
    val path = args.str("path") ?: return argsSummary(item.args)
    val name = splitPath(path).name
    if (parseToolResult(item.output)?.images?.isNotEmpty() == true) return "$name · image"
    val offset = args.int("offset")
    val limit = args.int("limit")
    if (offset != null && limit != null) return "$name L$offset–${offset + limit - 1}"
    if (offset != null) return "$name L$offset–"
    return name
}

fun writeSummary(item: PiItem.Tool): String {
    val args = parseToolArgs(item.args) ?: return argsSummary(item.args)
    val path = args.str("path") ?: return argsSummary(item.args)
    val name = splitPath(path).name
    val content = args.str("content").orEmpty()
    return "$name · ${numberLines(content, 1).size} lines"
}
