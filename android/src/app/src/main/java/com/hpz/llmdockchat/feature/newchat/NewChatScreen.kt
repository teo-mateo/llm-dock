package com.hpz.llmdockchat.feature.newchat

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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.feature.modelpicker.ModelPickerSheet

/**
 * Screen 03 · New chat sheet (F03). A pushed screen rather than a modal, as
 * established in F02's placeholder and Architecture D12 — [NEW_CHAT] carries
 * no bottom bar. Three rows at most (Model, system prompt, tools) with the
 * project row cut entirely (F03-R4, withdrawn); the tools row is hidden
 * outright when no servers are available, keeping the sheet coherent at any
 * combination of optional data (F03-R6).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewChatScreen(
    viewModel: NewChatViewModel,
    onBack: () -> Unit,
    onConversationCreated: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("new_chat_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text("New chat", color = colors.fg) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("new_chat_back")) {
                        Text("←", color = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val current = state) {
                is NewChatUiState.Loading -> LoadingState()
                is NewChatUiState.Failed -> FailedState(current.message, onRetry = viewModel::retry)
                is NewChatUiState.Loaded -> NewChatSheetBody(
                    state = current,
                    onSelectModel = viewModel::selectModel,
                    onSelectPrompt = viewModel::selectPrompt,
                    onToggleMcpServer = viewModel::toggleMcpServer,
                    onStart = { viewModel.create(onConversationCreated) },
                    onRetryTools = { viewModel.retryTools(onConversationCreated) },
                    onOpenAnyway = { viewModel.openAnyway(onConversationCreated) },
                )
            }
        }
    }
}

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize().testTag("new_chat_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun FailedState(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp).testTag("new_chat_failed"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Couldn't load the new chat sheet", color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = onRetry, modifier = Modifier.testTag("new_chat_retry")) {
            Text("Retry", color = colors.accent)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NewChatSheetBody(
    state: NewChatUiState.Loaded,
    onSelectModel: (ModelOption) -> Unit,
    onSelectPrompt: (String?) -> Unit,
    onToggleMcpServer: (String) -> Unit,
    onStart: () -> Unit,
    onRetryTools: () -> Unit,
    onOpenAnyway: () -> Unit,
) {
    val colors = LlmTheme.colors
    var showModelPicker by remember { mutableStateOf(false) }
    var showPromptPicker by remember { mutableStateOf(false) }
    var showToolsPicker by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().testTag("new_chat_body")) {
        SheetRow(
            label = "Model",
            value = state.selectedModel?.let { it.displayLabel() } ?: "Choose a model",
            valueColor = if (state.selectedModel != null) colors.accent else colors.muted,
            onClick = { showModelPicker = true },
            testTag = "new_chat_row_model",
        )
        if (state.rememberedModelUnavailable) {
            Text(
                "The model used last time isn't running — pick one to continue.",
                color = colors.amber,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp).testTag("new_chat_model_unavailable"),
            )
        }
        HorizontalDivider(color = colors.line)

        val selectedPromptName = state.prompts.find { it.id == state.selectedPromptId }?.name
        SheetRow(
            label = "System prompt",
            value = selectedPromptName ?: "Server default",
            onClick = { showPromptPicker = true },
            testTag = "new_chat_row_prompt",
        )

        if (state.mcpServers.isNotEmpty()) {
            HorizontalDivider(color = colors.line)
            val selectedNames = state.mcpServers.filter { it.id in state.selectedMcpServerIds }.map { it.name }
            SheetRow(
                label = "Tools",
                value = if (selectedNames.isEmpty()) "None" else selectedNames.joinToString(", "),
                badge = state.selectedMcpServerIds.size.takeIf { it > 0 },
                onClick = { showToolsPicker = true },
                testTag = "new_chat_row_tools",
            )
        }

        Spacer(Modifier.weight(1f))

        val toolsFailure = state.toolsFailure
        if (toolsFailure != null) {
            ToolsFailureBanner(
                message = toolsFailure.message,
                creating = state.creating,
                onRetry = onRetryTools,
                onOpenAnyway = onOpenAnyway,
            )
        } else {
            state.createError?.let { error ->
                Text(
                    error,
                    color = colors.red,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp).testTag("new_chat_error"),
                )
            }
            StartButton(enabled = state.canStart, creating = state.creating, onClick = onStart)
        }
    }

    if (showModelPicker) {
        ModelPickerSheet(
            services = state.services,
            remoteModels = state.remoteModels,
            remoteModelsConfigured = state.remoteModelsConfigured,
            selectedRef = state.selectedModel?.ref,
            onSelect = {
                onSelectModel(it)
                showModelPicker = false
            },
            onDismiss = { showModelPicker = false },
        )
    }

    if (showPromptPicker) {
        PromptPickerSheet(
            prompts = state.prompts,
            selectedId = state.selectedPromptId,
            onSelect = {
                onSelectPrompt(it)
                showPromptPicker = false
            },
            onDismiss = { showPromptPicker = false },
        )
    }

    if (showToolsPicker) {
        ToolsPickerSheet(
            servers = state.mcpServers,
            selectedIds = state.selectedMcpServerIds,
            onToggle = onToggleMcpServer,
            onDismiss = { showToolsPicker = false },
        )
    }
}

private fun ModelOption.displayLabel(): String = when (this) {
    is ModelOption.LocalService -> serviceName
    is ModelOption.Remote -> label
}

@Composable
private fun SheetRow(
    label: String,
    value: String,
    onClick: () -> Unit,
    testTag: String,
    valueColor: androidx.compose.ui.graphics.Color = LlmTheme.colors.muted,
    badge: Int? = null,
) {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp)
            .testTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, color = colors.fg, style = MaterialTheme.typography.bodyLarge)
            Text(
                value,
                color = valueColor,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        badge?.let {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .background(colors.green.copy(alpha = 0.2f))
                    .padding(horizontal = 8.dp, vertical = 2.dp),
            ) {
                Text("$it", color = colors.green, style = MaterialTheme.typography.labelSmall)
            }
        }
        Text("›", color = colors.subtle, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun StartButton(enabled: Boolean, creating: Boolean, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (enabled) colors.accent else colors.surfaceElevated)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(vertical = 14.dp)
            .testTag("new_chat_start"),
        contentAlignment = Alignment.Center,
    ) {
        if (creating) {
            CircularProgressIndicator(
                color = colors.onAccent,
                modifier = Modifier.height(20.dp).testTag("new_chat_creating"),
            )
        } else {
            Text(
                "Start",
                color = if (enabled) colors.onAccent else colors.subtle,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

/**
 * S1 fix-up: the conversation was created but the follow-up `mcp_servers_json`
 * PUT failed. Shown in place of the Start button — the create call itself is
 * never retried, only the tools assignment (S1's brief: "keep the sheet up
 * ... Retry / Open anyway", contained to this screen rather than passed
 * through the nav graph).
 */
@Composable
private fun ToolsFailureBanner(
    message: String,
    creating: Boolean,
    onRetry: () -> Unit,
    onOpenAnyway: () -> Unit,
) {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier.fillMaxWidth().padding(16.dp).testTag("new_chat_tools_failure"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            "Conversation created, but tools couldn't be set: $message",
            color = colors.amber,
            style = MaterialTheme.typography.bodyMedium,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (creating) {
                CircularProgressIndicator(
                    color = colors.accent,
                    modifier = Modifier.height(20.dp).testTag("new_chat_tools_retry_progress"),
                )
            } else {
                TextButton(onClick = onRetry, modifier = Modifier.testTag("new_chat_tools_retry")) {
                    Text("Retry", color = colors.accent)
                }
                TextButton(onClick = onOpenAnyway, modifier = Modifier.testTag("new_chat_tools_open_anyway")) {
                    Text("Open anyway", color = colors.muted)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PromptPickerSheet(
    prompts: List<ManagedPrompt>,
    selectedId: String?,
    onSelect: (String?) -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LlmTheme.colors
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("prompt_picker_sheet"),
    ) {
        // C3: the sheet draws behind the navigation bar, so without
        // this its last row is unreachable under the 44 dp button bar.
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            item {
                PickerRow(
                    title = "Server default",
                    subtitle = null,
                    selected = selectedId == null,
                    onClick = { onSelect(null) },
                    testTag = "prompt_option_default",
                )
            }
            items(prompts, key = { it.id }) { prompt ->
                PickerRow(
                    title = prompt.name,
                    subtitle = null,
                    selected = selectedId == prompt.id,
                    onClick = { onSelect(prompt.id) },
                    testTag = "prompt_option_${prompt.id}",
                )
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ToolsPickerSheet(
    servers: List<McpServerInfo>,
    selectedIds: Set<String>,
    onToggle: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LlmTheme.colors
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("tools_picker_sheet"),
    ) {
        // C3: the sheet draws behind the navigation bar, so without
        // this its last row is unreachable under the 44 dp button bar.
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            items(servers, key = { it.id }) { server ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onToggle(server.id) }
                        .padding(horizontal = 16.dp, vertical = 10.dp)
                        .testTag("tool_option_${server.id}"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Checkbox(
                        checked = server.id in selectedIds,
                        onCheckedChange = { onToggle(server.id) },
                        colors = CheckboxDefaults.colors(checkedColor = colors.accent, uncheckedColor = colors.subtle),
                    )
                    Column(Modifier.weight(1f)) {
                        Text(server.name, color = colors.fg, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            server.description,
                            color = colors.muted,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            item {
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().padding(16.dp).testTag("tools_picker_done"),
                ) {
                    Text("Done", color = colors.accent)
                }
            }
        }
    }
}

@Composable
private fun PickerSectionHeader(title: String) {
    Text(
        title,
        color = LlmTheme.colors.subtle,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun PickerRow(
    title: String,
    subtitle: String?,
    onClick: () -> Unit,
    testTag: String,
    selected: Boolean = false,
    subtitleColor: androidx.compose.ui.graphics.Color = LlmTheme.colors.muted,
) {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (selected) colors.accentDeep.copy(alpha = 0.25f) else colors.surface)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, color = colors.fg, style = MaterialTheme.typography.bodyLarge)
            subtitle?.let {
                Text(it, color = subtitleColor, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
