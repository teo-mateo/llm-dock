package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.bool
import com.hpz.llmdockchat.feature.pi.transcript.str
import com.hpz.llmdockchat.feature.pi.transcript.tools.ChatLine
import com.hpz.llmdockchat.feature.pi.transcript.tools.ProcessStatusTone
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.chatLines
import com.hpz.llmdockchat.feature.pi.transcript.tools.sendTarget
import kotlinx.serialization.json.JsonObject

@Composable
internal fun ChatterboxSendBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    val text = args?.str("text").orEmpty()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ToolResultMessage(item, result, ToolResultMode.ERRORS_ONLY)
        val target = sendTarget(args)
        if (target.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    target,
                    color = colors.fg,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.SemiBold,
                )
                if (args?.bool("important") == true) ToolStatusChip("important", ProcessStatusTone.RUNNING)
            }
        }
        if (text.isNotEmpty()) {
            Text(
                text,
                color = colors.fg,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(colors.surface)
                    .padding(12.dp),
            )
        }
        SendOutcome(item, result)
    }
}

@Composable
private fun SendOutcome(item: PiItem.Tool, result: ToolResult?) {
    val colors = LlmTheme.colors
    val outcome = result?.details?.str("outcome")
    val message = toolResultMessage(result)
    when {
        isToolError(item, result) -> Unit
        outcome == "confirmed" -> ToolStatusChip("confirmed", ProcessStatusTone.SUCCESS)
        message.isNotEmpty() -> Text(message, color = colors.red, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
internal fun ChatterboxLookBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val lines = remember(item.output) { chatLines(result) }
    if (lines == null) {
        GenericFormattedBody(item, args, result)
        return
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        ToolResultMessage(item, result, ToolResultMode.ERRORS_ONLY)
        lines.forEachIndexed { index, line -> ChatLineView(item.id, index, line) }
    }
}

@Composable
private fun ChatLineView(itemId: String, index: Int, line: ChatLine) {
    val colors = LlmTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            if (line.time.isNotEmpty()) {
                Text(
                    line.time,
                    color = colors.muted,
                    fontFamily = MonoFontFamily,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            if (line.from.isNotEmpty()) {
                Text(
                    line.from,
                    color = colors.fg,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            if (line.bot) ToolStatusChip("bot", ProcessStatusTone.NEUTRAL)
            if (line.important) ToolStatusChip("important", ProcessStatusTone.RUNNING)
        }
        if (line.text.isNotBlank()) {
            val textLines = remember(line.text) { line.text.lines() }
            CappedToolRows(itemId, "look_msg_$index", textLines, 6, "pi_tool_output_toggle") { text ->
                Text(text, color = colors.fg, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
