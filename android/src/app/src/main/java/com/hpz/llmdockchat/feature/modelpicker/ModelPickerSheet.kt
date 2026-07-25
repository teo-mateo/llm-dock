package com.hpz.llmdockchat.feature.modelpicker

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.Engine
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.data.model.engine

/**
 * The model picker (F07), shared by [com.hpz.llmdockchat.feature.newchat.NewChatScreen]
 * (choosing a model for a brand-new thread) and
 * [com.hpz.llmdockchat.feature.thread.ThreadScreen] (switching mid-thread,
 * F07-R4) — screen 07a. Grown out of F03's own flat, minimal build once F07
 * existed to own it (see F03's *Deviations*), without touching
 * [ModelOption], the repositories the two screens read from, or
 * `ConversationsRepository.create`'s signature: this composable only takes
 * richer input than F03's did.
 *
 * [services] is unfiltered — every row `GET /api/services` returned, not just
 * chat-capable ones — so an embedding service or `open-webui` never reaches
 * this composable only by the caller doing it right; this filters for itself
 * too, so a picker instantiated against the raw list can never show one
 * (F07-R1's second criterion, belt-and-suspenders with [ServiceSummary.isChatCapable]).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelPickerSheet(
    services: List<ServiceSummary>,
    remoteModels: List<ModelOption.Remote>,
    remoteModelsConfigured: Boolean,
    onSelect: (ModelOption) -> Unit,
    onDismiss: () -> Unit,
    selectedRef: ModelRef? = null,
) {
    val colors = LlmTheme.colors
    val chatCapable = services.filter { it.isChatCapable }
    // Favourites first; sortedByDescending is stable, so the server's own
    // host-port ordering holds within each group otherwise (F07-R5).
    val running = chatCapable.filter { it.isRunning }.sortedByDescending { it.favorite }
    val stopped = chatCapable.filter { !it.isRunning }.sortedByDescending { it.favorite }

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("model_picker_sheet"),
    ) {
        // C3 (F03): the sheet draws behind the navigation bar, so without this
        // its last row is unreachable under the 44 dp button bar.
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            item { ModelPickerSectionHeader("Running") }
            if (running.isEmpty()) {
                item {
                    Text(
                        "Nothing is running. Start a model from the Models tab.",
                        color = colors.amber,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                            .testTag("model_picker_nothing_running"),
                    )
                }
            }
            items(running, key = { "running:${it.name}" }) { service ->
                LocalServiceRow(
                    service = service,
                    selected = selectedRef == ModelRef.Local(service.name),
                    onClick = { onSelect(ModelOption.LocalService(service.name, service.status)) },
                )
            }

            if (stopped.isNotEmpty()) {
                item { ModelPickerSectionHeader("Stopped") }
                items(stopped, key = { "stopped:${it.name}" }) { service ->
                    // F07-R2: visible, greyed, and not clickable — starting one
                    // is F11's guarded action, reached from there, not here.
                    LocalServiceRow(service = service, selected = false, onClick = null)
                }
            }

            if (remoteModelsConfigured && remoteModels.isNotEmpty()) {
                item { ModelPickerSectionHeader("OpenRouter") }
                items(remoteModels, key = { "remote:${it.modelId}" }) { option ->
                    RemoteModelRow(
                        option = option,
                        selected = selectedRef == ModelRef.OpenRouter(option.modelId),
                        onClick = { onSelect(option) },
                    )
                }
            }

            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun LocalServiceRow(service: ServiceSummary, selected: Boolean, onClick: (() -> Unit)?) {
    val colors = LlmTheme.colors
    val enabled = onClick != null
    val rowAlpha = if (enabled) 1f else 0.5f
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (selected) colors.accentDeep.copy(alpha = 0.25f) else colors.surface)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag("model_option_${service.name}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(
            Modifier.size(8.dp).clip(CircleShape)
                .background(if (service.isRunning) colors.green else colors.subtle.copy(alpha = rowAlpha)),
        )
        Column(Modifier.weight(1f)) {
            Text(
                service.name,
                color = colors.fg.copy(alpha = rowAlpha),
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${service.engine.label()} · :${service.port}${service.statusSuffix()}",
                color = colors.subtle.copy(alpha = rowAlpha),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        if (selected) Text("✓", color = colors.accent, style = MaterialTheme.typography.titleMedium)
    }
}

/** `running`/`exited`/`not-created` — R2's second criterion: the two stopped states read differently. */
private fun ServiceSummary.statusSuffix(): String = when (status) {
    "running" -> ""
    "not-created" -> " · not created"
    else -> " · $status"
}

@Composable
private fun RemoteModelRow(option: ModelOption.Remote, selected: Boolean, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (selected) colors.accentDeep.copy(alpha = 0.25f) else colors.surface)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag("model_option_${option.modelId}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(colors.engineOpenRouter.foreground))
        Column(Modifier.weight(1f)) {
            Text(option.label, color = colors.fg, style = MaterialTheme.typography.bodyMedium)
            Text(
                option.modelId,
                color = colors.subtle,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (selected) Text("✓", color = colors.accent, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun ModelPickerSectionHeader(title: String) {
    Text(
        title,
        color = LlmTheme.colors.subtle,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

private fun Engine.label(): String = when (this) {
    Engine.LLAMA_CPP -> "llama.cpp"
    Engine.VLLM -> "vLLM"
    Engine.DS4 -> "ds4"
    Engine.OPEN_ROUTER -> "OpenRouter"
    Engine.UNKNOWN -> "Unknown"
}
