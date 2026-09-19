package com.hpz.llmdockchat.feature.modelpicker

import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.parseModelRef

/** What the remembered model resolved to (F03-R1). */
sealed interface RememberedModel {
    data class Resolved(val option: ModelOption) : RememberedModel

    /** Remembered, but deleted, renamed or stopped — the sheet must ask (F03-R1's fourth criterion). */
    data class Unavailable(val raw: String) : RememberedModel

    /** No prior chat. */
    data object None : RememberedModel
}

/**
 * The one remembered-model ladder. The new-chat sheet and the share-summarize
 * path (F14-R7) both start from the same preference and must reach the same
 * verdict — a summarize that silently picked a stopped model while the sheet
 * would have asked is the bug this single owner prevents.
 */
object RememberedModelResolver {
    /**
     * [preselectedServiceName] (F10-R6) wins outright when it is running;
     * otherwise the remembered model decides. A remote model dropped from the
     * curated list is still valid — the list is a picker, not an allowlist.
     */
    fun resolve(
        rememberedRaw: String?,
        localServices: List<ModelOption.LocalService>,
        remoteModels: List<ModelOption.Remote>,
        preselectedServiceName: String? = null,
    ): RememberedModel {
        preselectedServiceName
            ?.let { name -> localServices.find { it.serviceName == name } }
            ?.takeIf { it.isRunning }
            ?.let { return RememberedModel.Resolved(it) }

        val raw = rememberedRaw ?: return RememberedModel.None
        return when (val ref = parseModelRef(raw)) {
            is ModelRef.Local -> {
                val match = localServices.find { it.serviceName == ref.serviceName }
                if (match != null && match.isRunning) {
                    RememberedModel.Resolved(match)
                } else {
                    RememberedModel.Unavailable(raw)
                }
            }
            is ModelRef.OpenRouter -> RememberedModel.Resolved(
                remoteModels.find { it.modelId == ref.modelId } ?: ModelOption.Remote(ref.modelId, ref.modelId),
            )
        }
    }
}
