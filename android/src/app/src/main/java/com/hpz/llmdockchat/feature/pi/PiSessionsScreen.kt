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
import androidx.compose.ui.platform.*
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.*
import androidx.compose.ui.unit.*
import com.hpz.llmdockchat.core.ui.theme.*
import com.hpz.llmdockchat.data.model.*
@Composable
fun PiSessionsScreen(state: PiSessionsUiState, onOpen: (PiSessionKey) -> Unit) {
    val colors = LlmTheme.colors
    val loaded = state as? PiSessionsUiState.Loaded
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
            when (state) {
                is PiSessionsUiState.Loading -> Box(
                    Modifier.fillMaxWidth().weight(1f),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator(color = colors.accent) }
                is PiSessionsUiState.Loaded -> {
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
                    if (state.live.isEmpty() && state.ended.isEmpty()) {
                        Box(
                            Modifier.fillMaxWidth().weight(1f),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                "No pi sessions yet. Start pi with the pi-remote extension.",
                                color = colors.muted,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxWidth().weight(1f),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            contentPadding = PaddingValues(top = 10.dp, bottom = 16.dp),
                        ) {
                            if (state.live.isNotEmpty()) {
                                item(key = "live_header") {
                                    Text("Live", color = colors.muted, style = MaterialTheme.typography.labelMedium)
                                }
                                items(state.live, key = { "${it.key.sessionId}/${it.key.instanceId}" }) {
                                    PiSessionRow(it, onOpen)
                                }
                            }
                            if (state.ended.isNotEmpty()) {
                                item(key = "ended_header") {
                                    Text("Ended", color = colors.muted, style = MaterialTheme.typography.labelMedium)
                                }
                                items(state.ended, key = { "${it.key.sessionId}/${it.key.instanceId}" }) {
                                    PiSessionRow(it, onOpen)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
@Composable
fun PiSessionRow(session: PiSession, onOpen: (PiSessionKey) -> Unit) {
    val colors = LlmTheme.colors
    val status = when (session.state) {
        PiState.WORKING -> "working"
        PiState.IDLE -> "idle"
        PiState.ENDED -> "ended"
    }
    val statusColor = when (session.state) {
        PiState.WORKING -> colors.amber
        PiState.IDLE -> colors.green
        PiState.ENDED -> colors.subtle
    }
    val fallback = session.cwd.trimEnd('/').split('/').lastOrNull()?.takeIf { it.isNotBlank() }
        ?: session.cwd
    val name = session.name?.takeIf { it.isNotBlank() } ?: fallback
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
                piSessionMetaHead(session.cwd, session.model),
                color = colors.muted,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = MonoFontFamily,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
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