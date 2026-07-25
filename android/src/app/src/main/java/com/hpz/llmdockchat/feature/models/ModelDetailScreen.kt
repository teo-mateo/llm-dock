package com.hpz.llmdockchat.feature.models

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.logs.LogsPane
import com.hpz.llmdockchat.feature.logs.LogsUiState
import com.hpz.llmdockchat.feature.logs.LogsViewModel
import com.hpz.llmdockchat.feature.logs.shareLogsFrom
import com.hpz.llmdockchat.data.model.ServiceSummary

/**
 * Screen 10b · Model detail (F11-R1) and F12's logs, as two tabs of one
 * screen rather than two screens stacked on each other.
 *
 * Logs used to be a route pushed on top of this one, reached through a "Live
 * output" row buried under the flags. They are the thing most often wanted
 * from a container that just exited, and burying them two taps deep behind
 * the configuration had it backwards. The engine pill on the models list now
 * opens this screen straight onto [ModelTab.LOGS].
 */
@Composable
fun ModelDetailScreen(
    viewModel: ModelDetailViewModel,
    logsViewModel: LogsViewModel,
    onBack: () -> Unit,
    initialTab: ModelTab = ModelTab.CONFIG,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val actionState by viewModel.actionState.collectAsState()
    val logsState by logsViewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.start() }

    // Same ownership split as ModelsScreen's two LaunchedEffects: this stream
    // lives only as long as this composable does, so leaving the screen
    // (back, or navigating past it) tears it down (F11-R7's third criterion
    // reasoning applies here too, even though R7 itself is not built).
    LaunchedEffect(Unit) {
        viewModel.observeServicesStream().collect { viewModel.applyLiveSummary(it) }
    }

    var tab by rememberSaveable { mutableStateOf(initialTab) }
    val context = LocalContext.current

    ModelDetailContent(
        state = state,
        actionState = actionState,
        tab = tab,
        onTabChange = { tab = it },
        logsPane = { LogsPane(logsViewModel) },
        canShareLogs = (logsState as? LogsUiState.Loaded)?.lines?.isNotEmpty() == true,
        onShareLogs = { shareLogsFrom(context, logsState) },
        onBack = onBack,
        onRetry = viewModel::retry,
        onRequestStart = viewModel::requestStart,
        onRequestStop = viewModel::requestStop,
        onDismissAction = viewModel::dismissAction,
        onConfirmAction = viewModel::confirmAction,
        modifier = modifier,
    )
}

enum class ModelTab(val label: String) {
    CONFIG("Configuration"),
    LOGS("Logs"),
}

@Composable
private fun ModelDetailContent(
    state: ModelDetailUiState,
    actionState: ServiceActionState,
    tab: ModelTab,
    onTabChange: (ModelTab) -> Unit,
    logsPane: @Composable () -> Unit,
    canShareLogs: Boolean,
    onShareLogs: () -> Unit,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onRequestStart: () -> Unit,
    onRequestStop: () -> Unit,
    onDismissAction: () -> Unit,
    onConfirmAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    val summary = (state as? ModelDetailUiState.Loaded)?.summary
    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
    Scaffold(
        modifier = modifier.testTag("model_detail_screen"),
        containerColor = Color.Transparent,
        topBar = {
            Column {
                DetailHeader(
                    name = summary?.name ?: "Model",
                    // Engine only: the status has its own pill on the tab
                    // below, and saying it twice on one screen is noise.
                    subtitle = summary?.let { engineLabel(it.engine) },
                    onBack = onBack,
                    action = {
                        // Only on the logs tab, and only with something to
                        // send — an always-present share button on the
                        // configuration tab would have nothing to share.
                        if (tab == ModelTab.LOGS && canShareLogs) {
                            IconButton(onClick = onShareLogs, modifier = Modifier.testTag("logs_share")) {
                                Icon(DesignLabIcons.Send, contentDescription = "Share logs", tint = colors.fg, modifier = Modifier.size(19.dp))
                            }
                        }
                    },
                )
                ModelTabRow(tab, onTabChange)
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (tab) {
                ModelTab.CONFIG -> when (state) {
                    is ModelDetailUiState.Loading -> LoadingBox()
                    is ModelDetailUiState.Failed -> FailedBox(state.message, onRetry)
                    is ModelDetailUiState.Loaded -> DetailBody(state, actionState, onRequestStart, onRequestStop)
                }
                // Composed only while selected, which is what scopes the log
                // stream to the tab being open — see LogsPane's doc.
                ModelTab.LOGS -> logsPane()
            }
        }
        ServiceActionDialog(actionState, onDismiss = onDismissAction, onConfirm = onConfirmAction)
    }
    }
}

/** The same header shell as the thread and the two lists, for the same reasons. */
@Composable
private fun DetailHeader(
    name: String,
    subtitle: String?,
    onBack: () -> Unit,
    action: @Composable () -> Unit,
) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .height(64.dp)
            .padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack, modifier = Modifier.testTag("model_detail_back")) {
            Icon(DesignLabIcons.ChevronLeft, contentDescription = "Back", tint = colors.fg, modifier = Modifier.size(22.dp))
        }
        Column(Modifier.weight(1f).padding(horizontal = 4.dp)) {
            Text(
                name,
                color = colors.fg,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (subtitle != null) {
                Text(
                    subtitle,
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        action()
    }
}

@Composable
private fun ModelTabRow(selected: ModelTab, onSelect: (ModelTab) -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(colors.sunken)
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        ModelTab.entries.forEach { entry ->
            val active = entry == selected
            Box(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (active) colors.surface else Color.Transparent)
                    .clickable { onSelect(entry) }
                    .padding(vertical = 8.dp)
                    .testTag("model_tab_${entry.name.lowercase()}"),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    entry.label,
                    color = if (active) colors.fg else colors.subtle,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium,
                )
            }
        }
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
            Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
                // Status and its one control on the same row. The status used
                // to repeat the header's subtitle verbatim with the button
                // stranded below the field list, which read as an unrelated
                // afterthought.
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    StatusPill(summary)
                    Spacer(Modifier.weight(1f))
                    if (pending) {
                        CircularProgressIndicator(
                            color = colors.accent,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(20.dp).testTag("model_detail_pending"),
                        )
                    } else if (summary.isRunning) {
                        PowerButton(
                            label = "Stop",
                            icon = DesignLabIcons.Power,
                            tint = colors.red,
                            onClick = onRequestStop,
                            testTag = "model_detail_stop",
                        )
                    } else {
                        PowerButton(
                            label = "Start",
                            icon = DesignLabIcons.Play,
                            tint = colors.green,
                            onClick = onRequestStart,
                            testTag = "model_detail_start",
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                DetailRow("Host port", if (summary.port > 0) summary.port.toString() else "—")
                summary.modelSizeStr?.let { DetailRow("Model size", it) }
                if (summary.isExited) DetailRow("Exit code", summary.exitCode?.toString() ?: "—")
                state.config?.let { config ->
                    config.templateType?.let { DetailRow("Engine template", it) }
                    // model_path is deliberately not shown. It is a 200-character
                    // HF cache path that wrapped over six lines and dominated the
                    // tab, and it says nothing the service name does not — the
                    // flags below are the part worth reading.
                    config.modelName?.let { DetailRow("Model", it, last = true) }
                }
                if (state.configMissing) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "No stored configuration for this container — it isn't in services.json.",
                        color = colors.muted,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.testTag("model_detail_config_missing"),
                    )
                }
            }
        }

        // F11-R2 (Should): the flags rendered as a readable list, strictly
        // read-only — no field here is ever editable and api_key never
        // appears (ServiceConfig's mapper never reads it off the wire).
        val flags = state.config?.flags.orEmpty()
        if (flags.isNotEmpty()) {
            item { SectionLabel("Flags · ${flags.size}") }
            items(flags, key = { it.first }) { (flag, value) -> FlagRow(flag, value) }
            item { Spacer(Modifier.height(20.dp)) }
        }
    }
}

/**
 * Label fixed and single-line, value takes the rest of the row and wraps —
 * not the other way around. A first cut gave the label the `weight(1f)` and
 * left the value unconstrained; a long `model_path` (F11-R2) then measured at
 * its full intrinsic width, squeezed the label down to nothing, and "Model
 * path" wrapped one character per line — the same failure mode as the GPU
 * card's name column (see [ModelsScreen]'s `GpuCard` doc). Caught on-device
 * rather than in a JVM test, since Compose text layout isn't exercised there.
 */
/** The container's state as a tinted pill — green running, red on a non-zero exit. */
@Composable
private fun StatusPill(summary: ServiceSummary) {
    val colors = LlmTheme.colors
    val tint = when {
        summary.isRunning -> colors.green
        summary.isExited && (summary.exitCode ?: 0) != 0 -> colors.red
        else -> colors.subtle
    }
    Row(
        Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(tint.copy(alpha = 0.12f))
            .padding(horizontal = 10.dp, vertical = 5.dp)
            .testTag("model_detail_status"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(tint))
        Text(summary.statusLabel(), color = tint, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
    }
}

/** Icon and word together — an unlabelled circle here would be guessing, and unlike the
 * list row this screen has the width to say which it is. */
@Composable
private fun PowerButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    tint: Color,
    onClick: () -> Unit,
    testTag: String,
) {
    Row(
        Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(tint.copy(alpha = 0.12f))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp)
            .testTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(15.dp))
        Text(label, color = tint, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
    }
}

/**
 * Label in a fixed column so every value starts at the same x, with a hairline
 * under each. Cards around these groups were tried and dropped — the boxes were
 * louder than the fields inside them.
 */
@Composable
private fun DetailRow(label: String, value: String, mono: Boolean = false, last: Boolean = false) {
    val colors = LlmTheme.colors
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(vertical = 9.dp)) {
            Text(
                label,
                color = colors.subtle,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                modifier = Modifier.width(LABEL_COLUMN),
            )
            Text(
                value,
                color = colors.fg,
                style = MaterialTheme.typography.labelMedium,
                fontFamily = if (mono) FontFamily.Monospace else null,
                modifier = Modifier.weight(1f),
            )
        }
        if (!last) Box(Modifier.fillMaxWidth().height(1.dp).background(colors.line))
    }
}

private val LABEL_COLUMN = 116.dp

@Composable
private fun SectionLabel(title: String) {
    val colors = LlmTheme.colors
    Text(
        title,
        color = colors.subtle,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 2.dp),
    )
}

@Composable
private fun FlagRow(flag: String, value: String) {
    val colors = LlmTheme.colors
    Row(
        Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 2.dp, bottom = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            flag,
            color = colors.accent,
            fontSize = 11.sp,
            lineHeight = 15.sp,
            fontFamily = FontFamily.Monospace,
        )
        if (value.isNotEmpty()) {
            Text(
                value,
                color = colors.muted,
                fontSize = 11.sp,
                lineHeight = 15.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.weight(1f),
            )
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
