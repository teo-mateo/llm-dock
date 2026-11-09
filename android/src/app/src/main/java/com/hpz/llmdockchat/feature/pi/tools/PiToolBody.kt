package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.runtime.Composable
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus

@Composable
fun PiToolBody(item: PiItem.Tool) = when (item.name) {
    else -> GenericToolBody(item)
}

@Composable
internal fun statusColor(status: ToolStatus) = when (status) {
    ToolStatus.RUNNING -> LlmTheme.colors.amber
    ToolStatus.DONE -> LlmTheme.colors.green
    ToolStatus.ERROR -> LlmTheme.colors.red
}
