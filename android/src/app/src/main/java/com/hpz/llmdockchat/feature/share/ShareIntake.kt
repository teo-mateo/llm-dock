package com.hpz.llmdockchat.feature.share

import android.content.Intent
import java.security.MessageDigest

/** What the activity does with a delivered `ACTION_SEND` intent. */
enum class ShareIntake { Stage, KeepHydrated, IgnoreRedelivery }

/**
 * Identity of one share delivery, and the mark this app stamps into an intent
 * it has served. The extra is written by no other app and no other code path,
 * so its presence on a redelivered intent is unambiguous evidence of
 * redelivery rather than arrival.
 */
object ShareDeliveryToken {
    const val EXTRA_MARK = "com.hpz.llmdockchat.extra.SHARE_DELIVERY_TOKEN"

    fun of(
        action: String,
        mimeType: String?,
        text: String?,
        streamUri: String?,
        title: String?,
        subject: String?,
    ): String {
        val raw = listOf(action, mimeType, text, streamUri, title, subject)
            .joinToString("\u0000") { it.orEmpty() }
        return MessageDigest.getInstance("SHA-256")
            .digest(raw.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
            .take(16)
    }

    fun mark(intent: Intent, token: String) {
        intent.putExtra(EXTRA_MARK, token)
    }
}

/**
 * The consume-once gate for share intents. Takes primitives, not
 * an `Intent`, so the rules are JVM-testable over the throwing android.jar
 * stubs — the [SharedKindParser] arrangement.
 *
 * Arm order is load-bearing in two places. The mark (arm 2) precedes the
 * new-intent arm (3) because a marked intent is the launch intent coming back,
 * never a fresh delivery. The handled-token check (arm 4) follows the
 * new-intent arm so identity can only ever refuse a *restore*: a payload
 * shared twice while the app is open is indistinguishable from a replay by
 * content, and the second one wins.
 */
object ShareIntakeGate {
    fun decide(
        action: String?,
        viaNewIntent: Boolean,
        marked: Boolean,
        launchedFromHistory: Boolean,
        hasSavedState: Boolean,
        token: String,
        handledToken: String?,
    ): ShareIntake = when {
        action != SharedKindParser.ACTION_SEND -> ShareIntake.IgnoreRedelivery
        marked -> ShareIntake.IgnoreRedelivery
        viaNewIntent && !launchedFromHistory -> ShareIntake.Stage
        token == handledToken -> ShareIntake.IgnoreRedelivery
        hasSavedState || launchedFromHistory -> ShareIntake.KeepHydrated
        else -> ShareIntake.Stage
    }
}
