package com.example.app.network

import kotlinx.serialization.Serializable

// DTOs que CASAN 1:1 con el JSON real del servidor FastAPI (face_server/main.py).
// Validado contra los endpoints y los modelos pydantic del servidor.

/** GET /state -> { armed, last_event_ts } (last_event_ts puede ser null). */
@Serializable
data class StateDto(
    val armed: Boolean,
    val last_event_ts: String? = null,
)

/** Body de POST /arm -> { armed }. */
@Serializable
data class ArmBody(
    val armed: Boolean,
)

/** Respuesta de POST /arm y POST /disarm -> { armed }. */
@Serializable
data class ArmResponse(
    val armed: Boolean,
)

/** Respuesta de POST /enroll -> { enrolled, person, n_photos, n_valid }. */
@Serializable
data class EnrollResponse(
    val enrolled: Boolean,
    val person: String,
    val n_photos: Int,
    val n_valid: Int = 0,
)

/** Item de GET /enrolled -> { name, n_embeddings, enrolled_at }. */
@Serializable
data class EnrolledPersonDto(
    val name: String,
    val n_embeddings: Int,
    val enrolled_at: String? = null,
)

/** Respuesta de DELETE /enroll/{name} -> { deleted }. */
@Serializable
data class DeleteResponse(
    val deleted: Boolean,
)

/** Item de GET /events -> { id, ts, match, person, confidence, photo_id, latency_ms }. */
@Serializable
data class EventDto(
    val id: Int,
    val ts: String,
    val match: Boolean,
    val person: String,
    val confidence: Double,
    val photo_id: String,
    val latency_ms: Int,
)

/** Respuesta de GET /events -> { items, total, page, limit }. */
@Serializable
data class EventsPageDto(
    val items: List<EventDto>,
    val total: Int,
    val page: Int,
    val limit: Int,
)

/** Respuesta de DELETE /events -> { cleared, deleted_events, deleted_photos }. */
@Serializable
data class ClearEventsResponse(
    val cleared: Boolean,
    val deleted_events: Int = 0,
    val deleted_photos: Int = 0,
)

/** Body de POST /fcm/register -> { token }. */
@Serializable
data class FcmRegisterBody(
    val token: String,
)

/** Respuesta de POST /fcm/register -> { registered }. */
@Serializable
data class FcmRegisterResponse(
    val registered: Boolean,
)
