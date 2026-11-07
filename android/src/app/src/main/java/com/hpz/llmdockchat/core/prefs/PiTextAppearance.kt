package com.hpz.llmdockchat.core.prefs

import androidx.compose.runtime.State
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlin.math.roundToInt

/**
 * How large pi response prose is drawn, independently of [ChatAppearance].
 *
 * Only the assistant text on the session screen reads this. Chrome — the
 * header, chips, composer and list rows — keeps the system scale, so the
 * setting can shrink a long answer without shrinking the controls used to
 * navigate away from it.
 */
interface PiTextAppearance {
    val scale: StateFlow<Float>
    fun setScale(scale: Float)

    companion object {
        const val DEFAULT = 1.0f
        const val MIN = 0.7f
        const val MAX = 1.4f
        const val STEP = 0.1f

        fun clampToStep(raw: Float): Float =
            (Math.round(raw / STEP) * STEP).toFloat().coerceIn(MIN, MAX)

        fun label(scale: Float): String = "${(scale * 100).roundToInt()}%"

        fun isDefault(scale: Float): Boolean = clampToStep(scale) == DEFAULT
    }
}

class DataStorePiTextAppearance(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : PiTextAppearance {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "pi_response_text_scale",
        scope = scope,
        decode = { it.toFloatOrNull()?.let(PiTextAppearance::clampToStep) },
        encode = { it.toString() },
    )

    override val scale: StateFlow<Float> = pref.flow
        .map { it.valueOrNull ?: PiTextAppearance.DEFAULT }
        .stateIn(scope, SharingStarted.Eagerly, PiTextAppearance.DEFAULT)

    override fun setScale(scale: Float) = pref.set(PiTextAppearance.clampToStep(scale))
}

class InMemoryPiTextAppearance(initial: Float = PiTextAppearance.DEFAULT) : PiTextAppearance {
    private val _scale = MutableStateFlow(PiTextAppearance.clampToStep(initial))
    override val scale: StateFlow<Float> = _scale
    override fun setScale(scale: Float) {
        _scale.value = PiTextAppearance.clampToStep(scale)
    }
}

val LocalPiTextAppearance = staticCompositionLocalOf<PiTextAppearance> { InMemoryPiTextAppearance() }
