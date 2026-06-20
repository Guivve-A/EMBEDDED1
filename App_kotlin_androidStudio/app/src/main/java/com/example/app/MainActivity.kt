package com.example.app

import android.Manifest
import android.graphics.Color as AndroidColor
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.lifecycleScope
import com.example.app.fcm.FcmManager
import com.example.app.fcm.MyFirebaseMessagingService
import com.example.app.navigation.AppNavGraph
import com.example.app.ui.theme.AppTheme
import com.example.app.ui.theme.BlackAbsolute
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    // Solicitud de permiso POST_NOTIFICATIONS (Android 13+). Tras la respuesta,
    // intentamos registrar el token FCM de todas formas (el registro no depende del permiso).
    private val notifPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        registerFcm()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
        )

        // Canal de notificaciones de alta prioridad (debe existir antes de cualquier push).
        MyFirebaseMessagingService.createChannel(this)

        // ¿Se abrió desde el tap de una notificación FCM? (deeplink app://events)
        val openedFromNotification = intent?.data?.host == "events"

        setContent {
            AppTheme {
                AppNavGraph(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(BlackAbsolute),
                    deeplinkToEvents = openedFromNotification,
                )

                // Pide permiso de notificaciones y registra el token al arrancar.
                LaunchedEffect(Unit) {
                    requestNotificationPermissionIfNeeded()
                }
            }
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
            if (!granted) {
                notifPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                return
            }
        }
        // En <13, o si ya estaba concedido, registramos directamente.
        registerFcm()
    }

    private fun registerFcm() {
        lifecycleScope.launch {
            FcmManager.registerToken(applicationContext)
        }
    }
}
