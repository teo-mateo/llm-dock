package com.hpz.llmdockchat.data.model

/** A row of `GET /api/services` (F03, F10). */
data class ServiceSummary(
    val name: String,
    val status: String,
    val kind: String,
) {
    val engine: Engine get() = ModelRef.Local(name).engine

    /**
     * Chat-capable inference services only — the same filter the dashboard
     * frontend applies in `useRunningServices.js`: a recognised engine prefix
     * AND `kind == "chat"`. Both halves matter: `kind` alone would let
     * `open-webui` through (it isn't in `services.json`, so its `kind`
     * defaults to `"chat"`), and the prefix alone would let an embedding
     * service through.
     */
    val isChatCapable: Boolean get() = engine != Engine.UNKNOWN && kind == "chat"

    val isRunning: Boolean get() = status == "running"
}
