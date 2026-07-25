package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.prefs.ChatAppearance
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import kotlin.math.roundToInt

/**
 * Everything you change about the chat you are in, in one sheet: how big the
 * text is, which model answers, and which tools it may call.
 *
 * Replaces the two-item overflow menu, where both entries were a second tap
 * away from a sheet of their own and neither could show its current state.
 * Tools are listed in place — the whole registry, each a switch — because the
 * one thing you come here to do is flip one on.
 *
 * The sheet deliberately renders at [baseDensity] — the device's own — rather
 * than at the chat's scaled one. `LocalDensity` is a *static* CompositionLocal,
 * so changing it recomposes the whole subtree in one frame; with the sheet
 * inside that subtree, every A−/A+ press re-measured and resized the sheet
 * under the finger, which read as a flicker. The percentage is the readout
 * instead, and the thread behind the sheet is what actually changes size.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatSettingsSheet(
    modelName: String,
    canSwitchModel: Boolean,
    onOpenModelPicker: () -> Unit,
    servers: List<McpServerInfo>,
    selectedIds: Set<String>,
    canToggleTools: Boolean,
    onToggleTool: (String) -> Unit,
    prompts: List<ManagedPrompt>,
    activePromptContent: String,
    onSelectPrompt: (ManagedPrompt) -> Unit,
    textScale: Float,
    onTextScaleChange: (Float) -> Unit,
    baseDensity: Density,
    onDismiss: () -> Unit,
) {
    val colors = LlmTheme.colors
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("chat_settings_sheet"),
    ) {
      CompositionLocalProvider(LocalDensity provides baseDensity) {
        // C3: the sheet draws behind the navigation bar, so without this its
        // last row is unreachable under the button bar.
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            item { SectionLabel("Text size") }
            item {
                TextSizeRow(
                    scale = textScale,
                    onChange = onTextScaleChange,
                )
            }

            item { SectionLabel("Model") }
            item {
                SettingRow(
                    icon = DesignLabIcons.Chip,
                    enabled = canSwitchModel,
                    onClick = onOpenModelPicker,
                    testTag = "settings_switch_model",
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            modelName,
                            color = if (canSwitchModel) colors.fg else colors.subtle,
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodyMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            if (canSwitchModel) "Tap to change" else "Unavailable while a run is active",
                            color = colors.subtle,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    Icon(
                        DesignLabIcons.ChevronRight,
                        contentDescription = null,
                        tint = colors.subtle,
                        modifier = Modifier.size(16.dp),
                    )
                }
            }

            if (prompts.isNotEmpty()) {
                item { SectionLabel("System prompt") }
                items(prompts, key = { "prompt_${it.id}" }) { prompt ->
                    // Matched on content, not id: the conversation stores the
                    // resolved text, so a thread created before a prompt was
                    // edited legitimately matches nothing and shows as custom.
                    PromptRow(
                        prompt = prompt,
                        selected = prompt.content == activePromptContent,
                        enabled = canToggleTools,
                        onClick = { onSelectPrompt(prompt) },
                    )
                }
                if (prompts.none { it.content == activePromptContent }) {
                    item {
                        Text(
                            "This chat is using a prompt that isn't in the list — picking one replaces it.",
                            color = colors.subtle,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
                        )
                    }
                }
            }

            item {
                SectionLabel(
                    if (canToggleTools) "Tools" else "Tools · unavailable while a run is active",
                )
            }
            if (servers.isEmpty()) {
                item {
                    Text(
                        "No tools configured on the dashboard.",
                        color = colors.subtle,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 10.dp),
                    )
                }
            }
            items(servers, key = { it.id }) { server ->
                ToolRow(
                    server = server,
                    checked = server.id in selectedIds,
                    enabled = canToggleTools,
                    onToggle = { onToggleTool(server.id) },
                )
            }
            item { Box(Modifier.height(24.dp)) }
        }
      }
    }
}

@Composable
private fun SectionLabel(text: String) {
    val colors = LlmTheme.colors
    Text(
        text,
        color = colors.subtle,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 4.dp),
    )
}

/**
 * A−, the current percentage, A+, and a Reset that only appears off default.
 *
 * The two glyphs are a small and a large A rather than −/+ signs, so which
 * button does what is legible without a label. They are fixed sizes: the sheet
 * renders at base density (see this file's header), so the readout is the
 * percentage and the thread behind it.
 */
@Composable
private fun TextSizeRow(scale: Float, onChange: (Float) -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        StepButton(
            label = "A",
            fontSize = 13.sp,
            enabled = scale > ChatAppearance.MIN,
            testTag = "text_size_decrease",
            onClick = { onChange(scale - ChatAppearance.STEP) },
        )
        StepButton(
            label = "A",
            fontSize = 21.sp,
            enabled = scale < ChatAppearance.MAX,
            testTag = "text_size_increase",
            onClick = { onChange(scale + ChatAppearance.STEP) },
        )
        Text(
            "${(scale * 100).roundToInt()}%",
            color = colors.muted,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f).testTag("text_size_value"),
        )
        if (scale != ChatAppearance.DEFAULT) {
            Text(
                "Reset",
                color = colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier
                    .clickable { onChange(ChatAppearance.DEFAULT) }
                    .padding(horizontal = 8.dp, vertical = 6.dp)
                    .testTag("text_size_reset"),
            )
        }
    }
}

@Composable
private fun StepButton(
    label: String,
    fontSize: androidx.compose.ui.unit.TextUnit,
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
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun SettingRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    enabled: Boolean,
    onClick: () -> Unit,
    testTag: String,
    content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 12.dp)
            .testTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (enabled) colors.muted else colors.subtle,
            modifier = Modifier.size(20.dp),
        )
        content()
    }
}

/**
 * A radio-style row: one of these is the thread's prompt, so a switch per row
 * would be wrong — it would suggest they combine.
 */
@Composable
private fun PromptRow(
    prompt: ManagedPrompt,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 10.dp)
            .testTag("prompt_option_${prompt.id}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .size(18.dp)
                .clip(CircleShape)
                .background(if (selected) colors.accent else Color.Transparent)
                .border(1.5.dp, if (selected) colors.accent else colors.lineStrong, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) Box(Modifier.size(6.dp).clip(CircleShape).background(colors.onAccent))
        }
        Text(
            prompt.name,
            color = if (enabled) colors.fg else colors.subtle,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ToolRow(
    server: McpServerInfo,
    checked: Boolean,
    enabled: Boolean,
    onToggle: () -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, onClick = onToggle)
            .padding(horizontal = 20.dp, vertical = 8.dp)
            .testTag("tool_option_${server.id}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                server.name,
                color = if (enabled) colors.fg else colors.subtle,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                server.description,
                color = colors.subtle,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
        // A switch rather than the old checkbox: these are on/off capabilities
        // for the whole thread, not items being picked out of a list.
        Switch(
            checked = checked,
            onCheckedChange = { onToggle() },
            enabled = enabled,
            colors = SwitchDefaults.colors(
                checkedThumbColor = colors.onAccent,
                checkedTrackColor = colors.accent,
                uncheckedThumbColor = colors.muted,
                uncheckedTrackColor = Color.Transparent,
                uncheckedBorderColor = colors.lineStrong,
            ),
            modifier = Modifier.width(52.dp),
        )
    }
}
