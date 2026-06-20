package com.example.app.fcm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.example.app.R
import com.example.app.data.ServiceLocator
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.net.HttpURLConnection
import java.net.URL

/**
 * Servicio FCM real (Fase 9).
 *
 * - onNewToken: re-registra el token en el servidor (POST /fcm/register).
 * - onMessageReceived: construye una notificación local de alta prioridad en el
 *   canal "alerts"; si el push trae data.photo_id, intenta cargar la miniatura
 *   ({BASE_URL}/photos/{photo_id}) como BigPicture. Tap -> abre Events vía deeplink.
 *
 * Robusto: cualquier fallo de red/imagen se loguea y se degrada a una notificación
 * simple title+body. Nunca crashea la app.
 */
class MyFirebaseMessagingService : FirebaseMessagingService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "Nuevo token FCM, re-registrando en el servidor.")
        scope.launch {
            FcmManager.registerWithServer(applicationContext, token)
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        ensureChannel()

        val data = message.data
        // Preferimos el bloque notification; si solo viene data, usamos esos campos.
        val title = message.notification?.title
            ?: data["title"]
            ?: defaultTitle(data)
        val body = message.notification?.body
            ?: data["body"]
            ?: defaultBody(data)

        val photoId = data["photo_id"]

        scope.launch {
            val bitmap = photoId?.let { loadThumbnail(it) }
            showNotification(title, body, photoId, bitmap)
        }
    }

    private fun defaultTitle(data: Map<String, String>): String {
        val match = data["match"]?.toBooleanStrictOrNull() ?: false
        return if (match) "Acceso autorizado" else "Alerta de seguridad"
    }

    private fun defaultBody(data: Map<String, String>): String {
        val person = data["person"]?.takeIf { it.isNotBlank() } ?: "Desconocido"
        val conf = data["confidence"]
        return if (conf != null) "$person (confianza $conf)" else person
    }

    /** Descarga la miniatura del evento desde {BASE_URL}/photos/{photo_id}. */
    private suspend fun loadThumbnail(photoId: String): Bitmap? {
        return try {
            val url = ServiceLocator.repository(applicationContext).photoUrl(photoId)
            Log.d(TAG, "Descargando miniatura: $url")
            val conn = (URL(url).openConnection() as HttpURLConnection).apply {
                connectTimeout = 4000
                readTimeout = 5000
                doInput = true
            }
            conn.inputStream.use { BitmapFactory.decodeStream(it) }
        } catch (e: Exception) {
            Log.w(TAG, "No se pudo cargar la miniatura ($photoId): ${e.message}")
            null
        }
    }

    private fun showNotification(
        title: String,
        body: String,
        photoId: String?,
        bitmap: Bitmap?,
    ) {
        // Deeplink: app://events o app://events?photo_id=...
        val deeplink = if (photoId != null) "app://events?photo_id=$photoId" else "app://events"
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(deeplink)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        val pending = PendingIntent.getActivity(
            this,
            photoId?.hashCode() ?: 0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(pending)

        if (bitmap != null) {
            builder.setLargeIcon(bitmap)
            builder.setStyle(
                NotificationCompat.BigPictureStyle()
                    .bigPicture(bitmap)
                    .bigLargeIcon(null as Bitmap?),
            )
        } else {
            builder.setStyle(NotificationCompat.BigTextStyle().bigText(body))
        }

        val nm = NotificationManagerCompat.from(this)
        // En Android 13+ el sistema no muestra la notificación sin permiso; si no se
        // concedió, notify() simplemente no hace nada (no crashea).
        try {
            nm.notify(NOTIF_ID, builder.build())
        } catch (se: SecurityException) {
            Log.w(TAG, "Sin permiso POST_NOTIFICATIONS: ${se.message}")
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                val channel = NotificationChannel(
                    CHANNEL_ID,
                    "Alertas de seguridad",
                    NotificationManager.IMPORTANCE_HIGH,
                ).apply {
                    description = "Avisos de detección facial e intrusiones."
                    enableVibration(true)
                }
                nm.createNotificationChannel(channel)
            }
        }
    }

    companion object {
        private const val TAG = "FcmService"
        // Debe coincidir con default_notification_channel_id del Manifest ("alerts").
        const val CHANNEL_ID = "alerts"
        private const val NOTIF_ID = 1001

        /** Crea el canal de forma proactiva (llamar desde MainActivity al arrancar). */
        fun createChannel(context: Context) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                    val channel = NotificationChannel(
                        CHANNEL_ID,
                        "Alertas de seguridad",
                        NotificationManager.IMPORTANCE_HIGH,
                    ).apply {
                        description = "Avisos de detección facial e intrusiones."
                        enableVibration(true)
                    }
                    nm.createNotificationChannel(channel)
                }
            }
        }
    }
}
