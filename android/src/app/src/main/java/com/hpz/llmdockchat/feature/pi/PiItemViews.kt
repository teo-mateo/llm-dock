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
import com.hpz.llmdockchat.feature.pi.transcript.PiDisplayItem
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.thread.MarkdownBody
import com.hpz.llmdockchat.feature.thread.ReasoningBlock
@Composable
fun PiItemView(item: PiItem, lastStopAt: Long? = null) {
    when (item) {
        is PiItem.User -> PiUserItem(item)
        is PiItem.Assistant -> PiAssistantItem(item)
        is PiItem.Tool -> PiToolGroupView(PiDisplayItem.ToolGroup("g${item.id}", listOf(item)))
        is PiItem.Notice -> PiNoticeItem(item)
        is PiItem.RunEnd -> PiRunEndItem(item, lastStopAt)
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
private fun PiRunEndItem(item: PiItem.RunEnd, lastStopAt: Long?) {
    val colors = LlmTheme.colors
    val text = runEndLabel(item.outcome, item.ts, lastStopAt)
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
