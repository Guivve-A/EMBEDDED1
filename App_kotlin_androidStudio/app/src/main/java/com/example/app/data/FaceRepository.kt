package com.example.app.data

import android.content.Context
import com.example.app.network.ApiService
import com.example.app.network.ArmBody
import com.example.app.network.ClearEventsResponse
import com.example.app.network.DeleteResponse
import com.example.app.network.EnrollResponse
import com.example.app.network.EnrolledPersonDto
import com.example.app.network.EventsPageDto
import com.example.app.network.FcmRegisterBody
import com.example.app.network.FcmRegisterResponse
import com.example.app.network.NetworkModule
import com.example.app.network.StateDto
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
import java.io.File
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * Repository: única fuente de verdad para la app. Resuelve el ApiService correcto
 * según la config actual de DataStore y convierte cualquier excepción en
 * [ApiResult.Error] legible (servidor caído -> estado de error, sin crash).
 */
class FaceRepository(
    private val settings: SettingsDataStore,
) {
    val configFlow: Flow<ServerConfig> = settings.config

    private suspend fun api(): ApiService {
        val cfg = settings.config.first()
        return NetworkModule.service(cfg.baseUrl)
    }

    /** URL absoluta de la miniatura de un evento. */
    suspend fun photoUrl(photoId: String): String {
        val cfg = settings.config.first()
        return "${cfg.baseUrl}photos/$photoId"
    }

    private suspend fun <T> call(block: suspend (ApiService) -> T): ApiResult<T> {
        return try {
            ApiResult.Success(block(api()))
        } catch (e: SocketTimeoutException) {
            ApiResult.Error("Tiempo de espera agotado. El servidor no responde.")
        } catch (e: ConnectException) {
            ApiResult.Error("No se pudo conectar. Revisa IP/puerto y la red.")
        } catch (e: UnknownHostException) {
            ApiResult.Error("Host desconocido. Revisa la IP del servidor.")
        } catch (e: HttpException) {
            ApiResult.Error("Error del servidor (HTTP ${e.code()}).")
        } catch (e: Exception) {
            ApiResult.Error(e.message ?: "Error de red desconocido.")
        }
    }

    suspend fun getState(): ApiResult<StateDto> = call { it.getState() }

    suspend fun setArmed(armed: Boolean): ApiResult<Boolean> =
        call { if (armed) it.arm(ArmBody(true)).armed else it.disarm().armed }

    suspend fun getEvents(page: Int, limit: Int): ApiResult<EventsPageDto> =
        call { it.getEvents(page, limit) }

    suspend fun clearEvents(): ApiResult<ClearEventsResponse> =
        call { it.clearEvents() }

    suspend fun listEnrolled(): ApiResult<List<EnrolledPersonDto>> =
        call { it.listEnrolled() }

    suspend fun deleteEnrolled(name: String): ApiResult<DeleteResponse> =
        call { it.deleteEnroll(name) }

    suspend fun registerFcm(token: String): ApiResult<FcmRegisterResponse> =
        call { it.registerFcm(FcmRegisterBody(token)) }

    /**
     * Enrola una persona enviando UNA o VARIAS fotos (multipart) en una sola
     * petición. Con replace=true el servidor re-aprende el rostro desde cero con
     * estas muestras (atómico); con false las añade a las existentes.
     */
    suspend fun enroll(
        name: String,
        jpegs: List<File>,
        replace: Boolean,
    ): ApiResult<EnrollResponse> = call { service ->
        val namePart = name.toRequestBody("text/plain".toMediaType())
        val fileParts = jpegs.map { jpeg ->
            val body = jpeg.asRequestBody("image/jpeg".toMediaType())
            MultipartBody.Part.createFormData("file", jpeg.name, body)
        }
        val replacePart = replace.toString().toRequestBody("text/plain".toMediaType())
        service.enroll(namePart, fileParts, replacePart)
    }

    suspend fun saveConfig(host: String, port: String) = settings.save(host, port)
}
