package com.hpz.llmdockchat.feature.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.prefs.SummarizeDefaults
import com.hpz.llmdockchat.core.prefs.SummarizePreferences
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.model.McpServerInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The two settings F16 lands. F13 owns the Settings screen proper and absorbs
 * this row set when it is built; until then the screen holds only what the
 * summarize path needs, because a control with no store behind it is the thing
 * this feature must not ship.
 */
sealed interface SettingsUiState {
    data object Loading : SettingsUiState

    data class Loaded(
        val promptDraft: String,
        /** What is stored right now — the bar [canSavePrompt] compares the draft against. */
        val promptSaved: String,
        val usingDefaultPrompt: Boolean,
        val servers: List<McpServerInfo> = emptyList(),
        val selectedIds: Set<String> = emptySet(),
        val registryFailed: Boolean = false,
    ) : SettingsUiState {
        val canSavePrompt: Boolean
            get() = promptDraft.isNotBlank() && promptDraft.trim() != promptSaved

        val canResetPrompt: Boolean get() = !usingDefaultPrompt

        /**
         * False means the summarize row is hidden for want of a tool the turn
         * actually needs — said here rather than leaving a summarize feature
         * silently absent from the picker.
         */
        val summarizeRowAvailable: Boolean
            get() = SummarizeDefaults.effectiveTools(selectedIds.toList(), servers.map { it.id }).isNotEmpty()
    }
}

class SettingsViewModel(
    private val summarize: SummarizePreferences,
    private val mcpServersRepository: McpServersRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SettingsUiState>(SettingsUiState.Loading)
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            val override = summarize.promptOverride()
            // A never-chosen tool list shows the preselection and is written on
            // first read, so what the row offers and what Settings displays are
            // the same list rather than a default the next read might lose.
            val stored = summarize.toolIds()
            val registry = mcpServersRepository.list().getOrNull()
            val effective = SummarizeDefaults.effectiveTools(stored, registry.orEmpty().map { it.id })
            if (stored == null && effective.isNotEmpty()) summarize.setToolIds(effective)

            _state.value = SettingsUiState.Loaded(
                promptDraft = override ?: SummarizeDefaults.PROMPT,
                promptSaved = override ?: SummarizeDefaults.PROMPT,
                usingDefaultPrompt = override == null,
                servers = registry.orEmpty(),
                selectedIds = effective.toSet(),
                registryFailed = registry == null,
            )
        }
    }

    fun onPromptChange(text: String) {
        (_state.value as? SettingsUiState.Loaded)?.let { _state.value = it.copy(promptDraft = text) }
    }

    fun savePrompt() {
        val current = _state.value as? SettingsUiState.Loaded ?: return
        if (!current.canSavePrompt) return
        val stored = current.promptDraft.trim()
        summarize.setPromptOverride(stored)
        _state.value = current.copy(promptSaved = stored, usingDefaultPrompt = false)
    }

    /** Back to the built-in text, not to an empty one — an empty first message summarises nothing. */
    fun resetPrompt() {
        val current = _state.value as? SettingsUiState.Loaded ?: return
        summarize.setPromptOverride("")
        _state.value = current.copy(
            promptDraft = SummarizeDefaults.PROMPT,
            promptSaved = SummarizeDefaults.PROMPT,
            usingDefaultPrompt = true,
        )
    }

    fun toggleTool(id: String) {
        val current = _state.value as? SettingsUiState.Loaded ?: return
        val next = if (id in current.selectedIds) current.selectedIds - id else current.selectedIds + id
        summarize.setToolIds(next.sortedBy { id -> SummarizeDefaults.TOOL_IDS.indexOf(id).let { if (it < 0) 99 else it } })
        _state.value = current.copy(selectedIds = next)
    }
}
