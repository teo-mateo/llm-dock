package com.hpz.llmdockchat.core.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/**
 * The app's semantic colour tokens (Architecture D11). Screens reference these,
 * never a literal — a hardcoded hex is a light-mode bug waiting to happen.
 *
 * Dark is the mockups' palette verbatim (`docs/android/chat-app-mockups.html`,
 * the `--d-*` custom properties). Light is derived: same hierarchy, same accent
 * family, surfaces inverted. The engine chip pairs come from the dashboard's own
 * badges (`dashboard/frontend/src/index.css`), which already ships both themes,
 * so a thread's chip reads the same on the phone as on the desktop.
 */
@Immutable
data class LlmColors(
    val app: Color,
    /**
     * The app background as a brush. A flat fill was the single biggest reason
     * the screens read as "washed out": every surface sat in one narrow band,
     * so nothing looked lifted. Screens that want the flat colour still use
     * [app] — this is for the full-bleed backdrop of a list.
     */
    val appGradient: Brush,
    val surface: Color,
    val surfaceElevated: Color,
    /** One step above [surfaceElevated] — icon badges and neutral chips. */
    val surfaceHigh: Color,
    val sunken: Color,
    val fg: Color,
    val muted: Color,
    val subtle: Color,
    val line: Color,
    val lineStrong: Color,
    val accent: Color,
    /** A wash of [accent] — tinted badges and selected states. */
    val accentSoft: Color,
    val accentDeep: Color,
    val onAccent: Color,
    val green: Color,
    val amber: Color,
    val red: Color,
    val purple: Color,
    val engineLlamaCpp: ChipColors,
    val engineVllm: ChipColors,
    val engineDs4: ChipColors,
    val engineOpenRouter: ChipColors,
    val engineUnknown: ChipColors,
    val logError: Color,
    val logWarn: Color,
    val logInfo: Color,
    val logPlain: Color,
)

/** A chip's tinted background and its legible foreground, as a pair. */
@Immutable
data class ChipColors(val background: Color, val foreground: Color)

val DarkLlmColors = LlmColors(
    app = Color(0xFF0B0F15),
    appGradient = Brush.verticalGradient(listOf(Color(0xFF141B29), Color(0xFF0B0F15))),
    surface = Color(0xFF161C27),
    surfaceElevated = Color(0xFF1E2634),
    surfaceHigh = Color(0xFF273143),
    sunken = Color(0xFF11161F),
    fg = Color(0xFFF3F4F6),
    muted = Color(0xFF9CA3AF),
    subtle = Color(0xFF6B7280),
    line = Color(0x2194A3B8),
    lineStrong = Color(0x3D94A3B8),
    accent = Color(0xFF3B82F6),
    accentSoft = Color(0x333B82F6),
    accentDeep = Color(0xFF1E3A8A),
    onAccent = Color(0xFFFFFFFF),
    green = Color(0xFF22C55E),
    amber = Color(0xFFF59E0B),
    red = Color(0xFFEF4444),
    purple = Color(0xFFA855F7),
    engineLlamaCpp = ChipColors(Color(0x4D2563EB), Color(0xFF93C5FD)),
    engineVllm = ChipColors(Color(0x4D9333EA), Color(0xFFD8B4FE)),
    engineDs4 = ChipColors(Color(0x4DEA580C), Color(0xFFFDBA74)),
    engineOpenRouter = ChipColors(Color(0x4D059669), Color(0xFF6EE7B7)),
    engineUnknown = ChipColors(Color(0x4D4B5563), Color(0xFF9CA3AF)),
    logError = Color(0xFFF87171),
    logWarn = Color(0xFFF59E0B),
    logInfo = Color(0xFF60A5FA),
    logPlain = Color(0xFFD1D5DB),
)

val LightLlmColors = LlmColors(
    app = Color(0xFFF5F6F8),
    appGradient = Brush.verticalGradient(listOf(Color(0xFFFFFFFF), Color(0xFFEDF0F5))),
    surface = Color(0xFFFFFFFF),
    surfaceElevated = Color(0xFFEDF0F4),
    surfaceHigh = Color(0xFFE1E6EE),
    sunken = Color(0xFFE7EAEF),
    fg = Color(0xFF12161D),
    muted = Color(0xFF56606F),
    subtle = Color(0xFF6B7684),
    line = Color(0x1F12161D),
    lineStrong = Color(0x3812161D),
    accent = Color(0xFF2563EB),
    accentSoft = Color(0x242563EB),
    accentDeep = Color(0xFF1D4ED8),
    onAccent = Color(0xFFFFFFFF),
    green = Color(0xFF15803D),
    amber = Color(0xFFB45309),
    red = Color(0xFFDC2626),
    purple = Color(0xFF7E22CE),
    engineLlamaCpp = ChipColors(Color(0x1F2563EB), Color(0xFF1D4ED8)),
    engineVllm = ChipColors(Color(0x1F9333EA), Color(0xFF7E22CE)),
    engineDs4 = ChipColors(Color(0x1FEA580C), Color(0xFFC2410C)),
    engineOpenRouter = ChipColors(Color(0x1F059669), Color(0xFF047857)),
    engineUnknown = ChipColors(Color(0x1F64748B), Color(0xFF475569)),
    logError = Color(0xFFB91C1C),
    logWarn = Color(0xFFB45309),
    logInfo = Color(0xFF1D4ED8),
    logPlain = Color(0xFF1F2937),
)

val LocalLlmColors = staticCompositionLocalOf { DarkLlmColors }
