package com.example.app.network

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

/**
 * Construye instancias de [ApiService] con BASE_URL dinámica.
 *
 * Como la IP/puerto del servidor viven en DataStore y pueden cambiar en runtime,
 * cacheamos un único cliente por baseUrl para no reconstruir Retrofit en cada llamada.
 */
object NetworkModule {

    private val json = Json {
        ignoreUnknownKeys = true   // tolerante a campos extra del server (p. ej. "error").
        coerceInputValues = true
    }

    // Cabecera interna: las peticiones que la lleven obtienen un timeout largo
    // (su valor en segundos). Se usa para /enroll y /verify, cuya inferencia con
    // RetinaFace + ArcFace puede tardar decenas de segundos (sobre todo la 1ª vez,
    // que además carga los modelos). El resto de endpoints siguen rápidos.
    const val LONG_TIMEOUT_HEADER = "X-Long-Timeout"

    private val logging = HttpLoggingInterceptor().apply {
        // HEADERS en vez de BODY: evita volcar a logcat los bytes de las fotos
        // (multipart) en cada enroll, que es lento y enorme.
        level = HttpLoggingInterceptor.Level.HEADERS
    }

    // Aplica un timeout largo por-petición SOLO si trae la cabecera LONG_TIMEOUT.
    private val perRequestTimeout = Interceptor { chain ->
        val request = chain.request()
        val seconds = request.header(LONG_TIMEOUT_HEADER)?.toIntOrNull()
        if (seconds == null) {
            chain.proceed(request)
        } else {
            val clean = request.newBuilder().removeHeader(LONG_TIMEOUT_HEADER).build()
            chain
                .withConnectTimeout(15, TimeUnit.SECONDS)
                .withReadTimeout(seconds, TimeUnit.SECONDS)
                .withWriteTimeout(seconds, TimeUnit.SECONDS)
                .proceed(clean)
        }
    }

    private val okHttp: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(logging)
            .addInterceptor(perRequestTimeout)
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            // Sin tope global de llamada: el límite real lo ponen los timeouts de
            // conexión/lectura (cortos por defecto; largos para enroll/verify).
            .callTimeout(0, TimeUnit.SECONDS)
            .build()
    }

    @Volatile
    private var cachedBaseUrl: String? = null

    @Volatile
    private var cachedService: ApiService? = null

    /** Devuelve un ApiService para la [baseUrl] dada (reusa si no cambió). */
    @Synchronized
    fun service(baseUrl: String): ApiService {
        val current = cachedService
        if (current != null && cachedBaseUrl == baseUrl) return current

        val contentType = "application/json".toMediaType()
        val retrofit = Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttp)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()

        val service = retrofit.create(ApiService::class.java)
        cachedBaseUrl = baseUrl
        cachedService = service
        return service
    }
}
