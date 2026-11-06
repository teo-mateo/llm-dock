package com.hpz.llmdockchat.feature.modelpicker

import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.parseModelRef

/** What the remembered model resolved to. */
sealed interface RememberedModel {
    data class Resolved(val option: ModelOption) : RememberedModel

    /** Remembered, but deleted, renamed or stopped — the sheet must ask. */
    data class Unavailable(val raw: String) : RememberedModel

    /** No prior chat. */
    data object None : RememberedModel
}

/**
 * The one remembered-model ladder. The new-chat sheet and the share-summarize
 * path both start from the same preference and must reach the same
 * verdict — a summarize that silently picked a stopped model while the sheet
 * would have asked is the bug this single owner prevents.
 */
object RememberedModelResolver {
    /**
     * [preselectedServiceName] wins outright when it is running;
     * otherwise the remembered model decides. A remote or provider model no
     * longer listed is still resolved to its own ref, never replaced — the
     * lists are pickers, not allowlists, and the server reports a dead provider.
     */
    fun resolve(
        rememberedRaw: String?,
        localServices: List<ModelOption.LocalService>,
        remoteModels: List<ModelOption.Remote>,
        preselectedServiceName: String? = null,
        providerModels: List<ModelOption.ProviderModel> = emptyList(),
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
            is ModelRef.Provider -> RememberedModel.Resolved(
                providerModels.find { it.ref == ref }
                    ?: ModelOption.ProviderModel(ref.providerId, ref.providerId, ref.modelId, ref.modelId),
            )
        }
    }
}
