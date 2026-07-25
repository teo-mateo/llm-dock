package com.hpz.llmdockchat.feature.conversations

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberSwipeToDismissBoxState
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.font.FontWeight
import com.hpz.llmdockchat.core.time.Timestamps
import com.hpz.llmdockchat.core.ui.theme.ChipColors
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ActiveRun
import com.hpz.llmdockchat.data.model.ConversationSummary
import com.hpz.llmdockchat.data.model.Engine
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.displayName
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import java.time.Instant
import java.time.ZoneId

/**
 * Screen 02 · Conversations — the app's home screen (F02). Deviates from the
 * mockup as recorded in `F02-conversation-list.md`'s *Deviations*: no
 * last-line preview, no search, no project groups.
 */
@Composable
fun ConversationListScreen(
    viewModel: ConversationListViewModel,
    onOpenConversation: (ConversationSummary) -> Unit,
    onNewConversation: () -> Unit,
    listState: LazyListState = rememberLazyListState(),
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()

    // Fires on every (re)composition of this screen — cold start, and every
    // return to it after a tab switch or popping back from a thread, because
    // Navigation Compose disposes and re-invokes the destination's content
    // each time it stops being current (F02-R1's first and fourth criteria).
    LaunchedEffect(Unit) { viewModel.refresh() }

    ConversationListContent(
        state = state,
        listState = listState,
        onOpenConversation = onOpenConversation,
        onNewConversation = onNewConversation,
        onRetry = viewModel::refresh,
        onDelete = viewModel::delete,
        onEnterSelection = viewModel::enterSelection,
        onToggleSelection = viewModel::toggleSelection,
        onClearSelection = viewModel::clearSelection,
        onDeleteSelected = viewModel::deleteSelected,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationListContent(
    state: ConversationListUiState,
    listState: LazyListState,
    onOpenConversation: (ConversationSummary) -> Unit,
    onNewConversation: () -> Unit,
    onRetry: () -> Unit,
    onDelete: (String) -> Unit,
    onEnterSelection: (String) -> Unit,
    onToggleSelection: (String) -> Unit,
    onClearSelection: () -> Unit,
    onDeleteSelected: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    val loaded = state as? ConversationListUiState.Loaded

    var pendingDelete by remember { mutableStateOf<ConversationSummary?>(null) }
    var pendingBatchDelete by remember { mutableStateOf(false) }

    val snackbarHost = remember { SnackbarHostState() }
    LaunchedEffect(loaded?.actionError) {
        loaded?.actionError?.let { snackbarHost.showSnackbar(it) }
    }

    FollowNewConversations(loaded?.conversations, listState)

    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
    Scaffold(
        modifier = modifier.testTag("conversation_list_screen"),
        // Transparent so the gradient behind the Scaffold shows through; the
        // opaque `app` fill is what made every screen sit in one flat band.
        containerColor = Color.Transparent,
        snackbarHost = { SnackbarHost(snackbarHost) { Snackbar(it, containerColor = colors.surfaceElevated, contentColor = colors.fg) } },
        topBar = {
            if (loaded?.selectionMode == true) {
                SelectionTopBar(
                    count = loaded.selection.size,
                    onClose = onClearSelection,
                    onDelete = { pendingBatchDelete = true },
                )
            } else {
                ListHeader(count = loaded?.conversations?.size)
            }
        },
        floatingActionButton = {
            if (loaded?.selectionMode != true) {
                FloatingActionButton(
                    onClick = onNewConversation,
                    containerColor = colors.accent,
                    contentColor = colors.onAccent,
                    shape = RoundedCornerShape(18.dp),
                    modifier = Modifier.testTag("new_conversation_fab"),
                ) {
                    Icon(DesignLabIcons.Plus, contentDescription = "New chat")
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (state) {
                is ConversationListUiState.Loading -> LoadingState()
                is ConversationListUiState.Failed -> FailedState(state.message, onRetry)
                is ConversationListUiState.Loaded -> {
                    if (state.isEmpty) {
                        EmptyState()
                    } else {
                        Column(Modifier.fillMaxSize()) {
                            if (state.refreshing) {
                                LinearProgressIndicator(
                                    modifier = Modifier.fillMaxWidth().testTag("conversation_list_refreshing"),
                                    color = colors.accent,
                                    trackColor = colors.surface,
                                )
                            }
                            LazyColumn(
                                state = listState,
                                modifier = Modifier.fillMaxSize().testTag("conversation_list"),
                                // Fix pass A5: the FAB floats over the list, so
                                // without this the last conversation's title
                                // sits under it and its timestamp is
                                // unreachable — there is no further scroll.
                                contentPadding = PaddingValues(bottom = FAB_CLEARANCE),
                            ) {
                                items(state.conversations, key = { it.id }) { item ->
                                    ConversationRow(
                                        item = item,
                                        selected = item.id in state.selection,
                                        selectionMode = state.selectionMode,
                                        onOpen = {
                                            if (state.selectionMode) onToggleSelection(item.id) else onOpenConversation(item)
                                        },
                                        onLongPress = {
                                            if (state.selectionMode) onToggleSelection(item.id) else onEnterSelection(item.id)
                                        },
                                        onRequestDelete = { pendingDelete = item },
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    }

    pendingDelete?.let { target ->
        ConfirmDialog(
            title = "Delete conversation?",
            message = "“${target.title}” will be deleted. This can't be undone.",
            confirmLabel = "Delete",
            onConfirm = {
                onDelete(target.id)
                pendingDelete = null
            },
            onDismiss = { pendingDelete = null },
        )
    }

    if (pendingBatchDelete) {
        val count = loaded?.selection?.size ?: 0
        ConfirmDialog(
            title = "Delete $count conversations?",
            message = "This can't be undone.",
            confirmLabel = "Delete",
            onConfirm = {
                onDeleteSelected()
                pendingBatchDelete = false
            },
            onDismiss = { pendingBatchDelete = false },
        )
    }
}

/**
 * Fix pass A3 — "the conversation I just started is not in the list".
 *
 * The refresh on return does happen; what goes wrong is where the new row
 * lands. `LazyColumn` anchors its viewport on the first visible item's *key*,
 * so when a refresh prepends a conversation the anchor stays put and the new
 * row is laid out above the fold, with nothing on screen changing. The reader
 * concludes the thread was lost.
 *
 * So: when the head of the list changes, work out how many rows were prepended
 * and, if the viewport was sitting inside that region — i.e. at or near the top
 * — put it back at the top. Someone who has scrolled down to read older threads
 * keeps their place.
 */
@Composable
private fun FollowNewConversations(conversations: List<ConversationSummary>?, listState: LazyListState) {
    val head = conversations?.firstOrNull()?.id
    var previousHead by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(head) {
        val previous = previousHead
        previousHead = head
        if (previous == null || head == null || head == previous || conversations == null) {
            return@LaunchedEffect
        }
        val prepended = conversations.indexOfFirst { it.id == previous }
        if (prepended > 0 && listState.firstVisibleItemIndex <= prepended) {
            listState.scrollToItem(0)
        }
    }
}

/**
 * The list header. Replaces the `TopAppBar` rather than restyling it: Material's
 * app bar fixes its own height and title style, and the design wants a two-line
 * block (title over a live count) on the page background with no bar of its own.
 */
@Composable
private fun ListHeader(count: Int?) {
    val colors = LlmTheme.colors
    Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 10.dp)) {
        Text(
            "Chats",
            color = colors.fg,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        if (count != null) {
            Text(
                if (count == 1) "1 conversation" else "$count conversations",
                color = colors.subtle,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SelectionTopBar(count: Int, onClose: () -> Unit, onDelete: () -> Unit) {
    val colors = LlmTheme.colors
    TopAppBar(
        title = { Text("$count selected", color = colors.fg) },
        navigationIcon = {
            IconButton(onClick = onClose, modifier = Modifier.testTag("selection_close")) {
                Text("✕", color = colors.fg)
            }
        },
        actions = {
            TextButton(onClick = onDelete, modifier = Modifier.testTag("selection_delete")) {
                Text("Delete", color = colors.red)
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.surfaceElevated),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationRow(
    item: ConversationSummary,
    selected: Boolean,
    selectionMode: Boolean,
    onOpen: () -> Unit,
    onLongPress: () -> Unit,
    onRequestDelete: () -> Unit,
) {
    if (selectionMode) {
        ConversationRowBody(item, selected, selectionMode, onOpen, onLongPress)
        return
    }

    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            // Never let the library commit the dismiss itself — a swipe only
            // opens the confirm dialog (F02-R4); the row always springs back
            // (F00-R9's "cancelling leaves state untouched" applies to the
            // gesture too, not just the dialog).
            if (value != SwipeToDismissBoxValue.Settled) onRequestDelete()
            false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        modifier = Modifier.testTag("conversation_row_swipe_${item.id}"),
        // Only while the row is actually being dragged. `backgroundContent` is
        // composed unconditionally, and the row body above it is transparent so
        // the page gradient shows through — so an always-drawn red panel made
        // every settled row red with a stray "Delete" peeking out from under
        // the badge.
        backgroundContent = { if (dismissState.progress < 1f) DeleteSwipeBackground() },
    ) {
        ConversationRowBody(item, selected = false, selectionMode = false, onOpen, onLongPress)
    }
}

@Composable
private fun DeleteSwipeBackground() {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.red.copy(alpha = 0.85f))
            .padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Delete", color = Color.White, fontFamily = FontFamily.Monospace)
    }
}

@Composable
private fun ConversationRowBody(
    item: ConversationSummary,
    selected: Boolean,
    selectionMode: Boolean,
    onOpen: () -> Unit,
    onLongPress: () -> Unit,
) {
    val colors = LlmTheme.colors
    val now = remember { Instant.now() }
    val zone = remember { ZoneId.systemDefault() }
    val time = remember(item.updatedAt) { item.updatedAt?.let { Timestamps.relative(it, now, zone) }.orEmpty() }

    Column(
        Modifier
            .fillMaxWidth()
            // The row is drawn on the page gradient, so "unselected" is
            // transparent, not an opaque `app` fill — an opaque row would punch
            // a flat rectangle through the backdrop.
            .background(if (selected) colors.accentSoft else Color.Transparent)
            .combinedClickable(onClick = onOpen, onLongClick = onLongPress)
            .testTag("conversation_row_${item.id}"),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (selectionMode) {
                Checkbox(
                    checked = selected,
                    onCheckedChange = { onOpen() },
                    colors = CheckboxDefaults.colors(checkedColor = colors.accent, uncheckedColor = colors.subtle),
                )
            } else {
                // The badge carries the live state as colour, which is why the
                // generating dot can stay a small detail rather than the only
                // signal a row is busy.
                Box(
                    Modifier
                        .size(36.dp)
                        .background(
                            if (item.isGenerating) colors.accentSoft else colors.surfaceHigh,
                            RoundedCornerShape(12.dp),
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        DesignLabIcons.ChatBubble,
                        contentDescription = null,
                        tint = if (item.isGenerating) colors.accent else colors.muted,
                        modifier = Modifier.size(19.dp),
                    )
                }
            }

            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        item.title,
                        color = colors.fg,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        // Without the weight the title measures at its full
                        // intrinsic width and pushes the timestamp off the row
                        // — `maxLines = 1` alone does not constrain a Text.
                        modifier = Modifier.weight(1f),
                    )
                    Text(time, color = colors.subtle, style = MaterialTheme.typography.labelMedium)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // C2: the model name is the part that gives way when the row
                    // is narrow. Un-weighted, the chip took the whole width and
                    // the live badge next to it ellipsised to "● genera…".
                    EngineChip(item.modelRef, item.engine, Modifier.weight(1f, fill = false))
                    if (item.isGenerating) GeneratingIndicator(item.activeRun)
                }
            }
        }

        // Indented past the badge so the dividers read as separators between
        // rows rather than as a full-width grid. One fixed indent in both
        // modes — keying it off `selectionMode` made every divider jump
        // outwards the moment a long-press swapped the badge for a checkbox.
        Box(
            Modifier
                .padding(start = ROW_DIVIDER_INDENT)
                .fillMaxWidth()
                .height(1.dp)
                .background(colors.line),
        )
    }
}

@Composable
private fun EngineChip(modelRef: ModelRef, engine: Engine, modifier: Modifier = Modifier) {
    val chip = LlmTheme.colors.chipColors(engine)
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(chip.background)
            .padding(horizontal = 8.dp, vertical = 3.dp)
            .testTag("engine_chip_${engine.name}"),
    ) {
        Text(
            modelRef.displayName,
            color = chip.foreground,
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** Where the row's text column starts: 20 dp page margin + 36 dp badge + 12 dp gap. */
private val ROW_DIVIDER_INDENT = 68.dp

/** FAB (56 dp) plus the Scaffold's own 16 dp margin. */
private val FAB_CLEARANCE = 80.dp

private fun LlmColors.chipColors(engine: Engine): ChipColors = when (engine) {
    Engine.LLAMA_CPP -> engineLlamaCpp
    Engine.VLLM -> engineVllm
    Engine.DS4 -> engineDs4
    Engine.OPEN_ROUTER -> engineOpenRouter
    Engine.UNKNOWN -> engineUnknown
}

/** The live "generating" dot (F02-R3) — any thread with a non-terminal run. */
@Composable
private fun GeneratingIndicator(run: ActiveRun?) {
    val colors = LlmTheme.colors
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        modifier = Modifier.testTag("generating_indicator"),
    ) {
        Box(Modifier.size(7.dp).background(colors.green, CircleShape))
        Text(
            run?.activeStep?.takeIf { it.isNotBlank() } ?: "Generating…",
            color = colors.green,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize().testTag("conversation_list_loading"), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun EmptyState() {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp).testTag("conversation_list_empty"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("No conversations yet", color = colors.fg, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            "Tap New chat to start one.",
            color = colors.muted,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun FailedState(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp).testTag("conversation_list_failed"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Couldn't load conversations", color = colors.red, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(message, color = colors.muted, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = onRetry, modifier = Modifier.testTag("conversation_list_retry")) {
            Text("Retry", color = colors.accent)
        }
    }
}

@Composable
private fun ConfirmDialog(
    title: String,
    message: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LlmTheme.colors
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = colors.surface,
        title = { Text(title, color = colors.fg) },
        text = { Text(message, color = colors.muted) },
        confirmButton = {
            TextButton(onClick = onConfirm, modifier = Modifier.testTag("confirm_dialog_confirm")) {
                Text(confirmLabel, color = colors.red)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.testTag("confirm_dialog_dismiss")) {
                Text("Cancel", color = colors.muted)
            }
        },
    )
}

@Preview
@Composable
private fun ConversationListPopulatedPreview() {
    LLMDockChatTheme(darkTheme = true) {
        ConversationListContent(
            state = ConversationListUiState.Loaded(
                conversations = listOf(
                    ConversationSummary(
                        id = "1",
                        title = "Speculative decoding on Laguna",
                        modelRef = ModelRef.Local("llamacpp-laguna-s-2.1-q4"),
                        updatedAt = Instant.now().toString(),
                        activeRun = ActiveRun("r1", "running", "Thinking…", Instant.now().toString()),
                    ),
                    ConversationSummary(
                        id = "2",
                        title = "Xorg watchdog vs. deep context",
                        modelRef = ModelRef.Local("vllm-qwen3.6-35b-a3b-fp8"),
                        updatedAt = Instant.now().minusSeconds(3600).toString(),
                        activeRun = null,
                    ),
                    ConversationSummary(
                        id = "3",
                        title = "Rewriting compose_manager tests",
                        modelRef = ModelRef.OpenRouter("anthropic/claude-sonnet-5"),
                        updatedAt = Instant.now().minusSeconds(90_000).toString(),
                        activeRun = null,
                    ),
                    ConversationSummary(
                        id = "4",
                        title = "Old thread on a decommissioned service",
                        modelRef = ModelRef.Local("llamacpp-retired-model"),
                        updatedAt = Instant.now().minusSeconds(500_000).toString(),
                        activeRun = null,
                    ),
                ),
            ),
            listState = rememberLazyListState(),
            onOpenConversation = {}, onNewConversation = {}, onRetry = {},
            onDelete = {}, onEnterSelection = {}, onToggleSelection = {}, onClearSelection = {}, onDeleteSelected = {},
        )
    }
}

@Preview
@Composable
private fun ConversationListEmptyPreview() {
    LLMDockChatTheme(darkTheme = false) {
        ConversationListContent(
            state = ConversationListUiState.Loaded(conversations = emptyList()),
            listState = rememberLazyListState(),
            onOpenConversation = {}, onNewConversation = {}, onRetry = {},
            onDelete = {}, onEnterSelection = {}, onToggleSelection = {}, onClearSelection = {}, onDeleteSelected = {},
        )
    }
}

@Preview
@Composable
private fun ConversationListFailedPreview() {
    LLMDockChatTheme(darkTheme = true) {
        ConversationListContent(
            state = ConversationListUiState.Failed("Could not reach the server."),
            listState = rememberLazyListState(),
            onOpenConversation = {}, onNewConversation = {}, onRetry = {},
            onDelete = {}, onEnterSelection = {}, onToggleSelection = {}, onClearSelection = {}, onDeleteSelected = {},
        )
    }
}
