package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.data.model.ArtifactRecord
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ParseWarning
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.data.model.wireValue

data class PendingUserMessage(val content: String, val images: List<String> = emptyList())

data class StreamingToolCall(
    val name: String,
    val serverId: String?,
    val arguments: String? = null,
    val result: String? = null,
) {
    val isRunning: Boolean get() = result == null
}

data class StreamingTurn(
    val userMessage: PendingUserMessage?,
    val runId: String? = null,
    val content: String = "",
    val reasoning: String = "",
    val toolCalls: List<StreamingToolCall> = emptyList(),
    val parseWarning: ParseWarning? = null,
    val artifacts: List<ArtifactRecord> = emptyList(),
    val stopping: Boolean = false,
    val reconnecting: Boolean = false,
    val reattached: Boolean = false,
    val unconfirmed: Boolean = false,
    val error: String? = null,
) {
    val hasVisibleOutput: Boolean
        get() = content.isNotEmpty() || reasoning.isNotEmpty() || toolCalls.isNotEmpty()
}

data class ThreadState(
    val messages: List<ChatMessage> = emptyList(),
    val streaming: StreamingTurn? = null,
)

data class PendingEdit(
    val message: ChatMessage,
    val content: String,
    val images: List<String>,
    val discardCount: Int,
)

data class ModelPickerState(
    val services: List<ServiceSummary> = emptyList(),
    val remoteModels: List<ModelOption.Remote> = emptyList(),
    val remoteModelsConfigured: Boolean = false,
)

data class ChatSettingsState(
    val servers: List<McpServerInfo> = emptyList(),
    val prompts: List<ManagedPrompt> = emptyList(),
)

data class ReasoningPickerState(
    val writePending: Boolean = false,
)

sealed interface ThreadUiState {
    data object Loading : ThreadUiState

    data class Failed(val message: String) : ThreadUiState

    data class Loaded(
        val conversation: ConversationDetail,
        val thread: ThreadState,
        val composer: String = "",
        val attachments: List<String> = emptyList(),
        val sending: Boolean = false,
        val actionError: String? = null,
        val pendingDelete: ChatMessage? = null,
        val editingMessage: ChatMessage? = null,
        val pendingEdit: PendingEdit? = null,
        val modelPicker: ModelPickerState? = null,
        val settings: ChatSettingsState? = null,
        val reasoningPicker: ReasoningPickerState? = null,
        val reasoningNotice: String? = null,
        val laddersByService: Map<String, List<String>> = emptyMap(),
    ) : ThreadUiState {

        val ladder: List<String>
            get() = laddersByService[conversation.modelRef.wireValue].orEmpty()

        val reasoningStale: Boolean
            get() = isReasoningLevelStale(ladder, conversation.reasoningLevel)

        val reasoningControlVisible: Boolean
            get() = showsReasoningControl(ladder, conversation.reasoningLevel)


        val runActive: Boolean
            get() = sending ||
                thread.streaming?.unconfirmed == false ||
                conversation.isGenerating

        val canSend: Boolean
            get() = !runActive && (composer.isNotBlank() || attachments.isNotEmpty())

        val canSwitchModel: Boolean
            get() = !runActive

        val canToggleTools: Boolean
            get() = !runActive

        val runError: String?
            get() = conversation.lastRun?.takeIf { it.hasFailed }?.error
    }
}
