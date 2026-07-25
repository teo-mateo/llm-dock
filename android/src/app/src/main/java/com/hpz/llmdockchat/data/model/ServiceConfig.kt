package com.hpz.llmdockchat.data.model

/**
 * The stored config behind one service (F11-R2), read-only. [flags] renders
 * `params` as flag/value pairs in server order — good enough to read as the
 * equivalent command line without this client re-implementing
 * `flag_metadata.render_cli_flag`. Never carries `api_key`: [[F11-model-detail-and-control.md]]'s
 * R2 says it must not appear, so the mapper never reads it off the wire.
 */
data class ServiceConfig(
    val modelPath: String?,
    val modelName: String?,
    val flags: List<Pair<String, String>>,
    val templateType: String?,
    val modelSizeStr: String?,
)
