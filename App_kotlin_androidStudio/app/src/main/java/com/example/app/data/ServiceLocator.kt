package com.example.app.data

import android.content.Context

/**
 * Service locator mínimo (sin DI framework) para compartir un único
 * [FaceRepository] con todos los ViewModels.
 */
object ServiceLocator {
    @Volatile
    private var repo: FaceRepository? = null

    fun repository(context: Context): FaceRepository {
        return repo ?: synchronized(this) {
            repo ?: FaceRepository(SettingsDataStore(context.applicationContext)).also { repo = it }
        }
    }
}
