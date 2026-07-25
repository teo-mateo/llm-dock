package com.hpz.llmdockchat.feature.designlab

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme

/**
 * Mockup — model detail: status, resource stats, launch flags, actions.
 * Compared against `ModelDetailScreen`.
 */
@Composable
fun MockModelDetailScreen() {
    val colors = DesignLabTheme.colors
    val model = MOCK_MODEL_DETAIL
    val (chipBg, chipFg) = engineChipColors(model.engine)
    // Stopping is destructive to whatever's mid-generation on that model, so
    // it gets a confirmation popup instead of firing on the first tap.
    var showStopConfirm by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().background(colors.app)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = {}) { Icon(DesignLabIcons.Back, contentDescription = "Back", tint = colors.fg) }
            Text(
                "Model detail",
                style = MaterialTheme.typography.titleMedium,
                color = colors.fg,
                modifier = Modifier.weight(1f),
            )
            // Logs are one tap away from anywhere on the screen, not just at
            // the bottom of a scroll — the owner flagged logs as too buried.
            IconButton(onClick = {}) {
                Icon(DesignLabIcons.Terminal, contentDescription = "View logs", tint = colors.accent)
            }
        }

        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DlIconBadge(
                    icon = DesignLabIcons.Chip,
                    tint = colors.green,
                    background = colors.accentSoft,
                    modifier = Modifier.size(52.dp),
                )
                Column {
                    Text(model.name, style = MaterialTheme.typography.titleLarge, color = colors.fg)
                    Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DlChip(model.engine, chipBg, chipFg)
                        DlChip("running", colors.green.copy(alpha = 0.16f), colors.green)
                    }
                }
            }

            DlCard(Modifier.padding(top = 20.dp)) {
                Column {
                    Text("Resources", style = MaterialTheme.typography.titleMedium, color = colors.fg)
                    StatRow("Port", ":${model.port}")
                    StatRow("Alias", model.alias)
                    StatRow("VRAM", model.vram)
                    StatRow("Context", model.ctx)
                }
            }

            DlCard(Modifier.padding(top = 12.dp)) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(DesignLabIcons.Terminal, contentDescription = null, tint = colors.muted, modifier = Modifier.size(16.dp))
                        Text("Launch flags", style = MaterialTheme.typography.titleMedium, color = colors.fg)
                    }
                    Column(Modifier.padding(top = 10.dp)) {
                        model.flags.forEach { flag ->
                            Text(
                                flag,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodyMedium,
                                color = colors.muted,
                                modifier = Modifier.padding(vertical = 3.dp),
                            )
                        }
                    }
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(vertical = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Logs promoted to the primary (filled, accent) action — the
                // owner's second note. Stop stays reachable but demoted, since
                // it's destructive and shouldn't be the thing the eye lands on.
                ActionButton(
                    label = "View logs",
                    icon = DesignLabIcons.Terminal,
                    background = colors.accent,
                    foreground = colors.onAccent,
                    modifier = Modifier.weight(2f),
                )
                ActionButton(
                    label = "Stop",
                    icon = DesignLabIcons.Power,
                    background = colors.red.copy(alpha = 0.16f),
                    foreground = colors.red,
                    modifier = Modifier.weight(1f),
                    onClick = { showStopConfirm = true },
                )
            }
        }
    }

    if (showStopConfirm) {
        StopConfirmDialog(
            modelName = model.name,
            onDismiss = { showStopConfirm = false },
            onConfirm = { showStopConfirm = false },
        )
    }
}

@Composable
private fun StopConfirmDialog(modelName: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    val colors = DesignLabTheme.colors
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(colors.surfaceElevated)
                .border(1.dp, colors.lineStrong, RoundedCornerShape(20.dp))
                .padding(20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DlIconBadge(
                    icon = DesignLabIcons.Power,
                    tint = colors.red,
                    background = colors.red.copy(alpha = 0.16f),
                    modifier = Modifier.size(40.dp),
                )
                Text("Stop this model?", style = MaterialTheme.typography.titleMedium, color = colors.fg)
            }
            Text(
                "$modelName will stop accepting requests. Any conversation using it will need it started again before it can reply.",
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
                modifier = Modifier.padding(top = 12.dp, bottom = 20.dp),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ActionButton(
                    label = "Cancel",
                    icon = null,
                    background = colors.surfaceHigh,
                    foreground = colors.fg,
                    modifier = Modifier.weight(1f),
                    onClick = onDismiss,
                )
                ActionButton(
                    label = "Stop",
                    icon = DesignLabIcons.Power,
                    background = colors.red,
                    foreground = colors.onAccent,
                    modifier = Modifier.weight(1f),
                    onClick = onConfirm,
                )
            }
        }
    }
}

@Composable
private fun StatRow(label: String, value: String) {
    val colors = DesignLabTheme.colors
    Row(
        Modifier.fillMaxWidth().padding(top = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = colors.subtle)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = colors.fg)
    }
}

@Composable
private fun ActionButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector?,
    background: androidx.compose.ui.graphics.Color,
    foreground: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {},
) {
    Row(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .background(background)
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, tint = foreground, modifier = Modifier.size(16.dp))
            Text(label, color = foreground, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(start = 8.dp))
        } else {
            Text(label, color = foreground, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Preview(name = "Model detail — dark", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockModelDetailDarkPreview() {
    DesignLabTheme(darkTheme = true) { MockModelDetailScreen() }
}

@Preview(name = "Model detail — light", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockModelDetailLightPreview() {
    DesignLabTheme(darkTheme = false) { MockModelDetailScreen() }
}
