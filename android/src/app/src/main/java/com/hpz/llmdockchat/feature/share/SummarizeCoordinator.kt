package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.NewChatPreferences
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.UrlRetrieval
import com.hpz.llmdockchat.data.model.wireValue
import com.hpz.llmdockchat.feature.modelpicker.RememberedModel
import com.hpz.llmdockchat.feature.modelpicker.RememberedModelResolver

/** Where a summarize tap lands. */
sealed interface SummarizeOutcome {
    /** The thread exists, tools are on it, and its claim is waiting to be sent. */
    data class Opened(val conversationId: String) : SummarizeOutcome

    /** No usable remembered model — the sheet takes over with the intent intact. */
    data object ChooseModel : SummarizeOutcome

    /** Nothing was sent. The picker stays put with the reason on screen. */
    data class Failed(val message: String) : SummarizeOutcome
}

/** What the picker needs; faked in tests around [SummarizeCoordinator]. */
interface SummarizeLauncher {
    suspend fun probe(): Result<UrlRetrieval>

    suspend fun launch(url: String, serverIds: List<String>): SummarizeOutcome
}

/**
 * The direct path: create a thread on the remembered model, put the
 * URL-fetching server on it, file the claim, and hand the caller the id to
 * open. Every step is one round trip and none of them starts a container, so
 * the tap costs what the server already had to do anyway.
 *
 * Tools are written before the claim because `send_message` reads
 * `mcp_servers_json` off the stored row — a thread without the fetcher would
 * answer the instruction from the URL alone, which is the failure this whole
 * feature exists to prevent. A failed tools write therefore files nothing:
 * the created thread is orphaned and empty rather than ready to lie.
 */
class SummarizeCoordinator(
    private val servicesRepository: ServicesRepository,
    private val openRouterModelsRepository: OpenRouterModelsRepository,
    private val mcpServersRepository: McpServersRepository,
    private val conversationsRepository: ConversationsRepository,
    private val preferences: NewChatPreferences,
    private val store: SharedDraftStore,
) : SummarizeLauncher {

    override suspend fun probe(): Result<UrlRetrieval> = mcpServersRepository.urlFetchProbe()

    override suspend fun launch(url: String, serverIds: List<String>): SummarizeOutcome {
        val services = servicesRepository.list()
            .getOrElse { return SummarizeOutcome.Failed(it.appError.displayMessage) }
        val remote = openRouterModelsRepository.list().getOrNull()

        return when (
            val model = RememberedModelResolver.resolve(
                rememberedRaw = preferences.lastModel(),
                localServices = services.filter { it.isChatCapable }.map { ModelOption.LocalService(it.name, it.status) },
                remoteModels = remote?.models.orEmpty(),
            )
        ) {
            is RememberedModel.Resolved -> createAndClaim(model.option.ref.wireValue, url, serverIds)
            is RememberedModel.Unavailable, RememberedModel.None -> SummarizeOutcome.ChooseModel
        }
    }

    private suspend fun createAndClaim(mainService: String, url: String, serverIds: List<String>): SummarizeOutcome {
        val conversationId = conversationsRepository.create(mainService = mainService)
            .getOrElse { return SummarizeOutcome.Failed(it.appError.displayMessage) }

        conversationsRepository.setMcpServers(conversationId, serverIds)
            .getOrElse {
                return SummarizeOutcome.Failed(
                    "The thread was created but its page-fetch tool couldn't be enabled: " +
                        "${it.appError.displayMessage}. Nothing was sent.",
                )
            }

        store.stageForAutoSend(conversationId, SummarizeMessage.build(url))
        return SummarizeOutcome.Opened(conversationId)
    }
}
