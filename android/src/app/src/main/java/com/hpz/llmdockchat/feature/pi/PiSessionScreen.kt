package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiState
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import kotlin.math.roundToInt

@Composable
fun PiSessionScreen(
    state: PiSessionUiState,
    composerState: PiComposerState,
    onBack: () -> Unit,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    val colors = LlmTheme.colors
    val loaded = state as? PiSessionUiState.Loaded
    var showTextSize by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
        Scaffold(
            modifier = Modifier.testTag("pi_session_screen"),
            containerColor = Color.Transparent,
            topBar = {
                Column {
                    PiSessionHeader(loaded?.summary, onBack, onTextSize = { showTextSize = true })
                    if (loaded?.stale == true) {
                        Text(
                            "Reconnecting…",
                            color = colors.amber,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp),
                        )
                    }
                }
            },
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                when (state) {
                    is PiSessionUiState.Loading -> Box(
                        Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator(color = colors.accent) }
                    is PiSessionUiState.Unknown -> Box(
                        Modifier.fillMaxSize().padding(horizontal = 24.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            "This session is no longer known to the dashboard.",
                            color = colors.muted,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                    is PiSessionUiState.Loaded -> PiSessionLoaded(state, composerState, onDraftChange, onSend, onStop)
                }
            }
        }
    }
    if (showTextSize) {
        PiTextSizeSheet(onDismiss = { showTextSize = false })
    }
}

@Composable
private fun PiSessionHeader(summary: PiSession?, onBack: () -> Unit, onTextSize: () -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).height(64.dp).padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack, modifier = Modifier.testTag("pi_session_back")) {
            Icon(DesignLabIcons.Back, contentDescription = "Back", tint = colors.fg)
        }
        Column(Modifier.weight(1f).padding(horizontal = 4.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    sessionName(summary),
                    color = colors.fg,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f).testTag("pi_session_title"),
                )
                if (summary != null) {
                    val status = statusLabel(summary.state)
                    Text(
                        status,
                        color = statusColor(summary.state),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.background(statusColor(summary.state).copy(alpha = 0.14f), RoundedCornerShape(8.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                }
            }
            val details = listOfNotNull(
                summary?.model,
                summary?.thinkingLevel,
                summary?.contextPercent?.let { "ctx ${it.roundToInt()}%" },
            )
            if (details.isNotEmpty()) {
                Text(
                    details.joinToString(" · "),
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        IconButton(
            onClick = onTextSize,
            modifier = Modifier
                .size(width = 48.dp, height = 48.dp)
                .semantics { contentDescription = "Answer text size" }
                .testTag("pi_text_size_button"),
        ) {
            Text(
                "Aa",
                color = colors.muted,
                fontFamily = FontFamily.Monospace,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun PiSessionLoaded(
    state: PiSessionUiState.Loaded,
    composerState: PiComposerState,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    val summary = state.summary
    Column(Modifier.fillMaxSize()) {
        PiSessionTranscript(
            state,
            composerState.lastStopAt,
            Modifier.weight(1f),
        )
        if (summary != null) {
            PiComposer(
                live = summary.live,
                working = state.transcript.working,
                draft = composerState.draft,
                sending = composerState.sending,
                stopping = composerState.stopping,
                notice = composerState.notice,
                onDraftChange = onDraftChange,
                onSend = onSend,
                onStop = onStop,
            )
        }
    }
}

private fun sessionName(summary: PiSession?): String {
    val name = summary?.name?.takeIf { it.isNotBlank() }
    if (name != null) return name
    val cwd = summary?.cwd ?: return "pi session"
    return cwd.trimEnd('/').split('/').lastOrNull()?.takeIf { it.isNotBlank() } ?: cwd
}

private fun statusLabel(state: PiState): String = when (state) {
    PiState.WORKING -> "working"
    PiState.IDLE -> "idle"
    PiState.ENDED -> "ended"
}

@Composable
private fun statusColor(state: PiState): Color {
    val colors = LlmTheme.colors
    return when (state) {
        PiState.WORKING -> colors.amber
        PiState.IDLE -> colors.green
        PiState.ENDED -> colors.subtle
    }
}
