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
    val photos: List<Uri> = emptyList(),
    val submitting: Boolean = false,
    val success: Boolean = false,
    val successPerson: String? = null,
    val successSamples: Int = 0,
    val errorMessage: String? = null,
) {
    /** Se puede registrar con al menos 1 muestra; se recomiendan TARGET_SAMPLES. */
    val canSubmit: Boolean get() = name.isNotBlank() && photos.isNotEmpty() && !submitting
}

class EnrollViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)

    private val _ui = MutableStateFlow(EnrollUiState())
    val ui: StateFlow<EnrollUiState> = _ui.asStateFlow()

    companion object {
        /** Nº de tomas recomendado para que el sistema aprenda bien el rostro. */
        const val TARGET_SAMPLES = 5
    }

    fun setName(value: String) = _ui.update { it.copy(name = value, errorMessage = null) }

    /** Añade una toma a la lista (hasta TARGET_SAMPLES). */
    fun addPhoto(uri: Uri?) {
        if (uri == null) return
        _ui.update {
            if (it.photos.size >= TARGET_SAMPLES) it.copy(errorMessage = null)
            else it.copy(photos = it.photos + uri, errorMessage = null)
        }
    }

    /** Elimina la toma en la posición dada. */
    fun removePhoto(index: Int) = _ui.update {
        if (index in it.photos.indices) it.copy(photos = it.photos - it.photos[index])
        else it
    }

    /** Muestra un mensaje de error en la UI (p.ej. permiso de cámara denegado). */
    fun setError(message: String) = _ui.update { it.copy(errorMessage = message) }

    fun reset() = _ui.update { EnrollUiState() }

    fun submit() {
        val state = _ui.value
        if (state.name.isBlank()) {
            _ui.update { it.copy(errorMessage = "El nombre no puede estar vacío.") }
            return
        }
        if (state.photos.isEmpty()) {
            _ui.update { it.copy(errorMessage = "Toma al menos una foto (se recomiendan $TARGET_SAMPLES).") }
            return
        }
        _ui.update { it.copy(submitting = true, errorMessage = null) }
        viewModelScope.launch {
            val files = state.photos.mapNotNull { copyUriToTempFile(it) }
            if (files.isEmpty()) {
                _ui.update { it.copy(submitting = false, errorMessage = "No se pudieron leer las fotos.") }
                return@launch
            }
            // replace=true: re-aprende el rostro desde cero con estas muestras (atómico).
            when (val res = repo.enroll(state.name.trim(), files, replace = true)) {
                is ApiResult.Success ->
                    if (res.data.enrolled) {
                        _ui.update {
                            it.copy(
                                submitting = false,
                                success = true,
                                successPerson = res.data.person,
                                successSamples = res.data.n_valid,
                            )
                        }
                    } else {
                        // El servidor recibió las fotos pero NO detectó rostro en ninguna.
                        _ui.update {
                            it.copy(
                                submitting = false,
                                errorMessage = "No se detectó un rostro en las fotos. " +
                                    "Usa imágenes nítidas, de frente y bien iluminadas.",
                            )
                        }
                    }
                is ApiResult.Error -> _ui.update {
                    it.copy(submitting = false, errorMessage = res.message)
                }
            }
            files.forEach { it.delete() }
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
