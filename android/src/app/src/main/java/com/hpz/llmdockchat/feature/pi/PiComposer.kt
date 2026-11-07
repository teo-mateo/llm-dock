package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.icons.AppIcons

@Composable
fun PiComposer(
    live: Boolean,
    working: Boolean,
    draft: String,
    sending: Boolean,
    stopping: Boolean,
    notice: String?,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    val colors = LlmTheme.colors
    if (!live) {
        Text(
            "Session ended — read only",
            color = colors.muted,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        )
        return
    }

    val canSend = draft.isNotBlank() && !sending
    Column(
        Modifier.fillMaxWidth().background(colors.surface).imePadding(),
    ) {
        HorizontalDivider(color = colors.line)
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Box(
                Modifier.weight(1f)
                    .clip(RoundedCornerShape(22.dp))
                    .background(colors.sunken)
                    .border(1.dp, colors.lineStrong, RoundedCornerShape(22.dp))
                    .padding(horizontal = 16.dp, vertical = 12.dp),
            ) {
                if (draft.isEmpty()) {
                    Text(
                        if (working) "Steer pi…" else "Message pi…",
                        style = composerTextStyle(colors.subtle),
                    )
                }
                BasicTextField(
                    value = draft,
                    onValueChange = onDraftChange,
                    enabled = !sending,
                    maxLines = 5,
                    textStyle = composerTextStyle(colors.fg),
                    cursorBrush = SolidColor(colors.accent),
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Sentences,
                        imeAction = ImeAction.Default,
                    ),
                    modifier = Modifier.fillMaxWidth()
                        .heightIn(min = 22.dp)
                        .semantics { contentDescription = "Message to pi" }
                        .testTag("pi_composer_input"),
                )
            }
            if (working) {
                PiActionButton(
                    icon = AppIcons.Stop,
                    description = "Stop the run",
                    testTag = "pi_composer_stop",
                    enabled = !stopping,
                    background = colors.red,
                    onClick = onStop,
                )
            }
            PiActionButton(
                icon = AppIcons.Send,
                description = "Send",
                testTag = "pi_composer_send",
                enabled = canSend,
                background = colors.accent,
                onClick = onSend,
            )
        }
        if (notice != null) {
            Text(
                notice,
                color = colors.red,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 8.dp),
            )
        }
    }
}

@Composable
private fun PiActionButton(
    icon: ImageVector,
    description: String,
    testTag: String,
    enabled: Boolean,
    background: Color,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier.size(44.dp)
            .clip(CircleShape)
            .background(if (enabled) background else colors.surfaceElevated)
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            icon,
            contentDescription = description,
            tint = if (enabled) colors.onAccent else colors.subtle,
            modifier = Modifier.size(18.dp),
        )
    }
}

@Composable
private fun composerTextStyle(color: Color) =
    MaterialTheme.typography.bodyMedium.copy(
        color = color,
        lineHeightStyle = LineHeightStyle(
            alignment = LineHeightStyle.Alignment.Center,
            trim = LineHeightStyle.Trim.None,
        ),
    )
