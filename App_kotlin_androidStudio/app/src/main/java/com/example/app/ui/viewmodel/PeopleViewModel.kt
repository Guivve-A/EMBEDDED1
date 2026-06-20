package com.example.app.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.ApiResult
import com.example.app.data.FaceRepository
import com.example.app.data.ServiceLocator
import com.example.app.network.EnrolledPersonDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PeopleUiState(
    val loading: Boolean = true,
    val errorMessage: String? = null,
    val people: List<EnrolledPersonDto> = emptyList(),
    val pendingDelete: String? = null,
    val deleting: Boolean = false,
)

class PeopleViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)

    private val _ui = MutableStateFlow(PeopleUiState())
    val ui: StateFlow<PeopleUiState> = _ui.asStateFlow()

    // El refresco lo dispara la pantalla (LaunchedEffect), también al volver de
    // "Aprender Rostro", para que la lista quede siempre actualizada.

    fun refresh() {
        // Solo mostramos el spinner en la PRIMERA carga; en refrescos posteriores
        // (al volver de Enroll) actualizamos en silencio para no parpadear.
        val firstLoad = _ui.value.people.isEmpty()
        if (firstLoad) _ui.update { it.copy(loading = true, errorMessage = null) }
        viewModelScope.launch {
            when (val res = repo.listEnrolled()) {
                is ApiResult.Success -> _ui.update {
                    it.copy(loading = false, people = res.data, errorMessage = null)
                }
                is ApiResult.Error -> _ui.update {
                    it.copy(loading = false, errorMessage = res.message)
                }
            }
        }
    }

    fun requestDelete(name: String) = _ui.update { it.copy(pendingDelete = name) }
    fun cancelDelete() = _ui.update { it.copy(pendingDelete = null) }

    fun confirmDelete() {
        val name = _ui.value.pendingDelete ?: return
        _ui.update { it.copy(deleting = true) }
        viewModelScope.launch {
            when (val res = repo.deleteEnrolled(name)) {
                is ApiResult.Success -> {
                    _ui.update { it.copy(deleting = false, pendingDelete = null) }
                    refresh()
                }
                is ApiResult.Error -> _ui.update {
                    it.copy(deleting = false, pendingDelete = null, errorMessage = res.message)
                }
            }
        }
    }
}
