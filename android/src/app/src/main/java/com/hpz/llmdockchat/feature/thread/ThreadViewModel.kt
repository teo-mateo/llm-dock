package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ArtifactRecord
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.ParseWarning
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.data.model.wireValue
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class ThreadViewModel(
    private val conversationId: String,
    private val repository: ChatRepository,
    private val drafts: DraftStore,
    private val attachmentStore: SharedDraftStore? = null,
    private val servicesStreamRepository: ServicesStreamRepository,
    private val servicesRepository: ServicesRepository,
    private val openRouterModelsRepository: OpenRouterModelsRepository,
    private val conversationsRepository: ConversationsRepository,
    private val mcpServersRepository: McpServersRepository,
    private val promptsRepository: PromptsRepository,
    private val coalesceWindowMs: Long = DEFAULT_COALESCE_WINDOW_MS,
    private val reconnectInitialMs: Long = ReconnectBackoff.DEFAULT_INITIAL_MS,
    private val reconnectMaxMs: Long = ReconnectBackoff.DEFAULT_MAX_MS,
) : ViewModel() {

    private val _state = MutableStateFlow<ThreadUiState>(ThreadUiState.Loading)
    val state: StateFlow<ThreadUiState> = _state.asStateFlow()

    private var streamJob: Job? = null

    private var modelPickerJob: Job? = null

    private val toolsWriteLock = Mutex()

    private var latestToolsToggle = 0L

    private val levelWriteLock = Mutex()
    private var latestLevelWrite = 0L

    private var ladders: Map<String, List<String>> = emptyMap()

    private var remoteLadders: Map<String, List<String>> = emptyMap()

    private val mergedLadders: Map<String, List<String>>
        get() = ladders + remoteLadders

    private var composerBeforeEdit: String = ""
    private var attachmentsBeforeEdit: List<String> = emptyList()

    fun load() {
        viewModelScope.launch {
            val draft = drafts.draft(conversationId)
            val staged = attachmentStore?.attachments(conversationId).orEmpty()
            repository.load(conversationId).fold(
                onSuccess = { conversation ->
                    _state.value = loadedFrom(conversation, draft, staged)
                    reattachIfRunning(conversation)
                },
                onFailure = { failure ->
                    val current = _state.value
                    if (current is ThreadUiState.Loaded) {
                        _state.value = current.copy(actionError = failure.appError.displayMessage)
                    } else {
                        _state.value = ThreadUiState.Failed(failure.appError.displayMessage)
                    }
                },
            )
            refreshLadders()
        }
    }

    private fun loadedFrom(
        conversation: ConversationDetail,
        draft: String,
        staged: List<String> = emptyList(),
    ): ThreadUiState.Loaded {
        val current = _state.value as? ThreadUiState.Loaded
        return ThreadUiState.Loaded(
            conversation = conversation,
            thread = ThreadState(
                messages = conversation.messages,
                streaming = current?.thread?.streaming?.takeUnless { it.unconfirmed },
            ),
            composer = current?.composer ?: draft,
            attachments = (current?.attachments.orEmpty() + staged).distinct(),
            sending = current?.sending ?: false,
            actionError = current?.actionError,
            laddersByService = mergedLadders,
        )
    }


    private suspend fun refreshLadders() {
        servicesRepository.list().getOrNull()?.let(::updateLadders)
        if (loaded()?.conversation?.modelRef is ModelRef.OpenRouter) {
            openRouterModelsRepository.list().getOrNull()?.let { updateRemoteLadders(it.models) }
        }
    }

    private fun updateLadders(services: List<ServiceSummary>) {
        ladders = services.associate { it.name to it.reasoningLevels }
        publishLadders()
    }

    private fun updateRemoteLadders(models: List<ModelOption.Remote>) {
        remoteLadders = models.associate { it.ref.wireValue to it.reasoningLevels }
        publishLadders()
    }

    private fun publishLadders() {
        loaded()?.let { _state.value = it.copy(laddersByService = mergedLadders) }
    }

    fun openReasoningPicker() {
        val current = loaded() ?: return
        if (!current.canSwitchModel) return
        _state.value = current.copy(reasoningPicker = ReasoningPickerState())
        viewModelScope.launch { refreshLadders() }
    }

    fun closeReasoningPicker() {
        loaded()?.let { _state.value = it.copy(reasoningPicker = null) }
    }

    fun selectReasoningLevel(level: String?) {
        val current = loaded() ?: return
        if (!current.canSwitchModel) return
        if (current.conversation.reasoningLevel == level) {
            closeReasoningPicker()
            return
        }
        val previous = current.conversation.reasoningLevel
        _state.value = current.copy(
            conversation = current.conversation.copy(reasoningLevel = level),
            reasoningPicker = ReasoningPickerState(writePending = true),
        )
        val write = ++latestLevelWrite
        viewModelScope.launch {
            levelWriteLock.withLock {
                conversationsRepository.setReasoningLevel(conversationId, level).fold(
                    onSuccess = { closeReasoningPicker() },
                    onFailure = { failure ->
                        if (write != latestLevelWrite) return@fold
                        val latest = loaded() ?: return@fold
                        _state.value = latest.copy(
                            conversation = latest.conversation.copy(reasoningLevel = previous),
                            reasoningPicker = latest.reasoningPicker?.let { ReasoningPickerState() },
                            actionError = failure.appError.displayMessage,
                        )
                    },
                )
            }
        }
    }

    private fun reattachIfRunning(conversation: ConversationDetail) {
        if (!conversation.isGenerating) return
        val run = conversation.activeRun ?: return
        if (streamJob?.isActive == true) return
        val current = loaded() ?: return

        _state.value = current.copy(
            thread = current.thread.copy(
                streaming = current.thread.streaming
                    ?: StreamingTurn(userMessage = null, runId = run.id, reattached = true),
            ),
        )
        collectRun(
            first = repository.reattach(run.id),
            restoreOnEarlyFailure = null,
            initialRunId = run.id,
            reattach = true,
        )
    }

    fun onComposerChange(text: String) {
        val current = loaded() ?: return
        _state.value = current.copy(composer = text)
        drafts.save(conversationId, text)
    }

    fun dismissActionError() {
        loaded()?.let { _state.value = it.copy(actionError = null) }
    }

    fun send() {
        val current = loaded() ?: return
        if (!current.canSend) return

        val pending = PendingUserMessage(current.composer.trim(), current.attachments)
        _state.value = current.copy(
            composer = "",
            attachments = emptyList(),
            sending = true,
            actionError = null,
            reasoningNotice = null,
            thread = current.thread.copy(streaming = StreamingTurn(userMessage = pending)),
        )
        drafts.clear(conversationId)
        attachmentStore?.clear(conversationId)

        collectRun(
            first = repository.send(conversationId, pending.content, pending.images),
            restoreOnEarlyFailure = pending,
        )
    }

    fun stop() {
        val current = loaded() ?: return
        val turn = current.thread.streaming?.takeUnless { it.unconfirmed }
        val runId = turn?.runId ?: current.conversation.activeRun?.id
        if (turn == null && runId == null) return
        if (turn != null) {
            _state.value = current.copy(thread = current.thread.copy(streaming = turn.copy(stopping = true)))
        }
        viewModelScope.launch {
            repository.cancelActiveRun(conversationId, runId).fold(
                onSuccess = { if (turn == null) reloadConversation() },
                onFailure = { failure ->
                    loaded()?.let { _state.value = it.copy(actionError = failure.appError.displayMessage) }
                },
            )
        }
    }

    private suspend fun reloadConversation() {
        val conversation = repository.load(conversationId).getOrNull() ?: return
        val current = loaded() ?: return
        _state.value = current.copy(
            conversation = conversation,
            thread = current.thread.copy(
                messages = conversation.messages,
                streaming = current.thread.streaming?.takeUnless { it.unconfirmed },
            ),
        )
    }

    fun addAttachment(dataUrl: String) {
        val current = loaded() ?: return
        _state.value = current.copy(attachments = current.attachments + dataUrl)
    }

    fun removeAttachment(index: Int) {
        val current = loaded() ?: return
        if (index !in current.attachments.indices) return
        _state.value = current.copy(attachments = current.attachments.filterIndexed { i, _ -> i != index })
        attachmentStore?.removeAttachment(conversationId, index)
    }

    fun leaveThread() {
        attachmentStore?.clear(conversationId)
    }

    fun reportAttachmentFailure(message: String) {
        loaded()?.let { _state.value = it.copy(actionError = message) }
    }


    fun openModelPicker() {
        val current = loaded() ?: return
        if (current.runActive) return
        _state.value = current.copy(settings = null, modelPicker = ModelPickerState())
        modelPickerJob?.cancel()
        modelPickerJob = viewModelScope.launch {
            val openRouter = openRouterModelsRepository.list().getOrNull()
            openRouter?.let { updateRemoteLadders(it.models) }
            loaded()?.let {
                _state.value = it.copy(
                    modelPicker = it.modelPicker?.copy(
                        remoteModels = openRouter?.models.orEmpty(),
                        remoteModelsConfigured = openRouter?.configured ?: false,
                    ),
                )
            }
            servicesStreamRepository.stream().collect { services ->
                updateLadders(services)
                loaded()?.let {
                    _state.value = it.copy(modelPicker = it.modelPicker?.copy(services = services))
                }
            }
        }
    }

    fun closeModelPicker() {
        modelPickerJob?.cancel()
        modelPickerJob = null
        loaded()?.let { _state.value = it.copy(modelPicker = null) }
    }

    fun switchModel(ref: ModelRef) {
        val current = loaded() ?: return
        if (current.runActive) return
        viewModelScope.launch {
            repository.updateMainService(conversationId, ref.wireValue).fold(
                onSuccess = {
                    closeModelPicker()
                    reloadConversation()
                },
                onFailure = { failure ->
                    loaded()?.let { _state.value = it.copy(actionError = failure.appError.displayMessage) }
                },
            )
        }
    }


    fun openSettings() {
        val current = loaded() ?: return
        _state.value = current.copy(settings = ChatSettingsState())
        viewModelScope.launch {
            val servers = mcpServersRepository.list().getOrNull().orEmpty()
            loaded()?.settings?.let { open ->
                _state.value = loaded()!!.copy(settings = open.copy(servers = servers))
            }
        }
        viewModelScope.launch {
            val prompts = promptsRepository.list().getOrNull().orEmpty().sortedBy { it.sortOrder }
            loaded()?.settings?.let { open ->
                _state.value = loaded()!!.copy(settings = open.copy(prompts = prompts))
            }
        }
    }

    fun closeSettings() {
        loaded()?.let { _state.value = it.copy(settings = null) }
    }

    fun selectPrompt(promptId: String?) {
        val current = loaded() ?: return
        if (!current.canToggleTools) return
        if (current.conversation.promptId == promptId) return
        val previous = current.conversation.promptId
        _state.value = current.copy(
            conversation = current.conversation.copy(promptId = promptId),
        )
        viewModelScope.launch {
            conversationsRepository.setPrompt(conversationId, promptId).fold(
                onSuccess = {},
                onFailure = { failure ->
                    val latest = loaded() ?: return@fold
                    _state.value = latest.copy(
                        conversation = latest.conversation.copy(promptId = previous),
                        actionError = failure.appError.displayMessage,
                    )
                },
            )
        }
    }

    fun toggleTool(serverId: String) {
        val current = loaded() ?: return
        if (!current.canToggleTools) return
        val previous = current.conversation.mcpServers
        val next = if (serverId in previous) previous - serverId else previous + serverId
        _state.value = current.copy(conversation = current.conversation.copy(mcpServers = next))

        val toggle = ++latestToolsToggle
        viewModelScope.launch {
            toolsWriteLock.withLock {
                conversationsRepository.setMcpServers(conversationId, next).fold(
                    onSuccess = {},
                    onFailure = { failure ->
                        if (toggle != latestToolsToggle) return@fold
                        val latest = loaded() ?: return@fold
                        _state.value = latest.copy(
                            conversation = latest.conversation.copy(mcpServers = previous),
                            actionError = failure.appError.displayMessage,
                        )
                    },
                )
            }
        }
    }


    fun requestDelete(message: ChatMessage) {
        val current = loaded() ?: return
        if (current.runActive) return
        _state.value = current.copy(pendingDelete = message)
    }

    fun cancelDelete() {
        loaded()?.let { _state.value = it.copy(pendingDelete = null) }
    }

    fun confirmDelete() {
        val current = loaded() ?: return
        val target = current.pendingDelete ?: return
        _state.value = current.copy(pendingDelete = null)
        viewModelScope.launch {
            repository.deleteMessage(conversationId, target.id).fold(
                onSuccess = { reloadConversation() },
                onFailure = { failure ->
                    loaded()?.let { _state.value = it.copy(actionError = failure.appError.displayMessage) }
                },
            )
        }
    }


    fun beginEdit(message: ChatMessage) {
        if (message.role != MessageRole.USER) return
        val current = loaded() ?: return
        if (current.runActive) return
        composerBeforeEdit = current.composer
        attachmentsBeforeEdit = current.attachments
        _state.value = current.copy(
            editingMessage = message,
            composer = message.content,
            attachments = message.images,
            pendingEdit = null,
            actionError = null,
        )
    }

    fun cancelEdit() {
        val current = loaded() ?: return
        if (current.editingMessage == null) return
        _state.value = current.copy(
            editingMessage = null,
            pendingEdit = null,
            composer = composerBeforeEdit,
            attachments = attachmentsBeforeEdit,
        )
        drafts.save(conversationId, composerBeforeEdit)
    }

    fun requestEditConfirm() {
        val current = loaded() ?: return
        val target = current.editingMessage ?: return
        if (current.composer.isBlank() && current.attachments.isEmpty()) return
        _state.value = current.copy(
            pendingEdit = PendingEdit(
                message = target,
                content = current.composer.trim(),
                images = current.attachments,
                discardCount = current.thread.messages.count { it.seq > target.seq },
            ),
        )
    }

    fun cancelEditConfirm() {
        loaded()?.let { _state.value = it.copy(pendingEdit = null) }
    }

    fun confirmEdit() {
        val current = loaded() ?: return
        val edit = current.pendingEdit ?: return
        val pending = PendingUserMessage(edit.content, edit.images)
        val messagesBeforeEdit = current.thread.messages
        _state.value = current.copy(
            pendingEdit = null,
            editingMessage = null,
            composer = "",
            attachments = emptyList(),
            sending = true,
            actionError = null,
            reasoningNotice = null,
            thread = ThreadState(
                messages = messagesBeforeEdit.filter { it.seq < edit.message.seq },
                streaming = StreamingTurn(userMessage = pending),
            ),
        )
        drafts.clear(conversationId)

        collectRun(
            first = repository.editAndResend(conversationId, edit.message.id, pending.content, pending.images),
            restoreOnEarlyFailure = pending,
            messagesBeforeEdit = messagesBeforeEdit,
        )
    }


    private fun collectRun(
        first: Flow<RunEvent>,
        restoreOnEarlyFailure: PendingUserMessage?,
        messagesBeforeEdit: List<ChatMessage>? = null,
        initialRunId: String? = null,
        reattach: Boolean = false,
    ) {
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            var source: Flow<RunEvent> = first
            var runId: String? = initialRunId
            var failureMessage: String? = null
            var sawAnyFrame = false
            var error: Throwable?
            val backoff = ReconnectBackoff(reconnectInitialMs, reconnectMaxMs)

            while (true) {
                val attempt = collectAttempt(source, runId)
                runId = attempt.runId ?: runId
                failureMessage = attempt.failureMessage ?: failureMessage
                sawAnyFrame = sawAnyFrame || attempt.sawAnyFrame
                error = attempt.error

                val id = runId
                if (error == null || id == null || error.appError !is AppError.Network) break

                if (attempt.sawAnyFrame) backoff.reset()
                setReconnecting(true)
                delay(backoff.next())
                source = repository.reattach(id)
            }

            finishRun(
                error = error,
                sawAnyFrame = sawAnyFrame,
                failureMessage = failureMessage,
                restoreOnEarlyFailure = restoreOnEarlyFailure,
                messagesBeforeEdit = messagesBeforeEdit,
                reattach = reattach,
            )
        }
    }

    private suspend fun CoroutineScope.collectAttempt(
        source: Flow<RunEvent>,
        knownRunId: String?,
    ): RunAttempt {
        val accumulator = TurnAccumulator(loaded()?.thread?.streaming?.userMessage, knownRunId)
        var failureMessage: String? = null

        var pendingFlush: Job? = null
        val scheduleFlush = {
            if (pendingFlush?.isActive != true) {
                pendingFlush = launch {
                    delay(coalesceWindowMs)
                    if (accumulator.takeDirty()) publishTurn(accumulator)
                }
            }
        }

        val error: Throwable? = try {
            source.collect { event ->
                if (!accumulator.sawAnyFrame) setReconnecting(false)
                accumulator.sawFrame()
                when (event) {
                    is RunEvent.Delta -> {
                        accumulator.append(event)
                        scheduleFlush()
                    }
                    is RunEvent.Failed -> failureMessage = event.message
                    is RunEvent.RunStarted -> {
                        event.reasoningLevelNote?.let { note ->
                            loaded()?.let { _state.value = it.copy(reasoningNotice = note) }
                        }
                        accumulator.apply(event)
                        publishTurn(accumulator)
                    }
                    is RunEvent.RunStatus -> {
                        if (event.status == "failed") failureMessage = event.error ?: failureMessage
                    }
                    is RunEvent.ConversationUpdated -> applyTitle(event.title)
                    RunEvent.Done, is RunEvent.MessageSaved, is RunEvent.Heartbeat -> Unit
                    is RunEvent.Unknown -> Unit
                    else -> {
                        accumulator.apply(event)
                        publishTurn(accumulator)
                    }
                }
            }
            null
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            e
        } finally {
            pendingFlush?.cancel()
        }

        if (accumulator.takeDirty()) publishTurn(accumulator)

        return RunAttempt(
            error = error,
            runId = accumulator.runId,
            failureMessage = failureMessage,
            sawAnyFrame = accumulator.sawAnyFrame,
        )
    }

    private fun setReconnecting(value: Boolean) {
        val current = loaded() ?: return
        val turn = current.thread.streaming ?: return
        if (turn.reconnecting == value) return
        _state.value = current.copy(thread = current.thread.copy(streaming = turn.copy(reconnecting = value)))
    }

    private suspend fun finishRun(
        error: Throwable?,
        sawAnyFrame: Boolean,
        failureMessage: String?,
        restoreOnEarlyFailure: PendingUserMessage?,
        messagesBeforeEdit: List<ChatMessage>? = null,
        reattach: Boolean = false,
    ) {
        val current = loaded()

        if (error != null && !sawAnyFrame && !reattach) {
            val restored = restoreOnEarlyFailure?.content.orEmpty()
            val loadedCurrent = current ?: return
            val messages = if (messagesBeforeEdit != null) {
                repository.load(conversationId).getOrNull()?.messages ?: messagesBeforeEdit
            } else {
                loadedCurrent.thread.messages
            }
            _state.value = loadedCurrent.copy(
                sending = false,
                thread = loadedCurrent.thread.copy(streaming = null, messages = messages),
                composer = loadedCurrent.composer.ifBlank { restored },
                attachments = loadedCurrent.attachments.ifEmpty { restoreOnEarlyFailure?.images.orEmpty() },
                actionError = error.appError.displayMessage,
            )
            if (loadedCurrent.composer.isBlank() && restored.isNotBlank()) drafts.save(conversationId, restored)
            return
        }

        val refetch = repository.load(conversationId)
        val refetched = refetch.getOrNull()
        val latest = loaded() ?: return

        if (refetched == null) {
            _state.value = latest.copy(
                sending = false,
                thread = latest.thread.copy(
                    streaming = latest.thread.streaming
                        ?.takeIf { it.hasVisibleOutput || it.userMessage != null }
                        ?.copy(
                            unconfirmed = true,
                            stopping = false,
                            reconnecting = false,
                            error = failureMessage,
                        ),
                ),
                actionError = failureMessage
                    ?: error?.appError?.displayMessage
                    ?: refetch.exceptionOrNull()?.appError?.displayMessage,
            )
            return
        }

        _state.value = latest.copy(
            sending = false,
            conversation = refetched,
            thread = ThreadState(messages = refetched.messages, streaming = null),
            actionError = if (failureMessage == null) error?.appError?.displayMessage else null,
        )
    }

    private fun applyTitle(title: String) {
        if (title.isBlank()) return
        val current = loaded() ?: return
        _state.value = current.copy(conversation = current.conversation.copy(title = title))
    }

    private fun publishTurn(accumulator: TurnAccumulator) {
        val current = loaded() ?: return
        val existing = current.thread.streaming
        _state.value = current.copy(
            sending = false,
            thread = current.thread.copy(
                streaming = accumulator.snapshot(
                    stopping = existing?.stopping == true,
                    reconnecting = existing?.reconnecting == true,
                    reattached = existing?.reattached == true,
                ),
            ),
        )
    }

    private fun loaded(): ThreadUiState.Loaded? = _state.value as? ThreadUiState.Loaded

    companion object {
        const val DEFAULT_COALESCE_WINDOW_MS = 24L
    }
}

private class RunAttempt(
    val error: Throwable?,
    val runId: String?,
    val failureMessage: String?,
    val sawAnyFrame: Boolean,
)

private class TurnAccumulator(
    private val userMessage: PendingUserMessage?,
    seedRunId: String? = null,
) {
    private val content = StringBuilder()
    private val reasoning = StringBuilder()
    private val toolCalls = mutableListOf<StreamingToolCall>()
    private val artifacts = mutableListOf<ArtifactRecord>()
    private var parseWarning: ParseWarning? = null
    private var dirty = false

    var runId: String? = seedRunId
        private set

    var sawAnyFrame = false
        private set

    fun sawFrame() {
        sawAnyFrame = true
    }

    fun markDirty() {
        dirty = true
    }

    fun takeDirty(): Boolean = dirty.also { dirty = false }

    fun append(delta: RunEvent.Delta) {
        content.append(delta.content)
        reasoning.append(delta.reasoning)
        markDirty()
    }

    fun apply(event: RunEvent) {
        markDirty()
        when (event) {
            is RunEvent.RunStarted -> runId = event.runId
            is RunEvent.ToolCallPending -> toolCalls += StreamingToolCall(
                name = event.name.substringAfter(TOOL_NAMESPACE, event.name),
                serverId = event.name.substringBefore(TOOL_NAMESPACE).takeIf { TOOL_NAMESPACE in event.name },
            )
            is RunEvent.ToolCall -> upsertCall(event)
            is RunEvent.ToolResult -> completeCall(event)
            is RunEvent.ParseWarning ->
                parseWarning = ParseWarning(event.kind, event.description, event.snippet)
            is RunEvent.Artifact ->
                artifacts += ArtifactRecord(event.artifactType, event.title, event.content, language = null)
            else -> Unit
        }
    }

    private fun upsertCall(event: RunEvent.ToolCall) {
        val slot = toolCalls.indexOfFirst { it.name == event.name && it.arguments == null }
        val filled = StreamingToolCall(event.name, event.serverId, event.arguments, null)
        if (slot >= 0) toolCalls[slot] = filled else toolCalls += filled
    }

    private fun completeCall(event: RunEvent.ToolResult) {
        val slot = toolCalls.indexOfLast { it.name == event.name && it.result == null }
        if (slot >= 0) {
            toolCalls[slot] = toolCalls[slot].copy(result = event.result, arguments = toolCalls[slot].arguments)
        } else {
            toolCalls += StreamingToolCall(event.name, event.serverId, null, event.result)
        }
    }

    fun snapshot(stopping: Boolean, reconnecting: Boolean = false, reattached: Boolean = false) = StreamingTurn(
        userMessage = userMessage,
        runId = runId,
        content = content.toString(),
        reasoning = reasoning.toString(),
        toolCalls = toolCalls.toList(),
        parseWarning = parseWarning,
        artifacts = artifacts.toList(),
        stopping = stopping,
        reconnecting = reconnecting,
        reattached = reattached,
    )

    private companion object {
        const val TOOL_NAMESPACE = "__"
    }
}
