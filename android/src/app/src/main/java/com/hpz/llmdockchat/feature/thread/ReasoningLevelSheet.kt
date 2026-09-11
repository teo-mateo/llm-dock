package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * F15 — the per-conversation reasoning level: the thread header's chip and the
 * sheet it opens.
 *
 * The three functions at the top of this file are the whole decision, kept pure
 * and public on purpose. Nothing about F15-R1/R2/R3 needs a device to pin, and
 * the project's precedent for sheet content is exactly this split —
 * `feature/modelpicker/ModelPickerSheetTest` exists because the picker itself is
 * not testable without Compose. Rendering is covered on device instead.
 */

/** One row of [ReasoningLevelSheet]'s option list. */
data class ReasoningLevelOption(
    /** What goes to the server. `null` = "Model default" = say nothing. */
    val id: String?,
    val label: String,
    /** A stored level the service no longer declares — listed, never sendable. */
    val stale: Boolean = false,
) {
    val isDefault: Boolean get() = id == null && !stale
}

const val REASONING_DEFAULT_LABEL = "Model default"
const val REASONING_NOT_OFFERED_LABEL = "not offered by this model"

/**
 * "Model default" first, then the declared levels in declaration order, then a
 * stranded level last (F15-R2, F15-R3).
 *
 * Nothing is invented here: no level inserted because a neighbour exists, no
 * re-sorting into "less thinking → more thinking", the server's order preserved
 * exactly (F15-R1). The stale row exists so a value the server still holds can
 * be seen and cleared — it is listed but not selectable, and picking anything
 * else replaces it.
 */
fun reasoningLevelOptions(ladder: List<String>, stored: String?): List<ReasoningLevelOption> {
    val options = mutableListOf(ReasoningLevelOption(id = null, label = REASONING_DEFAULT_LABEL))
    options += ladder.map { ReasoningLevelOption(id = it, label = it) }
    if (stored != null && stored !in ladder) {
        options += ReasoningLevelOption(id = stored, label = stored, stale = true)
    }
    return options
}

/** A stored level the ladder no longer declares (F15-R3). A null stored level is never stale. */
fun isReasoningLevelStale(ladder: List<String>, stored: String?): Boolean =
    stored != null && stored !in ladder

/**
 * The control appears when there is something to choose, or when a value the
 * server still holds needs a way to be seen and cleared (F15-R3). Never on
 * OpenRouter (F15-R8): the server resolves no ladder for an `openrouter:`
 * service and rejects any level written to one, so such a thread can never hold
 * a value either.
 */
fun showsReasoningControl(ladder: List<String>, stored: String?, onOpenRouter: Boolean): Boolean =
    !onOpenRouter && (ladder.isNotEmpty() || stored != null)

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
                    // A stale row is a label, not a choice (F15-R3): the server
                    // will not send it, so offering it as a tap target would be
                    // an error waiting for a run.
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

/**
 * The header chip. F15's *Deviations* puts it here rather than in the composer's
 * control rail as on the desktop; what stays identical to web is the behaviour.
 *
 * Fixed width and ellipsized, so the model label beside it shrinks rather than
 * the 64 dp header growing. [pending] dims it while the write is in flight —
 * and the sheet stays open until that write lands, so choosing and immediately
 * sending can never send the old level (F15-R2's last criterion).
 */
@Composable
fun ReasoningLevelChip(
    level: String?,
    stale: Boolean,
    enabled: Boolean,
    pending: Boolean,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    val tint = when {
        stale -> colors.amber
        level != null -> colors.accent
        else -> colors.subtle
    }
    Box(
        Modifier
            .testTag("thread_reasoning_chip")
            .padding(start = 6.dp)
            .alpha(if (pending) 0.4f else 1f)
            .border(1.dp, colors.line, RoundedCornerShape(6.dp))
            .background(colors.sunken, RoundedCornerShape(6.dp))
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 7.dp, vertical = 3.dp),
    ) {
        Text(
            level ?: "default",
            color = tint,
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}
