package com.hpz.llmdockchat.feature.thread

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.result.PickVisualMediaRequest
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.snapshotFlow
import kotlinx.coroutines.flow.first
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.displayName
import kotlinx.coroutines.launch

/**
 * Screen 04 · the thread, mid-answer (F04).
 *
 * Deviates from the mockup as recorded in `F04-chat-turn-and-streaming.md`:
 * no tok/s readout in the stop bar, and no critique overlay.
 */
@Composable
fun ThreadScreen(
    viewModel: ThreadViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    listState: LazyListState = rememberLazyListState(),
) {
    val state by viewModel.state.collectAsState()

    // Fires on entry and on every return to the destination, the same pattern
    // the conversation list uses. It never disturbs a run in flight: `load`
    // carries the streaming turn across.
    LaunchedEffect(Unit) { viewModel.load() }

    ThreadContent(
        state = state,
        listState = listState,
        onBack = onBack,
        onComposerChange = viewModel::onComposerChange,
        onSend = viewModel::send,
        onStop = viewModel::stop,
        onRetry = viewModel::load,
        onDismissError = viewModel::dismissActionError,
        onAddAttachment = viewModel::addAttachment,
        onRemoveAttachment = viewModel::removeAttachment,
        onAttachmentFailed = viewModel::reportAttachmentFailure,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ThreadContent(
    state: ThreadUiState,
    listState: LazyListState,
    onBack: () -> Unit,
    onComposerChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
    onRetry: () -> Unit,
    onDismissError: () -> Unit,
    onAddAttachment: (String) -> Unit,
    onRemoveAttachment: (Int) -> Unit,
    onAttachmentFailed: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    val loaded = state as? ThreadUiState.Loaded

    val snackbarHost = remember { SnackbarHostState() }
    LaunchedEffect(loaded?.actionError) {
        loaded?.actionError?.let {
            snackbarHost.showSnackbar(it)
            onDismissError()
        }
    }

    Scaffold(
        modifier = modifier.testTag("thread_screen"),
        containerColor = colors.app,
        snackbarHost = {
            SnackbarHost(snackbarHost) {
                Snackbar(it, containerColor = colors.surfaceElevated, contentColor = colors.fg)
            }
        },
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            loaded?.conversation?.title ?: "Conversation",
                            color = colors.fg,
                            style = MaterialTheme.typography.titleMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.testTag("thread_title"),
                        )
                        // F04-R3: who is answering stays visible for the whole
                        // turn, not just at the moment it starts.
                        loaded?.conversation?.modelRef?.let { ref ->
                            Text(
                                ref.displayName,
                                color = colors.subtle,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.labelSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.testTag("thread_model"),
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("thread_back")) {
                        Text("←", color = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (state) {
                is ThreadUiState.Loading -> CenteredProgress()
                is ThreadUiState.Failed -> FailedState(state.message, onRetry)
                is ThreadUiState.Loaded -> LoadedThread(
                    state = state,
                    listState = listState,
                    onComposerChange = onComposerChange,
                    onSend = onSend,
                    onStop = onStop,
                    onAddAttachment = onAddAttachment,
                    onRemoveAttachment = onRemoveAttachment,
                    onAttachmentFailed = onAttachmentFailed,
                )
            }
        }
    }
}

@Composable
private fun LoadedThread(
    state: ThreadUiState.Loaded,
    listState: LazyListState,
    onComposerChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
    onAddAttachment: (String) -> Unit,
    onRemoveAttachment: (Int) -> Unit,
    onAttachmentFailed: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val streaming = state.thread.streaming

    // "At the bottom" is the whole auto-scroll rule (F04-R3): follow the tail
    // while the user is there, stop the instant they scroll up, resume when
    // they come back. No separate follow flag to get out of sync.
    val atBottom by remember { derivedStateOf { !listState.canScrollForward } }
    val tailSignal = streaming?.content?.length.orZero() +
        streaming?.reasoning?.length.orZero() +
        state.thread.messages.size

    LaunchedEffect(tailSignal) {
        if (atBottom && listState.layoutInfo.totalItemsCount > 0) {
            listState.scrollToItem(listState.layoutInfo.totalItemsCount - 1)
        }
    }

    // A thread opens on its most recent turn, not its first. Waiting for the
    // first laid-out item count is what makes this land: on the composition
    // that runs this effect the list has not been measured yet, so there is
    // nothing to scroll to.
    LaunchedEffect(Unit) {
        if (state.thread.messages.isEmpty()) return@LaunchedEffect
        val count = snapshotFlow { listState.layoutInfo.totalItemsCount }.first { it > 1 }
        listState.scrollToItem(count - 1)
    }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f)) {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize().testTag("thread_list"),
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                items(state.thread.messages)

                streaming?.let { turn ->
                    turn.userMessage?.let { pending ->
                        item(key = "pending_user") {
                            MessageBubble(pending.asMessage())
                        }
                    }
                    // Its own item, so a delta recomposes this element alone
                    // rather than the whole column (Architecture P2).
                    item(key = "streaming") { StreamingBubble(turn) }
                }

                // A persisted failure has no message of its own when the model
                // died before producing any text; the run's error is still the
                // truth about that turn (F04-R8).
                if (streaming == null) {
                    state.runError?.takeIf { state.thread.messages.lastOrNull()?.error == null }?.let { error ->
                        item(key = "run_error") {
                            Box(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) { ErrorNote(error) }
                        }
                    }
                }

                // Scrolling this 1 dp tail into view lands exactly at the
                // bottom of the content, whatever the last item's height.
                item(key = "tail") { Spacer(Modifier.height(1.dp)) }
            }

            if (!atBottom) {
                JumpToLatest(
                    modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                    onClick = {
                        scope.launch { listState.animateScrollToItem(listState.layoutInfo.totalItemsCount - 1) }
                    },
                )
            }
        }

        ThreadComposer(
            state = state,
            onComposerChange = onComposerChange,
            onSend = onSend,
            onStop = onStop,
            onAddAttachment = onAddAttachment,
            onRemoveAttachment = onRemoveAttachment,
            onAttachmentFailed = onAttachmentFailed,
        )
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.items(messages: List<ChatMessage>) {
    items(messages.size, key = { messages[it].id }) { index -> MessageBubble(messages[index]) }
}

private fun Int?.orZero(): Int = this ?: 0

/** The live turn. Same rendering as a saved one, so `message_saved` is invisible. */
@Composable
private fun StreamingBubble(turn: StreamingTurn) {
    AssistantBubble(
        content = turn.content,
        reasoning = turn.reasoning.takeIf { it.isNotBlank() },
        toolCalls = emptyList(),
        parseWarning = turn.parseWarning,
        // Normally null — the run's error arrives on the refetched message.
        // Set only when the turn is being held over because that refetch
        // failed, so a failure is never shown without its cause.
        error = turn.error,
        modifier = Modifier.testTag("streaming_turn"),
        trailing = {
            turn.toolCalls.forEach { ToolCallCard(it) }
            if (!turn.hasVisibleOutput && !turn.unconfirmed) WaitingIndicator(turn.stopping)
        },
    )
}

@Composable
private fun WaitingIndicator(stopping: Boolean) {
    val colors = LlmTheme.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp, color = colors.accent)
        Text(
            if (stopping) "Stopping…" else "Generating…",
            color = colors.muted,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}

@Composable
private fun JumpToLatest(modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Box(
        modifier = modifier
            .clip(CircleShape)
            .background(colors.surfaceElevated)
            .size(44.dp)
            .testTag("jump_to_latest"),
        contentAlignment = Alignment.Center,
    ) {
        IconButton(onClick = onClick) { Text("↓", color = colors.fg) }
    }
}

@Composable
private fun CenteredProgress() {
    Box(Modifier.fillMaxSize().testTag("thread_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun FailedState(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp).testTag("thread_failed"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Couldn't load this thread", color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = onRetry, modifier = Modifier.testTag("thread_retry")) {
            Text("Retry", color = colors.accent)
        }
    }
}

/**
 * The optimistic user turn lives inside `streaming`, never in
 * [ThreadState.messages] (Architecture D3) — which is what makes a 409 leave no
 * phantom behind (F04-R2): dropping `streaming` drops it.
 */
private fun PendingUserMessage.asMessage() = ChatMessage(
    id = "pending",
    role = MessageRole.USER,
    content = content,
    reasoning = null,
    modelService = null,
    images = images,
    seq = Int.MAX_VALUE,
    createdAt = null,
    toolCalls = emptyList(),
    parseWarning = null,
    error = null,
)

/**
 * Grows to five lines and then scrolls; Enter inserts a newline and the button
 * sends, the opposite of the desktop (F04-R1).
 */
@Composable
private fun ThreadComposer(
    state: ThreadUiState.Loaded,
    onComposerChange: (String) -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
    onAddAttachment: (String) -> Unit,
    onRemoveAttachment: (Int) -> Unit,
    onAttachmentFailed: (String) -> Unit,
) {
    val colors = LlmTheme.colors
    val context = LocalContext.current

    val pickImage = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val bitmap = runCatching { readImage(context.contentResolver, uri) }.getOrNull()
        if (bitmap == null) onAttachmentFailed("That image could not be read.")
        else onAddAttachment(bitmap.toDataUrl())
    }
    val takePhoto = rememberLauncherForActivityResult(ActivityResultContracts.TakePicturePreview()) { bitmap ->
        if (bitmap != null) onAddAttachment(bitmap.toDataUrl())
    }

    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .navigationBarsPadding()
            .imePadding()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (state.attachments.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("attachment_strip")) {
                state.attachments.forEachIndexed { index, dataUrl ->
                    ImageThumbnail(dataUrl, size = 58.dp, onRemove = { onRemoveAttachment(index) })
                }
            }
        }

        ComposerRow(
            value = state.composer,
            enabled = !state.runActive,
            canSend = state.canSend,
            runActive = state.runActive,
            stopping = state.thread.streaming?.stopping == true,
            onValueChange = onComposerChange,
            onSend = onSend,
            onStop = onStop,
            onPickImage = { pickImage.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
            onTakePhoto = { takePhoto.launch(null) },
        )
    }
}

@Preview
@Composable
private fun ThreadStreamingPreview() {
    LLMDockChatTheme(darkTheme = true) {
        ThreadContent(
            state = ThreadUiState.Loaded(
                conversation = ConversationDetail(
                    id = "c1",
                    title = "Speculative decoding on Laguna",
                    modelRef = ModelRef.Local("llamacpp-laguna-s-2.1-q4"),
                    messages = emptyList(),
                    activeRun = null,
                    lastRun = null,
                    updatedAt = null,
                ),
                thread = ThreadState(
                    messages = listOf(
                        ChatMessage(
                            id = "m1",
                            role = MessageRole.USER,
                            content = "Does Laguna have an MTP head I can point llama.cpp at?",
                            reasoning = null,
                            modelService = null,
                            images = emptyList(),
                            seq = 1,
                            createdAt = null,
                            toolCalls = emptyList(),
                            parseWarning = null,
                            error = null,
                        ),
                    ),
                    streaming = StreamingTurn(
                        userMessage = null,
                        runId = "r1",
                        content = "No MTP head ships with Laguna S 2.1 — the checkpoint has a single LM head.",
                        reasoning = "Checking the checkpoint layout first.",
                    ),
                ),
            ),
            listState = rememberLazyListState(),
            onBack = {}, onComposerChange = {}, onSend = {}, onStop = {}, onRetry = {},
            onDismissError = {}, onAddAttachment = {}, onRemoveAttachment = {}, onAttachmentFailed = {},
        )
    }
}
