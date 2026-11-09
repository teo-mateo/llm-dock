package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult

internal enum class ToolResultMode {
    ALL,
    ERRORS_ONLY,
    SUCCESS_ONLY,
}

internal fun isToolError(item: PiItem.Tool, result: ToolResult?): Boolean =
    item.status == ToolStatus.ERROR || result?.isError == true

internal fun toolResultMessage(result: ToolResult?): String = result?.text?.trim().orEmpty()

@Composable
internal fun ToolResultMessage(
    item: PiItem.Tool,
    result: ToolResult?,
    mode: ToolResultMode = ToolResultMode.ALL,
) {
    val message = toolResultMessage(result)
    if (message.isEmpty()) return
    val error = isToolError(item, result)
    if (mode == ToolResultMode.ERRORS_ONLY && !error) return
    if (mode == ToolResultMode.SUCCESS_ONLY && error) return
    Text(
        message,
        color = if (error) LlmTheme.colors.red else LlmTheme.colors.muted,
        style = MaterialTheme.typography.labelSmall,
    )
}
