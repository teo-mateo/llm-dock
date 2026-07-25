package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.clickable
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons

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
    var showAttachSheet by remember { mutableStateOf(false) }

    if (showAttachSheet) {
        AttachSheet(
            onDismiss = { showAttachSheet = false },
            onPickImage = { showAttachSheet = false; onPickImage() },
            onTakePhoto = { showAttachSheet = false; onTakePhoto() },
        )
    }

    Row(
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // One button, not two. The composer is the width-starved part of the
        // screen and a second 44 dp circle bought nothing the sheet can't say
        // in words — which is also where file browsing will go.
        CircleAction(DesignLabIcons.Paperclip, "Attach", "composer_attach", enabled) { showAttachSheet = true }

        Box(
            Modifier
                .weight(1f)
                .clip(RoundedCornerShape(22.dp))
                .background(colors.sunken)
                .border(1.dp, colors.lineStrong, RoundedCornerShape(22.dp))
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            if (value.isEmpty()) {
                // Same style as the field, so the placeholder sits exactly
                // where the first typed character will.
                Text(
                    if (runActive) "Generating…" else "Message",
                    style = composerTextStyle(colors.subtle),
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
                textStyle = composerTextStyle(colors.fg),
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
                icon = DesignLabIcons.Stop,
                description = "Stop",
                testTag = "composer_stop",
                enabled = !stopping,
                background = colors.red,
                onClick = onStop,
            )
        } else {
            SendButton(
                icon = DesignLabIcons.Send,
                description = "Send",
                testTag = "composer_send",
                enabled = canSend,
                background = colors.accent,
                onClick = onSend,
            )
        }
    }
}

/**
 * A line box taller than the glyphs needs an explicit alignment, or the text
 * is drawn at the *top* of it — which is why a single-line draft sat high in
 * the composer while a multi-line one looked fine. `Trim.None` keeps the
 * padding on the first and last lines so the centring survives wrapping.
 */
@Composable
private fun composerTextStyle(color: androidx.compose.ui.graphics.Color): TextStyle =
    MaterialTheme.typography.bodyMedium.copy(
        color = color,
        lineHeightStyle = LineHeightStyle(
            alignment = LineHeightStyle.Alignment.Center,
            trim = LineHeightStyle.Trim.None,
        ),
    )

/**
 * The attach menu. Its two rows keep the old buttons' test tags — they are the
 * same two actions, just no longer each spending a slot in the composer.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AttachSheet(onDismiss: () -> Unit, onPickImage: () -> Unit, onTakePhoto: () -> Unit) {
    val colors = LlmTheme.colors
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = colors.surface,
        modifier = Modifier.testTag("composer_attach_sheet"),
    ) {
        Column(Modifier.fillMaxWidth().padding(bottom = 28.dp)) {
            AttachSheetRow(DesignLabIcons.Image, "Photo library", "composer_pick_image", onPickImage)
            AttachSheetRow(DesignLabIcons.Camera, "Take photo", "composer_take_photo", onTakePhoto)
        }
    }
}

@Composable
private fun AttachSheetRow(icon: ImageVector, label: String, testTag: String, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 24.dp, vertical = 16.dp)
            .testTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Icon(icon, contentDescription = null, tint = colors.muted, modifier = Modifier.size(21.dp))
        Text(label, color = colors.fg, style = MaterialTheme.typography.bodyLarge)
    }
}

const val COMPOSER_MAX_LINES = 5

@Composable
private fun CircleAction(
    icon: ImageVector,
    description: String,
    testTag: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(colors.surfaceHigh)
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            icon,
            contentDescription = description,
            tint = if (enabled) colors.muted else colors.subtle,
            modifier = Modifier.size(19.dp),
        )
    }
}

@Composable
private fun SendButton(
    icon: ImageVector,
    description: String,
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
        Icon(
            icon,
            contentDescription = description,
            tint = if (enabled) colors.onAccent else colors.subtle,
            modifier = Modifier.size(18.dp),
        )
    }
}
