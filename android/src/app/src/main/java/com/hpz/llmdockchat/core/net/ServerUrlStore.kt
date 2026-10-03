package com.hpz.llmdockchat.core.net

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.StateFlow

/** The single stored server address every request is built from. */
interface ServerUrlStore {
    val baseUrl: StateFlow<Stored<BaseUrl>>

    /** Blocks until the first disk read lands; for network threads only. */
    fun current(): BaseUrl?
    fun set(url: BaseUrl)
    fun clear()
    fun ifCurrent(url: BaseUrl, action: () -> Unit): Boolean {
        if (current() != url) return false
        action()
        return true
    }
}

class DataStoreServerUrlStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : ServerUrlStore {

    private val lock = Any()

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "server_base_url",
        scope = scope,
        decode = BaseUrl::restore,
        encode = BaseUrl::value,
    )

    override val baseUrl: StateFlow<Stored<BaseUrl>> get() = pref.flow
    override fun current(): BaseUrl? = pref.get()
    override fun set(url: BaseUrl) = synchronized(lock) { pref.set(url) }
    override fun clear() = synchronized(lock) { pref.clear() }
    override fun ifCurrent(url: BaseUrl, action: () -> Unit): Boolean = synchronized(lock) {
        if (pref.get() != url) return@synchronized false
        action()
        true
    }

    internal suspend fun awaitPendingWrites() = pref.awaitPendingWrites()
}
