package com.hpz.llmdockchat.feature.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.core.prefs.NewChatPreferences
import com.hpz.llmdockchat.core.prefs.SummarizeDefaults
import com.hpz.llmdockchat.core.prefs.SummarizePreferences
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.model.ConversationSummary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * F00-R5's four states, for the share-target picker (F14-R2). Same list data as
 * the Chats tab — `ConversationsRepository.list()` is already `updated_at DESC`
 * and `unfiled=true` — but no selection, swipe or delete: the actions are
 * picking a row and, since F16, summarizing the shared link.
 */
sealed interface ShareTargetUiState {
    data object Loading : ShareTargetUiState

    data class Loaded(
        val conversations: List<ConversationSummary>,
        val share: StagedShare,
        val refreshing: Boolean = false,
        /** Ids as `GET /api/chat/mcp-servers` reported them. The row and the tap read this one list. */
        val registryIds: List<String> = emptyList(),
        /** The stored summarize selection; null means never chosen, which is what enables the preselection. */
        val storedToolIds: List<String>? = null,
        val summarizeUrl: String? = null,
        val summarizing: Boolean = false,
        /** A failed create — nothing was created and the share stays staged, so a second tap is the retry. */
        val summarizeError: String? = null,
        /** One-shot navigation request; [consumeLaunch] clears it. */
        val launch: SummarizeLaunch? = null,
    ) : ShareTargetUiState {
        val isEmpty: Boolean get() = conversations.isEmpty()

        /**
         * The tools a summarize turn would get, narrowed to what the registry
         * reports. Empty hides the row: the registry is the only source of tool
         * ids (F08-R1) and a summarize turn without a fetch tool answers from
         * imagination.
         */
        val summarizeTools: List<String> get() = SummarizeDefaults.effectiveTools(storedToolIds, registryIds)
        val canSummarize: Boolean get() = summarizeUrl != null && summarizeTools.isNotEmpty() && !summarizing
    }

    data class Failed(val message: String) : ShareTargetUiState
}

/** Where a summarize tap sends navigation. The staging itself has already happened. */
sealed interface SummarizeLaunch {
    /** Created, tools on, message staged with the auto-send armed — the thread opens generating. */
    data class Thread(val conversationId: String) : SummarizeLaunch

    /** Nothing created: the F03 sheet picks the model with the flow already armed. */
    data object NewChat : SummarizeLaunch
}

class ShareTargetViewModel(
    private val repository: ConversationsRepository,
    private val store: SharedDraftStore,
    private val drafts: DraftStore,
    private val servicesRepository: ServicesRepository,
    private val mcpServersRepository: McpServersRepository,
    private val summarizePreferences: SummarizePreferences,
    private val newChatPreferences: NewChatPreferences,
) : ViewModel() {

    private val _state = MutableStateFlow<ShareTargetUiState>(ShareTargetUiState.Loading)
    val state: StateFlow<ShareTargetUiState> = _state.asStateFlow()

    init {
        // A second share arriving while the picker is open replaces the staged
        // content on screen — the NavHost does not re-navigate (already here),
        // so the store is the only channel the change comes through.
        viewModelScope.launch {
            store.pending.collect { share ->
                val current = _state.value
                if (current is ShareTargetUiState.Loaded) {
                    _state.value = current.withShare(share ?: StagedShare())
                }
            }
        }
    }

    /** Same shape as the conversation list's refresh: cold start and retry show Loading, return shows a refresh. */
    fun refresh() {
        val current = _state.value
        _state.value = when (current) {
            is ShareTargetUiState.Loaded -> current.copy(refreshing = true)
            else -> ShareTargetUiState.Loading
        }
        viewModelScope.launch {
            // The registry rides along with the list rather than being read at
            // tap time: the row's visibility and the tap's decision must come
            // from one read of it, or the row can offer what the tap refuses.
            val registry = mcpServersRepository.list().getOrNull().orEmpty().map { it.id }
            repository.list().fold(
                onSuccess = { conversations ->
                    _state.value = ShareTargetUiState.Loaded(
                        conversations = conversations,
                        share = store.pending.value ?: StagedShare(),
                        registryIds = registry,
                        storedToolIds = summarizePreferences.toolIds(),
                        summarizeUrl = SummarizePlanner.urlIn(store.pending.value),
                    )
                },
                onFailure = { failure ->
                    _state.value = ShareTargetUiState.Failed(failure.appError.displayMessage)
                },
            )
        }
    }

    /**
     * F16 — one tap: create a thread on the remembered model, put the summarize
     * tools on it, stage the instruction + URL, arm the send. Three sequential
     * calls, because `POST /api/chat/conversations` builds its row from a fixed
     * field set and does not read `mcp_servers_json` — the create-then-PUT shape
     * F03 already documents.
     *
     * The three failures are not alike: a failed create leaves everything alone,
     * a failed tools PUT withdraws the auto-send on purpose
     * ([SummarizePlan.PickModelFirst]'s counterpart in [createOn]), and a failed
     * send is the ordinary F04 path inside the thread.
     */
    fun summarize() {
        val current = loaded() ?: return
        if (!current.canSummarize) return
        _state.value = current.copy(summarizing = true, summarizeError = null)

        viewModelScope.launch {
            val prompt = summarizePreferences.promptOverride() ?: SummarizeDefaults.PROMPT
            val services = servicesRepository.list().getOrNull().orEmpty()
            when (
                val plan = SummarizePlanner.plan(
                    share = current.share,
                    prompt = prompt,
                    storedToolIds = current.storedToolIds,
                    registry = current.registryIds,
                    rememberedModel = newChatPreferences.lastModel(),
                    services = services,
                )
            ) {
                SummarizePlan.Hidden -> settleWithMessage(
                    "No summarize-capable tool is reported by this dashboard.",
                )
                is SummarizePlan.PickModelFirst -> {
                    store.armSummarize(SummarizeIntent(plan.message, plan.toolIds))
                    publishLaunch(SummarizeLaunch.NewChat)
                }
                is SummarizePlan.CreateOn -> createOn(plan)
            }
        }
    }

    fun consumeLaunch() {
        loaded()?.let { _state.value = it.copy(launch = null) }
    }

    private suspend fun createOn(plan: SummarizePlan.CreateOn) {
        repository.create(plan.modelService).fold(
            onSuccess = { id ->
                // The auto-send deviation is withdrawn exactly here: a summarize
                // turn whose tools could not be enabled is a model inventing the
                // contents of a URL it never read — worse than an error, because
                // it looks like an answer.
                val toolsApplied = repository.setMcpServers(id, plan.toolIds).isSuccess
                store.stageForConversation(id, drafts, plan.message)
                if (toolsApplied) {
                    store.armAutoSend(id)
                } else {
                    store.saveNotice(id, SharedDraftStore.TOOLS_NOT_ENABLED_NOTICE)
                }
                publishLaunch(SummarizeLaunch.Thread(id))
            },
            onFailure = { failure -> settleWithMessage(failure.appError.displayMessage) },
        )
    }

    private fun settleWithMessage(message: String) {
        loaded()?.let { _state.value = it.copy(summarizing = false, summarizeError = message) }
    }

    private fun publishLaunch(launch: SummarizeLaunch) {
        loaded()?.let { _state.value = it.copy(summarizing = false, launch = launch) }
    }

    private fun loaded(): ShareTargetUiState.Loaded? = _state.value as? ShareTargetUiState.Loaded

    /** Re-derives the row with the new payload, so a second share cannot leave a stale row on screen. */
    private fun ShareTargetUiState.Loaded.withShare(share: StagedShare) = copy(
        share = share,
        summarizeUrl = SummarizePlanner.urlIn(share),
    )
}
