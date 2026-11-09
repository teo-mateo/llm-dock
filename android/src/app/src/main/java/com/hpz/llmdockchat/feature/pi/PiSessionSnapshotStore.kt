package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotCodec
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotLimits
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotTooLarge
import java.io.File
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

internal class PiSnapshotGeneration internal constructor(val identity: PiSnapshotIdentity)

internal data class PiCacheUsage(
    val files: Map<String, Long> = emptyMap(),
    val warningBytes: Long = Long.MAX_VALUE,
) {
    val totalBytes: Long get() = files.values.sum()
    val overWarning: Boolean get() = totalBytes > warningBytes

    fun bytesFor(identity: PiSnapshotIdentity): Long? = files[identity.fileName()]
}

internal sealed interface PiSnapshotWriteResult {
    data object Stored : PiSnapshotWriteResult
    data object Skipped : PiSnapshotWriteResult
    data object Superseded : PiSnapshotWriteResult
    data object Invalidated : PiSnapshotWriteResult
    data object QueueFull : PiSnapshotWriteResult
    data class Failed(val cause: IOException) : PiSnapshotWriteResult
}

internal class PiSessionSnapshotStore(
    directory: File,
    scope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
    private val clock: () -> Long = System::currentTimeMillis,
    private val limits: PiSnapshotLimits = PiSnapshotLimits(),
    private val files: PiSnapshotFiles = PiSnapshotFiles(directory),
) {
    private data class Pending(
        val generation: PiSnapshotGeneration,
        val snapshot: PiSessionSnapshot,
        val result: CompletableDeferred<PiSnapshotWriteResult>,
    )

    private val lock = Any()
    private val generations = mutableMapOf<PiSnapshotIdentity, PiSnapshotGeneration>()
    private val pending = linkedMapOf<PiSnapshotIdentity, Pending>()
    private val wake = Channel<Unit>(Channel.CONFLATED)
    private val ready = CompletableDeferred<Unit>()
    private val codec = PiSnapshotCodec(limits)
    private var closed = false
    private var failure: IOException? = null
    private val mutableUsage = MutableStateFlow(PiCacheUsage(warningBytes = limits.warningBytes))
    val usage: StateFlow<PiCacheUsage> = mutableUsage.asStateFlow()
    private val worker = scope.launch(ioDispatcher) {
        try {
            files.initialize()
            synchronized(lock) { refreshUsage() }
            ready.complete(Unit)
            for (signal in wake) {
                while (true) {
                    val next = synchronized(lock) {
                        pending.entries.firstOrNull()?.let { pending.remove(it.key) }
                    } ?: break
                    persist(next)
                }
            }
        } catch (error: IOException) {
            synchronized(lock) { failure = error }
            ready.completeExceptionally(error)
        }
    }.also { job ->
        job.invokeOnCompletion {
            synchronized(lock) {
                closed = true
                pending.values.forEach {
                    it.result.complete(failure?.let { error -> PiSnapshotWriteResult.Failed(error) } ?: PiSnapshotWriteResult.Invalidated)
                }
                pending.clear()
                generations.clear()
            }
            ready.cancel()
            wake.close()
        }
    }

    fun generation(identity: PiSnapshotIdentity): PiSnapshotGeneration = synchronized(lock) {
        check(!closed || failure != null) { "Snapshot store is closed" }
        generations.getOrPut(identity) { PiSnapshotGeneration(identity) }
    }

    fun enqueue(generation: PiSnapshotGeneration, snapshot: PiSessionSnapshot): Deferred<PiSnapshotWriteResult> =
        synchronized(lock) {
            val result = CompletableDeferred<PiSnapshotWriteResult>()
            when {
                failure != null -> result.complete(PiSnapshotWriteResult.Failed(failure!!))
                closed || !isCurrent(generation) || snapshot.identity != generation.identity ->
                    result.complete(PiSnapshotWriteResult.Invalidated)
                snapshot.identity !in pending && pending.size >= limits.pendingWrites ->
                    result.complete(PiSnapshotWriteResult.QueueFull)
                else -> {
                    val next = Pending(generation, snapshot.frozen(), result)
                    pending.put(snapshot.identity, next)?.result?.complete(PiSnapshotWriteResult.Superseded)
                    wake.trySend(Unit)
                }
            }
            result
        }

    suspend fun read(identity: PiSnapshotIdentity): PiSessionSnapshot? {
        val generation = synchronized(lock) {
            if (closed) return null
            generation(identity)
        }
        return withContext(ioDispatcher) {
            try {
                ready.await()
                val snapshot = files.open(identity.fileName(), limits.fileBytes)?.use { codec.read(it, identity) }
                    ?: return@withContext null
                synchronized(lock) {
                    if (!isCurrent(generation)) return@synchronized null
                    files.touch(identity.fileName(), clock())
                    snapshot
                }
            } catch (_: IOException) {
                null
            }
        }
    }

    suspend fun delete(identity: PiSnapshotIdentity) {
        synchronized(lock) { invalidateKey(identity) }
        withContext(ioDispatcher) {
            ready.await()
            synchronized(lock) {
                files.remove(identity.fileName())
                refreshUsage()
            }
        }
    }

    fun invalidate() = synchronized(lock) {
        generations.keys.toList().forEach { invalidateKey(it) }
    }

    suspend fun clear() {
        invalidate()
        withContext(ioDispatcher) {
            ready.await()
            synchronized(lock) {
                files.entries().forEach { files.remove(it.name) }
                refreshUsage()
            }
        }
    }

    suspend fun close() {
        synchronized(lock) {
            closed = true
            invalidate()
        }
        worker.cancelAndJoin()
    }

    fun isCurrent(generation: PiSnapshotGeneration): Boolean = synchronized(lock) {
        generations[generation.identity] === generation
    }

    fun invalidate(identity: PiSnapshotIdentity) = synchronized(lock) { invalidateKey(identity) }

    private fun invalidateKey(identity: PiSnapshotIdentity) {
        generations.remove(identity)
        pending.remove(identity)?.result?.complete(PiSnapshotWriteResult.Invalidated)
    }

    private suspend fun persist(next: Pending) {
        val name = next.snapshot.identity.fileName()
        var result: PiSnapshotWriteResult = PiSnapshotWriteResult.Invalidated
        try {
            currentCoroutineContext().ensureActive()
            if (synchronized(lock) { isCurrent(next.generation) }) {
                files.prepare(name) { codec.write(next.snapshot, it) }
                currentCoroutineContext().ensureActive()
                synchronized(lock) {
                    if (isCurrent(next.generation)) {
                        files.commit(name)
                        files.touch(name, clock())
                        refreshUsage()
                        result = PiSnapshotWriteResult.Stored
                    }
                }
            }
        } catch (error: CancellationException) {
            throw error
        } catch (_: PiSnapshotTooLarge) {
            result = PiSnapshotWriteResult.Skipped
        } catch (_: IllegalArgumentException) {
            result = PiSnapshotWriteResult.Skipped
        } catch (error: IOException) {
            result = PiSnapshotWriteResult.Failed(error)
        } finally {
            try {
                files.discard(name)
            } catch (error: IOException) {
                result = PiSnapshotWriteResult.Failed(error)
            }
            next.result.complete(result)
        }
    }

    private fun refreshUsage() {
        mutableUsage.value = mutableUsage.value.copy(files = files.entries().associate { it.name to it.length() })
    }
}
