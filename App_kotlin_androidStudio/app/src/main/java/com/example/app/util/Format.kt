package com.example.app.util

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Utilidades de formato para la UI (timestamps, confianza). */
object Format {

    private val isoParsers: List<SimpleDateFormat> = listOf(
        // ISO8601 UTC con offset (lo que emite datetime.isoformat() del server).
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX", Locale.US),
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US),
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") },
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") },
    )

    private val display = SimpleDateFormat("dd MMM yyyy · HH:mm:ss", Locale("es"))

    /** Convierte un timestamp ISO del server a texto legible en hora local. */
    fun timestamp(iso: String?): String {
        if (iso.isNullOrBlank()) return "—"
        for (parser in isoParsers) {
            try {
                val date: Date = parser.parse(iso) ?: continue
                return display.format(date)
            } catch (_: Exception) { /* prueba el siguiente patrón */ }
        }
        return iso
    }

    /** Confianza 0..1 -> porcentaje entero. */
    fun confidence(value: Double): String = "${(value * 100).toInt()}%"
}
