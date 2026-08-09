package com.hpz.llmdockchat.feature.share

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ConversationSummary
import com.hpz.llmdockchat.feature.conversations.ConversationRowBody
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.thread.decodeDataUrl

/**
 * F14-R2 — the share-target picker: a full-screen list of conversations, most
 * recent first, with the shared content staged on a header card above it.
 * Picking a row opens that thread with the content staged in the composer
 * (F14-R3); back dismisses the share entirely. The list is the same data and
 * ordering as the Chats tab — `ConversationsRepository.list()` already asks
 * for `limit=-1&unfiled=true`, so project threads never appear here either.
 */
@Composable
fun ShareTargetScreen(
    viewModel: ShareTargetViewModel,
    onPickConversation: (ConversationSummary) -> Unit,
    onNewConversation: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(Unit) { viewModel.refresh() }

    // F14 — the system back must dismiss the share the same way the top-bar
    // close does: without [onDismiss] the pending record survives the pop and
    // the picker would re-open on the next launch (a ghost share).
    BackHandler(onBack = onDismiss)

    ShareTargetContent(
        state = state,
        onPickConversation = onPickConversation,
        onNewConversation = onNewConversation,
        onDismiss = onDismiss,
        onRetry = viewModel::refresh,
        modifier = modifier,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ShareTargetContent(
    state: ShareTargetUiState,
    onPickConversation: (ConversationSummary) -> Unit,
    onNewConversation: () -> Unit,
    onDismiss: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors

    Scaffold(
        modifier = modifier.testTag("share_target_screen"),
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Send to a chat",
                        color = colors.fg,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onDismiss, modifier = Modifier.testTag("share_target_back")) {
                        Icon(DesignLabIcons.Close, contentDescription = "Cancel share", tint = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                    scrolledContainerColor = Color.Transparent,
                ),
                // The top bar consumes the status-bar inset itself; the header
                // card below it pads off the same inset so the two never stack.
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
            when (state) {
                is ShareTargetUiState.Loading -> LoadingState()
                is ShareTargetUiState.Failed -> FailedState(state.message, onRetry)
                is ShareTargetUiState.Loaded -> {
                    Column(Modifier.fillMaxSize()) {
                        ShareHeader(state.share)
                        if (state.refreshing) {
                            LinearProgressIndicator(
                                modifier = Modifier.fillMaxWidth().testTag("share_target_refreshing"),
                                color = colors.accent,
                                trackColor = colors.surface,
                            )
                        }
                        if (state.isEmpty) {
                            EmptyState(onNewConversation)
                        } else {
                            LazyColumn(
                                modifier = Modifier.fillMaxSize().testTag("share_target_list"),
                                contentPadding = PaddingValues(bottom = 24.dp),
                            ) {
                                items(state.conversations, key = { it.id }) { item ->
                                    ConversationRowBody(
                                        item = item,
                                        selected = false,
                                        selectionMode = false,
                                        onOpen = { onPickConversation(item) },
                                        onLongPress = {},
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

/**
 * What is being shared, so the user sees the payload before choosing a target:
 * a thumbnail for an image, the file name for a text file, the first line for
 * text, or the reason an unsupported share was refused (F14-R3).
 */
@Composable
private fun ShareHeader(share: StagedShare) {
    val colors = LlmTheme.colors
    val error = share.error
    val thumbnail = share.attachments.firstOrNull()?.let { decodeDataUrl(it) }
    val snippet = share.text.lineSequence().firstOrNull()?.take(120).orEmpty()

    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 12.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(
                if (error != null) colors.red.copy(alpha = 0.12f) else colors.surfaceHigh,
            )
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when {
            error != null -> {
                Icon(
                    DesignLabIcons.Close,
                    contentDescription = null,
                    tint = colors.red,
                    modifier = Modifier.size(22.dp),
                )
                Column {
                    Text(
                        "Couldn't share that",
                        color = colors.fg,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        error,
                        color = colors.subtle,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            thumbnail != null -> {
                Box(
                    Modifier
                        .size(44.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(colors.surface),
                ) {
                    Image(
                        bitmap = thumbnail.asImageBitmap(),
                        contentDescription = "Shared image",
                        modifier = Modifier.fillMaxSize(),
                    )
                }
                Column {
                    Text(
                        "Shared image",
                        color = colors.fg,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "Will be attached to your message",
                        color = colors.subtle,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            snippet.isNotEmpty() -> {
                Icon(
                    DesignLabIcons.ChatBubble,
                    contentDescription = null,
                    tint = colors.accent,
                    modifier = Modifier.size(22.dp),
                )
                Column {
                    Text(
                        "Shared text",
                        color = colors.fg,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        snippet,
                        color = colors.subtle,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = LlmTheme.colors.accent)
    }
}

@Composable
private fun FailedState(message: String, onRetry: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxSize().padding(40.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(message, color = colors.subtle, style = MaterialTheme.typography.bodyLarge)
        Box(
            Modifier
                .padding(top = 16.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(colors.accentSoft)
                .clickable(onClick = onRetry)
                .padding(horizontal = 20.dp, vertical = 10.dp),
        ) {
            Text("Retry", color = colors.accent, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun EmptyState(onNewConversation: () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        Modifier.fillMaxSize().padding(40.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "No conversations yet",
            color = colors.fg,
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "Start a new chat to send this to.",
            color = colors.subtle,
            style = MaterialTheme.typography.bodyMedium,
        )
        Box(
            Modifier
                .padding(top = 16.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(colors.accentSoft)
                .clickable(onClick = onNewConversation)
                .padding(horizontal = 20.dp, vertical = 10.dp),
        ) {
            Text("New chat", color = colors.accent, fontWeight = FontWeight.SemiBold)
        }
    }
}
