package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily

@Composable
internal fun WorkingDirectoryChip(dir: String) {
    val colors = LlmTheme.colors
    Text(
        "in $dir",
        color = colors.muted,
        style = MaterialTheme.typography.labelSmall,
        fontFamily = MonoFontFamily,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(colors.surface)
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

@Composable
internal fun ShellCommandCard(itemId: String, slot: String, command: String, prefix: String = "$ ") {
    ToolTextCard(
        itemId = itemId,
        slot = slot,
        text = prefix + command,
        color = LlmTheme.colors.fg,
        toggleTag = "pi_tool_command_toggle",
        maxLines = Int.MAX_VALUE,
    )
}
