package com.example.app.network

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Contrato Retrofit del servidor FastAPI.
 *
 * BASE_URL es dinámica (IP+puerto de DataStore); por eso el cliente Retrofit se
 * reconstruye cuando cambia (ver NetworkModule). Las rutas son relativas.
 */
interface ApiService {

    @GET("state")
    suspend fun getState(): StateDto

    @POST("arm")
    suspend fun arm(@Body body: ArmBody): ArmResponse

    @POST("disarm")
    suspend fun disarm(): ArmResponse

    @Multipart
    @POST("enroll")
    suspend fun enroll(
        @Part("name") name: okhttp3.RequestBody,
        @Part file: MultipartBody.Part,
    ): EnrollResponse

    @GET("enrolled")
    suspend fun listEnrolled(): List<EnrolledPersonDto>

    @DELETE("enroll/{name}")
    suspend fun deleteEnroll(@Path("name") name: String): DeleteResponse

    @GET("events")
    suspend fun getEvents(
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 20,
    ): EventsPageDto

    @DELETE("events")
    suspend fun clearEvents(): ClearEventsResponse

    @POST("fcm/register")
    suspend fun registerFcm(@Body body: FcmRegisterBody): FcmRegisterResponse
}
