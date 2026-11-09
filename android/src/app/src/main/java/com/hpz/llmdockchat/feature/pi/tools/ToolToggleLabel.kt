package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

@Composable
internal fun ToolToggleLabel(text: String, onClick: () -> Unit, tag: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.End,
    ) {
        Text(
            text,
            color = LlmTheme.colors.accent,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.clickable(onClick = onClick).testTag(tag),
        )
    }
}
