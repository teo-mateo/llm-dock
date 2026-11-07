package com.hpz.llmdockchat.navigation

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.icons.AppIcons
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

data class BottomTab(val route: String, val label: String, val icon: ImageVector) {
    val testTag: String get() = "nav_tab_$route"
}

// Shipped destinations only. Line icons rather than emoji: the emoji rendered
// at the system font's own weight and colour, so a selected tab could not tint
// them and a box glyph read as a rendering artefact. These are the same stroke
// glyphs the rest of the app draws (`core/ui/icons`), which is the only vector
// icon set on this classpath — `material-icons-extended` is not a dependency.
internal val BOTTOM_TABS = listOf(
    BottomTab(Destinations.CHATS, "Chats", AppIcons.ChatBubble),
    BottomTab(Destinations.MODELS, "Models", AppIcons.Chip),
    BottomTab(Destinations.PI, "Pi", AppIcons.Terminal),
)

/**
 * The bottom bar: present on the tab screens only — pushed destinations
 * (thread, new chat, model detail, logs) render without it.
 */
@Composable
fun AppBottomBar(currentRoute: String, onSelect: (String) -> Unit) {
    val colors = LlmTheme.colors
    NavigationBar(
        containerColor = colors.surface,
        contentColor = colors.fg,
        modifier = Modifier.testTag("app_bottom_bar"),
    ) {
        BOTTOM_TABS.forEach { tab ->
            val selected = currentRoute == tab.route
            NavigationBarItem(
                selected = selected,
                onClick = { onSelect(tab.route) },
                icon = {
                    Icon(
                        imageVector = tab.icon,
                        contentDescription = null,
                        // No background of our own: NavigationBarItem already
                        // draws `indicatorColor` behind the selected icon, and
                        // stacking accentDeep on top of it put a dark glyph on
                        // a dark pill.
                        modifier = Modifier.size(24.dp),
                    )
                },
                label = { Text(tab.label) },
                colors = NavigationBarItemDefaults.colors(
                    // Dark glyph on a pale wash of the accent. The previous
                    // pairing was accent-on-accentDeep — both blues, so the
                    // selected icon disappeared into its own indicator.
                    selectedIconColor = colors.accentDeep,
                    selectedTextColor = colors.accentDeep,
                    unselectedIconColor = colors.subtle,
                    unselectedTextColor = colors.subtle,
                    indicatorColor = colors.accent.copy(alpha = 0.14f),
                ),
                modifier = Modifier.testTag(tab.testTag),
            )
        }
    }
}
