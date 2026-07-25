package com.hpz.llmdockchat.feature.designlab

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme

/** A tinted label — engine name, status word, port. One shape, reused everywhere
 * instead of every screen inventing its own pill. */
@Composable
fun DlChip(text: String, background: Color, foreground: Color, modifier: Modifier = Modifier) {
    Box(
        modifier
            .background(background, RoundedCornerShape(7.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(text, color = foreground, style = MaterialTheme.typography.labelSmall)
    }
}

/** Elevated surface with a real edge — border + slightly lifted fill — so
 * cards read as raised instead of just a paler rectangle on a pale page. */
@Composable
fun DlCard(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val colors = DesignLabTheme.colors
    Box(
        modifier
            .fillMaxWidth()
            .background(colors.surfaceElevated, RoundedCornerShape(16.dp))
            .border(1.dp, colors.line, RoundedCornerShape(16.dp))
            .padding(16.dp),
    ) { content() }
}

@Composable
fun DlIconBadge(icon: ImageVector, tint: Color, background: Color, modifier: Modifier = Modifier) {
    Box(
        modifier
            .background(background, RoundedCornerShape(11.dp))
            .padding(9.dp),
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier)
    }
}
