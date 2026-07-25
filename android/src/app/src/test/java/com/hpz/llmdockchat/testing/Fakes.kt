package com.hpz.llmdockchat.testing

import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.valueOrNull
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class FakeTokenStore(initial: String? = null) : TokenStore {
    private val state = MutableStateFlow<Stored<String>>(Stored.Ready(initial))
    override val token: StateFlow<Stored<String>> = state.asStateFlow()
    override fun current(): String? = state.value.valueOrNull
    override fun update(token: String) { state.value = Stored.Ready(token) }
    override fun clear() { state.value = Stored.Ready(null) }
}

class FakeServerUrlStore(initial: BaseUrl? = null) : ServerUrlStore {
    private val state = MutableStateFlow<Stored<BaseUrl>>(Stored.Ready(initial))
    override val baseUrl: StateFlow<Stored<BaseUrl>> = state.asStateFlow()
    override fun current(): BaseUrl? = state.value.valueOrNull
    override fun set(url: BaseUrl) { state.value = Stored.Ready(url) }
    override fun clear() { state.value = Stored.Ready(null) }
}

fun baseUrl(raw: String): BaseUrl = (BaseUrl.normalize(raw) as BaseUrlResult.Valid).baseUrl

fun readFixture(name: String): String =
    checkNotNull(object {}.javaClass.getResourceAsStream("/fixtures/$name")) {
        "missing fixture: $name"
    }.bufferedReader().readText()
