package com.example.app.network

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.json.Json
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

    private val logging = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val okHttp: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(4, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .callTimeout(8, TimeUnit.SECONDS)
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
