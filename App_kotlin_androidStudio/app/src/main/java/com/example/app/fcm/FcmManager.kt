package com.example.app.fcm

import android.content.Context
import android.util.Log
import com.example.app.data.ApiResult
import com.example.app.data.ServiceLocator
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Punto único para activar FCM en la app:
 *  1) Pide el token actual a Firebase.
 *  2) Lo registra en el servidor vía POST /fcm/register (FaceRepository).
 *
 * Diseñado para NO romper nada si el servidor está caído o si Firebase aún no
 * está inicializado: cualquier fallo se loguea y se ignora (la app sigue viva).
 */
object FcmManager {

    private const val TAG = "FcmManager"

    /**
     * Obtiene el token FCM y lo registra en el servidor.
     * Pensado para llamarse desde un CoroutineScope (p. ej. lifecycleScope) en MainActivity.
     */
    suspend fun registerToken(context: Context) {
        val token = try {
            currentToken()
        } catch (e: Exception) {
            // Sin google-services.json válido o sin Google Play Services -> no crashea.
            Log.w(TAG, "No se pudo obtener el token FCM: ${e.message}")
            return
        }

        if (token.isNullOrBlank()) {
            Log.w(TAG, "Token FCM vacío; se omite el registro.")
            return
        }

        Log.d(TAG, "Token FCM obtenido, registrando en el servidor...")
        registerWithServer(context, token)
    }

    /** Registra un token concreto (usado también desde onNewToken del servicio). */
    suspend fun registerWithServer(context: Context, token: String) {
        try {
            val repo = ServiceLocator.repository(context)
            when (val result = repo.registerFcm(token)) {
                is ApiResult.Success ->
                    Log.d(TAG, "Token registrado en el servidor (registered=${result.data.registered}).")
                is ApiResult.Error ->
                    // Servidor caído / IP mal configurada: log y seguir. Se reintentará en el próximo arranque.
                    Log.w(TAG, "Registro de token falló (se reintentará luego): ${result.message}")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Excepción registrando token: ${e.message}")
        }
    }

    /** Envuelve el Task<String> de Firebase en una corrutina sin depender de play-services-coroutines. */
    private suspend fun currentToken(): String? = suspendCancellableCoroutine { cont ->
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token -> if (cont.isActive) cont.resume(token) }
            .addOnFailureListener { e -> if (cont.isActive) cont.resumeWithException(e) }
    }
}
