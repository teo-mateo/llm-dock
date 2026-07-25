package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.io.IOException

/**
 * A single DataStore-backed value, read once asynchronously and then served
 * from memory.
 *
 * Two callers with different needs share it. The UI observes [flow], which
 * reports [Stored.Loading] until the disk read lands, so nothing has to block
 * the main thread. The OkHttp interceptor and authenticator call [get] from
 * network threads outside any coroutine, and those threads exist to block —
 * [get] waits for the same single read rather than starting its own.
 *
 * Writes go through a one-consumer channel so they reach disk in call order.
 * Without that, `clear()` immediately followed by `set()` can land in either
 * order and leave a stale token on disk.
 */
class ValuePreference<T : Any>(
    private val dataStore: DataStore<Preferences>,
    name: String,
    scope: CoroutineScope,
    private val decode: (String) -> T?,
    private val encode: (T) -> String,
) {
    private val key = stringPreferencesKey(name)
    private val state = MutableStateFlow<Stored<T>>(Stored.Loading)
    private val writes = Channel<suspend () -> Unit>(Channel.UNLIMITED)

    val flow: StateFlow<Stored<T>> = state.asStateFlow()

    private val hydration = scope.launch {
        val loaded = try {
            dataStore.data.first()[key]?.let(decode)
        } catch (e: IOException) {
            // An unreadable preferences file is, for our purposes, an empty
            // one — the values here are a server address and a disposable
            // session token, both re-enterable. Settling on Ready(null) is
            // what stops the read being retried on every single access.
            null
        }
        // A write that beat the read to it wins: it is the newer truth.
        state.compareAndSet(Stored.Loading, Stored.Ready(loaded))
    }

    init {
        scope.launch {
            for (write in writes) write()
        }
    }

    fun get(): T? {
        if (state.value is Stored.Loading) {
            runBlocking { hydration.join() }
        }
        return state.value.valueOrNull
    }

    fun set(value: T) {
        state.value = Stored.Ready(value)
        val encoded = encode(value)
        enqueue { dataStore.edit { it[key] = encoded } }
    }

    fun clear() {
        state.value = Stored.Ready(null)
        enqueue { dataStore.edit { it.remove(key) } }
    }

    private fun enqueue(write: suspend () -> Unit) {
        writes.trySend {
            try {
                write()
            } catch (e: IOException) {
                // Memory already holds the new value, so the app behaves
                // correctly for this session; only persistence is lost.
            }
        }
    }

    /** Returns once every write enqueued before this call has reached disk. */
    internal suspend fun awaitPendingWrites() {
        val drained = CompletableDeferred<Unit>()
        writes.send { drained.complete(Unit) }
        drained.await()
    }
}
