package com.hpz.llmdockchat.data.model

/** A row of `GET /api/services` (F03, F07, F10). */
data class ServiceSummary(
    val name: String,
    val status: String,
    val kind: String,
    /** `host_port` server-side — the port the picker shows (F07-R1). 0 when the server omitted it. */
    val port: Int = 0,
    /** Set on the dashboard; the phone only ever reads it (F07-R5). */
    val favorite: Boolean = false,
    /** Only set when [status] is `"exited"` (F10-R1's third criterion). */
    val exitCode: Int? = null,
    /** Weights-on-disk size, pre-formatted server-side (e.g. `"25.74 GB"`). Null when unknown. */
    val modelSizeStr: String? = null,
    /** The container's creation time, ISO-8601 UTC. Not a start time — see [[F10-models-list.md]]'s Deviations. */
    val createdAt: String? = null,
) {
    val engine: Engine get() = ModelRef.Local(name).engine

    /**
     * Chat-capable inference services only — the same filter the dashboard
     * frontend applies in `useRunningServices.js`: a recognised engine prefix
     * AND `kind == "chat"`. Both halves matter: `kind` alone would let
     * `open-webui` through (it isn't in `services.json`, so its `kind`
     * defaults to `"chat"`), and the prefix alone would let an embedding
     * service through.
     *
     * A blank `kind` counts as `"chat"` too — `useRunningServices.js` reads
     * `(s.kind || 'chat') === kind` for exactly this reason (a snapshot from
     * before the `kind` column existed must not filter everything out).
     */
    val isChatCapable: Boolean get() = engine != Engine.UNKNOWN && (kind.isBlank() || kind == "chat")

    val isRunning: Boolean get() = status == "running"
    val isExited: Boolean get() = status == "exited"
    val isNotCreated: Boolean get() = status == "not-created"
}
