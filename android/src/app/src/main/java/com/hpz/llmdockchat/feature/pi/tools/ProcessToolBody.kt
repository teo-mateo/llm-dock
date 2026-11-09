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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.tools.ProcessInfo
import com.hpz.llmdockchat.feature.pi.transcript.tools.ProcessStatusTone
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.processInfo
import com.hpz.llmdockchat.feature.pi.transcript.tools.processStatusTone
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitCdPrefix
import kotlinx.serialization.json.JsonObject

private const val OUTPUT_LINES = 12

@Composable
internal fun ProcessToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    val info = processInfo(args, result)
    val error = isToolError(item, result)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ToolResultMessage(item, result, ToolResultMode.ERRORS_ONLY)
        ProcessHeader(info)
        ProcessKeyValues(info)
        val command = info.command
        if (info.action == "start" && !command.isNullOrEmpty()) {
            val parsed = splitCdPrefix(command)
            parsed.dir?.let { WorkingDirectoryChip(it) }
            ShellCommandCard(item.id, "process_command", parsed.command)
        }
        val text = if (error) "" else result?.text?.trimEnd().orEmpty()
        val lines = text.lines()
        if (text.isNotEmpty()) {
            CappedToolRows(item.id, "process_output", lines, OUTPUT_LINES, "pi_tool_output_toggle") {
                Text(it, color = colors.muted, fontFamily = MonoFontFamily, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ProcessHeader(info: ProcessInfo) {
    val colors = LlmTheme.colors
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            info.action ?: "process",
            color = colors.fg,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
        info.name?.let {
            Text(
                it,
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f, fill = false),
            )
        }
        info.status?.let { ProcessStatusChip(it, processStatusTone(it, info.exitCode)) }
    }
}

@Composable
private fun ProcessStatusChip(status: String, tone: ProcessStatusTone) {
    val colors = LlmTheme.colors
    val color = when (tone) {
        ProcessStatusTone.RUNNING -> colors.amber
        ProcessStatusTone.SUCCESS -> colors.green
        ProcessStatusTone.FAILURE -> colors.red
        ProcessStatusTone.NEUTRAL -> colors.muted
    }
    Text(
        status,
        color = color,
        style = MaterialTheme.typography.labelSmall,
        fontFamily = MonoFontFamily,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

@Composable
private fun ProcessKeyValues(info: ProcessInfo) {
    val colors = LlmTheme.colors
    if (info.pid == null && info.exitCode == null) return
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        info.pid?.let {
            Text("pid $it", color = colors.muted, style = MaterialTheme.typography.labelSmall, fontFamily = MonoFontFamily)
        }
        info.exitCode?.let {
            Text(
                "exit $it",
                color = if (it == 0) colors.muted else colors.red,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = MonoFontFamily,
            )
        }
    }
}
