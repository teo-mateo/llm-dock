package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiDisplayItem
import com.hpz.llmdockchat.feature.pi.transcript.groupToolRuns
import kotlinx.coroutines.launch

@Composable
fun PiSessionTranscript(
    state: PiSessionUiState.Loaded,
    lastStopAt: Long?,
    modifier: Modifier = Modifier,
) {
    val items = state.transcript.items
    val display = remember(items) { groupToolRuns(items) }
    val listState = rememberLazyListState()
    var follow by remember { mutableStateOf(FollowState(following = true, seen = items)) }
    val currentItems by rememberUpdatedState(items)

    LaunchedEffect(items, follow.following) {
        if (follow.following && display.isNotEmpty()) listState.scrollToItem(display.lastIndex, Int.MAX_VALUE)
    }
    LaunchedEffect(listState) {
        trackUserScrolling(
            listState,
            onDragStart = { follow = follow.pause(currentItems) },
            onSettled = { atBottom -> follow = follow.settle(atBottom, currentItems) },
        )
    }

    Box(modifier.fillMaxWidth()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().testTag("pi_session_list"),
            state = listState,
            contentPadding = PaddingValues(vertical = 8.dp),
        ) {
            items(display, key = { it.id }) { entry ->
                when (entry) {
                    is PiDisplayItem.Single -> PiItemView(entry.item, lastStopAt)
                    is PiDisplayItem.ToolGroup -> PiToolGroupView(entry)
                }
            }
        }
        if (follow.hasUnseen(items)) {
            NewContentButton(
                onClick = { follow = follow.jump(items) },
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 12.dp),
            )
        }
    }
}

private suspend fun trackUserScrolling(
    listState: LazyListState,
    onDragStart: () -> Unit,
    onSettled: (atBottom: Boolean) -> Unit,
) = kotlinx.coroutines.coroutineScope {
    var dragged = false
    launch {
        listState.interactionSource.interactions.collect {
            if (it is DragInteraction.Start) {
                dragged = true
                onDragStart()
            }
        }
    }
    snapshotFlow { listState.isScrollInProgress }.collect { scrolling ->
        if (!scrolling && dragged) {
            dragged = false
            onSettled(!listState.canScrollForward)
        }
    }
}

@Composable
private fun NewContentButton(onClick: () -> Unit, modifier: Modifier) {
    val colors = LlmTheme.colors
    Text(
        "New content ↓",
        color = colors.accent,
        fontWeight = FontWeight.SemiBold,
        style = MaterialTheme.typography.labelMedium,
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(colors.surfaceElevated)
            .border(1.dp, colors.line, RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp)
            .testTag("pi_new_content"),
    )
}
