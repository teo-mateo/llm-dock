package com.hpz.llmdockchat.data.model

/**
 * The trimmed run shape carried on a list row (F02-R3). [status] is kept as
 * the server's raw string — [ConversationSummary.isGenerating] is the single
 * place that decides what counts as "still going".
 */
data class ActiveRun(
    val id: String,
    val status: String,
    val activeStep: String?,
    val startedAt: String?,
)

/** A row of `GET /api/chat/conversations` (F02-R1). */
data class ConversationSummary(
    val id: String,
    val title: String,
    val modelRef: ModelRef,
    val updatedAt: String?,
    val activeRun: ActiveRun?,
) {
    val engine: Engine get() = modelRef.engine

    /**
     * The server only ever attaches [activeRun] for a `queued`/`running` run
     * (`chat/db.py:_attach_active_runs`), but this checks the status anyway: a
     * null `active_run` and one carrying a terminal status must both read as
     * "not generating" (F02-R3), and a future server change that starts
     * sending terminal runs here should not light up every row.
     */
    val isGenerating: Boolean
        get() = activeRun != null && activeRun.status in GENERATING_STATUSES

    private companion object {
        val GENERATING_STATUSES = setOf("queued", "running")
    }
}
