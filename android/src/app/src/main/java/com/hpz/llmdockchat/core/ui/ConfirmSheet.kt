package com.hpz.llmdockchat.core.ui

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
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * The app's one confirmation dialog.
 *
 * Material's `AlertDialog` was used everywhere before and looked it: a
 * left-aligned title, body copy at whatever the default is, and two text
 * buttons crammed bottom-right, with the destructive one indistinguishable
 * from Cancel apart from its colour. This gives the action an icon badge in
 * its own tint, full-width buttons in reading order, and a filled primary so
 * the thing you are confirming is the thing you can see.
 *
 * [tint] carries the meaning — red for a destructive action, green for
 * starting something, accent otherwise — and colours the badge and the
 * primary button together, so the two never disagree.
 */
@Composable
fun ConfirmDialog(
    icon: ImageVector,
    title: String,
    message: String,
    confirmLabel: String,
    tint: Color,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    dismissLabel: String = "Cancel",
    testTag: String = "confirm_dialog",
) {
    val colors = LlmTheme.colors
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(24.dp))
                .background(colors.surface)
                .padding(24.dp)
                .testTag(testTag),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(tint.copy(alpha = 0.13f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(23.dp))
            }
            Text(
                title,
                color = colors.fg,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 16.dp),
            )
            Text(
                message,
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp),
            )
            Row(
                Modifier.fillMaxWidth().padding(top = 22.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                DialogButton(
                    label = dismissLabel,
                    foreground = colors.muted,
                    background = colors.surfaceHigh,
                    onClick = onDismiss,
                    testTag = "confirm_dialog_dismiss",
                    modifier = Modifier.weight(1f),
                )
                DialogButton(
                    label = confirmLabel,
                    foreground = colors.onAccent,
                    background = tint,
                    onClick = onConfirm,
                    testTag = "confirm_dialog_confirm",
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

/** A one-button variant for "this failed, here is why". */
@Composable
fun NoticeDialog(
    icon: ImageVector,
    title: String,
    message: String,
    tint: Color,
    onDismiss: () -> Unit,
    testTag: String = "notice_dialog",
) {
    val colors = LlmTheme.colors
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(24.dp))
                .background(colors.surface)
                .padding(24.dp)
                .testTag(testTag),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(tint.copy(alpha = 0.13f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(23.dp))
            }
            Text(
                title,
                color = colors.fg,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 16.dp),
            )
            Text(
                message,
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp),
            )
            DialogButton(
                label = "OK",
                foreground = colors.onAccent,
                background = colors.accent,
                onClick = onDismiss,
                testTag = "notice_dialog_ok",
                modifier = Modifier.fillMaxWidth().padding(top = 22.dp),
            )
        }
    }
}

@Composable
private fun DialogButton(
    label: String,
    foreground: Color,
    background: Color,
    onClick: () -> Unit,
    testTag: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .background(background)
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = foreground, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
    }
}
