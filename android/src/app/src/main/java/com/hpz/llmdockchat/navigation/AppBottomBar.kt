package com.hpz.llmdockchat.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

private data class Tab(val route: String, val label: String, val glyph: String)

private val TABS = listOf(
    Tab(Destinations.CHATS, "Chats", "💬"),
    Tab(Destinations.MODELS, "Models", "▦"),
    Tab(Destinations.DESIGN, "Design", "✦"),
)

/**
 * The bottom bar (Architecture D12, F02-R7): present on the conversation
 * list and the models list, and on those screens only — pushed destinations
 * (thread, new chat, model detail, logs) render without it. The third
 * "Design" tab is the design-lab gallery (`feature/designlab`), a visual
 * proposal to compare against these screens — not a shipped feature.
 */
@Composable
fun AppBottomBar(currentRoute: String, onSelect: (String) -> Unit) {
    val colors = LlmTheme.colors
    NavigationBar(
        containerColor = colors.surface,
        contentColor = colors.fg,
        modifier = Modifier.testTag("app_bottom_bar"),
    ) {
        TABS.forEach { tab ->
            val selected = currentRoute == tab.route
            NavigationBarItem(
                selected = selected,
                onClick = { onSelect(tab.route) },
                icon = {
                    Text(
                        tab.glyph,
                        modifier = Modifier
                            .background(
                                if (selected) colors.accentDeep else Color.Transparent,
                                RoundedCornerShape(6.dp),
                            )
                            .padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                },
                label = { Text(tab.label) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = colors.accent,
                    selectedTextColor = colors.accent,
                    unselectedIconColor = colors.subtle,
                    unselectedTextColor = colors.subtle,
                    indicatorColor = colors.accentDeep.copy(alpha = 0.35f),
                ),
                modifier = Modifier.testTag("nav_tab_${tab.route}"),
            )
        }
    }
}
