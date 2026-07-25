package com.hpz.llmdockchat.feature.logs

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.LogLevel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Sharing a buffer this large (F12-R5's second criterion) truncates with an explicit marker instead. */
private const val MAX_SHARE_CHARS = 200_000
private const val TRUNCATION_MARKER = "[... earlier lines truncated ...]\n"

/**
 * F12: streaming container logs, follow-tail, and share (screens 10c).
 *
 * The stream is collected from this composition, not from the ViewModel's own
 * scope — see [LogsViewModel]'s class doc. [retryToken] is bumped to restart
 * the `LaunchedEffect` after a failure or a `stream_end`, the same "key
 * changes, effect restarts" idiom used everywhere else in this app for a
 * stream that should reconnect on demand rather than automatically.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogsScreen(
    viewModel: LogsViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
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

    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("logs_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text("Logs", color = colors.fg) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("logs_back")) {
                        Text("←", color = colors.fg)
                    }
                },
                actions = {
                    val loaded = state as? LogsUiState.Loaded
                    if (loaded != null && loaded.lines.isNotEmpty()) {
                        IconButton(
                            onClick = { shareLogs(context, loaded.lines) },
                            modifier = Modifier.testTag("logs_share"),
                        ) {
                            Text("⇪", color = colors.fg)
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
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
}

@Composable
private fun LoadedLogs(state: LogsUiState.Loaded) {
    val colors = LlmTheme.colors
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

    Column(Modifier.fillMaxSize()) {
        StatusBar(state.connection)
        Box(Modifier.fillMaxSize().nestedScroll(stopFollowingOnDragBack)) {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize().testTag("logs_body"),
                contentPadding = PaddingValues(vertical = 4.dp),
            ) {
                itemsIndexed(state.lines) { index, line ->
                    if (state.boundaryIndex == index && index != 0) {
                        SnapshotBoundary()
                    }
                    LogRow(line.text, colorFor(line.level, colors))
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

@Composable
private fun StatusBar(connection: LogsConnection) {
    val colors = LlmTheme.colors
    val (label, color) = when (connection) {
        LogsConnection.CONNECTING -> "Connecting…" to colors.subtle
        LogsConnection.LIVE -> "Live" to colors.green
        LogsConnection.ENDED -> "Stream ended — container stopped" to colors.muted
        LogsConnection.FALLBACK -> "Not live — showing last fetched tail" to colors.amber
    }
    Text(
        label,
        color = color,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp).testTag("logs_status"),
    )
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
private fun LogRow(text: String, color: Color) {
    Text(
        text,
        color = color,
        style = MaterialTheme.typography.bodySmall,
        fontFamily = FontFamily.Monospace,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 1.dp),
    )
}

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
private fun shareLogs(context: Context, lines: List<LogLine>) {
    val full = lines.joinToString("\n") { it.text }
    val text = if (full.length > MAX_SHARE_CHARS) {
        TRUNCATION_MARKER + full.takeLast(MAX_SHARE_CHARS)
    } else {
        full
    }
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    context.startActivity(Intent.createChooser(intent, "Share logs"))
}
