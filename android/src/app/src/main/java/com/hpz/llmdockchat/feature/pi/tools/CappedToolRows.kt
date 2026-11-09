package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

@Composable
internal fun <T> CappedToolRows(
    itemId: String,
    slot: String,
    items: List<T>,
    cap: Int,
    toggleTag: String,
    rowContent: @Composable (T) -> Unit,
) {
    val colors = LlmTheme.colors
    var showAll by rememberSaveable(itemId, slot) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.surface).padding(8.dp),
        ) {
            items.take(if (showAll) items.size else cap).forEach { rowContent(it) }
        }
        if (items.size > cap) {
            ToolToggleLabel(
                if (showAll) "Show less" else "Show all ${items.size} lines",
                onClick = { showAll = !showAll },
                tag = toggleTag,
            )
        }
    }
}
