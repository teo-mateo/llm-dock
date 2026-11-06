package com.hpz.llmdockchat.feature.pi
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.draw.*
import androidx.compose.ui.platform.*
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.*
import androidx.compose.ui.unit.*
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.thread.MarkdownBody
import com.hpz.llmdockchat.feature.thread.ReasoningBlock
@Composable
fun PiItemView(item: PiItem) {
    when (item) {
        is PiItem.User -> PiUserItem(item)
        is PiItem.Assistant -> PiAssistantItem(item)
        is PiItem.Tool -> PiToolItem(item)
        is PiItem.Notice -> PiNoticeItem(item)
        is PiItem.RunEnd -> PiRunEndItem(item)
    }
}
@Composable
private fun PiUserItem(item: PiItem.User) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.End,
    ) {
        Box(
            Modifier.clip(RoundedCornerShape(14.dp)).background(colors.surfaceElevated).padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(
                item.text,
                color = colors.fg,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        val footer = listOfNotNull(
            "from phone".takeIf { item.fromPhone },
            "+${item.imageCount} ${if (item.imageCount == 1) "image" else "images"}".takeIf { item.imageCount > 0 },
        )
        if (footer.isNotEmpty()) {
            Text(
                footer.joinToString(" · "),
                color = colors.subtle,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}
@Composable
private fun PiAssistantItem(item: PiItem.Assistant) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (item.thinking.isNotBlank()) ReasoningBlock(item.thinking)
        if (item.text.isNotEmpty()) MarkdownBody(item.text, modifier = Modifier.testTag("pi_assistant_text"))
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (item.streaming) {
                Text(
                    "▍",
                    color = colors.accent,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag("pi_streaming_caret"),
                )
            }
            if (item.outputTokens != null) {
                Text(
                    "${item.outputTokens} tokens",
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}
@Composable
private fun PiToolItem(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    var argsExpanded by remember { mutableStateOf(false) }
    var showAll by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(colors.surface)
            .border(1.dp, colors.line, RoundedCornerShape(12.dp))
            .padding(12.dp)
            .testTag("pi_tool_${item.callId}"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                item.name,
                color = colors.fg,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Text(
                statusLabel(item),
                color = when (item.status) {
                    ToolStatus.RUNNING -> colors.amber
                    ToolStatus.DONE -> colors.green
                    ToolStatus.ERROR -> colors.red
                },
                style = MaterialTheme.typography.labelSmall,
            )
        }
        if (item.args != null) {
            Text(
                if (argsExpanded) "▾ Arguments" else "▸ Arguments",
                color = colors.muted,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.clickable { argsExpanded = !argsExpanded }.testTag("pi_tool_args_toggle"),
            )
            if (argsExpanded) {
                Text(
                    item.args,
                    color = colors.muted,
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        if (item.output != null) {
            val lines = item.output.lines()
            Text(
                if (showAll) item.output else lines.take(20).joinToString("\n"),
                color = colors.muted,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.sunken).padding(10.dp),
            )
            if (lines.size > 20) {
                Text(
                    if (showAll) "Show less" else "Show all",
                    color = colors.accent,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.clickable { showAll = !showAll }.testTag("pi_tool_output_toggle"),
                )
            }
        }
        if (item.truncated) {
            Text(
                "output truncated by pi-remote",
                color = colors.amber,
                style = MaterialTheme.typography.labelSmall,
            )
        }
    }
}
@Composable
private fun PiNoticeItem(item: PiItem.Notice) {
    Text(
        item.text,
        color = LlmTheme.colors.muted,
        style = MaterialTheme.typography.bodySmall,
        textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
    )
}
@Composable
private fun PiRunEndItem(item: PiItem.RunEnd) {
    val colors = LlmTheme.colors
    val text = if (item.outcome.isBlank()) "run ended" else "run ${item.outcome}"
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(Modifier.weight(1f).height(1.dp).background(colors.line))
        Text(text, color = colors.subtle, style = MaterialTheme.typography.labelSmall)
        Box(Modifier.weight(1f).height(1.dp).background(colors.line))
    }
}
private fun statusLabel(item: PiItem.Tool): String = when (item.status) {
    ToolStatus.RUNNING -> "running…"
    ToolStatus.DONE -> item.durationMs?.let { "done · ${String.format("%.1f", it / 1000.0)} s" } ?: "done"
    ToolStatus.ERROR -> "error"
}
