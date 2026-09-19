package com.hpz.llmdockchat.feature.newchat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.NewChatPreferences
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.data.model.wireValue
import com.hpz.llmdockchat.feature.modelpicker.RememberedModel
import com.hpz.llmdockchat.feature.modelpicker.RememberedModelResolver
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.feature.share.SummarizeMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** F00-R5's Loading/Loaded/Failed, `Loaded` carrying every row of the sheet (F03-R6). */
sealed interface NewChatUiState {
    data object Loading : NewChatUiState

    data class Loaded(
        val localServices: List<ModelOption.LocalService>,
        /**
         * The full, unfiltered `GET /api/services` row set, kept live by
         * [ServicesStreamRepository] (F07-R1's third criterion) — what
         * [com.hpz.llmdockchat.feature.modelpicker.ModelPickerSheet] actually
         * renders. [localServices] above is untouched by F07: it still drives
         * the remembered-model resolution below, exactly as F03 built it.
         */
        val services: List<ServiceSummary> = emptyList(),
        val remoteModels: List<ModelOption.Remote>,
        val remoteModelsConfigured: Boolean,
        val selectedModel: ModelOption?,
        /** The remembered model from last time exists but isn't running (F03-R1's fourth criterion). */
        val rememberedModelUnavailable: Boolean,
        val prompts: List<ManagedPrompt>,
        /** null means "Default" — send neither `prompt_id` nor `main_system_prompt` (F03-R2). */
        val selectedPromptId: String?,
        val mcpServers: List<McpServerInfo>,
        val selectedMcpServerIds: Set<String>,
        /**
         * F14-R7 — the servers a summarize turn cannot do without, and the URL
         * it is about. [requiredMcpServerIds] gates [canStart]: a summarize
         * whose fetcher got untoggled would answer from the URL alone, so the
         * sheet refuses rather than starting it.
         */
        val requiredMcpServerIds: Set<String> = emptySet(),
        val summarizeUrl: String? = null,
        val creating: Boolean = false,
        /** A failed create — the server's own words, sheet stays open with selections intact (F03-R1's fifth criterion). */
        val createError: String? = null,
        /**
         * The conversation itself was created, but the follow-up `PUT
         * .../mcp_servers_json` failed (F00-R4 — never swallow an error).
         * The row selections stay intact; [Retry] re-issues only the PUT,
         * [openAnyway][NewChatViewModel.openAnyway] opens the thread with no
         * tools enabled.
         */
        val toolsFailure: ToolsFailure? = null,
    ) : NewChatUiState {
        val canStart: Boolean
            get() = selectedModel != null && !creating && toolsFailure == null && !blockedForSummarize

        private val blockedForSummarize: Boolean
            get() = summarizeUrl != null &&
                (requiredMcpServerIds.isEmpty() || !selectedMcpServerIds.containsAll(requiredMcpServerIds))
    }

    data class Failed(val message: String) : NewChatUiState
}

/** [conversationId] already exists server-side — see [NewChatUiState.Loaded.toolsFailure]. */
data class ToolsFailure(val conversationId: String, val message: String)

class NewChatViewModel(
    private val servicesRepository: ServicesRepository,
    private val promptsRepository: PromptsRepository,
    private val mcpServersRepository: McpServersRepository,
    private val openRouterModelsRepository: OpenRouterModelsRepository,
    private val conversationsRepository: ConversationsRepository,
    private val preferences: NewChatPreferences,
    private val servicesStreamRepository: ServicesStreamRepository,
    /**
     * F10-R6's "New chat from a model": the Models tab preselects a specific
     * running service, taking priority over whatever [preferences] last
     * remembered. Null for every other entry into this sheet (F02's FAB,
     * F07-R4's mid-thread switch does not use this screen at all).
     */
    private val preselectedServiceName: String? = null,
    /**
     * F14-R7 — the sheet reached from the share picker's summarize action. It
     * forces a URL-fetching server on the new thread, files the prepared turn
     * as a claim instead of a draft, and leaves [preferences] alone: choosing
     * to summarize a page must not silently change what the next ordinary
     * chat starts with.
     */
    private val summarizeMode: Boolean = false,
    private val sharedDraftStore: SharedDraftStore? = null,
) : ViewModel() {

    private val _state = MutableStateFlow<NewChatUiState>(NewChatUiState.Loading)
    val state: StateFlow<NewChatUiState> = _state.asStateFlow()

    /**
     * Guards against the screen's `LaunchedEffect(Unit)` re-firing on every
     * recomposition (same shape as [com.hpz.llmdockchat.feature.conversations.ConversationListViewModel],
     * but here a reload would also silently reset the user's picks) —
     * [load] is a one-shot fetch, not a refreshable list.
     */
    private var loaded = false

    fun load() {
        if (loaded) return
        loaded = true
        _state.value = NewChatUiState.Loading
        viewModelScope.launch {
            val services = servicesRepository.list().getOrElse { failure ->
                loaded = false
                _state.value = NewChatUiState.Failed(failure.appError.displayMessage)
                return@launch
            }
            val localServices = services
                .filter { it.isChatCapable }
                .map { ModelOption.LocalService(it.name, it.status) }

            // Prompts, tools and OpenRouter models are all Should-priority
            // (F03-R2, F03-R3) — a failure on any of them degrades to an
            // empty/unconfigured row rather than failing the whole sheet;
            // only the model list (Must, F03-R1) blocks the screen.
            val openRouter = openRouterModelsRepository.list().getOrNull()
            val prompts = promptsRepository.list().getOrNull().orEmpty().sortedBy { it.sortOrder }
            val catalog = mcpServersRepository.catalog(probe = summarizeMode).getOrNull()
            val mcpServers = catalog?.servers.orEmpty()
            val retrieval = catalog?.urlRetrieval

            val remoteModels = openRouter?.models.orEmpty()
            val remoteConfigured = openRouter?.configured ?: false

            val rememberedRaw = preferences.lastModel()
            val rememberedMcpIds = preferences.lastMcpServerIds().toSet()
            val summarizeUrl = if (summarizeMode) sharedDraftStore?.pending?.value?.url else null
            val requiredMcpIds = if (summarizeUrl != null) retrieval?.serverIds?.toSet().orEmpty() else emptySet()

            val remembered = RememberedModelResolver.resolve(
                rememberedRaw = rememberedRaw,
                localServices = localServices,
                remoteModels = remoteModels,
                preselectedServiceName = preselectedServiceName,
            )
            val selectedModel = (remembered as? RememberedModel.Resolved)?.option
            val unavailable = remembered is RememberedModel.Unavailable

            _state.value = NewChatUiState.Loaded(
                localServices = localServices,
                services = services,
                remoteModels = remoteModels,
                remoteModelsConfigured = remoteConfigured,
                selectedModel = selectedModel,
                rememberedModelUnavailable = unavailable,
                prompts = prompts,
                selectedPromptId = null,
                mcpServers = mcpServers,
                selectedMcpServerIds = requiredMcpIds +
                    if (summarizeUrl != null) emptySet() else rememberedMcpIds.intersect(mcpServers.map { it.id }.toSet()),
                requiredMcpServerIds = requiredMcpIds,
                summarizeUrl = summarizeUrl,
            )

            // F07-R1's third criterion: a container started or stopped
            // elsewhere while this sheet is open shows up with no manual
            // refresh. Runs for the screen's lifetime (Architecture D5) —
            // NEW_CHAT is a short pushed screen (F03), not a persistent tab,
            // so an always-open connection here is cheap.
            launch {
                servicesStreamRepository.stream().collect { live ->
                    updateLoaded { it.copy(services = live) }
                }
            }
        }
    }

    fun retry() {
        loaded = false
        load()
    }

    fun selectModel(option: ModelOption) = updateLoaded {
        it.copy(selectedModel = option, rememberedModelUnavailable = false, createError = null)
    }

    fun selectPrompt(promptId: String?) = updateLoaded { it.copy(selectedPromptId = promptId, createError = null) }

    fun toggleMcpServer(id: String) = updateLoaded {
        val selection = if (id in it.selectedMcpServerIds) it.selectedMcpServerIds - id else it.selectedMcpServerIds + id
        it.copy(selectedMcpServerIds = selection, createError = null)
    }

    fun create(onCreated: (String) -> Unit) {
        val current = _state.value as? NewChatUiState.Loaded ?: return
        val model = current.selectedModel ?: return
        if (current.creating) return
        _state.value = current.copy(creating = true, createError = null)

        viewModelScope.launch {
            conversationsRepository.create(
                mainService = model.ref.wireValue,
                promptId = current.selectedPromptId,
            ).fold(
                onSuccess = { id ->
                    if (current.summarizeUrl == null) {
                        preferences.rememberModel(model.ref.wireValue)
                        preferences.rememberMcpServerIds(current.selectedMcpServerIds.toList())
                    }
                    if (current.selectedMcpServerIds.isEmpty()) {
                        updateLoaded { it.copy(creating = false) }
                        onCreated(id)
                    } else {
                        // The conversation exists either way from here on —
                        // a failure past this point is never re-thrown or
                        // rolled back, only surfaced (F00-R4).
                        applyTools(id, current.selectedMcpServerIds.toList(), onCreated)
                    }
                },
                onFailure = { failure ->
                    updateLoaded { it.copy(creating = false, createError = failure.appError.displayMessage) }
                },
            )
        }
    }

    /** Re-issues the `mcp_servers_json` PUT for a conversation that already exists (S1 fix-up). */
    fun retryTools(onCreated: (String) -> Unit) {
        val current = _state.value as? NewChatUiState.Loaded ?: return
        val failure = current.toolsFailure ?: return
        if (current.creating) return
        _state.value = current.copy(creating = true)
        viewModelScope.launch {
            applyTools(failure.conversationId, current.selectedMcpServerIds.toList(), onCreated)
        }
    }

    /** Opens the thread as-is, with whatever tool state the failed PUT left it in. */
    fun openAnyway(onCreated: (String) -> Unit) {
        val failure = (_state.value as? NewChatUiState.Loaded)?.toolsFailure ?: return
        onCreated(failure.conversationId)
    }

    private suspend fun applyTools(conversationId: String, serverIds: List<String>, onCreated: (String) -> Unit) {
        conversationsRepository.setMcpServers(conversationId, serverIds).fold(
            onSuccess = {
                stageSummarizeClaim(conversationId)
                updateLoaded { it.copy(creating = false, toolsFailure = null) }
                onCreated(conversationId)
            },
            onFailure = { failure ->
                updateLoaded {
                    it.copy(
                        creating = false,
                        toolsFailure = ToolsFailure(conversationId, failure.appError.displayMessage),
                    )
                }
            },
        )
    }

    /** F14-R7 — claim instead of draft: the thread sends the turn on opening. */
    private fun stageSummarizeClaim(conversationId: String) {
        val url = (state.value as? NewChatUiState.Loaded)?.summarizeUrl ?: return
        sharedDraftStore?.stageForAutoSend(conversationId, SummarizeMessage.build(url))
    }

    private inline fun updateLoaded(transform: (NewChatUiState.Loaded) -> NewChatUiState.Loaded) {
        val current = _state.value
        if (current is NewChatUiState.Loaded) _state.value = transform(current)
    }
}
