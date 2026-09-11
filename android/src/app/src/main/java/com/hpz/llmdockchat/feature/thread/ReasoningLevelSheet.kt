package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons


data class ReasoningLevelOption(
    val id: String?,
    val label: String,
    val stale: Boolean = false,
) {
    val isDefault: Boolean get() = id == null && !stale
}

const val REASONING_DEFAULT_LABEL = "Model default"
const val REASONING_NOT_OFFERED_LABEL = "not offered by this model"

fun reasoningLevelOptions(ladder: List<String>, stored: String?): List<ReasoningLevelOption> {
    val options = mutableListOf(ReasoningLevelOption(id = null, label = REASONING_DEFAULT_LABEL))
    options += ladder.map { ReasoningLevelOption(id = it, label = it) }
    if (stored != null && stored !in ladder) {
        options += ReasoningLevelOption(id = stored, label = stored, stale = true)
    }
    return options
}

fun isReasoningLevelStale(ladder: List<String>, stored: String?): Boolean =
    stored != null && stored !in ladder

fun showsReasoningControl(ladder: List<String>, stored: String?): Boolean =
    ladder.isNotEmpty() || stored != null

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReasoningLevelSheet(
    ladder: List<String>,
    stored: String?,
    writePending: Boolean,
    onSelect: (String?) -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LlmTheme.colors
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("reasoning_level_sheet"),
    ) {
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            item {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                    Text(
                        "Reasoning level",
                        color = colors.fg,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "The model's own level names, not token budgets. How much it thinks is the " +
                            "model's choice; \"model default\" says nothing to it at all.",
                        color = colors.subtle,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            items(reasoningLevelOptions(ladder, stored), key = { it.id ?: "__default__" }) { option ->
                ReasoningOptionRow(
                    option = option,
                    selected = option.id == stored && !option.stale,
                    enabled = !writePending && !option.stale,
                    onClick = { onSelect(option.id) },
                )
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun ReasoningOptionRow(
    option: ReasoningLevelOption,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .background(if (selected) colors.accentDeep.copy(alpha = 0.25f) else colors.surface)
            .alpha(if (option.stale) 0.7f else 1f)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag("reasoning_option_${option.id ?: "default"}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            option.label,
            color = when {
                option.stale -> colors.amber
                option.isDefault -> colors.muted
                else -> colors.fg
            },
            style = MaterialTheme.typography.bodyMedium,
            fontFamily = if (option.id != null) FontFamily.Monospace else FontFamily.Default,
            modifier = Modifier.weight(1f),
        )
        if (option.stale) {
            Text(REASONING_NOT_OFFERED_LABEL, color = colors.amber, style = MaterialTheme.typography.labelSmall)
        }
        if (selected) Text("✓", color = colors.accent, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
fun ReasoningLevelChip(
    level: String?,
    stale: Boolean,
    enabled: Boolean,
    pending: Boolean,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    val valueColor = when {
        stale -> colors.amber
        level != null -> colors.accent
        else -> colors.muted
    }
    Box(
        Modifier
            .testTag("thread_reasoning_chip")
            .widthIn(min = 48.dp)
            .heightIn(min = 48.dp)
            .alpha(if (pending) 0.4f else 1f)
            .semantics(mergeDescendants = true) {
                contentDescription = "Reasoning level: " + (level ?: "model default")
            }
            .clickable(
                enabled = enabled,
                role = Role.Button,
                onClickLabel = "Choose the reasoning level",
                onClick = onClick,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier
                .widthIn(max = 128.dp)
                .padding(start = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Icon(
                DesignLabIcons.Brain,
                contentDescription = null,
                tint = valueColor,
                modifier = Modifier.size(21.dp),
            )
            Text(
                level ?: "default",
                color = valueColor,
                style = MaterialTheme.typography.labelMedium,
                fontFamily = FontFamily.Monospace,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            Icon(
                DesignLabIcons.ChevronDown,
                contentDescription = null,
                tint = valueColor,
                modifier = Modifier.size(11.dp),
            )
        }
    }
}
