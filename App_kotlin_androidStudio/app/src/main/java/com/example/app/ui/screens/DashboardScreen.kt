package com.example.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.app.navigation.Destination
import com.example.app.ui.components.GhostButton
import com.example.app.ui.components.GoldButton
import com.example.app.ui.components.PremiumCard
import com.example.app.ui.theme.DangerRed
import com.example.app.ui.theme.GoldPrimary
import com.example.app.ui.theme.SuccessGreen
import com.example.app.ui.theme.TextDisabled
import com.example.app.ui.theme.TextSecondary
import com.example.app.ui.viewmodel.DashboardViewModel
import com.example.app.util.Format

@Composable
fun DashboardScreen(
    onNavigate: (Destination) -> Unit,
    vm: DashboardViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()

    PremiumScreen(
        title = "Inicio",
        subtitle = if (ui.connected) (if (ui.armed) "Sistema armado" else "Sistema desarmado") else "Sin conexión",
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp), modifier = Modifier.fillMaxWidth()) {

            ConnectionRow(connected = ui.connected, message = ui.errorMessage)

            PremiumCard(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = "Estado del sistema",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextSecondary,
                )
                Text(
                    text = when {
                        ui.loading -> "Conectando…"
                        !ui.connected -> "Servidor no disponible"
                        ui.armed -> "ARMADO"
                        else -> "DESARMADO"
                    },
                    style = MaterialTheme.typography.headlineMedium,
                    color = when {
                        !ui.connected -> TextDisabled
                        ui.armed -> GoldPrimary
                        else -> MaterialTheme.colorScheme.onSurface
                    },
                    modifier = Modifier.padding(top = 6.dp),
                )
            }

            GoldButton(
                text = if (ui.armed) "Desarmar sistema" else "Armar sistema",
                onClick = { vm.toggleArmed() },
                modifier = Modifier.fillMaxWidth(),
                enabled = ui.connected && !ui.toggling,
            )

            LastEventCard(
                personLabel = ui.lastEvent?.let {
                    if (it.match) it.person else "Intruso"
                },
                isMatch = ui.lastEvent?.match,
                confidence = ui.lastEvent?.confidence,
                timestamp = ui.lastEvent?.ts,
                photoUrl = ui.lastEventPhotoUrl,
            )

            GhostButton(
                text = "Ver eventos",
                onClick = { onNavigate(Destination.Events) },
                modifier = Modifier.fillMaxWidth(),
            )
            GhostButton(
                text = "Personas permitidas",
                onClick = { onNavigate(Destination.People) },
                modifier = Modifier.fillMaxWidth(),
            )
            GhostButton(
                text = "Ajustes",
                onClick = { onNavigate(Destination.Settings) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ConnectionRow(connected: Boolean, message: String?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(RoundedCornerShape(50))
                .background(if (connected) SuccessGreen else DangerRed),
        )
        Text(
            text = if (connected) "Conectado al servidor" else (message ?: "Sin conexión"),
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary,
            modifier = Modifier.padding(start = 8.dp),
        )
    }
}

@Composable
private fun LastEventCard(
    personLabel: String?,
    isMatch: Boolean?,
    confidence: Double?,
    timestamp: String?,
    photoUrl: String?,
) {
    PremiumCard(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = "Último evento",
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary,
        )
        if (personLabel == null) {
            Text(
                text = "Sin eventos registrados",
                style = MaterialTheme.typography.titleMedium,
                color = TextDisabled,
                modifier = Modifier.padding(top = 8.dp),
            )
        } else {
            Row(
                modifier = Modifier.padding(top = 12.dp).fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (photoUrl != null) {
                    AsyncImage(
                        model = photoUrl,
                        contentDescription = "Foto del evento",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .size(64.dp)
                            .clip(RoundedCornerShape(12.dp)),
                    )
                }
                Column(modifier = Modifier.padding(start = if (photoUrl != null) 14.dp else 0.dp)) {
                    Text(
                        text = personLabel,
                        style = MaterialTheme.typography.titleMedium,
                        color = if (isMatch == true) SuccessGreen else DangerRed,
                    )
                    Text(
                        text = "Confianza ${confidence?.let { Format.confidence(it) } ?: "—"}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                    Text(
                        text = Format.timestamp(timestamp),
                        style = MaterialTheme.typography.labelSmall,
                        color = TextSecondary,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                }
            }
        }
    }
}
