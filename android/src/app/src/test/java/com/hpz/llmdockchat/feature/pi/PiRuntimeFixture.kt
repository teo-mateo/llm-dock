package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.data.PiSessionEventsRepository
import com.hpz.llmdockchat.data.model.PiSessionKey
import java.io.File
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

internal class PiRuntimeFixture(
    directory: File,
    val scope: CoroutineScope,
    private val dispatcher: CoroutineDispatcher = Dispatchers.Unconfined,
    private val clock: () -> Long = { 1_000L },
    files: PiSnapshotFiles = PiSnapshotFiles(directory),
) {
    var server = BaseUrl.restore("https://example.com")!!
    val store = PiSessionSnapshotStore(directory, scope, dispatcher, clock, files = files)
    val cache: PiSessionCache = PiSessionCache(store, scope, { server }, { !auth.authenticationRequired.value })
    val auth: SessionState = SessionState(cache::invalidate)

    fun switch(server: BaseUrl) {
        this.server = server
        cache.invalidate()
    }

    fun runtime(transport: SseTransport, key: PiSessionKey = PiSessionKey("s1", "i1")) = PiSessionRuntime(
        key, PiSessionEventsRepository(transport), cache, dispatcher, clock, clock,
    )
}

internal fun piSummary(firstSeen: Long = 100, session: String = "s1", instance: String = "i1"): String =
    """{"type":"session","session_id":"$session","instance_id":"$instance","name":"session",
        "cwd":"/repo","first_seen":$firstSeen,"last_seen":200,"live":true,"state":"working"}"""

internal fun piBatch(seq: Long, text: String): String = """{"type":"events","events":[
    {"seq":$seq,"type":"assistant_delta","ts":$seq,"payload":{"text":"$text"}}
]}"""
