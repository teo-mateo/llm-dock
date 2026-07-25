package com.hpz.llmdockchat.core.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.graphics.Color

/**
 * Follows the system theme (F00-R7). No dynamic colour: the palette is part of
 * the product identity and has to match the desktop dashboard, so wallpaper
 * extraction would be a regression, not a feature.
 */
@Composable
fun LLMDockChatTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkLlmColors else LightLlmColors
    CompositionLocalProvider(LocalLlmColors provides colors) {
        MaterialTheme(
            colorScheme = colors.toColorScheme(darkTheme),
            typography = Typography,
            content = content,
        )
    }
}

/** Shorthand for the semantic tokens: `LlmTheme.colors.muted`. */
object LlmTheme {
    val colors: LlmColors
        @Composable @ReadOnlyComposable get() = LocalLlmColors.current
}

/**
 * Material components that the app does not style by hand still have to land
 * inside the palette, so every M3 role is mapped onto a token.
 */
private fun LlmColors.toColorScheme(dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = accent,
        onPrimary = onAccent,
        primaryContainer = accentDeep,
        onPrimaryContainer = if (dark) fg else onAccent,
        secondary = purple,
        onSecondary = onAccent,
        secondaryContainer = surfaceElevated,
        onSecondaryContainer = fg,
        tertiary = green,
        onTertiary = onAccent,
        background = app,
        onBackground = fg,
        surface = surface,
        onSurface = fg,
        surfaceVariant = surfaceElevated,
        onSurfaceVariant = muted,
        surfaceTint = accent,
        surfaceDim = app,
        surfaceBright = surfaceElevated,
        surfaceContainerLowest = app,
        surfaceContainerLow = sunken,
        surfaceContainer = surface,
        surfaceContainerHigh = surfaceElevated,
        surfaceContainerHighest = surfaceElevated,
        inverseSurface = fg,
        inverseOnSurface = app,
        inversePrimary = accentDeep,
        error = red,
        onError = Color(0xFFFFFFFF),
        errorContainer = surfaceElevated,
        onErrorContainer = red,
        outline = subtle,
        outlineVariant = lineStrong,
        scrim = Color(0xCC000000),
    )
}
