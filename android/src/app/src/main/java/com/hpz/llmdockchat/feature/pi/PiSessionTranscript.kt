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

@Composable
fun PiSessionTranscript(
    state: PiSessionUiState.Loaded,
    lastStopAt: Long?,
    modifier: Modifier = Modifier,
) {
    val items = state.transcript.items
    val listState = rememberLazyListState()
    var itemCountBefore by remember { mutableIntStateOf(0) }
    LaunchedEffect(items.size) {
        if (items.size > itemCountBefore) {
            val follow = shouldFollow(listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1, itemCountBefore)
            itemCountBefore = items.size
            if (follow) listState.animateScrollToItem(items.lastIndex)
        } else {
            itemCountBefore = items.size
        }
    }
    LazyColumn(
        modifier = modifier.fillMaxWidth().testTag("pi_session_list"),
        state = listState,
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        items(items, key = { it.id }) { item -> PiItemView(item, lastStopAt) }
    }
}
