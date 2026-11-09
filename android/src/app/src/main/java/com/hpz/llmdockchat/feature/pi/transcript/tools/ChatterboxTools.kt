package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import com.hpz.llmdockchat.feature.pi.transcript.arr
import com.hpz.llmdockchat.feature.pi.transcript.bool
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.str
import kotlinx.serialization.json.JsonObject

data class ChatLine(
    val time: String,
    val from: String,
    val bot: Boolean,
    val text: String,
    val important: Boolean,
    val private: Boolean,
    val toYou: Boolean,
)


fun sendTarget(args: JsonObject?): String {
    return when (args?.str("audience")) {
        "participant" -> args.str("to")?.let { "→ $it" } ?: ""
        "channel" -> "→ channel"
        else -> ""
    }
}

fun chatLines(result: ToolResult?): List<ChatLine>? {
    val items = result?.details?.arr("items") ?: return null
    return items.mapNotNull { entry ->
        val line = entry as? JsonObject ?: return@mapNotNull null
        ChatLine(
            time = chatTime(line.str("time")),
            from = line.str("from").orEmpty(),
            bot = line.str("kind") == "bot",
            text = line.str("text").orEmpty(),
            important = line.bool("important"),
            private = line.bool("private"),
            toYou = line.bool("addressed"),
        )
    }
}

private fun chatTime(iso: String?): String {
    if (iso == null) return ""
    val start = iso.indexOf('T')
    if (start < 0 || iso.length < start + 6) return iso
    return iso.substring(start + 1, start + 6)
}

fun chatterboxSummary(item: PiItem.Tool): String = when (classifyTool(item.name)) {
    ToolKind.CHATTERBOX_SEND -> sendSummary(item)
    ToolKind.CHATTERBOX_LOOK -> lookSummary(item)
    ToolKind.CHATTERBOX_JOIN -> joinSummary(item)
    ToolKind.CHATTERBOX_LEAVE -> "leave"
    else -> argsSummary(item.args)
}

private fun sendSummary(item: PiItem.Tool): String {
    val args = parseToolArgs(item.args)
    val target = sendTarget(args)
    val text = args?.str("text")
    if (target.isEmpty() || text == null) return argsSummary(item.args)
    val firstLine = firstCollapsedLine(text)
    val outcome = parseToolResult(item.output)?.details?.str("outcome")
    return buildString {
        append("$target: $firstLine")
        if (outcome != null && outcome != "confirmed") append(" · $outcome")
    }
}

private fun lookSummary(item: PiItem.Tool): String {
    val args = parseToolArgs(item.args)
    val what = args?.str("what") ?: return argsSummary(item.args)
    val count = args?.int("count")
    return if (count != null) "look $what · $count" else "look $what"
}

private fun joinSummary(item: PiItem.Tool): String {
    val channel = parseToolArgs(item.args)?.str("channel") ?: return "join"
    return "join $channel"
}
