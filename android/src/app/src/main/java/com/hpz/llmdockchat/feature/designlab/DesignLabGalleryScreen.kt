package com.hpz.llmdockchat.feature.designlab

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme
import kotlinx.coroutines.launch

private data class MockScreen(val label: String, val content: @Composable () -> Unit)

private val MOCK_SCREENS = listOf(
    MockScreen("Chat list") { MockChatListScreen() },
    MockScreen("Chat thread") { MockChatThreadScreen() },
    MockScreen("Models list") { MockModelsListScreen() },
    MockScreen("Model detail") { MockModelDetailScreen() },
)

/**
 * The Design tab's gallery (owner's brief): cycle through the four mockups,
 * with the current screen's name visible, and a light/dark toggle so both
 * variants of the proposal are reachable without a system setting change.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun DesignLabGalleryScreen() {
    var darkPreview by remember { mutableStateOf(true) }
    val pagerState = rememberPagerState(pageCount = { MOCK_SCREENS.size })
    val scope = rememberCoroutineScope()

    DesignLabTheme(darkTheme = darkPreview) {
        val colors = DesignLabTheme.colors
        Column(Modifier.fillMaxSize().background(colors.app).testTag("design_lab_gallery")) {
            Row(
                Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("Design lab", style = MaterialTheme.typography.titleLarge, color = colors.fg)
                    Text(
                        MOCK_SCREENS[pagerState.currentPage].label,
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.accent,
                        modifier = Modifier.testTag("design_lab_current_label"),
                    )
                }
                ThemeToggle(darkPreview) { darkPreview = it }
            }

            Box(Modifier.weight(1f)) {
                HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
                    MOCK_SCREENS[page].content()
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                NavButton(DesignLabIcons.Back, "Previous mockup", enabled = pagerState.currentPage > 0) {
                    scope.launch { pagerState.animateScrollToPage(pagerState.currentPage - 1) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    MOCK_SCREENS.indices.forEach { index ->
                        Box(
                            Modifier
                                .size(if (index == pagerState.currentPage) 9.dp else 7.dp)
                                .background(
                                    if (index == pagerState.currentPage) colors.accent else colors.subtle,
                                    CircleShape,
                                ),
                        )
                    }
                }
                NavButton(DesignLabIcons.ChevronRight, "Next mockup", enabled = pagerState.currentPage < MOCK_SCREENS.lastIndex) {
                    scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) }
                }
            }
        }
    }
}

@Composable
private fun NavButton(icon: androidx.compose.ui.graphics.vector.ImageVector, description: String, enabled: Boolean, onClick: () -> Unit) {
    val colors = DesignLabTheme.colors
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier
            .size(48.dp)
            .background(colors.surfaceElevated, RoundedCornerShape(14.dp)),
    ) {
        Icon(icon, contentDescription = description, tint = if (enabled) colors.fg else colors.subtle)
    }
}

@Composable
private fun ThemeToggle(dark: Boolean, onChange: (Boolean) -> Unit) {
    val colors = DesignLabTheme.colors
    Row(
        Modifier
            .background(colors.surfaceHigh, RoundedCornerShape(20.dp))
            .padding(3.dp),
    ) {
        ToggleOption("Dark", selected = dark) { onChange(true) }
        ToggleOption("Light", selected = !dark) { onChange(false) }
    }
}

@Composable
private fun ToggleOption(label: String, selected: Boolean, onClick: () -> Unit) {
    val colors = DesignLabTheme.colors
    Box(
        Modifier
            .background(if (selected) colors.accent else androidx.compose.ui.graphics.Color.Transparent, RoundedCornerShape(17.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .testTag("design_lab_toggle_$label"),
    ) {
        Text(
            label,
            color = if (selected) colors.onAccent else colors.muted,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}

@Preview(name = "Design lab gallery", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun DesignLabGalleryPreview() {
    DesignLabGalleryScreen()
}
