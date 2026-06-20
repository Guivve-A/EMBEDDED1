package com.example.app.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.ApiResult
import com.example.app.data.FaceRepository
import com.example.app.data.ServiceLocator
import com.example.app.network.EventDto
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Estado de la pantalla Inicio. */
data class DashboardUiState(
    val armed: Boolean = false,
    val connected: Boolean = false,
    val loading: Boolean = true,
    val toggling: Boolean = false,
    val errorMessage: String? = null,
    val lastEvent: EventDto? = null,
    val lastEventPhotoUrl: String? = null,
)

class DashboardViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)

    private val _ui = MutableStateFlow(DashboardUiState())
    val ui: StateFlow<DashboardUiState> = _ui.asStateFlow()

    init {
        startPolling()
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (true) {
                refresh()
                delay(2000)  // refresco rápido: muestra el resultado casi al instante
            }
        }
    }

    suspend fun refresh() {
        when (val state = repo.getState()) {
            is ApiResult.Success -> {
                _ui.update { it.copy(armed = state.data.armed, connected = true, loading = false, errorMessage = null) }
                loadLastEvent()
            }
            is ApiResult.Error -> _ui.update {
                it.copy(connected = false, loading = false, errorMessage = state.message)
            }
        }
    }

    private suspend fun loadLastEvent() {
        when (val res = repo.getEvents(page = 1, limit = 1)) {
            is ApiResult.Success -> {
                val ev = res.data.items.firstOrNull()
                val url = ev?.let { repo.photoUrl(it.photo_id) }
                _ui.update { it.copy(lastEvent = ev, lastEventPhotoUrl = url) }
            }
            is ApiResult.Error -> { /* mantiene el último evento conocido */ }
        }
    }

    fun toggleArmed() {
        val target = !_ui.value.armed
        _ui.update { it.copy(toggling = true) }
        viewModelScope.launch {
            when (val res = repo.setArmed(target)) {
                is ApiResult.Success -> _ui.update {
                    it.copy(armed = res.data, toggling = false, connected = true, errorMessage = null)
                }
                is ApiResult.Error -> _ui.update {
                    it.copy(toggling = false, errorMessage = res.message)
                }
            }
        }
    }
}
