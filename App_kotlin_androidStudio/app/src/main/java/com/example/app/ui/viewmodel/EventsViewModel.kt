package com.example.app.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.ApiResult
import com.example.app.data.FaceRepository
import com.example.app.data.ServiceLocator
import com.example.app.network.EventDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Filtro de la lista de eventos. */
enum class EventFilter { ALL, AUTHORIZED, INTRUDERS }

data class EventsUiState(
    val loading: Boolean = true,
    val errorMessage: String? = null,
    val events: List<EventDto> = emptyList(),
    val filter: EventFilter = EventFilter.ALL,
    val baseUrl: String = "",
    val page: Int = 1,
    val total: Int = 0,
    val loadingMore: Boolean = false,
    val clearing: Boolean = false,
) {
    val filtered: List<EventDto>
        get() = when (filter) {
            EventFilter.ALL -> events
            EventFilter.AUTHORIZED -> events.filter { it.match }
            EventFilter.INTRUDERS -> events.filter { !it.match }
        }

    val canLoadMore: Boolean get() = events.size < total
}

class EventsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)
    private val pageSize = 20

    private val _ui = MutableStateFlow(EventsUiState())
    val ui: StateFlow<EventsUiState> = _ui.asStateFlow()

    init {
        viewModelScope.launch {
            val cfg = repo.configFlow.first()
            _ui.update { it.copy(baseUrl = cfg.baseUrl) }
            load(reset = true)
        }
    }

    fun setFilter(filter: EventFilter) = _ui.update { it.copy(filter = filter) }

    fun refresh() = viewModelScope.launch { load(reset = true) }

    fun loadMore() {
        if (_ui.value.loadingMore || !_ui.value.canLoadMore) return
        viewModelScope.launch { load(reset = false) }
    }

    /** Borra TODO el historial de eventos (servidor) y vacía la lista local. */
    fun clearEvents() {
        if (_ui.value.clearing) return
        viewModelScope.launch {
            _ui.update { it.copy(clearing = true, errorMessage = null) }
            when (val res = repo.clearEvents()) {
                is ApiResult.Success -> _ui.update {
                    it.copy(clearing = false, events = emptyList(), total = 0, page = 1)
                }
                is ApiResult.Error -> _ui.update {
                    it.copy(clearing = false, errorMessage = res.message)
                }
            }
        }
    }

    private suspend fun load(reset: Boolean) {
        val nextPage = if (reset) 1 else _ui.value.page + 1
        _ui.update {
            if (reset) it.copy(loading = true, errorMessage = null)
            else it.copy(loadingMore = true)
        }
        when (val res = repo.getEvents(page = nextPage, limit = pageSize)) {
            is ApiResult.Success -> _ui.update {
                val merged = if (reset) res.data.items else it.events + res.data.items
                it.copy(
                    loading = false, loadingMore = false, errorMessage = null,
                    events = merged, page = res.data.page, total = res.data.total,
                )
            }
            is ApiResult.Error -> _ui.update {
                it.copy(loading = false, loadingMore = false, errorMessage = res.message)
            }
        }
    }

    fun photoUrl(photoId: String): String = "${_ui.value.baseUrl}photos/$photoId"
}
