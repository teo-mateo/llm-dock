package com.hpz.llmdockchat.feature.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.model.ConversationSummary
import com.hpz.llmdockchat.data.model.UrlRetrieval
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The four UI states, for the share-target picker. Same list data
 * as the Chats tab — `ConversationsRepository.list()` is already
 * `updated_at DESC` and `unfiled=true` — but no selection, swipe or delete:
 * the actions are picking a row, and summarizing a shared page.
 */
sealed interface ShareTargetUiState {
    data object Loading : ShareTargetUiState

    data class Loaded(
        val conversations: List<ConversationSummary>,
        val share: StagedShare,
        val summarize: SummarizeOption = SummarizeOption.NotShared,
        val refreshing: Boolean = false,
        val actionError: String? = null,
    ) : ShareTargetUiState {
        val isEmpty: Boolean get() = conversations.isEmpty()
    }

    data class Failed(val message: String) : ShareTargetUiState
}

class ShareTargetViewModel(
    private val repository: ConversationsRepository,
    private val store: SharedDraftStore,
    private val summarizeLauncher: SummarizeLauncher,
) : ViewModel() {

    private val _state = MutableStateFlow<ShareTargetUiState>(ShareTargetUiState.Loading)
    val state: StateFlow<ShareTargetUiState> = _state.asStateFlow()

    /** The last probe verdict — the option is derived from it and the share, never stored twice. */
    private var retrieval: UrlRetrieval? = null

    private var probeFailed = false

    private var launching = false

    init {
        // A second share arriving while the picker is open replaces the staged
        // content on screen — the NavHost does not re-navigate (already here),
        // so the store is the only channel the change comes through.
        viewModelScope.launch {
            store.pending.collect { share ->
                val current = _state.value
                if (current is ShareTargetUiState.Loaded) {
                    val next = share ?: StagedShare()
                    _state.value = current.copy(share = next, summarize = optionFor(next))
                }
            }
        }
    }

    /**
     * The conversation list and the retrieval probe are independent reads, so
     * they run together: by the time a finger reaches the summarize action the
     * tap must not wait on anything.
     */
    fun refresh() {
        val current = _state.value
        _state.value = when (current) {
            is ShareTargetUiState.Loaded -> current.copy(refreshing = true, summarize = SummarizeOption.Checking)
            else -> ShareTargetUiState.Loading
        }
        viewModelScope.launch {
            val probe = async { summarizeLauncher.probe() }
            repository.list().fold(
                onSuccess = { conversations ->
                    val share = store.pending.value ?: StagedShare()
                    applyProbe(probe.await())
                    _state.value = ShareTargetUiState.Loaded(
                        conversations = conversations,
                        share = share,
                        summarize = optionFor(share),
                    )
                },
                onFailure = { failure ->
                    probe.cancel()
                    _state.value = ShareTargetUiState.Failed(failure.appError.displayMessage)
                },
            )
        }
    }

    /**
     * One tap of "Summarise". [onOpened] navigates to the thread that now owes
     * one turn; [onChooseModel] opens the new-chat sheet with the share still
     * staged, for a remembered model that is gone or stopped.
     */
    fun summarize(onOpened: (String) -> Unit, onChooseModel: () -> Unit) {
        val loaded = _state.value as? ShareTargetUiState.Loaded ?: return
        val ready = loaded.summarize as? SummarizeOption.Ready ?: return
        if (launching) return
        launching = true
        _state.value = loaded.copy(summarize = SummarizeOption.Checking, actionError = null)

        viewModelScope.launch {
            when (val outcome = summarizeLauncher.launch(ready.url, ready.serverIds)) {
                is SummarizeOutcome.Opened -> onOpened(outcome.conversationId)
                SummarizeOutcome.ChooseModel -> {
                    launching = false
                    restoreReady(loaded, ready)
                    onChooseModel()
                }
                is SummarizeOutcome.Failed -> {
                    launching = false
                    val now = _state.value as? ShareTargetUiState.Loaded
                    if (now != null) _state.value = now.copy(summarize = ready, actionError = outcome.message)
                }
            }
        }
    }

    fun dismissActionError() {
        (_state.value as? ShareTargetUiState.Loaded)?.let { _state.value = it.copy(actionError = null) }
    }

    private fun applyProbe(result: Result<UrlRetrieval>) {
        retrieval = result.getOrNull() ?: retrieval
        probeFailed = result.isFailure
    }

    private fun restoreReady(loaded: ShareTargetUiState.Loaded, ready: SummarizeOption.Ready) {
        val current = _state.value
        if (current is ShareTargetUiState.Loaded && current.share == loaded.share) {
            _state.value = current.copy(summarize = ready)
        }
    }

    private fun optionFor(share: StagedShare): SummarizeOption =
        if (probeFailed && share.url != null) SummarizeOption.UNREACHABLE
        else SummarizeOption.of(share, retrieval)
}
