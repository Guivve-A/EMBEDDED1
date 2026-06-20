package com.example.app.data

/** Resultado de una llamada de red: nunca lanza al ViewModel, encapsula el error. */
sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Error(val message: String) : ApiResult<Nothing>
}
