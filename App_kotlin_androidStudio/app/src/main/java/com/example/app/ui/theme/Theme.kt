package com.example.app.ui.theme

import android.app.Activity
import android.os.Build
import android.view.WindowManager
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val PremiumDarkColorScheme = darkColorScheme(
    primary = GoldPrimary,
    onPrimary = BlackAbsolute,
    primaryContainer = GoldSecondary,
    onPrimaryContainer = BlackAbsolute,

    secondary = GoldSecondary,
    onSecondary = BlackAbsolute,
    secondaryContainer = SurfaceCard,
    onSecondaryContainer = TextPrimary,

    tertiary = GoldSecondary,
    onTertiary = BlackAbsolute,

    background = BlackAbsolute,
    onBackground = TextPrimary,

    surface = BlackElevated,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceCard,
    onSurfaceVariant = TextSecondary,

    outline = BorderSubtle,
    outlineVariant = BorderSubtle,

    error = DangerRed,
    onError = TextPrimary,
)

@Composable
fun AppTheme(
    content: @Composable () -> Unit,
) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            // Edge-to-edge: el contenido pinta detrás de status/navigation bar.
            WindowCompat.setDecorFitsSystemWindows(window, false)
            window.statusBarColor = Color.Transparent.toArgb()
            window.navigationBarColor = Color.Transparent.toArgb()
            val controller = WindowCompat.getInsetsController(window, view)
            // Sobre fondo negro, los íconos del sistema deben ser claros (no dark).
            controller.isAppearanceLightStatusBars = false
            controller.isAppearanceLightNavigationBars = false
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                window.isNavigationBarContrastEnforced = false
            }
            @Suppress("DEPRECATION")
            window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
        }
    }

    MaterialTheme(
        colorScheme = PremiumDarkColorScheme,
        typography = Typography,
        shapes = Shapes,
        content = content,
    )
}
