package com.hpz.llmdockchat.navigation

import androidx.compose.foundation.layout.size
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons

private data class Tab(val route: String, val label: String, val icon: ImageVector)

// Line icons rather than emoji: the emoji rendered at the system font's own
// weight and colour, so a selected tab could not tint them and ▦ in
// particular read as a rendering artefact. These are the same stroke glyphs
// the design lab draws (`feature/designlab/icons`), which is the only vector
// icon set on this classpath — `material-icons-extended` is not a dependency.
private val TABS = listOf(
    Tab(Destinations.CHATS, "Chats", DesignLabIcons.ChatBubble),
    Tab(Destinations.MODELS, "Models", DesignLabIcons.Chip),
    Tab(Destinations.DESIGN, "Design", DesignLabIcons.Sparkle),
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
                modifier = Modifier.testTag("nav_tab_${tab.route}"),
            )
        }
    }
}
