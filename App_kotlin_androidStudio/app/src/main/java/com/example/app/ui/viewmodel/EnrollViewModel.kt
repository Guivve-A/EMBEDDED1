package com.example.app.ui.viewmodel

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.ApiResult
import com.example.app.data.FaceRepository
import com.example.app.data.ServiceLocator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

data class EnrollUiState(
    val name: String = "",
    val photoUri: Uri? = null,
    val submitting: Boolean = false,
    val success: Boolean = false,
    val successPerson: String? = null,
    val errorMessage: String? = null,
) {
    val canSubmit: Boolean get() = name.isNotBlank() && photoUri != null && !submitting
}

class EnrollViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)

    private val _ui = MutableStateFlow(EnrollUiState())
    val ui: StateFlow<EnrollUiState> = _ui.asStateFlow()

    fun setName(value: String) = _ui.update { it.copy(name = value, errorMessage = null) }
    fun setPhoto(uri: Uri?) = _ui.update { it.copy(photoUri = uri, errorMessage = null) }

    /** Muestra un mensaje de error en la UI (p.ej. permiso de cámara denegado). */
    fun setError(message: String) = _ui.update { it.copy(errorMessage = message) }

    fun reset() = _ui.update { EnrollUiState() }

    fun submit() {
        val state = _ui.value
        if (state.name.isBlank()) {
            _ui.update { it.copy(errorMessage = "El nombre no puede estar vacío.") }
            return
        }
        val uri = state.photoUri ?: run {
            _ui.update { it.copy(errorMessage = "Selecciona o toma una foto.") }
            return
        }
        _ui.update { it.copy(submitting = true, errorMessage = null) }
        viewModelScope.launch {
            val file = copyUriToTempFile(uri)
            if (file == null) {
                _ui.update { it.copy(submitting = false, errorMessage = "No se pudo leer la foto.") }
                return@launch
            }
            when (val res = repo.enroll(state.name.trim(), file)) {
                is ApiResult.Success ->
                    if (res.data.enrolled) {
                        _ui.update {
                            it.copy(submitting = false, success = true, successPerson = res.data.person)
                        }
                    } else {
                        // El servidor recibió la foto pero NO detectó un rostro.
                        _ui.update {
                            it.copy(
                                submitting = false,
                                errorMessage = "No se detectó un rostro en la foto. " +
                                    "Usa una imagen nítida, de frente y bien iluminada.",
                            )
                        }
                    }
                is ApiResult.Error -> _ui.update {
                    it.copy(submitting = false, errorMessage = res.message)
                }
            }
            file.delete()
        }
    }

    private suspend fun copyUriToTempFile(uri: Uri): File? = withContext(Dispatchers.IO) {
        try {
            val resolver = getApplication<Application>().contentResolver
            val input = resolver.openInputStream(uri) ?: return@withContext null
            val temp = File.createTempFile("enroll_", ".jpg", getApplication<Application>().cacheDir)
            input.use { ins -> temp.outputStream().use { outs -> ins.copyTo(outs) } }
            temp
        } catch (e: Exception) {
            null
        }
    }
}
