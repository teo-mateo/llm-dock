package com.hpz.llmdockchat.feature.models

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
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
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val actionState by viewModel.actionState.collectAsState()
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
        onQueryChange = viewModel::onQueryChange,
        onRequestStart = viewModel::requestStart,
        onRequestStop = viewModel::requestStop,
        onDismissAction = viewModel::dismissAction,
        onConfirmAction = viewModel::confirmAction,
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
    onQueryChange: (String) -> Unit,
    onRequestStart: (String) -> Unit,
    onRequestStop: (String) -> Unit,
    onDismissAction: () -> Unit,
    onConfirmAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("models_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text("Models", color = colors.fg) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (state) {
                is ModelsUiState.Loading -> LoadingState()
                is ModelsUiState.Failed -> FailedState(state.message, onRetry)
                is ModelsUiState.Loaded -> ModelsList(
                    state = state,
                    onNewChatFromModel = onNewChatFromModel,
                    onOpenDetail = onOpenDetail,
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

@Composable
private fun ModelsList(
    state: ModelsUiState.Loaded,
    onNewChatFromModel: (String) -> Unit,
    onOpenDetail: (String) -> Unit,
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
                    service, now, zone, onNewChatFromModel, onOpenDetail,
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
        is ServiceActionState.Confirming -> androidx.compose.material3.AlertDialog(
            onDismissRequest = onDismiss,
            modifier = Modifier.testTag("service_action_confirm"),
            title = {
                Text(
                    if (actionState.action == ServiceAction.STOP) "Stop ${actionState.serviceName}?" else "Start ${actionState.serviceName}?",
                    color = colors.fg,
                )
            },
            text = {
                Text(
                    if (actionState.action == ServiceAction.STOP) {
                        "Any chat streaming on ${actionState.serviceName} right now will fail."
                    } else {
                        // Deliberately does not promise the reason. There is no
                        // VRAM guard (F11-R5 was dropped), so an oversubscribed
                        // start really does fail — but all this screen learns is
                        // the exit code. The actual "cudaMalloc failed: out of
                        // memory" only exists in the container's log, so saying
                        // "you'll see the error here" overclaimed.
                        "This starts the container. If the model doesn't fit in memory it will exit " +
                            "almost immediately — the status shows the exit code, the reason is in the logs."
                    },
                    color = colors.muted,
                )
            },
            confirmButton = {
                TextButton(onClick = onConfirm, modifier = Modifier.testTag("service_action_confirm_button")) {
                    Text(if (actionState.action == ServiceAction.STOP) "Stop" else "Start", color = colors.accent)
                }
            },
            dismissButton = {
                TextButton(onClick = onDismiss) { Text("Cancel", color = colors.muted) }
            },
        )
        is ServiceActionState.Failed -> androidx.compose.material3.AlertDialog(
            onDismissRequest = onDismiss,
            modifier = Modifier.testTag("service_action_failed"),
            title = { Text("Couldn't ${if (actionState.action == ServiceAction.STOP) "stop" else "start"} ${actionState.serviceName}", color = colors.red) },
            text = { Text(actionState.message, color = colors.muted) },
            confirmButton = { TextButton(onClick = onDismiss) { Text("OK", color = colors.accent) } },
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
            .padding(16.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(colors.surface)
            .padding(16.dp)
            .testTag("gpu_header"),
    ) {
        when (gpu) {
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
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            gpu.shortName,
            color = colors.subtle,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text(
            "${mibToGb(gpu.memoryUsedMiB)} / ${mibToGb(gpu.memoryTotalMiB)} GB",
            color = colors.fg,
            style = MaterialTheme.typography.titleMedium,
            maxLines = 1,
            softWrap = false,
        )
    }
    Spacer(Modifier.height(8.dp))
    Box(
        Modifier
            .fillMaxWidth()
            .height(6.dp)
            .clip(RoundedCornerShape(3.dp))
            .background(colors.sunken),
    ) {
        Box(
            Modifier
                .fillMaxWidth(usedFraction)
                .height(6.dp)
                .clip(RoundedCornerShape(3.dp))
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
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun ServiceRow(
    service: ServiceSummary,
    now: Instant,
    zone: ZoneId,
    onNewChatFromModel: ((String) -> Unit)?,
    onOpenDetail: (String) -> Unit,
    pending: Boolean,
    onRequestStart: (String) -> Unit,
    onRequestStop: (String) -> Unit,
) {
    val colors = LlmTheme.colors
    // F11: the row body opens detail; the trailing icon is F10-R5's row
    // start/stop, sharing the same confirm dialog as the detail screen.
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = { onOpenDetail(service.name) })
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag("service_row_${service.name}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .size(8.dp)
                .background(if (service.isRunning) colors.green else colors.subtle, CircleShape)
                .testTag("service_dot_${service.name}"),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    service.name,
                    color = colors.fg,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                EngineChip(service.engine)
            }
            Text(
                service.subtitle(now, zone),
                color = colors.muted,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        // F10-R6: offered only for a running, chat-capable service.
        if (onNewChatFromModel != null && service.isRunning && service.isChatCapable) {
            TextButton(
                onClick = { onNewChatFromModel(service.name) },
                modifier = Modifier.testTag("new_chat_from_model_${service.name}"),
            ) {
                Text("New chat", color = colors.accent, style = MaterialTheme.typography.labelMedium)
            }
        }
        if (pending) {
            CircularProgressIndicator(
                color = colors.accent,
                strokeWidth = 2.dp,
                modifier = Modifier.size(20.dp).testTag("service_row_pending_${service.name}"),
            )
        } else if (service.isRunning) {
            TextButton(
                onClick = { onRequestStop(service.name) },
                modifier = Modifier.testTag("service_row_stop_${service.name}"),
            ) { Text("Stop", color = colors.red, style = MaterialTheme.typography.labelMedium) }
        } else {
            TextButton(
                onClick = { onRequestStart(service.name) },
                modifier = Modifier.testTag("service_row_start_${service.name}"),
            ) { Text("Start", color = colors.accent, style = MaterialTheme.typography.labelMedium) }
        }
    }
}

@Composable
private fun EngineChip(engine: Engine) {
    val colors = LlmTheme.colors
    val chip = when (engine) {
        Engine.LLAMA_CPP -> colors.engineLlamaCpp
        Engine.VLLM -> colors.engineVllm
        Engine.DS4 -> colors.engineDs4
        Engine.OPEN_ROUTER -> colors.engineOpenRouter
        Engine.UNKNOWN -> colors.engineUnknown
    }
    Box(
        Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(chip.background)
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(
            engineLabel(engine),
            color = chip.foreground,
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
        )
    }
}

internal fun engineLabel(engine: Engine): String = when (engine) {
    Engine.LLAMA_CPP -> "llama.cpp"
    Engine.VLLM -> "vLLM"
    Engine.DS4 -> "ds4"
    Engine.OPEN_ROUTER -> "OpenRouter"
    Engine.UNKNOWN -> "?"
}

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize().testTag("models_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun SearchField(query: String, onQueryChange: (String) -> Unit) {
    val colors = LlmTheme.colors
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        singleLine = true,
        placeholder = { Text("Filter by name or port", color = colors.muted) },
        leadingIcon = { Text("  \uD83D\uDD0D", color = colors.muted) },
        trailingIcon = {
            if (query.isNotEmpty()) {
                TextButton(onClick = { onQueryChange("") }) { Text("Clear", color = colors.accent) }
            }
        },
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .testTag("models_search"),
    )
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
        Modifier.fillMaxSize().padding(32.dp).testTag("models_failed"),
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
