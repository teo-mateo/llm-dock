package com.hpz.llmdockchat.testing

import com.hpz.llmdockchat.core.auth.Credential
import com.hpz.llmdockchat.core.auth.CredentialStore
import com.hpz.llmdockchat.core.auth.SecretCipher
import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.core.prefs.NewChatPreferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.valueOrNull
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

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

class FakeCredentialStore(initial: Credential? = null) : CredentialStore {
    private val state = MutableStateFlow<Stored<Credential>>(Stored.Ready(initial))
    private val presence = MutableStateFlow<Stored<Boolean>>(Stored.Ready(initial != null))
    override val hasCredential: StateFlow<Stored<Boolean>> = presence.asStateFlow()

    override fun current(): Credential? = state.value.valueOrNull

    override fun save(credential: Credential) {
        state.value = Stored.Ready(credential)
        presence.value = Stored.Ready(true)
    }

    override fun clear() {
        state.value = Stored.Ready(null)
        presence.value = Stored.Ready(false)
    }
}

/**
 * The same AES/GCM shape as [com.hpz.llmdockchat.core.auth.KeystoreSecretCipher]
 * with a JVM-resident key. The Keystore itself needs a device; what a unit test
 * can prove is that the store never hands plaintext to DataStore and that a
 * round trip survives it.
 */
class SoftwareSecretCipher : SecretCipher {
    private val key: SecretKey = KeyGenerator.getInstance("AES")
        .apply { init(256) }
        .generateKey()
    private val random = SecureRandom()

    override fun encrypt(plaintext: String): String {
        val iv = ByteArray(12).also(random::nextBytes)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(128, iv))
        return Base64.getEncoder()
            .encodeToString(iv + cipher.doFinal(plaintext.toByteArray()))
    }

    override fun decrypt(ciphertext: String): String? = runCatching {
        val raw = Base64.getDecoder().decode(ciphertext)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, raw, 0, 12))
        String(cipher.doFinal(raw, 12, raw.size - 12))
    }.getOrNull()
}

/** In-memory [NewChatPreferences] — no DataStore, so tests can assert on what was
 * remembered without any disk I/O or coroutine hydration. */
class FakeNewChatPreferences(
    initialModel: String? = null,
    initialMcpServerIds: List<String> = emptyList(),
) : NewChatPreferences {
    var rememberedModel: String? = initialModel
        private set
    var rememberedMcpServerIds: List<String> = initialMcpServerIds
        private set

    override suspend fun lastModel(): String? = rememberedModel
    override fun rememberModel(mainService: String) { rememberedModel = mainService }
    override suspend fun lastMcpServerIds(): List<String> = rememberedMcpServerIds
    override fun rememberMcpServerIds(ids: List<String>) { rememberedMcpServerIds = ids }
}

/**
 * In-memory [DraftStore] — the same shape as the DataStore-backed one without
 * the disk, so a test can assert what was remembered and when it was cleared.
 */
class FakeDraftStore(initial: Map<String, String> = emptyMap()) : DraftStore {
    val saved = initial.toMutableMap()
    override suspend fun draft(conversationId: String): String = saved[conversationId].orEmpty()
    override fun save(conversationId: String, text: String) {
        if (text.isBlank()) saved.remove(conversationId) else saved[conversationId] = text
    }
    override fun clear(conversationId: String) { saved.remove(conversationId) }
}

/**
 * A driveable [SseTransport]. The real one is covered end to end by
 * `OkHttpSseTransportTest`; what a ViewModel test needs instead is control over
 * *when* each payload lands, so delta coalescing and cancellation can be
 * asserted without racing a socket.
 */
class FakeSseTransport : SseTransport {
    val requests = mutableListOf<StreamRequest>()

    /** Payloads emitted, in order, as soon as the flow is collected. */
    var payloads: List<String> = emptyList()

    /** Thrown instead of emitting anything — how a 409 arrives (the POST *is* the stream). */
    var failWith: Throwable? = null

    /** Kept open after the payloads run out, so a test can cancel mid-run. */
    var stayOpen: Boolean = false

    /** Completed once a collector has been cancelled — proof the run was abandoned, not stopped. */
    val cancelled = CompletableDeferred<Unit>()

    /** Completed once every payload has been delivered and the stream has gone quiet. */
    val parked = CompletableDeferred<Unit>()

    override fun open(request: StreamRequest): Flow<String> = flow {
        requests += request
        failWith?.let { throw it }
        payloads.forEach { emit(it) }
        if (stayOpen) {
            try {
                parked.complete(Unit)
                awaitCancellation()
            } finally {
                cancelled.complete(Unit)
            }
        } else {
            parked.complete(Unit)
        }
    }
}

fun baseUrl(raw: String): BaseUrl = (BaseUrl.normalize(raw) as BaseUrlResult.Valid).baseUrl

fun readFixture(name: String): String =
    checkNotNull(object {}.javaClass.getResourceAsStream("/fixtures/$name")) {
        "missing fixture: $name"
    }.bufferedReader().readText()
