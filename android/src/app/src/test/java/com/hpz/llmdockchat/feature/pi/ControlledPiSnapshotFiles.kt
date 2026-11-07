package com.hpz.llmdockchat.feature.pi

import java.io.File
import java.io.IOException
import java.io.OutputStream
import kotlinx.coroutines.CompletableDeferred

internal class SnapshotWriteGate {
    val prepared = CompletableDeferred<Unit>()
    val release = CompletableDeferred<Unit>()
}

internal class ControlledPiSnapshotFiles(directory: File) : PiSnapshotFiles(directory) {
    var gate: SnapshotWriteGate? = null
    var failCommit = false
    var interruptPrepare = false
    var activePreparations = 0
    var maxPreparations = 0
    val commits = mutableListOf<String>()

    override suspend fun prepare(name: String, write: (OutputStream) -> Unit) {
        activePreparations++
        maxPreparations = maxOf(activePreparations, maxPreparations)
        try {
            super.prepare(name) { output ->
                if (interruptPrepare) {
                    output.write(byteArrayOf(0x1f, 0x8b.toByte()))
                    throw IOException("injected interrupted temporary write")
                }
                write(output)
            }
            val current = gate
            gate = null
            current?.prepared?.complete(Unit)
            current?.release?.await()
        } finally {
            activePreparations--
        }
    }

    override fun commit(name: String) {
        if (failCommit) throw IOException("injected replacement failure")
        super.commit(name)
        commits += name
    }
}
