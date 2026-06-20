package com.example.app.ui.screens

import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.app.ui.components.GhostButton
import com.example.app.ui.components.GoldButton
import com.example.app.ui.components.PremiumCard
import com.example.app.ui.theme.BorderSubtle
import com.example.app.ui.theme.DangerRed
import com.example.app.ui.theme.GoldPrimary
import com.example.app.ui.theme.SuccessGreen
import com.example.app.ui.theme.TextPrimary
import com.example.app.ui.theme.TextSecondary
import com.example.app.ui.viewmodel.SettingsViewModel
import com.example.app.ui.viewmodel.TestResult

@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    vm: SettingsViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val view = LocalView.current

    // Haptic al obtener el resultado de la prueba de conexión.
    LaunchedEffect(ui.testResult) {
        val constant = when (ui.testResult) {
            TestResult.OK ->
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) HapticFeedbackConstants.CONFIRM
                else HapticFeedbackConstants.LONG_PRESS
            TestResult.FAIL ->
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) HapticFeedbackConstants.REJECT
                else HapticFeedbackConstants.LONG_PRESS
            TestResult.NONE -> null
        }
        constant?.let { view.performHapticFeedback(it) }
    }

    PremiumScreen(title = "Ajustes", subtitle = "Conexión con el servidor", onBack = onBack) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp), modifier = Modifier.fillMaxWidth()) {

            PremiumCard(modifier = Modifier.fillMaxWidth()) {
                Text("Servidor FastAPI", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
                Text(
                    "IP y puerto del servidor de reconocimiento facial en la LAN.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
                )

                OutlinedTextField(
                    value = ui.host,
                    onValueChange = vm::setHost,
                    label = { Text("Dirección IP") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                OutlinedTextField(
                    value = ui.port,
                    onValueChange = vm::setPort,
                    label = { Text("Puerto") },
                    singleLine = true,
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    colors = fieldColors(),
                )
            }

            GoldButton(text = "Guardar", onClick = { vm.save() }, modifier = Modifier.fillMaxWidth())
            GhostButton(
                text = if (ui.testing) "Probando…" else "Probar conexión",
                onClick = { vm.testConnection() },
                modifier = Modifier.fillMaxWidth(),
                enabled = !ui.testing,
            )

            if (ui.saved) {
                Text("Configuración guardada.", color = TextSecondary, style = MaterialTheme.typography.labelSmall)
            }
            ui.testMessage?.let { msg ->
                Text(
                    text = msg,
                    color = if (ui.testResult == TestResult.OK) SuccessGreen else DangerRed,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            PremiumCard(modifier = Modifier.fillMaxWidth()) {
                Text("Notificaciones push (FCM)", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
                Text(
                    "Pendiente: requiere google-services.json de Firebase (Fase 9).",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = GoldPrimary,
    unfocusedBorderColor = BorderSubtle,
    focusedLabelColor = GoldPrimary,
    unfocusedLabelColor = TextSecondary,
    cursorColor = GoldPrimary,
    focusedTextColor = TextPrimary,
    unfocusedTextColor = TextPrimary,
)
