package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.data.PiSessionEventsRepository
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiTranscript
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.job
import kotlinx.coroutines.launch

private class PiFirstSeenChanged(val firstSeen: Long) : RuntimeException()
private class PiWrongSummary : RuntimeException()

internal class PiSessionRuntime(
    private val key: PiSessionKey,
    private val repository: PiSessionEventsRepository,
    private val cache: PiSessionCache,
    private val dispatcher: CoroutineDispatcher = Dispatchers.Default,
    private val clock: () -> Long = System::currentTimeMillis,
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
) {
    private val mutableState = MutableStateFlow<PiSessionUiState>(PiSessionUiState.Loading)
    val state = mutableState.asStateFlow()
    private var started = false
    private var job: Job? = null
    @Volatile private var lease: PiCacheLease? = null
    @Volatile private var writer: PiCheckpointWriter? = null

    fun start(scope: CoroutineScope) {
        if (started) return
        started = true
        job = scope.launch(dispatcher) { run() }
    }

    fun flush() {
        val pending = writer ?: return
        cache.scope.launch(dispatcher) { pending.flush() }
    }

    fun stop() { job?.cancel() }

    fun commandServer(): BaseUrl? {
        val lease = lease ?: return null
        if ((state.value as? PiSessionUiState.Loaded)?.commandsAvailable != true || !cache.current(lease)) return null
        return BaseUrl.restore(lease.identity.server)
    }

    private suspend fun run() {
        val owner = currentCoroutineContext().job
        val active = cache.open(key) { removed ->
            mutableState.value = if (removed) PiSessionUiState.Unknown else PiSessionUiState.Loading
            owner.cancel()
        } ?: return
        lease = active
        try {
            resume(active)
        } catch (error: CancellationException) {
            if (!cache.current(active) && state.value !is PiSessionUiState.Unknown) mutableState.value = PiSessionUiState.Loading
            throw error
        } catch (error: ApiException) {
            if (error.error == AppError.Unauthenticated) cache.invalidate() else throw error
        } catch (_: PiWrongSummary) {
            fail(active, "The dashboard returned a different session. Reopen this session.")
        } finally {
            writer?.close()
            writer = null
            cache.release(active)
            lease = null
        }
    }

    private suspend fun resume(active: PiCacheLease) {
        var session = cache.read(active).let { seed ->
            PiTranscriptSession(seed).also { restored ->
                if (seed != null) cache.publish(active) { mutableState.value = restored.initial() }
            }
        }
        var resets = 0
        while (cache.current(active)) {
            val generation = active.generation
            val checkpointWriter = PiCheckpointWriter(cache.scope, elapsedMillis) { snapshot ->
                cache.enqueue(active, generation, snapshot)
            }
            writer = checkpointWriter
            try {
                repository.stream(key, after = session.lastSeq, expectedServer = BaseUrl.restore(active.identity.server))
                    .collect { update ->
                        if (!cache.current(active)) throw CancellationException("Pi session context changed")
                        if (update.unknown) {
                            cache.remove(checkNotNull(BaseUrl.restore(active.identity.server)), key)
                            throw CancellationException("Pi session removed")
                        }
                        if (update.caughtUp && update.summary?.key != key) throw PiWrongSummary()
                        session.mismatch(update)?.let { throw PiFirstSeenChanged(it) }
                        val ui = session.accept(update)
                        cache.publish(active) { mutableState.value = ui }
                        session.checkpoint(active.identity, clock())?.let { checkpointWriter.changed(it) }
                        if (update.stale) checkpointWriter.flush()
                    }
                return
            } catch (changed: PiFirstSeenChanged) {
                checkpointWriter.close(flush = false)
                if (resets++ > 0) {
                    if (cache.reset(active)) fail(active, "Session identity changed again. Reopen this session.")
                    return
                }
                if (!cache.reset(active)) return
                session = PiTranscriptSession(null, changed.firstSeen)
                cache.publish(active) { mutableState.value = PiSessionUiState.Loading }
            } finally {
                checkpointWriter.close()
            }
        }
    }

    private fun fail(active: PiCacheLease, message: String) {
        cache.publish(active) {
            mutableState.value = PiSessionUiState.Loaded(null, PiTranscript(emptyList(), false), PiSessionPhase.FAILED, message)
        }
    }
}
