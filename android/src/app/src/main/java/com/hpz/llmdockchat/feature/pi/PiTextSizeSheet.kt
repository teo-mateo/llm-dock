package com.hpz.llmdockchat.feature.pi

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.prefs.LocalPiTextAppearance
import com.hpz.llmdockchat.core.prefs.PiTextAppearance
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PiTextSizeSheet(onDismiss: () -> Unit) {
    val appearance = LocalPiTextAppearance.current
    val colors = LlmTheme.colors
    val scale by appearance.scale.collectAsState()
    val baseDensity = LocalDensity.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("pi_text_size_sheet"),
    ) {
        // The sheet must not resize under the finger: the scale it edits is the
        // scale answers are drawn at, and applying it to the sheet too would
        // re-measure the control mid-press.
        CompositionLocalProvider(LocalDensity provides baseDensity) {
            LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
                item {
                    Text(
                        "Answer text size",
                        color = colors.subtle,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 10.dp),
                    )
                }
                item {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        SizeStep(
                            label = "A",
                            fontSize = 13.sp,
                            description = "Smaller answer text",
                            enabled = scale > PiTextAppearance.MIN,
                            testTag = "pi_text_size_decrease",
                            onClick = { appearance.setScale(scale - PiTextAppearance.STEP) },
                        )
                        SizeStep(
                            label = "A",
                            fontSize = 21.sp,
                            description = "Larger answer text",
                            enabled = scale < PiTextAppearance.MAX,
                            testTag = "pi_text_size_increase",
                            onClick = { appearance.setScale(scale + PiTextAppearance.STEP) },
                        )
                        Text(
                            PiTextAppearance.label(scale),
                            color = colors.muted,
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.weight(1f).testTag("pi_text_size_value"),
                        )
                        if (!PiTextAppearance.isDefault(scale)) {
                            Text(
                                "Reset",
                                color = colors.accent,
                                style = MaterialTheme.typography.labelMedium,
                                modifier = Modifier
                                    .clickable { appearance.setScale(PiTextAppearance.DEFAULT) }
                                    .padding(horizontal = 8.dp, vertical = 6.dp)
                                    .testTag("pi_text_size_reset"),
                            )
                        }
                    }
                }
                item {
                    Text(
                        "Only pi answers change size. Buttons, rows and the composer follow the system text size.",
                        color = colors.subtle,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 16.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun SizeStep(
    label: String,
    fontSize: TextUnit,
    description: String,
    enabled: Boolean,
    testTag: String,
    onClick: () -> Unit,
) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .size(44.dp)
            .background(colors.surfaceHigh, RoundedCornerShape(12.dp))
            .clickable(enabled = enabled, onClick = onClick, role = Role.Button)
            .semantics { contentDescription = description }
            .testTag(testTag),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (enabled) colors.fg else colors.subtle,
            fontSize = fontSize,
        )
    }
}
