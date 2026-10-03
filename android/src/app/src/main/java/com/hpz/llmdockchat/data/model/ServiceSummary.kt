package com.hpz.llmdockchat.data.model

/** A row of `GET /api/services`. */
data class ServiceSummary(
    val name: String,
    val status: String,
    val kind: String,
    /** `host_port` server-side — the port the picker shows. 0 when the server omitted it. */
    val port: Int = 0,
    /** Set on the dashboard; the phone only ever reads it. */
    val favorite: Boolean = false,
    /** Only set when [status] is `"exited"`. */
    val exitCode: Int? = null,
    /** Weights-on-disk size, pre-formatted server-side (e.g. `"25.74 GB"`). Null when unknown. */
    val modelSizeStr: String? = null,
    /** The container's creation time, ISO-8601 UTC. Not a start time. */
    val createdAt: String? = null,
    /**
     * Reasoning levels this service declares, in declaration order —
     * never sorted, never completed. Empty when it declares none (and the
     * server collapses an invalid declaration to none too), which is what
     * hides the level control on 90 % of services.
     */
    val reasoningLevels: List<String> = emptyList(),
    /**
     * The service's `template_type` verbatim from the payload — the authoritative
     * engine id ([com.hpz.llmdockchat.data.model.engineFromTemplateType]). Null on
     * a snapshot from before the field shipped, which falls [engine] back to the
     * name prefix.
     */
    val templateType: String? = null,
) {
    val engine: Engine get() = engineFromTemplateType(templateType) ?: ModelRef.Local(name).engine

    /**
     * Chat-capable inference services only — the dashboard frontend's own
     * filter (`useRunningServices.js`), modulo its legacy `PAIR_` prefix, which
     * has no `services.json` entry and so stays UNKNOWN here: a recognised engine
     * (`template_type`, falling back to the name prefix) AND `kind == "chat"`.
     * Both halves matter: `kind` alone would let
     * `open-webui` through (it isn't in `services.json`, so its `kind`
     * defaults to `"chat"`), and the engine alone would let an embedding
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
