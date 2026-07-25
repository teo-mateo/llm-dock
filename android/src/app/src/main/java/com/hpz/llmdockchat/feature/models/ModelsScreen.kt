package com.hpz.llmdockchat.feature.models

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.ui.ConfirmDialog
import com.hpz.llmdockchat.core.ui.NoticeDialog
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.data.model.Engine
import com.hpz.llmdockchat.data.model.GpuState
import com.hpz.llmdockchat.data.model.GpuSummary
import com.hpz.llmdockchat.data.model.ServiceSummary
import java.time.Instant
import java.time.ZoneId

/**
 * Screen 10a · Models (F10). Read-and-observe only: F10-R5 (start/stop from a
 * row, tap-to-detail) is deferred to F11 — a row here does nothing when
 * tapped, and carries no power/play icon, unlike the mockup. The one action a
 * row *does* carry is F10-R6's "New chat from this model", which is in scope
 * and is not a control over the container.
 */
@Composable
fun ModelsScreen(
    viewModel: ModelsViewModel,
    onNewChatFromModel: (String) -> Unit,
    onOpenDetail: (String) -> Unit,
    onOpenLogs: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val actionState by viewModel.actionState.collectAsState()
    val refreshing by viewModel.refreshing.collectAsState()
    LaunchedEffect(Unit) { viewModel.start() }

    // F10-R3's third criterion: these two run only while this composable is
    // part of the composition. Navigation Compose disposes it — cancelling
    // both `LaunchedEffect`s and, with them, the underlying SSE connections —
    // the moment this destination stops being current, even though the
    // ViewModel itself survives a tab switch (see the class doc on
    // ModelsViewModel for why viewModelScope was the wrong owner for these).
    LaunchedEffect(Unit) {
        viewModel.observeServicesStream().collect { viewModel.applyServicesUpdate(it) }
    }
    LaunchedEffect(Unit) {
        viewModel.observeGpuStream().collect { viewModel.applyGpuUpdate(it) }
    }

    ModelsContent(
        state = state,
        actionState = actionState,
        onRetry = viewModel::retry,
        onNewChatFromModel = onNewChatFromModel,
        onOpenDetail = onOpenDetail,
        onOpenLogs = onOpenLogs,
        onQueryChange = viewModel::onQueryChange,
        onRequestStart = viewModel::requestStart,
        onRequestStop = viewModel::requestStop,
        onDismissAction = viewModel::dismissAction,
        onConfirmAction = viewModel::confirmAction,
        refreshing = refreshing,
        onRefresh = viewModel::refresh,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ModelsContent(
    state: ModelsUiState,
    actionState: ServiceActionState,
    onRetry: () -> Unit,
    onNewChatFromModel: (String) -> Unit,
    onOpenDetail: (String) -> Unit,
    onOpenLogs: (String) -> Unit = {},
    onQueryChange: (String) -> Unit,
    onRequestStart: (String) -> Unit,
    onRequestStop: (String) -> Unit,
    onDismissAction: () -> Unit,
    onConfirmAction: () -> Unit,
    refreshing: Boolean = false,
    onRefresh: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    val loaded = state as? ModelsUiState.Loaded
    val pullState = rememberPullToRefreshState()
    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
    Scaffold(
        modifier = modifier.testTag("models_screen"),
        // Transparent so the page gradient shows through — see the same note
        // on the conversation list.
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
        topBar = {
            ListHeader(
                running = loaded?.running?.size,
                stopped = loaded?.stopped?.size,
            )
        },
    ) { padding ->
        // Wraps every state, not just the loaded one: a failed initial load is
        // exactly when someone reaches for a pull. That only works because
        // FailedState scrolls — PullToRefreshBox drives off nested scroll, so
        // a child that cannot scroll never dispatches the gesture at all and
        // the pull silently does nothing.
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = onRefresh,
            modifier = Modifier.fillMaxSize().padding(padding).testTag("models_pull_refresh"),
            indicator = {
                PullToRefreshDefaults.Indicator(
                    state = pullState,
                    isRefreshing = refreshing,
                    containerColor = colors.surfaceElevated,
                    color = colors.accent,
                    modifier = Modifier.align(Alignment.TopCenter),
                )
            },
            state = pullState,
        ) {
            when (state) {
                is ModelsUiState.Loading -> LoadingState()
                is ModelsUiState.Failed -> FailedState(state.message, onRetry)
                is ModelsUiState.Loaded -> ModelsList(
                    state = state,
                    onNewChatFromModel = onNewChatFromModel,
                    onOpenDetail = onOpenDetail,
                    onOpenLogs = onOpenLogs,
                    onQueryChange = onQueryChange,
                    actionState = actionState,
                    onRequestStart = onRequestStart,
                    onRequestStop = onRequestStop,
                )
            }
        }
        ServiceActionDialog(actionState, onDismiss = onDismissAction, onConfirm = onConfirmAction)
    }
    }
}

/**
 * Same shell as the conversation list's header, for the same reasons: a
 * two-line block a `TopAppBar` cannot express at a sane height, and matching
 * geometry so the two tabs do not jump when you switch between them.
 */
@Composable
private fun ListHeader(running: Int?, stopped: Int?) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .height(76.dp)
            .padding(horizontal = 20.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Column {
            Text(
                "Models",
                color = colors.fg,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            if (running != null && stopped != null) {
                Text(
                    "$running running · $stopped stopped",
                    color = colors.subtle,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun ModelsList(
    state: ModelsUiState.Loaded,
    onNewChatFromModel: (String) -> Unit,
    onOpenDetail: (String) -> Unit,
    onOpenLogs: (String) -> Unit,
    onQueryChange: (String) -> Unit,
    actionState: ServiceActionState,
    onRequestStart: (String) -> Unit,
    onRequestStop: (String) -> Unit,
) {
    val now = remember { Instant.now() }
    val zone = remember { ZoneId.systemDefault() }

    LazyColumn(Modifier.fillMaxSize().testTag("models_list")) {
        item(key = "gpu_header") { GpuHeaderCard(state.gpu) }

        if (state.stale) {
            item(key = "stale_indicator") { StaleBanner() }
        }

        if (state.running.isEmpty() && state.stopped.isEmpty()) {
            item(key = "empty") { EmptyState() }
            return@LazyColumn
        }

        // Only worth the vertical space once the list is long enough to need
        // it — this rig has ~20 services, a fresh one may have two.
        if (state.running.size + state.stopped.size >= SEARCH_THRESHOLD) {
            item(key = "search") { SearchField(state.query, onQueryChange) }
        }

        if (state.noMatches) {
            item(key = "no_matches") { NoMatches(state.query) }
            return@LazyColumn
        }

        val running = state.visibleRunning
        val stopped = state.visibleStopped
        if (running.isNotEmpty()) {
            item(key = "running_header") { SectionHeader("Running", running.size) }
            items(running, key = { "running_${it.name}" }) { service ->
                ServiceRow(
                    service, now, zone, onNewChatFromModel, onOpenDetail, onOpenLogs,
                    pending = actionState.pendingFor(service.name),
                    onRequestStart = onRequestStart, onRequestStop = onRequestStop,
                )
            }
        }
        if (stopped.isNotEmpty()) {
            item(key = "stopped_header") { SectionHeader("Stopped", stopped.size) }
            items(stopped, key = { "stopped_${it.name}" }) { service ->
                ServiceRow(
                    service, now, zone, onNewChatFromModel = null, onOpenDetail = onOpenDetail,
                    onOpenLogs = onOpenLogs,
                    pending = actionState.pendingFor(service.name),
                    onRequestStart = onRequestStart, onRequestStop = onRequestStop,
                )
            }
        }
    }
}

/** Whether an action on [name] is mid-flight — the row's pending state
 * (F10-R5's third criterion). */
private fun ServiceActionState.pendingFor(name: String): Boolean =
    this is ServiceActionState.InFlight && serviceName == name

/**
 * The one confirm surface for both F11-R3 (stop) and F11-R4 (start), reused
 * verbatim from the row and from the detail screen (F10-R5's second
 * criterion). Naming the service and, for a stop, warning about in-flight
 * chats is the entire point of the dialog (F11-R3) — it never blocks the
 * action, only makes sure the person tapping it knows what it does.
 */
@Composable
fun ServiceActionDialog(
    actionState: ServiceActionState,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    val colors = LlmTheme.colors
    when (actionState) {
        is ServiceActionState.Confirming -> {
            val stopping = actionState.action == ServiceAction.STOP
            ConfirmDialog(
                icon = if (stopping) DesignLabIcons.Power else DesignLabIcons.Play,
                tint = if (stopping) colors.red else colors.green,
                title = if (stopping) "Stop ${actionState.serviceName}?" else "Start ${actionState.serviceName}?",
                message = if (stopping) {
                    "Any chat streaming on ${actionState.serviceName} right now will fail."
                } else {
                    // Deliberately does not promise the reason. There is no
                    // VRAM guard (F11-R5 was dropped), so an oversubscribed
                    // start really does fail — but all this screen learns is
                    // the exit code. The actual "cudaMalloc failed: out of
                    // memory" only exists in the container's log, so saying
                    // "you'll see the error here" overclaimed.
                    "If the model doesn't fit in memory the container exits almost immediately — " +
                        "the status shows the exit code, the reason is in the logs."
                },
                confirmLabel = if (stopping) "Stop" else "Start",
                onConfirm = onConfirm,
                onDismiss = onDismiss,
                testTag = "service_action_confirm",
            )
        }
        is ServiceActionState.Failed -> NoticeDialog(
            icon = DesignLabIcons.Power,
            tint = colors.red,
            title = "Couldn't ${if (actionState.action == ServiceAction.STOP) "stop" else "start"} ${actionState.serviceName}",
            message = actionState.message,
            onDismiss = onDismiss,
            testTag = "service_action_failed",
        )
        ServiceActionState.Idle, is ServiceActionState.InFlight -> Unit
    }
}

@Composable
private fun GpuHeaderCard(gpu: GpuState) {
    val colors = LlmTheme.colors
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(colors.surfaceElevated)
            .border(1.dp, colors.line, RoundedCornerShape(16.dp))
            .padding(16.dp)
            .testTag("gpu_header"),
    ) {
        when (gpu) {
            is GpuState.Connecting -> Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.testTag("gpu_connecting"),
            ) {
                CircularProgressIndicator(
                    color = colors.accent,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(15.dp),
                )
                Text("Reading GPU stats…", color = colors.muted, style = MaterialTheme.typography.bodyMedium)
            }
            is GpuState.Available -> gpu.gpus.forEachIndexed { index, card ->
                if (index > 0) Spacer(Modifier.height(12.dp))
                GpuCard(card)
            }
            is GpuState.Unavailable -> Column(Modifier.testTag("gpu_unavailable")) {
                Text("GPU stats unavailable", color = colors.muted, style = MaterialTheme.typography.bodyMedium)
                gpu.message?.let {
                    Spacer(Modifier.height(4.dp))
                    Text(it, color = colors.subtle, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

/**
 * F10-R4: one total VRAM bar, not per-container segments. The API has no
 * per-process breakdown, and the only per-service number is weights-on-disk
 * size — drawing segments from it would present an estimate as a measured
 * figure, which the requirement rules out outright. The used/total number
 * itself is the real one from `/api/gpu`.
 */
@Composable
private fun GpuCard(gpu: GpuSummary) {
    val colors = LlmTheme.colors
    val usedFraction = if (gpu.memoryTotalMiB > 0) (gpu.memoryUsedMiB.toFloat() / gpu.memoryTotalMiB).coerceIn(0f, 1f) else 0f

    // The VRAM figure is the point of this card, so it is laid out first and
    // never allowed to shrink or wrap: `softWrap = false` plus no weight. The
    // name takes what is left with `weight(1f)` — without a weight a `maxLines
    // = 1` Text still *measures* at full intrinsic width, so a long name (this
    // host reports "NVIDIA RTX PRO 6000 Blackwell Workstation Edition") pushed
    // the number off the edge and left it wrapping one character per line.
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            DesignLabIcons.Chip,
            contentDescription = null,
            tint = colors.accent,
            modifier = Modifier.size(17.dp),
        )
        Text(
            gpu.shortName,
            color = colors.muted,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text(
            "${mibToGb(gpu.memoryUsedMiB)} / ${mibToGb(gpu.memoryTotalMiB)} GB",
            color = colors.fg,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            softWrap = false,
        )
    }
    Spacer(Modifier.height(8.dp))
    Box(
        Modifier
            .fillMaxWidth()
            .height(8.dp)
            .clip(RoundedCornerShape(4.dp))
            .background(colors.sunken),
    ) {
        Box(
            Modifier
                .fillMaxWidth(usedFraction)
                .height(8.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(if (usedFraction > 0.9f) colors.red else colors.accent),
        )
    }
    Spacer(Modifier.height(8.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Stat("util", "${gpu.utilizationPercent}%")
        Stat("temp", "${gpu.temperatureC} °C")
        Stat("power", "${gpu.powerDrawW.toInt()} / ${gpu.powerLimitW.toInt()} W")
    }
}

@Composable
private fun Stat(label: String, value: String) {
    val colors = LlmTheme.colors
    Row {
        Text("$label ", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
        Text(value, color = colors.muted, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun StaleBanner() {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .background(colors.amber.copy(alpha = 0.15f))
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .testTag("stale_indicator"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Reconnecting… showing the last known state", color = colors.amber, style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun SectionHeader(title: String, count: Int) {
    val colors = LlmTheme.colors
    Text(
        "$title · $count",
        color = colors.subtle,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 4.dp),
    )
}

@Composable
private fun ServiceRow(
    service: ServiceSummary,
    now: Instant,
    zone: ZoneId,
    onNewChatFromModel: ((String) -> Unit)?,
    onOpenDetail: (String) -> Unit,
    onOpenLogs: (String) -> Unit,
    pending: Boolean,
    onRequestStart: (String) -> Unit,
    onRequestStop: (String) -> Unit,
) {
    val colors = LlmTheme.colors
    // F11: the row body opens detail; the trailing control is F10-R5's row
    // start/stop, sharing the same confirm dialog as the detail screen.
    //
    // Flat rows with a hairline divider rather than the design lab's one card
    // per row: this rig lists ~20 services, and a card plus a 10 dp gap each
    // turns that into three screens of scrolling. The conversation list made
    // the same trade for the same reason.
    Column(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = { onOpenDetail(service.name) })
            .testTag("service_row_${service.name}"),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 10.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // The pill is its own tap target, opening the logs tab: the logs
            // are what is wanted from a container that just exited, and they
            // were two taps deep behind the configuration.
            EngineChip(
                service.engine,
                isRunning = service.isRunning,
                modifier = Modifier
                    .clickable { onOpenLogs(service.name) }
                    .testTag("service_dot_${service.name}"),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(
                    service.name,
                    color = colors.fg,
                    style = MaterialTheme.typography.bodyMedium,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    service.subtitle(now, zone),
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            // F10-R6: offered only for a running, chat-capable service.
            if (onNewChatFromModel != null && service.isRunning && service.isChatCapable) {
                RoundAction(
                    icon = DesignLabIcons.ChatBubble,
                    description = "New chat with ${service.name}",
                    tint = colors.accent,
                    background = colors.accentSoft,
                    testTag = "new_chat_from_model_${service.name}",
                    onClick = { onNewChatFromModel(service.name) },
                )
            }
            if (pending) {
                Box(Modifier.size(36.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(
                        color = colors.accent,
                        strokeWidth = 2.dp,
                        modifier = Modifier.size(18.dp).testTag("service_row_pending_${service.name}"),
                    )
                }
            } else if (service.isRunning) {
                RoundAction(
                    icon = DesignLabIcons.Power,
                    description = "Stop ${service.name}",
                    tint = colors.red,
                    background = colors.red.copy(alpha = 0.12f),
                    testTag = "service_row_stop_${service.name}",
                    onClick = { onRequestStop(service.name) },
                )
            } else {
                RoundAction(
                    icon = DesignLabIcons.Play,
                    description = "Start ${service.name}",
                    tint = colors.green,
                    background = colors.green.copy(alpha = 0.12f),
                    testTag = "service_row_start_${service.name}",
                    onClick = { onRequestStart(service.name) },
                )
            }
        }
        Box(
            Modifier
                .padding(start = 20.dp)
                .fillMaxWidth()
                .height(1.dp)
                .background(colors.line),
        )
    }
}

/**
 * Start, stop and new-chat as icons rather than the words they used to be.
 * Three text buttons on a row this narrow left the model name — the thing
 * being read — a few characters wide; `contentDescription` keeps them
 * announced.
 */
@Composable
private fun RoundAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    description: String,
    tint: androidx.compose.ui.graphics.Color,
    background: androidx.compose.ui.graphics.Color,
    testTag: String,
    onClick: () -> Unit,
) {
    Box(
        Modifier
            .size(36.dp)
            .clip(androidx.compose.foundation.shape.CircleShape)
            .background(background)
            .clickable(onClick = onClick)
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = description, tint = tint, modifier = Modifier.size(16.dp))
    }
}

/**
 * The engine pill, square rather than a rounded chip so it reads as a fixed
 * "type" tag rather than a status badge — the actual running/stopped status
 * is the vertical bar on its leading edge, not the pill's shape or color.
 * Green when running, gray otherwise; the bar and the pill sit flush against
 * each other (no gap, no rounding on the seam) so they read as one control.
 */
@Composable
private fun EngineChip(engine: Engine, isRunning: Boolean, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    val chip = when (engine) {
        Engine.LLAMA_CPP -> colors.engineLlamaCpp
        Engine.VLLM -> colors.engineVllm
        Engine.DS4 -> colors.engineDs4
        Engine.OPEN_ROUTER -> colors.engineOpenRouter
        Engine.UNKNOWN -> colors.engineUnknown
    }
    Row(modifier.height(IntrinsicSize.Min)) {
        Box(
            Modifier
                .width(3.dp)
                .fillMaxHeight()
                .background(if (isRunning) colors.green else colors.subtle),
        )
        val lines = engineLabelLines(engine)
        Column(
            Modifier
                .clip(RoundedCornerShape(topEnd = 4.dp, bottomEnd = 4.dp))
                .background(chip.background)
                .width(CHIP_WIDTH)
                .padding(vertical = 3.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            lines.forEach { line ->
                Text(
                    line,
                    color = chip.foreground,
                    fontSize = chipFontSize(lines),
                    lineHeight = 9.sp,
                    fontFamily = FontFamily.Monospace,
                    textAlign = TextAlign.Center,
                    maxLines = 1,
                    softWrap = false,
                )
            }
        }
    }
}

/**
 * Short on purpose. This label sits inline before the model name on every
 * row, so each character it costs is a character the name loses — and the
 * name is what the owner is actually reading. "llama.cpp" is unmistakable
 * as "llama"; the picker (which has a whole row to itself) still spells
 * them out in full.
 */
internal fun engineLabel(engine: Engine): String = when (engine) {
    Engine.LLAMA_CPP -> "llama.cpp"
    Engine.VLLM -> "vLLM"
    Engine.DS4 -> "ds4"
    Engine.OPEN_ROUTER -> "open router"
    Engine.UNKNOWN -> "?"
}

/**
 * Split for a fixed-width chip: break on a dot or a space, never mid-word,
 * so "llama.cpp" stacks as llama/cpp and "vLLM" stays on one line.
 */
internal fun engineLabelLines(engine: Engine): List<String> =
    engineLabel(engine).split('.', ' ').filter { it.isNotEmpty() }

/**
 * Every chip is [CHIP_WIDTH] wide regardless of engine, so the model names
 * beside them all start at the same x — a ragged left edge on a list this
 * long is harder to scan than a slightly small label. The type shrinks to
 * fit instead of the box growing: sizes are picked off the longest line
 * rather than measured, which is deterministic and needs no layout pass.
 */
private fun chipFontSize(lines: List<String>): TextUnit = when (lines.maxOf { it.length }) {
    in 0..3 -> 9.sp
    4 -> 8.sp
    5 -> 7.sp
    else -> 6.sp
}

private val CHIP_WIDTH = 30.dp

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize().testTag("models_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

/**
 * Not in the design lab's mockup — the filter was asked for afterwards — so it
 * borrows the composer's shape rather than inventing a third input style, and
 * drops the stock `OutlinedTextField`, whose floating label and magnifying-glass
 * emoji were the two loudest things on the screen.
 */
@Composable
private fun SearchField(query: String, onQueryChange: (String) -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(22.dp))
            .background(colors.sunken)
            .border(1.dp, colors.line, RoundedCornerShape(22.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp)
            .testTag("models_search"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(DesignLabIcons.Search, contentDescription = null, tint = colors.subtle, modifier = Modifier.size(16.dp))
        Box(Modifier.weight(1f)) {
            if (query.isEmpty()) {
                Text("Filter by name or port", color = colors.subtle, style = MaterialTheme.typography.bodyMedium)
            }
            BasicTextField(
                value = query,
                onValueChange = onQueryChange,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyMedium.copy(color = colors.fg),
                cursorBrush = SolidColor(colors.accent),
                modifier = Modifier.fillMaxWidth().testTag("models_search_input"),
            )
        }
        if (query.isNotEmpty()) {
            Icon(
                DesignLabIcons.Close,
                contentDescription = "Clear filter",
                tint = colors.muted,
                modifier = Modifier.size(15.dp).clickable { onQueryChange("") },
            )
        }
    }
}

@Composable
private fun NoMatches(query: String) {
    val colors = LlmTheme.colors
    Text(
        "No service matches \"$query\".",
        color = colors.muted,
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 24.dp).testTag("models_no_matches"),
    )
}

/** Below this many services the filter costs more screen than it saves. */
private const val SEARCH_THRESHOLD = 8

@Composable
private fun EmptyState() {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxWidth().padding(32.dp).testTag("models_empty"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("No services configured", color = colors.fg, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun FailedState(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        // verticalScroll with nothing to scroll: it is here so the column
        // dispatches nested scroll and pull-to-refresh works on this screen.
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(32.dp)
            .testTag("models_failed"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Couldn't load models", color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = onRetry, modifier = Modifier.testTag("models_retry")) {
            Text("Retry", color = colors.accent)
        }
    }
}

@Preview
@Composable
private fun ModelsPopulatedPreview() {
    LLMDockChatTheme(darkTheme = true) {
        ModelsContent(
            state = ModelsUiState.Loaded(
                running = listOf(
                    ServiceSummary("llamacpp-qwen3.6-27b-mtp-q8", "running", "chat", port = 3301, modelSizeStr = "26.1 GB", createdAt = Instant.now().minusSeconds(15120).toString()),
                    ServiceSummary("vllm-qwen3.6-35b-a3b-fp8", "running", "chat", port = 3310, modelSizeStr = "35.3 GB", createdAt = Instant.now().minusSeconds(3060).toString()),
                ),
                stopped = listOf(
                    ServiceSummary("ds4-deepseek-v4-flash", "not-created", "chat", port = 3315, modelSizeStr = "80.76 GB"),
                    ServiceSummary("llamacpp-gemma-4-31b-it-q8", "exited", "chat", port = 3303, modelSizeStr = "33.73 GB", exitCode = 1),
                ),
                gpu = GpuState.Available(
                    listOf(GpuSummary(0, "RTX PRO 6000 Blackwell", memoryUsedMiB = 62873, memoryTotalMiB = 97887, utilizationPercent = 84, temperatureC = 71, powerDrawW = 318.0, powerLimitW = 300.0)),
                ),
            ),
            actionState = ServiceActionState.Idle,
            onRetry = {},
            onNewChatFromModel = {},
            onOpenDetail = {},
            onQueryChange = {},
            onRequestStart = {},
            onRequestStop = {},
            onDismissAction = {},
            onConfirmAction = {},
        )
    }
}

@Preview
@Composable
private fun ModelsGpuUnavailablePreview() {
    LLMDockChatTheme(darkTheme = false) {
        ModelsContent(
            state = ModelsUiState.Loaded(
                running = emptyList(),
                stopped = listOf(ServiceSummary("llamacpp-a", "not-created", "chat", port = 3301)),
                gpu = GpuState.Unavailable("nvidia-smi command failed"),
            ),
            actionState = ServiceActionState.Idle,
            onRetry = {},
            onNewChatFromModel = {},
            onOpenDetail = {},
            onQueryChange = {},
            onRequestStart = {},
            onRequestStop = {},
            onDismissAction = {},
            onConfirmAction = {},
        )
    }
}
