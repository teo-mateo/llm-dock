package com.hpz.llmdockchat.core.time

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Server timestamps are UTC ISO-8601 (`2026-07-24T15:32:36Z`, sometimes with
 * microseconds). Rendered in device-local time, relative for recent items
 * (F00-R11).
 *
 * Pure: the clock and zone are arguments, never `Instant.now()`.
 */
object Timestamps {

    private val TIME = DateTimeFormatter.ofPattern("HH:mm")
    private val WEEKDAY = "EEE"
    private val DAY_MONTH = "d MMM"
    private val DAY_MONTH_YEAR = "d MMM yyyy"

    /** Accepts a trailing `Z`, an explicit offset, or neither (assumed UTC). */
    fun parse(raw: String): Instant? {
        val text = raw.trim()
        if (text.isEmpty()) return null
        runCatching { return Instant.parse(text) }
        runCatching { return OffsetDateTime.parse(text).toInstant() }
        runCatching {
            return LocalDateTime.parse(text, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                .toInstant(ZoneOffset.UTC)
        }
        runCatching {
            return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE)
                .atStartOfDay(ZoneOffset.UTC)
                .toInstant()
        }
        return null
    }

    /**
     * A short label for a list row. Unparseable input is returned as given
     * rather than blanked — a visible oddity beats an empty cell.
     */
    fun relative(
        raw: String,
        now: Instant,
        zone: ZoneId,
        locale: Locale = Locale.getDefault(),
    ): String {
        val instant = parse(raw) ?: return raw.trim()
        return relative(instant, now, zone, locale)
    }

    fun relative(
        instant: Instant,
        now: Instant,
        zone: ZoneId,
        locale: Locale = Locale.getDefault(),
    ): String {
        val elapsed = Duration.between(instant, now)
        if (!elapsed.isNegative && elapsed.toMinutes() < 1) return "just now"

        val then = instant.atZone(zone)
        val today = now.atZone(zone).toLocalDate()
        val date = then.toLocalDate()

        return when {
            date == today -> TIME.format(then)
            date == today.minusDays(1) -> "yesterday"
            date.isAfter(today.minusDays(7)) && date.isBefore(today) ->
                DateTimeFormatter.ofPattern(WEEKDAY, locale).format(then)
            date.year == today.year ->
                DateTimeFormatter.ofPattern(DAY_MONTH, locale).format(then)
            else ->
                DateTimeFormatter.ofPattern(DAY_MONTH_YEAR, locale).format(then)
        }
    }
}
