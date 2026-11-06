package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.pi.transcript.PiDisplayItem
import com.hpz.llmdockchat.feature.pi.transcript.groupToolRuns

@Composable
fun PiSessionTranscript(
    state: PiSessionUiState.Loaded,
    lastStopAt: Long?,
    modifier: Modifier = Modifier,
) {
    val items = state.transcript.items
    val display = remember(items) { groupToolRuns(items) }
    val listState = rememberLazyListState()
    var itemCountBefore by remember { mutableIntStateOf(0) }
    LaunchedEffect(display.size) {
        if (display.size > itemCountBefore) {
            val follow = shouldFollow(listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1, itemCountBefore)
            itemCountBefore = display.size
            if (follow) listState.animateScrollToItem(display.lastIndex)
        } else {
            itemCountBefore = display.size
        }
    }
    LazyColumn(
        modifier = modifier.fillMaxWidth().testTag("pi_session_list"),
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
}
