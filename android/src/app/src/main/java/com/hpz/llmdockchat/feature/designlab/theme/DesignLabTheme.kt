package com.hpz.llmdockchat.feature.designlab.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Design-lab proposal tokens (feature/designlab only). These are a sandbox —
 * the real app theme lives in `core/ui/theme` and is untouched. This palette
 * starts from `docs/android/chat-app-mockups.html`'s `--d-*` custom
 * properties (the ones the owner said already look better than the app) and
 * pushes further: a truer black app background, one accent doing real work
 * (violet, not the mockup's blue — chosen so accent chips don't collide with
 * the "running" green or the streaming amber), and a light theme built on
 * warm ink-on-paper rather than grey-on-white so both modes have an actual
 * contrast floor instead of everything living within one flat band.
 */
@Immutable
data class DesignLabColors(
    val app: Color,
    val appGradient: Brush,
    val surface: Color,
    val surfaceElevated: Color,
    val surfaceHigh: Color,
    val sunken: Color,
    val fg: Color,
    val muted: Color,
    val subtle: Color,
    val line: Color,
    val lineStrong: Color,
    val accent: Color,
    val accentSoft: Color,
    val onAccent: Color,
    val streaming: Color,
    val green: Color,
    val amber: Color,
    val red: Color,
    val chipBg: Color,
    val chipFg: Color,
)

val DesignLabDark = DesignLabColors(
    app = Color(0xFF05070A),
    appGradient = Brush.verticalGradient(listOf(Color(0xFF0A0E16), Color(0xFF05070A))),
    surface = Color(0xFF11141C),
    surfaceElevated = Color(0xFF171B26),
    surfaceHigh = Color(0xFF1F2432),
    sunken = Color(0xFF090B10),
    fg = Color(0xFFF7F8FA),
    muted = Color(0xFFA8B0C0),
    subtle = Color(0xFF6D7590),
    line = Color(0x2BAEB8CE),
    lineStrong = Color(0x4DAEB8CE),
    accent = Color(0xFF8B7CFF),
    accentSoft = Color(0x2E8B7CFF),
    onAccent = Color(0xFF0B0710),
    streaming = Color(0xFFFFB454),
    green = Color(0xFF34D399),
    amber = Color(0xFFFBBF24),
    red = Color(0xFFFB7185),
    chipBg = Color(0x2E8B7CFF),
    chipFg = Color(0xFFC7BEFF),
)

val DesignLabLight = DesignLabColors(
    app = Color(0xFFF1EFEA),
    appGradient = Brush.verticalGradient(listOf(Color(0xFFF7F5F0), Color(0xFFF1EFEA))),
    surface = Color(0xFFFFFFFF),
    surfaceElevated = Color(0xFFFFFFFF),
    surfaceHigh = Color(0xFFEDEAE2),
    sunken = Color(0xFFE7E3D9),
    fg = Color(0xFF181410),
    muted = Color(0xFF4E4A44),
    subtle = Color(0xFF7A756C),
    line = Color(0x2618140F),
    lineStrong = Color(0x4018140F),
    accent = Color(0xFF5B3DF6),
    accentSoft = Color(0x1F5B3DF6),
    onAccent = Color(0xFFFFFFFF),
    streaming = Color(0xFFB25E00),
    green = Color(0xFF12805C),
    amber = Color(0xFFB25E00),
    red = Color(0xFFC0324A),
    chipBg = Color(0x1F5B3DF6),
    chipFg = Color(0xFF4530C4),
)

val LocalDesignLabColors = staticCompositionLocalOf { DesignLabDark }

object DesignLabTheme {
    val colors: DesignLabColors
        @Composable @ReadOnlyComposable get() = LocalDesignLabColors.current
}

/** Deliberately bigger jumps between weights than the real app's Typography —
 * the point of this sandbox is to test more hierarchy, not the same amount. */
val DesignLabTypography = Typography(
    displaySmall = TextStyle(fontWeight = FontWeight.Bold, fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.3).sp),
    titleLarge = TextStyle(fontWeight = FontWeight.Bold, fontSize = 21.sp, lineHeight = 26.sp, letterSpacing = (-0.2).sp),
    titleMedium = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 21.sp),
    bodyLarge = TextStyle(fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 24.sp, letterSpacing = 0.1.sp),
    bodyMedium = TextStyle(fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 21.sp, letterSpacing = 0.1.sp),
    labelLarge = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 13.sp, lineHeight = 17.sp, letterSpacing = 0.2.sp),
    labelMedium = TextStyle(fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 0.2.sp),
    labelSmall = TextStyle(fontWeight = FontWeight.Medium, fontSize = 10.5.sp, lineHeight = 14.sp, letterSpacing = 0.4.sp),
)

@Composable
fun DesignLabTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (darkTheme) DesignLabDark else DesignLabLight
    CompositionLocalProvider(LocalDesignLabColors provides colors) {
        MaterialTheme(typography = DesignLabTypography, content = content)
    }
}
