package com.hpz.llmdockchat.feature.account

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons

/**
 * The header's way into [AccountScreen]. Both list tabs render this one
 * composable so the two cannot drift, and it is a labelled control rather than
 * a logo that happens to be clickable — the gap this closes was that sign-out
 * existed but nothing in the app said where it was.
 */
@Composable
fun AccountEntry(onClick: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(onClick = onClick, modifier = modifier.testTag("account_entry")) {
        Icon(
            DesignLabIcons.Cog,
            contentDescription = "Account",
            tint = LlmTheme.colors.subtle,
            modifier = Modifier.size(22.dp),
        )
    }
}
