package com.hpz.llmdockchat.data.model

/**
 * The stored config behind one service, read-only. [flags] renders
 * `params` as flag/value pairs in server order — good enough to read as the
 * equivalent command line without this client re-implementing
 * `flag_metadata.render_cli_flag`. Never carries `api_key`: it must not
  * appear on the wire, so the mapper never reads it.
 */
data class ServiceConfig(
    val modelPath: String?,
    val modelName: String?,
    val flags: List<Pair<String, String>>,
    val templateType: String?,
    val modelSizeStr: String?,
)
