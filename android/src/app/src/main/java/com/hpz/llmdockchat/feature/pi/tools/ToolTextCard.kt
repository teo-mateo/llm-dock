package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.icons.AppIcons
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

private const val DEFAULT_MAX_LINES = 20

@Composable
internal fun ToolTextCard(
    itemId: String,
    slot: String,
    text: String,
    color: Color,
    toggleTag: String,
    maxLines: Int = DEFAULT_MAX_LINES,
    toggleLabel: (Int) -> String = { "Show all" },
    style: TextStyle = MaterialTheme.typography.bodySmall,
    fontFamily: FontFamily = FontFamily.Monospace,
) {
    val colors = LlmTheme.colors
    var showAll by rememberSaveable(itemId, slot) { mutableStateOf(false) }
    var wrap by rememberSaveable(itemId, slot, "wrap") { mutableStateOf(true) }
    val lines = text.lines()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Box(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.surface).padding(8.dp),
        ) {
            Text(
                if (showAll) text else lines.take(maxLines).joinToString("\n"),
                color = color,
                fontFamily = fontFamily,
                style = style,
                softWrap = wrap,
                modifier = if (wrap) {
                    Modifier.fillMaxWidth().padding(end = 24.dp)
                } else {
                    Modifier.horizontalScroll(rememberScrollState()).padding(end = 24.dp)
                },
            )
            Icon(
                AppIcons.WrapText,
                contentDescription = if (wrap) "Turn off word wrap" else "Turn on word wrap",
                tint = if (wrap) colors.accent else colors.muted,
                modifier = Modifier.align(Alignment.TopEnd).size(20.dp).clickable { wrap = !wrap }.testTag("pi_tool_wrap_$slot"),
            )
        }
        if (lines.size > maxLines) {
            Text(
                if (showAll) "Show less" else toggleLabel(lines.size),
                color = colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.clickable { showAll = !showAll }.testTag(toggleTag),
            )
        }
    }
}
