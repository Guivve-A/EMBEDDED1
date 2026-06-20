package com.example.app.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.ApiResult
import com.example.app.data.FaceRepository
import com.example.app.data.ServiceLocator
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class TestResult { NONE, OK, FAIL }

data class SettingsUiState(
    val host: String = "",
    val port: String = "",
    val saved: Boolean = false,
    val testing: Boolean = false,
    val testResult: TestResult = TestResult.NONE,
    val testMessage: String? = null,
)

class SettingsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo: FaceRepository = ServiceLocator.repository(app)

    private val _ui = MutableStateFlow(SettingsUiState())
    val ui: StateFlow<SettingsUiState> = _ui.asStateFlow()

    init {
        viewModelScope.launch {
            val cfg = repo.configFlow.first()
            _ui.update { it.copy(host = cfg.host, port = cfg.port) }
        }
    }

    fun setHost(value: String) = _ui.update { it.copy(host = value, saved = false, testResult = TestResult.NONE) }
    fun setPort(value: String) = _ui.update { it.copy(port = value.filter { c -> c.isDigit() }, saved = false, testResult = TestResult.NONE) }

    fun save() {
        viewModelScope.launch {
            repo.saveConfig(_ui.value.host.trim(), _ui.value.port.trim())
            _ui.update { it.copy(saved = true) }
        }
    }

    /** Guarda la config y prueba la conexión con GET /state. */
    fun testConnection() {
        _ui.update { it.copy(testing = true, testResult = TestResult.NONE, testMessage = null) }
        viewModelScope.launch {
            repo.saveConfig(_ui.value.host.trim(), _ui.value.port.trim())
            when (val res = repo.getState()) {
                is ApiResult.Success -> _ui.update {
                    it.copy(testing = false, saved = true, testResult = TestResult.OK,
                        testMessage = "Conexión correcta. Sistema ${if (res.data.armed) "armado" else "desarmado"}.")
                }
                is ApiResult.Error -> _ui.update {
                    it.copy(testing = false, testResult = TestResult.FAIL, testMessage = res.message)
                }
            }
        }
    }
}
