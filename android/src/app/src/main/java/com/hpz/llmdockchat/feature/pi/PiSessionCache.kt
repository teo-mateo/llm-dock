package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import java.io.IOException
import java.util.logging.Logger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

internal class PiCacheLease(
    val identity: PiSnapshotIdentity,
    var generation: PiSnapshotGeneration,
    val epoch: Long,
    val invalidated: (removed: Boolean) -> Unit,
    val readAllowed: Boolean,
) {
    var valid = true
}

internal class PiSessionCache(
    private val store: PiSessionSnapshotStore,
    val scope: CoroutineScope,
    private val server: () -> BaseUrl?,
    private val authorized: () -> Boolean,
    private val reportFailure: (IOException) -> Unit = { Logger.getLogger("PiSessionCache").warning(it.toString()) },
) {
    private val lock = Any()
    private var epoch = 0L
    private val leases = mutableSetOf<PiCacheLease>()
    private val deletions = mutableMapOf<PiSnapshotIdentity, Deferred<Boolean>>()

    val usage: StateFlow<PiCacheUsage> get() = store.usage

    fun cachedBytes(usage: PiCacheUsage, key: PiSessionKey): Long? =
        server()?.let { usage.bytesFor(PiSnapshotIdentity(it.value, key)) }

    suspend fun open(key: PiSessionKey, invalidated: (Boolean) -> Unit): PiCacheLease? {
        val identity = server()?.let { PiSnapshotIdentity(it.value, key) } ?: return null
        while (true) {
            val deletion = synchronized(lock) { deletions[identity] }
            val readable = deletion?.await() != false
            val lease = synchronized(lock) {
                if (!authorized() || server()?.value != identity.server) return null
                if (deletions[identity] != null && deletions[identity] !== deletion) return@synchronized null
                leases.filter { it.identity == identity }.forEach { it.valid = false; it.invalidated(false) }
                leases.removeAll { !it.valid }
                PiCacheLease(identity, store.generation(identity), epoch, invalidated, readable).also { leases += it }
            }
            if (lease != null) return lease
        }
    }

    fun current(lease: PiCacheLease): Boolean = synchronized(lock) {
        contextCurrent(lease) && store.isCurrent(lease.generation)
    }

    fun publish(lease: PiCacheLease, action: () -> Unit): Boolean = synchronized(lock) {
        if (!current(lease)) return@synchronized false
        action()
        true
    }

    suspend fun read(lease: PiCacheLease): PiSessionSnapshot? =
        if (lease.readAllowed && current(lease)) store.read(lease.identity)?.takeIf { current(lease) } else null

    fun enqueue(lease: PiCacheLease, generation: PiSnapshotGeneration, snapshot: PiSessionSnapshot): Deferred<PiSnapshotWriteResult> =
        synchronized(lock) {
            if (!current(lease) || lease.generation !== generation) {
                CompletableDeferred(PiSnapshotWriteResult.Invalidated)
            } else {
                store.enqueue(generation, snapshot).also { result ->
                    scope.launch {
                        when (val outcome = result.await()) {
                            is PiSnapshotWriteResult.Failed -> reportFailure(outcome.cause)
                            PiSnapshotWriteResult.QueueFull -> reportFailure(IOException("Pi snapshot queue is full"))
                            else -> Unit
                        }
                    }
                }
            }
        }

    fun release(lease: PiCacheLease) = synchronized(lock) { leases.remove(lease) }

    fun invalidate(lease: PiCacheLease): Boolean = synchronized(lock) {
        if (!current(lease)) return@synchronized false
        invalidate()
        true
    }

    fun invalidate() = synchronized(lock) {
        epoch++
        store.invalidate()
        leases.toList().forEach { it.valid = false; it.invalidated(false) }
        leases.clear()
    }

    fun remove(lease: PiCacheLease): Boolean = synchronized(lock) {
        if (!current(lease)) return@synchronized false
        remove(lease.identity)
        true
    }

    fun remove(server: BaseUrl, key: PiSessionKey) {
        synchronized(lock) { remove(PiSnapshotIdentity(server.value, key)) }
    }

    suspend fun reset(lease: PiCacheLease): Boolean {
        val deletion = synchronized(lock) {
            if (!contextCurrent(lease)) return false
            remove(lease.identity, lease)
        }
        deletion.await()
        return synchronized(lock) {
            if (!contextCurrent(lease)) return@synchronized false
            lease.generation = store.generation(lease.identity)
            true
        }
    }

    private fun remove(identity: PiSnapshotIdentity, except: PiCacheLease? = null): Deferred<Boolean> {
        store.invalidate(identity)
        leases.filter { it.identity == identity && it !== except }.forEach {
            it.valid = false
            it.invalidated(true)
        }
        leases.removeAll { !it.valid }
        val result = CompletableDeferred<Boolean>()
        val previous = deletions.put(identity, result)
        scope.launch {
            previous?.await()
            val succeeded = try {
                store.delete(identity)
                true
            } catch (error: IOException) {
                reportFailure(error)
                false
            }
            synchronized(lock) {
                result.complete(succeeded)
                if (succeeded && deletions[identity] === result) deletions.remove(identity)
            }
        }
        return result
    }

    private fun contextCurrent(lease: PiCacheLease): Boolean =
        lease.valid && lease.epoch == epoch && authorized() && server()?.value == lease.identity.server
}
