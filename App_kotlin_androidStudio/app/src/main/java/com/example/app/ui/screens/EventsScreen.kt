package com.example.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.app.network.EventDto
import com.example.app.ui.components.PremiumCard
import com.example.app.ui.theme.BlackAbsolute
import com.example.app.ui.theme.BlackElevated
import com.example.app.ui.theme.DangerRed
import com.example.app.ui.theme.GoldPrimary
import com.example.app.ui.theme.SuccessGreen
import com.example.app.ui.theme.TextDisabled
import com.example.app.ui.theme.TextPrimary
import com.example.app.ui.theme.TextSecondary
import com.example.app.ui.viewmodel.EventFilter
import com.example.app.ui.viewmodel.EventsViewModel
import com.example.app.util.Format

@Composable
fun EventsScreen(
    onBack: () -> Unit,
    vm: EventsViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    var preview by remember { mutableStateOf<EventDto?>(null) }
    var showClearConfirm by remember { mutableStateOf(false) }

    PremiumScreen(title = "Eventos", subtitle = "Historial de detecciones", onBack = onBack) {
        Column(modifier = Modifier.fillMaxSize()) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                FilterChips(selected = ui.filter, onSelect = vm::setFilter)
                if (ui.events.isNotEmpty()) {
                    Text(
                        text = if (ui.clearing) "Borrando…" else "Borrar eventos",
                        style = MaterialTheme.typography.labelLarge,
                        color = DangerRed,
                        modifier = Modifier
                            .clickable(enabled = !ui.clearing) { showClearConfirm = true }
                            .padding(8.dp),
                    )
                }
            }

            when {
                ui.loading -> CenteredBox { CircularProgressIndicator(color = GoldPrimary) }
                ui.errorMessage != null -> CenteredBox {
                    Text(ui.errorMessage!!, color = DangerRed, style = MaterialTheme.typography.bodyMedium)
                }
                ui.filtered.isEmpty() -> CenteredBox {
                    Text("No hay eventos para este filtro.", color = TextDisabled)
                }
                else -> LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize().padding(top = 16.dp),
                ) {
                    items(ui.filtered, key = { it.id }) { event ->
                        EventCard(
                            event = event,
                            photoUrl = vm.photoUrl(event.photo_id),
                            onClick = { preview = event },
                        )
                    }
                    if (ui.canLoadMore) {
                        item {
                            Box(
                                modifier = Modifier.fillMaxWidth().padding(16.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    text = if (ui.loadingMore) "Cargando…" else "Cargar más",
                                    color = GoldPrimary,
                                    style = MaterialTheme.typography.labelLarge,
                                    modifier = Modifier.clickable { vm.loadMore() },
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    preview?.let { ev ->
        PhotoPreviewDialog(
            photoUrl = vm.photoUrl(ev.photo_id),
            label = if (ev.match) ev.person else "Intruso",
            onDismiss = { preview = null },
        )
    }

    if (showClearConfirm) {
        AlertDialog(
            onDismissRequest = { showClearConfirm = false },
            containerColor = BlackElevated,
            title = { Text("Borrar eventos", color = TextPrimary) },
            text = {
                Text(
                    "Se eliminará TODO el historial de eventos y sus fotos del " +
                        "servidor. Esta acción no se puede deshacer.",
                    color = TextSecondary,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showClearConfirm = false
                    vm.clearEvents()
                }) { Text("Borrar", color = DangerRed) }
            },
            dismissButton = {
                TextButton(onClick = { showClearConfirm = false }) {
                    Text("Cancelar", color = TextSecondary)
                }
            },
        )
    }
}

@Composable
private fun FilterChips(selected: EventFilter, onSelect: (EventFilter) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip("Todos", selected == EventFilter.ALL) { onSelect(EventFilter.ALL) }
        FilterChip("Autorizados", selected == EventFilter.AUTHORIZED) { onSelect(EventFilter.AUTHORIZED) }
        FilterChip("Intrusos", selected == EventFilter.INTRUDERS) { onSelect(EventFilter.INTRUDERS) }
    }
}

@Composable
private fun FilterChip(label: String, active: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(if (active) GoldPrimary else BlackElevated)
            .clickable { onClick() }
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = if (active) BlackAbsolute else TextSecondary,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

@Composable
private fun EventCard(event: EventDto, photoUrl: String, onClick: () -> Unit) {
    PremiumCard(modifier = Modifier.fillMaxWidth().clickable { onClick() }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            AsyncImage(
                model = photoUrl,
                contentDescription = "Foto del evento",
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(56.dp).clip(RoundedCornerShape(10.dp)),
            )
            Column(modifier = Modifier.padding(start = 14.dp).fillMaxWidth()) {
                Text(
                    text = if (event.match) event.person else "Intruso",
                    style = MaterialTheme.typography.titleMedium,
                    color = if (event.match) SuccessGreen else DangerRed,
                )
                Text(
                    text = "Confianza ${Format.confidence(event.confidence)}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    modifier = Modifier.padding(top = 2.dp),
                )
                Text(
                    text = Format.timestamp(event.ts),
                    style = MaterialTheme.typography.labelSmall,
                    color = TextSecondary,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }
    }
}

@Composable
private fun PhotoPreviewDialog(photoUrl: String, label: String, onDismiss: () -> Unit) {
    androidx.compose.ui.window.Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .clip(RoundedCornerShape(16.dp))
                .background(BlackElevated)
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            AsyncImage(
                model = photoUrl,
                contentDescription = "Foto ampliada",
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp)),
            )
            Text(
                text = label,
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
                modifier = Modifier.padding(top = 14.dp),
            )
            Text(
                text = "Tocar fuera para cerrar",
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun CenteredBox(content: @Composable () -> Unit) {
    Box(
        modifier = Modifier.fillMaxSize().padding(top = 48.dp),
        contentAlignment = Alignment.TopCenter,
    ) { content() }
}
