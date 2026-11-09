package com.hpz.llmdockchat.feature.pi.transcript

import java.io.ByteArrayOutputStream
import java.io.FilterInputStream
import java.io.FilterOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.encodeToStream

internal class PiSnapshotTooLarge : IOException("Snapshot exceeds cache limits")

internal class PiSnapshotCodec(private val limits: PiSnapshotLimits = PiSnapshotLimits()) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @OptIn(ExperimentalSerializationApi::class)
    fun write(snapshot: PiSessionSnapshot, output: OutputStream) {
        require(snapshot.isValidFor(snapshot.identity)) { "Invalid snapshot" }
        val sink = object : FilterOutputStream(output) {
            override fun close() = flush()
        }
        GZIPOutputStream(LimitedOutput(sink, limits.fileBytes)).use { gzip ->
            json.encodeToStream(snapshot, LimitedOutput(gzip, limits.jsonBytes.toLong()))
        }
    }

    fun read(input: InputStream, expected: PiSnapshotIdentity): PiSessionSnapshot? = try {
        GZIPInputStream(LimitedInput(input, limits.fileBytes)).use { gzip ->
            val bytes = readJson(gzip)
            val snapshot = json.decodeFromString<PiSessionSnapshot>(bytes.decodeToString(throwOnInvalidSequence = true))
            snapshot.takeIf { it.isValidFor(expected) }
        }
    } catch (_: IOException) {
        null
    } catch (_: IllegalArgumentException) {
        null
    }

    private fun readJson(input: InputStream): ByteArray {
        val bytes = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        var remaining = limits.jsonBytes
        while (true) {
            val count = input.read(buffer, 0, minOf(buffer.size.toLong(), remaining.toLong() + 1).toInt())
            if (count < 0) return bytes.toByteArray()
            if (count > remaining) throw PiSnapshotTooLarge()
            bytes.write(buffer, 0, count)
            remaining -= count
        }
    }
}

private class LimitedInput(input: InputStream, private val limit: Long) : FilterInputStream(input) {
    private var count = 0L

    override fun read(): Int {
        val value = `in`.read()
        if (value >= 0 && ++count > limit) throw PiSnapshotTooLarge()
        return value
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        val size = `in`.read(buffer, offset, minOf(length.toLong(), limit - count + 1).toInt())
        if (size > 0) {
            count += size
            if (count > limit) throw PiSnapshotTooLarge()
        }
        return size
    }
}

private class LimitedOutput(output: OutputStream, private val limit: Long) : FilterOutputStream(output) {
    private var count = 0L

    override fun write(value: Int) {
        if (++count > limit) throw PiSnapshotTooLarge()
        out.write(value)
    }

    override fun write(buffer: ByteArray, offset: Int, length: Int) {
        count += length
        if (count > limit) throw PiSnapshotTooLarge()
        out.write(buffer, offset, length)
    }
}
