package com.example.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

// DataStore Preferences para persistir la IP y el puerto del servidor FastAPI.
private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

/** Config de conexión hacia el servidor. */
data class ServerConfig(
    val host: String,
    val port: String,
) {
    /** BASE_URL para Retrofit (siempre con slash final). */
    val baseUrl: String get() = "http://$host:$port/"
}

class SettingsDataStore(private val context: Context) {

    private object Keys {
        val HOST = stringPreferencesKey("server_host")
        val PORT = stringPreferencesKey("server_port")
    }

    companion object {
        const val DEFAULT_HOST = "192.168.100.21"
        const val DEFAULT_PORT = "8000"
    }

    val config: Flow<ServerConfig> = context.dataStore.data.map { prefs ->
        ServerConfig(
            host = prefs[Keys.HOST] ?: DEFAULT_HOST,
            port = prefs[Keys.PORT] ?: DEFAULT_PORT,
        )
    }

    suspend fun save(host: String, port: String) {
        context.dataStore.edit { prefs ->
            prefs[Keys.HOST] = host.trim()
            prefs[Keys.PORT] = port.trim()
        }
    }
}
