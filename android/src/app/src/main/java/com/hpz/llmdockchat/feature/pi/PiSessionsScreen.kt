package com.hpz.llmdockchat.feature.pi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.draw.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.*
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.*
import androidx.compose.ui.unit.*
import com.hpz.llmdockchat.core.ui.theme.*
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.data.model.*
@Composable
fun PiSessionsScreen(
    state: PiSessionsUiState,
    onOpen: (PiSessionKey) -> Unit,
    onSwipeDelete: (PiSession) -> Unit,
    onUndoDelete: () -> Unit,
    cacheLabels: PiCacheLabels = PiCacheLabels(),
    projectToggles: Map<String, Boolean> = emptyMap(),
    onToggleProject: (PiSection, String) -> Unit = { _, _ -> },
) {
    val colors = LlmTheme.colors
    val loaded = state as? PiSessionsUiState.Loaded
    val snackbarHost = remember { SnackbarHostState() }

    LaunchedEffect(loaded?.actionError) {
        loaded?.actionError?.let { snackbarHost.showSnackbar(it) }
    }

    // Indefinite on purpose: the undo window is timed by the ViewModel, and when
    // it expires pendingUndo goes null, this effect is cancelled, and the
    // snackbar goes with it. A duration here would be a second clock to keep
    // in sync with that one.
    val pendingUndo = loaded?.pendingUndo
    LaunchedEffect(pendingUndo?.key) {
        val pending = pendingUndo ?: return@LaunchedEffect
        val result = snackbarHost.showSnackbar(
            message = "Deleted \u201c${pending.label}\u201d",
            actionLabel = "Undo",
            duration = SnackbarDuration.Indefinite,
        )
        if (result == SnackbarResult.ActionPerformed) onUndoDelete()
    }

    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
        Column(
            Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.statusBars)
                .padding(horizontal = 20.dp, vertical = 12.dp),
        ) {
            Text(
                "pi sessions",
                color = colors.fg,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            if (loaded != null) {
                Text(
                    "${loaded.live.size} live · ${loaded.ended.size} ended",
                    color = colors.subtle,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            cacheLabels.warning?.let {
                Text(
                    it,
                    color = colors.amber,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 10.dp).fillMaxWidth()
                        .background(colors.amber.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
                        .padding(horizontal = 10.dp, vertical = 8.dp)
                        .testTag("pi_cache_warning"),
                )
            }
            when (state) {
                is PiSessionsUiState.Loading -> Box(
                    Modifier.fillMaxWidth().weight(1f),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator(color = colors.accent) }
                is PiSessionsUiState.Loaded -> {
                    val tree = state.tree
                    if (state.stale) {
                        Text(
                            "Reconnecting…",
                            color = colors.amber,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(top = 10.dp).fillMaxWidth()
                                .background(colors.amber.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 8.dp),
                        )
                    }
                    if (state.isEmpty) {
                        Box(
                            Modifier.fillMaxWidth().weight(1f),
                            contentAlignment = Alignment.Center,
                        ) {
                            PiSessionsEmptyState()
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxWidth().weight(1f),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            contentPadding = PaddingValues(top = 10.dp, bottom = 16.dp),
                        ) {
                            piSectionRows(
                                PiSection.LIVE,
                                "Live",
                                tree.live,
                                projectToggles,
                                cacheLabels,
                                onOpen,
                                onSwipeDelete,
                                onToggleProject,
                            )
                            piSectionRows(
                                PiSection.ENDED,
                                "Ended",
                                tree.ended,
                                projectToggles,
                                cacheLabels,
                                onOpen,
                                onSwipeDelete,
                                onToggleProject,
                            )
                        }
                    }
                }
            }
        }
        SnackbarHost(
            snackbarHost,
            modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
        ) { data ->
            Snackbar(
                data,
                containerColor = colors.surface,
                contentColor = colors.fg,
                actionColor = colors.accent,
                shape = RoundedCornerShape(14.dp),
            )
        }
    }
}

@Composable
private fun PiSessionsEmptyState() {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxWidth().padding(32.dp).testTag("pi_sessions_empty"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("No pi sessions yet", color = colors.fg, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            "Start pi with the pi-remote extension and it will appear here.",
            color = colors.muted,
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun PiSessionSwipeRow(
    session: PiSession,
    cachedSize: String?,
    onOpen: (PiSessionKey) -> Unit,
    onSwipeDelete: (PiSession) -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            // The library never commits: the row springs back and the ViewModel
            // is what takes it out of the list, so an undo can put it back.
            if (value != SwipeToDismissBoxValue.Settled) onSwipeDelete(session)
            false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        modifier = Modifier.testTag("pi_session_swipe_${session.key.sessionId}_${session.key.instanceId}"),
        backgroundContent = { if (dismissState.progress < 1f) DeleteSwipeBackground() },
    ) {
        PiSessionRow(session, onOpen, cachedSize)
    }
}

@Composable
fun PiSessionRow(session: PiSession, onOpen: (PiSessionKey) -> Unit, cachedSize: String? = null) {
    val colors = LlmTheme.colors
    val status = piStatusLabel(session)
    val statusColor = piStatusColor(session.state)
    val name = piSessionTitle(session)
    val nowMs = remember { System.currentTimeMillis() }
    val emphasis = if (session.state == PiState.ENDED) 0.72f else 1f
    Column(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).alpha(emphasis)
            .background(colors.surface, RoundedCornerShape(14.dp))
            .border(1.dp, colors.line, RoundedCornerShape(14.dp))
            .clickable { onOpen(session.key) }
            .padding(horizontal = 14.dp, vertical = 10.dp)
            .testTag("pi_session_${session.key.sessionId}_${session.key.instanceId}"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(statusColor))
            Text(
                name,
                color = colors.fg,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (session.needsAnswer) {
                Text(
                    "Needs answer",
                    color = colors.purple,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    modifier = Modifier
                        .background(colors.purple.copy(alpha = 0.16f), RoundedCornerShape(8.dp))
                        .padding(horizontal = 8.dp, vertical = 3.dp)
                        .testTag("pi_needs_answer_${session.key.sessionId}_${session.key.instanceId}"),
                )
            }
            Text(
                status,
                color = statusColor,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.background(statusColor.copy(alpha = 0.14f), RoundedCornerShape(8.dp))
                    .padding(horizontal = 8.dp, vertical = 3.dp),
            )
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                piSessionMetaHead(session.project, session.model),
                color = colors.muted,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = MonoFontFamily,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            cachedSize?.let {
                Text(
                    it,
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                    fontSize = 10.sp,
                    maxLines = 1,
                    modifier = Modifier.testTag("pi_cached_size_${session.key.sessionId}_${session.key.instanceId}"),
                )
            }
            piContextLabel(session.contextPercent)?.let {
                Text(it, color = colors.muted, style = MaterialTheme.typography.labelSmall, maxLines = 1)
            }
            Text(
                formatAgo(nowMs, session.lastSeen),
                color = colors.subtle,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1,
            )
        }
    }
}
