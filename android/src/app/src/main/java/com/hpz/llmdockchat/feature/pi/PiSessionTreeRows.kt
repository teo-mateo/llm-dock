package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState

@Composable
internal fun DeleteSwipeBackground() {
    Row(
        modifier = Modifier
            .fillMaxSize()
            .background(LlmTheme.colors.red.copy(alpha = 0.85f))
            .padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Delete", color = Color.White, fontFamily = MonoFontFamily)
    }
}

@Composable
internal fun piStatusColor(state: PiState): Color {
    val colors = LlmTheme.colors
    return when (state) {
        PiState.WORKING -> colors.amber
        PiState.IDLE -> colors.green
        PiState.ENDED -> colors.subtle
    }
}

@Composable
private fun PiSectionHeader(title: String) {
    Text(title, color = LlmTheme.colors.muted, style = MaterialTheme.typography.labelMedium)
}

@Composable
private fun PiProjectHeader(
    section: PiSection,
    group: PiProjectGroup,
    expanded: Boolean,
    onToggle: (PiSection, String) -> Unit,
) {
    val colors = LlmTheme.colors
    val count = group.roots.sumOf { 1 + it.children.size }
    Row(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .clickable { onToggle(section, group.project) }
            .padding(horizontal = 6.dp, vertical = 8.dp)
            .testTag("pi_project_${section.name.lowercase()}_${group.project}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            if (expanded) "\u25BE" else "\u25B8",
            color = colors.muted,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.width(12.dp),
        )
        Text(
            group.project,
            color = colors.fg,
            style = MaterialTheme.typography.labelMedium,
            fontFamily = MonoFontFamily,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text("$count", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
    }
}

internal fun LazyListScope.piSectionRows(
    section: PiSection,
    title: String,
    groups: List<PiProjectGroup>,
    toggles: Map<String, Boolean>,
    cacheLabels: PiCacheLabels,
    onOpen: (PiSessionKey) -> Unit,
    onSwipeDelete: (PiSession) -> Unit,
    onToggleProject: (PiSection, String) -> Unit,
) {
    if (groups.isEmpty()) return
    item(key = "${section.name.lowercase()}_header") { PiSectionHeader(title) }
    for (group in groups) {
        val expanded = piProjectExpanded(section, group.project, toggles)
        item(key = "project:${piProjectKey(section, group.project)}") {
            PiProjectHeader(section, group, expanded, onToggleProject)
        }
        if (!expanded) continue
        for (node in group.roots) {
            item(key = "${node.session.key.sessionId}/${node.session.key.instanceId}") {
                PiSessionSwipeRow(node.session, cacheLabels.sizes[node.session.key], onOpen, onSwipeDelete)
            }
            for (child in node.children) {
                item(key = "${child.key.sessionId}/${child.key.instanceId}") {
                    PiSubagentSwipeRow(child, cacheLabels.sizes[child.key], onOpen, onSwipeDelete)
                }
            }
        }
    }
}

@Composable
private fun PiSubagentSwipeRow(
    session: PiSession,
    cachedSize: String?,
    onOpen: (PiSessionKey) -> Unit,
    onSwipeDelete: (PiSession) -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value != SwipeToDismissBoxValue.Settled) onSwipeDelete(session)
            false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        modifier = Modifier.testTag("pi_subagent_swipe_${session.key.sessionId}_${session.key.instanceId}"),
        backgroundContent = { if (dismissState.progress < 1f) DeleteSwipeBackground() },
    ) {
        PiSubagentRow(session, onOpen, cachedSize)
    }
}

@Composable
private fun PiSubagentRow(
    session: PiSession,
    onOpen: (PiSessionKey) -> Unit,
    cachedSize: String?,
) {
    val colors = LlmTheme.colors
    val statusColor = piStatusColor(session.state)
    val nowMs = remember { System.currentTimeMillis() }
    val emphasis = if (session.state == PiState.ENDED) 0.72f else 1f
    Column(
        Modifier.fillMaxWidth().padding(start = 18.dp).heightIn(min = 40.dp).alpha(emphasis)
            .background(colors.surface, RoundedCornerShape(12.dp))
            .border(1.dp, colors.line, RoundedCornerShape(12.dp))
            .clickable { onOpen(session.key) }
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .testTag("pi_subagent_${session.key.sessionId}_${session.key.instanceId}"),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Box(Modifier.size(6.dp).clip(CircleShape).background(statusColor))
            Text(
                "subagent",
                color = colors.purple,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.background(colors.purple.copy(alpha = 0.16f), RoundedCornerShape(6.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp)
                    .testTag("pi_subagent_chip_${session.key.sessionId}_${session.key.instanceId}"),
            )
            Text(
                piSessionTitle(session),
                color = colors.fg,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Text(
                piStatusLabel(session),
                color = statusColor,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                formatAgo(nowMs, session.lastSeen),
                color = colors.subtle,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1,
            )
            cachedSize?.let {
                Text(
                    it,
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                    fontSize = 10.sp,
                    maxLines = 1,
                )
            }
            if (session.needsAnswer) {
                Text(
                    "Needs answer",
                    color = colors.purple,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                )
            }
        }
    }
}
