package com.hpz.llmdockchat.core.net

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.StateFlow

/** The single stored server address every request is built from (F00-R1). */
interface ServerUrlStore {
    val baseUrl: StateFlow<Stored<BaseUrl>>

    /** Blocks until the first disk read lands; for network threads only. */
    fun current(): BaseUrl?
    fun set(url: BaseUrl)
    fun clear()
}

class DataStoreServerUrlStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : ServerUrlStore {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "server_base_url",
        scope = scope,
        decode = BaseUrl::restore,
        encode = BaseUrl::value,
    )

    override val baseUrl: StateFlow<Stored<BaseUrl>> get() = pref.flow
    override fun current(): BaseUrl? = pref.get()
    override fun set(url: BaseUrl) = pref.set(url)
    override fun clear() = pref.clear()
}
