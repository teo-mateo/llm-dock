package com.hpz.llmdockchat.feature.pi

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING

internal open class PiSnapshotFiles(private val directory: File) {
    fun initialize() {
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Cannot create Pi cache directory")
        directory.listFiles()?.filter { TEMP.matches(it.name) }?.forEach { remove(it.name) }
    }

    fun entries(): List<File> = directory.listFiles()?.filter { ENTRY.matches(it.name) && it.isFile }
        ?: throw IOException("Cannot list Pi cache directory")

    fun open(name: String, maxBytes: Long): InputStream? {
        val file = File(directory, name)
        if (!file.isFile || file.length() > maxBytes) return null
        return file.inputStream()
    }

    open suspend fun prepare(name: String, write: (OutputStream) -> Unit) {
        FileOutputStream(temporary(name)).use {
            write(it)
            it.fd.sync()
        }
    }

    open fun commit(name: String) {
        Files.move(temporary(name).toPath(), File(directory, name).toPath(), ATOMIC_MOVE, REPLACE_EXISTING)
    }

    fun discard(name: String) = remove(temporary(name).name)

    fun touch(name: String, timestamp: Long) {
        if (!File(directory, name).setLastModified(timestamp)) throw IOException("Cannot update Pi cache access time")
    }

    fun remove(name: String) {
        val file = File(directory, name)
        if (file.exists() && !file.delete()) throw IOException("Cannot remove Pi cache file")
    }

    private fun temporary(name: String) = File(directory, name.removeSuffix(".json.gz") + ".tmp")

    private companion object {
        val ENTRY = Regex("[0-9a-f]{64}\\.json\\.gz")
        val TEMP = Regex("[0-9a-f]{64}\\.tmp")
    }
}
