package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import com.hpz.llmdockchat.feature.pi.transcript.arr
import com.hpz.llmdockchat.feature.pi.transcript.str
import kotlinx.serialization.json.JsonObject

enum class DiffKind { HEADER, HUNK, ADD, REMOVE, CONTEXT }

data class DiffLine(val kind: DiffKind, val text: String)

fun parsePatch(patch: String): List<DiffLine> {
    if (patch.isEmpty()) return emptyList()
    return patch.lines().map { line ->
        when {
            line.startsWith("---") || line.startsWith("+++") -> DiffLine(DiffKind.HEADER, line)
            line.startsWith("@@") -> DiffLine(DiffKind.HUNK, line)
            line.startsWith("+") -> DiffLine(DiffKind.ADD, line.substring(1))
            line.startsWith("-") -> DiffLine(DiffKind.REMOVE, line.substring(1))
            else -> DiffLine(DiffKind.CONTEXT, line.removePrefix(" "))
        }
    }
}

fun editStats(lines: List<DiffLine>): Pair<Int, Int> =
    lines.count { it.kind == DiffKind.ADD } to lines.count { it.kind == DiffKind.REMOVE }

fun editSummary(item: PiItem.Tool): String {
    val path = parseToolArgs(item.args)?.str("path") ?: return argsSummary(item.args)
    val name = splitPath(path).name
    if (item.status == ToolStatus.ERROR) return "$name · failed"
    val patch = parseToolResult(item.output)?.details?.str("patch")
    if (patch == null) return name
    val (adds, removes) = editStats(parsePatch(patch))
    return "$name +$adds −$removes"
}

fun fallbackDiff(args: JsonObject?): List<DiffLine> {
    val edits = args?.arr("edits") ?: return emptyList()
    val lines = mutableListOf<DiffLine>()
    edits.forEachIndexed { index, element ->
        val edit = element as? JsonObject ?: return@forEachIndexed
        lines += DiffLine(DiffKind.HUNK, "edit ${index + 1}")
        (edit.str("oldText") ?: "").lines().forEach { lines += DiffLine(DiffKind.REMOVE, it) }
        (edit.str("newText") ?: "").lines().forEach { lines += DiffLine(DiffKind.ADD, it) }
    }
    return lines
}
