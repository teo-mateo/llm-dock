package com.hpz.llmdockchat.feature.logs

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.LogLevel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * F12: streaming container logs and follow-tail (screens 10c). F12-R5's
 * "share the buffer" was dropped as unwanted — see the feature file.
 *
 * A pane rather than a screen: it is the second tab of the model detail
 * screen, which owns the header and the back affordance.
 * Because the tab is only composed while it is selected, the log stream opens
 * when you switch to it and is torn down when you switch away — the same
 * composition-scoped ownership the two streams on the models list use.
 *
 * The stream is collected from this composition, not from the ViewModel's own
 * scope — see [LogsViewModel]'s class doc. [retryToken] is bumped to restart
 * the `LaunchedEffect` after a failure or a `stream_end`, the same "key
 * changes, effect restarts" idiom used everywhere else in this app for a
 * stream that should reconnect on demand rather than automatically.
 */
@Composable
fun LogsPane(
    viewModel: LogsViewModel,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    var retryToken by remember { mutableIntStateOf(0) }

    LaunchedEffect(retryToken) {
        try {
            viewModel.observeLogStream().collect { viewModel.onStreamEvent(it) }
            viewModel.onStreamCompleted()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            viewModel.onStreamFailed(e)
        }
    }

    Box(modifier.fillMaxSize().testTag("logs_screen")) {
        when (val current = state) {
            is LogsUiState.Loading -> LoadingBox()
            is LogsUiState.NotCreated -> MessageBox(
                testTag = "logs_not_created",
                title = "No container yet",
                message = current.message,
            )
            is LogsUiState.Failed -> MessageBox(
                testTag = "logs_failed",
                title = "Couldn't load logs",
                message = current.message,
                onRetry = { retryToken++ },
            )
            is LogsUiState.Loaded -> LoadedLogs(current)
        }
    }
}

@Composable
private fun LoadedLogs(state: LogsUiState.Loaded) {
    val colors = LlmTheme.colors
    // Kept here rather than in the ViewModel: they are how this pane is being
    // read right now, not anything about the container, and they should reset
    // when the pane goes away.
    var fontSize by rememberSaveable { mutableFloatStateOf(LOG_FONT_DEFAULT) }
    var wrap by rememberSaveable { mutableStateOf(true) }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()

    // Same "mode, not a measurement" following logic as ThreadScreen's F04-R3
    // (see its class doc) — a short buffer that never overflows the viewport
    // keeps `atBottom` true throughout, which is the correct behaviour here
    // too (nothing to disagree with when everything is already on screen).
    var following by remember { mutableStateOf(true) }
    val atBottom by remember { derivedStateOf { !listState.canScrollForward } }

    LaunchedEffect(atBottom) {
        if (atBottom) following = true
    }

    val stopFollowingOnDragBack = remember {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                if (available.y > 0f) following = false
                return Offset.Zero
            }
        }
    }

    LaunchedEffect(state.lines.size, following) {
        if (following && listState.layoutInfo.totalItemsCount > 0) {
            listState.scrollToItem(listState.layoutInfo.totalItemsCount - 1)
        }
    }

    // Off-wrap scrolls the whole column sideways rather than each line
    // separately, so the lines stay aligned with one another — per-row
    // horizontal scroll would let two rows sit at different offsets.
    val horizontal = rememberScrollState()

    Column(Modifier.fillMaxSize()) {
        LogToolbar(
            connection = state.connection,
            wrap = wrap,
            onToggleWrap = { wrap = !wrap },
            fontSize = fontSize,
            onFontSize = { fontSize = it.coerceIn(LOG_FONT_MIN, LOG_FONT_MAX) },
        )
        Box(Modifier.fillMaxSize().nestedScroll(stopFollowingOnDragBack)) {
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .fillMaxSize()
                    .then(if (wrap) Modifier else Modifier.horizontalScroll(horizontal))
                    .testTag("logs_body"),
                contentPadding = PaddingValues(vertical = 4.dp),
            ) {
                itemsIndexed(state.lines) { index, line ->
                    if (state.boundaryIndex == index && index != 0) {
                        SnapshotBoundary()
                    }
                    LogRow(line.text, colorFor(line.level, colors), fontSize, wrap)
                }
            }
            if (!following) {
                JumpToTail(
                    modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                    onClick = {
                        following = true
                        scope.launch { listState.animateScrollToItem(listState.layoutInfo.totalItemsCount - 1) }
                    },
                )
            }
        }
    }
}

/** Connection state on the left, the two reading controls on the right. */
@Composable
private fun LogToolbar(
    connection: LogsConnection,
    wrap: Boolean,
    onToggleWrap: () -> Unit,
    fontSize: Float,
    onFontSize: (Float) -> Unit,
) {
    val colors = LlmTheme.colors
    val (label, color) = when (connection) {
        LogsConnection.CONNECTING -> "Connecting…" to colors.subtle
        LogsConnection.LIVE -> "Live" to colors.green
        LogsConnection.ENDED -> "Stream ended — container stopped" to colors.muted
        LogsConnection.FALLBACK -> "Not live — showing last fetched tail" to colors.amber
    }
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            label,
            color = color,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            modifier = Modifier.weight(1f).testTag("logs_status"),
        )
        ToolbarChip(
            label = "wrap",
            active = wrap,
            onClick = onToggleWrap,
            testTag = "logs_wrap_toggle",
        )
        ToolbarChip(
            label = "A",
            fontSize = 10.sp,
            enabled = fontSize > LOG_FONT_MIN,
            onClick = { onFontSize(fontSize - LOG_FONT_STEP) },
            testTag = "logs_font_smaller",
        )
        ToolbarChip(
            label = "A",
            fontSize = 15.sp,
            enabled = fontSize < LOG_FONT_MAX,
            onClick = { onFontSize(fontSize + LOG_FONT_STEP) },
            testTag = "logs_font_larger",
        )
    }
}

@Composable
private fun ToolbarChip(
    label: String,
    onClick: () -> Unit,
    testTag: String,
    active: Boolean = false,
    enabled: Boolean = true,
    fontSize: androidx.compose.ui.unit.TextUnit = androidx.compose.ui.unit.TextUnit.Unspecified,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(width = 40.dp, height = 30.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(if (active) colors.accentSoft else colors.surfaceHigh)
            .clickable(enabled = enabled, onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = when {
                !enabled -> colors.subtle
                active -> colors.accent
                else -> colors.muted
            },
            fontSize = fontSize,
            style = if (fontSize == androidx.compose.ui.unit.TextUnit.Unspecified) {
                MaterialTheme.typography.labelSmall
            } else {
                MaterialTheme.typography.labelMedium
            },
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun SnapshotBoundary() {
    val colors = LlmTheme.colors
    Box(Modifier.fillMaxWidth().padding(vertical = 8.dp).testTag("logs_boundary")) {
        Text(
            "── live output ──",
            color = colors.subtle,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
}

@Composable
private fun LogRow(text: String, color: Color, fontSize: Float, wrap: Boolean) {
    Text(
        text,
        color = color,
        // Explicit and small rather than a body style: container output is
        // long unwrapped lines, and at bodySmall a single llama.cpp timing
        // line wrapped four times. Fitting more of a line matters more here
        // than matching the app's reading sizes — and A-/A+ move this, not the
        // chat text scale, which would be the wrong knob for a log.
        fontSize = fontSize.sp,
        lineHeight = (fontSize * 1.34f).sp,
        fontFamily = FontFamily.Monospace,
        softWrap = wrap,
        maxLines = if (wrap) Int.MAX_VALUE else 1,
        modifier = Modifier
            .then(if (wrap) Modifier.fillMaxWidth() else Modifier)
            .padding(horizontal = 12.dp),
    )
}

const val LOG_FONT_DEFAULT = 9f
private const val LOG_FONT_MIN = 6f
private const val LOG_FONT_MAX = 16f
private const val LOG_FONT_STEP = 1f

private fun colorFor(level: LogLevel, colors: LlmColors): Color = when (level) {
    LogLevel.ERROR -> colors.logError
    LogLevel.WARN -> colors.logWarn
    LogLevel.INFO -> colors.logInfo
    LogLevel.PLAIN -> colors.logPlain
}

@Composable
private fun JumpToTail(modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Box(
        modifier = modifier
            .background(colors.surfaceElevated, CircleShape)
            .testTag("logs_jump_to_tail"),
    ) {
        IconButton(onClick = onClick) { Text("↓", color = colors.fg) }
    }
}

@Composable
private fun LoadingBox() {
    Box(Modifier.fillMaxSize().testTag("logs_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun MessageBox(testTag: String, title: String, message: String, onRetry: (() -> Unit)? = null) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxSize().padding(32.dp).testTag(testTag),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(title, color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        if (onRetry != null) {
            Spacer(Modifier.height(16.dp))
            TextButton(onClick = onRetry, modifier = Modifier.testTag("logs_retry")) {
                Text("Retry", color = colors.accent)
            }
        }
    }
}

/** F12-R5: the whole visible buffer, in order; truncated with an explicit marker rather than failing silently. */
