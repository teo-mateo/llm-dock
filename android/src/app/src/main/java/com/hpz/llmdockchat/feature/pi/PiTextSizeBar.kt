package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.prefs.LocalPiTextAppearance
import com.hpz.llmdockchat.core.prefs.PiTextAppearance
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

@Composable
fun PiTextSizeBar(onClose: () -> Unit) {
    val appearance = LocalPiTextAppearance.current
    val colors = LlmTheme.colors
    val scale by appearance.scale.collectAsState()

    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .padding(horizontal = 16.dp)
            .testTag("pi_text_size_bar"),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                "Answer text",
                color = colors.fg,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            SizeStep(
                label = "A",
                fontSize = 13.sp,
                enabled = scale > PiTextAppearance.MIN,
                testTag = "pi_text_size_decrease",
                onClick = { appearance.setScale(scale - PiTextAppearance.STEP) },
            )
            SizeStep(
                label = "A",
                fontSize = 21.sp,
                enabled = scale < PiTextAppearance.MAX,
                testTag = "pi_text_size_increase",
                onClick = { appearance.setScale(scale + PiTextAppearance.STEP) },
            )
            Text(
                PiTextAppearance.label(scale),
                color = colors.muted,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag("pi_text_size_value"),
            )
            if (!PiTextAppearance.isDefault(scale)) {
                Text(
                    "Reset",
                    color = colors.accent,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier
                        .clickable { appearance.setScale(PiTextAppearance.DEFAULT) }
                        .padding(horizontal = 8.dp, vertical = 12.dp)
                        .testTag("pi_text_size_reset"),
                )
            }
            Text(
                "Done",
                color = colors.muted,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier
                    .clickable(onClick = onClose)
                    .padding(horizontal = 4.dp, vertical = 12.dp)
                    .testTag("pi_text_size_done"),
            )
        }
        Text(
            "Only pi answers change size. Buttons, rows and the composer follow the system text size.",
            color = colors.subtle,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
        )
        HorizontalDivider(color = colors.line)
    }
}

@Composable
private fun SizeStep(
    label: String,
    fontSize: TextUnit,
    enabled: Boolean,
    testTag: String,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(44.dp)
            .background(colors.surfaceHigh, RoundedCornerShape(12.dp))
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (enabled) colors.fg else colors.subtle,
            fontSize = fontSize,
        )
    }
}
