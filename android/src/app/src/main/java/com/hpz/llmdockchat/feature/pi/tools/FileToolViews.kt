package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitPath

@Composable
internal fun PathHeader(path: String) {
    val colors = LlmTheme.colors
    val split = splitPath(path)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        if (split.dir.isNotEmpty()) {
            Text(
                split.dir,
                color = colors.muted,
                fontFamily = MonoFontFamily,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
        }
        Text(
            split.name,
            color = colors.fg,
            fontFamily = MonoFontFamily,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
        )
    }
}
