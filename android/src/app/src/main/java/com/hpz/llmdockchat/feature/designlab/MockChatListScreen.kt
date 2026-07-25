package com.hpz.llmdockchat.feature.designlab

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme

/**
 * Mockup — chat list. Dummy data, no ViewModel. Compared against the real
 * `ConversationListScreen`.
 */
@Composable
fun MockChatListScreen() {
    val colors = DesignLabTheme.colors
    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 20.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("Chats", style = MaterialTheme.typography.displaySmall, color = colors.fg)
                    Text("7 conversations", style = MaterialTheme.typography.bodyMedium, color = colors.subtle)
                }
                Box(
                    Modifier
                        .size(42.dp)
                        .background(colors.surfaceElevated, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(DesignLabIcons.Search, contentDescription = "Search", tint = colors.muted, modifier = Modifier.size(19.dp))
                }
            }

            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(MOCK_CONVERSATIONS) { convo -> ConversationRow(convo) }
            }
        }

        FloatingActionButton(
            onClick = {},
            containerColor = colors.accent,
            contentColor = colors.onAccent,
            shape = RoundedCornerShape(18.dp),
            modifier = Modifier.align(Alignment.BottomEnd).padding(24.dp),
        ) {
            Icon(DesignLabIcons.Plus, contentDescription = "New chat")
        }
    }
}

@Composable
private fun ConversationRow(convo: MockConversation) {
    val colors = DesignLabTheme.colors
    val (chipBg, chipFg) = engineChipColors(convo.engine)
    DlCard {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DlIconBadge(
                icon = DesignLabIcons.ChatBubble,
                tint = if (convo.pinned) colors.accent else colors.muted,
                background = if (convo.pinned) colors.accentSoft else colors.surfaceHigh,
            )
            Column(Modifier.weight(1f)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(
                        convo.title,
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.fg,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    Text(convo.time, style = MaterialTheme.typography.labelSmall, color = colors.subtle)
                }
                Text(
                    convo.preview,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DlChip(convo.engine, chipBg, chipFg)
                    DlChip(convo.model, colors.surfaceHigh, colors.subtle)
                }
            }
        }
    }
}

@Composable
internal fun engineChipColors(engine: String): Pair<androidx.compose.ui.graphics.Color, androidx.compose.ui.graphics.Color> {
    val colors = DesignLabTheme.colors
    return when (engine) {
        "llama.cpp" -> colors.accentSoft to colors.accent
        "vLLM" -> androidx.compose.ui.graphics.Color(0x2EDB6BE0) to androidx.compose.ui.graphics.Color(0xFFDB6BE0)
        "DS4" -> androidx.compose.ui.graphics.Color(0x2EFF9F45) to androidx.compose.ui.graphics.Color(0xFFFF9F45)
        "OpenRouter" -> androidx.compose.ui.graphics.Color(0x2E34D399) to colors.green
        else -> colors.surfaceHigh to colors.subtle
    }
}

@Preview(name = "Chat list — dark", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockChatListDarkPreview() {
    DesignLabTheme(darkTheme = true) { MockChatListScreen() }
}

@Preview(name = "Chat list — light", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockChatListLightPreview() {
    DesignLabTheme(darkTheme = false) { MockChatListScreen() }
}
