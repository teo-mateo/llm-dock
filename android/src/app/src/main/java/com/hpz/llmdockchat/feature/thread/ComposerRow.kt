package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.clickable
import androidx.compose.ui.text.TextStyle
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * F04-R1. Multi-line, five lines then internal scroll, Enter is a newline.
 *
 * [ImeAction.Default] on a multi-line field is what gives the IME a return key
 * that inserts a newline instead of a "send" key — the opposite of the desktop,
 * deliberately, because a thumb hits Enter by accident and a mis-sent turn
 * costs a whole generation.
 */
@Composable
fun ComposerRow(
    value: String,
    enabled: Boolean,
    canSend: Boolean,
    runActive: Boolean,
    stopping: Boolean,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
    onPickImage: () -> Unit,
    onTakePhoto: () -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CircleAction("🖼", "composer_pick_image", enabled, onPickImage)
        CircleAction("📷", "composer_take_photo", enabled, onTakePhoto)

        Box(
            Modifier
                .weight(1f)
                .clip(RoundedCornerShape(20.dp))
                .background(colors.sunken)
                .border(1.dp, colors.line, RoundedCornerShape(20.dp))
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            if (value.isEmpty()) {
                Text(
                    if (runActive) "Generating…" else "Message",
                    color = colors.subtle,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                enabled = enabled,
                // Five lines then scroll: `maxLines` caps the measured height,
                // and BasicTextField scrolls its own content beyond that, so a
                // long draft never pushes the thread off screen.
                maxLines = COMPOSER_MAX_LINES,
                textStyle = TextStyle(
                    color = colors.fg,
                    fontSize = MaterialTheme.typography.bodyMedium.fontSize,
                    lineHeight = MaterialTheme.typography.bodyMedium.lineHeight,
                ),
                cursorBrush = androidx.compose.ui.graphics.SolidColor(colors.accent),
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Sentences,
                    imeAction = ImeAction.Default,
                ),
                // Fills the rounded box so the whole field is the touch
                // target; a BasicTextField sizes to its content otherwise, and
                // an empty composer would be a sliver to hit with a thumb.
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 22.dp)
                    .testTag("composer_input"),
            )
        }

        if (runActive) {
            SendButton(
                label = "■",
                testTag = "composer_stop",
                enabled = !stopping,
                background = colors.red,
                onClick = onStop,
            )
        } else {
            SendButton(
                label = "↑",
                testTag = "composer_send",
                enabled = canSend,
                background = colors.accent,
                onClick = onSend,
            )
        }
    }
}

const val COMPOSER_MAX_LINES = 5

@Composable
private fun CircleAction(label: String, testTag: String, enabled: Boolean, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(colors.surfaceElevated)
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (enabled) colors.muted else colors.subtle)
    }
}

@Composable
private fun SendButton(
    label: String,
    testTag: String,
    enabled: Boolean,
    background: androidx.compose.ui.graphics.Color,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(if (enabled) background else colors.surfaceElevated)
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (enabled) colors.onAccent else colors.subtle,
            style = MaterialTheme.typography.titleMedium,
        )
    }
}
