package com.hpz.llmdockchat.feature.models

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ServiceSummary

/**
 * Screen 10b · Model detail (F11-R1). Screen 10d (the start-conflict dialog)
 * is not implemented — F11-R5 is dropped, see the feature file.
 */
@Composable
fun ModelDetailScreen(
    viewModel: ModelDetailViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val actionState by viewModel.actionState.collectAsState()
    LaunchedEffect(Unit) { viewModel.start() }

    // Same ownership split as ModelsScreen's two LaunchedEffects: this stream
    // lives only as long as this composable does, so leaving the screen
    // (back, or navigating past it) tears it down (F11-R7's third criterion
    // reasoning applies here too, even though R7 itself is not built).
    LaunchedEffect(Unit) {
        viewModel.observeServicesStream().collect { viewModel.applyLiveSummary(it) }
    }

    ModelDetailContent(
        state = state,
        actionState = actionState,
        onBack = onBack,
        onRetry = viewModel::retry,
        onRequestStart = viewModel::requestStart,
        onRequestStop = viewModel::requestStop,
        onDismissAction = viewModel::dismissAction,
        onConfirmAction = viewModel::confirmAction,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ModelDetailContent(
    state: ModelDetailUiState,
    actionState: ServiceActionState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onRequestStart: () -> Unit,
    onRequestStop: () -> Unit,
    onDismissAction: () -> Unit,
    onConfirmAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("model_detail_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        (state as? ModelDetailUiState.Loaded)?.summary?.name ?: "Model",
                        color = colors.fg,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("model_detail_back")) {
                        Text("←", color = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (state) {
                is ModelDetailUiState.Loading -> LoadingBox()
                is ModelDetailUiState.Failed -> FailedBox(state.message, onRetry)
                is ModelDetailUiState.Loaded -> DetailBody(state, actionState, onRequestStart, onRequestStop)
            }
        }
        ServiceActionDialog(actionState, onDismiss = onDismissAction, onConfirm = onConfirmAction)
    }
}

@Composable
private fun DetailBody(
    state: ModelDetailUiState.Loaded,
    actionState: ServiceActionState,
    onRequestStart: () -> Unit,
    onRequestStop: () -> Unit,
) {
    val colors = LlmTheme.colors
    val summary = state.summary
    val pending = actionState is ServiceActionState.InFlight && actionState.serviceName == summary.name

    LazyColumn(Modifier.fillMaxSize().testTag("model_detail_body")) {
        item {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(engineLabel(summary.engine), color = colors.subtle, style = MaterialTheme.typography.labelLarge)
                    Text("·", color = colors.subtle)
                    Text(
                        statusLabelFor(summary),
                        color = if (summary.isRunning) colors.green else colors.muted,
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.testTag("model_detail_status"),
                    )
                }
                Spacer(Modifier.height(12.dp))
                DetailRow("Host port", if (summary.port > 0) summary.port.toString() else "—")
                summary.modelSizeStr?.let { DetailRow("Model size", it) }
                if (summary.isExited) DetailRow("Exit code", summary.exitCode?.toString() ?: "—")

                state.config?.let { config ->
                    config.modelPath?.let { DetailRow("Model path", it) }
                    config.modelName?.let { DetailRow("Model", it) }
                    config.templateType?.let { DetailRow("Engine template", it) }
                }
                if (state.configMissing) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "No stored configuration for this container — it isn't in services.json.",
                        color = colors.muted,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.testTag("model_detail_config_missing"),
                    )
                }

                Spacer(Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (pending) {
                        CircularProgressIndicator(color = colors.accent, modifier = Modifier.testTag("model_detail_pending"))
                    } else if (summary.isRunning) {
                        TextButton(onClick = onRequestStop, modifier = Modifier.testTag("model_detail_stop")) {
                            Text("Stop", color = colors.red)
                        }
                    } else {
                        TextButton(onClick = onRequestStart, modifier = Modifier.testTag("model_detail_start")) {
                            Text("Start", color = colors.accent)
                        }
                    }
                }
            }
        }

        // F11-R2 (Should): the flags rendered as a readable list, strictly
        // read-only — no field here is ever editable and api_key never
        // appears (ServiceConfig's mapper never reads it off the wire).
        val flags = state.config?.flags.orEmpty()
        if (flags.isNotEmpty()) {
            item { SectionLabel("Flags") }
            items(flags, key = { it.first }) { (flag, value) -> FlagRow(flag, value) }
        }
    }
}

private fun statusLabelFor(summary: ServiceSummary): String = summary.statusLabel()

/**
 * Label fixed and single-line, value takes the rest of the row and wraps —
 * not the other way around. A first cut gave the label the `weight(1f)` and
 * left the value unconstrained; a long `model_path` (F11-R2) then measured at
 * its full intrinsic width, squeezed the label down to nothing, and "Model
 * path" wrapped one character per line — the same failure mode as the GPU
 * card's name column (see [ModelsScreen]'s `GpuCard` doc). Caught on-device
 * rather than in a JVM test, since Compose text layout isn't exercised there.
 */
@Composable
private fun DetailRow(label: String, value: String) {
    val colors = LlmTheme.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(
            label,
            color = colors.subtle,
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 1,
            modifier = Modifier.padding(end = 12.dp),
        )
        Text(
            value,
            color = colors.fg,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun SectionLabel(title: String) {
    val colors = LlmTheme.colors
    Text(
        title,
        color = colors.subtle,
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun FlagRow(flag: String, value: String) {
    val colors = LlmTheme.colors
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp)) {
        Text(flag, color = colors.fg, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
        if (value.isNotEmpty()) {
            Text(" $value", color = colors.muted, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
private fun LoadingBox() {
    Box(Modifier.fillMaxSize().testTag("model_detail_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun FailedBox(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxSize().padding(32.dp).testTag("model_detail_failed"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Couldn't load this model", color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = onRetry, modifier = Modifier.testTag("model_detail_retry")) {
            Text("Retry", color = colors.accent)
        }
    }
}
