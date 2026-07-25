package com.hpz.llmdockchat.core.prefs

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.SharingStarted

/**
 * How large chat text is drawn, on top of whatever the system font scale
 * already says.
 *
 * This is app-wide appearance, not thread state, so it deliberately does not
 * live on a ViewModel: a thread's ViewModel is keyed by conversation id, and a
 * per-thread copy would mean the size you just chose reverts the moment you
 * open a different chat. It is read through [LocalChatAppearance] instead.
 *
 * The value multiplies the *font* scale only — `dp` is untouched — so padding,
 * icons and touch targets keep their sizes while every `sp` in the subtree
 * grows. See `ThreadScreen`'s density override for where that is applied.
 */
interface ChatAppearance {
    val textScale: StateFlow<Float>
    fun setTextScale(scale: Float)

    companion object {
        const val DEFAULT = 1.0f
        const val MIN = 0.8f
        const val MAX = 1.6f
        const val STEP = 0.1f

        /**
         * Rounded to the step grid, because repeated `+ 0.1f` on a Float drifts
         * (0.7999999f), and a value one ulp below [DEFAULT] would leave "Reset"
         * looking available on a thread that is already at default size.
         */
        fun clampToStep(raw: Float): Float =
            (Math.round(raw / STEP) * STEP).coerceIn(MIN, MAX)
    }
}

class DataStoreChatAppearance(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : ChatAppearance {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "chat_text_scale",
        scope = scope,
        decode = { it.toFloatOrNull()?.let(ChatAppearance::clampToStep) },
        encode = { it.toString() },
    )

    // Loading and unset both mean "no preference expressed", which for a font
    // size is simply the default — unlike a server URL, there is no state where
    // the screen must wait to find out.
    override val textScale: StateFlow<Float> = pref.flow
        .map { it.valueOrNull ?: ChatAppearance.DEFAULT }
        .stateIn(scope, SharingStarted.Eagerly, ChatAppearance.DEFAULT)

    override fun setTextScale(scale: Float) = pref.set(ChatAppearance.clampToStep(scale))
}

/** For previews and tests — holds the value, persists nothing. */
class InMemoryChatAppearance(initial: Float = ChatAppearance.DEFAULT) : ChatAppearance {
    private val _textScale = MutableStateFlow(initial)
    override val textScale: StateFlow<Float> = _textScale
    override fun setTextScale(scale: Float) {
        _textScale.value = ChatAppearance.clampToStep(scale)
    }
}

val LocalChatAppearance = staticCompositionLocalOf<ChatAppearance> { InMemoryChatAppearance() }
