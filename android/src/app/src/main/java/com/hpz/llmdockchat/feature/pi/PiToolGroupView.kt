package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiDisplayItem
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import com.hpz.llmdockchat.feature.pi.transcript.moreLabel
import com.hpz.llmdockchat.feature.pi.transcript.visibleTools

private const val MAX_OUTPUT_LINES = 20

@Composable
fun PiToolGroupView(group: PiDisplayItem.ToolGroup) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(colors.surface)
            .border(1.dp, colors.line, RoundedCornerShape(12.dp))
            .testTag("pi_tool_group"),
    ) {
        var expanded by rememberSaveable(group.id) { mutableStateOf(false) }
        val visible = visibleTools(group.tools, expanded)
        visible.shown.forEachIndexed { index, tool ->
            if (index > 0) HorizontalDivider(color = colors.line)
            PiToolRow(tool)
        }
        if (group.thinking) {
            HorizontalDivider(color = colors.line)
            Text(
                "thinking…",
                color = colors.muted,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp).testTag("pi_tool_group_thinking"),
            )
        }
        if (visible.hidden > 0) {
            HorizontalDivider(color = colors.line)
            Text(
                moreLabel(visible.hidden),
                color = colors.muted,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.fillMaxWidth().clickable { expanded = true }
                    .padding(horizontal = 12.dp, vertical = 8.dp).testTag("pi_tool_group_more"),
            )
        }
    }
}

@Composable
private fun PiToolRow(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    var open by rememberSaveable(item.id) { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().heightIn(min = 34.dp).clickable { open = !open }
            .padding(horizontal = 12.dp).testTag("pi_tool_${item.callId}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier.size(8.dp).clip(CircleShape).background(statusColor(item.status))
                .semantics { contentDescription = toolStatusText(item) },
        )
        Text(
            item.name,
            color = colors.fg,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelMedium,
            maxLines = 1,
        )
        Text(
            argsSummary(item.args),
            color = colors.muted,
            fontFamily = FontFamily.Monospace,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text(
            "Details",
            color = colors.accent,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
        )
    }
    if (open) PiToolDetails(item)
}

@Composable
private fun PiToolDetails(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    var showAll by rememberSaveable(item.id) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().background(colors.sunken).padding(12.dp).testTag("pi_tool_details"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(toolStatusText(item), color = statusColor(item.status), style = MaterialTheme.typography.labelSmall)
        if (item.args != null) {
            Text(item.args, color = colors.muted, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
        }
        if (item.output != null) {
            val lines = item.output.lines()
            Text(
                if (showAll) item.output else lines.take(MAX_OUTPUT_LINES).joinToString("\n"),
                color = colors.muted,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.surface).padding(10.dp),
            )
            if (lines.size > MAX_OUTPUT_LINES) {
                Text(
                    if (showAll) "Show less" else "Show all",
                    color = colors.accent,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.clickable { showAll = !showAll }.testTag("pi_tool_output_toggle"),
                )
            }
        }
        if (item.truncated) {
            Text("output truncated by pi-remote", color = colors.amber, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun statusColor(status: ToolStatus) = when (status) {
    ToolStatus.RUNNING -> LlmTheme.colors.amber
    ToolStatus.DONE -> LlmTheme.colors.green
    ToolStatus.ERROR -> LlmTheme.colors.red
}

internal fun toolStatusText(item: PiItem.Tool): String = when (item.status) {
    ToolStatus.RUNNING -> "running…"
    ToolStatus.DONE -> item.durationMs?.let { "done · ${String.format(java.util.Locale.ROOT, "%.1f", it / 1000.0)} s" } ?: "done"
    ToolStatus.ERROR -> "error"
}
