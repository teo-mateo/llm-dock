package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.tools.ProcessStatusTone

@Composable
internal fun statusToneColor(tone: ProcessStatusTone) = when (tone) {
    ProcessStatusTone.RUNNING -> LlmTheme.colors.amber
    ProcessStatusTone.SUCCESS -> LlmTheme.colors.green
    ProcessStatusTone.FAILURE -> LlmTheme.colors.red
    ProcessStatusTone.NEUTRAL -> LlmTheme.colors.muted
}

@Composable
internal fun ToolStatusChip(label: String, tone: ProcessStatusTone) {
    val color = statusToneColor(tone)
    Text(
        label,
        color = color,
        style = MaterialTheme.typography.labelSmall,
        fontFamily = MonoFontFamily,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}
