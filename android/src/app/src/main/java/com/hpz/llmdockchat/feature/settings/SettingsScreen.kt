package com.hpz.llmdockchat.feature.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons

/**
 * The two rows F16 needs: the instruction a summarize turn sends, and the tools
 * it is allowed to use. F13 builds the real Settings screen and takes these rows
 * when it does — until then this is a two-row screen rather than a settings
 * framework, because the alternative was a summarize path whose wording and tool
 * ids could only be changed by rebuilding the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    val colors = LlmTheme.colors

    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(
        modifier = modifier.testTag("settings_screen"),
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = { Text("Settings", color = colors.fg, fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("settings_back")) {
                        Icon(DesignLabIcons.Back, contentDescription = "Back", tint = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                    scrolledContainerColor = Color.Transparent,
                ),
                windowInsets = WindowInsets.statusBars,
            )
        },
    ) { padding ->
        Box(
            Modifier
                .fillMaxSize()
                .background(colors.appGradient)
                .padding(padding),
        ) {
            when (val current = state) {
                SettingsUiState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator(color = colors.accent)
                }
                is SettingsUiState.Loaded -> Column(
                    Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 20.dp),
                ) {
                    PromptCard(
                        draft = current.promptDraft,
                        usingDefault = current.usingDefaultPrompt,
                        canSave = current.canSavePrompt,
                        canReset = current.canResetPrompt,
                        onPromptChange = viewModel::onPromptChange,
                        onSave = viewModel::savePrompt,
                        onReset = viewModel::resetPrompt,
                    )
                    Spacer(Modifier.height(18.dp))
                    ToolsCard(current) { viewModel.toggleTool(it) }
                    Spacer(Modifier.height(28.dp))
                }
            }
        }
    }
}

@Composable
private fun PromptCard(
    draft: String,
    usingDefault: Boolean,
    canSave: Boolean,
    canReset: Boolean,
    onPromptChange: (String) -> Unit,
    onSave: () -> Unit,
    onReset: () -> Unit,
) {
    val colors = LlmTheme.colors
    Card(title = "Summarize prompt", subtitle = "First message of a summarize thread") {
        OutlinedTextField(
            value = draft,
            onValueChange = onPromptChange,
            minLines = 5,
            maxLines = 12,
            modifier = Modifier.fillMaxWidth().testTag("settings_summarize_prompt"),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = colors.fg,
                unfocusedTextColor = colors.fg,
                focusedBorderColor = colors.accent,
                unfocusedBorderColor = colors.line,
                cursorColor = colors.accent,
            ),
        )
        Row(
            Modifier.fillMaxWidth().padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                if (usingDefault) "Built-in default" else "Custom",
                color = if (usingDefault) colors.subtle else colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.weight(1f).testTag("settings_prompt_state"),
            )
            if (canReset) {
                TextButton(onClick = onReset, modifier = Modifier.testTag("settings_prompt_reset")) {
                    Text("Reset", color = colors.subtle)
                }
            }
            TextButton(
                onClick = onSave,
                enabled = canSave,
                modifier = Modifier.testTag("settings_prompt_save"),
            ) {
                Text("Save", color = if (canSave) colors.accent else colors.muted)
            }
        }
    }
}

@Composable
private fun ToolsCard(state: SettingsUiState.Loaded, onToggle: (String) -> Unit) {
    val colors = LlmTheme.colors
    Card(title = "Summarize tools", subtitle = "Enabled on the thread a share creates") {
        if (state.registryFailed) {
            Text(
                "The tool registry could not be read.",
                color = colors.amber,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag("settings_summarize_tools_empty"),
            )
        } else {
            if (!state.summarizeRowAvailable) {
                // Said, and then the rows stay on screen: a card that hides its own
                // checkboxes whenever they happen to be unchecked is a setting that
                // can be turned off once and never turned back on.
                Text(
                    "With no tool selected the summarize row stays hidden in the share " +
                        "picker — a summary without a fetch tool would be invented rather " +
                        "than read.",
                    color = colors.amber,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp).testTag("settings_summarize_tools_empty"),
                )
            }
            state.servers.forEach { server ->
                ToolRow(server, checked = server.id in state.selectedIds, onToggle = onToggle)
            }
        }
    }
}

@Composable
private fun ToolRow(server: McpServerInfo, checked: Boolean, onToggle: (String) -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .clickable { onToggle(server.id) }
            .padding(vertical = 6.dp)
            .testTag("settings_tool_${server.id}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Checkbox(
            checked = checked,
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

@Composable
private fun Card(title: String, subtitle: String, content: @Composable () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(colors.surfaceHigh)
            .padding(16.dp),
    ) {
        Text(
            title,
            color = colors.fg,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(subtitle, color = colors.subtle, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(10.dp))
        content()
    }
}
