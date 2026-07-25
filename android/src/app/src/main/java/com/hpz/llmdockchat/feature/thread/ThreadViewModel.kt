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
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ArtifactRecord
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.ParseWarning
import com.hpz.llmdockchat.data.model.wireValue
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

/**
 * One thread: load it, send a turn, render the stream, stop it (F04).
 *
 * Collection is screen-scoped (Architecture D5). Leaving the thread clears the
 * ViewModel, which cancels [streamJob], which cancels the HTTP call — and
 * **nothing else**. No cancel request is sent; the server finishes the run and
 * persists the reply (F04-R10).
 */
class ThreadViewModel(
    private val conversationId: String,
    private val repository: ChatRepository,
    private val drafts: DraftStore,
    private val servicesStreamRepository: ServicesStreamRepository,
    private val openRouterModelsRepository: OpenRouterModelsRepository,
    private val conversationsRepository: ConversationsRepository,
    private val mcpServersRepository: McpServersRepository,
    private val coalesceWindowMs: Long = DEFAULT_COALESCE_WINDOW_MS,
    private val titleSettleDelayMs: Long = DEFAULT_TITLE_SETTLE_DELAY_MS,
    private val reconnectInitialMs: Long = ReconnectBackoff.DEFAULT_INITIAL_MS,
    private val reconnectMaxMs: Long = ReconnectBackoff.DEFAULT_MAX_MS,
) : ViewModel() {

    private val _state = MutableStateFlow<ThreadUiState>(ThreadUiState.Loading)
    val state: StateFlow<ThreadUiState> = _state.asStateFlow()

    private var streamJob: Job? = null

    /** The model picker's own live subscription — separate from [streamJob], which is the chat run's. */
    private var modelPickerJob: Job? = null

    /**
     * Serialises the tools writes (F08-R2). Every toggle PUTs the **whole**
     * server-id array, so two writes in flight at once is a lost-update race:
     * the earlier one can reach the server last and leave it holding a list
     * the sheet no longer shows. Cancelling the earlier coroutine does not
     * help — `ApiClient` runs a blocking call, and a request already handed
     * to the server cannot be recalled — so the writes are ordered instead.
     * The last one queued is the last one sent, and it carries the newest
     * selection, so the server deterministically ends up agreeing with the UI.
     */
    private val toolsWriteLock = Mutex()

    /**
     * Which toggle is the newest, so a *stale* write's failure is not acted
     * on: a later write carries the whole array and will establish the right
     * state on its own, and reverting to a superseded selection would fight
     * it. Only the most recent toggle's own outcome reverts the sheet.
     */
    private var latestToolsToggle = 0L

    /** What the composer held before [beginEdit] overwrote it, restored by [cancelEdit]. */
    private var composerBeforeEdit: String = ""
    private var attachmentsBeforeEdit: List<String> = emptyList()

    fun load() {
        viewModelScope.launch {
            val draft = drafts.draft(conversationId)
            repository.load(conversationId).fold(
                onSuccess = { conversation ->
                    _state.value = loadedFrom(conversation, draft)
                    reattachIfRunning(conversation)
                },
                onFailure = { failure ->
                    // A reload that fails mid-thread must not throw away a
                    // thread already on screen; only a cold load goes to Failed.
                    val current = _state.value
                    if (current is ThreadUiState.Loaded) {
                        _state.value = current.copy(actionError = failure.appError.displayMessage)
                    } else {
                        _state.value = ThreadUiState.Failed(failure.appError.displayMessage)
                    }
                },
            )
        }
    }

    private fun loadedFrom(conversation: ConversationDetail, draft: String): ThreadUiState.Loaded {
        val current = _state.value as? ThreadUiState.Loaded
        return ThreadUiState.Loaded(
            conversation = conversation,
            thread = ThreadState(
                messages = conversation.messages,
                // A turn held over from a refetch that failed is superseded the
                // moment a load succeeds; keeping it would show it twice.
                streaming = current?.thread?.streaming?.takeUnless { it.unconfirmed },
            ),
            composer = current?.composer ?: draft,
            attachments = current?.attachments.orEmpty(),
            sending = current?.sending ?: false,
            actionError = current?.actionError,
        )
    }

    /**
     * F09-R1/R2 — the thread was opened on a run that is already going: started
     * here and left behind, or started on the desktop. Two things happen, in
     * this order and for two different reasons.
     *
     * The turn is put on screen **first**, empty. `active_run` is enough to know
     * the thread is generating, and the criterion is that it reads that way
     * *before any stream data arrives* — the alternative, waiting for the first
     * replayed frame, shows an idle thread with a live composer for as long as
     * the subscribe takes, and invites a send that would earn a 409.
     *
     * Then the reader is pointed at `GET /api/chat/runs/<id>/stream`, which is
     * the same reader the send path uses (Architecture D2) because it is the
     * same frames. The replay it opens with rebuilds the turn from nothing, so
     * there is no dedup step anywhere — see [collectAttempt].
     */
    private fun reattachIfRunning(conversation: ConversationDetail) {
        if (!conversation.isGenerating) return
        val run = conversation.activeRun ?: return
        // Already streaming — either this client's own send, or a reattach from
        // an earlier load(). A second subscription would be a second replay.
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
            titleBefore = conversation.title,
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
            thread = current.thread.copy(streaming = StreamingTurn(userMessage = pending)),
        )
        drafts.clear(conversationId)

        collectRun(
            first = repository.send(conversationId, pending.content, pending.images),
            restoreOnEarlyFailure = pending,
            titleBefore = current.conversation.title,
        )
    }

    /**
     * Cancel by conversation with the run id as a guard (F04-R6). The server
     * cancels cooperatively, so generation stops at the next stream event
     * rather than instantly, and the run emits **no terminal frame** — the
     * stream simply ends, which [collectRun] treats as a cancel.
     */
    fun stop() {
        val current = loaded() ?: return
        // A turn held over from a failed refetch belongs to a run that already
        // ended; there is nothing of ours left to stop.
        val turn = current.thread.streaming?.takeUnless { it.unconfirmed }
        // A run this client is not streaming is still stoppable — one started
        // on the desktop, or left running here and returned to. The server
        // finds it from the conversation; the id, when known, is only a guard.
        val runId = turn?.runId ?: current.conversation.activeRun?.id
        if (turn == null && runId == null) return
        if (turn != null) {
            _state.value = current.copy(thread = current.thread.copy(streaming = turn.copy(stopping = true)))
        }
        viewModelScope.launch {
            repository.cancelActiveRun(conversationId, runId).fold(
                // With no local stream there is no terminal to react to, so the
                // refetch that clears the thread's "generating" state has to be
                // issued here.
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
    }

    fun reportAttachmentFailure(message: String) {
        loaded()?.let { _state.value = it.copy(actionError = message) }
    }

    // -- switch model (F07-R4) --------------------------------------------------

    /**
     * Opens the sheet and starts its own live services subscription — separate
     * from [streamJob] (the chat run's), and unlike [NewChatViewModel]'s, not
     * kept open for the whole time the screen is: a thread stays open far
     * longer than a new-chat sheet does, so the SSE connection is scoped to the
     * sheet being visible, cancelled the moment it closes ([closeModelPicker]).
     */
    fun openModelPicker() {
        val current = loaded() ?: return
        if (current.runActive) return
        // Settings is where this is reached from; dismiss it rather than stack
        // one modal sheet on top of another.
        _state.value = current.copy(settings = null, modelPicker = ModelPickerState())
        modelPickerJob?.cancel()
        modelPickerJob = viewModelScope.launch {
            val openRouter = openRouterModelsRepository.list().getOrNull()
            loaded()?.let {
                _state.value = it.copy(
                    modelPicker = it.modelPicker?.copy(
                        remoteModels = openRouter?.models.orEmpty(),
                        remoteModelsConfigured = openRouter?.configured ?: false,
                    ),
                )
            }
            servicesStreamRepository.stream().collect { services ->
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

    /**
     * `PUT /api/chat/conversations/<id>` with the new `main_service`. Earlier
     * messages are untouched server-side — each already carries its own
     * `model_service` — only the next turn is affected. The reload afterwards
     * is what updates the thread header (F07-R4's first criterion).
     */
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

    // -- tools for this chat (F08) ----------------------------------------------

    /**
     * Opens the chat-settings sheet and fetches the registry once (unlike
     * [openModelPicker], no live subscription — see [ChatSettingsState]'s doc
     * for why a one-shot fetch already satisfies F08-R1's "no app update
     * needed" criterion).
     *
     * Unguarded, unlike [openModelPicker]: the sheet also carries the text-size
     * control, which is unrelated to any run. F08-R4's guarantee is enforced
     * where it actually matters — [toggleTool] refuses during a run, and the
     * rows render disabled — rather than by hiding the whole sheet.
     */
    fun openSettings() {
        val current = loaded() ?: return
        _state.value = current.copy(settings = ChatSettingsState())
        viewModelScope.launch {
            val servers = mcpServersRepository.list().getOrNull().orEmpty()
            val stillOpen = loaded() ?: return@launch
            if (stillOpen.settings != null) {
                _state.value = stillOpen.copy(settings = ChatSettingsState(servers = servers))
            }
        }
    }

    fun closeSettings() {
        loaded()?.let { _state.value = it.copy(settings = null) }
    }

    /**
     * `PUT /api/chat/conversations/<id>` with `mcp_servers_json` (F08-R2) —
     * the same call [com.hpz.llmdockchat.feature.newchat.NewChatViewModel]
     * uses for a brand-new thread, reused here for an existing one.
     *
     * Applied optimistically — the switch in the sheet must flip the instant
     * it's tapped, not after a round trip — and rolled back to exactly what
     * it was before this toggle if the write fails, so the UI never claims a
     * state the server doesn't have (F08-R2's fourth criterion). No refetch
     * on success: the writes are ordered by [toolsWriteLock], so the array
     * this client wrote last is already what the server has — a refetch
     * would cost a round trip to learn what it just told the server.
     */
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

    // -- delete (F06-R2) -------------------------------------------------------

    /** Opens the confirm. The menu itself hides Delete while a run is active; this is the second guard. */
    fun requestDelete(message: ChatMessage) {
        val current = loaded() ?: return
        if (current.runActive) return
        _state.value = current.copy(pendingDelete = message)
    }

    /** No request — the confirm's whole point is that cancelling touches nothing. */
    fun cancelDelete() {
        loaded()?.let { _state.value = it.copy(pendingDelete = null) }
    }

    /**
     * The message is **not** removed optimistically — only a refetch after a
     * confirmed 200 does that (F06-R2's second criterion: a 409 must show the
     * server's message, not a row that quietly vanished and came back).
     */
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

    // -- edit and resend (F06-R3) ----------------------------------------------

    /**
     * The menu hides this action on an assistant message; this is the second
     * guard (the server would 400 it anyway — F06-R3's fourth criterion).
     */
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

    /** Leaves edit mode and restores whatever was in the composer before it started. No request. */
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

    /**
     * Send, while editing, opens the confirm instead of sending. [discardCount]
     * is computed from what this client already has loaded — verified against
     * the server's own truncation in `ThreadEditAndResendTest`.
     */
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

    /** Stays in edit mode; only the confirm closes. No request. */
    fun cancelEditConfirm() {
        loaded()?.let { _state.value = it.copy(pendingEdit = null) }
    }

    /**
     * `PUT …/messages/<id>` truncates from [PendingEdit.message]'s position on
     * the server *before* the run even starts, so the local copy is truncated
     * here too rather than left to show stale turns under the new answer for
     * the length of the stream. If the request is rejected before any frame
     * arrives — a 409, someone else started a run in between — [finishRun]
     * refetches to undo this rather than trust the rollback to be correct on
     * its own (F06-R3's last criterion).
     */
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
            thread = ThreadState(
                messages = messagesBeforeEdit.filter { it.seq < edit.message.seq },
                streaming = StreamingTurn(userMessage = pending),
            ),
        )
        drafts.clear(conversationId)

        collectRun(
            first = repository.editAndResend(conversationId, edit.message.id, pending.content, pending.images),
            restoreOnEarlyFailure = pending,
            titleBefore = current.conversation.title,
            messagesBeforeEdit = messagesBeforeEdit,
        )
    }

    // -- the stream ----------------------------------------------------------

    /**
     * One run, however many connections it takes (F04 + F09-R4).
     *
     * [first] is the stream the run arrived on — a send's POST, an edit's PUT,
     * or a reattach's GET. If the *connection* breaks while the run is still
     * going, the run itself is untouched: it is executing on a worker thread on
     * the dashboard and will persist its reply whether anyone is listening or
     * not. So a broken connection is retried, and **always** by reattaching.
     * Re-issuing the POST would create a second run and a second copy of the
     * user's message, which is the one failure mode here that damages the
     * thread rather than the screen.
     *
     * A stream that *ends* is not retried. There is no frame that distinguishes
     * a cancelled run from any other clean close — `_sse_frames_for` maps
     * `run_cancelled` to nothing at all — so "the server closed it" is the
     * signal that the run is over, and what actually happened comes from the
     * refetch in [finishRun] (Architecture D3).
     */
    private fun collectRun(
        first: Flow<RunEvent>,
        restoreOnEarlyFailure: PendingUserMessage?,
        titleBefore: String,
        messagesBeforeEdit: List<ChatMessage>? = null,
        initialRunId: String? = null,
        reattach: Boolean = false,
    ) {
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            var source: Flow<RunEvent> = first
            var runId: String? = initialRunId
            var titleFrameSeen = false
            var failureMessage: String? = null
            var sawAnyFrame = false
            var error: Throwable?
            val backoff = ReconnectBackoff(reconnectInitialMs, reconnectMaxMs)

            while (true) {
                val attempt = collectAttempt(source, runId)
                runId = attempt.runId ?: runId
                titleFrameSeen = titleFrameSeen || attempt.titleFrameSeen
                failureMessage = attempt.failureMessage ?: failureMessage
                sawAnyFrame = sawAnyFrame || attempt.sawAnyFrame
                error = attempt.error

                val id = runId
                if (error == null || id == null || error.appError !is AppError.Network) break

                // Only a *failed* attempt earns a longer wait. One that
                // connected and then dropped starts the schedule over, so a
                // flaky link is not punished with the delay a previous outage
                // worked its way up to.
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
                expectTitle = !titleFrameSeen && titleBefore == UNTITLED,
                messagesBeforeEdit = messagesBeforeEdit,
                reattach = reattach,
            )
        }
    }

    /**
     * One connection's worth of frames.
     *
     * The accumulator is built here, per attempt, and that is the whole of
     * F09-R2's no-duplication rule. `GET /api/chat/runs/<id>/stream` replays the
     * run **from its first token every time it is subscribed to** — verified
     * against the dashboard: two consecutive reattaches to one run returned
     * 8,168 and 12,304 characters, the second containing the first in full. An
     * accumulator carried across attempts would therefore append the replay to
     * text it already had. Rebuilding instead is Architecture D3's reattach
     * corollary: the client holds no authoritative copy, so replay is
     * idempotent and there is no dedup logic anywhere.
     *
     * Nothing is blanked in the gap: the previous snapshot stays in `streaming`
     * until this attempt's first publish replaces it wholesale.
     */
    private suspend fun CoroutineScope.collectAttempt(
        source: Flow<RunEvent>,
        knownRunId: String?,
    ): RunAttempt {
        // Per attempt, deliberately. Do not hoist this into collectRun: every
        // reattach replays the run from its first token, so an accumulator
        // shared across attempts appends the replay to text it already has and
        // the answer appears twice. Pinned by ThreadReattachTest's `reattaching
        // twice does not duplicate…`, which fails at 20,472 characters for a
        // 12,304-character answer against the shared version.
        val accumulator = TurnAccumulator(loaded()?.thread?.streaming?.userMessage, knownRunId)
        var titleFrameSeen = false
        var failureMessage: String? = null

        // Deltas arrive faster than the display refreshes, so they are
        // folded into the accumulator and published on a timer rather than
        // one state copy per token (Architecture P1). One timer per burst,
        // not a ticker: nothing is scheduled while the stream is quiet.
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
                // Frames are flowing again, whatever this attempt turns out to
                // deliver — so the screen stops saying it is reconnecting.
                if (!accumulator.sawAnyFrame) setReconnecting(false)
                accumulator.sawFrame()
                when (event) {
                    is RunEvent.Delta -> {
                        accumulator.append(event)
                        scheduleFlush()
                    }
                    is RunEvent.Failed -> failureMessage = event.message
                    is RunEvent.RunStatus -> {
                        if (event.status == "failed") failureMessage = event.error ?: failureMessage
                    }
                    is RunEvent.ConversationUpdated -> {
                        titleFrameSeen = true
                        applyTitle(event.title)
                    }
                    // [DONE] and message_saved are NOT the end of the
                    // stream: the auto-title frame can still follow, so the
                    // loop keeps reading until the server closes it.
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
            // The screen went away. Not a run outcome — no cleanup, no
            // refetch, and above all no cancel request (F04-R10).
            throw e
        } catch (e: Throwable) {
            e
        } finally {
            pendingFlush?.cancel()
        }

        // A burst that ended inside the coalescing window leaves text the
        // cancelled timer will never publish. Flushing here is what makes
        // the turn on screen complete for the whole refetch that follows —
        // without it the tail of every answer blinks in only when the
        // saved message arrives.
        if (accumulator.takeDirty()) publishTurn(accumulator)

        return RunAttempt(
            error = error,
            runId = accumulator.runId,
            failureMessage = failureMessage,
            titleFrameSeen = titleFrameSeen,
            sawAnyFrame = accumulator.sawAnyFrame,
        )
    }

    /** The connection dropped and the app is trying to get it back (F09-R4). */
    private fun setReconnecting(value: Boolean) {
        val current = loaded() ?: return
        val turn = current.thread.streaming ?: return
        if (turn.reconnecting == value) return
        _state.value = current.copy(thread = current.thread.copy(streaming = turn.copy(reconnecting = value)))
    }

    /**
     * Every path here drops `streaming` and refetches — that is D3's whole
     * point. What the server has is the answer, whether it saved a message, a
     * partial plus an error, or nothing at all.
     */
    private suspend fun finishRun(
        error: Throwable?,
        sawAnyFrame: Boolean,
        failureMessage: String?,
        restoreOnEarlyFailure: PendingUserMessage?,
        expectTitle: Boolean,
        messagesBeforeEdit: List<ChatMessage>? = null,
        reattach: Boolean = false,
    ) {
        val current = loaded()

        // Not on the reattach path. "The run never started" is a statement
        // about a turn this client was trying to *send*; a reattach that never
        // connected — an unknown run id, say — says nothing about the thread,
        // and the refetch below is what corrects the `active_run` that sent us
        // looking for it (F09-R2's last criterion: an error, not a hang).
        if (error != null && !sawAnyFrame && !reattach) {
            // The run never started — a 409 because one is already active, or
            // the request never connected. The server rolled the user message
            // back, so dropping `streaming` leaves no phantom turn behind, and
            // the text goes back in the composer rather than vanishing.
            val restored = restoreOnEarlyFailure?.content.orEmpty()
            val loadedCurrent = current ?: return
            // `confirmEdit` truncated `messages` locally on the assumption the
            // request would succeed. A rejection here means the server never
            // touched anything (F06-R3's last criterion), so that truncation
            // has to come back — a refetch proves it rather than trusting the
            // in-memory rollback to be right on its own.
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

        // Refetch *before* dropping `streaming`, and swap both in one state
        // update: doing it the other way round blanks the answer for a round
        // trip and reads as a flicker at the end of every turn.
        val refetch = repository.load(conversationId)
        val refetched = refetch.getOrNull()
        val latest = loaded() ?: return

        if (refetched == null) {
            // The run is over but the server's copy of it could not be
            // fetched. Dropping `streaming` now would take the whole turn off
            // screen — the user's own message included — with nothing to say
            // why, and after a failure the text is real: the server persisted
            // the partial plus its error. So the turn stays, marked
            // unconfirmed: it no longer counts as a live run, it carries the
            // error the refetch could not deliver, and the next successful
            // load replaces it rather than duplicating it.
            _state.value = latest.copy(
                sending = false,
                thread = latest.thread.copy(
                    // Nothing to hold over when the turn is the empty placeholder
                    // a reattach put up: an unconfirmed blank bubble is noise, and
                    // the error is reported below either way.
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
            // A `{"error": …}` frame is already persisted on the run, so the
            // refetch surfaces it through `last_run`; only a client-side stream
            // failure needs reporting here.
            actionError = if (failureMessage == null) error?.appError?.displayMessage else null,
        )
        if (expectTitle) awaitAutoTitle()
    }

    /**
     * The auto-title is generated *after* the run is marked complete, and the
     * SSE observer closes on the run's durable status the moment it idles for
     * three seconds — so on a rig where titling takes longer than that (a local
     * model titling with itself does), `conversation_updated` is published to a
     * bus nobody is listening to any more. Polling briefly is what makes
     * F04-R7's "without a manual refresh" true in practice. See F04's
     * *Deviations*.
     */
    private suspend fun awaitAutoTitle() {
        repeat(TITLE_SETTLE_ATTEMPTS) {
            delay(titleSettleDelayMs)
            val conversation = repository.load(conversationId).getOrNull() ?: return
            if (conversation.title != UNTITLED) {
                applyTitle(conversation.title)
                return
            }
        }
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
                    // A snapshot replaces the turn wholesale, so the flags that
                    // belong to the *turn* rather than to the accumulated text
                    // have to be carried across it.
                    reconnecting = existing?.reconnecting == true,
                    reattached = existing?.reattached == true,
                ),
            ),
        )
    }

    private fun loaded(): ThreadUiState.Loaded? = _state.value as? ThreadUiState.Loaded

    companion object {
        /** Architecture P1 — roughly one publish per frame, not one per token. */
        const val DEFAULT_COALESCE_WINDOW_MS = 24L
        const val DEFAULT_TITLE_SETTLE_DELAY_MS = 1_500L
        const val TITLE_SETTLE_ATTEMPTS = 4

        /** The exact title `auto_generate_title` refuses to overwrite. */
        const val UNTITLED = "New Conversation"
    }
}

/**
 * What one connection's worth of frames turned out to be. Everything here
 * except [error] survives into the next attempt when there is one, so a title
 * frame or an error frame seen before a drop is not lost by reconnecting.
 */
private class RunAttempt(
    /** Null when the server closed the stream — which means the run is over. */
    val error: Throwable?,
    val runId: String?,
    val failureMessage: String?,
    val titleFrameSeen: Boolean,
    /** False means this attempt never got a byte: nothing to reset the backoff for. */
    val sawAnyFrame: Boolean,
)

/**
 * Mutable accumulation of one streaming turn, kept out of UI state so that
 * appending a token costs an `append` rather than a whole state copy and a
 * recomposition (Architecture P1).
 */
private class TurnAccumulator(
    private val userMessage: PendingUserMessage?,
    /**
     * The run this attempt is reattaching to, known before its `run_started`
     * frame arrives — so Stop has a guard to send even in a reconnect gap
     * (F09-R3).
     */
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

    /** Distinguishes "the run never started" from "the stream broke mid-run". */
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

    /** `tool_call_pending` announced the name; this fills in the arguments in place. */
    private fun upsertCall(event: RunEvent.ToolCall) {
        val slot = toolCalls.indexOfFirst { it.name == event.name && it.arguments == null }
        val filled = StreamingToolCall(event.name, event.serverId, event.arguments, null)
        if (slot >= 0) toolCalls[slot] = filled else toolCalls += filled
    }

    /** The server matches a result to the most recent unanswered call of that name; so does this. */
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
        /** `mcp_client.py` namespaces a pending call as `<server_id>__<tool>`. */
        const val TOOL_NAMESPACE = "__"
    }
}
